"""Health and status endpoints.

Provides:
- /health - Kubernetes liveness probe
- /ready - Kubernetes readiness probe
- /status - Detailed instance status
"""

from __future__ import annotations

from datetime import UTC, datetime

import psutil
from fastapi import APIRouter, HTTPException, status

from wrapper.dependencies import DatabaseServiceDep, LockServiceDep, SettingsDep
from wrapper.models.responses import HealthResponse, StatusResponse

router = APIRouter(tags=["Health"])

# Track startup time
_startup_time: datetime | None = None


def set_startup_time() -> None:
    """Set the startup timestamp."""
    global _startup_time
    _startup_time = datetime.now(UTC)


def get_startup_time() -> datetime:
    """Get the startup timestamp."""
    global _startup_time
    if _startup_time is None:
        _startup_time = datetime.now(UTC)
    return _startup_time


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness probe",
    description="Returns healthy if the service is running. Used by Kubernetes liveness probe.",
)
async def health() -> HealthResponse:
    """Liveness probe endpoint.

    Always returns healthy as long as the service is running.
    Used by Kubernetes to determine if the pod should be restarted.
    """
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now(UTC).isoformat(),
    )


@router.get(
    "/ready",
    response_model=HealthResponse,
    summary="Readiness probe",
    description="Returns healthy if the service is ready to accept requests.",
    responses={
        503: {"description": "Service not ready"},
    },
)
async def ready(
    db_service: DatabaseServiceDep,
) -> HealthResponse:
    """Readiness probe endpoint.

    Returns healthy only if the database is initialized and data is loaded.
    Used by Kubernetes to determine if traffic should be routed to this pod.
    """
    if not db_service.is_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not ready - data not loaded",
        )

    return HealthResponse(
        status="healthy",
        timestamp=datetime.now(UTC).isoformat(),
    )


@router.get(
    "/status",
    response_model=StatusResponse,
    summary="Detailed status",
    description="Returns detailed status information about the instance.",
)
async def get_status(
    settings: SettingsDep,
    db_service: DatabaseServiceDep,
    lock_service: LockServiceDep,
) -> StatusResponse:
    """Get detailed instance status.

    Returns comprehensive status information including:
    - Instance identifiers
    - Readiness state
    - Graph statistics
    - Resource usage
    - Lock status
    """
    started_at = get_startup_time()
    uptime = datetime.now(UTC) - started_at

    # Determine overall status
    if not db_service.is_initialized:
        status_value = "starting"
    elif not db_service.is_ready:
        status_value = "loading"
    else:
        status_value = "running"

    # Get graph stats if available
    node_count: int | None = None
    edge_count: int | None = None
    node_tables: list[str] = []
    edge_tables: list[str] = []

    if db_service.is_ready:
        try:
            stats = await db_service.get_stats()
            node_count = stats.get("node_count")
            edge_count = stats.get("edge_count")
        except Exception:
            pass

        try:
            schema = await db_service.get_schema()
            node_tables = [t["label"] for t in schema.get("node_tables", [])]
            edge_tables = [t["type"] for t in schema.get("edge_tables", [])]
        except Exception:
            pass

    # Get resource usage
    process = psutil.Process()
    memory_info = process.memory_info()

    return StatusResponse(
        status=status_value,
        instance_id=settings.wrapper.instance_id,
        snapshot_id=settings.wrapper.snapshot_id,
        mapping_id=settings.wrapper.mapping_id,
        owner_id=settings.wrapper.owner_id,
        ready=db_service.is_ready,
        started_at=started_at.isoformat(),
        uptime_seconds=int(uptime.total_seconds()),
        node_count=node_count,
        edge_count=edge_count,
        node_tables=node_tables,
        edge_tables=edge_tables,
        memory_usage_bytes=memory_info.rss,
        disk_usage_bytes=None,  # Would need to check database path
        lock=lock_service.get_lock_info(),
    )
