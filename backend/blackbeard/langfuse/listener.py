"""CrewAI event listener that maps events to Langfuse traces.

Hierarchy:
  Trace (crew execution)
    └─ Span (task)
        ├─ Span (tool call)
        └─ Generation (LLM call)
"""

from __future__ import annotations

import logging

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

from blackbeard.config import settings
from blackbeard.langfuse.client import get_langfuse

logger = logging.getLogger(__name__)


class BlackbeardLangfuseListener(BaseEventListener):
    """Maps CrewAI events to Langfuse trace hierarchy."""

    def __init__(self, execution_id: str | None = None, metadata: dict | None = None):
        self._execution_id = execution_id
        self._metadata = metadata or {}
        self._trace = None
        self._trace_failed = False
        self._task_spans: dict[str, object] = {}  # event_id → span
        self._tool_spans: dict[str, object] = {}  # tool event_id → span
        self._llm_generations: dict[str, object] = {}  # llm event_id → generation
        super().__init__()

    def _pop_span(self, mapping: dict[str, object], event_id: str) -> object | None:
        """Pop a span/generation by event_id, falling back to LIFO order."""
        span = mapping.pop(event_id, None)
        if span is None and mapping:
            last_key = next(reversed(mapping))
            span = mapping.pop(last_key)
        return span

    def _current_parent(self) -> object:
        """Return the innermost task span, or the trace itself."""
        if self._task_spans:
            last_key = next(reversed(self._task_spans))
            return self._task_spans[last_key]
        return self._trace

    @property
    def trace_id(self) -> str | None:
        """Return the Langfuse trace ID if available."""
        return self._trace.id if self._trace else None

    @property
    def trace_url(self) -> str | None:
        """Return the Langfuse trace URL if available."""
        if not self._trace:
            return None
        langfuse = get_langfuse()
        if not langfuse:
            return None
        return f"{settings.langfuse_host}/trace/{self._trace.id}"

    def setup_listeners(self, crewai_event_bus) -> None:  # type: ignore[no-untyped-def]
        """Register handlers for CrewAI events."""

        @crewai_event_bus.on(CrewKickoffStartedEvent)
        def on_crew_started(source, event):  # type: ignore[no-untyped-def]
            self._on_crew_started(event)

        @crewai_event_bus.on(CrewKickoffCompletedEvent)
        def on_crew_completed(source, event):  # type: ignore[no-untyped-def]
            self._on_crew_completed(event)

        @crewai_event_bus.on(TaskStartedEvent)
        def on_task_started(source, event):  # type: ignore[no-untyped-def]
            self._on_task_started(event)

        @crewai_event_bus.on(TaskCompletedEvent)
        def on_task_completed(source, event):  # type: ignore[no-untyped-def]
            self._on_task_completed(event)

        @crewai_event_bus.on(ToolUsageStartedEvent)
        def on_tool_started(source, event):  # type: ignore[no-untyped-def]
            self._on_tool_started(event)

        @crewai_event_bus.on(ToolUsageFinishedEvent)
        def on_tool_finished(source, event):  # type: ignore[no-untyped-def]
            self._on_tool_finished(event)

        @crewai_event_bus.on(LLMCallStartedEvent)
        def on_llm_started(source, event):  # type: ignore[no-untyped-def]
            self._on_llm_started(event)

        @crewai_event_bus.on(LLMCallCompletedEvent)
        def on_llm_completed(source, event):  # type: ignore[no-untyped-def]
            self._on_llm_completed(event)

    def _on_crew_started(self, event) -> None:  # type: ignore[no-untyped-def]
        """Create a Langfuse trace for the crew execution."""
        langfuse = get_langfuse()
        if not langfuse:
            return

        try:
            self._trace = langfuse.trace(
                name=f"crew:{event.crew_name or 'unknown'}",
                session_id=self._execution_id,
                metadata={
                    "execution_id": self._execution_id,
                    "crew_name": event.crew_name,
                    "inputs": event.inputs,
                    **self._metadata,
                },
                tags=["blackbeard", "crew-execution"],
                input=event.inputs,
            )
            logger.debug("Langfuse trace created: %s", self._trace.id)
        except Exception as e:
            self._trace_failed = True
            logger.warning("Failed to create Langfuse trace: %s", e, exc_info=True)

    def _on_crew_completed(self, event) -> None:  # type: ignore[no-untyped-def]
        """Finalize the Langfuse trace."""
        if not self._trace:
            return

        try:
            output = str(event.output) if event.output else None
            self._trace.update(
                output=output,
                metadata={
                    "total_tokens": getattr(event, "total_tokens", 0),
                    "status": "completed",
                },
            )
            langfuse = get_langfuse()
            if langfuse:
                langfuse.flush()
        except Exception as e:
            logger.warning("Failed to update Langfuse trace: %s", e, exc_info=True)

    def _on_task_started(self, event) -> None:  # type: ignore[no-untyped-def]
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
            task = getattr(event, "task", None)
            task_name = "unknown"
            agent_role = None
            if task:
                task_name = getattr(task, "name", None) or getattr(task, "description", "unknown")[:50]
                agent = getattr(task, "agent", None)
                if agent:
                    agent_role = getattr(agent, "role", None)

            span = self._trace.span(
                name=f"task:{task_name}",
                input={"context": event.context} if event.context else None,
                metadata={
                    "agent": agent_role,
                    "task_description": str(task_name),
                },
            )
            # Use event_id as key
            self._task_spans[event.event_id] = span
            logger.debug("Langfuse task span created: %s", task_name)
        except Exception as e:
            logger.warning("Failed to create task span: %s", e, exc_info=True)

    def _on_task_completed(self, event) -> None:  # type: ignore[no-untyped-def]
        """End the task span."""
        if not self._task_spans:
            return

        try:
            span = self._pop_span(self._task_spans, event.event_id)
            if span is None:
                return
            output = str(event.output) if event.output else None
            span.end(output=output)
        except Exception as e:
            logger.warning("Failed to end task span: %s", e, exc_info=True)

    def _on_tool_started(self, event) -> None:  # type: ignore[no-untyped-def]
        """Create a span for a tool call."""
        if not self._trace:
            return

        try:
            parent = self._current_parent()

            span = parent.span(
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

    def _on_tool_finished(self, event) -> None:  # type: ignore[no-untyped-def]
        """End the tool span."""
        if not self._tool_spans:
            return

        try:
            span = self._pop_span(self._tool_spans, event.event_id)
            if span is None:
                return
            duration_ms = None
            if hasattr(event, "started_at") and hasattr(event, "finished_at"):
                duration_ms = int((event.finished_at - event.started_at).total_seconds() * 1000)
            span.end(
                output={"from_cache": getattr(event, "from_cache", False)},
                metadata={"duration_ms": duration_ms} if duration_ms else None,
            )
        except Exception as e:
            logger.warning("Failed to end tool span: %s", e, exc_info=True)

    def _on_llm_started(self, event) -> None:  # type: ignore[no-untyped-def]
        """Create a generation for an LLM call."""
        if not self._trace:
            return

        try:
            parent = self._current_parent()

            generation = parent.generation(
                name=f"llm:{getattr(event, 'model', 'unknown')}",
                model=getattr(event, "model", None),
                input=event.messages if hasattr(event, "messages") else None,
                metadata={
                    "agent_role": getattr(event, "agent_role", None),
                    "call_type": str(getattr(event, "call_type", "unknown")),
                },
            )
            self._llm_generations[event.event_id] = generation
            logger.debug("Langfuse LLM generation created: %s", getattr(event, "model", "unknown"))
        except Exception as e:
            logger.warning("Failed to create LLM generation: %s", e, exc_info=True)

    def _on_llm_completed(self, event) -> None:  # type: ignore[no-untyped-def]
        """End the LLM generation."""
        if not self._llm_generations:
            return

        try:
            generation = self._pop_span(self._llm_generations, event.event_id)
            if generation is None:
                return

            output = None
            usage = None
            if hasattr(event, "response") and event.response:
                output = str(event.response)
                # Try to extract token usage from response
                if hasattr(event.response, "usage"):
                    u = event.response.usage
                    usage = {
                        "prompt_tokens": getattr(u, "prompt_tokens", 0) or 0,
                        "completion_tokens": getattr(u, "completion_tokens", 0) or 0,
                        "total_tokens": getattr(u, "total_tokens", 0) or 0,
                    }

            generation.end(
                output=output,
                usage_details=usage,
            )
        except Exception as e:
            logger.warning("Failed to end LLM generation: %s", e, exc_info=True)
