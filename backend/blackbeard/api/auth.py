"""Authentication API endpoints: register, login, refresh, profile."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime

import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from blackbeard.auth.dependencies import require_user
from blackbeard.auth.jwt import create_access_token, create_refresh_token, decode_token
from blackbeard.auth.passwords import hash_password, verify_password
from blackbeard.logging_config import request_id_var
from blackbeard.models import User, get_session
from blackbeard.models.user_schemas import UserResponse, user_response

logger = logging.getLogger(__name__)

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


def _auth_response(user: User) -> AuthResponse:
    """Build an AuthResponse with fresh access + refresh tokens."""
    return AuthResponse(
        access_token=create_access_token(str(user.id), user.email),
        refresh_token=create_refresh_token(str(user.id)),
        user=user_response(user),
    )


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=201,
    responses={409: {"description": "Email already registered"}},
)
async def register(
    data: RegisterRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> AuthResponse:
    """Register a new user account."""
    email = data.email.lower()
    user = User(
        email=email,
        display_name=data.display_name,
        password_hash=hash_password(data.password),
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        logger.info(
            "Registration conflict: %s",
            data.email,
            extra={"event": "registration_conflict", "email": data.email},
        )
        raise HTTPException(
            status_code=409, detail="Registration failed — please try again or log in"
        ) from None
    await session.refresh(user)

    logger.info(
        "User registered: %s",
        user.email,
        extra={
            "event": "user_registered",
            "user_id": str(user.id),
            "email": user.email,
            "request_id": request_id_var.get("-"),
        },
    )

    response.headers["Location"] = f"/api/v1/users/{user.id}"
    return _auth_response(user)


@router.post(
    "/login",
    response_model=AuthResponse,
    responses={
        401: {"description": "Invalid email or password"},
        403: {"description": "Account is deactivated"},
    },
)
async def login(
    data: LoginRequest,
    session: AsyncSession = Depends(get_session),
) -> AuthResponse:
    """Authenticate with email and password."""
    email = data.email.lower()
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    password_hash = user.password_hash if user else _DUMMY_HASH
    valid = verify_password(data.password, password_hash) and user is not None
    if not valid:
        logger.warning(
            "Login failed: %s",
            data.email,
            extra={
                "event": "login_failed",
                "email": data.email,
                "request_id": request_id_var.get("-"),
            },
        )
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    assert user is not None  # narrowing: valid=True implies user is not None
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
        extra={
            "event": "user_login",
            "user_id": str(user.id),
            "email": user.email,
            "request_id": request_id_var.get("-"),
        },
    )

    return _auth_response(user)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    responses={401: {"description": "Refresh token expired, invalid, or user inactive"}},
)
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
        raise HTTPException(
            status_code=401,
            detail="Refresh token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    except pyjwt.InvalidTokenError:
        logger.warning(
            "Invalid refresh token",
            extra={"event": "refresh_token_invalid"},
        )
        raise HTTPException(
            status_code=401,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    if payload.get("type") != "refresh":
        logger.warning(
            "Refresh attempt with wrong token type: %s",
            payload.get("type"),
            extra={"event": "refresh_token_wrong_type", "token_type": payload.get("type")},
        )
        raise HTTPException(
            status_code=401,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        logger.warning(
            "Refresh token missing sub claim",
            extra={"event": "refresh_token_missing_sub"},
        )
        raise HTTPException(
            status_code=401,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await session.execute(
        select(User).where(User.id == user_id).options(defer(User.password_hash))
    )
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        logger.warning(
            "Refresh token for missing/inactive user: sub=%s",
            user_id,
            extra={"event": "refresh_user_invalid", "user_id": str(user_id)},
        )
        raise HTTPException(
            status_code=401,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(str(user.id), user.email)
    logger.info(
        "Token refreshed: %s",
        user.email,
        extra={
            "event": "token_refreshed",
            "user_id": str(user.id),
            "request_id": request_id_var.get("-"),
        },
    )
    return TokenResponse(access_token=access_token)


@router.get(
    "/me",
    response_model=UserResponse,
    responses={401: {"description": "Missing or invalid Bearer token"}},
)
async def me(
    user: User = Depends(require_user),
) -> UserResponse:
    """Get the currently authenticated user's profile."""
    return user_response(user)
