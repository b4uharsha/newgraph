"""Unit tests for K8s Export Worker (ADR-025).

Tests the stateless database polling architecture:
- Three-phase loop: Claim -> Submit -> Poll
- Starburst client_tags for resource group routing
- Database-persisted polling state
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from export_worker.clients.starburst import QueryPollResult, QuerySubmissionResult
from export_worker.models import ExportJob, ExportJobStatus, SnapshotJobsResult
from export_worker.worker import ExportWorker, configure_logging


class TestConfigureLogging:
    """Tests for configure_logging function."""

    def test_configure_logging_json_format(self) -> None:
        """Test that JSON format configures JSON processors."""
        with patch("export_worker.worker.structlog.configure") as mock_configure:
            configure_logging(log_format="json", log_level="INFO")

            mock_configure.assert_called_once()
            call_kwargs = mock_configure.call_args.kwargs
            processors = call_kwargs["processors"]

            # Check that JSONRenderer is in processors
            from structlog.processors import JSONRenderer
            assert any((isinstance(p, type) and p == JSONRenderer) or isinstance(p, JSONRenderer)
                      for p in processors)

    def test_configure_logging_console_format(self) -> None:
        """Test that console format configures console renderer."""
        with patch("export_worker.worker.structlog.configure") as mock_configure:
            configure_logging(log_format="console", log_level="DEBUG")

            mock_configure.assert_called_once()
            call_kwargs = mock_configure.call_args.kwargs
            processors = call_kwargs["processors"]

            # Check that ConsoleRenderer is in processors
            from structlog.dev import ConsoleRenderer
            assert any((isinstance(p, type) and p == ConsoleRenderer) or isinstance(p, ConsoleRenderer)
                      for p in processors)

    def test_configure_logging_sets_log_level(self) -> None:
        """Test that log level is correctly set."""
        import logging

        with patch("export_worker.worker.structlog.configure") as mock_configure, \
             patch("export_worker.worker.structlog.make_filtering_bound_logger") as mock_filter:

            configure_logging(log_format="json", log_level="WARNING")

            # Verify that make_filtering_bound_logger was called with WARNING level
            mock_filter.assert_called_once_with(logging.WARNING)

    def test_configure_logging_handles_invalid_level(self) -> None:
        """Test that invalid log level defaults to INFO."""
        import logging

        with patch("export_worker.worker.structlog.configure") as mock_configure, \
             patch("export_worker.worker.structlog.make_filtering_bound_logger") as mock_filter:

            configure_logging(log_format="json", log_level="INVALID")

            # Should default to INFO
            mock_filter.assert_called_once_with(logging.INFO)


@pytest.fixture
def mock_settings() -> MagicMock:
    """Create mock settings for testing (ADR-025)."""
    settings = MagicMock()
    settings.poll_interval_seconds = 5
    settings.empty_poll_backoff_seconds = 10
    settings.claim_limit = 10
    settings.poll_limit = 10
    settings.log_format = "console"
    settings.log_level = "DEBUG"

    # Starburst config
    settings.starburst.url = "http://starburst.test"
    settings.starburst.user = "test"
    settings.starburst.password.get_secret_value.return_value = "password"
    settings.starburst.catalog = "analytics"
    settings.starburst.schema_name = "public"
    settings.starburst.request_timeout_seconds = 30
    settings.starburst.client_tags = "graph-olap-export"
    settings.starburst.source = "graph-olap-export-worker"

    # Control plane config
    settings.control_plane.url = "http://control-plane.test"
    settings.control_plane.timeout_seconds = 30
    settings.control_plane.max_retries = 3
    settings.control_plane.internal_api_key = None

    # GCS config
    settings.gcs.project = "test-project"

    return settings


class TestExportWorkerInit:
    """Tests for ExportWorker initialization."""

    def test_init_sets_worker_id_from_hostname(self, mock_settings: MagicMock) -> None:
        """Test that worker_id is set from HOSTNAME env var."""
        with patch("export_worker.worker.StarburstClient"), \
             patch("export_worker.worker.ControlPlaneClient"), \
             patch("export_worker.worker.GCSClient"), \
             patch.dict("os.environ", {"HOSTNAME": "export-worker-abc123"}):
            worker = ExportWorker(mock_settings)
            assert worker._worker_id == "export-worker-abc123"

    def test_init_creates_shutdown_event(self, mock_settings: MagicMock) -> None:
        """Test that shutdown event is created."""
        with patch("export_worker.worker.StarburstClient"), \
             patch("export_worker.worker.ControlPlaneClient"), \
             patch("export_worker.worker.GCSClient"):
            worker = ExportWorker(mock_settings)
            assert isinstance(worker._shutdown_event, asyncio.Event)
            assert not worker._shutdown_event.is_set()


class TestExportWorkerShutdown:
    """Tests for ExportWorker shutdown handling."""

    def test_request_shutdown_sets_event(self, mock_settings: MagicMock) -> None:
        """Test that request_shutdown sets the shutdown event."""
        with patch("export_worker.worker.StarburstClient"), \
             patch("export_worker.worker.ControlPlaneClient"), \
             patch("export_worker.worker.GCSClient"):
            worker = ExportWorker(mock_settings)
            assert not worker.is_shutting_down

            worker.request_shutdown()

            assert worker.is_shutting_down


class TestExportWorkerClaimPhase:
    """Tests for the claim phase."""

    @pytest.mark.asyncio
    async def test_claim_phase_returns_claimed_jobs(
        self,
        mock_settings: MagicMock,
        sample_export_jobs: list[ExportJob],
    ) -> None:
        """Test that claim phase returns claimed jobs."""
        with patch("export_worker.worker.StarburstClient"), \
             patch("export_worker.worker.ControlPlaneClient") as mock_cp_cls, \
             patch("export_worker.worker.GCSClient"):
            mock_cp = mock_cp_cls.from_config.return_value
            mock_cp.claim_export_jobs.return_value = sample_export_jobs

            worker = ExportWorker(mock_settings)
            claimed = await worker._claim_phase()

            assert len(claimed) == 2
            mock_cp.claim_export_jobs.assert_called_once_with(
                worker_id=worker._worker_id,
                limit=mock_settings.claim_limit,
            )

    @pytest.mark.asyncio
    async def test_claim_phase_returns_empty_on_error(
        self,
        mock_settings: MagicMock,
    ) -> None:
        """Test that claim phase returns empty list on error."""
        from export_worker.exceptions import ControlPlaneError

        with patch("export_worker.worker.StarburstClient"), \
             patch("export_worker.worker.ControlPlaneClient") as mock_cp_cls, \
             patch("export_worker.worker.GCSClient"):
            mock_cp = mock_cp_cls.from_config.return_value
            mock_cp.claim_export_jobs.side_effect = ControlPlaneError("Connection failed")

            worker = ExportWorker(mock_settings)
            claimed = await worker._claim_phase()

            assert claimed == []


class TestExportWorkerSubmitPhase:
    """Tests for the submit phase."""

    @pytest.mark.asyncio
    async def test_submit_phase_submits_jobs_direct_export(
        self,
        mock_settings: MagicMock,
        sample_export_jobs: list[ExportJob],
    ) -> None:
        """Test that submit phase submits jobs via direct export (default path)."""
        mock_settings.direct_export = True

        with patch("export_worker.worker.StarburstClient") as mock_starburst_cls, \
             patch("export_worker.worker.ControlPlaneClient") as mock_cp_cls, \
             patch("export_worker.worker.GCSClient"):
            mock_starburst = mock_starburst_cls.from_config.return_value
            mock_starburst.execute_and_export_async = AsyncMock(
                return_value=(100, 1024),
            )
            mock_cp = mock_cp_cls.from_config.return_value
            mock_cp.get_snapshot_jobs_result.return_value = SnapshotJobsResult(
                all_complete=False,
                any_failed=False,
                node_counts={},
                edge_counts={},
                total_size=0,
            )

            worker = ExportWorker(mock_settings)
            await worker._submit_phase(sample_export_jobs)

            assert mock_starburst.execute_and_export_async.call_count == 2
            # 2 completed + 2 snapshot-status-if-pending
            assert mock_cp.update_export_job.call_count == 2

    @pytest.mark.asyncio
    async def test_submit_phase_submits_jobs_unload(
        self,
        mock_settings: MagicMock,
        sample_export_jobs: list[ExportJob],
    ) -> None:
        """Test that submit phase submits jobs via UNLOAD when direct_export=False."""
        mock_settings.direct_export = False

        with patch("export_worker.worker.StarburstClient") as mock_starburst_cls, \
             patch("export_worker.worker.ControlPlaneClient") as mock_cp_cls, \
             patch("export_worker.worker.GCSClient"):
            mock_starburst = mock_starburst_cls.from_config.return_value
            mock_starburst.submit_unload_async = AsyncMock(
                return_value=QuerySubmissionResult(
                    query_id="query-123",
                    next_uri="http://starburst/v1/query/123/1",
                )
            )
            mock_cp = mock_cp_cls.from_config.return_value

            worker = ExportWorker(mock_settings)
            await worker._submit_phase(sample_export_jobs)

            assert mock_starburst.submit_unload_async.call_count == 2
            assert mock_cp.update_export_job.call_count == 2

    @pytest.mark.asyncio
    async def test_submit_phase_marks_failed_on_starburst_error(
        self,
        mock_settings: MagicMock,
        sample_export_jobs: list[ExportJob],
    ) -> None:
        """Test that submit phase marks job as failed on Starburst error."""
        from export_worker.exceptions import StarburstError

        mock_settings.direct_export = True

        with patch("export_worker.worker.StarburstClient") as mock_starburst_cls, \
             patch("export_worker.worker.ControlPlaneClient") as mock_cp_cls, \
             patch("export_worker.worker.GCSClient"):
            mock_starburst = mock_starburst_cls.from_config.return_value
            mock_starburst.execute_and_export_async = AsyncMock(
                side_effect=StarburstError("Connection refused")
            )
            mock_cp = mock_cp_cls.from_config.return_value

            worker = ExportWorker(mock_settings)
            await worker._submit_phase([sample_export_jobs[0]])

            # Should update job to failed
            mock_cp.update_export_job.assert_called_once()
            call_kwargs = mock_cp.update_export_job.call_args.kwargs
            assert call_kwargs["status"] == ExportJobStatus.FAILED
            assert "Connection refused" in call_kwargs["error_message"]

    @pytest.mark.asyncio
    async def test_submit_phase_stops_on_shutdown(
        self,
        mock_settings: MagicMock,
        sample_export_jobs: list[ExportJob],
    ) -> None:
        """Test that submit phase stops when shutdown is requested."""
        with patch("export_worker.worker.StarburstClient") as mock_starburst_cls, \
             patch("export_worker.worker.ControlPlaneClient"), \
             patch("export_worker.worker.GCSClient"):
            mock_starburst = mock_starburst_cls.from_config.return_value

            worker = ExportWorker(mock_settings)
            worker.request_shutdown()

            await worker._submit_phase(sample_export_jobs)

            # Should not submit any jobs (shutdown checked before gather)
            mock_starburst.execute_and_export_async.assert_not_called()
            mock_starburst.submit_unload_async.assert_not_called()


class TestExportWorkerPollPhase:
    """Tests for the poll phase."""

    @pytest.mark.asyncio
    async def test_poll_phase_polls_starburst(
        self,
        mock_settings: MagicMock,
        sample_submitted_export_job: ExportJob,
    ) -> None:
        """Test that poll phase polls Starburst for job status."""
        with patch("export_worker.worker.StarburstClient") as mock_starburst_cls, \
             patch("export_worker.worker.ControlPlaneClient") as mock_cp_cls, \
             patch("export_worker.worker.GCSClient") as mock_gcs_cls:
            mock_starburst = mock_starburst_cls.from_config.return_value
            mock_starburst.poll_query_async = AsyncMock(
                return_value=QueryPollResult(
                    state="FINISHED",
                    next_uri=None,
                    error_message=None,
                )
            )
            mock_cp = mock_cp_cls.from_config.return_value
            mock_cp.get_pollable_export_jobs.return_value = [sample_submitted_export_job]
            mock_cp.get_snapshot_jobs_result.return_value = SnapshotJobsResult(
                all_complete=True,
                any_failed=False,
                node_counts={"Customer": 1000},
                edge_counts={},
                total_size=1024,
            )
            mock_gcs = mock_gcs_cls.from_config.return_value
            mock_gcs.count_parquet_rows.return_value = (1000, 1024)

            worker = ExportWorker(mock_settings)
            polled = await worker._poll_phase()

            assert len(polled) == 1
            mock_starburst.poll_query_async.assert_called_once()

    @pytest.mark.asyncio
    async def test_poll_phase_schedules_next_poll_when_running(
        self,
        mock_settings: MagicMock,
        sample_submitted_export_job: ExportJob,
    ) -> None:
        """Test that poll phase schedules next poll when query still running."""
        with patch("export_worker.worker.StarburstClient") as mock_starburst_cls, \
             patch("export_worker.worker.ControlPlaneClient") as mock_cp_cls, \
             patch("export_worker.worker.GCSClient"):
            mock_starburst = mock_starburst_cls.from_config.return_value
            mock_starburst.poll_query_async = AsyncMock(
                return_value=QueryPollResult(
                    state="RUNNING",
                    next_uri="http://starburst/v1/query/123/2",
                    error_message=None,
                )
            )
            mock_cp = mock_cp_cls.from_config.return_value
            mock_cp.get_pollable_export_jobs.return_value = [sample_submitted_export_job]

            worker = ExportWorker(mock_settings)
            await worker._poll_phase()

            # Should update job with new next_poll_at
            mock_cp.update_export_job.assert_called_once()
            call_kwargs = mock_cp.update_export_job.call_args.kwargs
            assert "next_poll_at" in call_kwargs
            assert call_kwargs["poll_count"] == 2

    @pytest.mark.asyncio
    async def test_poll_phase_marks_failed_on_query_failure(
        self,
        mock_settings: MagicMock,
        sample_submitted_export_job: ExportJob,
    ) -> None:
        """Test that poll phase marks job as failed when query fails."""
        with patch("export_worker.worker.StarburstClient") as mock_starburst_cls, \
             patch("export_worker.worker.ControlPlaneClient") as mock_cp_cls, \
             patch("export_worker.worker.GCSClient"):
            mock_starburst = mock_starburst_cls.from_config.return_value
            mock_starburst.poll_query_async = AsyncMock(
                return_value=QueryPollResult(
                    state="FAILED",
                    next_uri=None,
                    error_message="Query execution failed",
                )
            )
            mock_cp = mock_cp_cls.from_config.return_value
            mock_cp.get_pollable_export_jobs.return_value = [sample_submitted_export_job]

            worker = ExportWorker(mock_settings)
            await worker._poll_phase()

            mock_cp.update_export_job.assert_called_once()
            call_kwargs = mock_cp.update_export_job.call_args.kwargs
            assert call_kwargs["status"] == ExportJobStatus.FAILED
            assert "Query execution failed" in call_kwargs["error_message"]


# =============================================================================
# SNAPSHOT TESTS DISABLED
# These tests are commented out as snapshot functionality has been disabled.
# =============================================================================
# class TestExportWorkerSnapshotFinalization:
#     """Tests for snapshot finalization."""
#
#     @pytest.mark.asyncio
#     async def test_finalize_snapshot_success(
#         self,
#         mock_settings: MagicMock,
#     ) -> None:
#         """Test snapshot finalization when all jobs succeed."""
#         with patch("export_worker.worker.StarburstClient"), \
#              patch("export_worker.worker.ControlPlaneClient") as mock_cp_cls, \
#              patch("export_worker.worker.GCSClient"):
#             mock_cp = mock_cp_cls.from_config.return_value
#             mock_cp.get_snapshot_jobs_result.return_value = SnapshotJobsResult(
#                 all_complete=True,
#                 any_failed=False,
#                 node_counts={"Customer": 1000},
#                 edge_counts={"PURCHASED": 500},
#                 total_size=2048,
#             )
#
#             worker = ExportWorker(mock_settings)
#
#             import structlog
#             log = structlog.get_logger()
#
#             await worker._check_snapshot_complete(123, log)
#
#             mock_cp.finalize_snapshot.assert_called_once()
#             call_kwargs = mock_cp.finalize_snapshot.call_args.kwargs
#             assert call_kwargs["success"] is True
#             assert call_kwargs["node_counts"] == {"Customer": 1000}
#             assert call_kwargs["edge_counts"] == {"PURCHASED": 500}
#             assert call_kwargs["size_bytes"] == 2048
#
#     @pytest.mark.asyncio
#     async def test_finalize_snapshot_failure(
#         self,
#         mock_settings: MagicMock,
#     ) -> None:
#         """Test snapshot finalization when some jobs fail."""
#         with patch("export_worker.worker.StarburstClient"), \
#              patch("export_worker.worker.ControlPlaneClient") as mock_cp_cls, \
#              patch("export_worker.worker.GCSClient"):
#             mock_cp = mock_cp_cls.from_config.return_value
#             mock_cp.get_snapshot_jobs_result.return_value = SnapshotJobsResult(
#                 all_complete=True,
#                 any_failed=True,
#                 first_error="Query execution failed",
#                 node_counts={},
#                 edge_counts={},
#                 total_size=0,
#             )
#
#             worker = ExportWorker(mock_settings)
#
#             import structlog
#             log = structlog.get_logger()
#
#             await worker._check_snapshot_complete(123, log)
#
#             mock_cp.finalize_snapshot.assert_called_once()
#             call_kwargs = mock_cp.finalize_snapshot.call_args.kwargs
#             assert call_kwargs["success"] is False
#             assert "Query execution failed" in call_kwargs["error_message"]
#
#     @pytest.mark.asyncio
#     async def test_finalize_snapshot_not_complete(
#         self,
#         mock_settings: MagicMock,
#     ) -> None:
#         """Test that finalization is skipped when jobs still running."""
#         with patch("export_worker.worker.StarburstClient"), \
#              patch("export_worker.worker.ControlPlaneClient") as mock_cp_cls, \
#              patch("export_worker.worker.GCSClient"):
#             mock_cp = mock_cp_cls.from_config.return_value
#             mock_cp.get_snapshot_jobs_result.return_value = SnapshotJobsResult(
#                 all_complete=False,
#                 any_failed=False,
#                 node_counts={},
#                 edge_counts={},
#                 total_size=0,
#             )
#
#             worker = ExportWorker(mock_settings)
#
#             import structlog
#             log = structlog.get_logger()
#
#             await worker._check_snapshot_complete(123, log)
#
#             # Should not finalize
#             mock_cp.finalize_snapshot.assert_not_called()


class TestExportWorkerMainLoop:
    """Tests for the main worker loop."""

    @pytest.mark.asyncio
    async def test_main_loop_runs_three_phases(
        self,
        mock_settings: MagicMock,
    ) -> None:
        """Test that main loop runs all three phases."""
        with patch("export_worker.worker.StarburstClient"), \
             patch("export_worker.worker.ControlPlaneClient") as mock_cp_cls, \
             patch("export_worker.worker.GCSClient"):
            mock_cp = mock_cp_cls.from_config.return_value
            mock_cp.claim_export_jobs.return_value = []
            mock_cp.get_pollable_export_jobs.return_value = []

            worker = ExportWorker(mock_settings)

            # Run for one iteration then shutdown
            async def run_and_stop():
                await asyncio.sleep(0.1)
                worker.request_shutdown()

            shutdown_task = asyncio.create_task(run_and_stop())
            await worker.run()
            await shutdown_task  # Ensure task completes

            # Both claim and poll should be called
            mock_cp.claim_export_jobs.assert_called()
            mock_cp.get_pollable_export_jobs.assert_called()
