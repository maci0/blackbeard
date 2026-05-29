"""Database models and session utilities.

This package re-exports ORM models and session factories.
Pydantic API schemas live in submodules and should be imported directly:
    ``from blackbeard.models.resource_schemas import ResourceCreate``
    ``from blackbeard.models.execution_schemas import ExecutionResponse``
    ``from blackbeard.models.user_schemas import UserResponse``
"""

from __future__ import annotations

from blackbeard.models.audit import AuditLog
from blackbeard.models.database import Base, async_session, get_session
from blackbeard.models.execution import (
    TERMINAL_STATUSES,
    Execution,
    ExecutionEvent,
    ExecutionStatus,
    ExecutionTask,
    ExecutionToolCall,
    ExecutionType,
    TaskStatus,
)
from blackbeard.models.resource import Resource, ResourceRef
from blackbeard.models.resource_version import ResourceVersion
from blackbeard.models.user import Group, GroupMember, User
from blackbeard.models.webhook import Webhook

__all__ = [
    "TERMINAL_STATUSES",
    "AuditLog",
    "Base",
    "Execution",
    "ExecutionEvent",
    "ExecutionStatus",
    "ExecutionTask",
    "ExecutionToolCall",
    "ExecutionType",
    "Group",
    "GroupMember",
    "Resource",
    "ResourceRef",
    "ResourceVersion",
    "TaskStatus",
    "User",
    "Webhook",
    "async_session",
    "get_session",
]
