"""Database models and API schemas.

ORM models:
    Resource, ResourceRef — generic resource storage (resource.py)
    Execution, ExecutionTask, ExecutionToolCall, ExecutionEvent — execution tracking (execution.py)
    User, Group, GroupMember — authentication and group membership (user.py)

API schemas (Pydantic):
    resource_schemas — request/response models for resource endpoints
    execution_schemas — request/response models for execution endpoints
"""

from __future__ import annotations

from blackbeard.models.database import Base, async_session, get_session
from blackbeard.models.execution import (
    TERMINAL_STATUSES,
    Execution,
    ExecutionEvent,
    ExecutionStatus,
    ExecutionTask,
    ExecutionToolCall,
    TaskStatus,
)
from blackbeard.models.resource import Resource, ResourceRef
from blackbeard.models.user import Group, GroupMember, User

__all__ = [
    "TERMINAL_STATUSES",
    "Base",
    "Execution",
    "ExecutionEvent",
    "ExecutionStatus",
    "ExecutionTask",
    "ExecutionToolCall",
    "Group",
    "GroupMember",
    "Resource",
    "ResourceRef",
    "TaskStatus",
    "User",
    "async_session",
    "get_session",
]
