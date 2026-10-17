"""llama.cpp's server for meaning search: one on the PATH, or a build of a
pinned release downloaded for this machine on first use."""

import os
import platform
import shutil
import stat
import sys
import tarfile
import tempfile
import time
import urllib.request
import zipfile

from . import config

TAG = "b11714"
BASE_URL = "https://github.com/ggml-org/llama.cpp/releases/download/%s/" % TAG
EXE = "llama-server.exe" if sys.platform == "win32" else "llama-server"


def asset_name():
  arch = platform.machine().lower()
  arm = arch in ("arm64", "aarch64")
  if sys.platform == "win32":
    return "llama-%s-bin-win-cpu-%s.zip" % (TAG, "arm64" if arm else "x64")
  if sys.platform == "darwin":
    return "llama-%s-bin-macos-%s.tar.gz" % (TAG, "arm64" if arm else "x64")
  if arch in ("x86_64", "amd64"):
    return "llama-%s-bin-ubuntu-x64.tar.gz" % TAG
  return ""


def install_dir():
  return os.path.join(config.data_dir(), "llama", TAG)


def downloaded_path():
  folder = install_dir()
  if not os.path.isdir(folder):
    return ""
  for dirpath, dirnames, filenames in os.walk(folder):
    if EXE in filenames:
      return os.path.join(dirpath, EXE)
  return ""


def server_path():
  """The server to run: the system's own first, then the downloaded one."""
  return shutil.which("llama-server") or downloaded_path()


def ensure_server(progress):
  """Download and unpack the release build if no server is available yet."""
  found = server_path()
  if found:
    return found
  name = asset_name()
  if not name:
    raise RuntimeError("no llama.cpp build for this machine; install llama-server yourself")
  folder = install_dir()
  os.makedirs(folder, exist_ok=True)
  fd, archive = tempfile.mkstemp(suffix=name[-7:], dir=folder)
  os.close(fd)
  try:
    request = urllib.request.Request(BASE_URL + name, headers={"User-Agent": "Savi Notes"})
    with urllib.request.urlopen(request, timeout=30) as response, open(archive, "wb") as f:
      total = int(response.headers.get("Content-Length") or 0)
      done, last = 0, 0
      while True:
        block = response.read(1 << 20)
        if not block:
          break
        f.write(block)
        done += len(block)
        if progress and time.time() - last > 0.5:
          progress(done, total or done)
          last = time.time()
    if name.endswith(".zip"):
      with zipfile.ZipFile(archive) as z:
        z.extractall(folder)
    else:
      with tarfile.open(archive) as t:
        try:
          t.extractall(folder, filter="data")
        except TypeError:  # Python < 3.12
          t.extractall(folder)
  finally:
    try:
      os.remove(archive)
    except OSError:
      pass
  if sys.platform != "win32":
    for dirpath, dirnames, filenames in os.walk(folder):
      for filename in filenames:
        path = os.path.join(dirpath, filename)
        if filename.startswith("llama") or ".so" in filename or filename.endswith(".dylib"):
          os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
  found = downloaded_path()
  if not found:
    raise RuntimeError("the llama.cpp download had no llama-server in it")
  return found
