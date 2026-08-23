"""Tests for PII redaction module (blackbeard.pii)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from blackbeard.pii import redact_dict, redact_text, reset_engines

# ---------------------------------------------------------------------------
# Shared fixture — reset Presidio singletons before each test so that tests
# are independent regardless of execution order.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_pii_engines():
    reset_engines()


# ---------------------------------------------------------------------------
# redact_text
# ---------------------------------------------------------------------------


class TestRedactText:
    """Tests for redact_text()."""

    def test_redact_email(self):
        text = "Contact john.doe@example.com for details."
        result = redact_text(text)
        assert "john.doe@example.com" not in result
        assert "<EMAIL_ADDRESS>" in result

    def test_redact_phone_number(self):
        text = "Call me at 212-555-1234 for more info."
        result = redact_text(text)
        assert "212-555-1234" not in result
        assert "<PHONE_NUMBER>" in result

    def test_no_pii_unchanged(self):
        text = "The weather is sunny today."
        result = redact_text(text)
        assert result == text

    def test_empty_string(self):
        assert redact_text("") == ""

    def test_redact_specific_entities(self):
        text = "Email john.doe@example.com or call 212-555-1234."
        result = redact_text(text, entities=["EMAIL_ADDRESS"])
        assert "john.doe@example.com" not in result
        assert "<EMAIL_ADDRESS>" in result
        # Phone number should remain (only EMAIL_ADDRESS entity requested)
        assert "212-555-1234" in result

    def test_redact_credit_card(self):
        text = "My card number is 4111111111111111."
        result = redact_text(text, entities=["CREDIT_CARD"])
        assert "4111111111111111" not in result
        assert "<CREDIT_CARD>" in result


# ---------------------------------------------------------------------------
# redact_dict
# ---------------------------------------------------------------------------


class TestRedactDict:
    """Tests for redact_dict()."""

    def test_nested_pii(self):
        data = {
            "result": "Contact john.doe@example.com",
            "metadata": {
                "phone": "Call 212-555-1234",
            },
        }
        result = redact_dict(data)
        assert "john.doe@example.com" not in result["result"]
        assert "<EMAIL_ADDRESS>" in result["result"]
        assert "212-555-1234" not in result["metadata"]["phone"]
        assert "<PHONE_NUMBER>" in result["metadata"]["phone"]
        assert "john.doe@example.com" in data["result"], "Original dict must not be mutated"

    def test_non_string_values_unchanged(self):
        data = {
            "count": 42,
            "active": True,
            "score": 3.14,
            "nothing": None,
        }
        result = redact_dict(data)
        assert result == data

    def test_max_depth_respected(self):
        data = {
            "level1": {
                "level2": {
                    "email": "john.doe@example.com",
                },
            },
        }
        # max_depth=1: only top-level string values are redacted
        result = redact_dict(data, max_depth=1)
        # The nested email should NOT be redacted because depth limit was hit
        assert result["level1"]["level2"]["email"] == "john.doe@example.com"

    def test_lists_in_dict(self):
        data = {
            "contacts": ["john.doe@example.com", "jane.doe@example.com"],
        }
        result = redact_dict(data)
        for item in result["contacts"]:
            assert "@example.com" not in item
            assert "<EMAIL_ADDRESS>" in item


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


class TestPIISchemaValidation:
    """Tests that PII config validates in AgentPolicy and Guardrail schemas."""

    def test_agent_policy_pii_config_valid(self):
        import jsonschema

        from blackbeard.resources.spec_schemas import AGENT_POLICY_SCHEMA

        spec = {
            "pii": {
                "enabled": True,
                "backend": "default",
                "entities": ["EMAIL_ADDRESS", "PHONE_NUMBER"],
                "redact_outputs": True,
                "redact_events": True,
            },
        }
        jsonschema.validate(spec, AGENT_POLICY_SCHEMA)

    def test_agent_policy_pii_litellm_backend(self):
        import jsonschema

        from blackbeard.resources.spec_schemas import AGENT_POLICY_SCHEMA

        spec = {
            "pii": {
                "enabled": True,
                "backend": "litellm",
                "model": "ollama/gliner-pii",
            },
        }
        jsonschema.validate(spec, AGENT_POLICY_SCHEMA)

    def test_agent_policy_pii_invalid_backend(self):
        import jsonschema

        from blackbeard.resources.spec_schemas import AGENT_POLICY_SCHEMA

        spec = {
            "pii": {
                "enabled": True,
                "backend": "invalid-backend",
            },
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(spec, AGENT_POLICY_SCHEMA)

    def test_agent_policy_pii_no_additional_properties(self):
        import jsonschema

        from blackbeard.resources.spec_schemas import AGENT_POLICY_SCHEMA

        spec = {
            "pii": {
                "enabled": True,
                "extra_field": "not-allowed",
            },
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(spec, AGENT_POLICY_SCHEMA)

    def test_guardrail_pii_type_valid(self):
        import jsonschema

        from blackbeard.resources.spec_schemas import GUARDRAIL_SCHEMA

        spec = {
            "type": "pii",
            "pii_entities": ["EMAIL_ADDRESS", "CREDIT_CARD"],
            "pii_action": "redact",
        }
        jsonschema.validate(spec, GUARDRAIL_SCHEMA)

    def test_guardrail_pii_backend_and_model_valid(self):
        """Studio emits backend/model fields for PII guardrails; schema must admit them."""
        import jsonschema

        from blackbeard.resources.spec_schemas import GUARDRAIL_SCHEMA

        spec = {
            "type": "pii",
            "pii_entities": ["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD"],
            "pii_action": "redact",
            "backend": "default",
            "model": "ollama/gliner-pii",
        }
        jsonschema.validate(spec, GUARDRAIL_SCHEMA)

    def test_guardrail_pii_invalid_backend(self):
        import jsonschema

        from blackbeard.resources.spec_schemas import GUARDRAIL_SCHEMA

        spec = {
            "type": "pii",
            "backend": "invalid-backend",
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(spec, GUARDRAIL_SCHEMA)

    def test_guardrail_pii_type_reject_action(self):
        import jsonschema

        from blackbeard.resources.spec_schemas import GUARDRAIL_SCHEMA

        spec = {
            "type": "pii",
            "pii_entities": ["PERSON"],
            "pii_action": "reject",
        }
        jsonschema.validate(spec, GUARDRAIL_SCHEMA)

    def test_guardrail_pii_invalid_action(self):
        import jsonschema

        from blackbeard.resources.spec_schemas import GUARDRAIL_SCHEMA

        spec = {
            "type": "pii",
            "pii_action": "delete",
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(spec, GUARDRAIL_SCHEMA)


# ---------------------------------------------------------------------------
# LLMPIIRecognizer
# ---------------------------------------------------------------------------


class TestLLMPIIRecognizer:
    """Tests for the LLM-based PII recognizer."""

    def test_llm_recognizer_success(self):
        from blackbeard.pii import LLMPIIRecognizer

        recognizer = LLMPIIRecognizer(model="test-model", proxy_url="http://localhost:4000")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": (
                            '[{"entity_type": "EMAIL_ADDRESS",'
                            ' "start": 0, "end": 20, "score": 0.95}]'
                        )
                    }
                }
            ]
        }

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response

        with patch("blackbeard.http_client.get_sync_client", return_value=mock_client):
            results = recognizer.analyze("john.doe@example.com", entities=["EMAIL_ADDRESS"])

        assert len(results) == 1
        assert results[0].entity_type == "EMAIL_ADDRESS"
        assert results[0].start == 0
        assert results[0].end == 20
        assert results[0].score == 0.95

    def test_llm_recognizer_http_error(self):
        from blackbeard.pii import LLMPIIRecognizer

        recognizer = LLMPIIRecognizer(model="test-model", proxy_url="http://localhost:4000")

        mock_response = MagicMock()
        mock_response.status_code = 500

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response

        with patch("blackbeard.http_client.get_sync_client", return_value=mock_client):
            with pytest.raises(RuntimeError, match="HTTP 500"):
                recognizer.analyze("some text", entities=["PERSON"])

    def test_llm_recognizer_connection_error(self):
        from blackbeard.pii import LLMPIIRecognizer

        recognizer = LLMPIIRecognizer(model="test-model", proxy_url="http://localhost:4000")

        mock_client = MagicMock()
        mock_client.post.side_effect = ConnectionError("Connection refused")

        with patch("blackbeard.http_client.get_sync_client", return_value=mock_client):
            with pytest.raises(ConnectionError):
                recognizer.analyze("some text", entities=["PERSON"])

    def test_llm_recognizer_malformed_json(self):
        from blackbeard.pii import LLMPIIRecognizer

        recognizer = LLMPIIRecognizer(model="test-model", proxy_url="http://localhost:4000")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"choices": [{"message": {"content": "not valid json"}}]}

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response

        with patch("blackbeard.http_client.get_sync_client", return_value=mock_client):
            results = recognizer.analyze("some text", entities=["PERSON"])
            assert results == []


# ---------------------------------------------------------------------------
# _get_pii_config (executor integration)
# ---------------------------------------------------------------------------


class TestGetPIIConfig:
    """Tests for PII config resolution from resource snapshots."""

    def test_returns_none_when_no_pii_policy(self):
        from blackbeard.engine.budget import get_pii_config as _get_pii_config

        snapshot = {
            "Crew/test-crew": {
                "kind": "Crew",
                "name": "test-crew",
                "project": "default",
                "spec": {
                    "process": "sequential",
                    "agents": ["ref:agents/researcher"],
                    "tasks": ["ref:tasks/research"],
                },
            },
            "Agent/researcher": {
                "kind": "Agent",
                "name": "researcher",
                "project": "default",
                "spec": {
                    "role": "Researcher",
                    "goal": "Research",
                    "backstory": "...",
                },
            },
        }
        assert _get_pii_config(snapshot, "test-crew") is None

    def test_returns_pii_config_from_agent_policy(self):
        from blackbeard.engine.budget import get_pii_config as _get_pii_config

        snapshot = {
            "Crew/test-crew": {
                "kind": "Crew",
                "name": "test-crew",
                "project": "default",
                "spec": {
                    "process": "sequential",
                    "agents": ["ref:agents/researcher"],
                    "tasks": ["ref:tasks/research"],
                },
            },
            "Agent/researcher": {
                "kind": "Agent",
                "name": "researcher",
                "project": "default",
                "spec": {
                    "role": "Researcher",
                    "goal": "Research",
                    "backstory": "...",
                    "policy": "ref:agent-policies/strict",
                },
            },
            "AgentPolicy/strict": {
                "kind": "AgentPolicy",
                "name": "strict",
                "project": "default",
                "spec": {
                    "pii": {
                        "enabled": True,
                        "backend": "default",
                        "entities": ["EMAIL_ADDRESS"],
                    },
                },
            },
        }
        config = _get_pii_config(snapshot, "test-crew")
        assert config is not None
        assert config["enabled"] is True
        assert config["entities"] == ["EMAIL_ADDRESS"]

    def test_returns_none_when_pii_disabled(self):
        from blackbeard.engine.budget import get_pii_config as _get_pii_config

        snapshot = {
            "Crew/test-crew": {
                "kind": "Crew",
                "name": "test-crew",
                "project": "default",
                "spec": {
                    "process": "sequential",
                    "agents": ["ref:agents/researcher"],
                    "tasks": ["ref:tasks/research"],
                },
            },
            "Agent/researcher": {
                "kind": "Agent",
                "name": "researcher",
                "project": "default",
                "spec": {
                    "role": "Researcher",
                    "goal": "Research",
                    "backstory": "...",
                    "policy": "ref:agent-policies/relaxed",
                },
            },
            "AgentPolicy/relaxed": {
                "kind": "AgentPolicy",
                "name": "relaxed",
                "project": "default",
                "spec": {
                    "pii": {
                        "enabled": False,
                    },
                },
            },
        }
        assert _get_pii_config(snapshot, "test-crew") is None

    def test_returns_pii_from_crew_default_policy(self):
        from blackbeard.engine.budget import get_pii_config as _get_pii_config

        snapshot = {
            "Crew/test-crew": {
                "kind": "Crew",
                "name": "test-crew",
                "project": "default",
                "spec": {
                    "process": "sequential",
                    "agents": ["ref:agents/researcher"],
                    "tasks": ["ref:tasks/research"],
                    "default_agent_policy": "ref:agent-policies/default-pii",
                },
            },
            "Agent/researcher": {
                "kind": "Agent",
                "name": "researcher",
                "project": "default",
                "spec": {
                    "role": "Researcher",
                    "goal": "Research",
                    "backstory": "...",
                },
            },
            "AgentPolicy/default-pii": {
                "kind": "AgentPolicy",
                "name": "default-pii",
                "project": "default",
                "spec": {
                    "pii": {
                        "enabled": True,
                        "backend": "litellm",
                        "model": "ollama/gliner-pii",
                        "redact_outputs": True,
                        "redact_events": False,
                    },
                },
            },
        }
        config = _get_pii_config(snapshot, "test-crew")
        assert config is not None
        assert config["backend"] == "litellm"
        assert config["redact_events"] is False


# ---------------------------------------------------------------------------
# reset_engines
# ---------------------------------------------------------------------------


class TestResetEngines:
    """Tests for reset_engines()."""

    def test_reset_clears_singletons(self):
        import blackbeard.pii as pii_mod

        assert len(pii_mod._analyzers) == 0
        assert pii_mod._anonymizer is None
