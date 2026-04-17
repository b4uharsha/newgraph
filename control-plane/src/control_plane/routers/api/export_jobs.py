"""Export jobs API router with role-scoped access (ADR-106 Phase 3, C1).

Analysts see only their own export jobs (via snapshot ownership).
Admin and Ops see all export jobs.

Also exposes a /pending-count endpoint for KEDA auto-scaling (no user auth required).
"""

from fastapi import APIRouter, Depends, Query
from graph_olap_schemas import ExportJobsListResponse, ExportJobSummary
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.infrastructure import tables
from control_plane.infrastructure.database import get_async_session
from control_plane.middleware.identity import CurrentUser
from control_plane.models import UserRole
from control_plane.models.responses import DataResponse

router = APIRouter(prefix="/api/export-jobs", tags=["Export Jobs"])


class PendingCountResponse(BaseModel):
    """Response for the pending-count endpoint (KEDA auto-scaling)."""

    pending_count: int


@router.get("/pending-count", response_model=PendingCountResponse)
async def get_pending_count(
    session: AsyncSession = Depends(get_async_session),
) -> PendingCountResponse:
    """Get count of pending export jobs for KEDA auto-scaling.

    This endpoint does NOT require user authentication so that KEDA
    (or a service account) can poll it to scale export workers.

    Returns:
        JSON with pending_count field
    """
    query = select(func.count()).select_from(tables.export_jobs).where(
        tables.export_jobs.c.status == "pending"
    )
    result = await session.execute(query)
    count = result.scalar() or 0
    return PendingCountResponse(pending_count=count)


@router.get("", response_model=DataResponse[ExportJobsListResponse])
async def get_export_jobs(
    user: CurrentUser,
    session: AsyncSession = Depends(get_async_session),
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> DataResponse[ExportJobsListResponse]:
    """Get export jobs with role-scoped access.

    - Analyst: sees only export jobs for snapshots they own
    - Admin/Ops: sees all export jobs

    Supports pagination via limit/offset query parameters.

    Args:
        status: Filter by status (pending, claimed, submitted, completed, failed)
        limit: Max jobs to return (default 50, max 200)
        offset: Number of jobs to skip (default 0)
    """
    if user.role == UserRole.ANALYST:
        # Join to snapshots to filter by owner
        query = (
            select(tables.export_jobs)
            .join(tables.snapshots, tables.export_jobs.c.snapshot_id == tables.snapshots.c.id)
            .where(tables.snapshots.c.owner_username == user.username)
        )
    else:
        query = select(tables.export_jobs)

    if status_filter:
        query = query.where(tables.export_jobs.c.status == status_filter)

    query = query.order_by(tables.export_jobs.c.created_at.desc()).offset(offset).limit(limit)

    result = await session.execute(query)
    rows = result.all()

    jobs_response = [
        ExportJobSummary(
            id=row.id,
            snapshot_id=row.snapshot_id,
            entity_type=row.job_type,
            entity_name=row.entity_name,
            status=row.status,
            claimed_at=row.claimed_at,
            claimed_by=row.claimed_by,
            attempts=row.poll_count,
            error_message=row.error_message,
        )
        for row in rows
    ]

    return DataResponse(data=ExportJobsListResponse(jobs=jobs_response))
