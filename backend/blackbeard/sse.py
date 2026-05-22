"""SSE connection tracking — shared between executions and health endpoints."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from blackbeard.config import settings

semaphore = asyncio.Semaphore(settings.max_concurrent_sse)
_active_count = 0


@asynccontextmanager
async def acquire_stream() -> AsyncIterator[bool]:
    """Try to acquire an SSE slot. Yields True on success, False if full.

    Ensures active_count stays in sync with the semaphore via
    paired increment/decrement in a context manager.
    """
    global _active_count
    try:
        await asyncio.wait_for(semaphore.acquire(), timeout=0)
    except TimeoutError:
        yield False
        return
    _active_count += 1
    try:
        yield True
    finally:
        _active_count -= 1
        semaphore.release()


def get_active_count() -> int:
    """Return the current number of active SSE streams."""
    return _active_count


def get_status() -> dict[str, int]:
    """Return current SSE stream usage for health checks."""
    return {"active": _active_count, "max": settings.max_concurrent_sse}
