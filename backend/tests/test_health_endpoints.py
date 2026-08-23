"""Integration tests for health check endpoints (api/health.py).

Covers the liveness endpoint (/health) and readiness endpoint
(/health/ready) with mocked external dependencies (Valkey, LiteLLM,
database).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from httpx import AsyncClient, Response

from tests.conftest import API_KEY_HEADER

_VALKEY_UP = {"status": "up", "latency_ms": 1.0}
_LITELLM_UP = {"status": "up", "latency_ms": 2.0}
_CHECK_DOWN = {"status": "down", "reason": "connection_failed", "latency_ms": 5.0}


async def _ready(
    client: AsyncClient,
    valkey: dict,
    litellm: dict,
) -> Response:
    """GET /health/ready with the Valkey/LiteLLM dependency checks mocked."""
    with (
        patch(
            "blackbeard.api.health._check_valkey",
            new_callable=AsyncMock,
            return_value=valkey,
        ),
        patch(
            "blackbeard.api.health._check_litellm",
            new_callable=AsyncMock,
            return_value=litellm,
        ),
    ):
        return await client.get("/api/v1/health/ready", headers=API_KEY_HEADER)


# ---------------------------------------------------------------------------
# GET /health (liveness)
# ---------------------------------------------------------------------------


async def test_health_liveness(client: AsyncClient):
    """GET /health returns 200 with expected shape."""
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "blackbeard"
    assert isinstance(data["version"], str)
    assert len(data["version"]) > 0
    assert "uptime_s" in data
    assert isinstance(data["uptime_s"], (int, float))


async def test_health_no_cache_header(client: AsyncClient):
    """GET /health response includes Cache-Control: no-cache."""
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    cache_ctrl = resp.headers.get("cache-control", "")
    assert "no-cache" in cache_ctrl


async def test_health_is_public(client: AsyncClient):
    """GET /health does not require authentication."""
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /metrics (Prometheus)
# ---------------------------------------------------------------------------


async def test_metrics_is_public(client: AsyncClient):
    """GET /metrics does not require authentication (scrape path)."""
    resp = await client.get("/api/v1/metrics")
    assert resp.status_code == 200


async def test_metrics_exposes_red_series(client: AsyncClient):
    """GET /metrics returns Prometheus text with HTTP RED + executor gauges."""
    # Generate at least one request sample first.
    await client.get("/api/v1/health")
    resp = await client.get("/api/v1/metrics")
    assert resp.status_code == 200
    body = resp.text
    assert "http_requests_total" in body
    assert "http_request_duration_seconds" in body
    assert "blackbeard_active_executions" in body
    assert "blackbeard_executor_queued_tasks" in body
    assert "blackbeard_executor_max_workers" in body
    assert "blackbeard_executor_saturated" in body
    assert "blackbeard_executions_total" in body
    assert "blackbeard_execution_duration_seconds" in body
    assert "blackbeard_webhook_deliveries_total" in body
    assert "blackbeard_sse_active" in body
    assert "blackbeard_sse_max" in body


# ---------------------------------------------------------------------------
# GET /health/ready (readiness)
# ---------------------------------------------------------------------------


async def test_readiness_healthy(client: AsyncClient):
    """GET /health/ready returns healthy when all components are up."""
    resp = await _ready(client, _VALKEY_UP, _LITELLM_UP)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["service"] == "blackbeard"
    assert "checks" in data
    assert "database" in data["checks"]
    assert "valkey" in data["checks"]
    assert "litellm" in data["checks"]
    assert "executor" in data["checks"]


async def test_readiness_degraded_when_valkey_down(client: AsyncClient):
    """GET /health/ready returns degraded when Valkey is down (soft dependency)."""
    resp = await _ready(client, _CHECK_DOWN, _LITELLM_UP)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "degraded"
    assert data["checks"]["valkey"]["status"] == "down"


async def test_readiness_degraded_when_litellm_down(client: AsyncClient):
    """GET /health/ready returns degraded when LiteLLM is down (soft dependency)."""
    resp = await _ready(client, _VALKEY_UP, _CHECK_DOWN)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "degraded"
    assert data["checks"]["litellm"]["status"] == "down"


async def test_readiness_has_uptime(client: AsyncClient):
    """GET /health/ready response includes uptime_s."""
    resp = await _ready(client, _VALKEY_UP, _LITELLM_UP)

    assert resp.status_code == 200
    data = resp.json()
    assert "uptime_s" in data
    assert isinstance(data["uptime_s"], (int, float))


async def test_readiness_no_cache_header(client: AsyncClient):
    """GET /health/ready response includes Cache-Control: no-cache."""
    resp = await _ready(client, _VALKEY_UP, _LITELLM_UP)

    assert resp.status_code == 200
    cache_ctrl = resp.headers.get("cache-control", "")
    assert "no-cache" in cache_ctrl


async def test_readiness_executor_check(client: AsyncClient):
    """GET /health/ready includes executor pool status."""
    resp = await _ready(client, _VALKEY_UP, _LITELLM_UP)

    assert resp.status_code == 200
    data = resp.json()
    executor = data["checks"]["executor"]
    assert executor["status"] in ("up", "saturated")
    assert "active_threads" in executor
    assert "max_workers" in executor


async def test_readiness_database_check(client: AsyncClient):
    """GET /health/ready database check reports up with in-memory SQLite."""
    resp = await _ready(client, _VALKEY_UP, _LITELLM_UP)

    assert resp.status_code == 200
    data = resp.json()
    assert data["checks"]["database"]["status"] == "up"
    assert "latency_ms" in data["checks"]["database"]


async def test_readiness_both_soft_deps_down(client: AsyncClient):
    """GET /health/ready returns degraded when both Valkey and LiteLLM are down."""
    resp = await _ready(client, _CHECK_DOWN, _CHECK_DOWN)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "degraded"
