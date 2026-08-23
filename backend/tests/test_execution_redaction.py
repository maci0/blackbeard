"""Unit tests for execution input redaction (models/execution_schemas.py).

redact_sensitive_values scrubs sensitive-looking values before they are
persisted on Execution rows or streamed as events; contains_redacted_values
detects the sentinel so retry can refuse to re-run with placeholder inputs.
"""

from __future__ import annotations

from blackbeard.models.execution_schemas import (
    contains_redacted_values,
    redact_sensitive_values,
)

REDACTED = "[REDACTED]"


class TestRedactSensitiveValues:
    def test_redacts_top_level_sensitive_keys(self):
        inputs = {
            "topic": "AI safety",
            "password": "hunter2",
            "api_key": "sk-live-123",
            "auth_token": "bearer-xyz",
        }
        out = redact_sensitive_values(inputs)
        assert out["password"] == REDACTED
        assert out["api_key"] == REDACTED
        assert out["auth_token"] == REDACTED
        # Non-sensitive values pass through untouched.
        assert out["topic"] == "AI safety"

    def test_matching_is_case_insensitive(self):
        out = redact_sensitive_values({"Password": "x", "SECRET_VALUE": "y"})
        assert out["Password"] == REDACTED
        assert out["SECRET_VALUE"] == REDACTED

    def test_benign_inputs_returned_unmodified(self):
        inputs = {"topic": "AI", "max_retries": 3, "tags": ["a", "b"]}
        assert redact_sensitive_values(inputs) is inputs

    def test_original_dict_not_mutated(self):
        inputs = {"password": "hunter2", "nested": {"credit_card": "4111"}}
        out = redact_sensitive_values(inputs)
        assert inputs["password"] == "hunter2"
        assert inputs["nested"]["credit_card"] == "4111"
        assert out is not inputs

    def test_recurses_into_nested_dicts(self):
        out = redact_sensitive_values({"config": {"db": {"password": "pw", "host": "localhost"}}})
        assert out["config"]["db"]["password"] == REDACTED
        assert out["config"]["db"]["host"] == "localhost"

    def test_recurses_into_lists_of_dicts(self):
        out = redact_sensitive_values({"steps": [{"name": "s1"}, {"api_token": "t", "name": "s2"}]})
        assert out["steps"][0] == {"name": "s1"}
        assert out["steps"][1]["api_token"] == REDACTED
        assert out["steps"][1]["name"] == "s2"

    def test_non_dict_list_items_pass_through(self):
        inputs = {"tags": ["alpha", "beta"], "count": 2}
        out = redact_sensitive_values(inputs)
        assert out == inputs

    def test_empty_dict(self):
        assert redact_sensitive_values({}) == {}


class TestContainsRedactedValues:
    def test_detects_sentinel_at_top_level(self):
        assert contains_redacted_values({"password": REDACTED}) is True

    def test_detects_sentinel_nested(self):
        assert contains_redacted_values({"cfg": {"deep": {"key": REDACTED}}}) is True

    def test_detects_sentinel_in_lists(self):
        assert contains_redacted_values({"items": [{"token": REDACTED}]}) is True

    def test_clean_data_is_negative(self):
        assert contains_redacted_values({"topic": "AI", "n": 1, "ok": True}) is False

    def test_plain_string_is_negative(self):
        assert contains_redacted_values("just text") is False

    def test_similar_but_different_value_is_negative(self):
        # The literal sentinel must match exactly; near-misses do not count.
        assert contains_redacted_values({"k": "[redacted]"}) is False
        assert contains_redacted_values({"k": "REDACTED"}) is False


class TestRoundTrip:
    def test_redaction_then_detection(self):
        """Anything redact_sensitive_values touches must be flagged for retry refusal."""
        cases = [
            {"password": "x"},
            {"nested": {"api_key": "x"}},
            {"list": [{"secret": "x"}]},
            {"email_address": "a@b.c"},
        ]
        for original in cases:
            assert contains_redacted_values(redact_sensitive_values(original)) is True, (
                f"sentinel not detected after redacting {original}"
            )

    def test_clean_input_round_trip(self):
        inputs = {"topic": "AI safety", "retries": 3}
        assert contains_redacted_values(redact_sensitive_values(inputs)) is False
