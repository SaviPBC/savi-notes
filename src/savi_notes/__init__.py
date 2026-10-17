"""Savi Notes: markdown notes organised by tags, with search, splits and a Claude Code skill."""

from importlib.metadata import PackageNotFoundError, version

try:
  __version__ = version("savi-notes")
except PackageNotFoundError:  # running from a checkout
  __version__ = "0.0.0"
