"""Tests for HITL (Human-in-the-Loop) response endpoint.

Covers:
  - HITL response creates event with correct type
  - HITL response on completed execution returns 409
  - HITL response on missing execution returns 404
  - HITL response with feedback field
  - HITL response validation (empty/too-long)
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from tests.conftest import API_KEY_HEADER

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_crew_and_kickoff(client: AsyncClient) -> str:
    """Create resources, kick off, and return execution ID."""
    from tests.test_executor import _create_full_crew

    await _create_full_crew(client)
    response = await client.post(
        "/api/v1/crews/test-crew/kickoff",
        json={"inputs": {}},
        headers=API_KEY_HEADER,
    )
    assert response.status_code == 202
    return response.json()["id"]


# ---------------------------------------------------------------------------
# Tests -- HITL respond endpoint
# ---------------------------------------------------------------------------


async def test_hitl_response_creates_event(client: AsyncClient):
    """POST /executions/{id}/respond should create an hitl_response event."""
    exec_id = await _create_crew_and_kickoff(client)

    response = await client.post(
        f"/api/v1/executions/{exec_id}/respond",
        json={"response": "approved"},
        headers=API_KEY_HEADER,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "recorded"
    assert data["execution_id"] == exec_id

    # Verify the event was created by querying the events endpoint
    events_resp = await client.get(
        f"/api/v1/executions/{exec_id}/events",
        headers=API_KEY_HEADER,
    )
    assert events_resp.status_code == 200
    events = events_resp.json()["events"]
    hitl_events = [e for e in events if e["event_type"] == "hitl_response"]
    assert len(hitl_events) == 1
    assert hitl_events[0]["data"]["response"] == "approved"
    assert hitl_events[0]["sequence"] >= 0


async def test_hitl_response_with_feedback(client: AsyncClient):
    """HITL response with optional feedback field should include it in event data."""
    exec_id = await _create_crew_and_kickoff(client)

    response = await client.post(
        f"/api/v1/executions/{exec_id}/respond",
        json={
            "response": "rejected",
            "feedback": "Please include more details about the methodology.",
        },
        headers=API_KEY_HEADER,
    )
    assert response.status_code == 200

    # Verify feedback is stored in the event
    events_resp = await client.get(
        f"/api/v1/executions/{exec_id}/events",
        headers=API_KEY_HEADER,
    )
    events = events_resp.json()["events"]
    hitl_events = [e for e in events if e["event_type"] == "hitl_response"]
    assert len(hitl_events) == 1
    assert hitl_events[0]["data"]["response"] == "rejected"
    assert hitl_events[0]["data"]["feedback"] == "Please include more details about the methodology."


async def test_hitl_response_on_cancelled_execution_returns_409(client: AsyncClient):
    """HITL response on a cancelled (terminal) execution should return 409."""
    exec_id = await _create_crew_and_kickoff(client)

    # Cancel the execution first
    cancel_resp = await client.patch(
        f"/api/v1/executions/{exec_id}/cancel",
        headers=API_KEY_HEADER,
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"

    # Try to respond
    response = await client.post(
        f"/api/v1/executions/{exec_id}/respond",
        json={"response": "approved"},
        headers=API_KEY_HEADER,
    )
    assert response.status_code == 409
    assert "terminal" in response.json()["detail"].lower()


async def test_hitl_response_on_missing_execution_returns_404(client: AsyncClient):
    """HITL response on non-existent execution should return 404."""
    fake_id = str(uuid.uuid4())

    response = await client.post(
        f"/api/v1/executions/{fake_id}/respond",
        json={"response": "approved"},
        headers=API_KEY_HEADER,
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


async def test_hitl_response_empty_body_returns_422(client: AsyncClient):
    """HITL response without body should return 422."""
    exec_id = await _create_crew_and_kickoff(client)

    response = await client.post(
        f"/api/v1/executions/{exec_id}/respond",
        content=b"",
        headers={**API_KEY_HEADER, "Content-Type": "application/json"},
    )
    assert response.status_code == 422


async def test_hitl_response_empty_response_field_returns_422(client: AsyncClient):
    """HITL response with empty string response should return 422 (min_length=1)."""
    exec_id = await _create_crew_and_kickoff(client)

    response = await client.post(
        f"/api/v1/executions/{exec_id}/respond",
        json={"response": ""},
        headers=API_KEY_HEADER,
    )
    assert response.status_code == 422


async def test_hitl_response_requires_auth(client: AsyncClient):
    """HITL respond endpoint should require authentication."""
    fake_id = str(uuid.uuid4())

    response = await client.post(
        f"/api/v1/executions/{fake_id}/respond",
        json={"response": "approved"},
    )
    assert response.status_code == 401


async def test_hitl_response_sequence_starts_at_zero(db_session):
    """First HITL response should get sequence=0."""
    from datetime import UTC, datetime

    from blackbeard.engine.executor import record_hitl_response
    from blackbeard.models.execution import Execution, ExecutionStatus

    execution = Execution(
        crew_name="test-crew",
        crew_namespace="default",
        status=ExecutionStatus.RUNNING,
        started_at=datetime.now(UTC),
        inputs={},
    )
    db_session.add(execution)
    await db_session.flush()

    event = await record_hitl_response(db_session, execution.id, response="first response")
    await db_session.commit()

    assert event.sequence == 0
    assert event.data["response"] == "first response"
    assert event.event_type == "hitl_response"


# ---------------------------------------------------------------------------
# Tests -- record_hitl_response unit test
# ---------------------------------------------------------------------------


async def test_record_hitl_response_event_type(db_session):
    """record_hitl_response should create an event with type 'hitl_response'."""
    from datetime import UTC, datetime

    from blackbeard.engine.executor import record_hitl_response
    from blackbeard.models.execution import Execution, ExecutionStatus

    # Create an execution in the DB
    execution = Execution(
        crew_name="test-crew",
        crew_namespace="default",
        status=ExecutionStatus.RUNNING,
        started_at=datetime.now(UTC),
        inputs={},
    )
    db_session.add(execution)
    await db_session.flush()

    event = await record_hitl_response(
        db_session,
        execution.id,
        response="looks good",
        feedback="no changes needed",
    )
    await db_session.commit()

    assert event.event_type == "hitl_response"
    assert event.data["response"] == "looks good"
    assert event.data["feedback"] == "no changes needed"
    assert event.sequence >= 0
    assert event.execution_id == execution.id


async def test_record_hitl_response_without_feedback(db_session):
    """record_hitl_response without feedback should omit it from event data."""
    from datetime import UTC, datetime

    from blackbeard.engine.executor import record_hitl_response
    from blackbeard.models.execution import Execution, ExecutionStatus

    execution = Execution(
        crew_name="test-crew",
        crew_namespace="default",
        status=ExecutionStatus.RUNNING,
        started_at=datetime.now(UTC),
        inputs={},
    )
    db_session.add(execution)
    await db_session.flush()

    event = await record_hitl_response(
        db_session,
        execution.id,
        response="approved",
    )
    await db_session.commit()

    assert event.event_type == "hitl_response"
    assert event.data["response"] == "approved"
    assert "feedback" not in event.data
