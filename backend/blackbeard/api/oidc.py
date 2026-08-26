"""OIDC / SSO authentication endpoints.

Generic OIDC client: works with any provider (Google, Azure AD, Okta,
Keycloak, Authentik). Required env vars: OIDC_ISSUER, OIDC_CLIENT_ID,
OIDC_CLIENT_SECRET.  Optional: OIDC_REDIRECT_URI, OIDC_SCOPES.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse as _urlparse

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request
from starlette.responses import RedirectResponse

from blackbeard.audit import get_client_ip, log_audit
from blackbeard.auth import create_access_token, create_refresh_token, hash_password
from blackbeard.config import settings
from blackbeard.logging_config import anonymize_ip, request_id_var
from blackbeard.models import User, get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/oidc", tags=["auth"])


def _make_oidc_placeholder_hash() -> str:
    """Generate a unique bcrypt hash of a random value.

    Each OIDC-provisioned user gets their own random hash so that
    cracking one cannot compromise every OIDC account.
    """
    return hash_password(secrets.token_urlsafe(64))


_oauth: OAuth | None = None
_oauth_lock = asyncio.Lock()


async def _ensure_oauth() -> OAuth:
    """Return the shared OAuth client, creating it on first call (async-safe)."""
    global _oauth
    if _oauth is not None:
        return _oauth

    async with _oauth_lock:
        if _oauth is not None:
            return _oauth

        if not settings.oidc_issuer:
            raise HTTPException(
                status_code=501, detail="OIDC not configured. Set OIDC_ISSUER env var."
            )

        oauth = OAuth()
        client_secret = (
            settings.oidc_client_secret.get_secret_value() if settings.oidc_client_secret else None
        )
        oauth.register(
            name="provider",
            server_metadata_url=f"{settings.oidc_issuer.rstrip('/')}/.well-known/openid-configuration",
            client_id=settings.oidc_client_id,
            client_secret=client_secret,
            client_kwargs={"scope": settings.oidc_scopes},
        )
        _oauth = oauth
        return oauth


@router.get(
    "/login",
    responses={
        302: {"description": "Redirect to OIDC provider"},
        501: {"description": "OIDC not configured"},
    },
)
async def oidc_login(request: Request) -> RedirectResponse:
    """Redirect to OIDC provider's authorization endpoint."""
    oauth = await _ensure_oauth()
    redirect_uri = settings.oidc_redirect_uri or str(request.url_for("oidc_callback"))
    return await oauth.provider.authorize_redirect(request, redirect_uri)  # type: ignore[no-any-return]


@router.get(
    "/callback",
    name="oidc_callback",
    responses={
        303: {"description": "Redirect to frontend with tokens"},
        400: {"description": "OIDC provider returned invalid email"},
        401: {"description": "OIDC token exchange failed"},
        403: {"description": "Email not verified or account deactivated"},
        501: {"description": "OIDC not configured"},
    },
)
async def oidc_callback(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    """Handle OIDC callback: exchange code, create/link user, redirect with tokens."""
    oauth = await _ensure_oauth()

    try:
        token: dict[str, Any] = await oauth.provider.authorize_access_token(request)
    except Exception as exc:
        logger.warning(
            "OIDC token exchange failed: %s",
            type(exc).__name__,
            exc_info=True,
            extra={
                "event": "oidc_token_exchange_failed",
                "error_type": type(exc).__name__,
                "request_id": request_id_var.get("-"),
            },
        )
        raise HTTPException(status_code=401, detail="OIDC authentication failed") from None

    userinfo = token.get("userinfo")
    if not userinfo:
        try:
            userinfo = await oauth.provider.userinfo(token=token)
        except Exception as exc:
            logger.warning(
                "OIDC userinfo fetch failed, proceeding with empty profile: %s",
                type(exc).__name__,
                exc_info=True,
                extra={
                    "event": "oidc_userinfo_failed",
                    "error_type": type(exc).__name__,
                    "request_id": request_id_var.get("-"),
                },
            )
            userinfo = {}

    email = (userinfo.get("email") or "").lower().strip()
    if not email:
        logger.warning(
            "OIDC login rejected: provider returned no email",
            extra={
                "event": "oidc_missing_email",
                "request_id": request_id_var.get("-"),
            },
        )
        raise HTTPException(status_code=400, detail="OIDC provider did not return an email address")
    if "@" not in email or len(email) > 320:
        logger.warning(
            "OIDC login rejected: invalid email format",
            extra={
                "event": "oidc_invalid_email",
                "request_id": request_id_var.get("-"),
            },
        )
        raise HTTPException(
            status_code=400, detail="OIDC provider returned an invalid email address"
        )

    if not userinfo.get("email_verified", False):
        logger.warning(
            "OIDC login rejected: email not verified",
            extra={
                "event": "oidc_email_not_verified",
                "request_id": request_id_var.get("-"),
            },
        )
        raise HTTPException(status_code=403, detail="OIDC provider reports email is not verified")

    ip = get_client_ip(request)
    user, created = await _find_or_create_user(session, email, userinfo)

    if created:
        await log_audit(
            session,
            action="user_registered",
            actor_type="system",
            actor_id=str(user.id),
            actor_email=user.email,
            resource_type="User",
            resource_id=str(user.id),
            detail={"method": "oidc"},
            ip_address=ip,
        )
    await log_audit(
        session,
        action="oidc_login",
        actor_type="user",
        actor_id=str(user.id),
        actor_email=user.email,
        resource_type="User",
        resource_id=str(user.id),
        ip_address=ip,
    )
    await session.commit()

    request.session.clear()

    access_token = create_access_token(str(user.id))
    refresh_token = create_refresh_token(str(user.id))

    logger.info(
        "OIDC login: user_id=%s from %s",
        user.id,
        anonymize_ip(ip),
        extra={
            "event": "oidc_login",
            "user_id": str(user.id),
            "client_ip": anonymize_ip(ip),
        },
    )

    # Build a same-origin fragment redirect.  The frontend reads the
    # tokens from window.location.hash which is never sent to the server,
    # mitigating token leakage via Referer / server logs.
    # Use 303 (See Other) instead of 302 to prevent browsers from replaying
    # the POST body on redirect and to signal that the callback should not
    # be cached or bookmarked.
    frontend_base = settings.oidc_redirect_uri or str(request.url_for("oidc_callback"))
    parsed = _urlparse(frontend_base)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    # Validate redirect origin against configured CORS origins to prevent
    # token theft via open-redirect if OIDC_REDIRECT_URI is misconfigured.
    if origin not in settings.cors_origins:
        logger.error(
            "OIDC redirect origin %s not in CORS_ORIGINS: refusing redirect",
            origin,
            extra={
                "event": "oidc_redirect_origin_rejected",
                "origin": origin,
                "request_id": request_id_var.get("-"),
            },
        )
        raise HTTPException(status_code=500, detail="OIDC redirect origin is not an allowed origin")

    frontend_url = f"{origin}/#token={access_token}&refresh={refresh_token}"
    return RedirectResponse(url=frontend_url, status_code=303)


async def _find_or_create_user(
    session: AsyncSession,
    email: str,
    userinfo: dict[str, Any],
) -> tuple[User, bool]:
    """Find existing user by email or create from OIDC claims.

    Returns ``(user, created)`` where *created* is True for newly
    provisioned accounts.
    """
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user:
        if not user.is_active:
            logger.warning(
                "OIDC login blocked (deactivated): user_id=%s",
                user.id,
                extra={
                    "event": "oidc_login_blocked_deactivated",
                    "user_id": str(user.id),
                    "request_id": request_id_var.get("-"),
                },
            )
            raise HTTPException(status_code=403, detail="Account is deactivated")
        user.last_login_at = datetime.now(UTC)
        return user, False

    display_name = (
        userinfo.get("name") or userinfo.get("preferred_username") or email.split("@")[0]
    )[:255]
    placeholder_hash = await asyncio.to_thread(_make_oidc_placeholder_hash)
    user = User(
        email=email,
        display_name=display_name,
        password_hash=placeholder_hash,
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)

    logger.info(
        "OIDC user created: user_id=%s",
        user.id,
        extra={"event": "oidc_user_created", "user_id": str(user.id)},
    )
    return user, True
