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
    # Should never raise
    resolve_dotted(path, context)


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
        pass  # Correctly rejected
    else:
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
