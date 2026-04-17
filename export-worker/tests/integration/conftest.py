"""Integration test fixtures for Export Worker (ADR-025).

Provides mocked clients that simulate real behavior for integration testing:
- MockStarburstClient: Simulates Trino REST API responses
- MockControlPlaneClient: Simulates Control Plane database operations
- MockGCSClient: Simulates GCS Parquet operations

These fixtures enable testing the full export flow without real external services.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest

from export_worker.clients.starburst import QueryPollResult, QuerySubmissionResult
from export_worker.models import ExportJob, ExportJobStatus, SnapshotJobsResult

# =============================================================================
# Mock Starburst Client
# =============================================================================


class MockStarburstClient:
    """Mock Starburst client that simulates Trino REST API behavior.

    Configurable behavior:
    - polls_until_finished: Number of poll calls before returning FINISHED
    - fail_queries: List of entity names that should fail
    - poll_delay_ms: Simulated delay per poll (default: 0 for fast tests)
    """

    def __init__(
        self,
        polls_until_finished: int = 3,
        fail_queries: list[str] | None = None,
        poll_delay_ms: int = 0,
    ) -> None:
        self.polls_until_finished = polls_until_finished
        self.fail_queries = fail_queries or []
        self.poll_delay_ms = poll_delay_ms
        self.client_tags = ["graph-olap-export"]
        self.source = "graph-olap-export-worker"

        # Track state per query
        self._query_poll_counts: dict[str, int] = {}
        self._query_entity_map: dict[str, str] = {}
        self._submitted_queries: list[str] = []

    async def submit_unload_async(
        self,
        sql: str,
        columns: list[str],
        destination: str,
        catalog: str,
        client_tags: list[str] | None = None,
        source: str | None = None,
    ) -> QuerySubmissionResult:
        """Simulate submitting UNLOAD query to Starburst."""
        query_id = f"query-{len(self._submitted_queries) + 1}"
        next_uri = f"http://starburst.test/v1/query/{query_id}/1"

        # Extract entity name from destination path for failure simulation
        entity_name = destination.rstrip("/").split("/")[-1]
        self._query_entity_map[query_id] = entity_name
        self._query_poll_counts[query_id] = 0
        self._submitted_queries.append(query_id)

        # Check if this query should fail immediately
        if entity_name in self.fail_queries:
            raise Exception(f"Simulated submission failure for {entity_name}")

        return QuerySubmissionResult(
            query_id=query_id,
            next_uri=next_uri,
        )

    async def poll_query_async(self, next_uri: str) -> QueryPollResult:
        """Simulate polling Starburst for query status."""
        # Extract query_id from URI
        parts = next_uri.split("/")
        query_id = parts[-2] if len(parts) >= 2 else "unknown"

        if self.poll_delay_ms > 0:
            await asyncio.sleep(self.poll_delay_ms / 1000)

        # Increment poll count
        self._query_poll_counts[query_id] = self._query_poll_counts.get(query_id, 0) + 1
        poll_count = self._query_poll_counts[query_id]

        entity_name = self._query_entity_map.get(query_id, "")

        # Check if query should fail during polling
        if entity_name in self.fail_queries:
            return QueryPollResult(
                state="FAILED",
                next_uri=None,
                error_message=f"Query failed for {entity_name}: simulated error",
            )

        # Return FINISHED after configured number of polls
        if poll_count >= self.polls_until_finished:
            return QueryPollResult(
                state="FINISHED",
                next_uri=None,
                error_message=None,
            )

        # Still running
        next_poll_uri = f"http://starburst.test/v1/query/{query_id}/{poll_count + 1}"
        return QueryPollResult(
            state="RUNNING",
            next_uri=next_poll_uri,
            error_message=None,
        )

    @property
    def submitted_query_count(self) -> int:
        """Number of queries submitted."""
        return len(self._submitted_queries)


@pytest.fixture
def mock_starburst_factory():
    """Factory for creating configured MockStarburstClient instances."""

    def _create(
        polls_until_finished: int = 3,
        fail_queries: list[str] | None = None,
        poll_delay_ms: int = 0,
    ) -> MockStarburstClient:
        return MockStarburstClient(
            polls_until_finished=polls_until_finished,
            fail_queries=fail_queries,
            poll_delay_ms=poll_delay_ms,
        )

    return _create


@pytest.fixture
def mock_starburst() -> MockStarburstClient:
    """Default MockStarburstClient for simple tests."""
    return MockStarburstClient(polls_until_finished=2)


# =============================================================================
# Mock Control Plane Client
# =============================================================================


class MockControlPlaneClient:
    """Mock Control Plane client that simulates database operations.

    Simulates:
    - Job claiming with atomic behavior
    - Job status updates
    - Snapshot finalization
    - Cancellation detection
    """

    def __init__(self) -> None:
        self._jobs: dict[int, ExportJob] = {}
        self._snapshots: dict[int, dict[str, Any]] = {}
        self._next_job_id = 1
        self._finalized_snapshots: list[dict[str, Any]] = []
        self._cancelled_snapshots: set[int] = set()

    def add_pending_job(
        self,
        snapshot_id: int,
        job_type: str,
        entity_name: str,
        sql: str,
        column_names: list[str],
        gcs_path: str,
        starburst_catalog: str = "analytics",
    ) -> ExportJob:
        """Add a pending job to the mock database."""
        job = ExportJob(
            id=self._next_job_id,
            snapshot_id=snapshot_id,
            job_type=job_type,
            entity_name=entity_name,
            status=ExportJobStatus.PENDING,
            sql=sql,
            column_names=column_names,
            starburst_catalog=starburst_catalog,
            gcs_path=gcs_path,
        )
        self._jobs[job.id] = job
        self._next_job_id += 1

        # Initialize snapshot if not exists
        if snapshot_id not in self._snapshots:
            self._snapshots[snapshot_id] = {"status": "pending"}

        return job

    def cancel_snapshot(self, snapshot_id: int) -> None:
        """Mark a snapshot as cancelled."""
        self._cancelled_snapshots.add(snapshot_id)
        if snapshot_id in self._snapshots:
            self._snapshots[snapshot_id]["status"] = "cancelled"

    def claim_export_jobs(
        self,
        worker_id: str,
        limit: int = 10,
    ) -> list[ExportJob]:
        """Simulate atomic job claiming (synchronous per actual interface)."""
        claimed = []
        now = datetime.now(UTC).isoformat()

        for job in list(self._jobs.values()):
            if job.status == ExportJobStatus.PENDING and len(claimed) < limit:
                # Simulate atomic claim
                job.status = ExportJobStatus.CLAIMED
                job.claimed_by = worker_id
                job.claimed_at = now
                claimed.append(job)

        return claimed

    def get_pollable_export_jobs(self, limit: int = 10) -> list[ExportJob]:
        """Get jobs that are ready to be polled (synchronous per actual interface)."""
        now = datetime.now(UTC)
        pollable = []

        for job in self._jobs.values():
            if job.status == ExportJobStatus.SUBMITTED:
                # Check if next_poll_at has passed
                if job.next_poll_at:
                    poll_time = datetime.fromisoformat(job.next_poll_at.replace("Z", "+00:00"))
                    if poll_time <= now and len(pollable) < limit:
                        pollable.append(job)
                elif len(pollable) < limit:
                    pollable.append(job)

        return pollable

    def update_export_job(
        self,
        job_id: int,
        status: ExportJobStatus | str | None = None,
        starburst_query_id: str | None = None,
        next_uri: str | None = None,
        next_poll_at: str | None = None,
        poll_count: int | None = None,
        submitted_at: str | None = None,
        row_count: int | None = None,
        size_bytes: int | None = None,
        error_message: str | None = None,
        completed_at: str | None = None,
    ) -> ExportJob:
        """Update export job status (synchronous per actual interface)."""
        job = self._jobs.get(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        if status is not None:
            if isinstance(status, str):
                status = ExportJobStatus(status)
            job.status = status

        if starburst_query_id is not None:
            job.starburst_query_id = starburst_query_id
        if next_uri is not None:
            job.next_uri = next_uri
        if next_poll_at is not None:
            job.next_poll_at = next_poll_at
        if poll_count is not None:
            job.poll_count = poll_count
        if submitted_at is not None:
            job.submitted_at = submitted_at
        if row_count is not None:
            job.row_count = row_count
        if size_bytes is not None:
            job.size_bytes = size_bytes
        if error_message is not None:
            job.error_message = error_message

        return job

    def get_snapshot_jobs_result(
        self,
        snapshot_id: int,
        updated_job: ExportJob | None = None,
    ) -> SnapshotJobsResult:
        """Get aggregated job status for snapshot (synchronous per actual interface).

        Args:
            snapshot_id: Snapshot ID
            updated_job: Optional recently updated job - used to avoid race conditions
                         by including the job's latest state even if not yet persisted.
        """
        jobs = [j for j in self._jobs.values() if j.snapshot_id == snapshot_id]

        # If updated_job provided, use its state instead of the stored one
        if updated_job:
            jobs = [updated_job if j.id == updated_job.id else j for j in jobs]

        all_complete = all(j.status in (ExportJobStatus.COMPLETED, ExportJobStatus.FAILED) for j in jobs)
        any_failed = any(j.status == ExportJobStatus.FAILED for j in jobs)

        node_counts = {
            j.entity_name: j.row_count or 0
            for j in jobs
            if j.job_type == "node" and j.status == ExportJobStatus.COMPLETED
        }
        edge_counts = {
            j.entity_name: j.row_count or 0
            for j in jobs
            if j.job_type == "edge" and j.status == ExportJobStatus.COMPLETED
        }
        total_size = sum(j.size_bytes or 0 for j in jobs if j.status == ExportJobStatus.COMPLETED)

        first_error = None
        for j in jobs:
            if j.status == ExportJobStatus.FAILED and j.error_message:
                first_error = j.error_message
                break

        return SnapshotJobsResult(
            all_complete=all_complete,
            any_failed=any_failed,
            first_error=first_error,
            node_counts=node_counts,
            edge_counts=edge_counts,
            total_size=total_size,
        )

    def finalize_snapshot(
        self,
        snapshot_id: int,
        success: bool,
        node_counts: dict[str, int] | None = None,
        edge_counts: dict[str, int] | None = None,
        size_bytes: int | None = None,
        error_message: str | None = None,
    ) -> None:
        """Finalize snapshot status (synchronous per actual interface)."""
        self._finalized_snapshots.append({
            "snapshot_id": snapshot_id,
            "success": success,
            "node_counts": node_counts,
            "edge_counts": edge_counts,
            "size_bytes": size_bytes,
            "error_message": error_message,
        })

        if snapshot_id in self._snapshots:
            self._snapshots[snapshot_id]["status"] = "ready" if success else "failed"

    def is_cancelled(self, snapshot_id: int) -> bool:
        """Check if snapshot is cancelled (synchronous per actual interface)."""
        return snapshot_id in self._cancelled_snapshots

    def update_snapshot_status(
        self,
        snapshot_id: int,
        status: str,
        **kwargs: Any,
    ) -> None:
        """Update snapshot status (synchronous per actual interface)."""
        if snapshot_id not in self._snapshots:
            self._snapshots[snapshot_id] = {}
        self._snapshots[snapshot_id]["status"] = status

    def update_snapshot_status_if_pending(
        self,
        snapshot_id: int,
        new_status: str,
    ) -> bool:
        """Update snapshot status only if currently 'pending'.

        This is used to atomically transition from pending -> creating
        when the first job is submitted.

        Returns:
            True if status was updated, False if snapshot wasn't pending.
        """
        if snapshot_id not in self._snapshots:
            self._snapshots[snapshot_id] = {"status": "pending"}

        if self._snapshots[snapshot_id].get("status") == "pending":
            self._snapshots[snapshot_id]["status"] = new_status
            return True
        return False

    def get_job(self, job_id: int) -> ExportJob | None:
        """Get job by ID (for test assertions)."""
        return self._jobs.get(job_id)

    @property
    def finalized_snapshots(self) -> list[dict[str, Any]]:
        """Get list of finalized snapshots (for test assertions)."""
        return self._finalized_snapshots


@pytest.fixture
def mock_control_plane() -> MockControlPlaneClient:
    """Create MockControlPlaneClient for integration tests."""
    return MockControlPlaneClient()


# =============================================================================
# Mock GCS Client
# =============================================================================


class MockGCSClient:
    """Mock GCS client that simulates Parquet operations."""

    def __init__(
        self,
        default_row_count: int = 1000,
        default_size_bytes: int = 1024 * 1024,
    ) -> None:
        self.default_row_count = default_row_count
        self.default_size_bytes = default_size_bytes
        self._path_results: dict[str, tuple[int, int]] = {}
        self._fail_paths: set[str] = set()

    def set_path_result(self, gcs_path: str, row_count: int, size_bytes: int) -> None:
        """Set specific result for a GCS path."""
        self._path_results[gcs_path] = (row_count, size_bytes)

    def set_path_failure(self, gcs_path: str) -> None:
        """Make a path fail when accessed."""
        self._fail_paths.add(gcs_path)

    async def count_parquet_rows_async(self, gcs_path: str) -> tuple[int, int]:
        """Simulate counting Parquet rows."""
        if gcs_path in self._fail_paths:
            raise Exception(f"Simulated GCS error for {gcs_path}")

        if gcs_path in self._path_results:
            return self._path_results[gcs_path]

        return (self.default_row_count, self.default_size_bytes)

    def count_parquet_rows(self, gcs_path: str) -> tuple[int, int]:
        """Synchronous version for compatibility."""
        if gcs_path in self._fail_paths:
            raise Exception(f"Simulated GCS error for {gcs_path}")

        if gcs_path in self._path_results:
            return self._path_results[gcs_path]

        return (self.default_row_count, self.default_size_bytes)


@pytest.fixture
def mock_gcs() -> MockGCSClient:
    """Create MockGCSClient for integration tests."""
    return MockGCSClient()


# =============================================================================
# Integration Test Fixtures
# =============================================================================


@pytest.fixture
def sample_snapshot_jobs(mock_control_plane: MockControlPlaneClient) -> list[ExportJob]:
    """Create sample jobs for a snapshot with 2 nodes and 1 edge."""
    snapshot_id = 1

    jobs = [
        mock_control_plane.add_pending_job(
            snapshot_id=snapshot_id,
            job_type="node",
            entity_name="Customer",
            sql="SELECT customer_id, name, email FROM analytics.customers",
            column_names=["customer_id", "name", "email"],
            gcs_path="gs://test-bucket/snapshot-1/nodes/Customer/",
        ),
        mock_control_plane.add_pending_job(
            snapshot_id=snapshot_id,
            job_type="node",
            entity_name="Product",
            sql="SELECT product_id, name, price FROM analytics.products",
            column_names=["product_id", "name", "price"],
            gcs_path="gs://test-bucket/snapshot-1/nodes/Product/",
        ),
        mock_control_plane.add_pending_job(
            snapshot_id=snapshot_id,
            job_type="edge",
            entity_name="PURCHASED",
            sql="SELECT customer_id, product_id, amount FROM analytics.purchases",
            column_names=["customer_id", "product_id", "amount"],
            gcs_path="gs://test-bucket/snapshot-1/edges/PURCHASED/",
        ),
    ]

    return jobs
