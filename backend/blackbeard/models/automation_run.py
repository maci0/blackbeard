"""SQLAlchemy model for cron automation firing deduplication."""

from __future__ import annotations

import uuid

# SQLAlchemy resolves Mapped[datetime] at runtime, so this cannot live in a
# TYPE_CHECKING block.
from datetime import datetime  # noqa: TC003

from sqlalchemy import CheckConstraint, DateTime, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from blackbeard.models.database import Base


class AutomationRun(Base):
    """One row per (automation, scheduled cron firing time).

    Every API replica runs its own in-process scheduler and computes the
    same absolute firing times from the cron expression. The unique
    constraint is the cross-replica dedup: only the replica whose INSERT
    wins triggers the target; the losers see an IntegrityError and skip.
    Rows are pruned by the scheduler after a retention window.
    """

    __tablename__ = "automation_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    automation_name: Mapped[str] = mapped_column(String(255), nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("automation_name", "scheduled_at", name="uq_automation_run_name_time"),
        CheckConstraint("length(automation_name) >= 1", name="ck_automation_run_name_nonempty"),
    )

    def __repr__(self) -> str:
        return f"<AutomationRun {self.automation_name} at {self.scheduled_at}>"
