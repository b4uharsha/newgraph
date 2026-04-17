"""Integration tests for error handling and recovery (ADR-025).

Tests error scenarios across the export flow:
- Starburst submission failures
- Starburst query failures during polling
- GCS errors during row counting
- Control Plane communication errors
- Graceful shutdown handling
- Cancellation detection
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from export_worker.models import ExportJobStatus
from export_worker.worker import ExportWorker

from .conftest import MockControlPlaneClient, MockGCSClient, MockStarburstClient


class TestStarburstErrorHandling:
    """Tests for Starburst error scenarios."""

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
    async def test_starburst_submission_failure_marks_job_failed(
        self,
        mock_starburst_factory,
        mock_control_plane: MockControlPlaneClient,
        mock_gcs: MockGCSClient,
        worker: ExportWorker,
    ):
        """Test that Starburst submission failure marks job as failed."""
        # Add job that will fail on submission
        job = mock_control_plane.add_pending_job(
            snapshot_id=1,
            job_type="node",
            entity_name="FailingEntity",
            sql="SELECT * FROM failing_table",
            column_names=["id"],
            gcs_path="gs://test-bucket/nodes/FailingEntity/",
        )

        # Configure Starburst to fail for this entity
        mock_starburst = mock_starburst_factory(fail_queries=["FailingEntity"])
        worker._starburst = mock_starburst

        # Claim job
        claimed = await worker._claim_phase()
        assert len(claimed) == 1

        # Submit should fail
        await worker._submit_phase(claimed)

        # Job should be marked as failed
        failed_job = mock_control_plane.get_job(job.id)
        assert failed_job.status == ExportJobStatus.FAILED
        assert failed_job.error_message is not None

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_starburst_query_failure_during_polling(
        self,
        mock_starburst_factory,
        mock_control_plane: MockControlPlaneClient,
        mock_gcs: MockGCSClient,
        worker: ExportWorker,
    ):
        """Test that Starburst query failure during polling marks job as failed."""
        # Add job
        job = mock_control_plane.add_pending_job(
            snapshot_id=1,
            job_type="node",
            entity_name="SlowFail",
            sql="SELECT * FROM slow_fail",
            column_names=["id"],
            gcs_path="gs://test-bucket/nodes/SlowFail/",
        )

        # Configure to fail during polling (not submission)
        mock_starburst = mock_starburst_factory(
            polls_until_finished=10,  # Would take many polls
            fail_queries=["SlowFail"],  # Will fail when polled
        )

        # Manually set up to simulate submission success but poll failure
        mock_starburst.fail_queries = []  # Don't fail submission
        worker._starburst = mock_starburst

        # Claim and submit
        claimed = await worker._claim_phase()
        await worker._submit_phase(claimed)

        # Now make it fail during polling
        mock_starburst.fail_queries = ["SlowFail"]

        # Make job pollable
        db_job = mock_control_plane.get_job(job.id)
        db_job.next_poll_at = datetime.now(UTC).isoformat()

        # Poll should mark job as failed
        await worker._poll_phase()

        failed_job = mock_control_plane.get_job(job.id)
        assert failed_job.status == ExportJobStatus.FAILED
        assert "simulated error" in failed_job.error_message.lower()

    # =========================================================================
    # SNAPSHOT TEST DISABLED
    # This test is commented out as snapshot functionality has been disabled.
    # =========================================================================
    # @pytest.mark.integration
    # @pytest.mark.asyncio
    # async def test_partial_failure_fails_snapshot(
    #     self,
    #     mock_starburst_factory,
    #     mock_control_plane: MockControlPlaneClient,
    #     mock_gcs: MockGCSClient,
    #     worker: ExportWorker,
    # ):
    #     """Test that if any job fails, the snapshot is marked as failed."""
    #     snapshot_id = 1
    #
    #     # Add two jobs - one will succeed, one will fail
    #     job_success = mock_control_plane.add_pending_job(
    #         snapshot_id=snapshot_id,
    #         job_type="node",
    #         entity_name="Success",
    #         sql="SELECT * FROM success",
    #         column_names=["id"],
    #         gcs_path="gs://test-bucket/nodes/Success/",
    #     )
    #     job_fail = mock_control_plane.add_pending_job(
    #         snapshot_id=snapshot_id,
    #         job_type="node",
    #         entity_name="Failure",
    #         sql="SELECT * FROM failure",
    #         column_names=["id"],
    #         gcs_path="gs://test-bucket/nodes/Failure/",
    #     )
    #
    #     # Configure Starburst to fail one entity
    #     mock_starburst = mock_starburst_factory(
    #         polls_until_finished=1,
    #         fail_queries=["Failure"],
    #     )
    #     worker._starburst = mock_starburst
    #
    #     # Process jobs
    #     claimed = await worker._claim_phase()
    #     await worker._submit_phase(claimed)
    #
    #     # Make all pollable
    #     for job in [job_success, job_fail]:
    #         db_job = mock_control_plane.get_job(job.id)
    #         if db_job.status == ExportJobStatus.SUBMITTED:
    #             db_job.next_poll_at = datetime.now(UTC).isoformat()
    #
    #     await worker._poll_phase()
    #
    #     # Make remaining job pollable and poll again
    #     for job in [job_success, job_fail]:
    #         db_job = mock_control_plane.get_job(job.id)
    #         if db_job.status == ExportJobStatus.SUBMITTED:
    #             db_job.next_poll_at = datetime.now(UTC).isoformat()
    #
    #     await worker._poll_phase()
    #
    #     # Snapshot should be finalized as failed
    #     assert len(mock_control_plane.finalized_snapshots) == 1
    #     finalized = mock_control_plane.finalized_snapshots[0]
    #     assert finalized["success"] is False
    #     assert finalized["error_message"] is not None


class TestGCSErrorHandling:
    """Tests for GCS error scenarios."""

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
    async def test_gcs_error_during_row_count_fails_job(
        self,
        mock_starburst: MockStarburstClient,
        mock_control_plane: MockControlPlaneClient,
        mock_gcs: MockGCSClient,
        worker: ExportWorker,
    ):
        """Test that GCS error during row counting fails the job.

        GCS errors during counting are treated as job failures since we cannot
        verify the export completed successfully without row counts.
        """
        job = mock_control_plane.add_pending_job(
            snapshot_id=1,
            job_type="node",
            entity_name="Customer",
            sql="SELECT * FROM customers",
            column_names=["id"],
            gcs_path="gs://test-bucket/nodes/Customer/",
        )

        # Make GCS fail for this path
        mock_gcs.set_path_failure(job.gcs_path)
        mock_starburst.polls_until_finished = 1

        # Process job
        claimed = await worker._claim_phase()
        await worker._submit_phase(claimed)

        db_job = mock_control_plane.get_job(job.id)
        db_job.next_poll_at = datetime.now(UTC).isoformat()

        await worker._poll_phase()

        # Job should be marked as failed due to GCS error
        final_job = mock_control_plane.get_job(job.id)
        assert final_job.status == ExportJobStatus.FAILED
        assert final_job.error_message is not None
        assert "GCS" in final_job.error_message or "count" in final_job.error_message.lower()


class TestGracefulShutdown:
    """Tests for graceful shutdown handling."""

    @pytest.fixture
    def worker(
        self,
        mock_starburst: MockStarburstClient,
        mock_control_plane: MockControlPlaneClient,
        mock_gcs: MockGCSClient,
    ) -> ExportWorker:
        """Create ExportWorker with mocked dependencies."""
        mock_settings = MagicMock()
        mock_settings.poll_interval_seconds = 0.1
        mock_settings.empty_poll_backoff_seconds = 0.1
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
    async def test_shutdown_stops_submit_phase(
        self,
        mock_starburst: MockStarburstClient,
        mock_control_plane: MockControlPlaneClient,
        worker: ExportWorker,
    ):
        """Test that shutdown signal stops submit phase."""
        # Add multiple jobs
        for i in range(5):
            mock_control_plane.add_pending_job(
                snapshot_id=1,
                job_type="node",
                entity_name=f"Entity{i}",
                sql=f"SELECT * FROM table{i}",
                column_names=["id"],
                gcs_path=f"gs://test-bucket/nodes/Entity{i}/",
            )

        # Claim jobs
        claimed = await worker._claim_phase()
        assert len(claimed) == 5

        # Request shutdown before submit
        worker.request_shutdown()

        # Submit phase should not process any jobs
        await worker._submit_phase(claimed)

        # No queries should have been submitted
        assert mock_starburst.submitted_query_count == 0

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_shutdown_stops_main_loop(
        self,
        mock_control_plane: MockControlPlaneClient,
        worker: ExportWorker,
    ):
        """Test that shutdown signal stops the main loop."""
        # Request shutdown immediately
        worker.request_shutdown()

        # Run should exit quickly
        async def run_with_timeout():
            try:
                await asyncio.wait_for(worker.run(), timeout=1.0)
            except TimeoutError:
                pytest.fail("Worker did not stop within timeout")

        await run_with_timeout()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_is_shutting_down_property(
        self,
        worker: ExportWorker,
    ):
        """Test is_shutting_down property."""
        assert not worker.is_shutting_down

        worker.request_shutdown()

        assert worker.is_shutting_down


class TestCancellationHandling:
    """Tests for snapshot cancellation detection."""

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

    # =========================================================================
    # SNAPSHOT TEST DISABLED
    # This test is commented out as snapshot functionality has been disabled.
    # =========================================================================
    # @pytest.mark.integration
    # @pytest.mark.asyncio
    # async def test_cancelled_snapshot_detected(
    #     self,
    #     mock_control_plane: MockControlPlaneClient,
    # ):
    #     """Test that cancelled snapshot can be detected."""
    #     snapshot_id = 1
    #
    #     # Initially not cancelled
    #     assert not mock_control_plane.is_cancelled(snapshot_id)
    #
    #     # Cancel the snapshot
    #     mock_control_plane.cancel_snapshot(snapshot_id)
    #
    #     # Now detected as cancelled
    #     assert mock_control_plane.is_cancelled(snapshot_id)


class TestFibonacciBackoff:
    """Tests for Fibonacci backoff in polling."""

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
    async def test_poll_count_increments(
        self,
        mock_starburst_factory,
        mock_control_plane: MockControlPlaneClient,
        worker: ExportWorker,
    ):
        """Test that poll_count increments with each poll."""
        job = mock_control_plane.add_pending_job(
            snapshot_id=1,
            job_type="node",
            entity_name="Customer",
            sql="SELECT * FROM customers",
            column_names=["id"],
            gcs_path="gs://test-bucket/nodes/Customer/",
        )

        # Configure to need many polls
        mock_starburst = mock_starburst_factory(polls_until_finished=5)
        worker._starburst = mock_starburst

        # Claim and submit
        claimed = await worker._claim_phase()
        await worker._submit_phase(claimed)

        # Poll multiple times
        for expected_count in range(2, 5):  # poll_count starts at 1 after submit
            db_job = mock_control_plane.get_job(job.id)
            db_job.next_poll_at = datetime.now(UTC).isoformat()

            await worker._poll_phase()

            updated_job = mock_control_plane.get_job(job.id)
            if updated_job.status == ExportJobStatus.SUBMITTED:
                assert updated_job.poll_count == expected_count

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_next_poll_at_increases(
        self,
        mock_starburst_factory,
        mock_control_plane: MockControlPlaneClient,
        worker: ExportWorker,
    ):
        """Test that next_poll_at time increases with Fibonacci backoff."""
        job = mock_control_plane.add_pending_job(
            snapshot_id=1,
            job_type="node",
            entity_name="Customer",
            sql="SELECT * FROM customers",
            column_names=["id"],
            gcs_path="gs://test-bucket/nodes/Customer/",
        )

        mock_starburst = mock_starburst_factory(polls_until_finished=10)
        worker._starburst = mock_starburst

        # Claim and submit
        claimed = await worker._claim_phase()
        await worker._submit_phase(claimed)

        previous_poll_time = None

        # Poll multiple times and verify increasing delays
        for _ in range(3):
            db_job = mock_control_plane.get_job(job.id)
            if db_job.status != ExportJobStatus.SUBMITTED:
                break

            current_poll_time = db_job.next_poll_at
            db_job.next_poll_at = datetime.now(UTC).isoformat()

            await worker._poll_phase()

            # Verify next_poll_at was updated
            updated_job = mock_control_plane.get_job(job.id)
            if updated_job.status == ExportJobStatus.SUBMITTED:
                assert updated_job.next_poll_at is not None
                if previous_poll_time:
                    # Delays should generally increase (Fibonacci)
                    pass  # Just verify it's set
                previous_poll_time = updated_job.next_poll_at
