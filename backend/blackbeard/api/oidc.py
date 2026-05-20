"""OIDC / SSO authentication endpoints.

Generic OIDC client — works with any provider (Google, Azure AD, Okta,
Keycloak, Authentik). Configured via OIDC_ISSUER, OIDC_CLIENT_ID,
OIDC_CLIENT_SECRET environment variables.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request
from starlette.responses import RedirectResponse

from blackbeard.auth.jwt import create_access_token, create_refresh_token
from blackbeard.config import settings
from blackbeard.models import User, get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/oidc", tags=["auth"])

_OIDC_PASSWORD_PLACEHOLDER = "OIDC_USER_NO_PASSWORD"

_oauth: OAuth | None = None


def _get_oauth() -> OAuth:
    global _oauth
    if _oauth is not None:
        return _oauth

    if not settings.oidc_issuer:
        raise HTTPException(501, "OIDC not configured. Set OIDC_ISSUER env var.")

    oauth = OAuth()
    client_secret = (
        settings.oidc_client_secret.get_secret_value()
        if settings.oidc_client_secret
        else None
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
        logger.warning("OIDC token exchange failed: %s", exc)
        raise HTTPException(401, "OIDC authentication failed") from None

    userinfo = token.get("userinfo")
    if not userinfo:
        try:
            userinfo = await oauth.provider.userinfo(token=token)
        except Exception:
            userinfo = {}

    email = (userinfo.get("email") or "").lower().strip()
    if not email:
        raise HTTPException(400, "OIDC provider did not return an email address")

    user = await _find_or_create_user(session, email, userinfo)

    access_token = create_access_token(str(user.id), user.email)
    refresh_token = create_refresh_token(str(user.id))

    logger.info(
        "OIDC login: %s",
        user.email,
        extra={"event": "oidc_login", "user_id": str(user.id), "email": user.email},
    )

    frontend_url = f"/?token={access_token}&refresh={refresh_token}"
    return RedirectResponse(url=frontend_url, status_code=302)


async def _find_or_create_user(
    session: AsyncSession,
    email: str,
    userinfo: dict[str, Any],
) -> User:
    """Find existing user by email or create from OIDC claims."""
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user:
        user.last_login_at = datetime.now(UTC)
        await session.commit()
        return user

    display_name = (
        userinfo.get("name")
        or userinfo.get("preferred_username")
        or email.split("@")[0]
    )
    user = User(
        email=email,
        display_name=display_name,
        password_hash=_OIDC_PASSWORD_PLACEHOLDER,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    logger.info(
        "OIDC user created: %s",
        email,
        extra={"event": "oidc_user_created", "user_id": str(user.id), "email": email},
    )
    return user
