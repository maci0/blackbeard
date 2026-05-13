"""Security tests: authentication, authorization, and data-leakage checks."""

from tests.conftest import API_KEY_HEADER


async def test_health_no_auth_required(client):
    """Health endpoint should not require auth."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200


async def test_api_rejects_no_key(client):
    """Protected endpoints should reject requests without API key."""
    response = await client.get("/api/v1/agents")
    assert response.status_code == 401


async def test_api_rejects_wrong_key(client):
    """Protected endpoints should reject wrong API key."""
    response = await client.get("/api/v1/agents", headers={"X-API-Key": "wrong-key"})
    assert response.status_code == 401


async def test_api_accepts_correct_key(client):
    """Protected endpoints should accept correct API key."""
    response = await client.get("/api/v1/agents", headers=API_KEY_HEADER)
    assert response.status_code == 200


async def test_cors_preflight(client):
    """CORS preflight with valid Origin should return 200 with correct CORS headers."""
    response = await client.options(
        "/api/v1/agents",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-API-Key",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "GET" in response.headers.get("access-control-allow-methods", "")
    assert "X-API-Key" in response.headers.get("access-control-allow-headers", "")


async def test_docs_no_auth(client):
    """OpenAPI docs should not require auth."""
    response = await client.get("/docs")
    assert response.status_code in (200, 307)  # 307 redirect is OK


async def test_error_no_secret_leak(client):
    """Error responses should not leak internal details."""
    response = await client.get(
        "/api/v1/agents/nonexistent",
        headers=API_KEY_HEADER,
    )
    assert response.status_code == 404
    body = response.json()
    detail = str(body.get("detail", ""))
    for forbidden in ("/Users/", "Traceback", "sqlalchemy", "pydantic", "File \"", "line "):
        assert forbidden not in detail, f"Error response leaks internal detail: {forbidden!r}"


async def test_401_response_does_not_leak_key(client):
    """401 error body should not echo back or hint at the real API key."""
    response = await client.get("/api/v1/agents", headers={"X-API-Key": "bad-key"})
    assert response.status_code == 401
    body = response.json()
    detail = str(body.get("detail", ""))
    # Must not contain the actual configured key value
    assert "change-me-in-production" not in detail


async def test_redoc_no_auth(client):
    """ReDoc docs should not require auth."""
    response = await client.get("/redoc")
    assert response.status_code in (200, 307)


async def test_openapi_json_no_auth(client):
    """OpenAPI JSON schema should not require auth."""
    response = await client.get("/openapi.json")
    assert response.status_code == 200
