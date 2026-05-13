"""Canonical resource kind registry — single source of truth.

All kind-to-plural mappings should import from here.
"""

import enum


class ResourceKind(enum.StrEnum):
    """Supported resource kinds."""

    AGENT = "Agent"
    TASK = "Task"
    CREW = "Crew"
    TOOL = "Tool"
    LLM_CONNECTION = "LLMConnection"
    AGENT_POLICY = "AgentPolicy"
    GUARDRAIL = "Guardrail"


# Kind value string → URL plural path segment
KIND_TO_PLURAL: dict[str, str] = {
    ResourceKind.AGENT.value: "agents",
    ResourceKind.TASK.value: "tasks",
    ResourceKind.CREW.value: "crews",
    ResourceKind.TOOL.value: "tools",
    ResourceKind.LLM_CONNECTION.value: "llm-connections",
    ResourceKind.AGENT_POLICY.value: "agent-policies",
    ResourceKind.GUARDRAIL.value: "guardrails",
}

assert set(KIND_TO_PLURAL.keys()) == {k.value for k in ResourceKind}, (
    f"KIND_TO_PLURAL keys {set(KIND_TO_PLURAL.keys())} don't match ResourceKind values"
)

# URL plural → Kind value string
PLURAL_TO_KIND: dict[str, str] = {v: k for k, v in KIND_TO_PLURAL.items()}

# URL plural → ResourceKind enum
PLURAL_TO_KIND_ENUM: dict[str, ResourceKind] = {
    plural: ResourceKind(kind) for plural, kind in PLURAL_TO_KIND.items()
}

# All valid kind strings
ALL_KINDS: list[str] = list(KIND_TO_PLURAL.keys())

# Regex for valid resource/namespace names (used across API and CLI layers)
NAME_PATTERN = r"^[a-z0-9][a-z0-9\-]*$"
