"""Pydantic schemas for API request/response models."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ResourceMetadata(BaseModel):
    """Resource metadata block (mirrors YAML metadata section)."""

    name: str = Field(..., min_length=1, max_length=255, pattern=r"^[a-z0-9][a-z0-9\-]*$")
    namespace: str = Field(default="default", max_length=255)
    labels: dict[str, str] = Field(default_factory=dict)


class ResourceCreate(BaseModel):
    """Schema for creating a resource via API or YAML apply."""

    apiVersion: str = Field(default="blackbeard/v1")
    kind: str
    metadata: ResourceMetadata
    spec: dict


class ResourceUpdate(BaseModel):
    """Schema for updating a resource (partial or full)."""

    metadata: ResourceMetadata | None = None
    spec: dict | None = None
    version: int = Field(..., description="Current version for optimistic locking")


class ResourceResponse(BaseModel):
    """Schema for resource API responses."""

    id: UUID
    apiVersion: str = "blackbeard/v1"
    kind: str
    metadata: ResourceMetadata
    spec: dict
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_db(cls, resource) -> "ResourceResponse":  # type: ignore[no-untyped-def]
        """Build response from a SQLAlchemy Resource model."""
        return cls(
            id=resource.id,
            kind=resource.kind.value,
            metadata=ResourceMetadata(
                name=resource.name,
                namespace=resource.namespace,
                labels=resource.labels or {},
            ),
            spec=resource.spec,
            version=resource.version,
            created_at=resource.created_at,
            updated_at=resource.updated_at,
        )


class ResourceListResponse(BaseModel):
    """Paginated list of resources."""

    items: list[ResourceResponse]
    total: int
    limit: int = 100
    offset: int = 0
    has_more: bool = False



