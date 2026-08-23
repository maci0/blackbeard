"""Tests for LiteLLM spend aggregation (blackbeard.litellm.spend)."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from blackbeard.litellm.spend import fetch_execution_spend, sum_spend_entries

# ---------------------------------------------------------------------------
# sum_spend_entries
# ---------------------------------------------------------------------------


def test_sum_empty_returns_none():
    """No entries means spend is unknown, not zero."""
    assert sum_spend_entries([]) is None


def test_sum_entries_without_spend_returns_none():
    assert sum_spend_entries([{"model": "gpt-4"}, {}, {"other": 1}]) is None


def test_sum_single_entry():
    assert sum_spend_entries([{"spend": 0.5}]) == Decimal("0.500000")


def test_sum_accumulates_across_entries():
    entries = [{"spend": 0.1}, {"spend": 0.2}, {"spend": "0.3"}]
    assert sum_spend_entries(entries) == Decimal("0.600000")


def test_sum_ignores_non_numeric_spend():
    entries = [{"spend": "abc"}, {"spend": None}, {"spend": 1.25}]
    assert sum_spend_entries(entries) == Decimal("1.250000")


def test_sum_rejects_boolean_spend():
    """isinstance(True, int) must not smuggle a 1 USD spend into the total."""
    assert sum_spend_entries([{"spend": True}, {"spend": False}]) is None
    assert sum_spend_entries([{"spend": True}, {"spend": 2.0}]) == Decimal("2.000000")


def test_sum_quantizes_to_stored_precision_half_up():
    """NUMERIC(14,6) storage: half-up at the 6th decimal, not banker's."""
    assert sum_spend_entries([{"spend": 0.0000005}]) == Decimal("0.000001")
    assert sum_spend_entries([{"spend": 0.0000015}]) == Decimal("0.000002")


def test_sum_negative_total_clamped_to_zero():
    """The cost_usd CHECK constraint forbids negatives; never persist one."""
    entries = [{"spend": 1.0}, {"spend": -4.0}]
    assert sum_spend_entries(entries) == Decimal("0.000000")


def test_sum_skips_non_dict_entries():
    assert sum_spend_entries(["nope", 42, None, {"spend": 2}]) == Decimal("2.000000")


def test_sum_float_noise_not_baked_in():
    """str() conversion keeps 0.1 + 0.2 exact instead of 0.30000000000000004."""
    assert sum_spend_entries([{"spend": 0.1}, {"spend": 0.2}]) == Decimal("0.300000")


# ---------------------------------------------------------------------------
# _extract_entries via fetch_execution_spend
# ---------------------------------------------------------------------------

_SPEND_URL = "http://litellm:4000/spend/logs"


@pytest.fixture
def any_execution_id() -> object:
    from uuid import uuid4

    return uuid4()


async def test_fetch_parses_list_payload(any_execution_id):
    resp = httpx.Response(200, json=[{"spend": 0.25}], request=httpx.Request("GET", _SPEND_URL))
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=resp):
        total = await fetch_execution_spend(any_execution_id)  # type: ignore[arg-type]
    assert total == Decimal("0.250000")


async def test_fetch_parses_results_wrapper(any_execution_id):
    resp = httpx.Response(
        200,
        json={"results": [{"spend": 1.5}, {"spend": 0.25}]},
        request=httpx.Request("GET", _SPEND_URL),
    )
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=resp):
        total = await fetch_execution_spend(any_execution_id)  # type: ignore[arg-type]
    assert total == Decimal("1.750000")


async def test_fetch_no_entries_returns_none(any_execution_id):
    resp = httpx.Response(200, json={"results": []}, request=httpx.Request("GET", _SPEND_URL))
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=resp):
        total = await fetch_execution_spend(any_execution_id)  # type: ignore[arg-type]
    assert total is None


async def test_fetch_http_error_returns_none(any_execution_id):
    resp = httpx.Response(503, request=httpx.Request("GET", _SPEND_URL))
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=resp):
        total = await fetch_execution_spend(any_execution_id)  # type: ignore[arg-type]
    assert total is None


async def test_fetch_transport_error_returns_none(any_execution_id):
    with patch(
        "httpx.AsyncClient.get",
        new_callable=AsyncMock,
        side_effect=httpx.ConnectError("connection refused"),
    ):
        total = await fetch_execution_spend(any_execution_id)  # type: ignore[arg-type]
    assert total is None


async def test_fetch_malformed_json_returns_none(any_execution_id):
    resp = httpx.Response(200, text="not-json", request=httpx.Request("GET", _SPEND_URL))
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=resp):
        total = await fetch_execution_spend(any_execution_id)  # type: ignore[arg-type]
    assert total is None
