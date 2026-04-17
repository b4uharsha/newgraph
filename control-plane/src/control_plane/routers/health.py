"""Health check endpoints."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.infrastructure.database import check_database_health, get_async_session
from control_plane.models.responses import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Basic health check endpoint.

    Returns:
        Health status
    """
    return HealthResponse(status="healthy", version="0.1.0")


@router.get("/ready", response_model=HealthResponse)
async def readiness_check(
    session: AsyncSession = Depends(get_async_session),
) -> HealthResponse:
    """Readiness check with database connectivity.

    Returns:
        Health status including database status
    """
    db_healthy = await check_database_health()

    return HealthResponse(
        status="ready" if db_healthy else "not_ready",
        database="connected" if db_healthy else "disconnected",
        version="0.1.0",
    )


@router.get("/api/debug/headers")
async def debug_headers(request: Request) -> dict:
    """Debug endpoint returning all request headers.

    Useful for verifying header propagation through Ingress/proxy layers
    (e.g., X-Username, X-Use-Case-Id).
    """
    return dict(request.headers)
