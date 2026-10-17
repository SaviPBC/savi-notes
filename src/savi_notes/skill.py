"""The Claude Code skill that ships with the app, installed into ~/.claude/skills."""

import hashlib
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(HERE, "skill")
NAME = "savi-notes"


def target():
  return os.path.join(os.path.expanduser("~"), ".claude", "skills", NAME)


def digest(folder):
  h = hashlib.sha1()
  for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
    path = os.path.join(folder, name)
    if os.path.isfile(path):
      h.update(name.encode("utf-8"))
      with open(path, "rb") as f:
        h.update(f.read())
  return h.hexdigest()


def install():
  """Copy the skill over whatever is there when it differs. Returns (path, changed)."""
  dest = target()
  if os.path.isdir(dest) and digest(dest) == digest(SOURCE):
    return dest, False
  os.makedirs(os.path.dirname(dest), exist_ok=True)
  if os.path.isdir(dest):
    shutil.rmtree(dest)
  shutil.copytree(SOURCE, dest)
  return dest, True
