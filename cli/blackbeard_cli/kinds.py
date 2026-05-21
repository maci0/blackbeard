"""Resource kind registry — copied from backend/blackbeard/kinds.py.

Keep in sync with the backend's canonical registry.
"""

from __future__ import annotations

import enum

__all__ = [
    "ALL_KINDS",
    "API_VERSION",
    "KIND_TO_PLURAL",
    "NAME_PATTERN",
    "PLURAL_TO_KIND",
    "PLURAL_TO_KIND_ENUM",
    "ResourceKind",
]

# Canonical API version string — used by resource schemas and response serializers.
# Must stay in sync with frontend/src/lib/kinds.ts.
API_VERSION = "blackbeard/v1"


class ResourceKind(enum.StrEnum):
    """Supported resource kinds."""

    AGENT = "Agent"
    TASK = "Task"
    CREW = "Crew"
    TOOL = "Tool"
    LLM_CONNECTION = "LLMConnection"
    AGENT_POLICY = "AgentPolicy"
    GUARDRAIL = "Guardrail"
    FLOW = "Flow"
    KNOWLEDGE_SOURCE = "KnowledgeSource"
    ROLE = "Role"
    ROLE_BINDING = "RoleBinding"
    AUTOMATION = "Automation"
    NAMESPACE = "Namespace"


KIND_TO_PLURAL: dict[str, str] = {
    ResourceKind.AGENT.value: "agents",
    ResourceKind.TASK.value: "tasks",
    ResourceKind.CREW.value: "crews",
    ResourceKind.TOOL.value: "tools",
    ResourceKind.LLM_CONNECTION.value: "llm-connections",
    ResourceKind.AGENT_POLICY.value: "agent-policies",
    ResourceKind.GUARDRAIL.value: "guardrails",
    ResourceKind.FLOW.value: "flows",
    ResourceKind.KNOWLEDGE_SOURCE.value: "knowledge-sources",
    ResourceKind.ROLE.value: "roles",
    ResourceKind.ROLE_BINDING.value: "role-bindings",
    ResourceKind.AUTOMATION.value: "automations",
    ResourceKind.NAMESPACE.value: "namespaces",
}

assert set(KIND_TO_PLURAL.keys()) == {k.value for k in ResourceKind}, (
    f"KIND_TO_PLURAL keys {set(KIND_TO_PLURAL.keys())} don't match ResourceKind values"
)

PLURAL_TO_KIND: dict[str, str] = {v: k for k, v in KIND_TO_PLURAL.items()}

PLURAL_TO_KIND_ENUM: dict[str, ResourceKind] = {
    plural: ResourceKind(kind) for plural, kind in PLURAL_TO_KIND.items()
}

ALL_KINDS: frozenset[str] = frozenset(KIND_TO_PLURAL.keys())

# Regex for valid resource/namespace names (used across API and CLI layers)
NAME_PATTERN = r"^[a-z0-9][a-z0-9\-]*$"
