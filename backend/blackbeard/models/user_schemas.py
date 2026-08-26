"""Pydantic schemas for user API response models."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from blackbeard.models.user import User

__all__ = [
    "UserResponse",
    "user_response",
]


class UserResponse(BaseModel):
    """Public user profile.

    last_login_at excluded: unnecessary activity-tracking exposure
    in list/detail endpoints. Frontend uses token expiry for session state.
    """

    id: str
    email: str
    display_name: str
    is_active: bool
    created_at: datetime


def user_response(user: User) -> UserResponse:
    return UserResponse(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        is_active=user.is_active,
        created_at=user.created_at,
    )
