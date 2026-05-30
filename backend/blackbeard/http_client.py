"""Shared lazy-initialized httpx client factories (async + sync).

Centralizes lock-always initialization + shutdown boilerplate across
chat, health, executions, and discovery_tools modules.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, TypeVar

_T = TypeVar("_T")

import httpx

__all__ = [
    "close_all_clients",
    "close_client",
    "get_client",
    "get_litellm_client",
    "get_sync_client",
]

logger = logging.getLogger(__name__)

_clients: dict[str, httpx.AsyncClient] = {}
_sync_clients: dict[str, httpx.Client] = {}
_lock = threading.Lock()


_DEFAULT_TIMEOUT = 30.0


def _get_or_create(
    cache: dict[str, _T],
    name: str,
    factory: type[_T],
    client_type: str,
    kwargs: dict[str, Any],
) -> _T:
    """Shared lock-always factory for sync/async httpx clients."""
    with _lock:
        client = cache.get(name)
        if client is not None:
            return client
        kwargs.setdefault("timeout", _DEFAULT_TIMEOUT)
        client = factory(**kwargs)
        cache[name] = client
        logger.debug(
            "HTTP client created: %s",
            name,
            extra={"event": "http_client_created", "client_name": name, "client_type": client_type},
        )
        return client


def get_client(name: str, **kwargs: Any) -> httpx.AsyncClient:
    """Return a named httpx.AsyncClient, creating it on first call.

    Thread-safe via lock-always (safe under both GIL and free-threaded Python).
    kwargs are forwarded to httpx.AsyncClient() on first creation and ignored
    on subsequent calls. Applies a 30s default timeout if none is specified.
    """
    return _get_or_create(_clients, name, httpx.AsyncClient, "async", kwargs)


def get_sync_client(name: str, **kwargs: Any) -> httpx.Client:
    """Return a named httpx.Client, creating it on first call.

    Thread-safe via lock-always (safe under both GIL and free-threaded Python).
    kwargs are forwarded to httpx.Client() on first creation and ignored
    on subsequent calls. Applies a 30s default timeout if none is specified.
    """
    return _get_or_create(_sync_clients, name, httpx.Client, "sync", kwargs)


def get_litellm_client(name: str, timeout: float = _DEFAULT_TIMEOUT) -> httpx.AsyncClient:
    """Return a shared httpx client pre-configured with LiteLLM Bearer auth."""
    from blackbeard.config import settings

    key = settings.litellm_master_key.get_secret_value()
    return get_client(name, timeout=timeout, headers={"Authorization": f"Bearer {key}"})


async def close_client(name: str) -> None:
    """Close and remove a named client."""
    with _lock:
        client = _clients.pop(name, None)
    if client is not None:
        await client.aclose()


async def close_all_clients() -> None:
    """Close all tracked clients (async + sync). Called during app shutdown."""
    with _lock:
        async_snapshot = dict(_clients)
        _clients.clear()
        sync_snapshot = dict(_sync_clients)
        _sync_clients.clear()
    total = len(async_snapshot) + len(sync_snapshot)
    if total:
        logger.info(
            "Closing %d HTTP clients (async=%d sync=%d)",
            total,
            len(async_snapshot),
            len(sync_snapshot),
            extra={
                "event": "http_clients_closing",
                "async_count": len(async_snapshot),
                "sync_count": len(sync_snapshot),
            },
        )
    for name, client in async_snapshot.items():
        try:
            await client.aclose()
        except Exception as exc:
            logger.warning(
                "Error closing async HTTP client '%s'",
                name,
                exc_info=True,
                extra={
                    "event": "http_client_close_error",
                    "client_name": name,
                    "client_type": "async",
                    "error_type": type(exc).__name__,
                },
            )
    for name, sync_client in sync_snapshot.items():
        try:
            sync_client.close()
        except Exception as exc:
            logger.warning(
                "Error closing sync HTTP client '%s'",
                name,
                exc_info=True,
                extra={
                    "event": "http_client_close_error",
                    "client_name": name,
                    "client_type": "sync",
                    "error_type": type(exc).__name__,
                },
            )
