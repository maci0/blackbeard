"""Pydantic schemas for user API response models."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from blackbeard.models.user import User


class UserResponse(BaseModel):
    """Public user profile."""

    id: str
    email: str
    display_name: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None = None


def user_response(user: User) -> UserResponse:
    return UserResponse(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )
