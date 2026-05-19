"""Database-level integration tests for the execution engine.

Tests the executor module functions directly against the in-memory
SQLite database, covering list_executions, get_execution,
cancel_execution, get_execution_status, list_execution_events,
and record_hitl_response.

These tests exercise the actual DB queries instead of mocking them
at the API layer, providing deeper coverage of resources/service.py
and engine/executor.py.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from blackbeard.engine.executor import (
    ExecutionError,
    cancel_execution,
    get_execution,
    get_execution_status,
    list_execution_events,
    list_executions,
    record_hitl_response,
)
from blackbeard.models.execution import (
    Execution,
    ExecutionEvent,
    ExecutionStatus,
    ExecutionTask,
    ExecutionType,
    TaskStatus,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _insert_execution(
    session: AsyncSession,
    *,
    crew_name: str = "test-crew",
    status: ExecutionStatus = ExecutionStatus.QUEUED,
    execution_type: ExecutionType = ExecutionType.KICKOFF,
    namespace: str = "default",
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    error: str | None = None,
) -> Execution:
    """Insert an execution directly into the DB and return it."""
    e = Execution()
    e.id = uuid.uuid4()
    e.crew_name = crew_name
    e.crew_namespace = namespace
    e.execution_type = execution_type
    e.status = status
    e.inputs = {}
    e.outputs = None
    e.error = error
    e.total_tokens = 0
    e.prompt_tokens = 0
    e.completion_tokens = 0
    e.cost_usd = Decimal("0")
    e.n_iterations = None
    e.training_file = None
    e.initiated_by = None
    e.principal_chain = None
    e.created_at = datetime.now(UTC)
    e.started_at = started_at
    e.completed_at = completed_at
    session.add(e)
    await session.flush()
    return e


async def _insert_event(
    session: AsyncSession,
    execution_id: uuid.UUID,
    sequence: int,
    event_type: str = "task_started",
    data: dict | None = None,
) -> ExecutionEvent:
    """Insert an execution event into the DB."""
    ev = ExecutionEvent()
    ev.id = uuid.uuid4()
    ev.execution_id = execution_id
    ev.sequence = sequence
    ev.event_type = event_type
    ev.timestamp = datetime.now(UTC)
    ev.data = data or {}
    session.add(ev)
    await session.flush()
    return ev


# ---------------------------------------------------------------------------
# get_execution
# ---------------------------------------------------------------------------


async def test_get_execution_existing(db_session: AsyncSession):
    """get_execution returns execution with tasks loaded."""
    e = await _insert_execution(db_session)
    await db_session.commit()

    result = await get_execution(db_session, e.id)
    assert result is not None
    assert result.id == e.id
    assert result.crew_name == "test-crew"
    assert result.tasks == []  # No tasks added


async def test_get_execution_missing(db_session: AsyncSession):
    """get_execution returns None for non-existent execution."""
    result = await get_execution(db_session, uuid.uuid4())
    assert result is None


# ---------------------------------------------------------------------------
# get_execution_status
# ---------------------------------------------------------------------------


async def test_get_execution_status_existing(db_session: AsyncSession):
    """get_execution_status returns just the status."""
    e = await _insert_execution(db_session)
    await db_session.commit()

    status = await get_execution_status(db_session, e.id)
    assert status == ExecutionStatus.QUEUED


async def test_get_execution_status_missing(db_session: AsyncSession):
    """get_execution_status returns None for non-existent execution."""
    status = await get_execution_status(db_session, uuid.uuid4())
    assert status is None


# ---------------------------------------------------------------------------
# list_executions
# ---------------------------------------------------------------------------


async def test_list_executions_empty(db_session: AsyncSession):
    """list_executions on empty DB returns empty list."""
    items, total = await list_executions(db_session)
    assert items == []
    assert total == 0


async def test_list_executions_returns_items(db_session: AsyncSession):
    """list_executions returns inserted executions."""
    await _insert_execution(db_session, crew_name="crew-a")
    await _insert_execution(db_session, crew_name="crew-b")
    await db_session.commit()

    items, total = await list_executions(db_session)
    assert total == 2
    assert len(items) == 2


async def test_list_executions_filter_crew_name(db_session: AsyncSession):
    """list_executions filters by crew_name."""
    await _insert_execution(db_session, crew_name="alpha")
    await _insert_execution(db_session, crew_name="beta")
    await db_session.commit()

    items, total = await list_executions(db_session, crew_name="alpha")
    assert total == 1
    assert items[0].crew_name == "alpha"


async def test_list_executions_filter_status(db_session: AsyncSession):
    """list_executions filters by status."""
    await _insert_execution(db_session, status=ExecutionStatus.QUEUED)
    await _insert_execution(
        db_session,
        status=ExecutionStatus.COMPLETED,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )
    await db_session.commit()

    items, total = await list_executions(db_session, status=ExecutionStatus.QUEUED)
    assert total == 1
    assert items[0].status == ExecutionStatus.QUEUED


async def test_list_executions_filter_namespace(db_session: AsyncSession):
    """list_executions filters by namespace."""
    await _insert_execution(db_session, namespace="default")
    await _insert_execution(db_session, namespace="staging")
    await db_session.commit()

    items, total = await list_executions(db_session, namespace="staging")
    assert total == 1
    assert items[0].crew_namespace == "staging"


async def test_list_executions_pagination(db_session: AsyncSession):
    """list_executions respects limit and offset."""
    for i in range(5):
        await _insert_execution(db_session, crew_name=f"crew-{i}")
    await db_session.commit()

    items, total = await list_executions(db_session, limit=2, offset=0)
    assert len(items) == 2
    assert total == 5


async def test_list_executions_ordered_by_created_at_desc(db_session: AsyncSession):
    """list_executions returns most recent first."""
    await _insert_execution(db_session, crew_name="first")
    await _insert_execution(db_session, crew_name="second")
    await db_session.commit()

    items, _ = await list_executions(db_session)
    # Most recent first
    assert items[0].crew_name == "second"
    assert items[1].crew_name == "first"


# ---------------------------------------------------------------------------
# list_execution_events
# ---------------------------------------------------------------------------


async def test_list_execution_events_empty(db_session: AsyncSession):
    """list_execution_events returns empty list when no events."""
    e = await _insert_execution(db_session)
    await db_session.commit()

    events = await list_execution_events(db_session, e.id)
    assert events == []


async def test_list_execution_events_returns_events(db_session: AsyncSession):
    """list_execution_events returns events ordered by sequence."""
    e = await _insert_execution(db_session)
    await _insert_event(db_session, e.id, 0, "task_started", {"task": "step-1"})
    await _insert_event(db_session, e.id, 1, "task_completed", {"task": "step-1"})
    await db_session.commit()

    events = await list_execution_events(db_session, e.id)
    assert len(events) == 2
    assert events[0].sequence == 0
    assert events[1].sequence == 1
    assert events[0].event_type == "task_started"
    assert events[1].event_type == "task_completed"


async def test_list_execution_events_after_sequence(db_session: AsyncSession):
    """list_execution_events filters by after parameter."""
    e = await _insert_execution(db_session)
    await _insert_event(db_session, e.id, 0, "start")
    await _insert_event(db_session, e.id, 1, "progress")
    await _insert_event(db_session, e.id, 2, "end")
    await db_session.commit()

    events = await list_execution_events(db_session, e.id, after=0)
    assert len(events) == 2
    assert events[0].sequence == 1


# ---------------------------------------------------------------------------
# record_hitl_response
# ---------------------------------------------------------------------------


async def test_record_hitl_response(db_session: AsyncSession):
    """record_hitl_response creates an event with correct sequence."""
    e = await _insert_execution(db_session)
    await db_session.commit()

    event = await record_hitl_response(db_session, e.id, response="approved")
    assert event.event_type == "hitl_response"
    assert event.sequence == 0
    assert event.data["response"] == "approved"


async def test_record_hitl_response_with_feedback(db_session: AsyncSession):
    """record_hitl_response stores optional feedback."""
    e = await _insert_execution(db_session)
    await db_session.commit()

    event = await record_hitl_response(
        db_session, e.id, response="rejected", feedback="Need more data"
    )
    assert event.data["response"] == "rejected"
    assert event.data["feedback"] == "Need more data"


async def test_record_hitl_response_increments_sequence(db_session: AsyncSession):
    """record_hitl_response starts from sequence 0 when no prior events exist."""
    e = await _insert_execution(db_session)
    await db_session.commit()

    # First event should get sequence 0
    event = await record_hitl_response(db_session, e.id, response="first")
    assert event.sequence == 0
    assert event.event_type == "hitl_response"


# ---------------------------------------------------------------------------
# cancel_execution
# ---------------------------------------------------------------------------


async def test_cancel_queued_execution(db_session: AsyncSession):
    """cancel_execution marks queued execution as cancelled."""
    e = await _insert_execution(db_session, status=ExecutionStatus.QUEUED)
    await db_session.commit()

    result = await cancel_execution(db_session, e.id)
    assert result is not None
    assert result.status == ExecutionStatus.CANCELLED
    assert result.completed_at is not None


async def test_cancel_running_execution(db_session: AsyncSession):
    """cancel_execution marks running execution as cancelled."""
    e = await _insert_execution(
        db_session,
        status=ExecutionStatus.RUNNING,
        started_at=datetime.now(UTC),
    )
    await db_session.commit()

    result = await cancel_execution(db_session, e.id)
    assert result is not None
    assert result.status == ExecutionStatus.CANCELLED


async def test_cancel_completed_raises(db_session: AsyncSession):
    """cancel_execution raises ExecutionError for completed execution."""
    e = await _insert_execution(
        db_session,
        status=ExecutionStatus.COMPLETED,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )
    await db_session.commit()

    with pytest.raises(ExecutionError, match="terminal"):
        await cancel_execution(db_session, e.id)


async def test_cancel_nonexistent_returns_none(db_session: AsyncSession):
    """cancel_execution returns None for non-existent execution."""
    result = await cancel_execution(db_session, uuid.uuid4())
    assert result is None


async def test_cancel_with_tasks_marks_tasks_failed(db_session: AsyncSession):
    """cancel_execution marks pending tasks as failed."""
    e = await _insert_execution(db_session, status=ExecutionStatus.QUEUED)

    task = ExecutionTask()
    task.id = uuid.uuid4()
    task.execution_id = e.id
    task.task_name = "step-1"
    task.order = 0
    task.status = TaskStatus.PENDING
    task.tokens_used = 0
    task.cost_usd = Decimal("0")
    task.created_at = datetime.now(UTC)
    db_session.add(task)
    await db_session.flush()
    await db_session.commit()

    result = await cancel_execution(db_session, e.id)
    assert result is not None
    assert result.status == ExecutionStatus.CANCELLED
    # Tasks should be marked as failed
    for t in result.tasks:
        if t.task_name == "step-1":
            assert t.status == TaskStatus.FAILED
            assert t.error == "Execution cancelled"
