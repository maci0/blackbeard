"""Targeted unit tests for individual functions lacking coverage.

Each section tests a specific helper function imported directly from its
module. No HTTP client or database session is needed for the majority of
these tests -- they exercise pure logic, mock only what touches I/O.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest

# -----------------------------------------------------------------------
# 1. blackbeard/pii.py -- resolve_pii_entities()
# -----------------------------------------------------------------------


class TestResolvePiiEntities:
    """Tests for resolve_pii_entities()."""

    def test_hipaa_preset(self):
        from blackbeard.pii import PII_PRESETS, resolve_pii_entities

        result = resolve_pii_entities(preset="hipaa")
        assert set(result) == set(PII_PRESETS["hipaa"])

    def test_gdpr_preset(self):
        from blackbeard.pii import PII_PRESETS, resolve_pii_entities

        result = resolve_pii_entities(preset="gdpr")
        assert set(result) == set(PII_PRESETS["gdpr"])

    def test_pci_dss_preset(self):
        from blackbeard.pii import PII_PRESETS, resolve_pii_entities

        result = resolve_pii_entities(preset="pci-dss")
        assert set(result) == set(PII_PRESETS["pci-dss"])

    def test_custom_preset_with_explicit_entities(self):
        """preset='custom' (unknown) is ignored; explicit entities are returned."""
        from blackbeard.pii import resolve_pii_entities

        result = resolve_pii_entities(preset="custom", entities=["PERSON"])
        assert result == ["PERSON"]

    def test_hipaa_plus_extra_entities_returns_union(self):
        from blackbeard.pii import PII_PRESETS, resolve_pii_entities

        result = resolve_pii_entities(preset="hipaa", entities=["CREDIT_CARD"])
        expected = set(PII_PRESETS["hipaa"]) | {"CREDIT_CARD"}
        assert set(result) == expected

    def test_no_preset_no_entities_returns_defaults(self):
        from blackbeard.pii import DEFAULT_ENTITIES, resolve_pii_entities

        result = resolve_pii_entities(preset=None, entities=None)
        assert result == list(DEFAULT_ENTITIES)

    def test_unknown_preset_no_entities_returns_defaults(self):
        from blackbeard.pii import DEFAULT_ENTITIES, resolve_pii_entities

        result = resolve_pii_entities(preset="unknown", entities=None)
        assert result == list(DEFAULT_ENTITIES)

    def test_result_is_sorted(self):
        from blackbeard.pii import resolve_pii_entities

        result = resolve_pii_entities(preset="hipaa")
        assert result == sorted(result)

    def test_empty_string_preset_returns_defaults(self):
        """Empty string is falsy, so it falls through to DEFAULT_ENTITIES."""
        from blackbeard.pii import DEFAULT_ENTITIES, resolve_pii_entities

        result = resolve_pii_entities(preset="", entities=None)
        assert result == list(DEFAULT_ENTITIES)

    def test_entities_only_no_preset(self):
        from blackbeard.pii import resolve_pii_entities

        result = resolve_pii_entities(preset=None, entities=["EMAIL_ADDRESS", "PERSON"])
        assert set(result) == {"EMAIL_ADDRESS", "PERSON"}




# -----------------------------------------------------------------------
# 2. blackbeard/api/middleware.py -- _redact_query_string() & get_request_id()
# -----------------------------------------------------------------------


class TestRedactQueryString:
    """Tests for _redact_query_string()."""

    def test_empty_string(self):
        from blackbeard.api.middleware import _redact_query_string

        assert _redact_query_string("") == ""

    def test_non_sensitive_params_unchanged(self):
        from blackbeard.api.middleware import _redact_query_string

        assert _redact_query_string("foo=bar") == "foo=bar"

    def test_api_key_redacted(self):
        from blackbeard.api.middleware import _redact_query_string

        result = _redact_query_string("api_key=secret123")
        assert "secret123" not in result
        # urlencode encodes brackets: [REDACTED] -> %5BREDACTED%5D
        assert "REDACTED" in result

    def test_name_not_redacted(self):
        from blackbeard.api.middleware import _redact_query_string

        result = _redact_query_string("name=bob&age=30")
        assert result == "name=bob&age=30"

    def test_multiple_sensitive_params(self):
        from blackbeard.api.middleware import _redact_query_string

        result = _redact_query_string("email=x@y.com&token=abc123")
        assert "x@y.com" not in result
        assert "abc123" not in result
        assert result.count("REDACTED") == 2

    def test_case_insensitive_detection(self):
        """The fast-path check lowercases the query to match sensitive param names."""
        from blackbeard.api.middleware import _redact_query_string

        result = _redact_query_string("API_KEY=secret")
        # parse_qsl preserves case of key; lowered comparison should still redact
        assert "secret" not in result

    def test_bare_sensitive_keyword_redacted(self):
        """A bare sensitive keyword (no '=') is parsed by parse_qsl with
        keep_blank_values=True as ('token', ''), and the value is redacted."""
        from blackbeard.api.middleware import _redact_query_string

        result = _redact_query_string("token")
        # parse_qsl("token", keep_blank_values=True) -> [("token", "")]
        # "token" is sensitive, so its blank value is replaced with [REDACTED]
        assert "REDACTED" in result
        assert result.startswith("token=")


class TestGetRequestId:
    """Tests for get_request_id()."""

    def test_valid_header_returned(self):
        from blackbeard.api.middleware import get_request_id

        request = MagicMock()
        request.headers = {"X-Request-Id": "abc-123"}
        assert get_request_id(request) == "abc-123"

    def test_no_header_returns_uuid(self):
        from blackbeard.api.middleware import get_request_id

        request = MagicMock()
        request.headers = {}
        result = get_request_id(request)
        # Should be a valid UUID
        uuid.UUID(result)

    def test_invalid_header_ignored(self):
        """Headers with special characters are rejected, a fresh UUID generated."""
        from blackbeard.api.middleware import get_request_id

        request = MagicMock()
        request.headers = {"X-Request-Id": "bad\nvalue"}
        result = get_request_id(request)
        assert result != "bad\nvalue"
        uuid.UUID(result)  # should be valid UUID

    def test_too_long_header_ignored(self):
        from blackbeard.api.middleware import get_request_id

        request = MagicMock()
        request.headers = {"X-Request-Id": "a" * 65}
        result = get_request_id(request)
        assert result != "a" * 65
        uuid.UUID(result)


# -----------------------------------------------------------------------
# 3. blackbeard/audit.py -- audit_from_request()
# -----------------------------------------------------------------------


class TestAuditFromRequest:
    """Tests for audit_from_request()."""

    def test_with_user(self):
        from blackbeard.audit import audit_from_request

        request = MagicMock()
        request.client.host = "10.0.0.1"

        user = MagicMock()
        user.id = uuid.uuid4()
        user.email = "admin@example.com"

        result = audit_from_request(request, user)
        assert result["actor_type"] == "user"
        assert result["actor_id"] == str(user.id)
        assert result["actor_email"] == "admin@example.com"
        assert result["ip_address"] == "10.0.0.1"

    def test_without_user(self):
        from blackbeard.audit import audit_from_request

        request = MagicMock()
        request.client.host = "192.168.1.1"

        result = audit_from_request(request, None)
        assert result["actor_type"] == "api_key"
        assert result["actor_id"] == "api_key"
        assert result["actor_email"] is None
        assert result["ip_address"] == "192.168.1.1"

    def test_no_client(self):
        """When request.client is None, ip_address should be None."""
        from blackbeard.audit import audit_from_request

        request = MagicMock()
        request.client = None

        result = audit_from_request(request, None)
        assert result["ip_address"] is None


# -----------------------------------------------------------------------
# 4. blackbeard/api/credentials.py -- _MASKED_VALUE constant
#
# The credentials module uses a fixed-width constant mask, not a _mask()
# function. We verify the constant is used correctly to avoid length
# leakage (CWE-200).
# -----------------------------------------------------------------------


class TestCredentialMasking:
    """Verify the credentials module masks values with a fixed constant."""

    def test_masked_value_is_fixed(self):
        from blackbeard.api.credentials import _MASKED_VALUE

        assert _MASKED_VALUE == "****"

    def test_masked_value_length_independent(self):
        """The mask is the same regardless of input length -- no suffix leakage."""
        from blackbeard.api.credentials import _MASKED_VALUE

        # Whether the secret is 2 chars or 20, the mask is always "****"
        assert _MASKED_VALUE == "****"
        assert len(_MASKED_VALUE) == 4


# -----------------------------------------------------------------------
# 5. blackbeard/engine/flow_runner.py -- evaluate_condition() & resolve_dotted()
# -----------------------------------------------------------------------


class TestEvaluateCondition:
    """Tests for evaluate_condition()."""

    def test_greater_than_true(self):
        from blackbeard.engine.flow_runner import evaluate_condition

        assert evaluate_condition("score > 0.8", {"score": 0.9}) is True

    def test_greater_than_false(self):
        from blackbeard.engine.flow_runner import evaluate_condition

        assert evaluate_condition("score > 0.8", {"score": 0.5}) is False

    def test_equality_string(self):
        from blackbeard.engine.flow_runner import evaluate_condition

        assert evaluate_condition("status == completed", {"status": "completed"}) is True

    def test_equality_string_false(self):
        from blackbeard.engine.flow_runner import evaluate_condition

        assert evaluate_condition("status == completed", {"status": "failed"}) is False

    def test_in_operator_string_true(self):
        from blackbeard.engine.flow_runner import evaluate_condition

        assert evaluate_condition("error in outputs", {"outputs": "has error"}) is True

    def test_in_operator_string_false(self):
        from blackbeard.engine.flow_runner import evaluate_condition

        assert evaluate_condition("error in outputs", {"outputs": "all good"}) is False

    def test_less_than(self):
        from blackbeard.engine.flow_runner import evaluate_condition

        assert evaluate_condition("score < 0.5", {"score": 0.3}) is True

    def test_greater_equal(self):
        from blackbeard.engine.flow_runner import evaluate_condition

        assert evaluate_condition("score >= 1.0", {"score": 1.0}) is True

    def test_not_equal(self):
        from blackbeard.engine.flow_runner import evaluate_condition

        assert evaluate_condition("status != failed", {"status": "completed"}) is True

    def test_boolean_key_truthy(self):
        from blackbeard.engine.flow_runner import evaluate_condition

        assert evaluate_condition("is_ready", {"is_ready": True}) is True

    def test_boolean_key_falsy(self):
        from blackbeard.engine.flow_runner import evaluate_condition

        assert evaluate_condition("is_ready", {"is_ready": False}) is False

    def test_missing_key_resolves_false(self):
        from blackbeard.engine.flow_runner import evaluate_condition

        assert evaluate_condition("missing_key > 0", {"other": 1}) is False

    def test_in_operator_with_dict(self):
        from blackbeard.engine.flow_runner import evaluate_condition

        assert evaluate_condition("key1 in results", {"results": {"key1": "val"}}) is True

    def test_in_operator_with_list(self):
        from blackbeard.engine.flow_runner import evaluate_condition

        assert evaluate_condition("apple in fruits", {"fruits": ["apple", "banana"]}) is True


class TestResolveDotted:
    """Tests for resolve_dotted()."""

    def test_nested_path(self):
        from blackbeard.engine.flow_runner import resolve_dotted

        assert resolve_dotted("a.b.c", {"a": {"b": {"c": 42}}}) == 42

    def test_missing_path_returns_none(self):
        from blackbeard.engine.flow_runner import resolve_dotted

        assert resolve_dotted("missing", {}) is None

    def test_top_level(self):
        from blackbeard.engine.flow_runner import resolve_dotted

        assert resolve_dotted("x", {"x": "hello"}) == "hello"

    def test_partial_path_returns_none(self):
        from blackbeard.engine.flow_runner import resolve_dotted

        assert resolve_dotted("a.b.c", {"a": {"b": 5}}) is None

    def test_deep_path_exceeding_limit_returns_none(self):
        from blackbeard.engine.flow_runner import _MAX_RESOLVE_DEPTH, resolve_dotted

        path = ".".join(["k"] * (_MAX_RESOLVE_DEPTH + 1))
        assert resolve_dotted(path, {"k": {}}) is None

    def test_returns_dict_value(self):
        from blackbeard.engine.flow_runner import resolve_dotted

        ctx: dict[str, Any] = {"a": {"nested": {"key": "value"}}}
        assert resolve_dotted("a.nested", ctx) == {"key": "value"}


# -----------------------------------------------------------------------
# 6. blackbeard/api/a2a.py -- _parse_ref_name() & _derive_base_url()
# -----------------------------------------------------------------------


class TestParseRefName:
    """Tests for _parse_ref_name()."""

    def test_valid_ref(self):
        from blackbeard.api.a2a import _parse_ref_name

        assert _parse_ref_name("ref:tasks/my-task") == "my-task"

    def test_invalid_ref_no_prefix(self):
        from blackbeard.api.a2a import _parse_ref_name

        assert _parse_ref_name("invalid") is None

    def test_invalid_ref_no_slash(self):
        from blackbeard.api.a2a import _parse_ref_name

        assert _parse_ref_name("ref:tasks") is None

    def test_agents_ref(self):
        from blackbeard.api.a2a import _parse_ref_name

        assert _parse_ref_name("ref:agents/researcher") == "researcher"

    def test_empty_name(self):
        from blackbeard.api.a2a import _parse_ref_name

        # "ref:tasks/" -> parts = ["tasks", ""] -> name is ""
        assert _parse_ref_name("ref:tasks/") == ""


class TestDeriveBaseUrl:
    """Tests for _derive_base_url()."""

    def test_with_forwarded_headers(self):
        from blackbeard.api.a2a import _derive_base_url

        request = MagicMock()
        request.headers = {
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "api.example.com",
            "Host": "internal:8000",
        }
        request.url.scheme = "http"
        assert _derive_base_url(request) == "https://api.example.com"

    def test_without_forwarded_headers(self):
        from blackbeard.api.a2a import _derive_base_url

        request = MagicMock()
        request.headers = {"Host": "localhost:8000"}
        request.url.scheme = "http"
        assert _derive_base_url(request) == "http://localhost:8000"

    def test_no_host_header_fallback(self):
        from blackbeard.api.a2a import _derive_base_url

        request = MagicMock()
        request.headers = {}
        request.url.scheme = "http"
        request.url.netloc = "fallback:9000"
        assert _derive_base_url(request) == "http://fallback:9000"


# -----------------------------------------------------------------------
# 7. blackbeard/engine/loader.py -- _check_path_safety() & _validate_tool_config()
# -----------------------------------------------------------------------


class TestCheckPathSafety:
    """Tests for _check_path_safety()."""

    def test_path_traversal_raises(self):
        from blackbeard.engine.loader import LoaderError, _check_path_safety

        with pytest.raises(LoaderError, match="path traversal"):
            _check_path_safety("../etc/passwd", "test")

    def test_safe_path_passes(self):
        from blackbeard.engine.loader import _check_path_safety

        # Should not raise
        _check_path_safety("safe/path", "test")

    def test_absolute_path_raises(self):
        from blackbeard.engine.loader import LoaderError, _check_path_safety

        with pytest.raises(LoaderError, match="absolute paths"):
            _check_path_safety("/etc/passwd", "test")

    def test_null_byte_raises(self):
        from blackbeard.engine.loader import LoaderError, _check_path_safety

        with pytest.raises(LoaderError, match="path traversal"):
            _check_path_safety("file\x00.txt", "test")

    def test_backslash_raises(self):
        from blackbeard.engine.loader import LoaderError, _check_path_safety

        with pytest.raises(LoaderError, match="path traversal"):
            _check_path_safety("path\\file", "test")

    def test_tilde_raises(self):
        from blackbeard.engine.loader import LoaderError, _check_path_safety

        with pytest.raises(LoaderError, match="path traversal"):
            _check_path_safety("~/something", "test")


class TestValidateToolConfig:
    """Tests for _validate_tool_config()."""

    def test_valid_config(self):
        from blackbeard.engine.loader import _validate_tool_config

        # Should not raise
        _validate_tool_config({"key": "value"}, "tool")

    def test_path_traversal_in_value_raises(self):
        from blackbeard.engine.loader import LoaderError, _validate_tool_config

        with pytest.raises(LoaderError, match="path traversal"):
            _validate_tool_config({"key": "../../../etc"}, "tool")

    def test_non_string_values_pass(self):
        from blackbeard.engine.loader import _validate_tool_config

        # Non-string values are skipped
        _validate_tool_config({"count": 42, "flag": True, "path": "safe/dir"}, "tool")

    def test_too_many_entries_raises(self):
        from blackbeard.engine.loader import (
            _MAX_CONFIG_ENTRIES,
            LoaderError,
            _validate_tool_config,
        )

        config = {f"key_{i}": "val" for i in range(_MAX_CONFIG_ENTRIES + 1)}
        with pytest.raises(LoaderError, match="entries"):
            _validate_tool_config(config, "tool")

    def test_value_too_long_raises(self):
        from blackbeard.engine.loader import (
            _MAX_CONFIG_VALUE_LEN,
            LoaderError,
            _validate_tool_config,
        )

        config = {"key": "x" * (_MAX_CONFIG_VALUE_LEN + 1)}
        with pytest.raises(LoaderError, match="too long"):
            _validate_tool_config(config, "tool")


# -----------------------------------------------------------------------
# 8. blackbeard/api/resources.py -- _compute_changed_keys()
# -----------------------------------------------------------------------


class TestComputeChangedKeys:
    """Tests for _compute_changed_keys()."""

    def test_one_key_differs(self):
        from blackbeard.api.resources import _compute_changed_keys

        current = {"role": "analyst", "goal": "research"}
        previous = {"role": "analyst", "goal": "old goal"}
        result = _compute_changed_keys(current, previous)
        assert result == ["goal"]

    def test_identical_dicts(self):
        from blackbeard.api.resources import _compute_changed_keys

        spec = {"role": "analyst", "goal": "research"}
        result = _compute_changed_keys(spec, spec)
        assert result == []

    def test_previous_none_returns_all_keys(self):
        from blackbeard.api.resources import _compute_changed_keys

        current = {"a": 1, "b": 2}
        result = _compute_changed_keys(current, None)
        assert result == ["a", "b"]

    def test_key_added(self):
        from blackbeard.api.resources import _compute_changed_keys

        current = {"a": 1, "b": 2}
        previous = {"a": 1}
        result = _compute_changed_keys(current, previous)
        assert result == ["b"]

    def test_key_removed(self):
        from blackbeard.api.resources import _compute_changed_keys

        current = {"a": 1}
        previous = {"a": 1, "b": 2}
        result = _compute_changed_keys(current, previous)
        assert result == ["b"]

    def test_multiple_changes(self):
        from blackbeard.api.resources import _compute_changed_keys

        current = {"a": 1, "b": "new", "c": 3}
        previous = {"a": 1, "b": "old", "c": 3}
        result = _compute_changed_keys(current, previous)
        assert result == ["b"]

    def test_result_is_sorted(self):
        from blackbeard.api.resources import _compute_changed_keys

        current = {"z": 1, "a": 2, "m": 3}
        result = _compute_changed_keys(current, None)
        assert result == sorted(result)


# -----------------------------------------------------------------------
# 9. blackbeard/config.py -- Settings._check_production_secrets (model_validator)
# -----------------------------------------------------------------------


class TestSettingsProductionSecrets:
    """Tests for Settings._check_production_secrets model validator."""

    def test_debug_mode_accepts_defaults(self):
        """In debug mode, insecure defaults are allowed."""
        from blackbeard.config import Settings

        # Should not raise
        s = Settings(debug=True)
        assert s.debug is True

    def test_production_rejects_default_api_key(self):
        from blackbeard.config import Settings

        with pytest.raises(ValueError, match=r"BLACKBEARD_API_KEY.*insecure default"):
            Settings(
                debug=False,
                blackbeard_api_key="change-me-in-production",
                jwt_secret="a-very-strong-jwt-secret-that-is-at-least-32-chars",
                litellm_master_key="real-litellm-key-production",
                database_url="postgresql+asyncpg://user:strongpw@host:5432/db",
                valkey_url="valkey://default:strong-prod-secret@host:6379/0",
            )

    def test_production_rejects_default_jwt_secret(self):
        from blackbeard.config import Settings

        with pytest.raises(ValueError, match=r"JWT_SECRET.*insecure default"):
            Settings(
                debug=False,
                blackbeard_api_key="real-api-key-production",
                jwt_secret="change-jwt-secret-in-production!",
                litellm_master_key="real-litellm-key-production",
                database_url="postgresql+asyncpg://user:strongpw@host:5432/db",
                valkey_url="valkey://default:strong-prod-secret@host:6379/0",
            )

    def test_production_rejects_short_jwt_secret(self):
        from blackbeard.config import Settings

        with pytest.raises(ValueError, match="JWT_SECRET must be at least 32"):
            Settings(
                debug=False,
                blackbeard_api_key="real-api-key-production",
                jwt_secret="short",
                litellm_master_key="real-litellm-key-production",
                database_url="postgresql+asyncpg://user:strongpw@host:5432/db",
                valkey_url="valkey://default:strong-prod-secret@host:6379/0",
            )

    def test_production_rejects_default_litellm_key(self):
        from blackbeard.config import Settings

        with pytest.raises(ValueError, match=r"LITELLM_MASTER_KEY.*insecure default"):
            Settings(
                debug=False,
                blackbeard_api_key="real-api-key-production",
                jwt_secret="a-very-strong-jwt-secret-that-is-at-least-32-chars",
                litellm_master_key="sk-litellm-master-key",
                database_url="postgresql+asyncpg://user:strongpw@host:5432/db",
                valkey_url="valkey://default:strong-prod-secret@host:6379/0",
            )

    def test_production_rejects_default_db_password(self):
        from blackbeard.config import Settings

        with pytest.raises(ValueError, match=r"DATABASE_URL.*insecure default"):
            Settings(
                debug=False,
                blackbeard_api_key="real-api-key-production",
                jwt_secret="a-very-strong-jwt-secret-that-is-at-least-32-chars",
                litellm_master_key="real-litellm-key-production",
                database_url="postgresql+asyncpg://blackbeard:blackbeard@host:5432/db",
                valkey_url="valkey://default:strong-prod-secret@host:6379/0",
            )

    def test_production_rejects_default_valkey_password(self):
        from blackbeard.config import Settings

        with pytest.raises(ValueError, match=r"VALKEY_URL.*insecure default"):
            Settings(
                debug=False,
                blackbeard_api_key="real-api-key-production",
                jwt_secret="a-very-strong-jwt-secret-that-is-at-least-32-chars",
                litellm_master_key="real-litellm-key-production",
                database_url="postgresql+asyncpg://user:strongpw@host:5432/db",
                valkey_url="valkey://default:valkey-dev-secret@host:6379/0",
            )

    def test_production_rejects_cors_wildcard(self):
        from blackbeard.config import Settings

        with pytest.raises(ValueError, match=r"CORS_ORIGINS.*wildcard"):
            Settings(
                debug=False,
                blackbeard_api_key="real-api-key-production",
                jwt_secret="a-very-strong-jwt-secret-that-is-at-least-32-chars",
                litellm_master_key="real-litellm-key-production",
                database_url="postgresql+asyncpg://user:strongpw@host:5432/db",
                valkey_url="valkey://default:strong-prod-secret@host:6379/0",
                cors_origins=["*"],
            )

    def test_production_all_secure_passes(self):
        from blackbeard.config import Settings

        # Should not raise
        s = Settings(
            debug=False,
            blackbeard_api_key="real-api-key-production",
            jwt_secret="a-very-strong-jwt-secret-that-is-at-least-32-chars",
            litellm_master_key="real-litellm-key-production",
            database_url="postgresql+asyncpg://user:strongpw@host:5432/db",
            valkey_url="valkey://default:strong-prod-secret@host:6379/0",
        )
        assert s.debug is False
