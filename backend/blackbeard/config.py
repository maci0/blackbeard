"""Application configuration via environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Blackbeard application settings.

    All values can be overridden via environment variables.
    """

    # App
    app_name: str = "Blackbeard"
    debug: bool = False

    # Auth
    blackbeard_api_key: str = "change-me-in-production"

    # Database
    database_url: str = "postgresql+asyncpg://blackbeard:blackbeard@localhost:5432/blackbeard"

    # Valkey (Redis-compatible cache)
    valkey_url: str = "valkey://default:valkey-dev-secret@localhost:6379/0"

    # LiteLLM Proxy
    litellm_proxy_url: str = "http://localhost:4000"
    litellm_master_key: str = "sk-litellm-master-key"

    # Langfuse
    langfuse_host: str = "http://localhost:3001"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""

    # GCP / Vertex AI (from crew project credentials)
    google_cloud_project: str = ""
    cloud_ml_region: str = "us-east5"
    google_application_credentials: str = ""

    # Execution
    max_concurrent_executions: int = 4

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    model_config = {"env_prefix": "", "case_sensitive": False}


settings = Settings()
