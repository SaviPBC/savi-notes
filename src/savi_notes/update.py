"""Newer releases on GitHub, and how to install one."""

import json
import re
import shutil
import urllib.request

REPO = "SaviPBC/savi-notes"
# The release's source archive under a name that doesn't change, which carries its own
# version, so installing needs neither git (Windows has none) nor a version number.
INSTALL_LATEST = "https://github.com/%s/releases/latest/download/savi-notes.tar.gz" % REPO


def latest():
  """(version, required) of the newest release, or None when it can't be read."""
  request = urllib.request.Request(
    "https://api.github.com/repos/%s/releases/latest" % REPO,
    headers={"Accept": "application/vnd.github+json", "User-Agent": "Savi Notes"})
  try:
    with urllib.request.urlopen(request, timeout=6) as r:
      data = json.load(r)
  except Exception:
    return None
  tag = str(data.get("tag_name") or "").lstrip("v")
  if not tag:
    return None
  # A release whose notes say "required update" loses the Later button.
  required = "required update" in str(data.get("body") or "").lower()
  return tag, required


def parts(version):
  """Comparable form; a .devN build sorts below the release of the same number."""
  numbers = tuple(int(p) for p in re.findall(r"\d+", str(version).split("+")[0])[:3])
  return numbers + (0 if "dev" in str(version) else 1,)


def is_newer(candidate, current):
  return parts(candidate) > parts(current)


def install_command(version):
  """The uv command that installs the given release, or None without uv."""
  uv = shutil.which("uv")
  if not uv:
    return None
  source = "https://github.com/%s/releases/download/v%s/savi-notes.tar.gz" % (REPO, version)
  return [uv, "tool", "install", "--force", "--reinstall", source]
