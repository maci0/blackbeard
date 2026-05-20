"""User and group management API endpoints."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from blackbeard.audit import audit_from_request, log_audit
from blackbeard.auth.dependencies import require_user
from blackbeard.models import Group, GroupMember, User, get_session
from blackbeard.models.user_schemas import UserResponse, user_response

logger = logging.getLogger(__name__)

router = APIRouter(tags=["users"])


class UserUpdateRequest(BaseModel):
    """Update fields on the authenticated user's own profile."""

    display_name: str | None = Field(default=None, min_length=1, max_length=255)


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


class GroupMemberAddRequest(BaseModel):
    """Add a user to a group."""

    user_id: str = Field(..., min_length=1, max_length=36)


class GroupMemberAddResponse(BaseModel):
    """Response after adding a user to a group."""

    group_id: str
    user_id: str
    status: str


class GroupMemberListResponse(BaseModel):
    """List of group members."""

    items: list[UserResponse]
    total: int
    limit: int = 100
    offset: int = 0
    has_more: bool = False


class GroupListResponse(BaseModel):
    """Paginated group list."""

    items: list[GroupResponse]
    total: int
    limit: int = 100
    offset: int = 0
    has_more: bool = False


def group_response(group: Group) -> GroupResponse:
    return GroupResponse(
        id=str(group.id),
        name=group.name,
        description=group.description,
        created_at=group.created_at,
    )


async def _require_group(
    session: AsyncSession, group_id: uuid.UUID, *, for_update: bool = False
) -> Group:
    """Load a group or raise 404."""
    query = select(Group).where(Group.id == group_id)
    if for_update:
        query = query.with_for_update()
    result = await session.execute(query)
    group = result.scalar_one_or_none()
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")
    return group


def _require_self_only(
    current_user: User, user_id: uuid.UUID, action: str
) -> None:
    """Raise 403 if current_user is not the target user."""
    if current_user.id != user_id:
        logger.warning(
            "Forbidden: user %s attempted to %s user %s",
            current_user.id,
            action,
            user_id,
            extra={
                "event": f"forbidden_user_{action}",
                "actor_user_id": str(current_user.id),
                "target_user_id": str(user_id),
            },
        )
        raise HTTPException(status_code=403, detail=f"Cannot {action} other users")


@router.get(
    "/users",
    response_model=UserListResponse,
    responses={401: {"description": "Authentication required"}},
)
async def list_users(
    limit: int = Query(default=100, ge=1, le=1000, description="Max results"),
    offset: int = Query(default=0, ge=0, le=100_000, description="Results to skip"),
    _current_user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> UserListResponse:
    """List users with pagination (requires authentication)."""
    result = await session.execute(
        select(User)
        .options(defer(User.password_hash))
        .order_by(User.created_at)
        .limit(limit)
        .offset(offset)
    )
    users = list(result.scalars().all())
    if len(users) < limit and (len(users) > 0 or offset == 0):
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


@router.get(
    "/users/{user_id}",
    response_model=UserResponse,
    responses={
        401: {"description": "Authentication required"},
        404: {"description": "User not found"},
    },
)
async def get_user(
    user_id: uuid.UUID,
    _current_user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> UserResponse:
    """Get a user by ID."""
    result = await session.execute(
        select(User).where(User.id == user_id).options(defer(User.password_hash))
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user_response(user)


@router.put(
    "/users/{user_id}",
    response_model=UserResponse,
    responses={
        401: {"description": "Authentication required"},
        403: {"description": "Cannot modify other users"},
        404: {"description": "User not found"},
    },
)
async def update_user(
    user_id: uuid.UUID,
    data: UserUpdateRequest,
    request: Request,
    current_user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> UserResponse:
    """Update a user (self-only — users can only modify their own profile)."""
    _require_self_only(current_user, user_id, "modify")

    result = await session.execute(
        select(User).where(User.id == user_id).options(defer(User.password_hash)).with_for_update()
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if data.display_name is not None:
        user.display_name = data.display_name

    await log_audit(
        session,
        action="user_updated",
        resource_type="User",
        resource_id=str(user.id),
        **audit_from_request(request, current_user),
    )
    await session.commit()
    await session.refresh(user)

    logger.info(
        "User updated: user_id=%s",
        user.id,
        extra={"event": "user_updated", "user_id": str(user.id)},
    )
    return user_response(user)


@router.delete(
    "/users/{user_id}",
    status_code=204,
    responses={
        401: {"description": "Authentication required"},
        403: {"description": "Cannot deactivate other users"},
        404: {"description": "User not found"},
    },
)
async def deactivate_user(
    user_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Deactivate a user (self-only soft delete)."""
    _require_self_only(current_user, user_id, "deactivate")

    result = await session.execute(select(User).where(User.id == user_id).with_for_update())
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_active = False
    user.password_hash = "!deactivated"
    user.api_key = None
    user.email = f"deleted-{user.id}@deactivated.local"
    user.display_name = "Deleted User"
    await log_audit(
        session,
        action="user_deactivated",
        resource_type="User",
        resource_id=str(user.id),
        **audit_from_request(request, current_user),
    )
    await session.commit()

    logger.info(
        "User deactivated: user_id=%s",
        user.id,
        extra={"event": "user_deactivated", "user_id": str(user.id)},
    )


@router.get(
    "/groups",
    response_model=GroupListResponse,
    responses={401: {"description": "Authentication required"}},
)
async def list_groups(
    limit: int = Query(default=100, ge=1, le=1000, description="Max results"),
    offset: int = Query(default=0, ge=0, le=100_000, description="Results to skip"),
    _current_user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> GroupListResponse:
    """List groups with pagination."""
    result = await session.execute(select(Group).order_by(Group.name).limit(limit).offset(offset))
    groups = list(result.scalars().all())
    if len(groups) < limit and (len(groups) > 0 or offset == 0):
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


@router.post(
    "/groups",
    response_model=GroupResponse,
    status_code=201,
    responses={
        401: {"description": "Authentication required"},
        409: {"description": "Group name already exists"},
    },
)
async def create_group(
    data: GroupCreateRequest,
    request: Request,
    response: Response,
    current_user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> GroupResponse:
    """Create a new group."""
    group = Group(name=data.name, description=data.description)
    session.add(group)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        logger.info(
            "Group create conflict: %s",
            data.name,
            extra={"event": "group_create_conflict", "group_name": data.name},
        )
        raise HTTPException(status_code=409, detail="Group name already exists") from None

    await log_audit(
        session,
        action="group_created",
        resource_type="Group",
        resource_id=data.name,
        **audit_from_request(request, current_user),
    )
    await session.commit()
    await session.refresh(group)

    response.headers["Location"] = f"/api/v1/groups/{group.id}"
    logger.info(
        "Group created: %s by user %s",
        group.name,
        current_user.id,
        extra={
            "event": "group_created",
            "group_id": str(group.id),
            "group_name": group.name,
            "actor_user_id": str(current_user.id),
        },
    )
    return group_response(group)


@router.get(
    "/groups/{group_id}",
    response_model=GroupResponse,
    responses={
        401: {"description": "Authentication required"},
        404: {"description": "Group not found"},
    },
)
async def get_group(
    group_id: uuid.UUID,
    _current_user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> GroupResponse:
    """Get a group by ID."""
    group = await _require_group(session, group_id)
    return group_response(group)


@router.put(
    "/groups/{group_id}",
    response_model=GroupResponse,
    responses={
        401: {"description": "Authentication required"},
        404: {"description": "Group not found"},
    },
)
async def update_group(
    group_id: uuid.UUID,
    data: GroupUpdateRequest,
    request: Request,
    current_user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> GroupResponse:
    """Update a group."""
    group = await _require_group(session, group_id, for_update=True)

    if "description" in data.model_fields_set:
        group.description = data.description

    await log_audit(
        session,
        action="group_updated",
        resource_type="Group",
        resource_id=group.name,
        **audit_from_request(request, current_user),
    )
    await session.commit()
    await session.refresh(group)

    logger.info(
        "Group updated: %s by user %s",
        group.name,
        current_user.id,
        extra={
            "event": "group_updated",
            "group_id": str(group.id),
            "group_name": group.name,
            "actor_user_id": str(current_user.id),
        },
    )
    return group_response(group)


@router.delete(
    "/groups/{group_id}",
    status_code=204,
    responses={
        204: {"description": "Group deleted (or did not exist — idempotent)"},
        401: {"description": "Authentication required"},
    },
)
async def delete_group(
    group_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete a group. Idempotent."""
    result = await session.execute(select(Group).where(Group.id == group_id).with_for_update())
    group = result.scalar_one_or_none()
    if group is None:
        logger.debug(
            "Delete no-op: group %s not found",
            group_id,
            extra={
                "event": "group_delete_noop",
                "group_id": str(group_id),
            },
        )
        return

    group_name = group.name
    await session.delete(group)
    await log_audit(
        session,
        action="group_deleted",
        resource_type="Group",
        resource_id=group_name,
        **audit_from_request(request, current_user),
    )
    await session.commit()

    logger.info(
        "Group deleted: %s by user %s",
        group_name,
        current_user.id,
        extra={
            "event": "group_deleted",
            "group_id": str(group_id),
            "group_name": group_name,
            "actor_user_id": str(current_user.id),
        },
    )


# ---------------------------------------------------------------------------
# Group Member Management
# ---------------------------------------------------------------------------


@router.get(
    "/groups/{group_id}/members",
    response_model=GroupMemberListResponse,
    responses={
        401: {"description": "Authentication required"},
        404: {"description": "Group not found"},
    },
)
async def list_group_members(
    group_id: uuid.UUID,
    limit: int = Query(default=100, ge=1, le=1000, description="Max results"),
    offset: int = Query(default=0, ge=0, le=100_000, description="Results to skip"),
    _current_user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> GroupMemberListResponse:
    """List members of a group."""
    await _require_group(session, group_id)

    result = await session.execute(
        select(User)
        .join(GroupMember, GroupMember.user_id == User.id)
        .where(GroupMember.group_id == group_id)
        .options(defer(User.password_hash))
        .order_by(User.email)
        .limit(limit)
        .offset(offset)
    )
    users = list(result.scalars().all())
    if len(users) < limit and (len(users) > 0 or offset == 0):
        total = offset + len(users)
    else:
        total_result = await session.execute(
            select(func.count())
            .select_from(GroupMember)
            .where(GroupMember.group_id == group_id)
        )
        total = total_result.scalar_one()
    return GroupMemberListResponse(
        items=[user_response(u) for u in users],
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + limit) < total,
    )


@router.post(
    "/groups/{group_id}/members",
    response_model=GroupMemberAddResponse,
    status_code=201,
    responses={
        401: {"description": "Authentication required"},
        404: {"description": "Group or user not found"},
        409: {"description": "User is already a member of the group"},
    },
)
async def add_group_member(
    group_id: uuid.UUID,
    data: GroupMemberAddRequest,
    request: Request,
    current_user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> GroupMemberAddResponse:
    """Add a user to a group."""
    # Validate user_id is a valid UUID
    try:
        target_user_id = uuid.UUID(data.user_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid user_id format") from None

    group = await _require_group(session, group_id)

    # Verify user exists
    user_result = await session.execute(select(User).where(User.id == target_user_id))
    target_user = user_result.scalar_one_or_none()
    if target_user is None:
        raise HTTPException(status_code=404, detail="User not found")

    membership = GroupMember(group_id=group_id, user_id=target_user_id)
    session.add(membership)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=409, detail="User is already a member of the group"
        ) from None

    await log_audit(
        session,
        action="group_member_added",
        resource_type="GroupMember",
        resource_id=f"{group.name}/{data.user_id}",
        **audit_from_request(request, current_user),
    )
    await session.commit()

    logger.info(
        "Member added to group %s: user %s by %s",
        group.name,
        data.user_id,
        current_user.id,
        extra={
            "event": "group_member_added",
            "group_id": str(group_id),
            "group_name": group.name,
            "target_user_id": data.user_id,
            "actor_user_id": str(current_user.id),
        },
    )
    return GroupMemberAddResponse(group_id=str(group_id), user_id=data.user_id, status="added")


@router.delete(
    "/groups/{group_id}/members/{user_id}",
    status_code=204,
    responses={
        401: {"description": "Authentication required"},
        404: {"description": "Group or membership not found"},
    },
)
async def remove_group_member(
    group_id: uuid.UUID,
    user_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Remove a user from a group."""
    group = await _require_group(session, group_id)

    result = await session.execute(
        select(GroupMember).where(
            GroupMember.group_id == group_id,
            GroupMember.user_id == user_id,
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=404, detail="User is not a member of the group")

    await session.delete(membership)
    await log_audit(
        session,
        action="group_member_removed",
        resource_type="GroupMember",
        resource_id=f"{group.name}/{user_id}",
        **audit_from_request(request, current_user),
    )
    await session.commit()

    logger.info(
        "Member removed from group %s: user %s by %s",
        group.name,
        user_id,
        current_user.id,
        extra={
            "event": "group_member_removed",
            "group_id": str(group_id),
            "group_name": group.name,
            "target_user_id": str(user_id),
            "actor_user_id": str(current_user.id),
        },
    )
