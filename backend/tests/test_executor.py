"""Integration tests for the execution API endpoints.

Uses the same in-memory SQLite + httpx pattern as test_api.py.
CrewAI's crew.kickoff() is mocked so no real LLM calls are made.

Note: conftest.py patches sqlalchemy.dialects.postgresql.{JSONB,UUID} and
imports execution models BEFORE this module loads.
"""

import uuid
import pytest
from httpx import AsyncClient

# Fixtures (db_session, client) are provided by conftest.py
API_KEY_HEADER = {"X-API-Key": "change-me-in-production"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_full_crew(client: AsyncClient, crew_name: str = "test-crew") -> None:
    """Create LLM connection, agent, task, and crew resources via the API."""
    await client.post(
        "/api/v1/llm-connections",
        json={
            "apiVersion": "blackbeard/v1",
            "kind": "LLMConnection",
            "metadata": {"name": "test-llm"},
            "spec": {"provider": "vertex_ai", "model": "claude-sonnet-4-6"},
        },
        headers=API_KEY_HEADER,
    )

    await client.post(
        "/api/v1/agents",
        json={
            "apiVersion": "blackbeard/v1",
            "kind": "Agent",
            "metadata": {"name": "test-agent"},
            "spec": {
                "role": "Test Agent",
                "goal": "Test goal",
                "backstory": "Test backstory",
                "llm": "ref:llm-connections/test-llm",
            },
        },
        headers=API_KEY_HEADER,
    )

    await client.post(
        "/api/v1/tasks",
        json={
            "apiVersion": "blackbeard/v1",
            "kind": "Task",
            "metadata": {"name": "test-task"},
            "spec": {
                "description": "Test task description",
                "expected_output": "Test expected output",
                "agent": "ref:agents/test-agent",
            },
        },
        headers=API_KEY_HEADER,
    )

    await client.post(
        "/api/v1/crews",
        json={
            "apiVersion": "blackbeard/v1",
            "kind": "Crew",
            "metadata": {"name": crew_name},
            "spec": {
                "process": "sequential",
                "agents": ["ref:agents/test-agent"],
                "tasks": ["ref:tasks/test-task"],
            },
        },
        headers=API_KEY_HEADER,
    )


# ---------------------------------------------------------------------------
# Tests — kickoff
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_kickoff_crew_not_found(client: AsyncClient):
    """POST /crews/{name}/kickoff for an unknown crew → 404."""
    response = await client.post(
        "/api/v1/crews/nonexistent/kickoff",
        json={"inputs": {}},
        headers=API_KEY_HEADER,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_kickoff_crew(client: AsyncClient):
    """Kicking off an existing crew returns 202 with status=queued."""
    await _create_full_crew(client)

    response = await client.post(
        "/api/v1/crews/test-crew/kickoff",
        json={"inputs": {"topic": "AI"}},
        headers=API_KEY_HEADER,
    )
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "queued"
    assert data["crew_name"] == "test-crew"
    assert "id" in data
    assert data["inputs"] == {"topic": "AI"}


@pytest.mark.asyncio
async def test_kickoff_crew_has_tasks(client: AsyncClient):
    """Kicked-off execution should have task records matching the crew's tasks."""
    await _create_full_crew(client)

    response = await client.post(
        "/api/v1/crews/test-crew/kickoff",
        json={"inputs": {}},
        headers=API_KEY_HEADER,
    )
    assert response.status_code == 202
    data = response.json()
    assert len(data["tasks"]) == 1
    assert data["tasks"][0]["task_name"] == "test-task"
    assert data["tasks"][0]["status"] == "pending"


# ---------------------------------------------------------------------------
# Tests — list executions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_executions_empty(client: AsyncClient):
    """GET /executions with no executions → 200, empty list."""
    response = await client.get("/api/v1/executions", headers=API_KEY_HEADER)
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_list_executions_after_kickoff(client: AsyncClient):
    """After kicking off, list executions should include the new execution."""
    await _create_full_crew(client)
    await client.post(
        "/api/v1/crews/test-crew/kickoff",
        json={"inputs": {}},
        headers=API_KEY_HEADER,
    )

    response = await client.get("/api/v1/executions", headers=API_KEY_HEADER)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["crew_name"] == "test-crew"


@pytest.mark.asyncio
async def test_list_executions_filter_by_crew(client: AsyncClient):
    """Filter by crew_name should return only matching executions."""
    # Create two crews
    await _create_full_crew(client, crew_name="crew-alpha")
    # Reuse same agents/tasks for crew-beta
    await client.post(
        "/api/v1/crews",
        json={
            "apiVersion": "blackbeard/v1",
            "kind": "Crew",
            "metadata": {"name": "crew-beta"},
            "spec": {
                "process": "sequential",
                "agents": ["ref:agents/test-agent"],
                "tasks": ["ref:tasks/test-task"],
            },
        },
        headers=API_KEY_HEADER,
    )

    await client.post("/api/v1/crews/crew-alpha/kickoff", json={"inputs": {}}, headers=API_KEY_HEADER)
    await client.post("/api/v1/crews/crew-beta/kickoff", json={"inputs": {}}, headers=API_KEY_HEADER)

    response = await client.get(
        "/api/v1/executions?crew_name=crew-alpha", headers=API_KEY_HEADER
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["crew_name"] == "crew-alpha"


# ---------------------------------------------------------------------------
# Tests — get execution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_execution_not_found(client: AsyncClient):
    """GET /executions/{random-uuid} → 404."""
    random_id = str(uuid.uuid4())
    response = await client.get(f"/api/v1/executions/{random_id}", headers=API_KEY_HEADER)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_execution_after_kickoff(client: AsyncClient):
    """After kickoff, GET /executions/{id} returns full execution details."""
    await _create_full_crew(client)
    kickoff_resp = await client.post(
        "/api/v1/crews/test-crew/kickoff",
        json={"inputs": {}},
        headers=API_KEY_HEADER,
    )
    assert kickoff_resp.status_code == 202
    execution_id = kickoff_resp.json()["id"]

    response = await client.get(f"/api/v1/executions/{execution_id}", headers=API_KEY_HEADER)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == execution_id
    assert data["crew_name"] == "test-crew"
    assert data["status"] in ("queued", "running", "completed", "failed")


# ---------------------------------------------------------------------------
# Tests — cancel execution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_execution_not_found(client: AsyncClient):
    """POST /executions/{random-uuid}/cancel → 404."""
    random_id = str(uuid.uuid4())
    response = await client.post(
        f"/api/v1/executions/{random_id}/cancel", headers=API_KEY_HEADER
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cancel_execution(client: AsyncClient):
    """Cancel a queued execution → status becomes 'cancelled'."""
    await _create_full_crew(client)
    kickoff_resp = await client.post(
        "/api/v1/crews/test-crew/kickoff",
        json={"inputs": {}},
        headers=API_KEY_HEADER,
    )
    execution_id = kickoff_resp.json()["id"]

    cancel_resp = await client.post(
        f"/api/v1/executions/{execution_id}/cancel", headers=API_KEY_HEADER
    )
    assert cancel_resp.status_code == 200
    data = cancel_resp.json()
    assert data["status"] == "cancelled"
    assert data["completed_at"] is not None


@pytest.mark.asyncio
async def test_cancel_already_cancelled_is_idempotent(client: AsyncClient):
    """Cancelling an already-cancelled execution returns it unchanged."""
    await _create_full_crew(client)
    kickoff_resp = await client.post(
        "/api/v1/crews/test-crew/kickoff",
        json={"inputs": {}},
        headers=API_KEY_HEADER,
    )
    execution_id = kickoff_resp.json()["id"]

    # Cancel first time — succeeds
    await client.post(f"/api/v1/executions/{execution_id}/cancel", headers=API_KEY_HEADER)
    # Cancel second time — returns 409 since execution is already in terminal state
    second_cancel = await client.post(
        f"/api/v1/executions/{execution_id}/cancel", headers=API_KEY_HEADER
    )
    assert second_cancel.status_code == 409


# ---------------------------------------------------------------------------
# Tests — executions require auth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_executions_require_api_key(client: AsyncClient):
    """Execution endpoints should reject requests without X-API-Key."""
    response = await client.get("/api/v1/executions")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Tests — cancel race condition
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_preserves_status(client: AsyncClient):
    """Cancelled execution should not be overwritten by a late completion write."""
    await _create_full_crew(client)

    # Kickoff
    response = await client.post(
        "/api/v1/crews/test-crew/kickoff",
        json={"inputs": {}},
        headers=API_KEY_HEADER,
    )
    assert response.status_code == 202
    exec_id = response.json()["id"]

    # Cancel immediately (execution is still queued / just started)
    cancel_resp = await client.post(
        f"/api/v1/executions/{exec_id}/cancel", headers=API_KEY_HEADER
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"

    # Verify status persists after re-fetch
    get_resp = await client.get(f"/api/v1/executions/{exec_id}", headers=API_KEY_HEADER)
    assert get_resp.status_code == 200
    assert get_resp.json()["status"] == "cancelled"
