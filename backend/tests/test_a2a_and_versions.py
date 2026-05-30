"""Tests for A2A Agent Card endpoint and Resource Versioning endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.conftest import API_KEY_HEADER

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clear_a2a_cache() -> None:
    """Reset the A2A module-level cache so each test gets a fresh DB query."""
    import blackbeard.api.a2a as _a2a_mod

    _a2a_mod._cache_entry = None


def _crew_payload(
    name: str,
    *,
    agents: list[str] | None = None,
    tasks: list[str] | None = None,
    description: str = "",
    a2a: dict | None = None,
) -> dict:
    """Build a valid Crew resource create payload."""
    spec: dict = {
        "process": "sequential",
        "agents": agents or ["ref:agents/default-agent"],
        "tasks": tasks or ["ref:tasks/default-task"],
    }
    if description:
        spec["description"] = description
    if a2a is not None:
        spec["a2a"] = a2a
    return {
        "apiVersion": "blackbeard/v1",
        "kind": "Crew",
        "metadata": {"name": name, "project": "default"},
        "spec": spec,
    }


def _agent_payload(name: str = "default-agent") -> dict:
    """Build a valid Agent resource create payload."""
    return {
        "apiVersion": "blackbeard/v1",
        "kind": "Agent",
        "metadata": {"name": name, "project": "default"},
        "spec": {
            "role": "Test Agent",
            "goal": "Do testing",
            "backstory": "A test agent",
        },
    }


def _task_payload(
    name: str = "default-task",
    *,
    description: str = "Do something useful",
    expected_output: str = "A useful result",
) -> dict:
    """Build a valid Task resource create payload."""
    return {
        "apiVersion": "blackbeard/v1",
        "kind": "Task",
        "metadata": {"name": name, "project": "default"},
        "spec": {
            "description": description,
            "expected_output": expected_output,
            "agent": "ref:agents/default-agent",
        },
    }


async def _create_resource(client: AsyncClient, payload: dict, kind_plural: str) -> dict:
    """POST a resource and assert it was created successfully."""
    resp = await client.post(
        f"/api/v1/{kind_plural}",
        json=payload,
        headers=API_KEY_HEADER,
    )
    assert resp.status_code in (200, 201), f"Create failed ({resp.status_code}): {resp.text}"
    return resp.json()


# =========================================================================
# Part 1: A2A Agent Card tests (GET /.well-known/agent-card.json)
# =========================================================================


@pytest.mark.asyncio
async def test_a2a_returns_empty_agents(client: AsyncClient) -> None:
    """No crews exist, should return ``{"agents": []}``."""
    _clear_a2a_cache()
    resp = await client.get("/.well-known/agent-card.json", headers=API_KEY_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data == {"agents": []}


@pytest.mark.asyncio
async def test_a2a_no_auth_required(client: AsyncClient) -> None:
    """Request without API key should still succeed (public endpoint)."""
    _clear_a2a_cache()
    resp = await client.get("/.well-known/agent-card.json")
    assert resp.status_code == 200
    data = resp.json()
    assert "agents" in data


@pytest.mark.asyncio
async def test_a2a_includes_a2a_enabled_crew(client: AsyncClient) -> None:
    """Create a Crew with ``spec.a2a.enabled: true``; verify it appears in the response."""
    _clear_a2a_cache()

    payload = _crew_payload(
        "a2a-enabled-crew",
        description="An A2A-enabled crew",
        a2a={"enabled": True},
    )
    await _create_resource(client, payload, "crews")

    _clear_a2a_cache()
    resp = await client.get("/.well-known/agent-card.json", headers=API_KEY_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["agents"]) == 1

    agent = data["agents"][0]
    assert agent["name"] == "a2a-enabled-crew"
    assert agent["description"] == "An A2A-enabled crew"
    assert "/api/v1/crews/a2a-enabled-crew/kickoff" in agent["url"]
    assert "authentication" in agent
    assert "skills" in agent


@pytest.mark.asyncio
async def test_a2a_excludes_disabled_crew(client: AsyncClient) -> None:
    """Create a Crew with ``spec.a2a.enabled: false``; verify it does NOT appear."""
    _clear_a2a_cache()

    payload = _crew_payload(
        "a2a-disabled-crew",
        a2a={"enabled": False},
    )
    await _create_resource(client, payload, "crews")

    _clear_a2a_cache()
    resp = await client.get("/.well-known/agent-card.json", headers=API_KEY_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    # No agents should appear (crew has a2a.enabled = false)
    assert len(data["agents"]) == 0


@pytest.mark.asyncio
async def test_a2a_excludes_crew_without_a2a(client: AsyncClient) -> None:
    """Create a Crew without ``a2a`` in spec; verify excluded."""
    _clear_a2a_cache()

    payload = _crew_payload("no-a2a-crew")
    await _create_resource(client, payload, "crews")

    _clear_a2a_cache()
    resp = await client.get("/.well-known/agent-card.json", headers=API_KEY_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["agents"]) == 0


@pytest.mark.asyncio
async def test_a2a_skills_from_task_refs(client: AsyncClient) -> None:
    """Create a Crew referencing tasks; verify skills array contains the tasks."""
    _clear_a2a_cache()

    # Create the agent and tasks first
    await _create_resource(client, _agent_payload("skill-agent"), "agents")
    await _create_resource(
        client,
        _task_payload(
            "research-task",
            description="Research the topic\nProvide detailed analysis",
            expected_output="A comprehensive research report",
        ),
        "tasks",
    )
    await _create_resource(
        client,
        _task_payload(
            "writing-task",
            description="Write the final document",
            expected_output="A polished written document",
        ),
        "tasks",
    )

    # Create crew referencing both tasks
    crew = _crew_payload(
        "skills-crew",
        agents=["ref:agents/skill-agent"],
        tasks=["ref:tasks/research-task", "ref:tasks/writing-task"],
        a2a={"enabled": True},
    )
    await _create_resource(client, crew, "crews")

    _clear_a2a_cache()
    resp = await client.get("/.well-known/agent-card.json", headers=API_KEY_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["agents"]) == 1

    skills = data["agents"][0]["skills"]
    assert len(skills) == 2

    skill_ids = {s["id"] for s in skills}
    assert skill_ids == {"research-task", "writing-task"}

    # Verify skill structure
    for skill in skills:
        assert "id" in skill
        assert "name" in skill
        assert "description" in skill

    # Check that skill name comes from first line of task description
    research_skill = next(s for s in skills if s["id"] == "research-task")
    assert research_skill["name"] == "Research the topic"
    assert research_skill["description"] == "A comprehensive research report"


@pytest.mark.asyncio
async def test_a2a_response_shape(client: AsyncClient) -> None:
    """Verify response has correct JSON structure per A2A spec."""
    _clear_a2a_cache()

    payload = _crew_payload(
        "shape-crew",
        description="Shape test crew",
        a2a={
            "enabled": True,
            "protocol_versions": ["1.0"],
            "transports": ["json-rpc"],
        },
    )
    await _create_resource(client, payload, "crews")

    _clear_a2a_cache()
    resp = await client.get("/.well-known/agent-card.json", headers=API_KEY_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert "agents" in data
    assert isinstance(data["agents"], list)
    assert len(data["agents"]) >= 1

    agent = data["agents"][0]

    # Required fields per A2A spec
    assert isinstance(agent["name"], str)
    assert isinstance(agent["description"], str)
    assert isinstance(agent["url"], str)
    assert isinstance(agent["version"], str)

    # Provider block
    assert "provider" in agent
    assert "organization" in agent["provider"]
    assert "url" in agent["provider"]

    # Capabilities
    assert "capabilities" in agent
    assert isinstance(agent["capabilities"]["streaming"], bool)
    assert isinstance(agent["capabilities"]["pushNotifications"], bool)

    # Authentication
    assert "authentication" in agent
    assert "schemes" in agent["authentication"]
    assert isinstance(agent["authentication"]["schemes"], list)

    # Input/output modes
    assert agent["defaultInputModes"] == ["application/json"]
    assert agent["defaultOutputModes"] == ["application/json"]

    # Skills is a list
    assert isinstance(agent["skills"], list)

    # Optional A2A metadata (we set protocol_versions and transports)
    assert agent["protocolVersions"] == ["1.0"]
    assert agent["supportedTransports"] == ["json-rpc"]


# =========================================================================
# Part 2: Resource Versioning tests
# =========================================================================


@pytest.mark.asyncio
async def test_create_resource_creates_version_snapshot(client: AsyncClient) -> None:
    """Create a resource, then GET versions should show version 1."""
    await _create_resource(client, _agent_payload("v-agent-1"), "agents")

    resp = await client.get(
        "/api/v1/agents/v-agent-1/versions",
        headers=API_KEY_HEADER,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["versions"]) == 1
    assert data["versions"][0]["version"] == 1


@pytest.mark.asyncio
async def test_update_resource_creates_new_version(client: AsyncClient) -> None:
    """Create then update; versions list should show 2 entries."""
    created = await _create_resource(client, _agent_payload("v-agent-2"), "agents")

    # Update the resource
    update_resp = await client.put(
        "/api/v1/agents/v-agent-2",
        json={
            "spec": {
                "role": "Updated Role",
                "goal": "Updated goal",
                "backstory": "Updated backstory",
            },
            "version": created["version"],
        },
        headers=API_KEY_HEADER,
    )
    assert update_resp.status_code == 200

    resp = await client.get(
        "/api/v1/agents/v-agent-2/versions",
        headers=API_KEY_HEADER,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["versions"]) == 2
    assert data["versions"][0]["version"] == 1
    assert data["versions"][1]["version"] == 2


@pytest.mark.asyncio
async def test_get_specific_version(client: AsyncClient) -> None:
    """GET ``/{kind_plural}/{name}/versions/{version}`` returns full spec snapshot."""
    original_spec = {
        "role": "Original Role",
        "goal": "Original goal",
        "backstory": "Original backstory",
    }
    payload = _agent_payload("v-agent-3")
    payload["spec"] = original_spec
    created = await _create_resource(client, payload, "agents")

    # Update to a different spec
    await client.put(
        "/api/v1/agents/v-agent-3",
        json={
            "spec": {
                "role": "Changed Role",
                "goal": "Changed goal",
                "backstory": "Changed backstory",
            },
            "version": created["version"],
        },
        headers=API_KEY_HEADER,
    )

    # Retrieve version 1 snapshot
    resp = await client.get(
        "/api/v1/agents/v-agent-3/versions/1",
        headers=API_KEY_HEADER,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["version"] == 1
    assert data["spec"]["role"] == "Original Role"
    assert data["spec"]["goal"] == "Original goal"
    assert data["spec"]["backstory"] == "Original backstory"

    # Retrieve version 2 snapshot
    resp2 = await client.get(
        "/api/v1/agents/v-agent-3/versions/2",
        headers=API_KEY_HEADER,
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["version"] == 2
    assert data2["spec"]["role"] == "Changed Role"


@pytest.mark.asyncio
async def test_version_not_found(client: AsyncClient) -> None:
    """GET version that doesn't exist returns 404."""
    await _create_resource(client, _agent_payload("v-agent-4"), "agents")

    resp = await client.get(
        "/api/v1/agents/v-agent-4/versions/999",
        headers=API_KEY_HEADER,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_rollback_restores_previous_spec(client: AsyncClient) -> None:
    """Create with spec A, update to spec B, rollback to version 1; verify spec is A again."""
    spec_a = {
        "role": "Role A",
        "goal": "Goal A",
        "backstory": "Backstory A",
    }
    payload = _agent_payload("v-agent-5")
    payload["spec"] = spec_a
    created = await _create_resource(client, payload, "agents")

    # Update to spec B
    await client.put(
        "/api/v1/agents/v-agent-5",
        json={
            "spec": {
                "role": "Role B",
                "goal": "Goal B",
                "backstory": "Backstory B",
            },
            "version": created["version"],
        },
        headers=API_KEY_HEADER,
    )

    # Rollback to version 1
    rollback_resp = await client.post(
        "/api/v1/agents/v-agent-5/rollback",
        json={"version": 1},
        headers=API_KEY_HEADER,
    )
    assert rollback_resp.status_code == 200
    rolled_back = rollback_resp.json()
    assert rolled_back["spec"]["role"] == "Role A"
    assert rolled_back["spec"]["goal"] == "Goal A"
    assert rolled_back["spec"]["backstory"] == "Backstory A"

    # Also verify via GET
    get_resp = await client.get(
        "/api/v1/agents/v-agent-5",
        headers=API_KEY_HEADER,
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["spec"]["role"] == "Role A"


@pytest.mark.asyncio
async def test_rollback_creates_new_version_entry(client: AsyncClient) -> None:
    """After rollback, versions list should have 3 entries (v1 original, v2 update, v3 rollback)."""
    payload = _agent_payload("v-agent-6")
    created = await _create_resource(client, payload, "agents")

    # Update
    await client.put(
        "/api/v1/agents/v-agent-6",
        json={
            "spec": {
                "role": "Updated Role",
                "goal": "Updated goal",
                "backstory": "Updated backstory",
            },
            "version": created["version"],
        },
        headers=API_KEY_HEADER,
    )

    # Rollback to v1
    await client.post(
        "/api/v1/agents/v-agent-6/rollback",
        json={"version": 1},
        headers=API_KEY_HEADER,
    )

    resp = await client.get(
        "/api/v1/agents/v-agent-6/versions",
        headers=API_KEY_HEADER,
    )
    assert resp.status_code == 200
    data = resp.json()
    versions = data["versions"]
    assert len(versions) == 3
    assert versions[0]["version"] == 1
    assert versions[1]["version"] == 2
    assert versions[2]["version"] == 3


@pytest.mark.asyncio
async def test_rollback_nonexistent_version(client: AsyncClient) -> None:
    """Rollback to version 999 returns 404."""
    await _create_resource(client, _agent_payload("v-agent-7"), "agents")

    resp = await client.post(
        "/api/v1/agents/v-agent-7/rollback",
        json={"version": 999},
        headers=API_KEY_HEADER,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_versions_list_includes_changed_keys(client: AsyncClient) -> None:
    """Verify ``changed_keys`` field shows which spec keys changed between versions."""
    spec_v1 = {
        "role": "Original Role",
        "goal": "Original Goal",
        "backstory": "Original Backstory",
    }
    payload = _agent_payload("v-agent-8")
    payload["spec"] = spec_v1
    created = await _create_resource(client, payload, "agents")

    # Update only the role — goal and backstory stay the same
    await client.put(
        "/api/v1/agents/v-agent-8",
        json={
            "spec": {
                "role": "Changed Role",
                "goal": "Original Goal",
                "backstory": "Original Backstory",
            },
            "version": created["version"],
        },
        headers=API_KEY_HEADER,
    )

    resp = await client.get(
        "/api/v1/agents/v-agent-8/versions",
        headers=API_KEY_HEADER,
    )
    assert resp.status_code == 200
    data = resp.json()
    versions = data["versions"]
    assert len(versions) == 2

    # Version 1: first version, all keys are "changed" (no previous version)
    v1_keys = versions[0]["changed_keys"]
    assert "role" in v1_keys
    assert "goal" in v1_keys
    assert "backstory" in v1_keys

    # Version 2: only "role" changed
    v2_keys = versions[1]["changed_keys"]
    assert v2_keys == ["role"]


@pytest.mark.asyncio
async def test_resource_not_found_versions(client: AsyncClient) -> None:
    """GET versions for nonexistent resource returns 404."""
    resp = await client.get(
        "/api/v1/agents/nonexistent-agent/versions",
        headers=API_KEY_HEADER,
    )
    assert resp.status_code == 404
