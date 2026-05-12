"""Resource Loader: converts stored resources into CrewAI objects.

Resolves refs, builds CrewAI Agent/Task/Crew instances, and wires
LLM connections through LiteLLM Proxy.
"""

from __future__ import annotations

import logging
from typing import Any

from crewai import Agent, Crew, LLM, Process, Task

from blackbeard.config import settings
from blackbeard.kinds import ResourceKind
from blackbeard.litellm.helpers import build_model_string
from blackbeard.models.resource import Resource
from blackbeard.resources.refs import parse_ref

logger = logging.getLogger(__name__)


class LoaderError(Exception):
    """Raised when resource loading fails."""


class ResourceLoader:
    """Loads resources from the database and builds CrewAI objects."""

    def __init__(self, resources: dict[str, Resource]):
        """Initialize with a dict of resources keyed by 'Kind/name'.

        Example: {"Agent/researcher": <Resource>, "Task/research-topic": <Resource>}
        """
        self._resources = resources
        self._llm_cache: dict[str, LLM] = {}
        self._agent_cache: dict[str, Agent] = {}
        self._task_cache: dict[str, Task] = {}

    def _resolve_ref(self, ref_str: str) -> Resource:
        """Resolve a ref string to a Resource object."""
        ref = parse_ref(ref_str)
        if ref is None:
            raise LoaderError(f"'{ref_str}' is not a valid ref")
        key = f"{ref.kind.value}/{ref.name}"
        resource = self._resources.get(key)
        if resource is None:
            raise LoaderError(f"Referenced resource '{key}' not found")
        return resource

    def build_llm(self, ref_or_name: str) -> LLM:
        """Build a CrewAI LLM from an LLMConnection resource ref."""
        if ref_or_name in self._llm_cache:
            return self._llm_cache[ref_or_name]

        resource = self._resolve_ref(ref_or_name)
        if resource.kind != ResourceKind.LLM_CONNECTION:
            raise LoaderError(f"Expected LLMConnection, got {resource.kind.value}")

        spec = resource.spec
        provider = spec.get("provider", "")
        model = spec.get("model", "")
        params = spec.get("parameters", {})
        vertex = spec.get("vertex", {})

        # Build the model string for LiteLLM
        model_str = build_model_string(provider, model)

        # Build LLM kwargs
        llm_kwargs: dict[str, Any] = {
            "model": model_str,
            "api_base": settings.litellm_proxy_url,
            "api_key": settings.litellm_master_key,
        }

        # Add parameters
        if "temperature" in params:
            llm_kwargs["temperature"] = params["temperature"]
        if "max_tokens" in params:
            llm_kwargs["max_tokens"] = params["max_tokens"]
        if "top_p" in params:
            llm_kwargs["top_p"] = params["top_p"]

        # Vertex AI specific
        if vertex:
            project = vertex.get("project") or settings.google_cloud_project
            location = vertex.get("location") or settings.cloud_ml_region
            if project:
                llm_kwargs["vertex_project"] = project
            if location:
                llm_kwargs["vertex_location"] = location

        llm = LLM(**llm_kwargs)
        self._llm_cache[ref_or_name] = llm
        return llm

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

        # Resolve LLM
        llm_ref = spec.get("llm")
        if llm_ref:
            agent_kwargs["llm"] = self.build_llm(llm_ref)

        # Log warning for declared tools (tool loading requires runtime integration)
        tool_refs = spec.get("tools", [])
        if tool_refs:
            logger.warning(
                f"Agent '{resource.name}' declares tools {tool_refs} — "
                f"tool loading from refs is not yet wired into CrewAI runtime. "
                f"Tools must be registered directly via CrewAI's tool system."
            )

        # Optional params
        if "max_iter" in spec:
            agent_kwargs["max_iter"] = spec["max_iter"]
        if "max_rpm" in spec:
            agent_kwargs["max_rpm"] = spec["max_rpm"]
        if "memory" in spec:
            agent_kwargs["memory"] = spec["memory"]
        if "cache" in spec:
            agent_kwargs["cache"] = spec["cache"]

        agent = Agent(**agent_kwargs)
        self._agent_cache[ref_or_name] = agent
        return agent

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

        # Resolve agent
        agent_ref = spec.get("agent")
        if agent_ref:
            task_kwargs["agent"] = self.build_agent(agent_ref)

        # Resolve context tasks
        context_refs = spec.get("context", [])
        if context_refs:
            context_tasks = []
            for ctx_ref in context_refs:
                context_tasks.append(self.build_task(ctx_ref))
            task_kwargs["context"] = context_tasks

        # Optional params
        if "async_execution" in spec:
            task_kwargs["async_execution"] = spec["async_execution"]
        if "human_input" in spec:
            task_kwargs["human_input"] = spec["human_input"]
        if "output_file" in spec:
            task_kwargs["output_file"] = spec["output_file"]

        task = Task(**task_kwargs)
        self._task_cache[ref_or_name] = task
        return task

    def build_crew(self, crew_name: str) -> Crew:
        """Build a complete CrewAI Crew from a Crew resource.

        This is the main entry point — resolves all agents, tasks, and their
        dependencies recursively.
        """
        key = f"Crew/{crew_name}"
        resource = self._resources.get(key)
        if resource is None:
            raise LoaderError(f"Crew '{crew_name}' not found")

        spec = resource.spec

        # Build agents
        agent_refs = spec.get("agents", [])
        agents = [self.build_agent(ref) for ref in agent_refs]

        # Build tasks
        task_refs = spec.get("tasks", [])
        tasks = [self.build_task(ref) for ref in task_refs]

        # Process type
        process_str = spec.get("process", "sequential")
        process = Process.sequential if process_str == "sequential" else Process.hierarchical

        crew_kwargs: dict[str, Any] = {
            "agents": agents,
            "tasks": tasks,
            "process": process,
            "verbose": spec.get("verbose", True),
        }

        # Optional params
        if "memory" in spec:
            crew_kwargs["memory"] = spec["memory"]
        if "cache" in spec:
            crew_kwargs["cache"] = spec["cache"]
        if "max_rpm" in spec:
            crew_kwargs["max_rpm"] = spec["max_rpm"]

        # Manager LLM for hierarchical process
        manager_llm_ref = spec.get("manager_llm")
        if manager_llm_ref:
            crew_kwargs["manager_llm"] = self.build_llm(manager_llm_ref)

        return Crew(**crew_kwargs)
