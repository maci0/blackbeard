"""Tests for schema guardrails and guardrail ref resolution.

Covers:
  - Schema guardrail with valid output passes
  - Schema guardrail with invalid output raises ValueError
  - Schema guardrail with non-JSON output raises ValueError
  - Guardrail ref resolution from Guardrail resource
  - LLM guardrail resolution (llm_prompt path)
  - Guardrail with dotted path import
  - Guardrail with free-text string passthrough
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from blackbeard.engine.loader import ResourceLoader
from blackbeard.kinds import ResourceKind
from tests.conftest import _resource_map, make_resource

# ---------------------------------------------------------------------------
# Tests -- _build_schema_guardrail
# ---------------------------------------------------------------------------


def test_schema_guardrail_valid_output():
    """Schema guardrail should return the output when it matches the schema."""
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "score": {"type": "number"},
        },
        "required": ["name", "score"],
    }

    guardrail_fn = ResourceLoader._build_schema_guardrail(schema, "test-guardrail")
    valid_output = json.dumps({"name": "Alice", "score": 95.5})

    result = guardrail_fn(valid_output)
    assert result == valid_output


def test_schema_guardrail_invalid_output_raises():
    """Schema guardrail should raise ValueError when output violates schema."""
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "score": {"type": "number"},
        },
        "required": ["name", "score"],
    }

    guardrail_fn = ResourceLoader._build_schema_guardrail(schema, "test-guardrail")
    invalid_output = json.dumps({"name": "Alice"})  # missing required "score"

    with pytest.raises(ValueError, match="test-guardrail"):
        guardrail_fn(invalid_output)


def test_schema_guardrail_wrong_type_raises():
    """Schema guardrail should raise ValueError for wrong type."""
    schema = {
        "type": "object",
        "properties": {
            "count": {"type": "integer"},
        },
        "required": ["count"],
    }

    guardrail_fn = ResourceLoader._build_schema_guardrail(schema, "type-check")
    wrong_type_output = json.dumps({"count": "not-a-number"})

    with pytest.raises(ValueError, match="type-check"):
        guardrail_fn(wrong_type_output)


def test_schema_guardrail_non_json_output_raises():
    """Schema guardrail should raise ValueError for non-JSON output."""
    schema = {"type": "object"}

    guardrail_fn = ResourceLoader._build_schema_guardrail(schema, "json-check")

    with pytest.raises(ValueError, match="not valid JSON"):
        guardrail_fn("this is not json {{{")


def test_schema_guardrail_empty_string_raises():
    """Schema guardrail should raise ValueError for empty string output."""
    schema = {"type": "object"}

    guardrail_fn = ResourceLoader._build_schema_guardrail(schema, "empty-check")

    with pytest.raises(ValueError, match="not valid JSON"):
        guardrail_fn("")


def test_schema_guardrail_array_schema():
    """Schema guardrail should work with array schemas."""
    schema = {
        "type": "array",
        "items": {"type": "string"},
        "minItems": 1,
    }

    guardrail_fn = ResourceLoader._build_schema_guardrail(schema, "array-check")

    # Valid
    valid = json.dumps(["item1", "item2"])
    assert guardrail_fn(valid) == valid

    # Invalid (empty array)
    with pytest.raises(ValueError, match="array-check"):
        guardrail_fn("[]")


# ---------------------------------------------------------------------------
# Tests -- _build_guardrails (ref resolution)
# ---------------------------------------------------------------------------


def test_build_guardrails_schema_ref():
    """Guardrail ref to a schema-type Guardrail should produce a callable."""
    guardrail_res = make_resource(
        ResourceKind.GUARDRAIL,
        "output-schema",
        {
            "type": "schema",
            "on_fail": "reject",
            "json_schema": {
                "type": "object",
                "properties": {"answer": {"type": "string"}},
                "required": ["answer"],
            },
        },
    )
    loader = ResourceLoader(_resource_map(guardrail_res))

    guardrails = loader._build_guardrails(["ref:guardrails/output-schema"])

    assert len(guardrails) == 1
    fn = guardrails[0]
    assert callable(fn)

    # Test that it validates correctly
    valid = json.dumps({"answer": "hello"})
    assert fn(valid) == valid

    with pytest.raises(ValueError):
        fn(json.dumps({"wrong_key": "hello"}))


def test_build_guardrails_function_ref():
    """Guardrail ref to a function-type Guardrail should import the callable."""
    guardrail_res = make_resource(
        ResourceKind.GUARDRAIL,
        "pii-check",
        {
            "type": "function",
            "on_fail": "reject",
            "function_path": "blackbeard.guardrails.check_pii.validate",
        },
    )
    loader = ResourceLoader(_resource_map(guardrail_res))

    mock_fn = MagicMock()
    with patch.object(ResourceLoader, "import_callable", return_value=mock_fn):
        guardrails = loader._build_guardrails(["ref:guardrails/pii-check"])

    assert len(guardrails) == 1
    assert guardrails[0] is mock_fn


def test_build_guardrails_llm_ref():
    """Guardrail ref to an llm-type Guardrail should return the prompt string."""
    guardrail_res = make_resource(
        ResourceKind.GUARDRAIL,
        "quality-check",
        {
            "type": "llm",
            "on_fail": "warn",
            "llm_prompt": "Check if the output is high quality and factual.",
        },
    )
    loader = ResourceLoader(_resource_map(guardrail_res))

    guardrails = loader._build_guardrails(["ref:guardrails/quality-check"])

    assert len(guardrails) == 1
    assert guardrails[0] == "Check if the output is high quality and factual."


def test_build_guardrails_dotted_path():
    """Dotted path without ref: prefix should be imported as callable."""
    loader = ResourceLoader({})

    mock_fn = MagicMock()
    with patch.object(ResourceLoader, "import_callable", return_value=mock_fn):
        guardrails = loader._build_guardrails(["blackbeard.guardrails.check.validate"])

    assert len(guardrails) == 1
    assert guardrails[0] is mock_fn


def test_build_guardrails_free_text():
    """Free-text string (no dots, no ref) should pass through as-is."""
    loader = ResourceLoader({})

    guardrails = loader._build_guardrails(
        ["Ensure the response is factual and well-structured"]
    )

    assert len(guardrails) == 1
    assert guardrails[0] == "Ensure the response is factual and well-structured"


def test_build_guardrails_mixed_types():
    """Mixed guardrail types should all resolve correctly."""
    guardrail_res = make_resource(
        ResourceKind.GUARDRAIL,
        "schema-guard",
        {
            "type": "schema",
            "on_fail": "reject",
            "json_schema": {"type": "object"},
        },
    )
    loader = ResourceLoader(_resource_map(guardrail_res))

    guardrails = loader._build_guardrails([
        "ref:guardrails/schema-guard",
        "Be accurate and concise",
    ])

    assert len(guardrails) == 2
    assert callable(guardrails[0])  # schema guardrail
    assert isinstance(guardrails[1], str)  # free text


def test_build_guardrails_unresolvable_ref_skipped():
    """Unresolvable guardrail ref should be skipped with warning."""
    loader = ResourceLoader({})

    guardrails = loader._build_guardrails(["ref:guardrails/nonexistent"])

    assert len(guardrails) == 0


def test_build_guardrails_failed_import_skipped():
    """Dotted path that fails to import should be skipped."""
    loader = ResourceLoader({})

    with patch.object(ResourceLoader, "import_callable", return_value=None):
        guardrails = loader._build_guardrails(["some.module.function"])

    assert len(guardrails) == 0
