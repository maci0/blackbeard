"""Resource Loader: converts stored resources into CrewAI objects.

Resolves refs, builds CrewAI Agent/Task/Crew instances, and wires
LLM connections through LiteLLM Proxy.
"""

from __future__ import annotations

import importlib
import json
import logging
import re
import threading
import time
from typing import TYPE_CHECKING, Any

import jsonschema

__all__ = [
    "LoaderError",
    "ResourceLoader",
]

from crewai import LLM, Agent, Crew, Process, Task

from blackbeard.config import settings
from blackbeard.engine.policy import AgentPolicy, resolve_policy
from blackbeard.engine.sandbox.selector import select_sandbox
from blackbeard.engine.sandbox.tool_wrapper import (
    SandboxExecutionError,
    build_wasm_tool,
    enforce_tool_sandbox,
    runtime_tier_for_tool,
)
from blackbeard.kinds import SAFE_FILENAME as _SAFE_FILENAME
from blackbeard.kinds import ResourceKind
from blackbeard.litellm import apply_model_params, apply_vertex_params
from blackbeard.resources import (
    check_callable_path,
    check_tool_class_path,
    check_url_ssrf,
    is_blocked_env_name,
    parse_ref,
)

if TYPE_CHECKING:
    from blackbeard.models import Resource

logger = logging.getLogger(__name__)

_PROCESS_MAP: dict[str, Process] = {
    "sequential": Process.sequential,
    "hierarchical": Process.hierarchical,
}

_PATH_TRAVERSAL_INDICATORS = ("..", "~", "\\", "\x00")

_SAFE_BUILTIN_NAME = re.compile(r"^[A-Z][a-zA-Z0-9]+$")

_BLOCKED_BUILTIN_NAMES = frozenset(
    {
        "CodeInterpreterTool",
        "CodeDocsSearchTool",
    }
)


def _self_api_url() -> str:
    """Return localhost API URL. Resolved at call time to avoid reading settings at import."""
    return f"http://localhost:{settings.port}"


def _check_path_safety(path: str, context: str) -> None:
    """Raise LoaderError if path contains traversal characters or targets sensitive directories."""
    if any(ind in path for ind in _PATH_TRAVERSAL_INDICATORS):
        raise LoaderError(f"{context}: path traversal characters not allowed")
    if path.startswith(("/", "\\")):
        raise LoaderError(f"{context}: absolute paths are not allowed")


_MAX_CONFIG_VALUE_LEN = 10_000
_MAX_CONFIG_ENTRIES = 50


def _validate_tool_config(config: dict[str, Any], tool_name: str) -> None:
    """Reject tool config values containing path traversal, sensitive paths, or excessive size."""
    if len(config) > _MAX_CONFIG_ENTRIES:
        raise LoaderError(
            f"Tool '{tool_name}' config has {len(config)} entries (max {_MAX_CONFIG_ENTRIES})"
        )
    for key, val in config.items():
        if not isinstance(val, str):
            continue
        if len(val) > _MAX_CONFIG_VALUE_LEN:
            raise LoaderError(
                f"Tool '{tool_name}' config.{key}: value too long "
                f"({len(val)} > {_MAX_CONFIG_VALUE_LEN})"
            )
        _check_path_safety(val, f"Tool '{tool_name}' config.{key}")


_KS_TYPE_MAP: dict[str, tuple[str, str]] = {
    "text": ("crewai.knowledge.source.text_file_knowledge_source", "TextFileKnowledgeSource"),
    "pdf": ("crewai.knowledge.source.pdf_knowledge_source", "PDFKnowledgeSource"),
    "csv": ("crewai.knowledge.source.csv_knowledge_source", "CSVKnowledgeSource"),
    "json": ("crewai.knowledge.source.json_knowledge_source", "JSONKnowledgeSource"),
    "string": ("crewai.knowledge.source.string_knowledge_source", "StringKnowledgeSource"),
}
_ks_class_cache: dict[str, type] = {}
_ks_class_cache_lock = threading.Lock()


class LoaderError(Exception):
    """Raised when resource loading fails."""


class ResourceLoader:
    """Converts pre-loaded resources into CrewAI objects."""

    def __init__(
        self,
        resources: dict[str, Resource],
        api_key: str | None = None,
        policies: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        """Initialize with a dict of resources keyed by 'Kind/name'.

        Args:
            resources: Dict of resources keyed by ``Kind/name``.
            api_key: Optional API key override for LLM connections.
                When provided, ``build_llm()`` uses this key instead of
                the global ``litellm_master_key``.  Used by the executor
                to inject per-execution virtual keys with budget limits.
            policies: Dict of policy name -> policy spec for policy
                enforcement.  When provided, ``build_agent()`` resolves
                agent policies and enforces tool filtering and delegation
                constraints at crew-build time.

        Example: {"Agent/researcher": <Resource>, "Task/research-topic": <Resource>}
        """
        self._resources = resources
        self._api_key = api_key
        self._policies = policies or {}
        self._llm_cache: dict[str, LLM] = {}
        self._agent_cache: dict[str, Agent] = {}
        self._task_cache: dict[str, Task] = {}
        self._tool_cache: dict[str, Any] = {}
        self._tools_loaded = 0
        self._tools_skipped = 0
        self._discovery_tools_cache: dict[str, list[Any]] = {}
        self._crew_guardrail_refs: list[str] = []

    def _resolve_ref(self, ref_str: str) -> Resource:
        """Resolve a ref string to a Resource object."""
        ref = parse_ref(ref_str)
        if ref is None:
            raise LoaderError(f"'{ref_str}' is not a valid ref")
        key = f"{ref.kind.value}/{ref.name}"
        resource = self._resources.get(key)
        if resource is None:
            logger.error(
                "Ref '%s' not found (%d resources loaded)",
                key,
                len(self._resources),
                extra={
                    "event": "ref_not_found",
                    "ref": key,
                    "available_count": len(self._resources),
                },
            )
            raise LoaderError(f"Referenced resource '{key}' not found")
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Resolved ref: %s → %s/%s", ref_str, resource.kind.value, resource.name)
        return resource

    def build_llm(self, ref_or_name: str) -> LLM:
        """Build a CrewAI LLM from an LLMConnection ref string."""
        if ref_or_name in self._llm_cache:
            return self._llm_cache[ref_or_name]

        resource = self._resolve_ref(ref_or_name)
        if resource.kind != ResourceKind.LLM_CONNECTION:
            raise LoaderError(f"Expected LLMConnection, got {resource.kind.value}")

        spec = resource.spec
        # LiteLLM registers the model under the resource name, not the provider model string.
        model = resource.name
        params = spec.get("parameters", {})
        vertex = spec.get("vertex", {})

        effective_key = self._api_key or settings.litellm_master_key.get_secret_value()
        llm_kwargs: dict[str, Any] = {
            "model": model,
            "base_url": settings.litellm_proxy_url,
            "api_base": settings.litellm_proxy_url,
            "api_key": effective_key,
        }

        apply_model_params(llm_kwargs, params)
        if vertex:
            apply_vertex_params(llm_kwargs, vertex)

        llm = LLM(**llm_kwargs)
        self._llm_cache[ref_or_name] = llm
        logger.info(
            "LLM built: %s model=%s",
            resource.name,
            model,
            extra={
                "event": "llm_built",
                "llm_name": resource.name,
                "model": model,
            },
        )
        return llm

    def _build_knowledge_source(self, ref_or_name: str) -> Any:
        """Build a CrewAI knowledge source from a KnowledgeSource resource ref.

        Supported types: text, pdf, csv, json, string (see ``_KS_TYPE_MAP``).
        Returns ``None`` with a warning on unsupported types or build failures.
        """
        try:
            resource = self._resolve_ref(ref_or_name)
            if resource.kind != ResourceKind.KNOWLEDGE_SOURCE:
                logger.warning(
                    "Expected KnowledgeSource, got %s",
                    resource.kind.value,
                    extra={
                        "event": "knowledge_source_kind_mismatch",
                        "ref": ref_or_name,
                        "actual_kind": resource.kind.value,
                    },
                )
                return None

            spec = resource.spec
            ks_type = spec.get("type", "string")
            file_paths = spec.get("file_paths", [])

            for fp in file_paths:
                if not isinstance(fp, str):
                    raise LoaderError(
                        f"KnowledgeSource '{resource.name}': file_path must be string"
                    )
                _check_path_safety(fp, f"KnowledgeSource '{resource.name}'")
            content = spec.get("content", "")

            entry = _KS_TYPE_MAP.get(ks_type)
            if entry is None:
                logger.warning(
                    "Knowledge source type '%s' not supported",
                    ks_type,
                    extra={
                        "event": "knowledge_source_type_unsupported",
                        "ref": ref_or_name,
                        "ks_type": ks_type,
                    },
                )
                return None

            module_path, class_name = entry
            cache_key = f"{module_path}.{class_name}"
            cls = _ks_class_cache.get(cache_key)
            if cls is None:
                with _ks_class_cache_lock:
                    cls = _ks_class_cache.get(cache_key)
                    if cls is None:
                        module = importlib.import_module(module_path)
                        cls = getattr(module, class_name)
                        _ks_class_cache[cache_key] = cls

            kwargs: dict[str, Any] = (
                {"content": content} if ks_type == "string" else {"file_paths": file_paths}
            )
            return cls(**kwargs)
        except Exception as exc:
            logger.exception(
                "Failed to build knowledge source from %s: %s",
                ref_or_name,
                exc,
                extra={
                    "event": "knowledge_source_build_failed",
                    "ref": ref_or_name,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc)[:500],
                },
            )
            return None

    def build_tool(self, ref_or_name: str) -> Any:
        """Build a tool from a Tool resource ref.

        Supports ``type: python`` (dynamic import via ``class_path``),
        ``type: builtin`` (import from ``crewai_tools``), and ``type: wasm``.
        MCP types (``mcp-stdio``, ``mcp-http``) are loaded via
        :meth:`_build_mcp_server` when attaching tools to an agent (not here).
        """
        if ref_or_name in self._tool_cache:
            return self._tool_cache[ref_or_name]

        resource = self._resolve_ref(ref_or_name)
        if resource.kind != ResourceKind.TOOL:
            raise LoaderError(f"Expected Tool, got {resource.kind.value}")

        spec = resource.spec
        tool_type = spec.get("type", "python")

        if tool_type == "python":
            class_path = spec.get("class_path")
            if not class_path:
                if spec.get("command"):
                    from blackbeard.engine.sandbox.tool_wrapper import PlaceholderTool

                    tool_instance = PlaceholderTool(
                        name=resource.name,
                        description=str(spec.get("description") or resource.name),
                    )
                    self._tool_cache[ref_or_name] = tool_instance
                    self._tools_loaded += 1
                    return tool_instance
                raise LoaderError(
                    f"Tool '{resource.name}' has type=python but no class_path or command"
                )
            path_error = check_tool_class_path(class_path)
            if path_error:
                raise LoaderError(f"Tool '{resource.name}': {path_error}")
            module_path, class_name = class_path.rsplit(".", 1)
            if class_name.startswith("_"):
                raise LoaderError(
                    f"Tool '{resource.name}': class_path '{class_path}' references a "
                    f"private/dunder attribute"
                )
            try:
                module = importlib.import_module(module_path)
                tool_cls = getattr(module, class_name)
            except Exception as exc:
                raise LoaderError(
                    f"Tool '{resource.name}': failed to import '{class_path}': {exc}"
                ) from exc

        elif tool_type == "builtin":
            builtin_name = spec.get("class_path") or resource.name
            if not _SAFE_BUILTIN_NAME.match(builtin_name):
                raise LoaderError(
                    f"Builtin tool name '{builtin_name}' is not a valid PascalCase identifier"
                )
            if builtin_name in _BLOCKED_BUILTIN_NAMES:
                raise LoaderError(
                    f"Builtin tool '{builtin_name}' is blocked because it can "
                    f"execute arbitrary code"
                )
            try:
                import crewai_tools

                tool_cls = getattr(crewai_tools, builtin_name, None)
                if tool_cls is None:
                    raise LoaderError(f"Builtin tool '{builtin_name}' not found in crewai_tools")
            except ImportError as exc:
                raise LoaderError("crewai_tools not installed") from exc

        elif tool_type == "wasm":
            wasm_path = spec.get("wasm_module")
            if not wasm_path:
                raise LoaderError(f"Tool '{resource.name}' has type=wasm but no wasm_module")
            try:
                tool_instance = build_wasm_tool(
                    name=resource.name,
                    description=str(spec.get("description") or f"WASM tool {resource.name}"),
                    wasm_path=str(wasm_path),
                )
            except SandboxExecutionError as exc:
                raise LoaderError(f"Tool '{resource.name}': {exc}") from exc
            self._tool_cache[ref_or_name] = tool_instance
            self._tools_loaded += 1
            return tool_instance

        else:
            if tool_type in ("mcp-stdio", "mcp-http"):
                logger.debug(
                    "MCP tool '%s' is attached via agent mcps, not build_tool",
                    resource.name,
                    extra={
                        "event": "mcp_tool_deferred",
                        "tool_name": resource.name,
                        "tool_type": tool_type,
                    },
                )
                return None
            self._tools_skipped += 1
            logger.warning(
                "Tool type '%s' not yet supported for runtime loading (tool=%s)",
                tool_type,
                resource.name,
                extra={
                    "event": "tool_type_unsupported",
                    "tool_name": resource.name,
                    "tool_type": tool_type,
                },
            )
            return None

        if spec.get("deprecated"):
            msg = spec.get("deprecated_message", "")
            logger.warning(
                "Tool '%s' is deprecated%s",
                resource.name,
                f": {msg}" if msg else "",
                extra={
                    "event": "tool_deprecated",
                    "tool_name": resource.name,
                    "deprecated_message": msg,
                },
            )

        config = spec.get("config", {})
        _validate_tool_config(config, resource.name)
        try:
            tool_instance = tool_cls(**config)
        except Exception as exc:
            raise LoaderError(f"Tool '{resource.name}': instantiation failed: {exc}") from exc
        self._tool_cache[ref_or_name] = tool_instance
        self._tools_loaded += 1
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "Tool loaded: %s type=%s",
                resource.name,
                tool_type,
                extra={
                    "event": "tool_loaded",
                    "tool_name": resource.name,
                    "tool_type": tool_type,
                },
            )
        return tool_instance


    def _build_mcp_server(self, resource: Resource) -> Any:
        """Build a CrewAI MCP server config from a Tool resource."""
        from crewai.mcp import MCPServerHTTP, MCPServerSSE, MCPServerStdio

        spec = resource.spec
        tool_type = str(spec.get("type", ""))
        if tool_type == "mcp-stdio":
            command = spec.get("command")
            if not command or not isinstance(command, str):
                raise LoaderError(
                    f"Tool '{resource.name}' type=mcp-stdio requires spec.command"
                )
            env_raw = spec.get("env") or {}
            env = {str(k): str(v) for k, v in env_raw.items()} if env_raw else None
            return MCPServerStdio(
                command=command,
                args=[str(a) for a in (spec.get("args") or [])],
                env=env,
            )
        if tool_type == "mcp-http":
            url = spec.get("url")
            if not url or not isinstance(url, str):
                raise LoaderError(
                    f"Tool '{resource.name}' type=mcp-http requires spec.url"
                )
            url_err = check_url_ssrf(url)
            if url_err:
                raise LoaderError(f"Tool '{resource.name}': {url_err}")
            config = spec.get("config") if isinstance(spec.get("config"), dict) else {}
            headers_raw = config.get("headers") if config else None
            headers = None
            if isinstance(headers_raw, dict):
                headers = {str(k): str(v) for k, v in headers_raw.items()}
            transport = str(config.get("transport", "http")).lower() if config else "http"
            if transport == "sse" or url.rstrip("/").endswith("/sse"):
                return MCPServerSSE(url=url, headers=headers)
            streamable = True
            if config and "streamable" in config:
                streamable = bool(config["streamable"])
            return MCPServerHTTP(url=url, headers=headers, streamable=streamable)
        raise LoaderError(
            f"Tool '{resource.name}': not an MCP type ({tool_type!r})"
        )

    def _build_agent_tools(
        self,
        tool_refs: list[str],
        policy: AgentPolicy,
        agent_name: str,
    ) -> tuple[list[Any], list[Any]]:
        """Load tools and MCP server configs; enforce sandbox on non-MCP tools.

        Returns:
            ``(tools, mcps)`` for the Agent constructor.
        """
        policy_min = policy.minimum_sandbox_tier
        tools: list[Any] = []
        mcps: list[Any] = []
        for ref in tool_refs:
            try:
                tool_resource = self._resolve_ref(ref)
            except LoaderError:
                continue
            if tool_resource.kind != ResourceKind.TOOL:
                continue
            tool_spec = tool_resource.spec
            tool_type = str(tool_spec.get("type", "python"))

            if tool_type in ("mcp-stdio", "mcp-http"):
                mcp = self._build_mcp_server(tool_resource)
                # Policy filter by resource name for allow/deny lists
                if policy.tool_mode == "denylist" and tool_resource.name in policy.denied_tools:
                    logger.warning(
                        "Policy denied MCP tool '%s' for agent '%s'",
                        tool_resource.name,
                        agent_name,
                        extra={
                            "event": "policy_tool_denied",
                            "tool_name": tool_resource.name,
                            "agent_name": agent_name,
                            "policy_mode": "denylist",
                        },
                    )
                    continue
                if (
                    policy.tool_mode == "allowlist"
                    and tool_resource.name not in policy.allowed_tools
                ):
                    logger.warning(
                        "Policy allowlist excludes MCP tool '%s' for agent '%s'",
                        tool_resource.name,
                        agent_name,
                        extra={
                            "event": "policy_tool_excluded",
                            "tool_name": tool_resource.name,
                            "agent_name": agent_name,
                            "allowed_tools": sorted(policy.allowed_tools),
                        },
                    )
                    continue
                mcps.append(mcp)
                logger.info(
                    "MCP server attached: agent=%s tool=%s type=%s",
                    agent_name,
                    tool_resource.name,
                    tool_type,
                    extra={
                        "event": "mcp_server_attached",
                        "agent_name": agent_name,
                        "tool_name": tool_resource.name,
                        "tool_type": tool_type,
                    },
                )
                continue

            tool = self.build_tool(ref)
            if tool is None:
                continue
            tool_tier = str(tool_spec.get("sandbox", "none") or "none")
            selected = select_sandbox(tool_tier=tool_tier, policy_minimum=policy_min)
            effective = runtime_tier_for_tool(selected, tool_type)
            logger.info(
                "Sandbox tier selected: agent=%s tool=%s effective=%s "
                "(tool_tier=%s policy_min=%s)",
                agent_name,
                tool_resource.name,
                effective,
                tool_tier,
                policy_min,
                extra={
                    "event": "sandbox_tier_selected",
                    "agent_name": agent_name,
                    "tool_name": tool_resource.name,
                    "effective_tier": effective,
                    "tool_tier": tool_tier,
                    "policy_minimum": policy_min,
                },
            )
            try:
                tool = enforce_tool_sandbox(
                    tool,
                    tier=effective,
                    tool_type=tool_type,
                    tool_name=tool_resource.name,
                    spec=tool_spec,
                )
            except SandboxExecutionError as exc:
                raise LoaderError(
                    f"Agent '{agent_name}': cannot enforce sandbox tier "
                    f"'{effective}' for tool '{tool_resource.name}': {exc}"
                ) from exc
            tools.append(tool)
        return tools, mcps

    def _filter_tools_by_policy(
        self,
        tools: list[Any],
        policy: AgentPolicy,
        agent_name: str,
    ) -> list[Any]:
        """Filter tools according to the agent's policy allowlist/denylist.

        - mode='allowlist': only tools whose name is in ``policy.allowed_tools`` pass.
        - mode='denylist': tools whose name is in ``policy.denied_tools`` are removed.
        - mode='all' (default): all tools pass through unchanged.
        """
        if policy.tool_mode == "all":
            return tools

        filtered: list[Any] = []
        for tool in tools:
            tool_name = getattr(tool, "name", str(tool))
            if policy.tool_mode == "denylist" and tool_name in policy.denied_tools:
                logger.warning(
                    "Policy denied tool '%s' for agent '%s'",
                    tool_name,
                    agent_name,
                    extra={
                        "event": "policy_tool_denied",
                        "tool_name": tool_name,
                        "agent_name": agent_name,
                        "policy_mode": "denylist",
                    },
                )
                continue
            if policy.tool_mode == "allowlist" and tool_name not in policy.allowed_tools:
                logger.warning(
                    "Policy allowlist excludes tool '%s' for agent '%s'",
                    tool_name,
                    agent_name,
                    extra={
                        "event": "policy_tool_excluded",
                        "tool_name": tool_name,
                        "agent_name": agent_name,
                        "allowed_tools": sorted(policy.allowed_tools),
                    },
                )
                continue
            filtered.append(tool)
        return filtered

    def build_agent(self, ref_or_name: str) -> Agent:
        """Build a CrewAI Agent from an Agent resource ref."""
        if ref_or_name in self._agent_cache:
            return self._agent_cache[ref_or_name]

        resource = self._resolve_ref(ref_or_name)
        if resource.kind != ResourceKind.AGENT:
            raise LoaderError(f"Expected Agent, got {resource.kind.value}")

        spec = resource.spec
        agent_kwargs: dict[str, Any] = {
            "role": spec["role"],
            "goal": spec["goal"],
            "backstory": spec["backstory"],
            "verbose": spec.get("verbose", True),
            "allow_delegation": spec.get("allow_delegation", False),
        }

        llm_ref = spec.get("llm")
        if llm_ref:
            agent_kwargs["llm"] = self.build_llm(llm_ref)

        tool_refs = spec.get("tools", [])
        # Always resolve policy (defaults when none configured) so sandbox
        # selection and optional tool filtering share one resolution path.
        policy = resolve_policy(spec, policies=self._policies)
        if tool_refs:
            tools, mcps = self._build_agent_tools(tool_refs, policy, resource.name)
            if tools:
                agent_kwargs["tools"] = tools
            if mcps:
                agent_kwargs["mcps"] = mcps

        # --- Policy enforcement ---
        if self._policies:
            if "tools" in agent_kwargs:
                agent_kwargs["tools"] = self._filter_tools_by_policy(
                    agent_kwargs["tools"], policy, resource.name
                )
                if not agent_kwargs["tools"]:
                    del agent_kwargs["tools"]
            if policy.delegation_allowed is not None and not policy.delegation_allowed:
                if agent_kwargs.get("allow_delegation"):
                    logger.info(
                        "Policy overrides delegation for agent '%s': "
                        "allow_delegation forced to False",
                        resource.name,
                        extra={
                            "event": "policy_delegation_override",
                            "agent_name": resource.name,
                        },
                    )
                agent_kwargs["allow_delegation"] = False
            # Log delegation targets constraint (informational — CrewAI does
            # not support restricting *which* agents can be delegated to,
            # so we can only log when targets are configured).
            if policy.delegation_targets:
                logger.info(
                    "Agent '%s' policy specifies delegation targets %s — "
                    "note: target restriction is advisory only (CrewAI limitation)",
                    resource.name,
                    policy.delegation_targets,
                    extra={
                        "event": "policy_delegation_targets",
                        "agent_name": resource.name,
                        "delegation_targets": policy.delegation_targets,
                    },
                )

        for key in ("max_iter", "max_rpm", "cache"):
            if key in spec:
                agent_kwargs[key] = spec[key]

        memory_spec = spec.get("memory")
        if isinstance(memory_spec, bool):
            agent_kwargs["memory"] = memory_spec
        elif isinstance(memory_spec, dict):
            if memory_spec.get("enabled", True):
                from crewai.memory.unified_memory import MemoryConfig  # type: ignore[attr-defined]

                cfg_kwargs = {}
                for key in ("recency_weight", "semantic_weight", "importance_weight"):
                    if key in memory_spec:
                        cfg_kwargs[key] = memory_spec[key]
                agent_kwargs["memory"] = MemoryConfig(**cfg_kwargs) if cfg_kwargs else True
            else:
                agent_kwargs["memory"] = False

        skills = spec.get("skills", [])
        if skills:
            agent_kwargs["skills"] = skills

        ks_refs = spec.get("knowledge_sources", [])
        if ks_refs:
            knowledge = [
                ks for ref in ks_refs if (ks := self._build_knowledge_source(ref)) is not None
            ]
            failed_count = len(ks_refs) - len(knowledge)
            if failed_count > 0:
                logger.warning(
                    "Agent '%s': %d/%d knowledge sources failed to load",
                    resource.name,
                    failed_count,
                    len(ks_refs),
                    extra={
                        "event": "knowledge_sources_partial",
                        "agent_name": resource.name,
                        "total_sources": len(ks_refs),
                        "failed_sources": failed_count,
                    },
                )
            if knowledge:
                agent_kwargs["knowledge_sources"] = knowledge

        agent = Agent(**agent_kwargs)
        self._agent_cache[ref_or_name] = agent
        logger.info(
            "Agent built: %s tools=%d llm=%s",
            resource.name,
            len(agent_kwargs.get("tools", [])),
            bool(llm_ref),
            extra={
                "event": "agent_built",
                "agent_name": resource.name,
                "tool_count": len(agent_kwargs.get("tools", [])),
                "has_llm": bool(llm_ref),
                "has_memory": bool(agent_kwargs.get("memory")),
            },
        )
        return agent

    @staticmethod
    def import_callable(dotted_path: str) -> Any | None:
        """Import a callable by dotted Python path (e.g. 'mymodule.my_func').

        Enforces a module allowlist to prevent arbitrary code execution via
        dynamic imports from task guardrails or output_pydantic fields.
        """
        if "." not in dotted_path:
            logger.warning(
                "Invalid callable path (no module separator): '%s' — skipping",
                dotted_path,
                extra={"event": "callable_import_invalid_path", "dotted_path": dotted_path},
            )
            return None
        path_error = check_callable_path(dotted_path)
        if path_error:
            msg = f"Blocked import: {dotted_path} — {path_error}"
            logger.warning(
                msg,
                extra={"event": "callable_import_blocked", "dotted_path": dotted_path},
            )
            raise LoaderError(msg)
        module_path, attr_name = dotted_path.rsplit(".", 1)
        if attr_name.startswith("_"):
            msg = f"Blocked import of private/dunder attribute: {dotted_path}"
            logger.warning(
                msg,
                extra={"event": "callable_import_blocked", "dotted_path": dotted_path},
            )
            raise LoaderError(msg)
        try:
            module = importlib.import_module(module_path)
            return getattr(module, attr_name)
        except (ImportError, AttributeError):
            logger.error(
                "Failed to import callable: %s — guardrail/output_pydantic will be skipped",
                dotted_path,
                exc_info=True,
                extra={"event": "callable_import_failed", "dotted_path": dotted_path},
            )
            return None

    @staticmethod
    def _build_schema_guardrail(schema: dict[str, Any], guardrail_name: str) -> Any:
        """Build a callable guardrail that validates output against a JSON Schema.

        The returned function accepts the agent output string, parses it as JSON,
        and validates it against ``schema``.  Returns the output unchanged on
        success; raises ``ValueError`` on validation failure.
        """
        validator = jsonschema.Draft7Validator(schema)

        def _schema_guardrail(output: str) -> str:
            try:
                parsed = json.loads(output)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Schema guardrail '{guardrail_name}': output is not valid JSON: {exc}"
                ) from exc
            errors = list(validator.iter_errors(parsed))
            if errors:
                raise ValueError(f"Schema guardrail '{guardrail_name}': {errors[0].message}")
            return output

        return _schema_guardrail

    @staticmethod
    def _build_hallucination_guardrail(
        gspec: dict[str, Any],
        guardrail_name: str,
    ) -> str:
        """Build an LLM prompt guardrail for hallucination detection.

        Translates the hallucination config into a prompt string that
        CrewAI will evaluate as an LLM guardrail.
        """
        check_type = gspec.get("hallucination_check", "factual_consistency")
        threshold = gspec.get("hallucination_threshold", 0.7)
        llm_ref = gspec.get("llm")

        prompts = {
            "factual_consistency": (
                "Verify the output contains only factual claims that are "
                "directly supported by the input context. Flag any claims "
                "that are fabricated or cannot be traced back to provided data."
            ),
            "source_grounding": (
                "Check that every assertion in the output is grounded in "
                "the source material. Reject outputs that introduce information "
                "not present in the original sources."
            ),
            "self_contradiction": (
                "Analyze the output for internal contradictions. Identify "
                "any statements that conflict with each other within the "
                "same response."
            ),
        }

        base_prompt = prompts.get(check_type, prompts["factual_consistency"])
        prompt = (
            f"[Hallucination guardrail: {guardrail_name}] "
            f"{base_prompt} "
            f"Confidence threshold: {threshold}. "
            f"Return PASS if the output meets the threshold, FAIL otherwise."
        )

        if llm_ref:
            logger.info(
                "Hallucination guardrail '%s' specifies llm=%s (advisory, "
                "CrewAI uses the task agent's LLM for guardrail evaluation)",
                guardrail_name,
                llm_ref,
                extra={
                    "event": "hallucination_guardrail_llm_advisory",
                    "guardrail_name": guardrail_name,
                    "llm_ref": llm_ref,
                },
            )

        return prompt

    def _build_composite_guardrail(
        self,
        gspec: dict[str, Any],
        guardrail_name: str,
    ) -> Any:
        """Build a composite guardrail that combines multiple child guardrails.

        For "and" operator: all child guardrails must pass. With short_circuit
        enabled (default), evaluation stops on first failure.
        For "or" operator: at least one child guardrail must pass. With
        short_circuit enabled, evaluation stops on first success.

        Child guardrails that resolve to strings (LLM prompts) are joined into
        a combined prompt. Child guardrails that resolve to callables are
        wrapped in a function that applies the operator logic.
        """
        operator = gspec.get("operator", "and")
        child_refs = gspec.get("guardrails", [])
        short_circuit = gspec.get("short_circuit", True)

        if len(child_refs) < 2:
            logger.warning(
                "Composite guardrail '%s' needs at least 2 child guardrails, got %d",
                guardrail_name,
                len(child_refs),
                extra={
                    "event": "composite_guardrail_insufficient_children",
                    "guardrail_name": guardrail_name,
                    "child_count": len(child_refs),
                },
            )
            return None

        children = self._build_guardrails(child_refs)
        if not children:
            logger.warning(
                "Composite guardrail '%s': no child guardrails resolved successfully",
                guardrail_name,
                extra={
                    "event": "composite_guardrail_no_children",
                    "guardrail_name": guardrail_name,
                },
            )
            return None

        # If all children are strings (LLM prompts), combine into a single prompt
        if all(isinstance(c, str) for c in children):
            if operator == "and":
                header = (
                    f"[Composite guardrail '{guardrail_name}': ALL of the "
                    f"following checks must pass]\n\n"
                )
                return header + "\n\n".join(
                    f"Check {i + 1}: {c}" for i, c in enumerate(children)
                )
            else:
                header = (
                    f"[Composite guardrail '{guardrail_name}': ANY ONE of the "
                    f"following checks must pass]\n\n"
                )
                return header + "\n\n".join(
                    f"Check {i + 1}: {c}" for i, c in enumerate(children)
                )

        # Mixed or all-callable children: wrap in a function
        def _composite_guardrail(output: str) -> str:
            errors: list[str] = []
            for child in children:
                if isinstance(child, str):
                    # String guardrails cannot be evaluated as functions,
                    # skip them in callable mode (they are advisory)
                    continue
                try:
                    child(output)
                    if operator == "or" and short_circuit:
                        return output
                except (ValueError, Exception) as exc:
                    if operator == "and" and short_circuit:
                        raise
                    errors.append(str(exc))

            if operator == "and" and errors:
                raise ValueError(
                    f"Composite guardrail '{guardrail_name}' failed: "
                    + "; ".join(errors)
                )
            if operator == "or" and errors and len(errors) >= len(
                [c for c in children if not isinstance(c, str)]
            ):
                raise ValueError(
                    f"Composite guardrail '{guardrail_name}': all checks failed: "
                    + "; ".join(errors)
                )
            return output

        return _composite_guardrail

    def _get_project_guardrails(self, project: str) -> list[str]:
        """Return guardrail refs from the project resource, if any."""
        ns_resource = self._resources.get(f"Project/{project}")
        if ns_resource is None:
            return []
        return list(ns_resource.spec.get("guardrails", []))

    def _build_guardrails(self, refs: list[str]) -> list[Any]:
        """Build guardrail callables from refs or inline strings.

        Each item can be:
        - ref:guardrails/<name> → loads Guardrail resource, resolves function_path or llm_prompt
        - dotted.python.path → imports as callable
        - free-text string → returned as-is (CrewAI treats strings as LLM guardrails)
        """
        result: list[Any] = []
        for ref_str in refs:
            if ref_str.startswith("ref:"):
                try:
                    resource = self._resolve_ref(ref_str)
                    gspec = resource.spec
                    if gspec.get("type") == "function" and gspec.get("function_path"):
                        fn = self.import_callable(gspec["function_path"])
                        if fn:
                            result.append(fn)
                    elif gspec.get("type") == "llm" and gspec.get("llm_prompt"):
                        result.append(gspec["llm_prompt"])
                    elif gspec.get("type") == "schema" and gspec.get("json_schema"):
                        guardrail_fn = self._build_schema_guardrail(
                            gspec["json_schema"], resource.name
                        )
                        result.append(guardrail_fn)
                    elif gspec.get("type") == "hallucination":
                        prompt = self._build_hallucination_guardrail(gspec, resource.name)
                        result.append(prompt)
                    elif gspec.get("type") == "composite":
                        composite = self._build_composite_guardrail(gspec, resource.name)
                        if composite is not None:
                            result.append(composite)
                except LoaderError:
                    logger.warning(
                        "Failed to resolve guardrail ref: %s",
                        ref_str,
                        exc_info=True,
                        extra={
                            "event": "guardrail_ref_failed",
                            "ref": ref_str,
                        },
                    )
            elif "." in ref_str and " " not in ref_str:
                fn = self.import_callable(ref_str)
                if fn:
                    result.append(fn)
            else:
                result.append(ref_str)
        return result

    def build_task(self, ref_or_name: str) -> Task:
        """Build a CrewAI Task from a Task resource ref."""
        if ref_or_name in self._task_cache:
            return self._task_cache[ref_or_name]

        resource = self._resolve_ref(ref_or_name)
        if resource.kind != ResourceKind.TASK:
            raise LoaderError(f"Expected Task, got {resource.kind.value}")

        spec = resource.spec
        task_kwargs: dict[str, Any] = {
            "description": spec["description"],
            "expected_output": spec["expected_output"],
        }

        agent_ref = spec.get("agent")
        if agent_ref:
            task_kwargs["agent"] = self.build_agent(agent_ref)

        context_refs = spec.get("context", [])
        if context_refs:
            task_kwargs["context"] = [self.build_task(ref) for ref in context_refs]

        for key in ("async_execution", "human_input"):
            if key in spec:
                task_kwargs[key] = spec[key]
        if "output_file" in spec:
            output_file = spec["output_file"]
            if not _SAFE_FILENAME.match(output_file) or len(output_file) > 255:
                raise LoaderError(f"output_file must be a plain filename, got '{output_file}'")
            task_kwargs["output_file"] = output_file

        if spec.get("output_pydantic"):
            pydantic_cls = self.import_callable(spec["output_pydantic"])
            if pydantic_cls:
                task_kwargs["output_pydantic"] = pydantic_cls
        elif spec.get("output_json"):
            task_kwargs["output_json"] = spec["output_json"]

        guardrail_refs = list(spec.get("guardrails", []))
        if self._crew_guardrail_refs:
            guardrail_refs = list(self._crew_guardrail_refs) + guardrail_refs
        ns_guardrails = self._get_project_guardrails(resource.project)
        if ns_guardrails:
            guardrail_refs = ns_guardrails + guardrail_refs
        if guardrail_refs:
            guardrails = self._build_guardrails(guardrail_refs)
            if guardrails:
                task_kwargs["guardrail"] = guardrails

        task = Task(**task_kwargs)
        self._task_cache[ref_or_name] = task
        return task

    def _build_discovery_tools(self, project: str) -> list[Any]:
        """Build the JIT discovery meta-tools for the given project (cached per loader)."""
        cached = self._discovery_tools_cache.get(project)
        if cached is not None:
            return cached

        from blackbeard.engine.discovery_tools import GetToolTool, SearchToolsTool

        api_key = settings.blackbeard_api_key.get_secret_value()
        tools = [
            SearchToolsTool(
                api_url=_self_api_url(),
                api_key=api_key,
                project=project,
            ),
            GetToolTool(
                api_url=_self_api_url(),
                api_key=api_key,
                project=project,
            ),
        ]
        self._discovery_tools_cache[project] = tools
        return tools

    def _inject_discovery_tools(
        self,
        agent: Agent,
        agent_resource: Resource,
        tool_loading: str,
        project: str,
    ) -> None:
        """Inject discovery meta-tools into an agent if the crew/agent config allows it."""
        if tool_loading not in ("jit", "hybrid"):
            return

        agent_spec = agent_resource.spec
        if not agent_spec.get("tool_discovery", True):
            return

        discovery_tools = self._build_discovery_tools(project)
        existing = agent.tools or []
        agent.tools = list(existing) + discovery_tools
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "Injected discovery tools into agent '%s'",
                agent_resource.name,
                extra={
                    "event": "discovery_tools_injected",
                    "agent_name": agent_resource.name,
                    "tool_loading": tool_loading,
                },
            )

    def _build_muninndb_backend(
        self,
        memory_spec: dict[str, Any],
        project: str,
    ) -> Any:
        """Build a MuninnDB memory backend from crew memory configuration.

        The returned backend is stored on the Crew kwargs for use by the
        executor or downstream hooks.  It is not passed to the Crew
        constructor directly because CrewAI does not support pluggable
        memory backends.

        Args:
            memory_spec: The ``memory`` dict from the Crew spec.
            project: Blackbeard resource project.

        Returns:
            A :class:`MuninnMemoryBackend` instance.

        Raises:
            LoaderError: If the ``muninn-python`` package is not installed.
        """
        import os

        from blackbeard.engine.memory.muninn import MuninnMemoryBackend

        url = memory_spec.get("muninndb_url", settings.muninndb_url)
        if url != settings.muninndb_url:
            ssrf_error = check_url_ssrf(url)
            if ssrf_error:
                raise LoaderError(f"muninndb_url blocked: {ssrf_error}")
        vault = memory_spec.get("muninndb_vault", project)
        token: str | None = None
        token_env = memory_spec.get("muninndb_token_env")
        if token_env:
            if is_blocked_env_name(token_env):
                raise LoaderError(
                    f"muninndb_token_env '{token_env}' references a blocked environment variable"
                )
            token = os.environ.get(token_env)

        try:
            backend = MuninnMemoryBackend(
                url=url,
                project=project,
                vault=vault,
                token=token,
            )
        except ImportError as exc:
            raise LoaderError(
                "Crew memory provider is 'muninndb' but the muninn-python "
                "package is not installed. Install it with: uv add muninn-python"
            ) from exc

        logger.info(
            "MuninnDB memory backend configured: vault=%s url=%s",
            vault,
            url,
            extra={
                "event": "muninndb_backend_built",
                "vault": vault,
                "url": url,
                "project": project,
            },
        )
        return backend

    def build_crew(self, crew_name: str) -> Crew:
        """Build a complete CrewAI Crew from a Crew resource.

        This is the main entry point — resolves all agents, tasks, and their
        dependencies recursively.
        """
        t0 = time.monotonic()
        crew_key = f"Crew/{crew_name}"
        resource = self._resources.get(crew_key)
        if resource is None:
            raise LoaderError(f"Crew '{crew_name}' not found")

        spec = resource.spec
        tool_loading = spec.get("tool_loading", "hybrid")

        agent_refs = spec.get("agents", [])
        agents: list[Agent] = []
        for ref_str in agent_refs:
            agent = self.build_agent(ref_str)
            agents.append(agent)
            ref = parse_ref(ref_str)
            if ref:
                agent_resource = self._resources.get(f"{ref.kind.value}/{ref.name}")
                if agent_resource:
                    self._inject_discovery_tools(
                        agent, agent_resource, tool_loading, resource.project
                    )

        # Set crew-level guardrails so build_task() can prepend them
        self._crew_guardrail_refs = list(spec.get("guardrails", []))

        task_refs = spec.get("tasks", [])
        tasks = [self.build_task(ref) for ref in task_refs]

        # Clear crew guardrails after tasks are built
        self._crew_guardrail_refs = []

        process_str = spec.get("process", "sequential")
        process = _PROCESS_MAP.get(process_str, Process.sequential)

        crew_kwargs: dict[str, Any] = {
            "agents": agents,
            "tasks": tasks,
            "process": process,
            "verbose": spec.get("verbose", True),
        }

        for key in ("cache", "max_rpm"):
            if key in spec:
                crew_kwargs[key] = spec[key]

        # Memory + RAG provider config
        memory_spec = spec.get("memory")
        if isinstance(memory_spec, bool):
            crew_kwargs["memory"] = memory_spec
        elif isinstance(memory_spec, dict):
            crew_kwargs["memory"] = memory_spec.get("enabled", True)
            provider = memory_spec.get("provider")
            if provider == "muninndb":
                crew_kwargs["_muninndb_backend"] = self._build_muninndb_backend(
                    memory_spec, resource.project
                )

        embedder_spec = spec.get("embedder")
        if embedder_spec:
            crew_kwargs["embedder"] = embedder_spec

        # Manager LLM for hierarchical process
        manager_llm_ref = spec.get("manager_llm")
        if manager_llm_ref:
            crew_kwargs["manager_llm"] = self.build_llm(manager_llm_ref)

        # Manager agent for hierarchical process
        manager_agent_ref = spec.get("manager_agent")
        if manager_agent_ref:
            crew_kwargs["manager_agent"] = self.build_agent(manager_agent_ref)

        # Validate hierarchical process has a manager configured
        if (
            process is Process.hierarchical
            and "manager_llm" not in crew_kwargs
            and "manager_agent" not in crew_kwargs
        ):
            raise LoaderError(
                f"Crew '{crew_name}' uses hierarchical process but has neither "
                f"'manager_llm' nor 'manager_agent' configured"
            )

        crew = Crew(**crew_kwargs)
        build_ms = round((time.monotonic() - t0) * 1000, 1)
        logger.info(
            "Crew built: %s agents=%d tasks=%d tools=%d skipped=%d process=%s (%.0fms)",
            crew_name,
            len(agents),
            len(tasks),
            self._tools_loaded,
            self._tools_skipped,
            process_str,
            build_ms,
            extra={
                "event": "crew_built",
                "crew_name": crew_name,
                "agent_count": len(agents),
                "task_count": len(tasks),
                "tools_loaded": self._tools_loaded,
                "tools_skipped": self._tools_skipped,
                "crew_process": process_str,
                "build_ms": build_ms,
            },
        )
        return crew
