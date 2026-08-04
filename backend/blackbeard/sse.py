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
# Serializes the locked()+acquire pair so concurrent connects cannot slip
# past a free-slot check and then block forever on a depleted semaphore
# (the previous check-then-await-acquire path was a TOCTOU).
_slot_lock = asyncio.Lock()


@asynccontextmanager
async def acquire_stream() -> AsyncIterator[bool]:
    """Try to acquire an SSE slot. Yields True on success, False if full."""
    global _active_streams
    acquired = False
    async with _slot_lock:
        # Under the lock the locked()/acquire pair is atomic w.r.t. other
        # acquire_stream callers, so we either take a free permit immediately
        # or reject without waiting for a release.
        if not semaphore.locked():
            await semaphore.acquire()
            acquired = True
            with _active_lock:
                _active_streams += 1
    if not acquired:
        yield False
        return
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
