"""JSON Schema definitions for each resource kind.

Used to validate the `spec` field of resources on create/update.
Copied from backend/blackbeard/resources/spec_schemas.py — keep in sync.
"""

from __future__ import annotations

from typing import Any

from blackbeard_cli.kinds import ALL_KINDS

AGENT_SCHEMA = {
    "type": "object",
    "required": ["role", "goal", "backstory"],
    "properties": {
        "role": {"type": "string", "minLength": 1, "maxLength": 1000},
        "goal": {"type": "string", "minLength": 1, "maxLength": 5000},
        "backstory": {"type": "string", "minLength": 1, "maxLength": 10000},
        "llm": {"type": "string", "maxLength": 500},
        "tools": {
            "type": "array",
            "items": {"type": "string", "maxLength": 500},
            "maxItems": 50,
        },
        "allow_delegation": {"type": "boolean", "default": False},
        "verbose": {"type": "boolean", "default": True},
        "max_iter": {"type": "integer", "minimum": 1},
        "max_rpm": {"type": "integer", "minimum": 1},
        "memory": {
            "oneOf": [
                {"type": "boolean"},
                {
                    "type": "object",
                    "properties": {
                        "enabled": {"type": "boolean", "default": True},
                        "recency_weight": {"type": "number", "minimum": 0, "maximum": 1},
                        "semantic_weight": {"type": "number", "minimum": 0, "maximum": 1},
                        "importance_weight": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                    "additionalProperties": False,
                },
            ],
        },
        "cache": {"type": "boolean"},
        "policy": {"type": "string", "maxLength": 500},
        "tool_discovery": {"type": "boolean", "default": True},
        "skills": {
            "type": "array",
            "items": {"type": "string", "maxLength": 500},
            "maxItems": 20,
        },
        "knowledge_sources": {
            "type": "array",
            "items": {"type": "string", "maxLength": 500},
            "maxItems": 20,
        },
        "system_template": {"type": "string", "maxLength": 50000},
        "prompt_template": {"type": "string", "maxLength": 50000},
        "response_template": {"type": "string", "maxLength": 50000},
        "serviceAccount": {
            "type": "string",
            "maxLength": 255,
            "pattern": "^[a-z0-9][a-z0-9\\-]*$",
        },
    },
    "additionalProperties": False,
}

TASK_SCHEMA = {
    "type": "object",
    "required": ["description", "expected_output", "agent"],
    "properties": {
        "description": {"type": "string", "minLength": 1, "maxLength": 50000},
        "expected_output": {"type": "string", "minLength": 1, "maxLength": 10000},
        "agent": {"type": "string", "minLength": 1, "maxLength": 500},
        "context": {
            "type": "array",
            "items": {"type": "string", "maxLength": 500},
            "maxItems": 50,
        },
        "tools": {
            "type": "array",
            "items": {"type": "string", "maxLength": 500},
            "maxItems": 50,
        },
        "async_execution": {"type": "boolean", "default": False},
        "human_input": {"type": "boolean", "default": False},
        "output_json": {"type": "object", "maxProperties": 100},
        "output_pydantic": {"type": "string", "maxLength": 500},
        "output_file": {
            "type": "string",
            "pattern": "^[a-zA-Z0-9][a-zA-Z0-9._-]*$",
            "maxLength": 255,
        },
        "callback": {"type": "string", "maxLength": 500},
        "guardrails": {
            "type": "array",
            "items": {"type": "string", "maxLength": 500},
            "maxItems": 20,
        },
    },
    "additionalProperties": False,
}

CREW_SCHEMA = {
    "type": "object",
    "required": ["process", "agents", "tasks"],
    "properties": {
        "description": {"type": "string", "maxLength": 5000},
        "process": {"type": "string", "enum": ["sequential", "hierarchical"]},
        "agents": {
            "type": "array",
            "items": {"type": "string", "maxLength": 500},
            "minItems": 1,
            "maxItems": 100,
        },
        "tasks": {
            "type": "array",
            "items": {"type": "string", "maxLength": 500},
            "minItems": 1,
            "maxItems": 100,
        },
        "verbose": {"type": "boolean", "default": True},
        "memory": {
            "oneOf": [
                {"type": "boolean"},
                {
                    "type": "object",
                    "properties": {
                        "enabled": {"type": "boolean", "default": True},
                        "provider": {
                            "type": "string",
                            "enum": ["lancedb", "chromadb", "qdrant", "muninndb"],
                            "default": "lancedb",
                        },
                        "config": {"type": "object", "maxProperties": 50},
                        "muninndb_url": {"type": "string", "maxLength": 500},
                        "muninndb_vault": {"type": "string", "maxLength": 255},
                        "muninndb_token_env": {
                            "type": "string",
                            "pattern": "^[A-Z][A-Z0-9_]*$",
                            "maxLength": 100,
                        },
                    },
                    "additionalProperties": False,
                },
            ],
        },
        "embedder": {
            "type": "object",
            "properties": {
                "provider": {"type": "string", "maxLength": 100},
                "config": {"type": "object", "maxProperties": 50},
            },
            "additionalProperties": False,
        },
        "cache": {"type": "boolean"},
        "max_rpm": {"type": "integer", "minimum": 1},
        "manager_llm": {"type": "string", "maxLength": 500},
        "manager_agent": {"type": "string", "maxLength": 500},
        "planning": {"type": "boolean"},
        "planning_llm": {"type": "string", "maxLength": 500},
        "inputs": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {"type": "string", "minLength": 1, "maxLength": 255},
                    "description": {"type": "string", "maxLength": 1000},
                    "required": {"type": "boolean", "default": True},
                    "default": {},
                },
            },
            "maxItems": 50,
        },
        "tool_loading": {
            "type": "string",
            "enum": ["jit", "eager", "hybrid"],
            "default": "hybrid",
        },
        "default_agent_policy": {"type": "string", "maxLength": 500},
        "hooks": {
            "type": "object",
            "properties": {
                "before_kickoff": {"type": "string", "maxLength": 500},
                "after_kickoff": {"type": "string", "maxLength": 500},
                "before_task": {"type": "string", "maxLength": 500},
                "after_task": {"type": "string", "maxLength": 500},
                "on_error": {"type": "string", "maxLength": 500},
            },
            "additionalProperties": False,
        },
        "inline": {"type": "object", "maxProperties": 200},
        "a2a": {
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean", "default": False},
                "protocol_versions": {
                    "type": "array",
                    "items": {"type": "string", "maxLength": 10},
                    "maxItems": 5,
                },
                "transports": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["json-rpc", "grpc"],
                    },
                    "maxItems": 2,
                },
                "auth": {"type": "string", "maxLength": 500},
                "public": {"type": "boolean", "default": False},
            },
            "additionalProperties": False,
        },
    },
    "additionalProperties": False,
}

TOOL_SCHEMA = {
    "type": "object",
    "required": ["type"],
    "properties": {
        "type": {
            "type": "string",
            "enum": ["python", "wasm", "builtin", "mcp-stdio", "mcp-http"],
        },
        "class_path": {"type": "string", "pattern": "^[a-zA-Z_][a-zA-Z0-9_.]*$", "maxLength": 500},
        "description": {"type": "string", "maxLength": 5000},
        "wasm_module": {
            "type": "string",
            "pattern": "^(?![/\\\\])(?!.*\\.\\.).*\\.wasm$",
            "maxLength": 500,
        },
        "config": {"type": "object", "maxProperties": 50},
        "sandbox": {
            "type": "string",
            "enum": ["none", "wasm", "docker", "podman", "gvisor", "microvm"],
            "default": "none",
        },
        "capabilities": {
            "type": "array",
            "items": {"type": "string", "maxLength": 100},
            "maxItems": 20,
        },
        "command": {"type": "string", "maxLength": 500},
        "args": {
            "type": "array",
            "items": {"type": "string", "maxLength": 500},
            "maxItems": 20,
        },
        "url": {"type": "string", "maxLength": 2000},
        "env": {
            "type": "object",
            "additionalProperties": {"type": "string", "maxLength": 10000},
            "maxProperties": 50,
        },
    },
    "additionalProperties": False,
}

LLM_CONNECTION_SCHEMA = {
    "type": "object",
    "required": ["provider", "model"],
    "properties": {
        "provider": {"type": "string", "minLength": 1, "maxLength": 100},
        "model": {"type": "string", "minLength": 1, "maxLength": 200},
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
                    "items": {"type": "string", "maxLength": 200},
                    "maxItems": 10,
                },
            },
            "additionalProperties": False,
        },
        "vertex": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "maxLength": 100},
                "location": {"type": "string", "maxLength": 100},
            },
            "additionalProperties": False,
        },
        "api_key_env": {
            "type": "string",
            "pattern": "^[A-Z][A-Z0-9_]*(_API_KEY|_KEY|_SECRET)$",
            "maxLength": 100,
        },
        "base_url": {
            "type": "string",
            "pattern": "^https?://[a-zA-Z0-9][a-zA-Z0-9.\\-]+(:[0-9]+)?(/.*)?$",
            "maxLength": 2000,
        },
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
                    "items": {"type": "string", "maxLength": 255},
                    "maxItems": 100,
                },
                "deny": {
                    "type": "array",
                    "items": {"type": "string", "maxLength": 255},
                    "maxItems": 100,
                },
            },
            "additionalProperties": False,
        },
        "budget": {
            "type": "object",
            "properties": {
                "max_usd": {"type": "number", "minimum": 0},
                "max_tokens": {"type": "integer", "minimum": 1},
            },
            "additionalProperties": False,
        },
        "sandbox": {
            "type": "object",
            "properties": {
                "minimum_tier": {
                    "type": "string",
                    "enum": ["none", "wasm", "docker", "podman", "gvisor", "microvm"],
                },
            },
            "additionalProperties": False,
        },
        "delegation": {
            "type": "object",
            "properties": {
                "allowed": {"type": "boolean"},
                "targets": {
                    "type": "array",
                    "items": {"type": "string", "maxLength": 255},
                    "maxItems": 50,
                },
            },
            "additionalProperties": False,
        },
        "pii": {
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean", "default": False},
                "backend": {
                    "type": "string",
                    "enum": ["default", "presidio-nlp", "litellm"],
                    "default": "default",
                },
                "model": {"type": "string", "maxLength": 255},
                "entities": {
                    "type": "array",
                    "items": {"type": "string", "maxLength": 50},
                    "maxItems": 30,
                },
                "redact_outputs": {"type": "boolean", "default": True},
                "redact_events": {"type": "boolean", "default": True},
            },
            "additionalProperties": False,
        },
    },
    "additionalProperties": False,
}

GUARDRAIL_SCHEMA = {
    "type": "object",
    "required": ["type"],
    "properties": {
        "type": {"type": "string", "enum": ["function", "llm", "schema", "pii"]},
        "description": {"type": "string", "maxLength": 5000},
        "function_path": {
            "type": "string",
            "pattern": "^[a-zA-Z_][a-zA-Z0-9_.]*$",
            "maxLength": 500,
        },
        "llm_prompt": {"type": "string", "maxLength": 50000},
        "llm": {"type": "string", "maxLength": 500},
        "json_schema": {"type": "object", "maxProperties": 200},
        "on_fail": {"type": "string", "enum": ["reject", "warn", "log"], "default": "reject"},
        "pii_entities": {
            "type": "array",
            "items": {"type": "string", "maxLength": 50},
            "maxItems": 30,
        },
        "pii_action": {
            "type": "string",
            "enum": ["redact", "reject", "warn"],
            "default": "redact",
        },
    },
    "additionalProperties": False,
}

FLOW_SCHEMA = {
    "type": "object",
    "required": ["steps"],
    "properties": {
        "description": {"type": "string", "maxLength": 5000},
        "state_schema": {"type": "object", "maxProperties": 100},
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "type"],
                "properties": {
                    "name": {"type": "string", "minLength": 1, "maxLength": 255},
                    "type": {
                        "type": "string",
                        "enum": ["crew", "function", "router", "condition", "transform"],
                    },
                    "crew": {"type": "string", "maxLength": 500},
                    "function_path": {
                        "type": "string",
                        "pattern": "^[a-zA-Z_][a-zA-Z0-9_.]*:[a-zA-Z_][a-zA-Z0-9_]*$",
                        "maxLength": 500,
                    },
                    "listen_to": {
                        "type": "array",
                        "items": {"type": "string", "maxLength": 255},
                        "maxItems": 20,
                    },
                    "condition": {"type": "string", "maxLength": 1000},
                    "wasm_module": {"type": "string", "maxLength": 500},
                    "transform_config": {"type": "object", "maxProperties": 50},
                    "routes": {
                        "type": "object",
                        "additionalProperties": {"type": "string", "maxLength": 255},
                    },
                    "hooks": {
                        "type": "object",
                        "properties": {
                            "before": {"type": "string", "maxLength": 500},
                            "after": {"type": "string", "maxLength": 500},
                            "on_error": {"type": "string", "maxLength": 500},
                        },
                        "additionalProperties": False,
                    },
                },
                "additionalProperties": False,
            },
            "minItems": 1,
            "maxItems": 50,
        },
        "memory": {"type": "boolean", "default": False},
        "verbose": {"type": "boolean", "default": True},
    },
    "additionalProperties": False,
}

KNOWLEDGE_SOURCE_SCHEMA = {
    "type": "object",
    "required": ["type"],
    "properties": {
        "type": {
            "type": "string",
            "enum": ["text", "pdf", "csv", "json", "excel", "string", "url"],
        },
        "description": {"type": "string", "maxLength": 5000},
        "file_paths": {
            "type": "array",
            "items": {
                "type": "string",
                "pattern": "^(?![/\\\\~])(?!.*\\.\\.).*$",
                "maxLength": 500,
            },
            "maxItems": 50,
        },
        "content": {"type": "string", "maxLength": 100000},
        "urls": {
            "type": "array",
            "items": {"type": "string", "maxLength": 2000},
            "maxItems": 20,
        },
        "chunk_size": {"type": "integer", "minimum": 100, "maximum": 10000, "default": 4000},
        "chunk_overlap": {"type": "integer", "minimum": 0, "maximum": 1000, "default": 200},
    },
    "additionalProperties": False,
}

ROLE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["rules"],
    "properties": {
        "description": {"type": "string", "maxLength": 5000},
        "rules": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["resources", "verbs"],
                "properties": {
                    "resources": {
                        "type": "array",
                        "items": {"type": "string", "maxLength": 255},
                        "minItems": 1,
                        "maxItems": 50,
                    },
                    "verbs": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                "get",
                                "list",
                                "create",
                                "update",
                                "delete",
                                "run",
                                "invoke",
                                "delegate",
                                "*",
                            ],
                        },
                        "minItems": 1,
                        "maxItems": 20,
                    },
                    "resourceNames": {
                        "type": "array",
                        "items": {"type": "string", "maxLength": 255},
                        "maxItems": 100,
                    },
                    "namespaces": {
                        "type": "array",
                        "items": {"type": "string", "maxLength": 255},
                        "maxItems": 50,
                    },
                },
                "additionalProperties": False,
            },
            "minItems": 1,
            "maxItems": 50,
        },
        "subjectKinds": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": ["User", "Group", "Agent", "Crew"],
            },
            "maxItems": 10,
        },
    },
    "additionalProperties": False,
}

ROLE_BINDING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["role", "subjects"],
    "properties": {
        "role": {"type": "string", "minLength": 1, "maxLength": 500},
        "subjects": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["kind", "name"],
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["User", "Group", "Agent", "Crew"],
                    },
                    "name": {"type": "string", "minLength": 1, "maxLength": 255},
                },
                "additionalProperties": False,
            },
            "minItems": 1,
            "maxItems": 100,
        },
        "scope": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "maxLength": 255},
            },
            "additionalProperties": False,
        },
    },
    "additionalProperties": False,
}

AUTOMATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["target", "trigger"],
    "properties": {
        "description": {"type": "string", "maxLength": 5000},
        "target": {
            "type": "object",
            "required": ["kind", "name"],
            "properties": {
                "kind": {"type": "string", "enum": ["Crew", "Flow"]},
                "name": {"type": "string", "maxLength": 255},
            },
            "additionalProperties": False,
        },
        "trigger": {
            "type": "object",
            "required": ["type"],
            "properties": {
                "type": {"type": "string", "enum": ["cron", "webhook", "api"]},
                "cron": {"type": "string", "maxLength": 100},
                "webhook_secret": {"type": "string", "minLength": 16, "maxLength": 255},
            },
            "additionalProperties": False,
        },
        "inputs": {"type": "object", "maxProperties": 100},
        "enabled": {"type": "boolean", "default": True},
        "max_concurrent": {"type": "integer", "minimum": 1, "maximum": 10, "default": 1},
        "namespace": {"type": "string", "maxLength": 255},
    },
    "additionalProperties": False,
}

NAMESPACE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "description": {"type": "string", "maxLength": 5000},
        "labels": {
            "type": "object",
            "additionalProperties": {"type": "string", "maxLength": 255},
            "maxProperties": 50,
        },
        "default_agent_policy": {"type": "string", "maxLength": 500},
        "resource_quota": {
            "type": "object",
            "properties": {
                "max_resources": {"type": "integer", "minimum": 1, "maximum": 10000},
                "max_executions_per_hour": {"type": "integer", "minimum": 1, "maximum": 1000},
            },
            "additionalProperties": False,
        },
    },
    "additionalProperties": False,
}

KIND_SCHEMAS: dict[str, dict[str, Any]] = {
    "Agent": AGENT_SCHEMA,
    "Task": TASK_SCHEMA,
    "Crew": CREW_SCHEMA,
    "Tool": TOOL_SCHEMA,
    "LLMConnection": LLM_CONNECTION_SCHEMA,
    "AgentPolicy": AGENT_POLICY_SCHEMA,
    "Guardrail": GUARDRAIL_SCHEMA,
    "Flow": FLOW_SCHEMA,
    "KnowledgeSource": KNOWLEDGE_SOURCE_SCHEMA,
    "Role": ROLE_SCHEMA,
    "RoleBinding": ROLE_BINDING_SCHEMA,
    "Automation": AUTOMATION_SCHEMA,
    "Namespace": NAMESPACE_SCHEMA,
}

# Verify all kinds have schemas — catches missing schemas at import time
assert set(KIND_SCHEMAS.keys()) == set(ALL_KINDS), (
    f"KIND_SCHEMAS keys {set(KIND_SCHEMAS.keys())} don't match ALL_KINDS {set(ALL_KINDS)}"
)
