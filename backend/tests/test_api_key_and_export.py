"""Tests for API key management and bulk resource export endpoints."""

from __future__ import annotations

import yaml
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from blackbeard.models.user import User
from tests.conftest import API_KEY_HEADER, _agent_payload, _bearer, _register_payload

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_APIKEY_EMAIL = "apikey-user@example.com"


async def _register_and_get_token(
    client: AsyncClient,
    email: str = _APIKEY_EMAIL,
) -> str:
    """Register a user and return their JWT access token."""
    resp = await client.post(
        "/api/v1/auth/register",
        json=_register_payload(email=email),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["access_token"]


# ---------------------------------------------------------------------------
# API Key generation (POST /auth/api-key)
# ---------------------------------------------------------------------------


async def test_generate_api_key(client: AsyncClient):
    """POST /auth/api-key with JWT auth should generate a new API key."""
    token = await _register_and_get_token(client)
    resp = await client.post(
        "/api/v1/auth/api-key",
        headers=_bearer(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "api_key" in data
    assert data["api_key"].startswith("bb-")
    assert len(data["api_key"]) > 10


async def test_generate_api_key_returns_different_key_each_time(client: AsyncClient):
    """Calling POST /auth/api-key twice should return different keys (rotation)."""
    token = await _register_and_get_token(client)
    resp1 = await client.post("/api/v1/auth/api-key", headers=_bearer(token))
    assert resp1.status_code == 200
    key1 = resp1.json()["api_key"]

    resp2 = await client.post("/api/v1/auth/api-key", headers=_bearer(token))
    assert resp2.status_code == 200
    key2 = resp2.json()["api_key"]

    assert key1 != key2, "Rotating the API key must produce a different key"


async def test_generate_api_key_requires_jwt(client: AsyncClient):
    """POST /auth/api-key without JWT Bearer token should return 401."""
    resp = await client.post(
        "/api/v1/auth/api-key",
        headers=API_KEY_HEADER,
    )
    assert resp.status_code == 401
    assert "jwt" in resp.json()["detail"].lower() or "bearer" in resp.json()["detail"].lower()


async def test_generate_api_key_no_auth(client: AsyncClient):
    """POST /auth/api-key without any auth should return 401."""
    resp = await client.post("/api/v1/auth/api-key")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# API Key revocation (DELETE /auth/api-key)
# ---------------------------------------------------------------------------


async def test_revoke_api_key(client: AsyncClient):
    """DELETE /auth/api-key should revoke the user's API key."""
    token = await _register_and_get_token(client)

    # Generate a key first
    gen_resp = await client.post("/api/v1/auth/api-key", headers=_bearer(token))
    assert gen_resp.status_code == 200

    # Revoke it
    resp = await client.delete("/api/v1/auth/api-key", headers=_bearer(token))
    assert resp.status_code == 204


async def test_revoke_api_key_idempotent(client: AsyncClient):
    """DELETE /auth/api-key should return 204 even when no key exists."""
    token = await _register_and_get_token(client)
    resp = await client.delete("/api/v1/auth/api-key", headers=_bearer(token))
    assert resp.status_code == 204


async def test_revoke_api_key_requires_jwt(client: AsyncClient):
    """DELETE /auth/api-key without JWT Bearer token should return 401."""
    resp = await client.delete(
        "/api/v1/auth/api-key",
        headers=API_KEY_HEADER,
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# API Key persistence (generate → stored, revoke → cleared)
# ---------------------------------------------------------------------------


async def test_generated_api_key_is_stored_on_user(client: AsyncClient, db_session: AsyncSession):
    """Generating an API key should persist it on the User record."""
    token = await _register_and_get_token(client)
    resp = await client.post("/api/v1/auth/api-key", headers=_bearer(token))
    assert resp.status_code == 200
    api_key = resp.json()["api_key"]

    # Verify the key is persisted on the user row
    result = await db_session.execute(select(User).where(User.api_key == api_key))
    user = result.scalar_one_or_none()
    assert user is not None, "Generated API key should be stored on the user"
    assert user.api_key == api_key


async def test_revoked_api_key_is_cleared_on_user(client: AsyncClient, db_session: AsyncSession):
    """Revoking an API key should clear it from the User record."""
    token = await _register_and_get_token(client)

    # Generate a key
    resp = await client.post("/api/v1/auth/api-key", headers=_bearer(token))
    api_key = resp.json()["api_key"]

    # Verify it's stored
    result = await db_session.execute(select(User).where(User.api_key == api_key))
    stored_user = result.scalar_one_or_none()
    assert stored_user is not None and stored_user.email == _APIKEY_EMAIL

    # Revoke it
    del_resp = await client.delete("/api/v1/auth/api-key", headers=_bearer(token))
    assert del_resp.status_code == 204

    # Verify the key is no longer stored
    result2 = await db_session.execute(select(User).where(User.api_key == api_key))
    assert result2.scalar_one_or_none() is None, "Revoked key should be cleared from DB"


async def test_rotated_key_invalidates_previous(client: AsyncClient, db_session: AsyncSession):
    """Rotating an API key should invalidate the previous key."""
    token = await _register_and_get_token(client)

    # Generate first key
    resp1 = await client.post("/api/v1/auth/api-key", headers=_bearer(token))
    key1 = resp1.json()["api_key"]

    # Generate second key (rotation)
    resp2 = await client.post("/api/v1/auth/api-key", headers=_bearer(token))
    key2 = resp2.json()["api_key"]

    # Old key should no longer resolve to any user
    result_old = await db_session.execute(select(User).where(User.api_key == key1))
    assert result_old.scalar_one_or_none() is None, "Old key must not resolve after rotation"

    # New key should resolve
    result_new = await db_session.execute(select(User).where(User.api_key == key2))
    new_user = result_new.scalar_one_or_none()
    assert new_user is not None and new_user.api_key == key2, "New key should resolve"


# ---------------------------------------------------------------------------
# Bulk resource export (GET /resources/export)
# ---------------------------------------------------------------------------


async def test_export_empty_database(client: AsyncClient):
    """GET /resources/export with no resources returns empty YAML."""
    resp = await client.get("/api/v1/resources/export", headers=API_KEY_HEADER)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/x-yaml"
    # Empty database should produce empty or no-document YAML
    content = resp.text
    docs = list(yaml.safe_load_all(content))
    # yaml.safe_load_all on empty string yields a single None
    non_none = [d for d in docs if d is not None]
    assert len(non_none) == 0


async def test_export_single_resource(client: AsyncClient):
    """GET /resources/export with one resource returns valid YAML document."""
    # Create an agent
    create_resp = await client.post("/api/v1/agents", json=_agent_payload(), headers=API_KEY_HEADER)
    assert create_resp.status_code == 201

    resp = await client.get("/api/v1/resources/export", headers=API_KEY_HEADER)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/x-yaml"

    docs = list(yaml.safe_load_all(resp.text))
    non_none = [d for d in docs if d is not None]
    assert len(non_none) == 1

    doc = non_none[0]
    assert doc["apiVersion"] == "blackbeard/v1"
    assert doc["kind"] == "Agent"
    assert doc["metadata"]["name"] == "researcher"
    assert doc["metadata"]["project"] == "default"
    assert doc["spec"]["role"] == "Research Analyst"


async def test_export_multiple_resources(client: AsyncClient):
    """GET /resources/export with multiple resources returns multi-document YAML."""
    # Create two agents
    for name in ["agent-alpha", "agent-beta"]:
        r = await client.post("/api/v1/agents", json=_agent_payload(name), headers=API_KEY_HEADER)
        assert r.status_code == 201

    # Create a task
    task_payload = {
        "apiVersion": "blackbeard/v1",
        "kind": "Task",
        "metadata": {"name": "gather-data", "project": "default"},
        "spec": {
            "description": "Gather data",
            "expected_output": "A JSON summary",
            "agent": "ref:agents/agent-alpha",
        },
    }
    r = await client.post("/api/v1/tasks", json=task_payload, headers=API_KEY_HEADER)
    assert r.status_code == 201

    resp = await client.get("/api/v1/resources/export", headers=API_KEY_HEADER)
    assert resp.status_code == 200

    docs = list(yaml.safe_load_all(resp.text))
    non_none = [d for d in docs if d is not None]
    assert len(non_none) == 3

    kinds = {d["kind"] for d in non_none}
    assert "Agent" in kinds
    assert "Task" in kinds

    names = {d["metadata"]["name"] for d in non_none}
    assert "agent-alpha" in names
    assert "agent-beta" in names
    assert "gather-data" in names

    # Every document should have the standard fields
    for doc in non_none:
        assert "apiVersion" in doc
        assert "kind" in doc
        assert "metadata" in doc
        assert "spec" in doc
        assert "name" in doc["metadata"]
        assert "project" in doc["metadata"]


async def test_export_contains_yaml_separators(client: AsyncClient):
    """Multi-document YAML should contain --- separators."""
    for name in ["sep-agent-a", "sep-agent-b"]:
        r = await client.post("/api/v1/agents", json=_agent_payload(name), headers=API_KEY_HEADER)
        assert r.status_code == 201

    resp = await client.get("/api/v1/resources/export", headers=API_KEY_HEADER)
    assert resp.status_code == 200
    assert "---" in resp.text


async def test_export_project_filter(client: AsyncClient):
    """GET /resources/export?project=X should filter by project."""
    # Create agents in different namespaces
    payload_default = _agent_payload("ns-default-agent")
    r = await client.post("/api/v1/agents", json=payload_default, headers=API_KEY_HEADER)
    assert r.status_code == 201

    payload_prod = _agent_payload("ns-prod-agent")
    payload_prod["metadata"]["project"] = "prod"
    r = await client.post("/api/v1/agents", json=payload_prod, headers=API_KEY_HEADER)
    assert r.status_code == 201

    # Export only default project
    resp = await client.get("/api/v1/resources/export?project=default", headers=API_KEY_HEADER)
    assert resp.status_code == 200
    docs = [d for d in yaml.safe_load_all(resp.text) if d is not None]
    assert len(docs) == 1
    assert docs[0]["metadata"]["name"] == "ns-default-agent"

    # Export only prod project
    resp_prod = await client.get("/api/v1/resources/export?project=prod", headers=API_KEY_HEADER)
    assert resp_prod.status_code == 200
    docs_prod = [d for d in yaml.safe_load_all(resp_prod.text) if d is not None]
    assert len(docs_prod) == 1
    assert docs_prod[0]["metadata"]["name"] == "ns-prod-agent"


async def test_export_requires_auth(client: AsyncClient):
    """GET /resources/export without authentication should return 401."""
    resp = await client.get("/api/v1/resources/export")
    assert resp.status_code == 401
