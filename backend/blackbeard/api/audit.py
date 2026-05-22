"""REST API endpoint for querying the audit log."""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from blackbeard.auth.dependencies import require_user
from blackbeard.models import AuditLog, User, get_session

logger = logging.getLogger(__name__)

router = APIRouter(tags=["audit"])


class AuditLogItem(BaseModel):
    """Single audit log entry returned by the API.

    actor_email and ip_address are stored in the DB for forensics
    but excluded from API responses to limit PII exposure.
    """

    id: str
    timestamp: datetime
    actor_type: str
    actor_id: str
    action: str
    resource_type: str | None = None
    resource_id: str | None = None
    detail: dict | None = None
    request_id: str | None = None


class AuditLogListResponse(BaseModel):
    """Paginated list of audit log entries."""

    items: list[AuditLogItem]
    total: int
    limit: int = 100
    offset: int = 0
    has_more: bool = False


@router.get(
    "/audit-logs",
    response_model=AuditLogListResponse,
    responses={
        401: {"description": "Authentication required"},
    },
)
async def list_audit_logs(
    action: str | None = Query(
        default=None,
        max_length=50,
        description="Filter by action (e.g. 'user_login', 'resource_created')",
    ),
    actor_id: str | None = Query(
        default=None,
        max_length=255,
        description="Filter by actor ID (user UUID or 'api_key')",
    ),
    resource_type: str | None = Query(
        default=None,
        max_length=50,
        description="Filter by resource type (e.g. 'Agent', 'Crew')",
    ),
    resource_id: str | None = Query(
        default=None,
        max_length=255,
        description="Filter by resource ID (resource name or UUID)",
    ),
    limit: int = Query(default=100, ge=1, le=1000, description="Max results"),
    offset: int = Query(default=0, ge=0, le=100_000, description="Results to skip"),
    _current_user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> AuditLogListResponse:
    """List audit log entries with optional filters. Requires authentication."""
    filters = []
    if action is not None:
        filters.append(AuditLog.action == action)
    if actor_id is not None:
        filters.append(AuditLog.actor_id == actor_id)
    if resource_type is not None:
        filters.append(AuditLog.resource_type == resource_type)
    if resource_id is not None:
        filters.append(AuditLog.resource_id == resource_id)

    data_query = (
        select(AuditLog)
        .where(*filters)
        .order_by(AuditLog.timestamp.desc())
        .options(defer(AuditLog.actor_email), defer(AuditLog.ip_address))
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(data_query)
    logs = list(result.scalars().all())

    if len(logs) < limit and (len(logs) > 0 or offset == 0):
        total = offset + len(logs)
    else:
        count_query = select(func.count(AuditLog.id)).where(*filters)
        total = (await session.execute(count_query)).scalar_one()

    return AuditLogListResponse(
        items=[
            AuditLogItem(
                id=str(entry.id),
                timestamp=entry.timestamp,
                actor_type=entry.actor_type,
                actor_id=entry.actor_id,
                action=entry.action,
                resource_type=entry.resource_type,
                resource_id=entry.resource_id,
                detail=entry.detail,
                request_id=entry.request_id,
            )
            for entry in logs
        ],
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + limit) < total,
    )
