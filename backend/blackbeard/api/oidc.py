"""OIDC / SSO authentication endpoints.

Generic OIDC client — works with any provider (Google, Azure AD, Okta,
Keycloak, Authentik). Required env vars: OIDC_ISSUER, OIDC_CLIENT_ID,
OIDC_CLIENT_SECRET.  Optional: OIDC_REDIRECT_URI, OIDC_SCOPES.
"""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime
from typing import Any

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request
from starlette.responses import RedirectResponse

from blackbeard.audit import log_audit
from blackbeard.auth.jwt import create_access_token, create_refresh_token
from blackbeard.auth.passwords import hash_password
from blackbeard.config import settings
from blackbeard.logging_config import request_id_var
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


def _get_oauth() -> OAuth:
    global _oauth
    if _oauth is not None:
        return _oauth

    if not settings.oidc_issuer:
        raise HTTPException(501, "OIDC not configured. Set OIDC_ISSUER env var.")

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


@router.get("/login")
async def oidc_login(request: Request) -> RedirectResponse:
    """Redirect to OIDC provider's authorization endpoint."""
    oauth = _get_oauth()
    redirect_uri = settings.oidc_redirect_uri or str(request.url_for("oidc_callback"))
    return await oauth.provider.authorize_redirect(request, redirect_uri)


@router.get("/callback", name="oidc_callback")
async def oidc_callback(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    """Handle OIDC callback — exchange code, create/link user, redirect with tokens."""
    oauth = _get_oauth()

    try:
        token: dict[str, Any] = await oauth.provider.authorize_access_token(request)
    except Exception as exc:
        logger.warning(
            "OIDC token exchange failed: %s",
            exc,
            exc_info=True,
            extra={
                "event": "oidc_token_exchange_failed",
                "error_type": type(exc).__name__,
                "error_message": str(exc)[:500],
                "request_id": request_id_var.get("-"),
            },
        )
        raise HTTPException(401, "OIDC authentication failed") from None

    userinfo = token.get("userinfo")
    if not userinfo:
        try:
            userinfo = await oauth.provider.userinfo(token=token)
        except Exception as exc:
            logger.warning(
                "OIDC userinfo fetch failed — proceeding with empty profile: %s",
                exc,
                exc_info=True,
                extra={
                    "event": "oidc_userinfo_failed",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc)[:500],
                    "request_id": request_id_var.get("-"),
                },
            )
            userinfo = {}

    email = (userinfo.get("email") or "").lower().strip()
    if not email:
        raise HTTPException(400, "OIDC provider did not return an email address")

    if not userinfo.get("email_verified", False):
        logger.warning(
            "OIDC login rejected: email not verified: %s",
            email,
            extra={
                "event": "oidc_email_not_verified",
                "email": email,
                "request_id": request_id_var.get("-"),
            },
        )
        raise HTTPException(403, "OIDC provider reports email is not verified")

    user = await _find_or_create_user(session, email, userinfo)

    ip = request.client.host if request.client else None
    await log_audit(
        session,
        action="oidc_login",
        actor_type="user",
        actor_id=str(user.id),
        actor_email=user.email,
        resource_type="User",
        resource_id=str(user.id),
        ip_address=ip,
        request_id=request_id_var.get("-"),
    )
    await session.commit()

    access_token = create_access_token(str(user.id), user.email)
    refresh_token = create_refresh_token(str(user.id))

    logger.info(
        "OIDC login: %s",
        user.email,
        extra={"event": "oidc_login", "user_id": str(user.id), "email": user.email},
    )

    # Build a same-origin fragment redirect.  The frontend reads the
    # tokens from window.location.hash which is never sent to the server,
    # mitigating token leakage via Referer / server logs.
    # Use 303 (See Other) instead of 302 to prevent browsers from replaying
    # the POST body on redirect and to signal that the callback should not
    # be cached or bookmarked.
    frontend_base = (settings.oidc_redirect_uri or str(request.url_for("oidc_callback")))
    # Strip the callback path to get the origin, then anchor to the root.
    from urllib.parse import urlparse as _urlparse

    parsed = _urlparse(frontend_base)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    frontend_url = f"{origin}/#token={access_token}&refresh={refresh_token}"
    return RedirectResponse(url=frontend_url, status_code=303)


async def _find_or_create_user(
    session: AsyncSession,
    email: str,
    userinfo: dict[str, Any],
) -> User:
    """Find existing user by email or create from OIDC claims."""
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user:
        if not user.is_active:
            raise HTTPException(401, "Account is deactivated")
        user.last_login_at = datetime.now(UTC)
        return user

    display_name = userinfo.get("name") or userinfo.get("preferred_username") or email.split("@")[0]
    user = User(
        email=email,
        display_name=display_name,
        password_hash=_make_oidc_placeholder_hash(),
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)

    logger.info(
        "OIDC user created: %s",
        email,
        extra={"event": "oidc_user_created", "user_id": str(user.id), "email": email},
    )
    return user
