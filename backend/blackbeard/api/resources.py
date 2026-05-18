"""REST API endpoints for generic resource CRUD operations."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from blackbeard.kinds import NAME_PATTERN, PLURAL_TO_KIND
from blackbeard.models import get_session
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

router = APIRouter(tags=["resources"])

_KIND_PATTERN = "^(" + "|".join(PLURAL_TO_KIND.keys()) + ")$"


def _resolve_kind(kind_plural: str) -> str:
    """Validate kind_plural and return the ResourceKind value string."""
    kind = PLURAL_TO_KIND.get(kind_plural)
    if kind is None:
        valid = ", ".join(PLURAL_TO_KIND.keys())
        raise HTTPException(
            status_code=404,
            detail=f"Unknown resource kind '{kind_plural}'. Valid kinds: {valid}",
        )
    return kind


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
    response: Response,
    kind_plural: str = Path(..., pattern=_KIND_PATTERN),
    session: AsyncSession = Depends(get_session),
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
    return ResourceResponse.from_db(resource)


@router.delete(
    "/{kind_plural}/{name}",
    status_code=204,
    responses={204: {"description": "Resource deleted (or did not exist — idempotent)"}},
)
async def delete_resource(
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
) -> None:
    """Delete a resource by kind and name. Idempotent."""
    kind = _resolve_kind(kind_plural)
    service = ResourceService(session)
    try:
        await service.delete(kind, name, namespace)
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
