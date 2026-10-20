"""What a Python process has to tell the desktop to pass for an app of its own. Without it
macOS's menu bar and Dock say "Python", Windows files the window under python.exe's taskbar
icon, and a window started from a terminal opens behind everything."""

import sys


def name_app():
  """Before Qt starts."""
  if sys.platform == "darwin":
    # macOS reads the app's name from the bundle, which here is Python's.
    from Foundation import NSBundle
    info = NSBundle.mainBundle().localizedInfoDictionary() or NSBundle.mainBundle().infoDictionary()
    info["CFBundleName"] = "Savi Notes"
  elif sys.platform == "win32":
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SaviPBC.SaviNotes")


def bring_forward():
  if sys.platform != "darwin":
    return
  from AppKit import NSApplication
  NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
