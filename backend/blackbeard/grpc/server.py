"""gRPC server implementation for the Blackbeard service.

Delegates to the existing ResourceService and executor for all operations,
providing a high-performance gRPC interface alongside the REST API.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any
from uuid import UUID

import grpc

from blackbeard import __version__
from blackbeard.grpc import blackbeard_pb2, blackbeard_pb2_grpc
from blackbeard.kinds import API_VERSION, KIND_TO_PLURAL, PLURAL_TO_KIND
from blackbeard.models import async_session
from blackbeard.models.resource_schemas import (
    ResourceCreate,
    ResourceMetadata,
)
from blackbeard.resources import (
    ResourceNotFoundError,
    ResourceService,
    ResourceValidationError,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)


def _resource_to_proto(resource: Any) -> blackbeard_pb2.Resource:
    """Convert a Resource ORM object to a protobuf Resource message."""
    return blackbeard_pb2.Resource(
        id=str(resource.id) if resource.id else "",
        api_version=API_VERSION,
        kind=resource.kind.value if hasattr(resource.kind, "value") else str(resource.kind),
        name=resource.name or "",
        namespace=resource.namespace or "default",
        spec_json=json.dumps(resource.spec) if resource.spec else "{}",
        version=resource.version or 1,
        created_at=resource.created_at.isoformat() if resource.created_at else "",
        updated_at=resource.updated_at.isoformat() if resource.updated_at else "",
    )


def _execution_to_proto(execution: Any) -> blackbeard_pb2.Execution:
    """Convert an Execution ORM object to a protobuf Execution message."""
    return blackbeard_pb2.Execution(
        id=str(execution.id) if execution.id else "",
        crew_name=execution.crew_name or "",
        namespace=execution.crew_namespace or "default",
        status=execution.status.value if hasattr(execution.status, "value") else str(execution.status),
        execution_type=(
            execution.execution_type.value
            if hasattr(execution.execution_type, "value")
            else str(execution.execution_type)
        ),
        inputs_json=json.dumps(execution.inputs) if execution.inputs else "{}",
        outputs_json=json.dumps(execution.outputs) if execution.outputs else "{}",
        error=execution.error or "",
        total_tokens=execution.total_tokens or 0,
        created_at=execution.created_at.isoformat() if execution.created_at else "",
        started_at=execution.started_at.isoformat() if execution.started_at else "",
        completed_at=execution.completed_at.isoformat() if execution.completed_at else "",
    )


def _resolve_kind(kind_str: str) -> str:
    """Convert a kind string from proto to internal kind value.

    Accepts both 'Agent' (kind value) and 'agents' (plural) forms.
    """
    if kind_str in KIND_TO_PLURAL:
        return kind_str
    if kind_str in PLURAL_TO_KIND:
        return PLURAL_TO_KIND[kind_str]
    return kind_str


class BlackbeardServicer(blackbeard_pb2_grpc.BlackbeardServiceServicer):
    """gRPC service implementation for Blackbeard."""

    async def Health(
        self,
        request: blackbeard_pb2.HealthRequest,
        context: grpc.aio.ServicerContext,
    ) -> blackbeard_pb2.HealthResponse:
        """Health check."""
        return blackbeard_pb2.HealthResponse(
            status="ok",
            version=__version__,
        )

    async def ListResources(
        self,
        request: blackbeard_pb2.ListResourcesRequest,
        context: grpc.aio.ServicerContext,
    ) -> blackbeard_pb2.ListResourcesResponse:
        """List resources by kind."""
        kind = _resolve_kind(request.kind)
        namespace = request.namespace or None
        limit = request.limit or 100
        offset = request.offset or 0

        async with async_session() as session:
            service = ResourceService(session)
            items, total = await service.list_resources(
                kind=kind,
                namespace=namespace,
                limit=limit,
                offset=offset,
            )

        return blackbeard_pb2.ListResourcesResponse(
            items=[_resource_to_proto(r) for r in items],
            total=total,
        )

    async def GetResource(
        self,
        request: blackbeard_pb2.GetResourceRequest,
        context: grpc.aio.ServicerContext,
    ) -> blackbeard_pb2.Resource:
        """Get a single resource."""
        kind = _resolve_kind(request.kind)
        namespace = request.namespace or "default"

        async with async_session() as session:
            service = ResourceService(session)
            try:
                resource = await service.get(kind, request.name, namespace)
            except ResourceNotFoundError as exc:
                await context.abort(grpc.StatusCode.NOT_FOUND, str(exc))

        return _resource_to_proto(resource)

    async def CreateResource(
        self,
        request: blackbeard_pb2.CreateResourceRequest,
        context: grpc.aio.ServicerContext,
    ) -> blackbeard_pb2.Resource:
        """Create a resource."""
        kind = _resolve_kind(request.kind)
        namespace = request.namespace or "default"

        try:
            spec = json.loads(request.spec_json) if request.spec_json else {}
        except json.JSONDecodeError as exc:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                f"Invalid spec_json: {exc}",
            )

        data = ResourceCreate(
            apiVersion=request.api_version or API_VERSION,
            kind=kind,
            metadata=ResourceMetadata(name=request.name, namespace=namespace),
            spec=spec,
        )

        async with async_session() as session:
            service = ResourceService(session)
            try:
                resource, _created = await service.create(data)
                await session.commit()
            except ResourceValidationError as exc:
                await context.abort(
                    grpc.StatusCode.INVALID_ARGUMENT,
                    str(exc),
                )

        return _resource_to_proto(resource)

    async def DeleteResource(
        self,
        request: blackbeard_pb2.DeleteResourceRequest,
        context: grpc.aio.ServicerContext,
    ) -> blackbeard_pb2.DeleteResponse:
        """Delete a resource."""
        kind = _resolve_kind(request.kind)
        namespace = request.namespace or "default"

        async with async_session() as session:
            service = ResourceService(session)
            try:
                await service.delete(kind, request.name, namespace)
                await session.commit()
            except ResourceNotFoundError:
                return blackbeard_pb2.DeleteResponse(deleted=False)

        return blackbeard_pb2.DeleteResponse(deleted=True)

    async def Kickoff(
        self,
        request: blackbeard_pb2.KickoffRequest,
        context: grpc.aio.ServicerContext,
    ) -> blackbeard_pb2.Execution:
        """Kick off a crew execution."""
        from blackbeard.engine import ExecutionError, ExecutionNotFoundError
        from blackbeard.engine import executor as _executor_mod

        namespace = request.namespace or "default"
        try:
            inputs = json.loads(request.inputs_json) if request.inputs_json else {}
        except json.JSONDecodeError as exc:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                f"Invalid inputs_json: {exc}",
            )

        async with async_session() as session:
            try:
                execution = await _executor_mod.kickoff(
                    session,
                    request.crew_name,
                    inputs,
                    namespace,
                )
            except ExecutionNotFoundError as exc:
                await context.abort(grpc.StatusCode.NOT_FOUND, str(exc))
            except ExecutionError as exc:
                await context.abort(grpc.StatusCode.INTERNAL, str(exc))

        return _execution_to_proto(execution)

    async def GetExecution(
        self,
        request: blackbeard_pb2.GetExecutionRequest,
        context: grpc.aio.ServicerContext,
    ) -> blackbeard_pb2.Execution:
        """Get execution details."""
        from blackbeard.engine import executor as _executor_mod

        try:
            execution_id = UUID(request.execution_id)
        except ValueError:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                f"Invalid execution_id: {request.execution_id}",
            )

        async with async_session() as session:
            execution = await _executor_mod.get_execution(session, execution_id)
            if execution is None:
                await context.abort(
                    grpc.StatusCode.NOT_FOUND,
                    f"Execution '{request.execution_id}' not found",
                )

        return _execution_to_proto(execution)

    async def StreamEvents(
        self,
        request: blackbeard_pb2.StreamEventsRequest,
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[blackbeard_pb2.ExecutionEvent]:
        """Stream execution events."""
        from blackbeard.engine import executor as _executor_mod
        from blackbeard.models import TERMINAL_STATUSES

        try:
            execution_id = UUID(request.execution_id)
        except ValueError:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                f"Invalid execution_id: {request.execution_id}",
            )
            return

        last_seq = request.after_sequence or -1
        max_polls = 200

        for _ in range(max_polls):
            async with async_session() as session:
                status = await _executor_mod.get_execution_status(session, execution_id)
                if status is None:
                    await context.abort(
                        grpc.StatusCode.NOT_FOUND,
                        f"Execution '{request.execution_id}' not found",
                    )
                    return

                events = await _executor_mod.list_execution_events(
                    session, execution_id, after=last_seq, limit=50
                )
                for ev in events:
                    yield blackbeard_pb2.ExecutionEvent(
                        sequence=ev.sequence,
                        event_type=ev.event_type,
                        timestamp=ev.timestamp.isoformat() if ev.timestamp else "",
                        data_json=json.dumps(ev.data) if ev.data else "{}",
                    )
                    last_seq = ev.sequence

                if status in TERMINAL_STATUSES:
                    return

            await asyncio.sleep(2)


async def start_grpc_server(port: int = 50051) -> grpc.aio.Server:
    """Create and start the gRPC server."""
    server = grpc.aio.server()
    servicer = BlackbeardServicer()
    blackbeard_pb2_grpc.add_BlackbeardServiceServicer_to_server(servicer, server)
    server.add_insecure_port(f"[::]:{port}")
    await server.start()
    logger.info(
        "gRPC server started on port %d",
        port,
        extra={"event": "grpc_server_started", "port": port},
    )
    return server
