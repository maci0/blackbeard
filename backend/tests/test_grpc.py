"""Tests for gRPC API (Feature 3)."""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import grpc
import pytest

from blackbeard.grpc.server import (
    AuthInterceptor,
    BlackbeardServicer,
    _execution_to_proto,
    _resource_to_proto,
)

# ── Proto conversion tests ───────────────────────────────────────────


def test_resource_to_proto():
    """_resource_to_proto converts a Resource ORM object to proto."""
    from blackbeard.kinds import ResourceKind
    from tests.conftest import make_resource

    resource = make_resource(
        ResourceKind.AGENT,
        "test-agent",
        {"role": "tester", "goal": "test", "backstory": "test"},
    )
    resource.version = 1

    proto = _resource_to_proto(resource)
    assert proto.kind == "Agent"
    assert proto.name == "test-agent"
    assert proto.project == "default"
    assert json.loads(proto.spec_json)["role"] == "tester"
    assert proto.version == 1


def test_execution_to_proto():
    """_execution_to_proto converts an Execution ORM object to proto."""
    from tests.conftest import _make_execution

    execution = _make_execution(
        crew_name="test-crew",
        status="queued",
        execution_type="kickoff",
        inputs={"key": "val"},
        total_tokens=100,
    )

    proto = _execution_to_proto(execution)
    assert proto.id == str(execution.id)
    assert proto.crew_name == "test-crew"
    assert proto.status == "queued"
    assert proto.execution_type == "kickoff"
    assert json.loads(proto.inputs_json)["key"] == "val"
    assert proto.total_tokens == 100
    assert proto.created_at != "", "Real datetime should serialize to non-empty ISO string"


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
        project="default",
        spec={"role": "tester", "goal": "test", "backstory": "test"},
        version=1,
    )
    db_session.add(resource)
    await db_session.commit()

    request = blackbeard_pb2.ListResourcesRequest(
        kind="Agent",
        project="default",
        limit=10,
        offset=0,
    )
    context = MagicMock()

    with patch("blackbeard.grpc.server.async_session") as mock_session_ctx:
        mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=db_session)
        mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        response = await servicer.ListResources(request, context)

    assert response.total == 1
    assert len(response.items) == 1
    assert response.items[0].name == "grpc-agent"


async def test_grpc_get_resource(servicer, db_session):
    """gRPC GetResource returns a single resource."""
    from blackbeard.grpc import blackbeard_pb2
    from blackbeard.kinds import ResourceKind
    from blackbeard.models.resource import Resource

    resource = Resource(
        kind=ResourceKind.TASK,
        name="grpc-task",
        project="default",
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
        project="default",
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
        project="default",
    )
    context = AsyncMock()

    with patch("blackbeard.grpc.server.async_session") as mock_session_ctx:
        mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=db_session)
        mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        await servicer.GetResource(request, context)

    context.abort.assert_called_once()
    abort_args = context.abort.call_args[0]
    assert abort_args[0] == grpc.StatusCode.NOT_FOUND, (
        f"Expected NOT_FOUND status code, got {abort_args[0]}"
    )


async def test_grpc_delete_resource(servicer, db_session):
    """gRPC DeleteResource deletes and returns True."""
    from blackbeard.grpc import blackbeard_pb2
    from blackbeard.kinds import ResourceKind
    from blackbeard.models.resource import Resource

    resource = Resource(
        kind=ResourceKind.GUARDRAIL,
        name="grpc-guard",
        project="default",
        spec={"type": "function"},
        version=1,
    )
    db_session.add(resource)
    await db_session.commit()

    request = blackbeard_pb2.DeleteResourceRequest(
        kind="Guardrail",
        name="grpc-guard",
        project="default",
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
        project="default",
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
        project="default",
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
    """gRPC server can start and stop without error."""
    from grpc.aio import Server

    from blackbeard.grpc.server import start_grpc_server

    server = await start_grpc_server(port=0)  # port 0 = ephemeral
    assert isinstance(server, Server)
    await server.stop(grace=0)


# ── Proto file exists test ───────────────────────────────────────────


def test_proto_file_exists():
    """Proto file is present in the repo."""
    import os

    proto_path = os.path.join(os.path.dirname(__file__), "..", "proto", "blackbeard.proto")
    assert os.path.exists(proto_path)


def test_generated_stubs_importable():
    """Generated gRPC stubs can be imported."""
    from blackbeard.grpc import blackbeard_pb2, blackbeard_pb2_grpc

    assert hasattr(blackbeard_pb2, "Resource")
    assert hasattr(blackbeard_pb2, "HealthRequest")
    assert hasattr(blackbeard_pb2_grpc, "BlackbeardServiceServicer")
    assert hasattr(blackbeard_pb2_grpc, "add_BlackbeardServiceServicer_to_server")


# ── AuthInterceptor tests ──────────────────────────────────────────────


@pytest.fixture
def auth_interceptor():
    return AuthInterceptor()


async def test_auth_interceptor_allows_health(auth_interceptor):
    """Health RPC should pass through without credentials."""
    handler_call_details = MagicMock()
    handler_call_details.method = "/blackbeard.BlackbeardService/Health"
    handler_call_details.invocation_metadata = []

    continuation = AsyncMock(return_value="handler")
    result = await auth_interceptor.intercept_service(continuation, handler_call_details)
    continuation.assert_called_once_with(handler_call_details)
    assert result == "handler"


async def test_auth_interceptor_rejects_no_credentials(auth_interceptor):
    """Non-Health RPCs without credentials should be rejected."""
    from blackbeard.grpc.server import _AbortingHandler

    handler_call_details = MagicMock()
    handler_call_details.method = "/blackbeard.BlackbeardService/ListResources"
    handler_call_details.invocation_metadata = []

    continuation = AsyncMock()
    result = await auth_interceptor.intercept_service(continuation, handler_call_details)
    continuation.assert_not_called()
    assert isinstance(result, _AbortingHandler)


async def test_auth_interceptor_accepts_valid_api_key(auth_interceptor):
    """Valid API key in metadata should be accepted."""
    from blackbeard.auth.api_key import _EXPECTED_API_KEY

    handler_call_details = MagicMock()
    handler_call_details.method = "/blackbeard.BlackbeardService/ListResources"
    handler_call_details.invocation_metadata = [
        ("x-api-key", _EXPECTED_API_KEY),
    ]

    continuation = AsyncMock(return_value="handler")
    result = await auth_interceptor.intercept_service(continuation, handler_call_details)
    continuation.assert_called_once()
    assert result == "handler"


async def test_auth_interceptor_rejects_invalid_api_key(auth_interceptor):
    """Invalid API key in metadata should be rejected."""
    from blackbeard.grpc.server import _AbortingHandler

    handler_call_details = MagicMock()
    handler_call_details.method = "/blackbeard.BlackbeardService/GetResource"
    handler_call_details.invocation_metadata = [
        ("x-api-key", "wrong-key"),
    ]

    continuation = AsyncMock()
    result = await auth_interceptor.intercept_service(continuation, handler_call_details)
    continuation.assert_not_called()
    assert isinstance(result, _AbortingHandler)


async def test_auth_interceptor_accepts_valid_jwt(auth_interceptor):
    """Valid JWT Bearer token in metadata should be accepted."""
    from blackbeard.auth.jwt import create_access_token

    token = create_access_token(user_id=str(uuid.uuid4()))

    handler_call_details = MagicMock()
    handler_call_details.method = "/blackbeard.BlackbeardService/CreateResource"
    handler_call_details.invocation_metadata = [
        ("authorization", f"Bearer {token}"),
    ]

    continuation = AsyncMock(return_value="handler")
    result = await auth_interceptor.intercept_service(continuation, handler_call_details)
    continuation.assert_called_once()
    assert result == "handler"


async def test_auth_interceptor_rejects_invalid_jwt(auth_interceptor):
    """Invalid JWT token should be rejected."""
    from blackbeard.grpc.server import _AbortingHandler

    handler_call_details = MagicMock()
    handler_call_details.method = "/blackbeard.BlackbeardService/DeleteResource"
    handler_call_details.invocation_metadata = [
        ("authorization", "Bearer invalid.jwt.token"),
    ]

    continuation = AsyncMock()
    result = await auth_interceptor.intercept_service(continuation, handler_call_details)
    continuation.assert_not_called()
    assert isinstance(result, _AbortingHandler)


async def test_auth_interceptor_rejects_refresh_token(auth_interceptor):
    """Refresh JWT token (type != access) should be rejected."""
    from blackbeard.auth.jwt import create_refresh_token
    from blackbeard.grpc.server import _AbortingHandler

    token = create_refresh_token(user_id=str(uuid.uuid4()))

    handler_call_details = MagicMock()
    handler_call_details.method = "/blackbeard.BlackbeardService/Kickoff"
    handler_call_details.invocation_metadata = [
        ("authorization", f"Bearer {token}"),
    ]

    continuation = AsyncMock()
    result = await auth_interceptor.intercept_service(continuation, handler_call_details)
    continuation.assert_not_called()
    assert isinstance(result, _AbortingHandler)


async def test_auth_interceptor_rejects_expired_jwt(auth_interceptor):
    """Expired JWT token should be rejected."""
    from datetime import UTC, datetime, timedelta

    import jwt as pyjwt

    from blackbeard.auth.jwt import _ALGORITHM, _AUDIENCE, _ISSUER, _get_secret
    from blackbeard.grpc.server import _AbortingHandler

    now = datetime.now(UTC)
    payload = {
        "sub": str(uuid.uuid4()),
        "type": "access",
        "iss": _ISSUER,
        "aud": _AUDIENCE,
        "iat": now - timedelta(hours=2),
        "exp": now - timedelta(hours=1),
    }
    expired_token = pyjwt.encode(payload, _get_secret(), algorithm=_ALGORITHM)

    handler_call_details = MagicMock()
    handler_call_details.method = "/blackbeard.BlackbeardService/GetExecution"
    handler_call_details.invocation_metadata = [
        ("authorization", f"Bearer {expired_token}"),
    ]

    continuation = AsyncMock()
    result = await auth_interceptor.intercept_service(continuation, handler_call_details)
    continuation.assert_not_called()
    assert isinstance(result, _AbortingHandler)


async def test_grpc_server_starts_with_auth_interceptor():
    """gRPC server should start with the AuthInterceptor installed."""
    from grpc.aio import Server

    from blackbeard.grpc.server import start_grpc_server

    server = await start_grpc_server(port=0)
    assert isinstance(server, Server)
    await server.stop(grace=0)
