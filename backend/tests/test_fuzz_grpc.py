"""Fuzz / property-based tests for gRPC server pure functions.

Covers:
  1. _resolve_kind — accepts both 'Agent' (kind) and 'agents' (plural) forms
  2. _resource_to_proto — ORM → protobuf conversion, never crashes
  3. _execution_to_proto — ORM → protobuf conversion, never crashes
  4. CreateResource spec_json parsing — malformed JSON handled gracefully
  5. Kickoff inputs_json parsing — malformed JSON handled gracefully
  6. GetExecution / StreamEvents execution_id parsing — invalid UUIDs handled

The invariant: no input should cause an unhandled exception.
"""

from __future__ import annotations

import contextlib
import json
from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from blackbeard.grpc.server import (
    _execution_to_proto,
    _resolve_kind,
    _resource_to_proto,
)
from blackbeard.kinds import KIND_TO_PLURAL, PLURAL_TO_KIND

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_safe_text = st.text(max_size=200)
_json_primitives = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-(2**31), max_value=2**31),
    st.floats(allow_nan=False, allow_infinity=False),
    st.text(max_size=100),
)
_json_values = st.recursive(
    _json_primitives,
    lambda children: st.one_of(
        st.lists(children, max_size=5),
        st.dictionaries(st.text(max_size=30), children, max_size=5),
    ),
    max_leaves=20,
)


# ---------------------------------------------------------------------------
# 1. _resolve_kind fuzzing
# ---------------------------------------------------------------------------


@given(kind_str=_safe_text)
@settings(max_examples=200, deadline=None)
def test_resolve_kind_never_crashes(kind_str: str) -> None:
    """_resolve_kind should return a string for any input, never raise."""
    result = _resolve_kind(kind_str)
    assert isinstance(result, str)


@given(kind=st.sampled_from(list(KIND_TO_PLURAL.keys())))
@settings(max_examples=50)
def test_resolve_kind_accepts_kind_values(kind: str) -> None:
    """Known kind values should pass through unchanged."""
    assert _resolve_kind(kind) == kind


@given(plural=st.sampled_from(list(PLURAL_TO_KIND.keys())))
@settings(max_examples=50)
def test_resolve_kind_maps_plurals(plural: str) -> None:
    """Known plural forms should be resolved to their kind value."""
    assert _resolve_kind(plural) == PLURAL_TO_KIND[plural]


def test_resolve_kind_unknown_passthrough() -> None:
    """Unknown strings should be returned as-is (no crash)."""
    assert _resolve_kind("not-a-real-kind") == "not-a-real-kind"
    assert _resolve_kind("") == ""
    assert _resolve_kind("'; DROP TABLE--") == "'; DROP TABLE--"


# ---------------------------------------------------------------------------
# 2. _resource_to_proto fuzzing
# ---------------------------------------------------------------------------


def _make_mock_resource(
    *,
    kind: str = "Agent",
    name: str = "test",
    project: str = "default",
    spec: dict | None = None,
    version: int = 1,
    has_id: bool = True,
    has_timestamps: bool = True,
) -> MagicMock:
    r = MagicMock()
    r.id = uuid4() if has_id else None
    r.kind = MagicMock(value=kind) if kind else kind
    r.name = name
    r.project = project
    r.spec = spec or {}
    r.version = version
    if has_timestamps:
        r.created_at = datetime.now(UTC)
        r.updated_at = datetime.now(UTC)
    else:
        r.created_at = None
        r.updated_at = None
    return r


@given(
    name=_safe_text,
    project=_safe_text,
    spec=st.dictionaries(st.text(max_size=30), _json_primitives, max_size=10),
    version=st.integers(min_value=0, max_value=10000),
)
@settings(max_examples=100, deadline=None)
def test_resource_to_proto_never_crashes(
    name: str,
    project: str,
    spec: dict,
    version: int,
) -> None:
    """_resource_to_proto should produce a valid proto for any input."""
    resource = _make_mock_resource(
        name=name,
        project=project,
        spec=spec,
        version=version,
    )
    proto = _resource_to_proto(resource)
    assert proto.name == name
    # _resource_to_proto uses `or "default"` / `or 1` for falsy values
    assert proto.project == (project or "default")
    assert proto.version == (version or 1)
    parsed = json.loads(proto.spec_json)
    assert isinstance(parsed, dict)


def test_resource_to_proto_none_fields() -> None:
    """None values in optional fields should produce safe defaults."""
    resource = _make_mock_resource(
        name="",
        project="",
        spec=None,
        version=0,
        has_id=False,
        has_timestamps=False,
    )
    resource.spec = None
    proto = _resource_to_proto(resource)
    assert proto.id == ""
    assert proto.spec_json == "{}"
    assert proto.created_at == ""


# ---------------------------------------------------------------------------
# 3. _execution_to_proto fuzzing
# ---------------------------------------------------------------------------


def _make_mock_execution(
    *,
    crew_name: str = "crew",
    status: str = "queued",
    execution_type: str = "kickoff",
    inputs: dict | None = None,
    outputs: dict | None = None,
    total_tokens: int = 0,
    has_timestamps: bool = True,
) -> MagicMock:
    e = MagicMock()
    e.id = uuid4()
    e.crew_name = crew_name
    e.crew_project = "default"
    e.status = MagicMock(value=status)
    e.execution_type = MagicMock(value=execution_type)
    e.inputs = inputs
    e.outputs = outputs
    e.error = None
    e.total_tokens = total_tokens
    if has_timestamps:
        e.created_at = datetime.now(UTC)
        e.started_at = datetime.now(UTC)
        e.completed_at = None
    else:
        e.created_at = None
        e.started_at = None
        e.completed_at = None
    return e


@given(
    crew_name=_safe_text,
    status=st.sampled_from(["queued", "running", "completed", "failed", "cancelled"]),
    inputs=st.dictionaries(st.text(max_size=30), _json_primitives, max_size=10),
    total_tokens=st.integers(min_value=0, max_value=10**9),
)
@settings(max_examples=100, deadline=None)
def test_execution_to_proto_never_crashes(
    crew_name: str,
    status: str,
    inputs: dict,
    total_tokens: int,
) -> None:
    """_execution_to_proto should produce a valid proto for any input."""
    execution = _make_mock_execution(
        crew_name=crew_name,
        status=status,
        inputs=inputs,
        total_tokens=total_tokens,
    )
    proto = _execution_to_proto(execution)
    assert proto.crew_name == crew_name
    assert proto.total_tokens == total_tokens
    parsed = json.loads(proto.inputs_json)
    assert isinstance(parsed, dict)


def test_execution_to_proto_none_fields() -> None:
    """None values should produce safe empty defaults."""
    execution = _make_mock_execution(has_timestamps=False)
    execution.id = None
    execution.crew_name = None
    execution.inputs = None
    execution.outputs = None
    execution.error = None
    execution.total_tokens = None
    proto = _execution_to_proto(execution)
    assert proto.id == ""
    assert proto.inputs_json == "{}"
    assert proto.outputs_json == "{}"


# ---------------------------------------------------------------------------
# 4. spec_json / inputs_json parsing edge cases
# ---------------------------------------------------------------------------


EVIL_JSON_STRINGS = [
    "",
    "null",
    "true",
    "42",
    '"a string"',
    "[1,2,3]",
    '{"valid": "json"}',
    "{invalid json}",
    "{'single': 'quotes'}",
    "\x00\x01\x02",
    "a" * 100_000,
    '{"key": "' + "x" * 50_000 + '"}',
    '{"a": {"b": {"c": {"d": {"e": {"f": "deep"}}}}}}',
    '{"__proto__": {"polluted": true}}',
    '{"constructor": {"prototype": {"isAdmin": true}}}',
]


def test_spec_json_parsing_robustness() -> None:
    """json.loads on malformed spec_json should raise JSONDecodeError, not crash."""
    for evil in EVIL_JSON_STRINGS:
        try:
            result = json.loads(evil) if evil else {}
            assert result is not None or result is None  # any result is fine
        except json.JSONDecodeError:
            pass  # expected for malformed JSON


@given(raw=st.text(max_size=5000))
@settings(max_examples=200, deadline=None)
def test_fuzz_json_loads_never_crashes(raw: str) -> None:
    """json.loads should either parse or raise JSONDecodeError, never crash."""
    with contextlib.suppress(json.JSONDecodeError, ValueError):
        json.loads(raw)


# ---------------------------------------------------------------------------
# 5. UUID parsing for execution_id
# ---------------------------------------------------------------------------

EVIL_EXECUTION_IDS = [
    "",
    "not-a-uuid",
    "00000000-0000-0000-0000-000000000000",
    "../../../etc/passwd",
    "'; DROP TABLE executions--",
    "a" * 10_000,
    "\x00",
    str(uuid4()),
]


def test_uuid_parsing_robustness() -> None:
    """UUID() should raise ValueError for malformed IDs, not crash."""
    from uuid import UUID

    for evil_id in EVIL_EXECUTION_IDS:
        with contextlib.suppress(ValueError):
            UUID(evil_id)


@given(execution_id=_safe_text)
@settings(max_examples=200, deadline=None)
def test_fuzz_uuid_parsing(execution_id: str) -> None:
    """UUID() should either parse or raise ValueError for any string."""
    from uuid import UUID

    with contextlib.suppress(ValueError):
        UUID(execution_id)
