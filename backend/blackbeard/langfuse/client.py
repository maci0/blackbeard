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

        if not settings.langfuse_public_key or not settings.langfuse_secret_key.get_secret_value():
            logger.info(
                "Langfuse not configured (missing public/secret key), tracing disabled",
                extra={"event": "langfuse_disabled"},
            )
            return None

        try:
            _client = Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key.get_secret_value(),
                base_url=settings.langfuse_host,
                release=f"blackbeard-{settings.app_name}",
            )
            logger.info(
                "Langfuse client initialized (host=%s)",
                settings.langfuse_host,
                extra={"event": "langfuse_initialized", "langfuse_host": settings.langfuse_host},
            )
            return _client
        except Exception as e:
            logger.warning(
                "Failed to initialize Langfuse client: %s",
                e,
                exc_info=True,
                extra={
                    "event": "langfuse_init_failed",
                    "error_type": type(e).__name__,
                    "langfuse_host": settings.langfuse_host,
                },
            )
            return None


def shutdown_langfuse() -> None:
    """Flush and shutdown the Langfuse client."""
    global _client
    if _client is not None:
        try:
            _client.flush()
            _client.shutdown()
        except Exception as e:
            logger.warning(
                "Error shutting down Langfuse: %s",
                e,
                exc_info=True,
                extra={"event": "langfuse_shutdown_error", "error_type": type(e).__name__},
            )
        _client = None
