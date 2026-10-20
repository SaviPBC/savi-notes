"""Savi Notes engine.

Owns everything the Notes window does to the vault: reading and writing
notes, tags, renames that keep [[links]] intact, hybrid search (words plus
local embeddings from llama.cpp) and the background sync with the AI Core
(sync.py).

  python -m savi_notes.engine serve VAULT            JSON lines on stdin/stdout (the app)
  python -m savi_notes.engine search VAULT QUERY...  print ranked notes (CLI, agents)
  python -m savi_notes.engine index VAULT            bring the embedding index up to date

Requests are {"id": n, "op": ..., ...}; every request gets one reply with
the same id. Events the app did not ask for ({"event": ...}) report index
progress, sync results, notes changed on disk (by a pull or another program), and assets (remote
images, math, diagrams) finished in the background.
"""

import datetime
import hashlib
import json
import os
import queue
import re
import shutil
import signal
import socket
import sqlite3
import struct
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request

import numpy as np

from . import account, config, llama, mathsvg
from .sync import Sync

try:
  from send2trash import send2trash
except ImportError:  # pragma: no cover
  send2trash = None

# Child processes on Windows get no console window of their own.
NO_WINDOW = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}

MODEL_NAME = "nomic-embed-text-v1.5.Q8_0.gguf"
MODEL_URL = "https://huggingface.co/nomic-ai/nomic-embed-text-v1.5-GGUF/resolve/main/" + MODEL_NAME
MODEL_SIZE = 146146432
MODEL_PATH = os.path.join(config.data_dir(), "models", MODEL_NAME)

CHUNK_CHARS = 1200
WATCH_INTERVAL = 2

FRONTMATTER = re.compile(r"\A---\n(.*?\n)?---\n?", re.S)
FENCE = re.compile(r"^(```|~~~)")
INLINE_CODE = re.compile(r"`[^`\n]*`")
# Not after \ (escaped), ( or [ (a link's #heading target), or inside a word or URL.
TAG_LEAD = r"(?<![\w&/#\\(\[])"
TAG = re.compile(TAG_LEAD + r"#([A-Za-z][\w/-]*)")
WIKILINK = re.compile(r"(!?)\[\[([^\]\n|#]+)(#[^\]\n|]*)?(\|[^\]\n]*)?\]\]")
WORD = re.compile(r"\w+", re.U)

out_lock = threading.Lock()


def emit(message):
  with out_lock:
    try:
      sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
      sys.stdout.flush()
    except OSError:
      pass  # the window is gone


# ------------------------------------------------------------------ parsing

def split_frontmatter(text):
  match = FRONTMATTER.match(text)
  if not match:
    return "", text
  return match.group(1) or "", text[match.end():]


def frontmatter_tags(meta):
  """Tags from a frontmatter block: `tags: [a, b]`, `tags: a b` or a list."""
  lines = meta.split("\n")
  for i, line in enumerate(lines):
    m = re.match(r"^(tags|tag)\s*:\s*(.*)$", line)
    if not m:
      continue
    value = m.group(2).strip()
    if value:
      value = value.strip("[]")
      return clean_tags(re.split(r"[,\s]+", value))
    items = []
    for item in lines[i + 1:]:
      im = re.match(r"^\s*-\s*(.*)$", item)
      if not im:
        break
      items.append(im.group(1))
    return clean_tags(items)
  return []


def clean_tags(items):
  tags = []
  for item in items:
    tag = item.strip().strip("'\"").lstrip("#").lower()
    if tag and tag not in tags:
      tags.append(tag)
  return tags


def set_frontmatter_tags(meta, tags):
  """Replace the tags entry in a frontmatter block, keeping every other key."""
  lines = meta.split("\n") if meta else []
  kept = []
  skipping = False
  for line in lines:
    if skipping:
      if re.match(r"^\s*-\s*", line):
        continue
      skipping = False
    if re.match(r"^(tags|tag)\s*:", line):
      skipping = True
      continue
    kept.append(line)
  while kept and not kept[-1].strip():
    kept.pop()
  if tags:
    kept.insert(0, "tags: [" + ", ".join(tags) + "]")
  return "\n".join(kept)


def join_note(meta, body):
  meta = meta.strip("\n")
  if not meta:
    return body
  return "---\n" + meta + "\n---\n" + body


def prose_lines(body):
  """Lines outside fenced code, with inline code removed."""
  fenced = False
  for line in body.split("\n"):
    if FENCE.match(line.strip()):
      fenced = not fenced
      continue
    if not fenced:
      yield INLINE_CODE.sub("", line)


def inline_tags(body):
  tags = []
  for line in prose_lines(body):
    for tag in TAG.findall(line):
      tag = tag.lower().rstrip("/-")
      if tag not in tags:
        tags.append(tag)
  return tags


def snippet_of(body):
  fenced = False
  for line in body.split("\n"):
    if FENCE.match(line.strip()):
      fenced = not fenced
      continue
    if fenced:
      continue
    text = line.strip()
    if not text or text.startswith(("#", "---", "![[", "|", ">")) and not text.startswith("> "):
      continue
    if re.match(r">\s*\[!", text):  # a callout's title line, not its text
      continue
    text = re.sub(r"^(>\s*)+", "", text)
    text = re.sub(r"^([-*+]|\d+\.)\s+(\[[ xX]\]\s+)?", "", text)
    text = WIKILINK.sub(lambda m: (m.group(4) or "|" + m.group(2))[1:], text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[*_~`]+|==", "", text).strip()
    if text:
      return text[:200]
  return ""


def link_targets(body):
  return sorted({m.group(2).strip().split("/")[-1].lower() for m in WIKILINK.finditer(body) if not m.group(1)})


def image_size(path):
  """Pixel size of a png, gif, jpeg or webp from its header; (0, 0) otherwise."""
  try:
    with open(path, "rb") as f:
      head = f.read(32)
      if head[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", head[16:24])
      if head[:6] in (b"GIF87a", b"GIF89a"):
        return struct.unpack("<HH", head[6:10])
      if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        kind = head[12:16]
        if kind == b"VP8X":
          return (int.from_bytes(head[24:27], "little") + 1, int.from_bytes(head[27:30], "little") + 1)
        if kind == b"VP8L":
          bits = int.from_bytes(head[21:25], "little")
          return ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
        if kind == b"VP8 ":
          w, h = struct.unpack("<HH", head[26:30])
          return (w & 0x3FFF, h & 0x3FFF)
      if head[:2] == b"\xff\xd8":
        f.seek(2)
        while True:
          marker = f.read(2)
          if len(marker) < 2 or marker[0] != 0xFF:
            break
          length = struct.unpack(">H", f.read(2))[0]
          if marker[1] in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            h, w = struct.unpack(">xHH", f.read(5))
            return (w, h)
          f.seek(length - 2, 1)
  except (OSError, struct.error):
    pass
  return (0, 0)


# ------------------------------------------------------------------ vault

class Vault:
  def __init__(self, root):
    self.root = os.path.realpath(os.path.expanduser(root))
    self.lock = threading.RLock()
    self.notes = {}

  def path_of(self, rel):
    path = os.path.realpath(os.path.join(self.root, rel))
    if not path.startswith(self.root + os.sep):
      raise ValueError("outside the vault: " + rel)
    return path

  def walk(self):
    for dirpath, dirnames, filenames in os.walk(self.root):
      dirnames[:] = [d for d in dirnames if not d.startswith(".")]
      for name in filenames:
        if name.endswith(".md") and not name.startswith("."):
          yield os.path.relpath(os.path.join(dirpath, name), self.root)

  def describe(self, rel, text, stat):
    meta, body = split_frontmatter(text)
    own = frontmatter_tags(meta)
    found = inline_tags(body)
    return {
      "path": rel,
      "title": os.path.basename(rel)[:-3],
      "tags": own + [t for t in found if t not in own],
      "ownTags": own,
      "mtime": int(stat.st_mtime),
      "size": stat.st_size,
      "snippet": snippet_of(body),
      "links": link_targets(body),
      "body": body,
    }

  def scan(self):
    """Re-read notes whose size or mtime changed. Returns True if anything did."""
    with self.lock:
      seen = set()
      changed = False
      for rel in self.walk():
        seen.add(rel)
        try:
          stat = os.stat(os.path.join(self.root, rel))
        except OSError:
          continue
        known = self.notes.get(rel)
        if known and known["mtime"] == int(stat.st_mtime) and known["size"] == stat.st_size:
          continue
        try:
          with open(os.path.join(self.root, rel), encoding="utf-8", errors="replace") as f:
            text = f.read()
        except OSError:
          continue
        self.notes[rel] = self.describe(rel, text, stat)
        changed = True
      for rel in list(self.notes):
        if rel not in seen:
          del self.notes[rel]
          changed = True
      return changed

  def refresh(self, rel):
    with self.lock:
      path = os.path.join(self.root, rel)
      try:
        stat = os.stat(path)
        with open(path, encoding="utf-8", errors="replace") as f:
          self.notes[rel] = self.describe(rel, f.read(), stat)
      except OSError:
        self.notes.pop(rel, None)

  def listing(self):
    with self.lock:
      notes = [{k: v for k, v in n.items() if k != "body"} for n in self.notes.values()]
    backlinks = {}
    for note in notes:
      for target in note["links"]:
        backlinks.setdefault(target, []).append(note["path"])
    for note in notes:
      note["backlinks"] = sorted(p for p in backlinks.get(note["title"].lower(), []) if p != note["path"])
    notes.sort(key=lambda n: -n["mtime"])
    return notes

  def by_title(self, title):
    want = title.strip().lower()
    with self.lock:
      for rel, note in self.notes.items():
        if note["title"].lower() == want:
          return rel
    return None

  def read(self, rel):
    with open(self.path_of(rel), encoding="utf-8", errors="replace") as f:
      text = f.read()
    meta, body = split_frontmatter(text)
    return {"path": rel, "body": body, "tags": frontmatter_tags(meta), "embeds": self.embeds(body)}

  def embeds(self, body):
    """Files embedded in a note, with pixel sizes for images."""
    found = {}
    names = [m.group(2).strip() for m in WIKILINK.finditer(body) if m.group(1)]
    names += [urllib.parse.unquote(m) for m in re.findall(r"!\[[^\]]*\]\(([^)\s]+)", body) if not m.startswith("http")]
    for name in names:
      if name in found:
        continue
      path = self.attachment(name)
      if path and not path.endswith(".md"):
        width, height = image_size(path)
        found[name] = {"file": path, "width": width, "height": height}
    return found

  def write_text(self, rel, text):
    path = self.path_of(rel)
    tmp = path + ".savi-tmp"
    with open(tmp, "w", encoding="utf-8") as f:
      f.write(text)
    os.replace(tmp, path)
    self.refresh(rel)

  def save(self, rel, body=None, tags=None):
    path = self.path_of(rel)
    try:
      with open(path, encoding="utf-8", errors="replace") as f:
        meta, old_body = split_frontmatter(f.read())
    except FileNotFoundError:
      meta, old_body = "", ""
    if tags is not None:
      meta = set_frontmatter_tags(meta, clean_tags(tags))
    self.write_text(rel, join_note(meta, old_body if body is None else body))

  def safe_title(self, title):
    title = re.sub(r"[/\\\x00-\x1f]", "-", title).strip().strip(".")
    return title or "Untitled"

  def free_name(self, title, current=None):
    base = self.safe_title(title)
    name = base + ".md"
    n = 2
    while os.path.exists(os.path.join(self.root, name)) and name != current:
      name = "%s %d.md" % (base, n)
      n += 1
    return name

  def create(self, title, tags, body):
    rel = self.free_name(title)
    meta = "created: " + datetime.date.today().isoformat()
    meta = set_frontmatter_tags(meta, clean_tags(tags or []))
    self.write_text(rel, join_note(meta, body or ""))
    return rel

  def rename(self, rel, title):
    old_title = os.path.basename(rel)[:-3]
    new_rel = os.path.join(os.path.dirname(rel), self.free_name(title, os.path.basename(rel)))
    if new_rel == rel:
      return rel, 0
    os.rename(self.path_of(rel), os.path.join(self.root, new_rel))
    with self.lock:
      self.notes.pop(rel, None)
    self.refresh(new_rel)
    new_title = os.path.basename(new_rel)[:-3]
    pattern = re.compile(r"(!?\[\[)" + re.escape(old_title) + r"((?:#[^\]\n|]*)?(?:\|[^\]\n]*)?\]\])", re.I)
    updated = 0
    for other in list(self.walk()):
      path = os.path.join(self.root, other)
      with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
      fixed = pattern.sub(lambda m: m.group(1) + new_title + m.group(2), text)
      if fixed != text:
        self.write_text(other, fixed)
        updated += 1
    return new_rel, updated

  def delete(self, rel):
    path = self.path_of(rel)
    try:
      if not send2trash:
        raise OSError("no trash")
      send2trash(path)
    except Exception:
      os.remove(path)
    with self.lock:
      self.notes.pop(rel, None)

  def attach(self, source):
    """Copy a file into Attachments/ and return the name to embed it by.
    A file already in the vault is embedded where it is."""
    source = os.path.realpath(source)
    if source.startswith(os.path.realpath(self.root) + os.sep):
      return os.path.basename(source)
    folder = os.path.join(self.root, "Attachments")
    os.makedirs(folder, exist_ok=True)
    stem, ext = os.path.splitext(os.path.basename(source))
    name, n = stem + ext, 1
    while os.path.exists(os.path.join(folder, name)):
      name = "%s %d%s" % (stem, n, ext)
      n += 1
    shutil.copyfile(source, os.path.join(folder, name))
    return name

  def import_folder(self, source):
    """Copy another vault in: an Obsidian vault, Wolfen Notes, or an export. Notes don't
    live in folders here, so a note's folders become its tags. A title already taken gets
    a number, and the imported notes' links to it follow, since that is what they meant."""
    source = os.path.realpath(os.path.expanduser(source))
    if source == self.root or source.startswith(self.root + os.sep) or self.root.startswith(source + os.sep):
      raise ValueError("choose a folder outside Savi Notes' own")
    taken = {n["title"].lower() for n in self.notes.values()}
    renamed, imported, files = {}, [], 0
    for dirpath, dirnames, filenames in os.walk(source):
      dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
      folders = [] if dirpath == source else os.path.relpath(dirpath, source).split(os.sep)
      for name in sorted(filenames):
        path = os.path.join(dirpath, name)
        if name.startswith("."):
          continue
        if not name.endswith(".md"):
          files += self.import_file(path)
          continue
        with open(path, encoding="utf-8", errors="replace") as f:
          meta, body = split_frontmatter(f.read())
        tags = clean_tags(re.sub(r"[^\w/-]+", "-", folder.lower()).strip("-") for folder in folders)
        if tags:
          own = frontmatter_tags(meta)
          meta = set_frontmatter_tags(meta, own + [t for t in tags if t not in own])
        rel = self.free_name(name[:-3])
        if rel[:-3] != name[:-3] and name[:-3].lower() in taken and name[:-3] not in renamed:
          renamed[name[:-3]] = rel[:-3]
        self.write_text(rel, join_note(meta, body))
        imported.append(rel)
    for old, new in renamed.items():
      pattern = re.compile(r"(!?\[\[)" + re.escape(old) + r"((?:#[^\]\n|]*)?(?:\|[^\]\n]*)?\]\])", re.I)
      for rel in imported:
        with open(self.path_of(rel), encoding="utf-8") as f:
          text = f.read()
        fixed = pattern.sub(lambda m: m.group(1) + new + m.group(2), text)
        if fixed != text:
          self.write_text(rel, fixed)
    return {"notes": len(imported), "files": files, "renamed": len(renamed)}

  def import_file(self, source):
    """An attachment, into Attachments/; one already there with the same bytes isn't copied twice."""
    folder = os.path.join(self.root, "Attachments")
    os.makedirs(folder, exist_ok=True)
    stem, ext = os.path.splitext(os.path.basename(source))
    name, n = stem + ext, 2
    with open(source, "rb") as f:
      data = f.read()
    while os.path.exists(os.path.join(folder, name)):
      with open(os.path.join(folder, name), "rb") as f:
        if f.read() == data:
          return 0
      name = "%s %d%s" % (stem, n, ext)
      n += 1
    with open(os.path.join(folder, name), "wb") as f:
      f.write(data)
    return 1

  def untag(self, rel, tag):
    """Take a tag off a note: out of its frontmatter, and #tag written in the text back to the
    plain word, outside code, so it stops counting as a tag."""
    with open(self.path_of(rel), encoding="utf-8", errors="replace") as f:
      meta, body = split_frontmatter(f.read())
    meta = set_frontmatter_tags(meta, [t for t in frontmatter_tags(meta) if t != tag])
    written = re.compile(TAG_LEAD + r"#(" + re.escape(tag) + r")(?![\w/-])", re.I)
    lines, fenced = [], False
    for line in body.split("\n"):
      if FENCE.match(line.strip()):
        fenced = not fenced
      elif not fenced:
        parts = re.split(r"(`[^`\n]*`)", line)
        line = "".join(p if i % 2 else written.sub(r"\1", p) for i, p in enumerate(parts))
      lines.append(line)
    self.write_text(rel, join_note(meta, "\n".join(lines)))

  def attachment(self, name):
    """Absolute path of an embedded file, found by name like Obsidian does."""
    name = name.strip()
    direct = os.path.join(self.root, name)
    if os.path.isfile(direct):
      return direct
    base = os.path.basename(name)
    for dirpath, dirnames, filenames in os.walk(self.root):
      dirnames[:] = [d for d in dirnames if not d.startswith(".")]
      if base in filenames:
        return os.path.join(dirpath, base)
    return ""


# ------------------------------------------------------------------ embeddings

class SemanticOff(Exception):
  """Meaning search is turned off in the settings."""


def free_port():
  with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    return s.getsockname()[1]


class Embedder:
  """llama-server with the embedding model, started on first use."""

  def __init__(self):
    self.proc = None
    self.url = ""
    self.lock = threading.Lock()
    self.state = "idle"
    self.error = ""
    self.spawner = None

  def spawn(self, argv):
    # The engine stops it on the way out; it exits with the window.
    return subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **NO_WINDOW)

  def available(self):
    return bool(llama.server_path())

  def ensure_model(self, progress):
    if os.path.exists(MODEL_PATH):
      return
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    part = MODEL_PATH + ".part"
    self.state = "downloading"
    with urllib.request.urlopen(MODEL_URL, timeout=30) as response, open(part, "wb") as f:
      total = int(response.headers.get("Content-Length") or MODEL_SIZE)
      done = 0
      last = 0
      while True:
        block = response.read(1 << 20)
        if not block:
          break
        f.write(block)
        done += len(block)
        if time.time() - last > 0.5:
          progress(done, total)
          last = time.time()
    if os.path.getsize(part) < total:
      raise RuntimeError("the model download was cut short")
    os.replace(part, MODEL_PATH)

  def start(self, progress):
    with self.lock:
      if self.proc and self.proc.poll() is None:
        return
      if not config.load().get("semantic", True):
        raise SemanticOff("meaning search is off")
      server = llama.ensure_server(progress)
      self.ensure_model(progress)
      self.state = "starting"
      port = free_port()
      self.proc = self.spawn(
        [server, "-m", MODEL_PATH, "--embeddings", "--pooling", "mean",
         "--host", "127.0.0.1", "--port", str(port), "-c", "8192", "-b", "2048", "-ub", "2048",
         "--parallel", "4", "--log-disable"])
      self.url = "http://127.0.0.1:%d" % port
      deadline = time.time() + 60
      while time.time() < deadline:
        if self.proc.poll() is not None:
          raise RuntimeError("llama-server exited while starting")
        try:
          with urllib.request.urlopen(self.url + "/health", timeout=2) as r:
            if r.status == 200:
              self.state = "ready"
              return
        except Exception:
          time.sleep(0.25)
      raise RuntimeError("llama-server did not start")

  def embed(self, texts):
    payload = json.dumps({"input": texts}).encode()
    request = urllib.request.Request(self.url + "/v1/embeddings", payload, {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=120) as r:
      data = json.load(r)["data"]
    vectors = np.array([d["embedding"] for d in sorted(data, key=lambda d: d["index"])], dtype=np.float32)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.maximum(norms, 1e-9)

  def stop(self):
    if self.proc and self.proc.poll() is None:
      self.proc.terminate()
      try:
        self.proc.wait(5)
      except subprocess.TimeoutExpired:
        self.proc.kill()


def chunks_of(title, body):
  """Paragraph-aligned pieces of a note, each prefixed with its title."""
  parts = []
  current = ""
  for block in re.split(r"\n\s*\n", body):
    block = block.strip()
    if not block:
      continue
    while len(block) > CHUNK_CHARS:
      cut = block.rfind(" ", 0, CHUNK_CHARS)
      cut = cut if cut > CHUNK_CHARS // 2 else CHUNK_CHARS
      parts.append(block[:cut])
      block = block[cut:].strip()
    if current and len(current) + len(block) > CHUNK_CHARS:
      parts.append(current)
      current = ""
    current = (current + "\n\n" + block).strip()
  if current:
    parts.append(current)
  return parts or [""]


class Index:
  """Chunk embeddings in sqlite, mirrored into one matrix for search."""

  def __init__(self, vault, embedder):
    self.vault = vault
    self.embedder = embedder
    key = hashlib.sha1(vault.root.encode()).hexdigest()[:12]
    folder = os.path.join(config.cache_dir(), "index")
    os.makedirs(folder, exist_ok=True)
    self.db = sqlite3.connect(os.path.join(folder, key + ".sqlite"), check_same_thread=False)
    self.db.execute("create table if not exists notes (path text primary key, stamp text, model text)")
    self.db.execute("create table if not exists chunks (path text, ord int, text text, vec blob)")
    self.db.execute("create index if not exists chunks_path on chunks(path)")
    self.lock = threading.Lock()
    self.running = threading.Lock()
    self.load()

  def load(self):
    with self.lock:
      rows = self.db.execute("select path, text, vec from chunks order by path, ord").fetchall()
      self.paths = [r[0] for r in rows]
      self.texts = [r[1] for r in rows]
      self.matrix = np.stack([np.frombuffer(r[2], dtype=np.float32) for r in rows]) if rows else np.zeros((0, 0), np.float32)

  def stamp(self, note):
    return "%d:%d" % (note["mtime"], note["size"])

  def stale(self):
    known = dict(((p, (s, m)) for p, s, m in self.db.execute("select path, stamp, model from notes")))
    with self.vault.lock:
      notes = list(self.vault.notes.values())
    todo = [n for n in notes if known.get(n["path"]) != (self.stamp(n), MODEL_NAME)]
    gone = [p for p in known if p not in self.vault.notes]
    return todo, gone

  def update(self, progress=None):
    """Embed notes that changed since they were last embedded."""
    if not self.running.acquire(blocking=False):
      return False
    try:
      todo, gone = self.stale()
      if self.vault.notes:
        self.embedder.start(lambda done, total: emit({"event": "model", "done": done, "total": total}))
      if not todo and not gone:
        return True
      for path in gone:
        self.db.execute("delete from chunks where path = ?", (path,))
        self.db.execute("delete from notes where path = ?", (path,))
      for i, note in enumerate(todo):
        if progress:
          progress(i, len(todo))
        pieces = chunks_of(note["title"], note["body"])
        # Paragraphs that didn't change keep their vectors; an edit costs one or two.
        known = {t: v for t, v in self.db.execute("select text, vec from chunks where path = ?", (note["path"],))}
        fresh = [p for p in pieces if p not in known]
        if fresh:
          for p, v in zip(fresh, self.embedder.embed(["search_document: " + note["title"] + "\n" + p for p in fresh])):
            known[p] = v.tobytes()
        vectors = [np.frombuffer(known[p], dtype=np.float32) for p in pieces]
        self.db.execute("delete from chunks where path = ?", (note["path"],))
        self.db.executemany("insert into chunks values (?, ?, ?, ?)",
                            [(note["path"], j, p, v.tobytes()) for j, (p, v) in enumerate(zip(pieces, vectors))])
        self.db.execute("insert or replace into notes values (?, ?, ?)", (note["path"], self.stamp(note), MODEL_NAME))
        self.db.commit()
      self.db.commit()
      self.load()
      if progress:
        progress(len(todo), len(todo))
      return True
    finally:
      self.running.release()

  def query(self, text):
    """Best cosine similarity and matching chunk per note."""
    with self.lock:
      if self.matrix.shape[0] == 0 or self.embedder.state != "ready":
        return {}
      vector = self.embedder.embed(["search_query: " + text])[0]
      sims = self.matrix @ vector
      best = {}
      for i in np.argsort(-sims)[:400]:
        path = self.paths[i]
        if path not in best:
          best[path] = (float(sims[i]), self.texts[i])
      return best


# ------------------------------------------------------------------ search

def excerpt(body, terms, width=180):
  flat = re.sub(r"\s+", " ", body)
  low = flat.lower()
  hits = [low.find(t) for t in terms if low.find(t) >= 0]
  if not hits:
    return ""
  start = max(0, min(hits) - width // 3)
  text = flat[start:start + width].strip()
  return ("…" if start > 0 else "") + text + ("…" if start + width < len(flat) else "")


STOPWORDS = set("""a an and are as at be by can did do does for from had has have how i if in is it me my
of on or our so that the their them then there these this to us was we were what when where which who
why will with you your""".split())


def search(vault, index, query, tags=None, limit=30):
  query = query.strip()
  words = [t.lower() for t in WORD.findall(query)]
  terms = [t for t in words if t not in STOPWORDS] or words
  phrase = query.lower()
  with vault.lock:
    notes = [n for n in vault.notes.values() if not tags or all(t in n["tags"] for t in tags)]
  if not terms:
    return []
  semantic = {}
  try:
    semantic = index.query(query) if index else {}
  except Exception:
    semantic = {}
  results = []
  for note in notes:
    title = note["title"].lower()
    body = note["body"].lower()
    score = 0.0
    kind = ""
    if phrase in title:
      score += 1.2 + (0.4 if title.startswith(phrase) else 0)
      kind = "title"
    elif all(t in title for t in terms):
      score += 0.9
      kind = "title"
    if all(t in title or t in note["tags"] or re.search(r"\b" + re.escape(t), body) for t in terms):
      # Scattered words in a long note say little about a longer question.
      score += 0.65 if phrase in body else 0.45 if len(terms) == 1 else 0.2
      kind = kind or "text"
    sim, chunk = semantic.get(note["path"], (0.0, ""))
    score += max(0.0, sim - 0.35) * 3
    if not kind and sim >= 0.5:
      kind = "meaning"
    if not kind:
      continue
    snippet = excerpt(note["body"], [phrase] + terms) if kind != "meaning" else snippet_of(chunk)
    results.append({"path": note["path"], "title": note["title"], "score": round(score, 4),
                    "match": kind, "snippet": snippet or note["snippet"], "tags": note["tags"], "mtime": note["mtime"]})
  results.sort(key=lambda r: (-r["score"], -r["mtime"]))
  if results and semantic:
    # Meaning-only matches far below the best one are noise.
    top = results[0]["score"]
    results = [r for r in results if r["match"] != "meaning" or r["score"] >= top * 0.7]
  return results[:limit]


# ------------------------------------------------------------------ assets

ASSET_DIR = os.path.join(config.cache_dir(), "assets")


class Assets:
  """What a rendered note needs beyond its own text: embedded notes and
  files answer at once; remote images, math and diagrams are fetched or
  drawn in the background and arrive as an "assets" event."""

  def __init__(self, vault):
    self.vault = vault
    self.work = queue.Queue()
    self.theme = {}
    threading.Thread(target=self.worker, daemon=True).start()

  def request(self, items, ink, theme=None):
    if theme:
      self.theme = theme
    ready = {}
    for item in items:
      key, kind = item.get("key"), item.get("kind")
      if kind == "note":
        rel = self.vault.by_title(item["name"].split("/")[-1])
        if rel:
          ready[key] = {"title": self.vault.notes[rel]["title"], "path": rel, "body": self.vault.read(rel)["body"]}
        else:
          ready[key] = {"missing": True}
      elif kind == "file":
        path = self.vault.attachment(item["name"])
        if path and not path.endswith(".md"):
          width, height = image_size(path)
          ready[key] = {"file": path, "width": width, "height": height}
        else:
          ready[key] = None
      elif kind in ("image", "math", "mermaid"):
        cached = self.cached(item, ink)
        if cached:
          ready[key] = cached
        else:
          self.work.put((item, ink))
    return ready

  def stem(self, item, ink):
    source = item.get("url") or item.get("tex") or item.get("src") or ""
    # The leading number changes whenever a renderer does, so stale drawings aren't reused.
    return os.path.join(ASSET_DIR, hashlib.sha1(("4\0%s\0%s\0%s\0%s" % (item["kind"], item.get("display"), ink, source)).encode()).hexdigest())

  def cached(self, item, ink):
    meta = self.stem(item, ink) + ".json"
    try:
      with open(meta) as f:
        info = json.load(f)
      return info if os.path.exists(info.get("file", "")) else None
    except (OSError, ValueError):
      return None

  def worker(self):
    while True:
      item, ink = self.work.get()
      try:
        info = getattr(self, "make_" + item["kind"])(item, ink, self.stem(item, ink))
      except Exception as e:
        info = {"error": str(e)}
      if info and "error" not in info:
        with open(self.stem(item, ink) + ".json", "w") as f:
          json.dump(info, f)
      emit({"event": "assets", "assets": {item["key"]: info}})

  def make_image(self, item, ink, stem):
    os.makedirs(ASSET_DIR, exist_ok=True)
    req = urllib.request.Request(item["url"], headers={"User-Agent": "Savi Notes"})
    with urllib.request.urlopen(req, timeout=20) as r:
      data = r.read(25 * 1024 * 1024)
    path = stem + os.path.splitext(urllib.parse.urlparse(item["url"]).path)[1][:5]
    with open(path, "wb") as f:
      f.write(data)
    width, height = image_size(path)
    if not width:
      raise RuntimeError("not an image")
    return {"file": path, "width": width, "height": height}

  def svg_pair(self, svg, ink, stem):
    """Screen and print copies of an SVG: themed ink, and black on white."""
    os.makedirs(ASSET_DIR, exist_ok=True)
    with open(stem + ".svg", "w") as f:
      f.write(svg.replace("currentColor", ink))
    with open(stem + "-print.svg", "w") as f:
      f.write(svg.replace("currentColor", "#000000"))
    return stem + ".svg", stem + "-print.svg"

  def make_math(self, item, ink, stem):
    """TeX to SVG in-process (ziamath), themed for the screen and black for print."""
    os.makedirs(ASSET_DIR, exist_ok=True)
    width = height = 0
    for suffix, color in ((".svg", ink), ("-print.svg", "#000000")):
      svg, width, height = mathsvg.render(item["tex"], bool(item.get("display")), color)
      with open(stem + suffix, "w", encoding="utf-8") as f:
        f.write(svg)
    return {"file": stem + ".svg", "printFile": stem + "-print.svg", "width": width, "height": height}

  def mermaid_theme(self, c):
    fg, bg = c.get("foreground", "#cdc6da"), c.get("background", "#16121d")
    box, line = c.get("lighter_background", bg), c.get("muted", fg)
    return {"theme": "base", "themeVariables": {
      "fontFamily": "sans-serif", "fontSize": 15, "background": bg, "textColor": fg,
      "primaryColor": box, "primaryTextColor": fg, "primaryBorderColor": line, "lineColor": c.get("dark_foreground", fg),
      "secondaryColor": c.get("dark_background", bg), "tertiaryColor": c.get("dark_background", bg),
      "edgeLabelBackground": bg, "clusterBkg": c.get("dark_background", bg), "clusterBorder": line,
      "actorBkg": box, "actorBorder": line, "actorLine": line, "actorTextColor": fg, "actorLineColor": line,
      "signalColor": fg, "signalTextColor": fg, "noteBkg": box, "noteBorderColor": line, "noteTextColor": fg,
      "activationBkgColor": box, "activationBorderColor": line}}

  def make_mermaid(self, item, ink, stem):
    """Diagrams need an external renderer: mmdr, or mermaid-cli's mmdc."""
    tool = shutil.which("mmdr") or shutil.which("mmdc")
    if not tool:
      raise RuntimeError("no diagram renderer; install mermaid-cli (npm install -g @mermaid-js/mermaid-cli)")
    os.makedirs(ASSET_DIR, exist_ok=True)
    light = {"foreground": "#1d1f21", "background": "#ffffff", "lighter_background": "#f3f3f5",
             "dark_background": "#f7f7f9", "muted": "#a0a0aa", "dark_foreground": "#55555f"}
    source = stem + ".mmd"
    with open(source, "w", encoding="utf-8") as f:
      f.write(item["src"])
    for out, colors in ((stem + ".svg", self.theme), (stem + "-print.svg", light)):
      conf = stem + ".json.tmp"
      with open(conf, "w") as f:
        json.dump(self.mermaid_theme(colors), f)
      if os.path.basename(tool).startswith("mmdr"):
        args, stdin = [tool, "-i", "-", "-o", out, "-c", conf], item["src"]
      else:
        args, stdin = [tool, "-i", source, "-o", out, "-c", conf, "-b", "transparent"], None
      result = subprocess.run(args, input=stdin, capture_output=True, text=True, timeout=90, **NO_WINDOW)
      os.remove(conf)
      if result.returncode != 0:
        raise RuntimeError(result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "diagram failed")
    os.remove(source)
    with open(stem + ".svg") as f:
      m = re.search(r'<svg[^>]*\bwidth="([\d.]+)"[^>]*\bheight="([\d.]+)"', f.read(2000))
    width, height = (float(m.group(1)), float(m.group(2))) if m else (600, 400)
    return {"file": stem + ".svg", "printFile": stem + "-print.svg", "width": width, "height": height}

# ------------------------------------------------------------------ articles

ARTICLE = "articles:"


class Articles:
  """The finder's Articles tab: internal articles of the departments this person edits on the
  AI Core. They are company content everyone's Claude searches, not personal notes, so they are
  plaintext and live on the gateway only. An open article's edits stay a draft here until the
  editor is left, because publishing re-indexes it for everyone."""

  def __init__(self, sync):
    self.sync = sync
    self.open = {}

  def listing(self):
    if not self.sync.enabled:
      return []
    try:
      departments = self.sync.client.call("GET", "/articles")["departments"]
    except (account.Offline, account.Refused, account.SignedOut):
      return []
    rows = [{"path": ARTICLE + a["key"], "title": a["title"], "department": d["name"], "status": a["status"],
             "mtime": int(datetime.datetime.fromisoformat(a["updated_at"]).timestamp()) if a["updated_at"] else 0}
            for d in departments for a in d["articles"]]
    return {"departments": [d["name"] for d in departments], "articles": rows}

  def read(self, key):
    if key not in self.open:
      self.open[key] = {**self.sync.client.call("GET", "/articles/" + urllib.parse.quote(key)), "draft": None}
    article = self.open[key]
    return {"path": ARTICLE + key, "body": article["draft"] if article["draft"] is not None else article["body"],
            "tags": [], "embeds": {}}

  def create(self, key, department, title):
    self.open[key] = {"key": key, "department": department, "title": title, "body": "", "updated_at": None, "draft": ""}

  def save(self, key, body):
    self.open[key]["draft"] = body

  def rename(self, key, title):
    self.open[key]["title"] = title
    self.open[key]["renamed"] = True
    return self.publish(key)

  def publish(self, key):
    """Sends the draft, if there is one. A colleague's newer save is a conflict, not overwritten."""
    article = self.open.get(key)
    if not article:
      return {}
    text = article["draft"] if article["draft"] is not None else article["body"]
    if not text.strip() or (text == article["body"] and not article.get("renamed")):
      return {}
    try:
      saved = self.sync.client.call("PUT", "/articles/" + urllib.parse.quote(key), {
        "department": article["department"], "title": article["title"], "body": text, "base_updated_at": article["updated_at"]})
    except account.Refused as e:
      if e.status == 409 and isinstance(e.body, dict) and e.body.get("error") == "conflict":
        self.open.pop(key)  # so reopening shows their version, not this draft
        raise ValueError("%s changed since you opened it. Copy your edits, then reopen it to see theirs." % article["title"])
      if e.status == 409:
        raise ValueError("Another department already has an article at %s; choose another title." % key)
      raise
    self.open[key] = {**saved, "draft": None}
    return {"published": saved["title"], "department": saved["department"]}

  def delete(self, key):
    self.sync.client.call("DELETE", "/articles/" + urllib.parse.quote(key))
    self.open.pop(key, None)

  def publish_all(self):
    for key in list(self.open):
      try:
        self.publish(key)
      except Exception as e:
        sys.stderr.write("savi-notes engine: could not publish %s: %s\n" % (key, e))


# ------------------------------------------------------------------ server

class Engine:
  def __init__(self, root):
    self.vault = Vault(root)
    self.vault.scan()
    self.embedder = Embedder()
    self.index = Index(self.vault, self.embedder)
    self.sync = Sync(self.vault, emit, self.pulled)
    self.articles = Articles(self.sync)
    self.assets = Assets(self.vault)
    self.index_timer = None

  def pulled(self):
    self.vault.scan()
    emit({"event": "changed"})
    self.reindex_soon(1)

  def watch(self):
    """Pick up notes written by other programs (editors, scripts, agents)."""
    while True:
      time.sleep(WATCH_INTERVAL)
      try:
        if self.vault.scan():
          emit({"event": "changed"})
          self.edited()
      except Exception as e:
        sys.stderr.write("notes-engine: watch: %s\n" % e)

  def reindex_soon(self, delay=4):
    if self.index_timer:
      self.index_timer.cancel()
    self.index_timer = threading.Timer(delay, self.reindex)
    self.index_timer.daemon = True
    self.index_timer.start()

  def reindex(self):
    try:
      self.index.update(lambda done, total: emit({"event": "index", "done": done, "total": total}))
      emit({"event": "search", "state": "ready"})
    except SemanticOff:
      emit({"event": "search", "state": "off"})
    except Exception as e:
      emit({"event": "search", "state": "error", "message": str(e)})

  def edited(self):
    self.reindex_soon()
    self.sync.soon()

  def article(self, req):
    """Ops on an articles: path go to the gateway, not the vault."""
    op, key = req["op"], req["path"][len(ARTICLE):]
    if op == "read":
      return self.articles.read(key)
    if op == "save":
      if req.get("body") is not None:
        self.articles.save(key, req["body"])
      return {"note": None}
    if op == "rename":
      self.articles.rename(key, req["title"].strip())
      return {"path": req["path"], "updated": 0}
    if op == "delete":
      self.articles.delete(key)
      return {}
    if op == "export":
      with open(req["out"], "w", encoding="utf-8") as f:
        f.write(self.articles.read(key)["body"])
      return {}
    if op == "publish":
      return self.articles.publish(key)
    raise ValueError("articles can't do " + op)

  def handle(self, req):
    op = req.get("op")
    v = self.vault
    if str(req.get("path", "")).startswith(ARTICLE):
      return self.article(req)
    if op == "articles":
      return self.articles.listing() or {"departments": [], "articles": []}
    if op == "newArticle":
      self.articles.create(req["key"], req["department"], req["title"])
      return {"path": ARTICLE + req["key"]}
    if op == "notes":
      if req.get("rescan"):
        v.scan()
      return {"notes": v.listing(), "root": v.root, "sync": self.sync.enabled}
    if op == "unsent":
      # Signing out deletes this copy, so first make sure the AI Core has all of it.
      self.sync.run()
      return {"unsent": self.sync.unsent()}
    if op == "read":
      return v.read(req["path"])
    if op == "save":
      v.save(req["path"], req.get("body"), req.get("tags"))
      self.edited()
      return {"note": next((n for n in v.listing() if n["path"] == req["path"]), None)}
    if op == "create":
      path = v.create(req.get("title") or "Untitled", req.get("tags"), req.get("body"))
      self.edited()
      return {"path": path}
    if op == "rename":
      path, updated = v.rename(req["path"], req["title"])
      self.sync.renamed(req["path"], path)
      self.edited()
      return {"path": path, "updated": updated}
    if op == "delete":
      v.delete(req["path"])
      self.edited()
      return {}
    # The vault sits in the app's data folder, so these are how notes leave it as files.
    if op == "export":
      shutil.copyfile(v.path_of(req["path"]), req["out"])
      return {}
    if op == "import":
      result = v.import_folder(req["folder"])
      self.edited()
      return result
    if op == "exportAll":
      base = os.path.join(req["folder"], "Savi Notes")
      out, n = base, 2
      while os.path.exists(out):
        out, n = "%s %d" % (base, n), n + 1
      shutil.copytree(v.root, out, ignore=shutil.ignore_patterns(".*", "*.savi-tmp"))
      return {"folder": out.replace(os.sep, "/"), "notes": len(v.notes)}
    if op == "untag":
      v.untag(req["path"], req["tag"])
      self.edited()
      return {"note": next((n for n in v.listing() if n["path"] == req["path"]), None)}
    if op == "resolve":
      return {"path": v.by_title(req["title"]) or ""}
    if op == "assets":
      return {"assets": self.assets.request(req.get("items", []), req.get("ink", "#000000"), req.get("theme"))}
    if op == "attach":
      return {"name": v.attach(req["source"])}
    if op == "attachment":
      return {"file": v.attachment(req["name"])}
    if op == "search":
      return {"results": search(v, self.index, req.get("query", ""), req.get("tags"))}
    if op == "sync":
      threading.Thread(target=self.sync.run, daemon=True).start()
      return {}
    if op == "settings":
      if not config.load().get("semantic", True):
        self.embedder.stop()
        self.embedder.state = "idle"
      self.reindex_soon(0)
      return {}
    raise ValueError("unknown op " + str(op))

  def serve(self):
    threading.Thread(target=self.reindex, daemon=True).start()
    threading.Thread(target=self.watch, daemon=True).start()
    threading.Thread(target=self.sync.loop, daemon=True).start()
    try:
      for line in sys.stdin:
        line = line.strip()
        if not line:
          continue
        req = {}
        try:
          req = json.loads(line)
          # Sync writes to the same files from its own thread.
          with self.vault.lock:
            reply = self.handle(req)
          reply["id"] = req.get("id")
          emit(reply)
        except Exception as e:
          emit({"id": req.get("id"), "error": str(e)})
    finally:
      self.embedder.stop()
      if self.sync.timer:
        self.sync.timer.cancel()
      # The window is gone; send what is left before exiting.
      self.articles.publish_all()
      self.sync.run()


def main(argv):
  if len(argv) < 3 or argv[1] not in ("serve", "search", "index"):
    sys.stderr.write(__doc__)
    return 2
  for stream in (sys.stdin, sys.stdout):
    if hasattr(stream, "reconfigure"):
      stream.reconfigure(encoding="utf-8", errors="replace")
  engine = Engine(argv[2])
  if argv[1] == "serve":
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    engine.serve()
    return 0
  try:
    try:
      engine.index.update(None if argv[1] == "search" else
                          lambda done, total: sys.stderr.write("\rEmbedding notes %d/%d" % (done, total)))
    except Exception as e:
      if argv[1] == "index":
        raise
      sys.stderr.write("savi-notes: matching words only: %s\n" % e)
    if argv[1] == "index":
      sys.stderr.write("\n")
      return 0
    for r in search(engine.vault, engine.index, " ".join(argv[3:])):
      print("%s\t%s\t%s" % (r["path"], r["match"], r["snippet"]))
    return 0
  except Exception as e:
    sys.stderr.write("savi-notes: %s\n" % e)
    return 1
  finally:
    engine.embedder.stop()


if __name__ == "__main__":
  sys.exit(main(sys.argv))
