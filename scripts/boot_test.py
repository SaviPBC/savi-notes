"""Start the app headless for a few seconds and fail on anything QML or the
engine complains about. CI runs this on every platform."""

import os
import subprocess
import sys
import tempfile
import time

from savi_notes import config

vault = os.path.join(tempfile.mkdtemp(), "vault")
os.makedirs(vault)
with open(os.path.join(vault, "Boot test.md"), "w", encoding="utf-8") as f:
  f.write("---\ntags: [ci]\n---\nA **note** with a [[link]] and a #tag.\n\n> [!tip] Callout\n> Body\n")
cfg = config.load()
cfg.update({"vault": vault, "semantic": False, "sync": False})
config.save(cfg)

env = dict(os.environ, QT_QPA_PLATFORM="offscreen", SAVI_NOTES_NO_UPDATE_CHECK="1")
proc = subprocess.Popen([sys.executable, "-m", "savi_notes", "Boot test"], env=env,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
time.sleep(10)
alive = proc.poll() is None
proc.terminate()
try:
  output = proc.communicate(timeout=10)[0]
except subprocess.TimeoutExpired:
  proc.kill()
  output = proc.communicate()[0]
print(output)
bad = [l for l in output.splitlines() if "is not installed" in l or "Type " in l and "unavailable" in l
       or "error" in l.lower() and "DeprecationWarning" not in l and "textinput" not in l]
if not alive:
  sys.exit("the app exited early with code %s" % proc.returncode)
if bad:
  sys.exit("problems in the log:\n" + "\n".join(bad))
print("boot ok")
