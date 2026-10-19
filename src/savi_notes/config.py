"""Where Savi Notes keeps its settings, data and caches on each platform."""

import json
import os

from platformdirs import user_cache_dir, user_config_dir, user_data_dir

APP = "savi-notes"

DEFAULTS = {
  # The Savi AI Core, which signs people in and holds their encrypted notes.
  "gateway": "https://aigateway.bysavi.com",
  # Meaning search: a local embedding model through llama.cpp, downloaded on first use.
  "semantic": True,
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


def theme_path():
  """An optional theme: colours, fonts, shapes, and the name and icon the launcher shows.
  Wolfen writes one for its current theme; without it the app keeps the Savi look."""
  return os.path.join(config_dir(), "theme.toml")


def vault_dir():
  """The local copy of the notes. Not a setting: the AI Core holds the notes, and this is
  the plain markdown the editor, search and the Claude skill read."""
  return os.path.join(data_dir(), "Notes")


def load():
  try:
    with open(path(), encoding="utf-8") as f:
      data = json.load(f)
  except (OSError, ValueError):
    data = {}
  merged = dict(DEFAULTS)
  merged.update(data if isinstance(data, dict) else {})
  merged["gateway"] = merged["gateway"].rstrip("/")
  return merged


def save(cfg):
  os.makedirs(config_dir(), exist_ok=True)
  with open(path(), "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=2)
    f.write("\n")
