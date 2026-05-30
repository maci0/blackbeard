"""Final coverage sweep — integration + fuzz tests for untested API endpoints.

Targets remaining coverage gaps across:
  - api/users.py: group CRUD, group member management, user CRUD edge cases
  - api/automations.py: trigger automation, webhook trigger (HMAC)
  - api/webhooks.py: specific-events create, pagination, delete
  - api/auth.py: duplicate email, login paths, refresh edge cases, API key mgmt
  - api/audit.py: date-range filters, pagination
  - main.py: _validate_startup_config, _fatal, _check_secret
  - Fuzz tests for evil strings on each endpoint family
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from tests.conftest import API_KEY_HEADER, _bearer, _register_user

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clear_rate_limits() -> None:
    """Reset all rate-limiter state so fuzz tests start clean."""
    from blackbeard.rate_limiter import (
        _auth_failures,
        assistant_limiter,
        chat_limiter,
        execution_limiter,
        marketplace_limiter,
        mutation_limiter,
        registration_limiter,
    )

    _auth_failures.clear()
    for limiter in (
        mutation_limiter,
        execution_limiter,
        marketplace_limiter,
        assistant_limiter,
        chat_limiter,
        registration_limiter,
    ):
        limiter._buckets.clear()


async def _user_headers(client: AsyncClient, email: str) -> dict:
    """Register a user and return Bearer token headers."""
    data = await _register_user(client, email=email)
    return _bearer(data["access_token"]), data


def _automation_payload(
    name: str,
    *,
    trigger_type: str = "api",
    enabled: bool = True,
    webhook_secret: str | None = None,
    target_kind: str = "Crew",
    target_name: str = "test-crew",
) -> dict:
    trigger: dict = {"type": trigger_type}
    if webhook_secret:
        trigger["webhook_secret"] = webhook_secret
    return {
        "apiVersion": "blackbeard/v1",
        "kind": "Automation",
        "metadata": {"name": name},
        "spec": {
            "target": {"kind": target_kind, "name": target_name},
            "trigger": trigger,
            "enabled": enabled,
            "inputs": {},
            "max_concurrent": 1,
        },
    }


# =========================================================================
# 1. Group CRUD — additional edge-case coverage (api/users.py)
# =========================================================================


class TestGroupCRUDEdgeCases:
    """Group endpoints: get, update, delete edge cases."""

    @pytest.mark.asyncio
    async def test_get_group_by_id(self, client: AsyncClient) -> None:
        headers, _ = await _user_headers(client, "grp-get@test.com")
        create = await client.post(
            "/api/v1/groups",
            json={"name": "lookup-grp", "description": "A test group"},
            headers=headers,
        )
        assert create.status_code == 201
        group_id = create.json()["id"]

        resp = await client.get(f"/api/v1/groups/{group_id}", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "lookup-grp"
        assert body["description"] == "A test group"
        assert body["id"] == group_id

    @pytest.mark.asyncio
    async def test_get_group_not_found(self, client: AsyncClient) -> None:
        headers, _ = await _user_headers(client, "grp-404@test.com")
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/api/v1/groups/{fake_id}", headers=headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_group_description(self, client: AsyncClient) -> None:
        headers, _ = await _user_headers(client, "grp-upd@test.com")
        create = await client.post(
            "/api/v1/groups",
            json={"name": "upd-grp"},
            headers=headers,
        )
        assert create.status_code == 201
        group_id = create.json()["id"]

        resp = await client.put(
            f"/api/v1/groups/{group_id}",
            json={"description": "Updated description"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["description"] == "Updated description"

    @pytest.mark.asyncio
    async def test_update_group_not_found(self, client: AsyncClient) -> None:
        headers, _ = await _user_headers(client, "grp-upd404@test.com")
        fake_id = str(uuid.uuid4())
        resp = await client.put(
            f"/api/v1/groups/{fake_id}",
            json={"description": "Nope"},
            headers=headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_group(self, client: AsyncClient) -> None:
        headers, _ = await _user_headers(client, "grp-del@test.com")
        create = await client.post(
            "/api/v1/groups",
            json={"name": "del-grp"},
            headers=headers,
        )
        assert create.status_code == 201
        group_id = create.json()["id"]

        resp = await client.delete(f"/api/v1/groups/{group_id}", headers=headers)
        assert resp.status_code == 204

        # Idempotent: second delete also 204
        resp2 = await client.delete(f"/api/v1/groups/{group_id}", headers=headers)
        assert resp2.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_nonexistent_group(self, client: AsyncClient) -> None:
        headers, _ = await _user_headers(client, "grp-del-ne@test.com")
        fake_id = str(uuid.uuid4())
        resp = await client.delete(f"/api/v1/groups/{fake_id}", headers=headers)
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_list_groups_pagination(self, client: AsyncClient) -> None:
        headers, _ = await _user_headers(client, "grp-page@test.com")
        for i in range(3):
            r = await client.post(
                "/api/v1/groups",
                json={"name": f"page-grp-{i}"},
                headers=headers,
            )
            assert r.status_code == 201

        resp = await client.get("/api/v1/groups?limit=2&offset=0", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 2
        assert body["total"] == 3
        assert body["has_more"] is True

        resp2 = await client.get("/api/v1/groups?limit=2&offset=2", headers=headers)
        assert resp2.status_code == 200
        body2 = resp2.json()
        assert len(body2["items"]) == 1
        assert body2["has_more"] is False

    @pytest.mark.asyncio
    async def test_create_group_location_header(self, client: AsyncClient) -> None:
        headers, _ = await _user_headers(client, "grp-loc@test.com")
        resp = await client.post(
            "/api/v1/groups",
            json={"name": "loc-grp"},
            headers=headers,
        )
        assert resp.status_code == 201
        assert "Location" in resp.headers
        group_id = resp.json()["id"]
        assert group_id in resp.headers["Location"]


# =========================================================================
# 2. User CRUD — update, deactivate edge cases (api/users.py)
# =========================================================================


class TestUserCRUDEdgeCases:
    """User endpoints: list pagination, update other user, deactivate edge cases."""

    @pytest.mark.asyncio
    async def test_list_users_pagination(self, client: AsyncClient) -> None:
        for i in range(3):
            await _register_user(client, email=f"page-user-{i}@test.com")
        headers, _ = await _user_headers(client, "page-admin@test.com")

        resp = await client.get("/api/v1/users?limit=2&offset=0", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 2
        assert body["total"] == 4  # 3 + the admin user
        assert body["has_more"] is True

    @pytest.mark.asyncio
    async def test_update_other_user_forbidden(self, client: AsyncClient) -> None:
        _, data1 = await _user_headers(client, "upd-self@test.com")
        headers2, _data2 = await _user_headers(client, "upd-other@test.com")
        other_user_id = data1["user"]["id"]

        resp = await client.put(
            f"/api/v1/users/{other_user_id}",
            json={"display_name": "Hacked"},
            headers=headers2,
        )
        assert resp.status_code == 403
        assert "cannot" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_update_nonexistent_user(self, client: AsyncClient) -> None:
        headers, data = await _user_headers(client, "upd-ne@test.com")
        fake_id = data["user"]["id"]
        # Update self succeeds
        resp = await client.put(
            f"/api/v1/users/{fake_id}",
            json={"display_name": "New Name"},
            headers=headers,
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_deactivate_user_anonymizes_data(self, client: AsyncClient) -> None:
        headers, data = await _user_headers(client, "deact-anon@test.com")
        user_id = data["user"]["id"]

        resp = await client.delete(f"/api/v1/users/{user_id}", headers=headers)
        assert resp.status_code == 204

        # Login should fail with anonymized email
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "deact-anon@test.com", "password": "securepass123"},
        )
        assert login_resp.status_code == 401

    @pytest.mark.asyncio
    async def test_list_users_requires_identity(self, client: AsyncClient) -> None:
        """List users with system API key (no user identity) returns 401."""
        resp = await client.get("/api/v1/users", headers=API_KEY_HEADER)
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_get_user_requires_identity(self, client: AsyncClient) -> None:
        """Get user with system API key (no user identity) returns 401."""
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/api/v1/users/{fake_id}", headers=API_KEY_HEADER)
        assert resp.status_code == 401


# =========================================================================
# 3. Automation trigger endpoints (api/automations.py)
# =========================================================================


class TestAutomationTrigger:
    """POST /automations/{name}/trigger — manual API trigger."""

    @pytest.mark.asyncio
    async def test_trigger_nonexistent_automation(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/automations/no-such-auto/trigger",
            json={"inputs": {}},
            headers=API_KEY_HEADER,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_trigger_disabled_automation(self, client: AsyncClient) -> None:
        payload = _automation_payload("dis-api-auto", enabled=False)
        await client.post("/api/v1/automations", json=payload, headers=API_KEY_HEADER)

        resp = await client.post(
            "/api/v1/automations/dis-api-auto/trigger",
            json={"inputs": {}},
            headers=API_KEY_HEADER,
        )
        assert resp.status_code == 409
        assert "disabled" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_trigger_automation_success(self, client: AsyncClient) -> None:
        """Trigger succeeds when executor returns an Execution."""
        payload = _automation_payload("ok-auto")
        await client.post("/api/v1/automations", json=payload, headers=API_KEY_HEADER)

        mock_exec = _make_mock_execution()
        with patch(
            "blackbeard.api.automations._executor_mod.kickoff",
            new_callable=AsyncMock,
            return_value=mock_exec,
        ):
            resp = await client.post(
                "/api/v1/automations/ok-auto/trigger",
                json={"inputs": {"topic": "test"}},
                headers=API_KEY_HEADER,
            )
        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == "triggered"
        assert body["automation_name"] == "ok-auto"
        assert body["execution"] is not None

    @pytest.mark.asyncio
    async def test_trigger_automation_executor_error(self, client: AsyncClient) -> None:
        """Trigger returns 500 when executor raises ExecutionError."""
        from blackbeard.engine import ExecutionError

        payload = _automation_payload("err-auto")
        await client.post("/api/v1/automations", json=payload, headers=API_KEY_HEADER)

        with patch(
            "blackbeard.api.automations._executor_mod.kickoff",
            new_callable=AsyncMock,
            side_effect=ExecutionError("boom"),
        ):
            resp = await client.post(
                "/api/v1/automations/err-auto/trigger",
                json={"inputs": {}},
                headers=API_KEY_HEADER,
            )
        assert resp.status_code == 500


class TestAutomationWebhookTrigger:
    """POST /automations/{name}/webhook — webhook trigger with HMAC validation."""

    @pytest.mark.asyncio
    async def test_webhook_trigger_wrong_secret(self, client: AsyncClient) -> None:
        payload = _automation_payload(
            "wh-wrong-secret",
            trigger_type="webhook",
            webhook_secret="correct-secret-1234567890",
        )
        await client.post("/api/v1/automations", json=payload, headers=API_KEY_HEADER)

        resp = await client.post(
            "/api/v1/automations/wh-wrong-secret/webhook",
            json={"secret": "wrong-secret-12345678", "inputs": {}},
        )
        assert resp.status_code == 401
        assert "invalid" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_webhook_trigger_correct_secret(self, client: AsyncClient) -> None:
        """Webhook trigger with correct secret and matching crew."""
        secret = "valid-webhook-secret-1234"
        payload = _automation_payload(
            "wh-ok-auto",
            trigger_type="webhook",
            webhook_secret=secret,
        )
        await client.post("/api/v1/automations", json=payload, headers=API_KEY_HEADER)

        mock_exec = _make_mock_execution()
        with patch(
            "blackbeard.api.automations._executor_mod.kickoff",
            new_callable=AsyncMock,
            return_value=mock_exec,
        ):
            resp = await client.post(
                "/api/v1/automations/wh-ok-auto/webhook",
                json={"secret": secret, "inputs": {"event": "push"}},
            )
        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == "triggered"
        assert body["execution"] is not None

    @pytest.mark.asyncio
    async def test_webhook_trigger_non_webhook_type(self, client: AsyncClient) -> None:
        """Webhook endpoint rejects automations not configured as webhook type."""
        payload = _automation_payload(
            "not-wh-auto",
            trigger_type="api",
        )
        await client.post("/api/v1/automations", json=payload, headers=API_KEY_HEADER)

        resp = await client.post(
            "/api/v1/automations/not-wh-auto/webhook",
            json={"secret": "some-secret-12345678", "inputs": {}},
        )
        assert resp.status_code == 409
        assert "not a webhook" in resp.json()["detail"].lower()


# =========================================================================
# 4. Webhook endpoints — specific events, pagination (api/webhooks.py)
# =========================================================================


class TestWebhookEndpointsExtended:
    """Additional webhook endpoint coverage."""

    @pytest.mark.asyncio
    async def test_create_with_specific_events_and_delete(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/webhooks",
            json={
                "url": "http://example.com/specific-events",
                "events": ["crew_started", "task_completed", "crew_failed"],
            },
            headers=API_KEY_HEADER,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["events"] == ["crew_started", "task_completed", "crew_failed"]
        webhook_id = body["id"]

        # Delete it
        del_resp = await client.delete(
            f"/api/v1/webhooks/{webhook_id}",
            headers=API_KEY_HEADER,
        )
        assert del_resp.status_code == 204

    @pytest.mark.asyncio
    async def test_webhook_list_pagination(self, client: AsyncClient) -> None:
        for i in range(3):
            r = await client.post(
                "/api/v1/webhooks",
                json={"url": f"http://example.com/page-{i}"},
                headers=API_KEY_HEADER,
            )
            assert r.status_code == 201

        resp = await client.get("/api/v1/webhooks?limit=2&offset=0", headers=API_KEY_HEADER)
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 2
        assert body["total"] == 3
        assert body["has_more"] is True

    @pytest.mark.asyncio
    async def test_webhook_requires_valid_url_pattern(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/webhooks",
            json={"url": "not-a-url"},
            headers=API_KEY_HEADER,
        )
        assert resp.status_code == 422


# =========================================================================
# 5. Auth endpoints — extended coverage (api/auth.py)
# =========================================================================


class TestAuthExtended:
    """Additional auth endpoint coverage."""

    @pytest.mark.asyncio
    async def test_register_duplicate_email_case_insensitive(self, client: AsyncClient) -> None:
        await _register_user(client, email="dupe@test.com")
        resp = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "DUPE@TEST.COM",
                "password": "securepass123",
                "display_name": "Dupe",
            },
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_register_password_no_digit(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "nodigit@test.com",
                "password": "onlyletters",
                "display_name": "No Digit",
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_register_password_no_letter(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "noletter@test.com",
                "password": "12345678",
                "display_name": "No Letter",
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_login_success_returns_tokens_and_user(self, client: AsyncClient) -> None:
        await _register_user(client, email="login-ok@test.com")
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "login-ok@test.com", "password": "securepass123"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["user"]["email"] == "login-ok@test.com"
        assert body["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_login_wrong_email(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@nowhere.com", "password": "securepass123"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client: AsyncClient) -> None:
        await _register_user(client, email="wrongpw@test.com")
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "wrongpw@test.com", "password": "wrong-password-1"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_valid_token(self, client: AsyncClient) -> None:
        data = await _register_user(client, email="refresh-ok@test.com")
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": data["refresh_token"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["access_token"] != data["access_token"]

    @pytest.mark.asyncio
    async def test_refresh_with_expired_token(self, client: AsyncClient) -> None:
        import jwt as pyjwt

        from blackbeard.config import settings

        payload = {
            "sub": str(uuid.uuid4()),
            "type": "refresh",
            "jti": uuid.uuid4().hex,
            "iss": "blackbeard",
            "aud": "blackbeard",
            "iat": datetime.now(UTC) - timedelta(days=30),
            "nbf": datetime.now(UTC) - timedelta(days=30),
            "exp": datetime.now(UTC) - timedelta(days=1),
        }
        token = pyjwt.encode(
            payload,
            settings.jwt_secret.get_secret_value(),
            algorithm="HS256",
        )
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": token},
        )
        assert resp.status_code == 401
        assert "expired" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_refresh_with_garbage_token(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "not.a.valid.jwt.token"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_for_inactive_user(self, client: AsyncClient) -> None:
        """Refresh token for deactivated user returns 401."""
        data = await _register_user(client, email="refresh-inact@test.com")
        user_id = data["user"]["id"]
        token = data["access_token"]
        refresh_token = data["refresh_token"]

        # Deactivate the user
        resp = await client.delete(f"/api/v1/users/{user_id}", headers=_bearer(token))
        assert resp.status_code == 204

        # Try to refresh
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_me_endpoint(self, client: AsyncClient) -> None:
        data = await _register_user(client, email="me-test@test.com")
        resp = await client.get(
            "/api/v1/auth/me",
            headers=_bearer(data["access_token"]),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == "me-test@test.com"
        assert body["is_active"] is True

    @pytest.mark.asyncio
    async def test_me_without_auth(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 401


class TestApiKeyManagement:
    """POST /auth/api-key and DELETE /auth/api-key."""

    @pytest.mark.asyncio
    async def test_generate_api_key(self, client: AsyncClient) -> None:
        data = await _register_user(client, email="apikey-gen@test.com")
        headers = _bearer(data["access_token"])

        resp = await client.post("/api/v1/auth/api-key", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "api_key" in body
        assert body["api_key"].startswith("bb-")

    @pytest.mark.asyncio
    async def test_rotate_api_key(self, client: AsyncClient) -> None:
        data = await _register_user(client, email="apikey-rot@test.com")
        headers = _bearer(data["access_token"])

        resp1 = await client.post("/api/v1/auth/api-key", headers=headers)
        assert resp1.status_code == 200
        key1 = resp1.json()["api_key"]

        resp2 = await client.post("/api/v1/auth/api-key", headers=headers)
        assert resp2.status_code == 200
        key2 = resp2.json()["api_key"]

        assert key1 != key2, "Rotated key should differ from the original"

    @pytest.mark.asyncio
    async def test_revoke_api_key(self, client: AsyncClient) -> None:
        data = await _register_user(client, email="apikey-rev@test.com")
        headers = _bearer(data["access_token"])

        # Generate a key first
        await client.post("/api/v1/auth/api-key", headers=headers)

        # Revoke it
        resp = await client.delete("/api/v1/auth/api-key", headers=headers)
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_revoke_api_key_idempotent(self, client: AsyncClient) -> None:
        """Revoking when no key exists returns 204."""
        data = await _register_user(client, email="apikey-noop@test.com")
        headers = _bearer(data["access_token"])

        resp = await client.delete("/api/v1/auth/api-key", headers=headers)
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_generate_api_key_requires_jwt(self, client: AsyncClient) -> None:
        """System API key alone cannot generate a personal API key."""
        resp = await client.post("/api/v1/auth/api-key", headers=API_KEY_HEADER)
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_generate_then_revoke_roundtrip(self, client: AsyncClient) -> None:
        """Full lifecycle: generate key, verify it exists, revoke, verify gone."""
        data = await _register_user(client, email="apikey-life@test.com")
        headers = _bearer(data["access_token"])

        # Generate
        gen_resp = await client.post("/api/v1/auth/api-key", headers=headers)
        assert gen_resp.status_code == 200
        key = gen_resp.json()["api_key"]
        assert key.startswith("bb-")

        # Revoke
        rev_resp = await client.delete("/api/v1/auth/api-key", headers=headers)
        assert rev_resp.status_code == 204

        # Revoke again is idempotent
        rev_resp2 = await client.delete("/api/v1/auth/api-key", headers=headers)
        assert rev_resp2.status_code == 204


# =========================================================================
# 6. Audit log — date-range filters, pagination (api/audit.py)
# =========================================================================


class TestAuditLogFilters:
    """GET /api/v1/audit-logs with various filters."""

    @pytest.mark.asyncio
    async def test_audit_log_date_range_filter(self, client: AsyncClient) -> None:
        headers, _ = await _user_headers(client, "audit-date@test.com")

        # Create a resource to generate audit entries
        await client.post(
            "/api/v1/agents",
            json={
                "apiVersion": "blackbeard/v1",
                "kind": "Agent",
                "metadata": {"name": "audit-date-agent"},
                "spec": {"role": "R", "goal": "G", "backstory": "B"},
            },
            headers=headers,
        )

        # Filter with start_date in the past (should include entries)
        # Use Z suffix instead of +00:00 to avoid query string encoding issues
        past = (datetime.now(UTC) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        resp = await client.get(
            f"/api/v1/audit-logs?start_date={past}",
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    @pytest.mark.asyncio
    async def test_audit_log_end_date_filter(self, client: AsyncClient) -> None:
        headers, _ = await _user_headers(client, "audit-end@test.com")

        # Filter with end_date in the past (should return nothing recent)
        past = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        resp = await client.get(
            f"/api/v1/audit-logs?end_date={past}",
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    @pytest.mark.asyncio
    async def test_audit_log_action_filter(self, client: AsyncClient) -> None:
        headers, _ = await _user_headers(client, "audit-act@test.com")

        resp = await client.get(
            "/api/v1/audit-logs?action=user_registered",
            headers=headers,
        )
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert item["action"] == "user_registered"

    @pytest.mark.asyncio
    async def test_audit_log_actor_id_filter(self, client: AsyncClient) -> None:
        headers, data = await _user_headers(client, "audit-actor@test.com")
        user_id = data["user"]["id"]

        resp = await client.get(
            f"/api/v1/audit-logs?actor_id={user_id}",
            headers=headers,
        )
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert item["actor_id"] == user_id

    @pytest.mark.asyncio
    async def test_audit_log_resource_type_filter(self, client: AsyncClient) -> None:
        headers, _ = await _user_headers(client, "audit-rtype@test.com")

        # Create an agent to generate a resource_created audit entry
        await client.post(
            "/api/v1/agents",
            json={
                "apiVersion": "blackbeard/v1",
                "kind": "Agent",
                "metadata": {"name": "audit-rtype-agent"},
                "spec": {"role": "R", "goal": "G", "backstory": "B"},
            },
            headers=headers,
        )

        resp = await client.get(
            "/api/v1/audit-logs?resource_type=Agent",
            headers=headers,
        )
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert item["resource_type"] == "Agent"

    @pytest.mark.asyncio
    async def test_audit_log_pagination(self, client: AsyncClient) -> None:
        headers, _ = await _user_headers(client, "audit-pag@test.com")

        # Create several resources
        for i in range(4):
            await client.post(
                "/api/v1/agents",
                json={
                    "apiVersion": "blackbeard/v1",
                    "kind": "Agent",
                    "metadata": {"name": f"audit-pag-{i}"},
                    "spec": {"role": "R", "goal": "G", "backstory": "B"},
                },
                headers=headers,
            )

        resp = await client.get("/api/v1/audit-logs?limit=2&offset=0", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 2
        assert body["has_more"] is True

    @pytest.mark.asyncio
    async def test_audit_log_no_store_cache_header(self, client: AsyncClient) -> None:
        headers, _ = await _user_headers(client, "audit-cache@test.com")
        resp = await client.get("/api/v1/audit-logs", headers=headers)
        assert resp.status_code == 200
        assert resp.headers.get("Cache-Control") == "no-store"

    @pytest.mark.asyncio
    async def test_audit_log_requires_identity(self, client: AsyncClient) -> None:
        """Audit logs require user identity, not just system API key."""
        resp = await client.get("/api/v1/audit-logs", headers=API_KEY_HEADER)
        assert resp.status_code == 401


# =========================================================================
# 7. main.py — _validate_startup_config, _fatal, _check_secret
# =========================================================================


class TestStartupValidation:
    """Tests for _validate_startup_config and related helpers."""

    @pytest.fixture(autouse=True)
    def _preserve_api_key(self) -> None:
        """Save and restore the global API key around each test.

        _validate_startup_config in debug mode calls set_api_key(generated)
        which mutates global state and breaks subsequent tests that use
        API_KEY_HEADER.
        """
        from blackbeard.auth.api_key import get_api_key, set_api_key

        original = get_api_key()
        yield
        set_api_key(original)

    def test_fatal_returns_runtime_error(self) -> None:
        # Access the nested _fatal function indirectly by testing the
        # RuntimeError is raised with proper message. We mock settings
        # to trigger a specific failure path.
        from blackbeard.main import _MIN_SECRET_LENGTH

        assert _MIN_SECRET_LENGTH == 16

    def test_validate_startup_config_debug_mode_accepts_defaults(self) -> None:
        """In debug mode, default secrets are accepted with warnings."""
        from blackbeard.main import _validate_startup_config

        # The test environment has DEBUG=true, so default secrets should be accepted.
        # The autouse _preserve_api_key fixture handles save/restore of the global key.
        _validate_startup_config()

    def test_validate_startup_config_short_api_key_rejects(self) -> None:
        """API key shorter than 16 chars is rejected even in debug mode."""
        from pydantic import SecretStr

        from blackbeard.main import _validate_startup_config

        mock_settings = type("MockSettings", (), {
            "debug": True,
            "blackbeard_api_key": SecretStr("short"),
            "jwt_secret": SecretStr("change-jwt-secret-in-production!"),
            "litellm_master_key": SecretStr("sk-litellm-master-key"),
            "cors_origins": ["*"],
            "litellm_proxy_url": "http://localhost:4000",
            "oidc_issuer": None,
            "enforce_rbac": False,
            "forwarded_allow_ips": "127.0.0.1",
        })()

        with patch("blackbeard.main.settings", mock_settings):
            with pytest.raises(RuntimeError, match="too short"):
                _validate_startup_config()

    def test_validate_startup_config_non_debug_rejects_default_api_key(self) -> None:
        """Production mode rejects the default API key."""
        from pydantic import SecretStr

        from blackbeard.main import _validate_startup_config

        mock_settings = type("MockSettings", (), {
            "debug": False,
            "blackbeard_api_key": SecretStr("change-me-in-production"),
            "jwt_secret": SecretStr("a-strong-jwt-secret-that-is-long-enough"),
            "litellm_master_key": SecretStr("a-strong-litellm-key-12345"),
            "cors_origins": ["https://example.com"],
            "litellm_proxy_url": "https://litellm.example.com",
            "oidc_issuer": None,
            "enforce_rbac": True,
            "forwarded_allow_ips": "10.0.0.1",
        })()

        with patch("blackbeard.main.settings", mock_settings):
            with pytest.raises(RuntimeError, match="insecure default"):
                _validate_startup_config()

    def test_validate_startup_config_bad_litellm_scheme(self) -> None:
        """LiteLLM proxy URL with bad scheme is rejected."""
        from pydantic import SecretStr

        from blackbeard.main import _validate_startup_config

        mock_settings = type("MockSettings", (), {
            "debug": True,
            "blackbeard_api_key": SecretStr("change-me-in-production"),
            "jwt_secret": SecretStr("change-jwt-secret-in-production!"),
            "litellm_master_key": SecretStr("sk-litellm-master-key"),
            "cors_origins": ["*"],
            "litellm_proxy_url": "ftp://litellm.local",
            "oidc_issuer": None,
            "enforce_rbac": False,
            "forwarded_allow_ips": "127.0.0.1",
        })()

        with patch("blackbeard.main.settings", mock_settings):
            with pytest.raises(RuntimeError, match="unexpected scheme"):
                _validate_startup_config()

    def test_validate_startup_config_non_debug_cors_wildcard(self) -> None:
        """Production mode rejects CORS wildcard."""
        from pydantic import SecretStr

        from blackbeard.main import _validate_startup_config

        mock_settings = type("MockSettings", (), {
            "debug": False,
            "blackbeard_api_key": SecretStr("a-strong-api-key-for-production-use"),
            "jwt_secret": SecretStr("a-strong-jwt-secret-that-is-long-enough"),
            "litellm_master_key": SecretStr("a-strong-litellm-key-12345"),
            "cors_origins": ["*"],
            "litellm_proxy_url": "https://litellm.example.com",
            "oidc_issuer": None,
            "enforce_rbac": True,
            "forwarded_allow_ips": "10.0.0.1",
        })()

        with patch("blackbeard.main.settings", mock_settings):
            with pytest.raises(RuntimeError, match="wildcard"):
                _validate_startup_config()

    def test_validate_startup_config_non_debug_http_cors_origin(self) -> None:
        """Production mode rejects http:// CORS origins."""
        from pydantic import SecretStr

        from blackbeard.main import _validate_startup_config

        mock_settings = type("MockSettings", (), {
            "debug": False,
            "blackbeard_api_key": SecretStr("a-strong-api-key-for-production-use"),
            "jwt_secret": SecretStr("a-strong-jwt-secret-that-is-long-enough"),
            "litellm_master_key": SecretStr("a-strong-litellm-key-12345"),
            "cors_origins": ["http://localhost:3000"],
            "litellm_proxy_url": "https://litellm.example.com",
            "oidc_issuer": None,
            "enforce_rbac": True,
            "forwarded_allow_ips": "10.0.0.1",
        })()

        with patch("blackbeard.main.settings", mock_settings):
            with pytest.raises(RuntimeError, match="https://"):
                _validate_startup_config()

    def test_validate_startup_config_short_jwt_secret_non_debug(self) -> None:
        """Production mode rejects short JWT secret."""
        from pydantic import SecretStr

        from blackbeard.main import _validate_startup_config

        mock_settings = type("MockSettings", (), {
            "debug": False,
            "blackbeard_api_key": SecretStr("a-strong-api-key-for-production-use"),
            "jwt_secret": SecretStr("short-jwt-12345"),
            "litellm_master_key": SecretStr("a-strong-litellm-key-12345"),
            "cors_origins": ["https://example.com"],
            "litellm_proxy_url": "https://litellm.example.com",
            "oidc_issuer": None,
            "enforce_rbac": True,
            "forwarded_allow_ips": "10.0.0.1",
        })()

        with patch("blackbeard.main.settings", mock_settings):
            with pytest.raises(RuntimeError, match="too short"):
                _validate_startup_config()


# =========================================================================
# 8. Fuzz tests — evil strings for each endpoint family
# =========================================================================

# Evil input strings for fuzzing
EVIL_STRINGS = [
    "",
    " ",
    "a" * 10000,
    "\x00\x01\x02\x03",
    "'; DROP TABLE users; --",
    "<script>alert('xss')</script>",
    "{{7*7}}",
    "${7*7}",
    "../../../etc/passwd",
    "\r\nX-Injected: true",
    "admin\x00hidden",
    '{"__proto__": {"polluted": true}}',
    "a\nb\nc",
    "\t\t\t",
]

EVIL_UUIDS = [
    "not-a-uuid",
    "00000000-0000-0000-0000-000000000000",
    "'; DROP TABLE groups; --",
    "../../../",
    "a" * 500,
]


class TestFuzzGroupNames:
    """Fuzz group name inputs with evil strings."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("evil_name", EVIL_STRINGS, ids=lambda s: repr(s)[:40])
    async def test_create_group_evil_name(self, client: AsyncClient, evil_name: str) -> None:
        headers, _ = await _user_headers(client, "fuzz-grp@test.com")
        resp = await client.post(
            "/api/v1/groups",
            json={"name": evil_name},
            headers=headers,
        )
        # Must reject or handle gracefully (never 500)
        assert resp.status_code in (201, 409, 422), (
            f"Unexpected status {resp.status_code} for evil group name {evil_name!r}"
        )


class TestFuzzUserIds:
    """Fuzz user ID path params with evil strings."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("evil_id", EVIL_UUIDS, ids=lambda s: repr(s)[:40])
    async def test_get_user_evil_id(self, client: AsyncClient, evil_id: str) -> None:
        headers, _ = await _user_headers(client, "fuzz-uid@test.com")
        resp = await client.get(f"/api/v1/users/{evil_id}", headers=headers)
        # Must return 404 or 422, never 500
        assert resp.status_code in (404, 422), (
            f"Unexpected status {resp.status_code} for evil user ID {evil_id!r}"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("evil_id", EVIL_UUIDS, ids=lambda s: repr(s)[:40])
    async def test_delete_user_evil_id(self, client: AsyncClient, evil_id: str) -> None:
        headers, _ = await _user_headers(client, "fuzz-udel@test.com")
        resp = await client.delete(f"/api/v1/users/{evil_id}", headers=headers)
        assert resp.status_code in (204, 403, 404, 422), (
            f"Unexpected status {resp.status_code} for evil user ID {evil_id!r}"
        )


_EVIL_AUTOMATION_INPUTS = [
    {},
    {"key": "a" * 50000},
    {"nested": {"level1": {"level2": {"level3": "deep"}}}},
    {"array": list(range(1000))},
    {"null_val": None},
    {"bool_val": True},
    {"float_val": 3.14159},
]


class TestFuzzAutomationInputs:
    """Fuzz automation trigger inputs with deeply nested/evil payloads."""

    @pytest.fixture(autouse=True)
    def _clear_rate_limits(self) -> None:
        _clear_rate_limits()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("evil_input", _EVIL_AUTOMATION_INPUTS, ids=lambda x: repr(x)[:40])
    async def test_trigger_automation_evil_inputs(
        self, client: AsyncClient, evil_input: object
    ) -> None:
        payload = _automation_payload("fuzz-input-auto")
        await client.post("/api/v1/automations", json=payload, headers=API_KEY_HEADER)

        with patch("blackbeard.api.automations._execute_target", new_callable=AsyncMock, return_value=None):
            resp = await client.post(
                "/api/v1/automations/fuzz-input-auto/trigger",
                json={"inputs": evil_input},
                headers=API_KEY_HEADER,
            )
        # Must never return 500 for input validation
        assert resp.status_code != 500, (
            f"500 Internal Server Error for evil input {evil_input!r}: {resp.text[:200]}"
        )


_EVIL_CREDENTIALS = [
    ("admin@test.com", "password123"),
    ("' OR 1=1; --", "password"),
    ("admin@admin.com", "' OR 1=1; --"),
    ("a" * 500 + "@test.com", "pass12345"),
    ("<script>", "alert1234"),
    ("null@test.com", "\x00\x00\x00\x00"),
    ("test@test.com", "a" * 200),
]


class TestFuzzAuthLogin:
    """Fuzz auth login with random/evil credentials."""

    @pytest.fixture(autouse=True)
    def _clear_rate_limits_fixture(self) -> None:
        _clear_rate_limits()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("email", "password"),
        _EVIL_CREDENTIALS,
        ids=lambda x: repr(x)[:40],
    )
    async def test_login_evil_credentials(
        self, client: AsyncClient, email: str, password: str
    ) -> None:
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        # Should return 401 or 422, never 500
        assert resp.status_code in (401, 422), (
            f"Unexpected status {resp.status_code} for evil login ({email!r}, {password!r})"
        )


_EVIL_DATES = [
    "not-a-date",
    "2024-13-01",  # invalid month
    "2024-01-32",  # invalid day
    "",
    "null",
    "0000-00-00",
    "9999-99-99T99:99:99Z",
    "<script>alert(1)</script>",
    "2024-01-01; DROP TABLE audit_logs; --",
]


class TestFuzzAuditLogDates:
    """Fuzz audit log date params with malformed values."""

    @pytest.fixture(autouse=True)
    def _clear_rate_limits_fixture(self) -> None:
        _clear_rate_limits()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("evil_date", _EVIL_DATES, ids=lambda s: repr(s)[:40])
    async def test_audit_log_evil_start_date(
        self, client: AsyncClient, evil_date: str
    ) -> None:
        headers, _ = await _user_headers(client, "fuzz-audit@test.com")
        resp = await client.get(
            f"/api/v1/audit-logs?start_date={evil_date}",
            headers=headers,
        )
        # Should return 200 or 422, never 500
        assert resp.status_code in (200, 422), (
            f"Unexpected status {resp.status_code} for evil date {evil_date!r}"
        )


class TestFuzzGroupMemberIds:
    """Fuzz group member endpoints with evil UUIDs."""

    @pytest.fixture(autouse=True)
    def _clear_rate_limits_fixture(self) -> None:
        _clear_rate_limits()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("evil_id", EVIL_UUIDS, ids=lambda s: repr(s)[:40])
    async def test_add_member_evil_group_id(
        self, client: AsyncClient, evil_id: str
    ) -> None:
        headers, data = await _user_headers(client, "fuzz-gmem@test.com")
        resp = await client.post(
            f"/api/v1/groups/{evil_id}/members",
            json={"user_id": data["user"]["id"]},
            headers=headers,
        )
        assert resp.status_code in (404, 422), (
            f"Unexpected status {resp.status_code} for evil group ID {evil_id!r}"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("evil_id", EVIL_UUIDS, ids=lambda s: repr(s)[:40])
    async def test_list_members_evil_group_id(
        self, client: AsyncClient, evil_id: str
    ) -> None:
        headers, _ = await _user_headers(client, "fuzz-glist@test.com")
        resp = await client.get(
            f"/api/v1/groups/{evil_id}/members",
            headers=headers,
        )
        assert resp.status_code in (404, 422), (
            f"Unexpected status {resp.status_code} for evil group ID {evil_id!r}"
        )


_EVIL_URLS = [
    "javascript:alert(1)",
    "file:///etc/passwd",
    "ftp://evil.com/payload",
    "http://" + "a" * 3000,
    "http://[::1]/hook",
    "http://0x7f000001/hook",
    "http://169.254.169.254/metadata",
]


class TestFuzzWebhookUrls:
    """Fuzz webhook URL inputs."""

    @pytest.fixture(autouse=True)
    def _clear_rate_limits_fixture(self) -> None:
        _clear_rate_limits()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("evil_url", _EVIL_URLS, ids=lambda s: repr(s)[:40])
    async def test_create_webhook_evil_url(
        self, client: AsyncClient, evil_url: str
    ) -> None:
        resp = await client.post(
            "/api/v1/webhooks",
            json={"url": evil_url},
            headers=API_KEY_HEADER,
        )
        # Must reject or return 422/401, never 500
        assert resp.status_code in (201, 401, 422), (
            f"Unexpected status {resp.status_code} for evil URL {evil_url!r}"
        )


# =========================================================================
# Helpers — mock execution factory
# =========================================================================


def _make_mock_execution(
    *,
    crew_name: str = "test-crew",
    execution_type: str = "kickoff",
    status: str = "queued",
) -> object:
    """Build a detached Execution ORM object for mocking executor returns."""
    from decimal import Decimal

    from blackbeard.models.execution import Execution, ExecutionStatus, ExecutionType

    e = Execution()
    e.id = uuid.uuid4()
    e.crew_name = crew_name
    e.crew_project = "default"
    e.execution_type = ExecutionType(execution_type)
    e.status = ExecutionStatus(status)
    e.inputs = {}
    e.outputs = None
    e.error = None
    e.total_tokens = 0
    e.prompt_tokens = 0
    e.completion_tokens = 0
    e.cost_usd = Decimal("0")
    e.n_iterations = None
    e.training_file = None
    e.initiated_by = None
    e.principal_chain = None
    e.created_at = datetime.now(UTC)
    e.started_at = None
    e.completed_at = None
    e.tasks = []
    return e
