"""User and group management API endpoints."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from blackbeard.auth.dependencies import require_user
from blackbeard.models import Group, User, get_session

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
    created_at: datetime
    last_login_at: datetime | None = None


class UserUpdateRequest(BaseModel):
    """Update fields on the authenticated user's own profile."""

    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    is_active: bool | None = None


class UserListResponse(BaseModel):
    """Paginated user list."""

    items: list[UserResponse]
    total: int
    limit: int = 100
    offset: int = 0
    has_more: bool = False


class GroupResponse(BaseModel):
    """Group response."""

    id: str
    name: str
    description: str | None = None
    created_at: datetime


class GroupCreateRequest(BaseModel):
    """Create a new group."""

    name: str = Field(..., min_length=1, max_length=255, pattern=r"^[a-z0-9][a-z0-9\-]*$")
    description: str | None = Field(default=None, max_length=5000)


class GroupUpdateRequest(BaseModel):
    """Update group fields."""

    description: str | None = Field(default=None, max_length=5000)


class GroupListResponse(BaseModel):
    """Paginated group list."""

    items: list[GroupResponse]
    total: int
    limit: int = 100
    offset: int = 0
    has_more: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def user_response(user: User) -> UserResponse:
    return UserResponse(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


def group_response(group: Group) -> GroupResponse:
    return GroupResponse(
        id=str(group.id),
        name=group.name,
        description=group.description,
        created_at=group.created_at,
    )


# ---------------------------------------------------------------------------
# User endpoints
# ---------------------------------------------------------------------------


@router.get("/users", response_model=UserListResponse)
async def list_users(
    limit: int = Query(default=100, ge=1, le=1000, description="Max results"),
    offset: int = Query(default=0, ge=0, le=100_000, description="Results to skip"),
    _current_user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> UserListResponse:
    """List users with pagination (requires authentication)."""
    result = await session.execute(
        select(User).order_by(User.created_at).limit(limit).offset(offset)
    )
    users = list(result.scalars().all())
    if len(users) < limit:
        total = offset + len(users)
    else:
        total_result = await session.execute(select(func.count()).select_from(User))
        total = total_result.scalar_one()
    return UserListResponse(
        items=[user_response(u) for u in users],
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + limit) < total,
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
    return user_response(user)


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    data: UserUpdateRequest,
    current_user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> UserResponse:
    """Update a user (self-only — users can only modify their own profile)."""
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Cannot modify other users")

    if data.display_name is not None:
        current_user.display_name = data.display_name
    if data.is_active is not None:
        current_user.is_active = data.is_active

    await session.commit()
    await session.refresh(current_user)

    logger.info(
        "User updated: %s",
        current_user.email,
        extra={"event": "user_updated", "user_id": str(current_user.id)},
    )
    return user_response(current_user)


@router.delete("/users/{user_id}", status_code=204)
async def deactivate_user(
    user_id: uuid.UUID,
    current_user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Deactivate a user (self-only soft delete)."""
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Cannot deactivate other users")

    current_user.is_active = False
    await session.commit()

    logger.info(
        "User deactivated: %s",
        current_user.email,
        extra={"event": "user_deactivated", "user_id": str(current_user.id)},
    )


# ---------------------------------------------------------------------------
# Group endpoints
# ---------------------------------------------------------------------------


@router.get("/groups", response_model=GroupListResponse)
async def list_groups(
    limit: int = Query(default=100, ge=1, le=1000, description="Max results"),
    offset: int = Query(default=0, ge=0, le=100_000, description="Results to skip"),
    _current_user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> GroupListResponse:
    """List groups with pagination."""
    result = await session.execute(select(Group).order_by(Group.name).limit(limit).offset(offset))
    groups = list(result.scalars().all())
    if len(groups) < limit:
        total = offset + len(groups)
    else:
        total_result = await session.execute(select(func.count()).select_from(Group))
        total = total_result.scalar_one()
    return GroupListResponse(
        items=[group_response(g) for g in groups],
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + limit) < total,
    )


@router.post("/groups", response_model=GroupResponse, status_code=201)
async def create_group(
    data: GroupCreateRequest,
    response: Response,
    _current_user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> GroupResponse:
    """Create a new group."""
    result = await session.execute(select(Group).where(Group.name == data.name))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Group name already exists")

    group = Group(name=data.name, description=data.description)
    session.add(group)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Group name already exists") from None
    await session.refresh(group)

    response.headers["Location"] = f"/api/v1/groups/{group.id}"
    logger.info(
        "Group created: %s",
        group.name,
        extra={"event": "group_created", "group_id": str(group.id), "group_name": group.name},
    )
    return group_response(group)


@router.get("/groups/{group_id}", response_model=GroupResponse)
async def get_group(
    group_id: uuid.UUID,
    _current_user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> GroupResponse:
    """Get a group by ID."""
    result = await session.execute(select(Group).where(Group.id == group_id))
    group = result.scalar_one_or_none()
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")
    return group_response(group)


@router.put("/groups/{group_id}", response_model=GroupResponse)
async def update_group(
    group_id: uuid.UUID,
    data: GroupUpdateRequest,
    _current_user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> GroupResponse:
    """Update a group."""
    result = await session.execute(select(Group).where(Group.id == group_id))
    group = result.scalar_one_or_none()
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")

    if data.description is not None:
        group.description = data.description

    await session.commit()
    await session.refresh(group)

    logger.info(
        "Group updated: %s",
        group.name,
        extra={"event": "group_updated", "group_id": str(group.id)},
    )
    return group_response(group)


@router.delete(
    "/groups/{group_id}",
    status_code=204,
    responses={204: {"description": "Group deleted (or did not exist — idempotent)"}},
)
async def delete_group(
    group_id: uuid.UUID,
    _current_user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete a group. Idempotent."""
    result = await session.execute(select(Group).where(Group.id == group_id))
    group = result.scalar_one_or_none()
    if group is None:
        return

    await session.delete(group)
    await session.commit()

    logger.info(
        "Group deleted: %s",
        group.name,
        extra={"event": "group_deleted", "group_id": str(group.id), "group_name": group.name},
    )
