"""Tests for workflow hooks (Feature 2)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from tests.conftest import API_KEY_HEADER, make_resource

from blackbeard.kinds import ResourceKind


# ── Schema validation tests ──────────────────────────────────────────


async def test_crew_with_hooks_schema_valid(client):
    """Crew with hooks field passes schema validation."""
    payload = {
        "apiVersion": "blackbeard/v1",
        "kind": "Crew",
        "metadata": {"name": "hooked-crew", "namespace": "default"},
        "spec": {
            "process": "sequential",
            "agents": ["ref:agents/researcher"],
            "tasks": ["ref:tasks/research"],
            "hooks": {
                "before_kickoff": "blackbeard.hooks.pre_check",
                "after_kickoff": "blackbeard.hooks.post_check",
                "on_error": "blackbeard.hooks.error_handler",
            },
        },
    }
    r = await client.post("/api/v1/crews", json=payload, headers=API_KEY_HEADER)
    assert r.status_code == 201
    data = r.json()
    assert data["spec"]["hooks"]["before_kickoff"] == "blackbeard.hooks.pre_check"


async def test_crew_hooks_invalid_additional_prop(client):
    """Crew hooks with unknown property is rejected."""
    payload = {
        "apiVersion": "blackbeard/v1",
        "kind": "Crew",
        "metadata": {"name": "bad-hook-crew", "namespace": "default"},
        "spec": {
            "process": "sequential",
            "agents": ["ref:agents/researcher"],
            "tasks": ["ref:tasks/research"],
            "hooks": {
                "before_kickoff": "blackbeard.hooks.pre",
                "invalid_hook": "blackbeard.hooks.nope",
            },
        },
    }
    r = await client.post("/api/v1/crews", json=payload, headers=API_KEY_HEADER)
    assert r.status_code == 422


async def test_flow_step_with_hooks_schema_valid(client):
    """Flow step with hooks passes schema validation."""
    payload = {
        "apiVersion": "blackbeard/v1",
        "kind": "Flow",
        "metadata": {"name": "hooked-flow", "namespace": "default"},
        "spec": {
            "steps": [
                {
                    "name": "step-one",
                    "type": "crew",
                    "crew": "ref:crews/test-crew",
                    "hooks": {
                        "before": "blackbeard.flows.pre_step",
                        "after": "blackbeard.flows.post_step",
                        "on_error": "blackbeard.flows.step_error",
                    },
                },
            ],
        },
    }
    r = await client.post("/api/v1/flows", json=payload, headers=API_KEY_HEADER)
    assert r.status_code == 201
    data = r.json()
    assert data["spec"]["steps"][0]["hooks"]["before"] == "blackbeard.flows.pre_step"


async def test_flow_step_hooks_invalid_additional_prop(client):
    """Flow step hooks with unknown property is rejected."""
    payload = {
        "apiVersion": "blackbeard/v1",
        "kind": "Flow",
        "metadata": {"name": "bad-flow-hooks", "namespace": "default"},
        "spec": {
            "steps": [
                {
                    "name": "step-one",
                    "type": "crew",
                    "crew": "ref:crews/test-crew",
                    "hooks": {
                        "before": "blackbeard.flows.pre",
                        "invalid_key": "blackbeard.flows.nope",
                    },
                },
            ],
        },
    }
    r = await client.post("/api/v1/flows", json=payload, headers=API_KEY_HEADER)
    assert r.status_code == 422


# ── Hook execution tests ─────────────────────────────────────────────


def test_call_hook_success():
    """_call_hook calls the resolved function."""
    from blackbeard.engine.executor import _call_hook
    from blackbeard.engine.loader import ResourceLoader

    mock_fn = MagicMock()
    loader = MagicMock(spec=ResourceLoader)
    loader._import_callable.return_value = mock_fn

    _call_hook(loader, "blackbeard.hooks.my_fn", {"key": "val"}, "before_kickoff")

    loader._import_callable.assert_called_once_with("blackbeard.hooks.my_fn")
    mock_fn.assert_called_once_with({"key": "val"})


def test_call_hook_import_fails_does_not_crash():
    """_call_hook logs warning when import fails but does not raise."""
    from blackbeard.engine.executor import _call_hook
    from blackbeard.engine.loader import ResourceLoader

    loader = MagicMock(spec=ResourceLoader)
    loader._import_callable.return_value = None

    # Should not raise
    _call_hook(loader, "nonexistent.module.fn", {}, "before_kickoff")
    loader._import_callable.assert_called_once()


def test_call_hook_exception_does_not_crash():
    """_call_hook logs warning when hook raises but does not propagate."""
    from blackbeard.engine.executor import _call_hook
    from blackbeard.engine.loader import ResourceLoader

    mock_fn = MagicMock(side_effect=RuntimeError("hook broke"))
    loader = MagicMock(spec=ResourceLoader)
    loader._import_callable.return_value = mock_fn

    # Should not raise
    _call_hook(loader, "blackbeard.hooks.broken", {}, "after_kickoff")
    mock_fn.assert_called_once()


# ── Flow step hooks execution tests ──────────────────────────────────


def test_flow_step_hooks_called():
    """Flow step before/after hooks are called during _run_flow_steps."""
    from unittest.mock import patch as _patch

    from blackbeard.engine.executor import _run_flow_steps

    mock_crew = MagicMock()
    mock_crew.kickoff.return_value = MagicMock(raw="result")

    mock_loader = MagicMock()
    mock_loader.build_crew.return_value = mock_crew

    hook_fn = MagicMock()
    mock_loader._import_callable.return_value = hook_fn

    resource_snapshot = {
        "Flow/test-flow": {
            "kind": "Flow",
            "name": "test-flow",
            "namespace": "default",
            "spec": {
                "steps": [
                    {
                        "name": "step1",
                        "type": "crew",
                        "crew": "ref:crews/my-crew",
                        "hooks": {
                            "before": "blackbeard.flows.pre",
                            "after": "blackbeard.flows.post",
                        },
                    },
                ],
            },
        },
        "Crew/my-crew": {
            "kind": "Crew",
            "name": "my-crew",
            "namespace": "default",
            "spec": {
                "process": "sequential",
                "agents": [],
                "tasks": [],
            },
        },
    }

    _run_flow_steps(
        mock_loader,
        resource_snapshot,
        "test-flow",
        {},
        MagicMock(),
    )

    # Both before and after hooks should have been called
    assert mock_loader._import_callable.call_count >= 2
    assert hook_fn.call_count >= 2


# ── Crew hooks wiring test ───────────────────────────────────────────


def test_crew_hooks_schema_all_fields():
    """All crew hook fields are accepted."""
    from blackbeard.resources.spec_schemas import CREW_SCHEMA

    hook_props = CREW_SCHEMA["properties"]["hooks"]["properties"]
    assert "before_kickoff" in hook_props
    assert "after_kickoff" in hook_props
    assert "before_task" in hook_props
    assert "after_task" in hook_props
    assert "on_error" in hook_props


def test_flow_step_hooks_schema_all_fields():
    """All flow step hook fields are accepted."""
    from blackbeard.resources.spec_schemas import FLOW_SCHEMA

    step_schema = FLOW_SCHEMA["properties"]["steps"]["items"]
    hook_props = step_schema["properties"]["hooks"]["properties"]
    assert "before" in hook_props
    assert "after" in hook_props
    assert "on_error" in hook_props
