"""Tests for automation triggers (Feature 1)."""

from __future__ import annotations

import pytest

from tests.conftest import API_KEY_HEADER


def _automation_payload(
    name="my-auto",
    trigger_type="cron",
    cron="*/5 * * * *",
    webhook_secret=None,
    target_kind="Crew",
    target_name="test-crew",
    enabled=True,
):
    """Build a valid Automation resource payload."""
    trigger = {"type": trigger_type}
    if cron and trigger_type == "cron":
        trigger["cron"] = cron
    if webhook_secret and trigger_type == "webhook":
        trigger["webhook_secret"] = webhook_secret
    return {
        "apiVersion": "blackbeard/v1",
        "kind": "Automation",
        "metadata": {"name": name, "project": "default"},
        "spec": {
            "target": {"kind": target_kind, "name": target_name},
            "trigger": trigger,
            "enabled": enabled,
            "inputs": {"topic": "AI trends"},
            "max_concurrent": 1,
        },
    }


# ── Schema & CRUD tests ──────────────────────────────────────────────


async def test_create_automation_cron(client):
    """Automation with cron trigger can be created."""
    payload = _automation_payload(trigger_type="cron", cron="0 * * * *")
    r = await client.post("/api/v1/automations", json=payload, headers=API_KEY_HEADER)
    assert r.status_code == 201
    data = r.json()
    assert data["kind"] == "Automation"
    assert data["spec"]["trigger"]["type"] == "cron"
    assert data["spec"]["trigger"]["cron"] == "0 * * * *"


async def test_create_automation_webhook(client):
    """Automation with webhook trigger can be created."""
    payload = _automation_payload(
        name="wh-auto",
        trigger_type="webhook",
        webhook_secret="super-secret-key-12345",
    )
    r = await client.post("/api/v1/automations", json=payload, headers=API_KEY_HEADER)
    assert r.status_code == 201
    data = r.json()
    assert data["spec"]["trigger"]["type"] == "webhook"
    assert data["spec"]["trigger"]["webhook_secret"] == "**REDACTED**"


async def test_create_automation_api(client):
    """Automation with api trigger can be created."""
    payload = _automation_payload(name="api-auto", trigger_type="api")
    # Remove cron since it's an api trigger
    payload["spec"]["trigger"] = {"type": "api"}
    r = await client.post("/api/v1/automations", json=payload, headers=API_KEY_HEADER)
    assert r.status_code == 201
    data = r.json()
    assert data["spec"]["trigger"]["type"] == "api"


async def test_create_automation_invalid_target_kind(client):
    """Automation with invalid target kind is rejected."""
    payload = _automation_payload()
    payload["spec"]["target"]["kind"] = "InvalidKind"
    r = await client.post("/api/v1/automations", json=payload, headers=API_KEY_HEADER)
    assert r.status_code == 422


async def test_create_automation_invalid_trigger_type(client):
    """Automation with invalid trigger type is rejected."""
    payload = _automation_payload()
    payload["spec"]["trigger"]["type"] = "invalid"
    r = await client.post("/api/v1/automations", json=payload, headers=API_KEY_HEADER)
    assert r.status_code == 422


async def test_list_automations(client):
    """Automations can be listed."""
    payload = _automation_payload(name="list-auto")
    await client.post("/api/v1/automations", json=payload, headers=API_KEY_HEADER)
    r = await client.get("/api/v1/automations", headers=API_KEY_HEADER)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 1


async def test_get_automation(client):
    """Single automation can be retrieved."""
    payload = _automation_payload(name="get-auto")
    await client.post("/api/v1/automations", json=payload, headers=API_KEY_HEADER)
    r = await client.get("/api/v1/automations/get-auto", headers=API_KEY_HEADER)
    assert r.status_code == 200
    data = r.json()
    assert data["metadata"]["name"] == "get-auto"


async def test_delete_automation(client):
    """Automation can be deleted."""
    payload = _automation_payload(name="del-auto")
    await client.post("/api/v1/automations", json=payload, headers=API_KEY_HEADER)
    r = await client.delete("/api/v1/automations/del-auto", headers=API_KEY_HEADER)
    assert r.status_code == 204


# ── Trigger endpoint tests ───────────────────────────────────────────


async def test_trigger_automation_api(client):
    """POST /automations/{name}/trigger triggers the automation (returns 404 for missing crew)."""
    # Create an automation targeting a non-existent crew
    payload = _automation_payload(name="trig-auto", trigger_type="api")
    payload["spec"]["trigger"] = {"type": "api"}
    await client.post("/api/v1/automations", json=payload, headers=API_KEY_HEADER)

    # Trigger it — should get 404 since the target crew doesn't exist
    r = await client.post(
        "/api/v1/automations/trig-auto/trigger",
        json={"inputs": {}},
        headers=API_KEY_HEADER,
    )
    assert r.status_code == 404  # Crew not found


async def test_trigger_disabled_automation(client):
    """Triggering a disabled automation returns 409."""
    payload = _automation_payload(name="disabled-auto", enabled=False)
    await client.post("/api/v1/automations", json=payload, headers=API_KEY_HEADER)

    r = await client.post(
        "/api/v1/automations/disabled-auto/trigger",
        json={"inputs": {}},
        headers=API_KEY_HEADER,
    )
    assert r.status_code == 409


async def test_trigger_nonexistent_automation(client):
    """Triggering a non-existent automation returns 404."""
    r = await client.post(
        "/api/v1/automations/no-such-auto/trigger",
        json={"inputs": {}},
        headers=API_KEY_HEADER,
    )
    assert r.status_code == 404


# ── Webhook trigger tests ────────────────────────────────────────────


async def test_webhook_trigger_correct_secret(client):
    """Webhook trigger with correct secret fires (returns 404 for missing crew)."""
    payload = _automation_payload(
        name="wh-trig",
        trigger_type="webhook",
        webhook_secret="correct-secret-12345",
    )
    await client.post("/api/v1/automations", json=payload, headers=API_KEY_HEADER)

    r = await client.post(
        "/api/v1/automations/wh-trig/webhook",
        json={"secret": "correct-secret-12345", "inputs": {}},
        headers=API_KEY_HEADER,
    )
    # Will be 404 because the target crew doesn't exist
    assert r.status_code == 404


async def test_webhook_trigger_wrong_secret(client):
    """Webhook trigger with wrong secret returns 401."""
    payload = _automation_payload(
        name="wh-wrong",
        trigger_type="webhook",
        webhook_secret="correct-secret-12345",
    )
    await client.post("/api/v1/automations", json=payload, headers=API_KEY_HEADER)

    r = await client.post(
        "/api/v1/automations/wh-wrong/webhook",
        json={"secret": "wrong-secret-value-xx", "inputs": {}},
        headers=API_KEY_HEADER,
    )
    assert r.status_code == 401


async def test_webhook_trigger_not_webhook_type(client):
    """Webhook trigger on non-webhook automation returns 409."""
    payload = _automation_payload(name="not-wh", trigger_type="cron")
    await client.post("/api/v1/automations", json=payload, headers=API_KEY_HEADER)

    r = await client.post(
        "/api/v1/automations/not-wh/webhook",
        json={"secret": "any-secret-value-123", "inputs": {}},
        headers=API_KEY_HEADER,
    )
    assert r.status_code == 409


# ── Scheduler unit tests ─────────────────────────────────────────────


async def test_scheduler_start_stop():
    """Scheduler can start and stop without errors."""
    from blackbeard.engine.scheduler import AutomationScheduler

    scheduler = AutomationScheduler()
    try:
        await scheduler.start()
    except OSError:
        pytest.skip("PostgreSQL unavailable in unit test environment")
    await scheduler.stop()
    assert len(scheduler._tasks) == 0


# ── Kind registry tests ──────────────────────────────────────────────


def test_automation_in_kind_registry():
    """Automation kind is registered in ALL_KINDS."""
    from blackbeard.kinds import ALL_KINDS, KIND_TO_PLURAL, PLURAL_TO_KIND, ResourceKind

    assert ResourceKind.AUTOMATION.value == "Automation"
    assert KIND_TO_PLURAL["Automation"] == "automations"
    assert PLURAL_TO_KIND["automations"] == "Automation"
    assert "Automation" in ALL_KINDS


def test_automation_schema_registered():
    """Automation schema is in KIND_SCHEMAS."""
    from blackbeard.resources.spec_schemas import KIND_SCHEMAS

    assert "Automation" in KIND_SCHEMAS
    schema = KIND_SCHEMAS["Automation"]
    assert "target" in schema["required"]
    assert "trigger" in schema["required"]


def test_automation_in_cli_kinds():
    """Automation kind is also in CLI kinds.py."""
    import os

    cli_kinds_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "cli", "blackbeard_cli", "kinds.py"
    )
    if not os.path.exists(cli_kinds_path):
        pytest.skip("CLI kinds.py not found")
    with open(cli_kinds_path) as f:
        content = f.read()
    assert 'AUTOMATION = "Automation"' in content
    assert '"automations"' in content
