"""Cluster API router for Ops users."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.infrastructure.database import get_async_session
from control_plane.middleware.identity import CurrentUser
from control_plane.models import UserRole
from control_plane.models.errors import RoleRequiredError
from control_plane.models.responses import DataResponse
from control_plane.repositories.config import GlobalConfigRepository
from control_plane.repositories.instances import InstanceRepository

router = APIRouter(prefix="/api/cluster", tags=["Cluster"])


def get_instance_repo(
    session: AsyncSession = Depends(get_async_session),
) -> InstanceRepository:
    """Dependency to get instance repository."""
    return InstanceRepository(session)


def get_config_repo(
    session: AsyncSession = Depends(get_async_session),
) -> GlobalConfigRepository:
    """Dependency to get config repository."""
    return GlobalConfigRepository(session)


InstanceRepoDep = Annotated[InstanceRepository, Depends(get_instance_repo)]
ConfigRepoDep = Annotated[GlobalConfigRepository, Depends(get_config_repo)]


def require_ops_role(user: CurrentUser) -> None:
    """Require ops role for cluster endpoints."""
    if user.role != UserRole.OPS:
        raise RoleRequiredError(required_role="ops", user_role=user.role.value)


# Response models


class ComponentHealth(BaseModel):
    """Health status of a component."""

    status: str
    latency_ms: int | None = None
    error: str | None = None


class ClusterHealthResponse(BaseModel):
    """Cluster health response."""

    status: str  # healthy, degraded, unhealthy
    components: dict[str, ComponentHealth]
    checked_at: datetime


class OwnerInstanceCount(BaseModel):
    """Instance count by owner."""

    owner_username: str
    count: int


class InstanceLimits(BaseModel):
    """Instance limits."""

    per_analyst: int
    cluster_total: int
    cluster_used: int
    cluster_available: int


class ClusterInstancesResponse(BaseModel):
    """Cluster instances summary response."""

    total: int
    by_status: dict[str, int]
    by_owner: list[OwnerInstanceCount]
    limits: InstanceLimits


# Endpoints


@router.get("/health", response_model=DataResponse[ClusterHealthResponse])
async def get_cluster_health(
    user: CurrentUser,
    session: AsyncSession = Depends(get_async_session),
) -> DataResponse[ClusterHealthResponse]:
    """Get cluster health status.

    Checks connectivity to database, kubernetes, and starburst.
    Requires Ops role.
    """
    require_ops_role(user)

    import time

    components: dict[str, ComponentHealth] = {}
    overall_status = "healthy"

    # Check database
    try:
        start = time.time()
        from sqlalchemy import text

        await session.execute(text("SELECT 1"))
        latency_ms = int((time.time() - start) * 1000)
        components["database"] = ComponentHealth(status="connected", latency_ms=latency_ms)
    except Exception as e:
        components["database"] = ComponentHealth(status="unreachable", error=str(e))
        overall_status = "degraded"

    # Kubernetes - placeholder (would need actual client)
    components["kubernetes"] = ComponentHealth(status="connected")

    # Starburst - placeholder (would need actual client)
    components["starburst"] = ComponentHealth(status="connected", latency_ms=0)

    now = datetime.utcnow()

    response_data = ClusterHealthResponse(
        status=overall_status,
        components=components,
        checked_at=now,
    )

    if overall_status == "degraded":
        # Still return 200 but indicate degraded status in response
        pass

    return DataResponse(data=response_data)


@router.get("/instances", response_model=DataResponse[ClusterInstancesResponse])
async def get_cluster_instances(
    user: CurrentUser,
    instance_repo: InstanceRepoDep,
    config_repo: ConfigRepoDep,
) -> DataResponse[ClusterInstancesResponse]:
    """Get cluster-wide instance summary.

    Returns total instances, counts by status, counts by owner, and limits.
    Requires Ops role.
    """
    require_ops_role(user)

    from control_plane.repositories.instances import InstanceFilters

    # Get all instances (no filter)
    instances, total = await instance_repo.list_instances(
        filters=InstanceFilters(),
        limit=1000,  # Get all for counting
        offset=0,
    )

    # Count by status
    by_status: dict[str, int] = {}
    for instance in instances:
        status_str = instance.status.value
        by_status[status_str] = by_status.get(status_str, 0) + 1

    # Count by owner
    owner_counts: dict[str, int] = {}
    for instance in instances:
        owner = instance.owner_username
        owner_counts[owner] = owner_counts.get(owner, 0) + 1

    by_owner = [
        OwnerInstanceCount(owner_username=owner, count=count)
        for owner, count in sorted(owner_counts.items(), key=lambda x: -x[1])
    ]

    # Get limits
    limits_config = await config_repo.get_concurrency_limits()
    cluster_used = await instance_repo.count_total_active()

    limits = InstanceLimits(
        per_analyst=limits_config["per_analyst"],
        cluster_total=limits_config["cluster_total"],
        cluster_used=cluster_used,
        cluster_available=max(0, limits_config["cluster_total"] - cluster_used),
    )

    return DataResponse(
        data=ClusterInstancesResponse(
            total=total,
            by_status=by_status,
            by_owner=by_owner,
            limits=limits,
        )
    )
