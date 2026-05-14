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
from blackbeard.models.resource import Resource

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def make_resource(kind: ResourceKind, name: str, spec: dict) -> Resource:
    """Create a detached Resource ORM object without a database session."""
    r = Resource()
    r.kind = kind
    r.name = name
    r.namespace = "default"
    r.spec = spec
    return r


def _resource_map(*resources: Resource) -> dict[str, Resource]:
    return {f"{r.kind.value}/{r.name}": r for r in resources}


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
    assert kwargs["model"] == "claude-sonnet-4-6"


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
    assert kwargs["model"] == "gpt-4o"


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
    fake_module = ModuleType("my_package.tools")
    fake_module.SearchTool = fake_cls  # type: ignore[attr-defined]
    mock_importlib.import_module.return_value = fake_module

    tool_res = make_resource(
        ResourceKind.TOOL,
        "search",
        {"type": "python", "class_path": "my_package.tools.SearchTool", "config": {"k": 5}},
    )
    loader = ResourceLoader(_resource_map(tool_res))
    result = loader.build_tool("ref:tools/search")

    mock_importlib.import_module.assert_called_once_with("my_package.tools")
    fake_cls.assert_called_once_with(k=5)
    assert result is fake_cls.return_value


@patch("blackbeard.engine.loader.importlib")
def test_build_tool_python_no_config(mock_importlib):
    """Tool with type=python and no config should pass empty kwargs."""
    fake_cls = MagicMock(name="PlainTool")
    fake_module = ModuleType("tools")
    fake_module.PlainTool = fake_cls  # type: ignore[attr-defined]
    mock_importlib.import_module.return_value = fake_module

    tool_res = make_resource(
        ResourceKind.TOOL,
        "plain",
        {"type": "python", "class_path": "tools.PlainTool"},
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


@patch("blackbeard.engine.loader.importlib")
def test_build_tool_builtin(mock_importlib):
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
    fake_module = ModuleType("my_tools")
    fake_module.SearchTool = fake_tool_cls  # type: ignore[attr-defined]
    mock_importlib.import_module.return_value = fake_module

    tool_res = make_resource(
        ResourceKind.TOOL,
        "search",
        {"type": "python", "class_path": "my_tools.SearchTool"},
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

    with patch(
        "blackbeard.engine.loader.ResourceLoader._build_knowledge_source"
    ) as mock_build_ks:
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
