"""Shared lazy-initialized httpx client factories (async + sync).

Eliminates duplicated double-checked locking + shutdown boilerplate across
chat, health, executions, and discovery_tools modules.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_clients: dict[str, httpx.AsyncClient] = {}
_sync_clients: dict[str, httpx.Client] = {}
_lock = threading.Lock()


def get_client(name: str, **kwargs: Any) -> httpx.AsyncClient:
    """Return a named httpx.AsyncClient, creating it on first call.

    Thread-safe via double-checked locking. kwargs are forwarded to
    httpx.AsyncClient() on first creation and ignored on subsequent calls.
    """
    client = _clients.get(name)
    if client is not None:
        return client
    with _lock:
        client = _clients.get(name)
        if client is not None:
            return client
        client = httpx.AsyncClient(**kwargs)
        _clients[name] = client
        logger.debug(
            "HTTP client created: %s",
            name,
            extra={"event": "http_client_created", "client_name": name, "client_type": "async"},
        )
        return client


def get_sync_client(name: str, **kwargs: Any) -> httpx.Client:
    """Return a named httpx.Client, creating it on first call.

    Thread-safe via double-checked locking. kwargs are forwarded to
    httpx.Client() on first creation and ignored on subsequent calls.
    """
    client = _sync_clients.get(name)
    if client is not None:
        return client
    with _lock:
        client = _sync_clients.get(name)
        if client is not None:
            return client
        client = httpx.Client(**kwargs)
        _sync_clients[name] = client
        logger.debug(
            "HTTP client created: %s",
            name,
            extra={"event": "http_client_created", "client_name": name, "client_type": "sync"},
        )
        return client


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
