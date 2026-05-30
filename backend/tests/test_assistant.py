"""Tests for the Copilot API and engine."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from blackbeard.engine.assistant import (
    AssistantError,
    NoLLMConnectionError,
    _parse_yaml_response,
    _strip_markdown_fences,
    _validate_and_filter,
    generate_resources,
)
from blackbeard.kinds import API_VERSION, ResourceKind

from .conftest import API_KEY_HEADER, make_resource

# ---------------------------------------------------------------------------
# Unit tests: YAML parsing helpers
# ---------------------------------------------------------------------------


class TestStripMarkdownFences:
    def test_no_fences(self):
        text = "---\napiVersion: blackbeard/v1\nkind: Agent"
        assert _strip_markdown_fences(text) == text.strip()

    def test_yaml_fence(self):
        text = "```yaml\n---\napiVersion: blackbeard/v1\nkind: Agent\n```"
        assert "```" not in _strip_markdown_fences(text)
        assert "apiVersion" in _strip_markdown_fences(text)

    def test_plain_fence(self):
        text = "```\n---\napiVersion: blackbeard/v1\nkind: Agent\n```"
        result = _strip_markdown_fences(text)
        assert "```" not in result
        assert "apiVersion" in result

    def test_yml_fence(self):
        text = "```yml\n---\napiVersion: blackbeard/v1\nkind: Agent\n```"
        result = _strip_markdown_fences(text)
        assert "```" not in result


class TestParseYamlResponse:
    def test_single_document(self):
        raw = f"""\
apiVersion: {API_VERSION}
kind: Agent
metadata:
  name: researcher
spec:
  role: Researcher
  goal: Find facts
  backstory: Expert researcher
"""
        docs = _parse_yaml_response(raw)
        assert len(docs) == 1
        assert docs[0]["kind"] == "Agent"

    def test_multi_document(self):
        raw = f"""\
---
apiVersion: {API_VERSION}
kind: Agent
metadata:
  name: researcher
spec:
  role: Researcher
  goal: Find facts
  backstory: Expert researcher
---
apiVersion: {API_VERSION}
kind: Task
metadata:
  name: research-task
spec:
  description: Research the topic
  expected_output: Key facts
  agent: "ref:agents/researcher"
"""
        docs = _parse_yaml_response(raw)
        assert len(docs) == 2
        assert docs[0]["kind"] == "Agent"
        assert docs[1]["kind"] == "Task"

    def test_invalid_yaml_raises(self):
        with pytest.raises(AssistantError, match="Failed to parse"):
            _parse_yaml_response("{{invalid yaml: [")

    def test_no_kind_skipped(self):
        raw = "foo: bar\nbaz: 1"
        with pytest.raises(AssistantError, match="did not return any valid"):
            _parse_yaml_response(raw)

    def test_with_markdown_fences(self):
        raw = f"""\
```yaml
---
apiVersion: {API_VERSION}
kind: Agent
metadata:
  name: test
spec:
  role: Test
  goal: Test goal
  backstory: Test backstory
```"""
        docs = _parse_yaml_response(raw)
        assert len(docs) == 1
        assert docs[0]["kind"] == "Agent"


class TestValidateAndFilter:
    def test_valid_agent(self):
        docs = [
            {
                "apiVersion": API_VERSION,
                "kind": "Agent",
                "metadata": {"name": "researcher"},
                "spec": {
                    "role": "Researcher",
                    "goal": "Find facts",
                    "backstory": "Expert",
                },
            }
        ]
        result = _validate_and_filter(docs)
        assert len(result) == 1
        assert result[0]["kind"] == "Agent"

    def test_invalid_agent_filtered_out(self):
        docs = [
            {
                "kind": "Agent",
                "metadata": {"name": "bad"},
                "spec": {
                    "role": "R",
                    # missing goal and backstory
                },
            }
        ]
        result = _validate_and_filter(docs)
        assert len(result) == 0

    def test_non_allowed_kind_filtered(self):
        docs = [
            {
                "kind": "Flow",
                "metadata": {"name": "f"},
                "spec": {"steps": [{"name": "s", "type": "crew"}]},
            }
        ]
        result = _validate_and_filter(docs)
        assert len(result) == 0

    def test_auto_generate_name(self):
        docs = [
            {
                "kind": "Agent",
                "spec": {
                    "role": "Research Analyst",
                    "goal": "Find facts",
                    "backstory": "Expert",
                },
            }
        ]
        result = _validate_and_filter(docs)
        assert len(result) == 1
        assert result[0]["metadata"]["name"] == "research-analyst"

    def test_valid_crew(self):
        docs = [
            {
                "kind": "Crew",
                "metadata": {"name": "test-crew"},
                "spec": {
                    "process": "sequential",
                    "agents": ["ref:agents/researcher"],
                    "tasks": ["ref:tasks/research"],
                },
            }
        ]
        result = _validate_and_filter(docs)
        assert len(result) == 1

    def test_mixed_valid_invalid(self):
        docs = [
            {
                "kind": "Agent",
                "metadata": {"name": "good"},
                "spec": {"role": "R", "goal": "G", "backstory": "B"},
            },
            {
                "kind": "Agent",
                "metadata": {"name": "bad"},
                "spec": {"role": "R"},  # missing required fields
            },
            {
                "kind": "Task",
                "metadata": {"name": "good-task"},
                "spec": {
                    "description": "D",
                    "expected_output": "E",
                    "agent": "ref:agents/good",
                },
            },
        ]
        result = _validate_and_filter(docs)
        assert len(result) == 2
        kinds = [d["kind"] for d in result]
        assert "Agent" in kinds
        assert "Task" in kinds


# ---------------------------------------------------------------------------
# Unit tests: generate_resources (mocked LLM)
# ---------------------------------------------------------------------------

_MOCK_LLM_YAML = f"""\
---
apiVersion: {API_VERSION}
kind: Agent
metadata:
  name: researcher
spec:
  role: Researcher
  goal: Find key facts about a topic
  backstory: An expert researcher with years of experience.
---
apiVersion: {API_VERSION}
kind: Task
metadata:
  name: research-task
spec:
  description: Research the given topic and list key facts.
  expected_output: A list of key facts.
  agent: "ref:agents/researcher"
---
apiVersion: {API_VERSION}
kind: Crew
metadata:
  name: research-crew
spec:
  process: sequential
  agents:
    - "ref:agents/researcher"
  tasks:
    - "ref:tasks/research-task"
"""


def _mock_llm_response(content: str = _MOCK_LLM_YAML, status: int = 200) -> httpx.Response:
    """Build a mock httpx.Response mimicking a LiteLLM chat completion."""
    if status != 200:
        return httpx.Response(status_code=status, json={"error": "test error"})
    return httpx.Response(
        status_code=200,
        json={
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 200, "total_tokens": 300},
        },
    )


@pytest.fixture
def llm_connection_resource(db_session):
    """Insert an LLMConnection resource into the test DB."""

    async def _insert(name: str = "test-llm", model: str = "llama3"):
        r = make_resource(
            ResourceKind.LLM_CONNECTION,
            name,
            {"provider": "ollama", "model": model},
        )
        db_session.add(r)
        await db_session.commit()
        return r

    return _insert


async def test_generate_resources_success(db_session, llm_connection_resource):
    await llm_connection_resource()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=_mock_llm_response())

    with patch("blackbeard.engine.assistant._get_assistant_client", return_value=mock_client):
        resources, explanation = await generate_resources(
            prompt="Build me a research crew",
            llm_connection_name="test-llm",
            project="default",
            session=db_session,
        )

    assert len(resources) == 3
    kinds = {r["kind"] for r in resources}
    assert kinds == {"Agent", "Task", "Crew"}
    assert "Generated" in explanation


async def test_generate_resources_no_llm_connection(db_session):
    with pytest.raises(NoLLMConnectionError, match="No LLMConnection found"):
        await generate_resources(
            prompt="Build me a research crew",
            llm_connection_name=None,
            project="default",
            session=db_session,
        )


async def test_generate_resources_specific_llm_not_found(db_session):
    with pytest.raises(NoLLMConnectionError, match="not found"):
        await generate_resources(
            prompt="Build me a research crew",
            llm_connection_name="nonexistent",
            project="default",
            session=db_session,
        )


async def test_generate_resources_llm_error(db_session, llm_connection_resource):
    await llm_connection_resource()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=_mock_llm_response(status=500))

    with patch("blackbeard.engine.assistant._get_assistant_client", return_value=mock_client):
        with pytest.raises(AssistantError, match="status 500"):
            await generate_resources(
                prompt="Build me a research crew",
                llm_connection_name="test-llm",
                project="default",
                session=db_session,
            )


async def test_generate_resources_rate_limited(db_session, llm_connection_resource):
    await llm_connection_resource()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=_mock_llm_response(status=429))

    with patch("blackbeard.engine.assistant._get_assistant_client", return_value=mock_client):
        with pytest.raises(AssistantError, match="rate limit"):
            await generate_resources(
                prompt="Build me a research crew",
                llm_connection_name="test-llm",
                project="default",
                session=db_session,
            )


async def test_generate_resources_empty_response(db_session, llm_connection_resource):
    await llm_connection_resource()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=_mock_llm_response(content=""))

    with patch("blackbeard.engine.assistant._get_assistant_client", return_value=mock_client):
        with pytest.raises(AssistantError, match="empty response"):
            await generate_resources(
                prompt="Build me a research crew",
                llm_connection_name="test-llm",
                project="default",
                session=db_session,
            )


async def test_generate_resources_transport_error(db_session, llm_connection_resource):
    await llm_connection_resource()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.ConnectError("connection refused"))

    with patch("blackbeard.engine.assistant._get_assistant_client", return_value=mock_client):
        with pytest.raises(AssistantError, match="unreachable"):
            await generate_resources(
                prompt="Build me a research crew",
                llm_connection_name="test-llm",
                project="default",
                session=db_session,
            )


async def test_generate_resources_auto_selects_llm(db_session, llm_connection_resource):
    """When no llm_connection_name is given, uses the first available."""
    await llm_connection_resource(name="my-llm", model="gpt-4")

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=_mock_llm_response())

    with patch("blackbeard.engine.assistant._get_assistant_client", return_value=mock_client):
        resources, _ = await generate_resources(
            prompt="Build me a research crew",
            llm_connection_name=None,
            project="default",
            session=db_session,
        )

    assert len(resources) == 3
    # Verify the model used was from the LLMConnection
    call_args = mock_client.post.call_args
    payload = call_args.kwargs.get("json") or call_args[1].get("json")
    assert payload["model"] == "ollama/gpt-4"


async def test_generate_resources_openai_provider(db_session):
    """OpenAI provider should not add prefix."""
    r = make_resource(
        ResourceKind.LLM_CONNECTION,
        "openai-llm",
        {"provider": "openai", "model": "gpt-4o"},
    )
    db_session.add(r)
    await db_session.commit()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=_mock_llm_response())

    with patch("blackbeard.engine.assistant._get_assistant_client", return_value=mock_client):
        await generate_resources(
            prompt="Build me a research crew",
            llm_connection_name="openai-llm",
            project="default",
            session=db_session,
        )

    call_args = mock_client.post.call_args
    payload = call_args.kwargs.get("json") or call_args[1].get("json")
    assert payload["model"] == "gpt-4o"


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


async def test_assistant_endpoint_short_prompt(client):
    """Prompt shorter than 10 chars should return 422."""
    resp = await client.post(
        "/api/v1/assistant/generate",
        json={"prompt": "short"},
        headers=API_KEY_HEADER,
    )
    assert resp.status_code == 422


async def test_assistant_endpoint_no_llm(client):
    """No LLMConnection in DB should return 424."""
    resp = await client.post(
        "/api/v1/assistant/generate",
        json={"prompt": "Build me a research crew that finds facts about topics"},
        headers=API_KEY_HEADER,
    )
    assert resp.status_code == 424
    data = resp.json()
    assert "llm connection" in data["detail"].lower()


async def test_assistant_endpoint_success(client, db_session):
    """Full success path with mocked LLM."""
    # Insert an LLMConnection
    r = make_resource(
        ResourceKind.LLM_CONNECTION,
        "test-llm",
        {"provider": "ollama", "model": "llama3"},
    )
    db_session.add(r)
    await db_session.commit()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=_mock_llm_response())

    with patch("blackbeard.engine.assistant._get_assistant_client", return_value=mock_client):
        resp = await client.post(
            "/api/v1/assistant/generate",
            json={"prompt": "Build me a research crew that finds facts about topics"},
            headers=API_KEY_HEADER,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "resources" in data
    assert "explanation" in data
    assert len(data["resources"]) == 3
    kinds = {r["kind"] for r in data["resources"]}
    assert kinds == {"Agent", "Task", "Crew"}


async def test_assistant_endpoint_llm_error(client, db_session):
    """LLM returning error should result in 502."""
    r = make_resource(
        ResourceKind.LLM_CONNECTION,
        "test-llm",
        {"provider": "ollama", "model": "llama3"},
    )
    db_session.add(r)
    await db_session.commit()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=_mock_llm_response(status=500))

    with patch("blackbeard.engine.assistant._get_assistant_client", return_value=mock_client):
        resp = await client.post(
            "/api/v1/assistant/generate",
            json={"prompt": "Build me a research crew that finds facts about topics"},
            headers=API_KEY_HEADER,
        )

    assert resp.status_code == 502


async def test_assistant_endpoint_specific_llm(client, db_session):
    """Request with specific llm_connection name."""
    r = make_resource(
        ResourceKind.LLM_CONNECTION,
        "my-special-llm",
        {"provider": "ollama", "model": "mistral"},
    )
    db_session.add(r)
    await db_session.commit()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=_mock_llm_response())

    with patch("blackbeard.engine.assistant._get_assistant_client", return_value=mock_client):
        resp = await client.post(
            "/api/v1/assistant/generate",
            json={
                "prompt": "Build me a research crew that finds facts about topics",
                "llm_connection": "my-special-llm",
            },
            headers=API_KEY_HEADER,
        )

    assert resp.status_code == 200
    # Verify the correct model was used
    call_args = mock_client.post.call_args
    payload = call_args.kwargs.get("json") or call_args[1].get("json")
    assert payload["model"] == "ollama/mistral"


async def test_assistant_endpoint_nonexistent_llm(client):
    """Requesting a nonexistent LLMConnection should return 424."""
    resp = await client.post(
        "/api/v1/assistant/generate",
        json={
            "prompt": "Build me a research crew that finds facts about topics",
            "llm_connection": "does-not-exist",
        },
        headers=API_KEY_HEADER,
    )
    assert resp.status_code == 424
    data = resp.json()
    assert "llm connection" in data["detail"].lower()
