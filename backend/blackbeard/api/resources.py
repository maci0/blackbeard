"""REST API endpoints for generic resource CRUD operations."""

from fastapi import APIRouter, Depends, HTTPException, Query, Path, Response
from sqlalchemy.ext.asyncio import AsyncSession

from blackbeard.models.database import get_session
from blackbeard.models.resource_schemas import (
    ResourceCreate,
    ResourceUpdate,
    ResourceResponse,
    ResourceListResponse,
)
from blackbeard.resources.service import (
    ResourceService,
    ResourceNotFoundError,
    ResourceValidationError,
    ResourceConflictError,
)
from blackbeard.kinds import PLURAL_TO_KIND

router = APIRouter(tags=["resources"])

# Regex pattern matching valid kind plurals for path parameter constraint
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


@router.get("/{kind_plural}", response_model=ResourceListResponse)
async def list_resources(
    kind_plural: str = Path(..., pattern=_KIND_PATTERN),
    namespace: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> ResourceListResponse:
    """List resources of a given kind."""
    kind = _resolve_kind(kind_plural)
    service = ResourceService(session)
    items, total = await service.list(kind=kind, namespace=namespace, limit=limit, offset=offset)
    return ResourceListResponse(
        items=[ResourceResponse.from_db(r) for r in items],
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + limit) < total,
    )


@router.post("/{kind_plural}", response_model=ResourceResponse, status_code=201)
async def create_resource(
    data: ResourceCreate,
    kind_plural: str = Path(..., pattern=_KIND_PATTERN),
    response: Response = ...,
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
        raise HTTPException(
            status_code=422,
            detail={
                "message": str(exc),
                "errors": [{"field": e.field, "message": e.message} for e in exc.errors],
            },
        ) from exc
    if not created:
        response.status_code = 200
    return ResourceResponse.from_db(resource)


_NAME_PATTERN = r"^[a-z0-9][a-z0-9\-]*$"


@router.get("/{kind_plural}/{name}", response_model=ResourceResponse)
async def get_resource(
    kind_plural: str = Path(..., pattern=_KIND_PATTERN),
    name: str = Path(..., pattern=_NAME_PATTERN, max_length=255),
    namespace: str = Query(default="default"),
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


@router.put("/{kind_plural}/{name}", response_model=ResourceResponse)
async def update_resource(
    data: ResourceUpdate,
    kind_plural: str = Path(..., pattern=_KIND_PATTERN),
    name: str = Path(..., pattern=_NAME_PATTERN, max_length=255),
    namespace: str = Query(default="default"),
    session: AsyncSession = Depends(get_session),
) -> ResourceResponse:
    """Update a resource by kind and name (optimistic locking via version)."""
    kind = _resolve_kind(kind_plural)
    service = ResourceService(session)
    try:
        resource = await service.update(kind, name, data, namespace=namespace)
        await session.commit()
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ResourceConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ResourceValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "message": str(exc),
                "errors": [{"field": e.field, "message": e.message} for e in exc.errors],
            },
        ) from exc
    return ResourceResponse.from_db(resource)


@router.delete("/{kind_plural}/{name}", status_code=204)
async def delete_resource(
    kind_plural: str = Path(..., pattern=_KIND_PATTERN),
    name: str = Path(..., pattern=_NAME_PATTERN, max_length=255),
    namespace: str = Query(default="default"),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete a resource by kind and name."""
    kind = _resolve_kind(kind_plural)
    service = ResourceService(session)
    try:
        await service.delete(kind, name, namespace)
        await session.commit()
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
