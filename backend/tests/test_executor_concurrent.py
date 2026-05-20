"""Tests for concurrent executor initialization and lifecycle.

Covers:
  - _get_executor() returns same instance on concurrent calls
  - shutdown_executor() is safe to call when no executor exists
  - get_pool_status() returns correct shape when executor is None
  - get_pool_status() returns correct shape when executor exists
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import blackbeard.engine.executor as executor_mod
from blackbeard.engine.executor import (
    _get_executor,
    get_pool_status,
    shutdown_executor,
)

# ---------------------------------------------------------------------------
# Tests -- _get_executor concurrency
# ---------------------------------------------------------------------------


def test_get_executor_returns_same_instance():
    """_get_executor() should return the same ThreadPoolExecutor on repeated calls."""
    original = executor_mod._executor
    try:
        executor_mod._executor = None

        first = _get_executor()
        second = _get_executor()

        assert first is second
        assert isinstance(first, ThreadPoolExecutor)
    finally:
        # Clean up
        if executor_mod._executor is not None and executor_mod._executor is not original:
            executor_mod._executor.shutdown(wait=False)
        executor_mod._executor = original


def test_get_executor_concurrent_calls():
    """Concurrent calls to _get_executor() should all get the same instance."""
    original = executor_mod._executor
    try:
        executor_mod._executor = None

        results: list[ThreadPoolExecutor] = []
        errors: list[Exception] = []

        def _get_and_store():
            try:
                results.append(_get_executor())
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_get_and_store) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert all(not t.is_alive() for t in threads), "Some threads did not complete"
        assert len(errors) == 0, f"Errors: {errors}"
        assert len(results) == 10

        # All should be the same instance
        first = results[0]
        for r in results[1:]:
            assert r is first
    finally:
        if executor_mod._executor is not None and executor_mod._executor is not original:
            executor_mod._executor.shutdown(wait=False)
        executor_mod._executor = original


# ---------------------------------------------------------------------------
# Tests -- shutdown_executor safety
# ---------------------------------------------------------------------------


def test_shutdown_executor_when_none():
    """shutdown_executor() should be safe when no executor exists."""
    original = executor_mod._executor
    try:
        executor_mod._executor = None

        # Should NOT raise
        with patch(
            "blackbeard.engine.execution_listener.dispose_sync_engine"
        ):
            shutdown_executor()

        assert executor_mod._executor is None
    finally:
        executor_mod._executor = original


def test_shutdown_executor_idempotent():
    """Calling shutdown_executor() twice should be safe."""
    original = executor_mod._executor
    try:
        executor_mod._executor = None
        # Force creation
        _get_executor()

        with patch(
            "blackbeard.engine.execution_listener.dispose_sync_engine"
        ):
            shutdown_executor()
        assert executor_mod._executor is None

        with patch(
            "blackbeard.engine.execution_listener.dispose_sync_engine"
        ):
            shutdown_executor()
        assert executor_mod._executor is None
    finally:
        executor_mod._executor = original


# ---------------------------------------------------------------------------
# Tests -- get_pool_status
# ---------------------------------------------------------------------------


def test_pool_status_no_executor():
    """get_pool_status() when executor is None should return safe defaults."""
    original = executor_mod._executor
    try:
        executor_mod._executor = None
        status = get_pool_status()

        assert status["active_threads"] == 0
        assert status["queued_tasks"] == 0
        assert status["saturated"] is False
        assert "max_workers" in status
    finally:
        executor_mod._executor = original


def test_pool_status_with_executor():
    """get_pool_status() when executor exists should report thread pool stats."""
    original = executor_mod._executor
    try:
        executor_mod._executor = None
        _get_executor()

        status = get_pool_status()
        assert isinstance(status["active_threads"], int)
        assert status["active_threads"] == 0
        assert isinstance(status["max_workers"], int)
        assert status["max_workers"] > 0
        assert isinstance(status["queued_tasks"], int)
        assert status["queued_tasks"] == 0
        assert status["saturated"] is False, (
            "Idle pool with no submitted tasks should not be saturated"
        )
    finally:
        if executor_mod._executor is not None and executor_mod._executor is not original:
            executor_mod._executor.shutdown(wait=False)
        executor_mod._executor = original
