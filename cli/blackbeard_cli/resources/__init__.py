"""Resource system: validation, reference management, and cycle detection."""

from __future__ import annotations

from blackbeard_cli.resources.exceptions import ValidationError
from blackbeard_cli.resources.refs import build_adjacency, detect_cycles, parse_ref
from blackbeard_cli.resources.validator import (
    ALLOWED_FUNCTION_MODULE_PREFIXES,
    ALLOWED_TOOL_MODULE_PREFIXES,
    BLOCKED_FUNCTION_MODULES,
    BLOCKED_TOOL_SUBMODULES,
    check_url_ssrf,
    is_internal_host,
    validate_resource,
)

__all__ = [
    "ALLOWED_FUNCTION_MODULE_PREFIXES",
    "ALLOWED_TOOL_MODULE_PREFIXES",
    "BLOCKED_FUNCTION_MODULES",
    "BLOCKED_TOOL_SUBMODULES",
    "ValidationError",
    "build_adjacency",
    "check_url_ssrf",
    "detect_cycles",
    "is_internal_host",
    "parse_ref",
    "validate_resource",
]
