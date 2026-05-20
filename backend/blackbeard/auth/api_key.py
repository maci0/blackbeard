"""API key state management — shared by HTTP and gRPC auth layers.

The expected API key is loaded from settings at import time and may be
replaced at runtime by ``set_api_key()`` (used during startup to inject
ephemeral keys in debug mode).
"""

from __future__ import annotations

from blackbeard.config import settings

_EXPECTED_API_KEY = settings.blackbeard_api_key.get_secret_value()


def set_api_key(key: str) -> None:
    """Replace the expected API key (used by startup to inject ephemeral keys)."""
    if len(key) < 16:
        raise ValueError("API key must be at least 16 characters")
    global _EXPECTED_API_KEY
    _EXPECTED_API_KEY = key


def get_api_key() -> str:
    """Return the currently active API key."""
    return _EXPECTED_API_KEY
