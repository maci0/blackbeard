"""Resource system: validation, CRUD service, and reference management."""

from blackbeard.resources.exceptions import (
    ResourceConflictError,
    ResourceNotFoundError,
    ResourceValidationError,
    ValidationError,
)
from blackbeard.resources.refs import build_adjacency, detect_cycles
from blackbeard.resources.service import ResourceService
from blackbeard.resources.validator import validate_resource

__all__ = [
    "ResourceConflictError",
    "ResourceNotFoundError",
    "ResourceService",
    "ResourceValidationError",
    "ValidationError",
    "build_adjacency",
    "detect_cycles",
    "validate_resource",
]
