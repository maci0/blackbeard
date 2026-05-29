"""Integration tests for the execution API endpoints.

Uses the same in-memory SQLite + httpx pattern as test_api.py.
CrewAI's crew.kickoff() is mocked so no real LLM calls are made.

Note: conftest.py patches sqlalchemy.dialects.postgresql.{JSONB,UUID} and
imports execution models BEFORE this module loads.
"""

import uuid

import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from blackbeard.engine.executor import _sanitize_error
from blackbeard.models.execution import TERMINAL_STATUSES, ExecutionStatus, ExecutionType
from blackbeard.models.execution_schemas import (
    KickoffRequest,
    TestRequest,
    TrainRequest,
)
from blackbeard.models.execution_schemas import (
    exceeds_depth as _exceeds_depth,
)
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
    assert "not found" in response.json()["detail"].lower()


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
    assert data["created_at"] is not None
    assert data["error"] is None, "New execution should have no error"
    assert data["outputs"] is None, "New execution should have no outputs"


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
    task = data["tasks"][0]
    assert task["task_name"] == "test-task"
    assert task["status"] == "pending"
    assert task["order"] == 0
    assert "id" in task
    assert "agent_name" in task
    assert task["tokens_used"] == 0
    assert task["output"] is None
    assert task["error"] is None


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
    assert data["has_more"] is False


async def test_list_executions_after_kickoff(client: AsyncClient):
    """After kicking off, list executions should include the new execution."""
    await _create_full_crew(client)
    r = await client.post(
        "/api/v1/crews/test-crew/kickoff",
        json={"inputs": {}},
        headers=API_KEY_HEADER,
    )
    assert r.status_code == 202, f"Kickoff setup failed: {r.status_code} {r.text}"

    response = await client.get("/api/v1/executions", headers=API_KEY_HEADER)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["crew_name"] == "test-crew"
    assert data["has_more"] is False


async def test_list_executions_filter_by_crew(client: AsyncClient):
    """Filter by crew_name should return only matching executions."""
    # Create two crews
    await _create_full_crew(client, crew_name="crew-alpha")
    # Reuse same agents/tasks for crew-beta
    r = await client.post(
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
    assert r.status_code in (200, 201), f"crew-beta setup failed: {r.status_code} {r.text}"

    r = await client.post(
        "/api/v1/crews/crew-alpha/kickoff", json={"inputs": {}}, headers=API_KEY_HEADER
    )
    assert r.status_code == 202, f"crew-alpha kickoff failed: {r.status_code} {r.text}"
    r = await client.post(
        "/api/v1/crews/crew-beta/kickoff", json={"inputs": {}}, headers=API_KEY_HEADER
    )
    assert r.status_code == 202, f"crew-beta kickoff failed: {r.status_code} {r.text}"

    response = await client.get("/api/v1/executions?crew_name=crew-alpha", headers=API_KEY_HEADER)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["crew_name"] == "crew-alpha"

    # Verify the other crew's execution exists but is filtered out
    all_resp = await client.get("/api/v1/executions", headers=API_KEY_HEADER)
    assert all_resp.json()["total"] == 2


# ---------------------------------------------------------------------------
# Tests — get execution
# ---------------------------------------------------------------------------


async def test_get_execution_not_found(client: AsyncClient):
    """GET /executions/{random-uuid} → 404."""
    random_id = str(uuid.uuid4())
    response = await client.get(f"/api/v1/executions/{random_id}", headers=API_KEY_HEADER)
    assert response.status_code == 404
    detail = response.json()["detail"].lower()
    assert "not found" in detail or "execution" in detail


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
    response = await client.patch(f"/api/v1/executions/{random_id}/cancel", headers=API_KEY_HEADER)
    assert response.status_code == 404
    detail = response.json()["detail"].lower()
    assert "not found" in detail or "execution" in detail


async def test_cancel_execution(client: AsyncClient):
    """Cancel a queued execution → status becomes 'cancelled'."""
    await _create_full_crew(client)
    kickoff_resp = await client.post(
        "/api/v1/crews/test-crew/kickoff",
        json={"inputs": {}},
        headers=API_KEY_HEADER,
    )
    assert kickoff_resp.status_code == 202
    execution_id = kickoff_resp.json()["id"]

    cancel_resp = await client.patch(
        f"/api/v1/executions/{execution_id}/cancel", headers=API_KEY_HEADER
    )
    assert cancel_resp.status_code == 200
    data = cancel_resp.json()
    assert data["status"] == "cancelled"
    assert isinstance(data["completed_at"], str), "completed_at should be a string"
    assert len(data["completed_at"]) > 0, "completed_at should be non-empty"
    assert data["error"] is None
    assert data["id"] == execution_id, "Cancelled response should return same execution id"
    assert data["crew_name"] == "test-crew", "Cancel response must preserve crew_name"


async def test_cancel_already_cancelled_returns_conflict(client: AsyncClient):
    """Cancelling an already-cancelled execution returns 409 Conflict."""
    await _create_full_crew(client)
    kickoff_resp = await client.post(
        "/api/v1/crews/test-crew/kickoff",
        json={"inputs": {}},
        headers=API_KEY_HEADER,
    )
    assert kickoff_resp.status_code == 202
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
# Tests — list executions with filters
# ---------------------------------------------------------------------------


async def test_list_executions_filter_by_status(client: AsyncClient):
    """Filter by status=queued should return only queued executions."""
    await _create_full_crew(client)
    r = await client.post(
        "/api/v1/crews/test-crew/kickoff",
        json={"inputs": {}},
        headers=API_KEY_HEADER,
    )
    assert r.status_code == 202, f"Kickoff setup failed: {r.status_code} {r.text}"

    response = await client.get("/api/v1/executions?status=queued", headers=API_KEY_HEADER)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert all(item["status"] == "queued" for item in data["items"])

    response_none = await client.get("/api/v1/executions?status=completed", headers=API_KEY_HEADER)
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
    cancel_resp = await client.patch(f"/api/v1/executions/{exec_id}/cancel", headers=API_KEY_HEADER)
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
    msg = "Crew 'my-crew' not found in project 'default'"
    assert _sanitize_error(msg) == msg


def test_sanitize_error_redacts_internal_details():
    """Internal error details (stack traces, DB errors) should be redacted."""
    msg = "sqlalchemy.exc.OperationalError: connection refused"
    result = _sanitize_error(msg)
    assert "sqlalchemy" not in result
    assert "connection refused" not in result
    assert result == "Execution failed — check server logs for details"


def test_sanitize_error_redacts_traceback():
    """Python traceback output should be redacted."""
    msg = 'Traceback (most recent call last):\n  File "/app/engine.py", line 42'
    result = _sanitize_error(msg)
    assert "Traceback" not in result
    assert "/app" not in result
    assert result == "Execution failed — check server logs for details"


def test_sanitize_error_redacts_file_path():
    """Error starting with File path should be redacted."""
    msg = 'File "/home/user/blackbeard/engine/loader.py", line 99, in build_crew'
    result = _sanitize_error(msg)
    assert "/home" not in result
    assert "loader.py" not in result
    assert "line 99" not in result
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


@pytest.mark.parametrize(
    "prefix",
    [
        "Crew '",
        "Agent '",
        "Task '",
        "Tool '",
        "Resource '",
        "Kind '",
        "LLMConnection '",
        "AgentPolicy '",
        "Guardrail '",
        "Flow '",
        "KnowledgeSource '",
    ],
)
def test_sanitize_error_all_safe_prefixes(prefix):
    """All documented safe prefixes should pass through."""
    msg = f"{prefix}some-name' failed for reasons"
    assert _sanitize_error(msg) == msg


@pytest.mark.parametrize(
    "prefix",
    [
        "Crew '",
        "Agent '",
        "Task '",
        "Tool '",
        "Resource '",
        "Kind '",
        "LLMConnection '",
        "AgentPolicy '",
        "Guardrail '",
        "Flow '",
        "KnowledgeSource '",
    ],
)
def test_sanitize_error_all_safe_prefixes_truncate_at_limit(prefix):
    """Long safe errors with any prefix should truncate at 500 chars."""
    msg = prefix + "x" * 600
    result = _sanitize_error(msg)
    assert len(result) == 503
    assert result.endswith("...")
    assert result[: len(prefix)] == prefix


# ---------------------------------------------------------------------------
# Tests — TERMINAL_STATUSES (critical for cancel logic)
# ---------------------------------------------------------------------------


def test_terminal_statuses_contains_expected():
    """TERMINAL_STATUSES must contain exactly the three terminal states."""
    expected = frozenset(
        {ExecutionStatus.COMPLETED, ExecutionStatus.FAILED, ExecutionStatus.CANCELLED}
    )
    assert expected == TERMINAL_STATUSES


def test_queued_and_running_not_terminal():
    """QUEUED and RUNNING must not be terminal — cancel relies on this."""
    assert ExecutionStatus.QUEUED not in TERMINAL_STATUSES
    assert ExecutionStatus.RUNNING not in TERMINAL_STATUSES


# ---------------------------------------------------------------------------
# Tests — KickoffRequest validation (security boundary)
# ---------------------------------------------------------------------------


def test_kickoff_request_accepts_valid_inputs():
    req = KickoffRequest(inputs={"topic": "AI", "depth": "detailed"})
    assert req.inputs["topic"] == "AI"


def test_kickoff_request_empty_inputs():
    req = KickoffRequest()
    assert req.inputs == {}


def test_kickoff_request_rejects_too_many_entries():
    inputs = {f"key-{i}": f"val-{i}" for i in range(101)}
    with pytest.raises(ValidationError, match=r"Too many"):
        KickoffRequest(inputs=inputs)


def test_kickoff_request_rejects_oversized_value():
    inputs = {"big": "x" * 50_001}
    with pytest.raises(ValidationError, match="exceeds"):
        KickoffRequest(inputs=inputs)


def test_kickoff_request_accepts_max_value_length():
    inputs = {"big": "x" * 50_000}
    req = KickoffRequest(inputs=inputs)
    assert len(req.inputs["big"]) == 50_000


def test_kickoff_request_rejects_unsafe_key():
    """Input keys must match [a-zA-Z_][a-zA-Z0-9_]* — reject injection vectors."""
    with pytest.raises(ValidationError, match="invalid"):
        KickoffRequest(inputs={"key with spaces": "val"})


def test_kickoff_request_rejects_key_starting_with_digit():
    with pytest.raises(ValidationError, match="invalid"):
        KickoffRequest(inputs={"123abc": "val"})


def test_kickoff_request_rejects_oversized_key():
    """Input keys longer than 256 chars should be rejected."""
    with pytest.raises(ValidationError, match="at most"):
        KickoffRequest(inputs={"k" * 257: "val"})


def test_kickoff_request_accepts_max_key_length():
    req = KickoffRequest(inputs={"k" * 256: "val"})
    assert len(next(iter(req.inputs.keys()))) == 256


def test_kickoff_request_rejects_deeply_nested():
    nested: dict = {}
    current = nested
    for _ in range(11):
        current["level"] = {}
        current = current["level"]
    with pytest.raises(ValidationError, match="depth"):
        KickoffRequest(inputs=nested)


# ---------------------------------------------------------------------------
# Tests — _exceeds_depth helper
# ---------------------------------------------------------------------------


def test_exceeds_depth_flat_dict():
    assert _exceeds_depth({"a": 1, "b": 2}) is False


def test_exceeds_depth_at_limit():
    nested: dict = {}
    current = nested
    for _ in range(9):
        current["k"] = {}
        current = current["k"]
    assert _exceeds_depth(nested, limit=10) is False


def test_exceeds_depth_over_limit():
    nested: dict = {}
    current = nested
    for _ in range(10):
        current["k"] = {}
        current = current["k"]
    assert _exceeds_depth(nested, limit=10) is True


def test_exceeds_depth_scalar_root():
    """Scalar (non-container) values should never exceed depth."""
    assert _exceeds_depth(42) is False
    assert _exceeds_depth("hello") is False
    assert _exceeds_depth(None) is False


def test_exceeds_depth_with_lists():
    obj = {"a": [{"b": [{"c": 1}]}]}
    assert _exceeds_depth(obj, limit=6) is False
    assert _exceeds_depth(obj, limit=4) is True


# ---------------------------------------------------------------------------
# Tests — _snapshot_resource
# ---------------------------------------------------------------------------


def test_build_principal_chain_without_user():
    """_build_principal_chain without a user should omit user key."""
    from blackbeard.engine.executor import _build_principal_chain

    resources = {
        "Agent/researcher": {
            "kind": "Agent",
            "name": "researcher",
            "project": "default",
            "spec": {"role": "R", "goal": "G", "backstory": "B"},
        },
    }
    chain = _build_principal_chain(None, "my-crew", resources)
    assert "user" not in chain
    assert chain["crew"] == "my-crew"
    assert len(chain["agents"]) == 1
    assert chain["agents"][0]["name"] == "researcher"
    assert chain["agents"][0]["serviceAccount"] == "sa-researcher"


def test_build_principal_chain_with_custom_service_account():
    """_build_principal_chain should use serviceAccount from agent spec."""
    from blackbeard.engine.executor import _build_principal_chain

    resources = {
        "Agent/deployer": {
            "kind": "Agent",
            "name": "deployer",
            "project": "default",
            "spec": {
                "role": "R",
                "goal": "G",
                "backstory": "B",
                "serviceAccount": "deploy-sa",
            },
        },
    }
    chain = _build_principal_chain(None, "deploy-crew", resources)
    assert chain["agents"][0]["serviceAccount"] == "deploy-sa"


def test_build_principal_chain_with_user():
    """_build_principal_chain with a user should include user info."""
    import uuid

    from blackbeard.engine.executor import _build_principal_chain
    from blackbeard.models.user import User

    user = User()
    user.id = uuid.UUID("12345678-1234-1234-1234-123456789abc")
    user.email = "alice@example.com"
    user.display_name = "Alice"
    user.password_hash = "hashed"

    resources = {
        "Agent/researcher": {
            "kind": "Agent",
            "name": "researcher",
            "project": "default",
            "spec": {"role": "R", "goal": "G", "backstory": "B"},
        },
    }
    chain = _build_principal_chain(user, "my-crew", resources)
    assert chain["user"]["id"] == "12345678-1234-1234-1234-123456789abc"
    assert "email" not in chain["user"], "Email must not leak into principal chain"
    assert "password_hash" not in chain["user"], "Password hash must not leak into principal chain"
    assert "hashed" not in str(chain["user"]), "Actual password hash value must not appear in chain"
    for key in chain["user"]:
        assert "password" not in key.lower(), f"Key {key!r} contains 'password' — must not leak"
    assert chain["crew"] == "my-crew"


def test_build_principal_chain_skips_non_agent_resources():
    """_build_principal_chain should only include Agent/* resources."""
    from blackbeard.engine.executor import _build_principal_chain

    resources = {
        "Crew/my-crew": {
            "kind": "Crew",
            "name": "my-crew",
            "project": "default",
            "spec": {"process": "sequential", "agents": [], "tasks": []},
        },
        "Agent/worker": {
            "kind": "Agent",
            "name": "worker",
            "project": "default",
            "spec": {"role": "R", "goal": "G", "backstory": "B"},
        },
        "Task/do-stuff": {
            "kind": "Task",
            "name": "do-stuff",
            "project": "default",
            "spec": {
                "description": "D",
                "expected_output": "E",
                "agent": "ref:agents/worker",
            },
        },
    }
    chain = _build_principal_chain(None, "my-crew", resources)
    assert len(chain["agents"]) == 1
    assert chain["agents"][0]["name"] == "worker"


def test_snapshot_resource_captures_essentials():
    """_snapshot_resource should capture kind/name/project/spec only."""
    from blackbeard.engine.executor import _snapshot_resource
    from blackbeard.kinds import ResourceKind
    from blackbeard.models.resource import Resource

    r = Resource()
    r.kind = ResourceKind.AGENT
    r.name = "test-agent"
    r.project = "default"
    r.spec = {"role": "R", "goal": "G", "backstory": "B"}
    r.raw_yaml = "should-not-appear"
    r.labels = {"env": "test"}

    snap = _snapshot_resource(r)
    assert snap == {
        "kind": "Agent",
        "name": "test-agent",
        "project": "default",
        "spec": {"role": "R", "goal": "G", "backstory": "B"},
    }
    assert "raw_yaml" not in snap
    assert "labels" not in snap


def test_snapshot_resource_none_spec():
    """_snapshot_resource with None spec should return empty dict for spec."""
    from blackbeard.engine.executor import _snapshot_resource
    from blackbeard.kinds import ResourceKind
    from blackbeard.models.resource import Resource

    r = Resource()
    r.kind = ResourceKind.TOOL
    r.name = "empty-tool"
    r.project = "default"
    r.spec = None

    snap = _snapshot_resource(r)
    assert snap["spec"] == {}


def test_snapshot_resource_spec_is_copy():
    """_snapshot_resource spec should be a new dict, not a reference to the original."""
    from blackbeard.engine.executor import _snapshot_resource
    from blackbeard.kinds import ResourceKind
    from blackbeard.models.resource import Resource

    original_spec = {"role": "R", "goal": "G"}
    r = Resource()
    r.kind = ResourceKind.AGENT
    r.name = "ag"
    r.project = "default"
    r.spec = original_spec

    snap = _snapshot_resource(r)
    snap["spec"]["injected"] = "bad"
    assert "injected" not in original_spec
    original_spec["mutated"] = "also-bad"
    assert "mutated" not in snap["spec"]


# ---------------------------------------------------------------------------
# Tests — kickoff input validation at the API boundary
# ---------------------------------------------------------------------------


async def test_kickoff_rejects_empty_body(client: AsyncClient):
    """POST /crews/{name}/kickoff without a body should return 422."""
    await _create_full_crew(client)
    response = await client.post(
        "/api/v1/crews/test-crew/kickoff",
        content=b"",
        headers={**API_KEY_HEADER, "Content-Type": "application/json"},
    )
    assert response.status_code == 422
    detail = response.json().get("detail")
    assert detail is not None, "422 response should include detail"
    assert detail != "", "422 detail should be non-empty"


async def test_kickoff_rejects_non_json_body(client: AsyncClient):
    """POST /crews/{name}/kickoff with non-JSON body should return 422."""
    await _create_full_crew(client)
    response = await client.post(
        "/api/v1/crews/test-crew/kickoff",
        content=b"not json",
        headers={**API_KEY_HEADER, "Content-Type": "application/json"},
    )
    assert response.status_code == 422
    detail = response.json().get("detail")
    assert detail is not None, "422 response should include detail"
    assert detail != "", "422 detail should be non-empty"


# ---------------------------------------------------------------------------
# Tests — execution listing pagination
# ---------------------------------------------------------------------------


async def test_list_executions_pagination(client: AsyncClient):
    """Pagination parameters should limit results correctly."""
    await _create_full_crew(client)
    # Create 3 executions
    for _ in range(3):
        await client.post(
            "/api/v1/crews/test-crew/kickoff",
            json={"inputs": {}},
            headers=API_KEY_HEADER,
        )

    # Fetch page 1 (limit 2)
    response = await client.get("/api/v1/executions?limit=2&offset=0", headers=API_KEY_HEADER)
    assert response.status_code == 200
    page1 = response.json()
    assert len(page1["items"]) == 2
    assert page1["total"] == 3
    assert page1["has_more"] is True

    # Fetch page 2
    response = await client.get("/api/v1/executions?limit=2&offset=2", headers=API_KEY_HEADER)
    assert response.status_code == 200
    page2 = response.json()
    assert len(page2["items"]) == 1
    assert page2["has_more"] is False

    # Pages must not overlap
    page1_ids = {item["id"] for item in page1["items"]}
    page2_ids = {item["id"] for item in page2["items"]}
    assert page1_ids.isdisjoint(page2_ids), "Pagination pages must not contain duplicate IDs"
    assert len(page1_ids | page2_ids) == 3, "All 3 executions should appear across pages"


# ---------------------------------------------------------------------------
# Tests — execution response shape validation
# ---------------------------------------------------------------------------


async def test_execution_response_has_required_fields(client: AsyncClient):
    """Execution response should include all required fields with correct types."""
    await _create_full_crew(client)
    kickoff_resp = await client.post(
        "/api/v1/crews/test-crew/kickoff",
        json={"inputs": {"topic": "AI"}},
        headers=API_KEY_HEADER,
    )
    assert kickoff_resp.status_code == 202
    data = kickoff_resp.json()

    # Verify all required fields are present
    required_fields = {
        "id",
        "crew_name",
        "crew_project",
        "status",
        "inputs",
        "total_tokens",
        "prompt_tokens",
        "completion_tokens",
        "cost_usd",
        "created_at",
        "tasks",
    }
    assert required_fields.issubset(data.keys()), (
        f"Missing fields: {required_fields - set(data.keys())}"
    )
    # Verify types and zero-initialization for new executions
    assert isinstance(data["total_tokens"], int)
    assert isinstance(data["tasks"], list)
    assert isinstance(data["cost_usd"], (int, float, str)), (
        f"cost_usd should be numeric or string-encoded decimal, got {type(data['cost_usd'])}"
    )
    if isinstance(data["cost_usd"], str):
        parsed = float(data["cost_usd"])
        assert parsed >= 0, f"cost_usd must be non-negative, got {parsed}"
    assert data["crew_project"] == "default"
    assert data["total_tokens"] == 0
    assert data["prompt_tokens"] == 0
    assert data["completion_tokens"] == 0
    assert data["started_at"] is None, "New execution should not have started_at"
    assert data["completed_at"] is None, "New execution should not have completed_at"


# ---------------------------------------------------------------------------
# Tests — ServiceAccount execution context (principal chain / initiated_by)
# ---------------------------------------------------------------------------


async def test_kickoff_without_user_has_no_initiated_by(client: AsyncClient):
    """Kickoff via API key (no JWT) should leave initiated_by as None."""
    await _create_full_crew(client)

    response = await client.post(
        "/api/v1/crews/test-crew/kickoff",
        json={"inputs": {}},
        headers=API_KEY_HEADER,
    )
    assert response.status_code == 202
    data = response.json()
    assert data["initiated_by"] is None


async def test_kickoff_without_user_has_principal_chain(client: AsyncClient):
    """Even without a user, principal_chain should contain crew and agents."""
    await _create_full_crew(client)

    response = await client.post(
        "/api/v1/crews/test-crew/kickoff",
        json={"inputs": {}},
        headers=API_KEY_HEADER,
    )
    assert response.status_code == 202
    data = response.json()
    chain = data["principal_chain"]
    assert chain is not None
    assert chain["crew"] == "test-crew"
    assert "agents" in chain
    assert isinstance(chain["agents"], list)
    assert len(chain["agents"]) >= 1
    # Agent should have default serviceAccount
    agent_entry = chain["agents"][0]
    assert agent_entry["name"] == "test-agent"
    assert agent_entry["serviceAccount"] == "sa-test-agent"
    # No user in chain when authenticating with API key only
    assert "user" not in chain


async def test_principal_chain_uses_custom_service_account(client: AsyncClient):
    """When agent spec has serviceAccount, it should appear in the principal chain."""
    # Create agent with custom serviceAccount
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
    assert r.status_code in (200, 201)

    r = await client.post(
        "/api/v1/agents",
        json={
            "apiVersion": "blackbeard/v1",
            "kind": "Agent",
            "metadata": {"name": "sa-agent"},
            "spec": {
                "role": "Test Agent",
                "goal": "Test goal",
                "backstory": "Test backstory",
                "serviceAccount": "custom-sa",
            },
        },
        headers=API_KEY_HEADER,
    )
    assert r.status_code in (200, 201)

    r = await client.post(
        "/api/v1/tasks",
        json={
            "apiVersion": "blackbeard/v1",
            "kind": "Task",
            "metadata": {"name": "sa-task"},
            "spec": {
                "description": "Test task",
                "expected_output": "Output",
                "agent": "ref:agents/sa-agent",
            },
        },
        headers=API_KEY_HEADER,
    )
    assert r.status_code in (200, 201)

    r = await client.post(
        "/api/v1/crews",
        json={
            "apiVersion": "blackbeard/v1",
            "kind": "Crew",
            "metadata": {"name": "sa-crew"},
            "spec": {
                "process": "sequential",
                "agents": ["ref:agents/sa-agent"],
                "tasks": ["ref:tasks/sa-task"],
            },
        },
        headers=API_KEY_HEADER,
    )
    assert r.status_code in (200, 201)

    response = await client.post(
        "/api/v1/crews/sa-crew/kickoff",
        json={"inputs": {}},
        headers=API_KEY_HEADER,
    )
    assert response.status_code == 202
    data = response.json()
    chain = data["principal_chain"]
    assert chain is not None
    # Find the agent with the custom service account
    agent_entry = next(a for a in chain["agents"] if a["name"] == "sa-agent")
    assert agent_entry["serviceAccount"] == "custom-sa"


async def test_execution_response_includes_identity_fields(client: AsyncClient):
    """Execution response should include initiated_by and principal_chain fields."""
    await _create_full_crew(client)
    kickoff_resp = await client.post(
        "/api/v1/crews/test-crew/kickoff",
        json={"inputs": {}},
        headers=API_KEY_HEADER,
    )
    assert kickoff_resp.status_code == 202
    data = kickoff_resp.json()

    # Fields must be present in the response
    assert "initiated_by" in data
    assert "principal_chain" in data

    # Verify via GET as well
    exec_id = data["id"]
    get_resp = await client.get(f"/api/v1/executions/{exec_id}", headers=API_KEY_HEADER)
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert "initiated_by" in get_data
    assert "principal_chain" in get_data
    assert get_data["principal_chain"]["crew"] == "test-crew"


async def test_list_executions_includes_identity_fields(client: AsyncClient):
    """List executions should include initiated_by and principal_chain."""
    await _create_full_crew(client)
    r = await client.post(
        "/api/v1/crews/test-crew/kickoff",
        json={"inputs": {}},
        headers=API_KEY_HEADER,
    )
    assert r.status_code == 202

    response = await client.get("/api/v1/executions", headers=API_KEY_HEADER)
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert "initiated_by" in items[0]
    assert "principal_chain" in items[0]


# ---------------------------------------------------------------------------
# Tests — execution_type field on kickoff
# ---------------------------------------------------------------------------


async def test_kickoff_has_execution_type_kickoff(client: AsyncClient):
    """Kickoff executions should have execution_type='kickoff'."""
    await _create_full_crew(client)
    response = await client.post(
        "/api/v1/crews/test-crew/kickoff",
        json={"inputs": {}},
        headers=API_KEY_HEADER,
    )
    assert response.status_code == 202
    data = response.json()
    assert data["execution_type"] == "kickoff"
    assert data["n_iterations"] is None
    assert data["training_file"] is None


# ---------------------------------------------------------------------------
# Tests — train endpoint
# ---------------------------------------------------------------------------


async def test_train_crew_not_found(client: AsyncClient):
    """POST /crews/{name}/train for an unknown crew returns 404."""
    response = await client.post(
        "/api/v1/crews/nonexistent/train",
        json={"inputs": {}, "n_iterations": 3},
        headers=API_KEY_HEADER,
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


async def test_train_crew(client: AsyncClient):
    """Training an existing crew returns 202 with execution_type=train."""
    await _create_full_crew(client)

    response = await client.post(
        "/api/v1/crews/test-crew/train",
        json={"inputs": {"topic": "AI"}, "n_iterations": 5, "filename": "custom.pkl"},
        headers=API_KEY_HEADER,
    )
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "queued"
    assert data["crew_name"] == "test-crew"
    assert data["execution_type"] == "train"
    assert data["n_iterations"] == 5
    assert data["training_file"] == "custom.pkl"
    assert data["inputs"] == {"topic": "AI"}
    assert "id" in data
    parsed_id = uuid.UUID(data["id"])
    assert isinstance(parsed_id, uuid.UUID)


async def test_train_crew_default_values(client: AsyncClient):
    """Train with default n_iterations and filename."""
    await _create_full_crew(client)

    response = await client.post(
        "/api/v1/crews/test-crew/train",
        json={"inputs": {}},
        headers=API_KEY_HEADER,
    )
    assert response.status_code == 202
    data = response.json()
    assert data["execution_type"] == "train"
    assert data["n_iterations"] == 3
    assert data["training_file"] == "training_data.pkl"


async def test_train_crew_has_tasks(client: AsyncClient):
    """Trained execution should have task records matching the crew's tasks."""
    await _create_full_crew(client)

    response = await client.post(
        "/api/v1/crews/test-crew/train",
        json={"inputs": {}},
        headers=API_KEY_HEADER,
    )
    assert response.status_code == 202
    data = response.json()
    assert len(data["tasks"]) == 1
    assert data["tasks"][0]["task_name"] == "test-task"
    assert data["tasks"][0]["status"] == "pending"


async def test_train_crew_requires_auth(client: AsyncClient):
    """Train endpoint should reject requests without API key."""
    response = await client.post(
        "/api/v1/crews/test-crew/train",
        json={"inputs": {}},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Tests — test endpoint
# ---------------------------------------------------------------------------


async def test_test_crew_not_found(client: AsyncClient):
    """POST /crews/{name}/test for an unknown crew returns 404."""
    response = await client.post(
        "/api/v1/crews/nonexistent/test",
        json={"inputs": {}, "n_iterations": 3},
        headers=API_KEY_HEADER,
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


async def test_test_crew(client: AsyncClient):
    """Testing an existing crew returns 202 with execution_type=test."""
    await _create_full_crew(client)

    response = await client.post(
        "/api/v1/crews/test-crew/test",
        json={"inputs": {"topic": "AI"}, "n_iterations": 2},
        headers=API_KEY_HEADER,
    )
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "queued"
    assert data["crew_name"] == "test-crew"
    assert data["execution_type"] == "test"
    assert data["n_iterations"] == 2
    assert data["training_file"] is None
    assert data["inputs"] == {"topic": "AI"}
    assert "id" in data


async def test_test_crew_default_iterations(client: AsyncClient):
    """Test with default n_iterations."""
    await _create_full_crew(client)

    response = await client.post(
        "/api/v1/crews/test-crew/test",
        json={"inputs": {}},
        headers=API_KEY_HEADER,
    )
    assert response.status_code == 202
    data = response.json()
    assert data["execution_type"] == "test"
    assert data["n_iterations"] == 3


async def test_test_crew_requires_auth(client: AsyncClient):
    """Test endpoint should reject requests without API key."""
    response = await client.post(
        "/api/v1/crews/test-crew/test",
        json={"inputs": {}},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Tests — train/test execution visible in list and get
# ---------------------------------------------------------------------------


async def test_train_execution_visible_in_list(client: AsyncClient):
    """Train executions should appear in the executions list."""
    await _create_full_crew(client)
    r = await client.post(
        "/api/v1/crews/test-crew/train",
        json={"inputs": {}},
        headers=API_KEY_HEADER,
    )
    assert r.status_code == 202

    response = await client.get("/api/v1/executions", headers=API_KEY_HEADER)
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["execution_type"] == "train"


async def test_test_execution_visible_via_get(client: AsyncClient):
    """Test executions should be retrievable via GET /executions/{id}."""
    await _create_full_crew(client)
    r = await client.post(
        "/api/v1/crews/test-crew/test",
        json={"inputs": {}},
        headers=API_KEY_HEADER,
    )
    assert r.status_code == 202
    execution_id = r.json()["id"]

    response = await client.get(f"/api/v1/executions/{execution_id}", headers=API_KEY_HEADER)
    assert response.status_code == 200
    data = response.json()
    assert data["execution_type"] == "test"
    assert data["id"] == execution_id


# ---------------------------------------------------------------------------
# Tests — TrainRequest / TestRequest validation
# ---------------------------------------------------------------------------


def test_train_request_valid():
    req = TrainRequest(inputs={"topic": "AI"}, n_iterations=5, filename="data.pkl")
    assert req.n_iterations == 5
    assert req.filename == "data.pkl"


def test_train_request_defaults():
    req = TrainRequest()
    assert req.inputs == {}
    assert req.n_iterations == 3
    assert req.filename == "training_data.pkl"


def test_train_request_rejects_bad_filename():
    with pytest.raises(ValidationError, match="filename"):
        TrainRequest(filename="../escape.pkl")


def test_train_request_rejects_non_pkl_filename():
    with pytest.raises(ValidationError, match="pkl"):
        TrainRequest(filename="data.json")


def test_train_request_rejects_zero_iterations():
    with pytest.raises(ValidationError):
        TrainRequest(n_iterations=0)


def test_train_request_rejects_excessive_iterations():
    with pytest.raises(ValidationError):
        TrainRequest(n_iterations=101)


def test_train_request_validates_inputs():
    """TrainRequest should validate inputs the same way KickoffRequest does."""
    with pytest.raises(ValidationError, match="invalid"):
        TrainRequest(inputs={"key with spaces": "val"})


def test_test_request_valid():
    req = TestRequest(inputs={"topic": "AI"}, n_iterations=5)
    assert req.n_iterations == 5


def test_test_request_defaults():
    req = TestRequest()
    assert req.inputs == {}
    assert req.n_iterations == 3


def test_test_request_rejects_zero_iterations():
    with pytest.raises(ValidationError):
        TestRequest(n_iterations=0)


def test_test_request_validates_inputs():
    with pytest.raises(ValidationError, match="invalid"):
        TestRequest(inputs={"123abc": "val"})


# ---------------------------------------------------------------------------
# Tests — ExecutionType enum
# ---------------------------------------------------------------------------


def test_execution_type_values():
    """ExecutionType enum should have kickoff, train, test, flow."""
    assert set(ExecutionType) == {
        ExecutionType.KICKOFF,
        ExecutionType.TRAIN,
        ExecutionType.TEST,
        ExecutionType.FLOW,
    }
    assert ExecutionType.KICKOFF.value == "kickoff"
    assert ExecutionType.TRAIN.value == "train"
    assert ExecutionType.TEST.value == "test"
    assert ExecutionType.FLOW.value == "flow"


# ---------------------------------------------------------------------------
# Tests — train/test cancel
# ---------------------------------------------------------------------------


async def test_cancel_train_execution(client: AsyncClient):
    """Cancel a queued training execution -> status becomes 'cancelled'."""
    await _create_full_crew(client)
    r = await client.post(
        "/api/v1/crews/test-crew/train",
        json={"inputs": {}},
        headers=API_KEY_HEADER,
    )
    assert r.status_code == 202
    execution_id = r.json()["id"]

    cancel_resp = await client.patch(
        f"/api/v1/executions/{execution_id}/cancel", headers=API_KEY_HEADER
    )
    assert cancel_resp.status_code == 200
    data = cancel_resp.json()
    assert data["status"] == "cancelled"
    assert data["execution_type"] == "train"
