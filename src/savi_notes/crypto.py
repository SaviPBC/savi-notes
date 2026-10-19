"""End-to-end encryption for notes.

One random 256-bit key per person, made on their first device. Every note and
attachment is sealed with AES-256-GCM under it before it leaves the computer,
so the AI Core stores ciphertext it has no key for. The key leaves the device
only as the recovery key the person writes down: it is the key itself, in a
form that survives a password manager.

Each sealed blob is bound to its id as associated data, so the server cannot
pass one note's ciphertext off as another's.
"""

import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

VERSION = b"\x01"
CHECK = b"savi-notes key check v1"


class WrongKey(Exception):
  """The key does not open this blob: a mistyped recovery key, or someone else's notes."""


def new_key():
  return os.urandom(32)


def recovery_text(key):
  """52 base32 letters in groups of four, unambiguous to read aloud or retype."""
  letters = base64.b32encode(key).decode().rstrip("=")
  return "-".join(letters[i:i + 4] for i in range(0, len(letters), 4))


def parse_recovery(text):
  letters = "".join(c for c in text.upper() if c.isalnum())
  try:
    key = base64.b32decode(letters + "=" * (-len(letters) % 8))
  except ValueError:
    raise WrongKey("that isn't a recovery key") from None
  if len(key) != 32:
    raise WrongKey("that isn't a recovery key")
  return key


def seal(key, plaintext, bound_to):
  nonce = os.urandom(12)
  return VERSION + nonce + AESGCM(key).encrypt(nonce, plaintext, bound_to.encode())


def unseal(key, blob, bound_to):
  if blob[:1] != VERSION:
    raise WrongKey("unknown format")
  try:
    return AESGCM(key).decrypt(blob[1:13], blob[13:], bound_to.encode())
  except InvalidTag:
    raise WrongKey("this key does not open it") from None


def key_check(key):
  """What the gateway keeps so a new device can tell a right recovery key from a wrong one."""
  return base64.b64encode(seal(key, CHECK, "key-check")).decode()


def opens(key, check):
  try:
    return unseal(key, base64.b64decode(check), "key-check") == CHECK
  except (WrongKey, ValueError):
    return False
