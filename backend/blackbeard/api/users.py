"""User and group management API endpoints."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from blackbeard.api import MUTATION_RATE_MSG as _MUTATION_RATE_MSG
from blackbeard.api import smart_total
from blackbeard.audit import audit_from_request, log_audit
from blackbeard.auth import require_permission
from blackbeard.models import (
    AuditLog,
    Execution,
    Group,
    GroupMember,
    ResourceVersion,
    User,
    get_session,
)
from blackbeard.models.user_schemas import UserResponse, user_response
from blackbeard.rate_limiter import check_rate_limit, mutation_limiter

logger = logging.getLogger(__name__)

_USER_SAFE_LOAD = (defer(User.password_hash), defer(User.api_key), defer(User.last_login_at))

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

    user_id: uuid.UUID


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


def _require_self_only(current_user: User, user_id: uuid.UUID, action: str) -> None:
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
    response: Response,
    limit: int = Query(default=100, ge=1, le=1000, description="Max results"),
    offset: int = Query(default=0, ge=0, le=100_000, description="Results to skip"),
    _current_user: User = Depends(require_permission("manage", "User", require_identity=True)),
    session: AsyncSession = Depends(get_session),
) -> UserListResponse:
    """List users with pagination (requires authentication)."""
    response.headers["Cache-Control"] = "no-store"
    result = await session.execute(
        select(User).options(*_USER_SAFE_LOAD).order_by(User.created_at).limit(limit).offset(offset)
    )
    users = list(result.scalars().all())
    total = await smart_total(session, users, limit, offset, select(func.count()).select_from(User))
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
    response: Response,
    _current_user: User = Depends(require_permission("manage", "User", require_identity=True)),
    session: AsyncSession = Depends(get_session),
) -> UserResponse:
    """Get a user by ID."""
    response.headers["Cache-Control"] = "no-store"
    result = await session.execute(select(User).where(User.id == user_id).options(*_USER_SAFE_LOAD))
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
        429: {"description": "Too many mutation requests"},
    },
)
async def update_user(
    user_id: uuid.UUID,
    data: UserUpdateRequest,
    request: Request,
    current_user: User = Depends(require_permission("manage", "User", require_identity=True)),
    session: AsyncSession = Depends(get_session),
) -> UserResponse:
    """Update a user (self-only — users can only modify their own profile)."""
    check_rate_limit(mutation_limiter, current_user, _MUTATION_RATE_MSG)
    _require_self_only(current_user, user_id, "modify")

    result = await session.execute(
        select(User).where(User.id == user_id).options(*_USER_SAFE_LOAD).with_for_update()
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
        429: {"description": "Too many mutation requests"},
    },
)
async def deactivate_user(
    user_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_permission("manage", "User", require_identity=True)),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Deactivate a user (self-only soft delete)."""
    check_rate_limit(mutation_limiter, current_user, _MUTATION_RATE_MSG)
    _require_self_only(current_user, user_id, "deactivate")

    result = await session.execute(select(User).where(User.id == user_id).with_for_update())
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    original_email = user.email
    user.is_active = False
    user.password_hash = "!deactivated"  # nosec B105 -- sentinel-value-not-a-real-password
    user.api_key = None
    anonymized_email = f"deleted-{user.id}@deactivated.local"
    user.email = anonymized_email
    user.display_name = "Deleted User"
    user.last_login_at = None
    # Remove group memberships (data minimization — sever organizational associations).
    await session.execute(delete(GroupMember).where(GroupMember.user_id == user.id))
    # Scrub PII from historical audit log entries (GDPR right to erasure).
    # Match by UUID (normal entries) and by original email (legacy failed-login entries
    # that used email as actor_id before the fix to use UUID).
    await session.execute(
        update(AuditLog)
        .where((AuditLog.actor_id == str(user.id)) | (AuditLog.actor_id == original_email))
        .values(actor_email=None, ip_address=None)
    )
    # Scrub user identity from execution records (principal_chain may reference user).
    await session.execute(
        update(Execution)
        .where(Execution.initiated_by == user.id)
        .values(initiated_by=None, principal_chain=None)
    )
    # Scrub user identity from resource version history (changed_by may store
    # user ID or legacy email).
    await session.execute(
        update(ResourceVersion)
        .where(
            (ResourceVersion.changed_by == str(user.id))
            | (ResourceVersion.changed_by == original_email)
        )
        .values(changed_by=None)
    )
    # Erasure: do not re-persist email/IP on the deactivation audit row.
    # audit_from_request would re-attach current_user.email (still in memory).
    audit_ctx = audit_from_request(request, current_user)
    audit_ctx["actor_email"] = None
    audit_ctx["ip_address"] = None
    await log_audit(
        session,
        action="user_deactivated",
        resource_type="User",
        resource_id=str(user.id),
        **audit_ctx,
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
    response: Response,
    limit: int = Query(default=100, ge=1, le=1000, description="Max results"),
    offset: int = Query(default=0, ge=0, le=100_000, description="Results to skip"),
    _current_user: User = Depends(require_permission("manage", "User", require_identity=True)),
    session: AsyncSession = Depends(get_session),
) -> GroupListResponse:
    """List groups with pagination."""
    response.headers["Cache-Control"] = "no-store"
    result = await session.execute(select(Group).order_by(Group.name).limit(limit).offset(offset))
    groups = list(result.scalars().all())
    total = await smart_total(
        session, groups, limit, offset, select(func.count()).select_from(Group)
    )
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
        429: {"description": "Too many mutation requests"},
    },
)
async def create_group(
    data: GroupCreateRequest,
    request: Request,
    response: Response,
    current_user: User = Depends(require_permission("manage", "User", require_identity=True)),
    session: AsyncSession = Depends(get_session),
) -> GroupResponse:
    """Create a new group."""
    check_rate_limit(mutation_limiter, current_user, _MUTATION_RATE_MSG)
    group = Group(name=data.name, description=data.description)
    try:
        async with session.begin_nested():
            session.add(group)
            await session.flush()
    except IntegrityError:
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
    response: Response,
    _current_user: User = Depends(require_permission("manage", "User", require_identity=True)),
    session: AsyncSession = Depends(get_session),
) -> GroupResponse:
    """Get a group by ID."""
    response.headers["Cache-Control"] = "no-store"
    group = await _require_group(session, group_id)
    return group_response(group)


@router.put(
    "/groups/{group_id}",
    response_model=GroupResponse,
    responses={
        401: {"description": "Authentication required"},
        404: {"description": "Group not found"},
        429: {"description": "Too many mutation requests"},
    },
)
async def update_group(
    group_id: uuid.UUID,
    data: GroupUpdateRequest,
    request: Request,
    current_user: User = Depends(require_permission("manage", "User", require_identity=True)),
    session: AsyncSession = Depends(get_session),
) -> GroupResponse:
    """Update a group."""
    check_rate_limit(mutation_limiter, current_user, _MUTATION_RATE_MSG)
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
        429: {"description": "Too many mutation requests"},
    },
)
async def delete_group(
    group_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_permission("manage", "User", require_identity=True)),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete a group. Idempotent."""
    check_rate_limit(mutation_limiter, current_user, _MUTATION_RATE_MSG)
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
    response: Response,
    limit: int = Query(default=100, ge=1, le=1000, description="Max results"),
    offset: int = Query(default=0, ge=0, le=100_000, description="Results to skip"),
    _current_user: User = Depends(require_permission("manage", "User", require_identity=True)),
    session: AsyncSession = Depends(get_session),
) -> GroupMemberListResponse:
    """List members of a group."""
    response.headers["Cache-Control"] = "no-store"
    await _require_group(session, group_id)

    result = await session.execute(
        select(User)
        .join(GroupMember, GroupMember.user_id == User.id)
        .where(GroupMember.group_id == group_id)
        .options(*_USER_SAFE_LOAD)
        .order_by(User.email)
        .limit(limit)
        .offset(offset)
    )
    users = list(result.scalars().all())
    total = await smart_total(
        session,
        users,
        limit,
        offset,
        select(func.count()).select_from(GroupMember).where(GroupMember.group_id == group_id),
    )
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
        429: {"description": "Too many mutation requests"},
    },
)
async def add_group_member(
    group_id: uuid.UUID,
    data: GroupMemberAddRequest,
    request: Request,
    response: Response,
    current_user: User = Depends(require_permission("manage", "User", require_identity=True)),
    session: AsyncSession = Depends(get_session),
) -> GroupMemberAddResponse:
    """Add a user to a group."""
    check_rate_limit(mutation_limiter, current_user, _MUTATION_RATE_MSG)
    target_user_id = data.user_id

    group = await _require_group(session, group_id)

    # Verify user exists
    user_result = await session.execute(
        select(User).where(User.id == target_user_id).options(*_USER_SAFE_LOAD)
    )
    target_user = user_result.scalar_one_or_none()
    if target_user is None or not target_user.is_active:
        raise HTTPException(status_code=404, detail="User not found")

    membership = GroupMember(group_id=group_id, user_id=target_user_id)
    try:
        async with session.begin_nested():
            session.add(membership)
            await session.flush()
    except IntegrityError:
        raise HTTPException(
            status_code=409, detail="User is already a member of the group"
        ) from None

    await log_audit(
        session,
        action="group_member_added",
        resource_type="GroupMember",
        resource_id=f"{group.name}/{target_user_id}",
        **audit_from_request(request, current_user),
    )
    await session.commit()

    response.headers["Location"] = f"/api/v1/groups/{group_id}/members/{target_user_id}"
    logger.info(
        "Member added to group %s: user %s by %s",
        group.name,
        target_user_id,
        current_user.id,
        extra={
            "event": "group_member_added",
            "group_id": str(group_id),
            "group_name": group.name,
            "target_user_id": str(target_user_id),
            "actor_user_id": str(current_user.id),
        },
    )
    return GroupMemberAddResponse(
        group_id=str(group_id), user_id=str(target_user_id), status="added"
    )


@router.delete(
    "/groups/{group_id}/members/{user_id}",
    status_code=204,
    responses={
        204: {"description": "Membership removed (or did not exist — idempotent)"},
        401: {"description": "Authentication required"},
        404: {"description": "Group not found"},
        429: {"description": "Too many mutation requests"},
    },
)
async def remove_group_member(
    group_id: uuid.UUID,
    user_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_permission("manage", "User", require_identity=True)),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Remove a user from a group. Idempotent."""
    check_rate_limit(mutation_limiter, current_user, _MUTATION_RATE_MSG)
    group = await _require_group(session, group_id)

    result = await session.execute(
        select(GroupMember)
        .where(
            GroupMember.group_id == group_id,
            GroupMember.user_id == user_id,
        )
        .with_for_update()
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        logger.debug(
            "Remove member no-op: user %s not in group %s",
            user_id,
            group_id,
            extra={
                "event": "group_member_remove_noop",
                "group_id": str(group_id),
                "target_user_id": str(user_id),
            },
        )
        return

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
