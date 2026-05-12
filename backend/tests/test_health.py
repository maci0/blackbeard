"""Tests for health endpoint."""

import pytest


@pytest.mark.asyncio
async def test_health_returns_ok(client):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "blackbeard"


@pytest.mark.asyncio
async def test_protected_endpoint_requires_api_key(client):
    """Any non-public endpoint should require X-API-Key."""
    response = await client.get("/api/v1/agents")
    assert response.status_code == 401
