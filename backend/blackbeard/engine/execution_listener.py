"""CrewAI event listener that writes execution events to the database.

Captures events during crew execution and persists them as ExecutionEvent
rows for real-time SSE streaming to the UI.
"""

from __future__ import annotations

import asyncio
import logging
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

    def __init__(
        self,
        execution_id: UUID,
        session_factory: Any,
    ) -> None:
        self._execution_id = execution_id
        self._session_factory = session_factory
        self._seq = 0
        super().__init__()

    def _next_seq(self) -> int:
        """Return a monotonically increasing sequence number."""
        seq = self._seq
        self._seq += 1
        return seq

    async def _write_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Persist an ExecutionEvent row."""
        async with self._session_factory() as session:
            event = ExecutionEvent(
                execution_id=self._execution_id,
                sequence=self._next_seq(),
                event_type=event_type,
                timestamp=datetime.now(UTC),
                data=data,
            )
            session.add(event)
            await session.commit()

    async def _update_task_status(
        self,
        task_name: str,
        status: TaskStatus,
        output: str | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> None:
        """Update the corresponding ExecutionTask row."""
        async with self._session_factory() as session:
            values: dict[str, Any] = {"status": status}
            if output is not None:
                values["output"] = output
            if started_at is not None:
                values["started_at"] = started_at
            if completed_at is not None:
                values["completed_at"] = completed_at

            await session.execute(
                update(ExecutionTask)
                .where(
                    ExecutionTask.execution_id == self._execution_id,
                    ExecutionTask.task_name == task_name,
                )
                .values(**values)
            )
            await session.commit()

    def _run_async(self, coro: Any) -> None:
        """Run an async coroutine from a synchronous CrewAI callback."""
        try:
            loop = asyncio.get_event_loop()
            loop.run_until_complete(coro)
        except Exception:
            logger.exception(
                "Failed to write execution event for %s",
                self._execution_id,
            )

    def setup_listeners(self, crewai_event_bus: Any) -> None:
        """Register handlers for CrewAI events."""

        @crewai_event_bus.on(CrewKickoffStartedEvent)
        def on_crew_started(source: Any, event: CrewKickoffStartedEvent) -> None:
            self._handle_crew_started(event)

        @crewai_event_bus.on(CrewKickoffCompletedEvent)
        def on_crew_completed(source: Any, event: CrewKickoffCompletedEvent) -> None:
            self._handle_crew_completed(event)

        @crewai_event_bus.on(TaskStartedEvent)
        def on_task_started(source: Any, event: TaskStartedEvent) -> None:
            self._handle_task_started(event)

        @crewai_event_bus.on(TaskCompletedEvent)
        def on_task_completed(source: Any, event: TaskCompletedEvent) -> None:
            self._handle_task_completed(event)

        @crewai_event_bus.on(ToolUsageStartedEvent)
        def on_tool_started(source: Any, event: ToolUsageStartedEvent) -> None:
            self._handle_tool_started(event)

        @crewai_event_bus.on(ToolUsageFinishedEvent)
        def on_tool_finished(source: Any, event: ToolUsageFinishedEvent) -> None:
            self._handle_tool_finished(event)

        @crewai_event_bus.on(LLMCallStartedEvent)
        def on_llm_started(source: Any, event: LLMCallStartedEvent) -> None:
            self._handle_llm_started(event)

        @crewai_event_bus.on(LLMCallCompletedEvent)
        def on_llm_completed(source: Any, event: LLMCallCompletedEvent) -> None:
            self._handle_llm_completed(event)

    def _handle_crew_started(self, event: CrewKickoffStartedEvent) -> None:
        """Record crew kickoff event."""
        try:
            data = {
                "crew_name": event.crew_name or "unknown",
                "inputs": event.inputs if event.inputs else {},
            }
            self._run_async(self._write_event("crew_started", data))
        except Exception:
            logger.exception("Error handling crew_started for %s", self._execution_id)

    def _handle_crew_completed(self, event: CrewKickoffCompletedEvent) -> None:
        """Record crew completion event."""
        try:
            data = {
                "total_tokens": event.total_tokens if hasattr(event, "total_tokens") else 0,
            }
            self._run_async(self._write_event("crew_completed", data))
        except Exception:
            logger.exception("Error handling crew_completed for %s", self._execution_id)

    def _handle_task_started(self, event: TaskStartedEvent) -> None:
        """Record task start and update ExecutionTask status."""
        try:
            task_name = event.task_name or "unknown"
            agent_role = event.agent_role if hasattr(event, "agent_role") else None
            data = {
                "task_name": task_name,
                "agent_role": agent_role,
            }
            now = datetime.now(UTC)
            self._run_async(self._write_event("task_started", data))
            self._run_async(
                self._update_task_status(
                    task_name=task_name,
                    status=TaskStatus.RUNNING,
                    started_at=now,
                )
            )
        except Exception:
            logger.exception("Error handling task_started for %s", self._execution_id)

    def _handle_task_completed(self, event: TaskCompletedEvent) -> None:
        """Record task completion and update ExecutionTask status."""
        try:
            task_name = event.task_name or "unknown"
            output = str(event.output) if event.output else None
            output_preview = output[:500] if output else None
            data = {
                "task_name": task_name,
                "output_preview": output_preview,
            }
            now = datetime.now(UTC)
            self._run_async(self._write_event("task_completed", data))
            self._run_async(
                self._update_task_status(
                    task_name=task_name,
                    status=TaskStatus.COMPLETED,
                    output=output,
                    completed_at=now,
                )
            )
        except Exception:
            logger.exception("Error handling task_completed for %s", self._execution_id)

    def _handle_tool_started(self, event: ToolUsageStartedEvent) -> None:
        """Record tool usage start."""
        try:
            data = {
                "tool_name": event.tool_name or "unknown",
                "tool_args": str(event.tool_args)[:500] if event.tool_args else None,
                "agent_role": event.agent_role if hasattr(event, "agent_role") else None,
            }
            self._run_async(self._write_event("tool_started", data))
        except Exception:
            logger.exception("Error handling tool_started for %s", self._execution_id)

    def _handle_tool_finished(self, event: ToolUsageFinishedEvent) -> None:
        """Record tool usage completion."""
        try:
            duration_ms = None
            if hasattr(event, "finished_at") and hasattr(event, "started_at"):
                duration_ms = int((event.finished_at - event.started_at).total_seconds() * 1000)
            data = {
                "tool_name": event.tool_name or "unknown",
                "duration_ms": duration_ms,
                "from_cache": event.from_cache if hasattr(event, "from_cache") else False,
            }
            self._run_async(self._write_event("tool_finished", data))
        except Exception:
            logger.exception("Error handling tool_finished for %s", self._execution_id)

    def _handle_llm_started(self, event: LLMCallStartedEvent) -> None:
        """Record LLM call start."""
        try:
            data = {
                "model": event.model or "unknown",
                "agent_role": event.agent_role if hasattr(event, "agent_role") else None,
            }
            self._run_async(self._write_event("llm_started", data))
        except Exception:
            logger.exception("Error handling llm_started for %s", self._execution_id)

    def _handle_llm_completed(self, event: LLMCallCompletedEvent) -> None:
        """Record LLM call completion."""
        try:
            response_str = str(event.response) if event.response else None
            response_preview = response_str[:200] if response_str else None
            data = {
                "model": event.model if hasattr(event, "model") else "unknown",
                "tokens": event.usage if hasattr(event, "usage") else None,
                "response_preview": response_preview,
            }
            self._run_async(self._write_event("llm_completed", data))
        except Exception:
            logger.exception("Error handling llm_completed for %s", self._execution_id)
