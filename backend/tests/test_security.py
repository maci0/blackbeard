"""Security tests: authentication, authorization, and data-leakage checks."""

import uuid

from blackbeard.api.middleware import SECURITY_HEADERS
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


async def test_cors_disallows_unauthorized_origin(client):
    """CORS preflight from an unauthorized origin should not reflect that origin."""
    response = await client.options(
        "/api/v1/agents",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    allow_origin = response.headers.get("access-control-allow-origin", "")
    assert allow_origin != "https://evil.example.com", (
        "CORS should not reflect an unauthorized origin"
    )
    assert allow_origin != "*", "CORS must not use wildcard — would allow any origin"
    assert allow_origin in ("", "http://localhost:3000", "http://localhost:5173"), (
        f"Unexpected CORS origin: {allow_origin!r} — should be empty or a configured origin"
    )


async def test_docs_no_auth(client):
    """OpenAPI docs should not require auth."""
    response = await client.get("/docs", follow_redirects=True)
    assert response.status_code == 200, (
        f"OpenAPI docs returned unexpected status {response.status_code}"
    )
    assert len(response.content) > 100, "Docs page should contain substantial HTML content"
    assert b"swagger" in response.content.lower() or b"openapi" in response.content.lower(), (
        "Docs page should contain Swagger/OpenAPI content"
    )


async def test_error_no_secret_leak(client):
    """Error responses should not leak internal details."""
    response = await client.get(
        "/api/v1/agents/nonexistent",
        headers=API_KEY_HEADER,
    )
    assert response.status_code == 404
    body = response.json()
    detail = str(body.get("detail", ""))
    for forbidden in ("/Users/", "Traceback", "sqlalchemy", "pydantic", 'File "', "line "):
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
    response = await client.get("/redoc", follow_redirects=True)
    assert response.status_code == 200
    assert len(response.content) > 100, "ReDoc page should contain substantial HTML content"


async def test_openapi_json_no_auth(client):
    """OpenAPI JSON schema should not require auth and be valid OpenAPI."""
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert "openapi" in data, "Response must be a valid OpenAPI document"
    assert "paths" in data, "OpenAPI document must contain paths"


# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------


async def test_security_headers_present(client):
    """Every response should include all hardened security headers."""
    assert len(SECURITY_HEADERS) > 0, "SECURITY_HEADERS must not be empty"
    response = await client.get("/api/v1/agents", headers=API_KEY_HEADER)
    for header_name, expected_value in SECURITY_HEADERS.items():
        actual = response.headers.get(header_name)
        assert actual == expected_value, (
            f"Missing or wrong {header_name}: expected {expected_value!r}, got {actual!r}"
        )


async def test_security_headers_on_error(client):
    """Security headers should appear even on error responses."""
    response = await client.get("/api/v1/agents/nonexistent", headers=API_KEY_HEADER)
    assert response.status_code == 404
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"


# ---------------------------------------------------------------------------
# Request ID
# ---------------------------------------------------------------------------


async def test_request_id_returned(client):
    """Every response should include an X-Request-Id header."""
    response = await client.get("/api/v1/agents", headers=API_KEY_HEADER)
    request_id = response.headers.get("X-Request-Id")
    assert request_id, "X-Request-Id header must be present and non-empty"
    assert len(request_id) <= 64, "Request ID should not exceed max length"
    parsed = uuid.UUID(request_id)
    assert isinstance(parsed, uuid.UUID), "Request ID must be a valid UUID"


async def test_client_request_id_echoed(client):
    """Valid client-supplied X-Request-Id should be echoed back."""
    custom_id = "my-request-12345"
    headers = {**API_KEY_HEADER, "X-Request-Id": custom_id}
    response = await client.get("/api/v1/agents", headers=headers)
    assert response.headers.get("X-Request-Id") == custom_id


async def test_invalid_request_id_replaced(client):
    """Invalid X-Request-Id (e.g. with spaces/special chars) should be replaced with a UUID."""
    headers = {**API_KEY_HEADER, "X-Request-Id": "bad id with spaces!@#"}
    response = await client.get("/api/v1/agents", headers=headers)
    returned_id = response.headers.get("X-Request-Id")
    assert returned_id != "bad id with spaces!@#"
    parsed = uuid.UUID(returned_id)
    assert isinstance(parsed, uuid.UUID), "Replaced request ID must be a valid UUID"


# ---------------------------------------------------------------------------
# Body size limiter
# ---------------------------------------------------------------------------


async def test_body_size_limit_rejects_large_content_length(client):
    """Request with Content-Length exceeding 10MB should be rejected with 413."""
    headers = {**API_KEY_HEADER, "Content-Length": str(11 * 1024 * 1024)}
    response = await client.post(
        "/api/v1/agents",
        content=b"{}",
        headers=headers,
    )
    assert response.status_code == 413
    assert "too large" in response.json()["detail"].lower()


async def test_body_size_limit_invalid_content_length(client):
    """Request with non-numeric Content-Length should be rejected with 400."""
    headers = {**API_KEY_HEADER, "Content-Length": "not-a-number"}
    response = await client.post(
        "/api/v1/agents",
        content=b"{}",
        headers=headers,
    )
    assert response.status_code == 400
    assert "content-length" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Timing-safe auth verification
# ---------------------------------------------------------------------------


async def test_empty_api_key_rejected(client):
    """Empty X-API-Key header should be rejected (timing-safe compare still runs)."""
    response = await client.get("/api/v1/agents", headers={"X-API-Key": ""})
    assert response.status_code == 401


async def test_401_no_internal_path_leak(client):
    """401 error response should not reveal server filesystem paths."""
    response = await client.get("/api/v1/agents")
    assert response.status_code == 401
    body_str = str(response.json())
    for forbidden in ("/Users/", "/home/", "Traceback", 'File "'):
        assert forbidden not in body_str, f"401 response leaks internal detail: {forbidden!r}"


# ---------------------------------------------------------------------------
# Security headers on auth failures
# ---------------------------------------------------------------------------


async def test_security_headers_on_401(client):
    """Security headers should be present even on 401 responses."""
    response = await client.get("/api/v1/agents")
    assert response.status_code == 401
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"


# ---------------------------------------------------------------------------
# Request ID on error responses
# ---------------------------------------------------------------------------


async def test_request_id_on_401(client):
    """401 responses should include X-Request-Id for log correlation."""
    response = await client.get("/api/v1/agents")
    assert response.status_code == 401
    request_id = response.headers.get("X-Request-Id")
    assert request_id, "401 response must include X-Request-Id"
    uuid.UUID(request_id)


async def test_request_id_on_404(client):
    """404 responses should include X-Request-Id for log correlation."""
    response = await client.get("/api/v1/agents/nonexistent", headers=API_KEY_HEADER)
    assert response.status_code == 404
    request_id = response.headers.get("X-Request-Id")
    assert request_id, "404 response must include X-Request-Id"
    uuid.UUID(request_id)


# ---------------------------------------------------------------------------
# Negative content-length
# ---------------------------------------------------------------------------


async def test_body_size_limit_negative_content_length(client):
    """Request with negative Content-Length should be rejected with 400 (invalid header)."""
    headers = {**API_KEY_HEADER, "Content-Length": "-1"}
    response = await client.post(
        "/api/v1/agents",
        content=b"{}",
        headers=headers,
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Query-string credential redaction
# ---------------------------------------------------------------------------


def test_redact_query_string_strips_api_key():
    """api_key parameter must be redacted from logged query strings."""
    from blackbeard.api.middleware import _redact_query_string

    result = _redact_query_string("api_key=super-secret&namespace=default")
    assert "super-secret" not in result
    # urlencode may percent-encode brackets; check the key is paired with redacted value
    assert "api_key=" in result
    assert "namespace=default" in result


def test_redact_query_string_case_insensitive():
    """Redaction should match parameter names case-insensitively."""
    from blackbeard.api.middleware import _redact_query_string

    result = _redact_query_string("API_KEY=secret123&limit=10")
    assert "secret123" not in result
    assert "limit=10" in result


def test_redact_query_string_preserves_safe_params():
    """Non-sensitive parameters must pass through unmodified."""
    from blackbeard.api.middleware import _redact_query_string

    result = _redact_query_string("namespace=prod&limit=50")
    assert result == "namespace=prod&limit=50"


def test_redact_query_string_empty():
    """Empty query string should return unchanged."""
    from blackbeard.api.middleware import _redact_query_string

    assert _redact_query_string("") == ""
