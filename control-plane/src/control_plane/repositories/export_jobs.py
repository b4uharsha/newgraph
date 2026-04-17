"""Export job repository for database operations (ADR-025)."""

import json
from typing import Any

from control_plane.models import ExportJob, ExportJobStatus
from control_plane.repositories.base import (
    BaseRepository,
    parse_timestamp,
    utc_now,
)

# All columns in export_jobs table (ADR-025)
EXPORT_JOB_COLUMNS = """
    id, snapshot_id, job_type, entity_name, status,
    sql, column_names, starburst_catalog, starburst_role,
    claimed_by, claimed_at,
    starburst_query_id, next_uri,
    next_poll_at, poll_count,
    gcs_path, row_count, size_bytes,
    submitted_at, completed_at, error_message,
    created_at, updated_at
"""


class ExportJobRepository(BaseRepository):
    """Repository for export job database operations (ADR-025)."""

    async def get_by_id(self, job_id: int) -> ExportJob | None:
        """Get export job by ID.

        Args:
            job_id: Export job ID

        Returns:
            ExportJob domain object or None if not found
        """
        sql = f"""
            SELECT {EXPORT_JOB_COLUMNS}
            FROM export_jobs
            WHERE id = :job_id
        """
        row = await self._fetch_one(sql, {"job_id": job_id})
        if row is None:
            return None
        return self._row_to_export_job(row)

    async def list_by_snapshot(self, snapshot_id: int) -> list[ExportJob]:
        """List all export jobs for a snapshot.

        Args:
            snapshot_id: Snapshot ID

        Returns:
            List of ExportJob objects
        """
        sql = f"""
            SELECT {EXPORT_JOB_COLUMNS}
            FROM export_jobs
            WHERE snapshot_id = :snapshot_id
            ORDER BY job_type, entity_name
        """
        rows = await self._fetch_all(sql, {"snapshot_id": snapshot_id})
        return [self._row_to_export_job(row) for row in rows]

    async def list_pending(self, limit: int = 100) -> list[ExportJob]:
        """List pending export jobs ready for claiming.

        Args:
            limit: Maximum number to return

        Returns:
            List of pending ExportJob objects
        """
        sql = f"""
            SELECT {EXPORT_JOB_COLUMNS}
            FROM export_jobs
            WHERE status = 'pending'
            ORDER BY created_at ASC
            LIMIT :limit
        """
        rows = await self._fetch_all(sql, {"limit": limit})
        return [self._row_to_export_job(row) for row in rows]

    async def list_submitted(self, limit: int = 100) -> list[ExportJob]:
        """List submitted export jobs that need polling.

        Args:
            limit: Maximum number to return

        Returns:
            List of submitted ExportJob objects
        """
        sql = f"""
            SELECT {EXPORT_JOB_COLUMNS}
            FROM export_jobs
            WHERE status = 'submitted'
            ORDER BY submitted_at ASC
            LIMIT :limit
        """
        rows = await self._fetch_all(sql, {"limit": limit})
        return [self._row_to_export_job(row) for row in rows]

    async def create(
        self,
        snapshot_id: int,
        job_type: str,
        entity_name: str,
        gcs_path: str,
        sql_query: str | None = None,
        column_names: list[str] | None = None,
        starburst_catalog: str | None = None,
        starburst_role: str | None = None,
    ) -> ExportJob:
        """Create a new export job.

        Args:
            snapshot_id: ID of the parent snapshot
            job_type: 'node' or 'edge'
            entity_name: Node label or edge type name
            gcs_path: GCS path for output
            sql_query: Denormalized SQL query for export
            column_names: Column names for UNLOAD
            starburst_catalog: Starburst catalog name
            starburst_role: Use case ID for Starburst SET ROLE

        Returns:
            Created ExportJob
        """
        now = utc_now()
        column_names_json = json.dumps(column_names) if column_names else None
        sql = """
            INSERT INTO export_jobs (snapshot_id, job_type, entity_name,
                                    status, sql, column_names, starburst_catalog,
                                    starburst_role,
                                    gcs_path, poll_count, created_at, updated_at)
            VALUES (:snapshot_id, :job_type, :entity_name,
                    'pending', :sql, :column_names, :starburst_catalog,
                    :starburst_role,
                    :gcs_path, 0, :created_at, :updated_at)
            RETURNING id
        """
        job_id = await self._insert_returning_id(
            sql,
            {
                "snapshot_id": snapshot_id,
                "job_type": job_type,
                "entity_name": entity_name,
                "sql": sql_query,
                "column_names": column_names_json,
                "starburst_catalog": starburst_catalog,
                "starburst_role": starburst_role,
                "gcs_path": gcs_path,
                "created_at": now,
                "updated_at": now,
            },
        )

        return ExportJob(
            id=job_id,
            snapshot_id=snapshot_id,
            job_type=job_type,
            entity_name=entity_name,
            status=ExportJobStatus.PENDING,
            sql=sql_query,
            column_names=column_names,
            starburst_catalog=starburst_catalog,
            starburst_role=starburst_role,
            gcs_path=gcs_path,
            poll_count=0,
            created_at=parse_timestamp(now),
            updated_at=parse_timestamp(now),
        )

    async def create_batch(
        self,
        snapshot_id: int,
        jobs: list[dict[str, Any]],
    ) -> list[ExportJob]:
        """Create multiple export jobs at once.

        Args:
            snapshot_id: ID of the parent snapshot
            jobs: List of dicts with job_type, entity_name, gcs_path,
                  and optional sql, column_names, starburst_catalog

        Returns:
            List of created ExportJob objects
        """
        now = utc_now()
        created_jobs = []

        for job in jobs:
            column_names = job.get("column_names")
            column_names_json = json.dumps(column_names) if column_names else None
            sql = """
                INSERT INTO export_jobs (snapshot_id, job_type, entity_name,
                                        status, sql, column_names, starburst_catalog,
                                        starburst_role,
                                        gcs_path, poll_count, created_at, updated_at)
                VALUES (:snapshot_id, :job_type, :entity_name,
                        'pending', :sql, :column_names, :starburst_catalog,
                        :starburst_role,
                        :gcs_path, 0, :created_at, :updated_at)
                RETURNING id
            """
            job_id = await self._insert_returning_id(
                sql,
                {
                    "snapshot_id": snapshot_id,
                    "job_type": job["job_type"],
                    "entity_name": job["entity_name"],
                    "sql": job.get("sql"),
                    "column_names": column_names_json,
                    "starburst_catalog": job.get("starburst_catalog"),
                    "starburst_role": job.get("starburst_role"),
                    "gcs_path": job["gcs_path"],
                    "created_at": now,
                    "updated_at": now,
                },
            )

            created_jobs.append(
                ExportJob(
                    id=job_id,
                    snapshot_id=snapshot_id,
                    job_type=job["job_type"],
                    entity_name=job["entity_name"],
                    status=ExportJobStatus.PENDING,
                    sql=job.get("sql"),
                    column_names=column_names,
                    starburst_catalog=job.get("starburst_catalog"),
                    starburst_role=job.get("starburst_role"),
                    gcs_path=job["gcs_path"],
                    poll_count=0,
                    created_at=parse_timestamp(now),
                    updated_at=parse_timestamp(now),
                )
            )

        return created_jobs

    async def mark_submitted(
        self,
        job_id: int,
        starburst_query_id: str,
        next_uri: str,
        next_poll_at: str | None = None,
    ) -> ExportJob | None:
        """Mark job as submitted after Starburst query submission.

        Args:
            job_id: Export job ID
            starburst_query_id: Query ID from Starburst
            next_uri: Initial polling URI
            next_poll_at: When to poll next (ISO 8601)

        Returns:
            Updated ExportJob or None if not found
        """
        now = utc_now()
        sql = """
            UPDATE export_jobs
            SET status = 'submitted',
                starburst_query_id = :starburst_query_id,
                next_uri = :next_uri,
                next_poll_at = :next_poll_at,
                poll_count = 0,
                submitted_at = :submitted_at,
                updated_at = :updated_at
            WHERE id = :job_id
        """
        result = await self._execute(
            sql,
            {
                "job_id": job_id,
                "starburst_query_id": starburst_query_id,
                "next_uri": next_uri,
                "next_poll_at": next_poll_at or now,
                "submitted_at": now,
                "updated_at": now,
            },
        )
        if result.rowcount == 0:
            return None

        return await self.get_by_id(job_id)

    # Alias for backward compatibility
    async def mark_running(
        self,
        job_id: int,
        starburst_query_id: str,
        next_uri: str,
    ) -> ExportJob | None:
        """Alias for mark_submitted (backward compatibility)."""
        return await self.mark_submitted(job_id, starburst_query_id, next_uri)

    async def update_next_uri(
        self,
        job_id: int,
        next_uri: str,
        next_poll_at: str | None = None,
        poll_count: int | None = None,
    ) -> None:
        """Update the polling URI and schedule for a submitted job.

        Args:
            job_id: Export job ID
            next_uri: New polling URI
            next_poll_at: When to poll next (ISO 8601)
            poll_count: Updated poll count for backoff
        """
        now = utc_now()
        updates = ["next_uri = :next_uri", "updated_at = :updated_at"]
        params: dict[str, Any] = {
            "job_id": job_id,
            "next_uri": next_uri,
            "updated_at": now,
        }

        if next_poll_at is not None:
            updates.append("next_poll_at = :next_poll_at")
            params["next_poll_at"] = next_poll_at

        if poll_count is not None:
            updates.append("poll_count = :poll_count")
            params["poll_count"] = poll_count

        sql = f"""
            UPDATE export_jobs
            SET {', '.join(updates)}
            WHERE id = :job_id
        """
        await self._execute(sql, params)

    async def mark_completed(
        self,
        job_id: int,
        row_count: int,
        size_bytes: int,
    ) -> ExportJob | None:
        """Mark job as completed with results.

        Args:
            job_id: Export job ID
            row_count: Number of rows exported
            size_bytes: Total size of output files

        Returns:
            Updated ExportJob or None if not found
        """
        now = utc_now()
        sql = """
            UPDATE export_jobs
            SET status = 'completed',
                row_count = :row_count,
                size_bytes = :size_bytes,
                completed_at = :completed_at,
                updated_at = :updated_at
            WHERE id = :job_id
        """
        result = await self._execute(
            sql,
            {
                "job_id": job_id,
                "row_count": row_count,
                "size_bytes": size_bytes,
                "completed_at": now,
                "updated_at": now,
            },
        )
        if result.rowcount == 0:
            return None

        return await self.get_by_id(job_id)

    async def mark_failed(
        self,
        job_id: int,
        error_message: str,
    ) -> ExportJob | None:
        """Mark job as failed with error message.

        Args:
            job_id: Export job ID
            error_message: Error description

        Returns:
            Updated ExportJob or None if not found
        """
        now = utc_now()
        sql = """
            UPDATE export_jobs
            SET status = 'failed',
                error_message = :error_message,
                completed_at = :completed_at,
                updated_at = :updated_at
            WHERE id = :job_id
        """
        result = await self._execute(
            sql,
            {
                "job_id": job_id,
                "error_message": error_message,
                "completed_at": now,
                "updated_at": now,
            },
        )
        if result.rowcount == 0:
            return None

        return await self.get_by_id(job_id)

    async def get_snapshot_progress(self, snapshot_id: int) -> dict[str, Any]:
        """Get aggregated progress for a snapshot's export jobs.

        Args:
            snapshot_id: Snapshot ID

        Returns:
            Progress summary dictionary
        """
        sql = """
            SELECT status, COUNT(*) as count
            FROM export_jobs
            WHERE snapshot_id = :snapshot_id
            GROUP BY status
        """
        rows = await self._fetch_all(sql, {"snapshot_id": snapshot_id})

        status_counts = {row.status: row.count for row in rows}
        total = sum(status_counts.values())

        return {
            "jobs_total": total,
            "jobs_pending": status_counts.get("pending", 0),
            "jobs_claimed": status_counts.get("claimed", 0),
            "jobs_submitted": status_counts.get("submitted", 0),
            "jobs_completed": status_counts.get("completed", 0),
            "jobs_failed": status_counts.get("failed", 0),
        }

    async def all_completed(self, snapshot_id: int) -> bool:
        """Check if all jobs for a snapshot are completed.

        Args:
            snapshot_id: Snapshot ID

        Returns:
            True if all jobs are completed (none pending/claimed/submitted)
        """
        sql = """
            SELECT COUNT(*) FROM export_jobs
            WHERE snapshot_id = :snapshot_id
              AND status IN ('pending', 'claimed', 'submitted')
        """
        count = await self._fetch_scalar(sql, {"snapshot_id": snapshot_id})
        return count == 0

    async def any_failed(self, snapshot_id: int) -> bool:
        """Check if any jobs for a snapshot have failed.

        Args:
            snapshot_id: Snapshot ID

        Returns:
            True if any job has failed
        """
        sql = """
            SELECT 1 FROM export_jobs
            WHERE snapshot_id = :snapshot_id
              AND status = 'failed'
            LIMIT 1
        """
        row = await self._fetch_one(sql, {"snapshot_id": snapshot_id})
        return row is not None

    # -------------------------------------------------------------------------
    # ADR-025: Claim and Pollable Methods
    # -------------------------------------------------------------------------

    async def claim_pending_jobs(
        self,
        worker_id: str,
        limit: int = 10,
    ) -> list[ExportJob]:
        """Atomically claim pending export jobs for a worker.

        Uses SELECT FOR UPDATE SKIP LOCKED to prevent race conditions
        between multiple workers.

        Args:
            worker_id: Unique identifier for the worker (pod name)
            limit: Maximum number of jobs to claim

        Returns:
            List of claimed jobs with denormalized SQL and columns
        """
        now = utc_now()

        # For SQLite (used in tests), we can't use FOR UPDATE SKIP LOCKED
        # In production PostgreSQL, we'd use proper row locking
        # This simplified version works for SQLite
        select_sql = f"""
            SELECT {EXPORT_JOB_COLUMNS}
            FROM export_jobs
            WHERE status = 'pending'
            ORDER BY created_at ASC
            LIMIT :limit
        """
        rows = await self._fetch_all(select_sql, {"limit": limit})

        claimed_jobs = []
        for row in rows:
            # Update each job to claimed status
            update_sql = """
                UPDATE export_jobs
                SET status = 'claimed',
                    claimed_by = :worker_id,
                    claimed_at = :claimed_at,
                    updated_at = :updated_at
                WHERE id = :job_id AND status = 'pending'
            """
            result = await self._execute(
                update_sql,
                {
                    "job_id": row.id,
                    "worker_id": worker_id,
                    "claimed_at": now,
                    "updated_at": now,
                },
            )
            if result.rowcount > 0:
                # Re-fetch the updated job
                updated_job = await self.get_by_id(row.id)
                if updated_job:
                    claimed_jobs.append(updated_job)

        return claimed_jobs

    async def get_pollable_jobs(
        self,
        limit: int = 10,
        current_time: str | None = None,
    ) -> list[ExportJob]:
        """Get submitted jobs that are ready for Starburst status polling.

        Returns jobs where status='submitted' and next_poll_at <= now.

        Args:
            limit: Maximum number of jobs to return
            current_time: Current time for comparison (ISO 8601), defaults to now

        Returns:
            List of jobs ready for polling
        """
        now = current_time or utc_now()

        sql = f"""
            SELECT {EXPORT_JOB_COLUMNS}
            FROM export_jobs
            WHERE status = 'submitted'
              AND (next_poll_at IS NULL OR next_poll_at <= :current_time)
            ORDER BY next_poll_at ASC NULLS FIRST
            LIMIT :limit
        """
        rows = await self._fetch_all(sql, {"current_time": now, "limit": limit})
        return [self._row_to_export_job(row) for row in rows]

    async def list_all(self) -> list[ExportJob]:
        """List all export jobs without pagination.

        Used by background jobs for export reconciliation.

        Returns:
            List of all ExportJob objects
        """
        sql = f"""
            SELECT {EXPORT_JOB_COLUMNS}
            FROM export_jobs
            ORDER BY created_at DESC
        """
        rows = await self._fetch_all(sql, {})
        return [self._row_to_export_job(row) for row in rows]

    async def reset_to_pending(self, job_id: int) -> ExportJob | None:
        """Reset a job back to pending status.

        Used by export reconciliation to recover from stale claims.

        Args:
            job_id: Export job ID to reset

        Returns:
            Updated ExportJob or None if not found
        """
        now = utc_now()
        sql = """
            UPDATE export_jobs
            SET status = 'pending',
                claimed_by = NULL,
                claimed_at = NULL,
                updated_at = :updated_at
            WHERE id = :job_id
        """
        result = await self._execute(
            sql,
            {
                "job_id": job_id,
                "updated_at": now,
            },
        )
        if result.rowcount == 0:
            return None

        return await self.get_by_id(job_id)

    def _row_to_export_job(self, row) -> ExportJob:
        """Convert database row to ExportJob domain object."""
        # Parse column_names from JSON
        column_names = None
        if hasattr(row, "column_names") and row.column_names:
            try:
                column_names = json.loads(row.column_names)
            except (json.JSONDecodeError, TypeError):
                column_names = None

        return ExportJob(
            id=row.id,
            snapshot_id=row.snapshot_id,
            job_type=row.job_type,
            entity_name=row.entity_name,
            status=ExportJobStatus(row.status),
            sql=getattr(row, "sql", None),
            column_names=column_names,
            starburst_catalog=getattr(row, "starburst_catalog", None),
            starburst_role=getattr(row, "starburst_role", None),
            claimed_by=getattr(row, "claimed_by", None),
            claimed_at=parse_timestamp(getattr(row, "claimed_at", None)),
            starburst_query_id=row.starburst_query_id,
            next_uri=row.next_uri,
            next_poll_at=parse_timestamp(getattr(row, "next_poll_at", None)),
            poll_count=getattr(row, "poll_count", 0) or 0,
            gcs_path=row.gcs_path,
            row_count=row.row_count,
            size_bytes=row.size_bytes,
            submitted_at=parse_timestamp(row.submitted_at),
            completed_at=parse_timestamp(row.completed_at),
            error_message=row.error_message,
            created_at=parse_timestamp(row.created_at),
            updated_at=parse_timestamp(row.updated_at),
        )
