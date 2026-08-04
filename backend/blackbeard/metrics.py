"""Prometheus metrics for HTTP RED signals and execution pool saturation.

Metrics are designed for low cardinality (method + status only on HTTP
series) so scrapes stay cheap. Executor gauges are refreshed on each
``/metrics`` scrape when the transport layer supplies pool status.

Dependency rule: this module must not import ``blackbeard.engine`` (or any
higher layer). Callers that know about the executor (e.g. health routes)
pass ``pool_status`` into ``render_metrics`` so the engine never cycles
back through metrics.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "CONTENT_TYPE_LATEST",
    "record_execution_outcome",
    "record_http_request",
    "record_webhook_delivery",
    "render_metrics",
    "set_sse_usage",
]

logger = logging.getLogger(__name__)

# Dedicated registry so tests can isolate collectors and we avoid double-
# registration if the module is reloaded under pytest.
REGISTRY = CollectorRegistry(auto_describe=True)

HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests handled by the API",
    ["method", "status"],
    registry=REGISTRY,
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "status"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
    registry=REGISTRY,
)

ACTIVE_EXECUTIONS = Gauge(
    "blackbeard_active_executions",
    "Executor threads currently running crew work",
    registry=REGISTRY,
)

EXECUTOR_QUEUED_TASKS = Gauge(
    "blackbeard_executor_queued_tasks",
    "Crew executions waiting on the thread pool queue",
    registry=REGISTRY,
)

EXECUTOR_MAX_WORKERS = Gauge(
    "blackbeard_executor_max_workers",
    "Configured maximum concurrent crew executions",
    registry=REGISTRY,
)

EXECUTOR_SATURATED = Gauge(
    "blackbeard_executor_saturated",
    "1 when the executor is at max workers with a non-empty queue",
    registry=REGISTRY,
)

EXECUTIONS_TOTAL = Counter(
    "blackbeard_executions_total",
    "Crew/flow executions that reached a terminal status",
    ["type", "status"],
    registry=REGISTRY,
)

# Crew runs are minutes-scale; buckets cover sub-second failures through hours.
EXECUTION_DURATION_SECONDS = Histogram(
    "blackbeard_execution_duration_seconds",
    "Wall-clock duration of terminal crew/flow executions",
    ["type", "status"],
    buckets=(1.0, 5.0, 15.0, 30.0, 60.0, 120.0, 300.0, 600.0, 1800.0, 3600.0, 7200.0),
    registry=REGISTRY,
)

WEBHOOK_DELIVERIES_TOTAL = Counter(
    "blackbeard_webhook_deliveries_total",
    "Outbound webhook delivery attempts by outcome",
    ["status"],
    registry=REGISTRY,
)

SSE_ACTIVE = Gauge(
    "blackbeard_sse_active",
    "Active SSE streams (execution event subscriptions)",
    registry=REGISTRY,
)

SSE_MAX = Gauge(
    "blackbeard_sse_max",
    "Configured maximum concurrent SSE streams",
    registry=REGISTRY,
)

# Bound method/status label cardinality: HTTP methods are fixed; status is 3 digits.
_ALLOWED_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"})
_WEBHOOK_STATUSES = frozenset({"success", "failure", "error", "ssrf_blocked"})


def record_http_request(method: str, status_code: int, duration_seconds: float) -> None:
    """Record one completed HTTP request for RED metrics."""
    method_label = method.upper() if method.upper() in _ALLOWED_METHODS else "OTHER"
    status_label = str(int(status_code)) if 100 <= int(status_code) <= 599 else "000"
    # Clamp pathological durations (clock skew) so histograms stay useful.
    duration = max(0.0, min(float(duration_seconds), 600.0))
    HTTP_REQUESTS_TOTAL.labels(method=method_label, status=status_label).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(method=method_label, status=status_label).observe(duration)


def record_execution_outcome(
    execution_type: str,
    status: str,
    duration_seconds: float | None = None,
) -> None:
    """Record a terminal execution outcome (completed / failed / cancelled).

    When ``duration_seconds`` is provided, also observe the execution-duration
    histogram so operators can alert on p95 crew latency (not just failure rate).
    """
    type_label = (execution_type or "unknown")[:32]
    status_label = (status or "unknown")[:32]
    EXECUTIONS_TOTAL.labels(type=type_label, status=status_label).inc()
    if duration_seconds is not None:
        # Clamp clock skew / missing clocks; crews can legitimately run hours.
        duration = max(0.0, min(float(duration_seconds), 86400.0))
        EXECUTION_DURATION_SECONDS.labels(type=type_label, status=status_label).observe(duration)


def record_webhook_delivery(status: str, duration_seconds: float | None = None) -> None:
    """Record one outbound webhook delivery attempt.

    ``status`` is one of: success, failure (HTTP 4xx/5xx), error (network),
    ssrf_blocked. Duration is logged only (no histogram) to avoid scrape bloat
    for a fire-and-forget side path; the counter is the operational signal.
    """
    status_label = status if status in _WEBHOOK_STATUSES else "unknown"
    WEBHOOK_DELIVERIES_TOTAL.labels(status=status_label).inc()
    # duration_seconds reserved for future histogram; keep API stable for callers.
    _ = duration_seconds


def set_sse_usage(active: int, max_streams: int) -> None:
    """Update SSE connection gauges (call on acquire/release)."""
    SSE_ACTIVE.set(float(max(0, int(active))))
    SSE_MAX.set(float(max(0, int(max_streams))))


def _apply_pool_status(pool: Mapping[str, object]) -> None:
    """Write executor pool stats into gauges for the next scrape export."""
    ACTIVE_EXECUTIONS.set(float(cast("int", pool["active_threads"])))
    EXECUTOR_QUEUED_TASKS.set(float(cast("int", pool["queued_tasks"])))
    EXECUTOR_MAX_WORKERS.set(float(cast("int", pool["max_workers"])))
    EXECUTOR_SATURATED.set(1.0 if pool["saturated"] else 0.0)


def render_metrics(*, pool_status: Mapping[str, object] | None = None) -> bytes:
    """Return Prometheus text exposition of all registered metrics.

    When ``pool_status`` is provided (typically from
    ``blackbeard.engine.get_pool_status`` at the API boundary), executor
    gauges are refreshed before export. Omitting it leaves gauges at their
    last values (or zero if never set).
    """
    if pool_status is not None:
        try:
            _apply_pool_status(pool_status)
        except Exception:
            logger.warning(
                "Failed to refresh executor gauges for metrics scrape",
                exc_info=True,
                extra={"event": "metrics_executor_gauge_refresh_failed"},
            )
    return generate_latest(REGISTRY)
