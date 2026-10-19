"""A launcher for the app where each platform looks for one: a desktop entry,
a Start Menu shortcut, or an app bundle in ~/Applications. Installed on every
launch, writing only what changed, so an update reaches launchers made by an
older version."""

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


def write_if_changed(path, data):
  try:
    with open(path, "rb") as f:
      if f.read() == data:
        return False
  except OSError:
    pass
  os.makedirs(os.path.dirname(path), exist_ok=True)
  with open(path, "wb") as f:
    f.write(data)
  return True


def macos():
  bundle = os.path.expanduser("~/Applications/Savi Notes.app")
  contents = os.path.join(bundle, "Contents")
  script = os.path.join(contents, "MacOS", "Savi Notes")
  with open(os.path.join(HERE, "icon.icns"), "rb") as f:
    icon = f.read()
  changed = write_if_changed(script, ("#!/bin/sh\nexec \"%s\" \"$@\"\n" % launcher()).encode())
  os.chmod(script, 0o755)
  changed |= write_if_changed(os.path.join(contents, "Resources", "icon.icns"), icon)
  changed |= write_if_changed(os.path.join(contents, "Info.plist"), plistlib.dumps({
    "CFBundleName": "Savi Notes", "CFBundleDisplayName": "Savi Notes", "CFBundleIdentifier": "com.savi.notes",
    "CFBundleExecutable": "Savi Notes", "CFBundleIconFile": "icon", "CFBundlePackageType": "APPL",
    "CFBundleVersion": "1", "LSMinimumSystemVersion": "12.0", "NSHighResolutionCapable": True,
  }))
  if changed:
    # Finder and Spotlight cache a bundle's icon; re-registering it shows the new one.
    subprocess.run(["/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister",
                    "-f", bundle], capture_output=True)
    os.utime(bundle)
  return "It's in ~/Applications as Savi Notes (Spotlight finds it)."


def windows():
  start_menu = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Microsoft", "Windows", "Start Menu", "Programs")
  os.makedirs(start_menu, exist_ok=True)
  link = os.path.join(start_menu, "Savi Notes.lnk")
  if os.path.exists(link):
    return "It's in the Start Menu as Savi Notes."
  target = launcher(gui=True)
  script = ("$s = (New-Object -ComObject WScript.Shell).CreateShortcut('%s'); $s.TargetPath = '%s'; "
            "$s.WorkingDirectory = '%s'; $s.Description = 'Savi Notes'; $s.Save()"
            % (link.replace("'", "''"), target.replace("'", "''"), os.path.expanduser("~").replace("'", "''")))
  subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], check=True, capture_output=True,
                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
  return "It's in the Start Menu as Savi Notes."
