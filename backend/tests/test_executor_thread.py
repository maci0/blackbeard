"""Unit tests for background-thread functions in executor and execution_listener.

Covers _run_crew_sync, _run_crew_async, _snapshot_crew_resources,
recover_stale_executions, cleanup_orphaned_keys, and
BlackbeardExecutionListener methods (_flush_buffer, flush,
setup_listeners, _write_event, _deliver_webhooks_sync,
_prepare_webhook_targets, _get_sync_session_factory, dispose_sync_engine).

All external dependencies (DB sessions, CrewAI, LiteLLM, httpx) are mocked.
"""

from __future__ import annotations

import socket
import threading
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from blackbeard.kinds import ResourceKind
from blackbeard.models import (
    Execution,
    ExecutionEvent,
    ExecutionStatus,
    ExecutionType,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_execution_obj(
    *,
    execution_id: uuid.UUID | None = None,
    crew_name: str = "test-crew",
    project: str = "default",
    status: ExecutionStatus = ExecutionStatus.QUEUED,
    started_at: datetime | None = None,
    litellm_key: str | None = None,
) -> Execution:
    """Build a detached Execution object for unit tests."""
    e = MagicMock(spec=Execution)
    e.id = execution_id or uuid.uuid4()
    e.crew_name = crew_name
    e.crew_project = project
    e.status = status
    e.started_at = started_at
    e.completed_at = None
    e.litellm_key = litellm_key
    e.cost_usd = Decimal("0")
    e.total_tokens = 0
    e.prompt_tokens = 0
    e.completion_tokens = 0
    e.outputs = None
    e.error = None
    e.tasks = []
    return e


def _minimal_snapshot(crew_name: str = "test-crew") -> dict[str, dict[str, Any]]:
    """Return a minimal resource snapshot with one crew and one agent."""
    return {
        f"Crew/{crew_name}": {
            "kind": "Crew",
            "name": crew_name,
            "project": "default",
            "spec": {
                "agents": ["ref:agents/test-agent"],
                "tasks": ["ref:tasks/test-task"],
                "process": "sequential",
            },
        },
        "Agent/test-agent": {
            "kind": "Agent",
            "name": "test-agent",
            "project": "default",
            "spec": {
                "role": "Researcher",
                "goal": "Research things",
                "backstory": "Expert researcher",
            },
        },
        "Task/test-task": {
            "kind": "Task",
            "name": "test-task",
            "project": "default",
            "spec": {
                "description": "Do research",
                "expected_output": "Research results",
                "agent": "ref:agents/test-agent",
            },
        },
    }


def _make_listener(
    session: MagicMock | None = None,
    execution_id: uuid.UUID | None = None,
) -> tuple[Any, MagicMock]:
    """Build a BlackbeardExecutionListener with a mocked sync-session factory and no OTEL tracer.

    When ``session`` is given, the factory yields a context manager wrapping it.
    Returns ``(listener, mock_factory)``.
    """
    from blackbeard.engine.execution_listener import BlackbeardExecutionListener

    if session is not None:
        session_ctx = MagicMock()
        session_ctx.__enter__ = MagicMock(return_value=session)
        session_ctx.__exit__ = MagicMock(return_value=False)
        mock_factory: MagicMock = MagicMock(return_value=session_ctx)
    else:
        mock_factory = MagicMock()

    with (
        patch(
            "blackbeard.engine.execution_listener._get_sync_session_factory",
            return_value=mock_factory,
        ),
        patch("blackbeard.engine.execution_listener._get_otel_tracer", return_value=None),
    ):
        listener = BlackbeardExecutionListener(
            execution_id=execution_id or uuid.uuid4(),
            db_url="postgresql+asyncpg://localhost/test",
        )
    return listener, mock_factory


# ===========================================================================
# 1. _run_crew_sync — main background thread entry point
# ===========================================================================


class TestRunCrewSync:
    """Tests for blackbeard.engine.executor._run_crew_sync."""

    def test_creates_event_loop_and_calls_async(self) -> None:
        from blackbeard.engine.executor import _run_crew_sync

        eid = uuid.uuid4()
        snapshot = _minimal_snapshot()
        mock_loop = MagicMock()
        mock_loop.run_until_complete = MagicMock()

        mock_factory = MagicMock()

        with (
            patch("blackbeard.engine.executor.asyncio.new_event_loop", return_value=mock_loop),
            patch("blackbeard.engine.executor._thread_session_factory", return_value=mock_factory),
        ):
            _run_crew_sync(eid, snapshot, "test-crew", {"topic": "AI"})

        mock_loop.run_until_complete.assert_called_once()
        mock_loop.close.assert_called_once()

    def test_closes_loop_on_exception(self) -> None:
        from blackbeard.engine.executor import _run_crew_sync

        eid = uuid.uuid4()
        snapshot = _minimal_snapshot()
        mock_loop = MagicMock()
        mock_loop.run_until_complete.side_effect = RuntimeError("crew exploded")

        mock_factory = MagicMock()

        with (
            patch("blackbeard.engine.executor.asyncio.new_event_loop", return_value=mock_loop),
            patch("blackbeard.engine.executor._thread_session_factory", return_value=mock_factory),
            pytest.raises(RuntimeError, match="crew exploded"),
        ):
            _run_crew_sync(eid, snapshot, "test-crew", {})

        mock_loop.close.assert_called_once()

    def test_passes_execution_type_and_iterations(self) -> None:
        from blackbeard.engine.executor import _run_crew_sync

        eid = uuid.uuid4()
        snapshot = _minimal_snapshot()
        mock_loop = MagicMock()
        mock_factory = MagicMock()

        with (
            patch("blackbeard.engine.executor.asyncio.new_event_loop", return_value=mock_loop),
            patch("blackbeard.engine.executor._thread_session_factory", return_value=mock_factory),
            patch("blackbeard.engine.executor._run_crew_async") as mock_async,
        ):
            _run_crew_sync(
                eid,
                snapshot,
                "test-crew",
                {},
                execution_type=ExecutionType.TRAIN,
                n_iterations=5,
                training_file="my_training.pkl",
            )

        assert mock_loop.run_until_complete.call_count == 1
        # _run_crew_sync passes these kwargs through to _run_crew_async
        kwargs = mock_async.call_args.kwargs
        assert kwargs["execution_type"] == ExecutionType.TRAIN
        assert kwargs["n_iterations"] == 5
        assert kwargs["training_file"] == "my_training.pkl"


# ===========================================================================
# 2. _run_crew_async — the async execution function
# ===========================================================================


class TestRunCrewAsync:
    """Tests for blackbeard.engine.executor._run_crew_async."""

    @pytest.mark.asyncio
    async def test_updates_status_to_running_then_completed(self) -> None:
        from blackbeard.engine.executor import _run_crew_async

        eid = uuid.uuid4()
        snapshot = _minimal_snapshot()

        exec_obj = _make_execution_obj(execution_id=eid)
        exec_obj.status = ExecutionStatus.QUEUED

        mock_session = AsyncMock()

        # _get_execution_for_update returns our mock execution on each call
        status_sequence = [exec_obj, exec_obj, exec_obj]
        call_count = 0

        async def mock_get_exec(session, exec_id):
            nonlocal call_count
            idx = min(call_count, len(status_sequence) - 1)
            call_count += 1
            return status_sequence[idx]

        mock_session_factory = MagicMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory.return_value = mock_session_ctx

        mock_crew = MagicMock()
        mock_crew.kickoff.return_value = MagicMock(
            raw="result text",
            token_usage=MagicMock(total_tokens=100, prompt_tokens=80, completion_tokens=20),
        )
        mock_crew.kickoff.return_value.__class__ = type("CrewOutput", (), {})

        mock_loader = MagicMock()
        mock_loader.build_crew.return_value = mock_crew

        with (
            patch(
                "blackbeard.engine.executor._get_execution_for_update", side_effect=mock_get_exec
            ),
            patch("blackbeard.engine.executor.ResourceLoader", return_value=mock_loader),
            patch("blackbeard.engine.executor._extract_policy_specs", return_value={}),
            patch(
                "blackbeard.engine.executor._derive_budget_and_pii",
                return_value=(None, None, None, None),
            ),
            patch("blackbeard.engine.executor.BlackbeardExecutionListener") as mock_listener_cls,
        ):
            mock_listener = MagicMock()
            mock_listener_cls.return_value = mock_listener

            await _run_crew_async(
                eid,
                snapshot,
                "test-crew",
                {"topic": "AI"},
                mock_session_factory,
            )

        # After successful execution, status should be COMPLETED
        assert exec_obj.status == ExecutionStatus.COMPLETED
        mock_loader.build_crew.assert_called_once_with("test-crew")
        mock_crew.kickoff.assert_called_once_with(inputs={"topic": "AI"})
        mock_listener.flush.assert_called()

    @pytest.mark.asyncio
    async def test_marks_failed_on_crew_exception(self) -> None:
        from blackbeard.engine.executor import _run_crew_async

        eid = uuid.uuid4()
        snapshot = _minimal_snapshot()

        exec_obj = _make_execution_obj(execution_id=eid)
        exec_obj.status = ExecutionStatus.QUEUED

        mock_session = AsyncMock()
        mock_session_factory = MagicMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory.return_value = mock_session_ctx

        mock_crew = MagicMock()
        mock_crew.kickoff.side_effect = RuntimeError("LLM provider down")

        mock_loader = MagicMock()
        mock_loader.build_crew.return_value = mock_crew

        async def mock_get_exec(session, exec_id):
            return exec_obj

        with (
            patch(
                "blackbeard.engine.executor._get_execution_for_update", side_effect=mock_get_exec
            ),
            patch("blackbeard.engine.executor.ResourceLoader", return_value=mock_loader),
            patch("blackbeard.engine.executor._extract_policy_specs", return_value={}),
            patch(
                "blackbeard.engine.executor._derive_budget_and_pii",
                return_value=(None, None, None, None),
            ),
            patch("blackbeard.engine.executor.BlackbeardExecutionListener") as mock_listener_cls,
            patch("blackbeard.engine.executor._sanitize_error", return_value="Execution failed"),
        ):
            mock_listener = MagicMock()
            mock_listener_cls.return_value = mock_listener

            # The function handles exceptions internally and marks execution as failed
            await _run_crew_async(
                eid,
                snapshot,
                "test-crew",
                {},
                mock_session_factory,
            )

        assert exec_obj.status == ExecutionStatus.FAILED
        assert exec_obj.error is not None

    @pytest.mark.asyncio
    async def test_returns_early_if_cancelled_before_start(self) -> None:
        from blackbeard.engine.executor import _run_crew_async

        eid = uuid.uuid4()
        snapshot = _minimal_snapshot()

        exec_obj = _make_execution_obj(execution_id=eid, status=ExecutionStatus.CANCELLED)

        mock_session = AsyncMock()
        mock_session_factory = MagicMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory.return_value = mock_session_ctx

        async def mock_get_exec(session, exec_id):
            return exec_obj

        with (
            patch(
                "blackbeard.engine.executor._get_execution_for_update",
                side_effect=mock_get_exec,
            ),
            patch("blackbeard.engine.executor.ResourceLoader") as mock_loader_cls,
        ):
            await _run_crew_async(
                eid,
                snapshot,
                "test-crew",
                {},
                mock_session_factory,
            )

        assert exec_obj.status == ExecutionStatus.CANCELLED
        mock_loader_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_early_if_execution_not_found(self) -> None:
        from blackbeard.engine.executor import _run_crew_async

        eid = uuid.uuid4()
        snapshot = _minimal_snapshot()

        mock_session = AsyncMock()
        mock_session_factory = MagicMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory.return_value = mock_session_ctx

        async def mock_get_exec(session, exec_id):
            return None

        with (
            patch(
                "blackbeard.engine.executor._get_execution_for_update",
                side_effect=mock_get_exec,
            ),
            patch("blackbeard.engine.executor.logger") as mock_logger,
        ):
            await _run_crew_async(
                eid,
                snapshot,
                "test-crew",
                {},
                mock_session_factory,
            )

        mock_logger.error.assert_called_once()
        assert "not found" in str(mock_logger.error.call_args)

    @pytest.mark.asyncio
    async def test_virtual_key_deleted_in_finally(self) -> None:
        from blackbeard.engine.executor import _run_crew_async

        eid = uuid.uuid4()
        snapshot = _minimal_snapshot()

        exec_obj = _make_execution_obj(execution_id=eid)
        exec_obj.status = ExecutionStatus.QUEUED

        mock_session = AsyncMock()
        mock_session_factory = MagicMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory.return_value = mock_session_ctx

        mock_crew = MagicMock()
        mock_crew.kickoff.return_value = MagicMock(
            raw="done",
            token_usage=MagicMock(total_tokens=50, prompt_tokens=30, completion_tokens=20),
        )

        mock_loader = MagicMock()
        mock_loader.build_crew.return_value = mock_crew

        mock_key_mgr = AsyncMock()
        mock_key_mgr.create_key.return_value = {"key": "sk-virt-123"}
        mock_key_mgr.delete_key.return_value = True

        async def mock_get_exec(session, exec_id):
            return exec_obj

        with (
            patch(
                "blackbeard.engine.executor._get_execution_for_update", side_effect=mock_get_exec
            ),
            patch("blackbeard.engine.executor.ResourceLoader", return_value=mock_loader),
            patch("blackbeard.engine.executor._extract_policy_specs", return_value={}),
            patch(
                "blackbeard.engine.executor._derive_budget_and_pii",
                return_value=(10.0, 5000, None, None),
            ),
            patch("blackbeard.engine.executor.BlackbeardExecutionListener") as mock_listener_cls,
            patch("blackbeard.litellm.key_manager.VirtualKeyManager", return_value=mock_key_mgr),
        ):
            mock_listener = MagicMock()
            mock_listener_cls.return_value = mock_listener

            await _run_crew_async(
                eid,
                snapshot,
                "test-crew",
                {},
                mock_session_factory,
            )

        # Virtual key should be deleted in finally block
        mock_key_mgr.delete_key.assert_called_once_with("sk-virt-123")

    @pytest.mark.asyncio
    async def test_train_execution_calls_crew_train(self) -> None:
        from blackbeard.engine.executor import _run_crew_async

        eid = uuid.uuid4()
        snapshot = _minimal_snapshot()

        exec_obj = _make_execution_obj(execution_id=eid)
        exec_obj.status = ExecutionStatus.QUEUED

        mock_session = AsyncMock()
        mock_session_factory = MagicMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory.return_value = mock_session_ctx

        mock_crew = MagicMock()
        mock_crew.train.return_value = None

        mock_loader = MagicMock()
        mock_loader.build_crew.return_value = mock_crew

        async def mock_get_exec(session, exec_id):
            return exec_obj

        with (
            patch(
                "blackbeard.engine.executor._get_execution_for_update", side_effect=mock_get_exec
            ),
            patch("blackbeard.engine.executor.ResourceLoader", return_value=mock_loader),
            patch("blackbeard.engine.executor._extract_policy_specs", return_value={}),
            patch(
                "blackbeard.engine.executor._derive_budget_and_pii",
                return_value=(None, None, None, None),
            ),
            patch("blackbeard.engine.executor.BlackbeardExecutionListener") as mock_listener_cls,
        ):
            mock_listener = MagicMock()
            mock_listener_cls.return_value = mock_listener

            await _run_crew_async(
                eid,
                snapshot,
                "test-crew",
                {"topic": "AI"},
                mock_session_factory,
                execution_type=ExecutionType.TRAIN,
                n_iterations=3,
                training_file="train.pkl",
            )

        mock_crew.train.assert_called_once_with(
            n_iterations=3,
            inputs={"topic": "AI"},
            filename="train.pkl",
        )


# ===========================================================================
# 3. _snapshot_crew_resources
# ===========================================================================


class TestSnapshotCrewResources:
    """Tests for blackbeard.engine.executor._snapshot_crew_resources."""

    def test_returns_dict_keyed_by_kind_name(self) -> None:
        from blackbeard.engine.executor import _snapshot_crew_resources

        crew_res = MagicMock(spec=["kind", "name", "project", "spec"])
        crew_res.kind = ResourceKind.CREW
        crew_res.name = "my-crew"
        crew_res.project = "default"
        crew_res.spec = {"agents": [], "tasks": [], "process": "sequential"}

        resources = {"Crew/my-crew": crew_res}
        result = _snapshot_crew_resources(resources, "my-crew")

        assert "Crew/my-crew" in result
        assert result["Crew/my-crew"]["kind"] == "Crew"
        assert result["Crew/my-crew"]["name"] == "my-crew"

    def test_resolves_refs_recursively(self) -> None:
        from blackbeard.engine.executor import _snapshot_crew_resources

        crew_res = MagicMock(spec=["kind", "name", "project", "spec"])
        crew_res.kind = ResourceKind.CREW
        crew_res.name = "my-crew"
        crew_res.project = "default"
        crew_res.spec = {
            "agents": ["ref:agents/researcher"],
            "tasks": ["ref:tasks/research"],
            "process": "sequential",
        }

        agent_res = MagicMock(spec=["kind", "name", "project", "spec"])
        agent_res.kind = ResourceKind.AGENT
        agent_res.name = "researcher"
        agent_res.project = "default"
        agent_res.spec = {
            "role": "Researcher",
            "goal": "Research",
            "backstory": "Expert",
            "llm": "ref:llm-connections/gpt4",
        }

        task_res = MagicMock(spec=["kind", "name", "project", "spec"])
        task_res.kind = ResourceKind.TASK
        task_res.name = "research"
        task_res.project = "default"
        task_res.spec = {
            "description": "Research AI",
            "expected_output": "Report",
            "agent": "ref:agents/researcher",
        }

        llm_res = MagicMock(spec=["kind", "name", "project", "spec"])
        llm_res.kind = ResourceKind.LLM_CONNECTION
        llm_res.name = "gpt4"
        llm_res.project = "default"
        llm_res.spec = {"provider": "openai", "model": "gpt-4o"}

        resources = {
            "Crew/my-crew": crew_res,
            "Agent/researcher": agent_res,
            "Task/research": task_res,
            "LLMConnection/gpt4": llm_res,
        }
        result = _snapshot_crew_resources(resources, "my-crew")

        assert "Crew/my-crew" in result
        assert "Agent/researcher" in result
        assert "Task/research" in result
        assert "LLMConnection/gpt4" in result

    def test_excludes_unreferenced_resources(self) -> None:
        from blackbeard.engine.executor import _snapshot_crew_resources

        crew_res = MagicMock(spec=["kind", "name", "project", "spec"])
        crew_res.kind = ResourceKind.CREW
        crew_res.name = "my-crew"
        crew_res.project = "default"
        crew_res.spec = {"agents": [], "tasks": [], "process": "sequential"}

        other_res = MagicMock(spec=["kind", "name", "project", "spec"])
        other_res.kind = ResourceKind.AGENT
        other_res.name = "unused-agent"
        other_res.project = "default"
        other_res.spec = {"role": "Unused", "goal": "N/A", "backstory": "N/A"}

        resources = {
            "Crew/my-crew": crew_res,
            "Agent/unused-agent": other_res,
        }
        result = _snapshot_crew_resources(resources, "my-crew")

        assert "Crew/my-crew" in result
        assert "Agent/unused-agent" not in result


# ===========================================================================
# 4. recover_stale_executions
# ===========================================================================


class TestRecoverStaleExecutions:
    """Tests for blackbeard.engine.executor.recover_stale_executions."""

    @pytest.mark.asyncio
    async def test_marks_running_executions_as_failed(self) -> None:
        from blackbeard.engine.executor import recover_stale_executions

        stale_ids = [uuid.uuid4(), uuid.uuid4()]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value = stale_ids
        mock_session.execute.return_value = mock_result
        mock_session.commit = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("blackbeard.engine.executor.async_session", return_value=mock_ctx),
            patch("blackbeard.engine.executor.cleanup_orphaned_keys", new_callable=AsyncMock),
        ):
            count = await recover_stale_executions()

        assert count == 2
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_stale(self) -> None:
        from blackbeard.engine.executor import recover_stale_executions

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value = []
        mock_session.execute.return_value = mock_result
        mock_session.commit = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("blackbeard.engine.executor.async_session", return_value=mock_ctx),
            patch("blackbeard.engine.executor.cleanup_orphaned_keys", new_callable=AsyncMock),
        ):
            count = await recover_stale_executions()

        assert count == 0

    @pytest.mark.asyncio
    async def test_continues_on_orphan_key_cleanup_failure(self) -> None:
        from blackbeard.engine.executor import recover_stale_executions

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value = []
        mock_session.execute.return_value = mock_result
        mock_session.commit = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("blackbeard.engine.executor.async_session", return_value=mock_ctx),
            patch(
                "blackbeard.engine.executor.cleanup_orphaned_keys",
                new_callable=AsyncMock,
                side_effect=RuntimeError("LiteLLM unreachable"),
            ),
        ):
            count = await recover_stale_executions()

        assert count == 0
        mock_session.commit.assert_called_once()


# ===========================================================================
# 5. cleanup_orphaned_keys
# ===========================================================================


class TestCleanupOrphanedKeys:
    """Tests for blackbeard.engine.executor.cleanup_orphaned_keys."""

    @pytest.mark.asyncio
    async def test_deletes_keys_for_stale_executions(self) -> None:
        from blackbeard.engine.executor import cleanup_orphaned_keys

        exec1 = MagicMock()
        exec1.id = uuid.uuid4()
        exec1.litellm_key = "sk-orphan-1"

        exec2 = MagicMock()
        exec2.id = uuid.uuid4()
        exec2.litellm_key = "sk-orphan-2"

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value = [exec1, exec2]
        mock_session.execute.return_value = mock_result

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_key_mgr = AsyncMock()
        mock_key_mgr.delete_key.return_value = True

        with (
            patch("blackbeard.engine.executor.async_session", return_value=mock_ctx),
            patch("blackbeard.litellm.key_manager.VirtualKeyManager", return_value=mock_key_mgr),
        ):
            count = await cleanup_orphaned_keys()

        assert count == 2
        assert mock_key_mgr.delete_key.call_count == 2

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_stale_keys(self) -> None:
        from blackbeard.engine.executor import cleanup_orphaned_keys

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value = []
        mock_session.execute.return_value = mock_result

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_key_mgr = AsyncMock()

        with (
            patch("blackbeard.engine.executor.async_session", return_value=mock_ctx),
            patch("blackbeard.litellm.key_manager.VirtualKeyManager", return_value=mock_key_mgr),
        ):
            count = await cleanup_orphaned_keys()

        assert count == 0
        mock_key_mgr.delete_key.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_key_deletion_failure(self) -> None:
        from blackbeard.engine.executor import cleanup_orphaned_keys

        exec1 = MagicMock()
        exec1.id = uuid.uuid4()
        exec1.litellm_key = "sk-fail"

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value = [exec1]
        mock_session.execute.return_value = mock_result

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_key_mgr = AsyncMock()
        mock_key_mgr.delete_key.return_value = False

        with (
            patch("blackbeard.engine.executor.async_session", return_value=mock_ctx),
            patch("blackbeard.litellm.key_manager.VirtualKeyManager", return_value=mock_key_mgr),
        ):
            count = await cleanup_orphaned_keys()

        assert count == 0


# ===========================================================================
# 6. BlackbeardExecutionListener.__init__
# ===========================================================================


class TestListenerInit:
    """Tests for BlackbeardExecutionListener initialization."""

    def test_init_sets_fields(self) -> None:
        from blackbeard.engine.execution_listener import BlackbeardExecutionListener

        eid = uuid.uuid4()
        db_url = "postgresql+asyncpg://localhost/test"
        pii_config = {"enabled": True, "entities": ["EMAIL"]}

        with (
            patch("blackbeard.engine.execution_listener._get_sync_session_factory") as mock_sf,
            patch("blackbeard.engine.execution_listener._get_otel_tracer", return_value=None),
        ):
            mock_sf.return_value = MagicMock()
            listener = BlackbeardExecutionListener(
                execution_id=eid,
                db_url=db_url,
                pii_config=pii_config,
            )

        assert listener._execution_id == eid
        assert listener._db_url == db_url
        assert listener._pii_config == pii_config
        assert listener._pii_redact_events is True
        assert listener._pii_entities == ["EMAIL"]
        assert listener._seq == 0
        assert listener._buffer == []

    def test_init_without_pii_config(self) -> None:
        from blackbeard.engine.execution_listener import BlackbeardExecutionListener

        eid = uuid.uuid4()

        with (
            patch("blackbeard.engine.execution_listener._get_sync_session_factory") as mock_sf,
            patch("blackbeard.engine.execution_listener._get_otel_tracer", return_value=None),
        ):
            mock_sf.return_value = MagicMock()
            listener = BlackbeardExecutionListener(
                execution_id=eid,
                db_url="postgresql+asyncpg://localhost/test",
            )

        assert listener._pii_config is None
        assert listener._pii_redact_events is False
        assert listener._pii_entities is None


# ===========================================================================
# 7. _flush_buffer
# ===========================================================================


class TestFlushBuffer:
    """Tests for BlackbeardExecutionListener._flush_buffer."""

    def test_flushes_events_to_db(self) -> None:
        mock_session = MagicMock()
        listener, _ = _make_listener(session=mock_session)

        # Put events in buffer
        event1 = MagicMock(spec=ExecutionEvent)
        event2 = MagicMock(spec=ExecutionEvent)
        listener._buffer = [event1, event2]

        listener._flush_buffer()

        mock_session.add_all.assert_called_once_with([event1, event2])
        mock_session.commit.assert_called_once()
        assert listener._buffer == []

    def test_noop_when_buffer_empty(self) -> None:
        listener, mock_factory = _make_listener()

        listener._buffer = []
        listener._flush_buffer()

        # Session factory should not have been called (no DB interaction)
        mock_factory.assert_not_called()

    def test_requeues_events_on_db_error(self) -> None:
        mock_session = MagicMock()
        mock_session.commit.side_effect = RuntimeError("DB connection lost")
        listener, _ = _make_listener(session=mock_session)

        event = MagicMock(spec=ExecutionEvent)
        event.sequence = 0
        event.event_type = "test_event"
        listener._buffer = [event]

        listener._flush_buffer()

        # Events should be re-queued back to buffer
        assert len(listener._buffer) == 1
        assert listener._buffer[0] is event

        # Failure schedules a retry timer; cancel it so no background thread
        # keeps retrying the failing flush after this test ends.
        assert listener._flush_timer is not None
        listener._flush_timer.cancel()


# ===========================================================================
# 8. flush (final flush with timer cancellation)
# ===========================================================================


class TestFlush:
    """Tests for BlackbeardExecutionListener.flush."""

    def test_cancels_timer_and_flushes(self) -> None:
        mock_session = MagicMock()
        listener, _ = _make_listener(session=mock_session)

        # Set up a mock timer
        mock_timer = MagicMock()
        listener._flush_timer = mock_timer

        # Put an event in the buffer
        event = MagicMock(spec=ExecutionEvent)
        event.sequence = 0
        listener._buffer = [event]

        listener.flush()

        mock_timer.cancel.assert_called_once()
        mock_timer.join.assert_called_once_with(timeout=5.0)
        # Buffer should be flushed
        mock_session.add_all.assert_called()

    def test_flush_with_no_timer(self) -> None:
        listener, mock_factory = _make_listener()

        listener._flush_timer = None
        listener._buffer = []

        # Should not raise, and must not touch the DB when there is nothing to flush.
        listener.flush()
        mock_factory.assert_not_called()


# ===========================================================================
# 9. setup_listeners
# ===========================================================================


class TestSetupListeners:
    """Tests for BlackbeardExecutionListener.setup_listeners."""

    def test_registers_all_event_handlers(self) -> None:
        listener, _ = _make_listener()

        mock_bus = MagicMock()
        # Mock the .on() decorator to capture event types
        registered_events = []

        def fake_on(event_type):
            registered_events.append(event_type)
            return lambda fn: fn

        mock_bus.on = fake_on

        listener.setup_listeners(mock_bus)

        from crewai.events import (
            CrewKickoffCompletedEvent,
            CrewKickoffStartedEvent,
            LLMCallCompletedEvent,
            LLMCallStartedEvent,
            TaskCompletedEvent,
            TaskStartedEvent,
            ToolUsageFinishedEvent,
            ToolUsageStartedEvent,
        )

        expected_events = {
            CrewKickoffStartedEvent,
            CrewKickoffCompletedEvent,
            TaskStartedEvent,
            TaskCompletedEvent,
            ToolUsageStartedEvent,
            ToolUsageFinishedEvent,
            LLMCallStartedEvent,
            LLMCallCompletedEvent,
        }
        assert set(registered_events) == expected_events


class TestListenerClose:
    """Tests for BlackbeardExecutionListener.close() bus teardown."""

    def test_close_unregisters_all_handlers(self) -> None:
        listener, _ = _make_listener()

        mock_bus = MagicMock()
        handlers: dict[type, Any] = {}

        def fake_on(event_type):
            def decorator(fn: Any) -> Any:
                handlers[event_type] = fn
                return fn

            return decorator

        mock_bus.on = fake_on

        listener.setup_listeners(mock_bus)
        assert len(handlers) == 8

        unregistered: list[tuple[type, Any]] = []
        mock_bus.off = lambda event_type, handler: unregistered.append((event_type, handler))

        listener.close()

        assert sorted(unregistered, key=lambda p: id(p[1])) == sorted(
            handlers.items(), key=lambda p: id(p[1])
        )
        assert {evt for evt, _ in unregistered} == set(handlers)

    def test_close_is_idempotent(self) -> None:
        listener, _ = _make_listener()
        mock_bus = MagicMock()

        def fake_on(event_type):
            return lambda fn: fn

        mock_bus.on = fake_on
        mock_bus.off = MagicMock()
        listener.setup_listeners(mock_bus)

        listener.close()
        assert mock_bus.off.call_count == 8

        listener.close()
        assert mock_bus.off.call_count == 8

    def test_close_swallows_unregister_errors(self) -> None:
        listener, _ = _make_listener()
        mock_bus = MagicMock()

        def fake_on(event_type):
            return lambda fn: fn

        mock_bus.on = fake_on

        def failing_off(event_type: type, handler: Any) -> None:
            raise RuntimeError("bus gone")

        mock_bus.off = failing_off
        listener.setup_listeners(mock_bus)

        # Must not raise and must drain the registration list.
        listener.close()
        assert listener._registered_handlers == []


# ===========================================================================
# 10. _write_event (_record_event equivalent)
# ===========================================================================


class TestWriteEvent:
    """Tests for BlackbeardExecutionListener._write_event."""

    def test_increments_sequence_counter(self) -> None:
        listener, _ = _make_listener()

        with patch.object(listener, "_dispatch_webhook"), patch.object(listener, "_schedule_flush"):
            listener._write_event("test_event", {"key": "value1"})
            listener._write_event("test_event", {"key": "value2"})

        assert listener._seq == 2
        assert len(listener._buffer) == 2
        assert listener._buffer[0].sequence == 0
        assert listener._buffer[1].sequence == 1

    def test_triggers_flush_when_buffer_full(self) -> None:
        listener, _ = _make_listener()

        with (
            patch.object(listener, "_dispatch_webhook"),
            patch.object(listener, "_flush_buffer") as mock_flush,
        ):
            # Fill buffer to _MAX_BUFFER - 1
            for i in range(listener._MAX_BUFFER - 1):
                listener._buffer.append(MagicMock(spec=ExecutionEvent))
                listener._seq = i + 1

            # This event should trigger flush
            listener._write_event("overflow_event", {"data": "x"})

        mock_flush.assert_called_once()

    def test_buffers_event_with_correct_data(self) -> None:
        eid = uuid.uuid4()
        listener, _ = _make_listener(execution_id=eid)

        with patch.object(listener, "_dispatch_webhook"), patch.object(listener, "_schedule_flush"):
            listener._write_event("crew_started", {"crew_name": "test-crew"})

        assert len(listener._buffer) == 1
        event = listener._buffer[0]
        assert event.event_type == "crew_started"
        assert event.data == {"crew_name": "test-crew"}
        assert event.execution_id == eid


# ===========================================================================
# 11. _deliver_webhooks_sync
# ===========================================================================


class TestDeliverWebhooksSync:
    """Tests for blackbeard.engine.execution_listener._deliver_webhooks_sync."""

    def test_delivers_to_matching_webhooks(self) -> None:
        from blackbeard.engine.execution_listener import _deliver_webhooks_sync

        mock_webhook = MagicMock()
        mock_webhook.url = "https://example.com/hook"
        mock_webhook.secret = "test-secret"
        mock_webhook.id = "wh-1"

        payload = '{"event_type":"crew_completed","execution_id":"exec-1","data":{}}'

        with (
            patch(
                "blackbeard.engine.execution_listener._prepare_webhook_targets",
                return_value=(payload, [mock_webhook]),
            ),
            patch("blackbeard.engine.execution_listener._deliver_single_webhook") as mock_deliver,
        ):
            _deliver_webhooks_sync("crew_completed", {}, "exec-1", "postgresql://localhost/test")

        mock_deliver.assert_called_once_with(
            mock_webhook, payload, "crew_completed", execution_id="exec-1"
        )

    def test_skips_when_no_targets(self) -> None:
        from blackbeard.engine.execution_listener import _deliver_webhooks_sync

        with (
            patch(
                "blackbeard.engine.execution_listener._prepare_webhook_targets",
                return_value=("", []),
            ),
            patch("blackbeard.engine.execution_listener._deliver_single_webhook") as mock_deliver,
        ):
            _deliver_webhooks_sync("crew_completed", {}, "exec-1", "postgresql://localhost/test")

        mock_deliver.assert_not_called()


# ===========================================================================
# 12. _prepare_webhook_targets
# ===========================================================================


class TestPrepareWebhookTargets:
    """Tests for blackbeard.engine.execution_listener._prepare_webhook_targets."""

    def test_filters_by_event_type(self) -> None:
        from blackbeard.engine.execution_listener import _prepare_webhook_targets

        wh_match = MagicMock()
        wh_match.events = ["crew_completed"]
        wh_match.url = "https://example.com/hook"
        wh_match.id = "wh-1"
        wh_match.secret = "s1"

        wh_no_match = MagicMock()
        wh_no_match.events = ["task_started"]
        wh_no_match.url = "https://other.com/hook"
        wh_no_match.id = "wh-2"
        wh_no_match.secret = "s2"

        with (
            patch(
                "blackbeard.engine.execution_listener._get_cached_webhooks",
                return_value=[wh_match, wh_no_match],
            ),
            patch(
                "blackbeard.engine.execution_listener._get_webhook_hostname",
                return_value="example.com",
            ),
        ):
            payload, targets = _prepare_webhook_targets(
                "crew_completed", {"result": "ok"}, "exec-1", "db-url"
            )

        assert len(targets) == 1
        assert targets[0] is wh_match
        assert payload  # non-empty payload

    def test_returns_empty_when_no_webhooks(self) -> None:
        from blackbeard.engine.execution_listener import _prepare_webhook_targets

        with patch(
            "blackbeard.engine.execution_listener._get_cached_webhooks",
            return_value=[],
        ):
            payload, targets = _prepare_webhook_targets("crew_completed", {}, "exec-1", "db-url")

        assert payload == ""
        assert targets == []

    def test_blocks_ssrf_targets(self) -> None:
        from blackbeard.engine.execution_listener import _prepare_webhook_targets

        wh = MagicMock()
        wh.events = None  # matches all events
        wh.url = "https://localhost/internal"
        wh.id = "wh-ssrf"
        wh.secret = "s"

        with (
            patch(
                "blackbeard.engine.execution_listener._get_cached_webhooks",
                return_value=[wh],
            ),
            patch(
                "blackbeard.engine.execution_listener._get_webhook_hostname",
                return_value=None,  # blocked
            ),
        ):
            payload, targets = _prepare_webhook_targets("crew_completed", {}, "exec-1", "db-url")

        assert targets == []
        assert payload == ""


# ===========================================================================
# 12b. _get_webhook_hostname (delivery-time SSRF re-check)
# ===========================================================================


class TestGetWebhookHostname:
    """Tests for blackbeard.engine.execution_listener._get_webhook_hostname."""

    def test_internal_host_blocked(self) -> None:
        import blackbeard.engine.execution_listener as el

        el._webhook_host_cache.clear()
        with patch.object(el, "host_resolves_external", return_value=True):
            assert el._get_webhook_hostname("https://169.254.169.254/hook") is None
            assert el._get_webhook_hostname("https://localhost/hook") is None

    def test_dns_rebind_to_internal_blocked(self) -> None:
        """A public-looking name that resolves internal at delivery time is blocked."""
        import blackbeard.engine.execution_listener as el

        el._webhook_host_cache.clear()
        with patch.object(el, "host_resolves_external", return_value=False):
            assert el._get_webhook_hostname("https://evil.example.com/hook") is None

    def test_safe_external_host_returned(self) -> None:
        import blackbeard.engine.execution_listener as el

        el._webhook_host_cache.clear()
        with patch.object(el, "host_resolves_external", return_value=True):
            assert el._get_webhook_hostname("https://hooks.example.com/hook") == "hooks.example.com"

    def test_unresolvable_host_blocked(self) -> None:
        """Fail closed when delivery-time DNS resolution errors."""
        import blackbeard.engine.execution_listener as el
        from blackbeard.resources import validator

        el._webhook_host_cache.clear()
        validator._delivery_dns_cache.clear()

        def _boom(*args: object, **kwargs: object) -> list[object]:
            raise socket.gaierror(1, "Name or service not known")

        with patch.object(validator.socket, "getaddrinfo", _boom):
            assert el._get_webhook_hostname("https://unresolvable.invalid/hook") is None


# ===========================================================================
# 13. _get_sync_session_factory
# ===========================================================================


class TestGetSyncSessionFactory:
    """Tests for blackbeard.engine.execution_listener._get_sync_session_factory."""

    def test_creates_session_factory(self) -> None:
        import blackbeard.engine.execution_listener as mod

        original_engine = mod._sync_engine
        original_factory = mod._sync_session_factory
        try:
            mod._sync_engine = None
            mod._sync_session_factory = None

            mock_engine = MagicMock()
            mock_engine.sync_engine = MagicMock()

            with (
                patch(
                    "blackbeard.engine.execution_listener.create_engine", return_value=mock_engine
                ),
                patch("blackbeard.engine.execution_listener.sessionmaker") as mock_sm,
                patch("blackbeard.models.database.instrument_engine"),
            ):
                mock_sm.return_value = MagicMock()
                factory = mod._get_sync_session_factory(
                    "postgresql+asyncpg://localhost:5432/testdb"
                )

            assert factory is not None
        finally:
            mod._sync_engine = original_engine
            mod._sync_session_factory = original_factory

    def test_returns_cached_factory(self) -> None:
        import blackbeard.engine.execution_listener as mod

        original_engine = mod._sync_engine
        original_factory = mod._sync_session_factory
        try:
            mock_factory = MagicMock()
            mod._sync_session_factory = mock_factory
            mod._sync_engine = MagicMock()

            result = mod._get_sync_session_factory("postgresql+asyncpg://localhost/test")
            assert result is mock_factory
        finally:
            mod._sync_engine = original_engine
            mod._sync_session_factory = original_factory


# ===========================================================================
# 14. dispose_sync_engine
# ===========================================================================


class TestDisposeSyncEngine:
    """Tests for blackbeard.engine.execution_listener.dispose_sync_engine."""

    def test_disposes_engine_and_clears_factory(self) -> None:
        import blackbeard.engine.execution_listener as mod

        original_engine = mod._sync_engine
        original_factory = mod._sync_session_factory
        try:
            mock_engine = MagicMock()
            mod._sync_engine = mock_engine
            mod._sync_session_factory = MagicMock()

            mod.dispose_sync_engine()

            assert mod._sync_engine is None
            assert mod._sync_session_factory is None
            mock_engine.dispose.assert_called_once()
        finally:
            mod._sync_engine = original_engine
            mod._sync_session_factory = original_factory

    def test_noop_when_no_engine(self) -> None:
        import blackbeard.engine.execution_listener as mod

        original_engine = mod._sync_engine
        original_factory = mod._sync_session_factory
        try:
            mod._sync_engine = None
            mod._sync_session_factory = None

            # Should not raise
            mod.dispose_sync_engine()

            assert mod._sync_engine is None
            assert mod._sync_session_factory is None
        finally:
            mod._sync_engine = original_engine
            mod._sync_session_factory = original_factory


# ===========================================================================
# 15. _resolve_eval_llm
# ===========================================================================


class TestResolveEvalLlm:
    """Tests for blackbeard.engine.executor._resolve_eval_llm."""

    def test_uses_manager_llm_when_available(self) -> None:
        from blackbeard.engine.executor import _resolve_eval_llm

        mock_llm = MagicMock()
        mock_llm.model = "gpt-4-turbo"
        loader = MagicMock()
        loader.build_llm.return_value = mock_llm

        snapshot = {
            "Crew/my-crew": {
                "kind": "Crew",
                "name": "my-crew",
                "project": "default",
                "spec": {
                    "manager_llm": "ref:llm-connections/turbo",
                    "agents": [],
                },
            },
        }

        result = _resolve_eval_llm(loader, snapshot, "my-crew")
        assert result == "gpt-4-turbo"

    def test_falls_back_to_agent_llm(self) -> None:
        from blackbeard.engine.executor import _resolve_eval_llm

        mock_llm = MagicMock()
        mock_llm.model = "claude-3-sonnet"
        loader = MagicMock()
        loader.build_llm.return_value = mock_llm

        snapshot = {
            "Crew/my-crew": {
                "kind": "Crew",
                "name": "my-crew",
                "project": "default",
                "spec": {
                    "agents": ["ref:agents/researcher"],
                },
            },
            "Agent/researcher": {
                "kind": "Agent",
                "name": "researcher",
                "project": "default",
                "spec": {
                    "llm": "ref:llm-connections/claude",
                },
            },
        }

        result = _resolve_eval_llm(loader, snapshot, "my-crew")
        assert result == "claude-3-sonnet"

    def test_defaults_to_gpt4o(self) -> None:
        from blackbeard.engine.executor import _resolve_eval_llm

        loader = MagicMock()

        snapshot = {
            "Crew/my-crew": {
                "kind": "Crew",
                "name": "my-crew",
                "project": "default",
                "spec": {"agents": []},
            },
        }

        result = _resolve_eval_llm(loader, snapshot, "my-crew")
        assert result == "gpt-4o"


# ===========================================================================
# 16. _snapshot_resource
# ===========================================================================


class TestSnapshotResource:
    """Tests for blackbeard.engine.executor._snapshot_resource."""

    def test_snapshots_all_fields(self) -> None:
        from blackbeard.engine.executor import _snapshot_resource

        resource = MagicMock()
        resource.kind = ResourceKind.AGENT
        resource.name = "my-agent"
        resource.project = "default"
        resource.spec = {"role": "Researcher", "goal": "Research"}

        result = _snapshot_resource(resource)

        assert result == {
            "kind": "Agent",
            "name": "my-agent",
            "project": "default",
            "spec": {"role": "Researcher", "goal": "Research"},
        }

    def test_handles_none_spec(self) -> None:
        from blackbeard.engine.executor import _snapshot_resource

        resource = MagicMock()
        resource.kind = ResourceKind.CREW
        resource.name = "my-crew"
        resource.project = "default"
        resource.spec = None

        result = _snapshot_resource(resource)

        assert result["spec"] == {}


# ===========================================================================
# 17. _build_principal_chain
# ===========================================================================


class TestBuildPrincipalChain:
    """Tests for blackbeard.engine.executor._build_principal_chain."""

    def test_builds_chain_with_user(self) -> None:
        from blackbeard.engine.executor import _build_principal_chain

        user = MagicMock()
        user.id = uuid.uuid4()

        agent_mock = MagicMock()
        agent_mock.name = "researcher"
        agent_mock.spec = {"serviceAccount": "sa-research"}

        resources: dict[str, Any] = {
            "Agent/researcher": agent_mock,
        }

        chain = _build_principal_chain(user, "my-crew", resources)

        assert chain["user"]["id"] == str(user.id)
        assert chain["crew"] == "my-crew"
        assert len(chain["agents"]) == 1
        assert chain["agents"][0]["name"] == "researcher"
        assert chain["agents"][0]["serviceAccount"] == "sa-research"

    def test_builds_chain_without_user(self) -> None:
        from blackbeard.engine.executor import _build_principal_chain

        resources: dict[str, Any] = {}

        chain = _build_principal_chain(None, "my-crew", resources)

        assert "user" not in chain
        assert chain["crew"] == "my-crew"
        assert chain["agents"] == []

    def test_default_service_account(self) -> None:
        from blackbeard.engine.executor import _build_principal_chain

        agent_mock = MagicMock()
        agent_mock.name = "writer"
        agent_mock.spec = {}  # No serviceAccount specified

        resources: dict[str, Any] = {
            "Agent/writer": agent_mock,
        }

        chain = _build_principal_chain(None, "my-crew", resources)

        assert chain["agents"][0]["serviceAccount"] == "sa-writer"


# ===========================================================================
# 18. _fail_pending_tasks
# ===========================================================================


class TestFailPendingTasks:
    """Tests for blackbeard.engine.executor._fail_pending_tasks."""

    @pytest.mark.asyncio
    async def test_updates_pending_tasks(self) -> None:
        from blackbeard.engine.executor import _fail_pending_tasks

        eid = uuid.uuid4()
        now = datetime.now(UTC)
        mock_session = AsyncMock()

        await _fail_pending_tasks(mock_session, eid, "Execution failed", now)

        mock_session.execute.assert_called_once()


# ===========================================================================
# 19. _mark_failed_async
# ===========================================================================


class TestMarkFailedAsync:
    """Tests for blackbeard.engine.executor._mark_failed_async."""

    @pytest.mark.asyncio
    async def test_marks_queued_execution_as_failed(self) -> None:
        from blackbeard.engine.executor import _mark_failed_async

        eid = uuid.uuid4()
        exec_obj = _make_execution_obj(execution_id=eid, status=ExecutionStatus.QUEUED)

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = exec_obj
        mock_session.execute.return_value = mock_result
        mock_session.commit = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("blackbeard.engine.executor.async_session", return_value=mock_ctx),
            patch("blackbeard.engine.executor._fail_pending_tasks", new_callable=AsyncMock),
        ):
            await _mark_failed_async(eid, "Thread crashed")

        assert exec_obj.status == ExecutionStatus.FAILED
        assert exec_obj.error == "Thread crashed"

    @pytest.mark.asyncio
    async def test_skips_already_terminal(self) -> None:
        from blackbeard.engine.executor import _mark_failed_async

        eid = uuid.uuid4()
        exec_obj = _make_execution_obj(execution_id=eid, status=ExecutionStatus.COMPLETED)

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = exec_obj
        mock_session.execute.return_value = mock_result

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("blackbeard.engine.executor.async_session", return_value=mock_ctx):
            await _mark_failed_async(eid, "Should not apply")

        # Status should remain COMPLETED, not changed to FAILED
        assert exec_obj.status == ExecutionStatus.COMPLETED
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_missing_execution(self) -> None:
        from blackbeard.engine.executor import _mark_failed_async

        eid = uuid.uuid4()

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("blackbeard.engine.executor.async_session", return_value=mock_ctx):
            # Should not raise, and must not commit anything for a missing execution.
            await _mark_failed_async(eid, "Execution missing")
        mock_session.commit.assert_not_called()


# ===========================================================================
# 20. _renumber_events
# ===========================================================================


class TestRenumberEvents:
    """Tests for BlackbeardExecutionListener._renumber_events."""

    def test_renumbers_from_db_max(self) -> None:
        mock_result = MagicMock()
        mock_result.scalar.return_value = 5  # max sequence in DB is 5
        mock_session = MagicMock()
        mock_session.execute.return_value = mock_result
        listener, _ = _make_listener(session=mock_session)

        events = [MagicMock(spec=ExecutionEvent), MagicMock(spec=ExecutionEvent)]
        events[0].sequence = 0
        events[1].sequence = 1

        listener._renumber_events(events)

        # Should renumber starting from max+1 = 6
        assert events[0].sequence == 6
        assert events[1].sequence == 7
        assert listener._seq == 8

    def test_falls_back_to_local_counter_on_db_failure(self) -> None:
        mock_session = MagicMock()
        mock_session.execute.side_effect = RuntimeError("DB down")
        listener, _ = _make_listener(session=mock_session)

        listener._seq = 10
        events = [MagicMock(spec=ExecutionEvent)]
        events[0].sequence = 0

        listener._renumber_events(events)

        # Should use local counter fallback
        assert events[0].sequence == 10
        assert listener._seq == 11


# ===========================================================================
# 21. shutdown_webhook_executor
# ===========================================================================


class TestShutdownWebhookExecutor:
    """Tests for blackbeard.engine.execution_listener.shutdown_webhook_executor."""

    def test_shuts_down_executor(self) -> None:
        import blackbeard.engine.execution_listener as mod

        original = mod._webhook_executor
        try:
            mock_executor = MagicMock()
            mod._webhook_executor = mock_executor

            mod.shutdown_webhook_executor()

            mock_executor.shutdown.assert_called_once_with(wait=True, cancel_futures=True)
            assert mod._webhook_executor is None
        finally:
            mod._webhook_executor = original

    def test_noop_when_no_executor(self) -> None:
        import blackbeard.engine.execution_listener as mod

        original = mod._webhook_executor
        try:
            mod._webhook_executor = None

            # Should not raise
            mod.shutdown_webhook_executor()

            assert mod._webhook_executor is None
        finally:
            mod._webhook_executor = original


# ===========================================================================
# 22. _dispatch_webhook (on listener)
# ===========================================================================


class TestDispatchWebhook:
    """Tests for BlackbeardExecutionListener._dispatch_webhook."""

    def test_dispatches_to_matching_targets(self) -> None:
        listener, _ = _make_listener()

        mock_wh = MagicMock()
        mock_executor = MagicMock()
        mock_future = MagicMock()
        mock_executor.submit.return_value = mock_future

        with (
            patch("blackbeard.engine.execution_listener._webhook_cache_lock", threading.Lock()),
            patch(
                "blackbeard.engine.execution_listener._prepare_webhook_targets",
                return_value=('{"test": true}', [mock_wh]),
            ),
            patch(
                "blackbeard.engine.execution_listener._get_webhook_executor",
                return_value=mock_executor,
            ),
        ):
            listener._dispatch_webhook("crew_completed", {"total_tokens": 100})

        mock_executor.submit.assert_called_once()

    def test_skips_when_cache_empty(self) -> None:
        import blackbeard.engine.execution_listener as mod

        listener, _ = _make_listener()

        original_cache = mod._webhook_cache_entry
        try:
            mod._webhook_cache_entry = (0.0, [])  # Empty cache

            with patch(
                "blackbeard.engine.execution_listener._prepare_webhook_targets"
            ) as mock_prep:
                listener._dispatch_webhook("test_event", {})

            # Should short-circuit before calling _prepare_webhook_targets
            mock_prep.assert_not_called()
        finally:
            mod._webhook_cache_entry = original_cache


# ===========================================================================
# 23. shutdown_otel
# ===========================================================================


class TestShutdownOtel:
    """Tests for blackbeard.engine.execution_listener.shutdown_otel."""

    def test_shuts_down_provider(self) -> None:
        import blackbeard.engine.execution_listener as mod

        original_provider = mod._otel_provider
        original_tracer = mod._otel_tracer
        try:
            mock_provider = MagicMock()
            mod._otel_provider = mock_provider
            mod._otel_tracer = MagicMock()

            mod.shutdown_otel()

            mock_provider.shutdown.assert_called_once()
            assert mod._otel_provider is None
            assert mod._otel_tracer is None
        finally:
            mod._otel_provider = original_provider
            mod._otel_tracer = original_tracer

    def test_noop_when_no_provider(self) -> None:
        import blackbeard.engine.execution_listener as mod

        original_provider = mod._otel_provider
        original_tracer = mod._otel_tracer
        try:
            mod._otel_provider = None
            mod._otel_tracer = None

            # Should not raise
            mod.shutdown_otel()
        finally:
            mod._otel_provider = original_provider
            mod._otel_tracer = original_tracer
