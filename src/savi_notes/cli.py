"""The savi-notes command: the app, and what Claude Code's skill calls."""

import os
import subprocess
import sys

from . import __version__, config

HERE = os.path.dirname(os.path.abspath(__file__))

USAGE = """savi-notes [NOTE]           open Savi Notes, or the named note
savi-notes search QUERY...  rank notes by title, words and meaning
savi-notes tags             the tags in use, with counts
savi-notes format           the markdown the app renders (for writing notes)
savi-notes vault            this computer's copy of the notes
savi-notes check            look for untitled, untagged or badly placed notes
savi-notes index            bring the meaning-search index up to date
savi-notes skill            install the Claude Code skill (the app does this too)
savi-notes update           install the newest release
savi-notes version
"""


def vault_or_exit():
  vault = config.vault_dir()
  if not os.path.isdir(vault):
    sys.stderr.write("savi-notes: no notes yet; open Savi Notes and sign in first\n")
    sys.exit(2)
  return vault


def cmd_search(args):
  from . import engine
  if not args:
    sys.stderr.write("savi-notes search QUERY...\n")
    return 2
  return engine.main(["engine", "search", vault_or_exit(), *args])


def cmd_index(args):
  from . import engine
  return engine.main(["engine", "index", vault_or_exit()])


def cmd_format(args):
  with open(os.path.join(HERE, "FORMAT.md"), encoding="utf-8") as f:
    sys.stdout.write(f.read())


def cmd_vault(args):
  print(vault_or_exit())


def cmd_tags(args):
  from .engine import Vault
  vault = Vault(vault_or_exit())
  vault.scan()
  counts = {}
  for note in vault.notes.values():
    for tag in note["tags"]:
      counts[tag] = counts.get(tag, 0) + 1
  for tag, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
    print("%s\t%d" % (tag, count))


def cmd_check(args):
  from . import vaultcheck
  for title, lines in vaultcheck.run(vault_or_exit()):
    print("\n== %s ==" % title)
    for line in lines:
      print(line)


def cmd_skill(args):
  from . import skill
  path, changed = skill.install()
  print(("Installed the Claude Code skill at %s" if changed else "The Claude Code skill at %s is current") % path)


def cmd_update(args):
  from . import update
  found = update.latest()
  if not found:
    sys.stderr.write("savi-notes: could not check for releases\n")
    return 1
  version, required = found
  if not update.is_newer(version, __version__):
    print("Savi Notes %s is the newest release" % __version__)
    return 0
  command = update.install_command(version)
  if not command:
    sys.stderr.write("savi-notes: uv is not installed, so the update can't be run\n")
    return 1
  print("Installing Savi Notes %s" % version)
  return subprocess.call(command)


def cmd_version(args):
  print("Savi Notes %s" % __version__)


def cmd_help(args):
  sys.stdout.write(USAGE)


COMMANDS = {
  "search": cmd_search, "index": cmd_index, "format": cmd_format, "vault": cmd_vault, "tags": cmd_tags,
  "check": cmd_check, "skill": cmd_skill, "update": cmd_update, "version": cmd_version, "help": cmd_help,
}


def main(argv=None):
  argv = list(sys.argv[1:] if argv is None else argv)
  if argv and argv[0] in ("-h", "--help"):
    return cmd_help([]) or 0
  if argv and argv[0] in COMMANDS:
    return COMMANDS[argv[0]](argv[1:]) or 0
  from .app import run
  return run(" ".join(argv))
