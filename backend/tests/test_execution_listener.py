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


class TestExecutionListenerSequencing:
    """Test thread-safe sequence number generation."""

    def test_next_seq_increments(self):
        """_next_seq should return monotonically increasing values."""
        listener = _make_listener_stub()

        assert listener._next_seq() == 0
        assert listener._next_seq() == 1
        assert listener._next_seq() == 2

    def test_next_seq_thread_safe(self):
        """_next_seq under concurrent access should produce unique values."""
        listener = _make_listener_stub()

        results: list[int] = []
        lock = threading.Lock()

        def worker():
            for _ in range(100):
                seq = listener._next_seq()
                with lock:
                    results.append(seq)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All 400 values should be unique
        assert len(results) == 400
        assert len(set(results)) == 400

    def test_task_order_independent_of_seq(self):
        """_task_order should start at 0 and be independent of _seq."""
        listener = _make_listener_stub()

        # Advance _seq
        listener._next_seq()
        listener._next_seq()

        # _task_order should still be at initial value
        with listener._lock:
            assert listener._task_order == 0

        # Simulate task completion: _task_order increments in on_task_completed
        with listener._lock:
            order = listener._task_order
            listener._task_order += 1
        assert order == 0

        with listener._lock:
            assert listener._task_order == 1
