"""Application configuration via environment variables."""

from __future__ import annotations

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = [
    "Settings",
    "settings",
]


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

    # Optional — used for model info enrichment in /models/test
    ollama_url: str = "http://host.docker.internal:11434"

    google_cloud_project: str = ""
    cloud_ml_region: str = "us-east5"
    google_application_credentials: str = ""

    jwt_secret: SecretStr = SecretStr("change-jwt-secret-in-production")
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7

    otel_endpoint: str | None = None

    # Container sandbox settings
    container_runtime: str = "auto"  # "docker", "podman", or "auto"
    container_default_image: str = "python:3.13-slim"
    container_timeout: int = 30
    container_memory_limit: str = "256m"

    # gVisor sandbox settings
    gvisor_enabled: bool = False

    # MicroVM sandbox settings (requires crun-krun + /dev/kvm)
    microvm_enabled: bool = True

    # MuninnDB cognitive memory settings
    muninndb_url: str = "http://localhost:8475"

    max_concurrent_executions: int = 4

    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)


settings = Settings()
