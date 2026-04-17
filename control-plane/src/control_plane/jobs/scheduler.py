"""Background job scheduler using APScheduler.

Manages periodic execution of lifecycle management and reconciliation jobs.
"""

import time
from typing import TYPE_CHECKING, Any

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from control_plane.config import Settings
from control_plane.jobs import metrics

if TYPE_CHECKING:
    from control_plane.cache.schema_cache import SchemaMetadataCache

logger = structlog.get_logger(__name__)


class BackgroundJobScheduler:
    """Manages background job scheduling and execution.

    Uses APScheduler to run periodic jobs for:
    - Reconciliation (orphan pod cleanup)
    - Lifecycle enforcement (TTL/inactivity timeouts)
    - Export reconciliation (export worker crash recovery)
    - Schema cache refresh (Starburst metadata)
    - Instance orchestration (waiting_for_snapshot -> starting transitions)
    - Resource monitor (dynamic memory monitoring and proactive resize)
    """

    def __init__(self, settings: Settings):
        """Initialize scheduler with settings.

        Args:
            settings: Application settings (contains job intervals)
        """
        self._settings = settings
        self._scheduler: AsyncIOScheduler | None = None
        self._running = False
        self._consecutive_failures: dict[str, int] = {}  # Track consecutive failures per job
        self._schema_cache: "SchemaMetadataCache | None" = None

    def set_schema_cache(self, cache: "SchemaMetadataCache") -> None:
        """Set the schema cache reference for the schema_cache job.

        Must be called before the first schema_cache job runs.

        Args:
            cache: SchemaMetadataCache instance
        """
        self._schema_cache = cache
        logger.info("scheduler_schema_cache_set")

    async def start(self) -> None:
        """Start the background job scheduler."""
        if self._running:
            logger.warning("scheduler_already_running")
            return

        logger.info("scheduler_starting")

        # Create scheduler
        self._scheduler = AsyncIOScheduler(
            timezone="UTC",
            job_defaults={
                "coalesce": True,  # Combine missed executions
                "max_instances": 1,  # Only one instance of each job at a time
                "misfire_grace_time": 60,  # Ignore misfires within 60s
            },
        )

        # Register jobs
        await self._register_jobs()

        # Start scheduler
        self._scheduler.start()
        self._running = True

        logger.info(
            "scheduler_started",
            jobs_registered=len(self._scheduler.get_jobs()),
        )

    async def _register_jobs(self) -> None:
        """Register all background jobs with the scheduler."""
        if self._scheduler is None:
            return

        # Import job functions (lazy import to avoid circular dependencies)
        from control_plane.jobs.export_reconciliation import run_export_reconciliation_job
        from control_plane.jobs.instance_orchestration import run_instance_orchestration_job
        from control_plane.jobs.lifecycle import run_lifecycle_job
        from control_plane.jobs.reconciliation import run_reconciliation_job
        from control_plane.jobs.resource_monitor import run_resource_monitor_job
        from control_plane.jobs.schema_cache import run_schema_cache_job

        # Reconciliation job (orphan pod cleanup, state drift detection)
        self._scheduler.add_job(
            func=self._wrap_job(run_reconciliation_job, "reconciliation"),
            trigger=IntervalTrigger(seconds=self._settings.reconciliation_job_interval_seconds),
            id="reconciliation",
            name="Reconciliation Job",
            replace_existing=True,
        )
        logger.info(
            "job_registered",
            job_id="reconciliation",
            interval_seconds=self._settings.reconciliation_job_interval_seconds,
        )

        # Lifecycle job (TTL and inactivity timeout enforcement)
        self._scheduler.add_job(
            func=self._wrap_job(run_lifecycle_job, "lifecycle"),
            trigger=IntervalTrigger(seconds=self._settings.lifecycle_job_interval_seconds),
            id="lifecycle",
            name="Lifecycle Job",
            replace_existing=True,
        )
        logger.info(
            "job_registered",
            job_id="lifecycle",
            interval_seconds=self._settings.lifecycle_job_interval_seconds,
        )

        # Export reconciliation job (export worker crash recovery)
        # Run every 1 minute for faster crash recovery (reduced from 5 minutes)
        self._scheduler.add_job(
            func=self._wrap_job(run_export_reconciliation_job, "export_reconciliation"),
            trigger=IntervalTrigger(seconds=5),  # Match orchestration interval
            id="export_reconciliation",
            name="Export Reconciliation Job",
            replace_existing=True,
        )
        logger.info(
            "job_registered",
            job_id="export_reconciliation",
            interval_seconds=5,
        )

        # Schema cache job (Starburst metadata refresh)
        self._scheduler.add_job(
            func=self._wrap_job(run_schema_cache_job, "schema_cache"),
            trigger=IntervalTrigger(seconds=self._settings.schema_cache_job_interval_seconds),
            id="schema_cache",
            name="Schema Cache Job",
            replace_existing=True,
        )
        logger.info(
            "job_registered",
            job_id="schema_cache",
            interval_seconds=self._settings.schema_cache_job_interval_seconds,
        )

        # Instance orchestration job (waiting_for_snapshot -> starting transitions)
        self._scheduler.add_job(
            func=self._wrap_job(run_instance_orchestration_job, "instance_orchestration"),
            trigger=IntervalTrigger(seconds=self._settings.instance_orchestration_job_interval_seconds),
            id="instance_orchestration",
            name="Instance Orchestration Job",
            replace_existing=True,
        )
        logger.info(
            "job_registered",
            job_id="instance_orchestration",
            interval_seconds=self._settings.instance_orchestration_job_interval_seconds,
        )

        # Resource monitor job (dynamic memory monitoring and proactive resize)
        # Run every 60 seconds to check memory usage and trigger resize if needed
        # Only runs if sizing_enabled is True
        self._scheduler.add_job(
            func=self._wrap_job(run_resource_monitor_job, "resource_monitor"),
            trigger=IntervalTrigger(seconds=60),
            id="resource_monitor",
            name="Resource Monitor Job",
            replace_existing=True,
        )
        logger.info(
            "job_registered",
            job_id="resource_monitor",
            interval_seconds=60,
        )

    def _wrap_job(self, job_func: Any, job_name: str) -> Any:
        """Wrap a job function with error handling, logging, and metrics.

        Args:
            job_func: Async function to execute
            job_name: Name of the job for logging

        Returns:
            Wrapped async function
        """
        async def wrapped():
            logger.info("job_started", job=job_name)
            start_time = time.time()
            status = "success"

            try:
                # Schema cache job needs the cache instance
                if job_name == "schema_cache" and self._schema_cache is not None:
                    await job_func(self._schema_cache)
                else:
                    await job_func()
                logger.info("job_completed", job=job_name)

                # Record success
                self._consecutive_failures[job_name] = 0
                metrics.job_last_success_timestamp_seconds.labels(job_name=job_name).set(time.time())
                metrics.job_health_status.labels(job_name=job_name).set(1)

            except Exception as e:
                status = "failed"
                logger.exception("job_failed", job=job_name, error=str(e))

                # Record failure
                self._consecutive_failures[job_name] = self._consecutive_failures.get(job_name, 0) + 1

                # Mark unhealthy if 3+ consecutive failures
                if self._consecutive_failures[job_name] >= 3:
                    metrics.job_health_status.labels(job_name=job_name).set(0)
                    logger.error(
                        "job_unhealthy",
                        job=job_name,
                        consecutive_failures=self._consecutive_failures[job_name],
                    )

            finally:
                # Record metrics
                duration = time.time() - start_time
                metrics.job_execution_total.labels(job_name=job_name, status=status).inc()
                metrics.job_execution_duration_seconds.labels(job_name=job_name).observe(duration)

        return wrapped

    async def stop(self) -> None:
        """Stop the background job scheduler gracefully."""
        if not self._running or self._scheduler is None:
            return

        logger.info("scheduler_stopping")

        # Shutdown scheduler (wait for running jobs to finish)
        self._scheduler.shutdown(wait=True)
        self._running = False

        logger.info("scheduler_stopped")

    def get_job_stats(self) -> dict[str, Any]:
        """Get statistics about registered jobs.

        Returns:
            Dictionary with job information
        """
        if self._scheduler is None:
            return {"running": False, "jobs": []}

        jobs = []
        for job in self._scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            })

        return {
            "running": self._running,
            "jobs": jobs,
        }
