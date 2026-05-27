"""Tests for remaining API endpoint coverage gaps.

Targets uncovered lines in:
  - api/webhooks.py: create, list, delete REST endpoints
  - api/audit.py: total count path (line 95-104)
  - api/copilot.py: success path through endpoint
  - api/automations.py: disabled webhook, flow target
  - api/marketplace.py: git clone error paths, validation error import
  - api/collaboration.py: non-dict message, room already gone
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import API_KEY_HEADER, make_resource

# ---------------------------------------------------------------------------
# Webhook REST API endpoint tests (api/webhooks.py)
# ---------------------------------------------------------------------------


async def test_webhook_create_and_list(client: AsyncClient, db_session: AsyncSession):
    """POST /webhooks creates a webhook, GET /webhooks lists it."""
    # Create
    resp = await client.post(
        "/api/v1/webhooks",
        json={
            "url": "http://example.com/hook",
            "events": ["execution_completed"],
        },
        headers=API_KEY_HEADER,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "id" in data
    assert data["url"] == "http://example.com/hook"
    assert data["events"] == ["execution_completed"]
    assert data["active"] is True
    assert "secret" in data  # secret shown on create
    assert len(data["secret"]) > 0

    # Location header
    assert "Location" in resp.headers

    # List
    webhook_id = data["id"]
    list_resp = await client.get("/api/v1/webhooks", headers=API_KEY_HEADER)
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert "items" in list_data
    items = list_data["items"]
    assert isinstance(items, list)
    listed_ids = [w["id"] for w in items]
    assert webhook_id in listed_ids, "Created webhook must appear in list"
    listed_hook = next(w for w in items if w["id"] == webhook_id)
    assert listed_hook["url"] == "http://example.com/hook"
    assert "secret" not in listed_hook, "Secret must not be exposed in list response"


async def test_webhook_create_with_custom_secret(client: AsyncClient):
    """POST /webhooks with custom secret should use it."""
    resp = await client.post(
        "/api/v1/webhooks",
        json={
            "url": "http://example.com/hook2",
            "secret": "my-custom-secret-1234567890",
        },
        headers=API_KEY_HEADER,
    )
    assert resp.status_code == 201
    assert resp.json()["secret"] == "my-custom-secret-1234567890"


async def test_webhook_create_rejects_embedded_credentials(client: AsyncClient):
    """POST /webhooks with URL containing credentials returns 422."""
    resp = await client.post(
        "/api/v1/webhooks",
        json={"url": "http://user:pass@example.com/hook"},
        headers=API_KEY_HEADER,
    )
    assert resp.status_code == 422
    assert "credentials" in resp.json()["detail"].lower()


async def test_webhook_delete(client: AsyncClient, db_session: AsyncSession):
    """DELETE /webhooks/{id} removes the webhook."""
    # Create first
    create_resp = await client.post(
        "/api/v1/webhooks",
        json={"url": "http://example.com/delete-me"},
        headers=API_KEY_HEADER,
    )
    assert create_resp.status_code == 201
    webhook_id = create_resp.json()["id"]

    # Delete
    del_resp = await client.delete(
        f"/api/v1/webhooks/{webhook_id}",
        headers=API_KEY_HEADER,
    )
    assert del_resp.status_code == 204

    # Verify gone from list
    list_resp = await client.get("/api/v1/webhooks", headers=API_KEY_HEADER)
    ids = [w["id"] for w in list_resp.json()["items"]]
    assert webhook_id not in ids


async def test_webhook_delete_nonexistent(client: AsyncClient):
    """DELETE /webhooks/{id} for nonexistent webhook returns 204 (idempotent)."""
    fake_id = str(uuid.uuid4())
    resp = await client.delete(
        f"/api/v1/webhooks/{fake_id}",
        headers=API_KEY_HEADER,
    )
    assert resp.status_code == 204


async def test_webhook_create_requires_auth(client: AsyncClient):
    """POST /webhooks without auth returns 401."""
    resp = await client.post(
        "/api/v1/webhooks",
        json={"url": "http://example.com/hook"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Audit log: total count path coverage (lines 95-104)
# ---------------------------------------------------------------------------


async def test_audit_logs_total_count_path(client: AsyncClient, db_session: AsyncSession):
    """Audit log with offset + limit triggering count query."""
    # Register user
    reg_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "count-test@example.com",
            "password": "securepass123",
            "display_name": "Count Test",
        },
    )
    assert reg_resp.status_code == 201
    token = reg_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Create multiple resources to generate audit entries
    for i in range(5):
        await client.post(
            "/api/v1/agents",
            json={
                "apiVersion": "blackbeard/v1",
                "kind": "Agent",
                "metadata": {"name": f"count-agent-{i}"},
                "spec": {
                    "role": "Role",
                    "goal": "Goal",
                    "backstory": "Backstory",
                },
            },
            headers=headers,
        )

    # Request with limit=1 to trigger the count query branch
    resp = await client.get(
        "/api/v1/audit-logs?limit=1&offset=0",
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["limit"] == 1
    assert len(body["items"]) == 1
    assert body["total"] >= 5, (
        f"Created 5 resources, expected >=5 audit entries, got {body['total']}"
    )
    assert body["has_more"] is True


async def test_audit_logs_filter_by_resource_id(client: AsyncClient):
    """Audit log endpoint filters by resource_id."""
    reg = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "resid-test@example.com",
            "password": "securepass123",
            "display_name": "ResId Test",
        },
    )
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    await client.post(
        "/api/v1/agents",
        json={
            "apiVersion": "blackbeard/v1",
            "kind": "Agent",
            "metadata": {"name": "resid-agent"},
            "spec": {"role": "R", "goal": "G", "backstory": "B"},
        },
        headers=headers,
    )

    resp = await client.get(
        "/api/v1/audit-logs?resource_id=resid-agent",
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    for item in body["items"]:
        assert item["resource_id"] == "resid-agent"


# ---------------------------------------------------------------------------
# Automation: disabled webhook trigger returns 409
# ---------------------------------------------------------------------------


async def test_webhook_trigger_disabled_automation(client: AsyncClient):
    """Webhook trigger on disabled automation returns 409."""
    payload = {
        "apiVersion": "blackbeard/v1",
        "kind": "Automation",
        "metadata": {"name": "dis-wh-auto"},
        "spec": {
            "target": {"kind": "Crew", "name": "test-crew"},
            "trigger": {"type": "webhook", "webhook_secret": "secret-12345-test"},
            "enabled": False,
            "inputs": {},
            "max_concurrent": 1,
        },
    }
    await client.post("/api/v1/automations", json=payload, headers=API_KEY_HEADER)

    resp = await client.post(
        "/api/v1/automations/dis-wh-auto/webhook",
        json={"secret": "secret-12345-test", "inputs": {}},
        headers=API_KEY_HEADER,
    )
    assert resp.status_code == 409
    assert "disabled" in resp.json()["detail"].lower()


async def test_trigger_nonexistent_webhook_automation(client: AsyncClient):
    """Webhook trigger on nonexistent automation returns 404."""
    resp = await client.post(
        "/api/v1/automations/nonexistent-auto/webhook",
        json={"secret": "any-secret-12345", "inputs": {}},
        headers=API_KEY_HEADER,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Marketplace: _parse_yaml_resources with multi-document YAML
# ---------------------------------------------------------------------------


def test_parse_yaml_multidoc():
    """_parse_yaml_resources handles multi-document YAML with valid resources."""
    import tempfile

    from blackbeard.api.marketplace import _parse_yaml_resources

    yaml_content = """\
---
apiVersion: blackbeard/v1
kind: Agent
metadata:
  name: agent-one
spec:
  role: R
  goal: G
  backstory: B
---
apiVersion: blackbeard/v1
kind: Task
metadata:
  name: task-one
spec:
  description: D
  expected_output: E
  agent: "ref:agents/agent-one"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = Path(tmpdir) / "multi.yaml"
        filepath.write_text(yaml_content)

        resources, errors = _parse_yaml_resources([filepath])
        assert len(resources) == 2
        assert resources[0]["kind"] == "Agent"
        assert resources[1]["kind"] == "Task"
        assert len(errors) == 0


def test_parse_yaml_oserror():
    """_parse_yaml_resources handles read errors gracefully."""
    from blackbeard.api.marketplace import _parse_yaml_resources

    # Create a path that exists stat-wise but will fail on read
    fake_path = MagicMock()
    fake_path.name = "broken.yaml"
    fake_path.stat.return_value = MagicMock(st_size=100)
    fake_path.read_text.side_effect = OSError("Permission denied")

    resources, errors = _parse_yaml_resources([fake_path])
    assert len(resources) == 0
    assert len(errors) == 1
    assert "read error" in errors[0].lower()


# ---------------------------------------------------------------------------
# Marketplace: import with validation error (bad resource schema)
# ---------------------------------------------------------------------------


async def test_marketplace_import_builtin_with_bad_resource(
    client: AsyncClient,
):
    """Import built-in with a resource that fails schema validation."""
    from blackbeard.api import marketplace as marketplace_mod

    original_examples = marketplace_mod._EXAMPLES_DIR

    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        research_dir = Path(tmpdir) / "research-crew"
        research_dir.mkdir()

        # Write a resource that passes model_validate but has an unknown kind
        yaml_content = """\
apiVersion: blackbeard/v1
kind: Agent
metadata:
  name: good-agent
  namespace: default
spec:
  role: R
  goal: G
  backstory: B
---
apiVersion: blackbeard/v1
kind: UnknownKind
metadata:
  name: bad-resource
spec:
  foo: bar
"""
        (research_dir / "resources.yaml").write_text(yaml_content)

        marketplace_mod._EXAMPLES_DIR = Path(tmpdir)
        try:
            resp = await client.post(
                "/api/v1/marketplace/import",
                json={"url": "built-in"},
                headers=API_KEY_HEADER,
            )
            assert resp.status_code == 200
            data = resp.json()
            # The good agent should import, the bad UnknownKind should error
            assert data["imported"] == 1, (
                f"Expected exactly 1 imported (the Agent), got {data['imported']}"
            )
            assert data["errors"] >= 1, (
                f"Expected at least 1 error (the UnknownKind), got {data['errors']}"
            )
        finally:
            marketplace_mod._EXAMPLES_DIR = original_examples


# ---------------------------------------------------------------------------
# Collaboration: non-dict message handling
# ---------------------------------------------------------------------------


def test_collaboration_non_dict_message_ignored():
    """WebSocket that sends non-dict JSON should have message ignored."""
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    from blackbeard.api.collaboration import _rooms, router
    from blackbeard.auth.api_key import _EXPECTED_API_KEY

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    auth_qs = f"?api_key={_EXPECTED_API_KEY}"
    _rooms.clear()
    with (
        TestClient(app) as tc,
        tc.websocket_connect(f"/api/v1/ws/collab/test-nondict{auth_qs}") as ws1,
    ):
        ws1.receive_json()  # room_state

        with tc.websocket_connect(f"/api/v1/ws/collab/test-nondict{auth_qs}") as ws2:
            ws2.receive_json()  # room_state
            ws1.receive_json()  # participant_joined

            # Send non-dict (it's a list)
            ws1.send_json(["not", "a", "dict"])

            # Send valid message to verify connection still works
            ws1.send_json({"type": "node_add", "data": {"id": "n1"}})
            received = ws2.receive_json()
            assert received["type"] == "node_add"
    _rooms.clear()


# ---------------------------------------------------------------------------
# Copilot API: edge cases
# ---------------------------------------------------------------------------


async def test_copilot_endpoint_transport_error(client: AsyncClient, db_session: AsyncSession):
    """Copilot endpoint with transport error returns 502."""
    from blackbeard.kinds import ResourceKind

    r = make_resource(
        ResourceKind.LLM_CONNECTION,
        "transport-llm",
        {"provider": "ollama", "model": "llama3"},
    )
    db_session.add(r)
    await db_session.commit()

    import httpx

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))

    with patch("blackbeard.engine.copilot._get_copilot_client", return_value=mock_client):
        resp = await client.post(
            "/api/v1/copilot/generate",
            json={"prompt": "Build me a research crew that finds facts about topics"},
            headers=API_KEY_HEADER,
        )

    assert resp.status_code == 502
    assert "failed" in resp.json()["detail"].lower()


async def test_copilot_endpoint_with_namespace(client: AsyncClient, db_session: AsyncSession):
    """Copilot endpoint accepts namespace parameter."""
    resp = await client.post(
        "/api/v1/copilot/generate",
        json={
            "prompt": "Build me a research crew that finds facts about topics",
            "namespace": "custom-ns",
        },
        headers=API_KEY_HEADER,
    )
    # Will return 424 (no LLM in custom-ns) but should not return 422
    assert resp.status_code == 424


# ---------------------------------------------------------------------------
# Webhook REST API: SSRF validation
# ---------------------------------------------------------------------------


async def test_webhook_create_rejects_ssrf(client: AsyncClient):
    """POST /webhooks with internal URL should be rejected."""
    resp = await client.post(
        "/api/v1/webhooks",
        json={"url": "http://127.0.0.1:8080/hook"},
        headers=API_KEY_HEADER,
    )
    # Should be rejected by SSRF check (422)
    assert resp.status_code == 422


async def test_webhook_list_returns_list(client: AsyncClient):
    """GET /webhooks returns a paginated list of webhook objects."""
    resp = await client.get("/api/v1/webhooks", headers=API_KEY_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert "has_more" in data
    for item in data["items"]:
        assert "id" in item
        assert "url" in item


# ---------------------------------------------------------------------------
# Automation trigger with overridden inputs
# ---------------------------------------------------------------------------


async def test_trigger_automation_with_custom_inputs(client: AsyncClient):
    """POST /automations/{name}/trigger accepts custom inputs without validation error."""
    payload = {
        "apiVersion": "blackbeard/v1",
        "kind": "Automation",
        "metadata": {"name": "input-auto"},
        "spec": {
            "target": {"kind": "Crew", "name": "test-crew"},
            "trigger": {"type": "api"},
            "enabled": True,
            "inputs": {"topic": "default-topic"},
            "max_concurrent": 1,
        },
    }
    await client.post("/api/v1/automations", json=payload, headers=API_KEY_HEADER)

    resp = await client.post(
        "/api/v1/automations/input-auto/trigger",
        json={"inputs": {"topic": "override-topic", "extra": "value"}},
        headers=API_KEY_HEADER,
    )
    # Will be 404 because target crew doesn't exist, but the merge happens before
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Automation trigger: Flow target path
# ---------------------------------------------------------------------------


async def test_trigger_automation_flow_target(client: AsyncClient):
    """POST /automations/{name}/trigger with Flow target kind."""
    payload = {
        "apiVersion": "blackbeard/v1",
        "kind": "Automation",
        "metadata": {"name": "flow-auto"},
        "spec": {
            "target": {"kind": "Flow", "name": "test-flow"},
            "trigger": {"type": "api"},
            "enabled": True,
            "inputs": {},
            "max_concurrent": 1,
        },
    }
    await client.post("/api/v1/automations", json=payload, headers=API_KEY_HEADER)

    resp = await client.post(
        "/api/v1/automations/flow-auto/trigger",
        json={"inputs": {}},
        headers=API_KEY_HEADER,
    )
    # Flow doesn't exist → ExecutionNotFoundError → 404
    assert resp.status_code == 404
