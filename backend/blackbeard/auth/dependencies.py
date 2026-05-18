"""FastAPI dependencies for authentication."""

from __future__ import annotations

import logging

import jwt as pyjwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from blackbeard.auth.jwt import decode_token
from blackbeard.logging_config import request_id_var
from blackbeard.models import User, get_session

logger = logging.getLogger(__name__)


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User | None:
    """Extract authenticated user from JWT Bearer token or API key.

    Returns the User if authentication succeeds, None if no credentials
    are present. The middleware layer handles X-API-Key auth for
    system-level access; this dependency resolves user identity from
    JWT tokens or per-user API keys.
    """
    # Try Authorization: Bearer <token>
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            payload = decode_token(token)
        except pyjwt.ExpiredSignatureError:
            logger.info(
                "JWT expired",
                extra={"event": "jwt_expired", "request_id": request_id_var.get("-")},
            )
            raise HTTPException(
                status_code=401,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            ) from None
        except pyjwt.InvalidTokenError:
            logger.warning(
                "JWT invalid",
                extra={"event": "jwt_invalid", "request_id": request_id_var.get("-")},
            )
            raise HTTPException(
                status_code=401,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            ) from None

        if payload.get("type") != "access":
            logger.warning(
                "JWT wrong type: %s",
                payload.get("type"),
                extra={
                    "event": "jwt_wrong_type",
                    "token_type": payload.get("type"),
                    "request_id": request_id_var.get("-"),
                },
            )
            raise HTTPException(
                status_code=401,
                detail="Invalid token type",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user_id = payload.get("sub")
        if not user_id:
            logger.warning(
                "JWT missing sub claim",
                extra={"event": "jwt_missing_sub", "request_id": request_id_var.get("-")},
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
                "JWT user not found or inactive: sub=%s",
                user_id,
                extra={
                    "event": "jwt_user_invalid",
                    "user_id": str(user_id),
                    "request_id": request_id_var.get("-"),
                },
            )
            raise HTTPException(
                status_code=401,
                detail="User not found or inactive",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user

    # Try resolving the X-API-Key to a user (optional — API key may belong to
    # the global system key rather than a user-specific key).
    # Only accept query-string keys on SSE/stream endpoints where EventSource
    # cannot set custom headers — query-string credentials leak via proxy logs,
    # browser history, and Referer headers (CWE-598).
    api_key = request.headers.get("X-API-Key", "")
    if not api_key and request.url.path.endswith("/stream"):
        api_key = request.query_params.get("api_key", "")
    if api_key and len(api_key) >= 16:
        result = await session.execute(
            select(User).where(User.api_key == api_key).options(defer(User.password_hash))
        )
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
        logger.warning(
            "Authentication required but no credentials provided",
            extra={
                "event": "auth_required_no_credentials",
                "request_id": request_id_var.get("-"),
            },
        )
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Provide a Bearer token or user API key.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
