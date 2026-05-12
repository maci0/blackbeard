"""Generic resource CRUD service."""

from uuid import UUID

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from blackbeard.kinds import ResourceKind
from blackbeard.models.resource import Resource, ResourceRef
from blackbeard.models.resource_schemas import ResourceCreate, ResourceUpdate
from blackbeard.resources.validator import validate_resource, ValidationError
from blackbeard.resources.refs import extract_refs, RefParseError


class ResourceNotFoundError(Exception):
    """Raised when a resource is not found."""

    def __init__(self, kind: str, name: str, namespace: str = "default"):
        self.kind = kind
        self.name = name
        self.namespace = namespace
        super().__init__(f"{kind}/{name} not found in namespace '{namespace}'")


class ResourceConflictError(Exception):
    """Raised on optimistic locking conflict."""

    def __init__(self, kind: str, name: str, expected: int, actual: int):
        super().__init__(
            f"Version conflict for {kind}/{name}: expected {expected}, actual {actual}"
        )


class ResourceValidationError(Exception):
    """Raised when resource validation fails."""

    def __init__(self, errors: list[ValidationError]):
        self.errors = errors
        messages = "; ".join(f"{e.field}: {e.message}" for e in errors)
        super().__init__(f"Validation failed: {messages}")


# Pre-built lookup for O(1) kind resolution
_KIND_LOOKUP: dict[str, ResourceKind] = {}
for _k in ResourceKind:
    _KIND_LOOKUP[_k.value] = _k
    _KIND_LOOKUP[_k.value.lower()] = _k


def _parse_kind(kind_str: str) -> ResourceKind:
    """Convert kind string to enum, handling both 'Agent' and 'agent' forms."""
    result = _KIND_LOOKUP.get(kind_str) or _KIND_LOOKUP.get(kind_str.lower())
    if result is None:
        raise ValueError(f"Unknown resource kind: {kind_str}")
    return result


class ResourceService:
    """CRUD operations for resources."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, data: ResourceCreate, raw_yaml: str | None = None) -> tuple[Resource, bool]:
        """Create or upsert a resource.

        If a resource with the same kind/name/namespace exists, it is updated
        (version incremented). Returns (resource, created) where created=True
        for new resources and created=False for upserted existing resources.
        """
        kind_enum = _parse_kind(data.kind)

        # Validate spec
        errors = validate_resource(data.kind, data.spec)
        if errors:
            raise ResourceValidationError(errors)

        # Lock the row if it exists to prevent lost updates on concurrent upsert
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
            # Update existing resource
            resource = await self._update_existing(existing, data, raw_yaml)
            return resource, False

        # Create new resource
        resource = Resource(
            kind=kind_enum,
            name=data.metadata.name,
            namespace=data.metadata.namespace,
            labels=data.metadata.labels,
            spec=data.spec,
            raw_yaml=raw_yaml,
            version=1,
        )
        self.session.add(resource)
        await self.session.flush()

        # Extract and store refs
        await self._sync_refs(resource)

        return resource, True

    async def get(self, kind: str, name: str, namespace: str = "default") -> Resource:
        """Get a single resource by kind/name/namespace."""
        kind_enum = _parse_kind(kind)
        resource = await self._get_by_identity(kind_enum, name, namespace)
        if not resource:
            raise ResourceNotFoundError(kind, name, namespace)
        return resource

    async def get_by_id(self, resource_id: UUID) -> Resource:
        """Get a resource by its UUID."""
        result = await self.session.execute(
            select(Resource).where(Resource.id == resource_id)
        )
        resource = result.scalar_one_or_none()
        if not resource:
            raise ResourceNotFoundError("unknown", str(resource_id))
        return resource

    async def list(
        self,
        kind: str | None = None,
        namespace: str | None = None,
        labels: dict[str, str] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Resource], int]:
        """List resources with optional filters. Returns (items, total_count)."""
        query = select(Resource)
        count_query = select(func.count(Resource.id))

        if kind:
            kind_enum = _parse_kind(kind)
            query = query.where(Resource.kind == kind_enum)
            count_query = count_query.where(Resource.kind == kind_enum)

        if namespace:
            query = query.where(Resource.namespace == namespace)
            count_query = count_query.where(Resource.namespace == namespace)

        if labels:
            for key, value in labels.items():
                query = query.where(Resource.labels[key].astext == value)
                count_query = count_query.where(Resource.labels[key].astext == value)

        # Get total count
        total = (await self.session.execute(count_query)).scalar() or 0

        # Get paginated results
        query = query.order_by(Resource.kind, Resource.name).limit(limit).offset(offset)
        result = await self.session.execute(query)
        items = list(result.scalars().all())

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
        kind_enum = _parse_kind(kind)

        # Lock the row for update to prevent lost updates
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

        # Optimistic locking check
        if resource.version != data.version:
            raise ResourceConflictError(kind, name, data.version, resource.version)

        # Validate new spec if provided
        if data.spec is not None:
            errors = validate_resource(kind, data.spec)
            if errors:
                raise ResourceValidationError(errors)
            resource.spec = data.spec

        if data.metadata is not None:
            resource.labels = data.metadata.labels
            # name and namespace are immutable after creation

        if raw_yaml is not None:
            resource.raw_yaml = raw_yaml

        resource.version += 1
        await self.session.flush()

        # Re-sync refs
        if data.spec is not None:
            await self._sync_refs(resource)

        return resource

    async def delete(self, kind: str, name: str, namespace: str = "default") -> None:
        """Delete a resource."""
        resource = await self.get(kind, name, namespace)
        await self.session.delete(resource)
        await self.session.flush()

    async def _get_by_identity(
        self, kind: ResourceKind, name: str, namespace: str
    ) -> Resource | None:
        """Look up a resource by its unique identity."""
        result = await self.session.execute(
            select(Resource).where(
                Resource.kind == kind,
                Resource.name == name,
                Resource.namespace == namespace,
            )
        )
        return result.scalar_one_or_none()

    async def _update_existing(
        self, resource: Resource, data: ResourceCreate, raw_yaml: str | None
    ) -> Resource:
        """Update an existing resource (used by create for upsert behavior)."""
        resource.labels = data.metadata.labels
        resource.spec = data.spec
        resource.raw_yaml = raw_yaml
        resource.version += 1
        await self.session.flush()
        await self._sync_refs(resource)
        return resource

    async def _sync_refs(self, resource: Resource) -> None:
        """Delete old refs and create new ones from the current spec."""
        # Delete existing refs
        await self.session.execute(
            delete(ResourceRef).where(ResourceRef.source_id == resource.id)
        )

        # Extract and create new refs
        try:
            refs = extract_refs(resource.spec)
        except RefParseError:
            return  # Ref format errors are caught during validation

        for ref in refs:
            ref_record = ResourceRef(
                source_id=resource.id,
                target_kind=ref.kind,
                target_name=ref.name,
                target_namespace=resource.namespace,
                ref_field=ref.field,
            )
            self.session.add(ref_record)

        await self.session.flush()
