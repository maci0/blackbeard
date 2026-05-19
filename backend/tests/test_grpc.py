"""Tests for gRPC API (Feature 3)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from blackbeard.grpc.server import BlackbeardServicer, _execution_to_proto, _resource_to_proto

# ── Proto conversion tests ───────────────────────────────────────────


def test_resource_to_proto():
    """_resource_to_proto converts a Resource ORM object to proto."""
    from blackbeard.kinds import ResourceKind

    resource = MagicMock()
    resource.id = "test-id-123"
    resource.kind = ResourceKind.AGENT
    resource.name = "test-agent"
    resource.namespace = "default"
    resource.spec = {"role": "tester", "goal": "test", "backstory": "test"}
    resource.version = 1
    resource.created_at = None
    resource.updated_at = None

    proto = _resource_to_proto(resource)
    assert proto.id == "test-id-123"
    assert proto.kind == "Agent"
    assert proto.name == "test-agent"
    assert proto.namespace == "default"
    assert json.loads(proto.spec_json)["role"] == "tester"
    assert proto.version == 1


def test_execution_to_proto():
    """_execution_to_proto converts an Execution ORM object to proto."""
    from blackbeard.models.execution import ExecutionStatus, ExecutionType

    execution = MagicMock()
    execution.id = "exec-id-456"
    execution.crew_name = "test-crew"
    execution.crew_namespace = "default"
    execution.status = ExecutionStatus.QUEUED
    execution.execution_type = ExecutionType.KICKOFF
    execution.inputs = {"key": "val"}
    execution.outputs = None
    execution.error = None
    execution.total_tokens = 100
    execution.created_at = None
    execution.started_at = None
    execution.completed_at = None

    proto = _execution_to_proto(execution)
    assert proto.id == "exec-id-456"
    assert proto.crew_name == "test-crew"
    assert proto.status == "queued"
    assert proto.execution_type == "kickoff"
    assert json.loads(proto.inputs_json)["key"] == "val"
    assert proto.total_tokens == 100


# ── Servicer unit tests ──────────────────────────────────────────────


@pytest.fixture
def servicer():
    return BlackbeardServicer()


async def test_grpc_health(servicer):
    """gRPC Health returns ok status."""
    from blackbeard.grpc import blackbeard_pb2

    request = blackbeard_pb2.HealthRequest()
    context = MagicMock()

    response = await servicer.Health(request, context)
    assert response.status == "ok"
    assert response.version != ""


async def test_grpc_list_resources(servicer, db_session):
    """gRPC ListResources returns items from the database."""
    from blackbeard.grpc import blackbeard_pb2
    from blackbeard.kinds import ResourceKind
    from blackbeard.models.resource import Resource

    # Insert a resource
    resource = Resource(
        kind=ResourceKind.AGENT,
        name="grpc-agent",
        namespace="default",
        spec={"role": "tester", "goal": "test", "backstory": "test"},
        version=1,
    )
    db_session.add(resource)
    await db_session.commit()

    request = blackbeard_pb2.ListResourcesRequest(
        kind="Agent",
        namespace="default",
        limit=10,
        offset=0,
    )
    context = MagicMock()

    with patch("blackbeard.grpc.server.async_session") as mock_session_ctx:
        mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=db_session)
        mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        response = await servicer.ListResources(request, context)

    assert response.total >= 1
    names = [item.name for item in response.items]
    assert "grpc-agent" in names


async def test_grpc_get_resource(servicer, db_session):
    """gRPC GetResource returns a single resource."""
    from blackbeard.grpc import blackbeard_pb2
    from blackbeard.kinds import ResourceKind
    from blackbeard.models.resource import Resource

    resource = Resource(
        kind=ResourceKind.TASK,
        name="grpc-task",
        namespace="default",
        spec={
            "description": "test task",
            "expected_output": "output",
            "agent": "ref:agents/test",
        },
        version=1,
    )
    db_session.add(resource)
    await db_session.commit()

    request = blackbeard_pb2.GetResourceRequest(
        kind="Task",
        name="grpc-task",
        namespace="default",
    )
    context = MagicMock()

    with patch("blackbeard.grpc.server.async_session") as mock_session_ctx:
        mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=db_session)
        mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        response = await servicer.GetResource(request, context)

    assert response.name == "grpc-task"
    assert response.kind == "Task"


async def test_grpc_get_resource_not_found(servicer, db_session):
    """gRPC GetResource aborts with NOT_FOUND for missing resource."""
    from blackbeard.grpc import blackbeard_pb2

    request = blackbeard_pb2.GetResourceRequest(
        kind="Agent",
        name="nonexistent",
        namespace="default",
    )
    context = AsyncMock()

    with patch("blackbeard.grpc.server.async_session") as mock_session_ctx:
        mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=db_session)
        mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        await servicer.GetResource(request, context)

    context.abort.assert_called_once()


async def test_grpc_delete_resource(servicer, db_session):
    """gRPC DeleteResource deletes and returns True."""
    from blackbeard.grpc import blackbeard_pb2
    from blackbeard.kinds import ResourceKind
    from blackbeard.models.resource import Resource

    resource = Resource(
        kind=ResourceKind.GUARDRAIL,
        name="grpc-guard",
        namespace="default",
        spec={"type": "function"},
        version=1,
    )
    db_session.add(resource)
    await db_session.commit()

    request = blackbeard_pb2.DeleteResourceRequest(
        kind="Guardrail",
        name="grpc-guard",
        namespace="default",
    )
    context = MagicMock()

    with patch("blackbeard.grpc.server.async_session") as mock_session_ctx:
        mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=db_session)
        mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        response = await servicer.DeleteResource(request, context)

    assert response.deleted is True


async def test_grpc_delete_resource_not_found(servicer, db_session):
    """gRPC DeleteResource returns deleted=False for missing resource."""
    from blackbeard.grpc import blackbeard_pb2

    request = blackbeard_pb2.DeleteResourceRequest(
        kind="Agent",
        name="no-such-agent",
        namespace="default",
    )
    context = MagicMock()

    with patch("blackbeard.grpc.server.async_session") as mock_session_ctx:
        mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=db_session)
        mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        response = await servicer.DeleteResource(request, context)

    assert response.deleted is False


async def test_grpc_create_resource(servicer, db_session):
    """gRPC CreateResource creates a new resource."""
    from blackbeard.grpc import blackbeard_pb2

    spec = {"role": "analyst", "goal": "analyze", "backstory": "experienced"}
    request = blackbeard_pb2.CreateResourceRequest(
        api_version="blackbeard/v1",
        kind="Agent",
        name="grpc-new-agent",
        namespace="default",
        spec_json=json.dumps(spec),
    )
    context = MagicMock()

    with patch("blackbeard.grpc.server.async_session") as mock_session_ctx:
        mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=db_session)
        mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        response = await servicer.CreateResource(request, context)

    assert response.name == "grpc-new-agent"
    assert response.kind == "Agent"
    parsed_spec = json.loads(response.spec_json)
    assert parsed_spec["role"] == "analyst"


# ── Server start/stop test ───────────────────────────────────────────


async def test_grpc_server_start_stop():
    """gRPC server can start and stop."""
    from blackbeard.grpc.server import start_grpc_server

    server = await start_grpc_server(port=0)  # port 0 = ephemeral
    assert server is not None
    await server.stop(grace=0)


# ── Proto file exists test ───────────────────────────────────────────


def test_proto_file_exists():
    """Proto file is present in the repo."""
    import os

    proto_path = os.path.join(
        os.path.dirname(__file__), "..", "proto", "blackbeard.proto"
    )
    assert os.path.exists(proto_path)


def test_generated_stubs_importable():
    """Generated gRPC stubs can be imported."""
    from blackbeard.grpc import blackbeard_pb2, blackbeard_pb2_grpc

    assert hasattr(blackbeard_pb2, "Resource")
    assert hasattr(blackbeard_pb2, "HealthRequest")
    assert hasattr(blackbeard_pb2_grpc, "BlackbeardServiceServicer")
    assert hasattr(blackbeard_pb2_grpc, "add_BlackbeardServiceServicer_to_server")
