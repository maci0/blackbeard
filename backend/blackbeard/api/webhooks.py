"""REST API endpoints for webhook management."""

from __future__ import annotations

import logging
import secrets
from datetime import datetime
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from blackbeard.audit import audit_from_request, log_audit
from blackbeard.auth.dependencies import get_current_user
from blackbeard.config import settings
from blackbeard.engine.execution_listener import invalidate_webhook_cache
from blackbeard.logging_config import safe_log_url
from blackbeard.models import User, Webhook, get_session
from blackbeard.resources import check_url_ssrf

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


class WebhookCreateRequest(BaseModel):
    """Request to register a new webhook."""

    url: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        pattern=r"^https?://",
        description="Webhook URL to POST events to",
    )
    events: list[str] = Field(
        default_factory=list,
        max_length=50,
        description=(
            "Event types to deliver (e.g. 'crew_started', 'task_completed'). "
            "Empty list means all events."
        ),
    )

    @field_validator("events")
    @classmethod
    def _validate_event_strings(cls, v: list[str]) -> list[str]:
        for event in v:
            if not event or len(event) > 100:
                raise ValueError("Each event type must be 1-100 characters")
        return v

    secret: str | None = Field(
        default=None,
        min_length=16,
        max_length=500,
        description="HMAC-SHA256 signing secret. Auto-generated if omitted.",
    )


class WebhookResponse(BaseModel):
    """Response for a webhook."""

    id: str
    url: str
    events: list[str]
    active: bool
    created_at: datetime | None = None


class WebhookListResponse(BaseModel):
    """Paginated webhook list."""

    items: list[WebhookResponse]
    total: int
    limit: int = 100
    offset: int = 0
    has_more: bool = False


class WebhookCreateResponse(WebhookResponse):
    """Response after creating a webhook (includes secret once)."""

    secret: str = Field(description="HMAC-SHA256 signing secret — shown only on create")


@router.post(
    "",
    response_model=WebhookCreateResponse,
    status_code=201,
    responses={
        201: {"description": "Webhook registered"},
        422: {"description": "Invalid request body"},
    },
)
async def create_webhook(
    request: Request,
    response: Response,
    body: WebhookCreateRequest = Body(...),
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(get_current_user),
) -> WebhookCreateResponse:
    """Register a new webhook for execution event delivery."""
    parsed = urlparse(body.url)

    if not settings.debug and parsed.scheme != "https":
        raise HTTPException(
            status_code=422,
            detail="Webhook URL must use HTTPS in production.",
        )

    if parsed.username or parsed.password:
        raise HTTPException(
            status_code=422,
            detail="Webhook URL must not contain embedded credentials.",
        )

    ssrf_error = check_url_ssrf(body.url)
    if ssrf_error:
        raise HTTPException(status_code=422, detail=ssrf_error)

    signing_secret = body.secret or secrets.token_urlsafe(32)

    webhook = Webhook(
        url=body.url,
        events=body.events,
        secret=signing_secret,
        active=True,
    )
    session.add(webhook)
    await session.flush()

    safe_url = safe_log_url(webhook.url)
    logger.info(
        "Webhook created: id=%s url=%s events=%s",
        webhook.id,
        safe_url,
        webhook.events,
        extra={
            "event": "webhook_created",
            "webhook_id": str(webhook.id),
            "webhook_url": safe_url,
            "event_types": webhook.events,
        },
    )
    await log_audit(
        session,
        action="webhook_created",
        resource_type="Webhook",
        resource_id=str(webhook.id),
        detail={"url": safe_url, "events": webhook.events},
        **audit_from_request(request, user),
    )
    await session.commit()
    invalidate_webhook_cache()
    response.headers["Location"] = f"/api/v1/webhooks/{webhook.id}"

    return WebhookCreateResponse(
        id=str(webhook.id),
        url=webhook.url,
        events=webhook.events,
        active=webhook.active,
        secret=signing_secret,
        created_at=webhook.created_at,
    )


@router.get(
    "",
    response_model=WebhookListResponse,
    responses={200: {"description": "Paginated list of registered webhooks"}},
)
async def list_webhooks(
    limit: int = Query(default=100, ge=1, le=1000, description="Max results"),
    offset: int = Query(default=0, ge=0, le=100_000, description="Results to skip"),
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(get_current_user),
) -> WebhookListResponse:
    """List all registered webhooks (secrets are not returned)."""
    result = await session.execute(
        select(Webhook)
        .options(defer(Webhook.secret))
        .order_by(Webhook.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    webhooks = list(result.scalars())
    items = [
        WebhookResponse(
            id=str(w.id),
            url=w.url,
            events=w.events,
            active=w.active,
            created_at=w.created_at,
        )
        for w in webhooks
    ]
    if len(items) < limit and (len(items) > 0 or offset == 0):
        total = offset + len(items)
    else:
        count_result = await session.execute(select(func.count()).select_from(Webhook))
        total = count_result.scalar_one()
    return WebhookListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + limit) < total,
    )


@router.delete(
    "/{webhook_id}",
    status_code=204,
    responses={
        204: {"description": "Webhook deleted (or did not exist — idempotent)"},
    },
)
async def delete_webhook(
    request: Request,
    webhook_id: UUID = Path(..., description="Webhook UUID"),
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(get_current_user),
) -> None:
    """Remove a registered webhook."""
    result = await session.execute(
        select(Webhook)
        .where(Webhook.id == webhook_id)
        .options(defer(Webhook.secret))
        .with_for_update()
    )
    webhook = result.scalar_one_or_none()
    if webhook is None:
        logger.debug(
            "Delete no-op: webhook %s not found",
            webhook_id,
            extra={
                "event": "webhook_delete_noop",
                "webhook_id": str(webhook_id),
            },
        )
        return

    safe_url = safe_log_url(webhook.url)
    await session.delete(webhook)
    await log_audit(
        session,
        action="webhook_deleted",
        resource_type="Webhook",
        resource_id=str(webhook_id),
        detail={"url": safe_url},
        **audit_from_request(request, user),
    )
    await session.commit()
    invalidate_webhook_cache()

    logger.info(
        "Webhook deleted: id=%s url=%s",
        webhook_id,
        safe_url,
        extra={
            "event": "webhook_deleted",
            "webhook_id": str(webhook_id),
            "webhook_url": safe_url,
        },
    )
