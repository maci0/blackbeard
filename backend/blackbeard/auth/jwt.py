"""JWT token creation and verification."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from blackbeard.config import settings

_ALGORITHM = "HS256"
_ISSUER = "blackbeard"
_AUDIENCE = "blackbeard"

_jwt_secret: str | None = None


def _get_secret() -> str:
    global _jwt_secret
    if _jwt_secret is None:
        _jwt_secret = settings.jwt_secret.get_secret_value()
    return _jwt_secret


def _create_token(token_type: str, expires_delta: timedelta, **extra: Any) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        **extra,
        "type": token_type,
        "jti": uuid.uuid4().hex,
        "iss": _ISSUER,
        "aud": _AUDIENCE,
        "iat": now,
        "nbf": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, _get_secret(), algorithm=_ALGORITHM)


def create_access_token(user_id: str) -> str:
    """Create a short-lived JWT access token (default 15 minutes)."""
    return _create_token(
        "access",
        timedelta(minutes=settings.jwt_access_token_expire_minutes),
        sub=user_id,
    )


def create_refresh_token(user_id: str) -> str:
    """Create a long-lived JWT refresh token (default 7 days)."""
    return _create_token(
        "refresh",
        timedelta(days=settings.jwt_refresh_token_expire_days),
        sub=user_id,
    )


def decode_token(token: str) -> dict[str, Any]:
    """Decode and verify a JWT token.

    Returns the decoded payload dict.
    Raises jwt.ExpiredSignatureError if the token has expired.
    Raises jwt.InvalidTokenError for any other validation failure
    (including issuer mismatch).
    """
    return jwt.decode(
        token,
        _get_secret(),
        algorithms=[_ALGORITHM],
        issuer=_ISSUER,
        audience=_AUDIENCE,
        options={"require": ["exp", "iat", "nbf", "iss", "sub", "aud", "type", "jti"]},
    )
