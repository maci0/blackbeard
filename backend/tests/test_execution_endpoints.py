"""Integration tests for the execution API endpoints (api/executions.py).

Covers crew kickoff, train, test, flow endpoints, execution listing,
detail retrieval, event listing, cancellation, and SSE streaming.

All executor functions are mocked to avoid running real CrewAI — the
executor unit tests already cover that layer.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

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
        "metadata": {"name": name, "namespace": "default"},
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
        "metadata": {"name": name, "namespace": "default"},
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
    namespace: str = "default",
) -> object:
    """Build a detached Execution ORM object for mocking executor returns."""
    from blackbeard.models.execution import Execution, ExecutionStatus, ExecutionType

    e = Execution()
    e.id = uuid.uuid4()
    e.crew_name = crew_name
    e.crew_namespace = namespace
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

    async def _capture_kickoff(session, crew_name, inputs, namespace, user=None):
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
    assert captured_kwargs.get("status") is not None
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
