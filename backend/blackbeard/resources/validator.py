"""Resource validation: JSON Schema + ref format validation."""

import ipaddress
from typing import Any
from urllib.parse import urlparse

import jsonschema

from blackbeard.resources.refs import RefInfo, RefParseError, extract_refs
from blackbeard.resources.spec_schemas import KIND_SCHEMAS

# Pre-compile validators for each kind (schemas never change at runtime)
_VALIDATORS: dict[str, jsonschema.Draft7Validator] = {
    kind: jsonschema.Draft7Validator(schema) for kind, schema in KIND_SCHEMAS.items()
}

# Environment variable prefixes that must not be referenced via api_key_env
# to prevent exfiltration of internal secrets through LiteLLM config.
_BLOCKED_ENV_PREFIXES = (
    "BLACKBEARD_",
    "LITELLM_",
    "LANGFUSE_",
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
)

_INTERNAL_HOSTNAMES = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "host.docker.internal",
        "gateway.docker.internal",
        "metadata.google.internal",
        "metadata.goog",
        "metadata",
        "kubernetes.default.svc",
        "169.254.169.254",
    }
)

_INTERNAL_DOMAIN_SUFFIXES = (
    ".internal",
    ".local",
    ".svc",
    ".svc.cluster.local",
    ".docker.internal",
)


class ValidationError:
    """A single validation error."""

    __slots__ = ("field", "message")

    def __init__(self, field: str, message: str) -> None:
        self.field = field
        self.message = message

    def __repr__(self) -> str:
        return f"ValidationError({self.field}: {self.message})"

    def to_dict(self) -> dict[str, str]:
        return {"field": self.field, "message": self.message}


def _is_internal_host(hostname: str) -> bool:
    hostname_lower = hostname.lower()
    if hostname_lower in _INTERNAL_HOSTNAMES:
        return True
    if any(hostname_lower.endswith(s) for s in _INTERNAL_DOMAIN_SUFFIXES):
        return True
    try:
        addr = ipaddress.ip_address(hostname_lower)
        if (
            addr.is_private
            or addr.is_reserved
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_unspecified
        ):
            return True
        if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
            m = addr.ipv4_mapped
            if (
                m.is_private
                or m.is_reserved
                or m.is_loopback
                or m.is_link_local
                or m.is_unspecified
            ):
                return True
        return False
    except ValueError:
        return False


def _validate_llm_connection_extra(spec: dict[str, Any], errors: list[ValidationError]) -> None:
    """Block SSRF via base_url and env var exfiltration via api_key_env."""
    api_key_env = spec.get("api_key_env")
    if isinstance(api_key_env, str) and api_key_env.startswith(_BLOCKED_ENV_PREFIXES):
        errors.append(
            ValidationError(
                "spec.api_key_env",
                f"Cannot reference internal environment variable '{api_key_env}'. "
                "Use a dedicated variable for external API keys.",
            )
        )

    base_url = spec.get("base_url")
    if base_url and isinstance(base_url, str):
        try:
            parsed = urlparse(base_url)
            if parsed.scheme not in ("http", "https"):
                errors.append(
                    ValidationError(
                        "spec.base_url",
                        "base_url must use http or https scheme.",
                    )
                )
            elif parsed.username or parsed.password:
                errors.append(
                    ValidationError(
                        "spec.base_url",
                        "base_url must not contain embedded credentials.",
                    )
                )
            else:
                hostname = parsed.hostname or ""
                if _is_internal_host(hostname):
                    errors.append(
                        ValidationError(
                            "spec.base_url",
                            "base_url must not point to internal or private network addresses.",
                        )
                    )
        except Exception:
            errors.append(
                ValidationError(
                    "spec.base_url",
                    "base_url could not be parsed for SSRF validation.",
                )
            )


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

    # Check kind is known
    validator = _VALIDATORS.get(kind)
    if validator is None:
        return [ValidationError(field="kind", message=f"Unknown kind: {kind}")], None

    # JSON Schema validation
    for error in sorted(validator.iter_errors(spec), key=lambda e: tuple(e.path)):
        path = ".".join(str(p) for p in error.absolute_path) or "spec"
        errors.append(ValidationError(f"spec.{path}", error.message))

    # Validate ref format
    try:
        refs = extract_refs(spec)
    except RefParseError as e:
        errors.append(ValidationError("spec", str(e)))

    if kind == "LLMConnection":
        _validate_llm_connection_extra(spec, errors)

    return errors, refs
