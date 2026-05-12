"""Health check endpoints."""

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from blackbeard.models.database import get_session

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Liveness check — returns ok if the process is running."""
    return {"status": "ok", "service": "blackbeard"}


@router.get("/health/ready")
async def readiness(session: AsyncSession = Depends(get_session)) -> JSONResponse:
    """Readiness check — verifies database connectivity."""
    checks = {}
    overall = "healthy"

    try:
        await session.execute(text("SELECT 1"))
        checks["database"] = {"status": "up"}
    except Exception as e:
        checks["database"] = {"status": "down"}
        overall = "unhealthy"
        logger.error("Health check: database is down: %s: %s", type(e).__name__, e)

    status_code = 200 if overall == "healthy" else 503
    return JSONResponse(
        content={"status": overall, "service": "blackbeard", "checks": checks},
        status_code=status_code,
    )
