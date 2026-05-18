"""SQLAlchemy models for users, groups, and group membership."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from blackbeard.models.database import Base


class User(Base):
    """Application user with email/password or API key authentication."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    api_key: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(
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
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    group_memberships: Mapped[list[GroupMember]] = relationship(
        "GroupMember",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="raise",
    )

    __table_args__ = (
        Index("ix_users_api_key", "api_key", postgresql_where=text("api_key IS NOT NULL")),
        Index("ix_users_created_at", "created_at"),
        Index("ix_users_email_lower", text("lower(email)"), unique=True),
        CheckConstraint("length(email) >= 1", name="ck_user_email_nonempty"),
        CheckConstraint("length(display_name) >= 1", name="ck_user_display_name_nonempty"),
    )

    def __repr__(self) -> str:
        return f"<User {self.email} active={self.is_active}>"


class Group(Base):
    """Named group for role-based access control."""

    __tablename__ = "groups"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
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

    members: Mapped[list[GroupMember]] = relationship(
        "GroupMember",
        back_populates="group",
        cascade="all, delete-orphan",
        lazy="raise",
    )

    __table_args__ = (CheckConstraint("length(name) >= 1", name="ck_group_name_nonempty"),)

    def __repr__(self) -> str:
        return f"<Group {self.name}>"


class GroupMember(Base):
    """Association table linking users to groups."""

    __tablename__ = "group_members"

    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("groups.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("now()"),
    )

    group: Mapped[Group] = relationship("Group", back_populates="members", lazy="raise")
    user: Mapped[User] = relationship("User", back_populates="group_memberships", lazy="raise")

    __table_args__ = (Index("ix_group_members_user_id", "user_id"),)

    def __repr__(self) -> str:
        return f"<GroupMember group={self.group_id} user={self.user_id}>"
