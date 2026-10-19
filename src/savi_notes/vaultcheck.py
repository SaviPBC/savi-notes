"""A read-only health check of the vault: what `savi-notes check` prints."""

import os
import re

MEDIA = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic", ".pdf", ".canvas")
TAGS_LINE = re.compile(r"^tags:\s*\S", re.M)
INLINE_TAG = re.compile(r"(^|\s)#[A-Za-z]")
INBOX = re.compile(r"^tags:.*\binbox\b", re.M)
SECRET_TAGS = re.compile(r"^tags:.*\b(credentials|security)\b", re.M)
KEY = re.compile(r"(sk-[A-Za-z0-9]{20,}|savi_sk_[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}|AKIA[A-Z0-9]{16}"
                 r"|pat[A-Za-z0-9]{14}\.[a-f0-9]{40,}|tok_(live|sandbox)_[A-Za-z0-9]{10,}|xox[abp]-[A-Za-z0-9-]{20,})")
WIKILINK = re.compile(r"(?<!!)\[\[([^\]|#\n]+)")


def read(path):
  with open(path, encoding="utf-8", errors="replace") as f:
    return f.read()


def run(root):
  """[(section title, lines)]; a section with no lines is clean."""
  names = sorted(n for n in os.listdir(root) if n.endswith(".md") and not n.startswith("."))
  texts = {n: read(os.path.join(root, n)) for n in names}
  titles = {n[:-3].lower() for n in names}

  nested = []
  for dirpath, dirnames, filenames in os.walk(root):
    dirnames[:] = [d for d in dirnames if not d.startswith(".")]
    if dirpath != root:
      nested += [os.path.relpath(os.path.join(dirpath, f), root) for f in filenames if f.endswith(".md")]

  keys = []
  for n, text in texts.items():
    if SECRET_TAGS.search(text):
      continue
    for i, line in enumerate(text.split("\n"), 1):
      if KEY.search(line):
        keys.append("%s:%d" % (n, i))

  targets = set()
  for text in texts.values():
    for m in WIKILINK.finditer(text):
      targets.add(m.group(1).strip().rstrip("\\").strip())

  sections = [
    ("Untitled notes (should be none)", [n for n in names if n.lower().startswith("untitled")]),
    ("Notes outside the vault root (notes don't live in folders)", nested),
    ("Media outside Attachments/", sorted(n for n in os.listdir(root) if n.lower().endswith(MEDIA))),
    ("Untagged notes", [n for n, t in texts.items() if not TAGS_LINE.search(t) and not INLINE_TAG.search(t)]),
    ("Tagged inbox, waiting for triage", [n for n, t in texts.items() if INBOX.search(t)]),
    ("Key-shaped strings outside credentials/security notes (file:line only)", keys),
    ("Links to notes that don't exist", sorted(t for t in targets if t.lower() not in titles)),
  ]

  from . import account
  if account.load().get("key"):
    from .engine import Vault
    from .sync import Sync
    vault = Vault(root)
    vault.scan()
    waiting = [item[2] if item[0] in ("note", "file") else "(a deletion)"
               for item in Sync(vault, lambda message: None, lambda: None).pending()]
    sections.append(("Changes not yet synced to the AI Core (the app sends them while it's open)", waiting))
  return sections
