"""Logging configuration with request-scoped context propagation.

Provides structured log output with request_id for correlating logs
to individual API requests during incident investigation.
"""

import contextvars
import json
import logging
import sys
from datetime import UTC, datetime

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


class _RequestIdFilter(logging.Filter):
    """Injects request_id from contextvars into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get("-")
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
    }
)


class _JsonFormatter(logging.Formatter):
    """Structured JSON log formatter for production log aggregation."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "thread": record.threadName,
        }
        if record.levelno >= logging.WARNING:
            log_entry["source"] = f"{record.pathname}:{record.lineno}:{record.funcName}"
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = self.formatException(record.exc_info)
        for key, val in record.__dict__.items():
            if key not in _LOG_RECORD_BUILTIN and key not in log_entry:
                log_entry[key] = val
        return json.dumps(log_entry, default=str)


def configure_logging(debug: bool = False) -> None:
    """Configure the blackbeard logger hierarchy with request_id context.

    Call once at startup, before any log statements execute.
    Uses human-readable format in debug mode, structured JSON in production.
    """
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
