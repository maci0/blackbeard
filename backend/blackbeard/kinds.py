"""Canonical resource kind registry — single source of truth.

All kind-to-plural mappings should import from here.
"""

import enum


class ResourceKind(str, enum.Enum):
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
    "Agent": "agents",
    "Task": "tasks",
    "Crew": "crews",
    "Tool": "tools",
    "LLMConnection": "llm-connections",
    "AgentPolicy": "agent-policies",
    "Guardrail": "guardrails",
}

# URL plural → Kind value string
PLURAL_TO_KIND: dict[str, str] = {v: k for k, v in KIND_TO_PLURAL.items()}

# URL plural → ResourceKind enum
PLURAL_TO_KIND_ENUM: dict[str, ResourceKind] = {
    plural: ResourceKind(kind) for plural, kind in PLURAL_TO_KIND.items()
}

# All valid kind plural strings
ALL_PLURALS: list[str] = list(KIND_TO_PLURAL.values())

# All valid kind strings
ALL_KINDS: list[str] = list(KIND_TO_PLURAL.keys())
