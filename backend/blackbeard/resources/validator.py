"""Resource validation: JSON Schema + ref format validation."""

from __future__ import annotations

import concurrent.futures
import ipaddress
import re
import socket
import threading
from typing import Any
from urllib.parse import urlparse

import jsonschema

from blackbeard.resources.exceptions import ValidationError
from blackbeard.resources.refs import RefInfo, RefParseError, extract_refs
from blackbeard.resources.spec_schemas import KIND_SCHEMAS

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
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "HUGGING_FACE_HUB_TOKEN",
        "HF_TOKEN",
        "WANDB_API_KEY",
        "COHERE_API_KEY",
        "REPLICATE_API_TOKEN",
        "SENDGRID_API_KEY",
        "STRIPE_SECRET_KEY",
        "TWILIO_AUTH_TOKEN",
        "SLACK_TOKEN",
        "SLACK_BOT_TOKEN",
        "DISCORD_TOKEN",
        "NPM_TOKEN",
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
    ".local",
    ".svc",
    ".svc.cluster.local",
)

_SHARED_ADDRESS_SPACE = ipaddress.IPv4Network("100.64.0.0/10")


def _is_nonroutable(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        addr.is_private
        or addr.is_reserved
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_unspecified
        or (isinstance(addr, ipaddress.IPv4Address) and addr in _SHARED_ADDRESS_SPACE)
    )


def _is_internal_ip(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if _is_nonroutable(addr):
        return True
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        return _is_nonroutable(addr.ipv4_mapped)
    return False


def _is_internal_host(hostname: str) -> bool:
    hostname_lower = hostname.lower().rstrip(".")
    if hostname_lower in _INTERNAL_HOSTNAMES:
        return True
    if any(hostname_lower.endswith(s) for s in _INTERNAL_DOMAIN_SUFFIXES):
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
    if isinstance(api_key_env, str):
        upper = api_key_env.upper()
        if upper.startswith(_BLOCKED_ENV_PREFIXES) or upper in _BLOCKED_ENV_EXACT:
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


def _is_path_traversal(path: str) -> bool:
    """Check if a file path contains traversal or escapes the working directory."""
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
    blocking the async event loop. This is acceptable because validation
    runs infrequently (resource create/update) and the timeout caps worst-case
    latency.
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            errors.append(ValidationError(field_name, "URL must use http or https scheme."))
        elif parsed.username or parsed.password:
            errors.append(ValidationError(field_name, "URL must not contain embedded credentials."))
        else:
            hostname = parsed.hostname or ""
            if _is_internal_host(hostname):
                errors.append(
                    ValidationError(
                        field_name,
                        "URL must not point to internal or private network addresses.",
                    )
                )
            else:
                _check_dns_resolution(hostname, field_name, errors)
    except Exception:
        errors.append(ValidationError(field_name, "URL could not be parsed for SSRF validation."))


_DNS_EXECUTOR: concurrent.futures.ThreadPoolExecutor | None = None
_DNS_EXECUTOR_LOCK = threading.Lock()


def _get_dns_executor() -> concurrent.futures.ThreadPoolExecutor:
    """Return a shared single-thread executor for DNS resolution."""
    global _DNS_EXECUTOR
    if _DNS_EXECUTOR is not None:
        return _DNS_EXECUTOR
    with _DNS_EXECUTOR_LOCK:
        if _DNS_EXECUTOR is not None:
            return _DNS_EXECUTOR
        _DNS_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="dns-resolve"
        )
        return _DNS_EXECUTOR


def _check_dns_resolution(
    hostname: str, field_name: str, errors: list[ValidationError]
) -> None:
    """Resolve hostname via DNS and reject if any address is internal.

    Runs in a thread with a timeout to avoid blocking the async event loop
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
        # DNS took too long — allow through; runtime request will handle failure.
        pass
    except socket.gaierror:
        # DNS resolution failed — hostname doesn't exist.
        # Allow it through: the actual HTTP request will fail at runtime,
        # and blocking here would reject valid hostnames during DNS outages.
        pass


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
_SHELL_METACHAR_PATTERN = re.compile(r"[;&|`$(){}!\n\r\\]")


def _validate_tool_extra(spec: dict[str, Any], errors: list[ValidationError]) -> None:
    """Block SSRF in tool URL, env var exfiltration, and shell injection in commands."""
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
                    "(;, &, |, `, $, parentheses, braces, backslash, or newlines).",
                )
            )
        if ".." in command or command.startswith(("~", "/")):
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
                        "(;, &, |, `, $, parentheses, braces, backslash, or newlines).",
                    )
                )

    env = spec.get("env")
    if isinstance(env, dict):
        for key, value in env.items():
            if isinstance(key, str) and (
                key.upper().startswith(_BLOCKED_ENV_PREFIXES) or key.upper() in _BLOCKED_ENV_EXACT
            ):
                errors.append(
                    ValidationError(
                        f"spec.env.{key}",
                        f"Cannot set environment variable '{key}'. "
                        "This variable is restricted for security reasons.",
                    )
                )
            if isinstance(value, str):
                if "`" in value or "$(" in value:
                    errors.append(
                        ValidationError(
                            f"spec.env.{key}",
                            "Environment variable value must not contain "
                            "command substitution (backticks or $(...)).",
                        )
                    )
                elif "$" in value:
                    blocked = False
                    upper_value = value.upper()
                    for prefix in _BLOCKED_ENV_PREFIXES:
                        if f"${prefix}" in upper_value or f"${{{prefix}" in upper_value:
                            blocked = True
                            break
                    if not blocked:
                        for exact in _BLOCKED_ENV_EXACT:
                            if f"${exact}" in upper_value or f"${{{exact}}}" in upper_value:
                                blocked = True
                                break
                    if blocked:
                        errors.append(
                            ValidationError(
                                f"spec.env.{key}",
                                "Environment variable value must not reference "
                                "internal variables via shell expansion.",
                            )
                        )


# Allowlist for function_path in guardrails and flow steps.
# Prevents arbitrary code execution via dynamic imports.
_ALLOWED_FUNCTION_MODULE_PREFIXES = (
    "crewai.",
    "crewai_tools.",
    "langchain.",
    "langchain_community.",
    "blackbeard.guardrails.",
    "blackbeard.flows.",
)

# Explicitly blocked modules -- dangerous even with prefix allowlist
_BLOCKED_FUNCTION_MODULES = frozenset(
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
    }
)


def _validate_function_path(
    spec: dict[str, Any], field_name: str, errors: list[ValidationError]
) -> None:
    """Validate a function_path field against the allowed module allowlist."""
    func_path = spec.get("function_path")
    if not func_path or not isinstance(func_path, str):
        return
    # Check for blocked top-level modules
    top_module = func_path.split(".")[0].split(":")[0]
    if top_module in _BLOCKED_FUNCTION_MODULES:
        errors.append(
            ValidationError(
                field_name,
                f"Function path '{func_path}' references a blocked module '{top_module}'.",
            )
        )
        return
    if not any(func_path.startswith(p) for p in _ALLOWED_FUNCTION_MODULE_PREFIXES):
        errors.append(
            ValidationError(
                field_name,
                f"Function path '{func_path}' is not in the allowed module list. "
                f"Permitted prefixes: {', '.join(_ALLOWED_FUNCTION_MODULE_PREFIXES)}",
            )
        )


def _validate_flow_extra(spec: dict[str, Any], errors: list[ValidationError]) -> None:
    """Validate function_path fields in flow steps."""
    steps = spec.get("steps", [])
    if not isinstance(steps, list):
        return
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        func_path = step.get("function_path")
        if func_path and isinstance(func_path, str):
            _validate_function_path(step, f"spec.steps[{i}].function_path", errors)


def _validate_crew_extra(spec: dict[str, Any], errors: list[ValidationError]) -> None:
    """Block SSRF and env-var exfiltration in embedder and memory config."""
    embedder = spec.get("embedder")
    if isinstance(embedder, dict):
        config = embedder.get("config", {})
        if isinstance(config, dict):
            for key, val in config.items():
                if isinstance(val, str) and val.startswith(("http://", "https://")):
                    _validate_url_ssrf(val, f"spec.embedder.config.{key}", errors)
                # Block api_key / credential exfiltration via embedder config
                if (
                    isinstance(key, str)
                    and key.lower()
                    in ("api_key", "api_secret", "secret", "password", "token", "credential")
                    and isinstance(val, str)
                    and val.upper().startswith(_BLOCKED_ENV_PREFIXES)
                ):
                    errors.append(
                        ValidationError(
                            f"spec.embedder.config.{key}",
                            "Cannot reference internal env variable in embedder config.",
                        )
                    )

    memory = spec.get("memory")
    if isinstance(memory, dict):
        config = memory.get("config", {})
        if isinstance(config, dict):
            for key, val in config.items():
                if isinstance(val, str) and val.startswith(("http://", "https://")):
                    _validate_url_ssrf(val, f"spec.memory.config.{key}", errors)


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
