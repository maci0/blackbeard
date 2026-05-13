"""Pydantic schemas for API request/response models."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from blackbeard.kinds import ALL_KINDS, NAME_PATTERN


class ResourceMetadata(BaseModel):
    """Resource metadata block (mirrors YAML metadata section)."""

    name: str = Field(..., min_length=1, max_length=255, pattern=NAME_PATTERN)
    namespace: str = Field(default="default", max_length=255, pattern=NAME_PATTERN)
    labels: dict[str, str] = Field(default_factory=dict, max_length=50)


class ResourceCreate(BaseModel):
    """Schema for creating a resource via API or YAML apply."""

    apiVersion: str = Field(default="blackbeard/v1")
    kind: str = Field(..., min_length=1)
    metadata: ResourceMetadata
    spec: dict = Field(..., min_length=1, max_length=500)

    @field_validator("kind")
    @classmethod
    def kind_must_be_valid(cls, v: str) -> str:
        if v not in ALL_KINDS:
            raise ValueError(f"Invalid kind '{v}'. Valid kinds: {', '.join(ALL_KINDS)}")
        return v


class ResourceUpdate(BaseModel):
    """Schema for updating a resource (partial or full)."""

    metadata: ResourceMetadata | None = None
    spec: dict | None = None
    version: int = Field(..., ge=1, description="Current version for optimistic locking")


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
        return cls.model_construct(
            id=resource.id,
            apiVersion="blackbeard/v1",
            kind=resource.kind.value,
            metadata=ResourceMetadata.model_construct(
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

