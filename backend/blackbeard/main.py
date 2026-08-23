"""FastAPI application entry point."""

from __future__ import annotations

import asyncio
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
from blackbeard.api.asyncapi import router as asyncapi_router
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
from blackbeard.api.plugins import router as plugins_router
from blackbeard.api.resources import router as resources_router
from blackbeard.api.tools_library import router as tools_library_router
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
    if settings.allow_internal_urls and not settings.debug:
        logger.warning(
            "SECURITY: ALLOW_INTERNAL_URLS is True in production, SSRF validation is disabled. "
            "Unset ALLOW_INTERNAL_URLS unless you have a specific reason to allow internal URLs.",
            extra={"event": "allow_internal_urls_in_production"},
        )
    if not settings.debug and settings.allow_registration and not settings.enforce_rbac:
        raise _fatal(
            "Refusing to start: ALLOW_REGISTRATION is enabled while ENFORCE_RBAC is false. "
            "Anyone who can reach the API can self-register with full access. "
            "Set ENFORCE_RBAC=true (and seed Role/RoleBinding), or ALLOW_REGISTRATION=false, "
            "or DEBUG=true for local development."
        )
    if not settings.enforce_rbac and not settings.debug:
        logger.warning(
            "SECURITY: ENFORCE_RBAC is False, all authenticated users have full access. "
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
    """Application lifespan.

    Startup: config validation, plugins, scheduler, LiteLLM sync,
    Temporal worker (when configured). Shutdown: reverse order.
    """
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
            "enforce_rbac": settings.enforce_rbac,
            "allow_registration": settings.allow_registration,
            "allow_internal_urls": settings.allow_internal_urls,
            "cors_origins": settings.cors_origins,
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

    # That reload only runs on the replica that served the mutation; other
    # replicas keep stale cron schedules until restart. Periodic resync
    # bounds the drift; the automation_runs dedup table prevents a freshly
    # resynced replica from double-firing.
    async def _scheduler_resync() -> None:
        while True:
            await asyncio.sleep(300)
            try:
                await scheduler.reload()
            except Exception:
                logger.warning(
                    "Scheduler resync failed — retrying in 300s",
                    exc_info=True,
                    extra={"event": "scheduler_resync_failed"},
                )

    scheduler_resync_task = asyncio.create_task(_scheduler_resync(), name="scheduler-resync")

    # Data retention purge (opt-in via *_RETENTION_DAYS settings)
    from blackbeard.retention import retention_enabled, retention_loop

    retention_task: asyncio.Task[None] | None = None
    if retention_enabled():
        retention_task = asyncio.create_task(retention_loop(), name="data-retention")
        logger.info(
            "Data retention purge enabled: audit_log_days=%s execution_days=%s",
            settings.audit_log_retention_days,
            settings.execution_retention_days,
            extra={
                "event": "retention_enabled",
                "audit_log_retention_days": settings.audit_log_retention_days,
                "execution_retention_days": settings.execution_retention_days,
            },
        )

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

    # Discover and load plugins
    try:
        from blackbeard.plugins.loader import load_plugins as _load_plugins

        loaded_plugins = _load_plugins(settings.plugin_dir)
        if loaded_plugins:
            logger.info(
                "Loaded %d plugin(s): %s",
                len(loaded_plugins),
                ", ".join(p.name for p in loaded_plugins),
                extra={
                    "event": "plugins_loaded",
                    "plugin_count": len(loaded_plugins),
                    "plugin_names": [p.name for p in loaded_plugins],
                },
            )
    except Exception:
        logger.warning(
            "Plugin loading failed, continuing without plugins",
            exc_info=True,
            extra={"event": "plugin_loading_failed"},
        )

    # Start Temporal worker if configured
    temporal_running = False
    if settings.temporal_host:
        try:
            from blackbeard.engine.temporal import TEMPORAL_AVAILABLE, start_temporal_worker

            if TEMPORAL_AVAILABLE:
                from blackbeard.engine.executor import (
                    run_crew_async,
                    thread_session_factory,
                )
                from blackbeard.engine.temporal import register_crew_runner

                register_crew_runner(
                    session_factory=thread_session_factory,
                    run_crew=run_crew_async,
                )
                await start_temporal_worker()
                temporal_running = True
                logger.info(
                    "Temporal worker started: host=%s queue=%s",
                    settings.temporal_host,
                    settings.temporal_task_queue,
                    extra={
                        "event": "temporal_worker_started",
                        "host": settings.temporal_host,
                        "task_queue": settings.temporal_task_queue,
                    },
                )
            else:
                logger.warning(
                    "TEMPORAL_HOST is set but temporalio package is not installed, "
                    "falling back to ThreadPoolExecutor",
                    extra={"event": "temporal_package_missing"},
                )
        except Exception:
            logger.warning(
                "Temporal worker failed to start, falling back to ThreadPoolExecutor",
                exc_info=True,
                extra={"event": "temporal_worker_start_failed"},
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
        # Stop the periodic loops and wait for them before disposing engines:
        # an un-awaited cancelled task can still hold a DB session when
        # engine.dispose() runs below.
        loop_tasks = [scheduler_resync_task]
        if retention_task is not None:
            loop_tasks.append(retention_task)
        for task in loop_tasks:
            task.cancel()
        if loop_tasks:
            await asyncio.gather(*loop_tasks, return_exceptions=True)
        await scheduler.stop()
        from blackbeard.api.collaboration import shutdown_collab_backend

        await shutdown_collab_backend()
        if temporal_running:
            try:
                from blackbeard.engine.temporal import stop_temporal_worker

                await stop_temporal_worker()
                logger.info(
                    "Temporal worker stopped",
                    extra={"event": "temporal_worker_stopped"},
                )
            except Exception:
                logger.warning(
                    "Temporal worker stop failed",
                    exc_info=True,
                    extra={"event": "temporal_worker_stop_failed"},
                )
        from blackbeard.api.resources import drain_background_tasks

        await drain_background_tasks()
        shutdown_executor()
        from blackbeard.engine import wait_for_bg_engine_dispose

        await wait_for_bg_engine_dispose()
        logger.info("Executor shut down", extra={"event": "executor_shutdown"})
        shutdown_webhook_executor()
        shutdown_otel()
        from blackbeard.engine.sandbox.runner import shutdown_sandbox_nest_pool
        from blackbeard.resources import shutdown_dns_executor

        shutdown_dns_executor()
        shutdown_sandbox_nest_pool()
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
        {
            "name": "import",
            "description": "Import agent personas from the Agency Agents library",
        },
        {
            "name": "tools-library",
            "description": "Browse and install curated tools from the built-in library",
        },
        {
            "name": "plugins",
            "description": "Plugin SDK: list and reload extension plugins",
        },
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key", "Authorization", "X-Request-Id"],
    expose_headers=["X-Request-Id", "Location", "Retry-After"],
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
app.include_router(asyncapi_router)
app.include_router(agency_import_router, prefix="/api/v1")
app.include_router(tools_library_router, prefix="/api/v1")
app.include_router(plugins_router, prefix="/api/v1")

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
