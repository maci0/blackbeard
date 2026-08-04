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
from blackbeard.metrics import set_sse_usage

_max_sse = settings.max_concurrent_sse
semaphore = asyncio.Semaphore(_max_sse)
_active_streams = 0
_active_lock = threading.Lock()
# Serializes the locked()+acquire pair so concurrent connects cannot slip
# past a free-slot check and then block forever on a depleted semaphore
# (the previous check-then-await-acquire path was a TOCTOU).
_slot_lock = asyncio.Lock()

# Export configured max immediately so scrapes before any connect are correct.
set_sse_usage(0, _max_sse)


def _publish_sse_gauge() -> None:
    """Push current SSE usage into Prometheus gauges (under lock)."""
    set_sse_usage(_active_streams, _max_sse)


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
                _publish_sse_gauge()
    if not acquired:
        yield False
        return
    try:
        yield True
    finally:
        with _active_lock:
            _active_streams -= 1
            _publish_sse_gauge()
        semaphore.release()


def get_active_count() -> int:
    """Return the current number of active SSE streams."""
    with _active_lock:
        return _active_streams


def get_status() -> dict[str, int]:
    """Return current SSE stream usage for health checks."""
    return {"active": get_active_count(), "max": _max_sse}
