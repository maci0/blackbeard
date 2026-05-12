"""Logging configuration with request-scoped context propagation.

Provides structured log output with request_id for correlating logs
to individual API requests during incident investigation.
"""

import contextvars
import logging
import sys

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


class _RequestIdFilter(logging.Filter):
    """Injects request_id from contextvars into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get("-")  # type: ignore[attr-defined]
        return True


def configure_logging(debug: bool = False) -> None:
    """Configure the blackbeard logger hierarchy with request_id context.

    Call once at startup, before any log statements execute.
    """
    level = logging.DEBUG if debug else logging.INFO

    handler = logging.StreamHandler(sys.stderr)
    handler.addFilter(_RequestIdFilter())
    handler.setFormatter(logging.Formatter(
        fmt="%(asctime)s %(levelname)-8s [%(request_id)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    ))

    app_logger = logging.getLogger("blackbeard")
    app_logger.setLevel(level)
    app_logger.addHandler(handler)
    app_logger.propagate = False
