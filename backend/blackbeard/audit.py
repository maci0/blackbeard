"""Audit logging service for security-relevant actions.

Provides helpers to record who did what, when, and from where.
Audit entries are append-only and stored in the audit_logs table.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

__all__ = [
    "audit_from_request",
    "get_client_ip",
    "log_audit",
]

if TYPE_CHECKING:
    from fastapi import Request
    from sqlalchemy.ext.asyncio import AsyncSession

    from blackbeard.models.user import User

from blackbeard.logging_config import anonymize_ip, request_id_var
from blackbeard.models import AuditLog

logger = logging.getLogger(__name__)


async def log_audit(
    session: AsyncSession,
    *,
    action: str,
    actor_type: str = "system",
    actor_id: str = "system",
    actor_email: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    detail: dict[str, Any] | None = None,
    request_id: str | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    """Write an audit log entry.

    The entry is added to the session but NOT committed -- the caller
    is responsible for committing the transaction so audit writes are
    atomic with the action they record.
    """
    entry = AuditLog(
        action=action,
        actor_type=actor_type,
        actor_id=actor_id,
        actor_email=actor_email,
        resource_type=resource_type,
        resource_id=resource_id,
        detail=detail,
        request_id=request_id or request_id_var.get("-"),
        ip_address=ip_address,
    )
    session.add(entry)

    logger.info(
        "Audit: %s by %s:%s on %s/%s",
        action,
        actor_type,
        actor_id,
        resource_type or "-",
        resource_id or "-",
        extra={
            "event": "audit_log",
            "audit_action": action,
            "actor_type": actor_type,
            "actor_id": actor_id,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "client_ip": anonymize_ip(ip_address),
            "request_id": entry.request_id,
        },
    )
    return entry


def get_client_ip(request: Request) -> str | None:
    """Extract client IP from a request, returning None when unavailable."""
    return request.client.host if request.client else None


def audit_from_request(request: Request, user: User | None) -> dict[str, Any]:
    """Extract audit context from a FastAPI request.

    Returns a dict of keyword arguments suitable for passing to
    ``log_audit()``.
    """
    return {
        "actor_type": "user" if user else "api_key",
        "actor_id": str(user.id) if user else "api_key",
        "actor_email": user.email if user else None,
        "ip_address": get_client_ip(request),
    }
