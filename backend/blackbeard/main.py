"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

from blackbeard.config import settings
from blackbeard.api.health import router as health_router
from blackbeard.api.resources import router as resources_router
from blackbeard.api.executions import router as executions_router
from blackbeard.api.middleware import api_key_middleware
from blackbeard.models.database import engine
import blackbeard.models.resource  # noqa: F401 — register Resource/ResourceRef tables
import blackbeard.models.execution  # noqa: F401 — register Execution tables
from blackbeard.langfuse.client import shutdown_langfuse
from blackbeard.engine.executor import shutdown_executor
from blackbeard.litellm.key_manager import shutdown_key_manager


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan: startup and shutdown."""
    # Warn if using default API key
    if settings.blackbeard_api_key == "change-me-in-production":
        import warnings
        warnings.warn(
            "⚠️  Using default API key 'change-me-in-production'. "
            "Set BLACKBEARD_API_KEY environment variable for production use.",
            stacklevel=1,
        )
        logger.warning("SECURITY: Using default API key — set BLACKBEARD_API_KEY for production")
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


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch unhandled exceptions and return a sanitized 500 response."""
    logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )

# Routers
app.include_router(health_router, prefix="/api/v1")
app.include_router(executions_router, prefix="/api/v1")
app.include_router(resources_router, prefix="/api/v1")
