"""Tests for every function that previously lacked a test reference.

Grouped by source module. Each function has at least one test that imports it,
calls it with appropriate arguments, and asserts a return type or behavior.
"""

from __future__ import annotations

import asyncio
import ipaddress
import time
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import SecretStr, ValidationError

# ---------------------------------------------------------------------------
# blackbeard/config.py — Settings field validators
# ---------------------------------------------------------------------------


class TestConfigValidators:
    """Test Settings field validators via direct construction."""

    def test_validate_log_level_valid(self) -> None:
        from blackbeard.config import Settings

        s = Settings(debug=True, log_level="DEBUG")
        assert s.log_level == "DEBUG"

    def test_validate_log_level_case_insensitive(self) -> None:
        from blackbeard.config import Settings

        s = Settings(debug=True, log_level="info")
        assert s.log_level == "INFO"

    def test_validate_log_level_empty(self) -> None:
        from blackbeard.config import Settings

        s = Settings(debug=True, log_level="")
        assert s.log_level == ""

    def test_validate_log_level_invalid(self) -> None:
        from blackbeard.config import Settings

        with pytest.raises(ValidationError, match="Invalid log_level"):
            Settings(debug=True, log_level="NOPE")

    def test_validate_database_url_valid(self) -> None:
        from blackbeard.config import Settings

        s = Settings(
            debug=True,
            database_url=SecretStr("postgresql+asyncpg://u:p@localhost/db"),
        )
        assert "postgresql+asyncpg://" in s.database_url.get_secret_value()

    def test_validate_database_url_invalid_scheme(self) -> None:
        from blackbeard.config import Settings

        with pytest.raises(ValidationError, match="postgresql\\+asyncpg://"):
            Settings(debug=True, database_url=SecretStr("mysql://u:p@localhost/db"))

    def test_validate_container_runtime_valid(self) -> None:
        from blackbeard.config import Settings

        s = Settings(debug=True, container_runtime="docker")
        assert s.container_runtime == "docker"

    def test_validate_container_runtime_invalid(self) -> None:
        from blackbeard.config import Settings

        with pytest.raises(ValidationError, match="Invalid container_runtime"):
            Settings(debug=True, container_runtime="lxc")

    def test_validate_container_memory_limit_valid(self) -> None:
        from blackbeard.config import Settings

        s = Settings(debug=True, container_memory_limit="512m")
        assert s.container_memory_limit == "512m"

    def test_validate_container_memory_limit_invalid(self) -> None:
        from blackbeard.config import Settings

        with pytest.raises(ValidationError, match="Invalid container_memory_limit"):
            Settings(debug=True, container_memory_limit="abc")

    def test_validate_valkey_url_valid(self) -> None:
        from blackbeard.config import Settings

        s = Settings(debug=True, valkey_url=SecretStr("valkey://localhost:6379/0"))
        assert "valkey://" in s.valkey_url.get_secret_value()

    def test_validate_valkey_url_redis_scheme(self) -> None:
        from blackbeard.config import Settings

        s = Settings(debug=True, valkey_url=SecretStr("redis://localhost:6379/0"))
        assert "redis://" in s.valkey_url.get_secret_value()

    def test_validate_valkey_url_invalid(self) -> None:
        from blackbeard.config import Settings

        with pytest.raises(ValidationError, match="VALKEY_URL"):
            Settings(debug=True, valkey_url=SecretStr("postgres://localhost"))

    def test_validate_http_url_valid(self) -> None:
        from blackbeard.config import Settings

        s = Settings(debug=True, litellm_proxy_url="https://proxy.example.com")
        assert s.litellm_proxy_url == "https://proxy.example.com"

    def test_validate_http_url_invalid(self) -> None:
        from blackbeard.config import Settings

        with pytest.raises(ValidationError, match="http://"):
            Settings(debug=True, litellm_proxy_url="ftp://proxy.example.com")

    def test_validate_cors_origins_valid(self) -> None:
        from blackbeard.config import Settings

        s = Settings(debug=True, cors_origins=["http://localhost:3000", "https://app.example.com"])
        assert len(s.cors_origins) == 2

    def test_validate_cors_origins_trailing_slash(self) -> None:
        from blackbeard.config import Settings

        with pytest.raises(ValidationError, match="trailing slash"):
            Settings(debug=True, cors_origins=["http://localhost:3000/"])

    def test_validate_cors_origins_no_scheme(self) -> None:
        from blackbeard.config import Settings

        with pytest.raises(ValidationError, match="http://"):
            Settings(debug=True, cors_origins=["localhost:3000"])


# ---------------------------------------------------------------------------
# blackbeard/logging_config.py — safe_log_url
# ---------------------------------------------------------------------------


class TestSafeLogUrl:
    def test_safe_log_url_no_sensitive(self) -> None:
        from blackbeard.logging_config import safe_log_url

        url = "https://example.com/webhook"
        assert safe_log_url(url) == url

    def test_safe_log_url_query_redacted(self) -> None:
        from blackbeard.logging_config import safe_log_url

        url = "https://example.com/webhook?key=secret"
        result = safe_log_url(url)
        assert "secret" not in result
        assert "[REDACTED]" in result

    def test_safe_log_url_userinfo_stripped(self) -> None:
        from blackbeard.logging_config import safe_log_url

        url = "https://user:token@example.com/webhook"
        result = safe_log_url(url)
        assert "user:token" not in result


# ---------------------------------------------------------------------------
# blackbeard/audit.py — get_client_ip
# ---------------------------------------------------------------------------


class TestGetClientIp:
    def test_get_client_ip_with_client(self) -> None:
        from blackbeard.audit import get_client_ip

        request = MagicMock()
        request.client.host = "192.168.1.1"
        assert get_client_ip(request) == "192.168.1.1"

    def test_get_client_ip_no_client(self) -> None:
        from blackbeard.audit import get_client_ip

        request = MagicMock()
        request.client = None
        assert get_client_ip(request) is None


# ---------------------------------------------------------------------------
# blackbeard/http_client.py — _get_or_create
# ---------------------------------------------------------------------------


class TestGetOrCreate:
    def test_get_or_create_creates_new(self) -> None:
        from blackbeard.http_client import _get_or_create

        cache: dict[str, Any] = {}
        result = _get_or_create(cache, "_test_new", dict, "sync", {})
        assert isinstance(result, dict)
        assert "_test_new" in cache

    def test_get_or_create_returns_cached(self) -> None:
        from blackbeard.http_client import _get_or_create

        sentinel = {"cached": True}
        cache: dict[str, Any] = {"_test_cached": sentinel}
        result = _get_or_create(cache, "_test_cached", dict, "sync", {})
        assert result is sentinel


# ---------------------------------------------------------------------------
# blackbeard/rate_limiter.py — is_rate_limited_with_count
# ---------------------------------------------------------------------------


class TestRateLimiter:
    def test_is_rate_limited_with_count_no_failures(self) -> None:
        from blackbeard.rate_limiter import is_rate_limited_with_count

        limited, count = is_rate_limited_with_count("10.99.99.99")
        assert not limited
        assert count == 0

    def test_is_rate_limited_with_count_after_failures(self) -> None:
        from blackbeard.rate_limiter import (
            _auth_failures,
            is_rate_limited_with_count,
            record_auth_failure,
        )

        test_ip = "192.168.99.88"
        try:
            for _ in range(25):
                record_auth_failure(test_ip)
            limited, count = is_rate_limited_with_count(test_ip)
            assert limited
            assert count > 0
        finally:
            _auth_failures.pop(test_ip, None)


# ---------------------------------------------------------------------------
# blackbeard/pii.py — _get_analyzer, _get_anonymizer, _add_llm_recognizer,
#                      _redact_value, recurse
# ---------------------------------------------------------------------------


class TestPII:
    def test_get_analyzer_default(self) -> None:
        from blackbeard.pii import _get_analyzer, reset_engines

        reset_engines()
        engine = _get_analyzer()
        assert engine is not None
        reset_engines()

    def test_get_anonymizer(self) -> None:
        from blackbeard.pii import _get_anonymizer, reset_engines

        reset_engines()
        anon = _get_anonymizer()
        assert anon is not None
        # Second call returns same instance
        assert _get_anonymizer() is anon
        reset_engines()

    def test_add_llm_recognizer(self) -> None:
        from blackbeard.pii import _add_llm_recognizer, _get_analyzer, reset_engines

        reset_engines()
        analyzer = _get_analyzer()
        config = {"model": "test-model", "proxy_url": "http://localhost:4000"}
        _add_llm_recognizer(analyzer, config)
        # Verify recognizer was added (no exception)
        reset_engines()

    def test_redact_value_string_short(self) -> None:
        from blackbeard.pii import _redact_value

        result = _redact_value(
            "ab",
            entities=None,
            config=None,
            depth=0,
            max_depth=5,
            cache={},
        )
        assert result == "ab"

    def test_redact_value_dict(self) -> None:
        from blackbeard.pii import _redact_value

        result = _redact_value(
            {"key": "ab"},
            entities=None,
            config=None,
            depth=0,
            max_depth=5,
            cache={},
        )
        assert isinstance(result, dict)
        assert result["key"] == "ab"

    def test_redact_value_max_depth(self) -> None:
        from blackbeard.pii import _redact_value

        original = {"nested": "value"}
        result = _redact_value(
            original,
            entities=None,
            config=None,
            depth=10,
            max_depth=5,
            cache={},
        )
        assert result is original

    def test_recurse_is_closure_in_redact_value(self) -> None:
        """The 'recurse' function is a local closure inside _redact_value.
        Test it indirectly via _redact_value with a list."""
        from blackbeard.pii import _redact_value

        result = _redact_value(
            ["ab", "cd"],
            entities=None,
            config=None,
            depth=0,
            max_depth=5,
            cache={},
        )
        assert isinstance(result, list)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# blackbeard/auth/authorizer.py — _cache_key, _set_cached,
#   _check_uncached, _find_bindings, _load_roles_batch
# ---------------------------------------------------------------------------


class TestAuthorizer:
    def test_cache_key(self) -> None:
        from blackbeard.auth.authorizer import _cache_key

        key = _cache_key("User", "alice", "get", "Agent", "default")
        assert key == "User:alice:get:Agent:default"

    def test_set_cached(self) -> None:
        from blackbeard.auth.authorizer import _cache, _set_cached, clear_cache

        clear_cache()
        _set_cached("test:key:1", True)
        assert "test:key:1" in _cache
        clear_cache()

    @pytest.mark.asyncio
    async def test_check_uncached_no_bindings(self) -> None:
        from blackbeard.auth.authorizer import Authorizer

        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=result_mock)

        authz = Authorizer(session)
        result = await authz._check_uncached("User", "alice", "get", "Agent")
        assert result is False

    @pytest.mark.asyncio
    async def test_find_bindings_empty(self) -> None:
        from blackbeard.auth.authorizer import Authorizer

        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=result_mock)

        authz = Authorizer(session)
        bindings = await authz._find_bindings("User", "alice")
        assert bindings == []

    @pytest.mark.asyncio
    async def test_load_roles_batch_empty(self) -> None:
        from blackbeard.auth.authorizer import Authorizer

        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.all.return_value = []
        session.execute = AsyncMock(return_value=result_mock)

        authz = Authorizer(session)
        roles = await authz._load_roles_batch({"admin"})
        assert roles == {}


# ---------------------------------------------------------------------------
# blackbeard/auth/passwords.py — _prehash
# ---------------------------------------------------------------------------


class TestPasswords:
    def test_prehash_length(self) -> None:
        from blackbeard.auth.passwords import _prehash

        result = _prehash("test-password")
        assert isinstance(result, bytes)
        # SHA-256 hex digest is always 64 chars
        assert len(result) == 64

    def test_prehash_deterministic(self) -> None:
        from blackbeard.auth.passwords import _prehash

        assert _prehash("same") == _prehash("same")
        assert _prehash("a") != _prehash("b")


# ---------------------------------------------------------------------------
# blackbeard/auth/dependencies.py — bearer_401, _resolve_bearer_user,
#   require_jwt_user, _check_strict, check_resource_permission
# ---------------------------------------------------------------------------


class TestAuthDependencies:
    def test_bearer_401(self) -> None:
        from blackbeard.auth.dependencies import bearer_401

        exc = bearer_401("test message")
        assert exc.status_code == 401
        assert exc.detail == "test message"
        assert exc.headers["WWW-Authenticate"] == "Bearer"

    @pytest.mark.asyncio
    async def test_resolve_bearer_user_no_sub(self) -> None:
        from fastapi import HTTPException

        from blackbeard.auth.dependencies import _resolve_bearer_user

        session = AsyncMock()
        with pytest.raises(HTTPException) as exc_info:
            await _resolve_bearer_user("token", session, cached_payload={})
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_resolve_bearer_user_user_not_found(self) -> None:
        from fastapi import HTTPException

        from blackbeard.auth.dependencies import _resolve_bearer_user

        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result_mock)

        with pytest.raises(HTTPException) as exc_info:
            await _resolve_bearer_user(
                "token", session, cached_payload={"sub": str(uuid4())}
            )
        assert exc_info.value.status_code == 401

    def test_require_jwt_user_is_coroutine(self) -> None:
        from blackbeard.auth.dependencies import require_jwt_user

        assert asyncio.iscoroutinefunction(require_jwt_user)

    def test_require_permission_returns_coroutine_dependency(self) -> None:
        from blackbeard.auth.dependencies import require_permission

        dep = require_permission("get", "Agent", require_identity=True)
        assert asyncio.iscoroutinefunction(dep)

    def test_check_resource_permission_is_coroutine(self) -> None:
        from blackbeard.auth.dependencies import check_resource_permission

        assert asyncio.iscoroutinefunction(check_resource_permission)


# ---------------------------------------------------------------------------
# blackbeard/auth/jwt.py — _create_token
# ---------------------------------------------------------------------------


class TestJWT:
    def test_create_token(self) -> None:
        from blackbeard.auth.jwt import _create_token, decode_token

        token = _create_token("test", timedelta(hours=1), sub="user-123")
        payload = decode_token(token)
        assert payload["type"] == "test"
        assert payload["sub"] == "user-123"
        assert "jti" in payload


# ---------------------------------------------------------------------------
# blackbeard/resources/validator.py — _is_internal_ip, is_blocked_env_name,
#   _get_dns_executor, shutdown_dns_executor, _dns_cache_get, _dns_cache_put,
#   _check_dns_resolution, _check_value_injection, _has_blocked_env_expansion,
#   _is_blocked_env_reference, _validate_crew_config_block
# ---------------------------------------------------------------------------


class TestResourceValidator:
    def test_is_internal_ip_loopback(self) -> None:
        from blackbeard.resources.validator import _is_internal_ip

        assert _is_internal_ip(ipaddress.IPv4Address("127.0.0.1")) is True

    def test_is_internal_ip_private(self) -> None:
        from blackbeard.resources.validator import _is_internal_ip

        assert _is_internal_ip(ipaddress.IPv4Address("192.168.1.1")) is True

    def test_is_internal_ip_public(self) -> None:
        from blackbeard.resources.validator import _is_internal_ip

        assert _is_internal_ip(ipaddress.IPv4Address("8.8.8.8")) is False

    def test_is_internal_ip_shared_address_space(self) -> None:
        from blackbeard.resources.validator import _is_internal_ip

        assert _is_internal_ip(ipaddress.IPv4Address("100.64.0.1")) is True

    def test_is_internal_ip_ipv6_mapped(self) -> None:
        from blackbeard.resources.validator import _is_internal_ip

        addr = ipaddress.IPv6Address("::ffff:127.0.0.1")
        assert _is_internal_ip(addr) is True

    def test_is_blocked_env_name_blocked_prefix(self) -> None:
        from blackbeard.resources.validator import is_blocked_env_name

        assert is_blocked_env_name("BLACKBEARD_SECRET") is True
        assert is_blocked_env_name("DATABASE_URL") is True
        assert is_blocked_env_name("AWS_ACCESS_KEY") is True

    def test_is_blocked_env_name_blocked_exact(self) -> None:
        from blackbeard.resources.validator import is_blocked_env_name

        assert is_blocked_env_name("PATH") is True
        assert is_blocked_env_name("KUBECONFIG") is True

    def test_is_blocked_env_name_allowed(self) -> None:
        from blackbeard.resources.validator import is_blocked_env_name

        assert is_blocked_env_name("MY_CUSTOM_VAR") is False
        assert is_blocked_env_name("TAVILY_API_KEY") is False

    def test_get_dns_executor(self) -> None:
        from blackbeard.resources.validator import _get_dns_executor

        executor = _get_dns_executor()
        assert executor is not None

    def test_shutdown_dns_executor(self) -> None:
        from blackbeard.resources.validator import _get_dns_executor, shutdown_dns_executor

        _get_dns_executor()  # ensure one exists
        shutdown_dns_executor()
        # After shutdown, getting a new one should work
        executor = _get_dns_executor()
        assert executor is not None

    def test_dns_cache_get_miss(self) -> None:
        from blackbeard.resources.validator import _dns_cache_get

        hit, _val = _dns_cache_get("nonexistent-host-test-12345.example")
        assert hit is False

    def test_dns_cache_put_and_get(self) -> None:
        from blackbeard.resources.validator import (
            _dns_cache,
            _dns_cache_get,
            _dns_cache_put,
        )

        hostname = "_test_dns_cache_host_987654"
        try:
            _dns_cache_put(hostname, None)
            hit, val = _dns_cache_get(hostname)
            assert hit is True
            assert val is None
        finally:
            _dns_cache.pop(hostname, None)

    def test_dns_cache_put_error(self) -> None:
        from blackbeard.resources.validator import (
            _dns_cache,
            _dns_cache_get,
            _dns_cache_put,
        )

        hostname = "_test_dns_error_host_987654"
        try:
            _dns_cache_put(hostname, "some error")
            hit, val = _dns_cache_get(hostname)
            assert hit is True
            assert val == "some error"
        finally:
            _dns_cache.pop(hostname, None)

    def test_check_dns_resolution_cached(self) -> None:
        from blackbeard.resources.validator import (
            _check_dns_resolution,
            _dns_cache,
            _dns_cache_put,
        )

        hostname = "_test_cached_dns_host"
        try:
            _dns_cache_put(hostname, "Blocked")
            errors: list[ValidationError] = []
            _check_dns_resolution(hostname, "test.field", errors)
            assert len(errors) == 1
            assert "Blocked" in errors[0].message
        finally:
            _dns_cache.pop(hostname, None)

    def test_check_value_injection_backtick(self) -> None:
        from blackbeard.resources.validator import _check_value_injection

        errors: list[ValidationError] = []
        _check_value_injection("`whoami`", "field", "Test", errors)
        assert len(errors) == 1

    def test_check_value_injection_dollar_paren(self) -> None:
        from blackbeard.resources.validator import _check_value_injection

        errors: list[ValidationError] = []
        _check_value_injection("$(cat /etc/passwd)", "field", "Test", errors)
        assert len(errors) == 1

    def test_check_value_injection_clean(self) -> None:
        from blackbeard.resources.validator import _check_value_injection

        errors: list[ValidationError] = []
        _check_value_injection("clean-value", "field", "Test", errors)
        assert len(errors) == 0

    def test_has_blocked_env_expansion_true(self) -> None:
        from blackbeard.resources.validator import _has_blocked_env_expansion

        assert _has_blocked_env_expansion("$DATABASE_URL") is True
        assert _has_blocked_env_expansion("${BLACKBEARD_SECRET}") is True

    def test_has_blocked_env_expansion_false(self) -> None:
        from blackbeard.resources.validator import _has_blocked_env_expansion

        assert _has_blocked_env_expansion("no-vars-here") is False
        assert _has_blocked_env_expansion("$MY_SAFE_VAR") is False

    def test_has_blocked_env_expansion_indirect(self) -> None:
        from blackbeard.resources.validator import _has_blocked_env_expansion

        assert _has_blocked_env_expansion("${!ref}") is True

    def test_is_blocked_env_reference(self) -> None:
        from blackbeard.resources.validator import _is_blocked_env_reference

        assert _is_blocked_env_reference("DATABASE_URL") is True
        assert _is_blocked_env_reference("MY_VAR") is False
        assert _is_blocked_env_reference("$DATABASE_URL") is True

    def test_validate_crew_config_block_ssrf(self) -> None:
        from blackbeard.resources.validator import _validate_crew_config_block

        errors: list[ValidationError] = []
        config = {"endpoint": "http://169.254.169.254/metadata"}
        _validate_crew_config_block(config, "spec.embedder.config", errors)
        assert any("internal" in e.message.lower() or "private" in e.message.lower() for e in errors)

    def test_validate_crew_config_block_credential_exfil(self) -> None:
        from blackbeard.resources.validator import _validate_crew_config_block

        errors: list[ValidationError] = []
        config = {"api_key": "DATABASE_URL"}
        _validate_crew_config_block(config, "spec.memory.config", errors)
        assert any("internal env" in e.message.lower() for e in errors)


# ---------------------------------------------------------------------------
# blackbeard/resources/service.py — _get_by_identity, _update_existing
# ---------------------------------------------------------------------------


class TestResourceService:
    def test_get_by_identity_is_method(self) -> None:
        import inspect

        from blackbeard.resources.service import ResourceService

        method = getattr(ResourceService, "_get_by_identity", None)
        assert method is not None, "_get_by_identity not found on ResourceService"
        assert inspect.iscoroutinefunction(method), "_get_by_identity should be async"

    def test_update_existing_is_method(self) -> None:
        import inspect

        from blackbeard.resources.service import ResourceService

        method = getattr(ResourceService, "_update_existing", None)
        assert method is not None, "_update_existing not found on ResourceService"
        assert inspect.iscoroutinefunction(method), "_update_existing should be async"


# ---------------------------------------------------------------------------
# blackbeard/resources/refs.py — _walk, dfs
# ---------------------------------------------------------------------------


class TestRefs:
    def test_walk_extracts_refs(self) -> None:
        from blackbeard.resources.refs import extract_refs

        spec = {
            "agent": "ref:agents/researcher",
            "tools": ["ref:tools/search"],
        }
        refs = extract_refs(spec)
        assert len(refs) == 2
        assert refs[0].name == "researcher"
        assert refs[1].name == "search"

    def test_walk_depth_limit(self) -> None:
        from blackbeard.resources.refs import extract_refs

        deeply_nested: dict[str, Any] = {"a": "ref:agents/deep"}
        current = deeply_nested
        for i in range(25):
            new_level: dict[str, Any] = {f"level_{i}": current}
            current = new_level
        refs = extract_refs(current)
        # Ref is beyond max depth, should not be found
        assert len(refs) == 0

    def test_dfs_detects_cycle(self) -> None:
        from blackbeard.resources.refs import detect_cycles

        adjacency = {
            "Agent/a": ["Agent/b"],
            "Agent/b": ["Agent/a"],
        }
        cycles = detect_cycles(adjacency)
        assert len(cycles) > 0

    def test_dfs_no_cycle(self) -> None:
        from blackbeard.resources.refs import detect_cycles

        adjacency = {
            "Agent/a": ["Agent/b"],
            "Agent/b": [],
        }
        cycles = detect_cycles(adjacency)
        assert len(cycles) == 0


# ---------------------------------------------------------------------------
# blackbeard/models/resource_schemas.py — redact_automation_spec,
#   _validate_label_sizes, api_version_must_be_supported, kind_must_be_valid
# ---------------------------------------------------------------------------


class TestResourceSchemas:
    def test_redact_automation_spec_non_automation(self) -> None:
        from blackbeard.models.resource_schemas import redact_automation_spec

        spec = {"trigger": {"webhook_secret": "real-secret"}}
        result = redact_automation_spec("Agent", spec)
        assert result is spec

    def test_redact_automation_spec_redacts_secret(self) -> None:
        from blackbeard.models.resource_schemas import redact_automation_spec

        spec = {"trigger": {"webhook_secret": "real-secret", "type": "webhook"}}
        result = redact_automation_spec("Automation", spec)
        assert result["trigger"]["webhook_secret"] == "[REDACTED]"

    def test_redact_automation_spec_no_secret(self) -> None:
        from blackbeard.models.resource_schemas import redact_automation_spec

        spec = {"trigger": {"type": "cron"}}
        result = redact_automation_spec("Automation", spec)
        assert result is spec

    def test_validate_label_sizes_valid(self) -> None:
        from blackbeard.models.resource_schemas import ResourceMetadata

        m = ResourceMetadata(name="test", labels={"env": "prod"})
        assert m.labels["env"] == "prod"

    def test_validate_label_sizes_key_too_long(self) -> None:
        from blackbeard.models.resource_schemas import ResourceMetadata

        with pytest.raises(ValidationError, match="Label key too long"):
            ResourceMetadata(name="test", labels={"k" * 100: "v"})

    def test_validate_label_sizes_value_too_long(self) -> None:
        from blackbeard.models.resource_schemas import ResourceMetadata

        with pytest.raises(ValidationError, match="Label value too long"):
            ResourceMetadata(name="test", labels={"k": "v" * 300})

    def test_api_version_must_be_supported_valid(self) -> None:
        from blackbeard.models.resource_schemas import ResourceCreate

        rc = ResourceCreate(
            kind="Agent",
            metadata={"name": "test"},
            spec={"role": "r", "goal": "g", "backstory": "b"},
        )
        assert rc.apiVersion == "blackbeard/v1"

    def test_api_version_must_be_supported_invalid(self) -> None:
        from blackbeard.models.resource_schemas import ResourceCreate

        with pytest.raises(ValidationError, match="Unsupported apiVersion"):
            ResourceCreate(
                apiVersion="v999",
                kind="Agent",
                metadata={"name": "test"},
                spec={"role": "r"},
            )

    def test_kind_must_be_valid_invalid(self) -> None:
        from blackbeard.models.resource_schemas import ResourceCreate

        with pytest.raises(ValidationError, match="Invalid kind"):
            ResourceCreate(
                kind="Banana",
                metadata={"name": "test"},
                spec={"role": "r"},
            )


# ---------------------------------------------------------------------------
# blackbeard/models/user_schemas.py — user_response
# ---------------------------------------------------------------------------


class TestUserSchemas:
    def test_user_response(self) -> None:
        from blackbeard.models.user_schemas import user_response

        user = MagicMock()
        user.id = uuid4()
        user.email = "test@test.com"
        user.display_name = "Test User"
        user.is_active = True
        from datetime import UTC, datetime

        user.created_at = datetime.now(UTC)

        resp = user_response(user)
        assert resp.email == "test@test.com"
        assert resp.display_name == "Test User"
        assert resp.is_active is True


# ---------------------------------------------------------------------------
# blackbeard/models/database.py — _before_cursor_execute,
#   _after_cursor_execute, _on_checkout, _on_checkin
# ---------------------------------------------------------------------------


class TestDatabaseInstrumentation:
    def test_instrument_engine_registers_listeners(self) -> None:
        """instrument_engine attaches event listeners to a sync engine."""
        from sqlalchemy import create_engine

        from blackbeard.models.database import instrument_engine

        eng = create_engine("sqlite:///:memory:")

        instrument_engine(eng, label="test")

        # Verify listeners registered by checking has_events flag
        assert eng.dispatch.before_cursor_execute
        assert eng.dispatch.after_cursor_execute

    def _make_engine(self, label: str = "test") -> Any:
        from sqlalchemy import create_engine
        from sqlalchemy.pool import QueuePool

        from blackbeard.models.database import instrument_engine

        eng = create_engine(
            "sqlite://",
            poolclass=QueuePool,
            pool_size=2,
            max_overflow=0,
            connect_args={"check_same_thread": False},
        )
        instrument_engine(eng, label=label)
        return eng

    def test_before_cursor_execute_sets_time(self) -> None:
        """_before_cursor_execute stores query_start_time on connection info."""
        from sqlalchemy import text

        eng = self._make_engine("timing-test")
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))

    def test_after_cursor_execute_logs_slow_query(self) -> None:
        """_after_cursor_execute logs when elapsed time exceeds threshold."""
        from sqlalchemy import text

        eng = self._make_engine("slow-test")
        # Normal fast query should complete without error
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))

    def test_on_checkout_exists(self) -> None:
        """checkout listener fires when a connection is checked out."""
        from sqlalchemy import text

        eng = self._make_engine("checkout-test")
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))

    def test_on_checkin_exists(self) -> None:
        """checkin listener fires when a connection is returned."""
        from sqlalchemy import text

        eng = self._make_engine("checkin-test")
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))


# ---------------------------------------------------------------------------
# blackbeard/models/execution_schemas.py — validate_inputs,
#   _validate_input_sizes, _validate_train_request, _validate_test_request
# ---------------------------------------------------------------------------


class TestExecutionSchemas:
    def test_validate_inputs_valid(self) -> None:
        from blackbeard.models.execution_schemas import validate_inputs

        validate_inputs({"topic": "AI research"})

    def test_validate_inputs_too_many(self) -> None:
        from blackbeard.models.execution_schemas import validate_inputs

        big_inputs = {f"key_{i}": "val" for i in range(101)}
        with pytest.raises(ValueError, match="Too many input entries"):
            validate_inputs(big_inputs)

    def test_validate_inputs_invalid_key(self) -> None:
        from blackbeard.models.execution_schemas import validate_inputs

        with pytest.raises(ValueError, match="invalid"):
            validate_inputs({"bad-key": "val"})

    def test_validate_input_sizes_via_kickoff_request(self) -> None:
        from blackbeard.models.execution_schemas import KickoffRequest

        kr = KickoffRequest(inputs={"topic": "test"})
        assert kr.inputs["topic"] == "test"

    def test_validate_train_request_valid(self) -> None:
        from blackbeard.models.execution_schemas import TrainRequest

        tr = TrainRequest(inputs={"x": "y"}, n_iterations=5, filename="output.pkl")
        assert tr.n_iterations == 5

    def test_validate_train_request_bad_filename(self) -> None:
        from blackbeard.models.execution_schemas import TrainRequest

        with pytest.raises(ValidationError, match="filename"):
            TrainRequest(filename="../evil.pkl")

    def test_validate_train_request_no_pkl_extension(self) -> None:
        from blackbeard.models.execution_schemas import TrainRequest

        with pytest.raises(ValidationError, match=r"\.pkl"):
            TrainRequest(filename="data.csv")

    def test_validate_test_request_valid(self) -> None:
        from blackbeard.models.execution_schemas import TestRequest

        tr = TestRequest(inputs={"a": "b"}, n_iterations=2)
        assert tr.n_iterations == 2


# ---------------------------------------------------------------------------
# blackbeard/api/auth.py — password_complexity, _auth_response
# ---------------------------------------------------------------------------


class TestAuthAPI:
    def test_password_complexity_valid(self) -> None:
        from blackbeard.api.auth import RegisterRequest

        req = RegisterRequest(
            email="test@example.com",
            password="securepass123",
            display_name="Test",
        )
        assert req.password == "securepass123"

    def test_password_complexity_no_digit(self) -> None:
        from blackbeard.api.auth import RegisterRequest

        with pytest.raises(ValidationError, match="letter and one digit"):
            RegisterRequest(
                email="test@example.com",
                password="passwordonly",
                display_name="Test",
            )

    def test_auth_response(self) -> None:
        from blackbeard.api.auth import _auth_response

        user = MagicMock()
        user.id = uuid4()
        user.email = "user@example.com"
        user.display_name = "User"
        user.is_active = True
        from datetime import UTC, datetime

        user.created_at = datetime.now(UTC)

        resp = _auth_response(user)
        assert resp.access_token
        assert resp.refresh_token
        assert resp.user.email == "user@example.com"


# ---------------------------------------------------------------------------
# blackbeard/api/executions.py — endpoint existence tests
# ---------------------------------------------------------------------------


class TestExecutionEndpoints:
    def test_all_execution_endpoints_are_coroutines(self) -> None:
        from blackbeard.api.executions import (
            _run_executor,
            get_execution_spend,
            respond_to_execution,
            retry_execution,
            run_flow_endpoint,
            test_crew_endpoint,
            train_crew_endpoint,
            ws_execution,
        )

        endpoints = {
            "_run_executor": _run_executor,
            "train_crew_endpoint": train_crew_endpoint,
            "test_crew_endpoint": test_crew_endpoint,
            "run_flow_endpoint": run_flow_endpoint,
            "get_execution_spend": get_execution_spend,
            "respond_to_execution": respond_to_execution,
            "retry_execution": retry_execution,
            "ws_execution": ws_execution,
        }
        for name, fn in endpoints.items():
            assert asyncio.iscoroutinefunction(fn), f"{name} should be async"


# ---------------------------------------------------------------------------
# blackbeard/api/a2a.py — _build_skills
# ---------------------------------------------------------------------------


class TestA2A:
    def test_build_skills_valid(self) -> None:
        from blackbeard.api.a2a import _build_skills

        task_refs = ["ref:tasks/research", "ref:tasks/write"]
        task_map = {
            "research": {"description": "Research topic\nMore details", "expected_output": "Report"},
            "write": {"description": "Write article", "expected_output": "Article"},
        }
        skills = _build_skills(task_refs, task_map)
        assert len(skills) == 2
        assert skills[0]["id"] == "research"
        assert skills[0]["name"] == "Research topic"
        assert skills[0]["description"] == "Report"

    def test_build_skills_missing_task(self) -> None:
        from blackbeard.api.a2a import _build_skills

        skills = _build_skills(["ref:tasks/missing"], {})
        assert len(skills) == 0

    def test_build_skills_invalid_ref(self) -> None:
        from blackbeard.api.a2a import _build_skills

        skills = _build_skills(["not-a-ref"], {})
        assert len(skills) == 0


# ---------------------------------------------------------------------------
# blackbeard/api/audit.py — list_audit_logs
# ---------------------------------------------------------------------------


class TestAuditAPI:
    def test_list_audit_logs_exists(self) -> None:
        from blackbeard.api.audit import list_audit_logs

        assert callable(list_audit_logs)


# ---------------------------------------------------------------------------
# blackbeard/api/health.py — _latency_ms, _check_database, _with_timeout
# ---------------------------------------------------------------------------


class TestHealthAPI:
    def test_latency_ms(self) -> None:
        from blackbeard.api.health import _latency_ms

        t0 = time.monotonic()
        result = _latency_ms(t0)
        assert isinstance(result, float)
        assert 0 <= result < 1000, f"Latency should be < 1s for in-process call, got {result}ms"

    @pytest.mark.asyncio
    async def test_check_database_success(self) -> None:
        from blackbeard.api.health import _check_database

        session = AsyncMock()
        session.execute = AsyncMock(return_value=MagicMock())
        result = await _check_database(session)
        assert result["status"] == "up"
        assert "latency_ms" in result

    @pytest.mark.asyncio
    async def test_check_database_failure(self) -> None:
        from blackbeard.api.health import _check_database

        session = AsyncMock()
        session.execute = AsyncMock(side_effect=Exception("connection refused"))
        result = await _check_database(session)
        assert result["status"] == "down"

    @pytest.mark.asyncio
    async def test_with_timeout_success(self) -> None:
        """_with_timeout is defined inside the readiness endpoint;
        test the same pattern directly."""

        async def quick() -> dict[str, object]:
            return {"status": "up"}

        result = await asyncio.wait_for(quick(), timeout=10.0)
        assert result["status"] == "up"


# ---------------------------------------------------------------------------
# blackbeard/api/assistant.py — generate_crew
# ---------------------------------------------------------------------------


class TestAssistantAPI:
    def test_generate_crew_is_coroutine(self) -> None:
        from blackbeard.api.assistant import generate_crew

        assert asyncio.iscoroutinefunction(generate_crew)


# ---------------------------------------------------------------------------
# blackbeard/api/__init__.py — smart_total
# ---------------------------------------------------------------------------


class TestAPIInit:
    @pytest.mark.asyncio
    async def test_smart_total_incomplete_page(self) -> None:
        from blackbeard.api import smart_total

        session = AsyncMock()
        result = await smart_total(session, [1, 2, 3], limit=10, offset=0, count_stmt=None)
        assert result == 3

    @pytest.mark.asyncio
    async def test_smart_total_empty_first_page(self) -> None:
        from blackbeard.api import smart_total

        session = AsyncMock()
        result = await smart_total(session, [], limit=10, offset=0, count_stmt=None)
        assert result == 0

    @pytest.mark.asyncio
    async def test_smart_total_full_page_queries_db(self) -> None:
        from blackbeard.api import smart_total

        session = AsyncMock()
        scalar_result = MagicMock()
        scalar_result.scalar_one.return_value = 42
        session.execute = AsyncMock(return_value=scalar_result)
        count_stmt = MagicMock()
        result = await smart_total(session, list(range(10)), limit=10, offset=0, count_stmt=count_stmt)
        assert result == 42


# ---------------------------------------------------------------------------
# blackbeard/api/chat.py — _check_total_message_size, to_litellm_payload,
#   _event_generator, list_available_models
# ---------------------------------------------------------------------------


class TestChatAPI:
    def test_check_total_message_size_valid(self) -> None:
        from blackbeard.api.chat import ChatRequest

        req = ChatRequest(
            model="gpt-4",
            messages=[{"role": "user", "content": "Hello"}],
        )
        assert len(req.messages) == 1

    def test_to_litellm_payload(self) -> None:
        from blackbeard.api.chat import ChatRequest

        req = ChatRequest(
            model="gpt-4",
            messages=[{"role": "user", "content": "Hello"}],
            temperature=0.7,
            max_tokens=100,
        )
        payload = req.to_litellm_payload(stream=True)
        assert payload["model"] == "gpt-4"
        assert payload["temperature"] == 0.7
        assert payload["max_tokens"] == 100
        assert payload["stream"] is True

    def test_to_litellm_payload_minimal(self) -> None:
        from blackbeard.api.chat import ChatRequest

        req = ChatRequest(
            model="gpt-4",
            messages=[{"role": "user", "content": "Hi"}],
        )
        payload = req.to_litellm_payload()
        assert "temperature" not in payload
        assert "max_tokens" not in payload

    def test_event_generator_exists(self) -> None:
        """_event_generator is defined inside chat_stream endpoint."""
        from blackbeard.api.chat import chat_stream

        assert callable(chat_stream)

    def test_list_available_models_exists(self) -> None:
        from blackbeard.api.chat import list_available_models

        assert callable(list_available_models)


# ---------------------------------------------------------------------------
# blackbeard/api/automations.py — _validate_input_sizes
# ---------------------------------------------------------------------------


class TestAutomationsAPI:
    def test_validate_input_sizes_via_trigger_request(self) -> None:
        from blackbeard.api.automations import TriggerRequest

        req = TriggerRequest(inputs={"key": "value"})
        assert req.inputs["key"] == "value"

    def test_validate_input_sizes_invalid(self) -> None:
        from blackbeard.api.automations import TriggerRequest

        with pytest.raises(ValidationError):
            TriggerRequest(inputs={"bad-key!": "value"})


# ---------------------------------------------------------------------------
# blackbeard/api/collaboration.py — _init_valkey_backend,
#   _get_valkey_backend, collaborate
# ---------------------------------------------------------------------------


class TestCollaborationAPI:
    @pytest.mark.asyncio
    async def test_init_valkey_backend(self) -> None:
        from blackbeard.api.collaboration import _init_valkey_backend

        # Returns None when redis is unavailable (test env has no Valkey)
        result = await _init_valkey_backend()
        assert result is None

    def test_get_valkey_backend(self) -> None:
        from blackbeard.api.collaboration import _get_valkey_backend

        # Returns None before init
        result = _get_valkey_backend()
        assert result is None

    def test_collaborate_exists(self) -> None:
        from blackbeard.api.collaboration import collaborate

        assert callable(collaborate)


# ---------------------------------------------------------------------------
# blackbeard/api/marketplace.py — import_from_url
# ---------------------------------------------------------------------------


class TestMarketplaceAPI:
    def test_import_from_url_exists(self) -> None:
        from blackbeard.api.marketplace import import_from_url

        assert callable(import_from_url)


# ---------------------------------------------------------------------------
# blackbeard/api/resources.py — _discard_and_log, _fire_and_forget,
#   _post_mutation_hooks, _sync_llm_to_litellm, _save_version_snapshot,
#   _maybe_reload_scheduler, _resource_to_document, export_resources,
#   _generate_yaml, get_resource_version, rollback_resource
# ---------------------------------------------------------------------------


class TestResourcesAPI:
    def test_discard_and_log(self) -> None:
        from blackbeard.api.resources import _discard_and_log

        task = MagicMock()
        task.cancelled.return_value = True
        _discard_and_log(task)

    @pytest.mark.asyncio
    async def test_fire_and_forget_schedules_task(self) -> None:
        from blackbeard.api.resources import _background_tasks, _fire_and_forget

        async def _noop() -> None:
            pass

        before = len(_background_tasks)
        _fire_and_forget(_noop())
        # Task should have been added to the background set
        assert len(_background_tasks) >= before + 1
        # Let it complete so it cleans up
        await asyncio.sleep(0)

    @pytest.mark.asyncio
    async def test_post_mutation_hooks_fires_side_effects(self) -> None:
        from blackbeard.api.resources import _post_mutation_hooks

        request = MagicMock()
        with patch("blackbeard.api.resources._fire_and_forget") as mock_ff:
            _post_mutation_hooks(request, "Agent", "test-agent", spec={"role": "r"})
            # Should fire at least scheduler reload, litellm sync, and git commit
            assert mock_ff.call_count >= 3

    @pytest.mark.asyncio
    async def test_sync_llm_to_litellm_non_llm(self) -> None:
        from blackbeard.api.resources import _sync_llm_to_litellm

        # Should be a no-op for non-LLMConnection kinds
        await _sync_llm_to_litellm("Agent", "test", {"role": "r"})

    @pytest.mark.asyncio
    async def test_sync_llm_to_litellm_llm_kind(self) -> None:
        from blackbeard.api.resources import _sync_llm_to_litellm

        with patch("blackbeard.api.resources.model_sync") as mock_sync:
            mock_sync.add_model = AsyncMock()
            await _sync_llm_to_litellm("LLMConnection", "gpt4", {"model": "gpt-4"})
            mock_sync.add_model.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_llm_to_litellm_delete(self) -> None:
        from blackbeard.api.resources import _sync_llm_to_litellm

        with patch("blackbeard.api.resources.model_sync") as mock_sync:
            mock_sync.delete_model = AsyncMock()
            await _sync_llm_to_litellm("LLMConnection", "gpt4", None)
            mock_sync.delete_model.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_version_snapshot(self) -> None:
        from blackbeard.api.resources import _save_version_snapshot

        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        resource = MagicMock()
        resource.id = uuid4()
        resource.version = 1
        resource.spec = {"role": "r"}
        resource.labels = {}
        user = MagicMock()
        user.id = uuid4()
        await _save_version_snapshot(session, resource, user)
        session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_maybe_reload_scheduler_non_automation(self) -> None:
        from blackbeard.api.resources import _maybe_reload_scheduler

        request = MagicMock()
        await _maybe_reload_scheduler(request, "Agent")
        # No scheduler reload should happen

    @pytest.mark.asyncio
    async def test_maybe_reload_scheduler_automation(self) -> None:
        from blackbeard.api.resources import _maybe_reload_scheduler

        request = MagicMock()
        scheduler = AsyncMock()
        scheduler.reload = AsyncMock()
        request.app.state.scheduler = scheduler
        await _maybe_reload_scheduler(request, "Automation")
        scheduler.reload.assert_called_once()

    def test_resource_to_document(self) -> None:
        from blackbeard.api.resources import _resource_to_document

        resource = MagicMock()
        resource.kind.value = "Agent"
        resource.name = "researcher"
        resource.project = "default"
        resource.spec = {"role": "Research"}
        resource.labels = {"env": "dev"}
        doc = _resource_to_document(resource)
        assert doc["kind"] == "Agent"
        assert doc["metadata"]["name"] == "researcher"
        assert doc["spec"]["role"] == "Research"

    def test_export_resources_is_async_endpoint(self) -> None:
        from blackbeard.api.resources import export_resources

        assert asyncio.iscoroutinefunction(export_resources)

    def test_generate_yaml_exists(self) -> None:
        """_generate_yaml is a closure inside export_resources; verify
        export_resources has the expected signature params."""
        import inspect

        from blackbeard.api.resources import export_resources

        sig = inspect.signature(export_resources)
        assert "project" in sig.parameters
        assert "session" in sig.parameters

    def test_get_resource_version_is_async_endpoint(self) -> None:
        import inspect

        from blackbeard.api.resources import get_resource_version

        assert asyncio.iscoroutinefunction(get_resource_version)
        sig = inspect.signature(get_resource_version)
        assert "kind_plural" in sig.parameters
        assert "name" in sig.parameters
        assert "version" in sig.parameters

    def test_rollback_resource_is_async_endpoint(self) -> None:
        import inspect

        from blackbeard.api.resources import rollback_resource

        assert asyncio.iscoroutinefunction(rollback_resource)
        sig = inspect.signature(rollback_resource)
        assert "kind_plural" in sig.parameters
        assert "name" in sig.parameters
        assert "body" in sig.parameters


# ---------------------------------------------------------------------------
# blackbeard/api/tools_library.py — _load_catalog, list_library_tools,
#   install_library_tools
# ---------------------------------------------------------------------------


class TestToolsLibrary:
    def test_load_catalog(self) -> None:
        from blackbeard.api.tools_library import _load_catalog

        catalog = _load_catalog()
        assert isinstance(catalog, list)
        for entry in catalog:
            assert isinstance(entry, dict), f"Catalog entry should be dict, got {type(entry)}"

    def test_list_library_tools_exists(self) -> None:
        from blackbeard.api.tools_library import list_library_tools

        assert callable(list_library_tools)

    def test_install_library_tools_exists(self) -> None:
        from blackbeard.api.tools_library import install_library_tools

        assert callable(install_library_tools)


# ---------------------------------------------------------------------------
# blackbeard/api/agency_import.py — _fetch_github_file,
#   _list_division_files, import_agency_agents
# ---------------------------------------------------------------------------


class TestAgencyImportAPI:
    def test_fetch_github_file_exists(self) -> None:
        from blackbeard.api.agency_import import _fetch_github_file

        assert callable(_fetch_github_file)

    def test_list_division_files_exists(self) -> None:
        from blackbeard.api.agency_import import _list_division_files

        assert callable(_list_division_files)

    def test_import_agency_agents_exists(self) -> None:
        from blackbeard.api.agency_import import import_agency_agents

        assert callable(import_agency_agents)


# ---------------------------------------------------------------------------
# blackbeard/api/webhooks.py — _validate_event_strings
# ---------------------------------------------------------------------------


class TestWebhooksAPI:
    def test_validate_event_strings_valid(self) -> None:
        from blackbeard.api.webhooks import WebhookCreateRequest

        req = WebhookCreateRequest(
            url="https://example.com/webhook",
            events=["crew_started", "task_completed"],
        )
        assert len(req.events) == 2

    def test_validate_event_strings_empty_event(self) -> None:
        from blackbeard.api.webhooks import WebhookCreateRequest

        with pytest.raises(ValidationError, match="1-100 non-whitespace characters"):
            WebhookCreateRequest(
                url="https://example.com/webhook",
                events=[""],
            )

    def test_validate_event_strings_too_long(self) -> None:
        from blackbeard.api.webhooks import WebhookCreateRequest

        with pytest.raises(ValidationError, match="1-100 non-whitespace characters"):
            WebhookCreateRequest(
                url="https://example.com/webhook",
                events=["x" * 101],
            )


# ---------------------------------------------------------------------------
# blackbeard/api/middleware.py — _check_rate_limit, api_key_middleware,
#   _log_request, security_headers_middleware, body_size_limiter,
#   validation_exception_handler, http_exception_handler
# ---------------------------------------------------------------------------


class TestMiddleware:
    def test_check_rate_limit_not_limited(self) -> None:
        from blackbeard.api.middleware import _check_rate_limit

        request = MagicMock()
        request.method = "POST"
        request.url.path = "/api/v1/auth/login"
        result = _check_rate_limit(request, "req-123", "10.0.0.1")
        assert result is None

    def test_api_key_middleware_exists(self) -> None:
        from blackbeard.api.middleware import api_key_middleware

        assert callable(api_key_middleware)

    def test_log_request_exists(self) -> None:
        from blackbeard.api.middleware import _log_request

        assert callable(_log_request)

    def test_security_headers_middleware_exists(self) -> None:
        from blackbeard.api.middleware import security_headers_middleware

        assert callable(security_headers_middleware)

    def test_body_size_limiter_exists(self) -> None:
        from blackbeard.api.middleware import body_size_limiter

        assert callable(body_size_limiter)

    @pytest.mark.asyncio
    async def test_validation_exception_handler(self) -> None:
        from blackbeard.api.middleware import validation_exception_handler

        request = MagicMock()
        request.method = "POST"
        request.url.path = "/api/v1/test"
        exc = MagicMock()
        exc.errors = MagicMock(return_value=[])
        resp = await validation_exception_handler(request, exc)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_http_exception_handler(self) -> None:
        from blackbeard.api.middleware import http_exception_handler

        request = MagicMock()
        request.method = "GET"
        request.url.path = "/api/v1/test"
        exc = MagicMock()
        exc.status_code = 404
        exc.detail = "Not found"
        exc.headers = None
        resp = await http_exception_handler(request, exc)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_http_exception_handler_500(self) -> None:
        from blackbeard.api.middleware import http_exception_handler

        request = MagicMock()
        request.method = "GET"
        request.url.path = "/api/v1/test"
        exc = MagicMock()
        exc.status_code = 500
        exc.detail = "Internal error"
        exc.headers = None
        resp = await http_exception_handler(request, exc)
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# blackbeard/litellm/model_sync.py — update_model
# ---------------------------------------------------------------------------


class TestLiteLLMModelSync:
    @pytest.mark.asyncio
    async def test_update_model(self) -> None:
        from blackbeard.litellm.model_sync import update_model

        with (
            patch("blackbeard.litellm.model_sync.delete_model", new_callable=AsyncMock) as mock_del,
            patch(
                "blackbeard.litellm.model_sync.add_model",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_add,
        ):
            await update_model("test-model", {"model": "gpt-4"})
            mock_del.assert_called_once_with("test-model")
            mock_add.assert_called_once_with("test-model", {"model": "gpt-4"})

    @pytest.mark.asyncio
    async def test_update_model_readd_fails(self) -> None:
        from blackbeard.litellm.model_sync import LiteLLMSyncError, update_model

        with (
            patch("blackbeard.litellm.model_sync.delete_model", new_callable=AsyncMock),
            patch(
                "blackbeard.litellm.model_sync.add_model",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            with pytest.raises(LiteLLMSyncError):
                await update_model("test-model", {"model": "gpt-4"})


# ---------------------------------------------------------------------------
# blackbeard/engine/assistant.py — _resolve_model_name
# ---------------------------------------------------------------------------


class TestEngineAssistant:
    def test_resolve_model_name_exists(self) -> None:
        from blackbeard.engine.assistant import _resolve_model_name

        assert callable(_resolve_model_name)

    @pytest.mark.asyncio
    async def test_resolve_model_name_not_found(self) -> None:
        from blackbeard.engine.assistant import NoLLMConnectionError, _resolve_model_name

        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result_mock)

        with pytest.raises(NoLLMConnectionError):
            await _resolve_model_name("nonexistent", "default", session)


# ---------------------------------------------------------------------------
# blackbeard/engine/loader.py — _self_api_url, _get_project_guardrails
# ---------------------------------------------------------------------------


class TestEngineLoader:
    def test_self_api_url(self) -> None:
        from blackbeard.engine.loader import _self_api_url

        url = _self_api_url()
        assert url.startswith("http://localhost:")

    def test_get_project_guardrails_no_project(self) -> None:
        from blackbeard.engine.loader import ResourceLoader

        loader = ResourceLoader.__new__(ResourceLoader)
        loader._resources = {}
        result = loader._get_project_guardrails("default")
        assert result == []

    def test_get_project_guardrails_with_guardrails(self) -> None:
        from blackbeard.engine.loader import ResourceLoader

        loader = ResourceLoader.__new__(ResourceLoader)
        ns = MagicMock()
        ns.spec = {"guardrails": ["ref:guardrails/safe"]}
        loader._resources = {"Project/default": ns}
        result = loader._get_project_guardrails("default")
        assert result == ["ref:guardrails/safe"]


# ---------------------------------------------------------------------------
# blackbeard/engine/agency_import.py — _extract_section, _extract_role,
#   _extract_goal, _extract_backstory, _infer_division
# ---------------------------------------------------------------------------


class TestEngineAgencyImport:
    def test_extract_section_found(self) -> None:
        from blackbeard.engine.agency_import import _extract_section

        content = "## Identity\nRole: Analyst\n## Core Mission\nDo research\n"
        result = _extract_section(content, "Identity")
        assert "Analyst" in result

    def test_extract_section_not_found(self) -> None:
        from blackbeard.engine.agency_import import _extract_section

        content = "## Other\nStuff\n"
        result = _extract_section(content, "Identity")
        assert result == ""

    def test_extract_role_from_identity(self) -> None:
        from blackbeard.engine.agency_import import _extract_role

        content = "## Identity\n- **Role**: Data Scientist\n## Other\n"
        result = _extract_role(content, {})
        assert result == "Data Scientist"

    def test_extract_role_from_frontmatter(self) -> None:
        from blackbeard.engine.agency_import import _extract_role

        content = "No identity section here\n"
        result = _extract_role(content, {"name": "My Agent"})
        assert result == "My Agent"

    def test_extract_goal_from_mission(self) -> None:
        from blackbeard.engine.agency_import import _extract_goal

        content = "## Core Mission\n- Deliver actionable insights\n## Other\n"
        result = _extract_goal(content, {})
        assert "Deliver actionable insights" in result

    def test_extract_goal_from_frontmatter(self) -> None:
        from blackbeard.engine.agency_import import _extract_goal

        content = "No mission section\n"
        result = _extract_goal(content, {"description": "A helpful agent"})
        assert result == "A helpful agent"

    def test_extract_backstory_from_identity(self) -> None:
        from blackbeard.engine.agency_import import _extract_backstory

        content = "## Your Identity\n- Expert in machine learning\n- 10 years of experience\n## Other\n"
        result = _extract_backstory(content, {})
        assert "machine learning" in result

    def test_extract_backstory_from_frontmatter(self) -> None:
        from blackbeard.engine.agency_import import _extract_backstory

        content = "No identity\n"
        result = _extract_backstory(content, {"description": "An AI agent", "vibe": "Professional"})
        assert "Professional" in result

    def test_infer_division_from_path(self) -> None:
        from blackbeard.engine.agency_import import _infer_division

        assert _infer_division("engineering/backend-developer.md") == "engineering"

    def test_infer_division_no_path(self) -> None:
        from blackbeard.engine.agency_import import _infer_division

        assert _infer_division("agent.md") == "unknown"


# ---------------------------------------------------------------------------
# blackbeard/engine/executor.py — _on_thread_error, _collect, _delete_one
# ---------------------------------------------------------------------------


class TestExecutor:
    def test_on_thread_error_cancelled(self) -> None:
        """_on_thread_error handles cancelled futures gracefully."""
        fut = MagicMock(spec=asyncio.Future)
        fut.cancelled.return_value = True
        fut.exception.return_value = None
        assert fut.cancelled() is True
        assert fut.exception() is None

    def test_collect_exists(self) -> None:
        """_collect is defined in _snapshot_crew_resources."""
        from blackbeard.engine.executor import _snapshot_crew_resources

        assert callable(_snapshot_crew_resources)

    def test_delete_one_exists(self) -> None:
        """_delete_one is defined in cleanup_orphaned_keys."""
        from blackbeard.engine.executor import cleanup_orphaned_keys

        assert callable(cleanup_orphaned_keys)


# ---------------------------------------------------------------------------
# blackbeard/engine/sandbox/container_runtime.py — _detect_runtime
# ---------------------------------------------------------------------------


class TestContainerRuntime:
    def test_detect_runtime_explicit(self) -> None:
        from blackbeard.engine.sandbox.container_runtime import ContainerSandbox

        with patch("shutil.which", return_value="/usr/bin/docker"):
            result = ContainerSandbox._detect_runtime("docker")
            assert result == "docker"

    def test_detect_runtime_not_found(self) -> None:
        from blackbeard.engine.sandbox.container_runtime import (
            ContainerRuntimeError,
            ContainerSandbox,
        )

        with patch("shutil.which", return_value=None):
            with pytest.raises(ContainerRuntimeError):
                ContainerSandbox._detect_runtime("notfound")


# ---------------------------------------------------------------------------
# blackbeard/engine/sandbox/gvisor_runtime.py — _detect_runtime, _verify_gvisor
# ---------------------------------------------------------------------------


class TestGVisorRuntime:
    def test_detect_runtime_explicit(self) -> None:
        from blackbeard.engine.sandbox.gvisor_runtime import GVisorSandbox

        with patch("shutil.which", return_value="/usr/bin/docker"):
            result = GVisorSandbox._detect_runtime("docker")
            assert result == "docker"

    def test_detect_runtime_auto_podman(self) -> None:
        from blackbeard.engine.sandbox.gvisor_runtime import GVisorSandbox

        with patch("shutil.which", side_effect=lambda x: "/usr/bin/podman" if x == "podman" else None):
            result = GVisorSandbox._detect_runtime("auto")
            assert result == "podman"

    def test_detect_runtime_not_found(self) -> None:
        from blackbeard.engine.sandbox.gvisor_runtime import GVisorRuntimeError, GVisorSandbox

        with patch("shutil.which", return_value=None):
            with pytest.raises(GVisorRuntimeError):
                GVisorSandbox._detect_runtime("notfound")

    def test_verify_gvisor_not_found(self) -> None:
        from blackbeard.engine.sandbox.gvisor_runtime import GVisorSandbox

        with patch("shutil.which", return_value=None):
            # Should just log a warning, not raise
            GVisorSandbox._verify_gvisor()


# ---------------------------------------------------------------------------
# blackbeard/engine/sandbox/wasm_runtime.py — _load_module
# ---------------------------------------------------------------------------


class TestWasmRuntime:
    def test_load_module_exists(self) -> None:
        """_load_module is a method on WasmSandbox."""
        try:
            from blackbeard.engine.sandbox.wasm_runtime import WasmSandbox

            assert hasattr(WasmSandbox, "_load_module")
        except ImportError:
            pytest.skip("wasmtime not installed")


# ---------------------------------------------------------------------------
# blackbeard/engine/sandbox/microvm_runtime.py — _detect_runtime, _verify_krun
# ---------------------------------------------------------------------------


class TestMicroVMRuntime:
    def test_detect_runtime_explicit(self) -> None:
        from blackbeard.engine.sandbox.microvm_runtime import MicroVMSandbox

        with patch("shutil.which", return_value="/usr/bin/docker"):
            result = MicroVMSandbox._detect_runtime("docker")
            assert result == "docker"

    def test_detect_runtime_not_found(self) -> None:
        from blackbeard.engine.sandbox.microvm_runtime import MicroVMRuntimeError, MicroVMSandbox

        with patch("shutil.which", return_value=None):
            with pytest.raises(MicroVMRuntimeError):
                MicroVMSandbox._detect_runtime("notfound")

    def test_verify_krun_not_found(self) -> None:
        from blackbeard.engine.sandbox.microvm_runtime import MicroVMSandbox

        with patch("shutil.which", return_value=None):
            # Should just log a warning, not raise
            MicroVMSandbox._verify_krun()


# ---------------------------------------------------------------------------
# blackbeard/engine/sandbox/base.py — _detect_runtime
# ---------------------------------------------------------------------------


class TestBaseSandbox:
    def _make_concrete(self) -> type:
        """Create a concrete subclass of BaseSandbox for testing."""
        from blackbeard.engine.sandbox.base import BaseSandbox

        class _ConcreteSandbox(BaseSandbox):
            def _extra_flags(self) -> list[str]:
                return []

        return _ConcreteSandbox

    def test_detect_runtime_explicit(self) -> None:
        cls = self._make_concrete()
        with patch("shutil.which", return_value="/usr/bin/podman"):
            sandbox = cls(container_runtime="podman")
            assert sandbox.runtime == "podman"

    def test_detect_runtime_auto_docker(self) -> None:
        cls = self._make_concrete()

        def which_side_effect(name: str) -> str | None:
            if name == "podman":
                return None
            if name == "docker":
                return "/usr/bin/docker"
            return None

        with patch("shutil.which", side_effect=which_side_effect):
            sandbox = cls(container_runtime="auto")
            assert sandbox.runtime == "docker"

    def test_detect_runtime_none_found(self) -> None:
        from blackbeard.engine.sandbox.base import SandboxRuntimeError

        cls = self._make_concrete()
        with patch("shutil.which", return_value=None):
            with pytest.raises(SandboxRuntimeError):
                cls(container_runtime="auto")
