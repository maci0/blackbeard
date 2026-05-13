"""Unit tests for ResourceLoader.

Tests build CrewAI objects from Resource stubs without hitting a real database
or making actual LLM/CrewAI API calls. crewai.Agent, crewai.Task, crewai.Crew,
and litellm.LLM are all mocked so no network traffic is produced.
"""

from unittest.mock import patch

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
    """vertex_ai provider should build model string as 'vertex_ai/<model>'."""
    conn = make_resource(
        ResourceKind.LLM_CONNECTION,
        "my-llm",
        {"provider": "vertex_ai", "model": "claude-sonnet-4-6"},
    )
    loader = ResourceLoader(_resource_map(conn))
    loader.build_llm("ref:llm-connections/my-llm")

    mock_llm_cls.assert_called_once()
    _, kwargs = mock_llm_cls.call_args
    assert kwargs["model"] == "vertex_ai/claude-sonnet-4-6"


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
