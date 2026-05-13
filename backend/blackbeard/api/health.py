"""Health check endpoints."""

import asyncio
import logging
import threading
import time
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from blackbeard.config import settings
from blackbeard.models import get_session

_redis_from_url: Any = None
_HAS_REDIS = False
try:
    from redis.asyncio import from_url as _redis_from_url_import

    _redis_from_url = _redis_from_url_import
    _HAS_REDIS = True
except ImportError:
    pass

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

_health_client: httpx.AsyncClient | None = None
_health_client_lock = threading.Lock()


def _get_health_client() -> httpx.AsyncClient:
    global _health_client
    if _health_client is None:
        with _health_client_lock:
            if _health_client is None:
                _health_client = httpx.AsyncClient(timeout=3.0)
    return _health_client


_NO_CACHE = "no-cache, no-store, must-revalidate"


class HealthResponse(BaseModel):
    status: str
    service: str


class ComponentCheck(BaseModel):
    status: str
    latency_ms: float | None = None
    reason: str | None = None
    http_status: int | None = None


class ReadinessResponse(BaseModel):
    status: str
    service: str
    checks: dict[str, ComponentCheck]


@router.get("/health", response_model=HealthResponse)
async def health(response: Response) -> HealthResponse:
    response.headers["Cache-Control"] = _NO_CACHE
    return HealthResponse(status="ok", service="blackbeard")


_valkey_client: Any = None
_valkey_lock = asyncio.Lock()


async def _check_valkey() -> dict[str, object]:
    """Ping Valkey/Redis and return status dict."""
    global _valkey_client
    if not _HAS_REDIS:
        return {"status": "skipped", "reason": "redis package not installed"}

    try:
        if _valkey_client is None:
            async with _valkey_lock:
                if _valkey_client is None:
                    # redis.asyncio expects redis:// scheme; Valkey is wire-compatible
                    url = settings.valkey_url.get_secret_value().replace("valkey://", "redis://", 1)
                    _valkey_client = _redis_from_url(url, socket_connect_timeout=2)
        t0 = time.monotonic()
        await _valkey_client.ping()
        latency_ms = round((time.monotonic() - t0) * 1000, 1)
        return {"status": "up", "latency_ms": latency_ms}
    except Exception as e:
        _valkey_client = None
        err = type(e).__name__
        logger.warning(
            "Health check: valkey is down: %s: %s",
            err,
            e,
            exc_info=True,
            extra={"event": "health_check_failed", "component": "valkey", "error_type": err},
        )
        return {"status": "down", "reason": type(e).__name__}


async def _check_litellm() -> dict[str, object]:
    """Hit LiteLLM /health/liveliness and return status dict."""
    try:
        client = _get_health_client()
        t0 = time.monotonic()
        resp = await client.get(f"{settings.litellm_proxy_url}/health/liveliness")
        latency_ms = round((time.monotonic() - t0) * 1000, 1)
        if resp.status_code == 200:
            return {"status": "up", "latency_ms": latency_ms}
        return {"status": "degraded", "http_status": resp.status_code, "latency_ms": latency_ms}
    except Exception as e:
        err = type(e).__name__
        logger.warning(
            "Health check: litellm is down: %s: %s",
            err,
            e,
            exc_info=True,
            extra={"event": "health_check_failed", "component": "litellm", "error_type": err},
        )
        return {"status": "down", "reason": type(e).__name__}


async def shutdown_health_clients() -> None:
    """Close persistent health-check clients. Called during app lifespan shutdown."""
    global _health_client, _valkey_client
    if _health_client is not None:
        await _health_client.aclose()
        _health_client = None
    if _valkey_client is not None:
        try:
            await _valkey_client.aclose()
        except Exception as e:
            logger.warning(
                "Error closing valkey client: %s",
                e,
                extra={"event": "valkey_close_error"},
            )
        _valkey_client = None


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    responses={503: {"description": "One or more components are down", "model": ReadinessResponse}},
)
async def readiness(
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> ReadinessResponse:
    """Readiness check — verifies database, Valkey, and LiteLLM connectivity."""
    overall = "healthy"

    async def _check_database() -> dict[str, object]:
        try:
            t0 = time.monotonic()
            await session.execute(text("SELECT 1"))
            latency_ms = round((time.monotonic() - t0) * 1000, 1)
            return {"status": "up", "latency_ms": latency_ms}
        except Exception as e:
            logger.warning(
                "Health check: database is down: %s: %s",
                type(e).__name__,
                e,
                exc_info=True,
                extra={
                    "event": "health_check_failed",
                    "component": "database",
                    "error_type": type(e).__name__,
                },
            )
            return {"status": "down", "reason": type(e).__name__}

    try:
        db_result, valkey_result, litellm_result = await asyncio.wait_for(
            asyncio.gather(_check_database(), _check_valkey(), _check_litellm()),
            timeout=10.0,
        )
    except TimeoutError:
        logger.error(
            "Readiness check timed out after 10s",
            extra={"event": "readiness_timeout"},
        )
        db_result = {"status": "down", "reason": "timeout"}
        valkey_result = {"status": "down", "reason": "timeout"}
        litellm_result = {"status": "down", "reason": "timeout"}
    checks: dict[str, dict[str, object]] = {
        "database": db_result,
        "valkey": valkey_result,
        "litellm": litellm_result,
    }
    if any(v["status"] in ("down", "degraded") for v in checks.values()):
        overall = "unhealthy"

    if overall != "healthy":
        response.status_code = 503
        logger.warning(
            "Readiness check unhealthy: db=%s valkey=%s litellm=%s",
            checks["database"]["status"],
            checks["valkey"]["status"],
            checks["litellm"]["status"],
            extra={
                "event": "readiness_unhealthy",
                "db_status": checks["database"]["status"],
                "db_latency_ms": checks["database"].get("latency_ms"),
                "valkey_status": checks["valkey"]["status"],
                "valkey_latency_ms": checks["valkey"].get("latency_ms"),
                "litellm_status": checks["litellm"]["status"],
                "litellm_latency_ms": checks["litellm"].get("latency_ms"),
            },
        )
    else:
        logger.debug(
            "Readiness check healthy: db=%s valkey=%s litellm=%s",
            checks["database"]["status"],
            checks["valkey"]["status"],
            checks["litellm"]["status"],
            extra={
                "event": "readiness_healthy",
                "db_latency_ms": checks["database"].get("latency_ms"),
                "valkey_latency_ms": checks["valkey"].get("latency_ms"),
                "litellm_latency_ms": checks["litellm"].get("latency_ms"),
            },
        )
    response.headers["Cache-Control"] = _NO_CACHE
    return ReadinessResponse(
        status=overall,
        service="blackbeard",
        checks={k: ComponentCheck(**v) for k, v in checks.items()},
    )
