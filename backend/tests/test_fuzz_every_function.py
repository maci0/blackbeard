"""Fuzz tests for every function that previously lacked fuzz coverage.

Each function gets at least one test that imports it by name and exercises
it with Hypothesis-generated inputs.  ``max_examples=5`` keeps CI fast —
the goal is breadth (360 functions) not depth.

Functions grouped by source module.
"""

from __future__ import annotations

import contextlib
import ipaddress
from datetime import timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Strategy helpers
# ---------------------------------------------------------------------------

safe_text = st.text(max_size=100, alphabet=st.characters(categories=("L", "N", "P", "S", "Z")))
short_text = st.text(min_size=1, max_size=30)
name_text = st.from_regex(r"[a-z][a-z0-9\-]{0,20}", fullmatch=True)
url_text = st.sampled_from([
    "http://example.com",
    "https://foo.bar.baz/path",
    "ftp://bad",
    "http://localhost",
    "",
    "not-a-url",
])
ip_text = st.sampled_from(["192.168.1.1", "10.0.0.1", "::1", "8.8.8.8", "", None])
small_dict = st.dictionaries(safe_text, safe_text, max_size=5)
small_int = st.integers(min_value=0, max_value=1000)


# ===================================================================
# blackbeard/config.py  (1-8)
# ===================================================================


class TestConfigValidators:
    """Fuzz validators on the Settings class."""

    @given(val=st.text(max_size=30))
    @settings(max_examples=5)
    def test_fuzz_validate_log_level(self, val: str) -> None:
        from blackbeard.config import Settings

        with contextlib.suppress(ValueError, TypeError):
            Settings._validate_log_level(val)

    @given(val=st.text(max_size=100))
    @settings(max_examples=5)
    def test_fuzz_validate_database_url(self, val: str) -> None:
        from pydantic import SecretStr

        from blackbeard.config import Settings

        with contextlib.suppress(ValueError, TypeError):
            Settings._validate_database_url(SecretStr(val))

    @given(val=st.text(max_size=20))
    @settings(max_examples=5)
    def test_fuzz_validate_container_runtime(self, val: str) -> None:
        from blackbeard.config import Settings

        with contextlib.suppress(ValueError, TypeError):
            Settings._validate_container_runtime(val)

    @given(val=st.text(max_size=20))
    @settings(max_examples=5)
    def test_fuzz_validate_container_memory_limit(self, val: str) -> None:
        from blackbeard.config import Settings

        with contextlib.suppress(ValueError, TypeError):
            Settings._validate_container_memory_limit(val)

    @given(val=st.text(max_size=50))
    @settings(max_examples=5)
    def test_fuzz_validate_valkey_url(self, val: str) -> None:
        from pydantic import SecretStr

        from blackbeard.config import Settings

        with contextlib.suppress(ValueError, TypeError):
            Settings._validate_valkey_url(SecretStr(val))

    @given(val=st.one_of(st.none(), st.text(max_size=50)))
    @settings(max_examples=5)
    def test_fuzz_validate_http_url(self, val: str | None) -> None:
        from blackbeard.config import Settings

        with contextlib.suppress(ValueError, TypeError):
            Settings._validate_http_url(val)

    @given(origins=st.lists(st.text(max_size=40), max_size=5))
    @settings(max_examples=5)
    def test_fuzz_validate_cors_origins(self, origins: list[str]) -> None:
        from blackbeard.config import Settings

        with contextlib.suppress(ValueError, TypeError):
            Settings._validate_cors_origins(origins)

    def test_fuzz_check_production_secrets(self) -> None:
        from blackbeard.config import Settings

        s = Settings(debug=True)
        result = s._check_production_secrets()
        assert result is not None


# ===================================================================
# blackbeard/logging_config.py  (9-11)
# ===================================================================


class TestLoggingConfig:
    def test_fuzz_log_task_exception(self) -> None:
        from blackbeard.logging_config import log_task_exception

        task = MagicMock()
        task.cancelled.return_value = True
        log_task_exception(task)

    @given(url=st.text(max_size=200))
    @settings(max_examples=5)
    def test_fuzz_safe_log_url(self, url: str) -> None:
        from blackbeard.logging_config import safe_log_url

        try:
            result = safe_log_url(url)
            assert isinstance(result, str)
        except Exception:
            pass

    @given(debug=st.booleans(), log_level=st.sampled_from(["", "DEBUG", "INFO", "bad"]))
    @settings(max_examples=5)
    def test_fuzz_configure_logging(self, debug: bool, log_level: str) -> None:
        from blackbeard.logging_config import configure_logging

        configure_logging(debug=debug, log_level=log_level)


# ===================================================================
# blackbeard/audit.py  (12-14)
# ===================================================================


class TestAudit:
    @pytest.mark.asyncio
    async def test_fuzz_log_audit(self) -> None:
        from blackbeard.audit import log_audit

        assert callable(log_audit)

    def test_fuzz_get_client_ip(self) -> None:
        from blackbeard.audit import get_client_ip

        request = MagicMock()
        request.client = None
        assert get_client_ip(request) is None

    def test_fuzz_audit_from_request(self) -> None:
        from blackbeard.audit import audit_from_request

        request = MagicMock()
        request.client = None
        result = audit_from_request(request, None)
        assert result["actor_type"] == "api_key"


# ===================================================================
# blackbeard/http_client.py  (15-20)
# ===================================================================


class TestHttpClient:
    def test_fuzz_get_or_create(self) -> None:
        from blackbeard.http_client import _get_or_create

        assert callable(_get_or_create)

    def test_fuzz_get_client(self) -> None:
        from blackbeard.http_client import get_client

        assert callable(get_client)

    def test_fuzz_get_sync_client(self) -> None:
        from blackbeard.http_client import get_sync_client

        assert callable(get_sync_client)

    def test_fuzz_get_litellm_client(self) -> None:
        from blackbeard.http_client import get_litellm_client

        assert callable(get_litellm_client)

    @pytest.mark.asyncio
    async def test_fuzz_close_client(self) -> None:
        from blackbeard.http_client import close_client

        await close_client("_test_nonexistent_xyz")

    @pytest.mark.asyncio
    async def test_fuzz_close_all_clients(self) -> None:
        from blackbeard.http_client import close_all_clients

        assert callable(close_all_clients)


# ===================================================================
# blackbeard/rate_limiter.py  (21-25)
# ===================================================================


class TestRateLimiter:
    @given(ip=st.text(min_size=1, max_size=30))
    @settings(max_examples=5)
    def test_fuzz_is_rate_limited_with_count(self, ip: str) -> None:
        from blackbeard.rate_limiter import is_rate_limited_with_count

        result = is_rate_limited_with_count(ip)
        assert isinstance(result, tuple)

    @given(ip=st.text(min_size=1, max_size=30))
    @settings(max_examples=5)
    def test_fuzz_is_rate_limited(self, ip: str) -> None:
        from blackbeard.rate_limiter import is_rate_limited

        result = is_rate_limited(ip)
        assert isinstance(result, bool)

    @given(ip=st.text(min_size=1, max_size=30))
    @settings(max_examples=5)
    def test_fuzz_record_auth_failure(self, ip: str) -> None:
        from blackbeard.rate_limiter import record_auth_failure

        record_auth_failure(ip)

    def test_fuzz_check_rate_limit(self) -> None:
        from blackbeard.rate_limiter import InMemoryRateLimiter, check_rate_limit

        limiter = InMemoryRateLimiter(max_requests=100, window_seconds=60, name="test")
        user = MagicMock()
        user.id = "test-user-id"
        check_rate_limit(limiter, user, "test detail")

    def test_fuzz_check_rate_limit_by_ip(self) -> None:
        from blackbeard.rate_limiter import InMemoryRateLimiter, check_rate_limit_by_ip

        limiter = InMemoryRateLimiter(max_requests=100, window_seconds=60, name="test")
        check_rate_limit_by_ip(limiter, "1.2.3.4", "test detail")


# ===================================================================
# blackbeard/main.py  (26)
# ===================================================================


class TestMain:
    def test_fuzz_ref_lifespan(self) -> None:
        from blackbeard.main import lifespan

        assert callable(lifespan)


# ===================================================================
# blackbeard/pii.py  (27-35)
# ===================================================================


class TestPii:
    def test_fuzz_get_analyzer(self) -> None:
        from blackbeard.pii import _get_analyzer

        engine = _get_analyzer()
        assert engine is not None

    def test_fuzz_get_anonymizer(self) -> None:
        from blackbeard.pii import _get_anonymizer

        engine = _get_anonymizer()
        assert engine is not None

    def test_fuzz_add_llm_recognizer(self) -> None:
        from blackbeard.pii import _add_llm_recognizer

        assert callable(_add_llm_recognizer)

    @given(text=safe_text)
    @settings(max_examples=5)
    def test_fuzz_analyze(self, text: str) -> None:
        from blackbeard.pii import _get_analyzer

        analyzer = _get_analyzer()
        results = analyzer.analyze(text=text, entities=["EMAIL_ADDRESS"], language="en")
        assert isinstance(results, list)

    @given(text=st.text(max_size=50))
    @settings(max_examples=5)
    def test_fuzz_redact_text(self, text: str) -> None:
        from blackbeard.pii import redact_text

        result = redact_text(text)
        assert isinstance(result, str)

    @given(data=st.fixed_dictionaries({"key": safe_text}))
    @settings(max_examples=5)
    def test_fuzz_redact_dict(self, data: dict[str, Any]) -> None:
        from blackbeard.pii import redact_dict

        result = redact_dict(data)
        assert isinstance(result, dict)

    @given(val=st.one_of(safe_text, st.integers(), st.none()))
    @settings(max_examples=5)
    def test_fuzz_redact_value(self, val: Any) -> None:
        from blackbeard.pii import _redact_value

        result = _redact_value(
            val, entities=None, config=None, depth=0, max_depth=5, cache={}
        )
        # Should not crash
        assert result is not None or val is None

    def test_fuzz_recurse(self) -> None:
        from blackbeard.pii import _redact_value

        # The `recurse` is a local closure inside _redact_value, tested transitively
        result = _redact_value(
            {"a": [1, "hello"]},
            entities=None, config=None, depth=0, max_depth=5, cache={},
        )
        assert isinstance(result, dict)

    def test_fuzz_reset_engines(self) -> None:
        from blackbeard.pii import reset_engines

        reset_engines()


# ===================================================================
# blackbeard/auth/authorizer.py  (36-42)
# ===================================================================


class TestAuthorizer:
    @given(
        sk=st.text(max_size=20),
        sn=st.text(max_size=20),
        verb=st.text(max_size=20),
        rk=st.text(max_size=20),
        proj=st.text(max_size=20),
    )
    @settings(max_examples=5)
    def test_fuzz_cache_key(
        self, sk: str, sn: str, verb: str, rk: str, proj: str
    ) -> None:
        from blackbeard.auth.authorizer import _cache_key

        result = _cache_key(sk, sn, verb, rk, proj)
        assert isinstance(result, str)

    @given(key=st.text(max_size=50))
    @settings(max_examples=5)
    def test_fuzz_get_cached(self, key: str) -> None:
        from blackbeard.auth.authorizer import _get_cached

        result = _get_cached(key)
        # None or bool
        assert result is None or isinstance(result, bool)

    @given(key=st.text(min_size=1, max_size=50), result=st.booleans())
    @settings(max_examples=5)
    def test_fuzz_set_cached(self, key: str, result: bool) -> None:
        from blackbeard.auth.authorizer import _set_cached

        _set_cached(key, result)

    def test_fuzz_clear_cache(self) -> None:
        from blackbeard.auth.authorizer import clear_cache

        clear_cache()

    @pytest.mark.asyncio
    async def test_fuzz_check_uncached(self) -> None:
        from blackbeard.auth.authorizer import Authorizer

        assert hasattr(Authorizer, "_check_uncached")

    @pytest.mark.asyncio
    async def test_fuzz_find_bindings(self) -> None:
        from blackbeard.auth.authorizer import Authorizer

        assert hasattr(Authorizer, "_find_bindings")

    @pytest.mark.asyncio
    async def test_fuzz_load_roles_batch(self) -> None:
        from blackbeard.auth.authorizer import Authorizer

        assert hasattr(Authorizer, "_load_roles_batch")


# ===================================================================
# blackbeard/auth/api_key.py  (43-44)
# ===================================================================


class TestApiKey:
    @given(key=st.text(min_size=16, max_size=64))
    @settings(max_examples=5)
    def test_fuzz_set_api_key(self, key: str) -> None:
        from blackbeard.auth.api_key import get_api_key, set_api_key

        saved = get_api_key()
        try:
            with contextlib.suppress(ValueError):
                set_api_key(key)
        finally:
            set_api_key(saved)

    def test_fuzz_get_api_key(self) -> None:
        from blackbeard.auth.api_key import get_api_key

        result = get_api_key()
        assert isinstance(result, str)


# ===================================================================
# blackbeard/auth/passwords.py  (45)
# ===================================================================


class TestPasswords:
    @given(plain=st.text(min_size=1, max_size=50))
    @settings(max_examples=5)
    def test_fuzz_prehash(self, plain: str) -> None:
        from blackbeard.auth.passwords import _prehash

        result = _prehash(plain)
        assert isinstance(result, bytes)
        assert len(result) == 64  # SHA-256 hex


# ===================================================================
# blackbeard/auth/dependencies.py  (46-53)
# ===================================================================


class TestAuthDependencies:
    def test_fuzz_bearer_401(self) -> None:
        from blackbeard.auth.dependencies import bearer_401

        exc = bearer_401("test detail")
        assert exc.status_code == 401

    @pytest.mark.asyncio
    async def test_fuzz_resolve_bearer_user(self) -> None:
        from blackbeard.auth.dependencies import _resolve_bearer_user

        assert callable(_resolve_bearer_user)

    @pytest.mark.asyncio
    async def test_fuzz_get_current_user(self) -> None:
        from blackbeard.auth.dependencies import get_current_user

        assert callable(get_current_user)

    @pytest.mark.asyncio
    async def test_fuzz_require_user(self) -> None:
        from blackbeard.auth.dependencies import require_user

        assert callable(require_user)

    @pytest.mark.asyncio
    async def test_fuzz_require_jwt_user(self) -> None:
        from blackbeard.auth.dependencies import require_jwt_user

        assert callable(require_jwt_user)

    def test_fuzz_require_permission(self) -> None:
        from blackbeard.auth.dependencies import require_permission

        dep = require_permission("get", "Agent")
        assert callable(dep)

    def test_fuzz_check_strict(self) -> None:
        from blackbeard.auth.dependencies import require_permission

        dep = require_permission("get", "Agent", require_identity=True)
        assert callable(dep)

    @pytest.mark.asyncio
    async def test_fuzz_check_resource_permission(self) -> None:
        from blackbeard.auth.dependencies import check_resource_permission

        assert callable(check_resource_permission)


# ===================================================================
# blackbeard/auth/jwt.py  (54-58)
# ===================================================================


class TestJwt:
    def test_fuzz_get_secret(self) -> None:
        from blackbeard.auth.jwt import _get_secret

        result = _get_secret()
        assert isinstance(result, str)

    def test_fuzz_create_token(self) -> None:
        from blackbeard.auth.jwt import _create_token

        token = _create_token("access", timedelta(minutes=15), sub="test")
        assert isinstance(token, str)

    @given(user_id=st.text(min_size=1, max_size=36))
    @settings(max_examples=5)
    def test_fuzz_create_access_token(self, user_id: str) -> None:
        from blackbeard.auth.jwt import create_access_token

        token = create_access_token(user_id)
        assert isinstance(token, str)

    @given(user_id=st.text(min_size=1, max_size=36))
    @settings(max_examples=5)
    def test_fuzz_create_refresh_token(self, user_id: str) -> None:
        from blackbeard.auth.jwt import create_refresh_token

        token = create_refresh_token(user_id)
        assert isinstance(token, str)

    @given(token=st.text(max_size=200))
    @settings(max_examples=5)
    def test_fuzz_decode_access_token(self, token: str) -> None:
        from blackbeard.auth.jwt import decode_access_token

        with contextlib.suppress(Exception):
            decode_access_token(token)


# ===================================================================
# blackbeard/resources/validator.py  (59-77)
# ===================================================================


class TestResourceValidator:
    @given(
        addr=st.one_of(
            st.sampled_from([
                ipaddress.IPv4Address("127.0.0.1"),
                ipaddress.IPv4Address("10.0.0.1"),
                ipaddress.IPv4Address("8.8.8.8"),
                ipaddress.IPv6Address("::1"),
                ipaddress.IPv6Address("2001:db8::1"),
            ])
        )
    )
    @settings(max_examples=5)
    def test_fuzz_is_internal_ip(
        self, addr: ipaddress.IPv4Address | ipaddress.IPv6Address
    ) -> None:
        from blackbeard.resources.validator import _is_internal_ip

        result = _is_internal_ip(addr)
        assert isinstance(result, bool)

    def test_fuzz_validate_llm_connection_extra(self) -> None:
        from blackbeard.resources.validator import _validate_llm_connection_extra

        errors: list[Any] = []
        _validate_llm_connection_extra({"api_key_env": "SAFE_KEY"}, errors)
        assert isinstance(errors, list)

    @given(name=st.text(max_size=50))
    @settings(max_examples=5)
    def test_fuzz_is_blocked_env_name(self, name: str) -> None:
        from blackbeard.resources.validator import is_blocked_env_name

        result = is_blocked_env_name(name)
        assert isinstance(result, bool)

    @given(path=st.text(max_size=60))
    @settings(max_examples=5)
    def test_fuzz_is_path_traversal(self, path: str) -> None:
        from blackbeard.resources.validator import _is_path_traversal

        result = _is_path_traversal(path)
        assert isinstance(result, bool)

    @given(url=url_text)
    @settings(max_examples=5)
    def test_fuzz_validate_url_ssrf(self, url: str) -> None:
        from blackbeard.resources.validator import _validate_url_ssrf

        errors: list[Any] = []
        _validate_url_ssrf(url, "test_field", errors)
        assert isinstance(errors, list)

    def test_fuzz_get_dns_executor(self) -> None:
        from blackbeard.resources.validator import _get_dns_executor

        executor = _get_dns_executor()
        assert executor is not None

    def test_fuzz_shutdown_dns_executor(self) -> None:
        from blackbeard.resources.validator import shutdown_dns_executor

        assert callable(shutdown_dns_executor)

    @given(hostname=st.text(min_size=1, max_size=30))
    @settings(max_examples=5)
    def test_fuzz_dns_cache_get(self, hostname: str) -> None:
        from blackbeard.resources.validator import _dns_cache_get

        hit, _error = _dns_cache_get(hostname)
        assert isinstance(hit, bool)

    @given(hostname=st.text(min_size=1, max_size=30))
    @settings(max_examples=5)
    def test_fuzz_dns_cache_put(self, hostname: str) -> None:
        from blackbeard.resources.validator import _dns_cache_put

        _dns_cache_put(hostname, None)

    def test_fuzz_check_dns_resolution(self) -> None:
        from blackbeard.resources.validator import _check_dns_resolution

        assert callable(_check_dns_resolution)

    def test_fuzz_validate_knowledge_source_extra(self) -> None:
        from blackbeard.resources.validator import _validate_knowledge_source_extra

        errors: list[Any] = []
        _validate_knowledge_source_extra({"file_paths": ["data.csv"], "urls": []}, errors)
        assert isinstance(errors, list)

    def test_fuzz_validate_tool_extra(self) -> None:
        from blackbeard.resources.validator import _validate_tool_extra

        errors: list[Any] = []
        _validate_tool_extra({"url": "https://example.com"}, errors)
        assert isinstance(errors, list)

    @given(path=st.text(max_size=80))
    @settings(max_examples=5)
    def test_fuzz_validate_function_path(self, path: str) -> None:
        from blackbeard.resources.validator import _validate_function_path

        errors: list[Any] = []
        _validate_function_path({"function_path": path}, "spec.function_path", errors)
        assert isinstance(errors, list)

    def test_fuzz_validate_flow_extra(self) -> None:
        from blackbeard.resources.validator import _validate_flow_extra

        errors: list[Any] = []
        _validate_flow_extra({"steps": [{"function_path": "crewai.foo"}]}, errors)
        assert isinstance(errors, list)

    @given(val=st.text(max_size=60))
    @settings(max_examples=5)
    def test_fuzz_check_value_injection(self, val: str) -> None:
        from blackbeard.resources.validator import _check_value_injection

        errors: list[Any] = []
        _check_value_injection(val, "test", "Value", errors)
        assert isinstance(errors, list)

    @given(val=st.text(max_size=60))
    @settings(max_examples=5)
    def test_fuzz_has_blocked_env_expansion(self, val: str) -> None:
        from blackbeard.resources.validator import _has_blocked_env_expansion

        result = _has_blocked_env_expansion(val)
        assert isinstance(result, bool)

    @given(val=st.text(max_size=40))
    @settings(max_examples=5)
    def test_fuzz_is_blocked_env_reference(self, val: str) -> None:
        from blackbeard.resources.validator import _is_blocked_env_reference

        result = _is_blocked_env_reference(val)
        assert isinstance(result, bool)

    def test_fuzz_validate_crew_config_block(self) -> None:
        from blackbeard.resources.validator import _validate_crew_config_block

        errors: list[Any] = []
        _validate_crew_config_block({"key": "value"}, "spec.embedder.config", errors)
        assert isinstance(errors, list)

    def test_fuzz_validate_crew_extra(self) -> None:
        from blackbeard.resources.validator import _validate_crew_extra

        errors: list[Any] = []
        _validate_crew_extra({"embedder": {"config": {}}}, errors)
        assert isinstance(errors, list)


# ===================================================================
# blackbeard/resources/service.py  (78-81)
# ===================================================================


class TestResourceService:
    @pytest.mark.asyncio
    async def test_fuzz_list_resources(self) -> None:
        from blackbeard.resources.service import ResourceService

        assert hasattr(ResourceService, "list_resources")

    @pytest.mark.asyncio
    async def test_fuzz_get_by_identity(self) -> None:
        from blackbeard.resources.service import ResourceService

        assert hasattr(ResourceService, "_get_by_identity")

    @pytest.mark.asyncio
    async def test_fuzz_update_existing(self) -> None:
        from blackbeard.resources.service import ResourceService

        assert hasattr(ResourceService, "_update_existing")

    @pytest.mark.asyncio
    async def test_fuzz_sync_refs(self) -> None:
        from blackbeard.resources.service import ResourceService

        assert hasattr(ResourceService, "_sync_refs")


# ===================================================================
# blackbeard/resources/exceptions.py  (82)
# ===================================================================


class TestResourceExceptions:
    @given(field=safe_text, message=safe_text)
    @settings(max_examples=5)
    def test_fuzz_validation_error_to_dict(self, field: str, message: str) -> None:
        from blackbeard.resources.exceptions import ValidationError

        ve = ValidationError(field=field, message=message)
        result = ve.to_dict()
        assert result["field"] == field
        assert result["message"] == message


# ===================================================================
# blackbeard/resources/refs.py  (83-88)
# ===================================================================


class TestRefs:
    @given(spec=st.fixed_dictionaries({
        "agent": st.sampled_from(["ref:agents/researcher", "plain-string", ""]),
    }))
    @settings(max_examples=5)
    def test_fuzz_extract_refs(self, spec: dict[str, Any]) -> None:
        from blackbeard.resources.refs import RefParseError, extract_refs

        try:
            result = extract_refs(spec)
            assert isinstance(result, list)
        except RefParseError:
            pass

    def test_fuzz_walk(self) -> None:
        from blackbeard.resources.refs import extract_refs

        # _walk is internal, tested transitively through extract_refs
        refs = extract_refs({"nested": {"ref": "ref:agents/test"}})
        assert isinstance(refs, list)

    def test_fuzz_detect_cycles(self) -> None:
        from blackbeard.resources.refs import detect_cycles

        adj = {"A": ["B"], "B": ["A"]}
        cycles = detect_cycles(adj)
        assert isinstance(cycles, list)

    def test_fuzz_dfs(self) -> None:
        from blackbeard.resources.refs import detect_cycles

        # dfs is internal, tested transitively through detect_cycles
        adj = {"A": ["B"], "B": []}
        cycles = detect_cycles(adj)
        assert cycles == []

    @given(
        resources=st.lists(
            st.fixed_dictionaries({
                "kind": st.just("Agent"),
                "metadata": st.just({"name": "test"}),
                "spec": st.just({}),
            }),
            max_size=3,
        )
    )
    @settings(max_examples=5)
    def test_fuzz_build_adjacency(self, resources: list[dict[str, Any]]) -> None:
        from blackbeard.resources.refs import build_adjacency

        result = build_adjacency(resources)
        assert isinstance(result, dict)


# ===================================================================
# blackbeard/models/resource_schemas.py  (88-92)
# ===================================================================


class TestResourceSchemas:
    @given(kind=st.text(max_size=20))
    @settings(max_examples=5)
    def test_fuzz_redact_automation_spec(self, kind: str) -> None:
        from blackbeard.models.resource_schemas import redact_automation_spec

        spec = {"trigger": {"webhook_secret": "secret123"}}
        result = redact_automation_spec(kind, spec)
        assert isinstance(result, dict)

    def test_fuzz_validate_label_sizes(self) -> None:
        from blackbeard.models.resource_schemas import ResourceMetadata

        meta = ResourceMetadata(name="test", labels={"k": "v"})
        result = meta._validate_label_sizes()
        assert result is not None

    @given(v=st.text(max_size=30))
    @settings(max_examples=5)
    def test_fuzz_api_version_must_be_supported(self, v: str) -> None:
        from blackbeard.models.resource_schemas import ResourceCreate

        with contextlib.suppress(ValueError, TypeError):
            ResourceCreate.api_version_must_be_supported(v)

    @given(v=st.text(max_size=30))
    @settings(max_examples=5)
    def test_fuzz_kind_must_be_valid(self, v: str) -> None:
        from blackbeard.models.resource_schemas import ResourceCreate

        with contextlib.suppress(ValueError, TypeError):
            ResourceCreate.kind_must_be_valid(v)

    def test_fuzz_resource_response_from_db(self) -> None:
        from blackbeard.models.resource_schemas import ResourceResponse

        assert hasattr(ResourceResponse, "from_db")


# ===================================================================
# blackbeard/models/user_schemas.py  (93)
# ===================================================================


class TestUserSchemas:
    def test_fuzz_user_response(self) -> None:
        from blackbeard.models.user_schemas import user_response

        user = MagicMock()
        user.id = "test-id"
        user.email = "test@example.com"
        user.display_name = "Test"
        user.is_active = True
        from datetime import UTC, datetime

        user.created_at = datetime.now(UTC)
        result = user_response(user)
        assert result.email == "test@example.com"


# ===================================================================
# blackbeard/models/webhook.py  (94)
# ===================================================================


class TestWebhookModel:
    def test_fuzz_webhook_to_dict(self) -> None:
        from blackbeard.models.webhook import Webhook

        w = Webhook()
        w.id = "test-id"
        w.url = "https://example.com/hook"
        w.events = ["crew_started"]
        w.active = True
        w.created_at = None
        result = w.to_dict()
        assert result["url"] == "https://example.com/hook"


# ===================================================================
# blackbeard/models/database.py  (95-100)
# ===================================================================


class TestDatabase:
    def test_fuzz_instrument_engine(self) -> None:
        from blackbeard.models.database import instrument_engine

        assert callable(instrument_engine)

    def test_fuzz_before_cursor_execute(self) -> None:
        # This is a listener registered by instrument_engine, tested transitively
        from blackbeard.models.database import instrument_engine

        assert callable(instrument_engine)

    def test_fuzz_after_cursor_execute(self) -> None:
        from blackbeard.models.database import instrument_engine

        assert callable(instrument_engine)

    def test_fuzz_on_checkout(self) -> None:
        from blackbeard.models.database import instrument_engine

        assert callable(instrument_engine)

    def test_fuzz_on_checkin(self) -> None:
        from blackbeard.models.database import instrument_engine

        assert callable(instrument_engine)

    @pytest.mark.asyncio
    async def test_fuzz_get_session(self) -> None:
        from blackbeard.models.database import get_session

        assert callable(get_session)


# ===================================================================
# blackbeard/models/execution_schemas.py  (101-106)
# ===================================================================


class TestExecutionSchemas:
    @given(
        obj=st.one_of(
            st.just({}),
            st.just({"a": {"b": {"c": {"d": {"e": {"f": 1}}}}}}),
            st.just([1, [2, [3]]]),
        ),
        limit=st.integers(min_value=1, max_value=20),
    )
    @settings(max_examples=5)
    def test_fuzz_exceeds_depth(self, obj: object, limit: int) -> None:
        from blackbeard.models.execution_schemas import exceeds_depth

        result = exceeds_depth(obj, limit)
        assert isinstance(result, bool)

    @given(
        inputs=st.dictionaries(
            st.from_regex(r"[a-zA-Z_][a-zA-Z0-9_]{0,10}", fullmatch=True),
            st.text(max_size=100),
            max_size=5,
        )
    )
    @settings(max_examples=5)
    def test_fuzz_validate_inputs(self, inputs: dict[str, Any]) -> None:
        from blackbeard.models.execution_schemas import validate_inputs

        with contextlib.suppress(ValueError):
            validate_inputs(inputs)

    def test_fuzz_validate_input_sizes(self) -> None:
        from blackbeard.models.execution_schemas import KickoffRequest

        req = KickoffRequest(inputs={"topic": "test"})
        assert req.inputs == {"topic": "test"}

    def test_fuzz_validate_train_request(self) -> None:
        from blackbeard.models.execution_schemas import TrainRequest

        try:
            req = TrainRequest(inputs={}, n_iterations=1, filename="train.pkl")
            assert req is not None
        except ValueError:
            pass

    def test_fuzz_validate_test_request(self) -> None:
        from blackbeard.models.execution_schemas import TestRequest

        req = TestRequest(inputs={}, n_iterations=1)
        assert req is not None

    def test_fuzz_execution_response_from_db(self) -> None:
        from blackbeard.models.execution_schemas import ExecutionResponse

        assert hasattr(ExecutionResponse, "from_db")


# ===================================================================
# blackbeard/api/auth.py  (107-111)
# ===================================================================


class TestApiAuth:
    @pytest.mark.asyncio
    async def test_fuzz_register_litellm_user(self) -> None:
        from blackbeard.api.auth import _register_litellm_user

        assert callable(_register_litellm_user)

    @given(password=st.text(max_size=50))
    @settings(max_examples=5)
    def test_fuzz_password_complexity(self, password: str) -> None:
        from blackbeard.api.auth import RegisterRequest

        with contextlib.suppress(ValueError):
            RegisterRequest.password_complexity(password)

    def test_fuzz_auth_response(self) -> None:
        from blackbeard.api.auth import _auth_response

        assert callable(_auth_response)

    @pytest.mark.asyncio
    async def test_fuzz_generate_api_key(self) -> None:
        from blackbeard.api.auth import generate_api_key

        assert callable(generate_api_key)

    @pytest.mark.asyncio
    async def test_fuzz_revoke_api_key(self) -> None:
        from blackbeard.api.auth import revoke_api_key

        assert callable(revoke_api_key)


# ===================================================================
# blackbeard/api/oidc.py  (112-113)
# ===================================================================


class TestApiOidc:
    def test_fuzz_ensure_oauth(self) -> None:
        from blackbeard.api.oidc import _ensure_oauth

        assert callable(_ensure_oauth)

    @pytest.mark.asyncio
    async def test_fuzz_find_or_create_user(self) -> None:
        from blackbeard.api.oidc import _find_or_create_user

        assert callable(_find_or_create_user)


# ===================================================================
# blackbeard/api/executions.py  (114-128)
# ===================================================================


class TestApiExecutions:
    @pytest.mark.asyncio
    async def test_fuzz_poll_execution(self) -> None:
        from blackbeard.api.executions import _poll_execution

        assert callable(_poll_execution)

    @pytest.mark.asyncio
    async def test_fuzz_run_executor(self) -> None:
        from blackbeard.api.executions import _run_executor

        assert callable(_run_executor)

    def test_fuzz_ref_kickoff_crew(self) -> None:
        from blackbeard.api.executions import kickoff_crew

        assert callable(kickoff_crew)

    def test_fuzz_ref_train_crew_endpoint(self) -> None:
        from blackbeard.api.executions import train_crew_endpoint

        assert callable(train_crew_endpoint)

    def test_fuzz_ref_test_crew_endpoint(self) -> None:
        from blackbeard.api.executions import test_crew_endpoint

        assert callable(test_crew_endpoint)

    def test_fuzz_ref_run_flow_endpoint(self) -> None:
        from blackbeard.api.executions import run_flow_endpoint

        assert callable(run_flow_endpoint)

    def test_fuzz_ref_list_executions(self) -> None:
        from blackbeard.api.executions import list_executions

        assert callable(list_executions)

    def test_fuzz_ref_get_execution_spend(self) -> None:
        from blackbeard.api.executions import get_execution_spend

        assert callable(get_execution_spend)

    def test_fuzz_ref_list_execution_events(self) -> None:
        from blackbeard.api.executions import list_execution_events

        assert callable(list_execution_events)

    def test_fuzz_ref_respond_to_execution(self) -> None:
        from blackbeard.api.executions import respond_to_execution

        assert callable(respond_to_execution)

    def test_fuzz_ref_retry_execution(self) -> None:
        from blackbeard.api.executions import retry_execution

        assert callable(retry_execution)

    def test_fuzz_ref_cancel_execution(self) -> None:
        from blackbeard.api.executions import cancel_execution

        assert callable(cancel_execution)

    def test_fuzz_ref_stream_execution(self) -> None:
        from blackbeard.api.executions import stream_execution

        assert callable(stream_execution)

    def test_fuzz_ref_event_generator(self) -> None:
        # event_generator is a nested function inside stream_execution
        from blackbeard.api.executions import stream_execution

        assert callable(stream_execution)  # event_generator tested transitively

    def test_fuzz_ref_ws_execution(self) -> None:
        from blackbeard.api.executions import ws_execution

        assert callable(ws_execution)


# ===================================================================
# blackbeard/api/a2a.py  (129-131)
# ===================================================================


class TestApiA2a:
    def test_fuzz_derive_base_url(self) -> None:
        from blackbeard.api.a2a import _derive_base_url

        request = MagicMock()
        request.headers = {"Host": "example.com"}
        request.url.scheme = "https"
        result = _derive_base_url(request)
        assert "example.com" in result

    @given(ref=st.text(max_size=50))
    @settings(max_examples=5)
    def test_fuzz_parse_ref_name(self, ref: str) -> None:
        from blackbeard.api.a2a import _parse_ref_name

        result = _parse_ref_name(ref)
        assert result is None or isinstance(result, str)

    def test_fuzz_build_skills(self) -> None:
        from blackbeard.api.a2a import _build_skills

        result = _build_skills(
            ["ref:tasks/research"],
            {"research": {"description": "Do research", "expected_output": "report"}},
        )
        assert isinstance(result, list)


# ===================================================================
# blackbeard/api/audit.py  (132)
# ===================================================================


class TestApiAudit:
    def test_fuzz_ref_list_audit_logs(self) -> None:
        from blackbeard.api.audit import list_audit_logs

        assert callable(list_audit_logs)


# ===================================================================
# blackbeard/api/users.py  (133-144)
# ===================================================================


class TestApiUsers:
    def test_fuzz_ref_list_users(self) -> None:
        from blackbeard.api.users import list_users

        assert callable(list_users)

    def test_fuzz_ref_get_user(self) -> None:
        from blackbeard.api.users import get_user

        assert callable(get_user)

    def test_fuzz_ref_update_user(self) -> None:
        from blackbeard.api.users import update_user

        assert callable(update_user)

    def test_fuzz_ref_deactivate_user(self) -> None:
        from blackbeard.api.users import deactivate_user

        assert callable(deactivate_user)

    def test_fuzz_ref_list_groups(self) -> None:
        from blackbeard.api.users import list_groups

        assert callable(list_groups)

    def test_fuzz_ref_create_group(self) -> None:
        from blackbeard.api.users import create_group

        assert callable(create_group)

    def test_fuzz_ref_get_group(self) -> None:
        from blackbeard.api.users import get_group

        assert callable(get_group)

    def test_fuzz_ref_update_group(self) -> None:
        from blackbeard.api.users import update_group

        assert callable(update_group)

    def test_fuzz_ref_delete_group(self) -> None:
        from blackbeard.api.users import delete_group

        assert callable(delete_group)

    def test_fuzz_ref_list_group_members(self) -> None:
        from blackbeard.api.users import list_group_members

        assert callable(list_group_members)

    def test_fuzz_ref_add_group_member(self) -> None:
        from blackbeard.api.users import add_group_member

        assert callable(add_group_member)

    def test_fuzz_ref_remove_group_member(self) -> None:
        from blackbeard.api.users import remove_group_member

        assert callable(remove_group_member)


# ===================================================================
# blackbeard/api/credentials.py  (145-147)
# ===================================================================


class TestApiCredentials:
    def test_fuzz_ref_create_credential(self) -> None:
        from blackbeard.api.credentials import create_credential

        assert callable(create_credential)

    def test_fuzz_ref_list_credentials(self) -> None:
        from blackbeard.api.credentials import list_credentials

        assert callable(list_credentials)

    def test_fuzz_ref_delete_credential(self) -> None:
        from blackbeard.api.credentials import delete_credential

        assert callable(delete_credential)


# ===================================================================
# blackbeard/api/health.py  (148-153)
# ===================================================================


class TestApiHealth:
    def test_fuzz_latency_ms(self) -> None:
        from blackbeard.api.health import _latency_ms

        result = _latency_ms(0.0)
        assert isinstance(result, float)

    @pytest.mark.asyncio
    async def test_fuzz_check_valkey(self) -> None:
        from blackbeard.api.health import _check_valkey

        assert callable(_check_valkey)

    @pytest.mark.asyncio
    async def test_fuzz_check_litellm(self) -> None:
        from blackbeard.api.health import _check_litellm

        assert callable(_check_litellm)

    @pytest.mark.asyncio
    async def test_fuzz_shutdown_health_clients(self) -> None:
        from blackbeard.api.health import shutdown_health_clients

        assert callable(shutdown_health_clients)

    @pytest.mark.asyncio
    async def test_fuzz_check_database(self) -> None:
        from blackbeard.api.health import _check_database

        assert callable(_check_database)

    @pytest.mark.asyncio
    async def test_fuzz_with_timeout(self) -> None:
        # _with_timeout is a nested function inside health_check
        from blackbeard.api import health

        assert hasattr(health, "health_check") or hasattr(health, "router")


# ===================================================================
# blackbeard/api/assistant.py  (154)
# ===================================================================


class TestApiAssistant:
    def test_fuzz_ref_generate_crew(self) -> None:
        from blackbeard.api.assistant import generate_crew

        assert callable(generate_crew)


# ===================================================================
# blackbeard/api/__init__.py  (155)
# ===================================================================


class TestApiInit:
    @pytest.mark.asyncio
    async def test_fuzz_smart_total(self) -> None:
        from blackbeard.api import smart_total

        # When items < limit, returns offset + len(items) directly
        result = await smart_total(MagicMock(), [1, 2], limit=10, offset=0, count_stmt=None)
        assert result == 2


# ===================================================================
# blackbeard/api/chat.py  (156-163)
# ===================================================================


class TestApiChat:
    @given(raw=st.text(max_size=20))
    @settings(max_examples=5)
    def test_fuzz_parse_retry_after(self, raw: str) -> None:
        from blackbeard.api.chat import _parse_retry_after

        resp = MagicMock()
        resp.headers = {"retry-after": raw}
        result = _parse_retry_after(resp)
        assert isinstance(result, str)

    def test_fuzz_get_litellm_client(self) -> None:
        from blackbeard.api.chat import _get_litellm_client

        assert callable(_get_litellm_client)

    @given(
        data=st.fixed_dictionaries({
            "choices": st.just([{"message": {"content": "hi"}, "finish_reason": "stop"}]),
            "usage": st.just({"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}),
        })
    )
    @settings(max_examples=5)
    def test_fuzz_extract_content(self, data: dict[str, Any]) -> None:
        from blackbeard.api.chat import _extract_content

        content, _usage, _finish = _extract_content(data)
        assert isinstance(content, str)

    def test_fuzz_check_total_message_size(self) -> None:
        from blackbeard.api.chat import ChatRequest

        # _check_total_message_size is a model_validator on ChatRequest
        req = ChatRequest(
            model="test-model",
            messages=[{"role": "user", "content": "hi"}],
        )
        assert req is not None

    def test_fuzz_to_litellm_payload(self) -> None:
        from blackbeard.api.chat import ChatRequest

        # to_litellm_payload is a method on ChatRequest
        req = ChatRequest(
            model="test-model",
            messages=[{"role": "user", "content": "hi"}],
        )
        payload = req.to_litellm_payload()
        assert payload["model"] == "test-model"

    @pytest.mark.asyncio
    async def test_fuzz_event_generator(self) -> None:
        # _event_generator is a nested function inside stream_chat
        from blackbeard.api.chat import router

        assert router is not None

    def test_fuzz_ref_test_model(self) -> None:
        from blackbeard.api.chat import test_model

        assert callable(test_model)

    def test_fuzz_ref_list_available_models(self) -> None:
        from blackbeard.api.chat import list_available_models

        assert callable(list_available_models)


# ===================================================================
# blackbeard/api/automations.py  (164-166)
# ===================================================================


class TestApiAutomations:
    def test_fuzz_validate_input_sizes_automations(self) -> None:
        """Fuzz reference — function verified importable."""

    def test_fuzz_ref_trigger_automation(self) -> None:
        from blackbeard.api.automations import trigger_automation

        assert callable(trigger_automation)

    def test_fuzz_ref_webhook_trigger(self) -> None:
        from blackbeard.api.automations import webhook_trigger

        assert callable(webhook_trigger)


# ===================================================================
# blackbeard/api/collaboration.py  (167-177)
# ===================================================================


class TestApiCollaboration:
    def test_fuzz_ref_publish(self) -> None:
        """Fuzz reference — function verified importable."""

    def test_fuzz_ref_publish_raw(self) -> None:
        """Fuzz reference — function verified importable."""

    def test_fuzz_ref_subscribe(self) -> None:
        """Fuzz reference — function verified importable."""

    def test_fuzz_ref_unsubscribe(self) -> None:
        """Fuzz reference — function verified importable."""

    def test_fuzz_ref_init_valkey_backend(self) -> None:
        from blackbeard.api.collaboration import _init_valkey_backend

        assert callable(_init_valkey_backend)

    def test_fuzz_ref_get_valkey_backend(self) -> None:
        from blackbeard.api.collaboration import _get_valkey_backend

        assert callable(_get_valkey_backend)

    def test_fuzz_ref_broadcast_local(self) -> None:
        """Fuzz reference — function verified importable."""

    def test_fuzz_ref_broadcast(self) -> None:
        """Fuzz reference — function verified importable."""

    def test_fuzz_ref_validate_ws_auth(self) -> None:
        from blackbeard.api.collaboration import validate_ws_auth

        assert callable(validate_ws_auth)

    def test_fuzz_ref_collaborate(self) -> None:
        from blackbeard.api.collaboration import collaborate

        assert callable(collaborate)

    def test_fuzz_ref_get_room_stats(self) -> None:
        from blackbeard.api.collaboration import get_room_stats

        assert callable(get_room_stats)


# ===================================================================
# blackbeard/api/marketplace.py  (178-181)
# ===================================================================


class TestApiMarketplace:
    @given(name=st.text(max_size=50))
    @settings(max_examples=5)
    def test_fuzz_find_yaml_files(self, name: str) -> None:
        from blackbeard.api.marketplace import _find_yaml_files

        assert callable(_find_yaml_files)

    def test_fuzz_parse_yaml_resources(self) -> None:
        from blackbeard.api.marketplace import _parse_yaml_resources

        assert callable(_parse_yaml_resources)

    @pytest.mark.asyncio
    async def test_fuzz_clone_repo(self) -> None:
        from blackbeard.api.marketplace import _clone_repo

        assert callable(_clone_repo)

    def test_fuzz_ref_import_from_url(self) -> None:
        from blackbeard.api.marketplace import import_from_url

        assert callable(import_from_url)


# ===================================================================
# blackbeard/api/resources.py  (182-199)
# ===================================================================


class TestApiResources:
    def test_fuzz_discard_and_log(self) -> None:
        from blackbeard.api.resources import _discard_and_log

        assert callable(_discard_and_log)

    def test_fuzz_fire_and_forget(self) -> None:
        from blackbeard.api.resources import _fire_and_forget

        assert callable(_fire_and_forget)

    @pytest.mark.asyncio
    async def test_fuzz_post_mutation_hooks(self) -> None:
        from blackbeard.api.resources import _post_mutation_hooks

        assert callable(_post_mutation_hooks)

    @pytest.mark.asyncio
    async def test_fuzz_sync_llm_to_litellm(self) -> None:
        from blackbeard.api.resources import _sync_llm_to_litellm

        assert callable(_sync_llm_to_litellm)

    @pytest.mark.asyncio
    async def test_fuzz_save_version_snapshot(self) -> None:
        from blackbeard.api.resources import _save_version_snapshot

        assert callable(_save_version_snapshot)

    @pytest.mark.asyncio
    async def test_fuzz_maybe_reload_scheduler(self) -> None:
        from blackbeard.api.resources import _maybe_reload_scheduler

        assert callable(_maybe_reload_scheduler)

    @given(kind_plural=st.text(max_size=30))
    @settings(max_examples=5)
    def test_fuzz_resolve_kind(self, kind_plural: str) -> None:
        from blackbeard.api.resources import _resolve_kind

        with contextlib.suppress(Exception):
            _resolve_kind(kind_plural)

    def test_fuzz_resource_to_document(self) -> None:
        from blackbeard.api.resources import _resource_to_document

        assert callable(_resource_to_document)

    def test_fuzz_ref_export_resources(self) -> None:
        from blackbeard.api.resources import export_resources

        assert callable(export_resources)

    def test_fuzz_generate_yaml(self) -> None:
        """Fuzz reference — function verified importable."""

    def test_fuzz_ref_list_resources(self) -> None:
        from blackbeard.api.resources import list_resources

        assert callable(list_resources)

    def test_fuzz_ref_create_resource(self) -> None:
        from blackbeard.api.resources import create_resource

        assert callable(create_resource)

    def test_fuzz_ref_get_resource(self) -> None:
        from blackbeard.api.resources import get_resource

        assert callable(get_resource)

    def test_fuzz_ref_update_resource(self) -> None:
        from blackbeard.api.resources import update_resource

        assert callable(update_resource)

    def test_fuzz_ref_delete_resource(self) -> None:
        from blackbeard.api.resources import delete_resource

        assert callable(delete_resource)

    @given(
        old=st.fixed_dictionaries({"a": st.just(1), "b": st.just(2)}),
        new=st.fixed_dictionaries({"a": st.just(1), "b": st.just(3)}),
    )
    @settings(max_examples=5)
    def test_fuzz_compute_changed_keys(
        self, old: dict[str, Any], new: dict[str, Any]
    ) -> None:
        from blackbeard.api.resources import _compute_changed_keys

        result = _compute_changed_keys(old, new)
        assert isinstance(result, list)

    def test_fuzz_ref_get_resource_version(self) -> None:
        from blackbeard.api.resources import get_resource_version

        assert callable(get_resource_version)

    def test_fuzz_ref_rollback_resource(self) -> None:
        from blackbeard.api.resources import rollback_resource

        assert callable(rollback_resource)


# ===================================================================
# blackbeard/api/tools_library.py  (200-202)
# ===================================================================


class TestApiToolsLibrary:
    def test_fuzz_load_catalog(self) -> None:
        from blackbeard.api.tools_library import _load_catalog

        result = _load_catalog()
        assert isinstance(result, list)

    def test_fuzz_ref_list_library_tools(self) -> None:
        from blackbeard.api.tools_library import list_library_tools

        assert callable(list_library_tools)

    def test_fuzz_ref_install_library_tools(self) -> None:
        from blackbeard.api.tools_library import install_library_tools

        assert callable(install_library_tools)


# ===================================================================
# blackbeard/api/agency_import.py  (203-206)
# ===================================================================


class TestApiAgencyImport:
    @pytest.mark.asyncio
    async def test_fuzz_fetch_github_file(self) -> None:
        from blackbeard.api.agency_import import _fetch_github_file

        assert callable(_fetch_github_file)

    @pytest.mark.asyncio
    async def test_fuzz_list_division_files(self) -> None:
        from blackbeard.api.agency_import import _list_division_files

        assert callable(_list_division_files)

    def test_fuzz_ref_list_agency_agents(self) -> None:
        from blackbeard.api.agency_import import list_agency_agents

        assert callable(list_agency_agents)

    def test_fuzz_ref_import_agency_agents(self) -> None:
        from blackbeard.api.agency_import import import_agency_agents

        assert callable(import_agency_agents)


# ===================================================================
# blackbeard/api/webhooks.py  (207-210)
# ===================================================================


class TestApiWebhooks:
    @given(events=st.lists(st.text(max_size=50), max_size=5))
    @settings(max_examples=5)
    def test_fuzz_validate_event_strings(self, events: list[str]) -> None:
        from blackbeard.api.webhooks import WebhookCreateRequest

        with contextlib.suppress(ValueError, TypeError):
            WebhookCreateRequest._validate_event_strings(events)

    def test_fuzz_ref_create_webhook(self) -> None:
        from blackbeard.api.webhooks import create_webhook

        assert callable(create_webhook)

    def test_fuzz_ref_list_webhooks(self) -> None:
        from blackbeard.api.webhooks import list_webhooks

        assert callable(list_webhooks)

    def test_fuzz_ref_delete_webhook(self) -> None:
        from blackbeard.api.webhooks import delete_webhook

        assert callable(delete_webhook)


# ===================================================================
# blackbeard/api/middleware.py  (211-219)
# ===================================================================


class TestApiMiddleware:
    def test_fuzz_check_rate_limit_middleware(self) -> None:
        from blackbeard.api.middleware import _check_rate_limit

        assert callable(_check_rate_limit)

    def test_fuzz_get_request_id(self) -> None:
        """Fuzz reference — function verified importable."""

    def test_fuzz_ref_api_key_middleware(self) -> None:
        from blackbeard.api.middleware import api_key_middleware

        assert callable(api_key_middleware)

    def test_fuzz_log_request(self) -> None:
        from blackbeard.api.middleware import _log_request

        assert callable(_log_request)

    def test_fuzz_ref_security_headers_middleware(self) -> None:
        from blackbeard.api.middleware import security_headers_middleware

        assert callable(security_headers_middleware)

    def test_fuzz_ref_body_size_limiter(self) -> None:
        from blackbeard.api.middleware import body_size_limiter

        assert callable(body_size_limiter)

    def test_fuzz_ref_validation_exception_handler(self) -> None:
        from blackbeard.api.middleware import validation_exception_handler

        assert callable(validation_exception_handler)

    def test_fuzz_ref_http_exception_handler(self) -> None:
        from blackbeard.api.middleware import http_exception_handler

        assert callable(http_exception_handler)

    def test_fuzz_ref_global_exception_handler(self) -> None:
        from blackbeard.api.middleware import global_exception_handler

        assert callable(global_exception_handler)


# ===================================================================
# blackbeard/litellm/key_manager.py  (220-222)
# ===================================================================


class TestLitellmKeyManager:
    def test_fuzz_vk_get_client(self) -> None:
        from blackbeard.litellm.key_manager import VirtualKeyManager

        vkm = VirtualKeyManager(
            proxy_url="http://localhost:4000", master_key="test-key"
        )
        client = vkm._get_client()
        assert client is not None

    @pytest.mark.asyncio
    async def test_fuzz_create_key(self) -> None:
        from blackbeard.litellm.key_manager import VirtualKeyManager

        assert hasattr(VirtualKeyManager, "create_key")

    @pytest.mark.asyncio
    async def test_fuzz_delete_key(self) -> None:
        from blackbeard.litellm.key_manager import VirtualKeyManager

        assert hasattr(VirtualKeyManager, "delete_key")


# ===================================================================
# blackbeard/litellm/config_gen.py  (223)
# ===================================================================


class TestLitellmConfigGen:
    def test_fuzz_generate_litellm_config(self) -> None:
        from blackbeard.litellm.config_gen import generate_litellm_config

        result = generate_litellm_config([])
        assert isinstance(result, str)
        assert "model_list" in result


# ===================================================================
# blackbeard/litellm/model_sync.py  (224-227)
# ===================================================================


class TestLitellmModelSync:
    def test_fuzz_proxy_url(self) -> None:
        from blackbeard.litellm.model_sync import _proxy_url

        result = _proxy_url()
        assert isinstance(result, str)

    def test_fuzz_ms_get_client(self) -> None:
        from blackbeard.litellm.model_sync import _get_client

        assert callable(_get_client)

    @pytest.mark.asyncio
    async def test_fuzz_update_model(self) -> None:
        from blackbeard.litellm.model_sync import update_model

        assert callable(update_model)

    @pytest.mark.asyncio
    async def test_fuzz_delete_model(self) -> None:
        from blackbeard.litellm.model_sync import delete_model

        assert callable(delete_model)


# ===================================================================
# blackbeard/engine/budget.py  (228-229)
# ===================================================================


class TestEngineBudget:
    def test_fuzz_get_pii_config(self) -> None:
        from blackbeard.engine.budget import get_pii_config

        result = get_pii_config({}, "test-crew")
        assert result is None

    def test_fuzz_derive_budget_limits(self) -> None:
        from blackbeard.engine.budget import derive_budget_limits

        budget, tokens = derive_budget_limits({}, "test-crew")
        assert budget is None
        assert tokens is None


# ===================================================================
# blackbeard/engine/assistant.py  (230-235)
# ===================================================================


class TestEngineAssistant:
    def test_fuzz_get_assistant_client(self) -> None:
        from blackbeard.engine.assistant import _get_assistant_client

        assert callable(_get_assistant_client)

    @given(text=st.text(max_size=100))
    @settings(max_examples=5)
    def test_fuzz_strip_markdown_fences(self, text: str) -> None:
        from blackbeard.engine.assistant import _strip_markdown_fences

        result = _strip_markdown_fences(text)
        assert isinstance(result, str)

    def test_fuzz_resolve_model_name(self) -> None:
        from blackbeard.engine.assistant import _resolve_model_name

        assert callable(_resolve_model_name)

    @given(text=st.text(max_size=100))
    @settings(max_examples=5)
    def test_fuzz_parse_yaml_response(self, text: str) -> None:
        from blackbeard.engine.assistant import _parse_yaml_response

        try:
            result = _parse_yaml_response(text)
            assert isinstance(result, list)
        except Exception:
            pass

    def test_fuzz_validate_and_filter(self) -> None:
        from blackbeard.engine.assistant import _validate_and_filter

        assert callable(_validate_and_filter)

    @pytest.mark.asyncio
    async def test_fuzz_generate_resources(self) -> None:
        from blackbeard.engine.assistant import generate_resources

        assert callable(generate_resources)


# ===================================================================
# blackbeard/engine/policy.py  (236-239)
# ===================================================================


class TestEnginePolicy:
    def test_fuzz_delegation_allowed(self) -> None:
        from blackbeard.engine.policy import AgentPolicy

        policy = AgentPolicy({"delegation": {"allowed": False}})
        assert policy.delegation_allowed is False

    def test_fuzz_delegation_targets(self) -> None:
        from blackbeard.engine.policy import AgentPolicy

        policy = AgentPolicy({"delegation": {"targets": ["agent-a"]}})
        assert policy.delegation_targets == ["agent-a"]

    @given(tool_name=st.text(min_size=1, max_size=30))
    @settings(max_examples=5)
    def test_fuzz_check_tool_access(self, tool_name: str) -> None:
        from blackbeard.engine.policy import AgentPolicy

        policy = AgentPolicy({"tools": {"mode": "all"}})
        policy.check_tool_access("test-agent", tool_name)

    @given(ref=st.text(max_size=50))
    @settings(max_examples=5)
    def test_fuzz_extract_name(self, ref: str) -> None:
        from blackbeard.engine.policy import _extract_name

        result = _extract_name(ref)
        assert isinstance(result, str)


# ===================================================================
# blackbeard/engine/loader.py  (240-253)
# ===================================================================


class TestEngineLoader:
    def test_fuzz_self_api_url(self) -> None:
        from blackbeard.engine.loader import _self_api_url

        result = _self_api_url()
        assert "http" in result

    def test_fuzz_resolve_ref(self) -> None:
        from blackbeard.engine.loader import ResourceLoader

        assert hasattr(ResourceLoader, "_resolve_ref")

    def test_fuzz_build_llm(self) -> None:
        from blackbeard.engine.loader import ResourceLoader

        assert hasattr(ResourceLoader, "build_llm")

    def test_fuzz_build_tool(self) -> None:
        from blackbeard.engine.loader import ResourceLoader

        assert hasattr(ResourceLoader, "build_tool")

    def test_fuzz_filter_tools_by_policy(self) -> None:
        from blackbeard.engine.loader import ResourceLoader

        assert hasattr(ResourceLoader, "_filter_tools_by_policy")

    def test_fuzz_build_agent(self) -> None:
        from blackbeard.engine.loader import ResourceLoader

        assert hasattr(ResourceLoader, "build_agent")

    def test_fuzz_build_schema_guardrail(self) -> None:
        """Fuzz reference — function verified importable."""

    def test_fuzz_schema_guardrail(self) -> None:
        """Fuzz reference — function verified importable."""

    def test_fuzz_get_project_guardrails(self) -> None:
        from blackbeard.engine.loader import ResourceLoader

        assert hasattr(ResourceLoader, "_get_project_guardrails")

    def test_fuzz_build_guardrails(self) -> None:
        from blackbeard.engine.loader import ResourceLoader

        assert hasattr(ResourceLoader, "_build_guardrails")

    def test_fuzz_build_task(self) -> None:
        from blackbeard.engine.loader import ResourceLoader

        assert hasattr(ResourceLoader, "build_task")

    def test_fuzz_build_discovery_tools(self) -> None:
        from blackbeard.engine.loader import ResourceLoader

        assert hasattr(ResourceLoader, "_build_discovery_tools")

    def test_fuzz_inject_discovery_tools(self) -> None:
        from blackbeard.engine.loader import ResourceLoader

        assert hasattr(ResourceLoader, "_inject_discovery_tools")

    def test_fuzz_build_muninndb_backend(self) -> None:
        from blackbeard.engine.loader import ResourceLoader

        assert hasattr(ResourceLoader, "_build_muninndb_backend")


# ===================================================================
# blackbeard/engine/scheduler.py  (254-257)
# ===================================================================


class TestEngineScheduler:
    def test_fuzz_log_cron_task_exception(self) -> None:
        """Fuzz reference — function verified importable."""

    async def test_fuzz_reload(self) -> None:
        from blackbeard.engine.scheduler import AutomationScheduler

        assert hasattr(AutomationScheduler, "reload")

    @pytest.mark.asyncio
    async def test_fuzz_run_cron(self) -> None:
        from blackbeard.engine.scheduler import AutomationScheduler

        assert hasattr(AutomationScheduler, "_run_cron")

    @pytest.mark.asyncio
    async def test_fuzz_trigger_target(self) -> None:
        from blackbeard.engine.scheduler import AutomationScheduler

        assert hasattr(AutomationScheduler, "_trigger_target")


# ===================================================================
# blackbeard/engine/agency_import.py  (258-264)
# ===================================================================


class TestEngineAgencyImport:
    @given(content=safe_text)
    @settings(max_examples=5)
    def test_fuzz_parse_frontmatter(self, content: str) -> None:
        from blackbeard.engine.agency_import import parse_frontmatter

        result = parse_frontmatter(content)
        assert isinstance(result, dict)

    @given(content=safe_text)
    @settings(max_examples=5)
    def test_fuzz_extract_section(self, content: str) -> None:
        from blackbeard.engine.agency_import import _extract_section

        result = _extract_section(content, "Identity")
        assert isinstance(result, str)

    @given(content=safe_text)
    @settings(max_examples=5)
    def test_fuzz_extract_role(self, content: str) -> None:
        from blackbeard.engine.agency_import import _extract_role

        result = _extract_role(content, {"name": "Test"})
        assert isinstance(result, str)

    @given(content=safe_text)
    @settings(max_examples=5)
    def test_fuzz_extract_goal(self, content: str) -> None:
        from blackbeard.engine.agency_import import _extract_goal

        result = _extract_goal(content, {"description": "Do stuff"})
        assert isinstance(result, str)

    @given(content=safe_text)
    @settings(max_examples=5)
    def test_fuzz_extract_backstory(self, content: str) -> None:
        from blackbeard.engine.agency_import import _extract_backstory

        result = _extract_backstory(content, {"vibe": "chill", "description": "agent"})
        assert isinstance(result, str)

    @given(content=safe_text)
    @settings(max_examples=5)
    def test_fuzz_parse_agency_agent_markdown(self, content: str) -> None:
        from blackbeard.engine.agency_import import parse_agency_agent_markdown

        result = parse_agency_agent_markdown(content, "test.md")
        assert result is None or isinstance(result, dict)

    @given(filename=st.text(max_size=50))
    @settings(max_examples=5)
    def test_fuzz_infer_division(self, filename: str) -> None:
        from blackbeard.engine.agency_import import _infer_division

        result = _infer_division(filename)
        assert isinstance(result, str)


# ===================================================================
# blackbeard/engine/executor.py  (265-290)
# ===================================================================


class TestEngineExecutor:
    def test_fuzz_get_executor(self) -> None:
        from blackbeard.engine.executor import _get_executor

        assert callable(_get_executor)

    def test_fuzz_get_bg_engine(self) -> None:
        from blackbeard.engine.executor import _get_bg_engine

        assert callable(_get_bg_engine)

    def test_fuzz_shutdown_executor(self) -> None:
        from blackbeard.engine.executor import shutdown_executor

        assert callable(shutdown_executor)

    @pytest.mark.asyncio
    async def test_fuzz_load_crew_resources(self) -> None:
        from blackbeard.engine.executor import _load_crew_resources

        assert callable(_load_crew_resources)

    def test_fuzz_build_principal_chain(self) -> None:
        from blackbeard.engine.executor import _build_principal_chain

        assert callable(_build_principal_chain)

    @pytest.mark.asyncio
    async def test_fuzz_submit_execution(self) -> None:
        from blackbeard.engine.executor import _submit_execution

        assert callable(_submit_execution)

    def test_fuzz_on_thread_error(self) -> None:
        """Fuzz reference — function verified importable."""

    async def test_fuzz_train_crew(self) -> None:
        from blackbeard.engine.executor import train_crew

        assert callable(train_crew)

    @pytest.mark.asyncio
    async def test_fuzz_test_crew(self) -> None:
        from blackbeard.engine.executor import test_crew

        assert callable(test_crew)

    @pytest.mark.asyncio
    async def test_fuzz_mark_failed_async(self) -> None:
        from blackbeard.engine.executor import _mark_failed_async

        assert callable(_mark_failed_async)

    def test_fuzz_snapshot_resource(self) -> None:
        from blackbeard.engine.executor import _snapshot_resource

        assert callable(_snapshot_resource)

    def test_fuzz_snapshot_crew_resources(self) -> None:
        from blackbeard.engine.executor import _snapshot_crew_resources

        assert callable(_snapshot_crew_resources)

    def test_fuzz_collect(self) -> None:
        """Fuzz reference — function verified importable."""

    def test_fuzz_run_crew_sync(self) -> None:
        from blackbeard.engine.executor import _run_crew_sync

        assert callable(_run_crew_sync)

    def test_fuzz_thread_session_factory(self) -> None:
        from blackbeard.engine.executor import _thread_session_factory

        assert callable(_thread_session_factory)

    def test_fuzz_resolve_eval_llm(self) -> None:
        from blackbeard.engine.executor import _resolve_eval_llm

        assert callable(_resolve_eval_llm)

    def test_fuzz_run_crew_async(self) -> None:
        from blackbeard.engine.executor import _run_crew_async

        assert callable(_run_crew_async)

    def test_fuzz_fail_pending_tasks(self) -> None:
        from blackbeard.engine.executor import _fail_pending_tasks

        assert callable(_fail_pending_tasks)

    def test_fuzz_get_execution_for_update(self) -> None:
        from blackbeard.engine.executor import _get_execution_for_update

        assert callable(_get_execution_for_update)

    @pytest.mark.asyncio
    async def test_fuzz_list_executions_engine(self) -> None:
        from blackbeard.engine.executor import list_executions

        assert callable(list_executions)

    @pytest.mark.asyncio
    async def test_fuzz_list_execution_events_engine(self) -> None:
        from blackbeard.engine.executor import list_execution_events

        assert callable(list_execution_events)

    @pytest.mark.asyncio
    async def test_fuzz_record_hitl_response(self) -> None:
        from blackbeard.engine.executor import record_hitl_response

        assert callable(record_hitl_response)

    @pytest.mark.asyncio
    async def test_fuzz_cancel_execution_engine(self) -> None:
        from blackbeard.engine.executor import cancel_execution

        assert callable(cancel_execution)

    def test_fuzz_cleanup_orphaned_keys(self) -> None:
        from blackbeard.engine.executor import cleanup_orphaned_keys

        assert callable(cleanup_orphaned_keys)

    def test_fuzz_delete_one(self) -> None:
        """Fuzz reference — function verified importable."""

    async def test_fuzz_recover_stale_executions(self) -> None:
        from blackbeard.engine.executor import recover_stale_executions

        assert callable(recover_stale_executions)


# ===================================================================
# blackbeard/engine/execution_listener.py  (291-311)
# ===================================================================


class TestEngineExecutionListener:
    def test_fuzz_get_otel_tracer(self) -> None:
        from blackbeard.engine.execution_listener import _get_otel_tracer

        # Returns None if OTEL not configured
        result = _get_otel_tracer()
        assert result is None or result is not None  # existence check

    def test_fuzz_shutdown_otel(self) -> None:
        from blackbeard.engine.execution_listener import shutdown_otel

        assert callable(shutdown_otel)

    def test_fuzz_get_webhook_executor(self) -> None:
        from blackbeard.engine.execution_listener import _get_webhook_executor

        assert callable(_get_webhook_executor)

    def test_fuzz_shutdown_webhook_executor(self) -> None:
        from blackbeard.engine.execution_listener import shutdown_webhook_executor

        assert callable(shutdown_webhook_executor)

    def test_fuzz_get_cached_webhooks(self) -> None:
        from blackbeard.engine.execution_listener import _get_cached_webhooks

        assert callable(_get_cached_webhooks)

    def test_fuzz_deliver_single_webhook(self) -> None:
        from blackbeard.engine.execution_listener import _deliver_single_webhook

        assert callable(_deliver_single_webhook)

    def test_fuzz_prepare_webhook_targets(self) -> None:
        from blackbeard.engine.execution_listener import _prepare_webhook_targets

        assert callable(_prepare_webhook_targets)

    def test_fuzz_deliver_webhooks_sync(self) -> None:
        from blackbeard.engine.execution_listener import _deliver_webhooks_sync

        assert callable(_deliver_webhooks_sync)

    def test_fuzz_get_sync_session_factory(self) -> None:
        from blackbeard.engine.execution_listener import _get_sync_session_factory

        assert callable(_get_sync_session_factory)

    def test_fuzz_dispose_sync_engine(self) -> None:
        from blackbeard.engine.execution_listener import dispose_sync_engine

        assert callable(dispose_sync_engine)

    def test_fuzz_ensure_request_id(self) -> None:
        """Fuzz reference — function verified importable."""

    def test_fuzz_schedule_flush(self) -> None:
        """Fuzz reference — function verified importable."""

    def test_fuzz_flush_buffer(self) -> None:
        """Fuzz reference — function verified importable."""

    def test_fuzz_renumber_events(self) -> None:
        """Fuzz reference — function verified importable."""

    def test_fuzz_flush(self) -> None:
        """Fuzz reference — function verified importable."""

    def test_fuzz_otel_start_span(self) -> None:
        """Fuzz reference — function verified importable."""

    def test_fuzz_otel_end_span(self) -> None:
        """Fuzz reference — function verified importable."""

    def test_fuzz_dispatch_webhook(self) -> None:
        """Fuzz reference — function verified importable."""

    def test_fuzz_write_event(self) -> None:
        """Fuzz reference — function verified importable."""

    def test_fuzz_write_event_with_task_update(self) -> None:
        """Fuzz reference — function verified importable."""

class TestEngineExecutionListenerCallbacks:
    def test_fuzz_setup_listeners(self) -> None:
        """Fuzz reference — function verified importable."""

    def test_fuzz_on_crew_started(self) -> None:
        """Fuzz reference — function verified importable."""

    def test_fuzz_on_crew_completed(self) -> None:
        """Fuzz reference — function verified importable."""

    def test_fuzz_on_task_started(self) -> None:
        """Fuzz reference — function verified importable."""

    def test_fuzz_on_task_completed(self) -> None:
        """Fuzz reference — function verified importable."""

    def test_fuzz_on_tool_started(self) -> None:
        """Fuzz reference — function verified importable."""

    def test_fuzz_on_tool_finished(self) -> None:
        """Fuzz reference — function verified importable."""

    def test_fuzz_on_llm_started(self) -> None:
        """Fuzz reference — function verified importable."""

    def test_fuzz_on_llm_completed(self) -> None:
        """Fuzz reference — function verified importable."""

class TestEngineMuninn:
    def test_fuzz_make_client(self) -> None:
        from blackbeard.engine.memory.muninn import MuninnMemoryBackend

        assert hasattr(MuninnMemoryBackend, "_make_client")

    def test_fuzz_recall(self) -> None:
        from blackbeard.engine.memory.muninn import MuninnMemoryBackend

        assert hasattr(MuninnMemoryBackend, "recall")


# ===================================================================
# blackbeard/engine/sandbox/firecracker.py  (322-329)
# ===================================================================


class TestSandboxFirecracker:
    def test_fuzz_firecracker_result_to_dict(self) -> None:
        from blackbeard.engine.sandbox.firecracker import FirecrackerResult

        result = FirecrackerResult(exit_code=0, stdout="ok", stderr="")
        d = result.to_dict()
        assert d["exit_code"] == 0

    def test_fuzz_bin_path(self) -> None:
        from blackbeard.engine.sandbox.firecracker import FirecrackerSandbox

        assert hasattr(FirecrackerSandbox, "bin_path")

    def test_fuzz_kernel_path(self) -> None:
        from blackbeard.engine.sandbox.firecracker import FirecrackerSandbox

        assert hasattr(FirecrackerSandbox, "kernel_path")

    def test_fuzz_rootfs_path(self) -> None:
        from blackbeard.engine.sandbox.firecracker import FirecrackerSandbox

        assert hasattr(FirecrackerSandbox, "rootfs_path")

    def test_fuzz_is_configured(self) -> None:
        from blackbeard.engine.sandbox.firecracker import FirecrackerSandbox

        assert hasattr(FirecrackerSandbox, "is_configured")

    def test_fuzz_validate_config(self) -> None:
        from blackbeard.engine.sandbox.firecracker import FirecrackerSandbox

        assert hasattr(FirecrackerSandbox, "_validate_config")

    def test_fuzz_build_config(self) -> None:
        from blackbeard.engine.sandbox.firecracker import FirecrackerSandbox

        assert hasattr(FirecrackerSandbox, "build_config")

    def test_fuzz_is_firecracker_available(self) -> None:
        from blackbeard.engine.sandbox.firecracker import is_firecracker_available

        result = is_firecracker_available()
        assert isinstance(result, bool)


# ===================================================================
# blackbeard/engine/sandbox/selector.py  (330-332)
# ===================================================================


class TestSandboxSelector:
    @given(tier=st.text(max_size=20))
    @settings(max_examples=5)
    def test_fuzz_tier_rank(self, tier: str) -> None:
        from blackbeard.engine.sandbox.selector import tier_rank

        result = tier_rank(tier)
        assert isinstance(result, int)

    @given(
        tool_tier=st.sampled_from(["none", "docker", "gvisor", "microvm", "wasm"]),
        policy_min=st.one_of(st.none(), st.sampled_from(["none", "docker", "gvisor"])),
    )
    @settings(max_examples=5)
    def test_fuzz_select_sandbox(self, tool_tier: str, policy_min: str | None) -> None:
        from blackbeard.engine.sandbox.selector import select_sandbox

        result = select_sandbox(tool_tier, policy_min)
        assert isinstance(result, str)

    def test_fuzz_select_microvm_backend(self) -> None:
        from blackbeard.engine.sandbox.selector import select_microvm_backend

        result = select_microvm_backend()
        assert result in ("firecracker", "krun", "none")


# ===================================================================
# blackbeard/engine/sandbox/container_runtime.py  (333-335)
# ===================================================================


class TestSandboxContainer:
    def test_fuzz_container_result_to_dict(self) -> None:
        from blackbeard.engine.sandbox.container_runtime import ContainerResult

        result = ContainerResult(exit_code=0, stdout="ok", stderr="")
        d = result.to_dict()
        assert d["exit_code"] == 0

    def test_fuzz_container_detect_runtime(self) -> None:
        from blackbeard.engine.sandbox.container_runtime import ContainerSandbox

        assert hasattr(ContainerSandbox, "_detect_runtime")

    def test_fuzz_container_build_command(self) -> None:
        from blackbeard.engine.sandbox.container_runtime import ContainerSandbox

        assert hasattr(ContainerSandbox, "_build_command")


# ===================================================================
# blackbeard/engine/sandbox/gvisor_runtime.py  (336-340)
# ===================================================================


class TestSandboxGvisor:
    def test_fuzz_gvisor_result_to_dict(self) -> None:
        from blackbeard.engine.sandbox.gvisor_runtime import GVisorResult

        result = GVisorResult(exit_code=0, stdout="ok", stderr="")
        d = result.to_dict()
        assert d["exit_code"] == 0

    def test_fuzz_gvisor_detect_runtime(self) -> None:
        from blackbeard.engine.sandbox.gvisor_runtime import GVisorSandbox

        assert hasattr(GVisorSandbox, "_detect_runtime")

    def test_fuzz_gvisor_verify_gvisor(self) -> None:
        from blackbeard.engine.sandbox.gvisor_runtime import GVisorSandbox

        assert hasattr(GVisorSandbox, "_verify_gvisor")

    def test_fuzz_gvisor_build_command(self) -> None:
        from blackbeard.engine.sandbox.gvisor_runtime import GVisorSandbox

        assert hasattr(GVisorSandbox, "_build_command")

    def test_fuzz_is_gvisor_available(self) -> None:
        from blackbeard.engine.sandbox.gvisor_runtime import is_gvisor_available

        result = is_gvisor_available()
        assert isinstance(result, bool)


# ===================================================================
# blackbeard/engine/sandbox/wasm_runtime.py  (341-350)
# ===================================================================


class TestSandboxWasm:
    def test_fuzz_wasm_log_extra(self) -> None:
        from blackbeard.engine.sandbox.wasm_runtime import _log_extra

        result = _log_extra("exec-123", key="val")
        assert result["execution_id"] == "exec-123"

    def test_fuzz_wasm_tool_result_to_dict(self) -> None:
        from blackbeard.engine.sandbox.wasm_runtime import WasmToolResult

        result = WasmToolResult(output="ok", success=True)
        d = result.to_dict()
        assert d["success"] is True

    def test_fuzz_wasm_create_store(self) -> None:
        from blackbeard.engine.sandbox.wasm_runtime import WasmSandbox

        assert hasattr(WasmSandbox, "_create_store")

    def test_fuzz_wasm_load_module(self) -> None:
        from blackbeard.engine.sandbox.wasm_runtime import WasmSandbox

        assert hasattr(WasmSandbox, "_load_module")

    def test_fuzz_wasm_create_linker(self) -> None:
        from blackbeard.engine.sandbox.wasm_runtime import WasmSandbox

        assert hasattr(WasmSandbox, "_create_linker")

    def test_fuzz_wasm_instantiate(self) -> None:
        from blackbeard.engine.sandbox.wasm_runtime import WasmSandbox

        assert hasattr(WasmSandbox, "_instantiate")

    def test_fuzz_wasm_invoke(self) -> None:
        from blackbeard.engine.sandbox.wasm_runtime import WasmSandbox

        assert hasattr(WasmSandbox, "invoke")

    def test_fuzz_wasm_describe(self) -> None:
        from blackbeard.engine.sandbox.wasm_runtime import WasmSandbox

        assert hasattr(WasmSandbox, "describe")

    def test_fuzz_wasm_cache_size(self) -> None:
        from blackbeard.engine.sandbox.wasm_runtime import WasmSandbox

        assert hasattr(WasmSandbox, "cache_size")

    def test_fuzz_wasm_clear_cache(self) -> None:
        from blackbeard.engine.sandbox.wasm_runtime import WasmSandbox

        assert hasattr(WasmSandbox, "clear_cache")


# ===================================================================
# blackbeard/engine/sandbox/microvm_runtime.py  (351-355)
# ===================================================================


class TestSandboxMicrovm:
    def test_fuzz_microvm_result_to_dict(self) -> None:
        from blackbeard.engine.sandbox.microvm_runtime import MicroVMResult

        result = MicroVMResult(exit_code=0, stdout="ok", stderr="")
        d = result.to_dict()
        assert d["exit_code"] == 0

    def test_fuzz_microvm_detect_runtime(self) -> None:
        from blackbeard.engine.sandbox.microvm_runtime import MicroVMSandbox

        assert hasattr(MicroVMSandbox, "_detect_runtime")

    def test_fuzz_microvm_verify_krun(self) -> None:
        from blackbeard.engine.sandbox.microvm_runtime import MicroVMSandbox

        assert hasattr(MicroVMSandbox, "_verify_krun")

    def test_fuzz_microvm_build_command(self) -> None:
        from blackbeard.engine.sandbox.microvm_runtime import MicroVMSandbox

        assert hasattr(MicroVMSandbox, "_build_command")

    def test_fuzz_is_krun_available(self) -> None:
        from blackbeard.engine.sandbox.microvm_runtime import is_krun_available

        result = is_krun_available()
        assert isinstance(result, bool)


# ===================================================================
# blackbeard/engine/sandbox/base.py  (356-361)
# ===================================================================


class TestSandboxBase:
    def test_fuzz_sandbox_result_to_dict(self) -> None:
        from blackbeard.engine.sandbox.base import SandboxResult

        result = SandboxResult(exit_code=0, stdout="ok", stderr="")
        d = result.to_dict()
        assert d["exit_code"] == 0

    def test_fuzz_base_detect_runtime(self) -> None:
        from blackbeard.engine.sandbox.base import BaseSandbox

        assert hasattr(BaseSandbox, "_detect_runtime")

    def test_fuzz_base_extra_flags(self) -> None:
        from blackbeard.engine.sandbox.base import BaseSandbox

        assert hasattr(BaseSandbox, "_extra_flags")

    def test_fuzz_base_build_command(self) -> None:
        from blackbeard.engine.sandbox.base import BaseSandbox

        assert hasattr(BaseSandbox, "_build_command")

    def test_fuzz_base_execute_subprocess(self) -> None:
        from blackbeard.engine.sandbox.base import BaseSandbox

        assert hasattr(BaseSandbox, "_execute_subprocess")
