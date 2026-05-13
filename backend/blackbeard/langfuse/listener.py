"""CrewAI event listener that maps events to Langfuse traces.

Hierarchy:
  Trace (crew execution)
    └─ Span (task)
        ├─ Span (tool call)
        └─ Generation (LLM call)
"""

from __future__ import annotations

import logging
from typing import Any

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

from blackbeard.langfuse.client import get_langfuse

logger = logging.getLogger(__name__)


class BlackbeardLangfuseListener(BaseEventListener):
    """Maps CrewAI events to Langfuse trace hierarchy."""

    def __init__(
        self,
        execution_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._execution_id = execution_id
        self._metadata = metadata or {}
        self._trace: Any = None
        self._trace_failed = False
        self._task_spans: dict[str, Any] = {}
        self._tool_spans: dict[str, Any] = {}
        self._llm_generations: dict[str, Any] = {}
        super().__init__()

    def _pop_span(self, mapping: dict[str, Any], event_id: str) -> Any | None:
        """Pop a span/generation by event_id, falling back to LIFO order."""
        span = mapping.pop(event_id, None)
        if span is None and mapping:
            last_key = next(reversed(mapping))
            span = mapping.pop(last_key)
        return span

    def _current_parent(self) -> Any:
        """Return the innermost task span, or the trace itself."""
        if self._task_spans:
            last_key = next(reversed(self._task_spans))
            return self._task_spans[last_key]
        return self._trace

    @property
    def trace_id(self) -> str | None:
        """Return the Langfuse trace ID if available."""
        return self._trace.trace_id if self._trace else None

    @property
    def trace_url(self) -> str | None:
        """Return the Langfuse trace URL if available."""
        if not self._trace:
            return None
        langfuse = get_langfuse()
        if not langfuse:
            return None
        return langfuse.get_trace_url(self._trace.trace_id)

    def setup_listeners(self, crewai_event_bus: Any) -> None:
        """Register handlers for CrewAI events."""

        @crewai_event_bus.on(CrewKickoffStartedEvent)
        def on_crew_started(source: Any, event: CrewKickoffStartedEvent) -> None:
            self._on_crew_started(event)

        @crewai_event_bus.on(CrewKickoffCompletedEvent)
        def on_crew_completed(source: Any, event: CrewKickoffCompletedEvent) -> None:
            self._on_crew_completed(event)

        @crewai_event_bus.on(TaskStartedEvent)
        def on_task_started(source: Any, event: TaskStartedEvent) -> None:
            self._on_task_started(event)

        @crewai_event_bus.on(TaskCompletedEvent)
        def on_task_completed(source: Any, event: TaskCompletedEvent) -> None:
            self._on_task_completed(event)

        @crewai_event_bus.on(ToolUsageStartedEvent)
        def on_tool_started(source: Any, event: ToolUsageStartedEvent) -> None:
            self._on_tool_started(event)

        @crewai_event_bus.on(ToolUsageFinishedEvent)
        def on_tool_finished(source: Any, event: ToolUsageFinishedEvent) -> None:
            self._on_tool_finished(event)

        @crewai_event_bus.on(LLMCallStartedEvent)
        def on_llm_started(source: Any, event: LLMCallStartedEvent) -> None:
            self._on_llm_started(event)

        @crewai_event_bus.on(LLMCallCompletedEvent)
        def on_llm_completed(source: Any, event: LLMCallCompletedEvent) -> None:
            self._on_llm_completed(event)

    def _on_crew_started(self, event: CrewKickoffStartedEvent) -> None:
        """Create a Langfuse trace for the crew execution."""
        langfuse = get_langfuse()
        if not langfuse:
            return

        try:
            self._trace = langfuse.start_observation(
                name=f"crew:{event.crew_name or 'unknown'}",
                input=event.inputs,
                metadata={
                    "execution_id": self._execution_id,
                    "crew_name": event.crew_name,
                    "session_id": self._execution_id,
                    "tags": ["blackbeard", "crew-execution"],
                    **self._metadata,
                },
            )
            logger.debug("Langfuse trace created: %s", self._trace.trace_id)
        except Exception as e:
            self._trace_failed = True
            logger.warning("Failed to create Langfuse trace: %s", e, exc_info=True)

    def _on_crew_completed(self, event: CrewKickoffCompletedEvent) -> None:
        """Finalize the Langfuse trace."""
        if not self._trace:
            return

        try:
            output = str(event.output) if event.output else None
            self._trace.update(
                output=output,
                metadata={
                    "total_tokens": event.total_tokens,
                    "status": "completed",
                },
            )
            self._trace.end()
            langfuse = get_langfuse()
            if langfuse:
                langfuse.flush()
        except Exception as e:
            logger.warning("Failed to update Langfuse trace: %s", e, exc_info=True)

    def _on_task_started(self, event: TaskStartedEvent) -> None:
        """Create a span for a task."""
        if not self._trace:
            if self._trace_failed:
                logger.debug(
                    "Dropping Langfuse events — trace creation failed for execution %s",
                    self._execution_id,
                )
                self._trace_failed = False
            return

        try:
            task_name = event.task_name or "unknown"
            span = self._trace.start_observation(
                name=f"task:{task_name}",
                input={"context": event.context} if event.context else None,
                metadata={
                    "agent_role": event.agent_role,
                    "task_description": task_name,
                },
            )
            self._task_spans[event.event_id] = span
            logger.debug("Langfuse task span created: %s", task_name)
        except Exception as e:
            logger.warning("Failed to create task span: %s", e, exc_info=True)

    def _on_task_completed(self, event: TaskCompletedEvent) -> None:
        """End the task span."""
        if not self._task_spans:
            return

        try:
            span = self._pop_span(self._task_spans, event.event_id)
            if span is None:
                return
            output = str(event.output) if event.output else None
            span.update(output=output)
            span.end()
        except Exception as e:
            logger.warning("Failed to end task span: %s", e, exc_info=True)

    def _on_tool_started(self, event: ToolUsageStartedEvent) -> None:
        """Create a span for a tool call."""
        if not self._trace:
            return

        try:
            parent = self._current_parent()
            span = parent.start_observation(
                name=f"tool:{event.tool_name}",
                input={"args": event.tool_args} if event.tool_args else None,
                metadata={
                    "agent_role": event.agent_role,
                    "tool_class": event.tool_class,
                },
            )
            self._tool_spans[event.event_id] = span
            logger.debug("Langfuse tool span created: %s", event.tool_name)
        except Exception as e:
            logger.warning("Failed to create tool span: %s", e, exc_info=True)

    def _on_tool_finished(self, event: ToolUsageFinishedEvent) -> None:
        """End the tool span."""
        if not self._tool_spans:
            return

        try:
            span = self._pop_span(self._tool_spans, event.event_id)
            if span is None:
                return
            duration_ms = int((event.finished_at - event.started_at).total_seconds() * 1000)
            span.update(
                output={"from_cache": event.from_cache},
                metadata={"duration_ms": duration_ms},
            )
            span.end()
        except Exception as e:
            logger.warning("Failed to end tool span: %s", e, exc_info=True)

    def _on_llm_started(self, event: LLMCallStartedEvent) -> None:
        """Create a generation for an LLM call."""
        if not self._trace:
            return

        try:
            parent = self._current_parent()
            generation = parent.start_observation(
                name=f"llm:{event.model or 'unknown'}",
                as_type="generation",
                model=event.model,
                input=event.messages,
                metadata={
                    "agent_role": event.agent_role,
                },
            )
            self._llm_generations[event.event_id] = generation
            logger.debug("Langfuse LLM generation created: %s", event.model)
        except Exception as e:
            logger.warning("Failed to create LLM generation: %s", e, exc_info=True)

    def _on_llm_completed(self, event: LLMCallCompletedEvent) -> None:
        """End the LLM generation."""
        if not self._llm_generations:
            return

        try:
            generation = self._pop_span(self._llm_generations, event.event_id)
            if generation is None:
                return

            output = str(event.response) if event.response else None
            usage = event.usage

            generation.update(output=output, usage_details=usage)
            generation.end()
        except Exception as e:
            logger.warning("Failed to end LLM generation: %s", e, exc_info=True)
