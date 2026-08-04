"""Logging configuration with request-scoped context propagation.

Provides structured log output with request_id for correlating logs
to individual API requests during incident investigation.
"""

from __future__ import annotations

import contextvars
import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from urllib.parse import urlparse, urlunparse

if TYPE_CHECKING:
    import asyncio

__all__ = [
    "SENSITIVE_KEYS",
    "anonymize_ip",
    "configure_logging",
    "execution_id_var",
    "log_task_exception",
    "request_id_var",
    "safe_log_url",
    "scrub_pii",
    "user_id_var",
]

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
user_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("user_id", default="")
execution_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("execution_id", default="")


def _current_trace_ids() -> tuple[str | None, str | None]:
    """Return (trace_id, span_id) from the active OpenTelemetry span, if any.

    Avoids importing OTEL at module load so optional tracing stays zero-cost
    when the SDK is not installed.
    """
    try:
        from opentelemetry import trace
    except ImportError:
        return None, None
    span = trace.get_current_span()
    ctx = span.get_span_context() if span is not None else None
    if ctx is None or not getattr(ctx, "is_valid", False):
        return None, None
    return format(ctx.trace_id, "032x"), format(ctx.span_id, "016x")


class _RequestIdFilter(logging.Filter):
    """Injects request_id, user_id, execution_id, and optional OTEL IDs into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get("-")
        record.user_id = user_id_var.get("")
        record.execution_id = execution_id_var.get("")
        trace_id, span_id = _current_trace_ids()
        record.trace_id = trace_id or ""
        record.span_id = span_id or ""
        return True


_LOG_RECORD_BUILTIN = frozenset(
    {
        "name",
        "msg",
        "args",
        "created",
        "relativeCreated",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "module",
        "filename",
        "pathname",
        "process",
        "processName",
        "thread",
        "threadName",
        "levelname",
        "levelno",
        "message",
        "msecs",
        "taskName",
        "request_id",
        "user_id",
        "execution_id",
        "trace_id",
        "span_id",
    }
)

# Keys that must never appear in structured log output — defense-in-depth
# against accidental secret leakage through extra={} fields.
# Also used by middleware to redact query-string parameters.
SENSITIVE_KEYS = frozenset(
    {
        "api_key",
        "api_secret",
        "password",
        "password_hash",
        "secret",
        "token",
        "credential",
        "authorization",
        "private_key",
        "secret_key",
        "access_key",
        "access_token",
        "refresh_token",
        "master_key",
        "database_url",
        "dsn",
        "connection_string",
        "valkey_url",
        "redis_url",
        "jwt_secret",
        "passphrase",
        "email",
        "user_email",
        "actor_email",
        "display_name",
        "user_name",
        "username",
        "phone",
        "phone_number",
        "ssn",
        "social_security_number",
        "credit_card",
        "card_number",
        "date_of_birth",
        "birthdate",
        "birthday",
        "birth_date",
        "bank_account",
        "litellm_key",
        "virtual_key",
        "signing_secret",
        "webhook_secret",
        "ip_address",
        "principal_chain",
        "initiated_by",
        "original_email",
        "address",
        "home_address",
        "mailing_address",
        "zip_code",
        "postal_code",
        "dob",
        "location",
        "first_name",
        "last_name",
        "full_name",
        "nationality",
        "ethnicity",
        "gender",
        "passport",
        "driver_license",
        "national_id",
        "tax_id",
    }
)

_SENSITIVE_SUFFIXES = tuple(f"_{s}" for s in SENSITIVE_KEYS)

_SCALAR_TYPES = (str, int, float, bool, type(None))

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(
    r"(?<!\d)"
    r"(?:\+?\d{1,3}[\s.\-]?)?"
    r"(?:\(?\d{2,4}\)?[\s.\-]?)"
    r"\d{3,4}[\s.\-]?\d{3,4}"
    r"(?!\d)"
)
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
# Grouped 4-digit card forms (e.g. 4111 1111 1111 1111 / 4111-1111-1111-1111).
_CREDIT_CARD_RE = re.compile(r"\b(?:\d{4}[ -]?){3}\d{1,4}\b")


def scrub_pii(text: str) -> str:
    """Replace PII patterns (email, phone, SSN, card numbers) in log text."""
    text = _EMAIL_RE.sub("[EMAIL]", text)
    text = _SSN_RE.sub("[SSN]", text)
    text = _CREDIT_CARD_RE.sub("[CARD]", text)
    return _PHONE_RE.sub("[PHONE]", text)


def _redact_log_value(key: str, val: object, *, depth: int = 0) -> object:
    """Redact sensitive keys and scrub PII patterns in structured log extras.

    Recurses into nested dict/list values so a secret buried under a non-
    sensitive parent key is still redacted.
    """
    if depth >= 8:
        return "[MAX_DEPTH]"
    key_lower = key.lower()
    if key_lower in SENSITIVE_KEYS or key_lower.endswith(_SENSITIVE_SUFFIXES):
        return "[REDACTED]"
    if isinstance(val, dict):
        return {k: _redact_log_value(str(k), v, depth=depth + 1) for k, v in val.items()}
    if isinstance(val, list):
        return [
            _redact_log_value(key, item, depth=depth + 1)
            if isinstance(item, (dict, list))
            else (scrub_pii(item) if isinstance(item, str) else item)
            for item in val
        ]
    if isinstance(val, str):
        return scrub_pii(val)
    return val


def anonymize_ip(ip: str | None) -> str:
    """Mask the host portion of an IP address for privacy-safe logging.

    IPv4: masks the last octet (``192.168.1.42`` → ``192.168.1.x``).
    IPv6: masks the last 80 bits (``2001:db8::1`` → ``2001:db8:x:x:x:x:x:x``).
    Applied everywhere client IPs are logged or persisted (including
    audit_logs); retention of those rows is governed by
    AUDIT_LOG_RETENTION_DAYS.
    """
    if not ip:
        return "unknown"
    if ":" in ip:
        parts = ip.split(":")
        keep = min(3, len(parts))
        return ":".join(parts[:keep]) + ":" + ":".join("x" for _ in parts[keep:])
    parts = ip.split(".")
    if len(parts) == 4:
        return f"{parts[0]}.{parts[1]}.{parts[2]}.x"
    return ip


def log_task_exception(task: asyncio.Task[None]) -> None:
    """Callback for fire-and-forget asyncio tasks that logs exceptions silently swallowed."""
    if task.cancelled():
        return
    _logger = logging.getLogger(__name__)
    try:
        exc = task.exception()
    except Exception:
        task_name = task.get_name()
        _logger.warning(
            "Could not retrieve exception from background task '%s'",
            task_name,
            exc_info=True,
            extra={
                "event": "background_task_exception_retrieval_failed",
                "task_name": task_name,
            },
        )
        return
    if exc is not None:
        _logger.error(
            "Background task '%s' failed: %s",
            task.get_name(),
            scrub_pii(str(exc)[:500]),
            exc_info=exc,
            extra={
                "event": "background_task_failed",
                "task_name": task.get_name(),
                "error_type": type(exc).__name__,
                "error_message": scrub_pii(str(exc)[:500]),
            },
        )


def safe_log_url(url: str) -> str:
    """Strip userinfo/query/fragment from URL to prevent credential leakage in logs.

    Webhook URLs may carry API keys or tokens in query parameters
    (e.g. ``?key=secret``) or as userinfo (e.g. ``https://user:token@host``).
    This preserves scheme/host/path for debugging while redacting the parts
    that could leak credentials.
    """
    parsed = urlparse(url)
    has_userinfo = parsed.username is not None
    has_sensitive = parsed.query or parsed.fragment or has_userinfo
    if not has_sensitive:
        return url
    netloc = parsed.hostname or ""
    if parsed.port:
        netloc += f":{parsed.port}"
    return urlunparse(
        parsed._replace(
            netloc=netloc,
            query="[REDACTED]" if parsed.query else "",
            fragment="",
        )
    )


class _PiiScrubFormatter(logging.Formatter):
    """Text formatter that scrubs PII patterns from the final output."""

    def format(self, record: logging.LogRecord) -> str:
        return scrub_pii(super().format(record))


class _JsonFormatter(logging.Formatter):
    """Structured JSON log formatter for production log aggregation."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": scrub_pii(record.getMessage()),
            "service": "blackbeard",
            "request_id": getattr(record, "request_id", "-"),
            "user_id": getattr(record, "user_id", "") or None,
            "execution_id": getattr(record, "execution_id", "") or None,
            "trace_id": getattr(record, "trace_id", "") or None,
            "span_id": getattr(record, "span_id", "") or None,
            "thread": record.threadName,
            "pid": record.process,
        }
        if record.levelno >= logging.WARNING:
            log_entry["source"] = f"{record.pathname}:{record.lineno}:{record.funcName}"
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = scrub_pii(self.formatException(record.exc_info))
            log_entry["error.type"] = type(record.exc_info[1]).__name__
            log_entry["error.message"] = scrub_pii(str(record.exc_info[1])[:500])
        for key, val in record.__dict__.items():
            if key not in _LOG_RECORD_BUILTIN and key not in log_entry:
                log_entry[key] = _redact_log_value(key, val)
        try:
            return json.dumps(log_entry, default=str)
        except (TypeError, ValueError, OverflowError):
            safe = {k: v for k, v in log_entry.items() if isinstance(v, _SCALAR_TYPES)}
            safe["_serialization_error"] = True
            return json.dumps(safe, default=str)


def configure_logging(debug: bool = False, log_level: str = "") -> None:
    """Configure the blackbeard logger hierarchy with request_id context.

    Call once at startup, before any log statements execute.
    Uses human-readable format in debug mode, structured JSON in production.

    log_level overrides the default (DEBUG in debug mode, INFO otherwise).
    Accepts standard level names: DEBUG, INFO, WARNING, ERROR, CRITICAL.
    """
    if log_level:
        level = getattr(logging, log_level.upper(), None)
        if not isinstance(level, int):
            logging.getLogger(__name__).warning(
                "Invalid LOG_LEVEL '%s', falling back to %s",
                log_level,
                "DEBUG" if debug else "INFO",
                extra={"event": "invalid_log_level", "configured_value": log_level},
            )
            level = logging.DEBUG if debug else logging.INFO
    else:
        level = logging.DEBUG if debug else logging.INFO

    handler = logging.StreamHandler(sys.stderr)
    handler.addFilter(_RequestIdFilter())

    if debug:
        handler.setFormatter(
            _PiiScrubFormatter(
                fmt="%(asctime)s %(levelname)-8s [%(request_id)s] %(name)s — %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )
    else:
        handler.setFormatter(_JsonFormatter())

    app_logger = logging.getLogger("blackbeard")
    app_logger.setLevel(level)
    app_logger.handlers.clear()
    app_logger.addHandler(handler)
    app_logger.propagate = False

    for noisy in ("httpx", "httpcore", "sqlalchemy.engine", "urllib3"):
        logging.getLogger(noisy).setLevel(max(level, logging.WARNING))

    # Route uvicorn logs through the same handler so production output is
    # uniformly structured JSON instead of a mix of plain-text and JSON lines.
    for uvi in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvi_logger = logging.getLogger(uvi)
        uvi_logger.handlers.clear()
        uvi_logger.addHandler(handler)
        uvi_logger.propagate = False

    app_logger.info(
        "Logging configured: level=%s format=%s",
        logging.getLevelName(level),
        "text" if debug else "json",
        extra={
            "event": "logging_configured",
            "log_level": logging.getLevelName(level),
            "log_format": "text" if debug else "json",
        },
    )
