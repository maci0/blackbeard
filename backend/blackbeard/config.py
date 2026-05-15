"""Application configuration via environment variables."""

from __future__ import annotations

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Canonical API version string — used by resource schemas and response serializers.
# Must stay in sync with frontend/src/lib/kinds.ts and frontend/src/pages/Studio.tsx.
API_VERSION = "blackbeard/v1"


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

    max_concurrent_executions: int = 4

    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)


settings = Settings()
