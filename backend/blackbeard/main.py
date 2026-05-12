"""FastAPI application entry point."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import blackbeard.models.execution  # noqa: F401 — register Execution tables
import blackbeard.models.resource  # noqa: F401 — register Resource/ResourceRef tables
from blackbeard.api.executions import router as executions_router
from blackbeard.api.health import router as health_router
from blackbeard.api.middleware import api_key_middleware
from blackbeard.api.resources import router as resources_router
from blackbeard.config import settings
from blackbeard.engine.executor import shutdown_executor
from blackbeard.langfuse.client import shutdown_langfuse
from blackbeard.litellm.key_manager import shutdown_key_manager
from blackbeard.logging_config import configure_logging, request_id_var
from blackbeard.models.database import engine

configure_logging(debug=settings.debug)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan: startup and shutdown."""
    if settings.blackbeard_api_key == "change-me-in-production":
        if not settings.debug:
            raise RuntimeError(
                "Refusing to start: BLACKBEARD_API_KEY is set to the insecure default. "
                "Set a strong random value via environment variable, or set DEBUG=true for local development."
            )
        logger.warning("SECURITY: Using default API key — set BLACKBEARD_API_KEY for production")
    logger.info(
        "Blackbeard starting: debug=%s, max_concurrent_executions=%d, litellm=%s, langfuse=%s",
        settings.debug,
        settings.max_concurrent_executions,
        settings.litellm_proxy_url,
        "enabled" if settings.langfuse_public_key else "disabled",
    )
    yield
    # Shutdown: stop executor, flush Langfuse, dispose key manager and engine
    try:
        shutdown_executor()
    finally:
        try:
            shutdown_langfuse()
        finally:
            try:
                await shutdown_key_manager()
            finally:
                await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Open, self-hosted Agent Management Platform",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    openapi_url="/openapi.json" if settings.debug else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key", "Authorization", "X-Request-Id"],
    expose_headers=["X-Request-Id"],
)

app.middleware("http")(api_key_middleware)


@app.middleware("http")
async def security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
    """Add security headers to every response."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch unhandled exceptions and return a sanitized 500 response."""
    rid = request_id_var.get("-")
    logger.error(
        "Unhandled exception on %s %s [request_id=%s]: %s",
        request.method, request.url.path, rid, exc,
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
        headers={"X-Request-Id": rid},
    )

# Routers
app.include_router(health_router, prefix="/api/v1")
app.include_router(executions_router, prefix="/api/v1")
app.include_router(resources_router, prefix="/api/v1")
