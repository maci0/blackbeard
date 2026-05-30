"""Tests for remaining uncovered lines in executor.py and execution_listener.py.

Complements test_engine_functions.py and test_executor_thread.py.
Covers: _get_bg_engine, _load_crew_resources, _submit_execution/kickoff,
train_crew, test_crew, run_flow, get_execution, get_execution_status,
list_executions edge cases, list_execution_events, record_hitl_response,
cancel_execution, _thread_session_factory, plus execution_listener event
handler bodies, PII redaction in _write_event, _write_event_with_task_update,
_get_otel_tracer, _get_cached_webhooks, _otel_start_span, _otel_end_span,
_ensure_request_id, _schedule_flush.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from blackbeard.kinds import ResourceKind
from blackbeard.models import (
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


def _mock_session_factory() -> tuple[MagicMock, AsyncMock]:
    """Return (factory, session) pair for async context manager mocking."""
    session = AsyncMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    factory = MagicMock(return_value=ctx)
    return factory, session


def _make_resource(
    kind: ResourceKind,
    name: str,
    project: str = "default",
    spec: dict[str, Any] | None = None,
) -> MagicMock:
    """Build a mock Resource object."""
    r = MagicMock()
    r.kind = kind
    r.name = name
    r.project = project
    r.spec = spec or {}
    return r


def _make_listener() -> Any:
    """Create a BlackbeardExecutionListener with mocked internals."""
    from blackbeard.engine.execution_listener import BlackbeardExecutionListener

    eid = uuid.uuid4()
    mock_factory = MagicMock()

    with (
        patch(
            "blackbeard.engine.execution_listener._get_sync_session_factory",
            return_value=mock_factory,
        ),
        patch("blackbeard.engine.execution_listener._get_otel_tracer", return_value=None),
    ):
        listener = BlackbeardExecutionListener(
            execution_id=eid,
            db_url="postgresql+asyncpg://localhost/test",
        )
    return listener


# ===========================================================================
# executor.py: _get_bg_engine
# ===========================================================================


class TestGetBgEngine:
    """Tests for blackbeard.engine.executor._get_bg_engine."""

    def test_creates_engine_on_first_call(self) -> None:
        import blackbeard.engine.executor as mod

        orig_engine = mod._bg_engine
        orig_factory = mod._bg_session_factory
        try:
            mod._bg_engine = None
            mod._bg_session_factory = None

            mock_engine = MagicMock()
            mock_engine.sync_engine = MagicMock()

            with (
                patch(
                    "sqlalchemy.ext.asyncio.create_async_engine",
                    return_value=mock_engine,
                ),
                patch("blackbeard.engine.executor.instrument_engine"),
                patch(
                    "blackbeard.engine.executor.settings",
                    max_concurrent_executions=4,
                    database_url=MagicMock(get_secret_value=lambda: "postgresql+asyncpg://x/db"),
                ),
            ):
                result = mod._get_bg_engine()

            assert result is mock_engine
            assert mod._bg_engine is mock_engine
            assert mod._bg_session_factory is not None
        finally:
            mod._bg_engine = orig_engine
            mod._bg_session_factory = orig_factory

    def test_returns_cached_engine(self) -> None:
        import blackbeard.engine.executor as mod

        orig_engine = mod._bg_engine
        orig_factory = mod._bg_session_factory
        try:
            mock_engine = MagicMock()
            mod._bg_engine = mock_engine
            mod._bg_session_factory = MagicMock()

            result = mod._get_bg_engine()
            assert result is mock_engine
        finally:
            mod._bg_engine = orig_engine
            mod._bg_session_factory = orig_factory


# ===========================================================================
# executor.py: _thread_session_factory
# ===========================================================================


class TestThreadSessionFactory:
    """Tests for blackbeard.engine.executor._thread_session_factory."""

    def test_returns_factory(self) -> None:
        import blackbeard.engine.executor as mod

        orig_engine = mod._bg_engine
        orig_factory = mod._bg_session_factory
        try:
            mock_engine = MagicMock()
            mock_factory = MagicMock()
            mod._bg_engine = mock_engine
            mod._bg_session_factory = mock_factory

            with patch.object(mod, "_get_bg_engine"):
                result = mod._thread_session_factory()

            assert result is mock_factory
        finally:
            mod._bg_engine = orig_engine
            mod._bg_session_factory = orig_factory

    def test_raises_when_factory_is_none(self) -> None:
        import blackbeard.engine.executor as mod

        orig_engine = mod._bg_engine
        orig_factory = mod._bg_session_factory
        try:
            mod._bg_engine = MagicMock()
            mod._bg_session_factory = None

            with (
                patch.object(mod, "_get_bg_engine"),
                pytest.raises(RuntimeError, match="unavailable"),
            ):
                mod._thread_session_factory()
        finally:
            mod._bg_engine = orig_engine
            mod._bg_session_factory = orig_factory


# ===========================================================================
# executor.py: _load_crew_resources
# ===========================================================================


class TestLoadCrewResources:
    """Tests for blackbeard.engine.executor._load_crew_resources."""

    @pytest.mark.asyncio
    async def test_raises_when_crew_not_found(self) -> None:
        from blackbeard.engine.executor import ExecutionNotFoundError, _load_crew_resources

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value = []
        session.execute.return_value = mock_result

        with pytest.raises(ExecutionNotFoundError, match="not found"):
            await _load_crew_resources(session, "nonexistent-crew", "default")

    @pytest.mark.asyncio
    async def test_returns_resources_keyed_by_kind_name(self) -> None:
        from blackbeard.engine.executor import _load_crew_resources

        crew = _make_resource(ResourceKind.CREW, "my-crew", spec={"agents": [], "tasks": []})
        agent = _make_resource(
            ResourceKind.AGENT,
            "researcher",
            spec={"role": "R", "goal": "G", "backstory": "B"},
        )

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value = [crew, agent]
        session.execute.return_value = mock_result

        resources = await _load_crew_resources(session, "my-crew", "default")
        assert "Crew/my-crew" in resources
        assert "Agent/researcher" in resources

    @pytest.mark.asyncio
    async def test_warns_on_large_project(self) -> None:
        from blackbeard.engine.executor import _load_crew_resources

        crew = _make_resource(ResourceKind.CREW, "my-crew", spec={"agents": [], "tasks": []})
        # Create 101 mock resources to trigger the warning
        resources_list = [crew]
        for i in range(100):
            resources_list.append(
                _make_resource(
                    ResourceKind.AGENT,
                    f"agent-{i}",
                    spec={"role": "R", "goal": "G", "backstory": "B"},
                )
            )

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value = resources_list
        session.execute.return_value = mock_result

        with patch("blackbeard.engine.executor.logger") as mock_logger:
            result = await _load_crew_resources(session, "my-crew", "default")

        assert "Crew/my-crew" in result
        mock_logger.warning.assert_called()
        assert any(
            "consider splitting" in str(call) for call in mock_logger.warning.call_args_list
        )

    @pytest.mark.asyncio
    async def test_truncates_at_namespace_limit(self) -> None:
        from blackbeard.engine.executor import _PROJECT_RESOURCE_LIMIT, _load_crew_resources

        crew = _make_resource(ResourceKind.CREW, "my-crew", spec={"agents": [], "tasks": []})
        resources_list = [crew]
        for i in range(_PROJECT_RESOURCE_LIMIT + 1):
            resources_list.append(
                _make_resource(ResourceKind.AGENT, f"agent-{i}", spec={"role": "R", "goal": "G", "backstory": "B"})
            )

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value = resources_list
        session.execute.return_value = mock_result

        with patch("blackbeard.engine.executor.logger"):
            result = await _load_crew_resources(session, "my-crew", "default")

        assert len(result) <= _PROJECT_RESOURCE_LIMIT


# ===========================================================================
# executor.py: kickoff / train_crew / test_crew / run_flow
# ===========================================================================


class TestKickoff:
    """Tests for blackbeard.engine.executor.kickoff."""

    @pytest.mark.asyncio
    async def test_creates_execution_and_returns(self) -> None:
        from blackbeard.engine.executor import kickoff

        session = AsyncMock()
        exec_obj = MagicMock(spec=Execution)
        exec_obj.id = uuid.uuid4()
        exec_obj.crew_name = "test-crew"
        exec_obj.status = ExecutionStatus.QUEUED

        crew_res = _make_resource(
            ResourceKind.CREW, "test-crew", spec={"agents": [], "tasks": []}
        )

        mock_result_load = MagicMock()
        mock_result_load.scalars.return_value = [crew_res]
        mock_result_get = MagicMock()
        mock_result_get.scalar_one_or_none.return_value = exec_obj

        session.execute.side_effect = [mock_result_load, mock_result_get]
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        session.add = MagicMock()
        session.add_all = MagicMock()

        mock_loop = MagicMock()
        mock_future = MagicMock()
        mock_loop.run_in_executor.return_value = mock_future

        with (
            patch("blackbeard.engine.executor.asyncio.get_running_loop", return_value=mock_loop),
            patch("blackbeard.engine.executor._get_executor", return_value=MagicMock()),
            patch(
                "blackbeard.engine.executor._snapshot_crew_resources",
                return_value={"Crew/test-crew": {"kind": "Crew", "name": "test-crew", "project": "default", "spec": {}}},
            ),
        ):
            result = await kickoff(session, "test-crew", {"topic": "AI"})

        assert result is exec_obj
        session.add.assert_called_once()
        session.commit.assert_called()


class TestTrainCrew:
    """Tests for blackbeard.engine.executor.train_crew."""

    @pytest.mark.asyncio
    async def test_delegates_to_submit_execution(self) -> None:
        from blackbeard.engine.executor import train_crew

        with patch(
            "blackbeard.engine.executor._submit_execution",
            new_callable=AsyncMock,
        ) as mock_submit:
            mock_submit.return_value = MagicMock(spec=Execution)
            result = await train_crew(
                AsyncMock(),
                "my-crew",
                inputs={"topic": "ML"},
                n_iterations=5,
                filename="train.pkl",
            )

        mock_submit.assert_called_once()
        call_args = mock_submit.call_args
        assert call_args[0][4] is None  # user
        assert call_args[0][5] == ExecutionType.TRAIN
        assert call_args[1]["n_iterations"] == 5
        assert call_args[1]["training_file"] == "train.pkl"
        assert result is mock_submit.return_value


class TestTestCrew:
    """Tests for blackbeard.engine.executor.test_crew."""

    @pytest.mark.asyncio
    async def test_delegates_to_submit_execution(self) -> None:
        from blackbeard.engine.executor import test_crew

        with patch(
            "blackbeard.engine.executor._submit_execution",
            new_callable=AsyncMock,
        ) as mock_submit:
            mock_submit.return_value = MagicMock(spec=Execution)
            result = await test_crew(
                AsyncMock(),
                "my-crew",
                n_iterations=2,
            )

        mock_submit.assert_called_once()
        call_args = mock_submit.call_args
        assert call_args[0][5] == ExecutionType.TEST
        assert call_args[1]["n_iterations"] == 2
        assert result is mock_submit.return_value


class TestRunFlow:
    """Tests for blackbeard.engine.executor.run_flow."""

    @pytest.mark.asyncio
    async def test_delegates_to_submit_execution_with_flow_type(self) -> None:
        from blackbeard.engine.executor import run_flow

        with patch(
            "blackbeard.engine.executor._submit_execution",
            new_callable=AsyncMock,
        ) as mock_submit:
            mock_submit.return_value = MagicMock(spec=Execution)
            result = await run_flow(AsyncMock(), "my-flow", {"key": "val"})

        mock_submit.assert_called_once()
        call_args = mock_submit.call_args
        assert call_args[0][5] == ExecutionType.FLOW
        assert result is mock_submit.return_value


# ===========================================================================
# executor.py: get_execution / get_execution_status
# ===========================================================================


class TestGetExecution:
    """Tests for blackbeard.engine.executor.get_execution."""

    @pytest.mark.asyncio
    async def test_returns_execution(self) -> None:
        from blackbeard.engine.executor import get_execution

        eid = uuid.uuid4()
        exec_obj = MagicMock(spec=Execution)
        exec_obj.id = eid

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = exec_obj
        session.execute.return_value = mock_result

        result = await get_execution(session, eid)
        assert result is exec_obj

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self) -> None:
        from blackbeard.engine.executor import get_execution

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        result = await get_execution(session, uuid.uuid4())
        assert result is None


class TestGetExecutionStatus:
    """Tests for blackbeard.engine.executor.get_execution_status."""

    @pytest.mark.asyncio
    async def test_returns_status(self) -> None:
        from blackbeard.engine.executor import get_execution_status

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = ExecutionStatus.RUNNING
        session.execute.return_value = mock_result

        result = await get_execution_status(session, uuid.uuid4())
        assert result == ExecutionStatus.RUNNING

    @pytest.mark.asyncio
    async def test_returns_none_for_missing(self) -> None:
        from blackbeard.engine.executor import get_execution_status

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        result = await get_execution_status(session, uuid.uuid4())
        assert result is None


# ===========================================================================
# executor.py: list_executions edge cases
# ===========================================================================


class TestListExecutions:
    """Tests for blackbeard.engine.executor.list_executions."""

    @pytest.mark.asyncio
    async def test_returns_items_and_total_without_count_query(self) -> None:
        """When items < limit and offset == 0, total = len(items)."""
        from blackbeard.engine.executor import list_executions

        exec1 = MagicMock(spec=Execution)
        exec2 = MagicMock(spec=Execution)

        session = AsyncMock()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [exec1, exec2]
        mock_result.scalars.return_value = mock_scalars
        session.execute.return_value = mock_result

        items, total = await list_executions(session, limit=100, offset=0)
        assert items == [exec1, exec2]
        assert total == 2
        # Only one execute call (no count query)
        assert session.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_issues_count_query_when_at_limit(self) -> None:
        """When items == limit, a count query is needed."""
        from blackbeard.engine.executor import list_executions

        items_list = [MagicMock(spec=Execution) for _ in range(10)]

        session = AsyncMock()

        # First call: list query
        mock_list_result = MagicMock()
        mock_list_scalars = MagicMock()
        mock_list_scalars.all.return_value = items_list
        mock_list_result.scalars.return_value = mock_list_scalars

        # Second call: count query
        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 50

        session.execute.side_effect = [mock_list_result, mock_count_result]

        items, total = await list_executions(session, limit=10, offset=0)
        assert len(items) == 10
        assert total == 50
        assert session.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_applies_filters(self) -> None:
        """Filters by crew_name, project, status, execution_type."""
        from blackbeard.engine.executor import list_executions

        session = AsyncMock()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        session.execute.return_value = mock_result

        items, total = await list_executions(
            session,
            crew_name="my-crew",
            project="prod",
            status=ExecutionStatus.COMPLETED,
            execution_type=ExecutionType.KICKOFF,
        )
        assert items == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_include_tasks_option(self) -> None:
        """include_tasks=True uses selectinload."""
        from blackbeard.engine.executor import list_executions

        session = AsyncMock()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        session.execute.return_value = mock_result

        items, _total = await list_executions(session, include_tasks=True)
        assert items == []


# ===========================================================================
# executor.py: list_execution_events
# ===========================================================================


class TestListExecutionEvents:
    """Tests for blackbeard.engine.executor.list_execution_events."""

    @pytest.mark.asyncio
    async def test_returns_events_after_sequence(self) -> None:
        from blackbeard.engine.executor import list_execution_events

        eid = uuid.uuid4()
        ev1 = MagicMock(spec=ExecutionEvent)
        ev2 = MagicMock(spec=ExecutionEvent)

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value = [ev1, ev2]
        session.execute.return_value = mock_result

        result = await list_execution_events(session, eid, after=5)
        assert result == [ev1, ev2]

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_events(self) -> None:
        from blackbeard.engine.executor import list_execution_events

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value = []
        session.execute.return_value = mock_result

        result = await list_execution_events(session, uuid.uuid4())
        assert result == []


# ===========================================================================
# executor.py: record_hitl_response
# ===========================================================================


class TestRecordHitlResponse:
    """Tests for blackbeard.engine.executor.record_hitl_response."""

    @staticmethod
    def _mock_begin_nested() -> MagicMock:
        """Return a MagicMock that works as an async context manager for begin_nested()."""
        nested_ctx = MagicMock()
        nested_ctx.__aenter__ = AsyncMock()
        nested_ctx.__aexit__ = AsyncMock(return_value=False)
        # begin_nested() is a sync method returning an async ctx manager
        return MagicMock(return_value=nested_ctx)

    @pytest.mark.asyncio
    async def test_records_response_event(self) -> None:
        from blackbeard.engine.executor import record_hitl_response

        eid = uuid.uuid4()
        session = AsyncMock()

        mock_seq_result = MagicMock()
        mock_seq_result.scalar.return_value = 5
        session.execute.return_value = mock_seq_result
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.begin_nested = self._mock_begin_nested()

        event = await record_hitl_response(session, eid, "Yes, proceed", feedback="LGTM")

        assert event.event_type == "hitl_response"
        assert event.data["response"] == "Yes, proceed"
        assert event.data["feedback"] == "LGTM"
        assert event.sequence == 6

    @pytest.mark.asyncio
    async def test_records_response_without_feedback(self) -> None:
        from blackbeard.engine.executor import record_hitl_response

        eid = uuid.uuid4()
        session = AsyncMock()

        mock_seq_result = MagicMock()
        mock_seq_result.scalar.return_value = -1
        session.execute.return_value = mock_seq_result
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.begin_nested = self._mock_begin_nested()

        event = await record_hitl_response(session, eid, "Approved")

        assert event.event_type == "hitl_response"
        assert event.data["response"] == "Approved"
        assert "feedback" not in event.data
        assert event.sequence == 0


# ===========================================================================
# executor.py: cancel_execution
# ===========================================================================


class TestCancelExecution:
    """Tests for blackbeard.engine.executor.cancel_execution."""

    @pytest.mark.asyncio
    async def test_cancels_queued_execution(self) -> None:
        from blackbeard.engine.executor import cancel_execution

        eid = uuid.uuid4()
        exec_obj = MagicMock(spec=Execution)
        exec_obj.id = eid
        exec_obj.status = ExecutionStatus.QUEUED
        exec_obj.crew_name = "test-crew"
        exec_obj.crew_project = "default"
        exec_obj.tasks = []

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = exec_obj
        session.execute.return_value = mock_result
        session.flush = AsyncMock()

        result = await cancel_execution(session, eid)

        assert result is exec_obj
        assert exec_obj.status == ExecutionStatus.CANCELLED
        assert exec_obj.completed_at is not None

    @pytest.mark.asyncio
    async def test_cancels_running_execution_with_tasks(self) -> None:
        from blackbeard.engine.executor import cancel_execution

        eid = uuid.uuid4()
        task1 = MagicMock(spec=ExecutionTask)
        task1.status = TaskStatus.RUNNING
        task2 = MagicMock(spec=ExecutionTask)
        task2.status = TaskStatus.PENDING

        exec_obj = MagicMock(spec=Execution)
        exec_obj.id = eid
        exec_obj.status = ExecutionStatus.RUNNING
        exec_obj.crew_name = "test-crew"
        exec_obj.crew_project = "default"
        exec_obj.tasks = [task1, task2]

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = exec_obj
        session.execute.return_value = mock_result
        session.flush = AsyncMock()

        result = await cancel_execution(session, eid)

        assert exec_obj.status == ExecutionStatus.CANCELLED
        assert task1.status == TaskStatus.FAILED
        assert task2.status == TaskStatus.FAILED
        assert task1.error == "Execution cancelled"
        assert result is exec_obj

    @pytest.mark.asyncio
    async def test_raises_for_terminal_execution(self) -> None:
        from blackbeard.engine.executor import ExecutionError, cancel_execution

        eid = uuid.uuid4()
        exec_obj = MagicMock(spec=Execution)
        exec_obj.id = eid
        exec_obj.status = ExecutionStatus.COMPLETED
        exec_obj.crew_name = "test-crew"
        exec_obj.tasks = []

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = exec_obj
        session.execute.return_value = mock_result

        with pytest.raises(ExecutionError, match="terminal status"):
            await cancel_execution(session, eid)

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self) -> None:
        from blackbeard.engine.executor import cancel_execution

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        result = await cancel_execution(session, uuid.uuid4())
        assert result is None


# ===========================================================================
# execution_listener.py: _get_otel_tracer initialization paths
# ===========================================================================


class TestGetOtelTracer:
    """Tests for blackbeard.engine.execution_listener._get_otel_tracer."""

    def test_returns_none_without_otel(self) -> None:
        import blackbeard.engine.execution_listener as mod

        orig = mod.HAS_OTEL
        orig_tracer = mod._otel_tracer
        try:
            mod.HAS_OTEL = False
            mod._otel_tracer = None
            result = mod._get_otel_tracer()
            assert result is None
        finally:
            mod.HAS_OTEL = orig
            mod._otel_tracer = orig_tracer

    def test_returns_cached_tracer(self) -> None:
        import blackbeard.engine.execution_listener as mod

        orig = mod._otel_tracer
        try:
            mock_tracer = MagicMock()
            mod._otel_tracer = mock_tracer
            result = mod._get_otel_tracer()
            assert result is mock_tracer
        finally:
            mod._otel_tracer = orig

    def test_initializes_otel_with_endpoint(self) -> None:
        import blackbeard.engine.execution_listener as mod

        orig_has = mod.HAS_OTEL
        orig_tracer = mod._otel_tracer
        orig_provider = mod._otel_provider
        try:
            mod.HAS_OTEL = True
            mod._otel_tracer = None
            mod._otel_provider = None

            mock_tracer = MagicMock()
            mock_settings = MagicMock()
            mock_settings.otel_endpoint = "http://otel:4317"

            with (
                patch("blackbeard.engine.execution_listener.OTELResource"),
                patch("blackbeard.engine.execution_listener.TracerProvider") as mock_tp,
                patch("blackbeard.engine.execution_listener.OTLPSpanExporter") as mock_exp,
                patch("blackbeard.engine.execution_listener.BatchSpanProcessor"),
                patch("blackbeard.engine.execution_listener.trace") as mock_trace,
                patch("blackbeard.config.settings", mock_settings),
            ):
                mock_trace.get_tracer.return_value = mock_tracer
                result = mod._get_otel_tracer()

            assert result is mock_tracer
            assert mod._otel_tracer is mock_tracer
            assert mod._otel_provider is not None
            mock_tp.assert_called_once()
            mock_exp.assert_called_once_with(endpoint="http://otel:4317")
        finally:
            mod.HAS_OTEL = orig_has
            mod._otel_tracer = orig_tracer
            mod._otel_provider = orig_provider

    def test_returns_none_without_endpoint(self) -> None:
        import blackbeard.engine.execution_listener as mod

        orig_has = mod.HAS_OTEL
        orig_tracer = mod._otel_tracer
        try:
            mod.HAS_OTEL = True
            mod._otel_tracer = None

            mock_settings = MagicMock()
            mock_settings.otel_endpoint = None

            with patch("blackbeard.config.settings", mock_settings):
                result = mod._get_otel_tracer()

            assert result is None
        finally:
            mod.HAS_OTEL = orig_has
            mod._otel_tracer = orig_tracer


# ===========================================================================
# execution_listener.py: _get_cached_webhooks
# ===========================================================================


class TestGetCachedWebhooks:
    """Tests for blackbeard.engine.execution_listener._get_cached_webhooks."""

    def test_returns_cached_webhooks(self) -> None:
        import time

        import blackbeard.engine.execution_listener as mod

        orig = mod._webhook_cache_entry
        try:
            mock_wh = MagicMock()
            mod._webhook_cache_entry = (time.monotonic(), [mock_wh])

            result = mod._get_cached_webhooks("db-url")
            assert result == [mock_wh]
        finally:
            mod._webhook_cache_entry = orig

    def test_refreshes_stale_cache(self) -> None:
        import time

        import blackbeard.engine.execution_listener as mod

        orig = mod._webhook_cache_entry
        try:
            # Set cache to a very old time so it's stale
            mod._webhook_cache_entry = (time.monotonic() - 600, [])

            mock_wh = MagicMock()
            mock_session = MagicMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value = [mock_wh]
            mock_session.execute.return_value = mock_result
            mock_session_ctx = MagicMock()
            mock_session_ctx.__enter__ = MagicMock(return_value=mock_session)
            mock_session_ctx.__exit__ = MagicMock(return_value=False)
            mock_factory = MagicMock(return_value=mock_session_ctx)

            with patch(
                "blackbeard.engine.execution_listener._get_sync_session_factory",
                return_value=mock_factory,
            ):
                result = mod._get_cached_webhooks("db-url")

            assert result == [mock_wh]
        finally:
            mod._webhook_cache_entry = orig

    def test_uses_stale_cache_on_db_error(self) -> None:
        import time

        import blackbeard.engine.execution_listener as mod

        orig = mod._webhook_cache_entry
        try:
            stale_wh = MagicMock()
            mod._webhook_cache_entry = (time.monotonic() - 600, [stale_wh])

            mock_factory = MagicMock()
            mock_session = MagicMock()
            mock_session.execute.side_effect = RuntimeError("DB down")
            mock_session_ctx = MagicMock()
            mock_session_ctx.__enter__ = MagicMock(return_value=mock_session)
            mock_session_ctx.__exit__ = MagicMock(return_value=False)
            mock_factory.return_value = mock_session_ctx

            with (
                patch(
                    "blackbeard.engine.execution_listener._get_sync_session_factory",
                    return_value=mock_factory,
                ),
                patch("blackbeard.engine.execution_listener.logger"),
            ):
                result = mod._get_cached_webhooks("db-url")

            assert result == [stale_wh]
        finally:
            mod._webhook_cache_entry = orig

    def test_returns_empty_on_db_error_without_stale_cache(self) -> None:
        import blackbeard.engine.execution_listener as mod

        orig = mod._webhook_cache_entry
        try:
            mod._webhook_cache_entry = None

            mock_factory = MagicMock()
            mock_session = MagicMock()
            mock_session.execute.side_effect = RuntimeError("DB down")
            mock_session_ctx = MagicMock()
            mock_session_ctx.__enter__ = MagicMock(return_value=mock_session)
            mock_session_ctx.__exit__ = MagicMock(return_value=False)
            mock_factory.return_value = mock_session_ctx

            with (
                patch(
                    "blackbeard.engine.execution_listener._get_sync_session_factory",
                    return_value=mock_factory,
                ),
                patch("blackbeard.engine.execution_listener.logger"),
            ):
                result = mod._get_cached_webhooks("db-url")

            assert result == []
        finally:
            mod._webhook_cache_entry = orig


# ===========================================================================
# execution_listener.py: _ensure_request_id / _schedule_flush
# ===========================================================================


class TestEnsureRequestId:
    """Tests for BlackbeardExecutionListener._ensure_request_id."""

    def test_sets_request_id_when_unset(self) -> None:
        from blackbeard.logging_config import request_id_var

        listener = _make_listener()

        # Clear the context var
        token = request_id_var.set("-")
        try:
            listener._ensure_request_id()
            assert request_id_var.get() == listener._execution_id_str
        finally:
            request_id_var.reset(token)

    def test_does_not_overwrite_existing_request_id(self) -> None:
        from blackbeard.logging_config import request_id_var

        listener = _make_listener()

        token = request_id_var.set("existing-id")
        try:
            listener._ensure_request_id()
            assert request_id_var.get() == "existing-id"
        finally:
            request_id_var.reset(token)


class TestScheduleFlush:
    """Tests for BlackbeardExecutionListener._schedule_flush."""

    def test_creates_timer_when_none_exists(self) -> None:
        listener = _make_listener()
        listener._flush_timer = None

        # Patch Timer to avoid actual thread creation
        with patch("blackbeard.engine.execution_listener.threading.Timer") as mock_timer_cls:
            mock_timer = MagicMock()
            mock_timer.is_alive.return_value = False
            mock_timer_cls.return_value = mock_timer
            listener._schedule_flush()

        mock_timer_cls.assert_called_once()
        mock_timer.start.assert_called_once()

    def test_does_not_create_timer_when_alive(self) -> None:
        listener = _make_listener()
        mock_timer = MagicMock()
        mock_timer.is_alive.return_value = True
        listener._flush_timer = mock_timer

        with patch("blackbeard.engine.execution_listener.threading.Timer") as mock_timer_cls:
            listener._schedule_flush()

        mock_timer_cls.assert_not_called()


# ===========================================================================
# execution_listener.py: _write_event with PII redaction
# ===========================================================================


class TestWriteEventPii:
    """Tests for PII redaction in _write_event."""

    def test_redacts_pii_when_enabled(self) -> None:
        from blackbeard.engine.execution_listener import BlackbeardExecutionListener

        eid = uuid.uuid4()
        mock_factory = MagicMock()

        with (
            patch(
                "blackbeard.engine.execution_listener._get_sync_session_factory",
                return_value=mock_factory,
            ),
            patch("blackbeard.engine.execution_listener._get_otel_tracer", return_value=None),
        ):
            listener = BlackbeardExecutionListener(
                execution_id=eid,
                db_url="postgresql+asyncpg://localhost/test",
                pii_config={"enabled": True, "redact_events": True, "entities": ["EMAIL"]},
            )

        assert listener._pii_redact_events is True

        with (
            patch.object(listener, "_dispatch_webhook"),
            patch.object(listener, "_schedule_flush"),
            patch(
                "blackbeard.engine.execution_listener._redact_dict",
                return_value={"message": "[REDACTED]"},
            ) as mock_redact,
        ):
            listener._write_event("test_event", {"message": "user@example.com"})

        mock_redact.assert_called_once()
        assert listener._buffer[0].data == {"message": "[REDACTED]"}


# ===========================================================================
# execution_listener.py: _write_event_with_task_update
# ===========================================================================


class TestWriteEventWithTaskUpdate:
    """Tests for BlackbeardExecutionListener._write_event_with_task_update."""

    def test_writes_event_and_updates_task(self) -> None:
        from blackbeard.engine.execution_listener import BlackbeardExecutionListener

        eid = uuid.uuid4()
        mock_session = MagicMock()
        mock_session_ctx = MagicMock()
        mock_session_ctx.__enter__ = MagicMock(return_value=mock_session)
        mock_session_ctx.__exit__ = MagicMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_session_ctx)

        with (
            patch(
                "blackbeard.engine.execution_listener._get_sync_session_factory",
                return_value=mock_factory,
            ),
            patch("blackbeard.engine.execution_listener._get_otel_tracer", return_value=None),
        ):
            listener = BlackbeardExecutionListener(
                execution_id=eid,
                db_url="postgresql+asyncpg://localhost/test",
            )

        now = datetime.now(UTC)
        with patch.object(listener, "_dispatch_webhook"):
            listener._write_event_with_task_update(
                "task_started",
                {"task_name": "research"},
                task_order=0,
                task_status=TaskStatus.RUNNING,
                task_started_at=now,
            )

        mock_session.add_all.assert_called_once()
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    def test_requeues_on_db_failure(self) -> None:
        from blackbeard.engine.execution_listener import BlackbeardExecutionListener

        eid = uuid.uuid4()
        mock_session = MagicMock()
        mock_session.commit.side_effect = RuntimeError("DB connection lost")
        mock_session_ctx = MagicMock()
        mock_session_ctx.__enter__ = MagicMock(return_value=mock_session)
        mock_session_ctx.__exit__ = MagicMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_session_ctx)

        with (
            patch(
                "blackbeard.engine.execution_listener._get_sync_session_factory",
                return_value=mock_factory,
            ),
            patch("blackbeard.engine.execution_listener._get_otel_tracer", return_value=None),
        ):
            listener = BlackbeardExecutionListener(
                execution_id=eid,
                db_url="postgresql+asyncpg://localhost/test",
            )

        with (
            patch.object(listener, "_dispatch_webhook"),
            patch.object(listener, "_schedule_flush"),
            patch("blackbeard.engine.execution_listener.logger"),
        ):
            listener._write_event_with_task_update(
                "task_completed",
                {"task_name": "research"},
                task_order=0,
                task_status=TaskStatus.COMPLETED,
                task_output="Research results",
            )

        # Events should be re-queued
        assert len(listener._buffer) == 1

    def test_pii_redacts_task_output(self) -> None:
        from blackbeard.engine.execution_listener import BlackbeardExecutionListener

        eid = uuid.uuid4()
        mock_session = MagicMock()
        mock_session_ctx = MagicMock()
        mock_session_ctx.__enter__ = MagicMock(return_value=mock_session)
        mock_session_ctx.__exit__ = MagicMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_session_ctx)

        with (
            patch(
                "blackbeard.engine.execution_listener._get_sync_session_factory",
                return_value=mock_factory,
            ),
            patch("blackbeard.engine.execution_listener._get_otel_tracer", return_value=None),
        ):
            listener = BlackbeardExecutionListener(
                execution_id=eid,
                db_url="postgresql+asyncpg://localhost/test",
                pii_config={"enabled": True, "redact_events": True, "entities": ["EMAIL"]},
            )

        with (
            patch.object(listener, "_dispatch_webhook"),
            patch(
                "blackbeard.engine.execution_listener._redact_dict",
                return_value={"task_name": "test"},
            ),
            patch(
                "blackbeard.engine.execution_listener._redact_text_fn",
                return_value="[REDACTED OUTPUT]",
            ) as mock_redact_text,
        ):
            listener._write_event_with_task_update(
                "task_completed",
                {"task_name": "test"},
                task_order=0,
                task_status=TaskStatus.COMPLETED,
                task_output="Contains user@example.com",
            )

        mock_redact_text.assert_called_once()


# ===========================================================================
# execution_listener.py: _otel_start_span / _otel_end_span
# ===========================================================================


class TestOtelSpans:
    """Tests for _otel_start_span and _otel_end_span."""

    def test_start_span_returns_none_without_tracer(self) -> None:
        listener = _make_listener()
        listener._otel_tracer = None

        result = listener._otel_start_span("test-span")
        assert result is None

    def test_start_span_with_tracer(self) -> None:
        listener = _make_listener()
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_tracer.start_span.return_value = mock_span
        listener._otel_tracer = mock_tracer

        with patch("blackbeard.engine.execution_listener.trace"):
            result = listener._otel_start_span("test-span", {"key": "value"})

        assert result is mock_span
        mock_tracer.start_span.assert_called_once()

    def test_start_span_with_root_span(self) -> None:
        listener = _make_listener()
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_root = MagicMock()
        mock_tracer.start_span.return_value = mock_span
        listener._otel_tracer = mock_tracer
        listener._otel_root_span = mock_root

        with patch("blackbeard.engine.execution_listener.trace") as mock_trace:
            mock_trace.set_span_in_context.return_value = MagicMock()
            result = listener._otel_start_span("child-span")

        assert result is mock_span
        mock_trace.set_span_in_context.assert_called_once_with(mock_root)

    def test_end_span_ends_tracked_span(self) -> None:
        listener = _make_listener()
        mock_span = MagicMock()
        listener._otel_active_spans["task/research"] = mock_span

        listener._otel_end_span("task/research", {"key": "val"})

        mock_span.set_attribute.assert_called_once_with("key", "val")
        mock_span.end.assert_called_once()
        assert "task/research" not in listener._otel_active_spans

    def test_end_span_noop_for_unknown_key(self) -> None:
        listener = _make_listener()

        # Should not raise
        listener._otel_end_span("nonexistent/span")


# ===========================================================================
# execution_listener.py: setup_listeners event handler bodies
# ===========================================================================


class TestEventHandlerBodies:
    """Tests for the actual event handler closures registered by setup_listeners.

    Registers handlers via setup_listeners, then invokes them with mock events
    to verify _write_event / _write_event_with_task_update calls.
    """

    def _setup_and_get_handlers(self) -> tuple[Any, dict[type, Any]]:
        """Create a listener, register handlers, and return (listener, handlers_dict)."""
        listener = _make_listener()
        handlers: dict[type, Any] = {}

        mock_bus = MagicMock()

        def fake_on(event_type: type) -> Any:
            def decorator(fn: Any) -> Any:
                handlers[event_type] = fn
                return fn
            return decorator

        mock_bus.on = fake_on
        listener.setup_listeners(mock_bus)
        return listener, handlers

    def test_on_crew_started(self) -> None:
        from crewai.events import CrewKickoffStartedEvent

        listener, handlers = self._setup_and_get_handlers()
        handler = handlers[CrewKickoffStartedEvent]

        event = MagicMock(spec=CrewKickoffStartedEvent)
        event.crew_name = "my-crew"
        event.inputs = {"topic": "AI"}

        with patch.object(listener, "_write_event") as mock_write:
            handler(MagicMock(), event)

        mock_write.assert_called_once()
        call_args = mock_write.call_args
        assert call_args[0][0] == "crew_started"
        assert call_args[0][1]["crew_name"] == "my-crew"

    def test_on_crew_started_with_none_inputs(self) -> None:
        from crewai.events import CrewKickoffStartedEvent

        listener, handlers = self._setup_and_get_handlers()
        handler = handlers[CrewKickoffStartedEvent]

        event = MagicMock(spec=CrewKickoffStartedEvent)
        event.crew_name = None
        event.inputs = None

        with patch.object(listener, "_write_event") as mock_write:
            handler(MagicMock(), event)

        mock_write.assert_called_once()
        data = mock_write.call_args[0][1]
        assert data["crew_name"] == "unknown"
        assert data["inputs"] == {}

    def test_on_crew_completed(self) -> None:
        from crewai.events import CrewKickoffCompletedEvent

        listener, handlers = self._setup_and_get_handlers()
        handler = handlers[CrewKickoffCompletedEvent]

        event = MagicMock(spec=CrewKickoffCompletedEvent)
        event.total_tokens = 1500

        with patch.object(listener, "_write_event") as mock_write:
            handler(MagicMock(), event)

        mock_write.assert_called_once()
        data = mock_write.call_args[0][1]
        assert data["total_tokens"] == 1500

    def test_on_crew_completed_ends_otel_root_span(self) -> None:
        from crewai.events import CrewKickoffCompletedEvent

        listener, handlers = self._setup_and_get_handlers()
        handler = handlers[CrewKickoffCompletedEvent]

        mock_root = MagicMock()
        listener._otel_root_span = mock_root

        event = MagicMock(spec=CrewKickoffCompletedEvent)
        event.total_tokens = 100

        with patch.object(listener, "_write_event"):
            handler(MagicMock(), event)

        mock_root.end.assert_called_once()
        assert listener._otel_root_span is None

    def test_on_task_started(self) -> None:
        from crewai.events import TaskStartedEvent

        listener, handlers = self._setup_and_get_handlers()
        handler = handlers[TaskStartedEvent]

        event = MagicMock(spec=TaskStartedEvent)
        event.task_name = "research-task"
        event.agent_role = "Researcher"

        with patch.object(listener, "_write_event_with_task_update") as mock_write:
            handler(MagicMock(), event)

        mock_write.assert_called_once()
        args = mock_write.call_args
        assert args[0][0] == "task_started"
        assert args[0][1]["task_name"] == "research-task"
        assert args[0][1]["agent_role"] == "Researcher"
        assert args[1]["task_status"] == TaskStatus.RUNNING

    def test_on_task_completed(self) -> None:
        from crewai.events import TaskCompletedEvent

        listener, handlers = self._setup_and_get_handlers()
        handler = handlers[TaskCompletedEvent]

        event = MagicMock(spec=TaskCompletedEvent)
        event.task_name = "research-task"
        event.output = "Research results from the analysis..."

        with patch.object(listener, "_write_event_with_task_update") as mock_write:
            handler(MagicMock(), event)

        mock_write.assert_called_once()
        args = mock_write.call_args
        assert args[0][0] == "task_completed"
        assert args[1]["task_status"] == TaskStatus.COMPLETED
        assert args[1]["task_output"] is not None

    def test_on_task_completed_increments_task_order(self) -> None:
        from crewai.events import TaskCompletedEvent

        listener, handlers = self._setup_and_get_handlers()
        handler = handlers[TaskCompletedEvent]

        event = MagicMock(spec=TaskCompletedEvent)
        event.task_name = "task1"
        event.output = "done"

        initial_order = listener._task_order

        with patch.object(listener, "_write_event_with_task_update"):
            handler(MagicMock(), event)

        assert listener._task_order == initial_order + 1

    def test_on_task_completed_with_none_output(self) -> None:
        from crewai.events import TaskCompletedEvent

        listener, handlers = self._setup_and_get_handlers()
        handler = handlers[TaskCompletedEvent]

        event = MagicMock(spec=TaskCompletedEvent)
        event.task_name = "task1"
        event.output = None

        with patch.object(listener, "_write_event_with_task_update") as mock_write:
            handler(MagicMock(), event)

        args = mock_write.call_args
        data = args[0][1]
        assert data["output_preview"] is None
        assert args[1]["task_output"] is None

    def test_on_tool_started(self) -> None:
        from crewai.events import ToolUsageStartedEvent

        listener, handlers = self._setup_and_get_handlers()
        handler = handlers[ToolUsageStartedEvent]

        event = MagicMock(spec=ToolUsageStartedEvent)
        event.tool_name = "web_search"
        event.tool_args = {"query": "AI news"}
        event.agent_role = "Researcher"

        with patch.object(listener, "_write_event") as mock_write:
            handler(MagicMock(), event)

        mock_write.assert_called_once()
        data = mock_write.call_args[0][1]
        assert data["tool_name"] == "web_search"
        assert data["agent_role"] == "Researcher"

    def test_on_tool_started_with_string_args(self) -> None:
        from crewai.events import ToolUsageStartedEvent

        listener, handlers = self._setup_and_get_handlers()
        handler = handlers[ToolUsageStartedEvent]

        event = MagicMock(spec=ToolUsageStartedEvent)
        event.tool_name = "calculator"
        event.tool_args = "2 + 2"
        event.agent_role = "Math"

        with patch.object(listener, "_write_event") as mock_write:
            handler(MagicMock(), event)

        data = mock_write.call_args[0][1]
        assert "2 + 2" in data["tool_args"]

    def test_on_tool_finished(self) -> None:
        from crewai.events import ToolUsageFinishedEvent

        listener, handlers = self._setup_and_get_handlers()
        handler = handlers[ToolUsageFinishedEvent]

        event = MagicMock(spec=ToolUsageFinishedEvent)
        event.tool_name = "web_search"
        event.from_cache = True
        event.started_at = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
        event.finished_at = datetime(2025, 1, 1, 0, 0, 1, tzinfo=UTC)

        with patch.object(listener, "_write_event") as mock_write:
            handler(MagicMock(), event)

        data = mock_write.call_args[0][1]
        assert data["tool_name"] == "web_search"
        assert data["from_cache"] is True
        assert data["duration_ms"] == 1000

    def test_on_tool_finished_without_timing(self) -> None:
        from crewai.events import ToolUsageFinishedEvent

        listener, handlers = self._setup_and_get_handlers()
        handler = handlers[ToolUsageFinishedEvent]

        event = MagicMock(spec=ToolUsageFinishedEvent)
        event.tool_name = "calculator"
        event.from_cache = False
        # Simulate missing timing attributes
        del event.started_at
        del event.finished_at

        with patch.object(listener, "_write_event") as mock_write:
            handler(MagicMock(), event)

        data = mock_write.call_args[0][1]
        assert "duration_ms" not in data

    def test_on_llm_started(self) -> None:
        from crewai.events import LLMCallStartedEvent

        listener, handlers = self._setup_and_get_handlers()
        handler = handlers[LLMCallStartedEvent]

        event = MagicMock(spec=LLMCallStartedEvent)
        event.model = "gpt-4o"
        event.agent_role = "Researcher"

        with patch.object(listener, "_write_event") as mock_write:
            handler(MagicMock(), event)

        data = mock_write.call_args[0][1]
        assert data["model"] == "gpt-4o"
        assert data["agent_role"] == "Researcher"

    def test_on_llm_completed(self) -> None:
        from crewai.events import LLMCallCompletedEvent

        listener, handlers = self._setup_and_get_handlers()
        handler = handlers[LLMCallCompletedEvent]

        event = MagicMock(spec=LLMCallCompletedEvent)
        event.model = "gpt-4o"
        event.usage = {"total_tokens": 500, "prompt_tokens": 400, "completion_tokens": 100}
        event.response = "Here is the analysis..."
        event.started_at = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
        event.finished_at = datetime(2025, 1, 1, 0, 0, 2, tzinfo=UTC)

        with patch.object(listener, "_write_event") as mock_write:
            handler(MagicMock(), event)

        data = mock_write.call_args[0][1]
        assert data["model"] == "gpt-4o"
        assert data["tokens"] == 500
        assert data["response_preview"] is not None
        assert data["duration_ms"] == 2000

    def test_on_llm_completed_with_none_usage(self) -> None:
        from crewai.events import LLMCallCompletedEvent

        listener, handlers = self._setup_and_get_handlers()
        handler = handlers[LLMCallCompletedEvent]

        event = MagicMock(spec=LLMCallCompletedEvent)
        event.model = "gpt-4o"
        event.usage = None
        event.response = None
        del event.started_at
        del event.finished_at

        with patch.object(listener, "_write_event") as mock_write:
            handler(MagicMock(), event)

        data = mock_write.call_args[0][1]
        assert data["tokens"] == 0
        assert data["response_preview"] is None
        assert "duration_ms" not in data

    def test_on_llm_completed_with_non_dict_usage(self) -> None:
        from crewai.events import LLMCallCompletedEvent

        listener, handlers = self._setup_and_get_handlers()
        handler = handlers[LLMCallCompletedEvent]

        event = MagicMock(spec=LLMCallCompletedEvent)
        event.model = "gpt-4o"
        event.usage = "not-a-dict"
        event.response = "response"
        del event.started_at
        del event.finished_at

        with patch.object(listener, "_write_event") as mock_write:
            handler(MagicMock(), event)

        data = mock_write.call_args[0][1]
        # Non-dict usage should yield 0 tokens
        assert data["tokens"] == 0


# ===========================================================================
# execution_listener.py: setup_listeners with OTEL spans
# ===========================================================================


class TestEventHandlersOtelIntegration:
    """Verify OTEL span creation/ending within event handlers."""

    def test_on_crew_started_creates_root_span(self) -> None:
        from crewai.events import CrewKickoffStartedEvent

        listener = _make_listener()
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_tracer.start_span.return_value = mock_span
        listener._otel_tracer = mock_tracer

        handlers: dict[type, Any] = {}
        mock_bus = MagicMock()
        mock_bus.on = lambda ev_type: (lambda fn: handlers.update({ev_type: fn}) or fn)
        listener.setup_listeners(mock_bus)

        event = MagicMock(spec=CrewKickoffStartedEvent)
        event.crew_name = "my-crew"
        event.inputs = {}

        with (
            patch.object(listener, "_write_event"),
            patch("blackbeard.engine.execution_listener.trace"),
        ):
            handlers[CrewKickoffStartedEvent](MagicMock(), event)

        assert listener._otel_root_span is mock_span

    def test_on_task_started_creates_task_span(self) -> None:
        from crewai.events import TaskStartedEvent

        listener = _make_listener()
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_tracer.start_span.return_value = mock_span
        listener._otel_tracer = mock_tracer

        handlers: dict[type, Any] = {}
        mock_bus = MagicMock()
        mock_bus.on = lambda ev_type: (lambda fn: handlers.update({ev_type: fn}) or fn)
        listener.setup_listeners(mock_bus)

        event = MagicMock(spec=TaskStartedEvent)
        event.task_name = "research"
        event.agent_role = "Researcher"

        with (
            patch.object(listener, "_write_event_with_task_update"),
            patch("blackbeard.engine.execution_listener.trace"),
        ):
            handlers[TaskStartedEvent](MagicMock(), event)

        assert "task/research" in listener._otel_active_spans

    def test_on_task_completed_ends_task_span(self) -> None:
        from crewai.events import TaskCompletedEvent

        listener = _make_listener()
        mock_span = MagicMock()
        listener._otel_active_spans["task/research"] = mock_span

        handlers: dict[type, Any] = {}
        mock_bus = MagicMock()
        mock_bus.on = lambda ev_type: (lambda fn: handlers.update({ev_type: fn}) or fn)
        listener.setup_listeners(mock_bus)

        event = MagicMock(spec=TaskCompletedEvent)
        event.task_name = "research"
        event.output = "done"

        with patch.object(listener, "_write_event_with_task_update"):
            handlers[TaskCompletedEvent](MagicMock(), event)

        mock_span.end.assert_called_once()

    def test_on_tool_started_creates_tool_span(self) -> None:
        from crewai.events import ToolUsageStartedEvent

        listener = _make_listener()
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_tracer.start_span.return_value = mock_span
        listener._otel_tracer = mock_tracer

        handlers: dict[type, Any] = {}
        mock_bus = MagicMock()
        mock_bus.on = lambda ev_type: (lambda fn: handlers.update({ev_type: fn}) or fn)
        listener.setup_listeners(mock_bus)

        event = MagicMock(spec=ToolUsageStartedEvent)
        event.tool_name = "web_search"
        event.tool_args = None
        event.agent_role = "R"

        with (
            patch.object(listener, "_write_event"),
            patch("blackbeard.engine.execution_listener.trace"),
        ):
            handlers[ToolUsageStartedEvent](MagicMock(), event)

        assert "tool/web_search" in listener._otel_active_spans

    def test_on_llm_started_creates_llm_span(self) -> None:
        from crewai.events import LLMCallStartedEvent

        listener = _make_listener()
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_tracer.start_span.return_value = mock_span
        listener._otel_tracer = mock_tracer

        handlers: dict[type, Any] = {}
        mock_bus = MagicMock()
        mock_bus.on = lambda ev_type: (lambda fn: handlers.update({ev_type: fn}) or fn)
        listener.setup_listeners(mock_bus)

        event = MagicMock(spec=LLMCallStartedEvent)
        event.model = "gpt-4o"
        event.agent_role = "Researcher"

        with (
            patch.object(listener, "_write_event"),
            patch("blackbeard.engine.execution_listener.trace"),
        ):
            handlers[LLMCallStartedEvent](MagicMock(), event)

        assert "llm/gpt-4o" in listener._otel_active_spans


# ===========================================================================
# execution_listener.py: flush with orphaned OTEL spans
# ===========================================================================


class TestFlushWithOrphanedSpans:
    """Tests for flush() cleaning up orphaned OTEL spans."""

    def test_flush_ends_orphaned_spans(self) -> None:
        from blackbeard.engine.execution_listener import BlackbeardExecutionListener

        eid = uuid.uuid4()
        mock_factory = MagicMock()

        with (
            patch(
                "blackbeard.engine.execution_listener._get_sync_session_factory",
                return_value=mock_factory,
            ),
            patch("blackbeard.engine.execution_listener._get_otel_tracer", return_value=None),
        ):
            listener = BlackbeardExecutionListener(
                execution_id=eid,
                db_url="postgresql+asyncpg://localhost/test",
            )

        mock_span1 = MagicMock()
        mock_span2 = MagicMock()
        mock_root = MagicMock()
        listener._otel_active_spans = {"task/t1": mock_span1, "tool/search": mock_span2}
        listener._otel_root_span = mock_root
        listener._flush_timer = None
        listener._buffer = []

        listener.flush()

        mock_span1.end.assert_called_once()
        mock_span2.end.assert_called_once()
        mock_root.end.assert_called_once()

    def test_flush_handles_span_end_failure(self) -> None:
        from blackbeard.engine.execution_listener import BlackbeardExecutionListener

        eid = uuid.uuid4()
        mock_factory = MagicMock()

        with (
            patch(
                "blackbeard.engine.execution_listener._get_sync_session_factory",
                return_value=mock_factory,
            ),
            patch("blackbeard.engine.execution_listener._get_otel_tracer", return_value=None),
        ):
            listener = BlackbeardExecutionListener(
                execution_id=eid,
                db_url="postgresql+asyncpg://localhost/test",
            )

        mock_span = MagicMock()
        mock_span.end.side_effect = RuntimeError("span already ended")
        listener._otel_active_spans = {"task/t1": mock_span}
        listener._otel_root_span = None
        listener._flush_timer = None
        listener._buffer = []

        # Should not raise
        with patch("blackbeard.engine.execution_listener.logger"):
            listener.flush()

    def test_flush_retries_when_buffer_not_empty(self) -> None:
        from blackbeard.engine.execution_listener import BlackbeardExecutionListener

        eid = uuid.uuid4()
        mock_session = MagicMock()
        mock_session_ctx = MagicMock()
        mock_session_ctx.__enter__ = MagicMock(return_value=mock_session)
        mock_session_ctx.__exit__ = MagicMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_session_ctx)

        with (
            patch(
                "blackbeard.engine.execution_listener._get_sync_session_factory",
                return_value=mock_factory,
            ),
            patch("blackbeard.engine.execution_listener._get_otel_tracer", return_value=None),
        ):
            listener = BlackbeardExecutionListener(
                execution_id=eid,
                db_url="postgresql+asyncpg://localhost/test",
            )

        listener._flush_timer = None
        listener._otel_active_spans = {}
        listener._otel_root_span = None

        # First _flush_buffer: fails and re-queues
        # Second _flush_buffer (retry): succeeds
        mock_event = MagicMock(spec=ExecutionEvent)
        mock_event.sequence = 0
        mock_event.event_type = "test"
        listener._buffer = [mock_event]

        flush_count = 0
        original_flush = listener._flush_buffer

        def tracking_flush() -> None:
            nonlocal flush_count
            flush_count += 1
            if flush_count == 1:
                # First call fails, re-queues
                mock_session.commit.side_effect = RuntimeError("DB error")
                original_flush()
                mock_session.commit.side_effect = None
            else:
                # Subsequent calls succeed
                original_flush()

        with (
            patch.object(listener, "_flush_buffer", side_effect=tracking_flush),
            patch("blackbeard.engine.execution_listener._time.sleep"),
            patch("blackbeard.engine.execution_listener.logger"),
        ):
            listener.flush()

        # Should have been called at least twice (initial + retry)
        assert flush_count >= 2
