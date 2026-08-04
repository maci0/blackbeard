"""SQLAlchemy model for resource version snapshots."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from blackbeard.models.database import Base


class ResourceVersion(Base):
    """Immutable snapshot of a resource at a specific version."""

    __tablename__ = "resource_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resources.id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    spec: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    labels: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True, default=None)
    changed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("now()"),
    )

    __table_args__ = (
        UniqueConstraint("resource_id", "version", name="uq_resource_version"),
        CheckConstraint("version >= 1", name="ck_resource_version_version_positive"),
        CheckConstraint(
            "changed_by IS NULL OR length(changed_by) >= 1",
            name="ck_resource_version_changed_by_nonempty",
        ),
    )

    def __repr__(self) -> str:
        return f"<ResourceVersion resource_id={self.resource_id} v{self.version}>"
