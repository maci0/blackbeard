"""Resource validation: JSON Schema + ref format validation."""

from __future__ import annotations

import concurrent.futures
import ipaddress
import logging
import re
import socket
import threading
from typing import Any
from urllib.parse import urlparse

import jsonschema

from blackbeard_cli.resources.exceptions import ValidationError
from blackbeard_cli.resources.refs import RefInfo, RefParseError, extract_refs
from blackbeard_cli.resources.spec_schemas import KIND_SCHEMAS

logger = logging.getLogger(__name__)

_VALIDATORS: dict[str, jsonschema.Draft7Validator] = {
    kind: jsonschema.Draft7Validator(schema) for kind, schema in KIND_SCHEMAS.items()
}

# Environment variable prefixes that must not be referenced via api_key_env
# to prevent exfiltration of internal secrets through LiteLLM config.
_BLOCKED_ENV_PREFIXES = (
    "BLACKBEARD_",
    "LITELLM_",
    "DATABASE_",
    "VALKEY_",
    "REDIS_",
    "GOOGLE_",
    "AWS_",
    "AZURE_",
    "GCP_",
    "CLOUD_",
    "NEXTAUTH_",
    "ENCRYPTION_",
    "SALT_",
    "POSTGRES_",
    "MINIO_",
    "CLICKHOUSE_",
    "DOCKER_",
    "HEROKU_",
    "VERCEL_",
    "RAILWAY_",
    "PRIVATE_",
    "INTERNAL_",
    "SECRET_",
    "PASSWORD_",
    "TOKEN_",
    "CREDENTIAL_",
    "AUTH_",
    "SIGNING_",
    "APIKEY_",
    "API_KEY_",
    "GITHUB_",
    "GITLAB_",
    "CI_",
    "JENKINS_",
    "OPENAI_",
    "ANTHROPIC_",
    "MISTRAL_",
    "DEEPSEEK_",
    "GROQ_",
    "TOGETHER_",
    "FIREWORKS_",
    "ANYSCALE_",
    "VOYAGE_",
    "COHERE_",
    "PINECONE_",
    "WEAVIATE_",
    "QDRANT_",
    "DATABRICKS_",
    "LANGFUSE_",
    "LANGCHAIN_",
    "LANGSMITH_",
    "HF_",
    "HUGGINGFACE_",
    "REPLICATE_",
    "SENDGRID_",
    "STRIPE_",
    "TWILIO_",
    "SLACK_",
    "DISCORD_",
    "NPM_",
    "JWT_",
    "OIDC_",
    "OTEL_",
    "SESSION_",
    "SENTRY_",
    "CORS_",
    "FORWARDED_",
    "GRPC_",
    "CONTAINER_",
    "FIRECRACKER_",
    "MUNINNDB_",
    "CELERY_",
    "FLOWER_",
    "KAFKA_",
    "RABBITMQ_",
    "AMQP_",
    "ELASTIC_",
    "MONGO_",
    "DATADOG_",
    "DD_",
    "NEWRELIC_",
    "SPLUNK_",
)

_BLOCKED_ENV_EXACT = frozenset(
    {
        "PATH",
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
        "PYTHONPATH",
        "PYTHONSTARTUP",
        "PYTHONHOME",
        "NODE_OPTIONS",
        "NODE_PATH",
        "HOME",
        "SHELL",
        "USER",
        "LOGNAME",
        "HOSTNAME",
        "PWD",
        "LANG",
        "SSH_AUTH_SOCK",
        "GPG_AGENT_INFO",
        "KUBECONFIG",
        "WANDB_API_KEY",
        "OTEL_ENDPOINT",
        "CORS_ORIGINS",
        "FORWARDED_ALLOW_IPS",
        "WEB_CONCURRENCY",
        "LITELLM_DATABASE_URL",
        "ENCRYPTION_KEY",
        "SIGNING_KEY",
        "MASTER_KEY",
    }
)

_INTERNAL_HOSTNAMES = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "metadata.google.internal",
        "metadata.goog",
        "metadata",
        "kubernetes.default.svc",
        "169.254.169.254",
        "host.docker.internal",
        "gateway.docker.internal",
    }
)

_INTERNAL_DOMAIN_SUFFIXES = (
    ".internal",
    ".local",
    ".svc",
    ".svc.cluster.local",
)

_SHARED_ADDRESS_SPACE = ipaddress.IPv4Network("100.64.0.0/10")


def _is_internal_ip(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    check = addr
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        check = addr.ipv4_mapped
    return (
        check.is_private
        or check.is_reserved
        or check.is_loopback
        or check.is_link_local
        or check.is_unspecified
        or (isinstance(check, ipaddress.IPv4Address) and check in _SHARED_ADDRESS_SPACE)
    )


def is_internal_host(hostname: str) -> bool:
    hostname_lower = hostname.lower().rstrip(".")
    if hostname_lower in _INTERNAL_HOSTNAMES:
        return True
    if hostname_lower.endswith(_INTERNAL_DOMAIN_SUFFIXES):
        return True
    try:
        addr = ipaddress.ip_address(hostname_lower)
        return _is_internal_ip(addr)
    except ValueError:
        pass
    # Catch obfuscated IP representations (hex, octal, decimal) that bypass
    # ipaddress.ip_address() but resolve via socket.inet_aton().
    # Examples: 0x7f000001, 2130706433, 017700000001 all resolve to 127.0.0.1.
    try:
        packed = socket.inet_aton(hostname_lower)
        addr = ipaddress.IPv4Address(packed)
        return _is_internal_ip(addr)
    except (OSError, ValueError):
        return False


def _validate_llm_connection_extra(spec: dict[str, Any], errors: list[ValidationError]) -> None:
    """Block SSRF via base_url and env var exfiltration via api_key_env."""
    api_key_env = spec.get("api_key_env")
    if isinstance(api_key_env, str) and is_blocked_env_name(api_key_env):
        errors.append(
            ValidationError(
                "spec.api_key_env",
                f"Cannot reference internal environment variable '{api_key_env}'. "
                "Use a dedicated variable for external API keys.",
            )
        )

    base_url = spec.get("base_url")
    if base_url and isinstance(base_url, str):
        _validate_url_ssrf(base_url, "spec.base_url", errors)


_SAFE_PATH_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._/ -]*$")


def is_blocked_env_name(name: str) -> bool:
    """Check if an environment variable name is on the blocklist."""
    upper = name.upper()
    return upper.startswith(_BLOCKED_ENV_PREFIXES) or upper in _BLOCKED_ENV_EXACT


def check_url_ssrf(url: str) -> str | None:
    """Check a URL for SSRF risks. Returns an error message or None if safe."""
    errors: list[ValidationError] = []
    _validate_url_ssrf(url, "url", errors)
    return errors[0].message if errors else None


def _is_path_traversal(path: str) -> bool:
    """Check if a file path contains traversal or escapes the working directory."""
    if "\x00" in path:
        return True
    if path.startswith(("/", "\\", "~")):
        return True
    normalized = path.replace("\\", "/")
    if ".." in normalized.split("/"):
        return True
    return not _SAFE_PATH_PATTERN.match(path)


def _validate_url_ssrf(url: str, field_name: str, errors: list[ValidationError]) -> None:
    """Validate a URL against SSRF — reusable across kinds.

    Performs two layers of validation:
    1. Hostname-based checks (blocklists, IP format checks)
    2. DNS resolution check — resolves the hostname and verifies all resolved
       IPs are routable. This prevents DNS rebinding attacks where a public
       domain resolves to an internal IP (e.g., 169.254.169.254).

    NOTE: DNS resolution uses socket.getaddrinfo which is a blocking call.
    A 5-second timeout is applied to prevent slow/hanging DNS lookups from
    blocking the CLI. This is acceptable because validation runs
    infrequently and the timeout caps worst-case latency.
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            errors.append(ValidationError(field_name, "URL must use http or https scheme."))
        elif parsed.username or parsed.password:
            errors.append(ValidationError(field_name, "URL must not contain embedded credentials."))
        else:
            hostname = parsed.hostname or ""
            if is_internal_host(hostname):
                errors.append(
                    ValidationError(
                        field_name,
                        "URL must not point to internal or private network addresses.",
                    )
                )
            else:
                _check_dns_resolution(hostname, field_name, errors)
    except Exception:
        logger.warning(
            "URL SSRF validation failed for field %s: %s",
            field_name,
            url[:200],
            exc_info=True,
            extra={"event": "url_ssrf_parse_error", "field": field_name},
        )
        errors.append(ValidationError(field_name, "URL could not be parsed for SSRF validation."))


_DNS_EXECUTOR: concurrent.futures.ThreadPoolExecutor | None = None
_DNS_EXECUTOR_LOCK = threading.Lock()


def _get_dns_executor() -> concurrent.futures.ThreadPoolExecutor:
    """Return a shared executor for DNS resolution.

    Uses lock-always pattern (safe under both GIL and free-threaded Python).
    """
    with _DNS_EXECUTOR_LOCK:
        global _DNS_EXECUTOR
        if _DNS_EXECUTOR is not None:
            return _DNS_EXECUTOR
        _DNS_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="dns-resolve"
        )
        return _DNS_EXECUTOR


def _check_dns_resolution(hostname: str, field_name: str, errors: list[ValidationError]) -> None:
    """Resolve hostname via DNS and reject if any address is internal.

    Runs in a thread with a 5-second timeout to avoid blocking the CLI
    when DNS is slow or unresponsive.
    """

    def _resolve() -> list[tuple[Any, ...]]:
        return socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)

    try:
        pool = _get_dns_executor()
        future = pool.submit(_resolve)
        results = future.result(timeout=5.0)
        for _family, _type, _proto, _canonname, sockaddr in results:
            addr_str = sockaddr[0]
            try:
                addr = ipaddress.ip_address(addr_str)
                if _is_internal_ip(addr):
                    errors.append(
                        ValidationError(
                            field_name,
                            "URL hostname resolves to an internal/private IP address.",
                        )
                    )
                    return
            except ValueError:
                pass
    except concurrent.futures.TimeoutError:
        errors.append(
            ValidationError(
                field_name,
                "URL hostname DNS resolution timed out. Verify the hostname is correct.",
            )
        )
    except socket.gaierror:
        errors.append(
            ValidationError(
                field_name,
                "URL hostname could not be resolved. Verify the hostname is correct.",
            )
        )


def _validate_knowledge_source_extra(spec: dict[str, Any], errors: list[ValidationError]) -> None:
    """Block path traversal in file_paths and SSRF in urls."""
    file_paths = spec.get("file_paths", [])
    if isinstance(file_paths, list):
        for i, fp in enumerate(file_paths):
            if isinstance(fp, str) and _is_path_traversal(fp):
                errors.append(
                    ValidationError(
                        f"spec.file_paths[{i}]",
                        f"Path '{fp}' is not allowed: must be a relative path without "
                        "traversal (no '..', absolute paths, or special characters).",
                    )
                )

    urls = spec.get("urls", [])
    if isinstance(urls, list):
        for i, url in enumerate(urls):
            if isinstance(url, str):
                _validate_url_ssrf(url, f"spec.urls[{i}]", errors)


# Shell metacharacters that must not appear in tool commands or args
_SHELL_METACHAR_PATTERN = re.compile(r"[;&|`$(){}!\n\r\\<>~#]")


ALLOWED_TOOL_MODULE_PREFIXES = (
    "crewai_tools.",
    "crewai.tools.",
    "langchain_community.tools.",
    "langchain.tools.",
)

BLOCKED_TOOL_SUBMODULES = (
    "langchain_community.tools.shell",
    "langchain_community.tools.python",
    "langchain_community.tools.file_management",
    "langchain_community.tools.requests_tool",
    "langchain_community.tools.sql_database",
    "langchain_community.tools.zapier",
    "langchain_community.tools.playwright",
    "langchain.tools.python_tool",
    "langchain.tools.shell_tool",
    "crewai_tools.code_interpreter_tool",
    "crewai_tools.code_docs_search_tool",
)


def _validate_tool_extra(spec: dict[str, Any], errors: list[ValidationError]) -> None:
    """Block SSRF in tool URL, env var exfiltration, shell injection, and dangerous imports."""
    class_path = spec.get("class_path")
    if class_path and isinstance(class_path, str) and spec.get("type", "python") == "python":
        if not class_path.startswith(ALLOWED_TOOL_MODULE_PREFIXES):
            errors.append(
                ValidationError(
                    "spec.class_path",
                    f"class_path '{class_path}' is not in the allowed module list. "
                    f"Permitted prefixes: {', '.join(ALLOWED_TOOL_MODULE_PREFIXES)}",
                )
            )
        elif "." in class_path:
            module_path = class_path.rsplit(".", 1)[0]
            for blocked in BLOCKED_TOOL_SUBMODULES:
                if module_path == blocked or module_path.startswith(blocked + "."):
                    errors.append(
                        ValidationError(
                            "spec.class_path",
                            f"class_path '{class_path}' references a blocked module "
                            f"that can execute arbitrary code.",
                        )
                    )
                    break

    url = spec.get("url")
    if url and isinstance(url, str):
        _validate_url_ssrf(url, "spec.url", errors)

    # Validate command field for mcp-stdio tools -- reject shell metacharacters
    command = spec.get("command")
    if command and isinstance(command, str):
        if _SHELL_METACHAR_PATTERN.search(command):
            errors.append(
                ValidationError(
                    "spec.command",
                    "Command must not contain shell metacharacters "
                    "(;, &, |, `, $, (), {}, <>, backslash, or newlines).",
                )
            )
        if ".." in command or command.startswith(("~", "/", "\\")):
            errors.append(
                ValidationError(
                    "spec.command",
                    "Command must be a simple executable name or relative path "
                    "without path traversal.",
                )
            )

    # Validate args for shell injection
    args = spec.get("args", [])
    if isinstance(args, list):
        for i, arg in enumerate(args):
            if isinstance(arg, str) and _SHELL_METACHAR_PATTERN.search(arg):
                errors.append(
                    ValidationError(
                        f"spec.args[{i}]",
                        "Argument must not contain shell metacharacters "
                        "(;, &, |, `, $, (), {}, <>, backslash, or newlines).",
                    )
                )

    config = spec.get("config")
    if isinstance(config, dict):
        for key, val in config.items():
            if isinstance(val, str):
                if val.startswith(("http://", "https://")):
                    _validate_url_ssrf(val, f"spec.config.{key}", errors)
                _check_value_injection(val, f"spec.config.{key}", "Config value", errors)
                if (
                    isinstance(key, str)
                    and key.lower() in _CREDENTIAL_CONFIG_KEYS
                    and _is_blocked_env_reference(val)
                ):
                    errors.append(
                        ValidationError(
                            f"spec.config.{key}",
                            "Cannot reference internal env variable in tool config.",
                        )
                    )

    env = spec.get("env")
    if isinstance(env, dict):
        for key, value in env.items():
            if isinstance(key, str) and is_blocked_env_name(key):
                errors.append(
                    ValidationError(
                        f"spec.env.{key}",
                        f"Cannot set environment variable '{key}'. "
                        "This variable is restricted for security reasons.",
                    )
                )
            if isinstance(value, str):
                _check_value_injection(
                    value, f"spec.env.{key}", "Environment variable value", errors
                )


# Allowlist for function_path in guardrails and flow steps.
# Prevents arbitrary code execution via dynamic imports.
ALLOWED_CALLABLE_MODULE_PREFIXES = (
    "crewai.",
    "crewai_tools.",
    "langchain.",
    "langchain_community.",
    "blackbeard.guardrails.",
    "blackbeard.flows.",
)

# Explicitly blocked modules -- dangerous even with prefix allowlist
BLOCKED_CALLABLE_MODULES = frozenset(
    {
        "os",
        "sys",
        "subprocess",
        "shutil",
        "importlib",
        "builtins",
        "ctypes",
        "code",
        "codeop",
        "compile",
        "pickle",  # arbitrary code execution via deserialization
        "shelve",  # uses pickle internally
        "marshal",  # unsafe deserialization
        "socket",  # arbitrary network access
        "multiprocessing",  # arbitrary process spawning
        "pty",  # pseudo-terminal access
        "signal",  # signal manipulation
        "runpy",  # run_module/run_path execute arbitrary code
        "ensurepip",  # can install arbitrary packages
        "pip",  # can install arbitrary packages
        "zipimport",  # import from arbitrary zip files
        "webbrowser",  # open arbitrary URLs
    }
)


def _validate_function_path(
    spec: dict[str, Any], field_name: str, errors: list[ValidationError]
) -> None:
    """Validate a function_path field against the module allowlist."""
    func_path = spec.get("function_path")
    if not func_path or not isinstance(func_path, str):
        return
    top_module = func_path.split(".")[0].split(":")[0]
    if top_module in BLOCKED_CALLABLE_MODULES:
        errors.append(
            ValidationError(
                field_name,
                f"Function path '{func_path}' references a blocked module '{top_module}'.",
            )
        )
        return
    if not func_path.startswith(ALLOWED_CALLABLE_MODULE_PREFIXES):
        errors.append(
            ValidationError(
                field_name,
                f"Function path '{func_path}' is not in the allowed module list. "
                f"Permitted prefixes: {', '.join(ALLOWED_CALLABLE_MODULE_PREFIXES)}",
            )
        )


def _validate_flow_extra(spec: dict[str, Any], errors: list[ValidationError]) -> None:
    """Validate function_path fields in flow steps."""
    steps = spec.get("steps", [])
    if not isinstance(steps, list):
        return
    for i, step in enumerate(steps):
        if isinstance(step, dict):
            _validate_function_path(step, f"spec.steps[{i}].function_path", errors)


def _check_value_injection(val: str, field: str, label: str, errors: list[ValidationError]) -> None:
    """Check a string value for command substitution and blocked env expansion."""
    if "`" in val or "$(" in val:
        errors.append(
            ValidationError(
                field,
                f"{label} must not contain command substitution (backticks or $(...)).",
            )
        )
    elif _has_blocked_env_expansion(val):
        errors.append(
            ValidationError(
                field,
                f"{label} must not reference internal variables via shell expansion.",
            )
        )


_CREDENTIAL_CONFIG_KEYS = frozenset(
    {"api_key", "api_secret", "secret", "password", "token", "credential"}
)


_INDIRECT_EXPANSION_RE = re.compile(r"\$\{!")

# Matches $VAR or ${VAR patterns and captures the variable name.
# Replaces a 150-alternation regex that enumerated every blocked prefix/name.
_ENV_VAR_RE = re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)")


def _has_blocked_env_expansion(val: str) -> bool:
    """Check if a string contains shell expansion ($VAR / ${VAR}) referencing blocked env vars."""
    if "$" not in val:
        return False
    if _INDIRECT_EXPANSION_RE.search(val):
        return True
    return any(is_blocked_env_name(match.group(1)) for match in _ENV_VAR_RE.finditer(val))


def _is_blocked_env_reference(val: str) -> bool:
    """Check if a config value references a blocked environment variable."""
    return is_blocked_env_name(val) or _has_blocked_env_expansion(val)


def _validate_crew_config_block(
    config: dict[str, Any], field_prefix: str, errors: list[ValidationError]
) -> None:
    """Validate a crew config block (embedder or memory) for SSRF and credential exfiltration."""
    for key, val in config.items():
        if isinstance(val, str) and val.startswith(("http://", "https://")):
            _validate_url_ssrf(val, f"{field_prefix}.{key}", errors)
        if (
            isinstance(key, str)
            and key.lower() in _CREDENTIAL_CONFIG_KEYS
            and isinstance(val, str)
            and _is_blocked_env_reference(val)
        ):
            errors.append(
                ValidationError(
                    f"{field_prefix}.{key}",
                    "Cannot reference internal env variable in config.",
                )
            )


def _validate_crew_extra(spec: dict[str, Any], errors: list[ValidationError]) -> None:
    """Block SSRF and env-var exfiltration in embedder and memory config."""
    embedder = spec.get("embedder")
    if isinstance(embedder, dict):
        config = embedder.get("config", {})
        if isinstance(config, dict):
            _validate_crew_config_block(config, "spec.embedder.config", errors)

    memory = spec.get("memory")
    if isinstance(memory, dict):
        config = memory.get("config", {})
        if isinstance(config, dict):
            _validate_crew_config_block(config, "spec.memory.config", errors)


def validate_resource(
    kind: str, spec: dict[str, Any]
) -> tuple[list[ValidationError], list[RefInfo] | None]:
    """Validate a resource spec against its JSON Schema.

    Returns (errors, refs) where refs is the list of extracted RefInfo objects
    (or None if ref extraction failed). Callers can reuse refs to avoid
    re-extracting them.
    """
    errors: list[ValidationError] = []
    refs = None

    validator = _VALIDATORS.get(kind)
    if validator is None:
        return [ValidationError(field="kind", message=f"Unknown kind: {kind}")], None

    for error in sorted(validator.iter_errors(spec), key=lambda e: tuple(e.path)):
        path = ".".join(str(p) for p in error.absolute_path) or "spec"
        errors.append(ValidationError(f"spec.{path}", error.message))

    try:
        refs = extract_refs(spec)
    except RefParseError as e:
        errors.append(ValidationError("spec", str(e)))

    if kind == "LLMConnection":
        _validate_llm_connection_extra(spec, errors)
    elif kind == "KnowledgeSource":
        _validate_knowledge_source_extra(spec, errors)
    elif kind == "Tool":
        _validate_tool_extra(spec, errors)
    elif kind == "Crew":
        _validate_crew_extra(spec, errors)
    elif kind == "Guardrail":
        _validate_function_path(spec, "spec.function_path", errors)
    elif kind == "Flow":
        _validate_flow_extra(spec, errors)

    return errors, refs
