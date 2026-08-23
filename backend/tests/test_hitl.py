"""Tests for the DB-backed human-in-the-loop input provider."""

from __future__ import annotations

import json as _json_mod
import threading
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from blackbeard.engine.hitl import (
    _REGULAR_PROMPT,
    BlackbeardHumanInputProvider,
    database_human_input,
)
from blackbeard.models.database import Base
from blackbeard.models.execution import (
    TERMINAL_STATUSES,
    Execution,
    ExecutionEvent,
    ExecutionEventType,
    ExecutionStatus,
)


@pytest.fixture
def sync_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    from sqlalchemy import event as sa_event

    @sa_event.listens_for(engine, "connect")
    def _register_sqlite_functions(dbapi_conn: Any, _record: Any) -> None:
        dbapi_conn.create_function("jsonb_typeof", 1, _sqlite_jsonb_typeof)

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    engine.dispose()


def _sqlite_jsonb_typeof(value: str) -> str | None:
    if not isinstance(value, str):
        return None
    return type(_json_mod.loads(value)).__name__.replace("list", "array").replace("dict", "object")


def _add_execution(factory: sessionmaker[Session], exec_id: uuid.UUID) -> None:
    with factory() as session:
        session.add(Execution(id=exec_id, crew_name="test-crew", inputs={}))
        session.commit()


def _set_execution_status(
    factory: sessionmaker[Session], exec_id: uuid.UUID, status: ExecutionStatus
) -> None:
    with factory() as session:
        row = session.get(Execution, exec_id)
        assert row is not None
        row.status = status
        row.started_at = datetime.now(UTC)
        if status in TERMINAL_STATUSES:
            row.completed_at = datetime.now(UTC)
        session.commit()


def _add_event(
    factory: sessionmaker[Session],
    exec_id: uuid.UUID,
    seq: int,
    event_type: str,
    data: dict[str, Any],
) -> None:
    with factory() as session:
        session.add(
            ExecutionEvent(
                execution_id=exec_id,
                sequence=seq,
                event_type=event_type,
                timestamp=datetime.now(UTC),
                data=data,
            )
        )
        session.commit()


def _make_provider(
    factory: sessionmaker[Session], exec_id: uuid.UUID, timeout_s: float = 5.0
) -> BlackbeardHumanInputProvider:
    return BlackbeardHumanInputProvider(
        execution_id=exec_id,
        db_url="unused",
        session_factory=factory,
        timeout_s=timeout_s,
    )


class TestWriteRequest:
    def test_writes_request_event_with_max_plus_one_sequence(
        self, sync_factory: sessionmaker[Session]
    ) -> None:
        exec_id = uuid.uuid4()
        _add_execution(sync_factory, exec_id)
        _add_event(sync_factory, exec_id, 0, "crew_started", {})

        provider = _make_provider(sync_factory, exec_id)
        seq = provider._write_request(_REGULAR_PROMPT)

        assert seq == 1
        with sync_factory() as session:
            row = session.execute(
                select(ExecutionEvent).where(
                    ExecutionEvent.execution_id == exec_id,
                    ExecutionEvent.sequence == seq,
                )
            ).scalar_one()
            assert row.event_type == ExecutionEventType.HITL_REQUEST.value
            assert row.data == {"prompt": _REGULAR_PROMPT}

    def test_retries_on_sequence_collision(self, sync_factory: sessionmaker[Session]) -> None:
        exec_id = uuid.uuid4()
        _add_execution(sync_factory, exec_id)

        calls = {"n": 0}
        real_factory = sync_factory

        def flaky_factory() -> Session:
            calls["n"] += 1
            if calls["n"] < 3:
                raise IntegrityError("INSERT INTO...", {}, Exception("uq_exec_event"))
            return real_factory()

        provider = _make_provider(sync_factory, exec_id)
        provider._session_factory = flaky_factory  # type: ignore[method-assign]
        seq = provider._write_request(_REGULAR_PROMPT)

        assert calls["n"] == 3
        assert seq == 0

    def test_raises_after_exhausted_retries(self, sync_factory: sessionmaker[Session]) -> None:
        provider = _make_provider(sync_factory, uuid.uuid4())

        def always_fails() -> Session:
            raise IntegrityError("INSERT INTO...", {}, Exception("uq_exec_event"))

        provider._session_factory = always_fails  # type: ignore[method-assign]
        with pytest.raises(RuntimeError, match="hitl_request"):
            provider._write_request(_REGULAR_PROMPT)


class TestWaitForResponse:
    def test_returns_response_recorded_after_request(
        self, sync_factory: sessionmaker[Session]
    ) -> None:
        exec_id = uuid.uuid4()
        _add_execution(sync_factory, exec_id)
        _add_event(sync_factory, exec_id, 0, "crew_started", {})

        provider = _make_provider(sync_factory, exec_id)
        request_seq = provider._write_request(_REGULAR_PROMPT)
        _add_event(
            sync_factory, exec_id, request_seq + 1, "hitl_response", {"response": "shorter please"}
        )

        assert provider._wait_for_response(request_seq) == "shorter please"

    def test_ignores_stale_responses_from_earlier_rounds(
        self, sync_factory: sessionmaker[Session]
    ) -> None:
        exec_id = uuid.uuid4()
        _add_execution(sync_factory, exec_id)
        _add_event(sync_factory, exec_id, 0, "hitl_response", {"response": "stale"})

        provider = _make_provider(sync_factory, exec_id, timeout_s=0.2)
        request_seq = provider._write_request(_REGULAR_PROMPT)
        assert request_seq == 1

        assert provider._wait_for_response(request_seq) == ""

    def test_stops_waiting_when_execution_turns_terminal(
        self, sync_factory: sessionmaker[Session]
    ) -> None:
        exec_id = uuid.uuid4()
        _add_execution(sync_factory, exec_id)

        provider = _make_provider(sync_factory, exec_id, timeout_s=30)
        _set_execution_status(sync_factory, exec_id, ExecutionStatus.CANCELLED)

        started = time.monotonic()
        assert provider._wait_for_response(0) == ""
        assert time.monotonic() - started < 5


class StubContext:
    """Minimal ExecutorContext double covering the methods the provider uses."""

    def __init__(self, training_mode: bool = False) -> None:
        self.messages: list[dict[str, str]] = []
        self.ask_for_human_input = True
        self.training_mode = training_mode
        self.loops = 0
        self.training_outputs: list[tuple[Any, str | None]] = []

    def _is_training_mode(self) -> bool:
        return self.training_mode

    def _format_feedback_message(self, feedback: str) -> dict[str, str]:
        return {"role": "user", "content": feedback}

    def _invoke_loop(self) -> str:
        self.loops += 1
        return f"revised-{self.loops}"

    def _handle_crew_training_output(self, result: Any, human_feedback: str | None = None) -> None:
        self.training_outputs.append((result, human_feedback))


def _respond_to_requests(
    factory: sessionmaker[Session], exec_id: uuid.UUID, responses: list[str]
) -> threading.Thread:
    """Answer each pending hitl_request with the next canned response."""

    def respond() -> None:
        answered = 0
        deadline = time.monotonic() + 5
        while answered < len(responses) and time.monotonic() < deadline:
            target: ExecutionEvent | None = None
            with factory() as session:
                requests = (
                    session.execute(
                        select(ExecutionEvent)
                        .where(
                            ExecutionEvent.execution_id == exec_id,
                            ExecutionEvent.event_type == ExecutionEventType.HITL_REQUEST.value,
                        )
                        .order_by(ExecutionEvent.sequence)
                    )
                    .scalars()
                    .all()
                )
                for request in requests:
                    answered_already = session.execute(
                        select(ExecutionEvent.id)
                        .where(
                            ExecutionEvent.execution_id == exec_id,
                            ExecutionEvent.sequence > request.sequence,
                            ExecutionEvent.event_type == ExecutionEventType.HITL_RESPONSE.value,
                        )
                        .limit(1)
                    ).scalar_one_or_none()
                    if answered_already is None:
                        target = request
                        break
            if target is not None:
                _add_event(
                    factory,
                    exec_id,
                    target.sequence + 1,
                    "hitl_response",
                    {"response": responses[answered]},
                )
                answered += 1
            time.sleep(0.05)

    thread = threading.Thread(target=respond)
    thread.start()
    return thread


class TestHandleFeedbackBridge:
    def test_round_trip_feeds_response_back_and_loops(
        self, sync_factory: sessionmaker[Session]
    ) -> None:
        exec_id = uuid.uuid4()
        _add_execution(sync_factory, exec_id)
        provider = _make_provider(sync_factory, exec_id, timeout_s=10)
        context = StubContext()

        # First request gets real feedback, second an empty one (done).
        responder = _respond_to_requests(sync_factory, exec_id, ["use bullet points", ""])
        try:
            result = provider.handle_feedback("draft", context)
        finally:
            responder.join(timeout=10)

        assert not responder.is_alive()
        assert result == "revised-1"
        assert context.messages == [{"role": "user", "content": "use bullet points"}]
        assert context.ask_for_human_input is False

    def test_empty_first_response_returns_original_answer(
        self, sync_factory: sessionmaker[Session]
    ) -> None:
        exec_id = uuid.uuid4()
        _add_execution(sync_factory, exec_id)
        provider = _make_provider(sync_factory, exec_id, timeout_s=0.2)
        context = StubContext()

        result = provider.handle_feedback("original", context)

        assert result == "original"
        assert context.messages == []
        assert context.ask_for_human_input is False
        assert context.loops == 0

    def test_training_mode_single_iteration(self, sync_factory: sessionmaker[Session]) -> None:
        exec_id = uuid.uuid4()
        _add_execution(sync_factory, exec_id)
        provider = _make_provider(sync_factory, exec_id, timeout_s=10)
        context = StubContext(training_mode=True)

        responder = _respond_to_requests(sync_factory, exec_id, ["train better"])
        try:
            result = provider.handle_feedback("initial", context)
        finally:
            responder.join(timeout=10)

        assert not responder.is_alive()
        assert result == "revised-1"
        assert ("initial", "train better") in context.training_outputs
        assert (result, None) in context.training_outputs
        assert any(m["content"] == "train better" for m in context.messages)


class TestDatabaseHumanInputContextManager:
    def test_installs_and_restores_provider(self, sync_factory: sessionmaker[Session]) -> None:
        from crewai.core.providers.human_input import get_provider, reset_provider, set_provider

        sentinel = object()
        exec_id = uuid.uuid4()

        token = set_provider(sentinel)  # type: ignore[arg-type]
        try:
            with database_human_input(exec_id, session_factory=sync_factory):
                installed = get_provider()
                assert isinstance(installed, BlackbeardHumanInputProvider)
                assert installed._execution_id == exec_id
            assert get_provider() is sentinel

            # None execution id installs nothing.
            with database_human_input(None):
                assert get_provider() is sentinel
        finally:
            reset_provider(token)

    def test_restores_previous_provider_on_exception(
        self, sync_factory: sessionmaker[Session]
    ) -> None:
        from crewai.core.providers.human_input import get_provider, reset_provider, set_provider

        sentinel = object()
        token = set_provider(sentinel)  # type: ignore[arg-type]
        try:
            with pytest.raises(RuntimeError, match="boom"):
                with database_human_input(uuid.uuid4(), session_factory=sync_factory):
                    raise RuntimeError("boom")
            assert get_provider() is sentinel
        finally:
            reset_provider(token)


# ---------------------------------------------------------------------------
# Tests -- HITL respond endpoint (API)
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
