"""Authentication API endpoints: register, login, refresh, profile, API key management."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import secrets
from datetime import UTC, datetime

import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from blackbeard.audit import get_client_ip, log_audit
from blackbeard.auth import (
    bearer_401,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    require_jwt_user,
    require_user,
    verify_password,
)
from blackbeard.config import settings
from blackbeard.logging_config import anonymize_ip
from blackbeard.models import User, get_session
from blackbeard.models.user_schemas import UserResponse, user_response
from blackbeard.rate_limiter import check_rate_limit_by_ip, registration_limiter

logger = logging.getLogger(__name__)


async def _register_litellm_user(user_id: str) -> None:
    """Register user in LiteLLM for per-user spend tracking (best-effort)."""
    try:
        from blackbeard.config import settings
        from blackbeard.http_client import get_litellm_client

        url = f"{settings.litellm_proxy_url}/user/new"
        client = get_litellm_client("litellm-user-reg", timeout=5)
        resp = await client.post(
            url,
            json={"user_id": user_id},
        )
        resp.raise_for_status()
    except Exception:
        logger.warning(
            "Could not register user in LiteLLM (proxy may not be running) — "
            "per-user spend tracking will be unavailable",
            exc_info=True,
            extra={"event": "litellm_user_registration_failed", "user_id": user_id},
        )


# Pre-computed bcrypt hash used to equalize timing when a login attempt
# targets a non-existent user (prevents email enumeration via timing).
_DUMMY_HASH = hash_password("timing-equalization-dummy")

router = APIRouter(prefix="/auth", tags=["auth"])


_PASSWORD_RE = re.compile(r"^(?=.*[a-zA-Z])(?=.*\d).{8,128}$")


class RegisterRequest(BaseModel):
    """User registration request."""

    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    display_name: str = Field(..., min_length=1, max_length=255)

    @field_validator("password")
    @classmethod
    def password_complexity(cls, v: str) -> str:
        if not _PASSWORD_RE.match(v):
            msg = "Password must contain at least one letter and one digit"
            raise ValueError(msg)
        return v


class LoginRequest(BaseModel):
    """User login request."""

    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    """Token refresh request."""

    refresh_token: str = Field(..., min_length=1, max_length=4096)


class AuthResponse(BaseModel):
    """Authentication response with tokens and user profile."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse


class TokenResponse(BaseModel):
    """Token refresh response (includes rotated refresh token)."""

    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"


def _auth_response(user: User) -> AuthResponse:
    """Build an AuthResponse with fresh access + refresh tokens."""
    return AuthResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
        user=user_response(user),
    )


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=201,
    responses={
        403: {"description": "Registration is disabled on this server"},
        409: {"description": "Email already registered"},
        429: {"description": "Too many registration attempts"},
    },
)
async def register(
    data: RegisterRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> AuthResponse:
    """Register a new user account."""
    if not settings.allow_registration:
        raise HTTPException(
            status_code=403,
            detail="User registration is disabled on this server",
        )
    ip = get_client_ip(request) or "unknown"
    check_rate_limit_by_ip(
        registration_limiter, ip, "Too many registration attempts. Try again later."
    )
    email = data.email.lower()

    hashed = await asyncio.to_thread(hash_password, data.password)
    user = User(
        email=email,
        display_name=data.display_name,
        password_hash=hashed,
    )
    try:
        async with session.begin_nested():
            session.add(user)
            await session.flush()
    except IntegrityError:
        logger.info(
            "Registration conflict from %s",
            anonymize_ip(ip),
            extra={"event": "registration_conflict", "client_ip": anonymize_ip(ip)},
        )
        raise HTTPException(
            status_code=409, detail="Registration failed — please try again or log in"
        ) from None

    await log_audit(
        session,
        action="user_registered",
        actor_type="user",
        actor_id=str(user.id),
        actor_email=user.email,
        resource_type="User",
        resource_id=str(user.id),
        ip_address=ip,
    )
    await session.commit()
    await session.refresh(user)

    logger.info(
        "User registered: user_id=%s from %s",
        user.id,
        anonymize_ip(ip),
        extra={
            "event": "user_registered",
            "user_id": str(user.id),
            "client_ip": anonymize_ip(ip),
        },
    )

    await _register_litellm_user(str(user.id))

    response.headers["Location"] = f"/api/v1/users/{user.id}"
    response.headers["Cache-Control"] = "no-store"
    return _auth_response(user)


@router.post(
    "/login",
    response_model=AuthResponse,
    responses={
        401: {"description": "Invalid email or password"},
        429: {"description": "Too many authentication failures"},
    },
)
async def login(
    data: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> AuthResponse:
    """Authenticate with email and password."""
    email = data.email.lower()
    ip = get_client_ip(request) or "unknown"
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    password_hash = user.password_hash if user else _DUMMY_HASH
    if not password_hash.startswith("$2"):
        # Spend bcrypt time to equalize timing with the normal path
        await asyncio.to_thread(verify_password, data.password, _DUMMY_HASH)
        valid = False
        if user is not None:
            logger.warning(
                "User %s has non-bcrypt password hash — login will always fail until reset",
                user.id,
                extra={
                    "event": "corrupted_password_hash",
                    "user_id": str(user.id),
                },
            )
    else:
        matched = await asyncio.to_thread(verify_password, data.password, password_hash)
        valid = matched and user is not None
    if not valid:
        logger.warning(
            "Login failed from %s",
            anonymize_ip(ip),
            extra={
                "event": "login_failed",
                "client_ip": anonymize_ip(ip),
            },
        )
        await log_audit(
            session,
            action="login_failed",
            actor_type="user",
            actor_id=str(user.id) if user is not None else "unknown",
            detail={"reason": "invalid_credentials"},
            ip_address=ip,
        )
        await session.commit()
        raise bearer_401("Invalid email or password")

    assert user is not None  # narrowing: valid=True implies user is not None
    if not user.is_active:
        logger.warning(
            "Login blocked (deactivated): user_id=%s from %s",
            user.id,
            anonymize_ip(ip),
            extra={
                "event": "login_blocked_deactivated",
                "user_id": str(user.id),
                "client_ip": anonymize_ip(ip),
            },
        )
        await log_audit(
            session,
            action="login_failed",
            actor_type="user",
            actor_id=str(user.id),
            actor_email=user.email,
            detail={"reason": "account_deactivated"},
            ip_address=ip,
        )
        await session.commit()
        raise bearer_401("Invalid email or password")

    user.last_login_at = datetime.now(UTC)
    await log_audit(
        session,
        action="user_login",
        actor_type="user",
        actor_id=str(user.id),
        actor_email=user.email,
        resource_type="User",
        resource_id=str(user.id),
        ip_address=ip,
    )
    await session.commit()
    await session.refresh(user)

    logger.info(
        "User logged in: user_id=%s from %s",
        user.id,
        anonymize_ip(ip),
        extra={
            "event": "user_login",
            "user_id": str(user.id),
            "client_ip": anonymize_ip(ip),
        },
    )

    response.headers["Cache-Control"] = "no-store"
    return _auth_response(user)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    responses={
        401: {"description": "Refresh token expired, invalid, or user inactive"},
        429: {"description": "Too many authentication failures"},
    },
)
async def refresh(
    data: RefreshRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    """Exchange a refresh token for a new access token."""
    try:
        payload = decode_token(data.refresh_token)
    except pyjwt.ExpiredSignatureError:
        logger.warning(
            "Refresh token expired",
            extra={"event": "refresh_token_expired"},
        )
        raise bearer_401("Refresh token has expired") from None
    except pyjwt.InvalidTokenError:
        logger.warning(
            "Invalid refresh token",
            extra={"event": "refresh_token_invalid"},
        )
        raise bearer_401("Invalid refresh token") from None

    if payload.get("type") != "refresh":
        logger.warning(
            "Refresh attempt with wrong token type: %s",
            payload.get("type"),
            extra={"event": "refresh_token_wrong_type", "token_type": payload.get("type")},
        )
        raise bearer_401("Invalid token type")

    user_id = payload.get("sub")
    if not user_id:
        logger.warning(
            "Refresh token missing sub claim",
            extra={"event": "refresh_token_missing_sub"},
        )
        raise bearer_401("Invalid token payload")

    result = await session.execute(
        select(User)
        .where(User.id == user_id)
        .options(defer(User.password_hash), defer(User.api_key))
    )
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        logger.warning(
            "Refresh token for missing/inactive user: sub=%s",
            user_id,
            extra={"event": "refresh_user_invalid", "user_id": str(user_id)},
        )
        raise bearer_401("User not found or inactive")

    access_token = create_access_token(str(user.id))
    new_refresh_token = create_refresh_token(str(user.id))
    logger.info(
        "Token refreshed: user_id=%s",
        user.id,
        extra={
            "event": "token_refreshed",
            "user_id": str(user.id),
        },
    )
    response.headers["Cache-Control"] = "no-store"
    return TokenResponse(access_token=access_token, refresh_token=new_refresh_token)


@router.get(
    "/me",
    response_model=UserResponse,
    responses={401: {"description": "Missing or invalid Bearer token"}},
)
async def me(
    response: Response,
    user: User = Depends(require_user),
) -> UserResponse:
    """Get the currently authenticated user's profile."""
    response.headers["Cache-Control"] = "no-store"
    return user_response(user)


# ---------------------------------------------------------------------------
# API Key management
# ---------------------------------------------------------------------------


class ApiKeyResponse(BaseModel):
    """Response containing a generated or rotated API key."""

    api_key: str


class ApiKeyStatusResponse(BaseModel):
    """Whether the current user has an API key configured."""

    has_key: bool


@router.get(
    "/api-key",
    response_model=ApiKeyStatusResponse,
    responses={401: {"description": "JWT Bearer token required"}},
)
async def get_api_key_status(
    response: Response,
    user: User = Depends(require_jwt_user),
) -> ApiKeyStatusResponse:
    """Check whether the current user has an API key configured.

    Requires JWT Bearer authentication (API key auth is not accepted).
    Only the SHA-256 hash of the key is stored, so no masked preview
    can be returned.
    """
    response.headers["Cache-Control"] = "no-store"
    return ApiKeyStatusResponse(has_key=user.api_key is not None)


@router.post(
    "/api-key",
    response_model=ApiKeyResponse,
    responses={401: {"description": "JWT Bearer token required"}},
)
async def generate_api_key(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_jwt_user),
) -> ApiKeyResponse:
    """Generate or rotate the current user's API key.

    Requires JWT Bearer authentication (API key auth is not accepted).
    Returns a new API key with ``bb-`` prefix.  Any previously issued
    key for this user is replaced.
    """
    ip = get_client_ip(request) or "unknown"
    # Re-fetch with row lock to prevent concurrent API key mutations.
    result = await session.execute(select(User).where(User.id == user.id).with_for_update())
    user = result.scalar_one()
    had_previous = user.api_key is not None
    new_key = f"bb-{secrets.token_urlsafe(32)}"
    user.api_key = hashlib.sha256(new_key.encode()).hexdigest()
    action = "api_key_rotated" if had_previous else "api_key_generated"
    await log_audit(
        session,
        action=action,
        actor_type="user",
        actor_id=str(user.id),
        actor_email=user.email,
        resource_type="User",
        resource_id=str(user.id),
        ip_address=ip,
    )
    await session.commit()

    logger.info(
        "API key %s for user_id=%s from %s",
        "rotated" if had_previous else "generated",
        user.id,
        anonymize_ip(ip),
        extra={
            "event": action,
            "user_id": str(user.id),
            "client_ip": anonymize_ip(ip),
        },
    )

    response.headers["Cache-Control"] = "no-store"
    return ApiKeyResponse(api_key=new_key)


@router.delete(
    "/api-key",
    status_code=204,
    responses={
        204: {"description": "API key revoked (or no key existed — idempotent)"},
        401: {"description": "JWT Bearer token required"},
    },
)
async def revoke_api_key(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_jwt_user),
) -> None:
    """Revoke the current user's API key.

    Requires JWT Bearer authentication (API key auth is not accepted).
    Idempotent: returns 204 even if the user has no active key.
    """
    ip = get_client_ip(request) or "unknown"
    # Re-fetch with row lock to prevent concurrent API key mutations.
    result = await session.execute(select(User).where(User.id == user.id).with_for_update())
    user = result.scalar_one()
    user.api_key = None

    await log_audit(
        session,
        action="api_key_revoked",
        actor_type="user",
        actor_id=str(user.id),
        actor_email=user.email,
        resource_type="User",
        resource_id=str(user.id),
        ip_address=ip,
    )
    await session.commit()

    logger.info(
        "API key revoked for user_id=%s from %s",
        user.id,
        anonymize_ip(ip),
        extra={
            "event": "api_key_revoked",
            "user_id": str(user.id),
            "client_ip": anonymize_ip(ip),
        },
    )
