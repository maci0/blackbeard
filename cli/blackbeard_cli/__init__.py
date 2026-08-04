"""Blackbeard CLI — standalone command-line interface."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("blackbeard-cli")
except PackageNotFoundError:  # running from source without an installed dist
    __version__ = "0.0.0.dev0"
