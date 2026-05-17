"""Authentication API endpoints: register, login, refresh, profile."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from blackbeard.api.users import UserResponse, user_response
from blackbeard.auth.dependencies import require_user
from blackbeard.auth.jwt import create_access_token, create_refresh_token, decode_token
from blackbeard.auth.passwords import hash_password, verify_password
from blackbeard.models import User, get_session

logger = logging.getLogger(__name__)

# Pre-computed bcrypt hash used to equalize timing when a login attempt
# targets a non-existent user (prevents email enumeration via timing).
_DUMMY_HASH = hash_password("timing-equalization-dummy")

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    """User registration request."""

    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    display_name: str = Field(..., min_length=1, max_length=255)


class LoginRequest(BaseModel):
    """User login request."""

    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    """Token refresh request."""

    refresh_token: str = Field(..., min_length=1)


class AuthResponse(BaseModel):
    """Authentication response with tokens and user profile."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse


class TokenResponse(BaseModel):
    """Token refresh response."""

    access_token: str
    token_type: str = "bearer"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/register", response_model=AuthResponse, status_code=201)
async def register(
    data: RegisterRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> AuthResponse:
    """Register a new user account."""
    # Check for existing user
    result = await session.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        email=data.email,
        display_name=data.display_name,
        password_hash=hash_password(data.password),
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        logger.info(
            "Registration race: %s",
            data.email,
            extra={"event": "registration_race", "email": data.email},
        )
        raise HTTPException(status_code=409, detail="Email already registered") from None
    await session.refresh(user)

    logger.info(
        "User registered: %s",
        user.email,
        extra={"event": "user_registered", "user_id": str(user.id), "email": user.email},
    )

    response.headers["Location"] = f"/api/v1/users/{user.id}"
    access_token = create_access_token(str(user.id), user.email)
    refresh_token = create_refresh_token(str(user.id))

    return AuthResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=user_response(user),
    )


@router.post("/login", response_model=AuthResponse)
async def login(
    data: LoginRequest,
    session: AsyncSession = Depends(get_session),
) -> AuthResponse:
    """Authenticate with email and password."""
    result = await session.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if user is None:
        verify_password(data.password, _DUMMY_HASH)
        logger.warning(
            "Login failed: %s",
            data.email,
            extra={"event": "login_failed", "email": data.email},
        )
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not verify_password(data.password, user.password_hash):
        logger.warning(
            "Login failed: %s",
            data.email,
            extra={"event": "login_failed", "email": data.email},
        )
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.is_active:
        logger.warning(
            "Login blocked (deactivated): %s",
            data.email,
            extra={
                "event": "login_blocked_deactivated",
                "user_id": str(user.id),
                "email": data.email,
            },
        )
        raise HTTPException(status_code=403, detail="Account is deactivated")

    user.last_login_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(user)

    logger.info(
        "User logged in: %s",
        user.email,
        extra={"event": "user_login", "user_id": str(user.id), "email": user.email},
    )

    access_token = create_access_token(str(user.id), user.email)
    refresh_token = create_refresh_token(str(user.id))

    return AuthResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=user_response(user),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    data: RefreshRequest,
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
        raise HTTPException(status_code=401, detail="Refresh token has expired") from None
    except pyjwt.InvalidTokenError:
        logger.warning(
            "Invalid refresh token",
            extra={"event": "refresh_token_invalid"},
        )
        raise HTTPException(status_code=401, detail="Invalid refresh token") from None

    if payload.get("type") != "refresh":
        logger.warning(
            "Refresh attempt with wrong token type: %s",
            payload.get("type"),
            extra={"event": "refresh_token_wrong_type", "token_type": payload.get("type")},
        )
        raise HTTPException(status_code=401, detail="Invalid token type")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        logger.warning(
            "Refresh token for missing/inactive user: sub=%s",
            user_id,
            extra={"event": "refresh_user_invalid", "user_id": str(user_id)},
        )
        raise HTTPException(status_code=401, detail="User not found or inactive")

    access_token = create_access_token(str(user.id), user.email)
    logger.info(
        "Token refreshed: %s",
        user.email,
        extra={"event": "token_refreshed", "user_id": str(user.id)},
    )
    return TokenResponse(access_token=access_token)


@router.get("/me", response_model=UserResponse)
async def me(
    user: User = Depends(require_user),
) -> UserResponse:
    """Get the currently authenticated user's profile."""
    return user_response(user)
