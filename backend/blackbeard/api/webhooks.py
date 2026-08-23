"""REST API endpoints for webhook management."""

from __future__ import annotations

import asyncio
import json
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

from blackbeard.api import MUTATION_RATE_MSG as _MUTATION_RATE_MSG
from blackbeard.api import smart_total
from blackbeard.audit import audit_from_request, log_audit
from blackbeard.auth import require_permission
from blackbeard.config import settings
from blackbeard.engine.execution_listener import (
    invalidate_webhook_cache,
    signed_webhook_headers,
)
from blackbeard.http_client import get_sync_client
from blackbeard.logging_config import safe_log_url
from blackbeard.models import KNOWN_EXECUTION_EVENT_TYPES, User, Webhook, get_session
from blackbeard.rate_limiter import check_rate_limit, mutation_limiter
from blackbeard.resources import check_url_ssrf

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

_KNOWN_EVENTS_HELP = ", ".join(sorted(KNOWN_EXECUTION_EVENT_TYPES))


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
            f"Must be known types: {_KNOWN_EVENTS_HELP}. "
            "Empty list means all events."
        ),
    )

    @field_validator("events")
    @classmethod
    def _validate_event_strings(cls, v: list[str]) -> list[str]:
        cleaned = []
        for event in v:
            event = event.strip()
            if not event or len(event) > 100:
                raise ValueError("Each event type must be 1-100 non-whitespace characters")
            if event not in KNOWN_EXECUTION_EVENT_TYPES:
                raise ValueError(f"Unknown event type '{event}'. Known types: {_KNOWN_EVENTS_HELP}")
            cleaned.append(event)
        # Deduplicate while preserving order (filter list is a set at delivery time).
        seen: set[str] = set()
        unique: list[str] = []
        for event in cleaned:
            if event not in seen:
                seen.add(event)
                unique.append(event)
        return unique

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


class WebhookTestResponse(BaseModel):
    """Outcome of a test delivery to a webhook endpoint."""

    delivered: bool
    status_code: int | None = None
    detail: str


@router.post(
    "",
    response_model=WebhookCreateResponse,
    status_code=201,
    responses={
        201: {"description": "Webhook registered"},
        422: {"description": "Invalid request body"},
        429: {"description": "Too many mutation requests"},
    },
)
async def create_webhook(
    request: Request,
    response: Response,
    body: WebhookCreateRequest = Body(...),
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_permission("create", "Webhook")),
) -> WebhookCreateResponse:
    """Register a new webhook for execution event delivery."""
    check_rate_limit(mutation_limiter, user, _MUTATION_RATE_MSG)
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

    # Off the event loop: uncached DNS resolution can block up to 2s.
    ssrf_error = await asyncio.to_thread(check_url_ssrf, body.url)
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
    _user: User | None = Depends(require_permission("list", "Webhook")),
) -> WebhookListResponse:
    """List all registered webhooks (secrets are not returned)."""
    result = await session.execute(
        select(Webhook)
        .options(defer(Webhook.secret))
        .order_by(Webhook.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    webhooks = result.scalars().all()
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
    total = await smart_total(
        session, items, limit, offset, select(func.count()).select_from(Webhook)
    )
    return WebhookListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + limit) < total,
    )


@router.get(
    "/{webhook_id}",
    response_model=WebhookResponse,
    responses={404: {"description": "Webhook not found"}},
)
async def get_webhook(
    webhook_id: UUID = Path(..., description="Webhook UUID"),
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_permission("get", "Webhook")),
) -> WebhookResponse:
    """Get a registered webhook by ID (secret is not returned)."""
    result = await session.execute(
        select(Webhook).where(Webhook.id == webhook_id).options(defer(Webhook.secret))
    )
    webhook = result.scalar_one_or_none()
    if webhook is None:
        raise HTTPException(status_code=404, detail=f"Webhook '{webhook_id}' not found")
    return WebhookResponse(
        id=str(webhook.id),
        url=webhook.url,
        events=webhook.events,
        active=webhook.active,
        created_at=webhook.created_at,
    )


_TEST_EVENT_TYPE = "crew_started"


def _deliver_test_webhook_sync(url: str, secret: str, payload: str) -> tuple[bool, int | None]:
    """POST a signed test payload to a webhook URL. Returns (delivered, status_code)."""
    try:
        client = get_sync_client("webhook-deliver", timeout=10, follow_redirects=False)
        resp = client.post(
            url,
            content=payload,
            headers=signed_webhook_headers(payload, secret, _TEST_EVENT_TYPE),
        )
    except Exception as exc:
        logger.info(
            "Webhook test delivery failed: %s (%s)",
            safe_log_url(url),
            type(exc).__name__,
            extra={"event": "webhook_test_delivery_error", "webhook_url": safe_log_url(url)},
        )
        return False, None
    return resp.status_code < 400, resp.status_code


@router.post(
    "/{webhook_id}/test",
    response_model=WebhookTestResponse,
    responses={
        404: {"description": "Webhook not found"},
        422: {"description": "Webhook URL is not reachable (SSRF blocked)"},
        429: {"description": "Too many mutation requests"},
    },
)
async def test_webhook(
    request: Request,
    webhook_id: UUID = Path(..., description="Webhook UUID"),
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_permission("get", "Webhook")),
) -> WebhookTestResponse:
    """Send a signed test event to the webhook endpoint.

    Delivers a payload shaped like real execution events (same HMAC-SHA256
    signature headers) so receivers can verify their integration end to end.
    """
    check_rate_limit(mutation_limiter, user, _MUTATION_RATE_MSG)
    result = await session.execute(select(Webhook).where(Webhook.id == webhook_id))
    webhook = result.scalar_one_or_none()
    if webhook is None:
        raise HTTPException(status_code=404, detail=f"Webhook '{webhook_id}' not found")

    ssrf_error = await asyncio.to_thread(check_url_ssrf, webhook.url)
    if ssrf_error:
        raise HTTPException(status_code=422, detail=ssrf_error)

    payload = json.dumps(
        {
            "event_type": _TEST_EVENT_TYPE,
            "execution_id": "",
            "data": {"test": True},
        },
        default=str,
    )
    delivered, status_code = await asyncio.to_thread(
        _deliver_test_webhook_sync, webhook.url, webhook.secret, payload
    )

    await log_audit(
        session,
        action="webhook_tested",
        resource_type="Webhook",
        resource_id=str(webhook.id),
        detail={"url": safe_log_url(webhook.url), "delivered": delivered},
        **audit_from_request(request, user),
    )
    await session.commit()

    if delivered:
        detail = f"Test event delivered (HTTP {status_code})"
    elif status_code is not None:
        detail = f"Endpoint responded with HTTP {status_code}"
    else:
        detail = "Delivery failed: endpoint unreachable"
    return WebhookTestResponse(delivered=delivered, status_code=status_code, detail=detail)


@router.delete(
    "/{webhook_id}",
    status_code=204,
    responses={
        204: {"description": "Webhook deleted (or did not exist — idempotent)"},
        429: {"description": "Too many mutation requests"},
    },
)
async def delete_webhook(
    request: Request,
    webhook_id: UUID = Path(..., description="Webhook UUID"),
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_permission("delete", "Webhook")),
) -> None:
    """Remove a registered webhook."""
    check_rate_limit(mutation_limiter, user, _MUTATION_RATE_MSG)
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
