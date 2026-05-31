"""Fuzz / property-based tests for security-critical functions.

Uses Hypothesis to throw random, malicious, and edge-case inputs at
authentication, authorization, and input validation primitives.
Every test asserts that the function never crashes and always returns
the expected type (or raises the expected exception).
"""

from __future__ import annotations

import contextlib
import datetime

import pytest
import yaml
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from blackbeard.auth.jwt import decode_token
from blackbeard.auth.passwords import hash_password, verify_password
from blackbeard.engine.flow_runner import evaluate_condition, resolve_dotted
from blackbeard.models.resource_schemas import ResourceCreate
from blackbeard.resources.refs import RefParseError, parse_ref
from blackbeard.resources.validator import check_url_ssrf

# ---------------------------------------------------------------------------
# 1. SSRF check fuzzing
# ---------------------------------------------------------------------------


@given(url=st.text(min_size=0, max_size=2000))
@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_fuzz_check_url_ssrf(url):
    """check_url_ssrf must never crash and must always return str | None."""
    result = check_url_ssrf(url)
    assert result is None or isinstance(result, str), (
        f"check_url_ssrf returned unexpected type {type(result)} for url={url!r}"
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",
        "http://127.0.0.1/admin",
        "http://0.0.0.0/",
        "http://[::1]/",
        "http://localhost/",
        "http://10.0.0.1/internal",
        "http://192.168.1.1/",
    ],
)
def test_check_url_ssrf_blocks_internal_urls(url):
    """Known internal/metadata URLs must be blocked (return error string)."""
    result = check_url_ssrf(url)
    assert result is not None, f"SSRF check should block {url!r} but returned None"
    assert isinstance(result, str)


@given(
    url=st.from_regex(
        r"https?://[a-z0-9._-]{1,50}(:[0-9]{1,5})?(/[a-z0-9._/-]{0,100})?",
        fullmatch=True,
    )
)
@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_fuzz_check_url_ssrf_http_shaped(url):
    """HTTP-shaped URLs must not crash and must return str | None."""
    result = check_url_ssrf(url)
    assert result is None or isinstance(result, str)


# ---------------------------------------------------------------------------
# 2. Expression evaluator fuzzing
# ---------------------------------------------------------------------------


@given(expr=st.text(min_size=0, max_size=500))
@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_fuzz_evaluate_condition(expr):
    """evaluate_condition must never crash and must always return bool.

    It uses only operator comparisons and dict lookups -- no dynamic
    code execution.
    """
    context = {"score": 0.5, "status": "completed", "outputs": {"result": "ok"}}
    result = evaluate_condition(expr, context)
    assert isinstance(result, bool), f"evaluate_condition returned {type(result)} for expr={expr!r}"


@given(path=st.text(min_size=0, max_size=200))
@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_fuzz_resolve_dotted(path):
    """resolve_dotted must never crash; returns Any (including None)."""
    context = {"a": {"b": {"c": 42}}, "x": [1, 2, 3]}
    result = resolve_dotted(path, context)
    if path == "a.b.c":
        assert result == 42, f"Known path 'a.b.c' should resolve to 42, got {result!r}"
    elif path == "a.b":
        assert result == {"c": 42}, f"Known path 'a.b' should resolve to dict, got {result!r}"
    elif path == "nonexistent":
        assert result is None, f"Missing path should resolve to None, got {result!r}"


# ---------------------------------------------------------------------------
# 3. Resource name validation fuzzing
# ---------------------------------------------------------------------------


@given(
    name=st.text(min_size=0, max_size=500),
)
@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_fuzz_resource_name_validation(name):
    """ResourceCreate.model_validate must either succeed or raise ValidationError.

    It must never raise an unhandled exception (TypeError, KeyError, etc.).
    """
    data = {
        "apiVersion": "blackbeard/v1",
        "kind": "Agent",
        "metadata": {"name": name},
        "spec": {"role": "x", "goal": "x", "backstory": "x"},
    }
    with contextlib.suppress(ValidationError):
        ResourceCreate.model_validate(data)


# ---------------------------------------------------------------------------
# 4. Ref parsing fuzzing
# ---------------------------------------------------------------------------

_PATH_TRAVERSAL_EXAMPLES = [
    "../../../etc/passwd",
    "..\\..\\windows\\system32",
    "ref:agents/../../etc/passwd",
    "ref:agents/name\x00injected",
    "ref:agents/../../../etc/shadow",
]


@given(value=st.text(min_size=0, max_size=500))
@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_fuzz_parse_ref(value):
    """parse_ref must return None or RefInfo, or raise RefParseError.

    It must never raise an unhandled exception.
    """
    try:
        result = parse_ref(value, field="test")
    except RefParseError:
        pass  # Expected for malformed refs
    else:
        if result is not None:
            # Valid ref -- verify fields are sane
            assert hasattr(result, "kind")
            assert hasattr(result, "name")
            assert hasattr(result, "raw")
            assert isinstance(result.name, str)
            assert ".." not in result.name, f"Path traversal in parsed ref name: {result.name!r}"


@pytest.mark.parametrize("value", _PATH_TRAVERSAL_EXAMPLES)
def test_parse_ref_path_traversal(value):
    """Path traversal attempts must never produce a valid RefInfo."""
    try:
        result = parse_ref(value, field="test")
    except RefParseError:
        return  # Correctly rejected
    # If parse_ref didn't raise, it must have returned None or a safe ref
    if result is not None:
        assert ".." not in result.name, (
            f"Path traversal succeeded: {value!r} -> {result.name!r}"
        )


# ---------------------------------------------------------------------------
# 5. YAML multi-document parsing fuzzing
# ---------------------------------------------------------------------------

_SAFE_TYPES = (str, int, float, bool, type(None), list, dict, datetime.date, datetime.datetime)


def _check_safe_types(obj):
    """Recursively verify that a parsed YAML value contains only safe types."""
    assert isinstance(obj, _SAFE_TYPES), f"Unsafe type loaded from YAML: {type(obj).__name__}"
    if isinstance(obj, dict):
        for k, v in obj.items():
            _check_safe_types(k)
            _check_safe_types(v)
    elif isinstance(obj, list):
        for item in obj:
            _check_safe_types(item)


@given(data=st.binary(min_size=0, max_size=2000))
@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_fuzz_yaml_safe_load_all(data):
    """yaml.safe_load_all must not crash or load dangerous objects.

    Only safe types (str, int, float, bool, None, list, dict, datetime)
    should be produced.
    """
    try:
        text = data.decode("utf-8", errors="replace")
        for doc in yaml.safe_load_all(text):
            if doc is not None:
                _check_safe_types(doc)
    except yaml.YAMLError:
        pass  # Expected for malformed YAML


# ---------------------------------------------------------------------------
# 6. Password validation fuzzing
# ---------------------------------------------------------------------------


@given(plain=st.text(min_size=1, max_size=200))
@settings(
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_fuzz_password_roundtrip(plain):
    """hash_password + verify_password must always round-trip correctly.

    For any non-empty plaintext string:
    - hash_password must not crash
    - verify_password(plain, hash) must return True
    """
    hashed = hash_password(plain)
    assert isinstance(hashed, str), f"hash_password returned {type(hashed)}"
    assert len(hashed) > 0, "hash_password returned empty string"
    assert verify_password(plain, hashed), f"verify_password failed round-trip for plain={plain!r}"


@given(plain=st.text(min_size=0, max_size=500))
@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_fuzz_hash_password_no_crash(plain):
    """hash_password must never crash, even with empty or huge strings."""
    hashed = hash_password(plain)
    assert isinstance(hashed, str)


# ---------------------------------------------------------------------------
# 7. JWT token fuzzing
# ---------------------------------------------------------------------------


@given(token=st.text(min_size=0, max_size=2000))
@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_fuzz_decode_token(token):
    """decode_token must always raise an exception for random input.

    Valid tokens require a specific secret, so random strings should
    always raise jwt.InvalidTokenError (or a subclass). The function
    must never crash with an unhandled exception.
    """
    import jwt as pyjwt

    try:
        result = decode_token(token)
        # If it somehow decoded, it must be a dict
        assert isinstance(result, dict)
    except pyjwt.InvalidTokenError:
        pass  # Expected for random/invalid tokens
    except pyjwt.PyJWTError:
        pass  # Any PyJWT error is acceptable


@given(
    token=st.from_regex(
        r"[A-Za-z0-9_-]{10,50}\.[A-Za-z0-9_-]{10,100}\.[A-Za-z0-9_-]{10,50}",
        fullmatch=True,
    )
)
@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_fuzz_decode_token_jwt_shaped(token):
    """JWT-shaped tokens (3 base64url segments) must be handled safely."""
    import jwt as pyjwt

    try:
        result = decode_token(token)
        assert isinstance(result, dict)
    except pyjwt.InvalidTokenError:
        pass
    except pyjwt.PyJWTError:
        pass


# ---------------------------------------------------------------------------
# 8. WebSocket auth validation fuzzing
# ---------------------------------------------------------------------------


@given(
    token=st.text(min_size=0, max_size=2000),
    api_key=st.text(min_size=0, max_size=500),
)
@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_fuzz_validate_ws_auth(token, api_key):
    """validate_ws_auth must never crash and must always return bool.

    Random tokens will fail JWT validation, random API keys will fail
    hmac comparison — but nothing should raise an unhandled exception.
    """
    from blackbeard.api.collaboration import validate_ws_auth

    result = validate_ws_auth(token, api_key)
    assert isinstance(result, bool), (
        f"validate_ws_auth returned {type(result)} for token={token!r}, api_key={api_key!r}"
    )


@given(
    token=st.from_regex(
        r"[A-Za-z0-9_-]{10,50}\.[A-Za-z0-9_-]{10,100}\.[A-Za-z0-9_-]{10,50}",
        fullmatch=True,
    ),
    api_key=st.text(min_size=0, max_size=200),
)
@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_fuzz_validate_ws_auth_jwt_shaped(token, api_key):
    """JWT-shaped tokens in WS auth must not crash."""
    from blackbeard.api.collaboration import validate_ws_auth

    result = validate_ws_auth(token, api_key)
    assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# 9. Assistant YAML response parser fuzzing
# ---------------------------------------------------------------------------


@given(raw=st.text(min_size=0, max_size=5000))
@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_fuzz_strip_markdown_fences(raw):
    """_strip_markdown_fences must never crash and must always return str."""
    from blackbeard.engine.assistant import _strip_markdown_fences

    result = _strip_markdown_fences(raw)
    assert isinstance(result, str), f"returned {type(result)}"
    assert len(result) <= len(raw) + 10


@given(raw=st.text(min_size=0, max_size=5000))
@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_fuzz_parse_yaml_response(raw):
    """_parse_yaml_response must raise AssistantError or return list[dict].

    Must never raise an unhandled exception (TypeError, KeyError, etc.).
    """
    from blackbeard.engine.assistant import AssistantError, _parse_yaml_response

    try:
        result = _parse_yaml_response(raw)
        assert isinstance(result, list)
        for doc in result:
            assert isinstance(doc, dict)
            assert "kind" in doc
    except AssistantError:
        pass


# ---------------------------------------------------------------------------
# 10. Depth checker fuzzing (used by WebSocket + execution schemas)
# ---------------------------------------------------------------------------

_nested_json = st.recursive(
    st.one_of(st.none(), st.booleans(), st.integers(min_value=-1000, max_value=1000), st.text(max_size=20)),
    lambda children: st.one_of(
        st.lists(children, max_size=5),
        st.dictionaries(st.text(max_size=10), children, max_size=5),
    ),
    max_leaves=30,
)


@given(obj=_nested_json, limit=st.integers(min_value=0, max_value=50))
@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_fuzz_exceeds_depth(obj, limit):
    """exceeds_depth must never crash and must always return bool."""
    from blackbeard.models.execution_schemas import exceeds_depth

    result = exceeds_depth(obj, limit)
    assert isinstance(result, bool)
    if limit == 0 and isinstance(obj, (dict, list)) and obj:
        assert result is True
    # Scalars (not dict/list) with limit > 0 never exceed depth
    if not isinstance(obj, (dict, list)) and limit > 0:
        assert result is False


# ---------------------------------------------------------------------------
# 11. Assistant resource validation fuzzing
# ---------------------------------------------------------------------------

_fuzz_resource_doc = st.fixed_dictionaries(
    {"kind": st.text(min_size=0, max_size=50)},
    optional={
        "apiVersion": st.text(max_size=30),
        "metadata": st.dictionaries(st.text(max_size=20), st.text(max_size=50), max_size=5),
        "spec": st.one_of(
            st.dictionaries(st.text(max_size=30), st.text(max_size=200), max_size=10),
            st.none(),
            st.text(max_size=50),
            st.integers(),
        ),
    },
)


@given(docs=st.lists(_fuzz_resource_doc, min_size=0, max_size=10))
@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_fuzz_validate_and_filter(docs):
    """_validate_and_filter must never crash and must always return list of valid docs."""
    from blackbeard.engine.assistant import _validate_and_filter

    result = _validate_and_filter(docs)
    assert isinstance(result, list)
    # Every returned doc must have an allowed kind
    for doc in result:
        assert isinstance(doc, dict)
        assert doc.get("kind") in {"Agent", "Task", "Crew"}
    # Result must be a subset of input — no docs invented
    assert len(result) <= len(docs)
    # Docs with non-allowed kinds must be filtered out
    non_allowed = [d for d in docs if d.get("kind") not in {"Agent", "Task", "Crew"}]
    for bad_doc in non_allowed:
        assert bad_doc not in result
    for doc in result:
        assert isinstance(doc, dict)
        assert doc.get("kind") in {"Agent", "Task", "Crew"}
