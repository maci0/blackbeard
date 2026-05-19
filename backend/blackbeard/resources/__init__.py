"""Resource system: validation, CRUD service, and reference management."""

from __future__ import annotations

from blackbeard.resources.exceptions import (
    ResourceConflictError,
    ResourceNotFoundError,
    ResourceValidationError,
    ValidationError,
)
from blackbeard.resources.refs import build_adjacency, detect_cycles, parse_ref
from blackbeard.resources.service import ResourceService
from blackbeard.resources.validator import (
    ALLOWED_TOOL_MODULE_PREFIXES,
    BLOCKED_TOOL_SUBMODULES,
    is_internal_host,
    validate_resource,
)

__all__ = [
    "ALLOWED_TOOL_MODULE_PREFIXES",
    "BLOCKED_TOOL_SUBMODULES",
    "ResourceConflictError",
    "ResourceNotFoundError",
    "ResourceService",
    "ResourceValidationError",
    "ValidationError",
    "build_adjacency",
    "detect_cycles",
    "is_internal_host",
    "parse_ref",
    "validate_resource",
]
