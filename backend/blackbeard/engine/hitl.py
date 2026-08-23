"""Database-backed human-in-the-loop input provider for CrewAI.

CrewAI's pluggable human-input provider protocol
(``crewai.core.providers.human_input``) defaults to reading stdin. Executions
run in background threads with no terminal, so a task with ``human_input``
would block forever or crash the run.

Blackbeard installs :class:`BlackbeardHumanInputProvider` instead: when CrewAI
pauses for feedback, this provider writes an ``hitl_request`` execution event
and polls until an ``hitl_response`` event is recorded via
``POST /api/v1/executions/{id}/respond`` (the UI polls for requests and shows
a response form). Sequence numbers are allocated with max+1 and retried on
unique-constraint collisions, mirroring ``record_hitl_response`` — the
execution listener renumbers its own buffered events after such collisions.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from crewai.core.providers.human_input import (
    SyncHumanInputProvider,
    reset_provider,
    set_provider,
)
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from blackbeard.config import settings
from blackbeard.engine.execution_listener import _get_sync_session_factory
from blackbeard.models.execution import (
    TERMINAL_STATUSES,
    Execution,
    ExecutionEvent,
    ExecutionEventType,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from uuid import UUID

    from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

__all__ = [
    "BlackbeardHumanInputProvider",
    "database_human_input",
]

_POLL_INTERVAL_S = 0.5
_MAX_WRITE_ATTEMPTS = 3

# Prompt text mirrors CrewAI's terminal prompts so users see consistent copy.
_TRAINING_PROMPT = (
    "TRAINING MODE: Provide feedback to improve the agent's performance.\n\n"
    "This will be used to train better versions of the agent.\n"
    "Please provide detailed feedback about the result quality and reasoning process."
)
_REGULAR_PROMPT = (
    "Provide feedback on the Final Result.\n\n"
    "- If you are happy with the result, submit an empty response.\n"
    "- Otherwise, provide specific improvement requests.\n"
    "- You can provide multiple rounds of feedback until satisfied."
)


class BlackbeardHumanInputProvider(SyncHumanInputProvider):
    """Bridge CrewAI human-input prompts to the Blackbeard execution event log."""

    def __init__(
        self,
        execution_id: UUID,
        db_url: str,
        session_factory: sessionmaker[Session] | None = None,
        timeout_s: float | None = None,
    ) -> None:
        super().__init__()
        self._execution_id = execution_id
        self._session_factory = session_factory or _get_sync_session_factory(db_url)
        self._timeout_s = settings.hitl_response_timeout_s if timeout_s is None else timeout_s

    def handle_feedback(self, formatted_answer: Any, context: Any) -> Any:
        """Handle the full human-feedback flow through execution events.

        Mirrors ``SyncHumanInputProvider.handle_feedback`` but replaces the
        terminal prompts with event-log round trips. An empty response (also
        returned on timeout or when the execution turns terminal) ends the
        feedback loop and lets the run continue unattended.
        """
        if context._is_training_mode():
            request_seq = self._write_request(_TRAINING_PROMPT)
            feedback = self._wait_for_response(request_seq)
            return self._handle_training_feedback(formatted_answer, feedback, context)

        answer = formatted_answer
        while True:
            request_seq = self._write_request(_REGULAR_PROMPT)
            feedback = self._wait_for_response(request_seq)
            if not feedback.strip():
                context.ask_for_human_input = False
                return answer
            context.messages.append(context._format_feedback_message(feedback))
            answer = context._invoke_loop()

    def _write_request(self, prompt: str) -> int:
        """Insert an ``hitl_request`` event; returns its sequence number."""
        last_exc: IntegrityError | None = None
        for attempt in range(_MAX_WRITE_ATTEMPTS):
            try:
                with self._session_factory() as session:
                    max_seq = session.execute(
                        select(func.coalesce(func.max(ExecutionEvent.sequence), -1)).where(
                            ExecutionEvent.execution_id == self._execution_id
                        )
                    ).scalar_one()
                    event = ExecutionEvent(
                        execution_id=self._execution_id,
                        sequence=max_seq + 1,
                        event_type=ExecutionEventType.HITL_REQUEST.value,
                        timestamp=datetime.now(UTC),
                        data={"prompt": prompt},
                    )
                    session.add(event)
                    session.commit()
                    return int(event.sequence)
            except IntegrityError as exc:
                last_exc = exc
                time.sleep(0.05 * (2**attempt))
        raise RuntimeError(
            f"Failed to record hitl_request for execution {self._execution_id} "
            f"after {_MAX_WRITE_ATTEMPTS} attempts"
        ) from last_exc

    def _wait_for_response(self, request_seq: int) -> str:
        """Poll for an ``hitl_response`` event newer than *request_seq*.

        Only responses recorded after this round's request qualify, so stale
        answers from earlier rounds are never consumed twice. Gives up (with
        an empty string) on timeout or when the execution turns terminal.
        """
        deadline = time.monotonic() + self._timeout_s
        while True:
            row: ExecutionEvent | None = None
            with self._session_factory() as session:
                row = session.execute(
                    select(ExecutionEvent)
                    .where(
                        ExecutionEvent.execution_id == self._execution_id,
                        ExecutionEvent.sequence > request_seq,
                        ExecutionEvent.event_type == ExecutionEventType.HITL_RESPONSE.value,
                    )
                    .order_by(ExecutionEvent.sequence)
                    .limit(1)
                ).scalar_one_or_none()
                if row is None:
                    status = session.execute(
                        select(Execution.status).where(Execution.id == self._execution_id)
                    ).scalar_one_or_none()
                    if status is not None and status in TERMINAL_STATUSES:
                        logger.info(
                            "Execution %s reached terminal status (%s) while waiting "
                            "for human input",
                            self._execution_id,
                            status.value,
                            extra={
                                "event": "hitl_wait_aborted_terminal",
                                "execution_id": str(self._execution_id),
                                "status": status.value,
                            },
                        )
                        return ""
            if row is not None:
                data = row.data or {}
                return str(data.get("response", ""))
            if time.monotonic() >= deadline:
                return ""
            time.sleep(_POLL_INTERVAL_S)


@contextmanager
def database_human_input(
    execution_id: UUID | None,
    session_factory: sessionmaker[Session] | None = None,
) -> Iterator[BlackbeardHumanInputProvider | None]:
    """Install the DB-backed HITL provider for the current thread.

    Wrap ``crew.kickoff()``/``crew.train()``/``crew.test()`` calls so any
    task pausing on ``human_input`` routes through the execution event log
    instead of stdin. Restores the previous provider on exit.

    A ``None`` execution id (no owning execution) installs nothing.
    """
    if execution_id is None:
        yield None
        return
    provider = BlackbeardHumanInputProvider(
        execution_id=execution_id,
        db_url=settings.database_url.get_secret_value(),
        session_factory=session_factory,
    )
    token = set_provider(provider)
    try:
        yield provider
    finally:
        reset_provider(token)
