"""Integration tests for untested API endpoint handlers.

Covers the actual HTTP endpoints via the test client for:
  - credentials.py: create, list, delete
  - tools_library.py: list (with filters), install
  - agency_import.py: list and import (mocked GitHub)
  - webhooks.py: create, list, delete
  - a2a.py: agent card with crew data, response shape
  - auth/dependencies.py: require_permission, JWT/API-key resolution
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from tests.conftest import API_KEY_HEADER, _bearer, _register_user

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------



# Bug fix applied: credentials.py no longer uses extra={"name": ...}
# which collided with Python's LogRecord.name attribute.
# See commit fixing "name" → "credential_name" in logger.info() calls.


def _clear_credentials_store() -> None:
    """Reset the in-memory credential store between tests."""
    from blackbeard.api.credentials import _credentials, _credentials_lock

    with _credentials_lock:
        _credentials.clear()


def _clear_a2a_cache() -> None:
    """Reset the A2A module-level cache so each test gets a fresh DB query."""
    import blackbeard.api.a2a as _a2a_mod

    _a2a_mod._cache_entry = None


def _clear_tools_library_cache() -> None:
    """Reset the tools library catalog cache so tests reload it."""
    import blackbeard.api.tools_library as _tl_mod

    _tl_mod._catalog = None


async def _get_user_headers(client: AsyncClient, email: str = "handler-test@example.com") -> dict:
    """Register a user and return Bearer token headers."""
    data = await _register_user(client, email=email)
    return _bearer(data["access_token"])


# =========================================================================
# 1. Credentials API — create, list, delete
# =========================================================================


class TestCredentialsCreate:
    """POST /api/v1/credentials."""

    @pytest.fixture(autouse=True)
    def _reset_store(self):
        _clear_credentials_store()
        yield
        _clear_credentials_store()

    @pytest.mark.asyncio
    async def test_create_credential_returns_201_with_masked_value(
        self, client: AsyncClient
    ) -> None:
        headers = await _get_user_headers(client, "cred-create@test.com")
        resp = await client.post(
            "/api/v1/credentials",
            json={
                "name": "my-api-key",
                "type": "api_key",
                "value": "sk-secret-value-1234",
                "description": "Test credential",
            },
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "my-api-key"
        assert data["type"] == "api_key"
        assert data["description"] == "Test credential"
        assert data["masked_value"] == "****"
        assert "sk-secret-value-1234" not in str(data)
        assert data["id"]
        assert data["created_at"]
        assert data["last_used_at"] is None

    @pytest.mark.asyncio
    async def test_create_duplicate_credential_returns_409(self, client: AsyncClient) -> None:
        headers = await _get_user_headers(client, "cred-dup@test.com")
        body = {
            "name": "dup-cred",
            "value": "some-secret-value",
        }
        resp1 = await client.post("/api/v1/credentials", json=body, headers=headers)
        assert resp1.status_code == 201

        resp2 = await client.post("/api/v1/credentials", json=body, headers=headers)
        assert resp2.status_code == 409
        assert "already exists" in resp2.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_credential_requires_user_identity(self, client: AsyncClient) -> None:
        """System API key alone is not enough (require_identity=True)."""
        resp = await client.post(
            "/api/v1/credentials",
            json={"name": "no-user", "value": "secret"},
            headers=API_KEY_HEADER,
        )
        assert resp.status_code == 401


class TestCredentialsList:
    """GET /api/v1/credentials."""

    @pytest.fixture(autouse=True)
    def _reset_store(self):
        _clear_credentials_store()
        yield
        _clear_credentials_store()

    @pytest.mark.asyncio
    async def test_list_credentials_returns_200_with_items(self, client: AsyncClient) -> None:
        headers = await _get_user_headers(client, "cred-list@test.com")

        # Create two credentials
        for name in ("cred-a", "cred-b"):
            resp = await client.post(
                "/api/v1/credentials",
                json={"name": name, "value": f"secret-{name}"},
                headers=headers,
            )
            assert resp.status_code == 201

        resp = await client.get("/api/v1/credentials", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2
        assert all(item["masked_value"] == "****" for item in data["items"])

    @pytest.mark.asyncio
    async def test_list_credentials_empty(self, client: AsyncClient) -> None:
        headers = await _get_user_headers(client, "cred-empty@test.com")
        resp = await client.get("/api/v1/credentials", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []


class TestCredentialsDelete:
    """DELETE /api/v1/credentials/{credential_id}."""

    @pytest.fixture(autouse=True)
    def _reset_store(self):
        _clear_credentials_store()
        yield
        _clear_credentials_store()

    @pytest.mark.asyncio
    async def test_delete_credential_returns_204(self, client: AsyncClient) -> None:
        headers = await _get_user_headers(client, "cred-del@test.com")
        create_resp = await client.post(
            "/api/v1/credentials",
            json={"name": "to-delete", "value": "secret-val"},
            headers=headers,
        )
        assert create_resp.status_code == 201
        cred_id = create_resp.json()["id"]

        del_resp = await client.delete(f"/api/v1/credentials/{cred_id}", headers=headers)
        assert del_resp.status_code == 204

        # Verify it is gone
        list_resp = await client.get("/api/v1/credentials", headers=headers)
        assert list_resp.json()["total"] == 0

    @pytest.mark.asyncio
    async def test_delete_nonexistent_credential_is_idempotent(self, client: AsyncClient) -> None:
        headers = await _get_user_headers(client, "cred-del-noop@test.com")
        fake_id = str(uuid.uuid4())
        resp = await client.delete(f"/api/v1/credentials/{fake_id}", headers=headers)
        # Delete is idempotent — returns 204 even if not found
        assert resp.status_code == 204


# =========================================================================
# 2. Tools Library API — list with filters, install
# =========================================================================


class TestToolsLibraryList:
    """GET /api/v1/tools/library."""

    @pytest.fixture(autouse=True)
    def _reset_catalog(self):
        _clear_tools_library_cache()
        yield
        _clear_tools_library_cache()

    @pytest.mark.asyncio
    async def test_list_returns_tools_and_categories(self, client: AsyncClient) -> None:
        headers = await _get_user_headers(client, "tools-list@test.com")
        resp = await client.get("/api/v1/tools/library", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["tools"], list)
        assert data["total"] > 0
        assert isinstance(data["categories"], list)
        assert len(data["categories"]) > 0

    @pytest.mark.asyncio
    async def test_list_filter_by_category(self, client: AsyncClient) -> None:
        headers = await _get_user_headers(client, "tools-cat@test.com")
        resp = await client.get("/api/v1/tools/library?category=web", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] > 0
        assert all(t["category"] == "web" for t in data["tools"])

    @pytest.mark.asyncio
    async def test_list_filter_by_search(self, client: AsyncClient) -> None:
        headers = await _get_user_headers(client, "tools-search@test.com")
        resp = await client.get("/api/v1/tools/library?search=csv", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        # The CSV Reader tool should match
        slugs = [t["slug"] for t in data["tools"]]
        assert "csv-reader" in slugs

    @pytest.mark.asyncio
    async def test_list_no_match_returns_empty(self, client: AsyncClient) -> None:
        headers = await _get_user_headers(client, "tools-nomatch@test.com")
        resp = await client.get("/api/v1/tools/library?search=zzzznonexistentzzz", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["tools"] == []
        # Categories should still be present (all categories, not filtered)
        assert len(data["categories"]) > 0

    @pytest.mark.asyncio
    async def test_list_works_with_system_api_key(self, client: AsyncClient) -> None:
        """List endpoint does not require user identity (no require_identity=True)."""
        resp = await client.get("/api/v1/tools/library", headers=API_KEY_HEADER)
        assert resp.status_code == 200
        assert resp.json()["total"] > 0


class TestToolsLibraryInstall:
    """POST /api/v1/tools/library/install."""

    @pytest.fixture(autouse=True)
    def _reset_catalog(self):
        _clear_tools_library_cache()

    @pytest.mark.asyncio
    async def test_install_valid_slug(self, client: AsyncClient) -> None:
        headers = await _get_user_headers(client, "tools-inst@test.com")
        resp = await client.post(
            "/api/v1/tools/library/install",
            json={"slugs": ["web-search"]},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["installed"] == 1
        assert data["skipped"] == 0
        assert data["errors"] == []

        # Verify the tool resource was created
        tool_resp = await client.get("/api/v1/tools/web-search", headers=headers)
        assert tool_resp.status_code == 200

    @pytest.mark.asyncio
    async def test_install_unknown_slug_returns_errors(self, client: AsyncClient) -> None:
        headers = await _get_user_headers(client, "tools-bad@test.com")
        resp = await client.post(
            "/api/v1/tools/library/install",
            json={"slugs": ["nonexistent-tool"]},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["installed"] == 0
        assert len(data["errors"]) == 1
        assert "not found" in data["errors"][0]

    @pytest.mark.asyncio
    async def test_install_duplicate_slug_upserts(self, client: AsyncClient) -> None:
        """ResourceService.create() does upsert, so duplicate installs succeed."""
        headers = await _get_user_headers(client, "tools-dup@test.com")
        # Install once
        resp1 = await client.post(
            "/api/v1/tools/library/install",
            json={"slugs": ["csv-reader"]},
            headers=headers,
        )
        assert resp1.status_code == 200
        assert resp1.json()["installed"] == 1

        # Install again — ResourceService.create() upserts, so it counts as installed
        resp2 = await client.post(
            "/api/v1/tools/library/install",
            json={"slugs": ["csv-reader"]},
            headers=headers,
        )
        assert resp2.status_code == 200
        # Upsert path: the resource is updated (not skipped)
        assert resp2.json()["installed"] == 1
        assert resp2.json()["errors"] == []

    @pytest.mark.asyncio
    async def test_install_mixed_valid_and_invalid(self, client: AsyncClient) -> None:
        headers = await _get_user_headers(client, "tools-mix@test.com")
        resp = await client.post(
            "/api/v1/tools/library/install",
            json={"slugs": ["json-reader", "does-not-exist"]},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["installed"] == 1
        assert len(data["errors"]) == 1


# =========================================================================
# 3. Agency Import API — list and import (mocked GitHub)
# =========================================================================


SAMPLE_AGENT_MD = """---
name: Test Engineer
description: A test engineer agent
color: green
---

# Test Engineer Agent Personality

## Your Identity
- **Role**: Quality assurance and testing specialist
- **Personality**: Thorough, detail-oriented

## Core Mission
- Ensure software quality through comprehensive testing
- Build automated test suites for all systems
"""


def _make_mock_httpx_client(
    *, dir_files: list[dict] | None = None, file_content: str = SAMPLE_AGENT_MD
) -> AsyncMock:
    """Build a mock httpx.AsyncClient for GitHub API calls."""
    mock_client = AsyncMock()

    async def mock_get(url: str, **kwargs) -> MagicMock:
        resp = MagicMock()
        if "/contents/" in url:
            # GitHub directory listing API
            resp.status_code = 200
            resp.json.return_value = dir_files or [
                {"name": "testing-test-engineer.md", "path": "testing/testing-test-engineer.md"},
            ]
        elif "raw.githubusercontent.com" in url:
            # Raw file content
            resp.status_code = 200
            resp.text = file_content
        else:
            resp.status_code = 404
        return resp

    mock_client.get = mock_get
    return mock_client


class TestAgencyImportList:
    """GET /api/v1/import/agency-agents."""

    @pytest.mark.asyncio
    async def test_list_agency_agents_returns_agents(self, client: AsyncClient) -> None:
        headers = await _get_user_headers(client, "agency-list@test.com")

        mock_client = _make_mock_httpx_client()

        with patch("blackbeard.api.agency_import.get_client", return_value=mock_client):
            resp = await client.get(
                "/api/v1/import/agency-agents?division=testing",
                headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["agents"], list)
        assert isinstance(data["divisions"], list)
        assert len(data["divisions"]) > 0
        # We mocked one file in the testing division
        assert data["total"] >= 1
        agent = data["agents"][0]
        assert agent["name"] == "Test Engineer"
        assert agent["slug"] == "test-engineer"
        assert "testing" in agent["role"].lower() or "quality" in agent["role"].lower()

    @pytest.mark.asyncio
    async def test_list_agency_agents_empty_division(self, client: AsyncClient) -> None:
        import blackbeard.api.agency_import as _aim
        _aim._division_cache.clear()
        _aim._file_cache.clear()
        headers = await _get_user_headers(client, "agency-empty@test.com")

        mock_client = AsyncMock()

        async def mock_get(url: str, **kwargs):
            resp = MagicMock()
            if "/contents/" in url:
                resp.status_code = 200
                resp.json.return_value = []  # No files in this division
            else:
                resp.status_code = 404
            return resp

        mock_client.get = mock_get

        with patch("blackbeard.api.agency_import.get_client", return_value=mock_client):
            resp = await client.get(
                "/api/v1/import/agency-agents?division=testing",
                headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["agents"] == []

    @pytest.mark.asyncio
    async def test_list_agency_agents_requires_user_identity(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/import/agency-agents", headers=API_KEY_HEADER)
        assert resp.status_code == 401


class TestAgencyImportCreate:
    """POST /api/v1/import/agency-agents."""

    @pytest.mark.asyncio
    async def test_import_agency_agent_creates_resource(self, client: AsyncClient) -> None:
        headers = await _get_user_headers(client, "agency-imp@test.com")

        mock_client = _make_mock_httpx_client()

        with patch("blackbeard.api.agency_import.get_client", return_value=mock_client):
            resp = await client.post(
                "/api/v1/import/agency-agents",
                json={"slugs": ["testing-test-engineer"]},
                headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["imported"] == 1
        assert data["skipped"] == 0
        assert data["errors"] == []

        # Verify the agent resource was created
        agent_resp = await client.get("/api/v1/agents/test-engineer", headers=headers)
        assert agent_resp.status_code == 200

    @pytest.mark.asyncio
    async def test_import_not_found_slug_returns_error(self, client: AsyncClient) -> None:
        headers = await _get_user_headers(client, "agency-notfound@test.com")

        mock_client = _make_mock_httpx_client(dir_files=[])

        with patch("blackbeard.api.agency_import.get_client", return_value=mock_client):
            resp = await client.post(
                "/api/v1/import/agency-agents",
                json={"slugs": ["nonexistent-agent"]},
                headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["imported"] == 0
        assert len(data["errors"]) == 1
        assert "not found" in data["errors"][0]

    @pytest.mark.asyncio
    async def test_import_duplicate_upserts(self, client: AsyncClient) -> None:
        """ResourceService.create() does upsert, so duplicate imports succeed."""
        headers = await _get_user_headers(client, "agency-dup@test.com")

        mock_client = _make_mock_httpx_client()

        with patch("blackbeard.api.agency_import.get_client", return_value=mock_client):
            # First import
            resp1 = await client.post(
                "/api/v1/import/agency-agents",
                json={"slugs": ["testing-test-engineer"]},
                headers=headers,
            )
            assert resp1.json()["imported"] == 1

            # Second import — upserts (ResourceService.create does upsert)
            resp2 = await client.post(
                "/api/v1/import/agency-agents",
                json={"slugs": ["testing-test-engineer"]},
                headers=headers,
            )
            assert resp2.json()["imported"] == 1
            assert resp2.json()["errors"] == []


# =========================================================================
# 4. Webhooks API — create, list, delete
# =========================================================================


class TestWebhooksCreate:
    """POST /api/v1/webhooks."""

    @pytest.mark.asyncio
    async def test_create_webhook_returns_201_with_secret(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/webhooks",
            json={
                "url": "https://example.com/webhook",
                "events": ["crew_started", "crew_completed"],
            },
            headers=API_KEY_HEADER,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["url"] == "https://example.com/webhook"
        assert data["events"] == ["crew_started", "crew_completed"]
        assert data["active"] is True
        assert "secret" in data
        assert len(data["secret"]) > 0
        assert data["id"]

    @pytest.mark.asyncio
    async def test_create_webhook_auto_generates_secret(self, client: AsyncClient) -> None:
        """When no secret is provided, one is auto-generated."""
        resp = await client.post(
            "/api/v1/webhooks",
            json={"url": "https://example.com/auto-secret"},
            headers=API_KEY_HEADER,
        )
        assert resp.status_code == 201
        assert len(resp.json()["secret"]) >= 16

    @pytest.mark.asyncio
    async def test_create_webhook_with_custom_secret(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/webhooks",
            json={
                "url": "https://example.com/custom-secret",
                "secret": "my-custom-signing-secret-value",
            },
            headers=API_KEY_HEADER,
        )
        assert resp.status_code == 201
        assert resp.json()["secret"] == "my-custom-signing-secret-value"

    @pytest.mark.asyncio
    async def test_create_webhook_empty_events_means_all(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/webhooks",
            json={"url": "https://example.com/all-events", "events": []},
            headers=API_KEY_HEADER,
        )
        assert resp.status_code == 201
        assert resp.json()["events"] == []

    @pytest.mark.asyncio
    async def test_create_webhook_rejects_embedded_credentials(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/webhooks",
            json={"url": "https://user:pass@example.com/hook"},
            headers=API_KEY_HEADER,
        )
        assert resp.status_code == 422
        assert "credentials" in resp.json()["detail"].lower()


class TestWebhooksList:
    """GET /api/v1/webhooks."""

    @pytest.mark.asyncio
    async def test_list_webhooks_returns_items(self, client: AsyncClient) -> None:
        # Create a webhook first
        create_resp = await client.post(
            "/api/v1/webhooks",
            json={"url": "https://example.com/list-test"},
            headers=API_KEY_HEADER,
        )
        assert create_resp.status_code == 201

        resp = await client.get("/api/v1/webhooks", headers=API_KEY_HEADER)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["items"], list)
        assert data["total"] >= 1
        # Secret should NOT be returned in list
        for item in data["items"]:
            assert "secret" not in item

    @pytest.mark.asyncio
    async def test_list_webhooks_empty(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/webhooks", headers=API_KEY_HEADER)
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0


class TestWebhooksDelete:
    """DELETE /api/v1/webhooks/{webhook_id}."""

    @pytest.mark.asyncio
    async def test_delete_webhook_returns_204(self, client: AsyncClient) -> None:
        create_resp = await client.post(
            "/api/v1/webhooks",
            json={"url": "https://example.com/to-delete"},
            headers=API_KEY_HEADER,
        )
        assert create_resp.status_code == 201
        webhook_id = create_resp.json()["id"]

        del_resp = await client.delete(f"/api/v1/webhooks/{webhook_id}", headers=API_KEY_HEADER)
        assert del_resp.status_code == 204

        # Verify it is gone
        list_resp = await client.get("/api/v1/webhooks", headers=API_KEY_HEADER)
        webhook_ids = [w["id"] for w in list_resp.json()["items"]]
        assert webhook_id not in webhook_ids

    @pytest.mark.asyncio
    async def test_delete_nonexistent_webhook_is_idempotent(self, client: AsyncClient) -> None:
        fake_id = str(uuid.uuid4())
        resp = await client.delete(f"/api/v1/webhooks/{fake_id}", headers=API_KEY_HEADER)
        # Idempotent — returns 204 even if not found
        assert resp.status_code == 204


# =========================================================================
# 5. A2A Agent Card — card with crew data, response shape
# =========================================================================


class TestA2AAgentCard:
    """GET /.well-known/agent-card.json."""

    @pytest.fixture(autouse=True)
    def _reset_cache(self):
        _clear_a2a_cache()
        yield
        _clear_a2a_cache()

    @pytest.mark.asyncio
    async def test_agent_card_with_a2a_crew_includes_skills(self, client: AsyncClient) -> None:
        # Create agent, task, and crew
        await client.post(
            "/api/v1/agents",
            json={
                "apiVersion": "blackbeard/v1",
                "kind": "Agent",
                "metadata": {"name": "card-agent", "project": "default"},
                "spec": {
                    "role": "Test Agent",
                    "goal": "Testing",
                    "backstory": "A test agent",
                },
            },
            headers=API_KEY_HEADER,
        )
        await client.post(
            "/api/v1/tasks",
            json={
                "apiVersion": "blackbeard/v1",
                "kind": "Task",
                "metadata": {"name": "card-task", "project": "default"},
                "spec": {
                    "description": "Perform a test task\nWith details",
                    "expected_output": "Test results",
                    "agent": "ref:agents/card-agent",
                },
            },
            headers=API_KEY_HEADER,
        )
        await client.post(
            "/api/v1/crews",
            json={
                "apiVersion": "blackbeard/v1",
                "kind": "Crew",
                "metadata": {"name": "card-crew", "project": "default"},
                "spec": {
                    "process": "sequential",
                    "agents": ["ref:agents/card-agent"],
                    "tasks": ["ref:tasks/card-task"],
                    "description": "A crew for card testing",
                    "a2a": {"enabled": True},
                },
            },
            headers=API_KEY_HEADER,
        )

        _clear_a2a_cache()
        resp = await client.get("/.well-known/agent-card.json")
        assert resp.status_code == 200
        data = resp.json()

        assert len(data["agents"]) >= 1
        crew_card = next(a for a in data["agents"] if a["name"] == "card-crew")
        assert crew_card["description"] == "A crew for card testing"
        assert len(crew_card["skills"]) == 1
        assert crew_card["skills"][0]["id"] == "card-task"
        assert crew_card["skills"][0]["name"] == "Perform a test task"
        assert crew_card["skills"][0]["description"] == "Test results"

    @pytest.mark.asyncio
    async def test_agent_card_response_shape(self, client: AsyncClient) -> None:
        await client.post(
            "/api/v1/crews",
            json={
                "apiVersion": "blackbeard/v1",
                "kind": "Crew",
                "metadata": {"name": "shape-test-crew", "project": "default"},
                "spec": {
                    "process": "sequential",
                    "agents": ["ref:agents/default"],
                    "tasks": ["ref:tasks/default"],
                    "description": "Shape test",
                    "a2a": {"enabled": True},
                },
            },
            headers=API_KEY_HEADER,
        )

        _clear_a2a_cache()
        resp = await client.get("/.well-known/agent-card.json")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["agents"]) >= 1

        agent = data["agents"][0]
        # Provider block
        assert agent["provider"]["organization"] == "Blackbeard"
        assert "url" in agent["provider"]
        # Capabilities
        assert agent["capabilities"]["streaming"] is True
        assert agent["capabilities"]["pushNotifications"] is False
        # Authentication
        assert "bearer" in agent["authentication"]["schemes"]
        assert "apiKey" in agent["authentication"]["schemes"]
        # IO modes
        assert agent["defaultInputModes"] == ["application/json"]
        assert agent["defaultOutputModes"] == ["application/json"]

    @pytest.mark.asyncio
    async def test_agent_card_is_public_endpoint(self, client: AsyncClient) -> None:
        """The A2A endpoint does not require authentication."""
        resp = await client.get("/.well-known/agent-card.json")
        assert resp.status_code == 200
        assert "agents" in resp.json()


# =========================================================================
# 6. Auth Dependencies — require_permission, JWT/API-key resolution
# =========================================================================


class TestRequirePermission:
    """Tests for require_permission RBAC dependency."""

    @pytest.mark.asyncio
    async def test_require_permission_allows_authenticated_user(self, client: AsyncClient) -> None:
        """When enforce_rbac is False (default), any authenticated user passes."""
        headers = await _get_user_headers(client, "rbac-allow@test.com")
        resp = await client.get("/api/v1/credentials", headers=headers)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_require_permission_blocks_system_key_for_identity_endpoints(
        self, client: AsyncClient
    ) -> None:
        """Endpoints with require_identity=True reject system API key without user."""
        resp = await client.get("/api/v1/credentials", headers=API_KEY_HEADER)
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_require_permission_allows_system_key_for_non_identity_endpoints(
        self, client: AsyncClient
    ) -> None:
        """Endpoints without require_identity work with system API key."""
        resp = await client.get("/api/v1/webhooks", headers=API_KEY_HEADER)
        assert resp.status_code == 200


class TestJWTAuth:
    """Tests for JWT-based authentication."""

    @pytest.mark.asyncio
    async def test_jwt_resolves_user_for_protected_endpoint(self, client: AsyncClient) -> None:
        data = await _register_user(client, email="jwt-resolve@test.com")
        headers = _bearer(data["access_token"])
        resp = await client.get("/api/v1/auth/me", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["email"] == "jwt-resolve@test.com"

    @pytest.mark.asyncio
    async def test_jwt_expired_returns_401(self, client: AsyncClient) -> None:
        from datetime import UTC, datetime, timedelta

        import jwt as pyjwt

        from blackbeard.config import settings

        payload = {
            "sub": str(uuid.uuid4()),
            "type": "access",
            "jti": uuid.uuid4().hex,
            "iss": "blackbeard",
            "aud": "blackbeard",
            "iat": datetime.now(UTC) - timedelta(hours=2),
            "nbf": datetime.now(UTC) - timedelta(hours=2),
            "exp": datetime.now(UTC) - timedelta(hours=1),
        }
        token = pyjwt.encode(
            payload,
            settings.jwt_secret.get_secret_value(),
            algorithm="HS256",
        )
        resp = await client.get("/api/v1/auth/me", headers=_bearer(token))
        assert resp.status_code == 401


class TestAPIKeyAuth:
    """Tests for API key authentication."""

    @pytest.mark.asyncio
    async def test_api_key_resolves_for_resource_endpoints(self, client: AsyncClient) -> None:
        """System API key grants access to resource endpoints."""
        resp = await client.get("/api/v1/agents", headers=API_KEY_HEADER)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_no_auth_returns_401_for_protected_endpoints(self, client: AsyncClient) -> None:
        """Protected endpoints without any auth return 401."""
        resp = await client.get("/api/v1/agents")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_api_key_returns_401(self, client: AsyncClient) -> None:
        """An invalid API key is rejected by the middleware."""
        resp = await client.get(
            "/api/v1/agents",
            headers={"X-API-Key": "completely-wrong-key-value"},
        )
        assert resp.status_code == 401
        assert "api key" in resp.json()["detail"].lower()
