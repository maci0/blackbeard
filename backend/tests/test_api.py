"""Integration tests for the Blackbeard REST API — Resource CRUD endpoints.

Dependencies:
  - aiosqlite  (pip install aiosqlite)   — async SQLite driver used for in-memory DB
  - httpx, pytest-asyncio                — already in dev dependencies

The test fixture spins up an in-memory SQLite database and overrides the
`get_session` dependency so no real PostgreSQL instance is needed.

Note: conftest.py patches sqlalchemy.dialects.postgresql.{JSONB,UUID} to
SQLite-compatible types *before* this module is imported.
"""

import pytest
from httpx import AsyncClient

from tests.conftest import API_KEY_HEADER, _agent_payload

# ---------------------------------------------------------------------------
# Payload helpers
# ---------------------------------------------------------------------------


def _task_payload(name: str = "gather-data", agent_ref: str = "ref:agents/researcher") -> dict:
    return {
        "apiVersion": "blackbeard/v1",
        "kind": "Task",
        "metadata": {"name": name, "namespace": "default"},
        "spec": {
            "description": "Gather relevant data from the web",
            "expected_output": "A structured JSON summary",
            "agent": agent_ref,
        },
    }


# ---------------------------------------------------------------------------
# Auth / middleware
# ---------------------------------------------------------------------------


async def test_requires_api_key(client: AsyncClient):
    """Requests without X-API-Key header should be rejected with 401."""
    response = await client.get("/api/v1/agents")
    assert response.status_code == 401


async def test_health_is_public(client: AsyncClient):
    """Health endpoint should not require an API key."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Invalid kind
# ---------------------------------------------------------------------------


async def test_invalid_kind_plural(client: AsyncClient):
    """Unknown kind plural should return 422 (path pattern constraint rejects it)."""
    response = await client.get("/api/v1/invalid", headers=API_KEY_HEADER)
    assert response.status_code == 422


async def test_create_resource_kind_mismatch(client: AsyncClient):
    """POST Agent to /api/v1/tools should fail with 422."""
    response = await client.post(
        "/api/v1/tools",
        json={
            "apiVersion": "blackbeard/v1",
            "kind": "Agent",
            "metadata": {"name": "mismatched"},
            "spec": {"role": "Test", "goal": "Test", "backstory": "Test"},
        },
        headers=API_KEY_HEADER,
    )
    assert response.status_code == 422
    assert "mismatch" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Agent CRUD
# ---------------------------------------------------------------------------


async def test_list_agents_empty(client: AsyncClient):
    """GET /agents on an empty database should return empty list with total=0."""
    response = await client.get("/api/v1/agents", headers=API_KEY_HEADER)
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0


async def test_create_agent(client: AsyncClient):
    """POST /agents with a valid body should return 201 with a resource id."""
    response = await client.post("/api/v1/agents", json=_agent_payload(), headers=API_KEY_HEADER)
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    import uuid as _uuid

    _uuid.UUID(data["id"])  # must be a valid UUID
    assert data["kind"] == "Agent"
    assert data["metadata"]["name"] == "researcher"
    assert data["metadata"]["namespace"] == "default"
    assert data["version"] == 1
    assert data["spec"]["role"] == "Research Analyst"
    assert isinstance(data["created_at"], str), "created_at should be a string"
    assert len(data["created_at"]) > 0, "created_at should be non-empty"


async def test_create_agent_invalid_spec(client: AsyncClient):
    """POST /agents with missing required spec fields should return 422."""
    bad_payload = {
        "apiVersion": "blackbeard/v1",
        "kind": "Agent",
        "metadata": {"name": "broken-agent"},
        "spec": {"goal": "Only goal, missing role and backstory"},
    }
    response = await client.post("/api/v1/agents", json=bad_payload, headers=API_KEY_HEADER)
    assert response.status_code == 422
    detail = response.json()["detail"]
    detail_str = str(detail).lower()
    assert "role" in detail_str
    assert "backstory" in detail_str


async def test_list_agents_after_create(client: AsyncClient):
    """Creating 2 agents and listing should return total=2."""
    r1 = await client.post("/api/v1/agents", json=_agent_payload("agent-1"), headers=API_KEY_HEADER)
    assert r1.status_code == 201
    r2 = await client.post("/api/v1/agents", json=_agent_payload("agent-2"), headers=API_KEY_HEADER)
    assert r2.status_code == 201

    response = await client.get("/api/v1/agents", headers=API_KEY_HEADER)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
    returned_names = {item["metadata"]["name"] for item in data["items"]}
    assert returned_names == {"agent-1", "agent-2"}


async def test_get_agent(client: AsyncClient):
    """GET /agents/{name} should return the created agent."""
    r = await client.post("/api/v1/agents", json=_agent_payload(), headers=API_KEY_HEADER)
    assert r.status_code == 201

    response = await client.get("/api/v1/agents/researcher", headers=API_KEY_HEADER)
    assert response.status_code == 200
    data = response.json()
    assert data["metadata"]["name"] == "researcher"
    assert data["kind"] == "Agent"


async def test_get_agent_not_found(client: AsyncClient):
    """GET /agents/{name} for a non-existent agent should return 404."""
    response = await client.get("/api/v1/agents/nonexistent", headers=API_KEY_HEADER)
    assert response.status_code == 404
    detail = response.json()["detail"].lower()
    assert "not found" in detail, f"Expected 'not found' in detail, got: {detail!r}"


async def test_update_agent(client: AsyncClient):
    """PUT /agents/{name} with correct version should succeed and bump version to 2."""
    create_resp = await client.post("/api/v1/agents", json=_agent_payload(), headers=API_KEY_HEADER)
    assert create_resp.status_code == 201

    update_payload = {
        "version": 1,
        "spec": {
            "role": "Senior Research Analyst",
            "goal": "Find deeper insights",
            "backstory": "Even more experience now",
        },
    }
    response = await client.put(
        "/api/v1/agents/researcher", json=update_payload, headers=API_KEY_HEADER
    )
    assert response.status_code == 200
    data = response.json()
    assert data["version"] == 2
    assert data["spec"]["role"] == "Senior Research Analyst"
    assert data["id"] == create_resp.json()["id"], "Update should preserve resource id"
    assert data["updated_at"] is not None


async def test_update_agent_version_conflict(client: AsyncClient):
    """PUT with the wrong version number should return 409 Conflict."""
    r = await client.post("/api/v1/agents", json=_agent_payload(), headers=API_KEY_HEADER)
    assert r.status_code == 201

    update_payload = {
        "version": 99,  # wrong version
        "spec": {
            "role": "Role",
            "goal": "Goal",
            "backstory": "Backstory",
        },
    }
    response = await client.put(
        "/api/v1/agents/researcher", json=update_payload, headers=API_KEY_HEADER
    )
    assert response.status_code == 409


async def test_delete_agent(client: AsyncClient):
    """DELETE /agents/{name} should return 204 and subsequent GET should return 404."""
    r = await client.post("/api/v1/agents", json=_agent_payload(), headers=API_KEY_HEADER)
    assert r.status_code == 201

    delete_resp = await client.delete("/api/v1/agents/researcher", headers=API_KEY_HEADER)
    assert delete_resp.status_code == 204

    get_resp = await client.get("/api/v1/agents/researcher", headers=API_KEY_HEADER)
    assert get_resp.status_code == 404


# ---------------------------------------------------------------------------
# Ref storage
# ---------------------------------------------------------------------------


async def test_create_task_with_refs(client: AsyncClient):
    """Creating a task with a ref should succeed and the ref should be stored."""
    # First create the referenced agent
    r = await client.post("/api/v1/agents", json=_agent_payload(), headers=API_KEY_HEADER)
    assert r.status_code == 201

    # Create task with a ref to the agent
    response = await client.post("/api/v1/tasks", json=_task_payload(), headers=API_KEY_HEADER)
    assert response.status_code == 201
    data = response.json()
    assert data["kind"] == "Task"
    assert data["spec"]["agent"] == "ref:agents/researcher"


# ---------------------------------------------------------------------------
# Upsert behaviour (create is idempotent)
# ---------------------------------------------------------------------------


async def test_create_agent_upsert(client: AsyncClient):
    """POSTing the same resource twice should upsert (update) rather than error."""
    payload = _agent_payload()
    r1 = await client.post("/api/v1/agents", json=payload, headers=API_KEY_HEADER)
    assert r1.status_code == 201
    assert r1.json()["version"] == 1

    r2 = await client.post("/api/v1/agents", json=payload, headers=API_KEY_HEADER)
    assert r2.status_code == 200  # 200 on upsert (update), 201 on create
    assert r2.json()["version"] == 2  # version bumped on upsert
    assert r2.json()["spec"]["role"] == payload["spec"]["role"]
    assert r2.json()["id"] == r1.json()["id"], "Upsert must preserve resource id"


# ---------------------------------------------------------------------------
# Other resource kinds (smoke tests)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/v1/tasks",
        "/api/v1/crews",
        "/api/v1/tools",
        "/api/v1/llm-connections",
    ],
)
async def test_list_resources_empty(client: AsyncClient, endpoint: str):
    """GET on any resource list endpoint with empty DB returns consistent shape."""
    response = await client.get(endpoint, headers=API_KEY_HEADER)
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0


async def test_create_and_get_llm_connection(client: AsyncClient):
    """End-to-end create+get for an LLMConnection resource."""
    payload = {
        "apiVersion": "blackbeard/v1",
        "kind": "LLMConnection",
        "metadata": {"name": "gpt4", "namespace": "default"},
        "spec": {
            "provider": "openai",
            "model": "gpt-4o",
            "parameters": {"temperature": 0.7},
        },
    }
    create_resp = await client.post("/api/v1/llm-connections", json=payload, headers=API_KEY_HEADER)
    assert create_resp.status_code == 201

    get_resp = await client.get("/api/v1/llm-connections/gpt4", headers=API_KEY_HEADER)
    assert get_resp.status_code == 200
    assert get_resp.json()["spec"]["provider"] == "openai"


# ---------------------------------------------------------------------------
# Update edge cases
# ---------------------------------------------------------------------------


async def test_update_nonexistent_resource(client: AsyncClient):
    """PUT on a resource that doesn't exist should return 404."""
    update_payload = {
        "version": 1,
        "spec": {"role": "R", "goal": "G", "backstory": "B"},
    }
    response = await client.put(
        "/api/v1/agents/ghost-agent", json=update_payload, headers=API_KEY_HEADER
    )
    assert response.status_code == 404


async def test_update_with_invalid_spec(client: AsyncClient):
    """PUT with spec violating JSON Schema should return 422."""
    r = await client.post("/api/v1/agents", json=_agent_payload(), headers=API_KEY_HEADER)
    assert r.status_code == 201

    update_payload = {
        "version": 1,
        "spec": {"goal": "Only goal, missing role and backstory"},
    }
    response = await client.put(
        "/api/v1/agents/researcher", json=update_payload, headers=API_KEY_HEADER
    )
    assert response.status_code == 422


async def test_delete_nonexistent_is_idempotent(client: AsyncClient):
    """DELETE on a non-existent resource should return 204 (idempotent)."""
    response = await client.delete("/api/v1/agents/ghost-agent", headers=API_KEY_HEADER)
    assert response.status_code == 204
    get_resp = await client.get("/api/v1/agents/ghost-agent", headers=API_KEY_HEADER)
    assert get_resp.status_code == 404, "Resource must not exist after idempotent delete"


# ---------------------------------------------------------------------------
# Resource response shape
# ---------------------------------------------------------------------------


async def test_resource_response_shape(client: AsyncClient):
    """Created resource should have all expected fields in the response."""
    response = await client.post("/api/v1/agents", json=_agent_payload(), headers=API_KEY_HEADER)
    assert response.status_code == 201
    data = response.json()

    required = {
        "id",
        "apiVersion",
        "kind",
        "metadata",
        "spec",
        "version",
        "created_at",
        "updated_at",
    }
    assert required.issubset(data.keys()), f"Missing: {required - set(data.keys())}"
    assert data["apiVersion"] == "blackbeard/v1"
    assert data["metadata"]["namespace"] == "default"
    assert isinstance(data["version"], int)
    assert isinstance(data["id"], str)
    assert isinstance(data["spec"], dict)
    assert isinstance(data["metadata"], dict)
    assert data["metadata"]["name"] == "researcher"
    assert data["kind"] == "Agent"


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


async def test_list_agents_pagination(client: AsyncClient):
    """Pagination with limit+offset should return correct slices."""
    for i in range(5):
        r = await client.post(
            "/api/v1/agents", json=_agent_payload(f"agent-{i}"), headers=API_KEY_HEADER
        )
        assert r.status_code == 201

    response = await client.get("/api/v1/agents?limit=2&offset=0", headers=API_KEY_HEADER)
    data = response.json()
    assert len(data["items"]) == 2
    assert data["total"] == 5
    assert data["has_more"] is True
    for item in data["items"]:
        assert "metadata" in item and "name" in item["metadata"], (
            "Paginated items should contain full resource objects"
        )
        assert "spec" in item
        assert "kind" in item
        assert item["kind"] == "Agent"
        assert "id" in item

    response = await client.get("/api/v1/agents?limit=2&offset=4", headers=API_KEY_HEADER)
    data = response.json()
    assert len(data["items"]) == 1
    assert data["total"] == 5
    assert data["has_more"] is False


# ---------------------------------------------------------------------------
# Invalid API version
# ---------------------------------------------------------------------------


async def test_create_resource_invalid_api_version(client: AsyncClient):
    """POST with unsupported apiVersion should return 422."""
    payload = {
        "apiVersion": "blackbeard/v999",
        "kind": "Agent",
        "metadata": {"name": "test"},
        "spec": {"role": "R", "goal": "G", "backstory": "B"},
    }
    response = await client.post("/api/v1/agents", json=payload, headers=API_KEY_HEADER)
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Resource name validation
# ---------------------------------------------------------------------------


async def test_create_resource_invalid_name(client: AsyncClient):
    """POST with uppercase/invalid name should return 422."""
    payload = {
        "apiVersion": "blackbeard/v1",
        "kind": "Agent",
        "metadata": {"name": "Invalid_Name", "namespace": "default"},
        "spec": {"role": "R", "goal": "G", "backstory": "B"},
    }
    response = await client.post("/api/v1/agents", json=payload, headers=API_KEY_HEADER)
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Ref integrity — dangling refs
# ---------------------------------------------------------------------------


async def test_create_task_with_dangling_ref_succeeds(client: AsyncClient):
    """Creating a task referencing a non-existent agent should still succeed (soft refs)."""
    payload = _task_payload(name="orphan-task", agent_ref="ref:agents/nonexistent")
    response = await client.post("/api/v1/tasks", json=payload, headers=API_KEY_HEADER)
    # Refs are soft — creation succeeds even if target doesn't exist
    assert response.status_code == 201
    data = response.json()
    assert data["kind"] == "Task"
    assert data["metadata"]["name"] == "orphan-task"
    assert data["spec"]["agent"] == "ref:agents/nonexistent"


# ---------------------------------------------------------------------------
# Namespace CRUD
# ---------------------------------------------------------------------------


def _namespace_payload(name: str = "default", description: str = "Default namespace") -> dict:
    return {
        "apiVersion": "blackbeard/v1",
        "kind": "Namespace",
        "metadata": {"name": name},
        "spec": {"description": description},
    }


async def test_create_namespace(client: AsyncClient):
    """POST /namespaces with a valid body should return 201."""
    response = await client.post(
        "/api/v1/namespaces", json=_namespace_payload(), headers=API_KEY_HEADER
    )
    assert response.status_code == 201
    data = response.json()
    assert data["kind"] == "Namespace"
    assert data["metadata"]["name"] == "default"
    assert data["spec"]["description"] == "Default namespace"


async def test_create_namespace_full_spec(client: AsyncClient):
    """POST /namespaces with all spec fields should return 201."""
    payload = {
        "apiVersion": "blackbeard/v1",
        "kind": "Namespace",
        "metadata": {"name": "production"},
        "spec": {
            "description": "Production namespace",
            "labels": {"team": "backend", "env": "prod"},
            "default_agent_policy": "ref:agent-policies/standard",
            "resource_quota": {
                "max_resources": 500,
                "max_executions_per_hour": 100,
            },
        },
    }
    response = await client.post("/api/v1/namespaces", json=payload, headers=API_KEY_HEADER)
    assert response.status_code == 201
    data = response.json()
    assert data["spec"]["resource_quota"]["max_resources"] == 500


async def test_get_namespace(client: AsyncClient):
    """GET /namespaces/{name} should return the created namespace."""
    await client.post("/api/v1/namespaces", json=_namespace_payload(), headers=API_KEY_HEADER)
    response = await client.get("/api/v1/namespaces/default", headers=API_KEY_HEADER)
    assert response.status_code == 200
    assert response.json()["metadata"]["name"] == "default"


async def test_list_namespaces(client: AsyncClient):
    """GET /namespaces should list created namespaces."""
    await client.post(
        "/api/v1/namespaces", json=_namespace_payload("ns-a", "A"), headers=API_KEY_HEADER
    )
    await client.post(
        "/api/v1/namespaces", json=_namespace_payload("ns-b", "B"), headers=API_KEY_HEADER
    )
    response = await client.get("/api/v1/namespaces", headers=API_KEY_HEADER)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2


async def test_delete_namespace(client: AsyncClient):
    """DELETE /namespaces/{name} should return 204."""
    await client.post("/api/v1/namespaces", json=_namespace_payload(), headers=API_KEY_HEADER)
    response = await client.delete("/api/v1/namespaces/default", headers=API_KEY_HEADER)
    assert response.status_code == 204
