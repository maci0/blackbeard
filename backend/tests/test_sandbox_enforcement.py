"""Tests for sandbox tier enforcement on tools."""

from __future__ import annotations

from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from blackbeard.engine.loader import LoaderError, ResourceLoader
from blackbeard.engine.sandbox.runner import (
    SandboxExecutionError,
    runtime_tier_for_tool,
)
from blackbeard.engine.sandbox.tool_wrapper import (
    SandboxedCommandTool,
    SandboxedPythonTool,
    enforce_tool_sandbox,
)
from blackbeard.kinds import ResourceKind
from tests.conftest import _resource_map, make_resource


def test_runtime_tier_promotes_wasm_for_python():
    assert runtime_tier_for_tool("wasm", "python") == "docker"
    assert runtime_tier_for_tool("wasm", "wasm") == "wasm"
    assert runtime_tier_for_tool("none", "python") == "none"
    assert runtime_tier_for_tool("gvisor", "python") == "gvisor"


def test_enforce_none_returns_same_tool():
    tool = MagicMock(name="inner")
    assert enforce_tool_sandbox(tool, tier="none", tool_type="python", tool_name="t", spec={}) is tool


def test_enforce_command_tool_wraps():
    tool = MagicMock()
    tool.name = "cmd"
    tool.description = "runs a command"
    with patch("blackbeard.engine.sandbox.tool_wrapper.ensure_sandbox_available"):
        wrapped = enforce_tool_sandbox(
            tool,
            tier="docker",
            tool_type="python",
            tool_name="cmd",
            spec={"command": "echo", "args": ["hi"], "description": "runs a command"},
        )
    assert isinstance(wrapped, SandboxedCommandTool)
    assert wrapped.name == "cmd"


def test_enforce_python_tool_wraps():
    tool = MagicMock()
    tool.name = "search"
    tool.description = "search"
    tool.args_schema = None
    with patch("blackbeard.engine.sandbox.tool_wrapper.ensure_sandbox_available"):
        wrapped = enforce_tool_sandbox(
            tool,
            tier="docker",
            tool_type="python",
            tool_name="search",
            spec={
                "type": "python",
                "class_path": "crewai_tools.search.SearchTool",
                "config": {"k": 1},
            },
        )
    assert isinstance(wrapped, SandboxedPythonTool)


def test_sandboxed_command_tool_runs_via_runner():
    tool = SandboxedCommandTool(
        name="echo",
        description="echo",
        command="echo",
        args=["ok"],
        tier="docker",
    )
    with patch(
        "blackbeard.engine.sandbox.tool_wrapper.execute_sandboxed",
        return_value=(0, "ok\n", ""),
    ) as mock_exec:
        out = tool._run()
    assert out == "ok\n"
    mock_exec.assert_called_once()
    assert mock_exec.call_args[0][0] == "docker"
    assert mock_exec.call_args[0][1] == ["echo", "ok"]


def test_sandboxed_command_tool_reports_failure():
    tool = SandboxedCommandTool(name="x", description="x", command="false", tier="docker")
    with patch(
        "blackbeard.engine.sandbox.tool_wrapper.execute_sandboxed",
        return_value=(1, "", "boom"),
    ):
        out = tool._run()
    assert "exit 1" in out
    assert "boom" in out


def test_sandboxed_python_tool_runs_script():
    tool = SandboxedPythonTool(
        name="t",
        description="t",
        class_path="crewai_tools.search.SearchTool",
        config={"k": 2},
        tier="podman",
    )
    with patch(
        "blackbeard.engine.sandbox.tool_wrapper.execute_sandboxed",
        return_value=(0, "result", ""),
    ) as mock_exec:
        out = tool._run(query="q")
    assert out == "result"
    assert mock_exec.call_args[0][0] == "podman"
    assert mock_exec.call_args[0][1][0] == "python"


@patch("blackbeard.engine.loader.build_wasm_tool")
def test_loader_builds_wasm_tool(mock_build):
    mock_build.return_value = MagicMock(name="wasm")
    tool_res = make_resource(
        ResourceKind.TOOL,
        "w",
        {"type": "wasm", "wasm_module": "tools/mod.wasm", "description": "w"},
    )
    loader = ResourceLoader(_resource_map(tool_res))
    result = loader.build_tool("ref:tools/w")
    mock_build.assert_called_once()
    assert result is mock_build.return_value


@patch("blackbeard.engine.loader.importlib")
@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
@patch("blackbeard.engine.loader.enforce_tool_sandbox")
def test_loader_enforces_sandbox_on_agent_tools(
    mock_enforce, mock_agent_cls, mock_llm_cls, mock_importlib
):
    fake_tool_cls = MagicMock(name="SearchTool")
    fake_module = ModuleType("crewai_tools.search")
    fake_module.SearchTool = fake_tool_cls  # type: ignore[attr-defined]
    mock_importlib.import_module.return_value = fake_module
    mock_enforce.side_effect = lambda tool, **kw: tool

    tool = make_resource(
        ResourceKind.TOOL,
        "search",
        {
            "type": "python",
            "class_path": "crewai_tools.search.SearchTool",
            "sandbox": "none",
        },
    )
    agent = make_resource(
        ResourceKind.AGENT,
        "a",
        {
            "role": "r",
            "goal": "g",
            "backstory": "b",
            "tools": ["ref:tools/search"],
            "policy": "ref:agent-policies/p",
        },
    )
    policy = make_resource(
        ResourceKind.AGENT_POLICY,
        "p",
        {"sandbox": {"minimum_tier": "docker"}},
    )
    loader = ResourceLoader(
        _resource_map(tool, agent, policy),
        policies={"p": policy.spec},
    )
    loader.build_agent("ref:agents/a")
    mock_enforce.assert_called_once()
    assert mock_enforce.call_args.kwargs["tier"] == "docker"


@patch("blackbeard.engine.loader.importlib")
@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
def test_loader_raises_when_sandbox_unavailable(mock_agent_cls, mock_llm_cls, mock_importlib):
    fake_tool_cls = MagicMock(name="SearchTool")
    fake_module = ModuleType("crewai_tools.search")
    fake_module.SearchTool = fake_tool_cls  # type: ignore[attr-defined]
    mock_importlib.import_module.return_value = fake_module

    tool = make_resource(
        ResourceKind.TOOL,
        "search",
        {
            "type": "python",
            "class_path": "crewai_tools.search.SearchTool",
            "sandbox": "docker",
        },
    )
    agent = make_resource(
        ResourceKind.AGENT,
        "a",
        {
            "role": "r",
            "goal": "g",
            "backstory": "b",
            "tools": ["ref:tools/search"],
        },
    )
    loader = ResourceLoader(_resource_map(tool, agent))
    with patch(
        "blackbeard.engine.loader.enforce_tool_sandbox",
        side_effect=SandboxExecutionError("no docker"),
    ):
        with pytest.raises(LoaderError, match="cannot enforce sandbox"):
            loader.build_agent("ref:agents/a")


def test_enforce_passes_image_and_network_capability():
    tool = MagicMock()
    tool.name = "cmd"
    tool.description = "c"
    with patch("blackbeard.engine.sandbox.tool_wrapper.ensure_sandbox_available"):
        wrapped = enforce_tool_sandbox(
            tool,
            tier="docker",
            tool_type="python",
            tool_name="cmd",
            spec={
                "command": "curl",
                "image": "curlimages/curl:8.5.0",
                "capabilities": ["network"],
            },
        )
    assert isinstance(wrapped, SandboxedCommandTool)
    assert wrapped._image == "curlimages/curl:8.5.0"
    assert wrapped._network is True


def test_python_sandbox_defaults_network_off():
    tool = MagicMock()
    tool.name = "search"
    tool.description = "s"
    tool.args_schema = None
    with patch("blackbeard.engine.sandbox.tool_wrapper.ensure_sandbox_available"):
        wrapped = enforce_tool_sandbox(
            tool,
            tier="docker",
            tool_type="python",
            tool_name="search",
            spec={"class_path": "crewai_tools.search.SearchTool"},
        )
    assert isinstance(wrapped, SandboxedPythonTool)
    assert wrapped._network is False


def test_execute_sandboxed_forwards_image():
    with patch(
        "blackbeard.engine.sandbox.runner.ensure_sandbox_available"
    ), patch(
        "blackbeard.engine.sandbox.runner._run_coro",
        return_value=(0, "out", ""),
    ) as mock_run:
        from blackbeard.engine.sandbox.runner import execute_sandboxed

        execute_sandboxed(
            "docker",
            ["echo", "hi"],
            image="alpine:3.20",
            network=False,
        )
    assert mock_run.called


@pytest.mark.skipif(
    __import__("shutil").which("docker") is None and __import__("shutil").which("podman") is None,
    reason="no container runtime on PATH",
)
def test_smoke_docker_echo():
    """Real container smoke: run echo in docker/podman when available."""
    from blackbeard.engine.sandbox.runner import execute_sandboxed

    code, out, err = execute_sandboxed(
        "docker",
        ["/bin/echo", "blackbeard-sandbox-ok"],
        image=None,
        network=False,
    )
    assert code == 0, err
    assert "blackbeard-sandbox-ok" in out
