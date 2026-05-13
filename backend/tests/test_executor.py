"""Integration tests for the execution API endpoints.

Uses the same in-memory SQLite + httpx pattern as test_api.py.
CrewAI's crew.kickoff() is mocked so no real LLM calls are made.

Note: conftest.py patches sqlalchemy.dialects.postgresql.{JSONB,UUID} and
imports execution models BEFORE this module loads.
"""

import uuid

import pytest
from httpx import AsyncClient

from blackbeard.engine.executor import _sanitize_error
from tests.conftest import API_KEY_HEADER

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_full_crew(client: AsyncClient, crew_name: str = "test-crew") -> None:
    """Create LLM connection, agent, task, and crew resources via the API."""
    r = await client.post(
        "/api/v1/llm-connections",
        json={
            "apiVersion": "blackbeard/v1",
            "kind": "LLMConnection",
            "metadata": {"name": "test-llm"},
            "spec": {"provider": "vertex_ai", "model": "claude-sonnet-4-6"},
        },
        headers=API_KEY_HEADER,
    )
    assert r.status_code in (200, 201), f"LLMConnection setup failed: {r.status_code} {r.text}"

    r = await client.post(
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
    assert r.status_code in (200, 201), f"Agent setup failed: {r.status_code} {r.text}"

    r = await client.post(
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
    assert r.status_code in (200, 201), f"Task setup failed: {r.status_code} {r.text}"

    r = await client.post(
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
    assert r.status_code in (200, 201), f"Crew setup failed: {r.status_code} {r.text}"


# ---------------------------------------------------------------------------
# Tests — kickoff
# ---------------------------------------------------------------------------


async def test_kickoff_crew_not_found(client: AsyncClient):
    """POST /crews/{name}/kickoff for an unknown crew → 404."""
    response = await client.post(
        "/api/v1/crews/nonexistent/kickoff",
        json={"inputs": {}},
        headers=API_KEY_HEADER,
    )
    assert response.status_code == 404


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
    parsed_id = uuid.UUID(data["id"])
    assert isinstance(parsed_id, uuid.UUID)
    assert data["inputs"] == {"topic": "AI"}


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


async def test_list_executions_empty(client: AsyncClient):
    """GET /executions with no executions → 200, empty list."""
    response = await client.get("/api/v1/executions", headers=API_KEY_HEADER)
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0


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


async def test_get_execution_not_found(client: AsyncClient):
    """GET /executions/{random-uuid} → 404."""
    random_id = str(uuid.uuid4())
    response = await client.get(f"/api/v1/executions/{random_id}", headers=API_KEY_HEADER)
    assert response.status_code == 404
    assert "detail" in response.json()


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
    assert data["status"] == "queued"


# ---------------------------------------------------------------------------
# Tests — cancel execution
# ---------------------------------------------------------------------------


async def test_cancel_execution_not_found(client: AsyncClient):
    """PATCH /executions/{random-uuid}/cancel → 404."""
    random_id = str(uuid.uuid4())
    response = await client.patch(
        f"/api/v1/executions/{random_id}/cancel", headers=API_KEY_HEADER
    )
    assert response.status_code == 404
    assert "detail" in response.json()


async def test_cancel_execution(client: AsyncClient):
    """Cancel a queued execution → status becomes 'cancelled'."""
    await _create_full_crew(client)
    kickoff_resp = await client.post(
        "/api/v1/crews/test-crew/kickoff",
        json={"inputs": {}},
        headers=API_KEY_HEADER,
    )
    execution_id = kickoff_resp.json()["id"]

    cancel_resp = await client.patch(
        f"/api/v1/executions/{execution_id}/cancel", headers=API_KEY_HEADER
    )
    assert cancel_resp.status_code == 200
    data = cancel_resp.json()
    assert data["status"] == "cancelled"
    assert data["completed_at"] is not None


async def test_cancel_already_cancelled_returns_conflict(client: AsyncClient):
    """Cancelling an already-cancelled execution returns 409 Conflict."""
    await _create_full_crew(client)
    kickoff_resp = await client.post(
        "/api/v1/crews/test-crew/kickoff",
        json={"inputs": {}},
        headers=API_KEY_HEADER,
    )
    execution_id = kickoff_resp.json()["id"]

    # Cancel first time — succeeds
    first_cancel = await client.patch(
        f"/api/v1/executions/{execution_id}/cancel", headers=API_KEY_HEADER
    )
    assert first_cancel.status_code == 200
    # Cancel second time — returns 409 since execution is already in terminal state
    second_cancel = await client.patch(
        f"/api/v1/executions/{execution_id}/cancel", headers=API_KEY_HEADER
    )
    assert second_cancel.status_code == 409
    detail = second_cancel.json()["detail"]
    assert "terminal" in detail.lower() or "cancel" in detail.lower()


# ---------------------------------------------------------------------------
# Tests — executions require auth
# ---------------------------------------------------------------------------


async def test_list_executions_filter_by_status(client: AsyncClient):
    """Filter by status=queued should return only queued executions."""
    await _create_full_crew(client)
    await client.post(
        "/api/v1/crews/test-crew/kickoff",
        json={"inputs": {}},
        headers=API_KEY_HEADER,
    )

    response = await client.get(
        "/api/v1/executions?status=queued", headers=API_KEY_HEADER
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert all(item["status"] == "queued" for item in data["items"])

    response_none = await client.get(
        "/api/v1/executions?status=completed", headers=API_KEY_HEADER
    )
    assert response_none.status_code == 200
    assert response_none.json()["total"] == 0


async def test_executions_require_api_key(client: AsyncClient):
    """Execution endpoints should reject requests without X-API-Key."""
    response = await client.get("/api/v1/executions")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Tests — cancel race condition
# ---------------------------------------------------------------------------


async def test_cancel_preserves_status(client: AsyncClient):
    """Cancelled status should persist across re-fetches."""
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
    cancel_resp = await client.patch(
        f"/api/v1/executions/{exec_id}/cancel", headers=API_KEY_HEADER
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"

    # Verify status persists after re-fetch
    get_resp = await client.get(f"/api/v1/executions/{exec_id}", headers=API_KEY_HEADER)
    assert get_resp.status_code == 200
    assert get_resp.json()["status"] == "cancelled"


# ---------------------------------------------------------------------------
# Tests — _sanitize_error (security-critical error redaction)
# ---------------------------------------------------------------------------


def test_sanitize_error_empty_string():
    """Empty error string has no safe prefix — should be redacted."""
    result = _sanitize_error("")
    assert result == "Execution failed — check server logs for details"


def test_sanitize_error_exactly_500_chars_not_truncated():
    """A safe error at exactly 500 chars should NOT be truncated."""
    msg = "Crew '" + "x" * (500 - len("Crew '"))
    assert len(msg) == 500
    result = _sanitize_error(msg)
    assert result == msg


def test_sanitize_error_safe_prefix_passthrough():
    """Errors starting with safe prefixes should be returned as-is."""
    msg = "Crew 'my-crew' not found in namespace 'default'"
    assert _sanitize_error(msg) == msg


def test_sanitize_error_redacts_internal_details():
    """Internal error details (stack traces, DB errors) should be redacted."""
    msg = "sqlalchemy.exc.OperationalError: connection refused"
    result = _sanitize_error(msg)
    assert "sqlalchemy" not in result
    assert result == "Execution failed — check server logs for details"


def test_sanitize_error_truncates_long_safe_errors():
    """Long safe errors should be truncated at 500 chars + '...' = 503."""
    msg = "Crew '" + "x" * 600
    result = _sanitize_error(msg)
    assert len(result) == 503
    assert result.endswith("...")
    assert result[:500] == msg[:500]


def test_sanitize_error_501_chars_truncated():
    """A safe error at 501 chars (just over limit) should be truncated."""
    msg = "Crew '" + "x" * (501 - len("Crew '"))
    assert len(msg) == 501
    result = _sanitize_error(msg)
    assert len(result) == 503
    assert result.endswith("...")


@pytest.mark.parametrize("prefix", [
    "Crew '", "Agent '", "Task '", "Tool '", "Resource '", "Kind '",
])
def test_sanitize_error_all_safe_prefixes(prefix):
    """All documented safe prefixes should pass through."""
    msg = f"{prefix}some-name' failed for reasons"
    assert _sanitize_error(msg) == msg


@pytest.mark.parametrize("prefix", [
    "Crew '", "Agent '", "Task '", "Tool '", "Resource '", "Kind '",
])
def test_sanitize_error_all_safe_prefixes_truncate_at_limit(prefix):
    """Long safe errors with any prefix should truncate at 500 chars."""
    msg = prefix + "x" * 600
    result = _sanitize_error(msg)
    assert len(result) == 503
    assert result.endswith("...")
    assert result[:len(prefix)] == prefix
