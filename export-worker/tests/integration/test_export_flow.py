"""Integration tests for complete export flow (ADR-025).

Tests the three-phase worker loop with mocked external services:
1. Claim phase: Get pending jobs from Control Plane
2. Submit phase: Submit UNLOAD queries to Starburst
3. Poll phase: Poll Starburst for completion, count rows, finalize

These tests verify component interactions without real external services.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from export_worker.models import ExportJob, ExportJobStatus
from export_worker.worker import ExportWorker

from .conftest import MockControlPlaneClient, MockGCSClient, MockStarburstClient


class TestExportFlowIntegration:
    """Integration tests for complete export flow."""

    @pytest.fixture
    def worker(
        self,
        mock_starburst: MockStarburstClient,
        mock_control_plane: MockControlPlaneClient,
        mock_gcs: MockGCSClient,
    ) -> ExportWorker:
        """Create ExportWorker with mocked dependencies."""
        # Create mock settings
        mock_settings = MagicMock()
        mock_settings.poll_interval_seconds = 0.01  # Fast for tests
        mock_settings.empty_poll_backoff_seconds = 0.01
        mock_settings.claim_limit = 10
        mock_settings.poll_limit = 10
        mock_settings.log_format = "console"
        mock_settings.log_level = "DEBUG"

        # Patch client creation
        with patch("export_worker.worker.StarburstClient") as mock_sb_cls, \
             patch("export_worker.worker.ControlPlaneClient") as mock_cp_cls, \
             patch("export_worker.worker.GCSClient") as mock_gcs_cls:

            mock_sb_cls.from_config.return_value = mock_starburst
            mock_cp_cls.from_config.return_value = mock_control_plane
            mock_gcs_cls.from_config.return_value = mock_gcs

            worker = ExportWorker(mock_settings)
            # Replace clients with our mocks
            worker._starburst = mock_starburst
            worker._control_plane = mock_control_plane
            worker._gcs = mock_gcs
            return worker

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_single_job_export_complete_flow(
        self,
        mock_starburst: MockStarburstClient,
        mock_control_plane: MockControlPlaneClient,
        mock_gcs: MockGCSClient,
        worker: ExportWorker,
    ):
        """Test complete flow for a single node export job.

        Flow:
        1. Job starts as PENDING
        2. Worker claims job (CLAIMED)
        3. Worker submits to Starburst (SUBMITTED)
        4. Worker polls until FINISHED
        5. Worker counts rows and marks COMPLETED
        6. Snapshot is finalized as ready
        """
        # Arrange: Add a pending job
        snapshot_id = 1
        job = mock_control_plane.add_pending_job(
            snapshot_id=snapshot_id,
            job_type="node",
            entity_name="Customer",
            sql="SELECT id, name FROM customers",
            column_names=["id", "name"],
            gcs_path="gs://test-bucket/snapshot-1/nodes/Customer/",
        )

        # Set up GCS to return specific counts
        mock_gcs.set_path_result(job.gcs_path, row_count=5000, size_bytes=2048000)

        # Configure Starburst to finish after 2 polls
        mock_starburst.polls_until_finished = 2

        # Act: Run claim phase
        claimed_jobs = await worker._claim_phase()

        # Assert: Job was claimed
        assert len(claimed_jobs) == 1
        assert claimed_jobs[0].id == job.id
        assert mock_control_plane.get_job(job.id).status == ExportJobStatus.CLAIMED

        # Act: Run submit phase
        await worker._submit_phase(claimed_jobs)

        # Assert: Job was submitted
        updated_job = mock_control_plane.get_job(job.id)
        assert updated_job.status == ExportJobStatus.SUBMITTED
        assert updated_job.starburst_query_id is not None
        assert updated_job.next_uri is not None
        assert mock_starburst.submitted_query_count == 1

        # Act: Run poll phase (first poll - still running)
        # Need to set next_poll_at to now to be pollable
        updated_job.next_poll_at = datetime.now(UTC).isoformat()
        await worker._poll_phase()

        # Should still be running after first poll
        assert mock_control_plane.get_job(job.id).status == ExportJobStatus.SUBMITTED

        # Act: Run poll phase again (second poll - finished)
        updated_job = mock_control_plane.get_job(job.id)
        updated_job.next_poll_at = datetime.now(UTC).isoformat()
        await worker._poll_phase()

        # Assert: Job completed
        final_job = mock_control_plane.get_job(job.id)
        assert final_job.status == ExportJobStatus.COMPLETED
        assert final_job.row_count == 5000
        assert final_job.size_bytes == 2048000

        # Assert: Snapshot was finalized
        assert len(mock_control_plane.finalized_snapshots) == 1
        finalized = mock_control_plane.finalized_snapshots[0]
        assert finalized["snapshot_id"] == snapshot_id
        assert finalized["success"] is True
        assert finalized["node_counts"] == {"Customer": 5000}

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_multi_job_export_flow(
        self,
        mock_starburst: MockStarburstClient,
        mock_control_plane: MockControlPlaneClient,
        mock_gcs: MockGCSClient,
        worker: ExportWorker,
        sample_snapshot_jobs: list[ExportJob],
    ):
        """Test export flow with multiple jobs (2 nodes + 1 edge).

        Verifies:
        - All jobs are claimed together
        - All jobs are submitted
        - All jobs complete
        - Snapshot is finalized with correct counts
        """
        snapshot_id = 1

        # Configure mocks
        mock_starburst.polls_until_finished = 1  # Fast completion
        mock_gcs.set_path_result(sample_snapshot_jobs[0].gcs_path, 1000, 100000)
        mock_gcs.set_path_result(sample_snapshot_jobs[1].gcs_path, 500, 50000)
        mock_gcs.set_path_result(sample_snapshot_jobs[2].gcs_path, 5000, 500000)

        # Run claim phase
        claimed = await worker._claim_phase()
        assert len(claimed) == 3

        # Run submit phase
        await worker._submit_phase(claimed)
        assert mock_starburst.submitted_query_count == 3

        # Run poll phases until all complete
        for _ in range(5):  # Max iterations
            # Make all jobs pollable
            for job_id in [j.id for j in sample_snapshot_jobs]:
                job = mock_control_plane.get_job(job_id)
                if job.status == ExportJobStatus.SUBMITTED:
                    job.next_poll_at = datetime.now(UTC).isoformat()

            await worker._poll_phase()

            # Check if all complete (synchronous method)
            result = mock_control_plane.get_snapshot_jobs_result(snapshot_id)
            if result.all_complete:
                break

        # Assert all completed
        for job in sample_snapshot_jobs:
            assert mock_control_plane.get_job(job.id).status == ExportJobStatus.COMPLETED

        # Assert snapshot finalized correctly
        assert len(mock_control_plane.finalized_snapshots) == 1
        finalized = mock_control_plane.finalized_snapshots[0]
        assert finalized["success"] is True
        assert finalized["node_counts"] == {"Customer": 1000, "Product": 500}
        assert finalized["edge_counts"] == {"PURCHASED": 5000}

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_no_pending_jobs_returns_empty(
        self,
        mock_control_plane: MockControlPlaneClient,
        worker: ExportWorker,
    ):
        """Test that claim phase returns empty when no pending jobs."""
        claimed = await worker._claim_phase()
        assert claimed == []

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_partial_completion_does_not_finalize(
        self,
        mock_starburst_factory,
        mock_control_plane: MockControlPlaneClient,
        mock_gcs: MockGCSClient,
        worker: ExportWorker,
    ):
        """Test that snapshot is not finalized until ALL jobs complete."""
        snapshot_id = 1

        # Add two jobs
        job1 = mock_control_plane.add_pending_job(
            snapshot_id=snapshot_id,
            job_type="node",
            entity_name="Customer",
            sql="SELECT id FROM customers",
            column_names=["id"],
            gcs_path="gs://test-bucket/nodes/Customer/",
        )
        job2 = mock_control_plane.add_pending_job(
            snapshot_id=snapshot_id,
            job_type="node",
            entity_name="Product",
            sql="SELECT id FROM products",
            column_names=["id"],
            gcs_path="gs://test-bucket/nodes/Product/",
        )

        # Use starburst that finishes immediately
        mock_starburst = mock_starburst_factory(polls_until_finished=1)
        worker._starburst = mock_starburst

        # Claim and submit both
        claimed = await worker._claim_phase()
        await worker._submit_phase(claimed)

        # Complete only job1
        job1_db = mock_control_plane.get_job(job1.id)
        job1_db.next_poll_at = datetime.now(UTC).isoformat()

        # Only poll job1 (don't make job2 pollable)
        job2_db = mock_control_plane.get_job(job2.id)
        job2_db.next_poll_at = (datetime.now(UTC) + timedelta(hours=1)).isoformat()

        await worker._poll_phase()

        # Job1 should be complete
        assert mock_control_plane.get_job(job1.id).status == ExportJobStatus.COMPLETED

        # Snapshot should NOT be finalized yet
        assert len(mock_control_plane.finalized_snapshots) == 0


class TestExportFlowConcurrency:
    """Tests for concurrent job processing."""

    @pytest.fixture
    def worker(
        self,
        mock_starburst: MockStarburstClient,
        mock_control_plane: MockControlPlaneClient,
        mock_gcs: MockGCSClient,
    ) -> ExportWorker:
        """Create ExportWorker with mocked dependencies."""
        mock_settings = MagicMock()
        mock_settings.poll_interval_seconds = 0.01
        mock_settings.empty_poll_backoff_seconds = 0.01
        mock_settings.claim_limit = 10
        mock_settings.poll_limit = 10
        mock_settings.log_format = "console"
        mock_settings.log_level = "DEBUG"

        with patch("export_worker.worker.StarburstClient"), \
             patch("export_worker.worker.ControlPlaneClient"), \
             patch("export_worker.worker.GCSClient"):

            worker = ExportWorker(mock_settings)
            worker._starburst = mock_starburst
            worker._control_plane = mock_control_plane
            worker._gcs = mock_gcs
            return worker

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_claim_respects_limit(
        self,
        mock_control_plane: MockControlPlaneClient,
        worker: ExportWorker,
    ):
        """Test that claim phase respects the claim limit."""
        # Add more jobs than claim limit
        for i in range(15):
            mock_control_plane.add_pending_job(
                snapshot_id=1,
                job_type="node",
                entity_name=f"Entity{i}",
                sql=f"SELECT * FROM table{i}",
                column_names=["id"],
                gcs_path=f"gs://test-bucket/nodes/Entity{i}/",
            )

        # Claim should respect limit (10)
        worker.settings.claim_limit = 10
        claimed = await worker._claim_phase()

        assert len(claimed) == 10

    # =========================================================================
    # SNAPSHOT TEST DISABLED
    # This test is commented out as snapshot functionality has been disabled.
    # =========================================================================
    # @pytest.mark.integration
    # @pytest.mark.asyncio
    # async def test_multiple_snapshots_independent(
    #     self,
    #     mock_starburst: MockStarburstClient,
    #     mock_control_plane: MockControlPlaneClient,
    #     mock_gcs: MockGCSClient,
    #     worker: ExportWorker,
    # ):
    #     """Test that multiple snapshots can be processed independently."""
    #     mock_starburst.polls_until_finished = 1
    #
    #     # Add jobs for two different snapshots
    #     job1 = mock_control_plane.add_pending_job(
    #         snapshot_id=1,
    #         job_type="node",
    #         entity_name="Customer",
    #         sql="SELECT * FROM customers",
    #         column_names=["id"],
    #         gcs_path="gs://test-bucket/snapshot-1/nodes/Customer/",
    #     )
    #     job2 = mock_control_plane.add_pending_job(
    #         snapshot_id=2,
    #         job_type="node",
    #         entity_name="Product",
    #         sql="SELECT * FROM products",
    #         column_names=["id"],
    #         gcs_path="gs://test-bucket/snapshot-2/nodes/Product/",
    #     )
    #
    #     # Process both
    #     claimed = await worker._claim_phase()
    #     assert len(claimed) == 2
    #
    #     await worker._submit_phase(claimed)
    #
    #     # Complete both
    #     for job in [job1, job2]:
    #         db_job = mock_control_plane.get_job(job.id)
    #         db_job.next_poll_at = datetime.now(UTC).isoformat()
    #
    #     await worker._poll_phase()
    #
    #     # Both snapshots should be finalized independently
    #     assert len(mock_control_plane.finalized_snapshots) == 2
    #
    #     snapshot_ids = {f["snapshot_id"] for f in mock_control_plane.finalized_snapshots}
    #     assert snapshot_ids == {1, 2}
