"""Unit tests for ref parsing, extraction, and cycle detection.

Tests cover:
  - parse_ref(): valid refs, all kinds, non-refs, malformed/unknown-kind errors
  - extract_refs(): nested spec traversal
  - detect_cycles(): no cycles, simple cycle, longer cycle
  - build_adjacency(): graph construction from resource dicts
"""

import pytest

from blackbeard.kinds import ResourceKind
from blackbeard.resources.refs import (
    RefParseError,
    RefInfo,
    parse_ref,
    extract_refs,
    detect_cycles,
    build_adjacency,
)


# ---------------------------------------------------------------------------
# parse_ref
# ---------------------------------------------------------------------------


def test_parse_valid_ref():
    ref = parse_ref("ref:agents/researcher")
    assert ref is not None
    assert isinstance(ref, RefInfo)
    assert ref.kind == ResourceKind.AGENT
    assert ref.name == "researcher"
    assert ref.raw == "ref:agents/researcher"


def test_parse_ref_all_kinds():
    cases = [
        ("ref:agents/my-agent", ResourceKind.AGENT),
        ("ref:tasks/my-task", ResourceKind.TASK),
        ("ref:crews/my-crew", ResourceKind.CREW),
        ("ref:tools/my-tool", ResourceKind.TOOL),
        ("ref:llm-connections/gpt4", ResourceKind.LLM_CONNECTION),
    ]
    for raw, expected_kind in cases:
        ref = parse_ref(raw)
        assert ref is not None, f"Expected RefInfo for {raw!r}"
        assert ref.kind == expected_kind, f"Wrong kind for {raw!r}: got {ref.kind}"


def test_parse_non_ref_returns_none():
    assert parse_ref("just-a-string") is None
    assert parse_ref("") is None
    assert parse_ref("http://example.com") is None
    assert parse_ref(42) is None  # type: ignore[arg-type]


def test_parse_malformed_ref_raises():
    """Strings that start with 'ref:' but don't match the pattern raise RefParseError."""
    with pytest.raises(RefParseError):
        parse_ref("ref:bad")  # missing slash / name

    with pytest.raises(RefParseError):
        parse_ref("ref:/no-kind")  # empty kind segment

    with pytest.raises(RefParseError):
        parse_ref("ref:agents/")  # empty name segment

    with pytest.raises(RefParseError):
        parse_ref("ref:agents/Name_With_Underscore")  # invalid name chars


def test_parse_unknown_kind_raises():
    """A well-formed ref with an unrecognised kind should raise RefParseError."""
    with pytest.raises(RefParseError, match="Unknown resource kind"):
        parse_ref("ref:unknown/foo")

    with pytest.raises(RefParseError, match="Unknown resource kind"):
        parse_ref("ref:widgets/bar")


# ---------------------------------------------------------------------------
# extract_refs
# ---------------------------------------------------------------------------


def test_extract_refs_from_spec():
    spec = {
        "agent": "ref:agents/researcher",
        "context": ["ref:tasks/gather-data", "plain-value"],
        "nested": {
            "llm": "ref:llm-connections/gpt4",
        },
    }
    refs = extract_refs(spec)
    raw_values = {r.raw for r in refs}
    assert "ref:agents/researcher" in raw_values
    assert "ref:tasks/gather-data" in raw_values
    assert "ref:llm-connections/gpt4" in raw_values
    # plain-value is not a ref
    assert len(refs) == 3


def test_extract_refs_empty_spec():
    assert extract_refs({}) == []


def test_extract_refs_no_refs_in_spec():
    spec = {"role": "analyst", "goal": "do stuff", "backstory": "none"}
    assert extract_refs(spec) == []


def test_extract_refs_list_items():
    spec = {"tools": ["ref:tools/scraper", "ref:tools/calculator", "not-a-ref"]}
    refs = extract_refs(spec)
    assert len(refs) == 2
    assert all(r.kind == ResourceKind.TOOL for r in refs)


def test_extract_refs_field_paths():
    """Verify that field paths are recorded correctly."""
    spec = {"agent": "ref:agents/writer"}
    refs = extract_refs(spec, prefix="spec")
    assert len(refs) == 1
    assert refs[0].field == "spec.agent"


# ---------------------------------------------------------------------------
# detect_cycles
# ---------------------------------------------------------------------------


def test_detect_no_cycles():
    adjacency = {
        "Agent/a": ["Agent/b"],
        "Agent/b": ["Agent/c"],
        "Agent/c": [],
    }
    result = detect_cycles(adjacency)
    assert result == []


def test_detect_simple_cycle():
    """A → B → A should be detected as a cycle."""
    adjacency = {
        "Agent/a": ["Agent/b"],
        "Agent/b": ["Agent/a"],
    }
    result = detect_cycles(adjacency)
    assert len(result) >= 1
    cycle = result[0]
    nodes_in_cycle = set(cycle)
    assert "Agent/a" in nodes_in_cycle and "Agent/b" in nodes_in_cycle


def test_detect_longer_cycle():
    """A → B → C → A should be detected."""
    adjacency = {
        "Agent/a": ["Task/b"],
        "Task/b": ["Crew/c"],
        "Crew/c": ["Agent/a"],
    }
    result = detect_cycles(adjacency)
    assert result is not None
    assert len(result) >= 1


def test_detect_no_cycle_linear_chain():
    adjacency = {
        "Crew/c": ["Agent/a", "Task/t"],
        "Agent/a": ["LLMConnection/gpt4"],
        "Task/t": ["Agent/a"],
        "LLMConnection/gpt4": [],
    }
    assert detect_cycles(adjacency) == []


# ---------------------------------------------------------------------------
# build_adjacency
# ---------------------------------------------------------------------------


def test_build_adjacency():
    resources = [
        {
            "kind": "Task",
            "metadata": {"name": "write-report"},
            "spec": {
                "description": "Write a report",
                "expected_output": "Report",
                "agent": "ref:agents/writer",
            },
        },
        {
            "kind": "Agent",
            "metadata": {"name": "writer"},
            "spec": {
                "role": "Writer",
                "goal": "Write stuff",
                "backstory": "Been writing forever",
                "llm": "ref:llm-connections/gpt4",
            },
        },
    ]
    adj = build_adjacency(resources)

    assert "Task/write-report" in adj
    assert "Agent/writer" in adj

    # Task → Agent
    assert "Agent/writer" in adj["Task/write-report"]
    # Agent → LLMConnection
    assert "LLMConnection/gpt4" in adj["Agent/writer"]


def test_build_adjacency_empty():
    assert build_adjacency([]) == {}


def test_build_adjacency_no_refs():
    resources = [
        {
            "kind": "Agent",
            "metadata": {"name": "standalone"},
            "spec": {"role": "R", "goal": "G", "backstory": "B"},
        }
    ]
    adj = build_adjacency(resources)
    assert adj["Agent/standalone"] == []
