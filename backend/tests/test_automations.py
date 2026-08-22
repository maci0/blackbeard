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
    assert data["spec"]["trigger"]["webhook_secret"] == "[REDACTED]"


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


async def test_scheduler_start_stop(db_session, monkeypatch):
    """Scheduler can start against an empty DB and stop cleanly."""
    from blackbeard.engine.scheduler import AutomationScheduler

    monkeypatch.setattr("blackbeard.engine.scheduler.async_session", lambda: db_session)
    scheduler = AutomationScheduler()
    await scheduler.start()
    assert scheduler._running is True
    await scheduler.stop()
    assert len(scheduler._tasks) == 0
    assert scheduler._running is False


async def test_scheduler_start_skips_disabled_and_non_cron(db_session, monkeypatch):
    """start() only schedules enabled automations with cron triggers."""
    from blackbeard.engine.scheduler import AutomationScheduler
    from tests.conftest import make_resource

    rows = [
        make_resource(
            "Automation",
            "cron-enabled",
            {
                "target": {"kind": "Crew", "name": "c"},
                "trigger": {"type": "cron", "cron": "0 12 * * *"},
                "enabled": True,
            },
        ),
        make_resource(
            "Automation",
            "cron-disabled",
            {
                "target": {"kind": "Crew", "name": "c"},
                "trigger": {"type": "cron", "cron": "0 12 * * *"},
                "enabled": False,
            },
        ),
        make_resource(
            "Automation",
            "webhook-only",
            {
                "target": {"kind": "Crew", "name": "c"},
                "trigger": {"type": "webhook", "webhook_secret": "s" * 20},
            },
        ),
    ]
    db_session.add_all(rows)
    await db_session.commit()

    monkeypatch.setattr("blackbeard.engine.scheduler.async_session", lambda: db_session)
    scheduler = AutomationScheduler()
    try:
        await scheduler.start()
        assert set(scheduler._tasks) == {"cron-enabled"}
    finally:
        await scheduler.stop()


class TestScheduleValidation:
    """_schedule() must reject dangerous cron expressions (DoS guard)."""

    async def _schedule_and_stop(self, cron_expr: str) -> int:
        from blackbeard.engine.scheduler import AutomationScheduler

        scheduler = AutomationScheduler()
        scheduler._running = True
        try:
            scheduler._schedule("auto-1", cron_expr, {"kind": "Crew", "name": "c"}, {}, "default")
            return len(scheduler._tasks)
        finally:
            scheduler._running = False
            await scheduler.stop()

    async def test_rejects_sub_minute_six_field_expression(self):
        """Second-resolution (6-field) crons can fire every second and are rejected."""
        assert await self._schedule_and_stop("*/5 * * * * *") == 0

    async def test_rejects_invalid_cron_expression(self):
        """Garbage expressions are rejected without raising."""
        assert await self._schedule_and_stop("not a cron") == 0

    async def test_accepts_valid_cron_expression(self):
        """A normal 5-field expression schedules exactly one task."""
        assert await self._schedule_and_stop("*/5 * * * *") == 1

    async def test_reschedule_cancels_previous_task(self):
        """Re-scheduling the same automation cancels the previous task."""
        from blackbeard.engine.scheduler import AutomationScheduler

        scheduler = AutomationScheduler()
        scheduler._running = True
        try:
            scheduler._schedule("auto-1", "0 12 * * *", {"kind": "Crew", "name": "c"}, {}, "d")
            first = scheduler._tasks["auto-1"]
            scheduler._schedule("auto-1", "0 13 * * *", {"kind": "Crew", "name": "c"}, {}, "d")
            second = scheduler._tasks["auto-1"]
            assert second is not first
        finally:
            scheduler._running = False
            await scheduler.stop()
        # stop() awaits cancellation of every task it saw, including `first`.
        assert first.cancelled()


class TestClaimFiring:
    """Cross-replica dedup via unique insert on automation_runs."""

    @pytest.fixture
    def _patched_session(self, db_session, monkeypatch):
        monkeypatch.setattr("blackbeard.engine.scheduler.async_session", lambda: db_session)

    @pytest.mark.usefixtures("_patched_session")
    async def test_first_claim_wins(self):
        from datetime import UTC, datetime

        from blackbeard.engine.scheduler import AutomationScheduler

        scheduler = AutomationScheduler()
        when = datetime.now(UTC).replace(microsecond=0)
        assert await scheduler._claim_firing("auto-1", when) is True
        # A different automation at the same time does not conflict.
        assert await scheduler._claim_firing("auto-2", when) is True

    @pytest.mark.usefixtures("_patched_session")
    async def test_duplicate_claim_is_deduped(self):
        """The same (automation, scheduled_at) claimed twice loses the second time."""
        from datetime import UTC, datetime

        from blackbeard.engine.scheduler import AutomationScheduler

        scheduler = AutomationScheduler()
        when = datetime.now(UTC).replace(microsecond=0)
        assert await scheduler._claim_firing("dup-auto", when) is True
        assert await scheduler._claim_firing("dup-auto", when) is False

    async def test_db_failure_fails_open(self, monkeypatch):
        """Non-conflict DB errors trigger the firing anyway (fail open)."""
        from datetime import UTC, datetime

        from sqlalchemy.exc import OperationalError

        from blackbeard.engine.scheduler import AutomationScheduler

        class BrokenSession:
            def add(self, _):
                pass

            async def flush(self):
                raise OperationalError("stmt", {}, Exception("db gone"))

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

        monkeypatch.setattr("blackbeard.engine.scheduler.async_session", lambda: BrokenSession())
        scheduler = AutomationScheduler()
        when = datetime.now(UTC)
        assert await scheduler._claim_firing("fail-open-auto", when) is True


class TestTriggerTarget:
    """_trigger_target dispatches Crew vs Flow targets to the executor."""

    async def test_crew_target_calls_kickoff(self, monkeypatch):
        from blackbeard.engine.scheduler import AutomationScheduler

        calls: list[tuple[str, dict]] = []

        async def fake_kickoff(_session, name, *, inputs, project):
            calls.append((name, inputs))

        async def fake_run_flow(*_a, **_kw):  # pragma: no cover - must not be called
            raise AssertionError("run_flow called for a Crew target")

        monkeypatch.setattr("blackbeard.engine.executor.kickoff", fake_kickoff)
        monkeypatch.setattr("blackbeard.engine.executor.run_flow", fake_run_flow)

        scheduler = AutomationScheduler()
        await scheduler._trigger_target(
            "t-auto",
            {"kind": "Crew", "name": "my-crew"},
            {"topic": "x"},
            "default",
        )
        assert calls == [("my-crew", {"topic": "x"})]

    async def test_flow_target_calls_run_flow(self, monkeypatch):
        from blackbeard.engine.scheduler import AutomationScheduler

        calls: list[str] = []

        async def fake_kickoff(*_a, **_kw):  # pragma: no cover - must not be called
            raise AssertionError("kickoff called for a Flow target")

        async def fake_run_flow(_session, name, *, inputs, project):
            calls.append(name)

        monkeypatch.setattr("blackbeard.engine.executor.kickoff", fake_kickoff)
        monkeypatch.setattr("blackbeard.engine.executor.run_flow", fake_run_flow)

        scheduler = AutomationScheduler()
        await scheduler._trigger_target(
            "t-auto-flow",
            {"kind": "Flow", "name": "my-flow"},
            {},
            "default",
        )
        assert calls == ["my-flow"]

    async def test_trigger_failure_does_not_raise(self, monkeypatch):
        """A failing target is logged, not raised (the cron task would die otherwise)."""
        from blackbeard.engine.scheduler import AutomationScheduler

        async def fake_kickoff(*_a, **_kw):
            raise RuntimeError("boom")

        monkeypatch.setattr("blackbeard.engine.executor.kickoff", fake_kickoff)

        scheduler = AutomationScheduler()
        await scheduler._trigger_target(
            "t-auto-fail", {"kind": "Crew", "name": "missing"}, {}, "default"
        )


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
