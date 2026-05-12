"""Langfuse SDK wrapper — singleton client for trace management."""

from __future__ import annotations

import logging
import threading

from langfuse import Langfuse

from blackbeard.config import settings

logger = logging.getLogger(__name__)

_client: Langfuse | None = None
_lock = threading.Lock()


def get_langfuse() -> Langfuse | None:
    """Get or create the Langfuse client singleton.

    Returns None if Langfuse is not configured (missing keys).
    """
    global _client

    if _client is not None:
        return _client

    with _lock:
        # Double-check after acquiring lock
        if _client is not None:
            return _client

        if not settings.langfuse_public_key or not settings.langfuse_secret_key:
            logger.info("Langfuse not configured (missing public/secret key), tracing disabled")
            return None

        try:
            _client = Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_host,
                release=f"blackbeard-{settings.app_name}",
            )
            logger.info(f"Langfuse client initialized (host={settings.langfuse_host})")
            return _client
        except Exception as e:
            logger.warning(f"Failed to initialize Langfuse client: {e}")
            return None


def shutdown_langfuse() -> None:
    """Flush and shutdown the Langfuse client."""
    global _client
    if _client is not None:
        try:
            _client.flush()
            _client.shutdown()
        except Exception as e:
            logger.warning(f"Error shutting down Langfuse: {e}")
        _client = None
