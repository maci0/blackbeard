"""LiteLLM spend lookup for executions.

Fetches per-request spend logs from the LiteLLM proxy and aggregates them
into a single ``Decimal`` total suitable for ``Execution.cost_usd``
(NUMERIC(14,6)). All network work is best-effort: callers must treat
``None`` as "spend unknown" and leave any stored value untouched.
"""

from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any

from blackbeard.http_client import get_litellm_client
from blackbeard.logging_config import request_id_var

if TYPE_CHECKING:
    from uuid import UUID

logger = logging.getLogger(__name__)

__all__ = ["fetch_execution_spend", "sum_spend_entries"]

# Matches Execution.cost_usd NUMERIC(14,6) — 6 digits after the decimal point.
_QUANTUM = Decimal("0.000001")

_MAX_ENTRIES = 10_000


def _to_decimal(value: Any) -> Decimal | None:
    """Convert a JSON spend value to Decimal exactly, or None if not numeric.

    Booleans are rejected (``isinstance(True, int)`` would otherwise pass).
    Floats go through ``str()`` so ``0.1 + 0.2`` style binary noise is not
    baked into the sum; the Decimal addition is then exact.
    """
    if isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (ArithmeticError, ValueError):
        return None


def sum_spend_entries(entries: list[Any]) -> Decimal | None:
    """Sum the ``spend`` field across LiteLLM spend-log entries.

    Returns ``None`` when no entry carries a numeric spend (the caller cannot
    distinguish "no data" from zero and should keep the stored value). The
    result is clamped to >= 0 — the ``cost_usd`` column forbids negatives —
    and quantized to the stored precision using half-up rounding.
    """
    total = Decimal(0)
    seen = 0
    for entry in entries[:_MAX_ENTRIES]:
        if not isinstance(entry, dict):
            continue
        value = _to_decimal(entry.get("spend"))
        if value is None:
            continue
        seen += 1
        total += value
    if seen == 0:
        return None
    if total < 0:
        return Decimal("0").quantize(_QUANTUM, rounding=ROUND_HALF_UP)
    return total.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


def _extract_entries(payload: Any) -> list[Any]:
    """Pull the results list out of the known /spend/logs response shapes."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("results", "response", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return []


async def fetch_execution_spend(execution_id: UUID) -> Decimal | None:
    """Return the aggregated USD spend recorded for an execution, or None.

    Uses the same correlation contract as ``GET /executions/{id}/spend``:
    ``GET /spend/logs?request_id=<execution_id>`` on the LiteLLM proxy.
    Any transport or shape error logs a warning and returns ``None``; this
    runs on the execution completion path and must never fail a run.
    """
    from blackbeard.config import settings

    try:
        client = get_litellm_client("litellm-spend-total", timeout=5.0)
        resp = await client.get(
            f"{settings.litellm_proxy_url}/spend/logs",
            params={"request_id": str(execution_id)},
            headers={"X-Request-Id": request_id_var.get("-")},
        )
        resp.raise_for_status()
        payload: Any = resp.json()
    except Exception as exc:
        logger.warning(
            "Spend lookup failed for execution %s: %s: %s",
            execution_id,
            type(exc).__name__,
            str(exc)[:200],
            extra={
                "event": "execution_spend_fetch_failed",
                "execution_id": str(execution_id),
                "error_type": type(exc).__name__,
            },
        )
        return None

    total = sum_spend_entries(_extract_entries(payload))
    if total is None:
        logger.debug(
            "No spend entries for execution %s",
            execution_id,
            extra={"event": "execution_spend_empty", "execution_id": str(execution_id)},
        )
    return total
