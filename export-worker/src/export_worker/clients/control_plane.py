"""Control Plane API client for status updates.

This client handles:
- Reporting snapshot status changes
- Sending progress updates
- Checking for cancellation

Service-to-service calls use plain HTTP within the cluster (ADR-104).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)

from export_worker.exceptions import ControlPlaneError
from export_worker.models import (
    ExportJob,
    ExportJobStatus,
    SnapshotJobsResult,
    SnapshotProgress,
    SnapshotStatus,
)

if TYPE_CHECKING:
    from export_worker.config import ControlPlaneConfig

logger = structlog.get_logger()


class ControlPlaneClient:
    """Client for Control Plane internal API."""

    def __init__(
        self,
        base_url: str,
        timeout: int = 30,
        max_retries: int = 5,
    ) -> None:
        """Initialize Control Plane client.

        Args:
            base_url: Control Plane internal URL
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self._logger = logger.bind(component="control_plane")

    @classmethod
    def from_config(cls, config: ControlPlaneConfig) -> ControlPlaneClient:
        """Create client from configuration object."""
        return cls(
            base_url=config.url,
            timeout=config.timeout_seconds,
            max_retries=config.max_retries,
        )

    def _get_headers(self) -> dict[str, str]:
        """Get request headers."""
        return {
            "Content-Type": "application/json",
            "X-Component": "worker",
        }

    @retry(
        retry=retry_if_exception_type((httpx.RequestError, httpx.TimeoutException)),
        stop=stop_after_attempt(5),
        wait=wait_fixed(1),
    )
    def update_snapshot_status(
        self,
        snapshot_id: int,
        status: SnapshotStatus | str,
        *,
        progress: SnapshotProgress | None = None,
        size_bytes: int | None = None,
        node_counts: dict[str, int] | None = None,
        edge_counts: dict[str, int] | None = None,
        error_message: str | None = None,
        failed_step: str | None = None,
    ) -> None:
        """Update snapshot status in Control Plane.

        Args:
            snapshot_id: Snapshot ID
            status: New status
            progress: Progress information
            size_bytes: Total export size (when ready)
            node_counts: Node counts by label (when ready)
            edge_counts: Edge counts by type (when ready)
            error_message: Error message (when failed)
            failed_step: Step that failed (when failed)

        Raises:
            ControlPlaneError: If update fails after retries
        """
        url = f"{self.base_url}/api/internal/snapshots/{snapshot_id}/status"

        # Convert status to string if enum
        status_str = status.value if isinstance(status, SnapshotStatus) else status

        body: dict[str, Any] = {"status": status_str}

        if progress is not None:
            body["progress"] = progress.to_api_dict()
        if size_bytes is not None:
            body["size_bytes"] = size_bytes
        if node_counts is not None:
            body["node_counts"] = node_counts
        if edge_counts is not None:
            body["edge_counts"] = edge_counts
        if error_message is not None:
            body["error_message"] = error_message
        if failed_step is not None:
            body["failed_step"] = failed_step

        self._logger.info(
            "Updating snapshot status",
            snapshot_id=snapshot_id,
            status=status_str,
        )

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.patch(url, json=body, headers=self._get_headers())

                if response.status_code != 200:
                    raise ControlPlaneError(
                        f"Failed to update snapshot status: {response.status_code}",
                        status_code=response.status_code,
                        response_body=response.text,
                    )

                self._logger.debug(
                    "Snapshot status updated",
                    snapshot_id=snapshot_id,
                    status=status_str,
                )

        except httpx.RequestError as e:
            raise ControlPlaneError(f"Request failed: {e}") from e

    @retry(
        retry=retry_if_exception_type((httpx.RequestError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_fixed(1),
    )
    def get_snapshot_status(self, snapshot_id: int) -> SnapshotStatus:
        """Get current snapshot status (for cancellation checks).

        Args:
            snapshot_id: Snapshot ID

        Returns:
            Current snapshot status

        Raises:
            ControlPlaneError: If request fails
        """
        url = f"{self.base_url}/api/internal/snapshots/{snapshot_id}/status"

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url, headers=self._get_headers())

                if response.status_code != 200:
                    raise ControlPlaneError(
                        f"Failed to get snapshot status: {response.status_code}",
                        status_code=response.status_code,
                        response_body=response.text,
                    )

                data = response.json()
                status_str = data.get("data", {}).get("status")

                if not status_str:
                    raise ControlPlaneError(
                        "Invalid response: missing status",
                        response_body=response.text,
                    )

                return SnapshotStatus(status_str)

        except httpx.RequestError as e:
            raise ControlPlaneError(f"Request failed: {e}") from e

    def is_cancelled(self, snapshot_id: int) -> bool:
        """Check if a snapshot has been cancelled.

        Args:
            snapshot_id: Snapshot ID

        Returns:
            True if snapshot is cancelled, False otherwise
        """
        try:
            status = self.get_snapshot_status(snapshot_id)
            return status == SnapshotStatus.CANCELLED
        except ControlPlaneError as e:
            self._logger.warning(
                "Failed to check cancellation status",
                snapshot_id=snapshot_id,
                error=str(e),
            )
            return False

    def update_snapshot_status_if_pending(
        self,
        snapshot_id: int,
        new_status: str,
    ) -> bool:
        """Update snapshot status only if currently pending.

        Used to transition snapshot from 'pending' to 'creating' when first
        job is submitted. Avoids race conditions by checking current status.

        Args:
            snapshot_id: Snapshot ID
            new_status: New status to set (e.g., 'creating')

        Returns:
            True if status was updated, False if not pending
        """
        try:
            current_status = self.get_snapshot_status(snapshot_id)
            if current_status != SnapshotStatus.PENDING:
                return False

            self.update_snapshot_status(snapshot_id, new_status)
            return True

        except ControlPlaneError as e:
            self._logger.warning(
                "Failed to update snapshot status",
                snapshot_id=snapshot_id,
                new_status=new_status,
                error=str(e),
            )
            return False

    # -------------------------------------------------------------------------
    # Export Job Methods (ADR-025 Database Polling Architecture)
    # -------------------------------------------------------------------------

    @retry(
        retry=retry_if_exception_type((httpx.RequestError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_fixed(1),
    )
    def get_pending_export_jobs(self, snapshot_id: int) -> list[ExportJob]:
        """Get pending export jobs for a snapshot.

        Called by Export Submitter to find jobs to process.

        Args:
            snapshot_id: Snapshot ID

        Returns:
            List of pending export jobs

        Raises:
            ControlPlaneError: If request fails
        """
        url = f"{self.base_url}/api/internal/snapshots/{snapshot_id}/export-jobs"

        self._logger.debug(
            "Getting pending export jobs",
            snapshot_id=snapshot_id,
        )

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(
                    url,
                    params={"status_filter": "pending"},
                    headers=self._get_headers(),
                )

                if response.status_code != 200:
                    raise ControlPlaneError(
                        f"Failed to get export jobs: {response.status_code}",
                        status_code=response.status_code,
                        response_body=response.text,
                    )

                data = response.json().get("data", [])
                return [ExportJob.from_api_dict(job) for job in data]

        except httpx.RequestError as e:
            raise ControlPlaneError(f"Request failed: {e}") from e

    @retry(
        retry=retry_if_exception_type((httpx.RequestError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_fixed(1),
    )
    def start_export_job(
        self,
        job_id: int,
        starburst_query_id: str,
        next_uri: str,
        submitted_at: str,
    ) -> ExportJob:
        """Mark an export job as started with Starburst query details.

        Called by Export Submitter after submitting a Starburst query.

        Args:
            job_id: Export job ID
            starburst_query_id: Query ID from Starburst
            next_uri: Polling URI for query status
            submitted_at: Submission timestamp

        Returns:
            Updated export job

        Raises:
            ControlPlaneError: If update fails
        """
        url = f"{self.base_url}/api/internal/export-jobs/{job_id}"

        self._logger.debug(
            "Starting export job",
            job_id=job_id,
            starburst_query_id=starburst_query_id,
        )

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.patch(
                    url,
                    json={
                        "status": "running",
                        "starburst_query_id": starburst_query_id,
                        "next_uri": next_uri,
                        "submitted_at": submitted_at,
                    },
                    headers=self._get_headers(),
                )

                if response.status_code != 200:
                    self._logger.error(
                        "Failed to start export job",
                        job_id=job_id,
                        status_code=response.status_code,
                        response_body=response.text,
                    )
                    raise ControlPlaneError(
                        f"Failed to start export job: {response.status_code}",
                        status_code=response.status_code,
                        response_body=response.text,
                    )

                data = response.json().get("data", {})
                return ExportJob.from_api_dict(data)

        except httpx.RequestError as e:
            raise ControlPlaneError(f"Request failed: {e}") from e

    @retry(
        retry=retry_if_exception_type((httpx.RequestError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_fixed(1),
    )
    def update_export_job(
        self,
        job_id: int,
        *,
        status: ExportJobStatus | None = None,
        starburst_query_id: str | None = None,
        next_uri: str | None = None,
        next_poll_at: str | None = None,
        poll_count: int | None = None,
        row_count: int | None = None,
        size_bytes: int | None = None,
        error_message: str | None = None,
        submitted_at: str | None = None,
        completed_at: str | None = None,
    ) -> ExportJob:
        """Update an export job in Control Plane.

        Called by Export Worker to update job status after claiming/polling.

        Args:
            job_id: Export job ID
            status: New status
            starburst_query_id: Query ID from Starburst (set when submitted)
            next_uri: Updated polling URI
            next_poll_at: When to poll next (ISO 8601, for stateless backoff)
            poll_count: Current poll count (for Fibonacci backoff calculation)
            row_count: Row count (when completed)
            size_bytes: Size in bytes (when completed)
            error_message: Error message (when failed)
            submitted_at: Submission timestamp (set when submitted)
            completed_at: Completion timestamp (when completed/failed)

        Returns:
            Updated export job

        Raises:
            ControlPlaneError: If update fails
        """
        url = f"{self.base_url}/api/internal/export-jobs/{job_id}"

        body: dict[str, Any] = {}
        if status is not None:
            body["status"] = status.value
        if starburst_query_id is not None:
            body["starburst_query_id"] = starburst_query_id
        if next_uri is not None:
            body["next_uri"] = next_uri
        if next_poll_at is not None:
            body["next_poll_at"] = next_poll_at
        if poll_count is not None:
            body["poll_count"] = poll_count
        if row_count is not None:
            body["row_count"] = row_count
        if size_bytes is not None:
            body["size_bytes"] = size_bytes
        if error_message is not None:
            body["error_message"] = error_message
        if submitted_at is not None:
            body["submitted_at"] = submitted_at
        if completed_at is not None:
            body["completed_at"] = completed_at

        self._logger.debug(
            "Updating export job",
            job_id=job_id,
            updates=list(body.keys()),
        )

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.patch(url, json=body, headers=self._get_headers())

                if response.status_code != 200:
                    raise ControlPlaneError(
                        f"Failed to update export job: {response.status_code}",
                        status_code=response.status_code,
                        response_body=response.text,
                    )

                data = response.json().get("data", {})
                return ExportJob.from_api_dict(data)

        except httpx.RequestError as e:
            raise ControlPlaneError(f"Request failed: {e}") from e

    @retry(
        retry=retry_if_exception_type((httpx.RequestError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_fixed(1),
    )
    def get_export_job(self, job_id: int) -> ExportJob:
        """Get an export job by ID.

        Args:
            job_id: Export job ID

        Returns:
            Export job

        Raises:
            ControlPlaneError: If request fails or job not found
        """
        url = f"{self.base_url}/api/internal/export-jobs/{job_id}"

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url, headers=self._get_headers())

                if response.status_code == 404:
                    raise ControlPlaneError(
                        f"Export job not found: {job_id}",
                        status_code=404,
                    )

                if response.status_code != 200:
                    raise ControlPlaneError(
                        f"Failed to get export job: {response.status_code}",
                        status_code=response.status_code,
                        response_body=response.text,
                    )

                data = response.json().get("data", {})
                return ExportJob.from_api_dict(data)

        except httpx.RequestError as e:
            raise ControlPlaneError(f"Request failed: {e}") from e

    @retry(
        retry=retry_if_exception_type((httpx.RequestError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_fixed(1),
    )
    def list_export_jobs(self, snapshot_id: int) -> list[ExportJob]:
        """List all export jobs for a snapshot.

        Args:
            snapshot_id: Snapshot ID

        Returns:
            List of export jobs

        Raises:
            ControlPlaneError: If request fails
        """
        url = f"{self.base_url}/api/internal/snapshots/{snapshot_id}/export-jobs"

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url, headers=self._get_headers())

                if response.status_code != 200:
                    raise ControlPlaneError(
                        f"Failed to list export jobs: {response.status_code}",
                        status_code=response.status_code,
                        response_body=response.text,
                    )

                data = response.json().get("data", [])
                return [ExportJob.from_api_dict(job) for job in data]

        except httpx.RequestError as e:
            raise ControlPlaneError(f"Request failed: {e}") from e

    def check_all_jobs_complete(self, snapshot_id: int) -> tuple[bool, bool]:
        """Check if all export jobs for a snapshot are complete.

        Used by Export Poller to determine if snapshot is ready.

        Args:
            snapshot_id: Snapshot ID

        Returns:
            Tuple of (all_complete, any_failed)
            - all_complete: True if no jobs are pending/running
            - any_failed: True if any job failed
        """
        jobs = self.list_export_jobs(snapshot_id)

        if not jobs:
            return True, False

        any_failed = any(job.status == ExportJobStatus.FAILED for job in jobs)
        all_complete = all(
            job.status in (ExportJobStatus.COMPLETED, ExportJobStatus.FAILED) for job in jobs
        )

        return all_complete, any_failed

    def finalize_snapshot(
        self,
        snapshot_id: int,
        *,
        success: bool,
        node_counts: dict[str, int] | None = None,
        edge_counts: dict[str, int] | None = None,
        size_bytes: int | None = None,
        error_message: str | None = None,
    ) -> None:
        """Finalize a snapshot after all export jobs complete.

        Called by Export Worker when the last job completes.

        Args:
            snapshot_id: Snapshot ID
            success: True if all jobs succeeded
            node_counts: Node counts by label (on success)
            edge_counts: Edge counts by type (on success)
            size_bytes: Total size in bytes (on success)
            error_message: Error message (on failure)
        """
        if success:
            self.update_snapshot_status(
                snapshot_id,
                SnapshotStatus.READY,
                node_counts=node_counts,
                edge_counts=edge_counts,
                size_bytes=size_bytes,
            )
        else:
            self.update_snapshot_status(
                snapshot_id,
                SnapshotStatus.FAILED,
                error_message=error_message,
            )

    # -------------------------------------------------------------------------
    # ADR-025: Database Polling - Claim and Poll Endpoints
    # -------------------------------------------------------------------------

    @retry(
        retry=retry_if_exception_type((httpx.RequestError, httpx.TimeoutException)),
        stop=stop_after_attempt(5),
        wait=wait_fixed(1),
    )
    def claim_export_jobs(self, worker_id: str, limit: int = 10) -> list[ExportJob]:
        """Atomically claim pending export jobs for this worker.

        Uses SELECT ... FOR UPDATE SKIP LOCKED on the server to prevent
        race conditions between multiple workers.

        Args:
            worker_id: Unique identifier for this worker (pod name)
            limit: Maximum number of jobs to claim (default: 10)

        Returns:
            List of claimed jobs with denormalized SQL, columns, and GCS path

        Raises:
            ControlPlaneError: If request fails
        """
        url = f"{self.base_url}/api/internal/export-jobs/claim"

        self._logger.debug(
            "Claiming export jobs",
            worker_id=worker_id,
            limit=limit,
        )

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    url,
                    json={"worker_id": worker_id, "limit": limit},
                    headers=self._get_headers(),
                )

                if response.status_code != 200:
                    raise ControlPlaneError(
                        f"Failed to claim jobs: {response.status_code}",
                        status_code=response.status_code,
                        response_body=response.text,
                    )

                data = response.json().get("data", {})
                jobs = data.get("jobs", [])

                if jobs:
                    self._logger.info(
                        "Claimed export jobs",
                        worker_id=worker_id,
                        count=len(jobs),
                    )

                return [ExportJob.from_api_dict(job) for job in jobs]

        except httpx.RequestError as e:
            raise ControlPlaneError(f"Request failed: {e}") from e

    @retry(
        retry=retry_if_exception_type((httpx.RequestError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_fixed(1),
    )
    def get_pollable_export_jobs(self, limit: int = 10) -> list[ExportJob]:
        """Get submitted jobs that are ready for Starburst status polling.

        Returns jobs where status='submitted' and next_poll_at <= now.
        Uses FOR UPDATE SKIP LOCKED to prevent multiple workers polling
        the same job.

        Args:
            limit: Maximum number of jobs to return

        Returns:
            List of jobs ready for polling

        Raises:
            ControlPlaneError: If request fails
        """
        url = f"{self.base_url}/api/internal/export-jobs/pollable"

        self._logger.debug(
            "Getting pollable export jobs",
            limit=limit,
        )

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(
                    url,
                    params={"limit": limit},
                    headers=self._get_headers(),
                )

                if response.status_code != 200:
                    raise ControlPlaneError(
                        f"Failed to get pollable jobs: {response.status_code}",
                        status_code=response.status_code,
                        response_body=response.text,
                    )

                data = response.json().get("data", {})
                jobs = data.get("jobs", [])

                if jobs:
                    self._logger.debug(
                        "Found pollable export jobs",
                        count=len(jobs),
                    )

                return [ExportJob.from_api_dict(job) for job in jobs]

        except httpx.RequestError as e:
            raise ControlPlaneError(f"Request failed: {e}") from e

    def get_snapshot_jobs_result(
        self,
        snapshot_id: int,
        updated_job: ExportJob | None = None,
    ) -> SnapshotJobsResult:
        """Check status of all export jobs for a snapshot.

        Returns aggregated result for determining if snapshot is complete.

        Args:
            snapshot_id: Snapshot ID
            updated_job: Optional job we just updated - used to avoid race conditions
                where the fetched job list doesn't yet reflect our recent update.

        Returns:
            SnapshotJobsResult with completion status and aggregated counts
        """
        jobs = self.list_export_jobs(snapshot_id)

        if not jobs:
            return SnapshotJobsResult(
                all_complete=True,
                any_failed=False,
            )

        # If we just updated a job, replace the fetched version with our known state
        # to avoid race conditions where the fetch returns stale data
        if updated_job is not None and updated_job.id is not None:
            jobs = [
                updated_job if job.id == updated_job.id else job
                for job in jobs
            ]

        any_failed = False
        first_error = None
        node_counts: dict[str, int] = {}
        edge_counts: dict[str, int] = {}
        total_size = 0

        for job in jobs:
            if job.status == ExportJobStatus.FAILED:
                any_failed = True
                if first_error is None:
                    first_error = job.error_message

            if job.status == ExportJobStatus.COMPLETED:
                if job.job_type == "node" and job.row_count is not None:
                    node_counts[job.entity_name] = job.row_count
                elif job.job_type == "edge" and job.row_count is not None:
                    edge_counts[job.entity_name] = job.row_count
                if job.size_bytes:
                    total_size += job.size_bytes

        all_complete = all(
            job.status in (ExportJobStatus.COMPLETED, ExportJobStatus.FAILED)
            for job in jobs
        )

        return SnapshotJobsResult(
            all_complete=all_complete,
            any_failed=any_failed,
            first_error=first_error,
            node_counts=node_counts,
            edge_counts=edge_counts,
            total_size=total_size,
        )
