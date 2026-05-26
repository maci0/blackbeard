"""SQLAlchemy model for the audit log."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from blackbeard.models.database import Base


class AuditLog(Base):
    """Immutable audit log entry for security-relevant actions."""

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("now()"),
    )
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    actor_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)

    __table_args__ = (
        Index("ix_audit_timestamp", "timestamp"),
        Index("ix_audit_actor_time", "actor_id", timestamp.desc()),
        Index("ix_audit_action_time", "action", timestamp.desc()),
        Index("ix_audit_resource_time", "resource_type", "resource_id", timestamp.desc()),
        Index("ix_audit_request_id", "request_id"),
        CheckConstraint("length(actor_type) >= 1", name="ck_audit_actor_type_nonempty"),
        CheckConstraint(
            "actor_type IN ('user', 'api_key', 'system')",
            name="ck_audit_actor_type_valid",
        ),
        CheckConstraint("length(actor_id) >= 1", name="ck_audit_actor_id_nonempty"),
        CheckConstraint("length(action) >= 1", name="ck_audit_action_nonempty"),
        CheckConstraint(
            "(resource_type IS NULL) = (resource_id IS NULL)",
            name="ck_audit_resource_pair",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<AuditLog {self.action} actor={self.actor_type}:{self.actor_id}"
            f" resource={self.resource_type}/{self.resource_id}>"
        )

    def __str__(self) -> str:
        return self.__repr__()
