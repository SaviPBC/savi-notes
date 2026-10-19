"""Start the app headless for a few seconds and fail on anything QML or the
engine complains about: once signed out (the sign-in screen), then signed in
with a note open, against a gateway that isn't there. CI runs this on every
platform."""

import base64
import os
import subprocess
import sys
import time

from savi_notes import account, config, crypto

cfg = config.load()
cfg.update({"semantic": False, "gateway": "http://127.0.0.1:9"})
config.save(cfg)
account.clear()


def boot(*args):
  env = dict(os.environ, QT_QPA_PLATFORM="offscreen", SAVI_NOTES_NO_UPDATE_CHECK="1", SAVI_NOTES_FOREGROUND="1")
  proc = subprocess.Popen([sys.executable, "-m", "savi_notes", *args], env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
  time.sleep(10)
  alive = proc.poll() is None
  proc.terminate()
  try:
    output = proc.communicate(timeout=15)[0]
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


boot()

os.makedirs(config.vault_dir(), exist_ok=True)
with open(os.path.join(config.vault_dir(), "Boot test.md"), "w", encoding="utf-8") as f:
  f.write("---\ntags: [ci]\n---\nA **note** with a [[link]] and a #tag.\n\n> [!tip] Callout\n> Body\n")
account.save({"gateway": cfg["gateway"], "access": "token", "refresh": "", "expires": time.time() + 3600,
              "email": "boot@bysavi.com", "key": base64.b64encode(crypto.new_key()).decode()})
boot("Boot test")
print("boot ok")
