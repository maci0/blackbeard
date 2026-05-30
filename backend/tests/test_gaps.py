"""Tests covering remaining gaps after the first review round.

Targeted areas:
  - Label selector parsing in the resource list API
  - Update metadata name/project mismatch rejection
  - Crew validation: empty tasks list (minItems enforcement)
  - _exceeds_depth edge cases (empty containers, lists of dicts)
  - _parse_kind case-insensitive lookup
  - ResourceResponse.from_db with None labels
  - ExecutionResponse.from_db with include_tasks=False
  - _check_path_safety sensitive-path branch for multiple prefixes
  - ResourceLoader._build_knowledge_source with string type
  - KickoffRequest: nested dict values (non-string) pass through
  - _extract_name in policy.py with ref vs. plain name
  - Crew empty-tasks validation at schema level
  - RefInfo __repr__ output
  - ResourceConflictError message format
  - ResourceNotFoundError attributes
  - ResourceValidationError aggregated message
  - Loader: output_file length > 255 rejected
  - _validate_tool_extra: command substitution via backtick
  - _validate_tool_extra: $() command substitution
  - is_internal_host: shared address space (100.64.x.x)
  - ModuleCache: put same key doesn't increase size
"""

import uuid
from decimal import Decimal
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from blackbeard.engine.loader import LoaderError, ResourceLoader, _check_path_safety
from blackbeard.engine.policy import _extract_name
from blackbeard.kinds import ResourceKind
from blackbeard.models.execution import TaskStatus
from blackbeard.models.execution_schemas import (
    ExecutionResponse,
    KickoffRequest,
)
from blackbeard.models.execution_schemas import (
    exceeds_depth as _exceeds_depth,
)
from blackbeard.models.resource import Resource
from blackbeard.models.resource_schemas import ResourceMetadata, ResourceResponse
from blackbeard.resources.exceptions import (
    ResourceConflictError,
    ResourceNotFoundError,
    ResourceValidationError,
)
from blackbeard.resources.exceptions import (
    ValidationError as ResValidationError,
)
from blackbeard.resources.refs import _MAX_REF_WALK_DEPTH, RefInfo, extract_refs
from blackbeard.resources.service import _parse_kind
from blackbeard.resources.validator import (
    _is_path_traversal,
    _validate_tool_extra,
    _validate_url_ssrf,
    is_internal_host,
    validate_resource,
)
from tests.conftest import (
    API_KEY_HEADER,
    _agent_payload,
    _make_execution,
    _resource_map,
    make_resource,
)

# ---------------------------------------------------------------------------
# _parse_kind: case-insensitive lookup
# ---------------------------------------------------------------------------


def test_parse_kind_exact_value():
    """_parse_kind('Agent') should return ResourceKind.AGENT."""
    assert _parse_kind("Agent") == ResourceKind.AGENT


def test_parse_kind_lowercase():
    """_parse_kind('agent') should return ResourceKind.AGENT via lowercase alias."""
    assert _parse_kind("agent") == ResourceKind.AGENT


def test_parse_kind_unknown_raises():
    """_parse_kind with unknown kind should raise ValueError."""
    with pytest.raises(ValueError, match="Unknown resource kind"):
        _parse_kind("Widget")


def test_parse_kind_all_kinds_lowercase():
    """All kinds should be resolvable via their lowercase form."""
    for kind in ResourceKind:
        result = _parse_kind(kind.value.lower())
        assert result == kind, f"Failed for {kind.value.lower()}"


# ---------------------------------------------------------------------------
# Label selector parsing (API integration)
# ---------------------------------------------------------------------------


async def test_list_with_valid_label_selector(client: AsyncClient):
    """GET /agents?label_selector=env=prod should parse and succeed."""
    response = await client.get(
        "/api/v1/agents?label_selector=env%3Dprod",
        headers=API_KEY_HEADER,
    )
    assert response.status_code == 200
    assert response.json()["total"] == 0  # no matching agents


async def test_list_with_invalid_label_selector(client: AsyncClient):
    """GET /agents?label_selector=invalid should return 400."""
    response = await client.get(
        "/api/v1/agents?label_selector=no-equals-sign",
        headers=API_KEY_HEADER,
    )
    assert response.status_code == 400
    assert "label selector" in response.json()["detail"].lower()


async def test_list_with_empty_key_label_selector(client: AsyncClient):
    """GET /agents?label_selector==value should return 400 (empty key)."""
    response = await client.get(
        "/api/v1/agents?label_selector=%3Dvalue",
        headers=API_KEY_HEADER,
    )
    assert response.status_code == 400
    assert "empty key" in response.json()["detail"].lower()


async def test_list_with_multi_label_selector(client: AsyncClient):
    """GET /agents?label_selector=env=prod,team=ml should parse both labels."""
    response = await client.get(
        "/api/v1/agents?label_selector=env%3Dprod%2Cteam%3Dml",
        headers=API_KEY_HEADER,
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Update metadata mismatch rejection
# ---------------------------------------------------------------------------


async def test_update_rejects_name_rename(client: AsyncClient):
    """PUT with metadata.name different from URL name should return 422."""
    r = await client.post("/api/v1/agents", json=_agent_payload(), headers=API_KEY_HEADER)
    assert r.status_code == 201

    update_payload = {
        "version": 1,
        "metadata": {"name": "different-name", "project": "default"},
        "spec": {"role": "R", "goal": "G", "backstory": "B"},
    }
    response = await client.put(
        "/api/v1/agents/researcher", json=update_payload, headers=API_KEY_HEADER
    )
    assert response.status_code == 422
    assert "rename" in response.json()["detail"].lower()


async def test_update_rejects_project_move(client: AsyncClient):
    """PUT with metadata.project different from URL project should return 422."""
    r = await client.post("/api/v1/agents", json=_agent_payload(), headers=API_KEY_HEADER)
    assert r.status_code == 201

    update_payload = {
        "version": 1,
        "metadata": {"name": "researcher", "project": "other-ns"},
        "spec": {"role": "R", "goal": "G", "backstory": "B"},
    }
    response = await client.put(
        "/api/v1/agents/researcher", json=update_payload, headers=API_KEY_HEADER
    )
    assert response.status_code == 422
    assert "project" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Crew validation: empty tasks list
# ---------------------------------------------------------------------------


def test_crew_empty_tasks_rejected():
    """Crew with empty tasks array should fail validation (minItems: 1)."""
    spec = {
        "process": "sequential",
        "agents": ["ref:agents/ag"],
        "tasks": [],
    }
    errors, _ = validate_resource("Crew", spec)
    assert len(errors) > 0
    assert any(e.field and "tasks" in e.field.lower() for e in errors), (
        f"Expected a validation error on 'tasks' field, got: {[e.to_dict() for e in errors]}"
    )


def test_crew_missing_tasks_rejected():
    """Crew without tasks field should fail validation."""
    spec = {
        "process": "sequential",
        "agents": ["ref:agents/ag"],
    }
    errors, _ = validate_resource("Crew", spec)
    assert len(errors) > 0
    error_text = " ".join(e.message.lower() for e in errors)
    assert "tasks" in error_text


# ---------------------------------------------------------------------------
# _exceeds_depth edge cases
# ---------------------------------------------------------------------------


def test_exceeds_depth_empty_dict():
    """Empty dict at the root should not exceed any depth."""
    assert _exceeds_depth({}) is False


def test_exceeds_depth_empty_list():
    """Empty list should not exceed any depth."""
    assert _exceeds_depth([]) is False


def test_exceeds_depth_list_of_dicts_at_limit():
    """A list of dicts exactly at the limit should return False."""
    obj = [{"a": 1}]
    assert _exceeds_depth(obj, limit=3) is False


def test_exceeds_depth_deeply_nested_lists():
    """Deeply nested lists should trigger depth check."""
    obj = [[[[[[[[[[["deep"]]]]]]]]]]]
    assert _exceeds_depth(obj, limit=5) is True


def test_exceeds_depth_bool():
    """Boolean root value should never exceed depth."""
    assert _exceeds_depth(True) is False
    assert _exceeds_depth(False) is False


def test_exceeds_depth_exactly_at_limit():
    """Nesting just under the limit returns False; at the limit returns True."""
    under_limit = {"a": {"b": "leaf"}}  # 2 levels of containers
    assert _exceeds_depth(under_limit, limit=3) is False
    at_limit = {"a": {"b": {"c": "leaf"}}}  # 3 levels → triggers at limit=3
    assert _exceeds_depth(at_limit, limit=3) is True


def test_exceeds_depth_mixed_dicts_and_lists():
    """Mixed dict/list nesting should count toward depth."""
    obj = {"a": [{"b": [{"c": "deep"}]}]}  # 5 levels: dict, list, dict, list, dict
    assert _exceeds_depth(obj, limit=3) is True
    assert _exceeds_depth(obj, limit=10) is False


# ---------------------------------------------------------------------------
# KickoffRequest: non-string values pass through
# ---------------------------------------------------------------------------


def test_kickoff_request_allows_nested_dict_values():
    """Non-string values like dicts and lists should be accepted."""
    req = KickoffRequest(inputs={"config": {"nested": True}, "items": [1, 2, 3]})
    assert req.inputs["config"]["nested"] is True
    assert req.inputs["items"] == [1, 2, 3]


def test_kickoff_request_allows_none_values():
    """None values in inputs should be accepted."""
    req = KickoffRequest(inputs={"optional_field": None})
    assert req.inputs["optional_field"] is None


def test_kickoff_request_allows_numeric_values():
    """Numeric values should be accepted without length checks."""
    req = KickoffRequest(inputs={"count": 42, "ratio": 3.14})
    assert req.inputs["count"] == 42


# ---------------------------------------------------------------------------
# ResourceResponse.from_db with None labels
# ---------------------------------------------------------------------------


def test_resource_response_from_db_none_labels():
    """from_db should handle None labels by defaulting to empty dict."""
    r = Resource()
    r.id = uuid.uuid4()
    r.kind = ResourceKind.AGENT
    r.name = "test"
    r.project = "default"
    r.spec = {"role": "R", "goal": "G", "backstory": "B"}
    r.version = 1
    r.labels = None
    r.created_at = None
    r.updated_at = None

    resp = ResourceResponse.from_db(r)
    assert resp.metadata.labels == {}


def test_resource_response_from_db_with_labels():
    """from_db with real labels should pass them through."""
    r = Resource()
    r.id = uuid.uuid4()
    r.kind = ResourceKind.TOOL
    r.name = "my-tool"
    r.project = "default"
    r.spec = {"type": "python", "class_path": "crewai_tools.Test"}
    r.version = 2
    r.labels = {"env": "prod"}
    r.created_at = None
    r.updated_at = None

    resp = ResourceResponse.from_db(r)
    assert resp.metadata.labels == {"env": "prod"}


# ---------------------------------------------------------------------------
# ExecutionResponse.from_db with include_tasks=False
# ---------------------------------------------------------------------------


def _make_exec_task(task_name: str = "some-task", agent_name: str = "some-agent"):
    """Build a detached ExecutionTask for unit tests."""
    from blackbeard.models.execution import ExecutionTask

    task = ExecutionTask()
    task.id = uuid.uuid4()
    task.task_name = task_name
    task.agent_name = agent_name
    task.order = 0
    task.status = TaskStatus.PENDING
    task.output = None
    task.error = None
    task.tokens_used = 0
    task.cost_usd = Decimal("0")
    task.started_at = None
    task.completed_at = None
    return task


def test_execution_response_from_db_no_tasks():
    """from_db with include_tasks=False should return empty tasks list."""
    e = _make_execution(inputs={"topic": "AI"}, tasks=[_make_exec_task()])

    resp = ExecutionResponse.from_db(e, include_tasks=False)
    assert resp.tasks == []
    assert resp.crew_name == "test-crew"


def test_execution_response_from_db_with_tasks():
    """from_db with include_tasks=True should include task data."""
    task = _make_exec_task(task_name="research", agent_name="researcher")
    e = _make_execution(
        status="running",
        inputs={},
        total_tokens=100,
        prompt_tokens=80,
        completion_tokens=20,
        cost_usd="0.01",
        tasks=[task],
    )

    resp = ExecutionResponse.from_db(e, include_tasks=True)
    assert len(resp.tasks) == 1
    assert resp.tasks[0].task_name == "research"
    assert resp.tasks[0].agent_name == "researcher"


# ---------------------------------------------------------------------------
# _check_path_safety: sensitive path prefixes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/etc/shadow",
        "/proc/self/environ",
        "/sys/class/net",
        "/dev/null",
        "/var/run/secrets/kubernetes.io",
    ],
)
def test_check_path_safety_rejects_sensitive_paths(path):
    """_check_path_safety should reject paths to sensitive directories."""
    with pytest.raises(LoaderError, match="not allowed"):
        _check_path_safety(path, "Test context")


def test_check_path_safety_rejects_traversal():
    """_check_path_safety should reject path traversal characters."""
    with pytest.raises(LoaderError, match="path traversal"):
        _check_path_safety("../../../etc/passwd", "Test context")


def test_check_path_safety_accepts_safe_path():
    """_check_path_safety should not raise for safe relative paths."""
    result = _check_path_safety("data/notes.txt", "Test context")
    assert result is None, "_check_path_safety should return None for safe paths"


# ---------------------------------------------------------------------------
# _extract_name in policy.py
# ---------------------------------------------------------------------------


def test_extract_name_from_ref():
    """_extract_name should extract the name from a ref string."""
    assert _extract_name("ref:agent-policies/strict") == "strict"


def test_extract_name_from_plain():
    """_extract_name should return plain names as-is."""
    assert _extract_name("plain-name") == "plain-name"


# ---------------------------------------------------------------------------
# RefInfo __repr__
# ---------------------------------------------------------------------------


def test_ref_info_repr():
    """RefInfo repr should include kind and name."""
    info = RefInfo(
        kind=ResourceKind.AGENT, name="researcher", raw="ref:agents/researcher", field="spec.agent"
    )
    r = repr(info)
    assert "Agent" in r
    assert "researcher" in r
    assert "spec.agent" in r


# ---------------------------------------------------------------------------
# Exception message formats
# ---------------------------------------------------------------------------


def test_resource_not_found_error_attributes():
    """ResourceNotFoundError should expose kind, name, project."""
    err = ResourceNotFoundError("Agent", "test-agent", "prod")
    assert err.kind == "Agent"
    assert err.name == "test-agent"
    assert err.project == "prod"
    assert "prod" in str(err)


def test_resource_conflict_error_message():
    """ResourceConflictError message should include versions."""
    err = ResourceConflictError("Agent", "test", 3, 5)
    msg = str(err)
    assert "3" in msg
    assert "5" in msg
    assert "Agent" in msg


def test_resource_validation_error_message():
    """ResourceValidationError should aggregate all error messages."""
    errs = [
        ResValidationError("spec.role", "Missing required field"),
        ResValidationError("spec.goal", "Too short"),
    ]
    exc = ResourceValidationError(errs)
    assert "role" in str(exc)
    assert "goal" in str(exc)
    assert len(exc.errors) == 2


# ---------------------------------------------------------------------------
# Loader: output_file length > 255 rejected
# ---------------------------------------------------------------------------


@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
@patch("blackbeard.engine.loader.Task")
def test_build_task_rejects_long_output_file(mock_task_cls, mock_agent_cls, mock_llm_cls):
    """output_file exceeding 255 chars should raise LoaderError."""
    agent_res = make_resource(
        ResourceKind.AGENT,
        "ag",
        {"role": "R", "goal": "G", "backstory": "B"},
    )
    task_res = make_resource(
        ResourceKind.TASK,
        "long-out-task",
        {
            "description": "D",
            "expected_output": "E",
            "agent": "ref:agents/ag",
            "output_file": "a" * 256 + ".txt",
        },
    )
    loader = ResourceLoader(_resource_map(agent_res, task_res))
    with pytest.raises(LoaderError, match="plain filename"):
        loader.build_task("ref:tasks/long-out-task")


# ---------------------------------------------------------------------------
# _validate_tool_extra: command substitution
# ---------------------------------------------------------------------------


def test_tool_env_blocks_backtick_command_substitution():
    """Tool env values with backticks should be rejected."""
    errors = []
    spec = {"type": "mcp-stdio", "command": "server", "env": {"MY_VAR": "`cat /etc/passwd`"}}
    _validate_tool_extra(spec, errors)
    assert any("command substitution" in e.message.lower() for e in errors)


def test_tool_env_blocks_dollar_paren_command_substitution():
    """Tool env values with $() should be rejected."""
    errors = []
    spec = {"type": "mcp-stdio", "command": "server", "env": {"MY_VAR": "$(cat /etc/shadow)"}}
    _validate_tool_extra(spec, errors)
    assert any("command substitution" in e.message.lower() for e in errors)


# ---------------------------------------------------------------------------
# is_internal_host: shared address space
# ---------------------------------------------------------------------------


def test_is_internal_host_shared_address_space():
    """100.64.0.0/10 (shared address space) should be detected as internal."""
    assert is_internal_host("100.64.0.1") is True
    assert is_internal_host("100.127.255.254") is True


def test_is_internal_host_just_outside_shared():
    """100.128.0.1 is outside 100.64.0.0/10 shared address space — public IP."""
    assert is_internal_host("100.128.0.1") is False


# ---------------------------------------------------------------------------
# extract_refs: max walk depth protection
# ---------------------------------------------------------------------------


def test_extract_refs_max_depth_protection():
    """extract_refs should stop recursing beyond _MAX_REF_WALK_DEPTH."""
    spec = {}
    current = spec
    for i in range(_MAX_REF_WALK_DEPTH + 5):
        current[f"level{i}"] = {}
        current = current[f"level{i}"]
    current["agent"] = "ref:agents/deep"

    refs = extract_refs(spec)
    assert len(refs) == 0


def test_extract_refs_within_depth_limit():
    """extract_refs should find refs within _MAX_REF_WALK_DEPTH."""
    spec = {"agent": "ref:agents/shallow"}
    refs = extract_refs(spec)
    assert len(refs) == 1
    assert refs[0].name == "shallow"


# ---------------------------------------------------------------------------
# _validate_url_ssrf: edge cases
# ---------------------------------------------------------------------------


def test_ssrf_rejects_file_scheme():
    """file:// scheme should be rejected."""
    errors = []
    _validate_url_ssrf("file:///etc/passwd", "test_field", errors)
    assert len(errors) > 0
    assert any("http" in e.message.lower() for e in errors)


def test_ssrf_rejects_javascript_scheme():
    """javascript: scheme should be rejected."""
    errors = []
    _validate_url_ssrf("javascript:alert(1)", "test_field", errors)
    assert len(errors) > 0


# ---------------------------------------------------------------------------
# ResourceMetadata label constraints
# ---------------------------------------------------------------------------


def test_resource_metadata_accepts_empty_labels():
    """Empty labels dict should be accepted."""
    meta = ResourceMetadata(name="test")
    assert meta.labels == {}


def test_resource_metadata_accepts_valid_labels():
    """Valid labels within size limits should be accepted."""
    meta = ResourceMetadata(name="test", labels={"env": "prod", "team": "ml"})
    assert meta.labels == {"env": "prod", "team": "ml"}


# ---------------------------------------------------------------------------
# Loader: tool caching (build_tool called twice returns cached)
# ---------------------------------------------------------------------------


@patch("blackbeard.engine.loader.importlib")
def test_build_tool_caches_by_ref(mock_importlib):
    """build_tool caches by ref string to avoid duplicate imports."""
    fake_cls = MagicMock(name="FakeTool")
    fake_module = ModuleType("crewai_tools.cache_test")
    fake_module.CacheTool = fake_cls
    mock_importlib.import_module.return_value = fake_module

    tool_res = make_resource(
        ResourceKind.TOOL,
        "cache-tool",
        {"type": "python", "class_path": "crewai_tools.cache_test.CacheTool"},
    )
    loader = ResourceLoader(_resource_map(tool_res))
    t1 = loader.build_tool("ref:tools/cache-tool")
    t2 = loader.build_tool("ref:tools/cache-tool")

    assert t1 is t2
    assert mock_importlib.import_module.call_count == 1
    assert fake_cls.call_count == 1


# ---------------------------------------------------------------------------
# Loader: build_crew with default tool_loading
# ---------------------------------------------------------------------------


@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
@patch("blackbeard.engine.loader.Task")
@patch("blackbeard.engine.loader.Crew")
def test_build_crew_default_tool_loading_is_hybrid(
    mock_crew_cls, mock_task_cls, mock_agent_cls, mock_llm_cls
):
    """Crew without explicit tool_loading should default to 'hybrid'."""
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
        "default-crew",
        {
            "process": "sequential",
            "agents": ["ref:agents/ag"],
            "tasks": ["ref:tasks/tk"],
        },
    )
    loader = ResourceLoader(_resource_map(agent_res, task_res, crew_res))

    with patch.object(loader, "_inject_discovery_tools") as mock_inject:
        loader.build_crew("default-crew")
        mock_inject.assert_called_once()
        assert mock_inject.call_args[0][2] == "hybrid"


# ---------------------------------------------------------------------------
# _is_path_traversal: edge cases
# ---------------------------------------------------------------------------


def test_path_traversal_dot_in_middle_is_safe():
    """A path with dots in filenames (not '..') should be safe."""
    assert _is_path_traversal("data/file.v2.txt") is False


def test_path_traversal_dot_dot_in_component():
    """A path with '..' as a path component should be unsafe."""
    assert _is_path_traversal("data/../secret.txt") is True


def test_path_traversal_windows_backslash():
    """Windows-style backslash paths should be detected."""
    assert _is_path_traversal("data\\..\\secret.txt") is True


# ---------------------------------------------------------------------------
# Loader: _build_knowledge_source with string type (integration path)
# ---------------------------------------------------------------------------


def test_build_knowledge_source_string_type():
    """_build_knowledge_source for type=string should call StringKnowledgeSource."""
    ks_res = make_resource(
        ResourceKind.KNOWLEDGE_SOURCE,
        "my-ks",
        {"type": "string", "content": "Important content."},
    )
    loader = ResourceLoader(_resource_map(ks_res))

    with patch("blackbeard.engine.loader.importlib") as mock_importlib:
        mock_cls = MagicMock()
        mock_module = MagicMock()
        mock_module.StringKnowledgeSource = mock_cls
        mock_importlib.import_module.return_value = mock_module

        result = loader._build_knowledge_source("ref:knowledge-sources/my-ks")

        mock_importlib.import_module.assert_called_once_with(
            "crewai.knowledge.source.string_knowledge_source"
        )
        mock_cls.assert_called_once_with(content="Important content.")
        assert result is mock_cls.return_value


# ---------------------------------------------------------------------------
# is_internal_host: IPv6 mapped IPv4
# ---------------------------------------------------------------------------


def test_is_internal_host_ipv6_mapped_ipv4():
    """IPv6-mapped IPv4 loopback (::ffff:127.0.0.1) should be internal."""
    assert is_internal_host("::ffff:127.0.0.1") is True


def test_is_internal_host_ipv6_mapped_private():
    """IPv6-mapped private IP should be internal."""
    assert is_internal_host("::ffff:10.0.0.1") is True


# ---------------------------------------------------------------------------
# ResourceMetadata: name with leading hyphen should be rejected
# ---------------------------------------------------------------------------


def test_resource_metadata_rejects_leading_hyphen():
    """Resource name starting with hyphen should fail NAME_PATTERN."""
    with pytest.raises(ValidationError):
        ResourceMetadata(name="-bad-name")


# ---------------------------------------------------------------------------
# Crew missing required fields: process
# ---------------------------------------------------------------------------


def test_crew_missing_process():
    """Crew without process field should fail validation."""
    spec = {
        "agents": ["ref:agents/ag"],
        "tasks": ["ref:tasks/tk"],
    }
    errors, _ = validate_resource("Crew", spec)
    assert len(errors) > 0
    error_text = " ".join(e.message.lower() for e in errors)
    assert "process" in error_text


# ---------------------------------------------------------------------------
# http_client.py: thread-safe lazy initialization
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("_clean_test_http_clients")
def test_get_client_returns_same_instance():
    """get_client should return the same AsyncClient for the same name."""
    from blackbeard.http_client import _clients, _lock, get_client

    name = "_test_async_dedup"
    with _lock:
        _clients.pop(name, None)

    c1 = get_client(name, timeout=5)
    c2 = get_client(name, timeout=99)
    assert c1 is c2


@pytest.mark.usefixtures("_clean_test_http_clients")
def test_get_sync_client_returns_same_instance():
    """get_sync_client should return the same Client for the same name."""
    from blackbeard.http_client import _lock, _sync_clients, get_sync_client

    name = "_test_sync_dedup"
    with _lock:
        _sync_clients.pop(name, None)

    c1 = get_sync_client(name, timeout=5)
    c2 = get_sync_client(name, timeout=99)
    assert c1 is c2


@pytest.mark.usefixtures("_clean_test_http_clients")
def test_get_client_different_names_different_instances():
    """get_client with different names should return different instances."""
    from blackbeard.http_client import _clients, _lock, get_client

    name_a = "_test_async_a"
    name_b = "_test_async_b"
    with _lock:
        _clients.pop(name_a, None)
        _clients.pop(name_b, None)

    a = get_client(name_a)
    b = get_client(name_b)
    assert a is not b


# ---------------------------------------------------------------------------
# discovery_tools.py: GetToolTool name validation
# ---------------------------------------------------------------------------


def test_get_tool_tool_rejects_invalid_name():
    """GetToolTool._run should reject tool names with invalid characters."""
    from blackbeard.engine.discovery_tools import GetToolTool

    tool = GetToolTool(
        api_url="http://localhost:8000",
        api_key="test-key",
        project="default",
    )
    result = tool._run("Invalid_Name!")
    assert "invalid" in result.lower()


def test_get_tool_tool_rejects_uppercase_name():
    """GetToolTool._run should reject uppercase tool names."""
    from blackbeard.engine.discovery_tools import GetToolTool

    tool = GetToolTool(
        api_url="http://localhost:8000",
        api_key="test-key",
        project="default",
    )
    result = tool._run("UpperCase")
    assert "Invalid tool name" in result
    assert "lowercase" in result


# ---------------------------------------------------------------------------
# _log_task_exception: branch coverage
# ---------------------------------------------------------------------------


def test_log_task_exception_cancelled():
    """log_task_exception should silently return for cancelled tasks."""
    import asyncio

    from blackbeard.logging_config import log_task_exception

    mock_task = MagicMock(spec=asyncio.Task)
    mock_task.cancelled.return_value = True

    log_task_exception(mock_task)
    mock_task.exception.assert_not_called()


def test_log_task_exception_no_exception():
    """log_task_exception should not log when task has no exception."""
    import asyncio

    from blackbeard.logging_config import log_task_exception

    mock_task = MagicMock(spec=asyncio.Task)
    mock_task.cancelled.return_value = False
    mock_task.exception.return_value = None

    log_task_exception(mock_task)


def test_log_task_exception_with_exception():
    """_log_task_exception should log an error when task has an exception."""
    import asyncio

    from blackbeard.logging_config import log_task_exception

    mock_task = MagicMock(spec=asyncio.Task)
    mock_task.cancelled.return_value = False
    exc = RuntimeError("boom")
    mock_task.exception.return_value = exc
    mock_task.get_name.return_value = "test-task"

    mock_logger = MagicMock()
    with patch("logging.getLogger", return_value=mock_logger):
        log_task_exception(mock_task)
    mock_logger.error.assert_called_once()
    args, kwargs = mock_logger.error.call_args
    assert "test-task" in args[1]
    assert args[2] is exc
    assert kwargs["extra"]["task_name"] == "test-task"
    assert kwargs["extra"]["error_type"] == "RuntimeError"


# ---------------------------------------------------------------------------
# _validate_function_path: security-critical guardrail validation
# ---------------------------------------------------------------------------


def test_validate_function_path_allows_crewai():
    """function_path starting with crewai. should be allowed."""
    from blackbeard.resources.validator import _validate_function_path

    errors = []
    spec = {"function_path": "crewai.guardrails.check_pii"}
    _validate_function_path(spec, "spec.function_path", errors)
    assert errors == []


def test_validate_function_path_blocks_os_module():
    """function_path referencing the os module should be blocked."""
    from blackbeard.resources.validator import _validate_function_path

    errors = []
    # Use a realistic dangerous path: os.popen
    spec = {"function_path": "os.popen"}
    _validate_function_path(spec, "spec.function_path", errors)
    assert len(errors) > 0
    assert "blocked" in errors[0].message.lower()


def test_validate_function_path_blocks_subprocess_module():
    """function_path referencing subprocess should be blocked."""
    from blackbeard.resources.validator import _validate_function_path

    errors = []
    spec = {"function_path": "subprocess.run"}
    _validate_function_path(spec, "spec.function_path", errors)
    assert len(errors) > 0
    assert "blocked" in errors[0].message.lower()


def test_validate_function_path_blocks_arbitrary_module():
    """function_path not in allowlist should be rejected."""
    from blackbeard.resources.validator import _validate_function_path

    errors = []
    spec = {"function_path": "mycompany.dangerous.function"}
    _validate_function_path(spec, "spec.function_path", errors)
    assert len(errors) > 0
    assert "allowed" in errors[0].message.lower()


def test_validate_function_path_allows_blackbeard_guardrails():
    """function_path starting with blackbeard.guardrails. should be allowed."""
    from blackbeard.resources.validator import _validate_function_path

    errors = []
    spec = {"function_path": "blackbeard.guardrails.check_pii"}
    _validate_function_path(spec, "spec.function_path", errors)
    assert errors == []


def test_validate_function_path_skips_empty():
    """Missing or empty function_path should not produce errors."""
    from blackbeard.resources.validator import _validate_function_path

    errors = []
    _validate_function_path({}, "spec.function_path", errors)
    assert errors == []

    errors = []
    _validate_function_path({"function_path": ""}, "spec.function_path", errors)
    assert errors == []


# ---------------------------------------------------------------------------
# _validate_flow_extra: function_path validation in flow steps
# ---------------------------------------------------------------------------


def test_validate_flow_extra_blocks_dangerous_function_path():
    """Flow step with function_path referencing subprocess should be blocked."""
    from blackbeard.resources.validator import _validate_flow_extra

    errors = []
    spec = {
        "steps": [
            {"name": "evil", "type": "function", "function_path": "subprocess:run"},
        ]
    }
    _validate_flow_extra(spec, errors)
    assert len(errors) > 0
    assert "blocked" in errors[0].message.lower()


def test_validate_flow_extra_allows_safe_function_path():
    """Flow step with function_path in allowlist should pass."""
    from blackbeard.resources.validator import _validate_flow_extra

    errors = []
    spec = {
        "steps": [
            {"name": "safe", "type": "function", "function_path": "blackbeard.flows.my_func:run"},
        ]
    }
    _validate_flow_extra(spec, errors)
    assert errors == []


def test_validate_flow_extra_skips_crew_steps():
    """Flow step with type=crew and no function_path should pass without errors."""
    from blackbeard.resources.validator import _validate_flow_extra

    errors = []
    spec = {
        "steps": [
            {"name": "step-1", "type": "crew", "crew": "ref:crews/my-crew"},
        ]
    }
    _validate_flow_extra(spec, errors)
    assert errors == []


# ---------------------------------------------------------------------------
# Guardrail: validate_resource integration with _validate_function_path
# ---------------------------------------------------------------------------


def test_guardrail_blocks_dangerous_function_path():
    """Guardrail with function_path referencing os.popen should be blocked."""
    spec = {
        "type": "function",
        "function_path": "os.popen",
        "on_fail": "reject",
    }
    errors, _ = validate_resource("Guardrail", spec)
    assert len(errors) > 0
    blocked_errors = [e for e in errors if "blocked" in e.message.lower()]
    assert len(blocked_errors) > 0


def test_guardrail_allows_safe_function_path():
    """Guardrail with function_path in allowlist should pass."""
    spec = {
        "type": "function",
        "function_path": "blackbeard.guardrails.check_pii",
        "on_fail": "reject",
    }
    errors, _ = validate_resource("Guardrail", spec)
    assert errors == []


# ---------------------------------------------------------------------------
# ExecutionNotFoundError: subclass of ExecutionError
# ---------------------------------------------------------------------------


def test_execution_not_found_error_is_execution_error():
    """ExecutionNotFoundError should be a subclass of ExecutionError."""
    from blackbeard.engine.executor import ExecutionError, ExecutionNotFoundError

    err = ExecutionNotFoundError("Crew 'x' not found")
    assert isinstance(err, ExecutionError)
    assert isinstance(err, Exception)
    assert "not found" in str(err)


# ---------------------------------------------------------------------------
# _validate_crew_extra: embedder SSRF and credential exfiltration
# ---------------------------------------------------------------------------


def test_crew_embedder_blocks_internal_url():
    """Crew embedder config with internal URL should be flagged."""
    from blackbeard.resources.validator import _validate_crew_extra

    errors = []
    spec = {
        "process": "sequential",
        "agents": ["ref:agents/ag"],
        "tasks": ["ref:tasks/tk"],
        "embedder": {
            "provider": "openai",
            "config": {"url": "http://localhost:8080/embed"},
        },
    }
    _validate_crew_extra(spec, errors)
    assert len(errors) > 0


def test_crew_embedder_blocks_credential_env_ref():
    """Crew embedder config with api_key referencing internal env should be flagged."""
    from blackbeard.resources.validator import _validate_crew_extra

    errors = []
    spec = {
        "process": "sequential",
        "agents": ["ref:agents/ag"],
        "tasks": ["ref:tasks/tk"],
        "embedder": {
            "provider": "openai",
            "config": {"api_key": "BLACKBEARD_DB_SECRET"},
        },
    }
    _validate_crew_extra(spec, errors)
    assert len(errors) > 0


# ---------------------------------------------------------------------------
# _is_path_traversal: null byte
# ---------------------------------------------------------------------------


def test_path_traversal_null_byte():
    """Paths with unusual characters should be detected by the safe pattern."""
    assert _is_path_traversal("file\x00.txt") is True


# ---------------------------------------------------------------------------
# Loader: _resolve_ref with non-ref string
# ---------------------------------------------------------------------------


def test_loader_resolve_ref_non_ref_string():
    """_resolve_ref with a plain string (not a ref) should raise LoaderError."""
    loader = ResourceLoader({})
    with pytest.raises(LoaderError, match="not a valid ref"):
        loader._resolve_ref("just-a-name")


# ---------------------------------------------------------------------------
# Loader: build_agent without LLM (no llm ref in spec)
# ---------------------------------------------------------------------------


@patch("blackbeard.engine.loader.Agent")
def test_build_agent_without_llm(mock_agent_cls):
    """Agent without llm ref should not include llm in kwargs."""
    agent_res = make_resource(
        ResourceKind.AGENT,
        "no-llm-agent",
        {"role": "R", "goal": "G", "backstory": "B"},
    )
    loader = ResourceLoader(_resource_map(agent_res))
    loader.build_agent("ref:agents/no-llm-agent")

    _, kwargs = mock_agent_cls.call_args
    assert "llm" not in kwargs
    assert kwargs["role"] == "R"
