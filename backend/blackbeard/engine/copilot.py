"""Copilot engine: generate Blackbeard resources from natural language.

Uses a configured LLMConnection via the LiteLLM proxy to generate
structured YAML resource definitions (Agent, Task, Crew).
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

import httpx
import yaml

from blackbeard.config import settings
from blackbeard.http_client import get_litellm_client
from blackbeard.kinds import API_VERSION, ResourceKind
from blackbeard.logging_config import request_id_var
from blackbeard.resources.validator import validate_resource

logger = logging.getLogger(__name__)

_yaml_loader: Any = getattr(yaml, "CSafeLoader", yaml.SafeLoader)

SYSTEM_PROMPT = f"""\
You are Blackbeard Copilot. Generate CrewAI agent/task/crew definitions as YAML.

Available resource kinds:
- Agent: {{ role, goal, backstory, llm: "ref:llm-connections/<name>", tools: [...], \
allow_delegation: bool }}
- Task: {{ description, expected_output, agent: "ref:agents/<name>", \
context: ["ref:tasks/<name>", ...] }}
- Crew: {{ process: "sequential"|"hierarchical", \
agents: ["ref:agents/<name>", ...], tasks: ["ref:tasks/<name>", ...] }}

Output format: Multi-document YAML (separated by ---) with apiVersion: {API_VERSION}

Rules:
- Use descriptive agent roles and goals
- Each task must reference an agent via ref:agents/<name>
- Crew must reference all agents and tasks
- Use ref:agents/<name> and ref:tasks/<name> format for references
- Names must be lowercase-with-hyphens (e.g. "research-analyst")
- Include a meaningful backstory for each agent
- Generate the crew resource last
- Do NOT wrap the YAML in markdown code fences
- Output ONLY valid YAML, no explanatory text before or after

Example output:
---
apiVersion: {API_VERSION}
kind: Agent
metadata:
  name: researcher
spec:
  role: Researcher
  goal: Find key facts about a given topic
  backstory: An experienced researcher who excels at finding information.
---
apiVersion: {API_VERSION}
kind: Task
metadata:
  name: research-task
spec:
  description: Research the given topic and list key facts.
  expected_output: A list of key facts about the topic.
  agent: "ref:agents/researcher"
---
apiVersion: {API_VERSION}
kind: Crew
metadata:
  name: research-crew
spec:
  process: sequential
  agents:
    - "ref:agents/researcher"
  tasks:
    - "ref:tasks/research-task"
"""

_MAX_RESPONSE_LEN = 50_000
_ALLOWED_COPILOT_KINDS = frozenset({"Agent", "Task", "Crew"})


class CopilotError(Exception):
    """Raised when the copilot engine encounters an error."""


class NoLLMConnectionError(CopilotError):
    """Raised when no LLMConnection is available."""


def _get_copilot_client() -> httpx.AsyncClient:
    """Return a shared httpx client for copilot LiteLLM requests."""
    return get_litellm_client("litellm-copilot", timeout=120.0)


def _strip_markdown_fences(text: str) -> str:
    """Remove markdown code fences if the LLM wrapped its output in them."""
    stripped = text.strip()
    # Match ```yaml ... ``` or ``` ... ```
    match = re.match(r"^```(?:ya?ml)?\s*\n(.*?)```\s*$", stripped, re.DOTALL)
    if match:
        return match.group(1).strip()
    return stripped


async def _resolve_model_name(
    llm_connection_name: str | None,
    project: str,
    session: Any,
) -> str:
    """Resolve an LLMConnection name to its LiteLLM model identifier.

    If no name is given, uses the first available LLMConnection in the project.
    """
    from sqlalchemy import select

    from blackbeard.models.resource import Resource

    if llm_connection_name:
        result = await session.execute(
            select(Resource).where(
                Resource.kind == ResourceKind.LLM_CONNECTION,
                Resource.name == llm_connection_name,
                Resource.project == project,
            )
        )
        resource = result.scalar_one_or_none()
        if resource is None:
            raise NoLLMConnectionError(
                f"LLMConnection '{llm_connection_name}' not found in project '{project}'. "
                "Create an LLMConnection resource first, or omit the llm_connection field "
                "to use any available model."
            )
    else:
        result = await session.execute(
            select(Resource)
            .where(
                Resource.kind == ResourceKind.LLM_CONNECTION,
                Resource.project == project,
            )
            .limit(1)
        )
        resource = result.scalar_one_or_none()
        if resource is None:
            raise NoLLMConnectionError(
                f"No LLMConnection found in project '{project}'. "
                "Create an LLMConnection resource first so the copilot knows which model to use. "
                "Example: POST /api/v1/llm-connections with provider='ollama' and model='llama3'."
            )

    spec = resource.spec
    provider: str = str(spec.get("provider", ""))
    model: str = str(spec.get("model", ""))

    if provider and provider.lower() not in ("openai", ""):
        return f"{provider}/{model}"
    return model


def _parse_yaml_response(raw: str) -> list[dict[str, Any]]:
    """Parse multi-document YAML from the LLM response.

    Returns a list of valid resource dicts, skipping any that are malformed.
    """
    cleaned = _strip_markdown_fences(raw)

    docs: list[dict[str, Any]] = []
    try:
        for doc in yaml.load_all(cleaned, Loader=_yaml_loader):
            if isinstance(doc, dict) and "kind" in doc:
                docs.append(doc)
    except yaml.YAMLError as e:
        logger.warning(
            "Copilot YAML parse error: %s",
            e,
            extra={"event": "copilot_yaml_parse_error", "error_type": type(e).__name__},
        )
        raise CopilotError("Failed to parse the generated YAML. Try rephrasing your prompt.") from e

    if not docs:
        raise CopilotError(
            "The LLM did not return any valid YAML resource documents. "
            "Try rephrasing your prompt with more detail."
        )

    return docs


def _validate_and_filter(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate each resource document against its schema.

    Returns only documents that pass validation. Logs warnings for invalid ones.
    """
    validated: list[dict[str, Any]] = []

    for doc in docs:
        kind = doc.get("kind", "")

        if kind not in _ALLOWED_COPILOT_KINDS:
            logger.debug(
                "Copilot skipping non-allowed kind: %s",
                kind,
                extra={"event": "copilot_skip_kind", "kind": kind},
            )
            continue

        spec = doc.get("spec", {})
        if not isinstance(spec, dict):
            logger.debug(
                "Copilot skipping doc with non-dict spec: kind=%s",
                kind,
                extra={"event": "copilot_skip_bad_spec", "kind": kind},
            )
            continue

        errors, _refs = validate_resource(kind, spec)
        if errors:
            error_msgs = [f"{e.field}: {e.message}" for e in errors]
            logger.info(
                "Copilot validation errors for %s: %s",
                kind,
                "; ".join(error_msgs),
                extra={
                    "event": "copilot_validation_errors",
                    "kind": kind,
                    "error_count": len(errors),
                },
            )
            continue

        # Ensure apiVersion and metadata are present
        if "apiVersion" not in doc:
            doc["apiVersion"] = API_VERSION
        if "metadata" not in doc or not isinstance(doc.get("metadata"), dict):
            doc["metadata"] = {}
        if "name" not in doc["metadata"]:
            # Generate a name from role (Agent) or description (Task) or kind
            if kind == "Agent" and spec.get("role"):
                name = re.sub(r"[^a-z0-9]+", "-", spec["role"].lower()).strip("-")
            elif kind == "Task" and spec.get("description"):
                words = spec["description"].lower().split()[:3]
                name = re.sub(r"[^a-z0-9]+", "-", "-".join(words)).strip("-")
            else:
                name = kind.lower()
            doc["metadata"]["name"] = name

        # SECURITY: Validate the generated name matches the Blackbeard
        # name pattern.  An LLM could produce names with illegal chars
        # or empty strings after sanitization.
        final_name = doc["metadata"].get("name", "")
        if not final_name or not re.match(r"^[a-z0-9][a-z0-9\-]*$", final_name):
            doc["metadata"]["name"] = f"{kind.lower()}-{len(validated)}"

        # Truncate overly long names (max 255 chars per NAME_PATTERN usage)
        if len(doc["metadata"]["name"]) > 255:
            doc["metadata"]["name"] = doc["metadata"]["name"][:255].rstrip("-")

        validated.append(doc)

    return validated


async def generate_resources(
    prompt: str,
    llm_connection_name: str | None,
    project: str,
    session: Any,
) -> tuple[list[dict[str, Any]], str]:
    """Generate Blackbeard resources from a natural language prompt.

    Uses a configured LLMConnection via the LiteLLM proxy to generate
    structured YAML resource definitions.

    Returns:
        Tuple of (validated_resources, explanation).

    Raises:
        NoLLMConnectionError: No LLMConnection available.
        CopilotError: LLM call or parsing failed.
    """
    model_name = await _resolve_model_name(llm_connection_name, project, session)

    logger.info(
        "Copilot generating resources: model=%s prompt_len=%d",
        model_name,
        len(prompt),
        extra={
            "event": "copilot_generate_start",
            "model": model_name,
            "prompt_length": len(prompt),
            "project": project,
        },
    )

    payload: dict[str, Any] = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 4000,
    }

    t0 = time.monotonic()
    try:
        client = _get_copilot_client()
        resp = await client.post(
            f"{settings.litellm_proxy_url}/chat/completions",
            json=payload,
            headers={"X-Request-Id": request_id_var.get("-")},
            timeout=120,
        )
    except httpx.TransportError as e:
        latency_ms = int((time.monotonic() - t0) * 1000)
        logger.warning(
            "Copilot LiteLLM unreachable: model=%s %s: %s (%.0fms)",
            model_name,
            type(e).__name__,
            e,
            latency_ms,
            extra={
                "event": "copilot_litellm_unreachable",
                "model": model_name,
                "error_type": type(e).__name__,
                "latency_ms": latency_ms,
            },
        )
        raise CopilotError(
            "Model proxy is unreachable. Check that LiteLLM is running and the "
            "LLMConnection is correctly configured."
        ) from e

    latency_ms = int((time.monotonic() - t0) * 1000)

    if resp.status_code != 200:
        error_body = resp.text[:500] if resp.text else ""
        logger.warning(
            "Copilot LiteLLM error: model=%s status=%d latency_ms=%d body=%s",
            model_name,
            resp.status_code,
            latency_ms,
            error_body[:200],
            extra={
                "event": "copilot_litellm_error",
                "model": model_name,
                "http_status": resp.status_code,
                "latency_ms": latency_ms,
            },
        )
        if resp.status_code == 429:
            raise CopilotError("Model rate limit exceeded. Try again later.")
        raise CopilotError(f"Model request failed with status {resp.status_code}.")

    try:
        data = resp.json()
    except ValueError:
        logger.error(
            "Copilot: unparseable LiteLLM response: model=%s status=%d content_type=%s",
            model_name,
            resp.status_code,
            resp.headers.get("content-type", "unknown"),
            exc_info=True,
            extra={
                "event": "copilot_litellm_unparseable",
                "model": model_name,
                "http_status": resp.status_code,
                "latency_ms": latency_ms,
                "content_type": resp.headers.get("content-type", "unknown"),
            },
        )
        raise CopilotError("Model proxy returned an unparseable response.") from None

    # Extract content from the chat completion response
    choices = data.get("choices") or []
    choice = choices[0] if isinstance(choices, list) and choices else {}
    message = choice.get("message", {}) if isinstance(choice, dict) else {}
    raw_content = message.get("content", "")

    if not raw_content:
        raise CopilotError("The model returned an empty response. Try rephrasing your prompt.")

    if len(raw_content) > _MAX_RESPONSE_LEN:
        raw_content = raw_content[:_MAX_RESPONSE_LEN]

    usage = data.get("usage") or {}
    total_tokens = usage.get("total_tokens", 0) if isinstance(usage, dict) else 0

    logger.info(
        "Copilot LLM response: model=%s tokens=%d latency_ms=%d content_len=%d",
        model_name,
        total_tokens,
        latency_ms,
        len(raw_content),
        extra={
            "event": "copilot_llm_response",
            "model": model_name,
            "total_tokens": total_tokens,
            "latency_ms": latency_ms,
            "content_length": len(raw_content),
        },
    )

    # Parse and validate the YAML response
    docs = _parse_yaml_response(raw_content)
    validated = _validate_and_filter(docs)

    if not validated:
        raise CopilotError(
            "None of the generated resources passed validation. "
            "Try rephrasing your prompt with more specific requirements."
        )

    # Build explanation
    kinds_generated = [d.get("kind", "Unknown") for d in validated]
    kind_counts: dict[str, int] = {}
    for k in kinds_generated:
        kind_counts[k] = kind_counts.get(k, 0) + 1

    parts = [f"{count} {kind}{'s' if count > 1 else ''}" for kind, count in kind_counts.items()]
    explanation = f"Generated {', '.join(parts)} from your prompt."

    logger.info(
        "Copilot generated %d resources: %s",
        len(validated),
        ", ".join(f"{k}={v}" for k, v in kind_counts.items()),
        extra={
            "event": "copilot_generate_complete",
            "resource_count": len(validated),
            "kind_counts": kind_counts,
            "model": model_name,
        },
    )

    return validated, explanation
