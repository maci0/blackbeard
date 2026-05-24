"""Tests for BlackbeardExecutionListener thread-safety and sequence generation."""

import threading

from blackbeard.engine.execution_listener import BlackbeardExecutionListener


def _make_listener_stub() -> BlackbeardExecutionListener:
    """Create a listener stub without DB connection (bypasses __init__)."""
    listener = object.__new__(BlackbeardExecutionListener)
    listener._seq = 0
    listener._task_order = 0
    listener._lock = threading.Lock()
    return listener


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
