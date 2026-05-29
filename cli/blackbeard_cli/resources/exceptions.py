"""Domain exceptions for the resource system."""

from __future__ import annotations

from typing import NamedTuple

__all__ = [
    "ResourceConflictError",
    "ResourceNotFoundError",
    "ResourceValidationError",
    "ValidationError",
]


class ValidationError(NamedTuple):
    """A single validation error."""

    field: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return self._asdict()


class ResourceNotFoundError(Exception):
    """Raised when a resource is not found."""

    def __init__(self, kind: str, name: str, project: str = "default") -> None:
        self.kind = kind
        self.name = name
        self.namespace = namespace
        super().__init__(f"{kind}/{name} not found in namespace '{namespace}'")


class ResourceConflictError(Exception):
    """Raised on optimistic locking conflict."""

    def __init__(self, kind: str, name: str, expected: int, actual: int) -> None:
        self.kind = kind
        self.name = name
        self.expected_version = expected
        self.actual_version = actual
        super().__init__(
            f"Version conflict for {kind}/{name}: expected {expected}, actual {actual}"
        )


class ResourceValidationError(Exception):
    """Raised when resource validation fails."""

    def __init__(self, errors: list[ValidationError]) -> None:
        self.errors = errors
        messages = "; ".join(f"{e.field}: {e.message}" for e in errors)
        super().__init__(f"Validation failed: {messages}")
