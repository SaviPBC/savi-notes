"""What a Python process has to tell macOS to pass for an app of its own. Without it the menu
bar and Dock say "Python", and a window started from a terminal opens behind everything."""

import sys


def name_app():
  """Before Qt starts: macOS reads the app's name from the bundle, which here is Python's."""
  if sys.platform != "darwin":
    return
  from Foundation import NSBundle
  info = NSBundle.mainBundle().localizedInfoDictionary() or NSBundle.mainBundle().infoDictionary()
  info["CFBundleName"] = "Savi Notes"


def bring_forward():
  if sys.platform != "darwin":
    return
  from AppKit import NSApplication
  NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
