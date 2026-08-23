"""Tests for logging formatters: UTC rendering regardless of host timezone."""

from __future__ import annotations

import datetime as dt
import json
import logging

from blackbeard.logging_config import _JsonFormatter, _PiiScrubFormatter


def test_debug_formatter_renders_asctime_in_utc() -> None:
    """%(asctime)s must not depend on the host's local timezone.

    The JSON formatter emits UTC ISO timestamps; the human-readable debug
    formatter must agree (converter = time.gmtime), otherwise replicas in
    different timezones produce logs that sort and correlate incorrectly.
    """
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    text = _PiiScrubFormatter(fmt="%(asctime)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S").format(
        record
    )
    # Strip the default ",mmm" millisecond suffix Formatter appends.
    stamp = text.split(" ", 1)[0].split(",")[0]
    parsed = dt.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=dt.UTC)
    expected = dt.datetime.fromtimestamp(record.created, tz=dt.UTC).replace(microsecond=0)
    assert parsed == expected


def test_json_formatter_timestamp_is_utc_aware() -> None:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    entry = json.loads(_JsonFormatter().format(record))
    ts = dt.datetime.fromisoformat(entry["timestamp"])
    assert ts.utcoffset() == dt.timedelta(0)
