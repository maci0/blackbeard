"""Tests for the RBAC authentication and authorization system.

Covers: user registration, login, JWT tokens, refresh flow, user/group CRUD,
Role and RoleBinding resource kinds, and the Authorizer engine.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import API_KEY_HEADER

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register_payload(
    email: str = "test@example.com",
    password: str = "securepass123",
    display_name: str = "Test User",
) -> dict:
    return {"email": email, "password": password, "display_name": display_name}


def _login_payload(
    email: str = "test@example.com",
    password: str = "securepass123",
) -> dict:
    return {"email": email, "password": password}


async def _register_user(
    client: AsyncClient,
    email: str = "test@example.com",
    password: str = "securepass123",
    display_name: str = "Test User",
) -> dict:
    """Register a user and return the response data."""
    resp = await client.post(
        "/api/v1/auth/register",
        json=_register_payload(email, password, display_name),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Auth endpoint availability (no API key required)
# ---------------------------------------------------------------------------


async def test_register_does_not_require_api_key(client: AsyncClient):
    """Auth endpoints should be accessible without X-API-Key."""
    resp = await client.post(
        "/api/v1/auth/register",
        json=_register_payload(),
    )
    # Should succeed (201) not fail with 401
    assert resp.status_code == 201


async def test_login_does_not_require_api_key(client: AsyncClient):
    """Login endpoint should be accessible without X-API-Key."""
    await _register_user(client)
    resp = await client.post(
        "/api/v1/auth/login",
        json=_login_payload(),
    )
    assert resp.status_code == 200


async def test_refresh_does_not_require_api_key(client: AsyncClient):
    """Refresh endpoint should be accessible without X-API-Key."""
    data = await _register_user(client)
    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": data["refresh_token"]},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


async def test_register_success(client: AsyncClient):
    """Successful registration returns user, access_token, and refresh_token."""
    data = await _register_user(client)
    assert "access_token" in data
    assert "refresh_token" in data
    assert isinstance(data["access_token"], str), "access_token must be a string"
    assert len(data["access_token"]) > 0, "access_token must be non-empty"
    assert isinstance(data["refresh_token"], str), "refresh_token must be a string"
    assert len(data["refresh_token"]) > 0, "refresh_token must be non-empty"
    assert data["access_token"] != data["refresh_token"], "Access and refresh tokens must differ"
    user = data["user"]
    assert user["email"] == "test@example.com"
    assert user["display_name"] == "Test User"
    assert user["is_active"] is True
    assert "id" in user, "User response should include an id"


async def test_register_duplicate_email(client: AsyncClient):
    """Registering the same email twice returns 409."""
    await _register_user(client)
    resp = await client.post(
        "/api/v1/auth/register",
        json=_register_payload(),
    )
    assert resp.status_code == 409
    detail = resp.json()["detail"].lower()
    assert "registration" in detail or "email" in detail or "exists" in detail


async def test_register_short_password(client: AsyncClient):
    """Password shorter than 8 chars should be rejected."""
    resp = await client.post(
        "/api/v1/auth/register",
        json=_register_payload(password="short"),
    )
    assert resp.status_code == 422
    detail_str = str(resp.json()["detail"]).lower()
    assert "password" in detail_str or "short" in detail_str or "8" in detail_str


async def test_register_invalid_email(client: AsyncClient):
    """Invalid email format should be rejected."""
    resp = await client.post(
        "/api/v1/auth/register",
        json=_register_payload(email="not-an-email"),
    )
    assert resp.status_code == 422
    detail_str = str(resp.json()["detail"]).lower()
    assert "email" in detail_str or "valid" in detail_str


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


async def test_login_success(client: AsyncClient):
    """Successful login returns tokens and user profile."""
    await _register_user(client)
    resp = await client.post(
        "/api/v1/auth/login",
        json=_login_payload(),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert isinstance(data["access_token"], str)
    assert len(data["access_token"]) > 0
    assert isinstance(data["refresh_token"], str)
    assert len(data["refresh_token"]) > 0
    assert data["user"]["email"] == "test@example.com"
    assert "id" in data["user"], "Login response user should include an id"
    assert data["user"]["is_active"] is True


async def test_login_wrong_password(client: AsyncClient):
    """Wrong password returns 401."""
    await _register_user(client)
    resp = await client.post(
        "/api/v1/auth/login",
        json=_login_payload(password="wrongpassword"),
    )
    assert resp.status_code == 401
    assert "invalid" in resp.json()["detail"].lower()


async def test_login_nonexistent_email(client: AsyncClient):
    """Login with non-existent email returns 401."""
    resp = await client.post(
        "/api/v1/auth/login",
        json=_login_payload(email="noone@nowhere.com"),
    )
    assert resp.status_code == 401
    assert "invalid" in resp.json()["detail"].lower()


async def test_login_deactivated_user(client: AsyncClient):
    """Deactivated user cannot login."""
    data = await _register_user(client)
    user_id = data["user"]["id"]
    token = data["access_token"]

    # Deactivate the user
    resp = await client.delete(
        f"/api/v1/users/{user_id}",
        headers=_bearer(token),
    )
    assert resp.status_code == 204

    # Try to login
    resp = await client.post(
        "/api/v1/auth/login",
        json=_login_payload(),
    )
    assert resp.status_code == 401
    detail = resp.json()["detail"]
    assert detail == "Invalid email or password", (
        f"Deactivated account login must return same error as invalid credentials "
        f"to prevent account state enumeration, got: {detail!r}"
    )


# ---------------------------------------------------------------------------
# Token refresh
# ---------------------------------------------------------------------------


async def test_refresh_success(client: AsyncClient):
    """Refresh token exchange returns a new access token."""
    data = await _register_user(client)
    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": data["refresh_token"]},
    )
    assert resp.status_code == 200
    refresh_data = resp.json()
    assert "access_token" in refresh_data
    assert isinstance(refresh_data["access_token"], str), "access_token must be a string"
    assert len(refresh_data["access_token"]) > 0, "access_token must be non-empty"
    assert refresh_data["access_token"] != data["refresh_token"], (
        "Refreshed access token should differ from the refresh token used"
    )
    assert refresh_data["token_type"] == "bearer"


async def test_refresh_with_access_token_fails(client: AsyncClient):
    """Using an access token as refresh token should fail."""
    data = await _register_user(client)
    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": data["access_token"]},
    )
    assert resp.status_code == 401
    assert "type" in resp.json()["detail"].lower()


async def test_refresh_with_invalid_token(client: AsyncClient):
    """Invalid refresh token returns 401."""
    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "invalid-token-string"},
    )
    assert resp.status_code == 401
    detail = resp.json().get("detail", "")
    assert "invalid" in detail.lower() or "token" in detail.lower(), (
        f"Expected error about invalid token, got: {detail!r}"
    )


# ---------------------------------------------------------------------------
# /auth/me — profile endpoint
# ---------------------------------------------------------------------------


async def test_me_with_jwt(client: AsyncClient):
    """GET /auth/me with valid JWT returns user profile."""
    data = await _register_user(client)
    resp = await client.get(
        "/api/v1/auth/me",
        headers=_bearer(data["access_token"]),
    )
    assert resp.status_code == 200
    assert resp.json()["email"] == "test@example.com"


async def test_me_without_auth(client: AsyncClient):
    """GET /auth/me without any auth returns 401."""
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


async def test_me_with_invalid_jwt(client: AsyncClient):
    """GET /auth/me with invalid JWT returns 401."""
    resp = await client.get(
        "/api/v1/auth/me",
        headers=_bearer("invalid.jwt.token"),
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# JWT auth for existing API endpoints
# ---------------------------------------------------------------------------


async def test_jwt_auth_on_resource_endpoints(client: AsyncClient):
    """JWT Bearer token should work for resource endpoints (middleware pass-through)."""
    data = await _register_user(client)
    resp = await client.get(
        "/api/v1/agents",
        headers=_bearer(data["access_token"]),
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------


async def test_list_users(client: AsyncClient):
    """List users endpoint returns registered users."""
    data = await _register_user(client)
    resp = await client.get("/api/v1/users", headers=_bearer(data["access_token"]))
    assert resp.status_code == 200
    users = resp.json()
    assert users["total"] == 1, f"Expected exactly 1 user, got {users['total']}"
    assert users["items"][0]["email"] == "test@example.com"


async def test_list_users_requires_auth(client: AsyncClient):
    """List users without auth should fail."""
    resp = await client.get("/api/v1/users")
    assert resp.status_code == 401


async def test_get_user_by_id(client: AsyncClient):
    """Get user by UUID returns the correct user."""
    data = await _register_user(client)
    user_id = data["user"]["id"]
    resp = await client.get(
        f"/api/v1/users/{user_id}",
        headers=_bearer(data["access_token"]),
    )
    assert resp.status_code == 200
    assert resp.json()["email"] == "test@example.com"


async def test_get_nonexistent_user(client: AsyncClient):
    """Get user with non-existent UUID returns 404."""
    data = await _register_user(client)
    fake_id = str(uuid.uuid4())
    resp = await client.get(
        f"/api/v1/users/{fake_id}",
        headers=_bearer(data["access_token"]),
    )
    assert resp.status_code == 404


async def test_update_user(client: AsyncClient):
    """Update user display name succeeds."""
    data = await _register_user(client)
    user_id = data["user"]["id"]
    resp = await client.put(
        f"/api/v1/users/{user_id}",
        json={"display_name": "New Name"},
        headers=_bearer(data["access_token"]),
    )
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "New Name"


async def test_deactivate_user(client: AsyncClient):
    """DELETE /users/{id} deactivates the user (self-only soft delete)."""
    data = await _register_user(client)
    user_id = data["user"]["id"]
    token = data["access_token"]

    resp = await client.delete(
        f"/api/v1/users/{user_id}",
        headers=_bearer(token),
    )
    assert resp.status_code == 204


async def test_deactivate_other_user_forbidden(client: AsyncClient):
    """Users cannot deactivate other users."""
    data = await _register_user(client)
    other_data = await _register_user(client, email="other@test.com", display_name="Other")
    other_id = other_data["user"]["id"]
    token = data["access_token"]

    resp = await client.delete(
        f"/api/v1/users/{other_id}",
        headers=_bearer(token),
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Group CRUD
# ---------------------------------------------------------------------------


async def test_create_group(client: AsyncClient):
    """Create a group."""
    data = await _register_user(client)
    resp = await client.post(
        "/api/v1/groups",
        json={"name": "developers", "description": "Dev team"},
        headers=_bearer(data["access_token"]),
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "developers"


async def test_create_duplicate_group(client: AsyncClient):
    """Duplicate group name returns 409."""
    data = await _register_user(client)
    headers = _bearer(data["access_token"])
    resp = await client.post(
        "/api/v1/groups",
        json={"name": "team-a"},
        headers=headers,
    )
    assert resp.status_code == 201
    resp = await client.post(
        "/api/v1/groups",
        json={"name": "team-a"},
        headers=headers,
    )
    assert resp.status_code == 409


async def test_list_groups(client: AsyncClient):
    """List groups returns created groups."""
    data = await _register_user(client)
    headers = _bearer(data["access_token"])
    r1 = await client.post("/api/v1/groups", json={"name": "alpha"}, headers=headers)
    assert r1.status_code == 201, f"Group alpha setup failed: {r1.status_code} {r1.text}"
    r2 = await client.post("/api/v1/groups", json={"name": "beta"}, headers=headers)
    assert r2.status_code == 201, f"Group beta setup failed: {r2.status_code} {r2.text}"

    resp = await client.get("/api/v1/groups", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 2


async def test_group_name_validation(client: AsyncClient):
    """Group name must match the resource name pattern."""
    data = await _register_user(client)
    resp = await client.post(
        "/api/v1/groups",
        json={"name": "INVALID_NAME"},
        headers=_bearer(data["access_token"]),
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Group Member Management
# ---------------------------------------------------------------------------


async def test_list_group_members_empty(client: AsyncClient):
    """Listing members of a group with no members returns empty list."""
    data = await _register_user(client)
    headers = _bearer(data["access_token"])
    group_resp = await client.post("/api/v1/groups", json={"name": "empty-group"}, headers=headers)
    assert group_resp.status_code == 201
    group_id = group_resp.json()["id"]

    resp = await client.get(f"/api/v1/groups/{group_id}/members", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0


async def test_add_and_list_group_member(client: AsyncClient):
    """Adding a user to a group and listing members returns that user."""
    data = await _register_user(client)
    headers = _bearer(data["access_token"])
    user_id = data["user"]["id"]

    group_resp = await client.post("/api/v1/groups", json={"name": "dev-team"}, headers=headers)
    assert group_resp.status_code == 201
    group_id = group_resp.json()["id"]

    # Add the user to the group
    add_resp = await client.post(
        f"/api/v1/groups/{group_id}/members",
        json={"user_id": user_id},
        headers=headers,
    )
    assert add_resp.status_code == 201
    add_body = add_resp.json()
    assert add_body["user_id"] == user_id
    assert add_body["status"] == "added"

    # List members
    list_resp = await client.get(f"/api/v1/groups/{group_id}/members", headers=headers)
    assert list_resp.status_code == 200
    body = list_resp.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == user_id


async def test_add_group_member_duplicate_returns_409(client: AsyncClient):
    """Adding the same user twice returns 409."""
    data = await _register_user(client)
    headers = _bearer(data["access_token"])
    user_id = data["user"]["id"]

    group_resp = await client.post("/api/v1/groups", json={"name": "dup-test"}, headers=headers)
    assert group_resp.status_code == 201
    group_id = group_resp.json()["id"]

    # Add once — success
    resp = await client.post(
        f"/api/v1/groups/{group_id}/members",
        json={"user_id": user_id},
        headers=headers,
    )
    assert resp.status_code == 201

    # Add again — conflict
    resp = await client.post(
        f"/api/v1/groups/{group_id}/members",
        json={"user_id": user_id},
        headers=headers,
    )
    assert resp.status_code == 409


async def test_add_group_member_nonexistent_group(client: AsyncClient):
    """Adding a member to a nonexistent group returns 404."""
    data = await _register_user(client)
    headers = _bearer(data["access_token"])
    fake_group_id = str(uuid.uuid4())

    resp = await client.post(
        f"/api/v1/groups/{fake_group_id}/members",
        json={"user_id": data["user"]["id"]},
        headers=headers,
    )
    assert resp.status_code == 404


async def test_add_group_member_nonexistent_user(client: AsyncClient):
    """Adding a nonexistent user to a group returns 404."""
    data = await _register_user(client)
    headers = _bearer(data["access_token"])

    group_resp = await client.post(
        "/api/v1/groups", json={"name": "no-user-group"}, headers=headers
    )
    assert group_resp.status_code == 201
    group_id = group_resp.json()["id"]

    resp = await client.post(
        f"/api/v1/groups/{group_id}/members",
        json={"user_id": str(uuid.uuid4())},
        headers=headers,
    )
    assert resp.status_code == 404


async def test_remove_group_member(client: AsyncClient):
    """Removing a user from a group returns 204 and member is gone."""
    data = await _register_user(client)
    headers = _bearer(data["access_token"])
    user_id = data["user"]["id"]

    group_resp = await client.post("/api/v1/groups", json={"name": "remove-test"}, headers=headers)
    assert group_resp.status_code == 201
    group_id = group_resp.json()["id"]

    # Add user
    add_resp = await client.post(
        f"/api/v1/groups/{group_id}/members",
        json={"user_id": user_id},
        headers=headers,
    )
    assert add_resp.status_code == 201

    # Remove user
    del_resp = await client.delete(
        f"/api/v1/groups/{group_id}/members/{user_id}",
        headers=headers,
    )
    assert del_resp.status_code == 204

    # Verify member is gone
    list_resp = await client.get(f"/api/v1/groups/{group_id}/members", headers=headers)
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] == 0


async def test_remove_group_member_not_a_member(client: AsyncClient):
    """Removing a user who is not a member returns 204 (idempotent)."""
    data = await _register_user(client)
    headers = _bearer(data["access_token"])

    group_resp = await client.post(
        "/api/v1/groups", json={"name": "not-member-group"}, headers=headers
    )
    assert group_resp.status_code == 201
    group_id = group_resp.json()["id"]

    resp = await client.delete(
        f"/api/v1/groups/{group_id}/members/{data['user']['id']}",
        headers=headers,
    )
    assert resp.status_code == 204


async def test_list_group_members_nonexistent_group(client: AsyncClient):
    """Listing members of a nonexistent group returns 404."""
    data = await _register_user(client)
    headers = _bearer(data["access_token"])
    fake_group_id = str(uuid.uuid4())

    resp = await client.get(f"/api/v1/groups/{fake_group_id}/members", headers=headers)
    assert resp.status_code == 404


async def test_remove_group_member_nonexistent_group(client: AsyncClient):
    """Removing a member from a nonexistent group returns 404."""
    data = await _register_user(client)
    headers = _bearer(data["access_token"])
    fake_group_id = str(uuid.uuid4())

    resp = await client.delete(
        f"/api/v1/groups/{fake_group_id}/members/{data['user']['id']}",
        headers=headers,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Role resource kind
# ---------------------------------------------------------------------------


async def test_create_role_resource(client: AsyncClient):
    """Role resources can be created through the standard resource API."""
    payload = {
        "apiVersion": "blackbeard/v1",
        "kind": "Role",
        "metadata": {"name": "test-viewer"},
        "spec": {
            "description": "Read-only access",
            "rules": [{"resources": ["*"], "verbs": ["get", "list"]}],
        },
    }
    resp = await client.post("/api/v1/roles", json=payload, headers=API_KEY_HEADER)
    assert resp.status_code == 201
    data = resp.json()
    assert data["kind"] == "Role"
    assert data["spec"]["rules"][0]["verbs"] == ["get", "list"]


async def test_create_role_invalid_verb(client: AsyncClient):
    """Role with invalid verb should be rejected."""
    payload = {
        "apiVersion": "blackbeard/v1",
        "kind": "Role",
        "metadata": {"name": "bad-role"},
        "spec": {
            "rules": [{"resources": ["Agent"], "verbs": ["destroy"]}],
        },
    }
    resp = await client.post("/api/v1/roles", json=payload, headers=API_KEY_HEADER)
    assert resp.status_code == 422
    detail_str = str(resp.json()["detail"]).lower()
    assert "destroy" in detail_str or "verb" in detail_str


async def test_create_role_missing_rules(client: AsyncClient):
    """Role without rules should be rejected."""
    payload = {
        "apiVersion": "blackbeard/v1",
        "kind": "Role",
        "metadata": {"name": "empty-role"},
        "spec": {"description": "No rules"},
    }
    resp = await client.post("/api/v1/roles", json=payload, headers=API_KEY_HEADER)
    assert resp.status_code == 422


async def test_list_roles(client: AsyncClient):
    """Roles can be listed through the standard resource API."""
    payload = {
        "apiVersion": "blackbeard/v1",
        "kind": "Role",
        "metadata": {"name": "list-test"},
        "spec": {"rules": [{"resources": ["Agent"], "verbs": ["get"]}]},
    }
    r = await client.post("/api/v1/roles", json=payload, headers=API_KEY_HEADER)
    assert r.status_code == 201, f"Role setup failed: {r.status_code} {r.text}"
    resp = await client.get("/api/v1/roles", headers=API_KEY_HEADER)
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


# ---------------------------------------------------------------------------
# RoleBinding resource kind
# ---------------------------------------------------------------------------


async def test_create_role_binding(client: AsyncClient):
    """RoleBinding resources can be created."""
    # Create role first
    role = {
        "apiVersion": "blackbeard/v1",
        "kind": "Role",
        "metadata": {"name": "binding-test-role"},
        "spec": {"rules": [{"resources": ["Agent"], "verbs": ["get", "list"]}]},
    }
    r = await client.post("/api/v1/roles", json=role, headers=API_KEY_HEADER)
    assert r.status_code == 201, f"Role setup failed: {r.status_code} {r.text}"

    binding = {
        "apiVersion": "blackbeard/v1",
        "kind": "RoleBinding",
        "metadata": {"name": "test-binding"},
        "spec": {
            "role": "ref:roles/binding-test-role",
            "subjects": [{"kind": "User", "name": "test@example.com"}],
        },
    }
    resp = await client.post("/api/v1/role-bindings", json=binding, headers=API_KEY_HEADER)
    assert resp.status_code == 201
    data = resp.json()
    assert data["kind"] == "RoleBinding"
    assert data["spec"]["subjects"][0]["kind"] == "User"


async def test_role_binding_invalid_subject_kind(client: AsyncClient):
    """RoleBinding with invalid subject kind should be rejected."""
    binding = {
        "apiVersion": "blackbeard/v1",
        "kind": "RoleBinding",
        "metadata": {"name": "bad-binding"},
        "spec": {
            "role": "ref:roles/some-role",
            "subjects": [{"kind": "InvalidKind", "name": "test"}],
        },
    }
    resp = await client.post("/api/v1/role-bindings", json=binding, headers=API_KEY_HEADER)
    assert resp.status_code == 422


async def test_role_binding_missing_subjects(client: AsyncClient):
    """RoleBinding without subjects should be rejected."""
    binding = {
        "apiVersion": "blackbeard/v1",
        "kind": "RoleBinding",
        "metadata": {"name": "no-subjects"},
        "spec": {"role": "ref:roles/some-role"},
    }
    resp = await client.post("/api/v1/role-bindings", json=binding, headers=API_KEY_HEADER)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Authorizer engine
# ---------------------------------------------------------------------------


async def test_authorizer_grants_access(client: AsyncClient, db_session: AsyncSession):
    """Authorizer grants access when a matching role+binding exists."""
    from blackbeard.auth.authorizer import Authorizer, clear_cache

    clear_cache()

    # Create a role
    role = {
        "apiVersion": "blackbeard/v1",
        "kind": "Role",
        "metadata": {"name": "auth-test-role"},
        "spec": {"rules": [{"resources": ["Agent"], "verbs": ["get", "list"]}]},
    }
    resp = await client.post("/api/v1/roles", json=role, headers=API_KEY_HEADER)
    assert resp.status_code == 201

    # Create a binding
    binding = {
        "apiVersion": "blackbeard/v1",
        "kind": "RoleBinding",
        "metadata": {"name": "auth-test-binding"},
        "spec": {
            "role": "ref:roles/auth-test-role",
            "subjects": [{"kind": "User", "name": "alice"}],
        },
    }
    resp = await client.post("/api/v1/role-bindings", json=binding, headers=API_KEY_HEADER)
    assert resp.status_code == 201

    authorizer = Authorizer(db_session)
    assert await authorizer.check("User", "alice", "get", "Agent") is True
    assert await authorizer.check("User", "alice", "list", "Agent") is True


async def test_authorizer_denies_unmatched_verb(client: AsyncClient, db_session: AsyncSession):
    """Authorizer denies access for verbs not in the role."""
    from blackbeard.auth.authorizer import Authorizer, clear_cache

    clear_cache()

    role = {
        "apiVersion": "blackbeard/v1",
        "kind": "Role",
        "metadata": {"name": "readonly-role"},
        "spec": {"rules": [{"resources": ["Agent"], "verbs": ["get"]}]},
    }
    r = await client.post("/api/v1/roles", json=role, headers=API_KEY_HEADER)
    assert r.status_code == 201, f"Role setup failed: {r.status_code} {r.text}"

    binding = {
        "apiVersion": "blackbeard/v1",
        "kind": "RoleBinding",
        "metadata": {"name": "readonly-binding"},
        "spec": {
            "role": "ref:roles/readonly-role",
            "subjects": [{"kind": "User", "name": "bob"}],
        },
    }
    r = await client.post("/api/v1/role-bindings", json=binding, headers=API_KEY_HEADER)
    assert r.status_code == 201, f"RoleBinding setup failed: {r.status_code} {r.text}"

    authorizer = Authorizer(db_session)
    assert await authorizer.check("User", "bob", "get", "Agent") is True
    assert await authorizer.check("User", "bob", "delete", "Agent") is False


async def test_authorizer_denies_unbound_user(db_session: AsyncSession):
    """Authorizer denies access for a user with no bindings."""
    from blackbeard.auth.authorizer import Authorizer, clear_cache

    clear_cache()
    authorizer = Authorizer(db_session)
    assert await authorizer.check("User", "nobody", "get", "Agent") is False


async def test_authorizer_wildcard_resources(client: AsyncClient, db_session: AsyncSession):
    """Authorizer handles wildcard '*' in resources field."""
    from blackbeard.auth.authorizer import Authorizer, clear_cache

    clear_cache()

    role = {
        "apiVersion": "blackbeard/v1",
        "kind": "Role",
        "metadata": {"name": "wildcard-role"},
        "spec": {"rules": [{"resources": ["*"], "verbs": ["get"]}]},
    }
    r = await client.post("/api/v1/roles", json=role, headers=API_KEY_HEADER)
    assert r.status_code == 201, f"Role setup failed: {r.status_code} {r.text}"

    binding = {
        "apiVersion": "blackbeard/v1",
        "kind": "RoleBinding",
        "metadata": {"name": "wildcard-binding"},
        "spec": {
            "role": "ref:roles/wildcard-role",
            "subjects": [{"kind": "User", "name": "charlie"}],
        },
    }
    r = await client.post("/api/v1/role-bindings", json=binding, headers=API_KEY_HEADER)
    assert r.status_code == 201, f"RoleBinding setup failed: {r.status_code} {r.text}"

    authorizer = Authorizer(db_session)
    assert await authorizer.check("User", "charlie", "get", "Agent") is True
    assert await authorizer.check("User", "charlie", "get", "Task") is True
    assert await authorizer.check("User", "charlie", "delete", "Agent") is False


async def test_authorizer_wildcard_verbs(client: AsyncClient, db_session: AsyncSession):
    """Authorizer handles wildcard '*' in verbs field."""
    from blackbeard.auth.authorizer import Authorizer, clear_cache

    clear_cache()

    role = {
        "apiVersion": "blackbeard/v1",
        "kind": "Role",
        "metadata": {"name": "all-verbs-role"},
        "spec": {"rules": [{"resources": ["Agent"], "verbs": ["*"]}]},
    }
    r = await client.post("/api/v1/roles", json=role, headers=API_KEY_HEADER)
    assert r.status_code == 201, f"Role setup failed: {r.status_code} {r.text}"

    binding = {
        "apiVersion": "blackbeard/v1",
        "kind": "RoleBinding",
        "metadata": {"name": "all-verbs-binding"},
        "spec": {
            "role": "ref:roles/all-verbs-role",
            "subjects": [{"kind": "User", "name": "dave"}],
        },
    }
    r = await client.post("/api/v1/role-bindings", json=binding, headers=API_KEY_HEADER)
    assert r.status_code == 201, f"RoleBinding setup failed: {r.status_code} {r.text}"

    authorizer = Authorizer(db_session)
    assert await authorizer.check("User", "dave", "get", "Agent") is True
    assert await authorizer.check("User", "dave", "delete", "Agent") is True
    assert await authorizer.check("User", "dave", "run", "Agent") is True
    # Different resource kind should not match
    assert await authorizer.check("User", "dave", "get", "Task") is False


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------


def test_password_hash_and_verify():
    """Password hashing and verification round-trip."""
    from blackbeard.auth.passwords import hash_password, verify_password

    hashed = hash_password("mypassword")
    assert hashed != "mypassword"
    assert len(hashed) >= 50, "Hash should be substantially longer than plaintext"
    assert verify_password("mypassword", hashed) is True
    assert verify_password("wrongpassword", hashed) is False
    hashed2 = hash_password("mypassword")
    assert hashed != hashed2, "Same input should produce different salted hashes"


# ---------------------------------------------------------------------------
# JWT token creation and decoding
# ---------------------------------------------------------------------------


def test_jwt_access_token_roundtrip():
    """Access token can be decoded and contains expected claims."""
    from blackbeard.auth.jwt import create_access_token, decode_token

    token = create_access_token("user-123")
    payload = decode_token(token)
    assert payload["sub"] == "user-123"
    assert "email" not in payload, "Email must not be embedded in JWT tokens"
    assert payload["type"] == "access"
    assert "exp" in payload, "Access token must have an expiration claim"
    assert "iat" in payload, "Access token must have an issued-at claim"


def test_jwt_refresh_token_roundtrip():
    """Refresh token can be decoded and contains expected claims."""
    from blackbeard.auth.jwt import create_refresh_token, decode_token

    token = create_refresh_token("user-456")
    payload = decode_token(token)
    assert payload["sub"] == "user-456"
    assert payload["type"] == "refresh"
    assert "exp" in payload, "Refresh token must have an expiration claim"


def test_jwt_decode_invalid_token():
    """Decoding an invalid token raises an error."""
    import jwt as pyjwt

    from blackbeard.auth.jwt import decode_token

    with pytest.raises(pyjwt.InvalidTokenError):
        decode_token("not-a-valid-jwt")
