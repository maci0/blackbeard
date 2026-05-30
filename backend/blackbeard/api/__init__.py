"""REST API layer: routers, middleware, and request/response handling."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

RETRY_HEADERS_30: dict[str, str] = {"Retry-After": "30"}
MUTATION_RATE_MSG = "Too many mutation requests. Try again later."


async def smart_total(
    session: AsyncSession,
    items: list[Any],
    limit: int,
    offset: int,
    count_stmt: Any,
) -> int:
    """Derive total count without a DB query when the page is incomplete."""
    if len(items) < limit and (len(items) > 0 or offset == 0):
        return offset + len(items)
    result = await session.execute(count_stmt)
    return int(result.scalar_one())
