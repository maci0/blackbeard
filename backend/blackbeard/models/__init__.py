"""Database models and API schemas.

ORM models:
    Resource, ResourceRef — generic resource storage (resource.py)
    Execution, ExecutionTask, ExecutionToolCall — execution tracking (execution.py)

API schemas (Pydantic):
    resource_schemas — request/response models for resource endpoints
    execution_schemas — request/response models for execution endpoints
"""

from blackbeard.models.database import Base, async_session, get_session
from blackbeard.models.execution import (
    TERMINAL_STATUSES,
    Execution,
    ExecutionStatus,
    ExecutionTask,
    ExecutionToolCall,
    TaskStatus,
)
from blackbeard.models.resource import Resource, ResourceRef

__all__ = [
    "TERMINAL_STATUSES",
    "Base",
    "Execution",
    "ExecutionStatus",
    "ExecutionTask",
    "ExecutionToolCall",
    "Resource",
    "ResourceRef",
    "TaskStatus",
    "async_session",
    "get_session",
]
