"""Data retention: periodic purge of aged audit logs, executions, and users.

Audit logs carry actor identity and (anonymized) IP addresses; executions
carry user-supplied inputs and crew outputs; soft-deleted users retain a
row (with scrubbed email) until hard-deleted. All three grow unbounded
without a retention limit (GDPR Art. 5(1)(e) storage limitation). Retention
is opt-in: set AUDIT_LOG_RETENTION_DAYS, EXECUTION_RETENTION_DAYS, and/or
USER_RETENTION_DAYS to enable.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import delete

from blackbeard.config import settings
from blackbeard.models import AuditLog, Execution, User
from blackbeard.models.database import async_session
from blackbeard.models.execution import TERMINAL_STATUSES

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["purge_expired_data", "retention_enabled", "retention_loop"]

logger = logging.getLogger(__name__)

_PURGE_INTERVAL_S = 6 * 3600


def retention_enabled() -> bool:
    """Return True if any retention period is configured."""
    return (
        settings.audit_log_retention_days is not None
        or settings.execution_retention_days is not None
        or settings.user_retention_days is not None
    )


async def purge_expired_data(session: AsyncSession) -> dict[str, int]:
    """Delete rows older than the configured retention periods.

    Audit logs are deleted by timestamp. Executions are deleted by creation
    time, terminal statuses only (queued/running rows are never touched);
    child rows (tasks, tool calls, events) go with them via FK cascade.
    Deactivated users are hard-deleted by updated_at (set when deactivated);
    executions.initiated_by is SET NULL via FK.
    Returns per-table deletion counts. Caller-provided session; commits.
    """
    now = datetime.now(UTC)
    purged = {"audit_logs": 0, "executions": 0, "users": 0}
    if settings.audit_log_retention_days is not None:
        cutoff = now - timedelta(days=settings.audit_log_retention_days)
        result = await session.execute(delete(AuditLog).where(AuditLog.timestamp < cutoff))
        purged["audit_logs"] = cast("Any", result).rowcount or 0
    if settings.execution_retention_days is not None:
        cutoff = now - timedelta(days=settings.execution_retention_days)
        result = await session.execute(
            delete(Execution).where(
                Execution.created_at < cutoff,
                Execution.status.in_(TERMINAL_STATUSES),
            )
        )
        purged["executions"] = cast("Any", result).rowcount or 0
    if settings.user_retention_days is not None:
        cutoff = now - timedelta(days=settings.user_retention_days)
        result = await session.execute(
            delete(User).where(
                User.is_active.is_(False),
                User.updated_at < cutoff,
            )
        )
        purged["users"] = cast("Any", result).rowcount or 0
    await session.commit()
    if purged["audit_logs"] or purged["executions"] or purged["users"]:
        logger.info(
            "Retention purge: %d audit log(s), %d execution(s), %d user(s) deleted",
            purged["audit_logs"],
            purged["executions"],
            purged["users"],
            extra={
                "event": "retention_purge",
                "audit_logs_purged": purged["audit_logs"],
                "executions_purged": purged["executions"],
                "users_purged": purged["users"],
            },
        )
    return purged


async def retention_loop() -> None:
    """Run the retention purge every 6 hours until cancelled."""
    while True:
        try:
            async with async_session() as session:
                await purge_expired_data(session)
        except Exception:
            logger.exception(
                "Retention purge failed — retrying next cycle",
                extra={"event": "retention_purge_failed"},
            )
        await asyncio.sleep(_PURGE_INTERVAL_S)
