"""Meta-tools for JIT tool discovery.

Agents use these to explore the tool registry on demand instead of
having all tool schemas injected into every prompt.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from crewai.tools import BaseTool
from pydantic import Field

from blackbeard.http_client import get_sync_client
from blackbeard.kinds import NAME_PATTERN

_SAFE_NAME = re.compile(NAME_PATTERN)

logger = logging.getLogger(__name__)


class _DiscoveryBaseTool(BaseTool):
    """Shared config for JIT discovery meta-tools."""

    api_url: str = Field(exclude=True)
    api_key: str = Field(exclude=True)
    namespace: str = Field(default="default", exclude=True)


class SearchToolsTool(_DiscoveryBaseTool):
    """Search the tool registry by keyword."""

    name: str = "search_tools"
    description: str = (
        "Search the tool registry for available tools by keyword or capability. "
        "Returns a list of tool names with short descriptions. "
        "Use this to discover what tools are available before using get_tool."
    )

    def _run(self, query: str) -> str:
        """Search tools matching the query."""
        try:
            client = get_sync_client("tool-discovery", timeout=10)
            resp = client.get(
                f"{self.api_url}/api/v1/tools",
                params={"namespace": self.namespace, "limit": 20},
                headers={"X-API-Key": self.api_key},
            )
            if resp.status_code != 200:
                logger.warning(
                    "search_tools API error: status=%d namespace=%s",
                    resp.status_code,
                    self.namespace,
                    extra={
                        "event": "search_tools_api_error",
                        "http_status": resp.status_code,
                        "namespace": self.namespace,
                    },
                )
                return f"Error searching tools: HTTP {resp.status_code}"

            data = resp.json()
            items: list[dict[str, Any]] = data.get("items", [])

            query_lower = query.lower()
            matches: list[dict[str, str]] = []
            for item in items:
                name = item.get("metadata", {}).get("name", "")
                spec = item.get("spec", {})
                desc = spec.get("description", "")
                tool_type = spec.get("type", "")
                text = f"{name} {desc} {tool_type}".lower()
                if query_lower in text or not query.strip():
                    matches.append(
                        {
                            "name": name,
                            "type": tool_type,
                            "description": desc[:100] if desc else "",
                        }
                    )

            if not matches:
                return "No tools found matching your query."

            return json.dumps(matches, indent=2)
        except Exception:
            logger.exception(
                "search_tools failed for query=%s namespace=%s",
                query[:200],
                self.namespace,
                extra={
                    "event": "search_tools_failed",
                    "query": query[:200],
                    "namespace": self.namespace,
                },
            )
            return "Error searching tools. Check server logs for details."


class GetToolTool(_DiscoveryBaseTool):
    """Get full details and usage instructions for a specific tool."""

    name: str = "get_tool"
    description: str = (
        "Get the full specification and usage instructions for a specific tool. "
        "Use search_tools first to find available tools, then use this to get "
        "detailed parameters and examples for a specific tool."
    )

    def _run(self, tool_name: str) -> str:
        """Get tool details by name."""
        if not _SAFE_NAME.match(tool_name):
            return f"Invalid tool name '{tool_name}': must be lowercase alphanumeric/hyphens."
        try:
            client = get_sync_client("tool-discovery", timeout=10)
            resp = client.get(
                f"{self.api_url}/api/v1/tools/{tool_name}",
                params={"namespace": self.namespace},
                headers={"X-API-Key": self.api_key},
            )
            if resp.status_code == 404:
                return f"Tool '{tool_name}' not found in the registry."
            if resp.status_code != 200:
                logger.warning(
                    "get_tool API error: tool=%s status=%d namespace=%s",
                    tool_name,
                    resp.status_code,
                    self.namespace,
                    extra={
                        "event": "get_tool_api_error",
                        "tool_name": tool_name,
                        "http_status": resp.status_code,
                        "namespace": self.namespace,
                    },
                )
                return f"Error fetching tool: HTTP {resp.status_code}"

            data = resp.json()
            spec = data.get("spec", {})

            result: dict[str, Any] = {
                "name": data.get("metadata", {}).get("name"),
                "type": spec.get("type"),
                "description": spec.get("description", ""),
                "config": spec.get("config", {}),
                "sandbox": spec.get("sandbox"),
                "class_path": spec.get("class_path"),
            }

            return json.dumps(result, indent=2)
        except Exception:
            logger.exception(
                "get_tool failed for tool=%s namespace=%s",
                tool_name,
                self.namespace,
                extra={
                    "event": "get_tool_failed",
                    "tool_name": tool_name,
                    "namespace": self.namespace,
                },
            )
            return "Error fetching tool. Check server logs for details."
