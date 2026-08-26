"""Tests for blackbeard_cli.helpers timestamp formatting."""

from __future__ import annotations

from blackbeard_cli.helpers import format_timestamp


def test_utc_offset_stripped_for_alignment():
    assert format_timestamp("2026-08-23T14:30:00+00:00") == "2026-08-23T14:30:00"


def test_z_suffix_handled():
    assert format_timestamp("2026-08-23T14:30:00Z") == "2026-08-23T14:30:00"


def test_non_utc_offset_converted_to_utc():
    # 16:30+02:00 is 14:30 UTC, the wall time shown must be the instant in UTC.
    assert format_timestamp("2026-08-23T16:30:00+02:00") == "2026-08-23T14:30:00"


def test_fractional_seconds_dropped():
    assert format_timestamp("2026-08-23T14:30:00.123456+00:00") == "2026-08-23T14:30:00"


def test_naive_value_passed_through():
    assert format_timestamp("2026-08-23T14:30:00") == "2026-08-23T14:30:00"


def test_unparseable_value_truncated():
    assert format_timestamp("not-a-timestamp-at-all") == "not-a-timestamp-at-"


def test_missing_value_falls_back():
    assert format_timestamp(None) == "\u2014"
    assert format_timestamp(None, fallback="n/a") == "n/a"
    assert format_timestamp("") == "\u2014"
