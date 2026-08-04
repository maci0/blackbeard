"""Tests for MCP tool loading on agents."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from blackbeard.engine.loader import LoaderError, ResourceLoader
from blackbeard.kinds import ResourceKind
from tests.conftest import _resource_map, make_resource


def test_build_mcp_stdio_config():
    tool = make_resource(
        ResourceKind.TOOL,
        "fs",
        {
            "type": "mcp-stdio",
            "command": "npx",
            "args": ["-y", "pkg"],
            "env": {"A": "1"},
        },
    )
    loader = ResourceLoader(_resource_map(tool))
    with patch("crewai.mcp.MCPServerStdio") as mock_stdio:
        mock_stdio.return_value = "STDIO"
        cfg = loader._build_mcp_server(tool)
    assert cfg == "STDIO"
    mock_stdio.assert_called_once_with(command="npx", args=["-y", "pkg"], env={"A": "1"})


def test_build_mcp_http_config():
    tool = make_resource(
        ResourceKind.TOOL,
        "remote",
        {"type": "mcp-http", "url": "https://example.com/mcp"},
    )
    loader = ResourceLoader(_resource_map(tool))
    with (
        patch("crewai.mcp.MCPServerHTTP") as mock_http,
        patch("blackbeard.engine.loader.check_url_ssrf", return_value=None),
    ):
        mock_http.return_value = "HTTP"
        cfg = loader._build_mcp_server(tool)
    assert cfg == "HTTP"
    mock_http.assert_called_once()
    assert mock_http.call_args.kwargs["url"] == "https://example.com/mcp"
    assert mock_http.call_args.kwargs["streamable"] is True


def test_build_mcp_http_sse_by_url():
    tool = make_resource(
        ResourceKind.TOOL,
        "remote",
        {"type": "mcp-http", "url": "https://example.com/mcp/sse"},
    )
    loader = ResourceLoader(_resource_map(tool))
    with (
        patch("crewai.mcp.MCPServerSSE") as mock_sse,
        patch("blackbeard.engine.loader.check_url_ssrf", return_value=None),
    ):
        mock_sse.return_value = "SSE"
        cfg = loader._build_mcp_server(tool)
    assert cfg == "SSE"
    mock_sse.assert_called_once()


def test_build_mcp_http_headers_from_config():
    tool = make_resource(
        ResourceKind.TOOL,
        "remote",
        {
            "type": "mcp-http",
            "url": "https://example.com/mcp",
            "config": {"headers": {"Authorization": "Bearer x"}, "streamable": False},
        },
    )
    loader = ResourceLoader(_resource_map(tool))
    with (
        patch("crewai.mcp.MCPServerHTTP") as mock_http,
        patch("blackbeard.engine.loader.check_url_ssrf", return_value=None),
    ):
        mock_http.return_value = "HTTP"
        loader._build_mcp_server(tool)
    assert mock_http.call_args.kwargs["headers"] == {"Authorization": "Bearer x"}
    assert mock_http.call_args.kwargs["streamable"] is False


def test_build_mcp_stdio_requires_command():
    tool = make_resource(ResourceKind.TOOL, "bad", {"type": "mcp-stdio"})
    loader = ResourceLoader(_resource_map(tool))
    with pytest.raises(LoaderError, match="command"):
        loader._build_mcp_server(tool)


def test_build_mcp_http_requires_url():
    tool = make_resource(ResourceKind.TOOL, "bad", {"type": "mcp-http"})
    loader = ResourceLoader(_resource_map(tool))
    with pytest.raises(LoaderError, match="url"):
        loader._build_mcp_server(tool)


def test_build_mcp_http_ssrf_blocked():
    tool = make_resource(
        ResourceKind.TOOL,
        "bad",
        {"type": "mcp-http", "url": "http://127.0.0.1/mcp"},
    )
    loader = ResourceLoader(_resource_map(tool))
    with patch(
        "blackbeard.engine.loader.check_url_ssrf",
        return_value="URL targets a private/internal address",
    ):
        with pytest.raises(LoaderError, match=r"private|internal|URL"):
            loader._build_mcp_server(tool)


@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
def test_agent_attaches_mcp_stdio(mock_agent_cls, mock_llm_cls):
    tool = make_resource(
        ResourceKind.TOOL,
        "fs",
        {
            "type": "mcp-stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem"],
            "description": "fs",
        },
    )
    agent = make_resource(
        ResourceKind.AGENT,
        "a",
        {
            "role": "r",
            "goal": "g",
            "backstory": "b",
            "tools": ["ref:tools/fs"],
        },
    )
    loader = ResourceLoader(_resource_map(tool, agent))
    with patch.object(ResourceLoader, "_build_mcp_server", return_value=MagicMock(name="mcp")):
        loader.build_agent("ref:agents/a")
    _, kwargs = mock_agent_cls.call_args
    assert "mcps" in kwargs
    assert len(kwargs["mcps"]) == 1
    assert "tools" not in kwargs


@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
def test_mcp_policy_denylist(mock_agent_cls, mock_llm_cls):
    tool = make_resource(
        ResourceKind.TOOL,
        "fs",
        {"type": "mcp-stdio", "command": "npx", "args": []},
    )
    agent = make_resource(
        ResourceKind.AGENT,
        "a",
        {
            "role": "r",
            "goal": "g",
            "backstory": "b",
            "tools": ["ref:tools/fs"],
            "policy": "ref:agent-policies/p",
        },
    )
    policy = make_resource(
        ResourceKind.AGENT_POLICY,
        "p",
        {"tools": {"mode": "denylist", "deny": ["fs"]}},
    )
    loader = ResourceLoader(
        _resource_map(tool, agent, policy),
        policies={"p": policy.spec},
    )
    with patch.object(ResourceLoader, "_build_mcp_server", return_value=MagicMock()):
        loader.build_agent("ref:agents/a")
    _, kwargs = mock_agent_cls.call_args
    assert "mcps" not in kwargs


def test_build_tool_mcp_returns_none():
    tool = make_resource(
        ResourceKind.TOOL,
        "fs",
        {"type": "mcp-stdio", "command": "npx"},
    )
    loader = ResourceLoader(_resource_map(tool))
    assert loader.build_tool("ref:tools/fs") is None


@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
@patch("blackbeard.engine.loader.importlib")
def test_agent_mixes_python_and_mcp(mock_importlib, mock_agent_cls, mock_llm_cls):
    from types import ModuleType

    fake_cls = MagicMock(name="SearchTool")
    fake_mod = ModuleType("crewai_tools.search")
    fake_mod.SearchTool = fake_cls  # type: ignore[attr-defined]
    mock_importlib.import_module.return_value = fake_mod

    py_tool = make_resource(
        ResourceKind.TOOL,
        "search",
        {"type": "python", "class_path": "crewai_tools.search.SearchTool"},
    )
    mcp_tool = make_resource(
        ResourceKind.TOOL,
        "fs",
        {"type": "mcp-stdio", "command": "npx", "args": ["-y", "pkg"]},
    )
    agent = make_resource(
        ResourceKind.AGENT,
        "a",
        {
            "role": "r",
            "goal": "g",
            "backstory": "b",
            "tools": ["ref:tools/search", "ref:tools/fs"],
        },
    )
    loader = ResourceLoader(_resource_map(py_tool, mcp_tool, agent))
    with patch.object(ResourceLoader, "_build_mcp_server", return_value=MagicMock()):
        with patch("blackbeard.engine.loader.enforce_tool_sandbox", side_effect=lambda t, **k: t):
            loader.build_agent("ref:agents/a")
    _, kwargs = mock_agent_cls.call_args
    assert "tools" in kwargs
    assert len(kwargs["tools"]) == 1
    assert "mcps" in kwargs
    assert len(kwargs["mcps"]) == 1
