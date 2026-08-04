"""AsyncAPI 3.0 spec endpoint describing webhook event schemas.

Returns a machine-readable specification of all execution events that
Blackbeard delivers to registered webhook URLs. The endpoint is public
(no authentication required) so external tools can discover the event
contract without credentials.
"""

from __future__ import annotations

from fastapi import APIRouter

from blackbeard import __version__
from blackbeard.models.execution import ExecutionEventType

router = APIRouter(tags=["webhooks"])

# ---------------------------------------------------------------------------
# Reusable schema fragments
# ---------------------------------------------------------------------------

_UUID_SCHEMA: dict[str, str] = {"type": "string", "format": "uuid"}
_DATETIME_SCHEMA: dict[str, str] = {"type": "string", "format": "date-time"}
_STRING_SCHEMA: dict[str, str] = {"type": "string"}
_INT_SCHEMA: dict[str, str] = {"type": "integer"}
_NUMBER_SCHEMA: dict[str, str] = {"type": "number"}
_BOOL_SCHEMA: dict[str, str] = {"type": "boolean"}

# The outer envelope that wraps every webhook POST body.
_ENVELOPE_PROPERTIES: dict[str, dict[str, object]] = {
    "event_type": {
        "type": "string",
        "description": "The event type identifier",
    },
    "execution_id": {
        **_UUID_SCHEMA,
        "description": "UUID of the execution that produced this event",
    },
    "data": {
        "type": "object",
        "description": "Event-specific payload (varies by event_type)",
    },
}


def _envelope(data_ref: str) -> dict[str, object]:
    """Build a message payload schema that wraps a $ref inside the envelope."""
    return {
        "type": "object",
        "required": ["event_type", "execution_id", "data"],
        "properties": {
            "event_type": _ENVELOPE_PROPERTIES["event_type"],
            "execution_id": _ENVELOPE_PROPERTIES["execution_id"],
            "data": {"$ref": data_ref},
        },
    }


# ---------------------------------------------------------------------------
# Per-event data schemas (the contents of the "data" field)
# ---------------------------------------------------------------------------

_DATA_SCHEMAS: dict[str, dict[str, object]] = {
    "CrewStartedData": {
        "type": "object",
        "required": ["crew_name"],
        "properties": {
            "crew_name": {
                **_STRING_SCHEMA,
                "description": "Name of the crew that started",
            },
            "inputs": {
                "type": "object",
                "additionalProperties": True,
                "description": (
                    "Key-value inputs passed to the crew. Sensitive values are redacted."
                ),
            },
        },
    },
    "CrewCompletedData": {
        "type": "object",
        "properties": {
            "total_tokens": {
                **_INT_SCHEMA,
                "description": "Total tokens consumed during the crew run",
            },
        },
    },
    "TaskStartedData": {
        "type": "object",
        "required": ["task_name"],
        "properties": {
            "task_name": {
                **_STRING_SCHEMA,
                "description": "Name of the task",
            },
            "agent_role": {
                **_STRING_SCHEMA,
                "description": "Role of the agent assigned to this task",
            },
        },
    },
    "TaskCompletedData": {
        "type": "object",
        "required": ["task_name"],
        "properties": {
            "task_name": {
                **_STRING_SCHEMA,
                "description": "Name of the completed task",
            },
            "output_preview": {
                "type": ["string", "null"],
                "description": "First 500 characters of the task output",
            },
        },
    },
    "ToolStartedData": {
        "type": "object",
        "required": ["tool_name"],
        "properties": {
            "tool_name": {
                **_STRING_SCHEMA,
                "description": "Name of the tool being invoked",
            },
            "tool_args": {
                "type": ["string", "null"],
                "description": "Truncated string representation of tool arguments (max 200 chars)",
            },
            "agent_role": {
                **_STRING_SCHEMA,
                "description": "Role of the agent using the tool",
            },
        },
    },
    "ToolFinishedData": {
        "type": "object",
        "required": ["tool_name"],
        "properties": {
            "tool_name": {
                **_STRING_SCHEMA,
                "description": "Name of the tool that finished",
            },
            "from_cache": {
                **_BOOL_SCHEMA,
                "description": "Whether the result was served from cache",
            },
            "duration_ms": {
                **_INT_SCHEMA,
                "description": (
                    "Wall-clock duration in milliseconds (present when timing data is available)"
                ),
            },
        },
    },
    "LLMStartedData": {
        "type": "object",
        "properties": {
            "model": {
                **_STRING_SCHEMA,
                "description": "Model identifier (e.g. gpt-4o, claude-sonnet-4-20250514)",
            },
            "agent_role": {
                **_STRING_SCHEMA,
                "description": "Role of the agent making the LLM call",
            },
        },
    },
    "LLMCompletedData": {
        "type": "object",
        "properties": {
            "model": {
                **_STRING_SCHEMA,
                "description": "Model identifier used for the call",
            },
            "tokens": {
                **_INT_SCHEMA,
                "description": "Total tokens consumed by this call",
            },
            "response_preview": {
                "type": ["string", "null"],
                "description": "First 200 characters of the LLM response",
            },
            "duration_ms": {
                **_INT_SCHEMA,
                "description": (
                    "Wall-clock duration in milliseconds (present when timing data is available)"
                ),
            },
        },
    },
    "CostAlertData": {
        "type": "object",
        "required": ["crew_name", "execution_id", "alerts_triggered"],
        "properties": {
            "crew_name": {
                **_STRING_SCHEMA,
                "description": "Crew that triggered the alert",
            },
            "execution_id": {
                **_UUID_SCHEMA,
                "description": "Execution UUID",
            },
            "alerts_triggered": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["cost_usd", "token_usage"],
                },
                "description": "Which thresholds were crossed",
            },
            "cost_usd": {
                **_NUMBER_SCHEMA,
                "description": "Current accumulated cost in USD",
            },
            "total_tokens": {
                **_INT_SCHEMA,
                "description": "Current total token count",
            },
            "thresholds": {
                "type": "object",
                "properties": {
                    "warn_at_usd": {**_NUMBER_SCHEMA},
                    "warn_at_tokens": {**_INT_SCHEMA},
                },
                "description": "The threshold values from the AgentPolicy",
            },
        },
    },
    "HITLRequestData": {
        "type": "object",
        "required": ["prompt"],
        "properties": {
            "prompt": {
                **_STRING_SCHEMA,
                "description": "The question or prompt presented to the human operator",
            },
            "task_name": {
                **_STRING_SCHEMA,
                "description": "Name of the task requesting human input",
            },
        },
    },
    "HITLResponseData": {
        "type": "object",
        "required": ["response"],
        "properties": {
            "response": {
                **_STRING_SCHEMA,
                "description": "The human operator's response text",
            },
            "feedback": {
                "type": ["string", "null"],
                "description": "Optional additional feedback or instructions",
            },
        },
    },
}

# ---------------------------------------------------------------------------
# Event type to schema mapping
# ---------------------------------------------------------------------------

# Keys must stay aligned with ExecutionEventType (single source of truth).
_EVENT_TYPES: dict[str, dict[str, str]] = {
    ExecutionEventType.CREW_STARTED.value: {
        "ref": "#/components/schemas/CrewStartedData",
        "summary": "Crew execution started",
        "description": "Fired when a crew begins its kickoff, train, or test run.",
    },
    ExecutionEventType.CREW_COMPLETED.value: {
        "ref": "#/components/schemas/CrewCompletedData",
        "summary": "Crew execution completed successfully",
        "description": "Fired when a crew finishes all tasks without error.",
    },
    ExecutionEventType.TASK_STARTED.value: {
        "ref": "#/components/schemas/TaskStartedData",
        "summary": "Task execution started",
        "description": "Fired when an individual task begins running.",
    },
    ExecutionEventType.TASK_COMPLETED.value: {
        "ref": "#/components/schemas/TaskCompletedData",
        "summary": "Task execution completed",
        "description": "Fired when a task finishes successfully.",
    },
    ExecutionEventType.TOOL_STARTED.value: {
        "ref": "#/components/schemas/ToolStartedData",
        "summary": "Tool invocation started",
        "description": "Fired when an agent begins using a tool.",
    },
    ExecutionEventType.TOOL_FINISHED.value: {
        "ref": "#/components/schemas/ToolFinishedData",
        "summary": "Tool invocation finished",
        "description": "Fired when a tool call returns a result.",
    },
    ExecutionEventType.LLM_STARTED.value: {
        "ref": "#/components/schemas/LLMStartedData",
        "summary": "LLM call started",
        "description": "Fired when an agent sends a request to an LLM.",
    },
    ExecutionEventType.LLM_COMPLETED.value: {
        "ref": "#/components/schemas/LLMCompletedData",
        "summary": "LLM call completed",
        "description": "Fired when an LLM response is received.",
    },
    ExecutionEventType.COST_ALERT.value: {
        "ref": "#/components/schemas/CostAlertData",
        "summary": "Cost or token usage alert triggered",
        "description": (
            "Fired when spend or token usage crosses the warning thresholds "
            "defined in the AgentPolicy. Delivered before the hard budget limit."
        ),
    },
    ExecutionEventType.HITL_REQUEST.value: {
        "ref": "#/components/schemas/HITLRequestData",
        "summary": "Human-in-the-loop input requested",
        "description": (
            "Fired when a task with human_input enabled pauses execution "
            "and waits for a human response."
        ),
    },
    ExecutionEventType.HITL_RESPONSE.value: {
        "ref": "#/components/schemas/HITLResponseData",
        "summary": "Human-in-the-loop response recorded",
        "description": "Fired when a human operator submits a response to a HITL prompt.",
    },
}

assert set(_EVENT_TYPES.keys()) == {e.value for e in ExecutionEventType}, (
    "AsyncAPI _EVENT_TYPES must cover every ExecutionEventType value"
)


def _build_spec() -> dict[str, object]:
    """Build the full AsyncAPI 3.0.0 specification dict."""
    # Messages keyed by event type
    messages: dict[str, dict[str, object]] = {}
    for event_type, meta in _EVENT_TYPES.items():
        messages[event_type] = {
            "name": event_type,
            "title": meta["summary"],
            "summary": meta["description"],
            "headers": {
                "type": "object",
                "properties": {
                    "Content-Type": {
                        "type": "string",
                        "const": "application/json",
                    },
                    "X-Webhook-Signature": {
                        "type": "string",
                        "description": (
                            "HMAC-SHA256 hex digest of the request body, "
                            "computed with the webhook's signing secret"
                        ),
                    },
                    "X-Blackbeard-Event": {
                        "type": "string",
                        "description": "The event type string",
                        "const": event_type,
                    },
                },
                "required": ["Content-Type", "X-Webhook-Signature", "X-Blackbeard-Event"],
            },
            "payload": _envelope(meta["ref"]),
        }

    # Single channel: the user-provided webhook URL
    channel_messages: dict[str, dict[str, str]] = {
        event_type: {"$ref": f"#/components/messages/{event_type}"} for event_type in _EVENT_TYPES
    }

    return {
        "asyncapi": "3.0.0",
        "info": {
            "title": "Blackbeard Webhook Events",
            "version": __version__,
            "description": (
                "Webhook events delivered to registered URLs when execution state changes. "
                "Register webhooks via POST /api/v1/webhooks. "
                "Each event is signed with HMAC-SHA256 using the webhook's signing secret. "
                "The signature is sent in the X-Webhook-Signature header as a hex digest."
            ),
            "license": {
                "name": "MIT",
            },
        },
        "defaultContentType": "application/json",
        "channels": {
            "webhookEndpoint": {
                "address": "{webhookUrl}",
                "description": (
                    "The URL provided when registering a webhook via POST /api/v1/webhooks. "
                    "Blackbeard POSTs event payloads to this URL."
                ),
                "messages": channel_messages,
                "parameters": {
                    "webhookUrl": {
                        "description": "The webhook URL registered by the consumer",
                    },
                },
            },
        },
        "operations": {
            "receiveWebhookEvent": {
                "action": "send",
                "channel": {"$ref": "#/channels/webhookEndpoint"},
                "summary": "Blackbeard sends execution events to your webhook URL",
                "description": (
                    "When execution state changes, Blackbeard POSTs a JSON payload to each "
                    "matching registered webhook. Delivery is fire-and-forget. "
                    "Events are filtered by the webhook's configured event list "
                    "(empty list means all events)."
                ),
                "messages": [
                    {"$ref": f"#/channels/webhookEndpoint/messages/{et}"} for et in _EVENT_TYPES
                ],
                "security": [{"$ref": "#/components/securitySchemes/hmacSignature"}],
            },
        },
        "components": {
            "messages": messages,
            "schemas": _DATA_SCHEMAS,
            "securitySchemes": {
                "hmacSignature": {
                    "type": "httpApiKey",
                    "name": "X-Webhook-Signature",
                    "in": "header",
                    "description": (
                        "HMAC-SHA256 hex digest computed over the raw request body "
                        "using the webhook's signing secret. Verify by computing "
                        "hmac.new(secret, body, sha256).hexdigest() and comparing "
                        "with constant-time equality."
                    ),
                },
            },
        },
    }


_CACHED_SPEC: dict[str, object] | None = None


def _get_spec() -> dict[str, object]:
    """Return the spec, building and caching on first call."""
    global _CACHED_SPEC
    if _CACHED_SPEC is None:
        _CACHED_SPEC = _build_spec()
    return _CACHED_SPEC


@router.get(
    "/api/v1/asyncapi.json",
    summary="AsyncAPI 3.0 specification for webhook events",
    description=(
        "Returns the AsyncAPI 3.0 specification describing all webhook event types, "
        "payload schemas, and the HMAC-SHA256 signing scheme."
    ),
    tags=["webhooks"],
)
async def get_asyncapi_spec() -> dict[str, object]:
    """Return the AsyncAPI 3.0 spec as JSON."""
    return _get_spec()
