"""Integration tests for ResourceService CRUD operations.

Tests the service layer directly using the db_session fixture,
verifying create, get, list, update, delete, upsert, and version
conflict behavior.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from blackbeard.models.resource_schemas import ResourceCreate, ResourceMetadata, ResourceUpdate
from blackbeard.resources.exceptions import (
    ResourceConflictError,
    ResourceNotFoundError,
    ResourceValidationError,
)
from blackbeard.resources.service import ResourceService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _agent_create(name: str = "svc-agent") -> ResourceCreate:
    """Build a valid Agent ResourceCreate."""
    return ResourceCreate(
        apiVersion="blackbeard/v1",
        kind="Agent",
        metadata=ResourceMetadata(name=name, namespace="default"),
        spec={
            "role": "Test Agent",
            "goal": "Test goal",
            "backstory": "Test backstory",
        },
    )


def _task_create(name: str = "svc-task", agent_ref: str = "ref:agents/svc-agent") -> ResourceCreate:
    """Build a valid Task ResourceCreate."""
    return ResourceCreate(
        apiVersion="blackbeard/v1",
        kind="Task",
        metadata=ResourceMetadata(name=name, namespace="default"),
        spec={
            "description": "Test task description",
            "expected_output": "Test expected output",
            "agent": agent_ref,
        },
    )


# ---------------------------------------------------------------------------
# create()
# ---------------------------------------------------------------------------


async def test_service_create_returns_resource(db_session: AsyncSession):
    """create() returns a resource and marks it as created."""
    service = ResourceService(db_session)
    resource, created = await service.create(_agent_create())

    assert created is True
    assert resource.name == "svc-agent"
    assert resource.kind.value == "Agent"
    assert resource.version == 1
    assert resource.spec["role"] == "Test Agent"
    assert resource.id is not None


async def test_service_create_upsert_on_duplicate(db_session: AsyncSession):
    """create() with same name/kind/namespace upserts (version incremented)."""
    service = ResourceService(db_session)

    resource1, created1 = await service.create(_agent_create())
    assert created1 is True
    assert resource1.version == 1

    resource2, created2 = await service.create(_agent_create())
    assert created2 is False
    assert resource2.version == 2
    assert resource2.id == resource1.id  # Same resource, updated


async def test_service_create_stores_refs(db_session: AsyncSession):
    """create() for a task with refs stores ResourceRef rows."""
    service = ResourceService(db_session)

    # Create the agent first (so the ref target exists)
    await service.create(_agent_create())

    # Create a task that references the agent
    task, created = await service.create(_task_create())
    assert created is True
    assert task.spec["agent"] == "ref:agents/svc-agent"


async def test_service_create_invalid_spec_raises(db_session: AsyncSession):
    """create() with invalid spec raises ResourceValidationError."""
    service = ResourceService(db_session)
    bad_data = ResourceCreate(
        apiVersion="blackbeard/v1",
        kind="Agent",
        metadata=ResourceMetadata(name="bad-agent", namespace="default"),
        spec={"goal": "Only goal, no role or backstory"},
    )
    with pytest.raises(ResourceValidationError):
        await service.create(bad_data)


async def test_service_create_different_namespaces(db_session: AsyncSession):
    """create() allows same name in different namespaces."""
    service = ResourceService(db_session)
    data1 = ResourceCreate(
        apiVersion="blackbeard/v1",
        kind="Agent",
        metadata=ResourceMetadata(name="agent-x", namespace="alpha"),
        spec={"role": "R", "goal": "G", "backstory": "B"},
    )
    data2 = ResourceCreate(
        apiVersion="blackbeard/v1",
        kind="Agent",
        metadata=ResourceMetadata(name="agent-x", namespace="beta"),
        spec={"role": "R2", "goal": "G2", "backstory": "B2"},
    )
    r1, c1 = await service.create(data1)
    r2, c2 = await service.create(data2)
    assert c1 is True
    assert c2 is True
    assert r1.id != r2.id


# ---------------------------------------------------------------------------
# get()
# ---------------------------------------------------------------------------


async def test_service_get_existing(db_session: AsyncSession):
    """get() returns a resource by name."""
    service = ResourceService(db_session)
    await service.create(_agent_create())

    resource = await service.get("Agent", "svc-agent")
    assert resource.name == "svc-agent"
    assert resource.spec["role"] == "Test Agent"


async def test_service_get_missing_raises(db_session: AsyncSession):
    """get() raises ResourceNotFoundError for non-existent resource."""
    service = ResourceService(db_session)
    with pytest.raises(ResourceNotFoundError):
        await service.get("Agent", "nonexistent")


async def test_service_get_wrong_kind_raises(db_session: AsyncSession):
    """get() with wrong kind raises ResourceNotFoundError."""
    service = ResourceService(db_session)
    await service.create(_agent_create())

    with pytest.raises(ResourceNotFoundError):
        await service.get("Task", "svc-agent")


# ---------------------------------------------------------------------------
# list_resources()
# ---------------------------------------------------------------------------


async def test_service_list_empty(db_session: AsyncSession):
    """list_resources() on empty DB returns empty list."""
    service = ResourceService(db_session)
    items, total = await service.list_resources(kind="Agent")
    assert items == []
    assert total == 0


async def test_service_list_returns_items(db_session: AsyncSession):
    """list_resources() returns created resources."""
    service = ResourceService(db_session)
    await service.create(_agent_create("agent-a"))
    await service.create(_agent_create("agent-b"))

    items, total = await service.list_resources(kind="Agent")
    assert total == 2
    assert len(items) == 2
    names = {r.name for r in items}
    assert names == {"agent-a", "agent-b"}


async def test_service_list_pagination(db_session: AsyncSession):
    """list_resources() respects limit and offset."""
    service = ResourceService(db_session)
    for i in range(5):
        await service.create(_agent_create(f"agent-{i}"))

    items, total = await service.list_resources(kind="Agent", limit=2, offset=0)
    assert len(items) == 2
    assert total == 5

    items2, total2 = await service.list_resources(kind="Agent", limit=2, offset=4)
    assert len(items2) == 1
    assert total2 == 5

    page1_names = {r.name for r in items}
    page2_names = {r.name for r in items2}
    assert page1_names.isdisjoint(page2_names), "Pages should not overlap"


async def test_service_list_filters_by_namespace(db_session: AsyncSession):
    """list_resources() filters by namespace."""
    service = ResourceService(db_session)
    data_default = ResourceCreate(
        apiVersion="blackbeard/v1",
        kind="Agent",
        metadata=ResourceMetadata(name="agent-default", namespace="default"),
        spec={"role": "R", "goal": "G", "backstory": "B"},
    )
    data_other = ResourceCreate(
        apiVersion="blackbeard/v1",
        kind="Agent",
        metadata=ResourceMetadata(name="agent-other", namespace="other"),
        spec={"role": "R", "goal": "G", "backstory": "B"},
    )
    await service.create(data_default)
    await service.create(data_other)

    items, total = await service.list_resources(kind="Agent", namespace="default")
    assert total == 1
    assert items[0].name == "agent-default"


async def test_service_list_filters_by_kind(db_session: AsyncSession):
    """list_resources() filters by kind correctly."""
    service = ResourceService(db_session)
    await service.create(_agent_create("my-agent"))
    await service.create(
        ResourceCreate(
            apiVersion="blackbeard/v1",
            kind="LLMConnection",
            metadata=ResourceMetadata(name="my-llm", namespace="default"),
            spec={"provider": "openai", "model": "gpt-4o"},
        )
    )

    agents, a_total = await service.list_resources(kind="Agent")
    assert a_total == 1
    assert agents[0].name == "my-agent"

    llms, l_total = await service.list_resources(kind="LLMConnection")
    assert l_total == 1
    assert llms[0].name == "my-llm"


# ---------------------------------------------------------------------------
# update()
# ---------------------------------------------------------------------------


async def test_service_update_spec(db_session: AsyncSession):
    """update() updates spec and increments version."""
    service = ResourceService(db_session)
    await service.create(_agent_create())

    update_data = ResourceUpdate(
        version=1,
        spec={"role": "Updated Role", "goal": "Updated Goal", "backstory": "Updated"},
    )
    updated = await service.update("Agent", "svc-agent", update_data)
    assert updated.version == 2
    assert updated.spec["role"] == "Updated Role"


async def test_service_update_version_conflict(db_session: AsyncSession):
    """update() raises ResourceConflictError on version mismatch."""
    service = ResourceService(db_session)
    await service.create(_agent_create())

    update_data = ResourceUpdate(
        version=99,  # wrong version
        spec={"role": "R", "goal": "G", "backstory": "B"},
    )
    with pytest.raises(ResourceConflictError):
        await service.update("Agent", "svc-agent", update_data)


async def test_service_update_missing_raises(db_session: AsyncSession):
    """update() raises ResourceNotFoundError for non-existent resource."""
    service = ResourceService(db_session)
    update_data = ResourceUpdate(
        version=1,
        spec={"role": "R", "goal": "G", "backstory": "B"},
    )
    with pytest.raises(ResourceNotFoundError):
        await service.update("Agent", "nonexistent", update_data)


async def test_service_update_invalid_spec_raises(db_session: AsyncSession):
    """update() with invalid spec raises ResourceValidationError."""
    service = ResourceService(db_session)
    await service.create(_agent_create())

    update_data = ResourceUpdate(
        version=1,
        spec={"goal": "Only goal"},  # missing role and backstory
    )
    with pytest.raises(ResourceValidationError):
        await service.update("Agent", "svc-agent", update_data)


async def test_service_update_metadata_only(db_session: AsyncSession):
    """update() with only metadata changes still increments version."""
    service = ResourceService(db_session)
    await service.create(_agent_create())

    update_data = ResourceUpdate(
        version=1,
        metadata=ResourceMetadata(name="svc-agent", namespace="default", labels={"env": "test"}),
    )
    updated = await service.update("Agent", "svc-agent", update_data)
    assert updated.version == 2
    assert updated.labels == {"env": "test"}


# ---------------------------------------------------------------------------
# delete()
# ---------------------------------------------------------------------------


async def test_service_delete_existing(db_session: AsyncSession):
    """delete() removes an existing resource."""
    service = ResourceService(db_session)
    await service.create(_agent_create())

    await service.delete("Agent", "svc-agent")

    with pytest.raises(ResourceNotFoundError):
        await service.get("Agent", "svc-agent")


async def test_service_delete_missing_raises(db_session: AsyncSession):
    """delete() raises ResourceNotFoundError for non-existent resource."""
    service = ResourceService(db_session)
    with pytest.raises(ResourceNotFoundError):
        await service.delete("Agent", "nonexistent")


async def test_service_delete_cleans_refs(db_session: AsyncSession):
    """delete() removes associated ResourceRef rows."""
    service = ResourceService(db_session)
    await service.create(_agent_create())
    await service.create(_task_create())

    # Delete the task (which has refs to the agent)
    await service.delete("Task", "svc-task")

    # The agent should still exist
    agent = await service.get("Agent", "svc-agent")
    assert agent is not None
