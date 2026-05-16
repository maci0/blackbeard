"""SSE connection tracking — shared between executions and health endpoints."""

from __future__ import annotations

import asyncio

MAX_CONCURRENT_SSE = 20
semaphore = asyncio.Semaphore(MAX_CONCURRENT_SSE)
active_count = 0


def get_status() -> dict[str, int]:
    """Return current SSE stream usage for health checks."""
    return {"active": active_count, "max": MAX_CONCURRENT_SSE}
