"""Authentication API endpoints: register, login, refresh, profile."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from blackbeard.auth.dependencies import require_user
from blackbeard.auth.jwt import create_access_token, create_refresh_token, decode_token
from blackbeard.auth.passwords import hash_password, verify_password
from blackbeard.models.database import get_session
from blackbeard.models.user import User

logger = logging.getLogger(__name__)

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


class UserResponse(BaseModel):
    """Public user profile response."""

    id: str
    email: str
    display_name: str
    is_active: bool
    created_at: str
    last_login_at: str | None = None


class AuthResponse(BaseModel):
    """Authentication response with tokens and user profile."""

    access_token: str
    refresh_token: str
    user: UserResponse


class TokenResponse(BaseModel):
    """Token refresh response."""

    access_token: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _user_response(user: User) -> UserResponse:
    return UserResponse(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        is_active=user.is_active,
        created_at=user.created_at.isoformat() if user.created_at else "",
        last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/register", response_model=AuthResponse, status_code=201)
async def register(
    data: RegisterRequest,
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
    await session.commit()
    await session.refresh(user)

    logger.info(
        "User registered: %s",
        user.email,
        extra={"event": "user_registered", "user_id": str(user.id), "email": user.email},
    )

    access_token = create_access_token(str(user.id), user.email)
    refresh_token = create_refresh_token(str(user.id))

    return AuthResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=_user_response(user),
    )


@router.post("/login", response_model=AuthResponse)
async def login(
    data: LoginRequest,
    session: AsyncSession = Depends(get_session),
) -> AuthResponse:
    """Authenticate with email and password."""
    result = await session.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.is_active:
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
        user=_user_response(user),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    data: RefreshRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    """Exchange a refresh token for a new access token."""
    import jwt as pyjwt

    try:
        payload = decode_token(data.refresh_token)
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token has expired") from None
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token") from None

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    access_token = create_access_token(str(user.id), user.email)
    return TokenResponse(access_token=access_token)


@router.get("/me", response_model=UserResponse)
async def me(
    user: User = Depends(require_user),
) -> UserResponse:
    """Get the currently authenticated user's profile."""
    return _user_response(user)
