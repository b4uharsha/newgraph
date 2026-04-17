"""K8s Export Worker - Stateless database polling architecture.

This module implements the K8s-native export worker per ADR-025:
1. Claims pending export jobs from Control Plane (atomic, lease-based)
2. Submits UNLOAD queries to Starburst with client_tags for resource group routing
3. Polls Starburst for completion using database-persisted Fibonacci backoff
4. Updates job/snapshot status in Control Plane

Architecture (ADR-025):
- Stateless workers with all state in database (survives restarts)
- KEDA scales based on pending job count (scale-to-zero when idle)
- Starburst resource groups handle query throttling (no client semaphore)
- Three-phase main loop: Claim -> Submit -> Poll

See docs/component-designs/export-worker.design.md for architecture details.
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from datetime import UTC, datetime, timedelta

import structlog

from export_worker.backoff import get_poll_delay
from export_worker.clients.control_plane import ControlPlaneClient
from export_worker.clients.gcs import GCSClient
from export_worker.clients.starburst import StarburstClient
from export_worker.config import Settings, get_settings
from export_worker.exceptions import ControlPlaneError, StarburstError
from export_worker.models import ExportJob, ExportJobStatus


def configure_logging(log_format: str = "json", log_level: str = "INFO") -> None:
    """Configure structured logging for K8s environment."""
    import logging

    level = getattr(logging, log_level.upper(), logging.INFO)

    if log_format == "json":
        processors = [
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        processors = [
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


logger = structlog.get_logger()


class ExportWorker:
    """Stateless export worker using database polling architecture.

    Per ADR-025:
    - Claims pending jobs atomically from Control Plane
    - Submits to Starburst with client_tags for resource group routing
    - Polls using database-persisted state (next_poll_at, poll_count)
    - All state survives worker restarts
    """

    def __init__(self, settings: Settings) -> None:
        """Initialize export worker.

        Args:
            settings: Application settings
        """
        self.settings = settings
        self._shutdown_event = asyncio.Event()
        self._worker_id = os.environ.get("HOSTNAME", f"worker-{os.getpid()}")
        self._logger = logger.bind(component="export_worker", worker_id=self._worker_id)

        # Initialize clients
        self._starburst = StarburstClient.from_config(
            settings.starburst,
            gcp_project=settings.gcp_project,
        )
        self._control_plane = ControlPlaneClient.from_config(settings.control_plane)
        self._gcs = GCSClient.from_config(settings.gcs)

    async def run(self) -> None:
        """Run the main worker loop.

        Three-phase loop per ADR-025:
        1. Claim: Get pending jobs from Control Plane
        2. Submit: Submit UNLOAD to Starburst, update job status
        3. Poll: Check Starburst for pollable jobs, update status

        Loops until shutdown signal received.
        """
        self._logger.info(
            "Starting export worker",
            poll_interval=self.settings.poll_interval_seconds,
            empty_poll_backoff=self.settings.empty_poll_backoff_seconds,
            claim_limit=self.settings.claim_limit,
            poll_limit=self.settings.poll_limit,
            direct_export=self.settings.direct_export,
            starburst_url=self.settings.starburst.url,
            starburst_catalog=self.settings.starburst.catalog,
            starburst_user=self.settings.starburst.user,
            starburst_source=self.settings.starburst.source,
            starburst_client_tags=self.settings.starburst.client_tags,
            starburst_request_timeout=self.settings.starburst.request_timeout_seconds,
            control_plane_url=self.settings.control_plane.url,
            gcp_project=self.settings.gcp_project,
            dry_run=self.settings.dry_run,
        )

        while not self._shutdown_event.is_set():
            work_done = False

            try:
                # Phase 1: Claim pending jobs
                claimed_jobs = await self._claim_phase()
                if claimed_jobs:
                    work_done = True

                # Phase 2: Submit claimed jobs to Starburst
                if claimed_jobs:
                    await self._submit_phase(claimed_jobs)

                # Phase 3: Poll submitted jobs
                polled_jobs = await self._poll_phase()
                if polled_jobs:
                    work_done = True

            except ControlPlaneError as e:
                self._logger.error("Control Plane error in main loop", error=str(e))

            except Exception as e:
                self._logger.exception("Unexpected error in main loop", error=str(e))

            # Backoff based on whether work was done
            if work_done:
                await self._wait_or_shutdown(self.settings.poll_interval_seconds)
            else:
                await self._wait_or_shutdown(self.settings.empty_poll_backoff_seconds)

        self._logger.info("Export worker stopped")

    async def _claim_phase(self) -> list[ExportJob]:
        """Phase 1: Claim pending export jobs.

        Uses atomic claiming via Control Plane to prevent race conditions.

        Returns:
            List of claimed jobs
        """
        try:
            jobs = self._control_plane.claim_export_jobs(
                worker_id=self._worker_id,
                limit=self.settings.claim_limit,
            )
            if jobs:
                self._logger.info(
                    "Claimed pending jobs",
                    count=len(jobs),
                    jobs=[
                        {
                            "job_id": j.id,
                            "snapshot_id": j.snapshot_id,
                            "entity_name": j.entity_name,
                            "job_type": j.job_type,
                            "starburst_catalog": j.starburst_catalog,
                            "gcs_path": j.gcs_path,
                        }
                        for j in jobs
                    ],
                )
            return jobs
        except ControlPlaneError as e:
            self._logger.warning("Failed to claim jobs", error=str(e))
            return []

    async def _submit_phase(self, jobs: list[ExportJob]) -> None:
        """Phase 2: Submit claimed jobs to Starburst in parallel.

        Uses ``asyncio.gather`` so that Starburst I/O for different jobs
        overlaps.  Each ``_submit_job`` call is independent: per-job role
        is passed explicitly to the Starburst client (no shared mutable
        state), and each submission creates its own HTTP session.

        Args:
            jobs: List of claimed jobs to submit
        """
        if self._shutdown_event.is_set():
            return

        await asyncio.gather(*(self._submit_job(job) for job in jobs))

    async def _submit_job(self, job: ExportJob) -> None:
        """Submit a single job to Starburst.

        Args:
            job: Job to submit
        """
        job_log = self._logger.bind(
            job_id=job.id,
            snapshot_id=job.snapshot_id,
            entity_name=job.entity_name,
            job_type=job.job_type,
            starburst_catalog=job.starburst_catalog,
            gcs_path=job.gcs_path,
            column_names=job.column_names,
            sql=job.sql,
        )

        if not job.sql or not job.column_names or not job.starburst_catalog:
            job_log.error(
                "Job missing required fields",
                has_sql=bool(job.sql),
                has_columns=bool(job.column_names),
                has_catalog=bool(job.starburst_catalog),
            )
            await self._mark_job_failed(job, "Job missing sql, column_names, or starburst_catalog")
            return

        # Extract role locally — do NOT mutate self._starburst.role.
        # Each job carries its own starburst_role; passing it explicitly to
        # the Starburst client methods keeps concurrent gather() calls safe.
        starburst_role = getattr(job, "starburst_role", None)
        if starburst_role:
            job_log.info("Using Starburst role", role=starburst_role)
        else:
            # Guard: require use case ID (ADR-102)
            self._logger.error("Job missing starburst_role", job_id=job.id)
            await self._mark_job_failed(job, "Missing use case ID (X-Use-Case-Id header required)")
            return

        # Use direct PyArrow export when flag is set (default)
        if self.settings.direct_export:
            job_log.info("Using direct export (PyArrow)", direct_export=True)
            await self._submit_job_direct_export(job, job_log, starburst_role=starburst_role)
            return

        try:
            job_log.info("Submitting UNLOAD query to Starburst")

            # Submit to Starburst using system.unload
            result = await self._starburst.submit_unload_async(
                sql=job.sql,
                columns=job.column_names,
                destination=job.gcs_path,
                catalog=job.starburst_catalog,
                role=starburst_role,
            )

            # Calculate next poll time using Fibonacci backoff
            now = datetime.now(UTC)
            delay_seconds = get_poll_delay(1)  # First poll
            next_poll_at = now + timedelta(seconds=delay_seconds)

            # Update job status to submitted
            self._control_plane.update_export_job(
                job.id,  # type: ignore
                status=ExportJobStatus.SUBMITTED,
                starburst_query_id=result.query_id,
                next_uri=result.next_uri,
                next_poll_at=next_poll_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                poll_count=1,
                submitted_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            )

            # Transition snapshot from 'pending' to 'creating' if this is the first job
            self._control_plane.update_snapshot_status_if_pending(
                job.snapshot_id,
                "creating",
            )

            job_log.info(
                "Job submitted to Starburst",
                query_id=result.query_id,
                next_poll_at=next_poll_at.isoformat(),
            )

        except StarburstError as e:
            error_msg = str(e)
            # Check if system.unload is not available (fallback to direct export)
            if "not registered" in error_msg.lower() or "function_not_found" in error_msg.lower():
                job_log.warning(
                    "system.unload not available, using direct export fallback",
                    error=error_msg,
                )
                await self._submit_job_direct_export(job, job_log, starburst_role=starburst_role)
            else:
                job_log.error("Failed to submit job to Starburst", error=error_msg)
                await self._mark_job_failed(job, error_msg)

        except Exception as e:
            job_log.exception("Unexpected error submitting job", error=str(e))
            await self._mark_job_failed(job, f"Unexpected error: {e}")

    async def _submit_job_direct_export(
        self, job: ExportJob, job_log, *, starburst_role: str | None = None
    ) -> None:
        """Submit a job using direct PyArrow export (fallback for system.unload).

        This method executes the query, fetches all results, and writes directly
        to GCS using PyArrow. Used when system.unload is not available.

        Args:
            job: Job to export
            job_log: Logger bound to job context
            starburst_role: Per-job Starburst role passed explicitly so that
                            concurrent submissions do not share mutable state.
        """
        try:
            # Transition snapshot to 'creating' before starting
            self._control_plane.update_snapshot_status_if_pending(
                job.snapshot_id,
                "creating",
            )

            job_log.info(
                "Executing direct export via PyArrow",
                starburst_url=self.settings.starburst.url,
                gcp_project=self.settings.gcp_project,
            )
            now = datetime.now(UTC)

            # Execute query and export directly
            row_count, size_bytes = await self._starburst.execute_and_export_async(
                sql=job.sql,
                columns=job.column_names,
                destination=job.gcs_path,
                catalog=job.starburst_catalog,
                role=starburst_role,
            )

            # Mark job as completed immediately (no polling needed)
            completed_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            self._control_plane.update_export_job(
                job.id,  # type: ignore
                status=ExportJobStatus.COMPLETED,
                row_count=row_count,
                size_bytes=size_bytes,
                submitted_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                completed_at=completed_at,
            )

            elapsed_seconds = (datetime.now(UTC) - now).total_seconds()
            job_log.info(
                "Direct export completed",
                row_count=row_count,
                size_bytes=size_bytes,
                elapsed_seconds=round(elapsed_seconds, 2),
            )

            # Create updated job with known completed status to avoid race condition
            updated_job = job.model_copy(
                update={
                    "status": ExportJobStatus.COMPLETED,
                    "row_count": row_count,
                    "size_bytes": size_bytes,
                    "submitted_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "completed_at": completed_at,
                }
            )

            # Check if all jobs for this snapshot are complete
            await self._check_snapshot_complete(job.snapshot_id, job_log, updated_job)

        except StarburstError as e:
            job_log.error("Direct export failed", error=str(e))
            await self._mark_job_failed(job, str(e))

        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
            # Retry on timeout (Starburst cold start can exceed request_timeout)
            if "Timeout" in type(e).__name__ or "timeout" in str(e).lower():
                max_retries = 2
                for retry_num in range(1, max_retries + 1):
                    job_log.warning(
                        f"Starburst timeout, retry {retry_num}/{max_retries}",
                        error=error_msg,
                    )
                    await asyncio.sleep(5)
                    try:
                        row_count, size_bytes = await self._starburst.execute_and_export_async(
                            sql=job.sql,
                            columns=job.column_names,
                            destination=job.gcs_path,
                            catalog=job.starburst_catalog,
                            role=starburst_role,
                        )
                        # Success on retry
                        completed_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
                        self._control_plane.update_export_job(
                            job.id,
                            status=ExportJobStatus.COMPLETED,
                            row_count=row_count,
                            size_bytes=size_bytes,
                            submitted_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                            completed_at=completed_at,
                        )
                        job_log.info(
                            f"Direct export succeeded on retry {retry_num}",
                            row_count=row_count,
                        )
                        await self._check_snapshot_complete(job.snapshot_id, job_log, None)
                        return  # Success — exit the except block
                    except Exception as retry_err:
                        error_msg = f"Retry {retry_num}/{max_retries} failed: {type(retry_err).__name__}: {retry_err}"
                        job_log.warning(error_msg)
                        continue  # Try next retry

                # All retries exhausted
                error_msg = f"Direct export failed after {max_retries} retries: {type(e).__name__}"

            else:
                job_log.exception("Unexpected error in direct export", error=error_msg)

            await self._mark_job_failed(job, f"Direct export error: {error_msg}")

    async def _poll_phase(self) -> list[ExportJob]:
        """Phase 3: Poll submitted jobs for completion.

        Gets jobs where next_poll_at <= now and polls Starburst for status.

        Returns:
            List of jobs that were polled
        """
        try:
            jobs = self._control_plane.get_pollable_export_jobs(
                limit=self.settings.poll_limit,
            )

            for job in jobs:
                if self._shutdown_event.is_set():
                    break
                await self._poll_job(job)

            return jobs

        except ControlPlaneError as e:
            self._logger.warning("Failed to get pollable jobs", error=str(e))
            return []

    async def _poll_job(self, job: ExportJob) -> None:
        """Poll a single job for Starburst query completion.

        Args:
            job: Job to poll
        """
        job_log = self._logger.bind(
            job_id=job.id,
            snapshot_id=job.snapshot_id,
            entity_name=job.entity_name,
            job_type=job.job_type,
            poll_count=job.poll_count,
            starburst_query_id=job.starburst_query_id,
            gcs_path=job.gcs_path,
            starburst_catalog=job.starburst_catalog,
        )

        if not job.next_uri:
            job_log.error("Job missing next_uri for polling")
            await self._mark_job_failed(job, "Missing next_uri for polling")
            return

        try:
            # Poll Starburst
            poll_result = await self._starburst.poll_query_async(job.next_uri)

            if poll_result.state == "FINISHED":
                await self._handle_job_complete(job, job_log)

            elif poll_result.state == "FAILED":
                error_msg = poll_result.error_message or "Query failed"
                # Check if system.unload is not available (fallback to direct export)
                if "not registered" in error_msg.lower() or "function_not_found" in error_msg.lower():
                    job_log.warning(
                        "system.unload failed, using direct export fallback",
                        error=error_msg,
                    )
                    await self._submit_job_direct_export(
                        job, job_log, starburst_role=getattr(job, "starburst_role", None)
                    )
                else:
                    job_log.error("Starburst query failed", error=error_msg)
                    await self._mark_job_failed(job, error_msg)

            else:
                # Still running - schedule next poll
                new_poll_count = job.poll_count + 1
                delay_seconds = get_poll_delay(new_poll_count)
                next_poll_at = datetime.now(UTC) + timedelta(seconds=delay_seconds)

                self._control_plane.update_export_job(
                    job.id,  # type: ignore
                    next_uri=poll_result.next_uri,
                    next_poll_at=next_poll_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    poll_count=new_poll_count,
                )

                job_log.debug(
                    "Query still running",
                    next_poll_at=next_poll_at.isoformat(),
                    poll_count=new_poll_count,
                )

        except StarburstError as e:
            job_log.error("Error polling Starburst", error=str(e))
            # Don't fail the job on poll error - try again next cycle
            # Just schedule next poll
            new_poll_count = job.poll_count + 1
            delay_seconds = get_poll_delay(new_poll_count)
            next_poll_at = datetime.now(UTC) + timedelta(seconds=delay_seconds)

            try:
                self._control_plane.update_export_job(
                    job.id,  # type: ignore
                    next_poll_at=next_poll_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    poll_count=new_poll_count,
                )
            except ControlPlaneError:
                job_log.warning("Failed to update poll schedule after error")

        except Exception as e:
            job_log.exception("Unexpected error polling job", error=str(e))

    async def _handle_job_complete(
        self,
        job: ExportJob,
        log: structlog.BoundLogger,
    ) -> None:
        """Handle a completed export job.

        Counts rows, calculates size, updates job status, and checks if
        snapshot is ready to finalize.

        Args:
            job: Completed job
            log: Bound logger
        """
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        try:
            # Count rows and get size from Parquet files
            row_count, size_bytes = self._gcs.count_parquet_rows(job.gcs_path)

            log.info(
                "Export job completed",
                row_count=row_count,
                size_bytes=size_bytes,
                gcs_path=job.gcs_path,
                entity_name=job.entity_name,
                job_type=job.job_type,
            )

            # Update job status
            self._control_plane.update_export_job(
                job.id,  # type: ignore
                status=ExportJobStatus.COMPLETED,
                row_count=row_count,
                size_bytes=size_bytes,
                completed_at=now,
            )

            # Create updated job with known completed status to avoid race condition
            updated_job = job.model_copy(
                update={
                    "status": ExportJobStatus.COMPLETED,
                    "row_count": row_count,
                    "size_bytes": size_bytes,
                    "completed_at": now,
                }
            )

            # Check if all jobs for this snapshot are complete
            await self._check_snapshot_complete(job.snapshot_id, log, updated_job)

        except Exception as e:
            log.error("Failed to finalize completed job", error=str(e))
            await self._mark_job_failed(job, f"Failed to count rows: {e}")

    async def _check_snapshot_complete(
        self,
        snapshot_id: int,
        log: structlog.BoundLogger,
        updated_job: ExportJob | None = None,
    ) -> None:
        """Check if all jobs for a snapshot are complete and finalize if so.

        Args:
            snapshot_id: Snapshot ID
            log: Bound logger
            updated_job: Optional job we just updated - passed to avoid race conditions
        """
        try:
            result = self._control_plane.get_snapshot_jobs_result(snapshot_id, updated_job)

            if not result.all_complete:
                log.debug("Not all jobs complete yet")
                return

            if result.any_failed:
                log.warning("Snapshot has failed jobs, marking as failed")
                self._control_plane.finalize_snapshot(
                    snapshot_id,
                    success=False,
                    error_message=result.first_error or "One or more export jobs failed",
                )
            else:
                log.info(
                    "All jobs complete, marking snapshot as ready",
                    node_counts=result.node_counts,
                    edge_counts=result.edge_counts,
                    total_size=result.total_size,
                )
                self._control_plane.finalize_snapshot(
                    snapshot_id,
                    success=True,
                    node_counts=result.node_counts,
                    edge_counts=result.edge_counts,
                    size_bytes=result.total_size,
                )

        except ControlPlaneError as e:
            log.error("Failed to check/finalize snapshot", error=str(e))

    async def _mark_job_failed(self, job: ExportJob, error_message: str) -> None:
        """Mark a job as failed and check if snapshot should be finalized.

        Args:
            job: Job that failed
            error_message: Error description
        """
        job_log = self._logger.bind(
            job_id=job.id,
            snapshot_id=job.snapshot_id,
            entity_name=job.entity_name,
            job_type=job.job_type,
            starburst_catalog=job.starburst_catalog,
            gcs_path=job.gcs_path,
        )

        job_log.warning(
            "Marking job as failed",
            error_message=error_message,
            sql=job.sql,
        )

        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            self._control_plane.update_export_job(
                job.id,  # type: ignore
                status=ExportJobStatus.FAILED,
                error_message=error_message,
                completed_at=now,
            )

            # Create updated job with known failed status to avoid race condition
            updated_job = job.model_copy(
                update={
                    "status": ExportJobStatus.FAILED,
                    "error_message": error_message,
                    "completed_at": now,
                }
            )

            # Check if snapshot should be finalized (all jobs done, including this failure)
            await self._check_snapshot_complete(job.snapshot_id, job_log, updated_job)

        except ControlPlaneError as e:
            job_log.warning(
                "Failed to mark job as failed",
                error=str(e),
            )

    async def _wait_or_shutdown(self, seconds: float) -> None:
        """Wait for specified duration or until shutdown.

        Args:
            seconds: Duration to wait
        """
        try:
            await asyncio.wait_for(
                self._shutdown_event.wait(),
                timeout=seconds,
            )
        except TimeoutError:
            pass  # Normal - timeout means continue

    def request_shutdown(self) -> None:
        """Request graceful shutdown."""
        self._logger.info("Shutdown requested")
        self._shutdown_event.set()

    @property
    def is_shutting_down(self) -> bool:
        """Check if shutdown has been requested."""
        return self._shutdown_event.is_set()


async def run_worker(settings: Settings) -> None:
    """Run the export worker.

    Sets up signal handlers and runs the main loop.

    Args:
        settings: Application settings
    """
    configure_logging(settings.log_format, settings.log_level)
    log = logger.bind(component="main")

    worker = ExportWorker(settings)

    # Setup signal handlers
    loop = asyncio.get_running_loop()

    def handle_signal(sig: signal.Signals) -> None:
        log.info("Received signal", signal=sig.name)
        worker.request_shutdown()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, handle_signal, sig)

    log.info("Export worker starting")

    try:
        await worker.run()
    except Exception as e:
        log.exception("Worker error", error=str(e))
        raise
    finally:
        log.info("Export worker exiting")


def main() -> None:
    """Entry point for the K8s export worker."""
    settings = get_settings()
    configure_logging(settings.log_format, settings.log_level)

    logger.info("Starting K8s Export Worker (ADR-025)")
    asyncio.run(run_worker(settings))


if __name__ == "__main__":
    main()
