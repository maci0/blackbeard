"""Health check endpoints."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from redis.asyncio import from_url as _redis_from_url
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from blackbeard import __version__
from blackbeard.api.sse_state import get_status as get_sse_status
from blackbeard.config import settings
from blackbeard.engine import get_pool_status
from blackbeard.http_client import get_client
from blackbeard.models import get_session

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

_start_time = time.monotonic()


def _get_health_client() -> httpx.AsyncClient:
    return get_client("health", timeout=3.0)


_NO_CACHE = "no-cache, no-store, must-revalidate"


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    uptime_s: float | None = None


class ComponentCheck(BaseModel):
    status: Literal["up", "down", "degraded", "saturated"]
    latency_ms: float | None = None
    reason: str | None = None
    http_status: int | None = None
    active_threads: int | None = None
    queued_tasks: int | None = None
    max_workers: int | None = None


class ReadinessResponse(BaseModel):
    status: Literal["healthy", "degraded", "unhealthy"]
    service: str
    version: str
    uptime_s: float | None = None
    checks: dict[str, ComponentCheck]


@router.get("/config/public")
async def public_config() -> dict[str, bool]:
    """Public configuration — no auth required."""
    return {"oidc_enabled": bool(settings.oidc_issuer)}


@router.get("/health", response_model=HealthResponse)
async def health(response: Response) -> HealthResponse:
    response.headers["Cache-Control"] = _NO_CACHE
    return HealthResponse(
        status="ok",
        service="blackbeard",
        version=__version__,
        uptime_s=round(time.monotonic() - _start_time, 1),
    )


_valkey_client: Any = None
_valkey_lock = asyncio.Lock()


async def _check_valkey() -> dict[str, object]:
    """Ping Valkey and return status dict.

    Converts valkey:// URLs to redis:// for the redis-py client.
    """
    global _valkey_client
    t0 = time.monotonic()
    client: Any = None
    try:
        if _valkey_client is None:
            async with _valkey_lock:
                if _valkey_client is None:
                    url = settings.valkey_url.get_secret_value().replace("valkey://", "redis://", 1)
                    _valkey_client = _redis_from_url(url, socket_connect_timeout=2)  # type: ignore[no-untyped-call]
        client = _valkey_client
        await client.ping()
        latency_ms = round((time.monotonic() - t0) * 1000, 1)
        return {"status": "up", "latency_ms": latency_ms}
    except Exception as e:
        latency_ms = round((time.monotonic() - t0) * 1000, 1)
        stale: Any = None
        async with _valkey_lock:
            if _valkey_client is client:
                stale = _valkey_client
                _valkey_client = None
        if stale is not None:
            try:
                await stale.aclose()
            except Exception as close_err:
                logger.debug(
                    "Error closing stale valkey client: %s",
                    close_err,
                    extra={
                        "event": "valkey_stale_close_error",
                        "error_type": type(close_err).__name__,
                    },
                )
        err = type(e).__name__
        logger.warning(
            "Health check: valkey is down: %s: %s (%.0fms)",
            err,
            e,
            latency_ms,
            extra={
                "event": "health_check_failed",
                "component": "valkey",
                "error_type": err,
                "error_message": str(e)[:200],
                "latency_ms": latency_ms,
            },
        )
        return {"status": "down", "reason": "connection_failed", "latency_ms": latency_ms}


async def _check_litellm() -> dict[str, object]:
    """Hit LiteLLM /health/liveliness and return status dict."""
    t0 = time.monotonic()
    try:
        client = _get_health_client()
        resp = await client.get(f"{settings.litellm_proxy_url}/health/liveliness")
        latency_ms = round((time.monotonic() - t0) * 1000, 1)
        if resp.status_code == 200:
            return {"status": "up", "latency_ms": latency_ms}
        logger.warning(
            "Health check: litellm degraded: status=%d (%.0fms)",
            resp.status_code,
            latency_ms,
            extra={
                "event": "health_check_degraded",
                "component": "litellm",
                "http_status": resp.status_code,
                "latency_ms": latency_ms,
            },
        )
        return {"status": "degraded", "http_status": resp.status_code, "latency_ms": latency_ms}
    except Exception as e:
        latency_ms = round((time.monotonic() - t0) * 1000, 1)
        err = type(e).__name__
        logger.warning(
            "Health check: litellm is down: %s: %s (%.0fms)",
            err,
            e,
            latency_ms,
            extra={
                "event": "health_check_failed",
                "component": "litellm",
                "error_type": err,
                "error_message": str(e)[:200],
                "latency_ms": latency_ms,
            },
        )
        return {"status": "down", "reason": "connection_failed", "latency_ms": latency_ms}


async def shutdown_health_clients() -> None:
    """Close persistent health-check clients. Called during app lifespan shutdown."""
    global _valkey_client
    if _valkey_client is not None:
        try:
            await _valkey_client.aclose()
        except Exception as e:
            logger.warning(
                "Error closing valkey client: %s",
                e,
                exc_info=True,
                extra={
                    "event": "valkey_close_error",
                    "error_type": type(e).__name__,
                    "error_message": str(e)[:500],
                },
            )
        _valkey_client = None


async def _check_database(session: AsyncSession) -> dict[str, object]:
    """Ping the database and return status dict."""
    t0 = time.monotonic()
    try:
        await session.execute(text("SELECT 1"))
        latency_ms = round((time.monotonic() - t0) * 1000, 1)
        return {"status": "up", "latency_ms": latency_ms}
    except Exception as e:
        latency_ms = round((time.monotonic() - t0) * 1000, 1)
        err = type(e).__name__
        logger.error(
            "Health check: database is down: %s: %s (%.0fms)",
            err,
            e,
            latency_ms,
            exc_info=True,
            extra={
                "event": "health_check_failed",
                "component": "database",
                "error_type": err,
                "error_message": str(e)[:200],
                "latency_ms": latency_ms,
            },
        )
        return {"status": "down", "reason": "connection_failed", "latency_ms": latency_ms}


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    responses={
        503: {
            "description": "Critical component (database) is down",
            "model": ReadinessResponse,
        },
    },
)
async def readiness(
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> ReadinessResponse:
    """Readiness check -- verifies database, Valkey, and LiteLLM connectivity.

    Returns 200 with status=healthy (all up) or status=degraded (non-critical
    component down). Returns 503 with status=unhealthy only when a critical
    component (database) is down.
    """
    overall = "healthy"
    t0_ready = time.monotonic()

    async def _with_timeout(coro: Any, label: str) -> dict[str, object]:
        try:
            return await asyncio.wait_for(coro, timeout=10.0)
        except TimeoutError:
            logger.warning(
                "Health check: %s timed out after 10s",
                label,
                extra={"event": "health_check_timeout", "component": label},
            )
            return {"status": "down", "reason": "timeout"}

    db_result, valkey_result, litellm_result = await asyncio.gather(
        _with_timeout(_check_database(session), "database"),
        _with_timeout(_check_valkey(), "valkey"),
        _with_timeout(_check_litellm(), "litellm"),
    )
    pool = get_pool_status()
    executor_status = "saturated" if pool["saturated"] else "up"
    executor_result: dict[str, object] = {
        "status": executor_status,
        "active_threads": pool["active_threads"],
        "queued_tasks": pool["queued_tasks"],
        "max_workers": pool["max_workers"],
    }
    checks: dict[str, dict[str, object]] = {
        "database": db_result,
        "valkey": valkey_result,
        "litellm": litellm_result,
        "executor": executor_result,
    }
    # Database is a hard dependency — if it is down, the service is unhealthy.
    # Valkey (cache) and LiteLLM (model proxy) are soft dependencies — degraded
    # but the API can still serve resource CRUD.
    critical_components = {"database"}
    for comp_name, comp_check in checks.items():
        if comp_check["status"] in ("down", "degraded", "saturated"):
            if comp_name in critical_components:
                overall = "unhealthy"
                break
            overall = "degraded"

    sse = get_sse_status()
    total_ms = round((time.monotonic() - t0_ready) * 1000, 1)
    if overall == "unhealthy":
        response.status_code = 503
        response.headers["Retry-After"] = "5"
        log_level = logging.ERROR
    elif overall == "degraded":
        log_level = logging.WARNING
    else:
        log_level = logging.DEBUG
    log_event = f"readiness_{overall}"
    logger.log(
        log_level,
        "Readiness check %s (%.0fms): db=%s valkey=%s litellm=%s sse=%d/%d",
        overall,
        total_ms,
        checks["database"]["status"],
        checks["valkey"]["status"],
        checks["litellm"]["status"],
        sse["active"],
        sse["max"],
        extra={
            "event": log_event,
            "total_ms": total_ms,
            "db_status": checks["database"]["status"],
            "db_latency_ms": checks["database"].get("latency_ms"),
            "valkey_status": checks["valkey"]["status"],
            "valkey_latency_ms": checks["valkey"].get("latency_ms"),
            "litellm_status": checks["litellm"]["status"],
            "litellm_latency_ms": checks["litellm"].get("latency_ms"),
            "executor_status": executor_status,
            "executor_active": pool["active_threads"],
            "executor_queued": pool["queued_tasks"],
            "sse_active": sse["active"],
            "sse_max": sse["max"],
            "uptime_s": round(time.monotonic() - _start_time, 1),
        },
    )
    response.headers["Cache-Control"] = _NO_CACHE
    return ReadinessResponse(
        status=overall,
        service="blackbeard",
        version=__version__,
        uptime_s=round(time.monotonic() - _start_time, 1),
        checks={k: ComponentCheck(**v) for k, v in checks.items()},
    )
