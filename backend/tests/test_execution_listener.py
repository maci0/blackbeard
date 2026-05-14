"""Tests for BlackbeardExecutionListener thread-safety and sequence generation."""

import threading

from blackbeard.engine.execution_listener import BlackbeardExecutionListener


class TestExecutionListenerSequencing:
    """Test thread-safe sequence number generation."""

    def test_next_seq_increments(self):
        """_next_seq should return monotonically increasing values."""
        # Bypass __init__ by creating an object and setting attrs directly
        listener = object.__new__(BlackbeardExecutionListener)
        listener._seq = 0
        listener._task_order = 0
        listener._lock = threading.Lock()

        assert listener._next_seq() == 0
        assert listener._next_seq() == 1
        assert listener._next_seq() == 2

    def test_next_seq_thread_safe(self):
        """_next_seq under concurrent access should produce unique values."""
        listener = object.__new__(BlackbeardExecutionListener)
        listener._seq = 0
        listener._task_order = 0
        listener._lock = threading.Lock()

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
