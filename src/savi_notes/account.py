"""Signing in to the Savi AI Core, and talking to it afterwards.

The app is a public OAuth client: it opens the browser on the gateway's
consent screen and catches the code on a loopback port (RFC 8252), with PKCE
in place of a secret. The tokens and the note key are kept in one file in the
config directory, readable only by this user. That is as well protected as the
notes themselves, which sit beside it in plain markdown.
"""

import base64
import hashlib
import json
import os
import secrets
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

from . import __version__, config

CLIENT_ID = "09b2eaa3-950b-4c40-be14-7eed31b2f22c"
SCOPE = "notes"
PLATFORM = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")


class Offline(Exception):
  """The gateway could not be reached."""


class SignedOut(Exception):
  """The gateway no longer accepts this sign-in: revoked, expired, or never made."""


class Refused(Exception):
  def __init__(self, status, body):
    super().__init__("the AI Core answered %d" % status)
    self.status = status
    self.body = body


class Cancelled(Exception):
  """The person declined on the consent screen, or started over."""


def path():
  return os.path.join(config.config_dir(), "account.json")


def load():
  try:
    with open(path(), encoding="utf-8") as f:
      return json.load(f)
  except (OSError, ValueError):
    return {}


def save(account):
  os.makedirs(config.config_dir(), exist_ok=True)
  tmp = path() + ".tmp"
  fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
  with os.fdopen(fd, "w", encoding="utf-8") as f:
    json.dump(account, f)
  os.replace(tmp, path())


def clear():
  try:
    os.remove(path())
  except FileNotFoundError:
    pass


def note_key(account):
  return base64.b64decode(account["key"]) if account.get("key") else None


def b64url(data):
  return base64.urlsafe_b64encode(data).decode().rstrip("=")


def token_request(gateway, form):
  data = urllib.parse.urlencode(form).encode()
  request = urllib.request.Request(gateway + "/oauth/token", data, {"Accept": "application/json"})
  try:
    with urllib.request.urlopen(request, timeout=30) as r:
      reply = json.load(r)
  except urllib.error.HTTPError as e:
    raise SignedOut("the AI Core would not issue a token (%d)" % e.code) from None
  except (urllib.error.URLError, OSError) as e:
    raise Offline(str(e)) from None
  return {"access": reply["access_token"], "refresh": reply.get("refresh_token", ""),
          "expires": int(time.time()) + int(reply.get("expires_in", 3600))}


def sign_in(gateway, cancel, opener=webbrowser.open):
  """Blocks until the browser comes back or `cancel` (a threading.Event) is set."""
  verifier = secrets.token_urlsafe(64)
  state = secrets.token_urlsafe(16)
  result = {}

  class Callback(BaseHTTPRequestHandler):
    def do_GET(self):
      url = urllib.parse.urlparse(self.path)
      query = urllib.parse.parse_qs(url.query)
      if url.path != "/callback" or query.get("state", [""])[0] != state:
        self.send_error(404)
        return
      result["code"] = query.get("code", [""])[0]
      result["error"] = query.get("error", [""])[0]
      if result["code"]:
        self.send_response(302)
        self.send_header("Location", gateway + "/notes/signed-in")
        self.end_headers()
        return
      page = b"<!doctype html><title>Savi Notes</title><p style='font-family:sans-serif'>Sign-in cancelled. You can close this tab.</p>"
      self.send_response(200)
      self.send_header("Content-Type", "text/html; charset=utf-8")
      self.send_header("Content-Length", str(len(page)))
      self.end_headers()
      self.wfile.write(page)

    def log_message(self, *args):
      pass

  server = HTTPServer(("127.0.0.1", 0), Callback)
  server.timeout = 0.5
  redirect = "http://127.0.0.1:%d/callback" % server.server_address[1]
  try:
    opener(gateway + "/oauth/authorize?" + urllib.parse.urlencode({
      "client_id": CLIENT_ID, "redirect_uri": redirect, "response_type": "code", "scope": SCOPE, "state": state,
      "code_challenge": b64url(hashlib.sha256(verifier.encode()).digest()), "code_challenge_method": "S256",
    }))
    while not result and not cancel.is_set():
      server.handle_request()
  finally:
    server.server_close()
  if not result.get("code"):
    raise Cancelled(result.get("error") or "cancelled")
  tokens = token_request(gateway, {"grant_type": "authorization_code", "client_id": CLIENT_ID,
                                   "redirect_uri": redirect, "code_verifier": verifier, "code": result["code"]})
  return {"gateway": gateway, **tokens}


class Client:
  """Requests to /notes/v1 as the signed-in person, refreshing the token as it runs out."""

  def __init__(self, account):
    self.account = account
    self.lock = threading.Lock()

  def refresh(self):
    if not self.account.get("refresh"):
      raise SignedOut("no refresh token")
    self.account.update(token_request(self.account["gateway"], {
      "grant_type": "refresh_token", "client_id": CLIENT_ID, "refresh_token": self.account["refresh"], "scope": SCOPE}))
    save(self.account)

  def call(self, method, path, body=None, raw=None):
    """JSON in and out, or raw bytes either way when `raw` is given or the reply is binary."""
    with self.lock:
      if self.account.get("expires", 0) < time.time() + 60:
        self.refresh()
    for attempt in (0, 1):
      headers = {"Authorization": "Bearer " + self.account["access"], "Accept": "application/json",
                 "X-Savi-Notes-Version": __version__, "X-Savi-Notes-Platform": PLATFORM}
      data = raw
      if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
      elif raw is not None:
        headers["Content-Type"] = "application/octet-stream"
      request = urllib.request.Request(self.account["gateway"] + "/notes/v1" + path, data, headers, method=method)
      try:
        with urllib.request.urlopen(request, timeout=60) as r:
          payload = r.read()
          if r.headers.get_content_type() == "application/json":
            return json.loads(payload or b"null")
          return payload
      except urllib.error.HTTPError as e:
        if e.code == 401 and attempt == 0:
          with self.lock:
            self.refresh()
          continue
        if e.code == 401:
          raise SignedOut("the AI Core no longer accepts this sign-in") from None
        payload = e.read()
        try:
          payload = json.loads(payload)
        except ValueError:
          pass
        raise Refused(e.code, payload) from None
      except (urllib.error.URLError, OSError) as e:
        raise Offline(str(e)) from None
