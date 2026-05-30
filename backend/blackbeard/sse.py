"""SSE connection tracking — shared between executions and health endpoints."""

from __future__ import annotations

import asyncio
import threading
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

__all__ = [
    "acquire_stream",
    "get_active_count",
    "get_status",
]

from blackbeard.config import settings

_max_sse = settings.max_concurrent_sse
semaphore = asyncio.Semaphore(_max_sse)
_active_streams = 0
_active_lock = threading.Lock()


@asynccontextmanager
async def acquire_stream() -> AsyncIterator[bool]:
    """Try to acquire an SSE slot. Yields True on success, False if full."""
    global _active_streams
    try:
        await asyncio.wait_for(semaphore.acquire(), timeout=0)
    except TimeoutError:
        yield False
        return
    with _active_lock:
        _active_streams += 1
    try:
        yield True
    finally:
        with _active_lock:
            _active_streams -= 1
        semaphore.release()


def get_active_count() -> int:
    """Return the current number of active SSE streams."""
    with _active_lock:
        return _active_streams


def get_status() -> dict[str, int]:
    """Return current SSE stream usage for health checks."""
    return {"active": get_active_count(), "max": _max_sse}
