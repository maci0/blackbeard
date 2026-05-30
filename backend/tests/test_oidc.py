"""Tests for OIDC / SSO endpoints."""

from __future__ import annotations

from httpx import AsyncClient


async def test_public_config_returns_oidc_disabled(client: AsyncClient):
    resp = await client.get("/api/v1/config/public")
    assert resp.status_code == 200
    assert resp.json()["oidc_enabled"] is False


async def test_public_config_no_auth_required(client: AsyncClient):
    resp = await client.get("/api/v1/config/public")
    assert resp.status_code == 200
    data = resp.json()
    assert "oidc_enabled" in data, "Public config must include oidc_enabled field"


async def test_oidc_user_cannot_login_with_password(client: AsyncClient, db_session):
    from blackbeard.api.oidc import _find_or_create_user

    user, created = await _find_or_create_user(db_session, "sso@example.com", {"name": "SSO User"})
    assert created is True
    assert user.password_hash is not None, "OIDC user should have an unusable password hash"

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "sso@example.com", "password": "anything"},
    )
    assert resp.status_code == 401


async def test_find_or_create_user_creates_new(db_session):
    from blackbeard.api.oidc import _find_or_create_user

    user, created = await _find_or_create_user(
        db_session, "new@example.com", {"name": "New User", "email": "new@example.com"}
    )
    assert created is True
    assert user.email == "new@example.com"
    assert user.display_name == "New User"
    assert user.is_active is True


async def test_find_or_create_user_links_existing(db_session):
    from blackbeard.api.oidc import _find_or_create_user

    user1, created1 = await _find_or_create_user(db_session, "existing@example.com", {"name": "First"})
    user2, created2 = await _find_or_create_user(db_session, "existing@example.com", {"name": "Second"})
    assert created1 is True
    assert created2 is False
    assert user1.id == user2.id
    assert user2.last_login_at is not None


async def test_find_or_create_user_fallback_display_name(db_session):
    from blackbeard.api.oidc import _find_or_create_user

    user, created = await _find_or_create_user(db_session, "noname@example.com", {})
    assert created is True
    assert user.display_name == "noname"
