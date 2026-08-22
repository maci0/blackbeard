"""Resource system: validation, CRUD service, and reference management.

- ``service`` — create/read/update/delete with optimistic locking
- ``validator`` — JSON Schema + structural/SSRF/callable path checks
- ``spec_schemas`` — per-kind JSON schemas (single source for ``spec``)
- ``refs`` — ``ref:kind/name`` parse, extract, cycle detection
- ``exceptions`` — validation and conflict errors for API mapping

Kind registry lives in ``blackbeard.kinds`` (not here) so CLI and API share it.
"""

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
    check_callable_path,
    check_tool_class_path,
    check_url_ssrf,
    host_resolves_external,
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
    "check_callable_path",
    "check_tool_class_path",
    "check_url_ssrf",
    "detect_cycles",
    "host_resolves_external",
    "is_blocked_env_name",
    "is_internal_host",
    "parse_ref",
    "shutdown_dns_executor",
    "validate_resource",
]
