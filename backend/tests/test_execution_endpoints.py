"""Integration tests for the execution API endpoints (api/executions.py).

Covers crew kickoff, train, test, flow endpoints, execution listing,
detail retrieval, event listing, cancellation, and SSE streaming.

All executor functions are mocked to avoid running real CrewAI: the
executor unit tests already cover that layer.
"""

from __future__ import annotations

import contextlib
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from tests.conftest import API_KEY_HEADER

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _crew_payload(name: str = "test-crew") -> dict:
    """Minimal Crew resource payload."""
    return {
        "apiVersion": "blackbeard/v1",
        "kind": "Crew",
        "metadata": {"name": name, "project": "default"},
        "spec": {
            "agents": [],
            "tasks": [],
            "process": "sequential",
        },
    }


def _flow_payload(name: str = "test-flow") -> dict:
    """Minimal Flow resource payload."""
    return {
        "apiVersion": "blackbeard/v1",
        "kind": "Flow",
        "metadata": {"name": name, "project": "default"},
        "spec": {
            "steps": [
                {"name": "step-1", "type": "crew", "crew": "ref:crews/test-crew"},
            ],
        },
    }


async def _create_crew(client: AsyncClient, name: str = "test-crew") -> None:
    """Create a crew resource in the test database."""
    resp = await client.post("/api/v1/crews", json=_crew_payload(name), headers=API_KEY_HEADER)
    assert resp.status_code == 201, f"Crew setup failed: {resp.status_code} {resp.text}"


async def _create_flow(client: AsyncClient, name: str = "test-flow") -> None:
    """Create a flow resource in the test database (plus its referenced crew)."""
    await _create_crew(client, "test-crew")
    resp = await client.post("/api/v1/flows", json=_flow_payload(name), headers=API_KEY_HEADER)
    assert resp.status_code == 201, f"Flow setup failed: {resp.status_code} {resp.text}"


def _make_mock_execution(
    *,
    crew_name: str = "test-crew",
    execution_type: str = "kickoff",
    status: str = "queued",
    project: str = "default",
) -> object:
    """Build a detached Execution ORM object for mocking executor returns."""
    from blackbeard.models.execution import Execution, ExecutionStatus, ExecutionType

    e = Execution()
    e.id = uuid.uuid4()
    e.crew_name = crew_name
    e.crew_project = project
    e.execution_type = ExecutionType(execution_type)
    e.status = ExecutionStatus(status)
    e.inputs = {}
    e.outputs = None
    e.error = None
    e.total_tokens = 0
    e.prompt_tokens = 0
    e.completion_tokens = 0
    e.cost_usd = Decimal("0")
    e.n_iterations = None
    e.training_file = None
    e.initiated_by = None
    e.principal_chain = None
    e.created_at = datetime.now(UTC)
    e.started_at = None
    e.completed_at = None
    e.tasks = []
    return e


# ---------------------------------------------------------------------------
# POST /crews/{name}/kickoff
# ---------------------------------------------------------------------------


async def test_kickoff_crew_not_found(client: AsyncClient):
    """POST /crews/{name}/kickoff for missing crew returns 404."""
    from blackbeard.engine import ExecutionNotFoundError

    with patch(
        "blackbeard.api.executions._executor_mod.kickoff",
        new_callable=AsyncMock,
        side_effect=ExecutionNotFoundError("Crew 'ghost' not found"),
    ):
        resp = await client.post(
            "/api/v1/crews/ghost/kickoff",
            json={"inputs": {}},
            headers=API_KEY_HEADER,
        )
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


async def test_kickoff_crew_success(client: AsyncClient):
    """POST /crews/{name}/kickoff for valid crew returns 202."""
    mock_exec = _make_mock_execution()

    with patch(
        "blackbeard.api.executions._executor_mod.kickoff",
        new_callable=AsyncMock,
        return_value=mock_exec,
    ):
        resp = await client.post(
            "/api/v1/crews/test-crew/kickoff",
            json={"inputs": {}},
            headers=API_KEY_HEADER,
        )
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "queued"
    assert data["crew_name"] == "test-crew"
    assert "id" in data


async def test_kickoff_crew_with_inputs(client: AsyncClient):
    """POST /crews/{name}/kickoff passes inputs to the executor."""
    mock_exec = _make_mock_execution()
    captured_inputs = {}

    async def _capture_kickoff(session, crew_name, inputs, project, user=None):
        captured_inputs.update(inputs)
        return mock_exec

    with patch(
        "blackbeard.api.executions._executor_mod.kickoff",
        new_callable=AsyncMock,
        side_effect=_capture_kickoff,
    ):
        resp = await client.post(
            "/api/v1/crews/test-crew/kickoff",
            json={"inputs": {"topic": "AI safety"}},
            headers=API_KEY_HEADER,
        )
    assert resp.status_code == 202
    assert captured_inputs == {"topic": "AI safety"}


async def test_kickoff_crew_internal_error(client: AsyncClient):
    """POST /crews/{name}/kickoff executor error returns 500."""
    from blackbeard.engine import ExecutionError

    with patch(
        "blackbeard.api.executions._executor_mod.kickoff",
        new_callable=AsyncMock,
        side_effect=ExecutionError("Internal consistency error"),
    ):
        resp = await client.post(
            "/api/v1/crews/test-crew/kickoff",
            json={"inputs": {}},
            headers=API_KEY_HEADER,
        )
    assert resp.status_code == 500
    assert "detail" in resp.json()


# ---------------------------------------------------------------------------
# POST /crews/{name}/train
# ---------------------------------------------------------------------------


async def test_train_crew_success(client: AsyncClient):
    """POST /crews/{name}/train returns 202 with correct body."""
    mock_exec = _make_mock_execution(execution_type="train")

    with patch(
        "blackbeard.api.executions._executor_mod.train_crew",
        new_callable=AsyncMock,
        return_value=mock_exec,
    ):
        resp = await client.post(
            "/api/v1/crews/test-crew/train",
            json={"inputs": {}, "n_iterations": 5, "filename": "output.pkl"},
            headers=API_KEY_HEADER,
        )
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "queued"
    assert data["crew_name"] == "test-crew"


async def test_train_crew_not_found(client: AsyncClient):
    """POST /crews/{name}/train for missing crew returns 404."""
    from blackbeard.engine import ExecutionNotFoundError

    with patch(
        "blackbeard.api.executions._executor_mod.train_crew",
        new_callable=AsyncMock,
        side_effect=ExecutionNotFoundError("Crew 'ghost' not found"),
    ):
        resp = await client.post(
            "/api/v1/crews/ghost/train",
            json={"inputs": {}, "n_iterations": 3, "filename": "train.pkl"},
            headers=API_KEY_HEADER,
        )
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


async def test_train_crew_internal_error(client: AsyncClient):
    """POST /crews/{name}/train executor error returns 500."""
    from blackbeard.engine import ExecutionError

    with patch(
        "blackbeard.api.executions._executor_mod.train_crew",
        new_callable=AsyncMock,
        side_effect=ExecutionError("Internal error"),
    ):
        resp = await client.post(
            "/api/v1/crews/test-crew/train",
            json={"inputs": {}, "n_iterations": 3, "filename": "train.pkl"},
            headers=API_KEY_HEADER,
        )
    assert resp.status_code == 500
    assert isinstance(resp.json()["detail"], str) and len(resp.json()["detail"]) > 0


# ---------------------------------------------------------------------------
# POST /crews/{name}/test
# ---------------------------------------------------------------------------


async def test_test_crew_success(client: AsyncClient):
    """POST /crews/{name}/test returns 202 with correct body."""
    mock_exec = _make_mock_execution(execution_type="test")

    with patch(
        "blackbeard.api.executions._executor_mod.test_crew",
        new_callable=AsyncMock,
        return_value=mock_exec,
    ):
        resp = await client.post(
            "/api/v1/crews/test-crew/test",
            json={"inputs": {}, "n_iterations": 2},
            headers=API_KEY_HEADER,
        )
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "queued"
    assert data["crew_name"] == "test-crew"


async def test_test_crew_not_found(client: AsyncClient):
    """POST /crews/{name}/test for missing crew returns 404."""
    from blackbeard.engine import ExecutionNotFoundError

    with patch(
        "blackbeard.api.executions._executor_mod.test_crew",
        new_callable=AsyncMock,
        side_effect=ExecutionNotFoundError("Crew 'ghost' not found"),
    ):
        resp = await client.post(
            "/api/v1/crews/ghost/test",
            json={"inputs": {}, "n_iterations": 2},
            headers=API_KEY_HEADER,
        )
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


async def test_test_crew_internal_error(client: AsyncClient):
    """POST /crews/{name}/test executor error returns 500."""
    from blackbeard.engine import ExecutionError

    with patch(
        "blackbeard.api.executions._executor_mod.test_crew",
        new_callable=AsyncMock,
        side_effect=ExecutionError("Internal error"),
    ):
        resp = await client.post(
            "/api/v1/crews/test-crew/test",
            json={"inputs": {}, "n_iterations": 2},
            headers=API_KEY_HEADER,
        )
    assert resp.status_code == 500
    assert isinstance(resp.json()["detail"], str) and len(resp.json()["detail"]) > 0


# ---------------------------------------------------------------------------
# POST /flows/{name}/run
# ---------------------------------------------------------------------------


async def test_run_flow_success(client: AsyncClient):
    """POST /flows/{name}/run returns 202 for valid flow."""
    mock_exec = _make_mock_execution(execution_type="flow", crew_name="test-flow")

    with patch(
        "blackbeard.api.executions._executor_mod.run_flow",
        new_callable=AsyncMock,
        return_value=mock_exec,
    ):
        resp = await client.post(
            "/api/v1/flows/test-flow/run",
            json={"inputs": {}},
            headers=API_KEY_HEADER,
        )
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "queued"
    assert data["crew_name"] == "test-flow"


async def test_run_flow_not_found(client: AsyncClient):
    """POST /flows/{name}/run for missing flow returns 404."""
    from blackbeard.engine import ExecutionNotFoundError

    with patch(
        "blackbeard.api.executions._executor_mod.run_flow",
        new_callable=AsyncMock,
        side_effect=ExecutionNotFoundError("Flow 'ghost' not found"),
    ):
        resp = await client.post(
            "/api/v1/flows/ghost/run",
            json={"inputs": {}},
            headers=API_KEY_HEADER,
        )
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


async def test_run_flow_internal_error(client: AsyncClient):
    """POST /flows/{name}/run executor error returns 500."""
    from blackbeard.engine import ExecutionError

    with patch(
        "blackbeard.api.executions._executor_mod.run_flow",
        new_callable=AsyncMock,
        side_effect=ExecutionError("Internal error"),
    ):
        resp = await client.post(
            "/api/v1/flows/test-flow/run",
            json={"inputs": {}},
            headers=API_KEY_HEADER,
        )
    assert resp.status_code == 500
    assert isinstance(resp.json()["detail"], str) and len(resp.json()["detail"]) > 0


# ---------------------------------------------------------------------------
# GET /executions
# ---------------------------------------------------------------------------


async def test_list_executions_empty(client: AsyncClient):
    """GET /executions on empty database returns empty list."""
    with patch(
        "blackbeard.api.executions._executor_mod.list_executions",
        new_callable=AsyncMock,
        return_value=([], 0),
    ):
        resp = await client.get("/api/v1/executions", headers=API_KEY_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


async def test_list_executions_with_items(client: AsyncClient):
    """GET /executions returns execution items."""
    mock_exec = _make_mock_execution()

    with patch(
        "blackbeard.api.executions._executor_mod.list_executions",
        new_callable=AsyncMock,
        return_value=([mock_exec], 1),
    ):
        resp = await client.get("/api/v1/executions", headers=API_KEY_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["crew_name"] == "test-crew"


async def test_list_executions_filter_by_crew_name(client: AsyncClient):
    """GET /executions?crew_name=xxx passes crew_name filter."""
    captured_kwargs = {}

    async def _capture_list(session, **kwargs):
        captured_kwargs.update(kwargs)
        return ([], 0)

    with patch(
        "blackbeard.api.executions._executor_mod.list_executions",
        new_callable=AsyncMock,
        side_effect=_capture_list,
    ):
        resp = await client.get("/api/v1/executions?crew_name=my-crew", headers=API_KEY_HEADER)
    assert resp.status_code == 200
    assert captured_kwargs.get("crew_name") == "my-crew"


async def test_list_executions_filter_by_status(client: AsyncClient):
    """GET /executions?status=running passes status filter."""
    captured_kwargs = {}

    async def _capture_list(session, **kwargs):
        captured_kwargs.update(kwargs)
        return ([], 0)

    with patch(
        "blackbeard.api.executions._executor_mod.list_executions",
        new_callable=AsyncMock,
        side_effect=_capture_list,
    ):
        resp = await client.get("/api/v1/executions?status=running", headers=API_KEY_HEADER)
    assert resp.status_code == 200
    assert captured_kwargs["status"].value == "running"


# ---------------------------------------------------------------------------
# GET /executions/{id}
# ---------------------------------------------------------------------------


async def test_get_execution_not_found(client: AsyncClient):
    """GET /executions/{id} for missing execution returns 404."""
    fake_id = str(uuid.uuid4())

    with patch(
        "blackbeard.api.executions._executor_mod.get_execution",
        new_callable=AsyncMock,
        return_value=None,
    ):
        resp = await client.get(f"/api/v1/executions/{fake_id}", headers=API_KEY_HEADER)
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


async def test_get_execution_success(client: AsyncClient):
    """GET /executions/{id} for existing execution returns 200."""
    mock_exec = _make_mock_execution()
    exec_id = str(mock_exec.id)

    with patch(
        "blackbeard.api.executions._executor_mod.get_execution",
        new_callable=AsyncMock,
        return_value=mock_exec,
    ):
        resp = await client.get(f"/api/v1/executions/{exec_id}", headers=API_KEY_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == exec_id
    assert data["crew_name"] == "test-crew"
    assert data["status"] == "queued"


# ---------------------------------------------------------------------------
# GET /executions/{id}/events
# ---------------------------------------------------------------------------


async def test_list_execution_events_not_found(client: AsyncClient):
    """GET /executions/{id}/events for missing execution returns 404."""
    fake_id = str(uuid.uuid4())

    with patch(
        "blackbeard.api.executions._executor_mod.get_execution_status",
        new_callable=AsyncMock,
        return_value=None,
    ):
        resp = await client.get(f"/api/v1/executions/{fake_id}/events", headers=API_KEY_HEADER)
    assert resp.status_code == 404
    assert "detail" in resp.json()


async def test_list_execution_events_empty(client: AsyncClient):
    """GET /executions/{id}/events returns empty list when no events."""
    from blackbeard.models.execution import ExecutionStatus

    fake_id = str(uuid.uuid4())

    with (
        patch(
            "blackbeard.api.executions._executor_mod.get_execution_status",
            new_callable=AsyncMock,
            return_value=ExecutionStatus.RUNNING,
        ),
        patch(
            "blackbeard.api.executions._executor_mod.list_execution_events",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        resp = await client.get(f"/api/v1/executions/{fake_id}/events", headers=API_KEY_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["events"] == []
    assert data["has_more"] is False


async def test_list_execution_events_with_events(client: AsyncClient):
    """GET /executions/{id}/events returns events when present."""
    from blackbeard.models.execution import ExecutionEvent, ExecutionStatus

    fake_id = uuid.uuid4()

    mock_event = ExecutionEvent()
    mock_event.id = uuid.uuid4()
    mock_event.execution_id = fake_id
    mock_event.sequence = 0
    mock_event.event_type = "task_started"
    mock_event.timestamp = datetime.now(UTC)
    mock_event.data = {"task": "gather-data"}

    with (
        patch(
            "blackbeard.api.executions._executor_mod.get_execution_status",
            new_callable=AsyncMock,
            return_value=ExecutionStatus.RUNNING,
        ),
        patch(
            "blackbeard.api.executions._executor_mod.list_execution_events",
            new_callable=AsyncMock,
            return_value=[mock_event],
        ),
    ):
        resp = await client.get(f"/api/v1/executions/{fake_id}/events", headers=API_KEY_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["events"]) == 1
    assert data["events"][0]["event_type"] == "task_started"
    assert data["events"][0]["sequence"] == 0


# ---------------------------------------------------------------------------
# PATCH /executions/{id}/cancel
# ---------------------------------------------------------------------------


async def test_cancel_execution_success(client: AsyncClient):
    """PATCH /executions/{id}/cancel for running execution returns 200."""
    mock_exec = _make_mock_execution(status="cancelled")
    exec_id = str(mock_exec.id)

    with patch(
        "blackbeard.api.executions._executor_mod.cancel_execution",
        new_callable=AsyncMock,
        return_value=mock_exec,
    ):
        resp = await client.patch(f"/api/v1/executions/{exec_id}/cancel", headers=API_KEY_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "cancelled"


async def test_cancel_execution_not_found(client: AsyncClient):
    """PATCH /executions/{id}/cancel for missing execution returns 404."""
    from blackbeard.engine import ExecutionNotFoundError

    fake_id = str(uuid.uuid4())

    with patch(
        "blackbeard.api.executions._executor_mod.cancel_execution",
        new_callable=AsyncMock,
        side_effect=ExecutionNotFoundError(f"Execution '{fake_id}' not found"),
    ):
        resp = await client.patch(f"/api/v1/executions/{fake_id}/cancel", headers=API_KEY_HEADER)
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


async def test_cancel_execution_already_terminal(client: AsyncClient):
    """PATCH /executions/{id}/cancel for completed execution returns 409."""
    from blackbeard.engine import ExecutionError

    fake_id = str(uuid.uuid4())

    with patch(
        "blackbeard.api.executions._executor_mod.cancel_execution",
        new_callable=AsyncMock,
        side_effect=ExecutionError("Cannot cancel execution in terminal status 'completed'"),
    ):
        resp = await client.patch(f"/api/v1/executions/{fake_id}/cancel", headers=API_KEY_HEADER)
    assert resp.status_code == 409
    assert isinstance(resp.json()["detail"], str) and len(resp.json()["detail"]) > 0


async def test_cancel_execution_returns_none(client: AsyncClient):
    """PATCH /executions/{id}/cancel returning None means 404."""
    fake_id = str(uuid.uuid4())

    with patch(
        "blackbeard.api.executions._executor_mod.cancel_execution",
        new_callable=AsyncMock,
        return_value=None,
    ):
        resp = await client.patch(f"/api/v1/executions/{fake_id}/cancel", headers=API_KEY_HEADER)
    assert resp.status_code == 404
    assert "detail" in resp.json()


# ---------------------------------------------------------------------------
# POST /executions/{id}/respond (HITL)
# ---------------------------------------------------------------------------


async def test_hitl_respond_success(client: AsyncClient):
    """POST /executions/{id}/respond records response for running execution."""
    from blackbeard.models.execution import ExecutionStatus

    fake_id = str(uuid.uuid4())

    with (
        patch(
            "blackbeard.api.executions._executor_mod.get_execution_status",
            new_callable=AsyncMock,
            return_value=ExecutionStatus.RUNNING,
        ),
        patch(
            "blackbeard.api.executions._executor_mod.record_hitl_response",
            new_callable=AsyncMock,
        ),
    ):
        resp = await client.post(
            f"/api/v1/executions/{fake_id}/respond",
            json={"response": "approved"},
            headers=API_KEY_HEADER,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "recorded"


async def test_hitl_respond_not_found(client: AsyncClient):
    """POST /executions/{id}/respond for missing execution returns 404."""
    fake_id = str(uuid.uuid4())

    with patch(
        "blackbeard.api.executions._executor_mod.get_execution_status",
        new_callable=AsyncMock,
        return_value=None,
    ):
        resp = await client.post(
            f"/api/v1/executions/{fake_id}/respond",
            json={"response": "approved"},
            headers=API_KEY_HEADER,
        )
    assert resp.status_code == 404
    assert isinstance(resp.json()["detail"], str) and len(resp.json()["detail"]) > 0


async def test_hitl_respond_terminal_status(client: AsyncClient):
    """POST /executions/{id}/respond for completed execution returns 409."""
    from blackbeard.models.execution import ExecutionStatus

    fake_id = str(uuid.uuid4())

    with patch(
        "blackbeard.api.executions._executor_mod.get_execution_status",
        new_callable=AsyncMock,
        return_value=ExecutionStatus.COMPLETED,
    ):
        resp = await client.post(
            f"/api/v1/executions/{fake_id}/respond",
            json={"response": "too late"},
            headers=API_KEY_HEADER,
        )
    assert resp.status_code == 409
    assert isinstance(resp.json()["detail"], str) and len(resp.json()["detail"]) > 0


# ---------------------------------------------------------------------------
# POST /executions/{id}/retry
# ---------------------------------------------------------------------------


async def test_retry_kickoff_success(client: AsyncClient):
    """POST /executions/{id}/retry for a failed kickoff creates a new queued execution."""
    original = _make_mock_execution(status="failed", execution_type="kickoff")
    original.inputs = {"topic": "AI"}
    new_exec = _make_mock_execution(status="queued")

    with (
        patch(
            "blackbeard.api.executions._executor_mod.get_execution",
            new_callable=AsyncMock,
            return_value=original,
        ),
        patch(
            "blackbeard.api.executions._executor_mod.kickoff",
            new_callable=AsyncMock,
            return_value=new_exec,
        ) as mock_kickoff,
    ):
        resp = await client.post(f"/api/v1/executions/{original.id}/retry", headers=API_KEY_HEADER)

    assert resp.status_code == 202
    data = resp.json()
    assert data["id"] == str(new_exec.id)
    assert data["status"] == "queued"
    assert resp.headers["location"] == f"/api/v1/executions/{new_exec.id}"
    mock_kickoff.assert_awaited_once()
    call_args = mock_kickoff.await_args
    assert call_args.args[1] == "test-crew"
    assert call_args.args[2] == {"topic": "AI"}
    assert call_args.args[3] == "default"


async def test_retry_not_found(client: AsyncClient):
    """POST /executions/{id}/retry for missing execution returns 404."""
    fake_id = str(uuid.uuid4())

    with patch(
        "blackbeard.api.executions._executor_mod.get_execution",
        new_callable=AsyncMock,
        return_value=None,
    ):
        resp = await client.post(f"/api/v1/executions/{fake_id}/retry", headers=API_KEY_HEADER)

    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


async def test_retry_non_terminal_rejected(client: AsyncClient):
    """POST /executions/{id}/retry for a running execution returns 409 without re-running."""
    running = _make_mock_execution(status="running")

    with (
        patch(
            "blackbeard.api.executions._executor_mod.get_execution",
            new_callable=AsyncMock,
            return_value=running,
        ),
        patch(
            "blackbeard.api.executions._executor_mod.kickoff", new_callable=AsyncMock
        ) as mock_kickoff,
    ):
        resp = await client.post(f"/api/v1/executions/{running.id}/retry", headers=API_KEY_HEADER)

    assert resp.status_code == 409
    assert "terminal" in resp.json()["detail"].lower()
    mock_kickoff.assert_not_awaited()


async def test_retry_rejects_redacted_inputs(client: AsyncClient):
    """POST /executions/{id}/retry refuses to re-run with redacted placeholder inputs."""
    failed = _make_mock_execution(status="failed")
    failed.inputs = {"api_token": "[REDACTED]"}

    with (
        patch(
            "blackbeard.api.executions._executor_mod.get_execution",
            new_callable=AsyncMock,
            return_value=failed,
        ),
        patch(
            "blackbeard.api.executions._executor_mod.kickoff", new_callable=AsyncMock
        ) as mock_kickoff,
    ):
        resp = await client.post(f"/api/v1/executions/{failed.id}/retry", headers=API_KEY_HEADER)

    assert resp.status_code == 409
    assert "redact" in resp.json()["detail"].lower()
    mock_kickoff.assert_not_awaited()


@pytest.mark.parametrize(
    ("exec_type", "executor_attr"),
    [
        ("kickoff", "kickoff"),
        ("flow", "run_flow"),
        ("train", "train_crew"),
        ("test", "test_crew"),
    ],
)
async def test_retry_dispatches_by_execution_type(client: AsyncClient, exec_type, executor_attr):
    """Retry dispatches to the executor function matching the original execution type."""
    original = _make_mock_execution(status="completed", execution_type=exec_type)
    new_exec = _make_mock_execution(status="queued")

    all_entry_points = ["kickoff", "run_flow", "train_crew", "test_crew"]
    patches = {
        name: patch(
            f"blackbeard.api.executions._executor_mod.{name}",
            new_callable=AsyncMock,
        )
        for name in all_entry_points
    }

    with (
        patch(
            "blackbeard.api.executions._executor_mod.get_execution",
            new_callable=AsyncMock,
            return_value=original,
        ) as mock_get,
        contextlib.ExitStack() as stack,
    ):
        mocks = {name: stack.enter_context(p) for name, p in patches.items()}
        mocks[executor_attr].return_value = new_exec
        resp = await client.post(f"/api/v1/executions/{original.id}/retry", headers=API_KEY_HEADER)

    assert resp.status_code == 202, f"{exec_type}: {resp.status_code} {resp.text}"
    assert resp.headers["location"] == f"/api/v1/executions/{new_exec.id}"
    mock_get.assert_awaited_once()
    for name, mock_fn in mocks.items():
        if name == executor_attr:
            mock_fn.assert_awaited_once()
        else:
            mock_fn.assert_not_awaited()


async def test_retry_train_passes_iterations_and_file(client: AsyncClient):
    """Retrying a train execution preserves n_iterations and training file."""
    original = _make_mock_execution(status="failed", execution_type="train")
    original.n_iterations = 7
    original.training_file = "custom.pkl"

    with (
        patch(
            "blackbeard.api.executions._executor_mod.get_execution",
            new_callable=AsyncMock,
            return_value=original,
        ),
        patch(
            "blackbeard.api.executions._executor_mod.train_crew",
            new_callable=AsyncMock,
            return_value=_make_mock_execution(status="queued"),
        ) as mock_train,
    ):
        resp = await client.post(f"/api/v1/executions/{original.id}/retry", headers=API_KEY_HEADER)

    assert resp.status_code == 202
    kwargs = mock_train.await_args.kwargs
    assert kwargs["n_iterations"] == 7
    assert kwargs["filename"] == "custom.pkl"


# ---------------------------------------------------------------------------
# GET /executions/{id}/spend
# ---------------------------------------------------------------------------


async def test_execution_spend_not_found(client: AsyncClient):
    """GET /executions/{id}/spend for missing execution returns 404."""
    fake_id = str(uuid.uuid4())

    with patch(
        "blackbeard.api.executions._executor_mod.get_execution_status",
        new_callable=AsyncMock,
        return_value=None,
    ):
        resp = await client.get(f"/api/v1/executions/{fake_id}/spend", headers=API_KEY_HEADER)
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# GET /executions/{id}/stream (SSE)
# ---------------------------------------------------------------------------


async def test_stream_execution_not_found(client: AsyncClient):
    """GET /executions/{id}/stream for missing execution returns 404."""
    fake_id = str(uuid.uuid4())

    # The stream endpoint uses async_session() directly, not the injected session.
    # We must patch _executor_mod.get_execution_status at the module level.
    with (
        patch(
            "blackbeard.api.executions._executor_mod.get_execution_status",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "blackbeard.api.executions.async_session",
        ) as mock_session_ctx,
    ):
        # Make the async context manager return a session that delegates to our mock
        mock_session = AsyncMock()
        mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = await client.get(f"/api/v1/executions/{fake_id}/stream", headers=API_KEY_HEADER)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Kickoff location header
# ---------------------------------------------------------------------------


async def test_kickoff_sets_location_header(client: AsyncClient):
    """POST /crews/{name}/kickoff response includes Location header."""
    mock_exec = _make_mock_execution()

    with patch(
        "blackbeard.api.executions._executor_mod.kickoff",
        new_callable=AsyncMock,
        return_value=mock_exec,
    ):
        resp = await client.post(
            "/api/v1/crews/test-crew/kickoff",
            json={"inputs": {}},
            headers=API_KEY_HEADER,
        )
    assert resp.status_code == 202
    assert f"/api/v1/executions/{mock_exec.id}" in resp.headers.get("location", "")


# ---------------------------------------------------------------------------
# Input validation on kickoff
# ---------------------------------------------------------------------------


async def test_kickoff_rejects_invalid_input_key(client: AsyncClient):
    """POST /crews/{name}/kickoff rejects input keys with special chars."""
    resp = await client.post(
        "/api/v1/crews/test-crew/kickoff",
        json={"inputs": {"invalid-key!": "value"}},
        headers=API_KEY_HEADER,
    )
    assert resp.status_code == 422


async def test_train_rejects_bad_filename(client: AsyncClient):
    """POST /crews/{name}/train rejects filename with path traversal."""
    resp = await client.post(
        "/api/v1/crews/test-crew/train",
        json={"inputs": {}, "n_iterations": 3, "filename": "../etc/passwd"},
        headers=API_KEY_HEADER,
    )
    assert resp.status_code == 422


async def test_train_rejects_non_pkl_filename(client: AsyncClient):
    """POST /crews/{name}/train rejects non-.pkl filename."""
    resp = await client.post(
        "/api/v1/crews/test-crew/train",
        json={"inputs": {}, "n_iterations": 3, "filename": "data.json"},
        headers=API_KEY_HEADER,
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# _poll_execution: shared SSE/WS polling loop
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def _patch_poll_loop():
    """Patch async_session and poll backoff so _poll_execution runs instantly.

    Yields (mock_session, mock_ctx) where mock_ctx is the patched
    async_session context manager; executor functions stay unpatched.
    """
    mock_session = AsyncMock()
    with (
        patch("blackbeard.api.executions.async_session") as mock_session_ctx,
        patch("blackbeard.api.executions._poll_backoff", return_value=0),
    ):
        mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
        yield mock_session, mock_session_ctx


async def _collect(execution_id):
    from blackbeard.api.executions import _poll_execution

    return [ev async for ev in _poll_execution(execution_id)]


async def test_poll_execution_not_found_yields_error():
    """Unknown execution id yields a single error event and stops."""
    exec_id = uuid.uuid4()

    with (
        _patch_poll_loop(),
        patch(
            "blackbeard.api.executions._executor_mod.get_execution",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        events = await _collect(exec_id)

    assert len(events) == 1
    assert events[0].kind == "error"
    assert "not found" in str(events[0].data["detail"])


async def test_poll_execution_terminal_immediately():
    """Already-terminal execution: one status event, no heartbeat, no timeout."""
    from blackbeard.models.execution import ExecutionStatus  # noqa: F401

    completed = _make_mock_execution(status="completed")
    exec_id = completed.id

    with (
        _patch_poll_loop(),
        patch(
            "blackbeard.api.executions._executor_mod.get_execution",
            new_callable=AsyncMock,
            return_value=completed,
        ) as mock_get,
        patch(
            "blackbeard.api.executions._executor_mod.get_execution_status",
            new_callable=AsyncMock,
        ),
        patch(
            "blackbeard.api.executions._executor_mod.list_execution_events",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        events = await _collect(exec_id)

    kinds = [ev.kind for ev in events]
    assert kinds == ["status"]
    assert events[0].data["status"] == "completed"
    # First poll loads the full execution directly; status polling never runs.
    mock_get.assert_awaited_once()


async def test_poll_execution_heartbeats_then_final_status():
    """Running execution yields heartbeats between polls and a final status on completion."""
    from blackbeard.models.execution import ExecutionStatus

    running = _make_mock_execution(status="running")
    completed = _make_mock_execution(status="completed")
    exec_id = running.id

    with (
        _patch_poll_loop(),
        patch(
            "blackbeard.api.executions._executor_mod.get_execution",
            new_callable=AsyncMock,
            side_effect=[running, completed],
        ) as mock_get,
        patch(
            "blackbeard.api.executions._executor_mod.get_execution_status",
            new_callable=AsyncMock,
            side_effect=[ExecutionStatus.RUNNING, ExecutionStatus.COMPLETED],
        ) as mock_status,
        patch(
            "blackbeard.api.executions._executor_mod.list_execution_events",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        events = await _collect(exec_id)

    assert [ev.kind for ev in events] == ["status", "heartbeat", "status"]
    assert events[0].data["status"] == "running"
    assert events[-1].data["status"] == "completed"
    # Heartbeat payload mirrors the unchanged status.
    assert events[1].data == {"status": "running"}
    assert mock_status.await_count == 2
    assert mock_get.await_count == 2


async def test_poll_execution_streams_new_events_with_sequence_cursor():
    """New events are forwarded and the next fetch resumes after the last sequence."""
    completed = _make_mock_execution(status="completed")
    exec_id = completed.id

    ev1 = SimpleNamespace(
        sequence=5, timestamp=datetime.now(UTC), event_type="task_started", data={"step": 1}
    )
    ev2 = SimpleNamespace(
        sequence=6, timestamp=datetime.now(UTC), event_type="task_output", data={"line": "x"}
    )

    with (
        _patch_poll_loop(),
        patch(
            "blackbeard.api.executions._executor_mod.get_execution",
            new_callable=AsyncMock,
            return_value=completed,
        ),
        patch(
            "blackbeard.api.executions._executor_mod.get_execution_status",
            new_callable=AsyncMock,
        ),
        patch(
            "blackbeard.api.executions._executor_mod.list_execution_events",
            new_callable=AsyncMock,
            return_value=[ev1, ev2],
        ) as mock_list,
    ):
        events = await _collect(exec_id)

    event_items = [ev for ev in events if ev.kind == "event"]
    assert [ev.event_type for ev in event_items] == ["task_started", "task_output"]
    assert event_items[0].data["sequence"] == 5
    assert event_items[1].data["sequence"] == 6
    assert isinstance(event_items[0].data["timestamp"], str)
    # Cursor starts before the first event.
    assert mock_list.await_args_list[0].kwargs["after"] == -1


async def test_poll_execution_times_out_when_still_running(monkeypatch):
    """Exhausting the poll budget yields a final timeout error event."""
    from blackbeard.models.execution import ExecutionStatus

    monkeypatch.setattr("blackbeard.api.executions._MAX_STREAM_POLLS", 3)

    running = _make_mock_execution(status="running")
    exec_id = running.id

    with (
        _patch_poll_loop(),
        patch(
            "blackbeard.api.executions._executor_mod.get_execution",
            new_callable=AsyncMock,
            return_value=running,
        ) as mock_get,
        patch(
            "blackbeard.api.executions._executor_mod.get_execution_status",
            new_callable=AsyncMock,
            return_value=ExecutionStatus.RUNNING,
        ),
        patch(
            "blackbeard.api.executions._executor_mod.list_execution_events",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        events = await _collect(exec_id)

    assert mock_get.await_count == 1  # only the initial load re-fetches full row
    assert events[0].kind == "status"
    assert events[-1].kind == "timeout"
    assert "timeout" in str(events[-1].data["detail"]).lower()


async def test_poll_execution_disappearing_execution_yields_error():
    """Execution deleted mid-stream yields an error instead of looping forever."""
    running = _make_mock_execution(status="running")
    exec_id = running.id

    with (
        _patch_poll_loop(),
        patch(
            "blackbeard.api.executions._executor_mod.get_execution",
            new_callable=AsyncMock,
            return_value=running,
        ),
        patch(
            "blackbeard.api.executions._executor_mod.get_execution_status",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "blackbeard.api.executions._executor_mod.list_execution_events",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        events = await _collect(exec_id)

    assert events[0].kind == "status"
    assert events[-1].kind == "error"
    assert "not found" in str(events[-1].data["detail"])


async def test_poll_execution_redacts_sensitive_event_data():
    """Event payloads forwarded to SSE/WS clients have sensitive values scrubbed."""
    completed = _make_mock_execution(status="completed")
    exec_id = completed.id

    ev = SimpleNamespace(
        sequence=0,
        timestamp=datetime.now(UTC),
        event_type="task_output",
        data={"line": "step done", "password": "hunter2"},
    )

    with (
        _patch_poll_loop(),
        patch(
            "blackbeard.api.executions._executor_mod.get_execution",
            new_callable=AsyncMock,
            return_value=completed,
        ),
        patch(
            "blackbeard.api.executions._executor_mod.get_execution_status",
            new_callable=AsyncMock,
        ),
        patch(
            "blackbeard.api.executions._executor_mod.list_execution_events",
            new_callable=AsyncMock,
            return_value=[ev],
        ),
    ):
        events = await _collect(exec_id)

    payload = events[-1].data
    assert payload["line"] == "step done"
    assert payload["password"] == "[REDACTED]"
    assert "hunter2" not in json.dumps(payload)
