"""CrewAI event listener that writes execution events to the database.

Captures events during crew execution and persists them as ExecutionEvent
rows for real-time SSE streaming to the UI. Uses synchronous DB sessions
since CrewAI callbacks run on a separate thread.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from crewai.events import (
    BaseEventListener,
    CrewKickoffCompletedEvent,
    CrewKickoffStartedEvent,
    LLMCallCompletedEvent,
    LLMCallStartedEvent,
    TaskCompletedEvent,
    TaskStartedEvent,
    ToolUsageFinishedEvent,
    ToolUsageStartedEvent,
)
from sqlalchemy import create_engine, update
from sqlalchemy.orm import Session, sessionmaker

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy import Engine

from blackbeard.logging_config import request_id_var
from blackbeard.models.execution import ExecutionEvent, ExecutionTask, TaskStatus

logger = logging.getLogger(__name__)

_sync_engine: Engine | None = None
_sync_session_factory: sessionmaker[Session] | None = None
_sync_engine_lock = threading.Lock()


def _get_sync_session_factory(db_url: str) -> sessionmaker[Session]:
    """Return a shared sync sessionmaker, creating engine+factory on first call.

    Both are thread-safe and not bound to event loops, so one instance
    can serve all execution listeners.
    """
    global _sync_engine, _sync_session_factory
    if _sync_session_factory is not None:
        return _sync_session_factory
    with _sync_engine_lock:
        if _sync_session_factory is not None:
            return _sync_session_factory
        sync_url = db_url.replace("postgresql+asyncpg", "postgresql+psycopg").replace(
            "postgresql+aiopg", "postgresql+psycopg"
        )
        _sync_engine = create_engine(
            sync_url,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=3600,
            connect_args={
                "options": "-c statement_timeout=30000"
                " -c idle_in_transaction_session_timeout=60000",
                "connect_timeout": 10,
            },
        )
        _sync_session_factory = sessionmaker(_sync_engine, class_=Session, expire_on_commit=False)
        return _sync_session_factory


def dispose_sync_engine() -> None:
    """Dispose the shared sync engine. Called during application shutdown."""
    global _sync_engine, _sync_session_factory
    with _sync_engine_lock:
        _sync_session_factory = None
        if _sync_engine is not None:
            _sync_engine.dispose()
            _sync_engine = None


class BlackbeardExecutionListener(BaseEventListener):
    """Writes CrewAI events to the execution_events table for real-time streaming."""

    def __init__(self, execution_id: UUID, db_url: str) -> None:
        self._execution_id = execution_id
        self._seq = 0
        self._task_order = 0  # tracks which task (by order) is currently running
        self._lock = threading.Lock()  # guards _seq and _task_order
        self._session_factory = _get_sync_session_factory(db_url)
        super().__init__()

    def _next_seq(self) -> int:
        with self._lock:
            seq = self._seq
            self._seq += 1
            return seq

    def _ensure_request_id(self) -> None:
        """Set request_id ContextVar on the current thread for log correlation.

        CrewAI callbacks may run on the event bus thread which does not inherit
        the executor thread's ContextVar, so we re-set it here.
        """
        if request_id_var.get("-") == "-":
            request_id_var.set(str(self._execution_id))

    def _write_event(self, event_type: str, data: dict[str, Any]) -> None:
        self._ensure_request_id()
        try:
            seq = self._next_seq()
            with self._session_factory() as session:
                event = ExecutionEvent(
                    execution_id=self._execution_id,
                    sequence=seq,
                    event_type=event_type,
                    timestamp=datetime.now(UTC),
                    data=data,
                )
                session.add(event)
                session.commit()
            logger.debug(
                "Event written: execution=%s type=%s seq=%d",
                self._execution_id,
                event_type,
                seq,
                extra={
                    "event": "event_written",
                    "execution_id": str(self._execution_id),
                    "event_type": event_type,
                    "sequence": seq,
                },
            )
        except Exception as exc:
            logger.exception(
                "Failed to write event for %s: type=%s",
                self._execution_id,
                event_type,
                extra={
                    "event": "event_write_failed",
                    "execution_id": str(self._execution_id),
                    "event_type": event_type,
                    "event_data_keys": sorted(data.keys()),
                    "error_type": type(exc).__name__,
                    "error_message": str(exc)[:500],
                },
            )

    def _write_event_with_task_update(
        self,
        event_type: str,
        data: dict[str, Any],
        task_order: int,
        task_status: TaskStatus,
        task_output: str | None = None,
        task_started_at: datetime | None = None,
        task_completed_at: datetime | None = None,
    ) -> None:
        """Write an event and update a task in a single DB transaction."""
        self._ensure_request_id()
        try:
            now = datetime.now(UTC)
            with self._session_factory() as session:
                event = ExecutionEvent(
                    execution_id=self._execution_id,
                    sequence=self._next_seq(),
                    event_type=event_type,
                    timestamp=now,
                    data=data,
                )
                session.add(event)
                values: dict[str, Any] = {"status": task_status}
                if task_output is not None:
                    values["output"] = task_output
                if task_started_at is not None:
                    values["started_at"] = task_started_at
                if task_completed_at is not None:
                    values["completed_at"] = task_completed_at
                session.execute(
                    update(ExecutionTask)
                    .where(
                        ExecutionTask.execution_id == self._execution_id,
                        ExecutionTask.order == task_order,
                    )
                    .values(**values)
                )
                session.commit()
        except Exception as exc:
            logger.exception(
                "Failed to write event+task for %s: type=%s order=%d",
                self._execution_id,
                event_type,
                task_order,
                extra={
                    "event": "event_task_write_failed",
                    "execution_id": str(self._execution_id),
                    "event_type": event_type,
                    "task_order": task_order,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc)[:500],
                },
            )

    def setup_listeners(self, crewai_event_bus: Any) -> None:
        @crewai_event_bus.on(CrewKickoffStartedEvent)
        def on_crew_started(source: Any, event: CrewKickoffStartedEvent) -> None:
            data = {
                "crew_name": event.crew_name or "unknown",
                "inputs": event.inputs or {},
            }
            self._write_event("crew_started", data)

        @crewai_event_bus.on(CrewKickoffCompletedEvent)
        def on_crew_completed(source: Any, event: CrewKickoffCompletedEvent) -> None:
            data = {"total_tokens": event.total_tokens}
            self._write_event("crew_completed", data)

        @crewai_event_bus.on(TaskStartedEvent)
        def on_task_started(source: Any, event: TaskStartedEvent) -> None:
            task_name = event.task_name or "unknown"
            data = {
                "task_name": task_name,
                "agent_role": event.agent_role,
            }
            with self._lock:
                order = self._task_order
            now = datetime.now(UTC)
            self._write_event_with_task_update(
                "task_started",
                data,
                task_order=order,
                task_status=TaskStatus.RUNNING,
                task_started_at=now,
            )

        @crewai_event_bus.on(TaskCompletedEvent)
        def on_task_completed(source: Any, event: TaskCompletedEvent) -> None:
            task_name = event.task_name or "unknown"
            output = str(event.output) if event.output else None
            data = {
                "task_name": task_name,
                "output_preview": (output[:500] if output else None),
            }
            with self._lock:
                order = self._task_order
                self._task_order += 1
            now = datetime.now(UTC)
            self._write_event_with_task_update(
                "task_completed",
                data,
                task_order=order,
                task_status=TaskStatus.COMPLETED,
                task_output=output,
                task_completed_at=now,
            )

        @crewai_event_bus.on(ToolUsageStartedEvent)
        def on_tool_started(source: Any, event: ToolUsageStartedEvent) -> None:
            data = {
                "tool_name": event.tool_name,
                "tool_args": str(event.tool_args)[:200] if event.tool_args else None,
                "agent_role": event.agent_role,
            }
            self._write_event("tool_started", data)

        @crewai_event_bus.on(ToolUsageFinishedEvent)
        def on_tool_finished(source: Any, event: ToolUsageFinishedEvent) -> None:
            duration_ms = int(
                (event.finished_at - event.started_at).total_seconds() * 1000
            )
            data = {
                "tool_name": event.tool_name,
                "duration_ms": duration_ms,
                "from_cache": event.from_cache,
            }
            self._write_event("tool_finished", data)

        @crewai_event_bus.on(LLMCallStartedEvent)
        def on_llm_started(source: Any, event: LLMCallStartedEvent) -> None:
            data = {
                "model": event.model,
                "agent_role": event.agent_role,
            }
            self._write_event("llm_started", data)

        @crewai_event_bus.on(LLMCallCompletedEvent)
        def on_llm_completed(source: Any, event: LLMCallCompletedEvent) -> None:
            usage = event.usage or {}
            response_preview = str(event.response)[:200] if event.response else None
            data = {
                "model": event.model,
                "tokens": usage.get("total_tokens", 0) if isinstance(usage, dict) else 0,
                "response_preview": response_preview,
            }
            self._write_event("llm_completed", data)
