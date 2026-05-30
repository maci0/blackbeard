"""Tests for the audit logging system.

Covers: audit log model creation, audit service, API endpoint (list + filters),
and integration tests verifying that key actions produce audit entries.
"""

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from blackbeard.audit import audit_from_request, log_audit
from blackbeard.models.audit import AuditLog
from tests.conftest import (
    API_KEY_HEADER,
    _agent_payload,
    _bearer,
    _login_payload,
    _register_user,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_AUDIT_EMAIL = "audit@example.com"


# ---------------------------------------------------------------------------
# Unit tests: AuditLog model
# ---------------------------------------------------------------------------


async def test_audit_log_creation(db_session: AsyncSession):
    """AuditLog records can be created directly in the database."""
    entry = await log_audit(
        db_session,
        action="test_action",
        actor_type="system",
        actor_id="test-system",
        resource_type="TestResource",
        resource_id="test-123",
        detail={"key": "value"},
        request_id="req-abc",
        ip_address="10.0.0.1",
    )
    await db_session.commit()

    result = await db_session.execute(select(AuditLog).where(AuditLog.id == entry.id))
    saved = result.scalar_one()

    assert saved.action == "test_action"
    assert saved.actor_type == "system"
    assert saved.actor_id == "test-system"
    assert saved.resource_type == "TestResource"
    assert saved.resource_id == "test-123"
    assert saved.detail == {"key": "value"}
    assert saved.request_id == "req-abc"
    assert saved.ip_address == "10.0.0.1"
    assert saved.timestamp is not None


async def test_audit_log_minimal_fields(db_session: AsyncSession):
    """AuditLog works with only required fields."""
    entry = await log_audit(
        db_session,
        action="minimal_action",
    )
    await db_session.commit()

    result = await db_session.execute(select(AuditLog).where(AuditLog.id == entry.id))
    saved = result.scalar_one()

    assert saved.action == "minimal_action"
    assert saved.actor_type == "system"
    assert saved.actor_id == "system"
    assert saved.actor_email is None
    assert saved.resource_type is None
    assert saved.resource_id is None
    assert saved.detail is None


async def test_audit_log_multiple_entries(db_session: AsyncSession):
    """Multiple audit log entries can be created and queried."""
    for i in range(5):
        await log_audit(
            db_session,
            action=f"action_{i}",
            actor_id=f"actor-{i}",
        )
    await db_session.commit()

    result = await db_session.execute(select(AuditLog))
    entries = list(result.scalars().all())
    assert len(entries) == 5


# ---------------------------------------------------------------------------
# Unit tests: audit_from_request helper
# ---------------------------------------------------------------------------


class _FakeClient:
    host = "192.168.1.1"


class _FakeRequest:
    client = _FakeClient()


class _FakeUser:
    id = "user-uuid-123"
    email = "test@example.com"


def test_audit_from_request_with_user():
    """audit_from_request extracts user context correctly."""
    ctx = audit_from_request(_FakeRequest(), _FakeUser())  # type: ignore[arg-type]
    assert ctx["actor_type"] == "user"
    assert ctx["actor_id"] == "user-uuid-123"
    assert ctx["actor_email"] == "test@example.com"
    assert ctx["ip_address"] == "192.168.1.1"


def test_audit_from_request_without_user():
    """audit_from_request handles API key auth (no user)."""
    ctx = audit_from_request(_FakeRequest(), None)  # type: ignore[arg-type]
    assert ctx["actor_type"] == "api_key"
    assert ctx["actor_id"] == "api_key"
    assert ctx["actor_email"] is None
    assert ctx["ip_address"] == "192.168.1.1"


# ---------------------------------------------------------------------------
# API endpoint tests: GET /api/v1/audit-logs
# ---------------------------------------------------------------------------


async def test_audit_logs_endpoint_requires_auth(client: AsyncClient):
    """Audit log endpoint requires authentication."""
    resp = await client.get("/api/v1/audit-logs")
    assert resp.status_code == 401


async def test_audit_logs_endpoint_returns_entries(client: AsyncClient):
    """Audit log endpoint returns entries after actions are performed."""
    data = await _register_user(client, email=_AUDIT_EMAIL)
    token = data["access_token"]

    # Registration itself creates an audit entry; query for it
    resp = await client.get(
        "/api/v1/audit-logs",
        headers=_bearer(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    assert len(body["items"]) >= 1

    # Verify the registration audit entry exists
    actions = [item["action"] for item in body["items"]]
    assert "user_registered" in actions


async def test_audit_logs_filter_by_action(client: AsyncClient):
    """Audit log endpoint filters by action."""
    data = await _register_user(client, email=_AUDIT_EMAIL)
    token = data["access_token"]

    # Login creates a user_login audit entry
    await client.post("/api/v1/auth/login", json=_login_payload(email=_AUDIT_EMAIL))

    resp = await client.get(
        "/api/v1/audit-logs?action=user_login",
        headers=_bearer(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    for item in body["items"]:
        assert item["action"] == "user_login"


async def test_audit_logs_filter_by_actor_id(client: AsyncClient):
    """Audit log endpoint filters by actor_id."""
    data = await _register_user(client, email=_AUDIT_EMAIL)
    token = data["access_token"]
    user_id = data["user"]["id"]

    resp = await client.get(
        f"/api/v1/audit-logs?actor_id={user_id}",
        headers=_bearer(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    for item in body["items"]:
        assert item["actor_id"] == user_id


async def test_audit_logs_filter_by_resource_type(client: AsyncClient):
    """Audit log endpoint filters by resource_type."""
    data = await _register_user(client, email=_AUDIT_EMAIL)
    token = data["access_token"]

    # Create a resource to generate a resource_created audit entry
    await client.post(
        "/api/v1/agents",
        json=_agent_payload("audit-agent"),
        headers=_bearer(token),
    )

    resp = await client.get(
        "/api/v1/audit-logs?resource_type=Agent",
        headers=_bearer(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    for item in body["items"]:
        assert item["resource_type"] == "Agent"


async def test_audit_logs_pagination(client: AsyncClient):
    """Audit log endpoint supports pagination."""
    data = await _register_user(client, email=_AUDIT_EMAIL)
    token = data["access_token"]

    # Create several resources to generate multiple audit entries
    for i in range(5):
        await client.post(
            "/api/v1/agents",
            json=_agent_payload(name=f"agent-{i}"),
            headers=_bearer(token),
        )

    # Request page 1 with limit 2
    resp = await client.get(
        "/api/v1/audit-logs?limit=2&offset=0",
        headers=_bearer(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["limit"] == 2
    assert len(body["items"]) == 2
    assert body["has_more"] is True

    # Request page 2
    resp2 = await client.get(
        "/api/v1/audit-logs?limit=2&offset=2",
        headers=_bearer(token),
    )
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert len(body2["items"]) == 2

    # Entries should be different
    ids_page1 = {item["id"] for item in body["items"]}
    ids_page2 = {item["id"] for item in body2["items"]}
    assert ids_page1.isdisjoint(ids_page2)


async def test_audit_logs_empty_result(client: AsyncClient):
    """Audit log endpoint returns empty list for unmatched filter."""
    data = await _register_user(client, email=_AUDIT_EMAIL)
    token = data["access_token"]

    resp = await client.get(
        "/api/v1/audit-logs?action=nonexistent_action",
        headers=_bearer(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["items"] == []
    assert body["has_more"] is False


# ---------------------------------------------------------------------------
# Integration: auth actions produce audit entries
# ---------------------------------------------------------------------------


async def test_register_creates_audit_entry(client: AsyncClient, db_session: AsyncSession):
    """Registration creates a user_registered audit entry."""
    await _register_user(client, email=_AUDIT_EMAIL)

    result = await db_session.execute(select(AuditLog).where(AuditLog.action == "user_registered"))
    entry = result.scalar_one()
    assert entry.actor_type == "user"
    assert entry.resource_type == "User"
    assert entry.actor_email == "audit@example.com"


async def test_login_creates_audit_entry(client: AsyncClient, db_session: AsyncSession):
    """Successful login creates a user_login audit entry."""
    await _register_user(client, email=_AUDIT_EMAIL)
    await client.post("/api/v1/auth/login", json=_login_payload(email=_AUDIT_EMAIL))

    result = await db_session.execute(select(AuditLog).where(AuditLog.action == "user_login"))
    entry = result.scalar_one()
    assert entry.actor_type == "user"
    assert entry.actor_email == "audit@example.com"


async def test_login_failure_creates_audit_entry(client: AsyncClient, db_session: AsyncSession):
    """Failed login creates a login_failed audit entry."""
    await _register_user(client, email=_AUDIT_EMAIL)
    await client.post(
        "/api/v1/auth/login",
        json=_login_payload(password="wrongpassword1"),
    )

    result = await db_session.execute(select(AuditLog).where(AuditLog.action == "login_failed"))
    entry = result.scalar_one()
    assert entry.actor_type == "user"
    assert entry.detail is not None
    assert entry.detail["reason"] == "invalid_credentials"


# ---------------------------------------------------------------------------
# Integration: resource actions produce audit entries
# ---------------------------------------------------------------------------


async def test_create_resource_creates_audit_entry(client: AsyncClient, db_session: AsyncSession):
    """Creating a resource creates a resource_created audit entry."""
    resp = await client.post(
        "/api/v1/agents",
        json=_agent_payload("audit-agent"),
        headers=API_KEY_HEADER,
    )
    assert resp.status_code == 201

    result = await db_session.execute(select(AuditLog).where(AuditLog.action == "resource_created"))
    entry = result.scalar_one()
    assert entry.resource_type == "Agent"
    assert entry.resource_id == "audit-agent"


async def test_update_resource_creates_audit_entry(client: AsyncClient, db_session: AsyncSession):
    """Updating a resource creates a resource_updated audit entry."""
    await client.post(
        "/api/v1/agents",
        json=_agent_payload("audit-agent"),
        headers=API_KEY_HEADER,
    )
    update_data = {
        "spec": {
            "role": "Updated Role",
            "goal": "Updated goal",
            "backstory": "Updated backstory",
        },
        "version": 1,
    }
    resp = await client.put(
        "/api/v1/agents/audit-agent",
        json=update_data,
        headers=API_KEY_HEADER,
    )
    assert resp.status_code == 200

    result = await db_session.execute(select(AuditLog).where(AuditLog.action == "resource_updated"))
    entries = list(result.scalars().all())
    assert len(entries) >= 1
    assert any(e.resource_id == "audit-agent" for e in entries)


async def test_delete_resource_creates_audit_entry(client: AsyncClient, db_session: AsyncSession):
    """Deleting a resource creates a resource_deleted audit entry."""
    await client.post(
        "/api/v1/agents",
        json=_agent_payload("audit-agent"),
        headers=API_KEY_HEADER,
    )
    resp = await client.delete(
        "/api/v1/agents/audit-agent",
        headers=API_KEY_HEADER,
    )
    assert resp.status_code == 204

    result = await db_session.execute(select(AuditLog).where(AuditLog.action == "resource_deleted"))
    entry = result.scalar_one()
    assert entry.resource_type == "Agent"
    assert entry.resource_id == "audit-agent"


# ---------------------------------------------------------------------------
# Integration: user actions produce audit entries
# ---------------------------------------------------------------------------


async def test_deactivate_user_creates_audit_entry(client: AsyncClient, db_session: AsyncSession):
    """Deactivating a user creates a user_deactivated audit entry."""
    data = await _register_user(client, email=_AUDIT_EMAIL)
    user_id = data["user"]["id"]
    token = data["access_token"]

    resp = await client.delete(
        f"/api/v1/users/{user_id}",
        headers=_bearer(token),
    )
    assert resp.status_code == 204

    result = await db_session.execute(select(AuditLog).where(AuditLog.action == "user_deactivated"))
    entry = result.scalar_one()
    assert entry.resource_type == "User"
    assert entry.resource_id == user_id


# ---------------------------------------------------------------------------
# Integration: group actions produce audit entries
# ---------------------------------------------------------------------------


async def test_create_group_creates_audit_entry(client: AsyncClient, db_session: AsyncSession):
    """Creating a group creates a group_created audit entry."""
    data = await _register_user(client, email=_AUDIT_EMAIL)
    token = data["access_token"]

    resp = await client.post(
        "/api/v1/groups",
        json={"name": "audit-test-group", "description": "Test group"},
        headers=_bearer(token),
    )
    assert resp.status_code == 201

    result = await db_session.execute(select(AuditLog).where(AuditLog.action == "group_created"))
    entry = result.scalar_one()
    assert entry.resource_type == "Group"
    assert entry.resource_id == "audit-test-group"


async def test_delete_group_creates_audit_entry(client: AsyncClient, db_session: AsyncSession):
    """Deleting a group creates a group_deleted audit entry."""
    data = await _register_user(client, email=_AUDIT_EMAIL)
    token = data["access_token"]

    resp = await client.post(
        "/api/v1/groups",
        json={"name": "to-delete-group"},
        headers=_bearer(token),
    )
    assert resp.status_code == 201
    group_id = resp.json()["id"]

    resp = await client.delete(
        f"/api/v1/groups/{group_id}",
        headers=_bearer(token),
    )
    assert resp.status_code == 204

    result = await db_session.execute(select(AuditLog).where(AuditLog.action == "group_deleted"))
    entry = result.scalar_one()
    assert entry.resource_type == "Group"
    assert entry.resource_id == "to-delete-group"


# ---------------------------------------------------------------------------
# Integration: upsert (create via POST with same name) produces resource_updated
# ---------------------------------------------------------------------------


async def test_upsert_resource_creates_updated_audit_entry(
    client: AsyncClient, db_session: AsyncSession
):
    """Upserting a resource (POST with existing name) logs resource_updated."""
    resp1 = await client.post(
        "/api/v1/agents",
        json=_agent_payload(name="upsert-agent"),
        headers=API_KEY_HEADER,
    )
    assert resp1.status_code == 201

    # Upsert: POST again with same name
    resp2 = await client.post(
        "/api/v1/agents",
        json=_agent_payload(name="upsert-agent"),
        headers=API_KEY_HEADER,
    )
    assert resp2.status_code == 200  # 200 = upsert

    result = await db_session.execute(
        select(AuditLog).where(
            AuditLog.resource_id == "upsert-agent",
        )
    )
    entries = list(result.scalars().all())
    actions = [e.action for e in entries]
    assert "resource_created" in actions
    assert "resource_updated" in actions
