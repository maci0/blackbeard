"""Application configuration via environment variables."""

from __future__ import annotations

import re

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = [
    "Settings",
    "settings",
]


_MEMORY_LIMIT_RE = re.compile(r"^\d+[bkmg]$", re.IGNORECASE)


class Settings(BaseSettings):
    """Blackbeard application settings.

    All values can be overridden via environment variables.
    Sensitive fields use SecretStr to prevent accidental exposure in logs/repr.
    """

    app_name: str = "Blackbeard"
    debug: bool = False
    log_level: str = ""

    blackbeard_api_key: SecretStr = SecretStr("change-me-in-production")

    database_url: SecretStr = SecretStr(
        "postgresql+asyncpg://blackbeard:blackbeard@localhost:5432/blackbeard"
    )

    valkey_url: SecretStr = SecretStr("valkey://default:valkey-dev-secret@localhost:6379/0")

    litellm_proxy_url: str = "http://localhost:4000"
    litellm_master_key: SecretStr = SecretStr("sk-litellm-master-key")

    google_cloud_project: str = ""
    cloud_ml_region: str = "us-east5"
    google_application_credentials: str = ""

    jwt_secret: SecretStr = SecretStr("change-jwt-secret-in-production!")
    jwt_access_token_expire_minutes: int = Field(default=15, ge=1)
    jwt_refresh_token_expire_days: int = Field(default=7, ge=1)

    enforce_rbac: bool = False

    otel_endpoint: str | None = None

    # OIDC / SSO (any provider: Google, Azure AD, Okta, Keycloak, Authentik, etc.)
    oidc_issuer: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: SecretStr | None = None
    oidc_redirect_uri: str | None = None
    oidc_scopes: str = "openid email profile"

    # Container sandbox settings
    container_runtime: str = "auto"  # "docker", "podman", or "auto"
    container_default_image: str = "python:3.13-slim"
    container_timeout: int = Field(default=30, ge=1)
    container_memory_limit: str = "256m"

    # gVisor sandbox settings
    gvisor_enabled: bool = False

    # MicroVM sandbox settings (requires crun-krun + /dev/kvm)
    microvm_enabled: bool = False

    # Firecracker MicroVM settings (alternative to libkrun for microvm tier)
    # Requires: firecracker binary, kernel image, rootfs image, /dev/kvm
    firecracker_bin: str = "firecracker"
    firecracker_kernel: str = ""
    firecracker_rootfs: str = ""

    # MuninnDB cognitive memory settings
    muninndb_url: str = "http://localhost:8475"

    db_pool_size: int = Field(default=10, ge=1)
    db_pool_max_overflow: int = Field(default=20, ge=0)
    db_pool_timeout: int = Field(default=30, ge=1)
    db_pool_recycle: int = Field(default=3600, ge=60)

    max_concurrent_executions: int = Field(default=4, ge=1)
    max_concurrent_sse: int = Field(default=20, ge=1)

    auth_fail_window_seconds: int = Field(default=300, ge=1)
    auth_fail_max_per_ip: int = Field(default=20, ge=1)
    auth_fail_max_tracked_ips: int = Field(default=200, ge=1)

    host: str = "0.0.0.0"  # nosec B104 -- intentional-for-containerized-deployment
    port: int = Field(default=8000, ge=1, le=65535)
    grpc_port: int = Field(default=50051, ge=1, le=65535)
    web_concurrency: int = Field(default=1, ge=1)
    forwarded_allow_ips: str = "127.0.0.1"
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, v: str) -> str:
        if v and v.upper() not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            raise ValueError(
                f"Invalid log_level {v!r}. "
                "Must be one of: DEBUG, INFO, WARNING, ERROR, CRITICAL (or empty for default)"
            )
        return v.upper() if v else v

    @field_validator("database_url")
    @classmethod
    def _validate_database_url(cls, v: SecretStr) -> SecretStr:
        url = v.get_secret_value()
        if not url.startswith("postgresql+asyncpg://"):
            raise ValueError(
                f"DATABASE_URL must use the 'postgresql+asyncpg://' scheme "
                f"(got {url.split('://')[0] + '://' if '://' in url else url!r}). "
                f"Example: postgresql+asyncpg://user:pass@host:5432/dbname"
            )
        return v

    @field_validator("container_runtime")
    @classmethod
    def _validate_container_runtime(cls, v: str) -> str:
        allowed = ("auto", "docker", "podman")
        if v not in allowed:
            raise ValueError(
                f"Invalid container_runtime {v!r}. Must be one of: {', '.join(allowed)}"
            )
        return v

    @field_validator("container_memory_limit")
    @classmethod
    def _validate_container_memory_limit(cls, v: str) -> str:
        if not _MEMORY_LIMIT_RE.match(v):
            raise ValueError(
                f"Invalid container_memory_limit {v!r}. "
                "Must be a number followed by a unit: b, k, m, or g (e.g. '256m', '1g')"
            )
        return v

    @field_validator("valkey_url")
    @classmethod
    def _validate_valkey_url(cls, v: SecretStr) -> SecretStr:
        url = v.get_secret_value()
        if not url.startswith(("valkey://", "redis://", "rediss://")):
            raise ValueError(
                f"VALKEY_URL must use 'valkey://', 'redis://', or 'rediss://' scheme "
                f"(got {url.split('://')[0] + '://' if '://' in url else url!r})"
            )
        return v

    @field_validator("otel_endpoint", "muninndb_url", "litellm_proxy_url")
    @classmethod
    def _validate_http_url(cls, v: str | None) -> str | None:
        if v is not None and not v.startswith(("http://", "https://")):
            raise ValueError(f"URL must start with http:// or https:// (got {v!r})")
        return v

    @field_validator("cors_origins")
    @classmethod
    def _validate_cors_origins(cls, v: list[str]) -> list[str]:
        for origin in v:
            if origin == "*":
                continue
            if not origin.startswith(("http://", "https://")):
                raise ValueError(f"CORS origin {origin!r} must start with http:// or https://")
            if origin.endswith("/"):
                raise ValueError(
                    f"CORS origin {origin!r} must not end with a trailing slash "
                    "(browsers strip it during CORS checks)"
                )
        return v

    @field_validator("oidc_redirect_uri")
    @classmethod
    def _validate_oidc_redirect_uri(cls, v: str | None) -> str | None:
        if v is not None and not v.startswith(("http://", "https://")):
            raise ValueError(f"OIDC_REDIRECT_URI must start with http:// or https:// (got {v!r})")
        return v

    @model_validator(mode="after")
    def _check_production_secrets(self) -> Settings:
        """Reject insecure default secrets in production (debug=False)."""
        if self.debug:
            return self
        insecure_defaults = {
            "blackbeard_api_key": "change-me-in-production",
            "jwt_secret": "change-jwt-secret-in-production!",
        }
        for field_name, insecure_value in insecure_defaults.items():
            secret: SecretStr = getattr(self, field_name)
            if secret.get_secret_value() == insecure_value:
                raise ValueError(
                    f"{field_name.upper()} is set to the insecure default. "
                    f"Set a strong, unique value via environment variable before running "
                    f"in production (DEBUG=false)."
                )
        if "*" in self.cors_origins:
            raise ValueError(
                "CORS_ORIGINS contains wildcard '*' which is not allowed in production "
                "(DEBUG=false). Set explicit origins instead."
            )
        return self

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)


settings = Settings()
