"""Resource Loader: converts stored resources into CrewAI objects.

Resolves refs, builds CrewAI Agent/Task/Crew instances, and wires
LLM connections through LiteLLM Proxy.
"""

from __future__ import annotations

import importlib
import json
import logging
import re
import time
from typing import TYPE_CHECKING, Any

__all__ = [
    "LoaderError",
    "ResourceLoader",
]

from crewai import LLM, Agent, Crew, Process, Task

from blackbeard.config import settings
from blackbeard.engine.policy import AgentPolicy, resolve_policy
from blackbeard.kinds import ResourceKind
from blackbeard.litellm import apply_model_params, apply_vertex_params
from blackbeard.resources import ALLOWED_TOOL_MODULE_PREFIXES, BLOCKED_TOOL_SUBMODULES, parse_ref

if TYPE_CHECKING:
    from blackbeard.models import Resource

logger = logging.getLogger(__name__)

_SAFE_FILENAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
_PATH_TRAVERSAL_INDICATORS = ("..", "~", "\\", "\x00")
_SENSITIVE_PATH_PREFIXES = ("/etc/", "/proc/", "/sys/", "/dev/", "/var/run/")

_SAFE_BUILTIN_NAME = re.compile(r"^[A-Z][a-zA-Z0-9]+$")

_BLOCKED_BUILTIN_NAMES = frozenset(
    {
        "CodeInterpreterTool",
        "CodeDocsSearchTool",
    }
)


def _self_api_url() -> str:
    """Resolve at call time so the module can be imported without reading settings."""
    return f"http://localhost:{settings.port}"


def _check_path_safety(path: str, context: str) -> None:
    """Raise LoaderError if path contains traversal characters or targets sensitive directories."""
    if any(ind in path for ind in _PATH_TRAVERSAL_INDICATORS):
        raise LoaderError(f"{context}: path traversal characters not allowed")
    if path.startswith(_SENSITIVE_PATH_PREFIXES):
        raise LoaderError(f"{context}: access to '{path}' is not allowed")


_MAX_CONFIG_VALUE_LEN = 10_000


def _validate_tool_config(config: dict[str, Any], tool_name: str) -> None:
    """Reject tool config values containing path traversal, sensitive paths, or excessive size."""
    for key, val in config.items():
        if not isinstance(val, str):
            continue
        if len(val) > _MAX_CONFIG_VALUE_LEN:
            raise LoaderError(
                f"Tool '{tool_name}' config.{key}: value too long "
                f"({len(val)} > {_MAX_CONFIG_VALUE_LEN})"
            )
        _check_path_safety(val, f"Tool '{tool_name}' config.{key}")


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
        """Build a CrewAI LLM from an LLMConnection resource ref."""
        if ref_or_name in self._llm_cache:
            return self._llm_cache[ref_or_name]

        resource = self._resolve_ref(ref_or_name)
        if resource.kind != ResourceKind.LLM_CONNECTION:
            raise LoaderError(f"Expected LLMConnection, got {resource.kind.value}")

        spec = resource.spec
        model = spec.get("model", "")
        params = spec.get("parameters", {})
        vertex = spec.get("vertex", {})

        # All LLM traffic routes through the LiteLLM proxy.
        # Use the per-execution virtual key when available, falling back
        # to the global master key.
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
        """Build a CrewAI knowledge source from a KnowledgeSource resource ref."""
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

            # Lazy-import map: type string → (module_path, class_name, kwargs)
            ks_types: dict[str, tuple[str, str, dict[str, Any]]] = {
                "text": (
                    "crewai.knowledge.source.text_file_knowledge_source",
                    "TextFileKnowledgeSource",
                    {"file_paths": file_paths},
                ),
                "pdf": (
                    "crewai.knowledge.source.pdf_knowledge_source",
                    "PDFKnowledgeSource",
                    {"file_paths": file_paths},
                ),
                "csv": (
                    "crewai.knowledge.source.csv_knowledge_source",
                    "CSVKnowledgeSource",
                    {"file_paths": file_paths},
                ),
                "json": (
                    "crewai.knowledge.source.json_knowledge_source",
                    "JSONKnowledgeSource",
                    {"file_paths": file_paths},
                ),
                "string": (
                    "crewai.knowledge.source.string_knowledge_source",
                    "StringKnowledgeSource",
                    {"content": content},
                ),
            }

            entry = ks_types.get(ks_type)
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

            module_path, class_name, kwargs = entry
            module = importlib.import_module(module_path)
            cls = getattr(module, class_name)
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

        Supports ``type: python`` (dynamic import via ``class_path``) and
        ``type: builtin`` (import from ``crewai_tools``).  Other types
        (``wasm``, ``mcp-stdio``, ``mcp-http``) log a warning and return
        ``None``.
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
                raise LoaderError(f"Tool '{resource.name}' has type=python but no class_path")
            if not class_path.startswith(ALLOWED_TOOL_MODULE_PREFIXES):
                raise LoaderError(
                    f"Tool '{resource.name}': class_path '{class_path}' is not in the "
                    f"allowed module list. Permitted prefixes: "
                    f"{', '.join(ALLOWED_TOOL_MODULE_PREFIXES)}"
                )
            module_path, class_name = class_path.rsplit(".", 1)
            for blocked in BLOCKED_TOOL_SUBMODULES:
                if module_path == blocked or module_path.startswith(blocked + "."):
                    raise LoaderError(
                        f"Tool '{resource.name}': class_path '{class_path}' references a "
                        f"blocked module that can execute arbitrary code"
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

        else:
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
        if tool_refs:
            tools = [t for ref in tool_refs if (t := self.build_tool(ref)) is not None]
            if tools:
                agent_kwargs["tools"] = tools

        # --- Policy enforcement ---
        # Resolve the effective policy for this agent and apply constraints
        # before the CrewAI Agent is constructed.
        if self._policies:
            policy = resolve_policy(spec, policies=self._policies)
            # Tool filtering: remove tools not permitted by policy
            if "tools" in agent_kwargs:
                agent_kwargs["tools"] = self._filter_tools_by_policy(
                    agent_kwargs["tools"], policy, resource.name
                )
                if not agent_kwargs["tools"]:
                    del agent_kwargs["tools"]
            # Delegation enforcement: policy can override allow_delegation
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
                from crewai.memory.unified_memory import MemoryConfig

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
    def _import_callable(dotted_path: str) -> Any | None:
        """Import a callable by dotted Python path (e.g. 'mymodule.my_func')."""
        if "." not in dotted_path:
            return None
        module_path, attr_name = dotted_path.rsplit(".", 1)
        try:
            module = importlib.import_module(module_path)
            return getattr(module, attr_name)
        except Exception:
            logger.warning("Failed to import callable: %s", dotted_path)
            return None

    @staticmethod
    def _build_schema_guardrail(schema: dict[str, Any], guardrail_name: str) -> Any:
        """Build a callable guardrail that validates output against a JSON Schema.

        The returned function accepts the agent output string, parses it as JSON,
        and validates it against ``schema``.  Returns the output unchanged on
        success; raises ``ValueError`` on validation failure.
        """
        import jsonschema

        def _schema_guardrail(output: str) -> str:
            try:
                parsed = json.loads(output)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Schema guardrail '{guardrail_name}': output is not valid JSON: {exc}"
                ) from exc
            try:
                jsonschema.validate(parsed, schema)
            except jsonschema.ValidationError as exc:
                raise ValueError(
                    f"Schema guardrail '{guardrail_name}': {exc.message}"
                ) from exc
            return output

        return _schema_guardrail

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
                        fn = self._import_callable(gspec["function_path"])
                        if fn:
                            result.append(fn)
                    elif gspec.get("type") == "llm" and gspec.get("llm_prompt"):
                        result.append(gspec["llm_prompt"])
                    elif gspec.get("type") == "schema" and gspec.get("json_schema"):
                        guardrail_fn = self._build_schema_guardrail(
                            gspec["json_schema"], resource.name
                        )
                        result.append(guardrail_fn)
                except LoaderError:
                    logger.warning("Failed to resolve guardrail ref: %s", ref_str)
            elif "." in ref_str and " " not in ref_str:
                fn = self._import_callable(ref_str)
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
            pydantic_cls = self._import_callable(spec["output_pydantic"])
            if pydantic_cls:
                task_kwargs["output_pydantic"] = pydantic_cls
        elif spec.get("output_json"):
            task_kwargs["output_json"] = spec["output_json"]

        guardrail_refs = spec.get("guardrails", [])
        if guardrail_refs:
            guardrails = self._build_guardrails(guardrail_refs)
            if guardrails:
                task_kwargs["guardrail"] = guardrails

        task = Task(**task_kwargs)
        self._task_cache[ref_or_name] = task
        return task

    def _build_discovery_tools(self, namespace: str) -> list[Any]:
        """Build the JIT discovery meta-tools for the given namespace (cached per loader)."""
        cached = self._discovery_tools_cache.get(namespace)
        if cached is not None:
            return cached

        from blackbeard.engine.discovery_tools import GetToolTool, SearchToolsTool

        api_key = settings.blackbeard_api_key.get_secret_value()
        tools = [
            SearchToolsTool(
                api_url=_self_api_url(),
                api_key=api_key,
                namespace=namespace,
            ),
            GetToolTool(
                api_url=_self_api_url(),
                api_key=api_key,
                namespace=namespace,
            ),
        ]
        self._discovery_tools_cache[namespace] = tools
        return tools

    def _inject_discovery_tools(
        self,
        agent: Agent,
        agent_resource: Resource,
        tool_loading: str,
        namespace: str,
    ) -> None:
        """Inject discovery meta-tools into an agent if the crew/agent config allows it."""
        if tool_loading not in ("jit", "hybrid"):
            return

        agent_spec = agent_resource.spec
        if not agent_spec.get("tool_discovery", True):
            return

        discovery_tools = self._build_discovery_tools(namespace)
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
        agents = [self.build_agent(ref) for ref in agent_refs]

        for ref_str, agent in zip(agent_refs, agents, strict=True):
            ref = parse_ref(ref_str)
            if ref:
                agent_resource = self._resources.get(f"{ref.kind.value}/{ref.name}")
                if agent_resource:
                    self._inject_discovery_tools(
                        agent, agent_resource, tool_loading, resource.namespace
                    )

        task_refs = spec.get("tasks", [])
        tasks = [self.build_task(ref) for ref in task_refs]

        process_str = spec.get("process", "sequential")
        process_map = {
            "sequential": Process.sequential,
            "hierarchical": Process.hierarchical,
        }
        process = process_map.get(process_str, Process.sequential)

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
