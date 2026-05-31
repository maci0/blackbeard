"""CrewAI event listener that writes execution events to the database.

Captures events during crew execution and persists them as ExecutionEvent
rows for real-time SSE streaming to the UI. Uses synchronous DB sessions
since CrewAI callbacks run on a separate thread.
"""

from __future__ import annotations

import collections
import functools
import hashlib
import hmac
import json
import logging
import threading
import time as _time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from crewai.events import (
    BaseEventListener,
    CrewKickoffCompletedEvent,
    CrewKickoffStartedEvent,
    LLMCallCompletedEvent,
    LLMCallStartedEvent,
    TaskCompletedEvent,
    TaskStartedEvent,
    ToolUsageFinishedEvent,
    ToolUsageStartedEvent,
)
from sqlalchemy import create_engine, func, update
from sqlalchemy import select as sync_select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy import Engine

from urllib.parse import urlparse

from blackbeard.http_client import get_sync_client
from blackbeard.logging_config import request_id_var, safe_log_url
from blackbeard.models import ExecutionEvent, ExecutionTask, TaskStatus
from blackbeard.models.execution_schemas import redact_sensitive_values
from blackbeard.pii import redact_dict as _redact_dict
from blackbeard.pii import redact_text as _redact_text_fn
from blackbeard.resources import is_internal_host

# ---------------------------------------------------------------------------
# Optional OpenTelemetry integration
# ---------------------------------------------------------------------------
try:
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource as OTELResource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    HAS_OTEL = True
except ImportError:
    HAS_OTEL = False

__all__ = [
    "BlackbeardExecutionListener",
    "dispose_sync_engine",
    "invalidate_webhook_cache",
    "shutdown_otel",
    "shutdown_webhook_executor",
]

logger = logging.getLogger(__name__)

_otel_tracer: Any = None
_otel_setup_lock = threading.Lock()
_otel_provider: Any = None


def _get_otel_tracer() -> Any:
    """Return a shared OpenTelemetry tracer, initializing the provider on first call.

    Returns ``None`` when OpenTelemetry is not installed or not configured.
    Uses lock-always pattern (safe under both GIL and free-threaded Python).
    """
    if not HAS_OTEL:
        return None

    with _otel_setup_lock:
        global _otel_tracer, _otel_provider
        if _otel_tracer is not None:
            return _otel_tracer

        from blackbeard.config import settings

        endpoint = settings.otel_endpoint
        if not endpoint:
            return None

        resource = OTELResource.create({"service.name": "blackbeard"})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _otel_provider = provider
        _otel_tracer = trace.get_tracer("blackbeard.execution")
        logger.info(
            "OpenTelemetry tracing enabled: endpoint=%s",
            endpoint,
            extra={"event": "otel_enabled", "otel_endpoint": endpoint},
        )
        return _otel_tracer


def shutdown_otel() -> None:
    """Shut down the OTEL provider. Called during application shutdown."""
    global _otel_provider, _otel_tracer
    with _otel_setup_lock:
        if _otel_provider is not None:
            _otel_provider.shutdown()
            _otel_provider = None
            _otel_tracer = None


_webhook_executor: Any = None
_webhook_executor_lock = threading.Lock()


def _get_webhook_executor() -> Any:
    """Return a shared ThreadPoolExecutor for fire-and-forget webhook delivery.

    Uses lock-always pattern (safe under both GIL and free-threaded Python).
    """
    with _webhook_executor_lock:
        global _webhook_executor
        if _webhook_executor is not None:
            return _webhook_executor
        from concurrent.futures import ThreadPoolExecutor

        from blackbeard.config import settings

        workers = max(4, settings.max_concurrent_executions * 2)
        _webhook_executor = ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix="webhook-deliver"
        )
        return _webhook_executor


def shutdown_webhook_executor() -> None:
    """Shut down the webhook delivery thread pool."""
    global _webhook_executor
    with _webhook_executor_lock:
        if _webhook_executor is not None:
            _webhook_executor.shutdown(wait=False)
            _webhook_executor = None


def _log_webhook_future_exception(future: Any, *, execution_id: str = "") -> None:
    """Log uncaught exceptions from webhook delivery futures."""
    try:
        exc = future.exception()
    except Exception:
        logger.warning(
            "Could not retrieve webhook future exception (likely cancelled)",
            exc_info=True,
            extra={
                "event": "webhook_future_exception_retrieval_failed",
                "execution_id": execution_id,
            },
        )
        return
    if exc is not None:
        logger.error(
            "Webhook delivery thread raised unhandled exception: %s",
            exc,
            exc_info=exc,
            extra={
                "event": "webhook_delivery_thread_error",
                "error_type": type(exc).__name__,
                "error_message": str(exc)[:500],
                "execution_id": execution_id,
            },
        )


_WEBHOOK_LOAD_LIMIT = 1000
_webhook_cache_entry: tuple[float, list[Any]] | None = None
_webhook_cache_lock = threading.Lock()
_WEBHOOK_CACHE_TTL = 300.0


def _get_cached_webhooks(db_url: str) -> list[Any]:
    """Return active webhooks, cached for 5min to avoid DB hit per event.

    Uses lock-always pattern (safe under both GIL and free-threaded Python).
    The lock is held during the DB query to prevent cache stampede — all
    threads hitting an expired cache simultaneously would otherwise all
    query the DB.  The query is bounded (LIMIT 1001) and fast.
    """
    global _webhook_cache_entry

    with _webhook_cache_lock:
        now = _time.monotonic()
        entry = _webhook_cache_entry
        if entry is not None:
            cache_time, cache = entry
            if (now - cache_time) < _WEBHOOK_CACHE_TTL:
                return cache

        from blackbeard.models.webhook import Webhook

        session_factory = _get_sync_session_factory(db_url)
        try:
            with session_factory() as session:
                result = session.execute(
                    sync_select(Webhook)
                    .where(Webhook.active.is_(True))
                    .order_by(Webhook.id)
                    .limit(_WEBHOOK_LOAD_LIMIT + 1)
                )
                cached = list(result.scalars())
                if len(cached) > _WEBHOOK_LOAD_LIMIT:
                    logger.warning(
                        "Active webhook count exceeds %d — some webhooks will not receive events",
                        _WEBHOOK_LOAD_LIMIT,
                        extra={
                            "event": "webhook_limit_exceeded",
                            "loaded": _WEBHOOK_LOAD_LIMIT,
                        },
                    )
                    cached = cached[:_WEBHOOK_LOAD_LIMIT]
                session.expunge_all()
        except Exception as exc:
            if entry is not None:
                logger.warning(
                    "Failed to refresh webhook cache — using stale data (%d webhooks): %s",
                    len(entry[1]),
                    exc,
                    exc_info=True,
                    extra={
                        "event": "webhook_load_failed_using_stale",
                        "error_type": type(exc).__name__,
                    },
                )
                return entry[1]
            logger.error(
                "Failed to load webhooks for event delivery — "
                "no stale cache available, webhook notifications will be skipped: %s",
                exc,
                exc_info=True,
                extra={
                    "event": "webhook_load_failed",
                    "error_type": type(exc).__name__,
                },
            )
            return []

        _webhook_cache_entry = (_time.monotonic(), cached)
        return cached


def invalidate_webhook_cache() -> None:
    """Clear the webhook cache (call after webhook create/update/delete)."""
    global _webhook_cache_entry
    with _webhook_cache_lock:
        _webhook_cache_entry = None
    with _webhook_host_cache_lock:
        _webhook_host_cache.clear()


def _deliver_single_webhook(
    webhook: Any,
    payload: str,
    event_type: str,
    execution_id: str = "",
) -> None:
    """Deliver a single webhook (called concurrently via ThreadPoolExecutor)."""
    safe_url = safe_log_url(webhook.url)
    t0 = _time.monotonic()
    try:
        client = get_sync_client("webhook-deliver", timeout=10, follow_redirects=False)
        sig = hmac.new(webhook.secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        resp = client.post(
            webhook.url,
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": sig,
                "X-Blackbeard-Event": event_type,
            },
        )
        latency_ms = round((_time.monotonic() - t0) * 1000, 1)
        if resp.status_code >= 400:
            logger.warning(
                "Webhook delivery failed: id=%s url=%s status=%d (%.0fms)",
                webhook.id,
                safe_url,
                resp.status_code,
                latency_ms,
                extra={
                    "event": "webhook_delivery_failed",
                    "webhook_id": str(webhook.id),
                    "webhook_url": safe_url,
                    "http_status": resp.status_code,
                    "event_type": event_type,
                    "execution_id": execution_id,
                    "latency_ms": latency_ms,
                },
            )
        else:
            logger.debug(
                "Webhook delivered: id=%s event=%s status=%d (%.0fms)",
                webhook.id,
                event_type,
                resp.status_code,
                latency_ms,
                extra={
                    "event": "webhook_delivered",
                    "webhook_id": str(webhook.id),
                    "http_status": resp.status_code,
                    "event_type": event_type,
                    "execution_id": execution_id,
                    "latency_ms": latency_ms,
                },
            )
    except Exception:
        latency_ms = round((_time.monotonic() - t0) * 1000, 1)
        logger.exception(
            "Webhook delivery error: id=%s url=%s event=%s (%.0fms)",
            webhook.id,
            safe_url,
            event_type,
            latency_ms,
            extra={
                "event": "webhook_delivery_error",
                "webhook_id": str(webhook.id),
                "webhook_url": safe_url,
                "event_type": event_type,
                "execution_id": execution_id,
                "latency_ms": latency_ms,
            },
        )


_webhook_host_cache: collections.OrderedDict[str, str | None] = collections.OrderedDict()
_webhook_host_cache_lock = threading.Lock()
_MAX_WEBHOOK_HOST_CACHE = 1000


def _get_webhook_hostname(webhook_url: str) -> str | None:
    """Return cached parsed hostname for a webhook URL. None if internal (blocked)."""
    with _webhook_host_cache_lock:
        cached = _webhook_host_cache.get(webhook_url)
        if cached is not None:
            _webhook_host_cache.move_to_end(webhook_url)
            return cached if cached != "" else None
    hostname = urlparse(webhook_url).hostname or ""
    is_blocked = is_internal_host(hostname) if hostname else True
    with _webhook_host_cache_lock:
        while len(_webhook_host_cache) >= _MAX_WEBHOOK_HOST_CACHE:
            _webhook_host_cache.popitem(last=False)
        _webhook_host_cache[webhook_url] = "" if is_blocked else hostname
    return None if is_blocked else hostname


def _prepare_webhook_targets(
    event_type: str,
    data: dict[str, Any],
    execution_id: str,
    db_url: str,
) -> tuple[str, list[Any]]:
    """Resolve webhooks and build payload. Returns (payload, targets)."""
    webhooks = _get_cached_webhooks(db_url)
    if not webhooks:
        return "", []

    targets = []
    for webhook in webhooks:
        if webhook.events and event_type not in webhook.events:
            continue
        hostname = _get_webhook_hostname(webhook.url)
        if hostname is None:
            logger.warning(
                "Webhook delivery blocked (SSRF): id=%s url=%s",
                webhook.id,
                safe_log_url(webhook.url),
                extra={
                    "event": "webhook_delivery_ssrf_blocked",
                    "webhook_id": str(webhook.id),
                    "webhook_url": safe_log_url(webhook.url),
                },
            )
            continue
        targets.append(webhook)

    if not targets:
        return "", []

    payload = json.dumps(
        {
            "event_type": event_type,
            "execution_id": execution_id,
            "data": redact_sensitive_values(data),
        },
        default=str,
    )

    return payload, targets


def _deliver_webhooks_sync(
    event_type: str,
    data: dict[str, Any],
    execution_id: str,
    db_url: str,
) -> None:
    """Deliver an event to all matching webhooks sequentially.

    Used by tests.  The live dispatch path uses ``_dispatch_webhook``
    which fans out individual deliveries to the shared webhook executor.
    """
    payload, targets = _prepare_webhook_targets(event_type, data, execution_id, db_url)
    for wh in targets:
        _deliver_single_webhook(wh, payload, event_type, execution_id=execution_id)


_sync_engine: Engine | None = None
_sync_session_factory: sessionmaker[Session] | None = None
_sync_engine_lock = threading.Lock()


def _get_sync_session_factory(db_url: str) -> sessionmaker[Session]:
    """Return a shared sync sessionmaker, creating engine+factory on first call.

    Both are thread-safe and not bound to event loops, so one instance
    can serve all execution listeners.
    Uses lock-always pattern (safe under both GIL and free-threaded Python).
    """
    with _sync_engine_lock:
        global _sync_engine, _sync_session_factory
        if _sync_session_factory is not None:
            return _sync_session_factory

        from blackbeard.config import settings

        sync_url = db_url.replace("postgresql+asyncpg", "postgresql+psycopg").replace(
            "postgresql+aiopg", "postgresql+psycopg"
        )
        pool_size = max(5, settings.max_concurrent_executions * 3)
        max_overflow = pool_size * 2
        _sync_engine = create_engine(
            sync_url,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=True,
            pool_recycle=3600,
            pool_timeout=30,
            connect_args={
                "options": "-c statement_timeout=30000"
                " -c idle_in_transaction_session_timeout=60000",
                "connect_timeout": 10,
            },
        )
        _sync_session_factory = sessionmaker(_sync_engine, class_=Session, expire_on_commit=False)
        from blackbeard.models.database import instrument_engine

        instrument_engine(_sync_engine, label="sync-events")
        logger.info(
            "Sync DB engine created for execution events",
            extra={
                "event": "sync_engine_created",
                "pool_size": pool_size,
                "max_overflow": max_overflow,
            },
        )
        return _sync_session_factory


def dispose_sync_engine() -> None:
    """Dispose the shared sync engine. Called during application shutdown."""
    global _sync_engine, _sync_session_factory
    with _sync_engine_lock:
        _sync_session_factory = None
        if _sync_engine is not None:
            _sync_engine.dispose()
            _sync_engine = None


class BlackbeardExecutionListener(BaseEventListener):
    """Writes CrewAI events to the execution_events table for real-time streaming."""

    _FLUSH_INTERVAL = 0.5
    _MAX_BUFFER = 20

    def __init__(
        self,
        execution_id: UUID,
        db_url: str,
        pii_config: dict[str, Any] | None = None,
    ) -> None:
        self._execution_id = execution_id
        self._execution_id_str = str(execution_id)
        self._db_url = db_url
        self._pii_config = pii_config
        self._pii_redact_events = bool(pii_config and pii_config.get("redact_events", True))
        self._pii_entities: list[str] | None = pii_config.get("entities") if pii_config else None
        self._pii_cache: dict[str, str] = {}
        self._seq = 0
        self._task_order = 0  # tracks which task (by order) is currently running
        self._lock = threading.Lock()  # guards _seq, _task_order, and _buffer
        self._session_factory = _get_sync_session_factory(db_url)
        self._buffer: list[ExecutionEvent] = []
        self._flush_timer: threading.Timer | None = None
        self._otel_tracer = _get_otel_tracer()
        self._otel_root_span: Any = None
        self._otel_active_spans: dict[str, Any] = {}
        super().__init__()
        logger.info(
            "Execution listener created: execution_id=%s otel=%s pii=%s",
            execution_id,
            self._otel_tracer is not None,
            self._pii_config is not None,
            extra={
                "event": "execution_listener_created",
                "execution_id": str(execution_id),
                "otel_enabled": self._otel_tracer is not None,
                "pii_enabled": self._pii_config is not None,
            },
        )

    def _ensure_request_id(self) -> None:
        """Set request_id ContextVar on the current thread for log correlation.

        CrewAI callbacks may run on the event bus thread which does not inherit
        the executor thread's ContextVar, so we re-set it here.
        """
        if request_id_var.get("-") == "-":
            request_id_var.set(self._execution_id_str)

    def _schedule_flush(self) -> None:
        """Schedule a deferred flush if one isn't already pending."""
        with self._lock:
            if self._flush_timer is None or not self._flush_timer.is_alive():
                self._flush_timer = threading.Timer(self._FLUSH_INTERVAL, self._flush_buffer)
                self._flush_timer.daemon = True
                self._flush_timer.start()

    def _flush_buffer(self) -> None:
        """Flush buffered events to DB in a single transaction."""
        with self._lock:
            to_flush = self._buffer
            self._buffer = []
        if not to_flush:
            return
        try:
            with self._session_factory() as session:
                session.add_all(to_flush)
                session.commit()
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "Events flushed: execution=%s count=%d",
                    self._execution_id,
                    len(to_flush),
                    extra={
                        "event": "events_flushed",
                        "execution_id": self._execution_id_str,
                        "count": len(to_flush),
                    },
                )
        except Exception as exc:
            if isinstance(exc, IntegrityError):
                self._renumber_events(to_flush)
            with self._lock:
                if isinstance(exc, IntegrityError) and self._buffer:
                    next_seq = self._seq
                    for evt in self._buffer:
                        evt.sequence = next_seq
                        next_seq += 1
                    self._seq = next_seq
                self._buffer = to_flush + self._buffer
            self._schedule_flush()
            logger.error(
                "Re-queued %d events for %s (flush failed, will retry on next flush): %s",
                len(to_flush),
                self._execution_id,
                exc,
                exc_info=True,
                extra={
                    "event": "event_flush_failed",
                    "execution_id": self._execution_id_str,
                    "requeued_count": len(to_flush),
                    "requeued_sequences": [e.sequence for e in to_flush],
                    "requeued_event_types": [e.event_type for e in to_flush],
                    "error_type": type(exc).__name__,
                    "error_message": str(exc)[:500],
                },
            )

    def _renumber_events(self, events: list[ExecutionEvent]) -> None:
        """Re-assign sequence numbers from current DB max after a collision.

        When the HITL endpoint inserts an event using DB-queried sequences,
        it can collide with the listener's locally-assigned sequence numbers.
        Without renumbering, the buffered events would permanently fail to
        flush due to the unique constraint on (execution_id, sequence).
        """
        try:
            with self._session_factory() as session:
                result = session.execute(
                    sync_select(func.coalesce(func.max(ExecutionEvent.sequence), -1)).where(
                        ExecutionEvent.execution_id == self._execution_id
                    )
                )
                max_seq = (result.scalar() or -1) + 1
            for event in events:
                event.sequence = max_seq
                max_seq += 1
            with self._lock:
                self._seq = max(self._seq, max_seq)
            logger.info(
                "Renumbered %d events for %s after sequence collision (new start=%d)",
                len(events),
                self._execution_id,
                max_seq - len(events),
                extra={
                    "event": "events_renumbered",
                    "execution_id": self._execution_id_str,
                    "count": len(events),
                    "new_start_seq": max_seq - len(events),
                },
            )
        except Exception:
            with self._lock:
                fallback_seq = self._seq
                for event in events:
                    event.sequence = fallback_seq
                    fallback_seq += 1
                self._seq = fallback_seq
            logger.warning(
                "Failed to renumber events for %s after sequence collision — "
                "using local counter fallback (start=%d)",
                self._execution_id,
                fallback_seq - len(events),
                exc_info=True,
                extra={
                    "event": "event_renumber_failed",
                    "execution_id": self._execution_id_str,
                    "fallback_start_seq": fallback_seq - len(events),
                },
            )

    _FLUSH_RETRIES = 2

    def flush(self) -> None:
        """Force-flush any buffered events. Called at end of execution."""
        with self._lock:
            timer = self._flush_timer
            self._flush_timer = None
            orphaned_spans = self._otel_active_spans
            self._otel_active_spans = {}
            root_span = self._otel_root_span
            self._otel_root_span = None
        if timer is not None:
            timer.cancel()
            timer.join(timeout=5.0)
        self._flush_buffer()
        for attempt in range(self._FLUSH_RETRIES):
            with self._lock:
                remaining = len(self._buffer)
            if remaining == 0:
                break
            logger.warning(
                "Retrying final flush for execution %s: %d events still buffered (attempt %d/%d)",
                self._execution_id,
                remaining,
                attempt + 1,
                self._FLUSH_RETRIES,
                extra={
                    "event": "final_flush_retry",
                    "execution_id": self._execution_id_str,
                    "remaining_events": remaining,
                    "attempt": attempt + 1,
                },
            )
            _time.sleep(0.5)
            self._flush_buffer()
        with self._lock:
            lost = len(self._buffer)
        if lost > 0:
            logger.error(
                "Execution %s: %d events lost — could not flush after %d retries",
                self._execution_id,
                lost,
                self._FLUSH_RETRIES,
                extra={
                    "event": "events_lost",
                    "execution_id": self._execution_id_str,
                    "lost_count": lost,
                },
            )
        orphaned = len(orphaned_spans)
        for span_key, span in orphaned_spans.items():
            try:
                span.end()
            except Exception:
                logger.warning(
                    "Failed to end orphaned OTEL span '%s' for execution %s",
                    span_key,
                    self._execution_id,
                    exc_info=True,
                    extra={
                        "event": "otel_span_end_failed",
                        "execution_id": self._execution_id_str,
                        "span_key": span_key,
                    },
                )
        if root_span is not None:
            try:
                root_span.end()
            except Exception:
                logger.warning(
                    "Failed to end root OTEL span for execution %s",
                    self._execution_id,
                    exc_info=True,
                    extra={
                        "event": "otel_root_span_end_failed",
                        "execution_id": self._execution_id_str,
                    },
                )
        logger.info(
            "Execution listener flushed: execution_id=%s total_events=%d orphaned_spans=%d",
            self._execution_id,
            self._seq,
            orphaned,
            extra={
                "event": "execution_listener_flushed",
                "execution_id": self._execution_id_str,
                "total_events": self._seq,
                "orphaned_spans": orphaned,
            },
        )

    def _otel_start_span(self, name: str, attributes: dict[str, Any] | None = None) -> Any:
        """Start an OTEL span if tracing is enabled. Returns the span or None."""
        if self._otel_tracer is None:
            return None
        parent_ctx = None
        with self._lock:
            root = self._otel_root_span
        if root is not None:
            parent_ctx = trace.set_span_in_context(root)
        span = self._otel_tracer.start_span(name, context=parent_ctx, attributes=attributes or {})
        return span

    def _otel_end_span(self, key: str, attributes: dict[str, Any] | None = None) -> None:
        """End a previously started span identified by key."""
        with self._lock:
            span = self._otel_active_spans.pop(key, None)
        if span is not None:
            if attributes:
                for k, v in attributes.items():
                    span.set_attribute(k, v)
            span.end()

    def _dispatch_webhook(self, event_type: str, data: dict[str, Any]) -> None:
        """Fire webhook delivery in background threads (fire-and-forget).

        Each matching webhook is delivered concurrently via the shared
        webhook executor, so a slow endpoint cannot block others.
        """
        try:
            # Fast path: skip payload serialization when no webhooks are registered.
            # Read under lock for free-threaded Python safety.
            with _webhook_cache_lock:
                cached = _webhook_cache_entry
            if cached is not None and not cached[1]:
                return
            payload, targets = _prepare_webhook_targets(
                event_type,
                data,
                self._execution_id_str,
                self._db_url,
            )
            if not targets:
                return
            exec_id = self._execution_id_str
            executor = _get_webhook_executor()
            for wh in targets:
                future = executor.submit(
                    _deliver_single_webhook, wh, payload, event_type, execution_id=exec_id
                )
                future.add_done_callback(
                    functools.partial(_log_webhook_future_exception, execution_id=exec_id)
                )
        except Exception as exc:
            logger.warning(
                "Webhook dispatch skipped (executor unavailable): event=%s error=%s",
                event_type,
                exc,
                exc_info=True,
                extra={
                    "event": "webhook_dispatch_skipped",
                    "event_type": event_type,
                    "execution_id": self._execution_id_str,
                    "error_type": type(exc).__name__,
                },
            )

    def _write_event(self, event_type: str, data: dict[str, Any]) -> None:
        self._ensure_request_id()
        if self._pii_redact_events:
            data = _redact_dict(
                data,
                entities=self._pii_entities,
                config=self._pii_config,
                shared_cache=self._pii_cache,
            )
        now = datetime.now(UTC)
        flush_now = False
        with self._lock:
            seq = self._seq
            self._seq += 1
            event = ExecutionEvent(
                execution_id=self._execution_id,
                sequence=seq,
                event_type=event_type,
                timestamp=now,
                data=data,
            )
            self._buffer.append(event)
            buffer_size = len(self._buffer)
            if buffer_size >= self._MAX_BUFFER:
                flush_now = True
        if flush_now:
            self._flush_buffer()
        else:
            self._schedule_flush()
        # Fire webhook delivery in background
        self._dispatch_webhook(event_type, data)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "Event buffered: execution=%s type=%s seq=%d buffer=%d/%d",
                self._execution_id,
                event_type,
                seq,
                buffer_size,
                self._MAX_BUFFER,
                extra={
                    "event": "event_buffered",
                    "execution_id": self._execution_id_str,
                    "event_type": event_type,
                    "sequence": seq,
                    "buffer_size": buffer_size,
                    "buffer_max": self._MAX_BUFFER,
                },
            )

    def _write_event_with_task_update(
        self,
        event_type: str,
        data: dict[str, Any],
        task_order: int,
        task_status: TaskStatus,
        task_output: str | None = None,
        task_started_at: datetime | None = None,
        task_completed_at: datetime | None = None,
    ) -> None:
        """Write an event and update a task in a single DB transaction.

        Also flushes any buffered events to maintain ordering.
        """
        self._ensure_request_id()
        if self._pii_redact_events:
            data = _redact_dict(
                data,
                entities=self._pii_entities,
                config=self._pii_config,
                shared_cache=self._pii_cache,
            )
            if task_output is not None:
                task_output = _redact_text_fn(
                    task_output,
                    entities=self._pii_entities,
                    config=self._pii_config,
                )
        # Cancel any pending flush timer and wait for an in-flight flush
        # to complete BEFORE draining the buffer.  This ensures that if the
        # timer's _flush_buffer failed and re-queued events, those events
        # are back in the buffer when we drain it below — preventing the
        # SSE consumer from skipping lower-sequence events.
        with self._lock:
            timer = self._flush_timer
            self._flush_timer = None
        if timer is not None:
            timer.cancel()
            timer.join(timeout=5.0)

        now = datetime.now(UTC)
        with self._lock:
            seq = self._seq
            self._seq += 1
            event = ExecutionEvent(
                execution_id=self._execution_id,
                sequence=seq,
                event_type=event_type,
                timestamp=now,
                data=data,
            )
            to_flush = self._buffer
            self._buffer = []
            to_flush.append(event)
        try:
            with self._session_factory() as session:
                session.add_all(to_flush)
                values: dict[str, Any] = {"status": task_status}
                if task_output is not None:
                    values["output"] = task_output
                if task_started_at is not None:
                    values["started_at"] = task_started_at
                if task_completed_at is not None:
                    values["completed_at"] = task_completed_at
                session.execute(
                    update(ExecutionTask)
                    .where(
                        ExecutionTask.execution_id == self._execution_id,
                        ExecutionTask.order == task_order,
                    )
                    .values(**values)
                )
                session.commit()
            # Fire webhook delivery in background
            self._dispatch_webhook(event_type, data)
        except Exception as exc:
            if isinstance(exc, IntegrityError):
                self._renumber_events(to_flush)
            with self._lock:
                if isinstance(exc, IntegrityError) and self._buffer:
                    next_seq = self._seq
                    for evt in self._buffer:
                        evt.sequence = next_seq
                        next_seq += 1
                    self._seq = next_seq
                self._buffer = to_flush + self._buffer
            self._schedule_flush()
            logger.exception(
                "Failed to write event+task for %s: type=%s order=%d — "
                "task status in DB may be stale (expected %s)",
                self._execution_id,
                event_type,
                task_order,
                task_status.value,
                extra={
                    "event": "event_task_write_failed",
                    "execution_id": self._execution_id_str,
                    "event_type": event_type,
                    "task_order": task_order,
                    "expected_task_status": task_status.value,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc)[:500],
                },
            )

    def setup_listeners(self, crewai_event_bus: Any) -> None:
        @crewai_event_bus.on(CrewKickoffStartedEvent)  # type: ignore[untyped-decorator]
        def on_crew_started(source: Any, event: CrewKickoffStartedEvent) -> None:
            crew_name = event.crew_name or "unknown"
            raw_inputs = event.inputs or {}
            data = {
                "crew_name": crew_name,
                "inputs": redact_sensitive_values(raw_inputs) if raw_inputs else {},
            }
            self._write_event("crew_started", data)
            # OTEL: start root span for crew execution
            span = self._otel_start_span(
                f"crew.kickoff/{crew_name}",
                attributes={
                    "blackbeard.execution_id": self._execution_id_str,
                    "blackbeard.crew_name": crew_name,
                },
            )
            if span is not None:
                with self._lock:
                    self._otel_root_span = span

        @crewai_event_bus.on(CrewKickoffCompletedEvent)  # type: ignore[untyped-decorator]
        def on_crew_completed(source: Any, event: CrewKickoffCompletedEvent) -> None:
            data = {"total_tokens": event.total_tokens}
            self._write_event("crew_completed", data)
            # OTEL: end root span
            with self._lock:
                root_span = self._otel_root_span
                self._otel_root_span = None
            if root_span is not None:
                root_span.set_attribute("blackbeard.total_tokens", event.total_tokens or 0)
                root_span.end()

        @crewai_event_bus.on(TaskStartedEvent)  # type: ignore[untyped-decorator]
        def on_task_started(source: Any, event: TaskStartedEvent) -> None:
            task_name = event.task_name or "unknown"
            data = {
                "task_name": task_name,
                "agent_role": event.agent_role,
            }
            with self._lock:
                order = self._task_order
            now = datetime.now(UTC)
            self._write_event_with_task_update(
                "task_started",
                data,
                task_order=order,
                task_status=TaskStatus.RUNNING,
                task_started_at=now,
            )
            # OTEL: start task span
            span = self._otel_start_span(
                f"task/{task_name}",
                attributes={
                    "blackbeard.task_name": task_name,
                    "blackbeard.agent_role": event.agent_role or "",
                    "blackbeard.task_order": order,
                },
            )
            if span is not None:
                with self._lock:
                    self._otel_active_spans[f"task/{task_name}"] = span

        @crewai_event_bus.on(TaskCompletedEvent)  # type: ignore[untyped-decorator]
        def on_task_completed(source: Any, event: TaskCompletedEvent) -> None:
            task_name = event.task_name or "unknown"
            output = str(event.output) if event.output else None
            data = {
                "task_name": task_name,
                "output_preview": (output[:500] if output else None),
            }
            with self._lock:
                order = self._task_order
                self._task_order += 1
            now = datetime.now(UTC)
            self._write_event_with_task_update(
                "task_completed",
                data,
                task_order=order,
                task_status=TaskStatus.COMPLETED,
                task_output=output,
                task_completed_at=now,
            )
            # OTEL: end task span
            self._otel_end_span(f"task/{task_name}")

        @crewai_event_bus.on(ToolUsageStartedEvent)  # type: ignore[untyped-decorator]
        def on_tool_started(source: Any, event: ToolUsageStartedEvent) -> None:
            raw_args = event.tool_args
            if isinstance(raw_args, dict):
                raw_args = redact_sensitive_values(raw_args)
            data = {
                "tool_name": event.tool_name,
                "tool_args": str(raw_args)[:200] if raw_args else None,
                "agent_role": event.agent_role,
            }
            self._write_event("tool_started", data)
            # OTEL: start tool span
            span = self._otel_start_span(
                f"tool/{event.tool_name}",
                attributes={
                    "blackbeard.tool_name": event.tool_name or "",
                    "blackbeard.agent_role": event.agent_role or "",
                },
            )
            if span is not None:
                with self._lock:
                    self._otel_active_spans[f"tool/{event.tool_name}"] = span

        @crewai_event_bus.on(ToolUsageFinishedEvent)  # type: ignore[untyped-decorator]
        def on_tool_finished(source: Any, event: ToolUsageFinishedEvent) -> None:
            duration_ms = None
            started = getattr(event, "started_at", None)
            finished = getattr(event, "finished_at", None)
            if started and finished:
                duration_ms = int((finished - started).total_seconds() * 1000)
            data: dict[str, Any] = {
                "tool_name": event.tool_name,
                "from_cache": event.from_cache,
            }
            if duration_ms is not None:
                data["duration_ms"] = duration_ms
            self._write_event("tool_finished", data)
            # OTEL: end tool span
            otel_attrs: dict[str, Any] = {
                "blackbeard.from_cache": event.from_cache or False,
            }
            if duration_ms is not None:
                otel_attrs["blackbeard.duration_ms"] = duration_ms
            self._otel_end_span(
                f"tool/{event.tool_name}",
                attributes=otel_attrs,
            )

        @crewai_event_bus.on(LLMCallStartedEvent)  # type: ignore[untyped-decorator]
        def on_llm_started(source: Any, event: LLMCallStartedEvent) -> None:
            data = {
                "model": event.model,
                "agent_role": event.agent_role,
            }
            self._write_event("llm_started", data)
            # OTEL: start LLM span
            span = self._otel_start_span(
                f"llm/{event.model or 'unknown'}",
                attributes={
                    "blackbeard.model": event.model or "",
                    "blackbeard.agent_role": event.agent_role or "",
                },
            )
            if span is not None:
                with self._lock:
                    self._otel_active_spans[f"llm/{event.model or 'unknown'}"] = span

        @crewai_event_bus.on(LLMCallCompletedEvent)  # type: ignore[untyped-decorator]
        def on_llm_completed(source: Any, event: LLMCallCompletedEvent) -> None:
            usage = event.usage or {}
            response_preview = str(event.response)[:200] if event.response else None
            duration_ms = None
            started = getattr(event, "started_at", None)
            finished = getattr(event, "finished_at", None)
            if started and finished:
                duration_ms = int((finished - started).total_seconds() * 1000)
            data: dict[str, Any] = {
                "model": event.model,
                "tokens": usage.get("total_tokens", 0) if isinstance(usage, dict) else 0,
                "response_preview": response_preview,
            }
            if duration_ms is not None:
                data["duration_ms"] = duration_ms
            self._write_event("llm_completed", data)
            # OTEL: end LLM span
            otel_attrs: dict[str, Any] = {
                "blackbeard.tokens": usage.get("total_tokens", 0) if isinstance(usage, dict) else 0,
            }
            if duration_ms is not None:
                otel_attrs["blackbeard.duration_ms"] = duration_ms
            self._otel_end_span(f"llm/{event.model or 'unknown'}", attributes=otel_attrs)
