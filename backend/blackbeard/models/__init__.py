"""Database models and session utilities.

This package re-exports ORM models and session factories.
Pydantic API schemas live in submodules and should be imported directly:
    ``from blackbeard.models.resource_schemas import ResourceCreate``
    ``from blackbeard.models.execution_schemas import ExecutionResponse``
    ``from blackbeard.models.user_schemas import UserResponse``
"""

from __future__ import annotations

from blackbeard.models.audit import AuditLog
from blackbeard.models.automation_run import AutomationRun
from blackbeard.models.database import Base, async_session, get_session
from blackbeard.models.execution import (
    KNOWN_EXECUTION_EVENT_TYPES,
    TERMINAL_STATUSES,
    Execution,
    ExecutionEvent,
    ExecutionEventType,
    ExecutionStatus,
    ExecutionTask,
    ExecutionToolCall,
    ExecutionType,
    TaskStatus,
    can_transition_status,
)
from blackbeard.models.resource import Resource, ResourceRef
from blackbeard.models.resource_version import ResourceVersion
from blackbeard.models.user import Group, GroupMember, User
from blackbeard.models.webhook import Webhook

__all__ = [
    "KNOWN_EXECUTION_EVENT_TYPES",
    "TERMINAL_STATUSES",
    "AuditLog",
    "AutomationRun",
    "Base",
    "Execution",
    "ExecutionEvent",
    "ExecutionEventType",
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
    "can_transition_status",
    "get_session",
]
