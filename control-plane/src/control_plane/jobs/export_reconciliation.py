"""Export reconciliation job for export worker crash recovery.

Handles recovery from export worker crashes by:
1. Resetting stale claims (jobs claimed but worker crashed)
2. Checking orphaned submissions (jobs submitted but Starburst query lost)
3. Finalizing snapshots (all jobs completed but snapshot still "creating")

Runs every 5 minutes (fixed interval matching worker claim timeout).
"""

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import func, select

from control_plane.infrastructure.database import get_session
from control_plane.infrastructure.tables import export_jobs
from control_plane.jobs import metrics
from control_plane.models import ExportJobStatus, SnapshotStatus
from control_plane.repositories.export_jobs import ExportJobRepository
from control_plane.repositories.snapshots import SnapshotRepository

logger = structlog.get_logger(__name__)

# Stale claim threshold: if claimed for > 10 minutes, assume worker crashed
STALE_CLAIM_THRESHOLD = timedelta(minutes=10)


async def run_export_reconciliation_job(session=None) -> None:
    """Recover from export worker crashes and finalize completed snapshots.

    Phases:
    1. Reset stale claims - Export jobs claimed > 10 minutes ago
    2. Finalize snapshots - All jobs completed but snapshot still "creating"

    Args:
        session: Optional database session (for testing). If None, creates a new session.
    """
    logger.info("export_reconciliation_job_started")

    # Use provided session or create a new one
    if session is not None:
        await _run_export_reconciliation_with_session(session)
    else:
        async with get_session() as session:
            await _run_export_reconciliation_with_session(session)


async def _run_export_reconciliation_with_session(session) -> None:
    """Internal export reconciliation logic with provided session."""
    export_job_repo = ExportJobRepository(session)
    snapshot_repo = SnapshotRepository(session)

    now = datetime.now(UTC)

    # Phase 1: Reset stale claims
    stale_claimed = await _find_stale_claimed_jobs(export_job_repo, now)
    stale_reset = await _reset_stale_claims(export_job_repo, stale_claimed)

    # Phase 2: Finalize snapshots with all jobs completed
    ready_snapshots = await _find_snapshots_ready_to_finalize(
        snapshot_repo,
        export_job_repo,
    )
    snapshots_finalized = await _finalize_snapshots(snapshot_repo, ready_snapshots, export_job_repo)

    # Update export jobs status gauge
    export_job_counts_result = await session.execute(
        select(export_jobs.c.status, func.count(export_jobs.c.id)).group_by(export_jobs.c.status)
    )
    for status, count in export_job_counts_result:
        metrics.export_jobs_by_status_total.labels(status=status).set(count)

    # Update export queue depth metric (Export pipeline health)
    pending_count = await session.scalar(
        select(func.count(export_jobs.c.id)).where(export_jobs.c.status == "pending")
    )
    metrics.export_queue_depth.set(pending_count or 0)

    # Record metrics
    metrics.export_reconciliation_passes_total.inc()
    metrics.stale_export_claims_detected_total.inc(len(stale_claimed))
    metrics.stale_export_claims_reset_total.inc(stale_reset)
    metrics.snapshots_ready_to_finalize_total.inc(len(ready_snapshots))
    metrics.snapshots_finalized_total.inc(snapshots_finalized)

    logger.info(
        "export_reconciliation_job_completed",
        stale_claims_reset=stale_reset,
        snapshots_finalized=snapshots_finalized,
    )


async def _find_stale_claimed_jobs(repo: ExportJobRepository, now: datetime) -> list:
    """Find export jobs with stale claims.

    A claim is stale if:
    - status = 'claimed'
    - claimed_at > STALE_CLAIM_THRESHOLD ago

    Args:
        repo: Export job repository
        now: Current timestamp

    Returns:
        List of stale claimed jobs
    """
    all_jobs = await repo.list_all()

    stale_threshold = now - STALE_CLAIM_THRESHOLD
    stale = []

    for job in all_jobs:
        if job.status == ExportJobStatus.CLAIMED:
            if job.claimed_at and job.claimed_at < stale_threshold:
                stale.append(job)

    return stale


async def _reset_stale_claims(repo: ExportJobRepository, jobs: list) -> int:
    """Reset stale claimed jobs back to pending.

    Args:
        repo: Export job repository
        jobs: List of stale claimed jobs

    Returns:
        Number of jobs successfully reset
    """
    reset_count = 0

    for job in jobs:
        try:
            logger.warning(
                "stale_claim_detected",
                job_id=job.id,
                snapshot_id=job.snapshot_id,
                job_type=job.job_type,
                entity_name=job.entity_name,
                claimed_by=job.claimed_by,
                claimed_at=job.claimed_at.isoformat() if job.claimed_at else None,
            )

            # Reset to pending
            await repo.reset_to_pending(job.id)

            logger.info(
                "stale_claim_reset",
                job_id=job.id,
                snapshot_id=job.snapshot_id,
            )
            reset_count += 1

        except Exception as e:
            logger.error(
                "stale_claim_reset_failed",
                job_id=job.id,
                snapshot_id=job.snapshot_id,
                error=str(e),
            )

    return reset_count


async def _find_snapshots_ready_to_finalize(
    snapshot_repo: SnapshotRepository,
    export_job_repo: ExportJobRepository,
) -> list:
    """Find snapshots with all export jobs completed but still in "creating" status.

    Args:
        snapshot_repo: Snapshot repository
        export_job_repo: Export job repository

    Returns:
        List of snapshots ready to finalize
    """
    # Get all creating snapshots
    all_snapshots = await snapshot_repo.list_all()
    creating_snapshots = [s for s in all_snapshots if s.status == SnapshotStatus.CREATING]

    ready = []

    for snapshot in creating_snapshots:
        # Get jobs for this snapshot
        jobs = await export_job_repo.list_by_snapshot(snapshot.id)

        if not jobs:
            # No jobs yet (snapshot just created)
            continue

        # Check if all jobs are completed
        all_completed = all(job.status == ExportJobStatus.COMPLETED for job in jobs)

        if all_completed:
            ready.append(snapshot)

    return ready


async def _finalize_snapshots(
    repo: SnapshotRepository,
    snapshots: list,
    export_job_repo: ExportJobRepository,
) -> int:
    """Finalize snapshots by setting status to "ready" with aggregated counts.

    Aggregates node_counts, edge_counts, and size_bytes from completed export jobs.

    Args:
        repo: Snapshot repository
        snapshots: List of snapshots to finalize
        export_job_repo: Export job repository for fetching job data

    Returns:
        Number of snapshots successfully finalized
    """
    finalized_count = 0

    for snapshot in snapshots:
        try:
            # Get completed jobs for this snapshot to aggregate counts
            jobs = await export_job_repo.list_by_snapshot(snapshot.id)

            # Aggregate counts from completed jobs
            node_counts: dict[str, int] = {}
            edge_counts: dict[str, int] = {}
            total_size = 0

            for job in jobs:
                if job.status == ExportJobStatus.COMPLETED and job.row_count is not None:
                    if job.job_type == "node":
                        node_counts[job.entity_name] = job.row_count
                    elif job.job_type == "edge":
                        edge_counts[job.entity_name] = job.row_count
                    if job.size_bytes:
                        total_size += job.size_bytes

            logger.info(
                "snapshot_ready_to_finalize",
                snapshot_id=snapshot.id,
                name=snapshot.name,
                node_counts=node_counts,
                edge_counts=edge_counts,
                total_size=total_size,
            )

            # Update status to ready with aggregated counts
            await repo.update_status(
                snapshot_id=snapshot.id,
                status=SnapshotStatus.READY,
                node_counts=node_counts or None,
                edge_counts=edge_counts or None,
                size_bytes=total_size or None,
                error_message=None,
            )

            logger.info(
                "snapshot_finalized",
                snapshot_id=snapshot.id,
                name=snapshot.name,
            )
            finalized_count += 1

        except Exception as e:
            logger.error(
                "snapshot_finalization_failed",
                snapshot_id=snapshot.id,
                error=str(e),
            )

    return finalized_count
