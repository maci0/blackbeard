"""Tests for MuninnDB memory backend integration.

Covers the MuninnMemoryBackend adapter, schema validation for the
muninndb provider, and loader wiring.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from blackbeard.resources.validator import validate_resource
from tests.conftest import _resource_map, make_resource
from tests.conftest import has_validation_error as _has_error

# ---------------------------------------------------------------------------
# MuninnMemoryBackend unit tests (mock MuninnClient)
# ---------------------------------------------------------------------------


def test_muninn_backend_import_error_when_not_installed():
    """MuninnMemoryBackend should raise ImportError if muninn-python is missing."""
    with patch("blackbeard.engine.memory.muninn.HAS_MUNINN", False):
        from blackbeard.engine.memory.muninn import MuninnMemoryBackend

        with pytest.raises(ImportError, match="muninn-python"):
            MuninnMemoryBackend()


def test_muninn_backend_init_defaults():
    """MuninnMemoryBackend should store default configuration correctly."""
    with patch("blackbeard.engine.memory.muninn.HAS_MUNINN", True):
        from blackbeard.engine.memory.muninn import MuninnMemoryBackend

        backend = MuninnMemoryBackend(
            url="http://muninn:8475",
            agent_name="researcher",
            namespace="prod",
        )
        assert backend._url == "http://muninn:8475"
        assert backend._agent_name == "researcher"
        assert backend._namespace == "prod"
        assert backend._vault == "prod"  # defaults to namespace
        assert backend._token is None


def test_muninn_backend_init_custom_vault():
    """MuninnMemoryBackend should accept a custom vault name."""
    with patch("blackbeard.engine.memory.muninn.HAS_MUNINN", True):
        from blackbeard.engine.memory.muninn import MuninnMemoryBackend

        backend = MuninnMemoryBackend(vault="custom-vault")
        assert backend._vault == "custom-vault"


def test_muninn_backend_init_with_token():
    """MuninnMemoryBackend should accept an API token."""
    with patch("blackbeard.engine.memory.muninn.HAS_MUNINN", True):
        from blackbeard.engine.memory.muninn import MuninnMemoryBackend

        backend = MuninnMemoryBackend(token="secret-token")
        assert backend._token == "secret-token"


@pytest.mark.asyncio
async def test_muninn_backend_store_calls_write():
    """store() should call client.write() with correct parameters."""
    with patch("blackbeard.engine.memory.muninn.HAS_MUNINN", True):
        from blackbeard.engine.memory.muninn import MuninnMemoryBackend

        backend = MuninnMemoryBackend(
            url="http://test:8475",
            agent_name="researcher",
            namespace="default",
        )

        mock_result = MagicMock()
        mock_result.id = "engram-123"

        mock_client = AsyncMock()
        mock_client.write = AsyncMock(return_value=mock_result)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(backend, "_make_client", return_value=mock_client):
            engram_id = await backend.store(
                content="Test memory content",
                concept="test-concept",
                tags=["tag1", "tag2"],
                confidence=0.9,
            )

        mock_client.write.assert_awaited_once_with(
            vault="default",
            concept="test-concept",
            content="Test memory content",
            tags=["tag1", "tag2"],
            confidence=0.9,
        )
        assert engram_id == "engram-123"


@pytest.mark.asyncio
async def test_muninn_backend_store_defaults():
    """store() should use default concept and tags when not provided."""
    with patch("blackbeard.engine.memory.muninn.HAS_MUNINN", True):
        from blackbeard.engine.memory.muninn import MuninnMemoryBackend

        backend = MuninnMemoryBackend(
            url="http://test:8475",
            agent_name="my-agent",
            namespace="ns1",
        )

        mock_result = MagicMock()
        mock_result.id = "engram-456"

        mock_client = AsyncMock()
        mock_client.write = AsyncMock(return_value=mock_result)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(backend, "_make_client", return_value=mock_client):
            await backend.store(content="Some content")

        call_kwargs = mock_client.write.call_args[1]
        assert call_kwargs["concept"] == "agent_memory"
        assert call_kwargs["tags"] == ["my-agent", "ns1"]
        assert "confidence" not in call_kwargs


@pytest.mark.asyncio
async def test_muninn_backend_recall_calls_activate():
    """recall() should call client.activate() and return structured results."""
    with patch("blackbeard.engine.memory.muninn.HAS_MUNINN", True):
        from blackbeard.engine.memory.muninn import MuninnMemoryBackend

        backend = MuninnMemoryBackend(
            url="http://test:8475",
            agent_name="researcher",
            namespace="default",
        )

        mock_activation = MagicMock()
        mock_activation.content = "recalled content"
        mock_activation.concept = "test-concept"
        mock_activation.score = 0.95
        mock_activation.confidence = 0.8
        mock_activation.why = "semantic match"

        mock_result = MagicMock()
        mock_result.activations = [mock_activation]

        mock_client = AsyncMock()
        mock_client.activate = AsyncMock(return_value=mock_result)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(backend, "_make_client", return_value=mock_client):
            memories = await backend.recall(
                context="how does learning work?",
                limit=5,
                threshold=0.3,
            )

        mock_client.activate.assert_awaited_once_with(
            vault="default",
            context=["how does learning work?"],
            max_results=5,
            threshold=0.3,
            include_why=True,
        )
        assert len(memories) == 1
        assert memories[0]["content"] == "recalled content"
        assert memories[0]["concept"] == "test-concept"
        assert memories[0]["score"] == 0.95
        assert memories[0]["confidence"] == 0.8
        assert memories[0]["why"] == "semantic match"


def test_muninn_backend_search_sync():
    """search() should bridge async recall() into a synchronous call."""
    with patch("blackbeard.engine.memory.muninn.HAS_MUNINN", True):
        from blackbeard.engine.memory.muninn import MuninnMemoryBackend

        backend = MuninnMemoryBackend(
            url="http://test:8475",
            agent_name="researcher",
            namespace="default",
        )

        expected = [{"content": "result", "concept": "c", "score": 0.9}]

        with patch.object(backend, "recall", new_callable=AsyncMock, return_value=expected):
            results = backend.search("test query", limit=3)

        assert results == expected


# ---------------------------------------------------------------------------
# Schema validation tests for muninndb memory provider
# ---------------------------------------------------------------------------


def test_crew_schema_accepts_muninndb_provider():
    """Crew spec with memory provider='muninndb' should pass validation."""
    spec = {
        "process": "sequential",
        "agents": ["ref:agents/a"],
        "tasks": ["ref:tasks/t"],
        "memory": {
            "enabled": True,
            "provider": "muninndb",
            "muninndb_url": "http://muninn:8475",
        },
    }
    errors, _ = validate_resource("Crew", spec)
    assert errors == []


def test_crew_schema_accepts_muninndb_with_vault():
    """Crew spec with muninndb_vault should pass validation."""
    spec = {
        "process": "sequential",
        "agents": ["ref:agents/a"],
        "tasks": ["ref:tasks/t"],
        "memory": {
            "enabled": True,
            "provider": "muninndb",
            "muninndb_vault": "my-vault",
        },
    }
    errors, _ = validate_resource("Crew", spec)
    assert errors == []


def test_crew_schema_accepts_muninndb_with_token_env():
    """Crew spec with muninndb_token_env should pass validation."""
    spec = {
        "process": "sequential",
        "agents": ["ref:agents/a"],
        "tasks": ["ref:tasks/t"],
        "memory": {
            "enabled": True,
            "provider": "muninndb",
            "muninndb_token_env": "MUNINN_API_TOKEN",
        },
    }
    errors, _ = validate_resource("Crew", spec)
    assert errors == []


def test_crew_schema_rejects_invalid_muninndb_token_env():
    """Crew spec with invalid muninndb_token_env pattern should fail."""
    spec = {
        "process": "sequential",
        "agents": ["ref:agents/a"],
        "tasks": ["ref:tasks/t"],
        "memory": {
            "enabled": True,
            "provider": "muninndb",
            "muninndb_token_env": "lowercase-bad",
        },
    }
    errors, _ = validate_resource("Crew", spec)
    assert len(errors) > 0
    assert _has_error(errors, field_contains="memory")


def test_crew_schema_still_accepts_existing_providers():
    """Existing memory providers should still pass validation."""
    for provider in ("lancedb", "chromadb", "qdrant"):
        spec = {
            "process": "sequential",
            "agents": ["ref:agents/a"],
            "tasks": ["ref:tasks/t"],
            "memory": {"enabled": True, "provider": provider},
        }
        errors, _ = validate_resource("Crew", spec)
        assert errors == [], f"Provider {provider!r} should be valid, got {errors}"


# ---------------------------------------------------------------------------
# Loader wiring tests
# ---------------------------------------------------------------------------


from blackbeard.engine.loader import LoaderError, ResourceLoader
from blackbeard.kinds import ResourceKind


@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
@patch("blackbeard.engine.loader.Task")
@patch("blackbeard.engine.loader.Crew")
def test_build_crew_muninndb_memory_creates_backend(
    mock_crew_cls, mock_task_cls, mock_agent_cls, mock_llm_cls
):
    """build_crew with muninndb provider should build a MuninnMemoryBackend."""
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
        "muninn-crew",
        {
            "process": "sequential",
            "agents": ["ref:agents/ag"],
            "tasks": ["ref:tasks/tk"],
            "memory": {
                "enabled": True,
                "provider": "muninndb",
                "muninndb_url": "http://muninn:8475",
                "muninndb_vault": "test-vault",
            },
        },
    )
    loader = ResourceLoader(_resource_map(agent_res, task_res, crew_res))

    mock_backend = MagicMock()
    with patch.object(loader, "_build_muninndb_backend", return_value=mock_backend) as mock_build:
        loader.build_crew("muninn-crew")

        mock_build.assert_called_once()
        call_args = mock_build.call_args
        assert call_args[0][0]["provider"] == "muninndb"
        assert call_args[0][0]["muninndb_url"] == "http://muninn:8475"
        assert call_args[0][1] == "default"  # namespace


@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
@patch("blackbeard.engine.loader.Task")
@patch("blackbeard.engine.loader.Crew")
def test_build_crew_non_muninndb_memory_no_backend(
    mock_crew_cls, mock_task_cls, mock_agent_cls, mock_llm_cls
):
    """build_crew with non-muninndb provider should not build a MuninnMemoryBackend."""
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
        "normal-crew",
        {
            "process": "sequential",
            "agents": ["ref:agents/ag"],
            "tasks": ["ref:tasks/tk"],
            "memory": {"enabled": True, "provider": "lancedb"},
        },
    )
    loader = ResourceLoader(_resource_map(agent_res, task_res, crew_res))

    with patch.object(loader, "_build_muninndb_backend") as mock_build:
        loader.build_crew("normal-crew")
        mock_build.assert_not_called()


def test_build_muninndb_backend_method():
    """_build_muninndb_backend should construct a MuninnMemoryBackend with correct params."""
    loader = ResourceLoader({})

    with patch("blackbeard.engine.memory.muninn.HAS_MUNINN", True):
        backend = loader._build_muninndb_backend(
            {
                "provider": "muninndb",
                "muninndb_url": "http://custom:9999",
                "muninndb_vault": "my-vault",
            },
            namespace="prod",
        )

    assert backend._url == "http://custom:9999"
    assert backend._vault == "my-vault"
    assert backend._namespace == "prod"


def test_build_muninndb_backend_defaults():
    """_build_muninndb_backend should use settings defaults when not specified."""
    loader = ResourceLoader({})

    with patch("blackbeard.engine.memory.muninn.HAS_MUNINN", True):
        backend = loader._build_muninndb_backend(
            {"provider": "muninndb"},
            namespace="default",
        )

    assert backend._vault == "default"  # defaults to namespace


def test_build_muninndb_backend_import_error():
    """_build_muninndb_backend should raise LoaderError if muninn-python is missing."""
    loader = ResourceLoader({})

    with (
        patch("blackbeard.engine.memory.muninn.HAS_MUNINN", False),
        pytest.raises(LoaderError, match="muninn-python"),
    ):
        loader._build_muninndb_backend(
            {"provider": "muninndb"},
            namespace="default",
        )


def test_build_muninndb_backend_token_from_env(monkeypatch):
    """_build_muninndb_backend should read token from env var when configured."""
    monkeypatch.setenv("MUNINN_SECRET_TOKEN", "my-secret")
    loader = ResourceLoader({})

    with patch("blackbeard.engine.memory.muninn.HAS_MUNINN", True):
        backend = loader._build_muninndb_backend(
            {
                "provider": "muninndb",
                "muninndb_token_env": "MUNINN_SECRET_TOKEN",
            },
            namespace="default",
        )

    assert backend._token == "my-secret"
