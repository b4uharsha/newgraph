"""Unit tests for the lifespan module."""

from __future__ import annotations

import asyncio
import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from graph_olap_schemas import (
    EdgeDefinition,
    InstanceMappingResponse,
    NodeDefinition,
    PrimaryKeyDefinition,
    PropertyDefinition,
)


@pytest.fixture
def mock_settings() -> MagicMock:
    """Create mock settings."""
    settings = MagicMock()
    settings.wrapper.instance_id = "test-instance"
    settings.wrapper.snapshot_id = "test-snapshot"
    settings.wrapper.control_plane_url = "http://localhost:8080"
    settings.wrapper.gcs_base_path = "gs://test-bucket/data"
    settings.wrapper.pod_name = "wrapper-pod-123"
    settings.wrapper.pod_ip = "10.0.0.1"
    settings.wrapper.port = 8000
    settings.wrapper.instance_url = None  # Force fallback to pod_ip:port
    settings.ryugraph.database_path = "/tmp/test_db"
    settings.ryugraph.buffer_pool_size = 1024 * 1024
    settings.ryugraph.max_threads = 4
    settings.metrics.enabled = False
    settings.metrics.report_interval_seconds = 60
    settings.internal_auth.internal_api_key = "test-key"
    return settings


@pytest.fixture
def sample_mapping() -> InstanceMappingResponse:
    """Create sample mapping definition using shared schema type."""
    return InstanceMappingResponse(
        snapshot_id=1,
        mapping_id=1,
        mapping_version=1,
        gcs_path="gs://test-bucket/test-user/test-mapping/test-snapshot/",
        node_definitions=[
            NodeDefinition(
                label="Person",
                sql="SELECT * FROM persons",
                primary_key=PrimaryKeyDefinition(name="id", type="STRING"),
                properties=[PropertyDefinition(name="name", type="STRING")],
            ),
        ],
        edge_definitions=[
            EdgeDefinition(
                type="KNOWS",
                from_node="Person",
                to_node="Person",
                sql="SELECT * FROM knows",
                from_key="from_id",
                to_key="to_id",
                properties=[],
            ),
        ],
    )


class TestLifespan:
    """Tests for the lifespan context manager."""

    @pytest.mark.unit
    async def test_lifespan_startup_success(
        self, mock_settings: MagicMock, sample_mapping: InstanceMappingResponse
    ) -> None:
        """Lifespan startup completes successfully."""
        mock_cp = MagicMock()
        mock_cp.update_status = AsyncMock()
        mock_cp.update_progress = AsyncMock()
        mock_cp.update_metrics = AsyncMock()
        mock_cp.get_mapping = AsyncMock(return_value=sample_mapping)
        mock_cp.close = AsyncMock()

        mock_db = MagicMock()
        mock_db.initialize = AsyncMock()
        mock_db.create_schema = AsyncMock()
        mock_db.load_data = AsyncMock(return_value={"nodes": 100, "edges": 200})
        mock_db.close = AsyncMock()

        mock_lock = MagicMock()
        mock_lock.force_release = AsyncMock(return_value=None)

        with patch("wrapper.lifespan.get_settings", return_value=mock_settings):
            with patch("wrapper.lifespan.ControlPlaneClient", return_value=mock_cp):
                with patch("wrapper.lifespan.DatabaseService", return_value=mock_db):
                    with patch("wrapper.lifespan.LockService", return_value=mock_lock):
                        with patch("wrapper.lifespan.AlgorithmService"):
                            with patch("wrapper.lifespan.register_native_algorithms"):
                                with patch("wrapper.lifespan.register_common_algorithms"):
                                    from wrapper.lifespan import lifespan

                                    app = FastAPI()
                                    async with lifespan(app):
                                        assert hasattr(app.state, "control_plane_client")
                                        assert hasattr(app.state, "db_service")

        # Verify status updates with new signature (pod_name, pod_ip, instance_url)
        mock_cp.update_status.assert_any_call(
            status="starting",
            pod_name="wrapper-pod-123",
            pod_ip="10.0.0.1",
        )
        # Running status now includes graph stats per schema (node_count, edge_count)
        mock_cp.update_status.assert_any_call(
            status="running",
            instance_url="http://10.0.0.1:8000",
            node_count=100,  # From mock load_data result {"nodes": 100, ...}
            edge_count=200,  # From mock load_data result {..., "edges": 200}
        )

    @pytest.mark.unit
    async def test_lifespan_startup_failure_reports_error(self, mock_settings: MagicMock) -> None:
        """Startup failure is reported to Control Plane via update_status."""
        mock_cp = MagicMock()
        mock_cp.update_status = AsyncMock()
        mock_cp.update_progress = AsyncMock()
        mock_cp.get_mapping = AsyncMock(side_effect=Exception("Connection failed"))
        mock_cp.close = AsyncMock()

        mock_db = MagicMock()
        mock_db.initialize = AsyncMock()
        mock_db.close = AsyncMock()

        mock_lock = MagicMock()
        mock_lock.force_release = AsyncMock(return_value=None)

        with patch("wrapper.lifespan.get_settings", return_value=mock_settings):
            with patch("wrapper.lifespan.ControlPlaneClient", return_value=mock_cp):
                with patch("wrapper.lifespan.DatabaseService", return_value=mock_db):
                    with patch("wrapper.lifespan.LockService", return_value=mock_lock):
                        with patch("wrapper.lifespan.AlgorithmService"):
                            from wrapper.lifespan import lifespan

                            app = FastAPI()
                            with pytest.raises(Exception, match="Connection failed"):
                                async with lifespan(app):
                                    pass

        # Verify error was reported via update_status with error fields
        # Find the 'failed' status call
        failed_calls = [
            call
            for call in mock_cp.update_status.call_args_list
            if call.kwargs.get("status") == "failed"
        ]
        assert len(failed_calls) == 1
        failed_call = failed_calls[0]
        assert failed_call.kwargs.get("error_code") == "STARTUP_FAILED"
        assert "Connection failed" in failed_call.kwargs.get("error_message", "")
        assert failed_call.kwargs.get("stack_trace") is not None


class TestMetricsReporter:
    """Tests for the metrics reporter background task."""

    @pytest.mark.unit
    async def test_metrics_reporter_reports_stats(self) -> None:
        """Metrics reporter sends stats to Control Plane."""
        mock_client = MagicMock()
        mock_client.update_metrics = AsyncMock()

        from wrapper.lifespan import _metrics_reporter

        # Run for a short time then cancel
        task = asyncio.create_task(
            _metrics_reporter(
                control_plane_client=mock_client,
                interval_seconds=1,
            )
        )

        # Let it run one cycle
        await asyncio.sleep(1.5)
        task.cancel()

        with contextlib.suppress(asyncio.CancelledError):
            await task

        # Verify metrics were reported
        assert mock_client.update_metrics.call_count >= 1

    @pytest.mark.unit
    async def test_metrics_reporter_reports_resource_metrics(self) -> None:
        """Metrics reporter sends resource metrics regardless of DB ready state.

        Note: Per schema, update_metrics only reports resource usage (memory, disk).
        Graph stats (node/edge counts) are sent via update_status.
        """
        mock_client = MagicMock()
        mock_client.update_metrics = AsyncMock()

        from wrapper.lifespan import _metrics_reporter

        task = asyncio.create_task(
            _metrics_reporter(
                control_plane_client=mock_client,
                interval_seconds=1,
            )
        )

        await asyncio.sleep(1.5)
        task.cancel()

        with contextlib.suppress(asyncio.CancelledError):
            await task

        # Should have called update_metrics with memory_usage_bytes only
        mock_client.update_metrics.assert_called()
        call_kwargs = mock_client.update_metrics.call_args
        assert "memory_usage_bytes" in call_kwargs.kwargs
        # Should NOT have node_count or edge_count (per schema change)
        assert "node_count" not in call_kwargs.kwargs
        assert "edge_count" not in call_kwargs.kwargs
