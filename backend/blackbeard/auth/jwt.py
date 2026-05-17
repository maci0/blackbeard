"""JWT token creation and verification."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from blackbeard.config import settings

_ALGORITHM = "HS256"
_ISSUER = "blackbeard"


def create_access_token(user_id: str, email: str) -> str:
    """Create a short-lived JWT access token (default 15 minutes)."""
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": user_id,
        "email": email,
        "type": "access",
        "iss": _ISSUER,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_token_expire_minutes),
    }
    return jwt.encode(
        payload,
        settings.jwt_secret.get_secret_value(),
        algorithm=_ALGORITHM,
    )


def create_refresh_token(user_id: str) -> str:
    """Create a long-lived JWT refresh token (default 7 days)."""
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": user_id,
        "type": "refresh",
        "iss": _ISSUER,
        "iat": now,
        "exp": now + timedelta(days=settings.jwt_refresh_token_expire_days),
    }
    return jwt.encode(
        payload,
        settings.jwt_secret.get_secret_value(),
        algorithm=_ALGORITHM,
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
        settings.jwt_secret.get_secret_value(),
        algorithms=[_ALGORITHM],
        issuer=_ISSUER,
    )
