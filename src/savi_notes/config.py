"""Where Savi Notes keeps its settings, data and caches on each platform."""

import json
import os

from platformdirs import user_cache_dir, user_config_dir, user_data_dir, user_documents_dir

APP = "savi-notes"

DEFAULTS = {
  "vault": "",
  # Meaning search: a local embedding model through llama.cpp, downloaded on first use.
  "semantic": True,
  # Commit, pull and push the vault while the app is open, when it is a git repo.
  "sync": True,
  # "system", "dark" or "light".
  "theme": "system",
}


def config_dir():
  return user_config_dir(APP, appauthor=False)


def data_dir():
  return user_data_dir(APP, appauthor=False)


def cache_dir():
  return user_cache_dir(APP, appauthor=False)


def path():
  return os.path.join(config_dir(), "config.json")


def default_vault():
  return os.path.join(user_documents_dir(), "Savi Notes")


def load():
  try:
    with open(path(), encoding="utf-8") as f:
      data = json.load(f)
  except (OSError, ValueError):
    data = {}
  merged = dict(DEFAULTS)
  merged.update(data if isinstance(data, dict) else {})
  if merged["vault"]:
    merged["vault"] = os.path.expanduser(merged["vault"])
  return merged


def save(cfg):
  os.makedirs(config_dir(), exist_ok=True)
  with open(path(), "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=2)
    f.write("\n")
