"""Integration tests for auth dependencies and additional user/group endpoints.

Covers: get_current_user dependency (JWT resolution, API key resolution),
require_user dependency (401 on missing auth), and edge cases for
user/group CRUD endpoints not covered in test_auth.py.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from tests.conftest import API_KEY_HEADER, _bearer, _register_user

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DEP_EMAIL = "dep-test@example.com"


# ---------------------------------------------------------------------------
# get_current_user: JWT auth
# ---------------------------------------------------------------------------


async def test_get_current_user_valid_jwt(client: AsyncClient):
    """Bearer token with valid JWT resolves user for protected endpoints."""
    data = await _register_user(client, email=_DEP_EMAIL)
    token = data["access_token"]

    # /auth/me uses require_user -> get_current_user
    resp = await client.get("/api/v1/auth/me", headers=_bearer(token))
    assert resp.status_code == 200
    assert resp.json()["email"] == "dep-test@example.com"


async def test_get_current_user_expired_jwt(client: AsyncClient):
    """Expired JWT returns 401."""
    from datetime import UTC, datetime, timedelta

    import jwt as pyjwt

    from blackbeard.config import settings

    # Create an expired token manually
    payload = {
        "sub": str(uuid.uuid4()),
        "email": "expired@test.com",
        "type": "access",
        "exp": datetime.now(UTC) - timedelta(hours=1),
        "iat": datetime.now(UTC) - timedelta(hours=2),
    }
    expired_token = pyjwt.encode(
        payload,
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )
    resp = await client.get("/api/v1/auth/me", headers=_bearer(expired_token))
    assert resp.status_code == 401
    assert "expired" in resp.json()["detail"].lower()


async def test_get_current_user_invalid_jwt(client: AsyncClient):
    """Invalid JWT string returns 401."""
    resp = await client.get("/api/v1/auth/me", headers=_bearer("not.valid.jwt"))
    assert resp.status_code == 401


async def test_get_current_user_wrong_token_type(client: AsyncClient):
    """JWT with type='refresh' used as Bearer returns 401."""
    data = await _register_user(client, email=_DEP_EMAIL)
    # Use the refresh token as a bearer token
    resp = await client.get(
        "/api/v1/auth/me",
        headers=_bearer(data["refresh_token"]),
    )
    assert resp.status_code == 401
    detail = resp.json()["detail"].lower()
    # Middleware rejects non-access tokens with "invalid or expired bearer token"
    assert "invalid" in detail or "token" in detail or "type" in detail


async def test_get_current_user_jwt_missing_sub(client: AsyncClient):
    """JWT without sub claim returns 401."""
    from datetime import UTC, datetime, timedelta

    import jwt as pyjwt

    from blackbeard.config import settings

    payload = {
        "email": "test@test.com",
        "type": "access",
        "exp": datetime.now(UTC) + timedelta(hours=1),
        "iat": datetime.now(UTC),
        # No 'sub' claim
    }
    token = pyjwt.encode(
        payload,
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )
    resp = await client.get("/api/v1/auth/me", headers=_bearer(token))
    assert resp.status_code == 401


async def test_get_current_user_jwt_deleted_user(client: AsyncClient):
    """JWT for deactivated user returns 401."""
    data = await _register_user(client, email=_DEP_EMAIL)
    token = data["access_token"]
    user_id = data["user"]["id"]

    # Deactivate the user
    resp = await client.delete(f"/api/v1/users/{user_id}", headers=_bearer(token))
    assert resp.status_code == 204

    # Try to access with the same token
    resp = await client.get("/api/v1/auth/me", headers=_bearer(token))
    assert resp.status_code == 401
    detail = resp.json()["detail"].lower()
    assert "inactive" in detail or "not found" in detail


async def test_get_current_user_returns_none_for_api_key_only(client: AsyncClient):
    """System API key auth returns None user (not 401) for execution endpoints."""
    # Resource endpoints work with system API key but get_current_user returns None
    resp = await client.get("/api/v1/agents", headers=API_KEY_HEADER)
    assert resp.status_code == 200  # Works: system API key is sufficient


# ---------------------------------------------------------------------------
# require_user: 401 on missing auth
# ---------------------------------------------------------------------------


async def test_require_user_no_auth(client: AsyncClient):
    """Endpoints using require_user return 401 without any auth."""
    resp = await client.get("/api/v1/users")
    assert resp.status_code == 401


async def test_require_user_api_key_without_user(client: AsyncClient):
    """System API key without per-user binding fails require_user endpoints."""
    resp = await client.get("/api/v1/users", headers=API_KEY_HEADER)
    assert resp.status_code == 401


async def test_require_user_with_jwt(client: AsyncClient):
    """require_user succeeds with valid JWT."""
    data = await _register_user(client, email=_DEP_EMAIL)
    resp = await client.get("/api/v1/users", headers=_bearer(data["access_token"]))
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# User endpoints: additional edge cases
# ---------------------------------------------------------------------------


async def test_update_other_user_forbidden(client: AsyncClient):
    """PUT /users/{id} for another user returns 403."""
    user1 = await _register_user(client, email="user1@test.com")
    user2 = await _register_user(client, email="user2@test.com")

    resp = await client.put(
        f"/api/v1/users/{user2['user']['id']}",
        json={"display_name": "Hacked Name"},
        headers=_bearer(user1["access_token"]),
    )
    assert resp.status_code == 403


async def test_update_user_preserves_email(client: AsyncClient):
    """PUT /users/{id} updating display_name does not change email."""
    data = await _register_user(client, email=_DEP_EMAIL)
    user_id = data["user"]["id"]
    token = data["access_token"]

    resp = await client.put(
        f"/api/v1/users/{user_id}",
        json={"display_name": "New Name"},
        headers=_bearer(token),
    )
    assert resp.status_code == 200
    assert resp.json()["email"] == "dep-test@example.com"
    assert resp.json()["display_name"] == "New Name"


async def test_get_user_not_found(client: AsyncClient):
    """GET /users/{id} for non-existent UUID returns 404."""
    data = await _register_user(client, email=_DEP_EMAIL)
    fake_id = str(uuid.uuid4())

    resp = await client.get(
        f"/api/v1/users/{fake_id}",
        headers=_bearer(data["access_token"]),
    )
    assert resp.status_code == 404


async def test_deactivate_self(client: AsyncClient, db_session):
    """DELETE /users/{id} deactivates the caller and erases their stored identity."""
    import uuid

    from sqlalchemy import select

    from blackbeard.models.audit import AuditLog
    from blackbeard.models.user import User

    data = await _register_user(client, email=_DEP_EMAIL)
    user_id = data["user"]["id"]
    token = data["access_token"]

    resp = await client.delete(f"/api/v1/users/{user_id}", headers=_bearer(token))
    assert resp.status_code == 204

    user = (
        await db_session.execute(select(User).where(User.id == uuid.UUID(user_id)))
    ).scalar_one()
    assert user.is_active is False
    assert user.api_key is None
    # Email is replaced by an anonymized address; the original must not survive.
    assert user.email != _DEP_EMAIL
    assert user.email.startswith(f"deleted-{user_id}@deactivated.local")

    # Historical audit entries written under this identity are scrubbed.
    audits = (
        (await db_session.execute(select(AuditLog).where(AuditLog.actor_id == str(user.id))))
        .scalars()
        .all()
    )
    assert audits, "expected at least the registration audit entry"
    for entry in audits:
        if entry.action != "user_deactivated":
            assert entry.actor_email is None, f"{entry.action} kept actor_email"

    # The original identity can no longer authenticate.
    resp = await client.post("/auth/login", json={"email": _DEP_EMAIL, "password": "securepass123"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Group endpoints: additional edge cases
# ---------------------------------------------------------------------------


async def test_get_group_by_id(client: AsyncClient):
    """GET /groups/{id} returns the group."""
    data = await _register_user(client, email=_DEP_EMAIL)
    headers = _bearer(data["access_token"])

    create_resp = await client.post(
        "/api/v1/groups",
        json={"name": "lookup-group", "description": "For lookup test"},
        headers=headers,
    )
    assert create_resp.status_code == 201
    group_id = create_resp.json()["id"]

    resp = await client.get(f"/api/v1/groups/{group_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "lookup-group"
    assert resp.json()["description"] == "For lookup test"


async def test_get_group_not_found(client: AsyncClient):
    """GET /groups/{id} for non-existent UUID returns 404."""
    data = await _register_user(client, email=_DEP_EMAIL)
    fake_id = str(uuid.uuid4())

    resp = await client.get(
        f"/api/v1/groups/{fake_id}",
        headers=_bearer(data["access_token"]),
    )
    assert resp.status_code == 404


async def test_update_group_description(client: AsyncClient):
    """PUT /groups/{id} updates the description."""
    data = await _register_user(client, email=_DEP_EMAIL)
    headers = _bearer(data["access_token"])

    create_resp = await client.post(
        "/api/v1/groups",
        json={"name": "updatable-group"},
        headers=headers,
    )
    assert create_resp.status_code == 201
    group_id = create_resp.json()["id"]

    resp = await client.put(
        f"/api/v1/groups/{group_id}",
        json={"description": "Updated description"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["description"] == "Updated description"


async def test_update_group_not_found(client: AsyncClient):
    """PUT /groups/{id} for non-existent group returns 404."""
    data = await _register_user(client, email=_DEP_EMAIL)
    fake_id = str(uuid.uuid4())

    resp = await client.put(
        f"/api/v1/groups/{fake_id}",
        json={"description": "No such group"},
        headers=_bearer(data["access_token"]),
    )
    assert resp.status_code == 404


async def test_delete_group(client: AsyncClient):
    """DELETE /groups/{id} removes the group."""
    data = await _register_user(client, email=_DEP_EMAIL)
    headers = _bearer(data["access_token"])

    create_resp = await client.post(
        "/api/v1/groups",
        json={"name": "deletable-group"},
        headers=headers,
    )
    assert create_resp.status_code == 201
    group_id = create_resp.json()["id"]

    # Delete
    resp = await client.delete(f"/api/v1/groups/{group_id}", headers=headers)
    assert resp.status_code == 204

    # Verify it is gone
    resp = await client.get(f"/api/v1/groups/{group_id}", headers=headers)
    assert resp.status_code == 404


async def test_delete_group_idempotent(client: AsyncClient):
    """DELETE /groups/{id} for non-existent group returns 204 (idempotent)."""
    data = await _register_user(client, email=_DEP_EMAIL)
    fake_id = str(uuid.uuid4())

    resp = await client.delete(
        f"/api/v1/groups/{fake_id}",
        headers=_bearer(data["access_token"]),
    )
    assert resp.status_code == 204


async def test_groups_require_auth(client: AsyncClient):
    """Group endpoints require authentication."""
    resp = await client.get("/api/v1/groups")
    assert resp.status_code == 401


async def test_add_member_invalid_user_id_format(client: AsyncClient):
    """POST /groups/{id}/members with invalid user_id format returns 422."""
    data = await _register_user(client, email=_DEP_EMAIL)
    headers = _bearer(data["access_token"])

    create_resp = await client.post(
        "/api/v1/groups",
        json={"name": "format-test-group"},
        headers=headers,
    )
    assert create_resp.status_code == 201
    group_id = create_resp.json()["id"]

    resp = await client.post(
        f"/api/v1/groups/{group_id}/members",
        json={"user_id": "not-a-uuid"},
        headers=headers,
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# User list pagination
# ---------------------------------------------------------------------------


async def test_list_users_pagination(client: AsyncClient):
    """GET /users with multiple users paginates correctly."""
    user1 = await _register_user(client, email="page1@test.com", display_name="Page One")
    await _register_user(client, email="page2@test.com", display_name="Page Two")
    await _register_user(client, email="page3@test.com", display_name="Page Three")

    headers = _bearer(user1["access_token"])

    resp = await client.get("/api/v1/users?limit=2&offset=0", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["total"] == 3
    assert data["has_more"] is True

    resp = await client.get("/api/v1/users?limit=2&offset=2", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["total"] == 3
    assert data["has_more"] is False
