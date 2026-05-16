"""SQLAlchemy models for the resource system."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from blackbeard.kinds import ResourceKind
from blackbeard.models.database import Base


class Resource(Base):
    """Generic resource table — stores all resource kinds."""

    __tablename__ = "resources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[ResourceKind] = mapped_column(
        Enum(ResourceKind, create_type=False, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    namespace: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="default",
        server_default=text("'default'"),
    )
    labels: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'")
    )
    spec: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    raw_yaml: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=text("now()"),
    )

    outgoing_refs: Mapped[list[ResourceRef]] = relationship(
        "ResourceRef",
        foreign_keys="ResourceRef.source_id",
        back_populates="source",
        cascade="all, delete-orphan",
        lazy="raise",
    )

    __table_args__ = (
        UniqueConstraint("kind", "name", "namespace", name="uq_resource_kind_name_ns"),
        Index("ix_resource_ns_kind", "namespace", "kind"),
        Index("ix_resource_kind_ns_name", "kind", "namespace", "name"),
        Index("ix_resource_labels", "labels", postgresql_using="gin"),
        CheckConstraint("version >= 1", name="ck_resource_version_positive"),
        CheckConstraint("length(name) >= 1", name="ck_resource_name_nonempty"),
        CheckConstraint("length(namespace) >= 1", name="ck_resource_namespace_nonempty"),
    )

    def __repr__(self) -> str:
        return f"<Resource {self.kind.value}/{self.name} ns={self.namespace} v{self.version}>"


class ResourceRef(Base):
    """Tracks cross-references between resources (e.g. ref:agents/researcher)."""

    __tablename__ = "resource_refs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resources.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_kind: Mapped[ResourceKind] = mapped_column(
        Enum(ResourceKind, create_type=False, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    target_name: Mapped[str] = mapped_column(String(255), nullable=False)
    target_namespace: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="default",
        server_default=text("'default'"),
    )
    ref_field: Mapped[str] = mapped_column(String(255), nullable=False)

    source: Mapped[Resource] = relationship(
        "Resource", foreign_keys=[source_id], back_populates="outgoing_refs", lazy="raise"
    )

    __table_args__ = (
        Index("ix_ref_target", "target_kind", "target_name", "target_namespace"),
        UniqueConstraint("source_id", "ref_field", name="uq_ref_source_field"),
        CheckConstraint("length(target_name) >= 1", name="ck_ref_target_name_nonempty"),
        CheckConstraint("length(target_namespace) >= 1", name="ck_ref_target_ns_nonempty"),
        CheckConstraint("length(ref_field) >= 1", name="ck_ref_field_nonempty"),
    )

    def __repr__(self) -> str:
        return f"<ResourceRef {self.source_id} -> {self.target_kind.value}/{self.target_name}>"
