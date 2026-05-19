"""CrewAI event listener that writes execution events to the database.

Captures events during crew execution and persists them as ExecutionEvent
rows for real-time SSE streaming to the UI. Uses synchronous DB sessions
since CrewAI callbacks run on a separate thread.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import threading
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
from sqlalchemy import create_engine, update
from sqlalchemy.orm import Session, sessionmaker

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy import Engine

from blackbeard.http_client import get_sync_client
from blackbeard.logging_config import request_id_var
from blackbeard.models import ExecutionEvent, ExecutionTask, TaskStatus

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

logger = logging.getLogger(__name__)

_otel_tracer: Any = None
_otel_setup_lock = threading.Lock()
_otel_provider: Any = None


def _get_otel_tracer() -> Any:
    """Return a shared OpenTelemetry tracer, initializing the provider on first call.

    Returns ``None`` when OpenTelemetry is not installed or not configured.
    """
    global _otel_tracer, _otel_provider
    if not HAS_OTEL:
        return None
    if _otel_tracer is not None:
        return _otel_tracer

    from blackbeard.config import settings

    endpoint = settings.otel_endpoint
    if not endpoint:
        return None

    with _otel_setup_lock:
        if _otel_tracer is not None:
            return _otel_tracer

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
    """Return a shared ThreadPoolExecutor for fire-and-forget webhook delivery."""
    global _webhook_executor
    if _webhook_executor is not None:
        return _webhook_executor
    with _webhook_executor_lock:
        if _webhook_executor is not None:
            return _webhook_executor
        from concurrent.futures import ThreadPoolExecutor

        _webhook_executor = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="webhook-deliver"
        )
        return _webhook_executor


def shutdown_webhook_executor() -> None:
    """Shut down the webhook delivery thread pool."""
    global _webhook_executor
    with _webhook_executor_lock:
        if _webhook_executor is not None:
            _webhook_executor.shutdown(wait=False)
            _webhook_executor = None


_webhook_cache: list[Any] | None = None
_webhook_cache_time: float = 0.0
_webhook_cache_lock = threading.Lock()
_WEBHOOK_CACHE_TTL = 30.0


def _get_cached_webhooks(db_url: str) -> list[Any]:
    """Return active webhooks, cached for 30s to avoid DB hit per event."""
    global _webhook_cache, _webhook_cache_time
    import time as _time

    now = _time.monotonic()
    if _webhook_cache is not None and (now - _webhook_cache_time) < _WEBHOOK_CACHE_TTL:
        return _webhook_cache

    with _webhook_cache_lock:
        if _webhook_cache is not None and (now - _webhook_cache_time) < _WEBHOOK_CACHE_TTL:
            return _webhook_cache

        from blackbeard.models.webhook import Webhook

        session_factory = _get_sync_session_factory(db_url)
        try:
            with session_factory() as session:
                from sqlalchemy import select as sync_select

                result = session.execute(
                    sync_select(Webhook).where(Webhook.active.is_(True))
                )
                cached = list(result.scalars())
                # Detach from session so they can be used outside
                session.expunge_all()
        except Exception:
            logger.exception(
                "Failed to load webhooks for event delivery",
                extra={"event": "webhook_load_failed"},
            )
            return []

        _webhook_cache = cached
        _webhook_cache_time = _time.monotonic()
        return cached


def invalidate_webhook_cache() -> None:
    """Clear the webhook cache (call after webhook create/update/delete)."""
    global _webhook_cache, _webhook_cache_time
    with _webhook_cache_lock:
        _webhook_cache = None
        _webhook_cache_time = 0.0


def _deliver_webhooks_sync(
    event_type: str,
    data: dict[str, Any],
    execution_id: str,
    db_url: str,
) -> None:
    """Deliver an event to all matching webhooks (runs in background thread).

    Uses a 30s cache for webhook list to avoid DB query per event.
    POSTs the payload with HMAC-SHA256 signature. Failures are logged
    but never raised — webhook delivery must not block execution.
    """
    from urllib.parse import urlparse

    from blackbeard.resources.validator import is_internal_host

    webhooks = _get_cached_webhooks(db_url)
    if not webhooks:
        return

    payload = json.dumps(
        {
            "event_type": event_type,
            "execution_id": execution_id,
            "data": data,
        },
        default=str,
    )

    client = get_sync_client("webhook-deliver", timeout=10)

    for webhook in webhooks:
        if webhook.events and event_type not in webhook.events:
            continue
        # Re-validate hostname at delivery time to mitigate TOCTOU SSRF
        # (DNS rebinding between webhook creation and event delivery).
        parsed = urlparse(webhook.url)
        hostname = parsed.hostname or ""
        if is_internal_host(hostname):
            logger.warning(
                "Webhook delivery blocked (SSRF): id=%s url=%s hostname=%s",
                webhook.id,
                webhook.url,
                hostname,
                extra={
                    "event": "webhook_delivery_ssrf_blocked",
                    "webhook_id": str(webhook.id),
                    "webhook_url": webhook.url,
                    "hostname": hostname,
                },
            )
            continue
        try:
            sig = hmac.new(
                webhook.secret.encode(), payload.encode(), hashlib.sha256
            ).hexdigest()
            resp = client.post(
                webhook.url,
                content=payload,
                headers={
                    "Content-Type": "application/json",
                    "X-Webhook-Signature": sig,
                    "X-Blackbeard-Event": event_type,
                },
            )
            if resp.status_code >= 400:
                logger.warning(
                    "Webhook delivery failed: id=%s url=%s status=%d",
                    webhook.id,
                    webhook.url,
                    resp.status_code,
                    extra={
                        "event": "webhook_delivery_failed",
                        "webhook_id": str(webhook.id),
                        "webhook_url": webhook.url,
                        "http_status": resp.status_code,
                        "event_type": event_type,
                    },
                )
            elif logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "Webhook delivered: id=%s event=%s",
                    webhook.id,
                    event_type,
                )
        except Exception:
            logger.exception(
                "Webhook delivery error: id=%s url=%s event=%s",
                webhook.id,
                webhook.url,
                event_type,
                extra={
                    "event": "webhook_delivery_error",
                    "webhook_id": str(webhook.id),
                    "webhook_url": webhook.url,
                    "event_type": event_type,
                },
            )


_sync_engine: Engine | None = None
_sync_session_factory: sessionmaker[Session] | None = None
_sync_engine_lock = threading.Lock()


def _get_sync_session_factory(db_url: str) -> sessionmaker[Session]:
    """Return a shared sync sessionmaker, creating engine+factory on first call.

    Both are thread-safe and not bound to event loops, so one instance
    can serve all execution listeners.
    """
    global _sync_engine, _sync_session_factory
    if _sync_session_factory is not None:
        return _sync_session_factory
    with _sync_engine_lock:
        if _sync_session_factory is not None:
            return _sync_session_factory
        sync_url = db_url.replace("postgresql+asyncpg", "postgresql+psycopg").replace(
            "postgresql+aiopg", "postgresql+psycopg"
        )
        _sync_engine = create_engine(
            sync_url,
            pool_size=5,
            max_overflow=10,
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
        logger.info(
            "Sync DB engine created for execution events",
            extra={"event": "sync_engine_created", "pool_size": 5, "max_overflow": 10},
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

    _FLUSH_INTERVAL = 0.5  # seconds between buffer flushes
    _MAX_BUFFER = 20  # flush if buffer reaches this size

    def __init__(self, execution_id: UUID, db_url: str) -> None:
        self._execution_id = execution_id
        self._db_url = db_url
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
            "Execution listener created: execution_id=%s otel=%s",
            execution_id,
            self._otel_tracer is not None,
            extra={
                "event": "execution_listener_created",
                "execution_id": str(execution_id),
                "otel_enabled": self._otel_tracer is not None,
            },
        )

    def _next_seq(self) -> int:
        with self._lock:
            seq = self._seq
            self._seq += 1
            return seq

    def _ensure_request_id(self) -> None:
        """Set request_id ContextVar on the current thread for log correlation.

        CrewAI callbacks may run on the event bus thread which does not inherit
        the executor thread's ContextVar, so we re-set it here.
        """
        if request_id_var.get("-") == "-":
            request_id_var.set(str(self._execution_id))

    def _schedule_flush(self) -> None:
        """Schedule a deferred flush if one isn't already pending."""
        if self._flush_timer is None or not self._flush_timer.is_alive():
            self._flush_timer = threading.Timer(self._FLUSH_INTERVAL, self._flush_buffer)
            self._flush_timer.daemon = True
            self._flush_timer.start()

    def _flush_buffer(self) -> None:
        """Flush buffered events to DB in a single transaction."""
        with self._lock:
            to_flush = list(self._buffer)
            self._buffer.clear()
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
                        "execution_id": str(self._execution_id),
                        "count": len(to_flush),
                    },
                )
        except Exception as exc:
            logger.exception(
                "Dropped %d events for %s (flush failed, not retried): %s",
                len(to_flush),
                self._execution_id,
                exc,
                extra={
                    "event": "event_flush_failed",
                    "execution_id": str(self._execution_id),
                    "dropped_count": len(to_flush),
                    "dropped_sequences": [e.sequence for e in to_flush],
                    "dropped_event_types": [e.event_type for e in to_flush],
                    "error_type": type(exc).__name__,
                    "error_message": str(exc)[:500],
                },
            )

    def flush(self) -> None:
        """Force-flush any buffered events. Called at end of execution."""
        if self._flush_timer is not None:
            self._flush_timer.cancel()
        self._flush_buffer()
        logger.info(
            "Execution listener flushed: execution_id=%s total_events=%d",
            self._execution_id,
            self._seq,
            extra={
                "event": "execution_listener_flushed",
                "execution_id": str(self._execution_id),
                "total_events": self._seq,
            },
        )

    def _otel_start_span(self, name: str, attributes: dict[str, Any] | None = None) -> Any:
        """Start an OTEL span if tracing is enabled. Returns the span or None."""
        if self._otel_tracer is None:
            return None
        parent_ctx = None
        if self._otel_root_span is not None:
            parent_ctx = trace.set_span_in_context(self._otel_root_span)
        span = self._otel_tracer.start_span(name, context=parent_ctx, attributes=attributes or {})
        return span

    def _otel_end_span(self, key: str, attributes: dict[str, Any] | None = None) -> None:
        """End a previously started span identified by key."""
        span = self._otel_active_spans.pop(key, None)
        if span is not None:
            if attributes:
                for k, v in attributes.items():
                    span.set_attribute(k, v)
            span.end()

    def _dispatch_webhook(self, event_type: str, data: dict[str, Any]) -> None:
        """Fire webhook delivery in a background thread (fire-and-forget)."""
        try:
            executor = _get_webhook_executor()
            executor.submit(
                _deliver_webhooks_sync,
                event_type,
                data,
                str(self._execution_id),
                self._db_url,
            )
        except Exception:
            logger.warning(
                "Webhook dispatch skipped (executor unavailable): event=%s",
                event_type,
                exc_info=True,
                extra={
                    "event": "webhook_dispatch_skipped",
                    "event_type": event_type,
                    "execution_id": str(self._execution_id),
                },
            )

    def _write_event(self, event_type: str, data: dict[str, Any]) -> None:
        self._ensure_request_id()
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
                    "execution_id": str(self._execution_id),
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
        if self._buffer:
            self._flush_buffer()
        try:
            now = datetime.now(UTC)
            with self._session_factory() as session:
                event = ExecutionEvent(
                    execution_id=self._execution_id,
                    sequence=self._next_seq(),
                    event_type=event_type,
                    timestamp=now,
                    data=data,
                )
                session.add(event)
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
            logger.exception(
                "Failed to write event+task for %s: type=%s order=%d — "
                "task status in DB may be stale (expected %s)",
                self._execution_id,
                event_type,
                task_order,
                task_status.value,
                extra={
                    "event": "event_task_write_failed",
                    "execution_id": str(self._execution_id),
                    "event_type": event_type,
                    "task_order": task_order,
                    "expected_task_status": task_status.value,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc)[:500],
                },
            )

    def setup_listeners(self, crewai_event_bus: Any) -> None:
        @crewai_event_bus.on(CrewKickoffStartedEvent)
        def on_crew_started(source: Any, event: CrewKickoffStartedEvent) -> None:
            crew_name = event.crew_name or "unknown"
            data = {
                "crew_name": crew_name,
                "inputs": event.inputs or {},
            }
            self._write_event("crew_started", data)
            # OTEL: start root span for crew execution
            span = self._otel_start_span(
                f"crew.kickoff/{crew_name}",
                attributes={
                    "blackbeard.execution_id": str(self._execution_id),
                    "blackbeard.crew_name": crew_name,
                },
            )
            if span is not None:
                self._otel_root_span = span

        @crewai_event_bus.on(CrewKickoffCompletedEvent)
        def on_crew_completed(source: Any, event: CrewKickoffCompletedEvent) -> None:
            data = {"total_tokens": event.total_tokens}
            self._write_event("crew_completed", data)
            # OTEL: end root span
            if self._otel_root_span is not None:
                self._otel_root_span.set_attribute(
                    "blackbeard.total_tokens", event.total_tokens or 0
                )
                self._otel_root_span.end()
                self._otel_root_span = None

        @crewai_event_bus.on(TaskStartedEvent)
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
                self._otel_active_spans[f"task/{task_name}"] = span

        @crewai_event_bus.on(TaskCompletedEvent)
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

        @crewai_event_bus.on(ToolUsageStartedEvent)
        def on_tool_started(source: Any, event: ToolUsageStartedEvent) -> None:
            data = {
                "tool_name": event.tool_name,
                "tool_args": str(event.tool_args)[:200] if event.tool_args else None,
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
                self._otel_active_spans[f"tool/{event.tool_name}"] = span

        @crewai_event_bus.on(ToolUsageFinishedEvent)
        def on_tool_finished(source: Any, event: ToolUsageFinishedEvent) -> None:
            duration_ms = int((event.finished_at - event.started_at).total_seconds() * 1000)
            data = {
                "tool_name": event.tool_name,
                "duration_ms": duration_ms,
                "from_cache": event.from_cache,
            }
            self._write_event("tool_finished", data)
            # OTEL: end tool span
            self._otel_end_span(
                f"tool/{event.tool_name}",
                attributes={
                    "blackbeard.duration_ms": duration_ms,
                    "blackbeard.from_cache": event.from_cache or False,
                },
            )

        @crewai_event_bus.on(LLMCallStartedEvent)
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
                self._otel_active_spans[f"llm/{event.model or 'unknown'}"] = span

        @crewai_event_bus.on(LLMCallCompletedEvent)
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
