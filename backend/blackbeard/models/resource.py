"""SQLAlchemy models for the resource system."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from blackbeard.models.database import Base
from blackbeard.kinds import ResourceKind


class Resource(Base):
    """Generic resource table — stores all resource kinds."""

    __tablename__ = "resources"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind = Column(Enum(ResourceKind), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    namespace = Column(String(255), nullable=False, default="default")
    labels = Column(JSONB, nullable=False, default=dict)
    spec = Column(JSONB, nullable=False)
    raw_yaml = Column(Text, nullable=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    outgoing_refs = relationship(
        "ResourceRef",
        foreign_keys="ResourceRef.source_id",
        back_populates="source",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("kind", "name", "namespace", name="uq_resource_kind_name_ns"),
        Index("ix_resource_ns_kind", "namespace", "kind"),
    )

    def __repr__(self) -> str:
        return f"<Resource {self.kind.value}/{self.name} ns={self.namespace} v{self.version}>"


class ResourceRef(Base):
    """Tracks cross-references between resources (e.g. ref:agents/researcher)."""

    __tablename__ = "resource_refs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id = Column(UUID(as_uuid=True), ForeignKey("resources.id", ondelete="CASCADE"), nullable=False)
    target_kind = Column(Enum(ResourceKind), nullable=False)
    target_name = Column(String(255), nullable=False)
    target_namespace = Column(String(255), nullable=False, default="default")
    ref_field = Column(String(255), nullable=False)  # e.g. "spec.llm", "spec.tools[0]"

    source = relationship("Resource", foreign_keys=[source_id], back_populates="outgoing_refs")

    __table_args__ = (
        Index("ix_ref_source", "source_id"),
        Index("ix_ref_target", "target_kind", "target_name", "target_namespace"),
    )

    def __repr__(self) -> str:
        return f"<ResourceRef {self.source_id} -> {self.target_kind.value}/{self.target_name}>"
