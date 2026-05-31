"""gRPC server implementation for the Blackbeard service.

Delegates to the existing ResourceService and executor for all operations,
providing a high-performance gRPC interface alongside the REST API.
"""
# mypy: ignore-errors

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import time
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import grpc

from blackbeard import __version__
from blackbeard.config import settings
from blackbeard.grpc import blackbeard_pb2, blackbeard_pb2_grpc
from blackbeard.kinds import API_VERSION, KIND_TO_PLURAL, PLURAL_TO_KIND
from blackbeard.logging_config import request_id_var, user_id_var
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


def _unauthenticated_handler(_request: Any, context: grpc.aio.ServicerContext) -> None:
    """Abort the call with UNAUTHENTICATED status."""
    context.abort(grpc.StatusCode.UNAUTHENTICATED, "Authentication required")


class _AbortingHandler(grpc.GenericRpcHandler):
    """RPC handler that aborts every call with UNAUTHENTICATED."""

    def service(self, handler_call_details: Any) -> grpc.RpcMethodHandler:
        return grpc.unary_unary_rpc_method_handler(_unauthenticated_handler)


class LoggingInterceptor(grpc.aio.ServerInterceptor):
    """gRPC interceptor that logs method, duration, and status for every call."""

    async def intercept_service(
        self,
        continuation: Any,
        handler_call_details: grpc.HandlerCallDetails,
    ) -> Any:
        method = handler_call_details.method
        request_id = str(uuid4())
        request_id_var.set(request_id)
        user_id_var.set("")
        start = time.monotonic()
        handler = await continuation(handler_call_details)

        if method.endswith("/Health"):
            return handler

        duration_ms = round((time.monotonic() - start) * 1000, 1)
        logger.info(
            "gRPC %s %.0fms",
            method,
            duration_ms,
            extra={
                "event": "grpc_request",
                "grpc_method": method,
                "duration_ms": duration_ms,
            },
        )
        return handler


class AuthInterceptor(grpc.aio.ServerInterceptor):
    """gRPC server interceptor that validates API key or JWT Bearer token.

    Allows the ``Health`` RPC without authentication.  All other RPCs
    require either an ``x-api-key`` metadata entry matching the configured
    API key, or an ``authorization: Bearer <JWT>`` metadata entry with a
    valid access token.
    """

    async def intercept_service(
        self,
        continuation: Any,
        handler_call_details: grpc.HandlerCallDetails,
    ) -> Any:
        # Allow Health checks without auth
        method = handler_call_details.method
        if method.endswith("/Health"):
            return await continuation(handler_call_details)

        # gRPC metadata keys are case-sensitive per the HTTP/2 spec, but
        # some clients may send mixed-case headers.  Normalize to lower-
        # case for robust matching.  Use the *last* value for each key
        # to match HTTP semantics (last header wins).
        metadata: dict[str, str] = {}
        for key, value in handler_call_details.invocation_metadata:
            metadata[key.lower()] = value

        api_key = metadata.get("x-api-key", "")
        if api_key:
            from blackbeard.auth import get_api_key

            if hmac.compare_digest(api_key.encode(), get_api_key().encode()):
                return await continuation(handler_call_details)

            logger.warning(
                "gRPC auth failed: invalid API key for %s",
                method,
                extra={
                    "event": "grpc_auth_failure",
                    "method": method,
                    "reason": "invalid_api_key",
                },
            )
            return _AbortingHandler()

        auth = metadata.get("authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
            import jwt as pyjwt

            from blackbeard.auth import decode_access_token

            try:
                payload = decode_access_token(token)
                user_id_var.set(payload.get("sub", ""))
                return await continuation(handler_call_details)
            except (pyjwt.ExpiredSignatureError, pyjwt.InvalidTokenError) as exc:
                logger.warning(
                    "gRPC auth failed: invalid JWT for %s (%s)",
                    method,
                    type(exc).__name__,
                    extra={
                        "event": "grpc_auth_failure",
                        "method": method,
                        "reason": type(exc).__name__,
                    },
                )
                return _AbortingHandler()

        logger.warning(
            "gRPC auth failed: no credentials for %s",
            method,
            extra={
                "event": "grpc_auth_failure",
                "method": method,
                "reason": "no_credentials",
            },
        )
        return _AbortingHandler()


async def _enforce_rbac_guard(context: grpc.aio.ServicerContext) -> None:
    """Abort with PERMISSION_DENIED when RBAC is enabled.

    The gRPC interface does not carry user identity for RBAC checks.
    Until per-user authorization is implemented for gRPC, mutating
    operations must be rejected when RBAC is enforced (CWE-285).
    """
    if settings.enforce_rbac:
        await context.abort(
            grpc.StatusCode.PERMISSION_DENIED,
            "RBAC is enabled — mutating operations require the REST API",
        )


def _resource_to_proto(resource: Any) -> blackbeard_pb2.Resource:
    """Convert a Resource ORM object to a protobuf Resource message."""
    return blackbeard_pb2.Resource(
        id=str(resource.id) if resource.id else "",
        api_version=API_VERSION,
        kind=resource.kind.value if hasattr(resource.kind, "value") else str(resource.kind),
        name=resource.name or "",
        project=resource.project or "default",
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
        project=execution.crew_project or "default",
        status=execution.status.value
        if hasattr(execution.status, "value")
        else str(execution.status),
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
        project = request.project or None
        limit = request.limit or 100
        offset = request.offset or 0

        async with async_session() as session:
            service = ResourceService(session)
            items, total = await service.list_resources(
                kind=kind,
                project=project,
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
        project = request.project or "default"

        async with async_session() as session:
            service = ResourceService(session)
            try:
                resource = await service.get(kind, request.name, project)
            except ResourceNotFoundError as exc:
                await context.abort(grpc.StatusCode.NOT_FOUND, str(exc))
                return blackbeard_pb2.Resource()

        return _resource_to_proto(resource)

    async def CreateResource(
        self,
        request: blackbeard_pb2.CreateResourceRequest,
        context: grpc.aio.ServicerContext,
    ) -> blackbeard_pb2.Resource:
        """Create a resource."""
        await _enforce_rbac_guard(context)
        kind = _resolve_kind(request.kind)
        project = request.project or "default"

        try:
            spec = json.loads(request.spec_json) if request.spec_json else {}
        except json.JSONDecodeError:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "Invalid spec_json: malformed JSON",
            )
            return blackbeard_pb2.Resource()

        data = ResourceCreate(
            apiVersion=request.api_version or API_VERSION,
            kind=kind,
            metadata=ResourceMetadata(name=request.name, project=project),
            spec=spec,
        )

        async with async_session() as session:
            service = ResourceService(session)
            try:
                resource, _created = await service.create(data)
                await session.commit()
            except ResourceValidationError as exc:
                msgs = "; ".join(e.message for e in exc.errors)
                await context.abort(
                    grpc.StatusCode.INVALID_ARGUMENT,
                    f"Resource validation failed: {msgs[:500]}",
                )
                return blackbeard_pb2.Resource()

        return _resource_to_proto(resource)

    async def DeleteResource(
        self,
        request: blackbeard_pb2.DeleteResourceRequest,
        context: grpc.aio.ServicerContext,
    ) -> blackbeard_pb2.DeleteResponse:
        """Delete a resource."""
        await _enforce_rbac_guard(context)
        kind = _resolve_kind(request.kind)
        project = request.project or "default"

        async with async_session() as session:
            service = ResourceService(session)
            try:
                await service.delete(kind, request.name, project)
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
        await _enforce_rbac_guard(context)
        from blackbeard.engine import ExecutionError, ExecutionNotFoundError
        from blackbeard.engine import executor as _executor_mod

        project = request.project or "default"
        try:
            inputs = json.loads(request.inputs_json) if request.inputs_json else {}
        except json.JSONDecodeError:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "Invalid inputs_json: malformed JSON",
            )
            return blackbeard_pb2.Execution()

        async with async_session() as session:
            try:
                execution = await _executor_mod.kickoff(
                    session,
                    request.crew_name,
                    inputs,
                    project,
                )
            except ExecutionNotFoundError as exc:
                await context.abort(grpc.StatusCode.NOT_FOUND, str(exc))
                return blackbeard_pb2.Execution()
            except ExecutionError as exc:
                logger.error(
                    "gRPC Kickoff failed: crew=%s: %s",
                    request.crew_name,
                    exc,
                    exc_info=True,
                    extra={
                        "event": "grpc_kickoff_failed",
                        "crew_name": request.crew_name,
                        "error_type": type(exc).__name__,
                    },
                )
                await context.abort(
                    grpc.StatusCode.INTERNAL,
                    "Execution could not be created. Check server logs.",
                )
                return blackbeard_pb2.Execution()

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
            return blackbeard_pb2.Execution()

        async with async_session() as session:
            execution = await _executor_mod.get_execution(session, execution_id)
            if execution is None:
                await context.abort(
                    grpc.StatusCode.NOT_FOUND,
                    f"Execution '{request.execution_id}' not found",
                )
                return blackbeard_pb2.Execution()

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
    server = grpc.aio.server(interceptors=[LoggingInterceptor(), AuthInterceptor()])
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
