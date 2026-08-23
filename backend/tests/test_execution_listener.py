"""Tests for BlackbeardExecutionListener thread-safety and sequence generation."""

import threading
import time
from datetime import UTC, datetime
from uuid import uuid4

from blackbeard.engine.execution_listener import BlackbeardExecutionListener
from blackbeard.models import ExecutionEvent, ExecutionEventType, TaskStatus


def _make_listener_stub() -> BlackbeardExecutionListener:
    """Create a listener stub without DB connection (bypasses __init__)."""
    listener = object.__new__(BlackbeardExecutionListener)
    listener._seq = 0
    listener._task_order = 0
    listener._lock = threading.Lock()
    return listener


def _make_full_stub(recorder: "CommitRecorder") -> BlackbeardExecutionListener:
    """Listener stub wired for flush/write-path tests (no real DB)."""
    listener = object.__new__(BlackbeardExecutionListener)
    execution_id = uuid4()
    listener._execution_id = execution_id
    listener._execution_id_str = str(execution_id)
    listener._seq = 0
    listener._task_order = 0
    listener._lock = threading.Lock()
    listener._flush_done = threading.Condition(listener._lock)
    listener._io_lock = threading.Lock()
    listener._flush_timer = None
    listener._flushing = False
    listener._buffer = []
    listener._pii_redact_events = False
    listener._session_factory = recorder.session_factory
    listener._schedule_flush = lambda: None  # type: ignore[method-assign]
    listener._dispatch_webhook = lambda *a, **k: None  # type: ignore[method-assign]
    return listener


class CommitRecorder:
    """Fake session factory tracking concurrent commits and their order."""

    def __init__(self, gate_first_commit: threading.Event | None = None) -> None:
        self.commits: list[list[int]] = []
        self.active = 0
        self.max_active = 0
        self.lock = threading.Lock()
        self.in_commit = threading.Event()
        self.gate_first_commit = gate_first_commit

    def session_factory(self):
        return _RecordingSession(self)

    def record(self, sequences: list[int]) -> None:
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            first = self.max_active == 1 and self.active == 1 and len(self.commits) == 0
            gated = self.gate_first_commit is not None and len(self.commits) == 0
            self.commits.append(list(sequences))
        if first or gated:
            self.in_commit.set()
        if gated:
            assert self.gate_first_commit is not None
            self.gate_first_commit.wait(timeout=10.0)
        with self.lock:
            self.active -= 1


class _RecordingSession:
    def __init__(self, recorder: CommitRecorder) -> None:
        self._recorder = recorder
        self._pending: list[int] = []

    def __enter__(self):
        return self

    def __exit__(self, *args: object):
        return False

    def add_all(self, events):
        self._pending = [e.sequence for e in events]

    def execute(self, *args, **kwargs):
        return None

    def commit(self):
        self._recorder.record(self._pending)


def _event(execution_id, sequence: int) -> ExecutionEvent:
    return ExecutionEvent(
        execution_id=execution_id,
        sequence=sequence,
        event_type=ExecutionEventType.CREW_STARTED.value,
        timestamp=datetime.now(UTC),
        data={},
    )


class TestFlushWriteSerialization:
    """Event-batch DB writes must be exclusive and land in sequence order.

    SSE consumers poll with ``sequence > last_seen``; if a later batch
    committed before an earlier one, the earlier events would never be
    delivered.
    """

    def test_concurrent_flushes_do_not_overlap_and_keep_order(self):
        gate = threading.Event()
        recorder = CommitRecorder(gate_first_commit=gate)
        listener = _make_full_stub(recorder)
        # Sequences 0 and 1 are handed to the manual batches below; keep the
        # internal counter in sync so the direct write gets sequence 2.
        listener._seq = 2

        def flush_batch(sequence: int) -> None:
            with listener._lock:
                listener._buffer.append(_event(listener._execution_id, sequence))
            listener._flush_buffer()

        t1 = threading.Thread(target=flush_batch, args=(0,))
        t1.start()
        assert recorder.in_commit.wait(timeout=5.0), "first flush never reached commit"

        # While the first batch's commit is parked mid-flight, start a second
        # flush and a direct task-event write from two other threads.
        t2 = threading.Thread(target=flush_batch, args=(1,))
        t2.start()

        def write_task_event() -> None:
            listener._write_event_with_task_update(
                ExecutionEventType.TASK_STARTED.value,
                {"task_name": "t"},
                task_order=0,
                task_status=TaskStatus.RUNNING,
            )

        t3 = threading.Thread(target=write_task_event)
        t3.start()
        time.sleep(0.1)

        assert recorder.max_active == 1, (
            f"event-batch writes overlapped (max_active={recorder.max_active})"
        )

        gate.set()
        t1.join(timeout=5.0)
        t2.join(timeout=5.0)
        t3.join(timeout=5.0)

        assert not any(t.is_alive() for t in (t1, t2, t3)), "flush threads deadlocked"
        committed_sequences = [s for batch in recorder.commits for s in batch]
        assert committed_sequences == sorted(committed_sequences), (
            f"commits out of sequence order: {recorder.commits}"
        )
        assert recorder.max_active == 1


def _next_seq(listener: BlackbeardExecutionListener) -> int:
    """Replicate inline seq increment used in the listener."""
    with listener._lock:
        seq = listener._seq
        listener._seq += 1
    return seq


class TestExecutionListenerSequencing:
    """Test thread-safe sequence number generation."""

    def test_seq_increments(self):
        """_seq should return monotonically increasing values."""
        listener = _make_listener_stub()

        assert _next_seq(listener) == 0
        assert _next_seq(listener) == 1
        assert _next_seq(listener) == 2

    def test_seq_thread_safe(self):
        """_seq under concurrent access should produce unique values."""
        listener = _make_listener_stub()

        results: list[int] = []
        lock = threading.Lock()

        def worker():
            for _ in range(100):
                seq = _next_seq(listener)
                with lock:
                    results.append(seq)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 400
        assert len(set(results)) == 400, "All sequence numbers must be unique"
        assert set(results) == set(range(400))

    def test_task_order_independent_of_seq(self):
        """_task_order should start at 0 and be independent of _seq."""
        listener = _make_listener_stub()

        _next_seq(listener)
        _next_seq(listener)

        with listener._lock:
            assert listener._task_order == 0

        with listener._lock:
            order = listener._task_order
            listener._task_order += 1
        assert order == 0

        with listener._lock:
            assert listener._task_order == 1


class _FailingSession:
    """Session stand-in simulating a prolonged DB outage."""

    def __enter__(self):
        return self

    def __exit__(self, *args: object):
        return False

    def add_all(self, events):
        raise RuntimeError("db down")

    def commit(self):
        raise RuntimeError("db down")


class TestPendingBufferBound:
    """Failed flushes requeue into the buffer; pending events must stay bounded.

    Without the cap, a long-running execution during a DB outage grows the
    in-memory buffer without bound for its whole lifetime.
    """

    def _make_outage_stub(self) -> BlackbeardExecutionListener:
        listener = _make_full_stub(CommitRecorder())
        listener._session_factory = lambda: _FailingSession()
        return listener

    def test_buffer_never_exceeds_cap_during_outage(self):
        listener = self._make_outage_stub()
        cap = BlackbeardExecutionListener._MAX_PENDING_EVENTS
        total = cap + 250
        for i in range(total):
            listener._write_event(ExecutionEventType.CREW_STARTED.value, {"i": i})
        assert len(listener._buffer) == cap
        assert listener._buffer[0].sequence == total - cap
        assert listener._buffer[-1].sequence == total - 1

    def test_direct_write_path_also_bounded(self):
        listener = self._make_outage_stub()
        cap = BlackbeardExecutionListener._MAX_PENDING_EVENTS
        with listener._lock:
            listener._buffer = [_event(listener._execution_id, i) for i in range(cap)]
            listener._seq = cap
        listener._write_event_with_task_update(
            ExecutionEventType.TASK_COMPLETED.value,
            {},
            task_order=0,
            task_status=TaskStatus.COMPLETED,
        )
        assert len(listener._buffer) == cap
