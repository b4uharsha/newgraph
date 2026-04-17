"""Unit tests for the application lifespan.

Tests cover:
- Startup sequence
- Service initialization
- Error handling during startup
- Shutdown sequence
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI


@pytest.fixture
def mock_settings():
    """Create mock settings for lifespan tests."""
    settings = MagicMock()
    settings.wrapper.instance_id = "test-instance"
    settings.wrapper.snapshot_id = "test-snapshot"
    settings.wrapper.control_plane_url = "http://localhost:8080"
    settings.wrapper.gcs_base_path = "gs://test-bucket/snapshot"
    settings.wrapper.pod_name = "test-pod"
    settings.wrapper.pod_ip = "10.0.0.1"
    settings.wrapper.port = 8080
    settings.wrapper.instance_url = None
    settings.auth.internal_api_key = "test-key"
    settings.falkordb.database_path = MagicMock()
    settings.falkordb.database_path.__truediv__ = MagicMock(
        return_value=MagicMock(spec=["__str__"], __str__=lambda x: "/tmp/test_db")
    )
    settings.falkordb.query_timeout_ms = 60000
    settings.metrics.enabled = False
    settings.metrics.report_interval_seconds = 60
    return settings


@pytest.fixture
def mock_control_plane_client_class(mock_mapping):
    """Create a mock ControlPlaneClient class that returns proper async mocks."""

    def create_client(*args, **kwargs):
        client = MagicMock()
        client.update_status = AsyncMock()
        client.update_progress = AsyncMock()
        client.get_mapping = AsyncMock(return_value=mock_mapping)
        client.close = AsyncMock()
        return client

    return create_client


@pytest.fixture
def mock_db_service_class():
    """Create a mock DatabaseService class that returns proper async mocks."""

    def create_service(*args, **kwargs):
        service = MagicMock()
        service.graph_name = "test_graph"
        service.initialize = AsyncMock()
        service.create_schema = AsyncMock()
        service.load_data = AsyncMock()
        service.mark_ready = MagicMock()
        service.get_stats = AsyncMock(return_value={"total_nodes": 100, "total_edges": 200})
        service.close = AsyncMock()
        return service

    return create_service


@pytest.fixture
def mock_mapping():
    """Create mock mapping response."""
    mapping = MagicMock()
    mapping.id = 1
    mapping.name = "test-mapping"
    mapping.node_definitions = []
    mapping.edge_definitions = []
    return mapping


@pytest.fixture
def mock_lock_service_class():
    """Create a mock LockService class."""

    def create_service(*args, **kwargs):
        service = MagicMock()
        service.force_release = AsyncMock(return_value=None)
        return service

    return create_service


@pytest.fixture
def mock_algorithm_service_class():
    """Create a mock AlgorithmService class."""

    def create_service(*args, **kwargs):
        return MagicMock()

    return create_service


class TestLifespanStartup:
    """Tests for lifespan startup sequence."""

    @pytest.mark.asyncio
    async def test_startup_creates_services(
        self,
        mock_settings,
        mock_control_plane_client_class,
        mock_db_service_class,
        mock_lock_service_class,
        mock_algorithm_service_class,
        mock_mapping,
    ):
        """Startup creates all required services."""
        with (
            patch("wrapper.lifespan.get_settings", return_value=mock_settings),
            patch("wrapper.lifespan.ControlPlaneClient", side_effect=mock_control_plane_client_class),
            patch("wrapper.lifespan.DatabaseService", side_effect=mock_db_service_class),
            patch("wrapper.lifespan.LockService", side_effect=mock_lock_service_class),
            patch("wrapper.lifespan.AlgorithmService", side_effect=mock_algorithm_service_class),
            patch("wrapper.lifespan.GCSClient"),
            patch("wrapper.lifespan.set_startup_time"),
        ):
            from wrapper.lifespan import lifespan

            app = FastAPI()

            async with lifespan(app):
                # Verify services are created
                assert hasattr(app.state, "db_service")
                assert hasattr(app.state, "lock_service")
                assert hasattr(app.state, "control_plane_client")
                assert hasattr(app.state, "algorithm_service")

    @pytest.mark.asyncio
    async def test_startup_initializes_database(
        self,
        mock_settings,
        mock_control_plane_client_class,
        mock_db_service_class,
        mock_lock_service_class,
        mock_algorithm_service_class,
        mock_mapping,
    ):
        """Startup initializes the database."""
        with (
            patch("wrapper.lifespan.get_settings", return_value=mock_settings),
            patch("wrapper.lifespan.ControlPlaneClient", side_effect=mock_control_plane_client_class),
            patch("wrapper.lifespan.DatabaseService", side_effect=mock_db_service_class),
            patch("wrapper.lifespan.LockService", side_effect=mock_lock_service_class),
            patch("wrapper.lifespan.AlgorithmService", side_effect=mock_algorithm_service_class),
            patch("wrapper.lifespan.GCSClient"),
            patch("wrapper.lifespan.set_startup_time"),
        ):
            from wrapper.lifespan import lifespan

            app = FastAPI()

            async with lifespan(app):
                app.state.db_service.initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_startup_loads_mapping(
        self,
        mock_settings,
        mock_control_plane_client_class,
        mock_db_service_class,
        mock_lock_service_class,
        mock_algorithm_service_class,
        mock_mapping,
    ):
        """Startup fetches mapping from Control Plane."""
        with (
            patch("wrapper.lifespan.get_settings", return_value=mock_settings),
            patch("wrapper.lifespan.ControlPlaneClient", side_effect=mock_control_plane_client_class),
            patch("wrapper.lifespan.DatabaseService", side_effect=mock_db_service_class),
            patch("wrapper.lifespan.LockService", side_effect=mock_lock_service_class),
            patch("wrapper.lifespan.AlgorithmService", side_effect=mock_algorithm_service_class),
            patch("wrapper.lifespan.GCSClient"),
            patch("wrapper.lifespan.set_startup_time"),
        ):
            from wrapper.lifespan import lifespan

            app = FastAPI()

            async with lifespan(app):
                app.state.control_plane_client.get_mapping.assert_called_once()

    @pytest.mark.asyncio
    async def test_startup_creates_schema(
        self,
        mock_settings,
        mock_control_plane_client_class,
        mock_db_service_class,
        mock_lock_service_class,
        mock_algorithm_service_class,
        mock_mapping,
    ):
        """Startup creates schema from mapping."""
        with (
            patch("wrapper.lifespan.get_settings", return_value=mock_settings),
            patch("wrapper.lifespan.ControlPlaneClient", side_effect=mock_control_plane_client_class),
            patch("wrapper.lifespan.DatabaseService", side_effect=mock_db_service_class),
            patch("wrapper.lifespan.LockService", side_effect=mock_lock_service_class),
            patch("wrapper.lifespan.AlgorithmService", side_effect=mock_algorithm_service_class),
            patch("wrapper.lifespan.GCSClient"),
            patch("wrapper.lifespan.set_startup_time"),
        ):
            from wrapper.lifespan import lifespan

            app = FastAPI()

            async with lifespan(app):
                app.state.db_service.create_schema.assert_called_once_with(mock_mapping)

    @pytest.mark.asyncio
    async def test_startup_loads_data(
        self,
        mock_settings,
        mock_control_plane_client_class,
        mock_db_service_class,
        mock_lock_service_class,
        mock_algorithm_service_class,
        mock_mapping,
    ):
        """Startup loads data from GCS."""
        with (
            patch("wrapper.lifespan.get_settings", return_value=mock_settings),
            patch("wrapper.lifespan.ControlPlaneClient", side_effect=mock_control_plane_client_class),
            patch("wrapper.lifespan.DatabaseService", side_effect=mock_db_service_class),
            patch("wrapper.lifespan.LockService", side_effect=mock_lock_service_class),
            patch("wrapper.lifespan.AlgorithmService", side_effect=mock_algorithm_service_class),
            patch("wrapper.lifespan.GCSClient"),
            patch("wrapper.lifespan.set_startup_time"),
        ):
            from wrapper.lifespan import lifespan

            app = FastAPI()

            async with lifespan(app):
                app.state.db_service.load_data.assert_called_once()

    @pytest.mark.asyncio
    async def test_startup_reports_ready(
        self,
        mock_settings,
        mock_control_plane_client_class,
        mock_db_service_class,
        mock_lock_service_class,
        mock_algorithm_service_class,
        mock_mapping,
    ):
        """Startup reports ready status to Control Plane."""
        with (
            patch("wrapper.lifespan.get_settings", return_value=mock_settings),
            patch("wrapper.lifespan.ControlPlaneClient", side_effect=mock_control_plane_client_class),
            patch("wrapper.lifespan.DatabaseService", side_effect=mock_db_service_class),
            patch("wrapper.lifespan.LockService", side_effect=mock_lock_service_class),
            patch("wrapper.lifespan.AlgorithmService", side_effect=mock_algorithm_service_class),
            patch("wrapper.lifespan.GCSClient"),
            patch("wrapper.lifespan.set_startup_time"),
        ):
            from wrapper.lifespan import lifespan

            app = FastAPI()

            async with lifespan(app):
                # Find the call that sets status to "running"
                calls = app.state.control_plane_client.update_status.call_args_list
                running_calls = [c for c in calls if c.kwargs.get("status") == "running"]
                assert len(running_calls) == 1


class TestLifespanStartupErrors:
    """Tests for error handling during startup."""

    @pytest.mark.asyncio
    async def test_startup_failure_reports_error(
        self,
        mock_settings,
        mock_control_plane_client_class,
        mock_lock_service_class,
        mock_mapping,
    ):
        """Startup failure reports error to Control Plane."""
        error_raised = Exception("Database init failed")

        def create_failing_db_service(*args, **kwargs):
            service = MagicMock()
            service.graph_name = "test_graph"
            service.initialize = AsyncMock(side_effect=error_raised)
            service.close = AsyncMock()
            return service

        with (
            patch("wrapper.lifespan.get_settings", return_value=mock_settings),
            patch("wrapper.lifespan.ControlPlaneClient", side_effect=mock_control_plane_client_class),
            patch("wrapper.lifespan.DatabaseService", side_effect=create_failing_db_service),
            patch("wrapper.lifespan.LockService", side_effect=mock_lock_service_class),
            patch("wrapper.lifespan.set_startup_time"),
        ):
            from wrapper.lifespan import lifespan

            app = FastAPI()

            with pytest.raises(Exception, match="Database init failed"):
                async with lifespan(app):
                    pass

            # Verify error was reported
            calls = app.state.control_plane_client.update_status.call_args_list
            failed_calls = [c for c in calls if c.kwargs.get("status") == "failed"]
            assert len(failed_calls) >= 1

    @pytest.mark.asyncio
    async def test_startup_oom_error_handling(
        self,
        mock_settings,
        mock_control_plane_client_class,
        mock_lock_service_class,
        mock_algorithm_service_class,
        mock_mapping,
    ):
        """OOM error is reported with correct error code."""
        from wrapper.exceptions import OutOfMemoryError

        oom_error = OutOfMemoryError(
            memory_limit_bytes=1000000,
            current_usage_bytes=2000000,
        )

        def create_oom_db_service(*args, **kwargs):
            service = MagicMock()
            service.graph_name = "test_graph"
            service.initialize = AsyncMock()
            service.create_schema = AsyncMock()
            service.load_data = AsyncMock(side_effect=oom_error)
            service.close = AsyncMock()
            return service

        with (
            patch("wrapper.lifespan.get_settings", return_value=mock_settings),
            patch("wrapper.lifespan.ControlPlaneClient", side_effect=mock_control_plane_client_class),
            patch("wrapper.lifespan.DatabaseService", side_effect=create_oom_db_service),
            patch("wrapper.lifespan.LockService", side_effect=mock_lock_service_class),
            patch("wrapper.lifespan.AlgorithmService", side_effect=mock_algorithm_service_class),
            patch("wrapper.lifespan.GCSClient"),
            patch("wrapper.lifespan.set_startup_time"),
        ):
            from wrapper.lifespan import lifespan

            app = FastAPI()

            with pytest.raises(OutOfMemoryError):
                async with lifespan(app):
                    pass

            # Verify OOM_KILLED error code was reported
            calls = app.state.control_plane_client.update_status.call_args_list
            oom_calls = [c for c in calls if c.kwargs.get("error_code") == "OOM_KILLED"]
            assert len(oom_calls) >= 1


class TestLifespanShutdown:
    """Tests for lifespan shutdown sequence."""

    @pytest.mark.asyncio
    async def test_shutdown_releases_locks(
        self,
        mock_settings,
        mock_control_plane_client_class,
        mock_db_service_class,
        mock_lock_service_class,
        mock_algorithm_service_class,
        mock_mapping,
    ):
        """Shutdown force releases any held locks."""
        with (
            patch("wrapper.lifespan.get_settings", return_value=mock_settings),
            patch("wrapper.lifespan.ControlPlaneClient", side_effect=mock_control_plane_client_class),
            patch("wrapper.lifespan.DatabaseService", side_effect=mock_db_service_class),
            patch("wrapper.lifespan.LockService", side_effect=mock_lock_service_class),
            patch("wrapper.lifespan.AlgorithmService", side_effect=mock_algorithm_service_class),
            patch("wrapper.lifespan.GCSClient"),
            patch("wrapper.lifespan.set_startup_time"),
        ):
            from wrapper.lifespan import lifespan

            app = FastAPI()

            async with lifespan(app):
                pass

            app.state.lock_service.force_release.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_closes_database(
        self,
        mock_settings,
        mock_control_plane_client_class,
        mock_db_service_class,
        mock_lock_service_class,
        mock_algorithm_service_class,
        mock_mapping,
    ):
        """Shutdown closes database connection."""
        with (
            patch("wrapper.lifespan.get_settings", return_value=mock_settings),
            patch("wrapper.lifespan.ControlPlaneClient", side_effect=mock_control_plane_client_class),
            patch("wrapper.lifespan.DatabaseService", side_effect=mock_db_service_class),
            patch("wrapper.lifespan.LockService", side_effect=mock_lock_service_class),
            patch("wrapper.lifespan.AlgorithmService", side_effect=mock_algorithm_service_class),
            patch("wrapper.lifespan.GCSClient"),
            patch("wrapper.lifespan.set_startup_time"),
        ):
            from wrapper.lifespan import lifespan

            app = FastAPI()

            async with lifespan(app):
                pass

            app.state.db_service.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_reports_stopping(
        self,
        mock_settings,
        mock_control_plane_client_class,
        mock_db_service_class,
        mock_lock_service_class,
        mock_algorithm_service_class,
        mock_mapping,
    ):
        """Shutdown reports stopping status to Control Plane."""
        with (
            patch("wrapper.lifespan.get_settings", return_value=mock_settings),
            patch("wrapper.lifespan.ControlPlaneClient", side_effect=mock_control_plane_client_class),
            patch("wrapper.lifespan.DatabaseService", side_effect=mock_db_service_class),
            patch("wrapper.lifespan.LockService", side_effect=mock_lock_service_class),
            patch("wrapper.lifespan.AlgorithmService", side_effect=mock_algorithm_service_class),
            patch("wrapper.lifespan.GCSClient"),
            patch("wrapper.lifespan.set_startup_time"),
        ):
            from wrapper.lifespan import lifespan

            app = FastAPI()

            async with lifespan(app):
                pass

            # Find the stopping status call
            calls = app.state.control_plane_client.update_status.call_args_list
            stopping_calls = [c for c in calls if c.kwargs.get("status") == "stopping"]
            assert len(stopping_calls) >= 1

    @pytest.mark.asyncio
    async def test_shutdown_closes_control_plane_client(
        self,
        mock_settings,
        mock_control_plane_client_class,
        mock_db_service_class,
        mock_lock_service_class,
        mock_algorithm_service_class,
        mock_mapping,
    ):
        """Shutdown closes Control Plane client."""
        with (
            patch("wrapper.lifespan.get_settings", return_value=mock_settings),
            patch("wrapper.lifespan.ControlPlaneClient", side_effect=mock_control_plane_client_class),
            patch("wrapper.lifespan.DatabaseService", side_effect=mock_db_service_class),
            patch("wrapper.lifespan.LockService", side_effect=mock_lock_service_class),
            patch("wrapper.lifespan.AlgorithmService", side_effect=mock_algorithm_service_class),
            patch("wrapper.lifespan.GCSClient"),
            patch("wrapper.lifespan.set_startup_time"),
        ):
            from wrapper.lifespan import lifespan

            app = FastAPI()

            async with lifespan(app):
                pass

            app.state.control_plane_client.close.assert_called_once()


class TestGetErrorCode:
    """Tests for error code mapping."""

    def test_control_plane_error_mapped(self):
        """ControlPlaneError maps to MAPPING_FETCH_ERROR."""
        from wrapper.exceptions import ControlPlaneError
        from wrapper.lifespan import _get_error_code

        exc = ControlPlaneError("Failed to fetch mapping")
        assert _get_error_code(exc) == "MAPPING_FETCH_ERROR"

    def test_data_load_error_mapped(self):
        """DataLoadError maps to DATA_LOAD_ERROR."""
        from wrapper.exceptions import DataLoadError
        from wrapper.lifespan import _get_error_code

        exc = DataLoadError("Failed to load data")
        assert _get_error_code(exc) == "DATA_LOAD_ERROR"

    def test_database_error_mapped(self):
        """DatabaseError maps to DATABASE_ERROR."""
        from wrapper.exceptions import DatabaseError
        from wrapper.lifespan import _get_error_code

        exc = DatabaseError("Database error")
        assert _get_error_code(exc) == "DATABASE_ERROR"

    def test_unknown_error_mapped_to_startup_failed(self):
        """Unknown errors map to STARTUP_FAILED."""
        from wrapper.lifespan import _get_error_code

        exc = ValueError("Unknown error")
        assert _get_error_code(exc) == "STARTUP_FAILED"
