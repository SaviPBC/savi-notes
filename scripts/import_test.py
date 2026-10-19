"""Importing an Obsidian-shaped vault: folders become tags, hidden folders are skipped,
taken titles get numbers with links following, attachments land in Attachments/."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from savi_notes import engine  # noqa: E402


def write(path, text, mode="w"):
  os.makedirs(os.path.dirname(path), exist_ok=True)
  with open(path, mode, **({} if "b" in mode else {"encoding": "utf-8"})) as f:
    f.write(text)


def check(label, got, want):
  if got != want:
    sys.exit("FAIL %s: got %r, want %r" % (label, got, want))
  print("ok  " + label)


root = tempfile.mkdtemp(prefix="savi-import-")
obsidian, vault = os.path.join(root, "Obsidian"), os.path.join(root, "Notes")
write(os.path.join(vault, "Groceries.md"), "already here\n")
write(os.path.join(obsidian, ".obsidian", "app.json"), "{}")
write(os.path.join(obsidian, "Work", "Projects", "Launch Plan.md"), "---\ntags:\n  - planning\n---\nSee [[Groceries]] and ![[chart.png]]\n")
write(os.path.join(obsidian, "Home", "Groceries.md"), "milk\n")
write(os.path.join(obsidian, "Inbox.md"), "plain\n")
write(os.path.join(obsidian, "A", "Same.md"), "first\n")
write(os.path.join(obsidian, "B", "Same.md"), "second\n")
write(os.path.join(obsidian, "Assets", "chart.png"), b"\x89PNG", "wb")

v = engine.Vault(vault)
v.scan()
result = v.import_folder(obsidian)
v.scan()
titles = sorted(n["title"] for n in v.notes.values())
read = lambda title: open(os.path.join(vault, title + ".md"), encoding="utf-8").read()

check("every note comes in, hidden folders don't", result, {"notes": 5, "files": 1, "renamed": 1})
check("titles at the top level", titles, ["Groceries", "Groceries 2", "Inbox", "Launch Plan", "Same", "Same 2"])
check("folders become tags beside its own", v.notes["Launch Plan.md"]["tags"], ["planning", "work", "projects"])
check("a link to a taken title follows the rename", "[[Groceries 2]]" in read("Launch Plan"), True)
check("the note already here is untouched", read("Groceries"), "already here\n")
check("a note at the top keeps no tags", v.notes["Inbox.md"]["tags"], [])
check("attachments land in Attachments/", os.listdir(os.path.join(vault, "Attachments")), ["chart.png"])
check("importing the same files again copies no attachment twice", v.import_folder(obsidian)["files"], 0)
try:
  v.import_folder(vault)
  sys.exit("FAIL importing the vault into itself was allowed")
except ValueError:
  print("ok  the vault can't be imported into itself")
print("import ok")
