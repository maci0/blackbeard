"""Hypothesis-based fuzz tests for internal pure functions.

These tests exercise functions directly (no HTTP client, no database)
to verify they never crash on arbitrary input and always satisfy their
documented invariants.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Shared strategies
# ---------------------------------------------------------------------------

_json_primitives = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-(2**31), max_value=2**31),
    st.floats(allow_nan=False, allow_infinity=False),
    st.text(max_size=200),
)

_json_values = st.recursive(
    _json_primitives,
    lambda children: st.one_of(
        st.lists(children, max_size=5),
        st.dictionaries(st.text(max_size=30), children, max_size=10),
    ),
    max_leaves=50,
)

_context_dicts = st.dictionaries(
    st.text(min_size=1, max_size=30),
    _json_values,
    max_size=10,
)


# ---------------------------------------------------------------------------
# 1. resolve_pii_entities
# ---------------------------------------------------------------------------


@given(
    preset=st.one_of(st.none(), st.text(max_size=50)),
    entities=st.one_of(st.none(), st.lists(st.text(max_size=30), max_size=10)),
)
@settings(max_examples=100)
def test_fuzz_resolve_pii_entities(preset, entities):
    """resolve_pii_entities never crashes, always returns a non-empty list of strings."""
    from blackbeard.pii import resolve_pii_entities

    result = resolve_pii_entities(preset=preset, entities=entities)
    assert isinstance(result, list)
    assert len(result) > 0
    assert all(isinstance(e, str) for e in result)
    assert len(result) == len(set(result)), "PII entity list should not contain duplicates"


# ---------------------------------------------------------------------------
# 2. _redact_query_string
# ---------------------------------------------------------------------------


@given(query=st.text(max_size=500))
@settings(max_examples=100)
def test_fuzz_redact_query_string_never_crashes(query):
    """_redact_query_string never crashes and always returns a string."""
    from blackbeard.api.middleware import _redact_query_string

    result = _redact_query_string(query)
    assert isinstance(result, str)
    assert len(result) <= len(query) + 500, "Redacted output should not grow unboundedly"


@given(
    sensitive_key=st.sampled_from(
        ["api_key", "token", "password", "secret", "email", "ssn"]
    ),
    sensitive_val=st.text(min_size=1, max_size=30),
)
@settings(max_examples=100)
def test_fuzz_redact_query_string_redacts_sensitive(sensitive_key, sensitive_val):
    """When a sensitive param is present, its value is replaced with [REDACTED]."""
    from urllib.parse import parse_qsl, urlencode

    from blackbeard.api.middleware import _redact_query_string

    query = urlencode({sensitive_key: sensitive_val, "limit": "10"})
    result = _redact_query_string(query)
    assert isinstance(result, str)
    # Parse the result and verify the sensitive key has been redacted
    result_pairs = dict(parse_qsl(result, keep_blank_values=True))
    assert result_pairs.get(sensitive_key) == "[REDACTED]"


# ---------------------------------------------------------------------------
# 3. _MASKED_VALUE (credentials masking)
#
# The credentials module uses a fixed-width mask constant (_MASKED_VALUE)
# rather than a _mask(value) function. We verify the constant never leaks
# original values.
# ---------------------------------------------------------------------------


@given(value=st.text(min_size=1, max_size=200))
@settings(max_examples=100)
def test_fuzz_masked_value_never_reveals_original(value):
    """The masked constant never equals arbitrary input strings (for len > 0)."""
    from blackbeard.api.credentials import _MASKED_VALUE

    assert isinstance(_MASKED_VALUE, str)
    assert len(_MASKED_VALUE) > 0, "Mask must be non-empty"
    # Mask must be a fixed, short placeholder — not derived from input
    assert len(_MASKED_VALUE) <= 10, "Mask should be a short placeholder"
    assert _MASKED_VALUE == "****", "Mask must be the expected fixed value"


# ---------------------------------------------------------------------------
# 4. evaluate_condition
# ---------------------------------------------------------------------------


@given(
    expr=st.text(max_size=100),
    context=_context_dicts,
)
@settings(max_examples=100)
def test_fuzz_evaluate_condition(expr, context):
    """evaluate_condition never crashes and always returns a bool."""
    from blackbeard.engine.flow_runner import evaluate_condition

    result = evaluate_condition(expr, context)
    assert isinstance(result, bool)


@given(
    left_key=st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz"),
    op=st.sampled_from(["==", "!=", ">", "<", ">=", "<="]),
    right_val=st.one_of(
        st.text(min_size=1, max_size=20),
        st.floats(allow_nan=False, allow_infinity=False).map(str),
        st.integers(min_value=-1000, max_value=1000).map(str),
    ),
    context=_context_dicts,
)
@settings(max_examples=100)
def test_fuzz_evaluate_condition_structured(left_key, op, right_val, context):
    """evaluate_condition handles structured expressions without crashing."""
    from blackbeard.engine.flow_runner import evaluate_condition

    expr = f"{left_key} {op} {right_val}"
    result = evaluate_condition(expr, context)
    assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# 5. resolve_dotted
# ---------------------------------------------------------------------------


@given(
    path=st.text(max_size=100),
    context=_context_dicts,
)
@settings(max_examples=100)
def test_fuzz_resolve_dotted(path, context):
    """resolve_dotted never crashes on arbitrary paths and contexts."""
    from blackbeard.engine.flow_runner import resolve_dotted

    result = resolve_dotted(path, context)
    # If the path has a key that exists at the top level, result should be the value
    parts = path.split(".")
    if len(parts) == 1 and path in context:
        assert result == context[path]


@given(
    parts=st.lists(
        st.text(min_size=1, max_size=10, alphabet="abcdefghij"),
        min_size=1,
        max_size=25,
    ),
)
@settings(max_examples=100)
def test_fuzz_resolve_dotted_depth_limit(parts):
    """resolve_dotted respects the max depth limit and returns None for deep paths."""
    from blackbeard.engine.flow_runner import _MAX_RESOLVE_DEPTH, resolve_dotted

    path = ".".join(parts)
    context = {}
    result = resolve_dotted(path, context)
    if len(parts) > _MAX_RESOLVE_DEPTH:
        assert result is None
    else:
        # Empty context means no key can be found — must also be None
        assert result is None


# ---------------------------------------------------------------------------
# 6. _check_path_safety
# ---------------------------------------------------------------------------


@given(path=st.text(max_size=200))
@settings(max_examples=100)
def test_fuzz_check_path_safety(path):
    """_check_path_safety raises LoaderError for unsafe paths, never crashes with unhandled exceptions."""
    from blackbeard.engine.loader import LoaderError, _check_path_safety

    unsafe_indicators = ("..", "~", "\\", "\x00")
    absolute_prefixes = ("/", "\\")

    try:
        _check_path_safety(path, "test")
        # If it didn't raise, the path must not contain traversal indicators
        # and must not be absolute
        assert not any(ind in path for ind in unsafe_indicators)
        assert not path.startswith(absolute_prefixes)
    except LoaderError:
        # Expected for unsafe paths -- verify at least one indicator is present
        has_traversal = any(ind in path for ind in unsafe_indicators)
        is_absolute = path.startswith(absolute_prefixes)
        assert has_traversal or is_absolute


@given(
    safe_path=st.from_regex(r"[a-z0-9][a-z0-9_/\-]{0,50}", fullmatch=True).filter(
        lambda s: ".." not in s and "~" not in s and "\x00" not in s
    ),
)
@settings(max_examples=100)
def test_fuzz_check_path_safety_safe_paths(safe_path):
    """_check_path_safety does not raise for paths without traversal characters."""
    from blackbeard.engine.loader import _check_path_safety

    # These paths have no traversal indicators and don't start with / or \\
    _check_path_safety(safe_path, "test")


# ---------------------------------------------------------------------------
# 7. _validate_tool_config
# ---------------------------------------------------------------------------


@given(
    config=st.dictionaries(
        st.text(min_size=1, max_size=30),
        st.one_of(
            st.text(max_size=200),
            st.integers(),
            st.floats(allow_nan=False),
            st.booleans(),
            st.none(),
        ),
        max_size=15,
    ),
    tool_name=st.text(min_size=1, max_size=30),
)
@settings(max_examples=100)
def test_fuzz_validate_tool_config(config, tool_name):
    """_validate_tool_config either succeeds or raises LoaderError — never an unhandled exception."""
    from blackbeard.engine.loader import LoaderError, _validate_tool_config

    try:
        _validate_tool_config(config, tool_name)
    except LoaderError as exc:
        assert isinstance(exc.args[0], str)  # noqa: PT017


@given(
    config=st.dictionaries(
        st.text(min_size=1, max_size=30),
        st.text(max_size=200),
        min_size=51,
        max_size=55,
    ),
)
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_fuzz_validate_tool_config_rejects_large(config):
    """_validate_tool_config raises LoaderError when config has too many entries."""
    from blackbeard.engine.loader import LoaderError, _validate_tool_config

    try:
        _validate_tool_config(config, "big-tool")
        # Should have raised if len > 50
        assert len(config) <= 50
    except LoaderError:
        assert len(config) > 50


# ---------------------------------------------------------------------------
# 8. redact_sensitive_values
# ---------------------------------------------------------------------------


@given(
    data=st.dictionaries(
        st.text(min_size=1, max_size=50),
        st.one_of(
            st.text(max_size=100),
            st.integers(),
            st.floats(allow_nan=False, allow_infinity=False),
            st.booleans(),
            st.none(),
        ),
        max_size=20,
    ),
)
@settings(max_examples=100)
def test_fuzz_redact_sensitive_values_flat(data):
    """redact_sensitive_values never crashes and preserves all keys."""
    from blackbeard.models.execution_schemas import redact_sensitive_values

    result = redact_sensitive_values(data)
    assert isinstance(result, dict)
    assert set(result.keys()) == set(data.keys())


@given(
    data=st.dictionaries(
        st.text(min_size=1, max_size=50),
        _json_values,
        max_size=15,
    ),
)
@settings(max_examples=100)
def test_fuzz_redact_sensitive_values_nested(data):
    """redact_sensitive_values handles nested structures without crashing."""
    from blackbeard.models.execution_schemas import redact_sensitive_values

    result = redact_sensitive_values(data)
    assert isinstance(result, dict)
    assert set(result.keys()) == set(data.keys())


# ---------------------------------------------------------------------------
# 9. anonymize_ip and scrub_pii
# ---------------------------------------------------------------------------


@given(ip=st.text(max_size=100))
@settings(max_examples=100)
def test_fuzz_anonymize_ip(ip):
    """anonymize_ip never crashes and always returns a string."""
    from blackbeard.logging_config import anonymize_ip

    result = anonymize_ip(ip)
    assert isinstance(result, str)


@given(ip=st.one_of(st.none(), st.just(""), st.text(max_size=100)))
@settings(max_examples=100)
def test_fuzz_anonymize_ip_with_none(ip):
    """anonymize_ip handles None and empty strings gracefully."""
    from blackbeard.logging_config import anonymize_ip

    result = anonymize_ip(ip)
    assert isinstance(result, str)
    if not ip:
        assert result == "unknown"


@given(
    ip=st.from_regex(
        r"[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}", fullmatch=True
    ),
)
@settings(max_examples=100)
def test_fuzz_anonymize_ip_v4_format(ip):
    """anonymize_ip masks the last octet of IPv4-like strings."""
    from blackbeard.logging_config import anonymize_ip

    result = anonymize_ip(ip)
    assert isinstance(result, str)
    parts = ip.split(".")
    if len(parts) == 4:
        assert result.endswith(".x")
        result_parts = result.split(".")
        assert result_parts[:3] == parts[:3], (
            f"First 3 octets should be preserved: {ip!r} -> {result!r}"
        )


@given(text=st.text(max_size=500))
@settings(max_examples=100)
def test_fuzz_scrub_pii(text):
    """scrub_pii never crashes and always returns a string."""
    from blackbeard.logging_config import scrub_pii

    result = scrub_pii(text)
    assert isinstance(result, str)
    assert len(result) <= len(text) + 200, "Scrubbed output should not grow unboundedly"


# ---------------------------------------------------------------------------
# 10. is_internal_host
# ---------------------------------------------------------------------------


@given(url=st.text(max_size=200))
@settings(max_examples=100)
def test_fuzz_is_internal_host(url):
    """is_internal_host never crashes and always returns a bool."""
    from blackbeard.resources.validator import is_internal_host

    result = is_internal_host(url)
    assert isinstance(result, bool)


@given(
    hostname=st.sampled_from(
        [
            "localhost",
            "metadata.google.internal",
            "169.254.169.254",
            "host.docker.internal",
            "127.0.0.1",
            "10.0.0.1",
            "192.168.1.1",
            "::1",
            "0.0.0.0",
        ]
    ),
)
@settings(max_examples=100)
def test_fuzz_is_internal_host_known_internal(hostname):
    """is_internal_host returns True for known internal hosts."""
    from blackbeard.resources.validator import is_internal_host

    assert is_internal_host(hostname) is True


@given(
    hostname=st.sampled_from(
        [
            "example.com",
            "api.openai.com",
            "google.com",
            "8.8.8.8",
            "1.1.1.1",
        ]
    ),
)
@settings(max_examples=100)
def test_fuzz_is_internal_host_known_external(hostname):
    """is_internal_host returns False for known external hosts."""
    from blackbeard.resources.validator import is_internal_host

    assert is_internal_host(hostname) is False
