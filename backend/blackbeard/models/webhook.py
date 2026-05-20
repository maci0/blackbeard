"""SQLAlchemy model for webhook registrations."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from blackbeard.models.database import Base


class Webhook(Base):
    """A registered webhook endpoint for receiving execution events."""

    __tablename__ = "webhooks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    url: Mapped[str] = mapped_column(String(2000), nullable=False)
    events: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'")
    )
    secret: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
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

    __table_args__ = (
        Index("ix_webhook_active", "active", postgresql_where=text("active IS TRUE")),
        CheckConstraint("length(url) >= 1", name="ck_webhook_url_nonempty"),
        CheckConstraint("length(secret) >= 1", name="ck_webhook_secret_nonempty"),
    )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict for API responses (excludes secret)."""
        return {
            "id": str(self.id),
            "url": self.url,
            "events": self.events,
            "active": self.active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
