"""Domain exceptions for the resource system."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from blackbeard.resources.validator import ValidationError


class ResourceNotFoundError(Exception):
    """Raised when a resource is not found."""

    def __init__(self, kind: str, name: str, namespace: str = "default") -> None:
        self.kind = kind
        self.name = name
        self.namespace = namespace
        super().__init__(f"{kind}/{name} not found in namespace '{namespace}'")


class ResourceConflictError(Exception):
    """Raised on optimistic locking conflict."""

    def __init__(self, kind: str, name: str, expected: int, actual: int) -> None:
        super().__init__(
            f"Version conflict for {kind}/{name}: expected {expected}, actual {actual}"
        )


class ResourceValidationError(Exception):
    """Raised when resource validation fails."""

    def __init__(self, errors: list[ValidationError]) -> None:
        self.errors = errors
        messages = "; ".join(f"{e.field}: {e.message}" for e in errors)
        super().__init__(f"Validation failed: {messages}")
