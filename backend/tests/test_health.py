"""Tests for health endpoint."""


async def test_health_returns_ok(client):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "blackbeard"
    assert "version" in data


async def test_health_response_has_no_extra_fields(client):
    """Health response should only contain status, service, and version — no internal details."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert set(data.keys()) == {"status", "service", "version", "uptime_s"}
