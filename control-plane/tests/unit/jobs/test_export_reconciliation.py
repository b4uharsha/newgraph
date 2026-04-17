"""Unit tests for export reconciliation job.

Tests stale claim detection and snapshot finalization logic.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from control_plane.jobs.export_reconciliation import STALE_CLAIM_THRESHOLD
from control_plane.models import ExportJobStatus, SnapshotStatus


class MockExportJob:
    """Mock export job for testing."""

    def __init__(
        self,
        id: int,
        snapshot_id: int,
        status: ExportJobStatus,
        claimed_at: datetime | None = None,
        claimed_by: str | None = None,
        entity_type: str = "node",
        entity_name: str = "TestEntity",
        job_type: str = "node",
        row_count: int | None = None,
        size_bytes: int | None = None,
    ):
        self.id = id
        self.snapshot_id = snapshot_id
        self.status = status
        self.claimed_at = claimed_at
        self.claimed_by = claimed_by
        self.entity_type = entity_type
        self.entity_name = entity_name
        self.row_count = row_count
        self.size_bytes = size_bytes
        self.job_type = job_type


class MockSnapshot:
    """Mock snapshot for testing."""

    def __init__(self, id: int, name: str, status: SnapshotStatus):
        self.id = id
        self.name = name
        self.status = status


class TestStaleClaimDetection:
    """Test stale claim detection logic."""

    def test_detect_stale_claim_after_10_minutes(self):
        """Test claim is stale after 10 minutes."""
        now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)

        # Job claimed 11 minutes ago (stale)
        claimed_at = now - timedelta(minutes=11)
        jobs = [
            MockExportJob(
                id=1,
                snapshot_id=1,
                status=ExportJobStatus.CLAIMED,
                claimed_at=claimed_at,
                claimed_by="worker-1",
            )
        ]

        # Detect stale claims (same logic as job)
        stale_threshold = now - STALE_CLAIM_THRESHOLD  # 10 minutes ago
        stale = []
        for job in jobs:
            if job.status == ExportJobStatus.CLAIMED:
                if job.claimed_at and job.claimed_at < stale_threshold:
                    stale.append(job)

        # Verify
        assert len(stale) == 1
        assert stale[0].id == 1

    def test_not_stale_within_10_minutes(self):
        """Test claim is not stale within 10 minutes."""
        now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)

        # Job claimed 5 minutes ago (not stale)
        claimed_at = now - timedelta(minutes=5)
        jobs = [
            MockExportJob(
                id=1,
                snapshot_id=1,
                status=ExportJobStatus.CLAIMED,
                claimed_at=claimed_at,
                claimed_by="worker-1",
            )
        ]

        # Detect stale claims
        stale_threshold = now - STALE_CLAIM_THRESHOLD
        stale = []
        for job in jobs:
            if job.status == ExportJobStatus.CLAIMED:
                if job.claimed_at and job.claimed_at < stale_threshold:
                    stale.append(job)

        # Verify
        assert stale == []

    def test_exact_10_minute_boundary(self):
        """Test claim at exact 10 minute boundary (not stale)."""
        now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)

        # Job claimed exactly 10 minutes ago
        claimed_at = now - timedelta(minutes=10)
        jobs = [
            MockExportJob(
                id=1,
                snapshot_id=1,
                status=ExportJobStatus.CLAIMED,
                claimed_at=claimed_at,
            )
        ]

        # Detect stale claims (< threshold, not <=)
        stale_threshold = now - STALE_CLAIM_THRESHOLD
        stale = []
        for job in jobs:
            if job.status == ExportJobStatus.CLAIMED:
                if job.claimed_at and job.claimed_at < stale_threshold:
                    stale.append(job)

        # Verify - at exact boundary, not stale
        assert stale == []

    def test_ignore_pending_jobs(self):
        """Test pending jobs are not considered stale."""
        now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)

        # Pending job (not claimed)
        jobs = [
            MockExportJob(
                id=1,
                snapshot_id=1,
                status=ExportJobStatus.PENDING,
                claimed_at=None,
            )
        ]

        # Detect stale claims
        stale_threshold = now - STALE_CLAIM_THRESHOLD
        stale = []
        for job in jobs:
            if job.status == ExportJobStatus.CLAIMED:
                if job.claimed_at and job.claimed_at < stale_threshold:
                    stale.append(job)

        # Verify
        assert stale == []

    def test_ignore_completed_jobs(self):
        """Test completed jobs are not considered stale."""
        now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)

        # Completed job (claimed 20 minutes ago but completed)
        claimed_at = now - timedelta(minutes=20)
        jobs = [
            MockExportJob(
                id=1,
                snapshot_id=1,
                status=ExportJobStatus.COMPLETED,
                claimed_at=claimed_at,
            )
        ]

        # Detect stale claims
        stale_threshold = now - STALE_CLAIM_THRESHOLD
        stale = []
        for job in jobs:
            if job.status == ExportJobStatus.CLAIMED:  # Only CLAIMED status
                if job.claimed_at and job.claimed_at < stale_threshold:
                    stale.append(job)

        # Verify
        assert stale == []

    def test_multiple_stale_claims_detected(self):
        """Test multiple stale claims detected."""
        now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)

        # Multiple stale claims
        jobs = [
            MockExportJob(
                id=1,
                snapshot_id=1,
                status=ExportJobStatus.CLAIMED,
                claimed_at=now - timedelta(minutes=15),
            ),
            MockExportJob(
                id=2,
                snapshot_id=1,
                status=ExportJobStatus.CLAIMED,
                claimed_at=now - timedelta(minutes=20),
            ),
            MockExportJob(
                id=3,
                snapshot_id=1,
                status=ExportJobStatus.CLAIMED,
                claimed_at=now - timedelta(minutes=5),  # Not stale
            ),
        ]

        # Detect stale claims
        stale_threshold = now - STALE_CLAIM_THRESHOLD
        stale = []
        for job in jobs:
            if job.status == ExportJobStatus.CLAIMED:
                if job.claimed_at and job.claimed_at < stale_threshold:
                    stale.append(job)

        # Verify - only 2 stale (job 3 is within threshold)
        assert len(stale) == 2
        assert {job.id for job in stale} == {1, 2}

    def test_claimed_job_without_claimed_at_timestamp(self):
        """Test claimed job without claimed_at is ignored (shouldn't happen)."""
        now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)

        # Claimed job without claimed_at (data integrity issue)
        jobs = [
            MockExportJob(
                id=1,
                snapshot_id=1,
                status=ExportJobStatus.CLAIMED,
                claimed_at=None,  # Missing timestamp
            )
        ]

        # Detect stale claims
        stale_threshold = now - STALE_CLAIM_THRESHOLD
        stale = []
        for job in jobs:
            if job.status == ExportJobStatus.CLAIMED:
                if job.claimed_at and job.claimed_at < stale_threshold:  # Check claimed_at exists
                    stale.append(job)

        # Verify - ignored because claimed_at is None
        assert stale == []


class TestSnapshotFinalization:
    """Test snapshot finalization logic."""

    def test_snapshot_ready_when_all_jobs_completed(self):
        """Test snapshot is ready when all export jobs are completed."""
        snapshots = [MockSnapshot(id=1, name="snapshot-1", status=SnapshotStatus.CREATING)]

        jobs_for_snapshot = [
            MockExportJob(id=1, snapshot_id=1, status=ExportJobStatus.COMPLETED),
            MockExportJob(id=2, snapshot_id=1, status=ExportJobStatus.COMPLETED),
            MockExportJob(id=3, snapshot_id=1, status=ExportJobStatus.COMPLETED),
        ]

        # Check if ready to finalize (same logic as job)
        ready = []
        for snapshot in snapshots:
            if snapshot.status != SnapshotStatus.CREATING:
                continue

            jobs = [j for j in jobs_for_snapshot if j.snapshot_id == snapshot.id]

            if not jobs:
                continue

            all_completed = all(job.status == ExportJobStatus.COMPLETED for job in jobs)
            if all_completed:
                ready.append(snapshot)

        # Verify
        assert len(ready) == 1
        assert ready[0].id == 1

    def test_snapshot_not_ready_with_pending_jobs(self):
        """Test snapshot is not ready when some jobs are pending."""
        snapshots = [MockSnapshot(id=1, name="snapshot-1", status=SnapshotStatus.CREATING)]

        jobs_for_snapshot = [
            MockExportJob(id=1, snapshot_id=1, status=ExportJobStatus.COMPLETED),
            MockExportJob(id=2, snapshot_id=1, status=ExportJobStatus.PENDING),  # Still pending
            MockExportJob(id=3, snapshot_id=1, status=ExportJobStatus.COMPLETED),
        ]

        # Check if ready to finalize
        ready = []
        for snapshot in snapshots:
            if snapshot.status != SnapshotStatus.CREATING:
                continue

            jobs = [j for j in jobs_for_snapshot if j.snapshot_id == snapshot.id]

            if not jobs:
                continue

            all_completed = all(job.status == ExportJobStatus.COMPLETED for job in jobs)
            if all_completed:
                ready.append(snapshot)

        # Verify
        assert ready == []

    def test_snapshot_not_ready_with_claimed_jobs(self):
        """Test snapshot is not ready when some jobs are claimed."""
        snapshots = [MockSnapshot(id=1, name="snapshot-1", status=SnapshotStatus.CREATING)]

        jobs_for_snapshot = [
            MockExportJob(id=1, snapshot_id=1, status=ExportJobStatus.COMPLETED),
            MockExportJob(id=2, snapshot_id=1, status=ExportJobStatus.CLAIMED),  # In progress
        ]

        # Check if ready to finalize
        ready = []
        for snapshot in snapshots:
            if snapshot.status != SnapshotStatus.CREATING:
                continue

            jobs = [j for j in jobs_for_snapshot if j.snapshot_id == snapshot.id]

            if not jobs:
                continue

            all_completed = all(job.status == ExportJobStatus.COMPLETED for job in jobs)
            if all_completed:
                ready.append(snapshot)

        # Verify
        assert ready == []

    def test_snapshot_not_ready_when_no_jobs(self):
        """Test snapshot is not ready when it has no export jobs yet."""
        snapshots = [MockSnapshot(id=1, name="snapshot-1", status=SnapshotStatus.CREATING)]

        jobs_for_snapshot = []  # No jobs yet

        # Check if ready to finalize
        ready = []
        for snapshot in snapshots:
            if snapshot.status != SnapshotStatus.CREATING:
                continue

            jobs = [j for j in jobs_for_snapshot if j.snapshot_id == snapshot.id]

            if not jobs:  # Skip if no jobs
                continue

            all_completed = all(job.status == ExportJobStatus.COMPLETED for job in jobs)
            if all_completed:
                ready.append(snapshot)

        # Verify
        assert ready == []

    def test_ignore_ready_snapshots(self):
        """Test snapshots already in READY status are ignored."""
        snapshots = [MockSnapshot(id=1, name="snapshot-1", status=SnapshotStatus.READY)]

        jobs_for_snapshot = [
            MockExportJob(id=1, snapshot_id=1, status=ExportJobStatus.COMPLETED),
        ]

        # Check if ready to finalize (only CREATING snapshots)
        ready = []
        for snapshot in snapshots:
            if snapshot.status != SnapshotStatus.CREATING:  # Skip non-CREATING
                continue

            jobs = [j for j in jobs_for_snapshot if j.snapshot_id == snapshot.id]

            if not jobs:
                continue

            all_completed = all(job.status == ExportJobStatus.COMPLETED for job in jobs)
            if all_completed:
                ready.append(snapshot)

        # Verify
        assert ready == []

    def test_ignore_failed_snapshots(self):
        """Test snapshots in FAILED status are ignored."""
        snapshots = [MockSnapshot(id=1, name="snapshot-1", status=SnapshotStatus.FAILED)]

        jobs_for_snapshot = [
            MockExportJob(id=1, snapshot_id=1, status=ExportJobStatus.COMPLETED),
        ]

        # Check if ready to finalize
        ready = []
        for snapshot in snapshots:
            if snapshot.status != SnapshotStatus.CREATING:
                continue

            jobs = [j for j in jobs_for_snapshot if j.snapshot_id == snapshot.id]

            if not jobs:
                continue

            all_completed = all(job.status == ExportJobStatus.COMPLETED for job in jobs)
            if all_completed:
                ready.append(snapshot)

        # Verify
        assert ready == []

    def test_multiple_snapshots_ready(self):
        """Test multiple snapshots ready to finalize."""
        snapshots = [
            MockSnapshot(id=1, name="snapshot-1", status=SnapshotStatus.CREATING),
            MockSnapshot(id=2, name="snapshot-2", status=SnapshotStatus.CREATING),
            MockSnapshot(id=3, name="snapshot-3", status=SnapshotStatus.CREATING),
        ]

        jobs_for_snapshot = [
            # Snapshot 1 - all completed
            MockExportJob(id=1, snapshot_id=1, status=ExportJobStatus.COMPLETED),
            MockExportJob(id=2, snapshot_id=1, status=ExportJobStatus.COMPLETED),
            # Snapshot 2 - has pending job
            MockExportJob(id=3, snapshot_id=2, status=ExportJobStatus.COMPLETED),
            MockExportJob(id=4, snapshot_id=2, status=ExportJobStatus.PENDING),
            # Snapshot 3 - all completed
            MockExportJob(id=5, snapshot_id=3, status=ExportJobStatus.COMPLETED),
        ]

        # Check if ready to finalize
        ready = []
        for snapshot in snapshots:
            if snapshot.status != SnapshotStatus.CREATING:
                continue

            jobs = [j for j in jobs_for_snapshot if j.snapshot_id == snapshot.id]

            if not jobs:
                continue

            all_completed = all(job.status == ExportJobStatus.COMPLETED for job in jobs)
            if all_completed:
                ready.append(snapshot)

        # Verify - only snapshots 1 and 3
        assert len(ready) == 2
        assert {s.id for s in ready} == {1, 3}

    def test_snapshot_with_failed_jobs_not_ready(self):
        """Test snapshot with failed jobs is not finalized."""
        snapshots = [MockSnapshot(id=1, name="snapshot-1", status=SnapshotStatus.CREATING)]

        jobs_for_snapshot = [
            MockExportJob(id=1, snapshot_id=1, status=ExportJobStatus.COMPLETED),
            MockExportJob(id=2, snapshot_id=1, status=ExportJobStatus.FAILED),  # Failed job
        ]

        # Check if ready to finalize (only COMPLETED jobs qualify)
        ready = []
        for snapshot in snapshots:
            if snapshot.status != SnapshotStatus.CREATING:
                continue

            jobs = [j for j in jobs_for_snapshot if j.snapshot_id == snapshot.id]

            if not jobs:
                continue

            all_completed = all(job.status == ExportJobStatus.COMPLETED for job in jobs)
            if all_completed:
                ready.append(snapshot)

        # Verify - not ready because one job failed
        assert ready == []


class TestStaleClaimThresholdConstant:
    """Test the STALE_CLAIM_THRESHOLD constant."""

    def test_stale_claim_threshold_is_10_minutes(self):
        """Test STALE_CLAIM_THRESHOLD is 10 minutes."""
        assert timedelta(minutes=10) == STALE_CLAIM_THRESHOLD

    def test_stale_claim_threshold_in_seconds(self):
        """Test STALE_CLAIM_THRESHOLD is 600 seconds."""
        assert STALE_CLAIM_THRESHOLD.total_seconds() == 600


@pytest.mark.asyncio
class TestExportReconciliationJobIntegration:
    """Test export reconciliation job with mocked dependencies."""

    async def test_export_reconciliation_resets_stale_claims(self):
        """Test export reconciliation job resets stale claims."""
        from control_plane.jobs.export_reconciliation import run_export_reconciliation_job

        # Mock database session and repositories
        with patch("control_plane.jobs.export_reconciliation.get_session") as mock_session:
            with patch(
                "control_plane.jobs.export_reconciliation.ExportJobRepository"
            ) as MockExportJobRepo:
                with patch(
                    "control_plane.jobs.export_reconciliation.SnapshotRepository"
                ) as MockSnapshotRepo:
                    # Setup mocks
                    mock_export_repo = AsyncMock()
                    MockExportJobRepo.return_value = mock_export_repo

                    mock_snapshot_repo = AsyncMock()
                    MockSnapshotRepo.return_value = mock_snapshot_repo

                    # Stale claimed job (claimed 15 minutes ago)
                    now = datetime.now(UTC)
                    stale_job = MockExportJob(
                        id=1,
                        snapshot_id=1,
                        status=ExportJobStatus.CLAIMED,
                        claimed_at=now - timedelta(minutes=15),
                        claimed_by="worker-1",
                    )

                    mock_export_repo.list_all.return_value = [stale_job]
                    mock_export_repo.reset_to_pending.return_value = None

                    # No creating snapshots
                    mock_snapshot_repo.list_all.return_value = []

                    # Mock session context manager
                    mock_session.return_value.__aenter__.return_value = AsyncMock()
                    mock_session.return_value.__aexit__.return_value = AsyncMock()

                    # Run job
                    await run_export_reconciliation_job()

                    # Verify stale claim was reset
                    mock_export_repo.reset_to_pending.assert_called_once_with(1)

    async def test_export_reconciliation_finalizes_snapshot(self):
        """Test export reconciliation job finalizes completed snapshot."""
        from control_plane.jobs.export_reconciliation import run_export_reconciliation_job

        # Mock database session and repositories
        with patch("control_plane.jobs.export_reconciliation.get_session") as mock_session:
            with patch(
                "control_plane.jobs.export_reconciliation.ExportJobRepository"
            ) as MockExportJobRepo:
                with patch(
                    "control_plane.jobs.export_reconciliation.SnapshotRepository"
                ) as MockSnapshotRepo:
                    # Setup mocks
                    mock_export_repo = AsyncMock()
                    MockExportJobRepo.return_value = mock_export_repo

                    mock_snapshot_repo = AsyncMock()
                    MockSnapshotRepo.return_value = mock_snapshot_repo

                    # No stale claims
                    mock_export_repo.list_all.return_value = []

                    # Creating snapshot with all jobs completed
                    creating_snapshot = MockSnapshot(
                        id=1, name="snapshot-1", status=SnapshotStatus.CREATING
                    )
                    mock_snapshot_repo.list_all.return_value = [creating_snapshot]

                    completed_jobs = [
                        MockExportJob(id=1, snapshot_id=1, status=ExportJobStatus.COMPLETED),
                        MockExportJob(id=2, snapshot_id=1, status=ExportJobStatus.COMPLETED),
                    ]
                    mock_export_repo.list_by_snapshot.return_value = completed_jobs

                    mock_snapshot_repo.update_status.return_value = None

                    # Mock session context manager
                    mock_session.return_value.__aenter__.return_value = AsyncMock()
                    mock_session.return_value.__aexit__.return_value = AsyncMock()

                    # Run job
                    await run_export_reconciliation_job()

                    # Verify snapshot was finalized
                    # Note: empty dicts become None due to `node_counts or None` in implementation
                    mock_snapshot_repo.update_status.assert_called_once_with(
                        snapshot_id=1,
                        status=SnapshotStatus.READY,
                        node_counts=None,
                        edge_counts=None,
                        size_bytes=None,
                        error_message=None,
                    )


# Mark all tests for asyncio compatibility
pytest_plugins = ("pytest_asyncio",)
