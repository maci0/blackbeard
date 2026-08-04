"""Tests for OIDC / SSO endpoints.

Covers the full OIDC flow: login redirect, callback token exchange, user
creation and linking, error handling, and the public config endpoint.

All OIDC provider HTTP calls are mocked via unittest.mock patches on the
authlib OAuth client, so no external services are needed.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from blackbeard.models.database import get_session

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_USERINFO_VERIFIED = {
    "email": "oidc-user@example.com",
    "email_verified": True,
    "name": "Jane Doe",
    "preferred_username": "janedoe",
    "sub": "provider-sub-12345",
}


def _make_oidc_token(userinfo: dict | None = None) -> dict:
    """Build a fake OIDC token response dict with embedded userinfo."""
    return {
        "access_token": "fake-access-token",
        "token_type": "bearer",
        "id_token": "fake-id-token",
        "userinfo": userinfo or _USERINFO_VERIFIED,
    }


def _mock_oauth_provider(
    *,
    token_response: dict | None = None,
    token_side_effect: Exception | None = None,
    userinfo_response: dict | None = None,
) -> MagicMock:
    """Create a mock authlib OAuth provider with configurable behavior.

    The mock replicates the two methods used by the OIDC callback:
    ``authorize_access_token`` and ``authorize_redirect``.
    """
    provider = MagicMock()

    # authorize_redirect returns a RedirectResponse-like object
    redirect = MagicMock()
    redirect.status_code = 302
    redirect.headers = {"location": "https://provider.example.com/authorize?state=abc123"}
    provider.authorize_redirect = AsyncMock(return_value=redirect)

    # authorize_access_token returns the token dict or raises
    if token_side_effect:
        provider.authorize_access_token = AsyncMock(side_effect=token_side_effect)
    else:
        provider.authorize_access_token = AsyncMock(
            return_value=token_response or _make_oidc_token()
        )

    # userinfo fallback (used when token dict has no userinfo key)
    provider.userinfo = AsyncMock(return_value=userinfo_response or {})

    return provider


def _build_mock_oauth(provider: MagicMock) -> MagicMock:
    """Wrap a mock provider in a mock OAuth object matching authlib's API."""
    oauth = MagicMock()
    oauth.provider = provider
    return oauth


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def oidc_client(db_session: AsyncSession):
    """HTTP test client with OIDC enabled via patched settings.

    The OIDC router is registered conditionally in main.py, but here we
    directly import and include it so that tests can exercise the endpoints
    without requiring the env var to be set at import time.  We also add
    session middleware (required by authlib's state parameter handling).
    """
    from fastapi import FastAPI
    from starlette.middleware.cors import CORSMiddleware
    from starlette.middleware.sessions import SessionMiddleware

    from blackbeard.api.oidc import router as oidc_router

    test_app = FastAPI()
    test_app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    test_app.add_middleware(
        SessionMiddleware,
        secret_key="test-session-secret",
        https_only=False,
        same_site="lax",
        max_age=600,
    )

    # Mount the OIDC router and health router (for /config/public)
    from blackbeard.api.health import router as health_router

    test_app.include_router(oidc_router, prefix="/api/v1")
    test_app.include_router(health_router, prefix="/api/v1")

    async def override_get_session():
        yield db_session

    test_app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=test_app)
    async with AsyncClient(
        transport=transport,
        base_url="http://localhost:3000",
        follow_redirects=False,
    ) as ac:
        yield ac

    test_app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Public config endpoint
# ---------------------------------------------------------------------------


class TestPublicConfig:
    """GET /api/v1/config/public."""

    async def test_returns_oidc_disabled_when_no_issuer(self, client: AsyncClient):
        """Without OIDC_ISSUER set, the flag should be False."""
        resp = await client.get("/api/v1/config/public")
        assert resp.status_code == 200
        assert resp.json()["oidc_enabled"] is False

    async def test_returns_oidc_enabled_when_issuer_set(self, oidc_client: AsyncClient):
        """With OIDC_ISSUER set, the flag should be True."""
        with patch("blackbeard.api.health.settings") as mock_settings:
            mock_settings.oidc_issuer = "https://provider.example.com"
            resp = await oidc_client.get("/api/v1/config/public")
            assert resp.status_code == 200
            assert resp.json()["oidc_enabled"] is True

    async def test_no_auth_required(self, client: AsyncClient):
        """The public config endpoint must not require auth headers."""
        resp = await client.get("/api/v1/config/public")
        assert resp.status_code == 200
        data = resp.json()
        assert "oidc_enabled" in data


# ---------------------------------------------------------------------------
# OIDC disabled (no issuer configured)
# ---------------------------------------------------------------------------


class TestOidcDisabled:
    """Endpoints should reject requests when OIDC is not configured."""

    async def test_login_returns_501_when_not_configured(self, oidc_client: AsyncClient):
        """GET /auth/oidc/login should return 501 when OIDC_ISSUER is empty."""
        import blackbeard.api.oidc as oidc_mod

        # Reset the cached OAuth instance so _ensure_oauth re-checks settings
        original = oidc_mod._oauth
        oidc_mod._oauth = None
        try:
            with patch.object(oidc_mod, "settings") as mock_settings:
                mock_settings.oidc_issuer = None
                resp = await oidc_client.get("/api/v1/auth/oidc/login")
                assert resp.status_code == 501
                assert "not configured" in resp.json()["detail"].lower()
        finally:
            oidc_mod._oauth = original

    async def test_callback_returns_501_when_not_configured(self, oidc_client: AsyncClient):
        """GET /auth/oidc/callback should return 501 when OIDC_ISSUER is empty."""
        import blackbeard.api.oidc as oidc_mod

        original = oidc_mod._oauth
        oidc_mod._oauth = None
        try:
            with patch.object(oidc_mod, "settings") as mock_settings:
                mock_settings.oidc_issuer = None
                resp = await oidc_client.get("/api/v1/auth/oidc/callback?code=abc&state=xyz")
                assert resp.status_code == 501
        finally:
            oidc_mod._oauth = original


# ---------------------------------------------------------------------------
# OIDC login redirect
# ---------------------------------------------------------------------------


class TestOidcLogin:
    """GET /api/v1/auth/oidc/login."""

    async def test_redirects_to_provider(self, oidc_client: AsyncClient):
        """Should call authorize_redirect with the configured redirect_uri."""
        provider = _mock_oauth_provider()
        oauth = _build_mock_oauth(provider)

        with (
            patch("blackbeard.api.oidc._oauth", oauth),
            patch("blackbeard.api.oidc.settings") as mock_settings,
        ):
            mock_settings.oidc_redirect_uri = "http://localhost:3000/api/v1/auth/oidc/callback"
            await oidc_client.get("/api/v1/auth/oidc/login")

        # The endpoint returns the RedirectResponse from authorize_redirect,
        # called with the configured redirect_uri (not an attacker-influenced one).
        provider.authorize_redirect.assert_awaited_once()
        _, redirect_uri = provider.authorize_redirect.call_args.args
        assert redirect_uri == "http://localhost:3000/api/v1/auth/oidc/callback"


# ---------------------------------------------------------------------------
# OIDC callback: successful flows
# ---------------------------------------------------------------------------


class TestOidcCallbackSuccess:
    """GET /api/v1/auth/oidc/callback with valid token exchange."""

    async def test_creates_new_user_on_first_login(
        self, oidc_client: AsyncClient, db_session: AsyncSession
    ):
        """First OIDC login should create a new user and return tokens."""
        provider = _mock_oauth_provider()
        oauth = _build_mock_oauth(provider)

        with (
            patch("blackbeard.api.oidc._oauth", oauth),
            patch("blackbeard.api.oidc.settings") as mock_settings,
        ):
            mock_settings.oidc_redirect_uri = "http://localhost:3000/api/v1/auth/oidc/callback"
            mock_settings.cors_origins = ["http://localhost:3000"]
            resp = await oidc_client.get("/api/v1/auth/oidc/callback?code=valid&state=abc")

        # Should redirect to frontend with token fragment
        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "token=" in location
        assert "refresh=" in location
        assert location.startswith("http://localhost:3000/#")

        # Verify user was created in the database
        from sqlalchemy import select

        from blackbeard.models import User

        result = await db_session.execute(
            select(User).where(User.email == "oidc-user@example.com")
        )
        user = result.scalar_one_or_none()
        assert user is not None
        assert user.display_name == "Jane Doe"
        assert user.is_active is True

    async def test_returns_existing_user_on_subsequent_login(
        self, oidc_client: AsyncClient, db_session: AsyncSession
    ):
        """Second OIDC login should reuse the existing user, not create a duplicate."""
        provider = _mock_oauth_provider()
        oauth = _build_mock_oauth(provider)

        # First login: create user
        with patch("blackbeard.api.oidc._oauth", oauth), patch(
            "blackbeard.api.oidc.settings"
        ) as mock_settings:
            mock_settings.oidc_redirect_uri = "http://localhost:3000/api/v1/auth/oidc/callback"
            mock_settings.cors_origins = ["http://localhost:3000"]
            resp1 = await oidc_client.get("/api/v1/auth/oidc/callback?code=valid&state=abc")
        assert resp1.status_code == 303

        # Second login: same email
        with patch("blackbeard.api.oidc._oauth", oauth), patch(
            "blackbeard.api.oidc.settings"
        ) as mock_settings:
            mock_settings.oidc_redirect_uri = "http://localhost:3000/api/v1/auth/oidc/callback"
            mock_settings.cors_origins = ["http://localhost:3000"]
            resp2 = await oidc_client.get("/api/v1/auth/oidc/callback?code=valid&state=def")
        assert resp2.status_code == 303

        # Only one user should exist
        from sqlalchemy import func, select

        from blackbeard.models import User

        result = await db_session.execute(
            select(func.count()).select_from(User).where(User.email == "oidc-user@example.com")
        )
        count = result.scalar()
        assert count == 1

    async def test_updates_last_login_on_existing_user(
        self, oidc_client: AsyncClient, db_session: AsyncSession
    ):
        """Returning user should get their last_login_at timestamp updated."""
        provider = _mock_oauth_provider()
        oauth = _build_mock_oauth(provider)

        # First login
        with patch("blackbeard.api.oidc._oauth", oauth), patch(
            "blackbeard.api.oidc.settings"
        ) as mock_settings:
            mock_settings.oidc_redirect_uri = "http://localhost:3000/api/v1/auth/oidc/callback"
            mock_settings.cors_origins = ["http://localhost:3000"]
            await oidc_client.get("/api/v1/auth/oidc/callback?code=valid&state=abc")

        from sqlalchemy import select

        from blackbeard.models import User

        result = await db_session.execute(
            select(User).where(User.email == "oidc-user@example.com")
        )
        user = result.scalar_one()
        first_login_at = user.last_login_at

        # Second login
        with patch("blackbeard.api.oidc._oauth", oauth), patch(
            "blackbeard.api.oidc.settings"
        ) as mock_settings:
            mock_settings.oidc_redirect_uri = "http://localhost:3000/api/v1/auth/oidc/callback"
            mock_settings.cors_origins = ["http://localhost:3000"]
            await oidc_client.get("/api/v1/auth/oidc/callback?code=valid2&state=def")

        await db_session.refresh(user)
        assert user.last_login_at is not None
        # The second login should have set or updated last_login_at
        if first_login_at is not None:
            assert user.last_login_at >= first_login_at

    async def test_tokens_are_valid_jwt(
        self, oidc_client: AsyncClient, db_session: AsyncSession
    ):
        """Callback should return valid JWT access and refresh tokens in the redirect."""
        provider = _mock_oauth_provider()
        oauth = _build_mock_oauth(provider)

        with patch("blackbeard.api.oidc._oauth", oauth), patch(
            "blackbeard.api.oidc.settings"
        ) as mock_settings:
            mock_settings.oidc_redirect_uri = "http://localhost:3000/api/v1/auth/oidc/callback"
            mock_settings.cors_origins = ["http://localhost:3000"]
            resp = await oidc_client.get("/api/v1/auth/oidc/callback?code=valid&state=abc")

        assert resp.status_code == 303
        location = resp.headers["location"]

        # Parse the fragment to extract tokens
        fragment = location.split("#", 1)[1]
        params = dict(p.split("=", 1) for p in fragment.split("&"))
        access_token = params["token"]
        refresh_token = params["refresh"]

        # Both should be decodable JWTs
        from blackbeard.auth.jwt import decode_token

        access_payload = decode_token(access_token)
        assert access_payload["type"] == "access"
        assert "sub" in access_payload

        refresh_payload = decode_token(refresh_token)
        assert refresh_payload["type"] == "refresh"
        assert refresh_payload["sub"] == access_payload["sub"]


# ---------------------------------------------------------------------------
# OIDC callback: userinfo without embedded claims
# ---------------------------------------------------------------------------


class TestOidcCallbackUserinfo:
    """Handle cases where userinfo is not embedded in the token response."""

    async def test_fetches_userinfo_when_not_in_token(
        self, oidc_client: AsyncClient, db_session: AsyncSession
    ):
        """When token has no userinfo, the endpoint should call the userinfo endpoint."""
        token_without_userinfo = {
            "access_token": "fake-access-token",
            "token_type": "bearer",
            "id_token": "fake-id-token",
        }
        provider = _mock_oauth_provider(
            token_response=token_without_userinfo,
            userinfo_response=_USERINFO_VERIFIED,
        )
        oauth = _build_mock_oauth(provider)

        with patch("blackbeard.api.oidc._oauth", oauth), patch(
            "blackbeard.api.oidc.settings"
        ) as mock_settings:
            mock_settings.oidc_redirect_uri = "http://localhost:3000/api/v1/auth/oidc/callback"
            mock_settings.cors_origins = ["http://localhost:3000"]
            resp = await oidc_client.get("/api/v1/auth/oidc/callback?code=valid&state=abc")

        assert resp.status_code == 303
        provider.userinfo.assert_awaited_once()

    async def test_uses_preferred_username_as_fallback_name(
        self, oidc_client: AsyncClient, db_session: AsyncSession
    ):
        """When userinfo has no 'name', should fall back to preferred_username."""
        userinfo = {
            "email": "noname@example.com",
            "email_verified": True,
            "preferred_username": "preferred_user",
            "sub": "sub-789",
        }
        provider = _mock_oauth_provider(
            token_response=_make_oidc_token(userinfo),
        )
        oauth = _build_mock_oauth(provider)

        with patch("blackbeard.api.oidc._oauth", oauth), patch(
            "blackbeard.api.oidc.settings"
        ) as mock_settings:
            mock_settings.oidc_redirect_uri = "http://localhost:3000/api/v1/auth/oidc/callback"
            mock_settings.cors_origins = ["http://localhost:3000"]
            resp = await oidc_client.get("/api/v1/auth/oidc/callback?code=valid&state=abc")

        assert resp.status_code == 303

        from sqlalchemy import select

        from blackbeard.models import User

        result = await db_session.execute(
            select(User).where(User.email == "noname@example.com")
        )
        user = result.scalar_one()
        assert user.display_name == "preferred_user"

    async def test_uses_email_local_part_as_last_resort_name(
        self, oidc_client: AsyncClient, db_session: AsyncSession
    ):
        """When userinfo has no name or preferred_username, use the email local part."""
        userinfo = {
            "email": "fallback@example.com",
            "email_verified": True,
            "sub": "sub-999",
        }
        provider = _mock_oauth_provider(
            token_response=_make_oidc_token(userinfo),
        )
        oauth = _build_mock_oauth(provider)

        with patch("blackbeard.api.oidc._oauth", oauth), patch(
            "blackbeard.api.oidc.settings"
        ) as mock_settings:
            mock_settings.oidc_redirect_uri = "http://localhost:3000/api/v1/auth/oidc/callback"
            mock_settings.cors_origins = ["http://localhost:3000"]
            resp = await oidc_client.get("/api/v1/auth/oidc/callback?code=valid&state=abc")

        assert resp.status_code == 303

        from sqlalchemy import select

        from blackbeard.models import User

        result = await db_session.execute(
            select(User).where(User.email == "fallback@example.com")
        )
        user = result.scalar_one()
        assert user.display_name == "fallback"


# ---------------------------------------------------------------------------
# OIDC callback: error cases
# ---------------------------------------------------------------------------


class TestOidcCallbackErrors:
    """Error handling in the OIDC callback."""

    async def test_token_exchange_failure_returns_401(self, oidc_client: AsyncClient):
        """If the provider rejects the auth code, return 401."""
        provider = _mock_oauth_provider(
            token_side_effect=Exception("invalid_grant: code expired")
        )
        oauth = _build_mock_oauth(provider)

        with patch("blackbeard.api.oidc._oauth", oauth):
            resp = await oidc_client.get(
                "/api/v1/auth/oidc/callback?code=invalid&state=abc"
            )

        assert resp.status_code == 401
        assert "failed" in resp.json()["detail"].lower()

    async def test_missing_email_returns_400(self, oidc_client: AsyncClient):
        """Provider returning no email should be rejected."""
        userinfo = {"email_verified": True, "name": "No Email User", "sub": "sub-no-email"}
        provider = _mock_oauth_provider(
            token_response=_make_oidc_token(userinfo),
        )
        oauth = _build_mock_oauth(provider)

        with patch("blackbeard.api.oidc._oauth", oauth):
            resp = await oidc_client.get("/api/v1/auth/oidc/callback?code=valid&state=abc")

        assert resp.status_code == 400
        assert "email" in resp.json()["detail"].lower()

    async def test_invalid_email_format_returns_400(self, oidc_client: AsyncClient):
        """Email without @ should be rejected."""
        userinfo = {
            "email": "not-an-email",
            "email_verified": True,
            "name": "Bad Email",
            "sub": "sub-bad",
        }
        provider = _mock_oauth_provider(
            token_response=_make_oidc_token(userinfo),
        )
        oauth = _build_mock_oauth(provider)

        with patch("blackbeard.api.oidc._oauth", oauth):
            resp = await oidc_client.get("/api/v1/auth/oidc/callback?code=valid&state=abc")

        assert resp.status_code == 400
        assert "invalid" in resp.json()["detail"].lower()

    async def test_unverified_email_returns_403(self, oidc_client: AsyncClient):
        """Provider reporting email_verified=False should be rejected."""
        userinfo = {
            "email": "unverified@example.com",
            "email_verified": False,
            "name": "Unverified User",
            "sub": "sub-unv",
        }
        provider = _mock_oauth_provider(
            token_response=_make_oidc_token(userinfo),
        )
        oauth = _build_mock_oauth(provider)

        with patch("blackbeard.api.oidc._oauth", oauth):
            resp = await oidc_client.get("/api/v1/auth/oidc/callback?code=valid&state=abc")

        assert resp.status_code == 403
        assert "not verified" in resp.json()["detail"].lower()

    async def test_deactivated_user_returns_403(
        self, oidc_client: AsyncClient, db_session: AsyncSession
    ):
        """OIDC login for a deactivated user should be rejected."""
        # First, create the user via OIDC
        provider = _mock_oauth_provider()
        oauth = _build_mock_oauth(provider)

        with patch("blackbeard.api.oidc._oauth", oauth), patch(
            "blackbeard.api.oidc.settings"
        ) as mock_settings:
            mock_settings.oidc_redirect_uri = "http://localhost:3000/api/v1/auth/oidc/callback"
            mock_settings.cors_origins = ["http://localhost:3000"]
            resp = await oidc_client.get("/api/v1/auth/oidc/callback?code=valid&state=abc")
        assert resp.status_code == 303

        # Deactivate the user
        from sqlalchemy import select

        from blackbeard.models import User

        result = await db_session.execute(
            select(User).where(User.email == "oidc-user@example.com")
        )
        user = result.scalar_one()
        user.is_active = False
        await db_session.commit()

        # Try logging in again
        with patch("blackbeard.api.oidc._oauth", oauth), patch(
            "blackbeard.api.oidc.settings"
        ) as mock_settings:
            mock_settings.oidc_redirect_uri = "http://localhost:3000/api/v1/auth/oidc/callback"
            mock_settings.cors_origins = ["http://localhost:3000"]
            resp = await oidc_client.get("/api/v1/auth/oidc/callback?code=valid2&state=def")

        assert resp.status_code == 403
        assert "deactivated" in resp.json()["detail"].lower()

    async def test_redirect_origin_not_in_cors_returns_500(
        self, oidc_client: AsyncClient, db_session: AsyncSession
    ):
        """If the computed redirect origin is not in CORS_ORIGINS, reject it."""
        provider = _mock_oauth_provider()
        oauth = _build_mock_oauth(provider)

        with patch("blackbeard.api.oidc._oauth", oauth), patch(
            "blackbeard.api.oidc.settings"
        ) as mock_settings:
            mock_settings.oidc_redirect_uri = "https://evil.example.com/callback"
            mock_settings.cors_origins = ["http://localhost:3000"]
            resp = await oidc_client.get("/api/v1/auth/oidc/callback?code=valid&state=abc")

        assert resp.status_code == 500
        assert "not an allowed origin" in resp.json()["detail"].lower()

    async def test_empty_email_string_returns_400(self, oidc_client: AsyncClient):
        """Provider returning an empty string for email should be rejected."""
        userinfo = {
            "email": "",
            "email_verified": True,
            "name": "Empty Email",
            "sub": "sub-empty",
        }
        provider = _mock_oauth_provider(
            token_response=_make_oidc_token(userinfo),
        )
        oauth = _build_mock_oauth(provider)

        with patch("blackbeard.api.oidc._oauth", oauth):
            resp = await oidc_client.get("/api/v1/auth/oidc/callback?code=valid&state=abc")

        assert resp.status_code == 400

    async def test_overly_long_email_returns_400(self, oidc_client: AsyncClient):
        """Email exceeding 320 chars should be rejected."""
        long_local = "a" * 310
        userinfo = {
            "email": f"{long_local}@example.com",
            "email_verified": True,
            "name": "Long Email",
            "sub": "sub-long",
        }
        provider = _mock_oauth_provider(
            token_response=_make_oidc_token(userinfo),
        )
        oauth = _build_mock_oauth(provider)

        with patch("blackbeard.api.oidc._oauth", oauth):
            resp = await oidc_client.get("/api/v1/auth/oidc/callback?code=valid&state=abc")

        assert resp.status_code == 400
        assert "invalid" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# OIDC user cannot use password login
# ---------------------------------------------------------------------------


class TestOidcPasswordIsolation:
    """OIDC-provisioned users should not be able to log in with passwords."""

    async def test_oidc_user_cannot_login_with_password(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """An OIDC-created user has a random password hash, so password login must fail."""
        from blackbeard.api.oidc import _find_or_create_user

        user, created = await _find_or_create_user(
            db_session, "sso@example.com", {"name": "SSO User"}
        )
        assert created is True
        assert user.password_hash is not None

        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "sso@example.com", "password": "anything"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# _find_or_create_user unit tests
# ---------------------------------------------------------------------------


class TestFindOrCreateUser:
    """Direct tests for the _find_or_create_user helper."""

    async def test_creates_new_user(self, db_session: AsyncSession):
        from blackbeard.api.oidc import _find_or_create_user

        user, created = await _find_or_create_user(
            db_session, "new@example.com", {"name": "New User", "email": "new@example.com"}
        )
        assert created is True
        assert user.email == "new@example.com"
        assert user.display_name == "New User"
        assert user.is_active is True

    async def test_links_existing_user(self, db_session: AsyncSession):
        from blackbeard.api.oidc import _find_or_create_user

        user1, created1 = await _find_or_create_user(
            db_session, "existing@example.com", {"name": "First"}
        )
        user2, created2 = await _find_or_create_user(
            db_session, "existing@example.com", {"name": "Second"}
        )
        assert created1 is True
        assert created2 is False
        assert user1.id == user2.id
        assert user2.last_login_at is not None

    async def test_fallback_display_name_from_email(self, db_session: AsyncSession):
        from blackbeard.api.oidc import _find_or_create_user

        user, created = await _find_or_create_user(db_session, "noname@example.com", {})
        assert created is True
        assert user.display_name == "noname"

    async def test_deactivated_user_raises_403(self, db_session: AsyncSession):
        from blackbeard.api.oidc import _find_or_create_user

        user, _ = await _find_or_create_user(
            db_session, "deact@example.com", {"name": "Will Deactivate"}
        )
        user.is_active = False
        await db_session.commit()

        with pytest.raises(Exception) as exc_info:
            await _find_or_create_user(db_session, "deact@example.com", {"name": "Try Again"})
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# OIDC callback: userinfo endpoint failure fallback
# ---------------------------------------------------------------------------


class TestOidcUserinfoFallback:
    """When the userinfo endpoint fails, the callback should handle it gracefully."""

    async def test_userinfo_failure_with_empty_email_returns_400(
        self, oidc_client: AsyncClient
    ):
        """If token has no userinfo and the userinfo call fails, should get 400 (no email)."""
        token_without_userinfo = {
            "access_token": "fake-access-token",
            "token_type": "bearer",
            "id_token": "fake-id-token",
        }
        provider = _mock_oauth_provider(token_response=token_without_userinfo)
        # Make the userinfo call raise
        provider.userinfo = AsyncMock(side_effect=Exception("userinfo endpoint down"))
        oauth = _build_mock_oauth(provider)

        with patch("blackbeard.api.oidc._oauth", oauth):
            resp = await oidc_client.get("/api/v1/auth/oidc/callback?code=valid&state=abc")

        # Should fail because no email is available from the empty fallback
        assert resp.status_code == 400
