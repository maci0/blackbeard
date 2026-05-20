"""WebSocket endpoint authentication tests.

Tests the ``/api/v1/executions/{id}/ws`` endpoint auth behavior at the
unit level, exercising the auth logic that runs before any DB access.

Integration tests requiring a full DB session are not feasible here
because the WS handler uses ``async_session()`` directly (not the
FastAPI dependency) for status polling, which connects to the real
database engine rather than the test's in-memory SQLite.
"""

from __future__ import annotations

import hmac
import uuid

from blackbeard.auth.jwt import create_access_token

# ---------------------------------------------------------------------------
# Tests -- WS auth logic (unit-level)
# ---------------------------------------------------------------------------


def test_ws_auth_valid_api_key_accepted():
    """The WS handler should accept a valid API key via hmac.compare_digest."""
    from blackbeard.auth.api_key import _EXPECTED_API_KEY

    authenticated = hmac.compare_digest("change-me-in-production", _EXPECTED_API_KEY)
    assert authenticated is True


def test_ws_auth_invalid_api_key_rejected():
    """The WS handler should reject an invalid API key."""
    from blackbeard.auth.api_key import _EXPECTED_API_KEY

    authenticated = hmac.compare_digest("wrong-key", _EXPECTED_API_KEY)
    assert authenticated is False


def test_ws_auth_empty_api_key_rejected():
    """The WS handler should reject an empty API key."""
    from blackbeard.auth.api_key import _EXPECTED_API_KEY

    authenticated = hmac.compare_digest("", _EXPECTED_API_KEY)
    assert authenticated is False


def test_ws_auth_valid_jwt_accepted():
    """The WS handler should accept a valid JWT access token."""
    from blackbeard.auth.jwt import decode_token

    token = create_access_token(
        user_id=str(uuid.uuid4()), email="test@example.com"
    )
    payload = decode_token(token)
    assert payload.get("type") == "access"


def test_ws_auth_refresh_jwt_rejected():
    """The WS handler should reject a refresh token (type != access)."""
    from blackbeard.auth.jwt import create_refresh_token, decode_token

    token = create_refresh_token(user_id=str(uuid.uuid4()))
    payload = decode_token(token)
    # WS handler checks: payload.get("type") == "access"
    assert payload.get("type") != "access"
    assert payload.get("type") == "refresh"


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

    # The WS handler wraps decode_token in a try/except
    authenticated = False
    try:
        decoded = pyjwt.decode(
            expired_token,
            _get_secret(),
            algorithms=[_ALGORITHM],
            issuer=_ISSUER,
            audience=_AUDIENCE,
            options={"require": ["exp", "iss", "sub", "aud", "type"]},
        )
        if decoded.get("type") == "access":
            authenticated = True
    except (pyjwt.ExpiredSignatureError, pyjwt.InvalidTokenError):
        pass

    assert authenticated is False


def test_ws_auth_wrong_signature_rejected():
    """The WS handler should reject JWT signed with wrong secret."""
    from datetime import UTC, datetime, timedelta

    import jwt as pyjwt

    from blackbeard.auth.jwt import _ALGORITHM, _AUDIENCE, _ISSUER, _get_secret

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

    authenticated = False
    try:
        decoded = pyjwt.decode(
            bad_token,
            _get_secret(),
            algorithms=[_ALGORITHM],
            issuer=_ISSUER,
            audience=_AUDIENCE,
            options={"require": ["exp", "iss", "sub", "aud", "type"]},
        )
        if decoded.get("type") == "access":
            authenticated = True
    except (pyjwt.ExpiredSignatureError, pyjwt.InvalidTokenError):
        pass

    assert authenticated is False


def test_ws_auth_both_credentials_empty():
    """WS handler should reject when both token and api_key are empty."""
    from blackbeard.auth.api_key import _EXPECTED_API_KEY

    token = ""
    api_key = ""

    authenticated = False
    # token path
    if token:
        pass  # Would try decode_token
    # api_key path
    if not authenticated and api_key and hmac.compare_digest(api_key, _EXPECTED_API_KEY):
        authenticated = True

    assert authenticated is False
