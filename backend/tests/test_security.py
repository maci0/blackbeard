"""Security tests: authentication, authorization, and data-leakage checks."""

# Fixtures (db_session, client) are provided by conftest.py
import pytest


@pytest.mark.asyncio
async def test_health_no_auth_required(client):
    """Health endpoint should not require auth."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_api_rejects_no_key(client):
    """Protected endpoints should reject requests without API key."""
    response = await client.get("/api/v1/agents")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_api_rejects_wrong_key(client):
    """Protected endpoints should reject wrong API key."""
    response = await client.get("/api/v1/agents", headers={"X-API-Key": "wrong-key"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_api_accepts_correct_key(client):
    """Protected endpoints should accept correct API key."""
    response = await client.get("/api/v1/agents", headers={"X-API-Key": "change-me-in-production"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_cors_preflight(client):
    """OPTIONS requests should be allowed without auth (CORS preflight)."""
    response = await client.options("/api/v1/agents")
    assert response.status_code in (200, 204, 405)


@pytest.mark.asyncio
async def test_docs_no_auth(client):
    """OpenAPI docs should not require auth."""
    response = await client.get("/docs")
    assert response.status_code in (200, 307)  # 307 redirect is OK


@pytest.mark.asyncio
async def test_error_no_secret_leak(client):
    """Error responses should not leak internal details."""
    response = await client.get(
        "/api/v1/agents/nonexistent",
        headers={"X-API-Key": "change-me-in-production"},
    )
    assert response.status_code == 404
    body = response.json()
    detail = str(body.get("detail", ""))
    assert "/Users/" not in detail
    assert "Traceback" not in detail


@pytest.mark.asyncio
async def test_401_response_does_not_leak_key(client):
    """401 error body should not echo back or hint at the real API key."""
    response = await client.get("/api/v1/agents", headers={"X-API-Key": "bad-key"})
    assert response.status_code == 401
    body = response.json()
    detail = str(body.get("detail", ""))
    # Must not contain the actual configured key value
    assert "change-me-in-production" not in detail


@pytest.mark.asyncio
async def test_redoc_no_auth(client):
    """ReDoc docs should not require auth."""
    response = await client.get("/redoc")
    assert response.status_code in (200, 307)


@pytest.mark.asyncio
async def test_openapi_json_no_auth(client):
    """OpenAPI JSON schema should not require auth."""
    response = await client.get("/openapi.json")
    assert response.status_code == 200
