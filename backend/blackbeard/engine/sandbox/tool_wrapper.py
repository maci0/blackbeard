"""CrewAI tools that enforce sandbox isolation at call time."""

from __future__ import annotations

import json
import logging
import textwrap
from typing import Any

from crewai.tools import BaseTool
from pydantic import PrivateAttr

from blackbeard.engine.sandbox.runner import (
    SandboxExecutionError,
    ensure_sandbox_available,
    execute_sandboxed,
    runtime_tier_for_tool,
)

logger = logging.getLogger(__name__)

__all__ = [
    "SandboxExecutionError",
    "build_wasm_tool",
    "enforce_tool_sandbox",
    "ensure_sandbox_available",
    "runtime_tier_for_tool",
]


class PlaceholderTool(BaseTool):
    """Stand-in for command-only tools before sandbox wrapping."""

    name: str = "placeholder"
    description: str = "placeholder"

    def _run(self, **kwargs: Any) -> str:
        return "Tool is not configured for in-process execution"


class WasmCrewTool(BaseTool):
    """Invoke a WASM module via WasmSandbox."""

    name: str = "wasm_tool"
    description: str = "WASM tool"
    _wasm_path: str = PrivateAttr()

    def __init__(self, *, name: str, description: str, wasm_path: str, **data: Any) -> None:
        super().__init__(name=name, description=description, **data)
        self._wasm_path = wasm_path

    def _run(self, **kwargs: Any) -> str:
        from blackbeard.engine.sandbox.wasm_runtime import get_shared_sandbox

        try:
            result = get_shared_sandbox().invoke(self._wasm_path, kwargs if kwargs else {})
        except Exception as exc:
            logger.exception(
                "WASM tool failed: name=%s path=%s",
                self.name,
                self._wasm_path,
                extra={"event": "wasm_tool_failed", "tool_name": self.name},
            )
            return f"WASM tool error: {type(exc).__name__}: {exc}"
        if not result.success:
            return result.error or "WASM tool reported failure"
        return result.output


class SandboxedCommandTool(BaseTool):
    """Run a fixed command (plus optional args) inside a container/microvm sandbox."""

    name: str = "sandboxed_command"
    description: str = "Sandboxed command tool"
    _command: str = PrivateAttr()
    _args: list[str] = PrivateAttr(default_factory=list)
    _tier: str = PrivateAttr(default="docker")
    _env: dict[str, str] = PrivateAttr(default_factory=dict)
    _network: bool = PrivateAttr(default=False)
    _image: str | None = PrivateAttr(default=None)

    def __init__(
        self,
        *,
        name: str,
        description: str,
        command: str,
        args: list[str] | None = None,
        tier: str = "docker",
        env: dict[str, str] | None = None,
        network: bool = False,
        image: str | None = None,
        **data: Any,
    ) -> None:
        super().__init__(name=name, description=description, **data)
        self._command = command
        self._args = list(args or [])
        self._tier = tier
        self._env = dict(env or {})
        self._network = network
        self._image = image

    def _run(self, **kwargs: Any) -> str:
        cmd = [self._command, *self._args]
        payload = json.dumps(kwargs) if kwargs else None
        try:
            code, out, err = execute_sandboxed(
                self._tier,
                cmd,
                input_data=payload,
                env=self._env or None,
                network=self._network,
                image=self._image,
            )
        except SandboxExecutionError as exc:
            return f"Sandbox unavailable: {exc}"
        if code != 0:
            detail = (err or out or "").strip()
            return f"Sandboxed command failed (exit {code}): {detail[:2000]}"
        return out


class SandboxedPythonTool(BaseTool):
    """Re-instantiate a python tool class and call ``_run`` inside a container."""

    name: str = "sandboxed_python"
    description: str = "Sandboxed python tool"
    _class_path: str = PrivateAttr()
    _config: dict[str, Any] = PrivateAttr(default_factory=dict)
    _tier: str = PrivateAttr(default="docker")
    _env: dict[str, str] = PrivateAttr(default_factory=dict)
    _network: bool = PrivateAttr(default=False)
    _image: str | None = PrivateAttr(default=None)

    def __init__(
        self,
        *,
        name: str,
        description: str,
        class_path: str,
        config: dict[str, Any] | None = None,
        tier: str = "docker",
        env: dict[str, str] | None = None,
        network: bool = False,
        image: str | None = None,
        args_schema: Any = None,
        **data: Any,
    ) -> None:
        if args_schema is not None:
            data = {**data, "args_schema": args_schema}
        super().__init__(name=name, description=description, **data)
        self._class_path = class_path
        self._config = dict(config or {})
        self._tier = tier
        self._env = dict(env or {})
        self._network = network
        self._image = image

    def _run(self, **kwargs: Any) -> str:
        module_path, class_name = self._class_path.rsplit(".", 1)
        # Runner script: import tool class, instantiate with config, call _run with kwargs.
        script = textwrap.dedent(
            f"""
            import json, sys
            from importlib import import_module
            payload = json.load(sys.stdin)
            mod = import_module({module_path!r})
            cls = getattr(mod, {class_name!r})
            tool = cls(**payload.get("config", {{}}))
            result = tool._run(**payload.get("kwargs", {{}}))
            if not isinstance(result, str):
                result = json.dumps(result)
            sys.stdout.write(result)
            """
        ).strip()
        payload = json.dumps({"config": self._config, "kwargs": kwargs})
        try:
            code, out, err = execute_sandboxed(
                self._tier,
                ["python", "-c", script],
                input_data=payload,
                env=self._env or None,
                network=self._network,
                image=self._image,
            )
        except SandboxExecutionError as exc:
            return f"Sandbox unavailable: {exc}"
        if code != 0:
            detail = (err or out or "").strip()
            return f"Sandboxed python tool failed (exit {code}): {detail[:2000]}"
        return out


def build_wasm_tool(*, name: str, description: str, wasm_path: str) -> BaseTool:
    """Build a CrewAI tool that invokes a WASM module."""
    ensure_sandbox_available("wasm")
    desc = description or f"WASM tool {name}"
    return WasmCrewTool(name=name, description=desc, wasm_path=wasm_path)


def enforce_tool_sandbox(
    tool: Any,
    *,
    tier: str,
    tool_type: str,
    tool_name: str,
    spec: dict[str, Any],
) -> Any:
    """Apply sandbox isolation to a loaded tool instance.

    - ``none``: return tool unchanged
    - ``wasm`` type tools: already isolated (WasmCrewTool)
    - tools with ``command``: run that command in the container/microvm tier
    - python/builtin with tier != none: re-run class in a container
    """
    effective = runtime_tier_for_tool(tier, tool_type)
    if effective == "none":
        return tool

    if tool_type == "wasm" or isinstance(tool, WasmCrewTool):
        return tool

    ensure_sandbox_available(effective)

    description = str(getattr(tool, "description", None) or spec.get("description") or tool_name)
    name = str(getattr(tool, "name", None) or tool_name)
    env = {str(k): str(v) for k, v in (spec.get("env") or {}).items()}
    caps = [str(c) for c in (spec.get("capabilities") or [])]
    network = "network" in caps
    image = spec.get("image")
    image_s = str(image) if image else None

    command = spec.get("command")
    if command:
        return SandboxedCommandTool(
            name=name,
            description=description,
            command=str(command),
            args=[str(a) for a in (spec.get("args") or [])],
            tier=effective,
            env=env,
            network=network,
            image=image_s,
        )

    class_path = spec.get("class_path")
    if tool_type == "builtin":
        raw = str(class_path or tool_name)
        class_path = raw if "." in raw else f"crewai_tools.{raw}"

    if class_path:
        args_schema = getattr(tool, "args_schema", None)
        return SandboxedPythonTool(
            name=name,
            description=description,
            class_path=str(class_path),
            config=dict(spec.get("config") or {}),
            tier=effective,
            env=env,
            network=network,
            image=image_s,
            args_schema=args_schema,
        )

    logger.warning(
        "Cannot sandbox tool '%s' (no command/class_path); running in-process",
        tool_name,
        extra={"event": "sandbox_fallback_inprocess", "tool_name": tool_name, "tier": effective},
    )
    return tool
