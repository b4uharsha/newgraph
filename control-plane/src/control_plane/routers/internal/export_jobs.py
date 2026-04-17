"""Internal API for export job management by export worker (ADR-025).

ADR-104/105: Internal API key verification removed. Internal endpoints
are protected by network policy (pod-to-pod only within the cluster).
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.infrastructure.database import get_async_session
from control_plane.models import ExportJob
from control_plane.models.errors import NotFoundError
from control_plane.models.requests import CreateExportJobsRequest, UpdateExportJobRequest
from control_plane.models.responses import (
    ClaimExportJobsRequest,
    ClaimExportJobsResponse,
    DataResponse,
    ExportJobResponse,
    PollableExportJobsResponse,
)
from control_plane.repositories.export_jobs import ExportJobRepository
from control_plane.repositories.snapshots import SnapshotRepository

router = APIRouter(prefix="/api/internal", tags=["Internal - Export Jobs"])


def get_export_job_repo(
    session: AsyncSession = Depends(get_async_session),
) -> ExportJobRepository:
    """Dependency to get export job repository."""
    return ExportJobRepository(session)


def get_snapshot_repo(
    session: AsyncSession = Depends(get_async_session),
) -> SnapshotRepository:
    """Dependency to get snapshot repository."""
    return SnapshotRepository(session)


ExportJobRepoDep = Annotated[ExportJobRepository, Depends(get_export_job_repo)]
SnapshotRepoDep = Annotated[SnapshotRepository, Depends(get_snapshot_repo)]


def export_job_to_response(job: ExportJob) -> ExportJobResponse:
    """Convert domain ExportJob to response model."""
    return ExportJobResponse(
        id=job.id,
        snapshot_id=job.snapshot_id,
        job_type=job.job_type,
        entity_name=job.entity_name,
        status=job.status.value,
        starburst_query_id=job.starburst_query_id,
        next_uri=job.next_uri,
        gcs_path=job.gcs_path,
        row_count=job.row_count,
        size_bytes=job.size_bytes,
        submitted_at=job.submitted_at,
        completed_at=job.completed_at,
        error_message=job.error_message,
        starburst_role=job.starburst_role,
    )


def export_job_to_dict(job: ExportJob) -> dict[str, Any]:
    """Convert domain ExportJob to dict with all ADR-025 fields."""
    return {
        "id": job.id,
        "snapshot_id": job.snapshot_id,
        "job_type": job.job_type,
        "entity_name": job.entity_name,
        "status": job.status.value,
        # Denormalized definition
        "sql": job.sql,
        "column_names": job.column_names,
        "starburst_catalog": job.starburst_catalog,
        "starburst_role": job.starburst_role,
        # Claiming state
        "claimed_by": job.claimed_by,
        "claimed_at": job.claimed_at.isoformat() if job.claimed_at else None,
        # Starburst tracking
        "starburst_query_id": job.starburst_query_id,
        "next_uri": job.next_uri,
        # Polling state
        "next_poll_at": job.next_poll_at.isoformat() if job.next_poll_at else None,
        "poll_count": job.poll_count,
        # Output
        "gcs_path": job.gcs_path,
        "row_count": job.row_count,
        "size_bytes": job.size_bytes,
        "submitted_at": job.submitted_at.isoformat() if job.submitted_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }


@router.post(
    "/snapshots/{snapshot_id}/export-jobs",
    response_model=DataResponse[list[ExportJobResponse]],
    status_code=status.HTTP_201_CREATED,
)
async def create_export_jobs(
    snapshot_id: int,
    request: CreateExportJobsRequest,
    export_job_repo: ExportJobRepoDep,
    snapshot_repo: SnapshotRepoDep,
) -> DataResponse[list[ExportJobResponse]]:
    """Create export jobs for a snapshot.

    Called by export worker when starting export to create job records
    for each node/edge type.

    Args:
        snapshot_id: Snapshot ID
        request: List of export job definitions
        export_job_repo: Export job repository
        snapshot_repo: Snapshot repository

    Returns:
        List of created export jobs

    Raises:
        404: Snapshot not found
        409: Export jobs already exist for this snapshot
    """
    # Verify snapshot exists
    snapshot = await snapshot_repo.get_by_id(snapshot_id)
    if snapshot is None:
        raise NotFoundError("snapshot", snapshot_id)

    # Check if jobs already exist
    existing_jobs = await export_job_repo.list_by_snapshot(snapshot_id)
    if existing_jobs:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "JOBS_ALREADY_EXIST",
                "message": f"Export jobs already exist for snapshot {snapshot_id}",
            },
        )

    # Create jobs
    job_dicts = [
        {
            "job_type": job.job_type,
            "entity_name": job.entity_name,
            "gcs_path": job.gcs_path,
        }
        for job in request.jobs
    ]
    created_jobs = await export_job_repo.create_batch(snapshot_id, job_dicts)

    return DataResponse(data=[export_job_to_response(job) for job in created_jobs])


@router.get(
    "/snapshots/{snapshot_id}/export-jobs",
    response_model=DataResponse[list[ExportJobResponse]],
)
async def list_export_jobs(
    snapshot_id: int,
    export_job_repo: ExportJobRepoDep,
    snapshot_repo: SnapshotRepoDep,
    status_filter: str | None = None,
) -> DataResponse[list[ExportJobResponse]]:
    """List export jobs for a snapshot.

    Called by export worker poller to get current job states.

    Args:
        snapshot_id: Snapshot ID
        export_job_repo: Export job repository
        snapshot_repo: Snapshot repository
        status_filter: Optional status to filter by (pending, running, completed, failed)

    Returns:
        List of export jobs

    Raises:
        404: Snapshot not found
    """
    # Verify snapshot exists
    snapshot = await snapshot_repo.get_by_id(snapshot_id)
    if snapshot is None:
        raise NotFoundError("snapshot", snapshot_id)

    jobs = await export_job_repo.list_by_snapshot(snapshot_id)

    # Filter by status if provided
    if status_filter:
        jobs = [job for job in jobs if job.status.value == status_filter]

    return DataResponse(data=[export_job_to_response(job) for job in jobs])


# =============================================================================
# ADR-025: Database Polling Endpoints (MUST be before /{job_id} routes)
# =============================================================================


@router.post(
    "/export-jobs/claim",
    response_model=DataResponse[ClaimExportJobsResponse],
)
async def claim_export_jobs(
    request: ClaimExportJobsRequest,
    export_job_repo: ExportJobRepoDep,
) -> DataResponse[ClaimExportJobsResponse]:
    """Atomically claim pending export jobs for a worker.

    Uses SELECT ... FOR UPDATE SKIP LOCKED on the server to prevent
    race conditions between multiple workers.

    Args:
        request: Claim request with worker_id and limit
        export_job_repo: Export job repository

    Returns:
        List of claimed jobs with denormalized SQL, columns, and GCS path
    """
    claimed_jobs = await export_job_repo.claim_pending_jobs(
        worker_id=request.worker_id,
        limit=request.limit,
    )

    return DataResponse(
        data=ClaimExportJobsResponse(
            jobs=[export_job_to_dict(job) for job in claimed_jobs]
        )
    )


@router.get(
    "/export-jobs/pollable",
    response_model=DataResponse[PollableExportJobsResponse],
)
async def get_pollable_export_jobs(
    export_job_repo: ExportJobRepoDep,
    limit: int = Query(default=10, ge=1, le=100),
) -> DataResponse[PollableExportJobsResponse]:
    """Get submitted jobs that are ready for Starburst status polling.

    Returns jobs where status='submitted' and next_poll_at <= now.
    Uses FOR UPDATE SKIP LOCKED to prevent multiple workers polling
    the same job.

    Args:
        export_job_repo: Export job repository
        limit: Maximum number of jobs to return

    Returns:
        List of jobs ready for polling
    """
    pollable_jobs = await export_job_repo.get_pollable_jobs(limit=limit)

    return DataResponse(
        data=PollableExportJobsResponse(
            jobs=[export_job_to_dict(job) for job in pollable_jobs]
        )
    )


# =============================================================================
# Individual Job Routes (parameterized /{job_id} - MUST be after specific routes)
# =============================================================================


@router.get(
    "/export-jobs/{job_id}",
    response_model=DataResponse[ExportJobResponse],
)
async def get_export_job(
    job_id: int,
    export_job_repo: ExportJobRepoDep,
) -> DataResponse[ExportJobResponse]:
    """Get a single export job by ID.

    Called by export worker poller to get job details.

    Args:
        job_id: Export job ID
        export_job_repo: Export job repository

    Returns:
        Export job

    Raises:
        404: Export job not found
    """
    job = await export_job_repo.get_by_id(job_id)
    if job is None:
        raise NotFoundError("export_job", job_id)

    return DataResponse(data=export_job_to_response(job))


@router.patch(
    "/export-jobs/{job_id}",
    response_model=DataResponse[ExportJobResponse],
)
async def update_export_job(
    job_id: int,
    request: UpdateExportJobRequest,
    export_job_repo: ExportJobRepoDep,
) -> DataResponse[ExportJobResponse]:
    """Update an export job status.

    Called by export worker to update job status after Starburst submission
    or completion/failure.

    Args:
        job_id: Export job ID
        request: Status update request
        export_job_repo: Export job repository

    Returns:
        Updated export job

    Raises:
        404: Export job not found
    """
    # Verify job exists
    job = await export_job_repo.get_by_id(job_id)
    if job is None:
        raise NotFoundError("export_job", job_id)

    # Update based on new status
    updated_job: ExportJob | None = None

    # Handle both 'running' (legacy) and 'submitted' (ADR-025) statuses
    if request.status in ("running", "submitted"):
        if not request.starburst_query_id or not request.next_uri:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "INVALID_REQUEST",
                    "message": "starburst_query_id and next_uri required for submitted status",
                },
            )
        updated_job = await export_job_repo.mark_submitted(
            job_id=job_id,
            starburst_query_id=request.starburst_query_id,
            next_uri=request.next_uri,
            next_poll_at=request.next_poll_at,
        )
    elif request.status == "completed":
        if request.row_count is None or request.size_bytes is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "INVALID_REQUEST",
                    "message": "row_count and size_bytes required for completed status",
                },
            )
        updated_job = await export_job_repo.mark_completed(
            job_id=job_id,
            row_count=request.row_count,
            size_bytes=request.size_bytes,
        )
    elif request.status == "failed":
        updated_job = await export_job_repo.mark_failed(
            job_id=job_id,
            error_message=request.error_message or "Unknown error",
        )
    elif request.status is None and request.next_uri:
        # Update only next_uri without status change (used during polling)
        await export_job_repo.update_next_uri(job_id=job_id, next_uri=request.next_uri)
        updated_job = await export_job_repo.get_by_id(job_id)

    if updated_job is None:
        raise NotFoundError("export_job", job_id)

    return DataResponse(data=export_job_to_response(updated_job))
