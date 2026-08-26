"""Tests for the rate limiter module (security-critical).

Covers:
  - InMemoryRateLimiter: sliding window, thread safety, key pruning
  - Auth failure tracking: record, rate limit check, window expiry
  - check_rate_limit: HTTP 429 behaviour
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from blackbeard.rate_limiter import (
    InMemoryRateLimiter,
    _auth_failures,
    _auth_failures_lock,
    check_rate_limit,
    is_rate_limited,
    record_auth_failure,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_auth_failures():
    """Reset global auth-failure state before and after each test."""
    with _auth_failures_lock:
        _auth_failures.clear()
    yield
    with _auth_failures_lock:
        _auth_failures.clear()


# ---------------------------------------------------------------------------
# InMemoryRateLimiter: basic sliding window
# ---------------------------------------------------------------------------


class TestInMemoryRateLimiter:
    def test_allows_requests_within_limit(self):
        limiter = InMemoryRateLimiter(max_requests=3, window_seconds=60)
        assert limiter.check("user-1") is True
        assert limiter.check("user-1") is True
        assert limiter.check("user-1") is True

    def test_blocks_requests_over_limit(self):
        limiter = InMemoryRateLimiter(max_requests=2, window_seconds=60)
        assert limiter.check("user-1") is True
        assert limiter.check("user-1") is True
        assert limiter.check("user-1") is False

    def test_different_keys_independent(self):
        limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60)
        assert limiter.check("user-a") is True
        assert limiter.check("user-b") is True
        assert limiter.check("user-a") is False
        assert limiter.check("user-b") is False

    def test_window_expiry(self):
        limiter = InMemoryRateLimiter(max_requests=1, window_seconds=1)
        assert limiter.check("user-1") is True
        assert limiter.check("user-1") is False

        with patch("blackbeard.rate_limiter.time.monotonic", return_value=time.monotonic() + 2):
            assert limiter.check("user-1") is True

    def test_key_pruning(self):
        limiter = InMemoryRateLimiter(max_requests=10, window_seconds=60)

        with patch("blackbeard.rate_limiter._MAX_TRACKED_KEYS", 3):
            for i in range(5):
                limiter.check(f"user-{i}")

        assert len(limiter._buckets) <= 3

    def test_thread_safety(self):
        limiter = InMemoryRateLimiter(max_requests=100, window_seconds=60)
        results: list[bool] = []
        lock = threading.Lock()

        def worker():
            for _ in range(50):
                r = limiter.check("shared-key")
                with lock:
                    results.append(r)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 200
        allowed = sum(1 for r in results if r)
        denied = sum(1 for r in results if not r)
        assert allowed == 100
        assert denied == 100


# ---------------------------------------------------------------------------
# Auth failure rate limiting
# ---------------------------------------------------------------------------


class TestAuthFailureRateLimiting:
    def test_not_limited_initially(self):
        assert is_rate_limited("10.0.0.1") is False

    def test_limited_after_threshold(self):
        with patch("blackbeard.rate_limiter.settings") as mock_settings:
            mock_settings.auth_fail_max_per_ip = 3
            mock_settings.auth_fail_window_seconds = 300
            mock_settings.auth_fail_max_tracked_ips = 1000

            for _ in range(3):
                record_auth_failure("10.0.0.1")

            assert is_rate_limited("10.0.0.1") is True

    def test_not_limited_below_threshold(self):
        with patch("blackbeard.rate_limiter.settings") as mock_settings:
            mock_settings.auth_fail_max_per_ip = 5
            mock_settings.auth_fail_window_seconds = 300
            mock_settings.auth_fail_max_tracked_ips = 1000

            for _ in range(4):
                record_auth_failure("10.0.0.2")

            assert is_rate_limited("10.0.0.2") is False

    def test_different_ips_independent(self):
        with patch("blackbeard.rate_limiter.settings") as mock_settings:
            mock_settings.auth_fail_max_per_ip = 2
            mock_settings.auth_fail_window_seconds = 300
            mock_settings.auth_fail_max_tracked_ips = 1000

            for _ in range(2):
                record_auth_failure("10.0.0.3")

            assert is_rate_limited("10.0.0.3") is True
            assert is_rate_limited("10.0.0.4") is False

    def test_ip_pruning(self):
        with patch("blackbeard.rate_limiter.settings") as mock_settings:
            mock_settings.auth_fail_max_per_ip = 100
            mock_settings.auth_fail_window_seconds = 300
            mock_settings.auth_fail_max_tracked_ips = 3

            for i in range(5):
                record_auth_failure(f"10.0.0.{i}")

        with _auth_failures_lock:
            assert len(_auth_failures) <= 3


# ---------------------------------------------------------------------------
# check_rate_limit helper
# ---------------------------------------------------------------------------


class TestCheckRateLimit:
    def test_raises_429_when_limited(self):
        limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60)
        user = MagicMock()
        user.id = "user-xyz"

        check_rate_limit(limiter, user, "Too many requests")
        with pytest.raises(HTTPException) as exc_info:
            check_rate_limit(limiter, user, "Too many requests")

        assert exc_info.value.status_code == 429
        assert "Too many requests" in exc_info.value.detail

    def test_allows_when_within_limit(self):
        limiter = InMemoryRateLimiter(max_requests=5, window_seconds=60)
        user = MagicMock()
        user.id = "user-ok"

        check_rate_limit(limiter, user, "Rate limited")

    def test_anonymous_user_uses_shared_key(self):
        limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60)

        check_rate_limit(limiter, None, "Rate limited")
        with pytest.raises(HTTPException) as exc_info:
            check_rate_limit(limiter, None, "Rate limited")

        assert exc_info.value.status_code == 429
