"""REST API endpoints for generic resource CRUD operations."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any

import yaml
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from blackbeard.api import MUTATION_RATE_MSG as _MUTATION_RATE_MSG
from blackbeard.audit import audit_from_request, log_audit
from blackbeard.auth.authorizer import clear_cache as _clear_authz_cache
from blackbeard.auth.dependencies import check_resource_permission, get_current_user
from blackbeard.kinds import API_VERSION, NAME_PATTERN, PLURAL_TO_KIND, ResourceKind
from blackbeard.litellm import model_sync
from blackbeard.logging_config import log_task_exception
from blackbeard.models import ResourceVersion, User, get_session
from blackbeard.models.resource_schemas import (
    ResourceCreate,
    ResourceListResponse,
    ResourceResponse,
    ResourceUpdate,
)
from blackbeard.rate_limiter import check_rate_limit, mutation_limiter
from blackbeard.resources import (
    ResourceConflictError,
    ResourceNotFoundError,
    ResourceService,
    ResourceValidationError,
)

logger = logging.getLogger(__name__)

_yaml_dumper: Any = getattr(yaml, "CSafeDumper", yaml.SafeDumper)

_background_tasks: set[asyncio.Task[None]] = set()


def _discard_and_log(task: asyncio.Task[None]) -> None:
    _background_tasks.discard(task)
    log_task_exception(task)


def _fire_and_forget(coro: Any) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_discard_and_log)


_LLM_KIND = "LLMConnection"
_AUTHZ_CACHE_KINDS = frozenset({ResourceKind.ROLE.value, ResourceKind.ROLE_BINDING.value})


def _post_mutation_hooks(
    request: Request,
    kind: str,
    name: str,
    spec: dict[str, Any] | None = None,
) -> None:
    """Fire scheduler/LiteLLM/RBAC side-effects after a resource mutation."""
    _fire_and_forget(_maybe_reload_scheduler(request, kind))
    _fire_and_forget(_sync_llm_to_litellm(kind, name, spec))
    if kind in _AUTHZ_CACHE_KINDS:
        _clear_authz_cache()


async def _sync_llm_to_litellm(kind: str, name: str, spec: dict[str, Any] | None) -> None:
    """Push LLMConnection changes to LiteLLM proxy (errors logged, not raised)."""
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


_VERSION_LIST_LIMIT = 500


async def _save_version_snapshot(
    session: AsyncSession,
    resource: Any,
    user: User | None,
) -> None:
    """Persist a version snapshot for the given resource."""
    snapshot = ResourceVersion(
        resource_id=resource.id,
        version=resource.version,
        spec=resource.spec,
        labels=resource.labels,
        changed_by=str(user.id) if user else None,
    )
    session.add(snapshot)
    await session.flush()


class _VersionSummary(BaseModel):
    """Summary of a single version snapshot (without full spec)."""

    version: int
    changed_by: str | None
    created_at: datetime
    changed_keys: list[str]


class _VersionListResponse(BaseModel):
    """List of version summaries for a resource."""

    versions: list[_VersionSummary]


class _VersionDetailResponse(BaseModel):
    """Full snapshot of a resource at a specific version."""

    version: int
    changed_by: str | None
    created_at: datetime
    spec: dict[str, Any]
    labels: dict[str, Any] | None


class _RollbackRequest(BaseModel):
    """Request body for rolling back a resource."""

    version: int = Field(..., ge=1)


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
    spec = resource.spec
    if resource.kind.value == "Automation" and spec:
        spec = dict(spec)
        trigger = spec.get("trigger")
        if isinstance(trigger, dict) and "webhook_secret" in trigger:
            trigger = {**trigger, "webhook_secret": "**REDACTED**"}  # nosec B105
            spec["trigger"] = trigger
    metadata: dict[str, Any] = {
        "name": resource.name,
        "project": resource.project,
    }
    if resource.labels:
        metadata["labels"] = resource.labels
    return {
        "apiVersion": API_VERSION,
        "kind": resource.kind.value,
        "metadata": metadata,
        "spec": spec,
    }


_EXPORT_PAGE_SIZE = 200


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
    project: str | None = Query(
        default=None,
        pattern=NAME_PATTERN,
        max_length=255,
        description="Filter by project (omit for all projects)",
    ),
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(get_current_user),
) -> StreamingResponse:
    """Export all resources as a multi-document YAML stream.

    Streams resources in pages to avoid loading all into memory at once.
    Returns resources separated by ``---`` document markers, suitable for
    piping into ``blackbeard apply -f -`` or storing as a backup file.
    """
    service = ResourceService(session)

    async def _generate_yaml() -> AsyncGenerator[str]:
        offset = 0
        while True:
            items, _total = await service.list_resources(
                project=project,
                limit=_EXPORT_PAGE_SIZE,
                offset=offset,
                skip_total=True,
            )
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
            if len(items) < _EXPORT_PAGE_SIZE:
                break
            offset += _EXPORT_PAGE_SIZE

    return StreamingResponse(
        _generate_yaml(),
        media_type="application/x-yaml",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": 'attachment; filename="blackbeard-resources.yaml"',
        },
    )


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
    project: str | None = Query(
        default=None,
        pattern=NAME_PATTERN,
        max_length=255,
        description="Filter by project (omit for all projects)",
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
        project=project,
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
        429: {"description": "Too many mutation requests"},
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
    check_rate_limit(mutation_limiter, user, _MUTATION_RATE_MSG)
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
        await _save_version_snapshot(session, resource, user)
        await session.commit()
    except ResourceValidationError as exc:
        logger.warning(
            "Resource validation failed: %s/%s project=%s",
            data.kind,
            data.metadata.name,
            data.metadata.project,
            extra={
                "event": "resource_api_validation_failed",
                "resource_kind": data.kind,
                "resource_name": data.metadata.name,
                "project": data.metadata.project,
                "error_count": len(exc.errors),
            },
        )
        raise HTTPException(
            status_code=422,
            detail=[e.to_dict() for e in exc.errors],
        ) from exc
    if created:
        ns = data.metadata.project
        response.headers["Location"] = f"/api/v1/{kind_plural}/{data.metadata.name}?project={ns}"
    else:
        response.status_code = 200
    _post_mutation_hooks(request, url_kind, data.metadata.name, data.spec)
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
    project: str = Query(
        default="default",
        pattern=NAME_PATTERN,
        max_length=255,
        description="Resource project",
    ),
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(check_resource_permission),
) -> ResourceResponse:
    """Get a single resource by kind and name."""
    kind = _resolve_kind(kind_plural)
    service = ResourceService(session)
    try:
        resource = await service.get(kind, name, project)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ResourceResponse.from_db(resource)


@router.put(
    "/{kind_plural}/{name}",
    response_model=ResourceResponse,
    responses={
        404: {"description": "Resource not found"},
        409: {"description": "Version conflict (optimistic locking)"},
        422: {"description": "Validation error or name/project mismatch"},
        429: {"description": "Too many mutation requests"},
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
    project: str = Query(
        default="default",
        pattern=NAME_PATTERN,
        max_length=255,
        description="Resource project",
    ),
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(check_resource_permission),
) -> ResourceResponse:
    """Update a resource by kind and name (optimistic locking via version)."""
    check_rate_limit(mutation_limiter, user, _MUTATION_RATE_MSG)
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
        if data.metadata.project != project:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Cannot move resource to different project: "
                    f"URL project is '{project}' but body has '{data.metadata.project}'"
                ),
            )

    service = ResourceService(session)
    try:
        resource = await service.update(kind, name, data, project=project)
        await log_audit(
            session,
            action="resource_updated",
            resource_type=kind,
            resource_id=name,
            **audit_from_request(request, user),
        )
        await _save_version_snapshot(session, resource, user)
        await session.commit()
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ResourceConflictError as exc:
        logger.warning(
            "Version conflict: %s/%s project=%s",
            kind,
            name,
            project,
            extra={
                "event": "resource_version_conflict",
                "resource_kind": kind,
                "resource_name": name,
                "project": project,
            },
        )
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ResourceValidationError as exc:
        logger.warning(
            "Resource update validation failed: %s/%s project=%s",
            kind,
            name,
            project,
            extra={
                "event": "resource_update_validation_failed",
                "resource_kind": kind,
                "resource_name": name,
                "project": project,
                "error_count": len(exc.errors),
            },
        )
        raise HTTPException(
            status_code=422,
            detail=[e.to_dict() for e in exc.errors],
        ) from exc
    _post_mutation_hooks(request, kind, name, resource.spec)
    return ResourceResponse.from_db(resource)


@router.delete(
    "/{kind_plural}/{name}",
    status_code=204,
    responses={
        204: {"description": "Resource deleted (or did not exist — idempotent)"},
        429: {"description": "Too many mutation requests"},
    },
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
    project: str = Query(
        default="default",
        pattern=NAME_PATTERN,
        max_length=255,
        description="Resource project",
    ),
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(check_resource_permission),
) -> None:
    """Delete a resource by kind and name. Idempotent."""
    check_rate_limit(mutation_limiter, user, _MUTATION_RATE_MSG)
    kind = _resolve_kind(kind_plural)
    service = ResourceService(session)
    try:
        await service.delete(kind, name, project)
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
            "Delete no-op: %s/%s not found in project=%s",
            kind,
            name,
            project,
            extra={
                "event": "resource_delete_noop",
                "resource_kind": kind,
                "resource_name": name,
                "project": project,
            },
        )
    else:
        _post_mutation_hooks(request, kind, name)


# ---------------------------------------------------------------------------
# Version history endpoints
# ---------------------------------------------------------------------------


def _compute_changed_keys(
    current_spec: dict[str, Any],
    previous_spec: dict[str, Any] | None,
) -> list[str]:
    """Return the list of top-level spec keys that differ from the previous version."""
    if previous_spec is None:
        return sorted(current_spec.keys())
    all_keys = current_spec.keys() | previous_spec.keys()
    return sorted(k for k in all_keys if current_spec.get(k) != previous_spec.get(k))


@router.get(
    "/{kind_plural}/{name}/versions",
    response_model=_VersionListResponse,
    responses={404: {"description": "Resource not found"}},
)
async def list_resource_versions(
    kind_plural: str = Path(..., pattern=_KIND_PATTERN),
    name: str = Path(
        ...,
        pattern=NAME_PATTERN,
        max_length=255,
        description="Resource name",
    ),
    project: str = Query(
        default="default",
        pattern=NAME_PATTERN,
        max_length=255,
        description="Resource project",
    ),
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(check_resource_permission),
) -> _VersionListResponse:
    """List all version snapshots for a resource."""
    kind = _resolve_kind(kind_plural)
    service = ResourceService(session)
    try:
        resource = await service.get(kind, name, project)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    result = await session.execute(
        select(ResourceVersion)
        .where(ResourceVersion.resource_id == resource.id)
        .options(
            load_only(
                ResourceVersion.version,
                ResourceVersion.spec,
                ResourceVersion.changed_by,
                ResourceVersion.created_at,
            )
        )
        .order_by(ResourceVersion.version.asc())
        .limit(_VERSION_LIST_LIMIT)
    )
    snapshots = list(result.scalars().all())

    summaries: list[_VersionSummary] = []
    for i, snap in enumerate(snapshots):
        prev_spec = snapshots[i - 1].spec if i > 0 else None
        summaries.append(
            _VersionSummary(
                version=snap.version,
                changed_by=snap.changed_by,
                created_at=snap.created_at,
                changed_keys=_compute_changed_keys(snap.spec, prev_spec),
            )
        )

    return _VersionListResponse(versions=summaries)


@router.get(
    "/{kind_plural}/{name}/versions/{version}",
    response_model=_VersionDetailResponse,
    responses={404: {"description": "Resource or version not found"}},
)
async def get_resource_version(
    kind_plural: str = Path(..., pattern=_KIND_PATTERN),
    name: str = Path(
        ...,
        pattern=NAME_PATTERN,
        max_length=255,
        description="Resource name",
    ),
    version: int = Path(..., ge=1, description="Version number"),
    project: str = Query(
        default="default",
        pattern=NAME_PATTERN,
        max_length=255,
        description="Resource project",
    ),
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(check_resource_permission),
) -> _VersionDetailResponse:
    """Get the full snapshot of a resource at a specific version."""
    kind = _resolve_kind(kind_plural)
    service = ResourceService(session)
    try:
        resource = await service.get(kind, name, project)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    result = await session.execute(
        select(ResourceVersion).where(
            ResourceVersion.resource_id == resource.id,
            ResourceVersion.version == version,
        )
    )
    snapshot = result.scalar_one_or_none()
    if snapshot is None:
        raise HTTPException(
            status_code=404,
            detail=f"Version {version} not found for {kind}/{name}",
        )

    return _VersionDetailResponse(
        version=snapshot.version,
        changed_by=snapshot.changed_by,
        created_at=snapshot.created_at,
        spec=snapshot.spec,
        labels=snapshot.labels,
    )


@router.post(
    "/{kind_plural}/{name}/rollback",
    response_model=ResourceResponse,
    responses={
        404: {"description": "Resource or version not found"},
        422: {"description": "Validation error"},
        429: {"description": "Too many mutation requests"},
    },
)
async def rollback_resource(
    body: _RollbackRequest,
    request: Request,
    kind_plural: str = Path(..., pattern=_KIND_PATTERN),
    name: str = Path(
        ...,
        pattern=NAME_PATTERN,
        max_length=255,
        description="Resource name",
    ),
    project: str = Query(
        default="default",
        pattern=NAME_PATTERN,
        max_length=255,
        description="Resource project",
    ),
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(check_resource_permission),
) -> ResourceResponse:
    """Rollback a resource to a previous version snapshot."""
    check_rate_limit(mutation_limiter, user, _MUTATION_RATE_MSG)
    kind = _resolve_kind(kind_plural)
    service = ResourceService(session)
    try:
        resource = await service.get(kind, name, project, for_update=True)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    # Find the target version snapshot
    result = await session.execute(
        select(ResourceVersion).where(
            ResourceVersion.resource_id == resource.id,
            ResourceVersion.version == body.version,
        )
    )
    snapshot = result.scalar_one_or_none()
    if snapshot is None:
        raise HTTPException(
            status_code=404,
            detail=f"Version {body.version} not found for {kind}/{name}",
        )

    # Restore spec and labels from the snapshot, bump version
    resource.spec = snapshot.spec
    resource.labels = snapshot.labels or {}
    resource.version += 1

    await log_audit(
        session,
        action="resource_rollback",
        resource_type=kind,
        resource_id=name,
        detail={"rollback_to_version": body.version, "new_version": resource.version},
        **audit_from_request(request, user),
    )
    await _save_version_snapshot(session, resource, user)
    await session.commit()

    _post_mutation_hooks(request, kind, name, resource.spec)
    return ResourceResponse.from_db(resource)
