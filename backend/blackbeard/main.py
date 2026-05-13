"""FastAPI application entry point."""

import logging
import os
import platform
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, cast

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import blackbeard.models.execution
import blackbeard.models.resource  # noqa: F401 — register Resource/ResourceRef tables
from blackbeard import __version__
from blackbeard.api.executions import router as executions_router
from blackbeard.api.health import router as health_router
from blackbeard.api.health import shutdown_health_clients
from blackbeard.api.middleware import (
    api_key_middleware,
    body_size_limiter,
    global_exception_handler,
    security_headers_middleware,
)
from blackbeard.api.resources import router as resources_router
from blackbeard.config import settings
from blackbeard.engine import shutdown_executor
from blackbeard.langfuse import shutdown_langfuse
from blackbeard.litellm import shutdown_key_manager
from blackbeard.logging_config import configure_logging
from blackbeard.models.database import engine

configure_logging(debug=settings.debug)
logger = logging.getLogger(__name__)

_LANGFUSE_INSECURE_DEFAULTS = {
    "LANGFUSE_NEXTAUTH_SECRET": "blackbeard-langfuse-secret",
    "LANGFUSE_SALT": "blackbeard-salt",
    "LANGFUSE_ENCRYPTION_KEY": "0" * 64,
}


def _validate_startup_config() -> None:
    """Validate security-critical configuration before accepting traffic."""
    api_key = settings.blackbeard_api_key.get_secret_value()
    if api_key == "change-me-in-production":
        if not settings.debug:
            raise RuntimeError(
                "Refusing to start: BLACKBEARD_API_KEY is set to the insecure default. "
                "Set a strong random value via environment variable, "
                "or set DEBUG=true for local development."
            )
        logger.warning("SECURITY: Using default API key — set BLACKBEARD_API_KEY for production")
    elif len(api_key) < 16:
        raise RuntimeError(
            "Refusing to start: BLACKBEARD_API_KEY is too short (minimum 16 characters). "
            'Generate a strong key with: python -c "import secrets; '
            'print(secrets.token_urlsafe(32))"'
        )
    if settings.litellm_master_key.get_secret_value() == "sk-litellm-master-key":
        if not settings.debug:
            raise RuntimeError(
                "Refusing to start: LITELLM_MASTER_KEY is set to the insecure default. "
                "Set a strong random value via environment variable, "
                "or set DEBUG=true for local development."
            )
        logger.warning("SECURITY: Using default LiteLLM master key — set LITELLM_MASTER_KEY")
    if "*" in settings.cors_origins and not settings.debug:
        raise RuntimeError(
            "Refusing to start: CORS_ORIGINS contains wildcard '*'. "
            "Set explicit origins for production, or set DEBUG=true for local development."
        )
    for env_name, insecure_val in _LANGFUSE_INSECURE_DEFAULTS.items():
        if os.environ.get(env_name) == insecure_val and not settings.debug:
            logger.warning(
                "SECURITY: %s is set to an insecure default — "
                "generate a strong value with: openssl rand -hex 32",
                env_name,
            )
    if not settings.litellm_proxy_url.startswith(("http://", "https://")):
        url = settings.litellm_proxy_url
        raise RuntimeError(
            f"Refusing to start: LITELLM_PROXY_URL has unexpected scheme: {url!r}. "
            "Must start with http:// or https://."
        )
    if settings.langfuse_host and not settings.langfuse_host.startswith(("http://", "https://")):
        host = settings.langfuse_host
        raise RuntimeError(
            f"Refusing to start: LANGFUSE_HOST has unexpected scheme: {host!r}. "
            "Must start with http:// or https://."
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan: startup and shutdown."""
    _validate_startup_config()
    pool = cast("Any", engine.pool)
    logger.info(
        "Blackbeard %s starting: debug=%s, max_concurrent_executions=%d, litellm=%s, langfuse=%s",
        app.version,
        settings.debug,
        settings.max_concurrent_executions,
        settings.litellm_proxy_url,
        "enabled" if settings.langfuse_public_key else "disabled",
        extra={
            "event": "app_startup",
            "version": app.version,
            "python_version": platform.python_version(),
            "pid": os.getpid(),
            "debug": settings.debug,
            "max_concurrent_executions": settings.max_concurrent_executions,
            "litellm_url": settings.litellm_proxy_url,
            "langfuse_enabled": bool(settings.langfuse_public_key),
            "db_pool_size": pool.size(),
            "db_pool_max_overflow": pool.overflow(),
            "db_pool_timeout": pool.timeout(),
        },
    )
    yield
    # Order matters: executor first (may emit Langfuse events), then Langfuse, then connections
    logger.info("Shutdown starting", extra={"event": "app_shutdown_start"})
    try:
        shutdown_executor()
        logger.info("Executor shut down", extra={"event": "executor_shutdown_complete"})
    finally:
        try:
            shutdown_langfuse()
            logger.info("Langfuse shut down", extra={"event": "langfuse_shutdown_complete"})
        finally:
            try:
                await shutdown_key_manager()
                logger.info(
                    "Key manager shut down",
                    extra={"event": "key_manager_shutdown_complete"},
                )
            finally:
                try:
                    await shutdown_health_clients()
                    logger.info(
                        "Health clients closed",
                        extra={"event": "health_clients_shutdown_complete"},
                    )
                finally:
                    await engine.dispose()
                    logger.info(
                        "Database connections closed",
                        extra={"event": "database_shutdown_complete"},
                    )


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description="Open, self-hosted Agent Management Platform",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,  # Swagger UI — debug only
    redoc_url="/redoc" if settings.debug else None,  # ReDoc — debug only
    openapi_url="/openapi.json" if settings.debug else None,  # OpenAPI spec — debug only
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key", "Authorization", "X-Request-Id"],
    expose_headers=["X-Request-Id"],
)

# Middleware stack (LIFO order — last registered runs first):
#   1. security_headers — always runs, adds headers to every response
#   2. api_key_middleware — authenticate, set request ID
#   3. body_size_limiter — reject oversized bodies (innermost)
app.middleware("http")(body_size_limiter)
app.middleware("http")(api_key_middleware)
app.middleware("http")(security_headers_middleware)

app.add_exception_handler(Exception, global_exception_handler)

# Routers
app.include_router(health_router, prefix="/api/v1")
app.include_router(executions_router, prefix="/api/v1")
app.include_router(resources_router, prefix="/api/v1")
