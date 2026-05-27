"""Rate limiters: per-IP auth failure limiter and per-user mutation limiter.

Tracks authentication failures per client IP and blocks requests that
exceed the configured threshold within a time window.  Thread-safe for
use from both async middleware and sync background tasks.

Also provides ``InMemoryRateLimiter`` — a reusable sliding-window counter
for per-user mutation rate limiting on resource, execution, marketplace,
copilot, and chat endpoints.
"""

from __future__ import annotations

import collections
import logging
import threading
import time
from typing import Any

from fastapi import HTTPException

from blackbeard.config import settings

logger = logging.getLogger(__name__)

_ANON_KEY = "__anonymous__"
_RATE_LIMIT_HEADERS = {"Retry-After": "60"}

__all__ = [
    "InMemoryRateLimiter",
    "chat_limiter",
    "check_rate_limit",
    "check_rate_limit_by_ip",
    "copilot_limiter",
    "execution_limiter",
    "is_rate_limited",
    "is_rate_limited_with_count",
    "marketplace_limiter",
    "mutation_limiter",
    "record_auth_failure",
    "registration_limiter",
]

_auth_failures: collections.OrderedDict[str, collections.deque[float]] = collections.OrderedDict()
_auth_failures_lock = threading.Lock()


def is_rate_limited_with_count(client_ip: str) -> tuple[bool, int]:
    """Return (is_limited, failure_count) in a single lock acquisition."""
    now = time.monotonic()
    with _auth_failures_lock:
        ip_failures = _auth_failures.get(client_ip)
        if ip_failures is None:
            return False, 0
        while ip_failures and ip_failures[0] < now - settings.auth_fail_window_seconds:
            ip_failures.popleft()
        if not ip_failures:
            del _auth_failures[client_ip]
            return False, 0
        count = len(ip_failures)
        return count >= settings.auth_fail_max_per_ip, count


def is_rate_limited(client_ip: str) -> bool:
    """Return True if client_ip has exceeded the auth failure threshold."""
    limited, _ = is_rate_limited_with_count(client_ip)
    return limited


def record_auth_failure(client_ip: str) -> None:
    """Record an authentication failure for rate limiting and prune stale entries."""
    now = time.monotonic()
    with _auth_failures_lock:
        if client_ip in _auth_failures:
            _auth_failures.move_to_end(client_ip)
        else:
            _auth_failures[client_ip] = collections.deque(
                maxlen=settings.auth_fail_max_per_ip + 10,
            )
        _auth_failures[client_ip].append(now)
        while len(_auth_failures) > settings.auth_fail_max_tracked_ips:
            _auth_failures.popitem(last=False)


# ---------------------------------------------------------------------------
# Per-user mutation rate limiter
# ---------------------------------------------------------------------------

_MAX_TRACKED_KEYS = 10_000


class InMemoryRateLimiter:
    """Sliding-window in-memory rate limiter.

    Thread-safe.  Tracks request timestamps per key (e.g. user ID) and
    rejects requests that exceed ``max_requests`` within
    ``window_seconds``.  Stale keys are pruned on every ``check()`` call
    to prevent unbounded memory growth.
    """

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._buckets: collections.OrderedDict[str, collections.deque[float]] = (
            collections.OrderedDict()
        )
        self._lock = threading.Lock()

    def check(self, key: str) -> bool:
        """Return True if the request is allowed, False if rate limited."""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = collections.deque(maxlen=self.max_requests + 10)
                self._buckets[key] = bucket
            else:
                self._buckets.move_to_end(key)

            while bucket and bucket[0] < cutoff:
                bucket.popleft()

            if len(bucket) >= self.max_requests:
                return False

            bucket.append(now)

            while len(self._buckets) > _MAX_TRACKED_KEYS:
                self._buckets.popitem(last=False)

        return True


# Pre-configured limiters for API endpoints
mutation_limiter = InMemoryRateLimiter(max_requests=100, window_seconds=60)
execution_limiter = InMemoryRateLimiter(max_requests=10, window_seconds=60)
marketplace_limiter = InMemoryRateLimiter(max_requests=5, window_seconds=60)
copilot_limiter = InMemoryRateLimiter(max_requests=10, window_seconds=60)
chat_limiter = InMemoryRateLimiter(max_requests=30, window_seconds=60)
registration_limiter = InMemoryRateLimiter(max_requests=5, window_seconds=3600)


def check_rate_limit(limiter: InMemoryRateLimiter, user: Any, detail: str) -> None:
    """Raise HTTP 429 if *user* exceeds *limiter*'s rate limit."""
    key = str(user.id) if user is not None else _ANON_KEY
    if not limiter.check(key):
        raise HTTPException(status_code=429, detail=detail, headers=_RATE_LIMIT_HEADERS)


def check_rate_limit_by_ip(limiter: InMemoryRateLimiter, ip: str, detail: str) -> None:
    """Raise HTTP 429 if *ip* exceeds *limiter*'s rate limit."""
    if not limiter.check(ip):
        raise HTTPException(status_code=429, detail=detail, headers=_RATE_LIMIT_HEADERS)
