"""User and group management API endpoints."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from blackbeard.auth.dependencies import require_user
from blackbeard.models.database import get_session
from blackbeard.models.user import Group, User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["users"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class UserResponse(BaseModel):
    """Public user profile."""

    id: str
    email: str
    display_name: str
    is_active: bool
    created_at: str
    last_login_at: str | None = None


class UserUpdateRequest(BaseModel):
    """Update user fields (admin only)."""

    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    is_active: bool | None = None


class UserListResponse(BaseModel):
    """Paginated user list."""

    items: list[UserResponse]
    total: int


class GroupResponse(BaseModel):
    """Group response."""

    id: str
    name: str
    description: str | None = None
    created_at: str


class GroupCreateRequest(BaseModel):
    """Create a new group."""

    name: str = Field(..., min_length=1, max_length=255, pattern=r"^[a-z0-9][a-z0-9\-]*$")
    description: str | None = Field(default=None, max_length=5000)


class GroupListResponse(BaseModel):
    """Paginated group list."""

    items: list[GroupResponse]
    total: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _user_response(user: User) -> UserResponse:
    return UserResponse(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        is_active=user.is_active,
        created_at=user.created_at.isoformat() if user.created_at else "",
        last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
    )


def _group_response(group: Group) -> GroupResponse:
    return GroupResponse(
        id=str(group.id),
        name=group.name,
        description=group.description,
        created_at=group.created_at.isoformat() if group.created_at else "",
    )


# ---------------------------------------------------------------------------
# User endpoints
# ---------------------------------------------------------------------------


@router.get("/users", response_model=UserListResponse)
async def list_users(
    _current_user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> UserListResponse:
    """List all users (requires authentication)."""
    result = await session.execute(select(User).order_by(User.created_at))
    users = list(result.scalars().all())
    count_result = await session.execute(select(func.count()).select_from(User))
    total = count_result.scalar_one()
    return UserListResponse(
        items=[_user_response(u) for u in users],
        total=total,
    )


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: uuid.UUID,
    _current_user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> UserResponse:
    """Get a user by ID."""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return _user_response(user)


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    data: UserUpdateRequest,
    _current_user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> UserResponse:
    """Update a user (requires authentication)."""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if data.display_name is not None:
        user.display_name = data.display_name
    if data.is_active is not None:
        user.is_active = data.is_active

    await session.commit()
    await session.refresh(user)

    logger.info(
        "User updated: %s",
        user.email,
        extra={"event": "user_updated", "user_id": str(user.id)},
    )
    return _user_response(user)


@router.delete("/users/{user_id}", status_code=204)
async def deactivate_user(
    user_id: uuid.UUID,
    _current_user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Deactivate a user (soft delete)."""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_active = False
    await session.commit()

    logger.info(
        "User deactivated: %s",
        user.email,
        extra={"event": "user_deactivated", "user_id": str(user.id)},
    )


# ---------------------------------------------------------------------------
# Group endpoints
# ---------------------------------------------------------------------------


@router.get("/groups", response_model=GroupListResponse)
async def list_groups(
    _current_user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> GroupListResponse:
    """List all groups."""
    result = await session.execute(select(Group).order_by(Group.name))
    groups = list(result.scalars().all())
    count_result = await session.execute(select(func.count()).select_from(Group))
    total = count_result.scalar_one()
    return GroupListResponse(
        items=[_group_response(g) for g in groups],
        total=total,
    )


@router.post("/groups", response_model=GroupResponse, status_code=201)
async def create_group(
    data: GroupCreateRequest,
    _current_user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> GroupResponse:
    """Create a new group."""
    # Check for existing group
    result = await session.execute(select(Group).where(Group.name == data.name))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Group name already exists")

    group = Group(name=data.name, description=data.description)
    session.add(group)
    await session.commit()
    await session.refresh(group)

    logger.info(
        "Group created: %s",
        group.name,
        extra={"event": "group_created", "group_id": str(group.id), "group_name": group.name},
    )
    return _group_response(group)
