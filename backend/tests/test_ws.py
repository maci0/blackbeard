"""WebSocket endpoint authentication tests.

Tests the ``/api/v1/executions/{id}/ws`` endpoint auth behavior at the
unit level, exercising the auth logic that runs before any DB access.

Integration tests requiring a full DB session are not feasible here
because the WS handler uses ``async_session()`` directly (not the
FastAPI dependency) for status polling, which connects to the real
database engine rather than the test's in-memory SQLite.
"""

from __future__ import annotations

import uuid

from blackbeard.api.collaboration import validate_ws_auth
from blackbeard.auth.api_key import _EXPECTED_API_KEY
from blackbeard.auth.jwt import create_access_token

# ---------------------------------------------------------------------------
# Tests -- WS auth logic (unit-level) — uses the actual validate_ws_auth
# ---------------------------------------------------------------------------


def test_ws_auth_valid_api_key_accepted():
    """The WS handler should accept a valid API key."""
    assert validate_ws_auth("", _EXPECTED_API_KEY) is True


def test_ws_auth_invalid_api_key_rejected():
    """The WS handler should reject an invalid API key."""
    assert validate_ws_auth("", "wrong-key") is False


def test_ws_auth_empty_api_key_rejected():
    """The WS handler should reject an empty API key."""
    assert validate_ws_auth("", "") is False


def test_ws_auth_valid_jwt_accepted():
    """The WS handler should accept a valid JWT access token."""
    token = create_access_token(
        user_id=str(uuid.uuid4())
    )
    assert validate_ws_auth(token, "") is True


def test_ws_auth_refresh_jwt_rejected():
    """The WS handler should reject a refresh token (type != access)."""
    from blackbeard.auth.jwt import create_refresh_token

    token = create_refresh_token(user_id=str(uuid.uuid4()))
    assert validate_ws_auth(token, "") is False


def test_ws_auth_expired_jwt_rejected():
    """The WS handler should reject an expired JWT token."""
    from datetime import UTC, datetime, timedelta

    import jwt as pyjwt

    from blackbeard.auth.jwt import _ALGORITHM, _AUDIENCE, _ISSUER, _get_secret

    now = datetime.now(UTC)
    payload = {
        "sub": str(uuid.uuid4()),
        "type": "access",
        "iss": _ISSUER,
        "aud": _AUDIENCE,
        "iat": now - timedelta(hours=2),
        "exp": now - timedelta(hours=1),
    }
    expired_token = pyjwt.encode(payload, _get_secret(), algorithm=_ALGORITHM)
    assert validate_ws_auth(expired_token, "") is False


def test_ws_auth_wrong_signature_rejected():
    """The WS handler should reject JWT signed with wrong secret."""
    from datetime import UTC, datetime, timedelta

    import jwt as pyjwt

    from blackbeard.auth.jwt import _ALGORITHM, _AUDIENCE, _ISSUER

    now = datetime.now(UTC)
    payload = {
        "sub": str(uuid.uuid4()),
        "type": "access",
        "iss": _ISSUER,
        "aud": _AUDIENCE,
        "iat": now,
        "exp": now + timedelta(hours=1),
    }
    bad_token = pyjwt.encode(payload, "wrong-secret-key", algorithm=_ALGORITHM)
    assert validate_ws_auth(bad_token, "") is False


def test_ws_auth_both_credentials_empty():
    """WS handler should reject when both token and api_key are empty."""
    assert validate_ws_auth("", "") is False
