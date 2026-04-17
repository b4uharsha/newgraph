"""Unit tests for background job scheduler.

Tests scheduler lifecycle, job registration, and metrics recording.
"""

from unittest.mock import AsyncMock, patch

import pytest

from control_plane.config import Settings
from control_plane.jobs.scheduler import BackgroundJobScheduler


@pytest.fixture
def test_settings():
    """Create test settings with short intervals."""
    return Settings(
        # Database settings (required)
        database_url="postgresql+asyncpg://test:test@localhost:5432/test",
        # Job intervals (short for testing)
        reconciliation_job_interval_seconds=60,
        lifecycle_job_interval_seconds=60,
        schema_cache_job_interval_seconds=300,
    )


@pytest.mark.asyncio
class TestSchedulerLifecycle:
    """Test scheduler startup and shutdown."""

    async def test_scheduler_starts_successfully(self, test_settings):
        """Test scheduler starts and registers jobs."""
        scheduler = BackgroundJobScheduler(test_settings)

        await scheduler.start()

        assert scheduler._running is True
        assert scheduler._scheduler is not None

        # Clean up
        await scheduler.stop()

    async def test_scheduler_registers_six_jobs(self, test_settings):
        """Test scheduler registers all 6 jobs."""
        scheduler = BackgroundJobScheduler(test_settings)

        await scheduler.start()

        stats = scheduler.get_job_stats()
        assert stats["running"] is True
        assert len(stats["jobs"]) == 6

        # Verify job IDs
        job_ids = {job["id"] for job in stats["jobs"]}
        assert job_ids == {
            "reconciliation",
            "lifecycle",
            "export_reconciliation",
            "schema_cache",
            "instance_orchestration",
            "resource_monitor",
        }

        # Clean up
        await scheduler.stop()

    async def test_scheduler_stops_gracefully(self, test_settings):
        """Test scheduler stops gracefully."""
        scheduler = BackgroundJobScheduler(test_settings)

        await scheduler.start()
        assert scheduler._running is True

        await scheduler.stop()
        assert scheduler._running is False

    async def test_scheduler_prevents_double_start(self, test_settings):
        """Test scheduler prevents starting twice."""
        scheduler = BackgroundJobScheduler(test_settings)

        await scheduler.start()
        assert scheduler._running is True

        # Try to start again - should be no-op
        with patch("control_plane.jobs.scheduler.logger") as mock_logger:
            await scheduler.start()
            mock_logger.warning.assert_called_once_with("scheduler_already_running")

        # Clean up
        await scheduler.stop()

    async def test_scheduler_stop_when_not_running(self, test_settings):
        """Test stopping scheduler when not running is safe."""
        scheduler = BackgroundJobScheduler(test_settings)

        # Stop without starting - should be no-op
        await scheduler.stop()
        assert scheduler._running is False

    async def test_get_job_stats_when_not_running(self, test_settings):
        """Test get_job_stats returns empty when not running."""
        scheduler = BackgroundJobScheduler(test_settings)

        stats = scheduler.get_job_stats()
        assert stats == {"running": False, "jobs": []}


@pytest.mark.asyncio
class TestJobWrapper:
    """Test job wrapper functionality (error handling, metrics)."""

    async def test_job_wrapper_records_success_metrics(self, test_settings):
        """Test job wrapper records metrics on successful execution."""
        scheduler = BackgroundJobScheduler(test_settings)

        # Mock job function
        mock_job = AsyncMock()

        # Mock metrics
        with patch("control_plane.jobs.scheduler.metrics") as mock_metrics:
            # Create wrapped job
            wrapped = scheduler._wrap_job(mock_job, "test_job")

            # Execute wrapped job
            await wrapped()

            # Verify job was called
            mock_job.assert_called_once()

            # Verify success metrics recorded
            mock_metrics.job_execution_total.labels.assert_called_with(
                job_name="test_job", status="success"
            )
            mock_metrics.job_execution_total.labels().inc.assert_called_once()

            # Verify duration metrics recorded
            mock_metrics.job_execution_duration_seconds.labels.assert_called_with(
                job_name="test_job"
            )
            mock_metrics.job_execution_duration_seconds.labels().observe.assert_called_once()

    async def test_job_wrapper_records_failure_metrics(self, test_settings):
        """Test job wrapper records metrics on failed execution."""
        scheduler = BackgroundJobScheduler(test_settings)

        # Mock job function that raises exception
        mock_job = AsyncMock(side_effect=RuntimeError("Test error"))

        # Mock metrics
        with patch("control_plane.jobs.scheduler.metrics") as mock_metrics:
            # Create wrapped job
            wrapped = scheduler._wrap_job(mock_job, "test_job")

            # Execute wrapped job - should not raise
            await wrapped()

            # Verify job was called
            mock_job.assert_called_once()

            # Verify failure metrics recorded
            mock_metrics.job_execution_total.labels.assert_called_with(
                job_name="test_job", status="failed"
            )
            mock_metrics.job_execution_total.labels().inc.assert_called_once()

            # Verify duration still recorded even on failure
            mock_metrics.job_execution_duration_seconds.labels.assert_called_with(
                job_name="test_job"
            )
            mock_metrics.job_execution_duration_seconds.labels().observe.assert_called_once()

    async def test_job_wrapper_logs_success(self, test_settings):
        """Test job wrapper logs job start and completion."""
        scheduler = BackgroundJobScheduler(test_settings)
        mock_job = AsyncMock()

        with patch("control_plane.jobs.scheduler.logger") as mock_logger:
            wrapped = scheduler._wrap_job(mock_job, "test_job")
            await wrapped()

            # Verify logging
            assert mock_logger.info.call_count == 2
            mock_logger.info.assert_any_call("job_started", job="test_job")
            mock_logger.info.assert_any_call("job_completed", job="test_job")

    async def test_job_wrapper_logs_failure(self, test_settings):
        """Test job wrapper logs job failures with exception."""
        scheduler = BackgroundJobScheduler(test_settings)
        mock_job = AsyncMock(side_effect=RuntimeError("Test error"))

        with patch("control_plane.jobs.scheduler.logger") as mock_logger:
            wrapped = scheduler._wrap_job(mock_job, "test_job")
            await wrapped()

            # Verify error logging
            mock_logger.exception.assert_called_once_with(
                "job_failed", job="test_job", error="Test error"
            )

    async def test_job_wrapper_does_not_raise_on_failure(self, test_settings):
        """Test job wrapper catches exceptions and doesn't crash scheduler."""
        scheduler = BackgroundJobScheduler(test_settings)
        mock_job = AsyncMock(side_effect=RuntimeError("Test error"))

        wrapped = scheduler._wrap_job(mock_job, "test_job")

        # Should not raise - exception should be caught
        await wrapped()  # No assertion needed - test passes if no exception

    async def test_job_wrapper_records_duration(self, test_settings):
        """Test job wrapper records accurate execution duration."""
        scheduler = BackgroundJobScheduler(test_settings)

        # Mock job that takes ~100ms
        async def slow_job():
            await asyncio.sleep(0.1)

        with patch("control_plane.jobs.scheduler.metrics") as mock_metrics:
            wrapped = scheduler._wrap_job(slow_job, "slow_job")
            await wrapped()

            # Get the duration that was observed
            observe_call = mock_metrics.job_execution_duration_seconds.labels().observe.call_args
            duration = observe_call[0][0]

            # Duration should be approximately 0.1 seconds (allow 50ms tolerance)
            assert 0.05 < duration < 0.15


@pytest.mark.asyncio
class TestJobConfiguration:
    """Test job configuration and intervals."""

    async def test_reconciliation_job_uses_configured_interval(self, test_settings):
        """Test reconciliation job uses interval from settings."""
        test_settings.reconciliation_job_interval_seconds = 123

        scheduler = BackgroundJobScheduler(test_settings)
        await scheduler.start()

        # Find reconciliation job
        jobs = scheduler._scheduler.get_jobs()
        recon_job = next(job for job in jobs if job.id == "reconciliation")

        # Check trigger interval
        assert recon_job.trigger.interval.total_seconds() == 123

        await scheduler.stop()

    async def test_lifecycle_job_uses_configured_interval(self, test_settings):
        """Test lifecycle job uses interval from settings."""
        test_settings.lifecycle_job_interval_seconds = 456

        scheduler = BackgroundJobScheduler(test_settings)
        await scheduler.start()

        # Find lifecycle job
        jobs = scheduler._scheduler.get_jobs()
        lifecycle_job = next(job for job in jobs if job.id == "lifecycle")

        # Check trigger interval
        assert lifecycle_job.trigger.interval.total_seconds() == 456

        await scheduler.stop()

    async def test_export_reconciliation_job_uses_fixed_interval(self, test_settings):
        """Test export reconciliation job uses fixed 1 minute interval."""
        scheduler = BackgroundJobScheduler(test_settings)
        await scheduler.start()

        # Find export reconciliation job
        jobs = scheduler._scheduler.get_jobs()
        export_job = next(job for job in jobs if job.id == "export_reconciliation")

        # Check trigger interval is fixed at 60 seconds
        assert export_job.trigger.interval.total_seconds() == 60

        await scheduler.stop()

    async def test_schema_cache_job_uses_configured_interval(self, test_settings):
        """Test schema cache job uses interval from settings."""
        test_settings.schema_cache_job_interval_seconds = 86400

        scheduler = BackgroundJobScheduler(test_settings)
        await scheduler.start()

        # Find schema cache job
        jobs = scheduler._scheduler.get_jobs()
        schema_job = next(job for job in jobs if job.id == "schema_cache")

        # Check trigger interval
        assert schema_job.trigger.interval.total_seconds() == 86400

        await scheduler.stop()


# Import asyncio for sleep in tests
import asyncio
