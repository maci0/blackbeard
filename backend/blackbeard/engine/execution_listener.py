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
from sqlalchemy import update

if TYPE_CHECKING:
    from uuid import UUID

from blackbeard.models.execution import ExecutionEvent, ExecutionTask, TaskStatus

logger = logging.getLogger(__name__)


class BlackbeardExecutionListener(BaseEventListener):
    """Writes CrewAI events to the execution_events table for real-time streaming."""

    def __init__(self, execution_id: UUID, db_url: str) -> None:
        self._execution_id = execution_id
        self._seq = 0
        self._task_order = 0  # tracks which task (by order) is currently running
        self._lock = threading.Lock()  # guards _seq and _task_order
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session, sessionmaker

        # Convert async driver URL to sync driver.  Handle both asyncpg
        # (default) and other async drivers that follow the same naming pattern.
        sync_url = db_url.replace("postgresql+asyncpg", "postgresql+psycopg").replace(
            "postgresql+aiopg", "postgresql+psycopg"
        )
        self._sync_engine = create_engine(sync_url, pool_size=2, max_overflow=3)
        self._sync_session_factory = sessionmaker(self._sync_engine, class_=Session)
        super().__init__()

    def _next_seq(self) -> int:
        with self._lock:
            seq = self._seq
            self._seq += 1
            return seq

    def _write_event(self, event_type: str, data: dict[str, Any]) -> None:
        try:
            with self._sync_session_factory() as session:
                event = ExecutionEvent(
                    execution_id=self._execution_id,
                    sequence=self._next_seq(),
                    event_type=event_type,
                    timestamp=datetime.now(UTC),
                    data=data,
                )
                session.add(event)
                session.commit()
        except Exception:
            logger.exception("Failed to write event for %s", self._execution_id)

    def _update_task_by_order(
        self,
        order: int,
        status: TaskStatus,
        output: str | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> None:
        """Update ExecutionTask by order (CrewAI task names don't match resource names)."""
        try:
            with self._sync_session_factory() as session:
                values: dict[str, Any] = {"status": status}
                if output is not None:
                    values["output"] = output
                if started_at is not None:
                    values["started_at"] = started_at
                if completed_at is not None:
                    values["completed_at"] = completed_at
                session.execute(
                    update(ExecutionTask)
                    .where(
                        ExecutionTask.execution_id == self._execution_id,
                        ExecutionTask.order == order,
                    )
                    .values(**values)
                )
                session.commit()
        except Exception:
            logger.exception("Failed to update task for %s", self._execution_id)

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
            data = {"total_tokens": getattr(event, "total_tokens", 0)}
            self._write_event("crew_completed", data)

        @crewai_event_bus.on(TaskStartedEvent)
        def on_task_started(source: Any, event: TaskStartedEvent) -> None:
            task_name = event.task_name or "unknown"
            data = {
                "task_name": task_name,
                "agent_role": event.agent_role,
            }
            self._write_event("task_started", data)
            with self._lock:
                order = self._task_order
            self._update_task_by_order(
                order=order,
                status=TaskStatus.RUNNING,
                started_at=datetime.now(UTC),
            )

        @crewai_event_bus.on(TaskCompletedEvent)
        def on_task_completed(source: Any, event: TaskCompletedEvent) -> None:
            task_name = event.task_name or "unknown"
            output = str(event.output) if event.output else None
            data = {
                "task_name": task_name,
                "output_preview": (output[:500] if output else None),
            }
            self._write_event("task_completed", data)
            with self._lock:
                order = self._task_order
                self._task_order += 1
            self._update_task_by_order(
                order=order,
                status=TaskStatus.COMPLETED,
                output=output,
                completed_at=datetime.now(UTC),
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
            duration_ms = None
            if hasattr(event, "started_at") and hasattr(event, "finished_at"):
                duration_ms = int((event.finished_at - event.started_at).total_seconds() * 1000)
            data = {
                "tool_name": event.tool_name,
                "duration_ms": duration_ms,
                "from_cache": getattr(event, "from_cache", False),
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
