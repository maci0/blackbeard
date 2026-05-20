"""Logging configuration with request-scoped context propagation.

Provides structured log output with request_id for correlating logs
to individual API requests during incident investigation.
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
from datetime import UTC, datetime

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
user_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("user_id", default="")


class _RequestIdFilter(logging.Filter):
    """Injects request_id from contextvars into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get("-")
        record.user_id = user_id_var.get("")
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
    }
)

# Keys that must never appear in structured log output — defense-in-depth
# against accidental secret leakage through extra={} fields.
_SENSITIVE_KEYS = frozenset(
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
        "jwt_secret",
        "passphrase",
        "email",
        "user_email",
        "actor_email",
        "phone",
        "phone_number",
        "ssn",
        "social_security_number",
        "credit_card",
        "card_number",
        "date_of_birth",
        "bank_account",
    }
)

_SENSITIVE_SUFFIXES = tuple(f"_{s}" for s in _SENSITIVE_KEYS)

_SCALAR_TYPES = (str, int, float, bool, type(None))


class _JsonFormatter(logging.Formatter):
    """Structured JSON log formatter for production log aggregation."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": "blackbeard",
            "request_id": getattr(record, "request_id", "-"),
            "user_id": getattr(record, "user_id", "") or None,
            "thread": record.threadName,
            "pid": record.process,
        }
        if record.levelno >= logging.WARNING:
            log_entry["source"] = f"{record.pathname}:{record.lineno}:{record.funcName}"
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = self.formatException(record.exc_info)
            log_entry["error.type"] = type(record.exc_info[1]).__name__
            log_entry["error.message"] = str(record.exc_info[1])[:500]
        for key, val in record.__dict__.items():
            if key not in _LOG_RECORD_BUILTIN and key not in log_entry:
                key_lower = key.lower()
                if key_lower in _SENSITIVE_KEYS or key_lower.endswith(_SENSITIVE_SUFFIXES):
                    log_entry[key] = "[REDACTED]"
                else:
                    log_entry[key] = val
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
            logging.Formatter(
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
