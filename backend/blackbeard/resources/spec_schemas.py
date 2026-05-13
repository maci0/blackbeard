"""JSON Schema definitions for each resource kind.

Used to validate the `spec` field of resources on create/update.
"""

from blackbeard.kinds import ALL_KINDS

AGENT_SCHEMA = {
    "type": "object",
    "required": ["role", "goal", "backstory"],
    "properties": {
        "role": {"type": "string", "minLength": 1},
        "goal": {"type": "string", "minLength": 1},
        "backstory": {"type": "string", "minLength": 1},
        "llm": {"type": "string"},
        "tools": {
            "type": "array",
            "items": {"type": "string"},
        },
        "allow_delegation": {"type": "boolean", "default": False},
        "verbose": {"type": "boolean", "default": True},
        "max_iter": {"type": "integer", "minimum": 1},
        "max_rpm": {"type": "integer", "minimum": 1},
        "memory": {"type": "boolean"},
        "cache": {"type": "boolean"},
        "system_template": {"type": "string"},
        "prompt_template": {"type": "string"},
        "response_template": {"type": "string"},
    },
    "additionalProperties": False,
}

TASK_SCHEMA = {
    "type": "object",
    "required": ["description", "expected_output", "agent"],
    "properties": {
        "description": {"type": "string", "minLength": 1},
        "expected_output": {"type": "string", "minLength": 1},
        "agent": {"type": "string"},
        "context": {
            "type": "array",
            "items": {"type": "string"},
        },
        "tools": {
            "type": "array",
            "items": {"type": "string"},
        },
        "async_execution": {"type": "boolean", "default": False},
        "human_input": {"type": "boolean", "default": False},
        "output_json": {"type": "object"},
        "output_pydantic": {"type": "string"},
        "output_file": {"type": "string", "pattern": "^[a-zA-Z0-9][a-zA-Z0-9._-]*$"},
        "callback": {"type": "string"},
        "guardrails": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "additionalProperties": False,
}

CREW_SCHEMA = {
    "type": "object",
    "required": ["process", "agents", "tasks"],
    "properties": {
        "description": {"type": "string"},
        "process": {"type": "string", "enum": ["sequential", "hierarchical"]},
        "agents": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
        },
        "tasks": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
        },
        "verbose": {"type": "boolean", "default": True},
        "memory": {"type": "boolean"},
        "cache": {"type": "boolean"},
        "max_rpm": {"type": "integer", "minimum": 1},
        "manager_llm": {"type": "string"},
        "manager_agent": {"type": "string"},
        "planning": {"type": "boolean"},
        "planning_llm": {"type": "string"},
        "inputs": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "required": {"type": "boolean", "default": True},
                    "default": {},
                },
            },
        },
        "default_agent_policy": {"type": "string"},
        "inline": {"type": "object"},
    },
    "additionalProperties": False,
}

TOOL_SCHEMA = {
    "type": "object",
    "required": ["type"],
    "properties": {
        "type": {"type": "string", "enum": ["python", "wasm", "builtin"]},
        "class_path": {"type": "string", "pattern": "^[a-zA-Z_][a-zA-Z0-9_.]*$"},
        "description": {"type": "string"},
        "wasm_module": {"type": "string", "pattern": "^(?![/\\\\])(?!.*\\.\\.).*\\.wasm$"},
        "config": {"type": "object"},
        "sandbox": {"type": "string", "enum": ["none", "wasm"], "default": "none"},
        "capabilities": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "additionalProperties": False,
}

LLM_CONNECTION_SCHEMA = {
    "type": "object",
    "required": ["provider", "model"],
    "properties": {
        "provider": {"type": "string"},
        "model": {"type": "string"},
        "parameters": {
            "type": "object",
            "properties": {
                "temperature": {"type": "number", "minimum": 0, "maximum": 2},
                "max_tokens": {"type": "integer", "minimum": 1},
                "top_p": {"type": "number", "minimum": 0, "maximum": 1},
                "frequency_penalty": {"type": "number"},
                "presence_penalty": {"type": "number"},
                "stop": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "additionalProperties": True,
        },
        "vertex": {
            "type": "object",
            "properties": {
                "project": {"type": "string"},
                "location": {"type": "string"},
            },
        },
        "api_key_env": {"type": "string", "pattern": "^[A-Z][A-Z0-9_]*(_API_KEY|_KEY|_SECRET)$"},
        "base_url": {"type": "string", "pattern": "^https?://[a-zA-Z0-9][a-zA-Z0-9.\\-]+(:[0-9]+)?(/.*)?$"},
    },
    "additionalProperties": False,
}

AGENT_POLICY_SCHEMA = {
    "type": "object",
    "properties": {
        "tools": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["all", "allowlist", "denylist"]},
                "allow": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "deny": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
        },
        "budget": {
            "type": "object",
            "properties": {
                "max_usd": {"type": "number", "minimum": 0},
                "max_tokens": {"type": "integer", "minimum": 1},
            },
        },
        "sandbox": {
            "type": "object",
            "properties": {
                "minimum_tier": {"type": "string", "enum": ["none", "wasm", "docker", "microvm"]},
            },
        },
    },
    "additionalProperties": False,
}

GUARDRAIL_SCHEMA = {
    "type": "object",
    "required": ["type"],
    "properties": {
        "type": {"type": "string", "enum": ["function", "llm"]},
        "description": {"type": "string"},
        "function_path": {"type": "string", "pattern": "^[a-zA-Z_][a-zA-Z0-9_.]*$"},
        "llm_prompt": {"type": "string"},
        "llm": {"type": "string"},
        "on_fail": {"type": "string", "enum": ["reject", "warn", "log"], "default": "reject"},
    },
    "additionalProperties": False,
}

# Map kind string → schema
KIND_SCHEMAS: dict[str, dict] = {
    "Agent": AGENT_SCHEMA,
    "Task": TASK_SCHEMA,
    "Crew": CREW_SCHEMA,
    "Tool": TOOL_SCHEMA,
    "LLMConnection": LLM_CONNECTION_SCHEMA,
    "AgentPolicy": AGENT_POLICY_SCHEMA,
    "Guardrail": GUARDRAIL_SCHEMA,
}

# Verify all kinds have schemas — catches missing schemas at import time
assert set(KIND_SCHEMAS.keys()) == set(ALL_KINDS), (
    f"KIND_SCHEMAS keys {set(KIND_SCHEMAS.keys())} don't match ALL_KINDS {set(ALL_KINDS)}"
)
