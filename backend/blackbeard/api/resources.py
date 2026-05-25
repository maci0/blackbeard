"""REST API endpoints for generic resource CRUD operations."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Generator
from typing import Any

import yaml
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from blackbeard.audit import audit_from_request, log_audit
from blackbeard.auth.dependencies import check_resource_permission, get_current_user
from blackbeard.kinds import API_VERSION, NAME_PATTERN, PLURAL_TO_KIND, ResourceKind
from blackbeard.litellm import model_sync
from blackbeard.models import User, get_session
from blackbeard.models.resource_schemas import (
    ResourceCreate,
    ResourceListResponse,
    ResourceResponse,
    ResourceUpdate,
)
from blackbeard.resources import (
    ResourceConflictError,
    ResourceNotFoundError,
    ResourceService,
    ResourceValidationError,
)

logger = logging.getLogger(__name__)

_yaml_dumper: Any = getattr(yaml, "CSafeDumper", yaml.SafeDumper)

_background_tasks: set[asyncio.Task[None]] = set()


def _log_bg_task_exception(task: asyncio.Task[None]) -> None:
    _background_tasks.discard(task)
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error(
            "Background task %s failed: %s",
            task.get_name(),
            exc,
            exc_info=exc,
            extra={
                "event": "background_task_failed",
                "task_name": task.get_name(),
                "error_type": type(exc).__name__,
                "error_message": str(exc)[:500],
            },
        )


def _fire_and_forget(coro: Any) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_log_bg_task_exception)


_LLM_KIND = "LLMConnection"


async def _sync_llm_to_litellm(kind: str, name: str, spec: dict[str, Any] | None) -> None:
    """Push LLMConnection changes to LiteLLM proxy. Fire-and-forget."""
    if kind != _LLM_KIND:
        return
    try:
        if spec is not None:
            await model_sync.add_model(name, spec)
        else:
            await model_sync.delete_model(name)
    except Exception:
        logger.warning(
            "LiteLLM sync failed for %s (non-fatal)",
            name,
            exc_info=True,
            extra={"event": "litellm_sync_failed", "model_name": name},
        )


router = APIRouter(tags=["resources"])

_KIND_PATTERN = "^(" + "|".join(PLURAL_TO_KIND.keys()) + ")$"

_AUTOMATION_KIND = ResourceKind.AUTOMATION.value


async def _maybe_reload_scheduler(request: Request, kind: str) -> None:
    """Trigger scheduler reload when an Automation resource is modified."""
    if kind != _AUTOMATION_KIND:
        return
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is not None:
        try:
            await scheduler.reload()
        except Exception as exc:
            logger.error(
                "Scheduler reload failed after Automation change — "
                "cron schedules may be stale until next restart",
                exc_info=True,
                extra={
                    "event": "scheduler_reload_failed",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc)[:500],
                },
            )


def _resolve_kind(kind_plural: str) -> str:
    """Validate kind_plural and return the ResourceKind value string."""
    kind = PLURAL_TO_KIND.get(kind_plural)
    if kind is None:
        valid = ", ".join(sorted(PLURAL_TO_KIND.keys()))
        raise HTTPException(
            status_code=404,
            detail=f"Unknown resource kind '{kind_plural}'. Valid kinds: {valid}",
        )
    return kind


def _resource_to_document(resource: Any) -> dict[str, Any]:
    """Convert a Resource ORM object to a YAML-serializable document."""
    return {
        "apiVersion": API_VERSION,
        "kind": resource.kind.value,
        "metadata": {
            "name": resource.name,
            "namespace": resource.namespace,
        },
        "spec": resource.spec,
    }


@router.get(
    "/resources/export",
    responses={
        200: {
            "description": "All resources as a multi-document YAML stream",
            "content": {"application/x-yaml": {}},
        },
    },
)
async def export_resources(
    namespace: str | None = Query(
        default=None,
        pattern=NAME_PATTERN,
        max_length=255,
        description="Filter by namespace (omit for all namespaces)",
    ),
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(get_current_user),
) -> StreamingResponse:
    """Export all resources as a multi-document YAML stream.

    Returns resources separated by ``---`` document markers, suitable for
    piping into ``blackbeard apply -f -`` or storing as a backup file.
    """
    service = ResourceService(session)
    items, _total = await service.list_resources(
        namespace=namespace,
        limit=10_000,
        offset=0,
    )

    def _generate_yaml() -> Generator[str]:
        for resource in items:
            doc = _resource_to_document(resource)
            yield yaml.dump(
                doc,
                Dumper=_yaml_dumper,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
                explicit_start=True,
            )

    return StreamingResponse(_generate_yaml(), media_type="application/x-yaml")


@router.get(
    "/{kind_plural}",
    response_model=ResourceListResponse,
    responses={
        400: {"description": "Invalid label_selector format"},
        404: {"description": "Unknown resource kind"},
    },
)
async def list_resources(
    kind_plural: str = Path(..., pattern=_KIND_PATTERN),
    namespace: str | None = Query(
        default=None,
        pattern=NAME_PATTERN,
        max_length=255,
        description="Filter by namespace (omit for all namespaces)",
    ),
    label_selector: str | None = Query(
        default=None,
        max_length=1024,
        description="Comma-separated label filters, e.g. 'env=prod,team=ml'",
    ),
    limit: int = Query(default=100, ge=1, le=1000, description="Max results"),
    offset: int = Query(default=0, ge=0, le=100_000, description="Results to skip"),
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(check_resource_permission),
) -> ResourceListResponse:
    """List resources of a given kind."""
    kind = _resolve_kind(kind_plural)
    labels: dict[str, str] | None = None
    if label_selector:
        labels = {}
        for pair in label_selector.split(","):
            pair = pair.strip()
            if "=" not in pair:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid label selector '{pair}': expected 'key=value' format",
                )
            k, v = pair.split("=", 1)
            k = k.strip()
            if not k:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid label selector '{pair}': empty key",
                )
            if k in labels:
                raise HTTPException(
                    status_code=400,
                    detail=f"Duplicate label key '{k}' in selector",
                )
            labels[k] = v.strip()
    service = ResourceService(session)
    items, total = await service.list_resources(
        kind=kind,
        namespace=namespace,
        labels=labels,
        limit=limit,
        offset=offset,
    )
    return ResourceListResponse(
        items=[ResourceResponse.from_db(r) for r in items],
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + limit) < total,
    )


@router.post(
    "/{kind_plural}",
    response_model=ResourceResponse,
    status_code=201,
    responses={
        200: {"description": "Resource updated (upsert)", "model": ResourceResponse},
        422: {"description": "Validation error or kind mismatch between URL and body"},
    },
)
async def create_resource(
    data: ResourceCreate,
    request: Request,
    response: Response,
    kind_plural: str = Path(..., pattern=_KIND_PATTERN),
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(check_resource_permission),
) -> ResourceResponse:
    """Create (or upsert) a resource of a given kind."""
    url_kind = _resolve_kind(kind_plural)
    if data.kind != url_kind:
        raise HTTPException(
            status_code=422,
            detail=f"Kind mismatch: URL is for '{url_kind}' but body has kind '{data.kind}'",
        )
    service = ResourceService(session)
    try:
        resource, created = await service.create(data)
        audit_action = "resource_created" if created else "resource_updated"
        await log_audit(
            session,
            action=audit_action,
            resource_type=data.kind,
            resource_id=data.metadata.name,
            **audit_from_request(request, user),
        )
        await session.commit()
    except ResourceValidationError as exc:
        logger.warning(
            "Resource validation failed: %s/%s namespace=%s",
            data.kind,
            data.metadata.name,
            data.metadata.namespace,
            extra={
                "event": "resource_api_validation_failed",
                "resource_kind": data.kind,
                "resource_name": data.metadata.name,
                "namespace": data.metadata.namespace,
                "error_count": len(exc.errors),
            },
        )
        raise HTTPException(
            status_code=422,
            detail=[e.to_dict() for e in exc.errors],
        ) from exc
    if created:
        ns = data.metadata.namespace
        response.headers["Location"] = f"/api/v1/{kind_plural}/{data.metadata.name}?namespace={ns}"
    else:
        response.status_code = 200
    _fire_and_forget(_maybe_reload_scheduler(request, url_kind))
    _fire_and_forget(_sync_llm_to_litellm(url_kind, data.metadata.name, data.spec))
    return ResourceResponse.from_db(resource)


@router.get(
    "/{kind_plural}/{name}",
    response_model=ResourceResponse,
    responses={404: {"description": "Resource not found"}},
)
async def get_resource(
    kind_plural: str = Path(..., pattern=_KIND_PATTERN),
    name: str = Path(
        ...,
        pattern=NAME_PATTERN,
        max_length=255,
        description="Resource name",
    ),
    namespace: str = Query(
        default="default",
        pattern=NAME_PATTERN,
        max_length=255,
        description="Resource namespace",
    ),
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(check_resource_permission),
) -> ResourceResponse:
    """Get a single resource by kind and name."""
    kind = _resolve_kind(kind_plural)
    service = ResourceService(session)
    try:
        resource = await service.get(kind, name, namespace)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ResourceResponse.from_db(resource)


@router.put(
    "/{kind_plural}/{name}",
    response_model=ResourceResponse,
    responses={
        404: {"description": "Resource not found"},
        409: {"description": "Version conflict (optimistic locking)"},
        422: {"description": "Validation error or name/namespace mismatch"},
    },
)
async def update_resource(
    data: ResourceUpdate,
    request: Request,
    kind_plural: str = Path(..., pattern=_KIND_PATTERN),
    name: str = Path(
        ...,
        pattern=NAME_PATTERN,
        max_length=255,
        description="Resource name",
    ),
    namespace: str = Query(
        default="default",
        pattern=NAME_PATTERN,
        max_length=255,
        description="Resource namespace",
    ),
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(check_resource_permission),
) -> ResourceResponse:
    """Update a resource by kind and name (optimistic locking via version)."""
    kind = _resolve_kind(kind_plural)

    if data.metadata is not None:
        if data.metadata.name != name:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Cannot rename resource: URL name is '{name}'"
                    f" but body has '{data.metadata.name}'"
                ),
            )
        if data.metadata.namespace != namespace:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Cannot move resource to different namespace: "
                    f"URL namespace is '{namespace}' but body has '{data.metadata.namespace}'"
                ),
            )

    service = ResourceService(session)
    try:
        resource = await service.update(kind, name, data, namespace=namespace)
        await log_audit(
            session,
            action="resource_updated",
            resource_type=kind,
            resource_id=name,
            **audit_from_request(request, user),
        )
        await session.commit()
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ResourceConflictError as exc:
        logger.warning(
            "Version conflict: %s/%s namespace=%s",
            kind,
            name,
            namespace,
            extra={
                "event": "resource_version_conflict",
                "resource_kind": kind,
                "resource_name": name,
                "namespace": namespace,
            },
        )
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ResourceValidationError as exc:
        logger.warning(
            "Resource update validation failed: %s/%s namespace=%s",
            kind,
            name,
            namespace,
            extra={
                "event": "resource_update_validation_failed",
                "resource_kind": kind,
                "resource_name": name,
                "namespace": namespace,
                "error_count": len(exc.errors),
            },
        )
        raise HTTPException(
            status_code=422,
            detail=[e.to_dict() for e in exc.errors],
        ) from exc
    _fire_and_forget(_maybe_reload_scheduler(request, kind))
    _fire_and_forget(_sync_llm_to_litellm(kind, name, resource.spec))
    return ResourceResponse.from_db(resource)


@router.delete(
    "/{kind_plural}/{name}",
    status_code=204,
    responses={204: {"description": "Resource deleted (or did not exist — idempotent)"}},
)
async def delete_resource(
    request: Request,
    kind_plural: str = Path(..., pattern=_KIND_PATTERN),
    name: str = Path(
        ...,
        pattern=NAME_PATTERN,
        max_length=255,
        description="Resource name",
    ),
    namespace: str = Query(
        default="default",
        pattern=NAME_PATTERN,
        max_length=255,
        description="Resource namespace",
    ),
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(check_resource_permission),
) -> None:
    """Delete a resource by kind and name. Idempotent."""
    kind = _resolve_kind(kind_plural)
    service = ResourceService(session)
    try:
        await service.delete(kind, name, namespace)
        await log_audit(
            session,
            action="resource_deleted",
            resource_type=kind,
            resource_id=name,
            **audit_from_request(request, user),
        )
        await session.commit()
    except ResourceNotFoundError:
        logger.debug(
            "Delete no-op: %s/%s not found in namespace=%s",
            kind,
            name,
            namespace,
            extra={
                "event": "resource_delete_noop",
                "resource_kind": kind,
                "resource_name": name,
                "namespace": namespace,
            },
        )
    else:
        _fire_and_forget(_maybe_reload_scheduler(request, kind))
        _fire_and_forget(_sync_llm_to_litellm(kind, name, None))
