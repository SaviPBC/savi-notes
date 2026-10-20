"""Sync with the Savi AI Core.

The gateway holds each person's notes as ciphertext under ids this app chose;
the vault folder is the plain copy everything local reads. A run pulls what
changed since the last cursor, then pushes every file whose text differs from
what was last synced. `sync.sqlite` remembers, per note, its id, the revision
the gateway last confirmed and a hash of the text at that point, which is how
a local edit is told from a remote one.

When both sides changed a note, the local text wins and the gateway's version
is kept beside it as "Title (conflict DATE)", so nothing is lost and nothing
merges silently. A note deleted on one side and edited on the other comes back.
"""

import base64
import datetime
import hashlib
import json
import os
import sqlite3
import struct
import threading
import time
import uuid

from . import account, config, crypto

DELAY = 4
INTERVAL = 60
MAX_ATTACHMENT = 25 * 1024 * 1024


def state_path():
  return os.path.join(config.data_dir(), "sync.sqlite")


def digest(data):
  return hashlib.sha256(data).hexdigest()


def read_bytes(path):
  try:
    with open(path, "rb") as f:
      return f.read()
  except OSError:
    return None


def pack_file(name, data):
  raw = name.encode("utf-8")
  return struct.pack(">H", len(raw)) + raw + data


def unpack_file(blob):
  size = struct.unpack(">H", blob[:2])[0]
  return blob[2:2 + size].decode("utf-8"), blob[2 + size:]


class Sync:
  def __init__(self, vault, emit, on_change):
    self.vault = vault
    self.emit = emit
    self.on_change = on_change
    self.lock = threading.Lock()
    self.timer = None
    self.again = False
    self.account = account.load()
    self.key = account.note_key(self.account)
    self.enabled = bool(self.key and self.account.get("access"))
    self.client = account.Client(self.account) if self.enabled else None
    os.makedirs(config.data_dir(), exist_ok=True)
    self.db = sqlite3.connect(state_path(), check_same_thread=False)
    self.db.executescript("""
      create table if not exists meta (k text primary key, v text);
      create table if not exists notes (id text primary key, path text unique, revision int, hash text);
      create table if not exists files (id text primary key, name text unique, hash text);
    """)
    self.db_lock = threading.Lock()

  # ---------------------------------------------------------------- state

  def q(self, sql, *args):
    with self.db_lock:
      rows = self.db.execute(sql, args).fetchall()
      self.db.commit()
      return rows

  def cursor(self):
    rows = self.q("select v from meta where k = 'cursor'")
    return int(rows[0][0]) if rows else 0

  def renamed(self, old, new):
    """A rename in the app is an edit of one note, not a delete and a new note. The title
    travels inside the ciphertext, so clearing the hash is what gets it sent."""
    self.q("update notes set path = ?, hash = '' where path = ?", new.replace(os.sep, "/"), old.replace(os.sep, "/"))

  def local(self, rel):
    return os.path.join(self.vault.root, rel)

  def local_files(self):
    """Everything in the vault that is not a note: attachments, wherever they sit."""
    for dirpath, dirnames, filenames in os.walk(self.vault.root):
      dirnames[:] = [d for d in dirnames if not d.startswith(".")]
      for name in filenames:
        if not name.endswith(".md") and not name.startswith(".") and not name.endswith(".savi-tmp"):
          yield os.path.relpath(os.path.join(dirpath, name), self.vault.root).replace(os.sep, "/")

  # ---------------------------------------------------------------- running

  def soon(self, delay=DELAY):
    if not self.enabled:
      return
    if self.timer:
      self.timer.cancel()
    self.timer = threading.Timer(delay, self.run)
    self.timer.daemon = True
    self.timer.start()

  def loop(self):
    """After the first run, which the engine makes before it says it's ready."""
    while self.enabled:
      time.sleep(INTERVAL)
      self.run()

  def run(self):
    """One pull and push. True when nothing is left to send."""
    if not self.enabled:
      return False
    if not self.lock.acquire(blocking=False):
      self.again = True  # an edit arrived mid-run; go again once this one is done
      return False
    self.again = False
    self.conflicts = 0
    try:
      self.emit({"event": "sync", "state": "running"})
      done = False
      # A refused push means the gateway moved on since the pull; pull again and retry.
      for _ in range(3):
        if self.pull():
          self.on_change()
        if self.push():
          done = True
          break
      if self.conflicts:
        self.emit({"event": "sync", "state": "conflict", "message": "%d note%s changed on two devices; both versions are kept"
                   % (self.conflicts, "" if self.conflicts == 1 else "s")})
      else:
        self.emit({"event": "sync", "state": "ok", "time": int(time.time())})
      return done
    except account.Offline:
      self.emit({"event": "sync", "state": "offline"})
    except account.SignedOut:
      self.enabled = False
      self.emit({"event": "account", "state": "signedOut"})
    except crypto.WrongKey:
      # Notes sealed under another key: the person started over on another device.
      self.enabled = False
      self.emit({"event": "account", "state": "wrongKey"})
    except Exception as e:
      self.emit({"event": "sync", "state": "error", "message": str(e)})
    finally:
      self.lock.release()
      if self.again:
        self.soon(1)
    return False

  # ---------------------------------------------------------------- pull

  def pull(self):
    changed = False
    cursor = self.cursor()
    pulled = 0
    while True:
      page = self.client.call("GET", "/changes?since=%d" % cursor)
      downloads = {}
      for item in page["attachments"]:
        if not item["deleted"] and not self.q("select 1 from files where id = ?", item["id"]):
          downloads[item["id"]] = self.client.call("GET", "/attachments/" + item["id"])
      with self.vault.lock:
        for note in page["notes"]:
          changed = self.apply_note(note) or changed
        for item in page["attachments"]:
          changed = self.apply_file(item, downloads.get(item["id"])) or changed
      cursor = page["cursor"]
      self.q("insert or replace into meta values ('cursor', ?)", str(cursor))
      pulled += len(page["notes"])
      self.emit({"event": "pulling", "notes": pulled})
      if not page["more"]:
        return changed

  def apply_note(self, note):
    row = self.q("select path, revision, hash from notes where id = ?", note["id"])
    path, revision, synced = row[0] if row else (None, 0, None)
    current = read_bytes(self.local(path)) if path else None
    edited_here = current is not None and digest(current) != synced
    # Not newer than what this computer last confirmed: its own push coming back, which
    # anything typed since must not be mistaken for a clash with.
    if row and note["revision"] <= revision:
      return False

    if note["deleted"]:
      if not row:
        return False
      self.q("delete from notes where id = ?", note["id"])
      if edited_here:
        return False  # no row now, so the next push sends it as a new note
      if current is not None:
        self.vault.delete(path)
      return True

    plain = json.loads(crypto.unseal(self.key, base64.b64decode(note["ciphertext"]), note["id"]))
    # Already what this side has, which is the usual case: the echo of our own push.
    if (current is not None and current.replace(b"\r\n", b"\n") == plain["text"].encode("utf-8")
        and os.path.basename(path)[:-3] == plain["title"]):
      self.q("update notes set revision = ?, hash = ? where id = ?", note["revision"], digest(current), note["id"])
      return False

    if edited_here:
      stamp = datetime.date.today().isoformat()
      self.vault.write_text(self.vault.free_name("%s (conflict %s)" % (plain["title"], stamp)), plain["text"])
      self.q("update notes set revision = ? where id = ?", note["revision"], note["id"])
      self.conflicts += 1
      return True

    keep = path and os.path.basename(path)[:-3] == plain["title"]
    target = path if keep else self.vault.free_name(plain["title"], os.path.basename(path) if path else None)
    if path and target != path and current is not None:
      os.replace(self.local(path), self.local(target))
      with self.vault.lock:
        self.vault.notes.pop(path, None)
    self.vault.write_text(target, plain["text"])
    # Hashed as written, not as received: Windows writes the newlines back as CRLF.
    written = read_bytes(self.local(target)) or b""
    self.q("insert or replace into notes values (?, ?, ?, ?)", note["id"], target.replace(os.sep, "/"), note["revision"], digest(written))
    return True

  def apply_file(self, item, blob):
    row = self.q("select name, hash from files where id = ?", item["id"])
    if item["deleted"]:
      if not row:
        return False
      name, synced = row[0]
      self.q("delete from files where id = ?", item["id"])
      current = read_bytes(self.local(name))
      if current is not None and digest(current) == synced:
        os.remove(self.local(name))
      return True
    if row or blob is None:
      return False
    name, data = unpack_file(crypto.unseal(self.key, blob, item["id"]))
    existing = read_bytes(self.local(name))
    if existing is not None and digest(existing) != digest(data):
      # Two devices added different files under one name: keep both.
      stem, ext = os.path.splitext(name)
      n = 2
      while os.path.exists(self.local("%s %d%s" % (stem, n, ext))):
        n += 1
      name = "%s %d%s" % (stem, n, ext)
    os.makedirs(os.path.dirname(self.local(name)), exist_ok=True)
    with open(self.local(name), "wb") as f:
      f.write(data)
    self.q("insert or replace into files values (?, ?, ?)", item["id"], name, digest(data))
    return True

  # ---------------------------------------------------------------- push

  def pending(self):
    """What differs from the last sync: [(kind, ...)] for notes, then files."""
    work = []
    with self.vault.lock:
      rows = {path: (id_, revision, synced) for id_, path, revision, synced in self.q("select id, path, revision, hash from notes")}
      present = set()
      for rel in self.vault.walk():
        rel = rel.replace(os.sep, "/")
        present.add(rel)
        text = read_bytes(self.local(rel))
        if text is None:
          continue
        row = rows.get(rel)
        if not row:
          work.append(("note", str(uuid.uuid4()), rel, text, 0))
        elif row[2] != digest(text):
          work.append(("note", row[0], rel, text, row[1]))
      work += [("gone", id_, revision) for path, (id_, revision, _) in rows.items() if path not in present]

      files = {name: (id_, synced) for id_, name, synced in self.q("select id, name, hash from files")}
      seen = set()
      for name in self.local_files():
        seen.add(name)
        data = read_bytes(self.local(name))
        if data is None or len(data) > MAX_ATTACHMENT:
          continue
        row = files.get(name)
        if not row or row[1] != digest(data):
          if row:
            work.append(("unfile", row[0]))
          work.append(("file", str(uuid.uuid4()), name, data))
      work += [("unfile", id_) for name, (id_, _) in files.items() if name not in seen]
    return work

  def push(self):
    """True when everything went; False when the gateway had newer notes to pull first."""
    clean = True
    for item in self.pending():
      kind = item[0]
      try:
        if kind == "note":
          _, id_, rel, text, base = item
          body = text.decode("utf-8", "replace").replace("\r\n", "\n")
          plain = json.dumps({"title": os.path.basename(rel)[:-3], "text": body}).encode()
          sealed = base64.b64encode(crypto.seal(self.key, plain, id_)).decode()
          reply = self.client.call("PUT", "/notes/" + id_, {"base_revision": base, "ciphertext": sealed})
          self.q("insert or replace into notes values (?, ?, ?, ?)", id_, rel, reply["revision"], digest(text))
        elif kind == "gone":
          _, id_, base = item
          self.client.call("DELETE", "/notes/" + id_, {"base_revision": base})
          self.q("delete from notes where id = ?", id_)
        elif kind == "file":
          _, id_, name, data = item
          self.client.call("PUT", "/attachments/" + id_, raw=crypto.seal(self.key, pack_file(name, data), id_))
          self.q("insert or replace into files values (?, ?, ?)", id_, name, digest(data))
        elif kind == "unfile":
          self.client.call("DELETE", "/attachments/" + item[1])
          self.q("delete from files where id = ?", item[1])
      except account.Refused as e:
        if e.status == 404 and kind == "unfile":
          self.q("delete from files where id = ?", item[1])
        elif e.status == 409 and kind == "gone":
          # Edited elsewhere since: forget it here, and the pull brings the edit back.
          self.q("delete from notes where id = ?", item[1])
          clean = False
        elif e.status == 409:
          clean = False
        else:
          raise
    return clean

  def unsent(self):
    return len(self.pending())
