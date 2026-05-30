"""FastAPI application entry point."""

from __future__ import annotations

import logging
import os
import platform
import secrets
import time
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from blackbeard import __version__
from blackbeard.api.a2a import router as a2a_router
from blackbeard.api.agency_import import router as agency_import_router
from blackbeard.api.assistant import router as assistant_router
from blackbeard.api.audit import router as audit_router
from blackbeard.api.auth import router as auth_router
from blackbeard.api.automations import router as automations_router
from blackbeard.api.chat import router as chat_router
from blackbeard.api.collaboration import router as collaboration_router
from blackbeard.api.credentials import router as credentials_router
from blackbeard.api.executions import router as executions_router
from blackbeard.api.health import router as health_router
from blackbeard.api.health import shutdown_health_clients
from blackbeard.api.marketplace import router as marketplace_router
from blackbeard.api.middleware import (
    api_key_middleware,
    body_size_limiter,
    global_exception_handler,
    http_exception_handler,
    security_headers_middleware,
    validation_exception_handler,
)
from blackbeard.api.resources import router as resources_router
from blackbeard.api.users import router as users_router
from blackbeard.api.webhooks import router as webhooks_router
from blackbeard.auth.api_key import set_api_key
from blackbeard.config import settings
from blackbeard.engine import recover_stale_executions, shutdown_executor
from blackbeard.engine.execution_listener import shutdown_otel, shutdown_webhook_executor
from blackbeard.http_client import close_all_clients
from blackbeard.logging_config import configure_logging
from blackbeard.models import Resource
from blackbeard.models.database import async_session, engine

configure_logging(debug=settings.debug, log_level=settings.log_level)
logger = logging.getLogger(__name__)


_MIN_SECRET_LENGTH = 16


def _validate_startup_config() -> None:
    """Validate security-critical configuration before accepting traffic."""

    def _fatal(reason: str) -> RuntimeError:
        logger.critical(
            "Startup blocked: %s",
            reason,
            extra={"event": "startup_validation_failed", "reason": reason},
        )
        return RuntimeError(reason)

    api_key = settings.blackbeard_api_key.get_secret_value()
    if api_key == "change-me-in-production":
        if not settings.debug:
            raise _fatal(
                "Refusing to start: BLACKBEARD_API_KEY is set to the insecure default. "
                "Set a strong random value via environment variable, "
                "or set DEBUG=true for local development."
            )
        generated = secrets.token_urlsafe(32)
        set_api_key(generated)
        logger.warning(
            "SECURITY: No API key configured — generated ephemeral key for this session: ...%s",
            generated[-8:],
            extra={"event": "ephemeral_api_key_generated"},
        )
        import sys

        print(  # noqa: T201
            f"Ephemeral API key (stderr only): {generated}",
            file=sys.stderr,
            flush=True,
        )
    elif len(api_key) < _MIN_SECRET_LENGTH:
        raise _fatal(
            f"Refusing to start: BLACKBEARD_API_KEY is too short "
            f"(minimum {_MIN_SECRET_LENGTH} characters). "
            'Generate a strong key with: python -c "import secrets; '
            'print(secrets.token_urlsafe(32))"'
        )

    def _check_secret(
        value: str,
        env_var: str,
        defaults: tuple[str, ...],
        event: str,
        warn_msg: str,
    ) -> None:
        if value in defaults:
            if not settings.debug:
                raise _fatal(
                    f"Refusing to start: {env_var} is set to the insecure default. "
                    "Set a strong random value via environment variable, "
                    "or set DEBUG=true for local development."
                )
            logger.warning(warn_msg, extra={"event": event})
        elif len(value) < _MIN_SECRET_LENGTH:
            raise _fatal(
                f"Refusing to start: {env_var} is too short "
                f"(minimum {_MIN_SECRET_LENGTH} characters). "
                'Generate a strong key with: python -c "import secrets; '
                'print(secrets.token_urlsafe(32))"'
            )

    _check_secret(
        settings.jwt_secret.get_secret_value(),
        "JWT_SECRET",
        ("change-jwt-secret-in-production!", "change-jwt-secret-in-production"),
        "insecure_default_jwt_secret",
        "SECURITY: Using default JWT secret — set JWT_SECRET",
    )
    _check_secret(
        settings.litellm_master_key.get_secret_value(),
        "LITELLM_MASTER_KEY",
        ("sk-litellm-master-key",),
        "insecure_default_litellm_key",
        "SECURITY: Using default LiteLLM master key — set LITELLM_MASTER_KEY",
    )
    if "*" in settings.cors_origins and not settings.debug:
        raise _fatal(
            "Refusing to start: CORS_ORIGINS contains wildcard '*'. "
            "Set explicit origins for production, or set DEBUG=true for local development."
        )
    if not settings.debug:
        for origin in settings.cors_origins:
            if not origin.startswith("https://"):
                raise _fatal(
                    f"Refusing to start: CORS origin '{origin}' must use https:// in production. "
                    "Set DEBUG=true for local development with http origins."
                )
    if not settings.litellm_proxy_url.startswith(("http://", "https://")):
        raise _fatal(
            f"Refusing to start: LITELLM_PROXY_URL has unexpected scheme: "
            f"{settings.litellm_proxy_url!r}. Must start with http:// or https://."
        )
    if settings.oidc_issuer and not settings.debug:
        if not settings.oidc_client_secret:
            raise _fatal(
                "Refusing to start: OIDC_ISSUER is set but OIDC_CLIENT_SECRET is missing. "
                "Set OIDC_CLIENT_SECRET for confidential client flow, "
                "or set DEBUG=true for local development."
            )
        if not settings.oidc_client_id:
            raise _fatal("Refusing to start: OIDC_ISSUER is set but OIDC_CLIENT_ID is missing.")
        if not settings.oidc_redirect_uri:
            raise _fatal(
                "Refusing to start: OIDC_ISSUER is set but OIDC_REDIRECT_URI is missing. "
                "Set OIDC_REDIRECT_URI to the callback URL "
                "(e.g. https://your-domain/api/v1/auth/oidc/callback)."
            )
        if not settings.oidc_redirect_uri.startswith("https://"):
            raise _fatal(
                "Refusing to start: OIDC_REDIRECT_URI must use https:// in production "
                "(got http://). Set DEBUG=true for local development with http."
            )
    if not settings.enforce_rbac and not settings.debug:
        logger.warning(
            "SECURITY: ENFORCE_RBAC is False — all authenticated users have full access. "
            "Set ENFORCE_RBAC=true and configure Role/RoleBinding resources for production.",
            extra={"event": "rbac_disabled_in_production"},
        )
    if settings.forwarded_allow_ips == "*" and not settings.debug:
        logger.warning(
            "SECURITY: FORWARDED_ALLOW_IPS='*' trusts X-Forwarded-For from any source. "
            "Set to your reverse proxy's IP to prevent IP spoofing.",
            extra={"event": "insecure_forwarded_allow_ips"},
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan: config validation, scheduler, LiteLLM sync, gRPC, cleanup."""
    t0_startup = time.monotonic()
    _validate_startup_config()
    pool = cast("Any", engine.pool)
    try:
        from crewai import __version__ as crewai_version
    except (ImportError, AttributeError):
        crewai_version = "unknown"
    logger.info(
        "Blackbeard %s starting: debug=%s host=%s:%d crewai=%s",
        app.version,
        settings.debug,
        settings.host,
        settings.port,
        crewai_version,
        extra={
            "event": "app_startup",
            "version": app.version,
            "crewai_version": crewai_version,
            "python_version": platform.python_version(),
            "pid": os.getpid(),
            "debug": settings.debug,
            "log_level": settings.log_level or ("DEBUG" if settings.debug else "INFO"),
            "host": settings.host,
            "port": settings.port,
            "max_concurrent_executions": settings.max_concurrent_executions,
            "litellm_url": settings.litellm_proxy_url,
            "cors_origin_count": len(settings.cors_origins),
            "db_pool_size": pool.size(),
            "db_pool_max_overflow": pool.overflow(),
            "db_pool_timeout": pool.timeout(),
            "oidc_enabled": bool(settings.oidc_issuer),
            "otel_configured": bool(settings.otel_endpoint),
            "valkey_configured": bool(settings.valkey_url.get_secret_value()),
        },
    )
    recovered = await recover_stale_executions()

    from blackbeard.engine.scheduler import AutomationScheduler

    scheduler = AutomationScheduler()
    try:
        await scheduler.start()
    except Exception:
        logger.warning(
            "Automation scheduler failed to start — cron automations disabled until restart",
            exc_info=True,
            extra={"event": "scheduler_start_failed"},
        )
    # Store on app.state so resource CRUD can trigger reload on Automation changes.
    app.state.scheduler = scheduler

    # Sync LLMConnection resources to LiteLLM proxy
    try:
        from blackbeard.litellm import model_sync

        async with async_session() as sync_session:
            from blackbeard.kinds import ResourceKind

            result = await sync_session.execute(
                select(Resource.name, Resource.spec).where(
                    Resource.kind == ResourceKind.LLM_CONNECTION
                )
            )
            connections = [{"name": r.name, "spec": r.spec} for r in result.all()]
        synced = await model_sync.sync_all(connections)
        logger.info(
            "LiteLLM model sync: %d models pushed",
            synced,
            extra={"event": "litellm_startup_sync", "synced_count": synced},
        )
    except Exception:
        logger.warning(
            "LiteLLM model sync failed on startup — models from static config only",
            exc_info=True,
            extra={"event": "litellm_startup_sync_failed"},
        )

    # Start gRPC server alongside FastAPI
    grpc_server = None
    try:
        from blackbeard.grpc.server import start_grpc_server

        grpc_port = settings.grpc_port
        grpc_server = await start_grpc_server(port=grpc_port)
        logger.info(
            "gRPC server started on port %d",
            grpc_port,
            extra={"event": "grpc_server_started", "port": grpc_port},
        )
    except Exception:
        logger.warning(
            "gRPC server failed to start — continuing without gRPC",
            exc_info=True,
            extra={"event": "grpc_server_start_failed"},
        )

    startup_ms = round((time.monotonic() - t0_startup) * 1000, 1)
    logger.info(
        "Blackbeard %s ready to accept traffic (%.0fms, %d stale executions recovered)",
        app.version,
        startup_ms,
        recovered,
        extra={
            "event": "startup_complete",
            "version": app.version,
            "startup_ms": startup_ms,
            "stale_executions_recovered": recovered,
        },
    )
    yield
    t0 = time.monotonic()
    logger.info("Shutdown starting", extra={"event": "app_shutdown_start"})
    try:
        await scheduler.stop()
        if grpc_server is not None:
            await grpc_server.stop(grace=5)
            logger.info("gRPC server stopped", extra={"event": "grpc_server_stopped"})
        shutdown_executor()
        logger.info("Executor shut down", extra={"event": "executor_shutdown"})
        shutdown_webhook_executor()
        shutdown_otel()
        from blackbeard.resources import shutdown_dns_executor

        shutdown_dns_executor()
    finally:
        try:
            await shutdown_health_clients()
            await close_all_clients()
            logger.info(
                "HTTP clients closed",
                extra={"event": "http_clients_shutdown_complete"},
            )
        except Exception:
            logger.exception(
                "Error closing HTTP clients",
                extra={"event": "http_clients_shutdown_error"},
            )
        finally:
            await engine.dispose()
            shutdown_ms = round((time.monotonic() - t0) * 1000, 1)
            uptime_s = round(time.monotonic() - t0_startup, 1)
            logger.info(
                "Shutdown complete in %.0fms (uptime %.1fs)",
                shutdown_ms,
                uptime_s,
                extra={
                    "event": "app_shutdown_complete",
                    "shutdown_ms": shutdown_ms,
                    "uptime_s": uptime_s,
                },
            )


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description="Open, self-hosted Agent Management Platform",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    openapi_url="/openapi.json" if settings.debug else None,
    openapi_tags=[
        {"name": "health", "description": "Liveness and readiness probes"},
        {"name": "auth", "description": "Authentication: register, login, refresh, profile"},
        {"name": "users", "description": "User and group management"},
        {"name": "audit", "description": "Security audit log queries"},
        {"name": "chat", "description": "Ad-hoc chat completions and model management"},
        {
            "name": "executions",
            "description": "Crew execution lifecycle (kickoff, status, cancel, stream)",
        },
        {
            "name": "marketplace",
            "description": "Import resources from git repositories or built-in examples",
        },
        {
            "name": "resources",
            "description": "Generic CRUD for all resource kinds (Agent, Task, Crew, etc.)",
        },
        {
            "name": "webhooks",
            "description": "Webhook registration for execution event delivery",
        },
        {
            "name": "automations",
            "description": "Automation triggers: cron, webhook, and API-triggered executions",
        },
        {
            "name": "collaboration",
            "description": "Real-time canvas collaboration via WebSocket",
        },
        {
            "name": "assistant",
            "description": "AI-powered resource generation from natural language prompts",
        },
        {
            "name": "credentials",
            "description": "Centralized secret management (API keys, tokens, passwords)",
        },
        {
            "name": "a2a",
            "description": "Agent-to-Agent protocol (agent card discovery)",
        },
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key", "Authorization", "X-Request-Id"],
    expose_headers=["X-Request-Id"],
)

# Middleware stack (LIFO): security_headers → api_key_middleware → body_size_limiter
app.middleware("http")(body_size_limiter)
app.middleware("http")(api_key_middleware)
app.middleware("http")(security_headers_middleware)

app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)

app.include_router(health_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(audit_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
app.include_router(executions_router, prefix="/api/v1")
app.include_router(marketplace_router, prefix="/api/v1")
app.include_router(webhooks_router, prefix="/api/v1")
app.include_router(automations_router, prefix="/api/v1")
app.include_router(collaboration_router, prefix="/api/v1")
app.include_router(assistant_router, prefix="/api/v1")
app.include_router(credentials_router, prefix="/api/v1")
app.include_router(a2a_router)
app.include_router(agency_import_router, prefix="/api/v1")

if settings.oidc_issuer:
    from blackbeard.api.oidc import router as oidc_router

    app.include_router(oidc_router, prefix="/api/v1")
    import hmac as _hmac

    from starlette.middleware.sessions import SessionMiddleware

    _session_key = _hmac.new(
        settings.jwt_secret.get_secret_value().encode(),
        b"blackbeard-session-middleware",
        "sha256",
    ).hexdigest()
    app.add_middleware(
        SessionMiddleware,
        secret_key=_session_key,
        https_only=not settings.debug,
        same_site="lax",
        max_age=600,
    )

app.include_router(resources_router, prefix="/api/v1")
