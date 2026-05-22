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
    ALLOWED_CALLABLE_MODULE_PREFIXES,
    ALLOWED_TOOL_MODULE_PREFIXES,
    BLOCKED_CALLABLE_MODULES,
    BLOCKED_TOOL_SUBMODULES,
    check_url_ssrf,
    is_blocked_env_name,
    is_internal_host,
    shutdown_dns_executor,
    validate_resource,
)

__all__ = [
    "ALLOWED_CALLABLE_MODULE_PREFIXES",
    "ALLOWED_TOOL_MODULE_PREFIXES",
    "BLOCKED_CALLABLE_MODULES",
    "BLOCKED_TOOL_SUBMODULES",
    "ResourceConflictError",
    "ResourceNotFoundError",
    "ResourceService",
    "ResourceValidationError",
    "ValidationError",
    "build_adjacency",
    "check_url_ssrf",
    "detect_cycles",
    "is_blocked_env_name",
    "is_internal_host",
    "parse_ref",
    "shutdown_dns_executor",
    "validate_resource",
]
