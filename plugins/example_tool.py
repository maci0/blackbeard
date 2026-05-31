"""Example tool plugin for Blackbeard.

Demonstrates the plugin pattern: define a handler class that extends
one of the base classes, then expose a ``blackbeard_plugin`` dict at
module level with metadata and the handler class.
"""

from __future__ import annotations

from typing import Any

from blackbeard.plugins.base import ToolPlugin


class HelloPlugin(ToolPlugin):
    """A simple greeting tool that returns a personalized message."""

    name = "hello"
    description = "A simple greeting tool"

    def execute(self, input: dict[str, Any]) -> dict[str, Any]:
        name = input.get("name", "World")
        return {"greeting": f"Hello, {name}!"}


blackbeard_plugin = {
    "name": "hello",
    "version": "1.0.0",
    "description": "Example greeting plugin",
    "type": "tool",
    "handler": HelloPlugin,
}
