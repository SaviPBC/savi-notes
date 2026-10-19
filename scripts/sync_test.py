"""Two devices syncing through a stand-in for the AI Core's /notes/v1, which
behaves like the real one: ciphertext in and out, a revision per note, one
change cursor per person, 409 on a stale push. Fails loudly on any mismatch."""

import json
import os
import re
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from savi_notes import account, config, crypto, engine, sync  # noqa: E402


class Store:
  def __init__(self):
    self.lock = threading.Lock()
    self.seq = 0
    self.notes = {}
    self.files = {}


def gateway(store):
  class Handler(BaseHTTPRequestHandler):
    def reply(self, status, body=None, raw=None):
      data = raw if raw is not None else json.dumps(body).encode()
      self.send_response(status)
      self.send_header("Content-Type", "application/octet-stream" if raw is not None else "application/json")
      self.send_header("Content-Length", str(len(data)))
      self.end_headers()
      self.wfile.write(data)

    def body(self):
      return self.rfile.read(int(self.headers.get("Content-Length") or 0))

    def do_GET(self):
      with store.lock:
        if self.path.startswith("/notes/v1/changes"):
          since = int(re.search(r"since=(\d+)", self.path).group(1))
          notes = [{"id": k, "revision": v["revision"], "deleted": v["ciphertext"] is None, "ciphertext": v["ciphertext"]}
                   for k, v in store.notes.items() if v["seq"] > since]
          files = [{"id": k, "size": len(v["data"] or b""), "deleted": v["data"] is None}
                   for k, v in store.files.items() if v["seq"] > since]
          return self.reply(200, {"notes": notes, "attachments": files, "cursor": store.seq, "more": False})
        name = self.path.rsplit("/", 1)[1]
        if store.files.get(name, {}).get("data") is None:
          return self.reply(404, {})
        return self.reply(200, raw=store.files[name]["data"])

    def do_PUT(self):
      data = self.body()
      with store.lock:
        name = self.path.rsplit("/", 1)[1]
        if "/attachments/" in self.path:
          if name not in store.files:
            store.seq += 1
            store.files[name] = {"data": data, "seq": store.seq}
          return self.reply(200, {"seq": store.files[name]["seq"]})
        body = json.loads(data)
        note = store.notes.get(name, {"revision": 0})
        if note["revision"] != body["base_revision"]:
          return self.reply(409, {"error": "conflict"})
        store.seq += 1
        store.notes[name] = {"ciphertext": body["ciphertext"], "revision": note["revision"] + 1, "seq": store.seq}
        return self.reply(200, {"revision": store.notes[name]["revision"], "seq": store.seq})

    def do_DELETE(self):
      data = self.body()
      with store.lock:
        name = self.path.rsplit("/", 1)[1]
        store.seq += 1
        if "/attachments/" in self.path:
          store.files[name] = {"data": None, "seq": store.seq}
          return self.reply(200, {"seq": store.seq})
        note = store.notes[name]
        if note["revision"] != json.loads(data)["base_revision"]:
          store.seq -= 1
          return self.reply(409, {"error": "conflict"})
        store.notes[name] = {"ciphertext": None, "revision": note["revision"] + 1, "seq": store.seq}
        return self.reply(200, {"revision": note["revision"] + 1, "seq": store.seq})

    def log_message(self, *args):
      pass

  server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
  threading.Thread(target=server.serve_forever, daemon=True).start()
  return "http://127.0.0.1:%d" % server.server_address[1]


class Device:
  def __init__(self, name, url, key):
    self.root = tempfile.mkdtemp(prefix="savi-sync-" + name + "-")
    self.data = os.path.join(self.root, "data")
    self.events = []
    os.makedirs(os.path.join(self.root, "config"))
    with self.dirs():
      account.save({"gateway": url, "access": "token", "refresh": "", "expires": time.time() + 3600,
                    "email": "someone@bysavi.com", "key": __import__("base64").b64encode(key).decode()})
      self.vault = engine.Vault(os.path.join(self.data, "Notes"))
      os.makedirs(self.vault.root, exist_ok=True)
      self.sync = sync.Sync(self.vault, self.events.append, self.vault.scan)

  def dirs(self):
    device = self

    class Scope:
      def __enter__(self):
        self.saved = (config.data_dir, config.config_dir)
        config.data_dir = lambda: device.data
        config.config_dir = lambda: os.path.join(device.root, "config")

      def __exit__(self, *exc):
        config.data_dir, config.config_dir = self.saved
    return Scope()

  def run(self):
    with self.dirs():
      assert self.sync.run(), self.events[-3:]
    self.vault.scan()

  def write(self, title, text):
    self.vault.write_text(title + ".md", text)

  def read(self, title):
    with open(os.path.join(self.vault.root, title + ".md"), encoding="utf-8") as f:
      return f.read()

  def titles(self):
    self.vault.scan()
    return sorted(n["title"] for n in self.vault.notes.values())


def check(label, got, want):
  if got != want:
    sys.exit("FAIL %s: got %r, want %r" % (label, got, want))
  print("ok  " + label)


def main():
  store = Store()
  url = gateway(store)
  key = crypto.new_key()
  a, b = Device("a", url, key), Device("b", url, key)

  a.write("Groceries", "tags: [home]\n\nmilk, eggs\n")
  a.run()
  b.run()
  check("a new note reaches the other device", b.read("Groceries"), "tags: [home]\n\nmilk, eggs\n")
  check("the server never sees the text", any("milk" in (n["ciphertext"] or "") for n in store.notes.values()), False)

  b.write("Groceries", "tags: [home]\n\nmilk, eggs, bread\n")
  b.run()
  a.run()
  check("an edit comes back", a.read("Groceries"), "tags: [home]\n\nmilk, eggs, bread\n")

  a.write("Groceries", "from a\n")
  b.write("Groceries", "from b\n")
  a.run()
  b.run()
  a.run()
  conflict = [t for t in b.titles() if t.startswith("Groceries (conflict")]
  check("an edit on both sides keeps the later device's text", (a.read("Groceries"), b.read("Groceries")), ("from b\n", "from b\n"))
  check("and the other side's as a conflict copy", [b.read(t) for t in conflict], ["from a\n"])
  check("which reaches the first device too", a.titles(), b.titles())

  with a.dirs():
    new, _ = a.vault.rename("Groceries.md", "Shopping")
    a.sync.renamed("Groceries.md", new)
  a.run()
  b.run()
  check("a rename is a rename", ("Shopping" in b.titles(), "Groceries" in b.titles()), (True, False))
  check("and kept the text", b.read("Shopping"), "from b\n")

  os.makedirs(os.path.join(a.vault.root, "Attachments"), exist_ok=True)
  with open(os.path.join(a.vault.root, "Attachments", "receipt.png"), "wb") as f:
    f.write(b"\x89PNG not really")
  a.run()
  b.run()
  with open(os.path.join(b.vault.root, "Attachments", "receipt.png"), "rb") as f:
    check("an attachment arrives intact", f.read(), b"\x89PNG not really")
  check("and is sealed on the server", any(b"not really" in (f["data"] or b"") for f in store.files.values()), False)

  os.remove(os.path.join(a.vault.root, "Attachments", "receipt.png"))
  with a.dirs():
    a.vault.delete("Shopping.md")
  a.run()
  b.run()
  check("a delete reaches the other device", ("Shopping" in b.titles(), os.path.exists(os.path.join(b.vault.root, "Attachments", "receipt.png"))), (False, False))

  b.write("Deleted here, edited there", "one\n")
  b.run()
  a.run()
  with b.dirs():
    b.vault.delete("Deleted here, edited there.md")
  a.write("Deleted here, edited there", "two\n")
  a.run()
  b.run()
  check("an edit beats a delete", b.read("Deleted here, edited there"), "two\n")

  stranger = Device("c", url, crypto.new_key())
  with stranger.dirs():
    stranger.sync.run()
  check("another key cannot open the notes", stranger.events[-1], {"event": "account", "state": "wrongKey"})

  check("a recovery key round-trips", crypto.parse_recovery(crypto.recovery_text(key).lower().replace("-", " ")), key)
  check("the key check knows its key", (crypto.opens(key, crypto.key_check(key)), crypto.opens(crypto.new_key(), crypto.key_check(key))), (True, False))
  print("sync ok")


if __name__ == "__main__":
  main()
