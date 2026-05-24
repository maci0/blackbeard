"""Pydantic schemas for API request/response models."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

if TYPE_CHECKING:
    from blackbeard.models.resource import Resource

from blackbeard.kinds import ALL_KINDS, API_VERSION, NAME_PATTERN

__all__ = [
    "ResourceCreate",
    "ResourceListResponse",
    "ResourceMetadata",
    "ResourceResponse",
    "ResourceUpdate",
]

# Label key/value constraints (prevent abuse via oversized JSONB labels)
_MAX_LABEL_KEY_LEN = 63
_MAX_LABEL_VALUE_LEN = 255


class ResourceMetadata(BaseModel):
    """Resource metadata block (mirrors YAML metadata section)."""

    name: str = Field(..., min_length=1, max_length=255, pattern=NAME_PATTERN)
    namespace: str = Field(default="default", max_length=255, pattern=NAME_PATTERN)
    labels: dict[str, str] = Field(default_factory=dict, max_length=50)

    @model_validator(mode="after")
    def _validate_label_sizes(self) -> ResourceMetadata:
        for k, v in self.labels.items():
            if len(k) > _MAX_LABEL_KEY_LEN:
                raise ValueError(
                    f"Label key too long ({len(k)} chars, max {_MAX_LABEL_KEY_LEN}): '{k[:20]}...'"
                )
            if len(v) > _MAX_LABEL_VALUE_LEN:
                raise ValueError(
                    f"Label value too long for key '{k}' "
                    f"({len(v)} chars, max {_MAX_LABEL_VALUE_LEN})"
                )
        return self


_SUPPORTED_API_VERSIONS = frozenset({API_VERSION})


class ResourceCreate(BaseModel):
    """Schema for creating a resource via API or YAML apply."""

    apiVersion: str = Field(default=API_VERSION)
    kind: str = Field(..., min_length=1)
    metadata: ResourceMetadata
    spec: dict[str, Any] = Field(..., min_length=1, max_length=500)

    @field_validator("apiVersion")
    @classmethod
    def api_version_must_be_supported(cls, v: str) -> str:
        if v not in _SUPPORTED_API_VERSIONS:
            raise ValueError(
                f"Unsupported apiVersion '{v}'. "
                f"Supported: {', '.join(sorted(_SUPPORTED_API_VERSIONS))}"
            )
        return v

    @field_validator("kind")
    @classmethod
    def kind_must_be_valid(cls, v: str) -> str:
        if v not in ALL_KINDS:
            raise ValueError(f"Invalid kind '{v}'. Valid kinds: {', '.join(sorted(ALL_KINDS))}")
        return v


class ResourceUpdate(BaseModel):
    """Schema for updating a resource (partial or full)."""

    metadata: ResourceMetadata | None = None
    spec: dict[str, Any] | None = Field(default=None, min_length=1, max_length=500)
    version: int = Field(..., ge=1, description="Current version for optimistic locking")


class ResourceResponse(BaseModel):
    """Schema for resource API responses."""

    id: UUID
    apiVersion: str = API_VERSION
    kind: str
    metadata: ResourceMetadata
    spec: dict[str, Any]
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_db(cls, resource: Resource) -> ResourceResponse:
        """Build response from a SQLAlchemy Resource model."""
        spec = resource.spec
        if resource.kind.value == "Automation" and spec:
            spec = dict(spec)
            trigger = spec.get("trigger")
            if isinstance(trigger, dict) and "webhook_secret" in trigger:
                trigger = {**trigger, "webhook_secret": "**REDACTED**"}  # nosec B105 -- redaction-placeholder
                spec["trigger"] = trigger
        return cls.model_construct(
            id=resource.id,
            apiVersion=API_VERSION,
            kind=resource.kind.value,
            metadata=ResourceMetadata.model_construct(
                name=resource.name,
                namespace=resource.namespace,
                labels=resource.labels or {},
            ),
            spec=spec,
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
