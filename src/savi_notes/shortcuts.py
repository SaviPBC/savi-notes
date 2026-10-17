"""A launcher for the app where each platform looks for one: a desktop entry,
a Start Menu shortcut, or an app bundle in ~/Applications."""

import os
import plistlib
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def launcher(gui=False):
  """The installed command, the windowless one on Windows when asked."""
  if gui and sys.platform == "win32":
    found = shutil.which("savi-notes-app")
    if found:
      return found
  found = shutil.which("savi-notes")
  if found:
    return found
  return sys.argv[0] if os.path.isabs(sys.argv[0]) else "savi-notes"


def install():
  """Returns a line saying where the app can now be opened from, or ""."""
  try:
    if sys.platform == "win32":
      return windows()
    if sys.platform == "darwin":
      return macos()
    return linux()
  except Exception as e:  # a missing launcher is not worth failing setup over
    return "Could not add a launcher: %s" % e


def linux():
  folder = os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), "applications")
  os.makedirs(folder, exist_ok=True)
  path = os.path.join(folder, "savi-notes.desktop")
  with open(path, "w", encoding="utf-8") as f:
    f.write("[Desktop Entry]\nType=Application\nName=Savi Notes\nComment=Markdown notes with tags and search\n"
            "Exec=\"%s\" %%u\nIcon=%s\nTerminal=false\nCategories=Office;TextEditor;\nStartupWMClass=savi-notes\n"
            % (launcher(), os.path.join(HERE, "icon.svg")))
  return "It's in your app launcher as Savi Notes."


def macos():
  bundle = os.path.expanduser("~/Applications/Savi Notes.app")
  macos_dir = os.path.join(bundle, "Contents", "MacOS")
  os.makedirs(macos_dir, exist_ok=True)
  script = os.path.join(macos_dir, "Savi Notes")
  with open(script, "w", encoding="utf-8") as f:
    f.write("#!/bin/sh\nexec \"%s\" \"$@\"\n" % launcher())
  os.chmod(script, 0o755)
  with open(os.path.join(bundle, "Contents", "Info.plist"), "wb") as f:
    plistlib.dump({
      "CFBundleName": "Savi Notes", "CFBundleDisplayName": "Savi Notes", "CFBundleIdentifier": "com.savi.notes",
      "CFBundleExecutable": "Savi Notes", "CFBundlePackageType": "APPL", "CFBundleVersion": "1",
      "LSMinimumSystemVersion": "12.0", "NSHighResolutionCapable": True,
    }, f)
  return "It's in ~/Applications as Savi Notes (Spotlight finds it)."


def windows():
  start_menu = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Microsoft", "Windows", "Start Menu", "Programs")
  os.makedirs(start_menu, exist_ok=True)
  link = os.path.join(start_menu, "Savi Notes.lnk")
  target = launcher(gui=True)
  script = ("$s = (New-Object -ComObject WScript.Shell).CreateShortcut('%s'); $s.TargetPath = '%s'; "
            "$s.WorkingDirectory = '%s'; $s.Description = 'Savi Notes'; $s.Save()"
            % (link.replace("'", "''"), target.replace("'", "''"), os.path.expanduser("~").replace("'", "''")))
  subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], check=True, capture_output=True,
                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
  return "It's in the Start Menu as Savi Notes."
