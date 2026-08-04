"""API key state management for HTTP auth middleware.

The expected API key is loaded from settings at import time and may be
replaced at runtime by ``set_api_key()`` (used during startup to inject
ephemeral keys in debug mode).  All reads/writes use a lock-always
pattern for safety under both GIL and free-threaded Python.
"""

from __future__ import annotations

import threading

from blackbeard.config import settings

_EXPECTED_API_KEY = settings.blackbeard_api_key.get_secret_value()
_api_key_lock = threading.Lock()


def set_api_key(key: str) -> None:
    """Replace the expected API key (used by startup to inject ephemeral keys).

    Uses lock-always pattern (safe under both GIL and free-threaded Python).
    """
    if len(key) < 16:
        raise ValueError("API key must be at least 16 characters")
    with _api_key_lock:
        global _EXPECTED_API_KEY
        _EXPECTED_API_KEY = key


def get_api_key() -> str:
    """Return the currently active API key.

    Uses lock-always pattern (safe under both GIL and free-threaded Python).
    """
    with _api_key_lock:
        return _EXPECTED_API_KEY
