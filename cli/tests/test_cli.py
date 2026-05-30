"""Smoke tests for the Blackbeard CLI using Click's CliRunner.

No server required for help/version/validate commands. Commands that talk
to a server are tested with error-path assertions (e.g. connection refused).
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from blackbeard_cli.__main__ import cli

runner = CliRunner()

# Path to example resources shipped with the repo
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_EXAMPLES_DIR = _REPO_ROOT / "examples" / "research-crew"


# ---------------------------------------------------------------------------
# Top-level help and version
# ---------------------------------------------------------------------------


def test_cli_help():
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "Blackbeard" in result.output


def test_cli_version():
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert re.search(r"\d+\.\d+\.\d+", result.output), "output should contain semver"


# ---------------------------------------------------------------------------
# Subcommand --help: every subcommand should produce exit 0 with help text
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cmd",
    [
        "health",
        "validate",
        "apply",
        "get",
        "list",
        "delete",
        "kickoff",
        "status",
        "login",
        "logout",
        "whoami",
        "register",
        "executions",
        "events",
        "cancel",
        "export",
        "pull",
        "train",
        "test-crew",
    ],
)
def test_subcommand_help(cmd):
    result = runner.invoke(cli, [cmd, "--help"])
    assert result.exit_code == 0, f"'{cmd} --help' failed: {result.output}"
    # Help text should include the command name or description keywords
    assert cmd in result.output.lower() or "usage:" in result.output.lower(), (
        f"'{cmd} --help' should contain command name or Usage"
    )


# ---------------------------------------------------------------------------
# Subgroup --help: user, group, role, rolebinding sub-commands
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "group,sub",
    [
        ("user", "list"),
        ("user", "invite"),
        ("group", "list"),
        ("group", "create"),
        ("group", "delete"),
        ("role", "list"),
        ("role", "describe"),
        ("rolebinding", "list"),
        ("rolebinding", "create"),
        ("rolebinding", "delete"),
    ],
)
def test_subgroup_help(group, sub):
    result = runner.invoke(cli, [group, sub, "--help"])
    assert result.exit_code == 0, f"'{group} {sub} --help' failed: {result.output}"


# ---------------------------------------------------------------------------
# validate command — offline, uses bundled examples
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _EXAMPLES_DIR.is_dir(),
    reason="Example resources not found",
)
def test_validate_examples_directory():
    """Validate bundled example resources — should pass validation."""
    result = runner.invoke(cli, ["validate", "-f", str(_EXAMPLES_DIR)])
    assert result.exit_code == 0, f"Validation failed: {result.output}"
    assert "valid" in result.output.lower() or "OK" in result.output


@pytest.mark.skipif(
    not _EXAMPLES_DIR.is_dir(),
    reason="Example resources not found",
)
def test_validate_examples_json_output():
    """Validate examples with --json output."""
    result = runner.invoke(cli, ["validate", "-f", str(_EXAMPLES_DIR), "--json"])
    assert result.exit_code == 0, f"Validation failed: {result.output}"
    data = json.loads(result.output)
    assert data["valid"] is True
    assert data["total"] > 0
    assert data["errors"] == []
    assert data["cycles"] == []


def test_validate_single_valid_file():
    """Validate a single YAML file with a valid resource."""
    yaml_content = """\
apiVersion: blackbeard/v1
kind: Agent
metadata:
  name: test-agent
  project: default
spec:
  role: Research Analyst
  goal: Find information
  backstory: Expert researcher
"""
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        f.write(yaml_content)
        f.flush()
        try:
            result = runner.invoke(cli, ["validate", "-f", f.name])
            assert result.exit_code == 0, f"Validation failed: {result.output}"
        finally:
            os.unlink(f.name)


def test_validate_invalid_resource():
    """Validate a YAML file with an invalid resource (missing required fields)."""
    yaml_content = """\
apiVersion: blackbeard/v1
kind: Agent
metadata:
  name: bad-agent
spec:
  role: R
"""
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        f.write(yaml_content)
        f.flush()
        try:
            result = runner.invoke(cli, ["validate", "-f", f.name])
            assert result.exit_code == 1, f"Expected validation to fail, got: {result.output}"
        finally:
            os.unlink(f.name)


def test_validate_invalid_name():
    """Validate a YAML file with an invalid resource name (uppercase)."""
    yaml_content = """\
apiVersion: blackbeard/v1
kind: Agent
metadata:
  name: Bad-Agent
spec:
  role: R
  goal: G
  backstory: B
"""
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        f.write(yaml_content)
        f.flush()
        try:
            result = runner.invoke(cli, ["validate", "-f", f.name])
            assert result.exit_code == 1
        finally:
            os.unlink(f.name)


def test_validate_nonexistent_path():
    """Validate with a nonexistent path exits with code 2."""
    result = runner.invoke(cli, ["validate", "-f", "/nonexistent/path.yaml"])
    assert result.exit_code == 2


def test_validate_empty_directory():
    """Validate an empty directory exits with code 2."""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = runner.invoke(cli, ["validate", "-f", tmpdir])
        assert result.exit_code == 2


def test_validate_multi_document_yaml():
    """Validate multi-document YAML file."""
    yaml_content = """\
---
apiVersion: blackbeard/v1
kind: Agent
metadata:
  name: agent-a
spec:
  role: Researcher
  goal: Find facts
  backstory: Expert
---
apiVersion: blackbeard/v1
kind: Task
metadata:
  name: task-a
spec:
  description: Research topic
  expected_output: Key facts
  agent: "ref:agents/agent-a"
"""
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        f.write(yaml_content)
        f.flush()
        try:
            result = runner.invoke(cli, ["validate", "-f", f.name])
            assert result.exit_code == 0, f"Validation failed: {result.output}"
        finally:
            os.unlink(f.name)


# ---------------------------------------------------------------------------
# health command — expects connection failure to be handled gracefully
# ---------------------------------------------------------------------------


def test_health_no_server():
    """Health with unreachable server should fail gracefully."""
    result = runner.invoke(cli, ["-s", "http://localhost:99999", "health"])
    assert result.exit_code != 0
    assert "error" in result.output.lower() or "cannot reach" in result.output.lower()


def test_health_ready_no_server():
    """Health --ready with unreachable server should fail gracefully."""
    result = runner.invoke(cli, ["-s", "http://localhost:99999", "health", "--ready"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Commands requiring auth — should fail with helpful message when no auth
# ---------------------------------------------------------------------------


def test_list_no_auth():
    """List without auth should fail with exit code 2 and helpful message."""
    result = runner.invoke(
        cli,
        ["-s", "http://localhost:99999", "list", "Agent"],
        catch_exceptions=False,
    )
    assert result.exit_code == 2
    assert "auth" in result.output.lower() or "login" in result.output.lower()


def test_get_no_auth():
    """Get without auth should fail with exit code 2."""
    result = runner.invoke(
        cli,
        ["-s", "http://localhost:99999", "get", "Agent", "test"],
        catch_exceptions=False,
    )
    assert result.exit_code == 2


def test_delete_no_auth():
    """Delete without auth should fail with exit code 2."""
    result = runner.invoke(
        cli,
        ["-s", "http://localhost:99999", "delete", "Agent", "test", "-y"],
        catch_exceptions=False,
    )
    assert result.exit_code == 2


def test_kickoff_no_auth():
    """Kickoff without auth should fail with exit code 2."""
    result = runner.invoke(
        cli,
        ["-s", "http://localhost:99999", "kickoff", "test-crew"],
        catch_exceptions=False,
    )
    assert result.exit_code == 2


def test_executions_no_auth():
    """Executions without auth should fail with exit code 2."""
    result = runner.invoke(
        cli,
        ["-s", "http://localhost:99999", "executions"],
        catch_exceptions=False,
    )
    assert result.exit_code == 2


def test_export_no_auth():
    """Export without auth should fail with exit code 2."""
    result = runner.invoke(
        cli,
        ["-s", "http://localhost:99999", "export", "--all"],
        catch_exceptions=False,
    )
    assert result.exit_code == 2


# ---------------------------------------------------------------------------
# logout command — offline, no server needed
# ---------------------------------------------------------------------------


def test_logout_no_credentials():
    """Logout with no stored credentials should succeed."""
    with patch("blackbeard_cli.auth_cmds.clear_credentials", return_value=False):
        result = runner.invoke(cli, ["logout"])
    assert result.exit_code == 0
    out = result.output.lower()
    assert "no credentials" in out or "no stored" in out or "not logged" in out, (
        f"logout with no creds should say so, got: {result.output!r}"
    )


def test_logout_with_credentials():
    """Logout with stored credentials should clear them."""
    with patch("blackbeard_cli.auth_cmds.clear_credentials", return_value=True):
        result = runner.invoke(cli, ["logout"])
    assert result.exit_code == 0
    assert "logged out" in result.output.lower()


def test_logout_json_output():
    """Logout with --json should output JSON."""
    with patch("blackbeard_cli.auth_cmds.clear_credentials", return_value=True):
        result = runner.invoke(cli, ["logout", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "logged_out"


# ---------------------------------------------------------------------------
# apply command — validation checks (offline part)
# ---------------------------------------------------------------------------


def test_apply_dry_run():
    """Apply with --dry-run should not apply resources."""
    yaml_content = """\
apiVersion: blackbeard/v1
kind: Agent
metadata:
  name: dry-agent
spec:
  role: Researcher
  goal: Find facts
  backstory: Expert
"""
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        f.write(yaml_content)
        f.flush()
        try:
            result = runner.invoke(
                cli,
                ["-k", "test-key", "apply", "-f", f.name, "--dry-run"],
            )
            assert result.exit_code == 0
            assert "dry run" in result.output.lower()
        finally:
            os.unlink(f.name)


def test_apply_dry_run_json():
    """Apply with --dry-run --json should output JSON."""
    yaml_content = """\
apiVersion: blackbeard/v1
kind: Agent
metadata:
  name: dry-agent
spec:
  role: Researcher
  goal: Find facts
  backstory: Expert
"""
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        f.write(yaml_content)
        f.flush()
        try:
            result = runner.invoke(
                cli,
                ["-k", "test-key", "apply", "-f", f.name, "--dry-run", "--json"],
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["dry_run"] is True
            assert len(data["resources"]) == 1
        finally:
            os.unlink(f.name)


def test_apply_validation_error_aborts():
    """Apply with invalid resources should abort."""
    yaml_content = """\
apiVersion: blackbeard/v1
kind: Agent
metadata:
  name: bad-agent
spec:
  role: R
"""
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        f.write(yaml_content)
        f.flush()
        try:
            result = runner.invoke(
                cli,
                ["-k", "test-key", "apply", "-f", f.name, "-y"],
            )
            assert result.exit_code == 1
        finally:
            os.unlink(f.name)


# ---------------------------------------------------------------------------
# CLI helpers unit tests
# ---------------------------------------------------------------------------


def test_parse_key_value_inputs():
    """parse_key_value_inputs should parse KEY=VALUE pairs."""
    from blackbeard_cli.helpers import parse_key_value_inputs

    result = parse_key_value_inputs(("topic=AI agents", "count=3"))
    assert result["topic"] == "AI agents"
    assert result["count"] == 3  # JSON-parsed


def test_parse_key_value_inputs_json_value():
    """parse_key_value_inputs should parse JSON values."""
    from blackbeard_cli.helpers import parse_key_value_inputs

    result = parse_key_value_inputs(('config={"nested": true}',))
    assert result["config"]["nested"] is True


def test_parse_key_value_inputs_invalid():
    """parse_key_value_inputs should exit on invalid format."""
    from blackbeard_cli.helpers import parse_key_value_inputs

    with pytest.raises(SystemExit):
        parse_key_value_inputs(("no-equals-sign",))


def test_parse_key_value_inputs_empty_key():
    """parse_key_value_inputs should exit on empty key."""
    from blackbeard_cli.helpers import parse_key_value_inputs

    with pytest.raises(SystemExit):
        parse_key_value_inputs(("=value",))


def test_validate_name_valid():
    """validate_name should accept valid names."""
    from blackbeard_cli.helpers import validate_name

    validate_name("my-agent")
    validate_name("agent123")
    validate_name("a")


def test_validate_name_invalid():
    """validate_name should reject invalid names."""
    from blackbeard_cli.helpers import validate_name

    with pytest.raises(SystemExit):
        validate_name("Bad-Name")

    with pytest.raises(SystemExit):
        validate_name("-starts-with-hyphen")


def test_extract_detail_json():
    """extract_detail should extract from JSON body."""
    from blackbeard_cli.helpers import extract_detail

    resp = MagicMock()
    resp.json.return_value = {"detail": "Not found"}
    result = extract_detail(resp)
    assert result == "Not found"


def test_extract_detail_non_json():
    """extract_detail should fall back to text for non-JSON."""
    from blackbeard_cli.helpers import extract_detail

    resp = MagicMock()
    resp.json.side_effect = ValueError("not json")
    resp.text = "Internal Server Error"
    result = extract_detail(resp)
    assert result == "Internal Server Error"


# ---------------------------------------------------------------------------
# Credentials module unit tests
# ---------------------------------------------------------------------------


def test_credentials_save_and_load(tmp_path):
    """Credentials can be saved and loaded."""
    from blackbeard_cli import credentials as creds_mod

    original_file = creds_mod._CREDENTIALS_FILE
    original_dir = creds_mod._CONFIG_DIR
    creds_mod._CONFIG_DIR = tmp_path
    creds_mod._CREDENTIALS_FILE = tmp_path / "credentials.json"
    try:
        creds_mod.save_credentials(
            server="http://localhost:8000",
            access_token="tok-123",
            refresh_token="ref-456",
            email="test@example.com",
            expires_at=9999999999.0,
        )
        creds = creds_mod.load_credentials()
        assert creds is not None
        assert creds.server == "http://localhost:8000"
        assert creds.access_token == "tok-123"
        assert creds.email == "test@example.com"
    finally:
        creds_mod._CREDENTIALS_FILE = original_file
        creds_mod._CONFIG_DIR = original_dir


def test_credentials_load_missing(tmp_path):
    """Loading from nonexistent file returns None."""
    from blackbeard_cli import credentials as creds_mod

    original_file = creds_mod._CREDENTIALS_FILE
    creds_mod._CREDENTIALS_FILE = tmp_path / "nonexistent.json"
    try:
        assert creds_mod.load_credentials() is None
    finally:
        creds_mod._CREDENTIALS_FILE = original_file


def test_credentials_load_corrupt(tmp_path):
    """Loading corrupt JSON returns None."""
    from blackbeard_cli import credentials as creds_mod

    original_file = creds_mod._CREDENTIALS_FILE
    creds_file = tmp_path / "credentials.json"
    creds_file.write_text("not valid json{{{", encoding="utf-8")
    creds_mod._CREDENTIALS_FILE = creds_file
    try:
        assert creds_mod.load_credentials() is None
    finally:
        creds_mod._CREDENTIALS_FILE = original_file


def test_credentials_clear(tmp_path):
    """clear_credentials removes the file and returns True."""
    from blackbeard_cli import credentials as creds_mod

    original_file = creds_mod._CREDENTIALS_FILE
    original_dir = creds_mod._CONFIG_DIR
    creds_mod._CONFIG_DIR = tmp_path
    creds_mod._CREDENTIALS_FILE = tmp_path / "credentials.json"
    try:
        creds_mod.save_credentials(
            server="http://localhost:8000",
            access_token="tok",
            refresh_token="ref",
            email="x@y.com",
            expires_at=0,
        )
        assert creds_mod.clear_credentials() is True
        assert not creds_mod._CREDENTIALS_FILE.exists()
        # Clearing again returns False
        assert creds_mod.clear_credentials() is False
    finally:
        creds_mod._CREDENTIALS_FILE = original_file
        creds_mod._CONFIG_DIR = original_dir


# ---------------------------------------------------------------------------
# Kinds module: sanity checks
# ---------------------------------------------------------------------------


def test_all_kinds_match_enum():
    """ALL_KINDS should match ResourceKind enum values."""
    from blackbeard_cli.kinds import ALL_KINDS, ResourceKind

    assert ALL_KINDS == frozenset(k.value for k in ResourceKind)


def test_plural_to_kind_roundtrip():
    """KIND_TO_PLURAL and PLURAL_TO_KIND should be inverses."""
    from blackbeard_cli.kinds import KIND_TO_PLURAL, PLURAL_TO_KIND

    for kind, plural in KIND_TO_PLURAL.items():
        assert PLURAL_TO_KIND[plural] == kind


# ---------------------------------------------------------------------------
# Export command: _strip_server_fields helper
# ---------------------------------------------------------------------------


def test_strip_server_fields():
    """_strip_server_fields should keep only apiVersion, kind, metadata, spec."""
    from blackbeard_cli.export_cmd import _strip_server_fields

    resource = {
        "apiVersion": "blackbeard/v1",
        "kind": "Agent",
        "metadata": {
            "name": "test",
            "project": "default",
            "labels": {"env": "prod"},
        },
        "spec": {"role": "R", "goal": "G", "backstory": "B"},
        "version": 5,
        "created_at": "2024-01-01",
    }
    cleaned = _strip_server_fields(resource)
    assert "version" not in cleaned
    assert "created_at" not in cleaned
    assert cleaned["metadata"]["name"] == "test"
    # default namespace is not included
    assert "project" not in cleaned["metadata"]
    assert cleaned["metadata"]["labels"] == {"env": "prod"}


def test_strip_server_fields_non_default_namespace():
    """_strip_server_fields should include non-default namespace."""
    from blackbeard_cli.export_cmd import _strip_server_fields

    resource = {
        "kind": "Agent",
        "metadata": {"name": "test", "project": "prod"},
        "spec": {},
    }
    cleaned = _strip_server_fields(resource)
    assert cleaned["metadata"]["project"] == "prod"


# ---------------------------------------------------------------------------
# exec.py: _event_color and _event_summary helpers
# ---------------------------------------------------------------------------


def test_event_color_started():
    from blackbeard_cli.exec import _event_color

    assert _event_color("task_started") == "blue"


def test_event_color_completed():
    from blackbeard_cli.exec import _event_color

    assert _event_color("task_completed") == "green"


def test_event_color_failed():
    from blackbeard_cli.exec import _event_color

    assert _event_color("task_failed") == "red"


def test_event_color_unknown():
    from blackbeard_cli.exec import _event_color

    assert _event_color("unknown_type") == "dim"


def test_event_summary_with_data():
    from blackbeard_cli.exec import _event_summary

    result = _event_summary(
        "task_started",
        {
            "task_name": "research",
            "agent_name": "researcher",
            "status": "running",
        },
    )
    assert "task=research" in result
    assert "agent=researcher" in result
    assert "status=running" in result


def test_event_summary_empty_data():
    from blackbeard_cli.exec import _event_summary

    result = _event_summary("task_started", {})
    assert result == ""
