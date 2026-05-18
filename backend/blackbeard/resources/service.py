"""Generic resource CRUD service."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import defer, load_only

from blackbeard.kinds import ResourceKind
from blackbeard.logging_config import request_id_var
from blackbeard.models import Resource, ResourceRef
from blackbeard.resources.exceptions import (
    ResourceConflictError,
    ResourceNotFoundError,
    ResourceValidationError,
)
from blackbeard.resources.refs import RefInfo, RefParseError, extract_refs
from blackbeard.resources.validator import validate_resource

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from blackbeard.models.resource_schemas import ResourceCreate, ResourceUpdate

__all__ = [
    "ResourceService",
]


_KIND_LOOKUP: dict[str, ResourceKind] = {
    alias: k for k in ResourceKind for alias in (k.value, k.value.lower())
}


def _parse_kind(kind_str: str) -> ResourceKind:
    """Convert kind string to enum, handling both 'Agent' and 'agent' forms."""
    result = _KIND_LOOKUP.get(kind_str)
    if result is None:
        raise ValueError(f"Unknown resource kind: {kind_str}")
    return result


logger = logging.getLogger(__name__)


class ResourceService:
    """CRUD operations for resources."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        data: ResourceCreate,
        raw_yaml: str | None = None,
    ) -> tuple[Resource, bool]:
        """Create or upsert a resource.

        If a resource with the same kind/name/namespace exists, it is updated
        (version incremented). Returns (resource, created) where created=True
        for new resources and created=False for upserted existing resources.
        """
        t0 = time.monotonic()
        kind_enum = _parse_kind(data.kind)

        errors, validated_refs = await asyncio.to_thread(validate_resource, data.kind, data.spec)
        if errors:
            raise ResourceValidationError(errors)

        result = await self.session.execute(
            select(Resource)
            .where(
                Resource.kind == kind_enum,
                Resource.name == data.metadata.name,
                Resource.namespace == data.metadata.namespace,
            )
            .with_for_update()
        )
        existing = result.scalar_one_or_none()
        if existing:
            resource = await self._update_existing(existing, data, raw_yaml, validated_refs)
            duration_ms = round((time.monotonic() - t0) * 1000, 1)
            logger.info(
                "Resource upsert (create path): %s/%s namespace=%s version=%d (%.0fms)",
                kind_enum.value,
                data.metadata.name,
                data.metadata.namespace,
                resource.version,
                duration_ms,
                extra={
                    "event": "resource_upsert_via_create",
                    "resource_kind": kind_enum.value,
                    "resource_name": data.metadata.name,
                    "namespace": data.metadata.namespace,
                    "version": resource.version,
                    "duration_ms": duration_ms,
                    "request_id": request_id_var.get("-"),
                },
            )
            return resource, False

        resource = Resource(
            kind=kind_enum,
            name=data.metadata.name,
            namespace=data.metadata.namespace,
            labels=data.metadata.labels,
            spec=data.spec,
            raw_yaml=raw_yaml,
            version=1,
        )
        try:
            async with self.session.begin_nested():
                self.session.add(resource)
                await self.session.flush()
        except IntegrityError:
            logger.info(
                "Create race: %s/%s namespace=%s — retrying as upsert",
                kind_enum.value,
                data.metadata.name,
                data.metadata.namespace,
                extra={
                    "event": "resource_create_race",
                    "resource_kind": kind_enum.value,
                    "resource_name": data.metadata.name,
                    "namespace": data.metadata.namespace,
                    "request_id": request_id_var.get("-"),
                },
            )
            result = await self.session.execute(
                select(Resource)
                .where(
                    Resource.kind == kind_enum,
                    Resource.name == data.metadata.name,
                    Resource.namespace == data.metadata.namespace,
                )
                .with_for_update()
            )
            existing = result.scalar_one_or_none()
            if existing:
                resource = await self._update_existing(existing, data, raw_yaml, validated_refs)
                return resource, False
            raise
        await self._sync_refs(resource, validated_refs)

        duration_ms = round((time.monotonic() - t0) * 1000, 1)
        logger.info(
            "Resource created: %s/%s namespace=%s (%.0fms)",
            kind_enum.value,
            data.metadata.name,
            data.metadata.namespace,
            duration_ms,
            extra={
                "event": "resource_created",
                "resource_kind": kind_enum.value,
                "resource_name": data.metadata.name,
                "namespace": data.metadata.namespace,
                "duration_ms": duration_ms,
                "request_id": request_id_var.get("-"),
            },
        )
        return resource, True

    async def get(self, kind: str, name: str, namespace: str = "default") -> Resource:
        """Get a single resource by kind/name/namespace."""
        kind_enum = _parse_kind(kind)
        resource = await self._get_by_identity(kind_enum, name, namespace)
        if not resource:
            raise ResourceNotFoundError(kind, name, namespace)
        return resource

    async def list_resources(
        self,
        kind: str | None = None,
        namespace: str | None = None,
        labels: dict[str, str] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Resource], int]:
        """List resources with optional filters. Returns (items, total_count)."""
        filters = []
        if kind:
            filters.append(Resource.kind == _parse_kind(kind))
        if namespace:
            filters.append(Resource.namespace == namespace)
        if labels:
            filters.append(Resource.labels.contains(labels))

        query = (
            select(Resource)
            .options(
                load_only(
                    Resource.id,
                    Resource.kind,
                    Resource.name,
                    Resource.namespace,
                    Resource.labels,
                    Resource.spec,
                    Resource.version,
                    Resource.created_at,
                    Resource.updated_at,
                )
            )
            .where(*filters)
            .order_by(Resource.kind, Resource.namespace, Resource.name)
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(query)
        items = list(result.scalars().all())

        if len(items) < limit and (len(items) > 0 or offset == 0):
            total = offset + len(items)
        else:
            count_query = select(func.count(Resource.id)).where(*filters)
            total = (await self.session.execute(count_query)).scalar() or 0

        return items, total

    async def update(
        self,
        kind: str,
        name: str,
        data: ResourceUpdate,
        namespace: str = "default",
        raw_yaml: str | None = None,
    ) -> Resource:
        """Update a resource with optimistic locking."""
        t0 = time.monotonic()
        kind_enum = _parse_kind(kind)

        result = await self.session.execute(
            select(Resource)
            .where(
                Resource.kind == kind_enum,
                Resource.name == name,
                Resource.namespace == namespace,
            )
            .with_for_update()
        )
        resource = result.scalar_one_or_none()
        if not resource:
            raise ResourceNotFoundError(kind, name, namespace)

        if resource.version != data.version:
            raise ResourceConflictError(kind, name, data.version, resource.version)

        validated_refs = None
        has_changes = False
        if data.spec is not None:
            errors, validated_refs = await asyncio.to_thread(validate_resource, kind, data.spec)
            if errors:
                raise ResourceValidationError(errors)
            resource.spec = data.spec
            has_changes = True

        if data.metadata is not None:
            resource.labels = data.metadata.labels
            # name and namespace are immutable after creation
            has_changes = True

        if raw_yaml is not None:
            resource.raw_yaml = raw_yaml
            has_changes = True

        if has_changes:
            resource.version += 1
        await self.session.flush()

        if data.spec is not None:
            await self._sync_refs(resource, validated_refs)

        duration_ms = round((time.monotonic() - t0) * 1000, 1)
        logger.info(
            "Resource updated: %s/%s namespace=%s version=%d (%.0fms)",
            kind,
            name,
            namespace,
            resource.version,
            duration_ms,
            extra={
                "event": "resource_updated",
                "resource_kind": kind,
                "resource_name": name,
                "namespace": namespace,
                "version": resource.version,
                "duration_ms": duration_ms,
                "request_id": request_id_var.get("-"),
            },
        )
        return resource

    async def delete(self, kind: str, name: str, namespace: str = "default") -> None:
        """Delete a resource. Raises ResourceNotFoundError if not found."""
        t0 = time.monotonic()
        kind_enum = _parse_kind(kind)
        await self.session.execute(
            delete(ResourceRef).where(
                ResourceRef.source_id.in_(
                    select(Resource.id).where(
                        Resource.kind == kind_enum,
                        Resource.name == name,
                        Resource.namespace == namespace,
                    )
                )
            )
        )
        result = await self.session.execute(
            delete(Resource)
            .where(
                Resource.kind == kind_enum,
                Resource.name == name,
                Resource.namespace == namespace,
            )
            .returning(Resource.id)
        )
        if result.scalar_one_or_none() is None:
            raise ResourceNotFoundError(kind, name, namespace)
        duration_ms = round((time.monotonic() - t0) * 1000, 1)
        logger.info(
            "Resource deleted: %s/%s namespace=%s (%.0fms)",
            kind,
            name,
            namespace,
            duration_ms,
            extra={
                "event": "resource_deleted",
                "resource_kind": kind,
                "resource_name": name,
                "namespace": namespace,
                "duration_ms": duration_ms,
                "request_id": request_id_var.get("-"),
            },
        )

    async def _get_by_identity(
        self, kind: ResourceKind, name: str, namespace: str
    ) -> Resource | None:
        """Look up a resource by its unique identity."""
        result = await self.session.execute(
            select(Resource)
            .where(
                Resource.kind == kind,
                Resource.name == name,
                Resource.namespace == namespace,
            )
            .options(defer(Resource.raw_yaml))
        )
        return result.scalar_one_or_none()

    async def _update_existing(
        self,
        resource: Resource,
        data: ResourceCreate,
        raw_yaml: str | None,
        refs: list[RefInfo] | None = None,
    ) -> Resource:
        """Update an existing resource (used by create for upsert behavior)."""
        resource.labels = data.metadata.labels
        resource.spec = data.spec
        if raw_yaml is not None:
            resource.raw_yaml = raw_yaml
        resource.version += 1
        await self.session.flush()
        await self._sync_refs(resource, refs)
        logger.info(
            "Resource upserted: %s/%s namespace=%s version=%d",
            resource.kind.value,
            resource.name,
            resource.namespace,
            resource.version,
            extra={
                "event": "resource_upserted",
                "resource_kind": resource.kind.value,
                "resource_name": resource.name,
                "namespace": resource.namespace,
                "version": resource.version,
                "request_id": request_id_var.get("-"),
            },
        )
        return resource

    async def _sync_refs(self, resource: Resource, refs: list[RefInfo] | None = None) -> None:
        """Delete old refs and create new ones from the current spec."""
        if refs is None:
            try:
                refs = extract_refs(resource.spec)
            except RefParseError as e:
                logger.warning(
                    "Skipping ref sync for %s/%s: %s",
                    resource.kind.value,
                    resource.name,
                    e,
                    extra={
                        "event": "ref_sync_skipped",
                        "resource_kind": resource.kind.value,
                        "resource_name": resource.name,
                        "namespace": resource.namespace,
                        "error_message": str(e)[:500],
                        "request_id": request_id_var.get("-"),
                    },
                )
                return

        await self.session.execute(delete(ResourceRef).where(ResourceRef.source_id == resource.id))

        if refs:
            self.session.add_all(
                [
                    ResourceRef(
                        source_id=resource.id,
                        target_kind=ref.kind,
                        target_name=ref.name,
                        target_namespace=resource.namespace,
                        ref_field=ref.field,
                    )
                    for ref in refs
                ]
            )
            await self.session.flush()
