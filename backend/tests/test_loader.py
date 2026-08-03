"""Unit tests for ResourceLoader.

Tests build CrewAI objects from Resource stubs without hitting a real database
or making actual LLM/CrewAI API calls. crewai.Agent, crewai.Task, crewai.Crew,
and litellm.LLM are all mocked so no network traffic is produced.
"""

from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from blackbeard.engine.loader import LoaderError, ResourceLoader
from blackbeard.kinds import ResourceKind
from tests.conftest import _resource_map, make_resource

# ---------------------------------------------------------------------------
# LLM tests
# ---------------------------------------------------------------------------


@patch("blackbeard.engine.loader.LLM")
def test_build_llm_vertex_ai(mock_llm_cls):
    """Model name should be passed through as-is (proxy handles provider routing)."""
    conn = make_resource(
        ResourceKind.LLM_CONNECTION,
        "my-llm",
        {"provider": "vertex_ai", "model": "claude-sonnet-4-6"},
    )
    loader = ResourceLoader(_resource_map(conn))
    loader.build_llm("ref:llm-connections/my-llm")

    mock_llm_cls.assert_called_once()
    _, kwargs = mock_llm_cls.call_args
    assert kwargs["model"] == "my-llm"


@patch("blackbeard.engine.loader.LLM")
def test_build_llm_openai(mock_llm_cls):
    """openai provider should pass the model string through unchanged."""
    conn = make_resource(
        ResourceKind.LLM_CONNECTION,
        "gpt4",
        {"provider": "openai", "model": "gpt-4o"},
    )
    loader = ResourceLoader(_resource_map(conn))
    loader.build_llm("ref:llm-connections/gpt4")

    _, kwargs = mock_llm_cls.call_args
    assert kwargs["model"] == "gpt4"


@patch("blackbeard.engine.loader.LLM")
def test_build_llm_caching(mock_llm_cls):
    """Calling build_llm twice with the same ref should return the cached instance."""
    conn = make_resource(
        ResourceKind.LLM_CONNECTION,
        "cached-llm",
        {"provider": "openai", "model": "gpt-4o"},
    )
    loader = ResourceLoader(_resource_map(conn))
    llm_a = loader.build_llm("ref:llm-connections/cached-llm")
    llm_b = loader.build_llm("ref:llm-connections/cached-llm")

    assert llm_a is llm_b
    assert mock_llm_cls.call_count == 1


@patch("blackbeard.engine.loader.LLM")
def test_build_llm_parameters(mock_llm_cls):
    """temperature and max_tokens in parameters should be forwarded to LLM."""
    conn = make_resource(
        ResourceKind.LLM_CONNECTION,
        "param-llm",
        {
            "provider": "openai",
            "model": "gpt-4o",
            "parameters": {"temperature": 0.2, "max_tokens": 512},
        },
    )
    loader = ResourceLoader(_resource_map(conn))
    loader.build_llm("ref:llm-connections/param-llm")

    _, kwargs = mock_llm_cls.call_args
    assert kwargs["temperature"] == 0.2
    assert kwargs["max_tokens"] == 512


# ---------------------------------------------------------------------------
# Agent tests
# ---------------------------------------------------------------------------


@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
def test_build_agent(mock_agent_cls, mock_llm_cls):
    """Agent with role/goal/backstory should construct a CrewAI Agent."""
    agent_res = make_resource(
        ResourceKind.AGENT,
        "researcher",
        {"role": "Researcher", "goal": "Find things", "backstory": "Expert"},
    )
    loader = ResourceLoader(_resource_map(agent_res))
    loader.build_agent("ref:agents/researcher")

    mock_agent_cls.assert_called_once()
    _, kwargs = mock_agent_cls.call_args
    assert kwargs["role"] == "Researcher"
    assert kwargs["goal"] == "Find things"
    assert kwargs["backstory"] == "Expert"
    assert kwargs["verbose"] is True
    assert kwargs["allow_delegation"] is False
    mock_llm_cls.assert_not_called()
    assert "llm" not in kwargs


@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
def test_build_agent_with_llm_ref(mock_agent_cls, mock_llm_cls):
    """Agent spec with llm ref should resolve and pass LLM to Agent constructor."""
    llm_res = make_resource(
        ResourceKind.LLM_CONNECTION,
        "test-llm",
        {"provider": "openai", "model": "gpt-4o"},
    )
    agent_res = make_resource(
        ResourceKind.AGENT,
        "smart-agent",
        {
            "role": "Analyst",
            "goal": "Analyse data",
            "backstory": "Data expert",
            "llm": "ref:llm-connections/test-llm",
        },
    )
    loader = ResourceLoader(_resource_map(llm_res, agent_res))
    loader.build_agent("ref:agents/smart-agent")

    _, kwargs = mock_agent_cls.call_args
    assert "llm" in kwargs
    assert kwargs["llm"] is mock_llm_cls.return_value


@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
def test_build_agent_caching(mock_agent_cls, mock_llm_cls):
    """build_agent called twice returns the cached instance."""
    agent_res = make_resource(
        ResourceKind.AGENT,
        "cached-agent",
        {"role": "R", "goal": "G", "backstory": "B"},
    )
    loader = ResourceLoader(_resource_map(agent_res))
    a1 = loader.build_agent("ref:agents/cached-agent")
    a2 = loader.build_agent("ref:agents/cached-agent")

    assert a1 is a2
    assert mock_agent_cls.call_count == 1


# ---------------------------------------------------------------------------
# Task tests
# ---------------------------------------------------------------------------


@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
@patch("blackbeard.engine.loader.Task")
def test_build_task(mock_task_cls, mock_agent_cls, mock_llm_cls):
    """Task with description/expected_output/agent ref should build a CrewAI Task."""
    agent_res = make_resource(
        ResourceKind.AGENT,
        "worker",
        {"role": "Worker", "goal": "Work", "backstory": "Does work"},
    )
    task_res = make_resource(
        ResourceKind.TASK,
        "my-task",
        {
            "description": "Do the thing",
            "expected_output": "The thing is done",
            "agent": "ref:agents/worker",
        },
    )
    loader = ResourceLoader(_resource_map(agent_res, task_res))
    loader.build_task("ref:tasks/my-task")

    mock_task_cls.assert_called_once()
    _, kwargs = mock_task_cls.call_args
    assert kwargs["description"] == "Do the thing"
    assert kwargs["expected_output"] == "The thing is done"
    assert "agent" in kwargs
    assert kwargs["agent"] is mock_agent_cls.return_value


@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
@patch("blackbeard.engine.loader.Task")
def test_build_task_with_context(mock_task_cls, mock_agent_cls, mock_llm_cls):
    """Task with context refs should resolve context tasks and pass them to Task."""
    agent_res = make_resource(
        ResourceKind.AGENT,
        "agent1",
        {"role": "R", "goal": "G", "backstory": "B"},
    )
    ctx_task_res = make_resource(
        ResourceKind.TASK,
        "context-task",
        {
            "description": "Context work",
            "expected_output": "Context output",
            "agent": "ref:agents/agent1",
        },
    )
    main_task_res = make_resource(
        ResourceKind.TASK,
        "main-task",
        {
            "description": "Main work",
            "expected_output": "Main output",
            "agent": "ref:agents/agent1",
            "context": ["ref:tasks/context-task"],
        },
    )
    loader = ResourceLoader(_resource_map(agent_res, ctx_task_res, main_task_res))
    loader.build_task("ref:tasks/main-task")

    # Task should have been built twice (context-task + main-task)
    assert mock_task_cls.call_count == 2
    # The last call (main-task) should have context kwarg
    calls = mock_task_cls.call_args_list
    main_call_kwargs = calls[1][1]
    assert "context" in main_call_kwargs
    assert len(main_call_kwargs["context"]) == 1


# ---------------------------------------------------------------------------
# Crew tests
# ---------------------------------------------------------------------------


@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
@patch("blackbeard.engine.loader.Task")
@patch("blackbeard.engine.loader.Crew")
def test_build_crew(mock_crew_cls, mock_task_cls, mock_agent_cls, mock_llm_cls):
    """build_crew should assemble agents + tasks and return a Crew."""
    agent_res = make_resource(
        ResourceKind.AGENT,
        "agent-a",
        {"role": "R", "goal": "G", "backstory": "B"},
    )
    task_res = make_resource(
        ResourceKind.TASK,
        "task-a",
        {"description": "D", "expected_output": "E", "agent": "ref:agents/agent-a"},
    )
    crew_res = make_resource(
        ResourceKind.CREW,
        "my-crew",
        {
            "process": "sequential",
            "agents": ["ref:agents/agent-a"],
            "tasks": ["ref:tasks/task-a"],
        },
    )
    loader = ResourceLoader(_resource_map(agent_res, task_res, crew_res))
    loader.build_crew("my-crew")

    mock_crew_cls.assert_called_once()
    _, kwargs = mock_crew_cls.call_args
    assert len(kwargs["agents"]) == 1
    assert len(kwargs["tasks"]) == 1
    from crewai import Process

    assert kwargs["process"] is Process.sequential
    assert kwargs["verbose"] is True


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


def test_resolve_missing_ref_raises():
    """Referencing a resource that doesn't exist should raise LoaderError."""
    loader = ResourceLoader({})
    with pytest.raises(LoaderError, match="not found"):
        loader.build_agent("ref:agents/nonexistent")


@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
def test_invalid_kind_raises(mock_agent_cls, mock_llm_cls):
    """Resolving a ref where the kind doesn't match should raise LoaderError."""
    task_res = make_resource(
        ResourceKind.TASK,
        "oops",
        {"description": "D", "expected_output": "E"},
    )
    loader = ResourceLoader({"Agent/oops": task_res})
    with pytest.raises(LoaderError, match="Expected Agent"):
        loader.build_agent("ref:agents/oops")


def test_invalid_ref_string_raises():
    """A non-ref string passed to build methods should raise LoaderError."""
    loader = ResourceLoader({})
    with pytest.raises(LoaderError, match="not a valid ref"):
        loader.build_agent("not-a-ref-string")


def test_build_crew_missing_crew_raises():
    """build_crew for a crew not in the resource map should raise LoaderError."""
    loader = ResourceLoader({})
    with pytest.raises(LoaderError, match="not found"):
        loader.build_crew("ghost-crew")


# ---------------------------------------------------------------------------
# output_file path traversal protection (security-critical)
# ---------------------------------------------------------------------------


@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
@patch("blackbeard.engine.loader.Task")
def test_build_task_rejects_path_traversal_in_output_file(
    mock_task_cls, mock_agent_cls, mock_llm_cls
):
    """output_file with path traversal should raise LoaderError."""
    agent_res = make_resource(
        ResourceKind.AGENT,
        "agent-a",
        {"role": "R", "goal": "G", "backstory": "B"},
    )
    task_res = make_resource(
        ResourceKind.TASK,
        "bad-task",
        {
            "description": "D",
            "expected_output": "E",
            "agent": "ref:agents/agent-a",
            "output_file": "../../../etc/passwd",
        },
    )
    loader = ResourceLoader(_resource_map(agent_res, task_res))
    with pytest.raises(LoaderError, match="plain filename"):
        loader.build_task("ref:tasks/bad-task")


@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
@patch("blackbeard.engine.loader.Task")
def test_build_task_rejects_absolute_output_file(mock_task_cls, mock_agent_cls, mock_llm_cls):
    """output_file with absolute path should raise LoaderError."""
    agent_res = make_resource(
        ResourceKind.AGENT,
        "agent-a",
        {"role": "R", "goal": "G", "backstory": "B"},
    )
    task_res = make_resource(
        ResourceKind.TASK,
        "abs-task",
        {
            "description": "D",
            "expected_output": "E",
            "agent": "ref:agents/agent-a",
            "output_file": "/tmp/output.txt",
        },
    )
    loader = ResourceLoader(_resource_map(agent_res, task_res))
    with pytest.raises(LoaderError, match="plain filename"):
        loader.build_task("ref:tasks/abs-task")


@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
@patch("blackbeard.engine.loader.Task")
def test_build_task_accepts_safe_output_file(mock_task_cls, mock_agent_cls, mock_llm_cls):
    """output_file with a plain filename should pass through."""
    agent_res = make_resource(
        ResourceKind.AGENT,
        "agent-a",
        {"role": "R", "goal": "G", "backstory": "B"},
    )
    task_res = make_resource(
        ResourceKind.TASK,
        "safe-task",
        {
            "description": "D",
            "expected_output": "E",
            "agent": "ref:agents/agent-a",
            "output_file": "report.json",
        },
    )
    loader = ResourceLoader(_resource_map(agent_res, task_res))
    loader.build_task("ref:tasks/safe-task")

    mock_task_cls.assert_called_once()
    _, kwargs = mock_task_cls.call_args
    assert kwargs["output_file"] == "report.json"


# ---------------------------------------------------------------------------
# Hierarchical crew with manager LLM
# ---------------------------------------------------------------------------


@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
@patch("blackbeard.engine.loader.Task")
@patch("blackbeard.engine.loader.Crew")
def test_build_crew_hierarchical_with_manager_llm(
    mock_crew_cls, mock_task_cls, mock_agent_cls, mock_llm_cls
):
    """Hierarchical crew should set process=hierarchical and wire manager_llm."""
    llm_res = make_resource(
        ResourceKind.LLM_CONNECTION,
        "mgr-llm",
        {"provider": "openai", "model": "gpt-4o"},
    )
    agent_res = make_resource(
        ResourceKind.AGENT,
        "agent-h",
        {"role": "R", "goal": "G", "backstory": "B"},
    )
    task_res = make_resource(
        ResourceKind.TASK,
        "task-h",
        {"description": "D", "expected_output": "E", "agent": "ref:agents/agent-h"},
    )
    crew_res = make_resource(
        ResourceKind.CREW,
        "hier-crew",
        {
            "process": "hierarchical",
            "agents": ["ref:agents/agent-h"],
            "tasks": ["ref:tasks/task-h"],
            "manager_llm": "ref:llm-connections/mgr-llm",
        },
    )
    loader = ResourceLoader(_resource_map(llm_res, agent_res, task_res, crew_res))
    loader.build_crew("hier-crew")

    _, kwargs = mock_crew_cls.call_args
    assert kwargs["manager_llm"] is mock_llm_cls.return_value


# ---------------------------------------------------------------------------
# Task caching
# ---------------------------------------------------------------------------


@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
@patch("blackbeard.engine.loader.Task")
def test_build_task_caching(mock_task_cls, mock_agent_cls, mock_llm_cls):
    """build_task called twice returns the cached instance."""
    agent_res = make_resource(
        ResourceKind.AGENT,
        "ag",
        {"role": "R", "goal": "G", "backstory": "B"},
    )
    task_res = make_resource(
        ResourceKind.TASK,
        "cached-task",
        {"description": "D", "expected_output": "E", "agent": "ref:agents/ag"},
    )
    loader = ResourceLoader(_resource_map(agent_res, task_res))
    t1 = loader.build_task("ref:tasks/cached-task")
    t2 = loader.build_task("ref:tasks/cached-task")

    assert t1 is t2
    assert mock_task_cls.call_count == 1


# ---------------------------------------------------------------------------
# Tool loading tests
# ---------------------------------------------------------------------------


@patch("blackbeard.engine.loader.importlib")
def test_build_tool_python(mock_importlib):
    """Tool with type=python should dynamically import the class_path."""
    fake_cls = MagicMock(name="FakeTool")
    fake_module = ModuleType("crewai_tools.search")
    fake_module.SearchTool = fake_cls  # type: ignore[attr-defined]
    mock_importlib.import_module.return_value = fake_module

    tool_res = make_resource(
        ResourceKind.TOOL,
        "search",
        {"type": "python", "class_path": "crewai_tools.search.SearchTool", "config": {"k": 5}},
    )
    loader = ResourceLoader(_resource_map(tool_res))
    result = loader.build_tool("ref:tools/search")

    mock_importlib.import_module.assert_called_once_with("crewai_tools.search")
    fake_cls.assert_called_once_with(k=5)
    assert result is fake_cls.return_value


@patch("blackbeard.engine.loader.importlib")
def test_build_tool_python_no_config(mock_importlib):
    """Tool with type=python and no config should pass empty kwargs."""
    fake_cls = MagicMock(name="PlainTool")
    fake_module = ModuleType("crewai_tools.plain")
    fake_module.PlainTool = fake_cls  # type: ignore[attr-defined]
    mock_importlib.import_module.return_value = fake_module

    tool_res = make_resource(
        ResourceKind.TOOL,
        "plain",
        {"type": "python", "class_path": "crewai_tools.plain.PlainTool"},
    )
    loader = ResourceLoader(_resource_map(tool_res))
    result = loader.build_tool("ref:tools/plain")

    fake_cls.assert_called_once_with()
    assert result is fake_cls.return_value


def test_build_tool_python_missing_class_path():
    """Tool with type=python but no class_path should raise LoaderError."""
    tool_res = make_resource(
        ResourceKind.TOOL,
        "broken",
        {"type": "python"},
    )
    loader = ResourceLoader(_resource_map(tool_res))
    with pytest.raises(LoaderError, match="no class_path"):
        loader.build_tool("ref:tools/broken")


def test_build_tool_python_disallowed_class_path():
    """Tool with class_path outside the allowlist should raise LoaderError (security).

    The allowlist only permits crewai_tools.*, crewai.tools.*, langchain_community.tools.*,
    and langchain.tools.* prefixes to prevent arbitrary code execution.
    """
    tool_res = make_resource(
        ResourceKind.TOOL,
        "evil",
        {"type": "python", "class_path": "subprocess.Popen"},
    )
    loader = ResourceLoader(_resource_map(tool_res))
    with pytest.raises(LoaderError, match="not in the allowed module list"):
        loader.build_tool("ref:tools/evil")


@pytest.mark.parametrize(
    "class_path",
    [
        "shutil.rmtree",
        "my_custom_module.EvilTool",
        "builtins.__import__",
    ],
)
def test_build_tool_python_various_disallowed_paths(class_path):
    """Various module paths outside the allowlist should all be rejected."""
    tool_res = make_resource(
        ResourceKind.TOOL,
        "bad-tool",
        {"type": "python", "class_path": class_path},
    )
    loader = ResourceLoader(_resource_map(tool_res))
    with pytest.raises(LoaderError, match="not in the allowed module list"):
        loader.build_tool("ref:tools/bad-tool")


def test_build_tool_builtin():
    """Tool with type=builtin should import from crewai_tools."""
    fake_tool_cls = MagicMock(name="SerperDevTool")
    fake_crewai_tools = MagicMock()
    fake_crewai_tools.SerperDevTool = fake_tool_cls

    tool_res = make_resource(
        ResourceKind.TOOL,
        "serper",
        {"type": "builtin", "class_path": "SerperDevTool"},
    )
    loader = ResourceLoader(_resource_map(tool_res))

    with patch.dict("sys.modules", {"crewai_tools": fake_crewai_tools}):
        result = loader.build_tool("ref:tools/serper")

    fake_tool_cls.assert_called_once_with()
    assert result is fake_tool_cls.return_value


def test_build_tool_unsupported_type():
    """Tool with unsupported type (e.g. wasm) should return None."""
    tool_res = make_resource(
        ResourceKind.TOOL,
        "wasm-tool",
        {"type": "wasm", "module": "something.wasm"},
    )
    loader = ResourceLoader(_resource_map(tool_res))
    result = loader.build_tool("ref:tools/wasm-tool")

    assert result is None


def test_build_tool_mcp_stdio_unsupported():
    """Tool with type=mcp-stdio should return None (not yet supported)."""
    tool_res = make_resource(
        ResourceKind.TOOL,
        "mcp-tool",
        {"type": "mcp-stdio", "command": "npx", "args": ["-y", "some-server"]},
    )
    loader = ResourceLoader(_resource_map(tool_res))
    result = loader.build_tool("ref:tools/mcp-tool")

    assert result is None


def test_build_tool_mcp_http_unsupported():
    """Tool with type=mcp-http should return None (not yet supported)."""
    tool_res = make_resource(
        ResourceKind.TOOL,
        "mcp-http-tool",
        {"type": "mcp-http", "url": "http://example.com/mcp"},
    )
    loader = ResourceLoader(_resource_map(tool_res))
    result = loader.build_tool("ref:tools/mcp-http-tool")

    assert result is None


def test_build_tool_wrong_kind_raises():
    """build_tool with a non-Tool resource should raise LoaderError."""
    agent_res = make_resource(
        ResourceKind.AGENT,
        "not-a-tool",
        {"role": "R", "goal": "G", "backstory": "B"},
    )
    # Store the agent under Tool/ key so _resolve_ref finds it
    loader = ResourceLoader({"Tool/not-a-tool": agent_res})
    with pytest.raises(LoaderError, match="Expected Tool"):
        loader.build_tool("ref:tools/not-a-tool")


# ---------------------------------------------------------------------------
# Agent with tools integration
# ---------------------------------------------------------------------------


@patch("blackbeard.engine.loader.importlib")
@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
def test_build_agent_with_tool_refs(mock_agent_cls, mock_llm_cls, mock_importlib):
    """Agent with tool refs should resolve tools and pass them to Agent constructor."""
    fake_tool_cls = MagicMock(name="SearchTool")
    fake_module = ModuleType("crewai_tools.search")
    fake_module.SearchTool = fake_tool_cls  # type: ignore[attr-defined]
    mock_importlib.import_module.return_value = fake_module

    tool_res = make_resource(
        ResourceKind.TOOL,
        "search",
        {"type": "python", "class_path": "crewai_tools.search.SearchTool"},
    )
    agent_res = make_resource(
        ResourceKind.AGENT,
        "tooled-agent",
        {
            "role": "Researcher",
            "goal": "Find things",
            "backstory": "Expert",
            "tools": ["ref:tools/search"],
        },
    )
    loader = ResourceLoader(_resource_map(tool_res, agent_res))
    loader.build_agent("ref:agents/tooled-agent")

    _, kwargs = mock_agent_cls.call_args
    assert "tools" in kwargs
    assert len(kwargs["tools"]) == 1
    assert kwargs["tools"][0] is fake_tool_cls.return_value


@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
def test_build_agent_with_unsupported_tool_skips(mock_agent_cls, mock_llm_cls):
    """Agent with unsupported tool type should skip the tool (no tools kwarg)."""
    tool_res = make_resource(
        ResourceKind.TOOL,
        "wasm-tool",
        {"type": "wasm", "module": "something.wasm"},
    )
    agent_res = make_resource(
        ResourceKind.AGENT,
        "wasm-agent",
        {
            "role": "Runner",
            "goal": "Run",
            "backstory": "Fast",
            "tools": ["ref:tools/wasm-tool"],
        },
    )
    loader = ResourceLoader(_resource_map(tool_res, agent_res))
    loader.build_agent("ref:agents/wasm-agent")

    _, kwargs = mock_agent_cls.call_args
    assert "tools" not in kwargs


# ---------------------------------------------------------------------------
# Knowledge source loading tests
# ---------------------------------------------------------------------------


@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
def test_build_agent_with_knowledge_sources(mock_agent_cls, mock_llm_cls):
    """Agent with knowledge_sources refs should resolve and pass them to Agent."""
    ks_res = make_resource(
        ResourceKind.KNOWLEDGE_SOURCE,
        "my-docs",
        {"type": "string", "content": "Important knowledge here."},
    )
    agent_res = make_resource(
        ResourceKind.AGENT,
        "smart-agent",
        {
            "role": "Expert",
            "goal": "Be knowledgeable",
            "backstory": "Well-read",
            "knowledge_sources": ["ref:knowledge-sources/my-docs"],
        },
    )
    loader = ResourceLoader(_resource_map(ks_res, agent_res))

    with patch("blackbeard.engine.loader.ResourceLoader._build_knowledge_source") as mock_build_ks:
        mock_ks = MagicMock()
        mock_build_ks.return_value = mock_ks
        loader.build_agent("ref:agents/smart-agent")

        mock_build_ks.assert_called_once_with("ref:knowledge-sources/my-docs")
        _, kwargs = mock_agent_cls.call_args
        assert "knowledge_sources" in kwargs
        assert kwargs["knowledge_sources"] == [mock_ks]


def test_build_knowledge_source_wrong_kind():
    """_build_knowledge_source with a non-KnowledgeSource resource returns None."""
    agent_res = make_resource(
        ResourceKind.AGENT,
        "not-ks",
        {"role": "R", "goal": "G", "backstory": "B"},
    )
    loader = ResourceLoader({"KnowledgeSource/not-ks": agent_res})
    result = loader._build_knowledge_source("ref:knowledge-sources/not-ks")
    assert result is None


def test_build_knowledge_source_unsupported_type():
    """_build_knowledge_source with an unsupported type returns None."""
    ks_res = make_resource(
        ResourceKind.KNOWLEDGE_SOURCE,
        "unknown-ks",
        {"type": "unknown_type"},
    )
    loader = ResourceLoader(_resource_map(ks_res))
    result = loader._build_knowledge_source("ref:knowledge-sources/unknown-ks")
    assert result is None


# ---------------------------------------------------------------------------
# Memory config tests
# ---------------------------------------------------------------------------


@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
def test_build_agent_memory_bool_true(mock_agent_cls, mock_llm_cls):
    """Agent with memory=True should pass memory=True to Agent."""
    agent_res = make_resource(
        ResourceKind.AGENT,
        "mem-agent",
        {"role": "R", "goal": "G", "backstory": "B", "memory": True},
    )
    loader = ResourceLoader(_resource_map(agent_res))
    loader.build_agent("ref:agents/mem-agent")

    _, kwargs = mock_agent_cls.call_args
    assert kwargs["memory"] is True


@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
def test_build_agent_memory_bool_false(mock_agent_cls, mock_llm_cls):
    """Agent with memory=False should pass memory=False to Agent."""
    agent_res = make_resource(
        ResourceKind.AGENT,
        "nomem-agent",
        {"role": "R", "goal": "G", "backstory": "B", "memory": False},
    )
    loader = ResourceLoader(_resource_map(agent_res))
    loader.build_agent("ref:agents/nomem-agent")

    _, kwargs = mock_agent_cls.call_args
    assert kwargs["memory"] is False


@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
def test_build_agent_memory_dict_disabled(mock_agent_cls, mock_llm_cls):
    """Agent with memory dict and enabled=False should pass memory=False."""
    agent_res = make_resource(
        ResourceKind.AGENT,
        "disabled-mem-agent",
        {"role": "R", "goal": "G", "backstory": "B", "memory": {"enabled": False}},
    )
    loader = ResourceLoader(_resource_map(agent_res))
    loader.build_agent("ref:agents/disabled-mem-agent")

    _, kwargs = mock_agent_cls.call_args
    assert kwargs["memory"] is False


# ---------------------------------------------------------------------------
# _validate_tool_config (security-critical path traversal protection)
# ---------------------------------------------------------------------------


@patch("blackbeard.engine.loader.importlib")
def test_build_tool_rejects_config_path_traversal(mock_importlib):
    """Tool config values with path traversal characters should raise LoaderError."""
    fake_cls = MagicMock(name="FakeTool")
    fake_module = ModuleType("crewai_tools.search")
    fake_module.SearchTool = fake_cls  # type: ignore[attr-defined]
    mock_importlib.import_module.return_value = fake_module

    tool_res = make_resource(
        ResourceKind.TOOL,
        "evil-cfg",
        {
            "type": "python",
            "class_path": "crewai_tools.search.SearchTool",
            "config": {"data_dir": "../../../etc/passwd"},
        },
    )
    loader = ResourceLoader(_resource_map(tool_res))
    with pytest.raises(LoaderError, match="path traversal"):
        loader.build_tool("ref:tools/evil-cfg")


@patch("blackbeard.engine.loader.importlib")
def test_build_tool_rejects_config_sensitive_path(mock_importlib):
    """Tool config values pointing to sensitive system paths should raise LoaderError."""
    fake_cls = MagicMock(name="FakeTool")
    fake_module = ModuleType("crewai_tools.read")
    fake_module.ReadTool = fake_cls  # type: ignore[attr-defined]
    mock_importlib.import_module.return_value = fake_module

    tool_res = make_resource(
        ResourceKind.TOOL,
        "secret-cfg",
        {
            "type": "python",
            "class_path": "crewai_tools.read.ReadTool",
            "config": {"path": "/etc/shadow"},
        },
    )
    loader = ResourceLoader(_resource_map(tool_res))
    with pytest.raises(LoaderError, match="not allowed"):
        loader.build_tool("ref:tools/secret-cfg")


# ---------------------------------------------------------------------------
# build_agent — forwarded kwargs (max_iter, max_rpm, cache)
# ---------------------------------------------------------------------------


@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
def test_build_agent_forwards_extra_kwargs(mock_agent_cls, mock_llm_cls):
    """max_iter, max_rpm, cache should be forwarded to Agent constructor."""
    agent_res = make_resource(
        ResourceKind.AGENT,
        "tuned-agent",
        {
            "role": "R",
            "goal": "G",
            "backstory": "B",
            "max_iter": 15,
            "max_rpm": 30,
            "cache": False,
        },
    )
    loader = ResourceLoader(_resource_map(agent_res))
    loader.build_agent("ref:agents/tuned-agent")

    _, kwargs = mock_agent_cls.call_args
    assert kwargs["max_iter"] == 15
    assert kwargs["max_rpm"] == 30
    assert kwargs["cache"] is False


# ---------------------------------------------------------------------------
# build_crew — memory config
# ---------------------------------------------------------------------------


@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
@patch("blackbeard.engine.loader.Task")
@patch("blackbeard.engine.loader.Crew")
def test_build_crew_memory_bool(mock_crew_cls, mock_task_cls, mock_agent_cls, mock_llm_cls):
    """Crew with memory=True should pass memory=True to Crew constructor."""
    agent_res = make_resource(
        ResourceKind.AGENT,
        "ag",
        {"role": "R", "goal": "G", "backstory": "B"},
    )
    task_res = make_resource(
        ResourceKind.TASK,
        "tk",
        {"description": "D", "expected_output": "E", "agent": "ref:agents/ag"},
    )
    crew_res = make_resource(
        ResourceKind.CREW,
        "mem-crew",
        {
            "process": "sequential",
            "agents": ["ref:agents/ag"],
            "tasks": ["ref:tasks/tk"],
            "memory": True,
        },
    )
    loader = ResourceLoader(_resource_map(agent_res, task_res, crew_res))
    loader.build_crew("mem-crew")

    _, kwargs = mock_crew_cls.call_args
    assert kwargs["memory"] is True


@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
@patch("blackbeard.engine.loader.Task")
@patch("blackbeard.engine.loader.Crew")
def test_build_crew_memory_dict(mock_crew_cls, mock_task_cls, mock_agent_cls, mock_llm_cls):
    """Crew with memory dict should extract enabled field."""
    agent_res = make_resource(
        ResourceKind.AGENT,
        "ag",
        {"role": "R", "goal": "G", "backstory": "B"},
    )
    task_res = make_resource(
        ResourceKind.TASK,
        "tk",
        {"description": "D", "expected_output": "E", "agent": "ref:agents/ag"},
    )
    crew_res = make_resource(
        ResourceKind.CREW,
        "dict-mem-crew",
        {
            "process": "sequential",
            "agents": ["ref:agents/ag"],
            "tasks": ["ref:tasks/tk"],
            "memory": {"enabled": True, "provider": "mem0"},
        },
    )
    loader = ResourceLoader(_resource_map(agent_res, task_res, crew_res))
    loader.build_crew("dict-mem-crew")

    _, kwargs = mock_crew_cls.call_args
    assert kwargs["memory"] is True


# ---------------------------------------------------------------------------
# Crew — embedder passthrough
# ---------------------------------------------------------------------------


@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
@patch("blackbeard.engine.loader.Task")
@patch("blackbeard.engine.loader.Crew")
def test_build_crew_embedder_passthrough(
    mock_crew_cls, mock_task_cls, mock_agent_cls, mock_llm_cls
):
    """Crew with embedder config should forward it to Crew constructor."""
    agent_res = make_resource(
        ResourceKind.AGENT,
        "ag",
        {"role": "R", "goal": "G", "backstory": "B"},
    )
    task_res = make_resource(
        ResourceKind.TASK,
        "tk",
        {"description": "D", "expected_output": "E", "agent": "ref:agents/ag"},
    )
    embedder_cfg = {"provider": "openai", "config": {"model": "text-embedding-3-small"}}
    crew_res = make_resource(
        ResourceKind.CREW,
        "embed-crew",
        {
            "process": "sequential",
            "agents": ["ref:agents/ag"],
            "tasks": ["ref:tasks/tk"],
            "embedder": embedder_cfg,
        },
    )
    loader = ResourceLoader(_resource_map(agent_res, task_res, crew_res))
    loader.build_crew("embed-crew")

    _, kwargs = mock_crew_cls.call_args
    assert kwargs["embedder"] == embedder_cfg


# ---------------------------------------------------------------------------
# Crew — cache and max_rpm forwarding
# ---------------------------------------------------------------------------


@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
@patch("blackbeard.engine.loader.Task")
@patch("blackbeard.engine.loader.Crew")
def test_build_crew_cache_and_max_rpm(mock_crew_cls, mock_task_cls, mock_agent_cls, mock_llm_cls):
    """Crew with cache and max_rpm should forward them to Crew constructor."""
    agent_res = make_resource(
        ResourceKind.AGENT,
        "ag",
        {"role": "R", "goal": "G", "backstory": "B"},
    )
    task_res = make_resource(
        ResourceKind.TASK,
        "tk",
        {"description": "D", "expected_output": "E", "agent": "ref:agents/ag"},
    )
    crew_res = make_resource(
        ResourceKind.CREW,
        "perf-crew",
        {
            "process": "sequential",
            "agents": ["ref:agents/ag"],
            "tasks": ["ref:tasks/tk"],
            "cache": True,
            "max_rpm": 60,
        },
    )
    loader = ResourceLoader(_resource_map(agent_res, task_res, crew_res))
    loader.build_crew("perf-crew")

    _, kwargs = mock_crew_cls.call_args
    assert kwargs["cache"] is True
    assert kwargs["max_rpm"] == 60


# ---------------------------------------------------------------------------
# Task — async_execution and human_input forwarding
# ---------------------------------------------------------------------------


@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
@patch("blackbeard.engine.loader.Task")
def test_build_task_async_and_human_input(mock_task_cls, mock_agent_cls, mock_llm_cls):
    """Task with async_execution and human_input should forward them."""
    agent_res = make_resource(
        ResourceKind.AGENT,
        "ag",
        {"role": "R", "goal": "G", "backstory": "B"},
    )
    task_res = make_resource(
        ResourceKind.TASK,
        "interactive-task",
        {
            "description": "D",
            "expected_output": "E",
            "agent": "ref:agents/ag",
            "async_execution": True,
            "human_input": True,
        },
    )
    loader = ResourceLoader(_resource_map(agent_res, task_res))
    loader.build_task("ref:tasks/interactive-task")

    _, kwargs = mock_task_cls.call_args
    assert kwargs["async_execution"] is True
    assert kwargs["human_input"] is True


# ---------------------------------------------------------------------------
# Agent — skills forwarding
# ---------------------------------------------------------------------------


@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
def test_build_agent_with_skills(mock_agent_cls, mock_llm_cls):
    """Agent with skills list should forward it to Agent constructor."""
    agent_res = make_resource(
        ResourceKind.AGENT,
        "skilled-agent",
        {
            "role": "Expert",
            "goal": "Be skilled",
            "backstory": "Trained",
            "skills": ["data/domain-instructions/"],
        },
    )
    loader = ResourceLoader(_resource_map(agent_res))
    loader.build_agent("ref:agents/skilled-agent")

    _, kwargs = mock_agent_cls.call_args
    assert kwargs["skills"] == ["data/domain-instructions/"]


# ---------------------------------------------------------------------------
# Agent — memory dict with custom weights → MemoryConfig
# ---------------------------------------------------------------------------


@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
def test_build_agent_memory_dict_with_weights(mock_agent_cls, mock_llm_cls):
    """Agent with memory dict including weights should create a MemoryConfig."""
    agent_res = make_resource(
        ResourceKind.AGENT,
        "weighted-mem-agent",
        {
            "role": "R",
            "goal": "G",
            "backstory": "B",
            "memory": {
                "enabled": True,
                "recency_weight": 0.5,
                "semantic_weight": 0.3,
                "importance_weight": 0.2,
            },
        },
    )
    loader = ResourceLoader(_resource_map(agent_res))

    with patch("crewai.memory.unified_memory.MemoryConfig") as mock_mem_cfg:
        mock_mem_cfg.return_value = "memory-config-sentinel"
        loader.build_agent("ref:agents/weighted-mem-agent")

        mock_mem_cfg.assert_called_once_with(
            recency_weight=0.5,
            semantic_weight=0.3,
            importance_weight=0.2,
        )
        _, kwargs = mock_agent_cls.call_args
        assert kwargs["memory"] == "memory-config-sentinel"


# ---------------------------------------------------------------------------
# Builtin tool name validation (security-critical)
# ---------------------------------------------------------------------------


def test_build_tool_builtin_rejects_unsafe_name():
    """Builtin tool with unsafe name (dunder, dots) should raise LoaderError."""
    tool_res = make_resource(
        ResourceKind.TOOL,
        "bad-builtin",
        {"type": "builtin", "class_path": "__import__"},
    )
    loader = ResourceLoader(_resource_map(tool_res))
    with pytest.raises(LoaderError, match="not a valid PascalCase"):
        loader.build_tool("ref:tools/bad-builtin")


def test_build_tool_builtin_rejects_dotted_name():
    """Builtin tool with dotted module path should raise LoaderError."""
    tool_res = make_resource(
        ResourceKind.TOOL,
        "dotted",
        {"type": "builtin", "class_path": "subprocess.run"},
    )
    loader = ResourceLoader(_resource_map(tool_res))
    with pytest.raises(LoaderError, match="not a valid PascalCase"):
        loader.build_tool("ref:tools/dotted")


# ---------------------------------------------------------------------------
# Tool config with nested path traversal in non-string values
# ---------------------------------------------------------------------------


@patch("blackbeard.engine.loader.importlib")
def test_build_tool_config_non_string_values_are_safe(mock_importlib):
    """Tool config with non-string values should not trigger path traversal check."""
    fake_cls = MagicMock(name="FakeTool")
    fake_module = ModuleType("crewai_tools.search")
    fake_module.SearchTool = fake_cls  # type: ignore[attr-defined]
    mock_importlib.import_module.return_value = fake_module

    tool_res = make_resource(
        ResourceKind.TOOL,
        "numeric-cfg",
        {
            "type": "python",
            "class_path": "crewai_tools.search.SearchTool",
            "config": {"count": 5, "enabled": True},
        },
    )
    loader = ResourceLoader(_resource_map(tool_res))
    result = loader.build_tool("ref:tools/numeric-cfg")
    assert result is fake_cls.return_value


# ---------------------------------------------------------------------------
# build_crew — hierarchical process
# ---------------------------------------------------------------------------


@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
@patch("blackbeard.engine.loader.Task")
@patch("blackbeard.engine.loader.Crew")
def test_build_crew_hierarchical_process_enum(
    mock_crew_cls, mock_task_cls, mock_agent_cls, mock_llm_cls
):
    """Crew with process='hierarchical' should set Process.hierarchical."""
    from crewai import Process

    llm_res = make_resource(
        ResourceKind.LLM_CONNECTION,
        "mgr-llm",
        {"provider": "openai", "model": "gpt-4o"},
    )
    agent_res = make_resource(
        ResourceKind.AGENT,
        "ag",
        {"role": "R", "goal": "G", "backstory": "B"},
    )
    task_res = make_resource(
        ResourceKind.TASK,
        "tk",
        {"description": "D", "expected_output": "E", "agent": "ref:agents/ag"},
    )
    crew_res = make_resource(
        ResourceKind.CREW,
        "hier-crew",
        {
            "process": "hierarchical",
            "agents": ["ref:agents/ag"],
            "tasks": ["ref:tasks/tk"],
            "manager_llm": "ref:llm-connections/mgr-llm",
        },
    )
    loader = ResourceLoader(_resource_map(llm_res, agent_res, task_res, crew_res))
    loader.build_crew("hier-crew")

    _, kwargs = mock_crew_cls.call_args
    assert kwargs["process"] is Process.hierarchical


# ---------------------------------------------------------------------------
# Hierarchical crew with manager_agent
# ---------------------------------------------------------------------------


@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
@patch("blackbeard.engine.loader.Task")
@patch("blackbeard.engine.loader.Crew")
def test_build_crew_hierarchical_with_manager_agent(
    mock_crew_cls, mock_task_cls, mock_agent_cls, mock_llm_cls
):
    """Hierarchical crew with manager_agent should wire the agent as manager."""
    agent_res = make_resource(
        ResourceKind.AGENT,
        "worker",
        {"role": "Worker", "goal": "G", "backstory": "B"},
    )
    manager_res = make_resource(
        ResourceKind.AGENT,
        "manager",
        {"role": "Manager", "goal": "Manage", "backstory": "Lead"},
    )
    task_res = make_resource(
        ResourceKind.TASK,
        "task-h",
        {"description": "D", "expected_output": "E", "agent": "ref:agents/worker"},
    )
    crew_res = make_resource(
        ResourceKind.CREW,
        "hier-mgr-crew",
        {
            "process": "hierarchical",
            "agents": ["ref:agents/worker"],
            "tasks": ["ref:tasks/task-h"],
            "manager_agent": "ref:agents/manager",
        },
    )
    loader = ResourceLoader(_resource_map(agent_res, manager_res, task_res, crew_res))
    loader.build_crew("hier-mgr-crew")

    _, kwargs = mock_crew_cls.call_args
    assert "manager_agent" in kwargs
    # manager_agent is built via build_agent, so it's a mock return value
    assert kwargs["manager_agent"] is mock_agent_cls.return_value


@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
@patch("blackbeard.engine.loader.Task")
@patch("blackbeard.engine.loader.Crew")
def test_build_crew_hierarchical_without_manager_raises(
    mock_crew_cls, mock_task_cls, mock_agent_cls, mock_llm_cls
):
    """Hierarchical crew without manager_llm or manager_agent should raise LoaderError."""
    agent_res = make_resource(
        ResourceKind.AGENT,
        "ag",
        {"role": "R", "goal": "G", "backstory": "B"},
    )
    task_res = make_resource(
        ResourceKind.TASK,
        "tk",
        {"description": "D", "expected_output": "E", "agent": "ref:agents/ag"},
    )
    crew_res = make_resource(
        ResourceKind.CREW,
        "bad-hier-crew",
        {
            "process": "hierarchical",
            "agents": ["ref:agents/ag"],
            "tasks": ["ref:tasks/tk"],
        },
    )
    loader = ResourceLoader(_resource_map(agent_res, task_res, crew_res))
    with pytest.raises(LoaderError, match=r"neither.*manager_llm.*nor.*manager_agent"):
        loader.build_crew("bad-hier-crew")


# ---------------------------------------------------------------------------
# Loader isolation — different loaders don't share caches
# ---------------------------------------------------------------------------


@patch("blackbeard.engine.loader.LLM")
def test_loader_caches_are_per_instance(mock_llm_cls):
    """Two ResourceLoader instances should have independent caches."""
    conn = make_resource(
        ResourceKind.LLM_CONNECTION,
        "shared-llm",
        {"provider": "openai", "model": "gpt-4o"},
    )
    loader1 = ResourceLoader(_resource_map(conn))
    loader2 = ResourceLoader(_resource_map(conn))

    loader1.build_llm("ref:llm-connections/shared-llm")
    loader2.build_llm("ref:llm-connections/shared-llm")

    # Each loader builds its own instance
    assert mock_llm_cls.call_count == 2

# ---------------------------------------------------------------------------
# Sandbox tier selection at agent load
# ---------------------------------------------------------------------------


@patch("blackbeard.engine.loader.importlib")
@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
@patch("blackbeard.engine.loader.logger")
def test_build_agent_selects_sandbox_tier(
    mock_logger, mock_agent_cls, mock_llm_cls, mock_importlib
):
    """Policy minimum promotes tool sandbox tier and emits structured log."""
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
            "description": "search",
            "sandbox": "none",
        },
    )
    agent = make_resource(
        ResourceKind.AGENT,
        "tooled",
        {
            "role": "r",
            "goal": "g",
            "backstory": "b",
            "tools": ["ref:tools/search"],
            "policy": "ref:agent-policies/strict",
        },
    )
    policy = make_resource(
        ResourceKind.AGENT_POLICY,
        "strict",
        {"sandbox": {"minimum_tier": "docker"}},
    )
    loader = ResourceLoader(
        _resource_map(tool, agent, policy),
        policies={"strict": policy.spec},
    )
    loader.build_agent("ref:agents/tooled")

    extras = [
        c.kwargs.get("extra")
        for c in mock_logger.info.call_args_list
        if c.kwargs.get("extra")
    ]
    tier_events = [e for e in extras if e and e.get("event") == "sandbox_tier_selected"]
    assert tier_events, "expected sandbox_tier_selected log event"
    assert tier_events[0]["effective_tier"] == "docker"
    assert tier_events[0]["tool_tier"] == "none"
    assert tier_events[0]["policy_minimum"] == "docker"
    assert tier_events[0]["tool_name"] == "search"
    assert tier_events[0]["agent_name"] == "tooled"


@patch("blackbeard.engine.loader.importlib")
@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
@patch("blackbeard.engine.loader.logger")
def test_build_agent_sandbox_default_none(
    mock_logger, mock_agent_cls, mock_llm_cls, mock_importlib
):
    """Without policy, tool sandbox default none stays none."""
    fake_tool_cls = MagicMock(name="PlainTool")
    fake_module = ModuleType("crewai_tools.plain")
    fake_module.PlainTool = fake_tool_cls  # type: ignore[attr-defined]
    mock_importlib.import_module.return_value = fake_module

    tool = make_resource(
        ResourceKind.TOOL,
        "plain",
        {
            "type": "python",
            "class_path": "crewai_tools.plain.PlainTool",
            "description": "plain",
        },
    )
    agent = make_resource(
        ResourceKind.AGENT,
        "a",
        {
            "role": "r",
            "goal": "g",
            "backstory": "b",
            "tools": ["ref:tools/plain"],
        },
    )
    loader = ResourceLoader(_resource_map(tool, agent))
    loader.build_agent("ref:agents/a")

    extras = [
        c.kwargs.get("extra")
        for c in mock_logger.info.call_args_list
        if c.kwargs.get("extra")
    ]
    tier_events = [e for e in extras if e and e.get("event") == "sandbox_tier_selected"]
    assert tier_events
    assert tier_events[0]["effective_tier"] == "none"

