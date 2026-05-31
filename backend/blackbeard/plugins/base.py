"""Abstract base classes for plugin extension points.

Each base class defines the interface that plugin authors must implement.
Plugins are instantiated by the plugin loader and registered in the
global registry.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import Request

    from blackbeard.models import User

__all__ = [
    "AuthPlugin",
    "ExecutionHookPlugin",
    "GuardrailPlugin",
    "ToolPlugin",
]


class ToolPlugin(ABC):
    """Base class for custom tool plugins.

    Subclasses must set ``name`` and ``description`` as class attributes
    and implement ``execute()``.
    """

    name: str = ""
    description: str = ""

    @abstractmethod
    def execute(self, input: dict[str, Any]) -> dict[str, Any]:
        """Run the tool with the given input and return results."""
        ...


class GuardrailPlugin(ABC):
    """Base class for custom guardrail plugins.

    Subclasses must set ``name`` and implement ``validate()``.
    The validate method returns a (passed, message) tuple where
    ``passed`` is True if the output is acceptable.
    """

    name: str = ""

    @abstractmethod
    def validate(self, output: str, context: dict[str, Any]) -> tuple[bool, str]:
        """Validate agent output.

        Args:
            output: The text output to validate.
            context: Additional context (task description, agent name, etc.).

        Returns:
            Tuple of (passed, message). When passed is False, message
            should explain why validation failed.
        """
        ...


class AuthPlugin(ABC):
    """Base class for custom authentication provider plugins.

    Subclasses must set ``name`` and implement ``authenticate()``.
    The auth middleware calls registered auth plugins when standard
    JWT/API-key authentication does not resolve a user.
    """

    name: str = ""

    @abstractmethod
    async def authenticate(self, request: Request) -> User | None:
        """Attempt to authenticate the request.

        Args:
            request: The incoming FastAPI/Starlette request.

        Returns:
            A User instance if authentication succeeds, None to
            pass through to the next provider.
        """
        ...


class ExecutionHookPlugin(ABC):
    """Base class for execution lifecycle hook plugins.

    Subclasses must set ``name`` and implement the hook methods.
    Hooks are called by the executor around crew kickoff.
    """

    name: str = ""

    @abstractmethod
    def before_kickoff(self, crew: Any, inputs: dict[str, Any]) -> None:
        """Called before crew.kickoff(). May mutate inputs in place."""
        ...

    @abstractmethod
    def after_kickoff(self, crew: Any, result: Any) -> None:
        """Called after crew.kickoff() completes (success or failure)."""
        ...
