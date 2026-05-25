"""Per-IP sliding-window auth failure rate limiter.

Tracks authentication failures per client IP and blocks requests that
exceed the configured threshold within a time window.  Thread-safe for
use from both async middleware and sync background tasks.
"""

from __future__ import annotations

import collections
import threading
import time

from blackbeard.config import settings

__all__ = [
    "is_rate_limited",
    "record_auth_failure",
]

_auth_failures: collections.OrderedDict[str, collections.deque[float]] = collections.OrderedDict()
_auth_failures_lock = threading.Lock()


def _is_rate_limited_with_count(client_ip: str) -> tuple[bool, int]:
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
    limited, _ = _is_rate_limited_with_count(client_ip)
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
