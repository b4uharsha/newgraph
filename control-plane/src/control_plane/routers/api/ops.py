"""Ops API router for operational endpoints (background jobs, system state)."""

from datetime import UTC, datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Query, Request
from graph_olap_schemas import (
    ExportJobsListResponse,
    ExportJobSummary,
    JobsStatusResponse,
    JobStatus,
    SystemStateResponse,
    TriggerJobRequest,
    TriggerJobResponse,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.infrastructure import tables
from control_plane.infrastructure.database import get_async_session
from control_plane.jobs.scheduler import BackgroundJobScheduler
from control_plane.middleware.identity import CurrentUser
from control_plane.models import UserRole
from control_plane.models.errors import (
    NotFoundError,
    RateLimitError,
    RoleRequiredError,
    ServiceUnavailableError,
)
from control_plane.models.responses import DataResponse

router = APIRouter(prefix="/api/ops", tags=["Ops"])

logger = structlog.get_logger(__name__)


def require_ops_role(user: CurrentUser) -> None:
    """Require ops role for ops endpoints."""
    if user.role != UserRole.OPS:
        raise RoleRequiredError(required_role="ops", user_role=user.role.value)


# Rate limiting state (in-memory, simple implementation)
_trigger_timestamps: dict[str, datetime] = {}


async def rate_limit_job_trigger(job_name: str) -> bool:
    """Check if job can be triggered (max 1 per minute per job).

    Args:
        job_name: Name of the job

    Returns:
        True if allowed, False if rate limited
    """
    now = datetime.now(UTC)
    key = f"trigger:{job_name}"

    last_trigger = _trigger_timestamps.get(key)
    if last_trigger:
        elapsed = (now - last_trigger).total_seconds()
        if elapsed < 60:
            return False

    _trigger_timestamps[key] = now
    return True


# All response models are imported from graph_olap_schemas above


# Dependencies


def get_scheduler(request: Request) -> BackgroundJobScheduler:
    """Get the background job scheduler instance from app state.

    Args:
        request: FastAPI request object

    Returns:
        Background job scheduler

    Raises:
        HTTPException: If scheduler not initialized
    """
    app = request.app

    if hasattr(app.state, "scheduler"):
        return app.state.scheduler
    raise ServiceUnavailableError(
        service="background_job_scheduler",
        message="Background job scheduler not initialized"
    )


SchedulerDep = Annotated[BackgroundJobScheduler, Depends(get_scheduler)]


# Endpoints


@router.post("/jobs/trigger", response_model=DataResponse[TriggerJobResponse])
async def trigger_job(
    request: TriggerJobRequest,
    user: CurrentUser,
    scheduler: SchedulerDep,
) -> DataResponse[TriggerJobResponse]:
    """Manually trigger background job execution.

    Requires: Ops or admin role

    Use cases:
    - Production smoke tests
    - Manual reconciliation after incident
    - Debugging

    Rate limit: 1 trigger per job per minute
    """
    require_ops_role(user)

    # Rate limit check
    if not await rate_limit_job_trigger(request.job_name):
        logger.warning(
            "job_trigger_rate_limited",
            job_name=request.job_name,
            user=user.username,
            reason=request.reason,
        )
        raise RateLimitError(
            resource=f"job_trigger:{request.job_name}",
            retry_after_seconds=60
        )

    # Get the job from scheduler
    if scheduler._scheduler is None:
        raise ServiceUnavailableError(
            service="background_job_scheduler",
            message="Scheduler not running"
        )

    job = scheduler._scheduler.get_job(request.job_name)
    if job is None:
        raise NotFoundError(
            resource_type="background_job",
            resource_id=request.job_name
        )

    # Trigger job by setting next_run_time to now
    job.modify(next_run_time=datetime.now(UTC))

    # Audit log: Record manual job trigger
    logger.info(
        "background_job_triggered",
        job_name=request.job_name,
        triggered_by=user.username,
        reason=request.reason,
    )

    return DataResponse(
        data=TriggerJobResponse(
            job_name=request.job_name,
            triggered_at=datetime.now(UTC).isoformat(),
            triggered_by=user.username,
            reason=request.reason,
            status="queued",
        )
    )


@router.get("/jobs/status", response_model=DataResponse[JobsStatusResponse])
async def get_jobs_status(
    user: CurrentUser,
    scheduler: SchedulerDep,
) -> DataResponse[JobsStatusResponse]:
    """Get status of all background jobs.

    Requires: Ops or admin role
    """
    require_ops_role(user)

    if scheduler._scheduler is None:
        raise ServiceUnavailableError(
            service="background_job_scheduler",
            message="Scheduler not running"
        )

    jobs = []
    for job in scheduler._scheduler.get_jobs():
        jobs.append(
            JobStatus(
                name=job.id,
                next_run=job.next_run_time.isoformat() if job.next_run_time else None,
            )
        )

    return DataResponse(data=JobsStatusResponse(jobs=jobs))


@router.get("/state", response_model=DataResponse[SystemStateResponse])
async def get_system_state(
    user: CurrentUser,
    session: AsyncSession = Depends(get_async_session),
) -> DataResponse[SystemStateResponse]:
    """Get system state summary.

    Requires: Ops or admin role

    Returns counts of instances, snapshots, export jobs by status.
    """
    require_ops_role(user)

    # Query instance counts by status
    instance_counts_result = await session.execute(
        select(tables.instances.c.status, func.count(tables.instances.c.id)).group_by(tables.instances.c.status)
    )
    instances_by_status = {row[0]: row[1] for row in instance_counts_result}

    # Query snapshot counts by status
    snapshot_counts_result = await session.execute(
        select(tables.snapshots.c.status, func.count(tables.snapshots.c.id)).group_by(tables.snapshots.c.status)
    )
    snapshots_by_status = {row[0]: row[1] for row in snapshot_counts_result}

    # Query export job counts by status
    export_job_counts_result = await session.execute(
        select(tables.export_jobs.c.status, func.count(tables.export_jobs.c.id)).group_by(tables.export_jobs.c.status)
    )
    export_jobs_by_status = {row[0]: row[1] for row in export_job_counts_result}

    # Count instances without pod_name
    instances_without_pod = await session.scalar(
        select(func.count(tables.instances.c.id)).where(tables.instances.c.pod_name.is_(None))
    )

    return DataResponse(
        data=SystemStateResponse(
            instances={
                "total": sum(instances_by_status.values()),
                "by_status": instances_by_status,
                "without_pod_name": instances_without_pod,
            },
            snapshots={
                "total": sum(snapshots_by_status.values()),
                "by_status": snapshots_by_status,
            },
            export_jobs={
                "by_status": export_jobs_by_status,
            },
        )
    )


@router.get("/export-jobs", response_model=DataResponse[ExportJobsListResponse])
async def get_export_jobs(
    user: CurrentUser,
    session: AsyncSession = Depends(get_async_session),
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(100, le=1000),
) -> DataResponse[ExportJobsListResponse]:
    """Get export jobs for debugging.

    Requires: Ops or admin role

    Args:
        status: Filter by status (pending, claimed, completed, failed)
        limit: Max jobs to return (default 100, max 1000)
    """
    require_ops_role(user)

    query = select(tables.export_jobs)

    if status_filter:
        query = query.where(tables.export_jobs.c.status == status_filter)

    query = query.limit(limit).order_by(tables.export_jobs.c.created_at.desc())

    result = await session.execute(query)
    rows = result.all()

    jobs_response = [
        ExportJobSummary(
            id=row.id,
            snapshot_id=row.snapshot_id,
            entity_type=row.job_type,
            entity_name=row.entity_name,
            status=row.status,
            claimed_at=row.claimed_at,  # Already stored as ISO 8601 string
            claimed_by=row.claimed_by,
            attempts=row.poll_count,  # Use poll_count as attempts proxy
            error_message=row.error_message,
        )
        for row in rows
    ]

    return DataResponse(data=ExportJobsListResponse(jobs=jobs_response))
