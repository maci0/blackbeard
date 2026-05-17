"""FastAPI dependencies for authentication."""

from __future__ import annotations

import logging

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from blackbeard.auth.jwt import decode_token
from blackbeard.models.database import get_session
from blackbeard.models.user import User

logger = logging.getLogger(__name__)


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User | None:
    """Extract authenticated user from JWT Bearer token or API key.

    Returns the User if authentication succeeds, None if no credentials
    are present. The middleware layer handles X-API-Key auth for backward
    compatibility; this dependency handles JWT-based user identity.
    """
    # Try Authorization: Bearer <token>
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            payload = decode_token(token)
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token has expired") from None
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token") from None

        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token payload")

        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None or not user.is_active:
            raise HTTPException(status_code=401, detail="User not found or inactive")
        return user

    # Try resolving the X-API-Key to a user (optional — API key may belong to
    # the global system key rather than a user-specific key)
    api_key = request.headers.get("X-API-Key", "") or request.query_params.get("api_key", "")
    if api_key:
        result = await session.execute(select(User).where(User.api_key == api_key))
        user = result.scalar_one_or_none()
        if user is not None and user.is_active:
            return user

    # No user-level credentials found — request may still be authenticated
    # via the global API key middleware
    return None


async def require_user(
    user: User | None = Depends(get_current_user),
) -> User:
    """Require an authenticated user. Returns 401 if not authenticated."""
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Provide a Bearer token or user API key.",
        )
    return user
