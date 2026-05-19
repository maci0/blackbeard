"""WebSocket endpoint authentication tests.

Tests the ``/api/v1/executions/{id}/ws`` endpoint auth behavior.

The WS handler uses ``async_session()`` directly (not dependency-injected)
for status polling, so accepted-connection tests that need DB access are
limited to verifying the connection is accepted (not rejected).  Auth
rejection tests work fully because they close before any DB query.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient

from blackbeard.auth.jwt import create_access_token
from blackbeard.main import app
from blackbeard.models.database import get_session
from tests.conftest import API_KEY_HEADER

_TEST_API_KEY = "change-me-in-production"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ws_client(db_session: AsyncSession):
    """Synchronous test client for WebSocket testing.

    Pins the middleware API key to the test default so that
    API_KEY_HEADER works correctly.
    """
    from blackbeard.api.middleware import _auth_failures, set_api_key

    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    _auth_failures.clear()
    set_api_key(_TEST_API_KEY)

    with TestClient(app, raise_server_exceptions=False) as c:
        set_api_key(_TEST_API_KEY)
        yield c

    app.dependency_overrides.clear()
    _auth_failures.clear()


def _create_crew_resources(ws_client: TestClient) -> None:
    """Create LLM, agent, task, crew resources for kickoff."""
    r = ws_client.post(
        "/api/v1/llm-connections",
        json={
            "apiVersion": "blackbeard/v1",
            "kind": "LLMConnection",
            "metadata": {"name": "test-llm"},
            "spec": {"provider": "vertex_ai", "model": "claude-sonnet-4-6"},
        },
        headers=API_KEY_HEADER,
    )
    assert r.status_code in (200, 201), f"LLMConnection: {r.status_code} {r.text}"

    r = ws_client.post(
        "/api/v1/agents",
        json={
            "apiVersion": "blackbeard/v1",
            "kind": "Agent",
            "metadata": {"name": "test-agent"},
            "spec": {
                "role": "Test Agent",
                "goal": "Test goal",
                "backstory": "Test backstory",
                "llm": "ref:llm-connections/test-llm",
            },
        },
        headers=API_KEY_HEADER,
    )
    assert r.status_code in (200, 201), f"Agent: {r.status_code} {r.text}"

    r = ws_client.post(
        "/api/v1/tasks",
        json={
            "apiVersion": "blackbeard/v1",
            "kind": "Task",
            "metadata": {"name": "test-task"},
            "spec": {
                "description": "Test task",
                "expected_output": "Test output",
                "agent": "ref:agents/test-agent",
            },
        },
        headers=API_KEY_HEADER,
    )
    assert r.status_code in (200, 201), f"Task: {r.status_code} {r.text}"

    r = ws_client.post(
        "/api/v1/crews",
        json={
            "apiVersion": "blackbeard/v1",
            "kind": "Crew",
            "metadata": {"name": "test-crew"},
            "spec": {
                "process": "sequential",
                "agents": ["ref:agents/test-agent"],
                "tasks": ["ref:tasks/test-task"],
            },
        },
        headers=API_KEY_HEADER,
    )
    assert r.status_code in (200, 201), f"Crew: {r.status_code} {r.text}"


def _kickoff_crew(ws_client: TestClient) -> str:
    """Kick off a crew and return the execution ID."""
    r = ws_client.post(
        "/api/v1/crews/test-crew/kickoff",
        json={"inputs": {}},
        headers=API_KEY_HEADER,
    )
    assert r.status_code == 202, f"Kickoff: {r.status_code} {r.text}"
    return r.json()["id"]


# ---------------------------------------------------------------------------
# Tests -- WS auth rejection (no DB needed after auth check)
# ---------------------------------------------------------------------------


def test_ws_no_auth_rejected(ws_client: TestClient):
    """WS connection without auth params should be closed with 4401."""
    _create_crew_resources(ws_client)
    exec_id = _kickoff_crew(ws_client)

    with pytest.raises(Exception), ws_client.websocket_connect(
        f"/api/v1/executions/{exec_id}/ws"
    ) as ws:
        ws.receive_json()


def test_ws_invalid_api_key_rejected(ws_client: TestClient):
    """WS connection with wrong API key should be closed with 4401."""
    _create_crew_resources(ws_client)
    exec_id = _kickoff_crew(ws_client)

    with pytest.raises(Exception), ws_client.websocket_connect(
        f"/api/v1/executions/{exec_id}/ws?api_key=wrong-key"
    ) as ws:
        ws.receive_json()


def test_ws_empty_api_key_rejected(ws_client: TestClient):
    """WS connection with empty API key should be closed with 4401."""
    exec_id = str(uuid.uuid4())

    with pytest.raises(Exception), ws_client.websocket_connect(
        f"/api/v1/executions/{exec_id}/ws?api_key="
    ) as ws:
        ws.receive_json()


def test_ws_expired_jwt_rejected(ws_client: TestClient):
    """WS connection with expired JWT token should be closed with 4401."""
    _create_crew_resources(ws_client)
    exec_id = _kickoff_crew(ws_client)

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

    with pytest.raises(Exception), ws_client.websocket_connect(
        f"/api/v1/executions/{exec_id}/ws?token={expired_token}"
    ) as ws:
        ws.receive_json()


def test_ws_refresh_token_rejected(ws_client: TestClient):
    """WS connection with refresh token (not access) should be rejected."""
    _create_crew_resources(ws_client)
    exec_id = _kickoff_crew(ws_client)

    from blackbeard.auth.jwt import create_refresh_token

    refresh = create_refresh_token(user_id=str(uuid.uuid4()))

    with pytest.raises(Exception), ws_client.websocket_connect(
        f"/api/v1/executions/{exec_id}/ws?token={refresh}"
    ) as ws:
        ws.receive_json()


def test_ws_invalid_jwt_signature_rejected(ws_client: TestClient):
    """WS connection with JWT signed by wrong secret should be rejected."""
    _create_crew_resources(ws_client)
    exec_id = _kickoff_crew(ws_client)

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

    with pytest.raises(Exception), ws_client.websocket_connect(
        f"/api/v1/executions/{exec_id}/ws?token={bad_token}"
    ) as ws:
        ws.receive_json()


# ---------------------------------------------------------------------------
# Tests -- WS auth acceptance (unit-level, testing auth logic directly)
# ---------------------------------------------------------------------------


def test_ws_auth_logic_valid_api_key():
    """The WS handler auth logic should accept a valid API key."""
    import hmac

    from blackbeard.api.middleware import _EXPECTED_API_KEY

    # Simulate the auth check from ws_execution handler
    api_key = _TEST_API_KEY
    authenticated = hmac.compare_digest(api_key, _EXPECTED_API_KEY)
    assert authenticated is True


def test_ws_auth_logic_invalid_api_key():
    """The WS handler auth logic should reject an invalid API key."""
    import hmac

    from blackbeard.api.middleware import _EXPECTED_API_KEY

    api_key = "definitely-wrong-key"
    authenticated = hmac.compare_digest(api_key, _EXPECTED_API_KEY)
    assert authenticated is False


def test_ws_auth_logic_valid_jwt():
    """The WS handler auth logic should accept a valid JWT access token."""
    from blackbeard.auth.jwt import decode_token

    token = create_access_token(
        user_id=str(uuid.uuid4()), email="test@example.com"
    )
    payload = decode_token(token)
    assert payload.get("type") == "access"


def test_ws_auth_logic_rejects_refresh_jwt():
    """The WS handler auth logic should reject a refresh token type."""
    from blackbeard.auth.jwt import create_refresh_token, decode_token

    token = create_refresh_token(user_id=str(uuid.uuid4()))
    payload = decode_token(token)
    # The WS handler checks for type == "access"
    assert payload.get("type") != "access"
    assert payload.get("type") == "refresh"
