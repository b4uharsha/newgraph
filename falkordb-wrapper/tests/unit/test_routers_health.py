"""Unit tests for health router.

Note: Uses REAL LockService (not mocks) because LockService has no external
dependencies - it's pure in-memory Python. DatabaseService is still mocked
because it requires actual database I/O. This follows Google testing best
practices: only mock at system boundaries.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI, status
from fastapi.testclient import TestClient

from wrapper.routers import health
from wrapper.services.lock import LockService


class TestHealthRouter:
    """Tests for health router."""

    @pytest.fixture
    def mock_database_service(self):
        """Create a mock database service.

        DatabaseService IS mocked because it requires FalkorDB (external I/O).
        """
        service = Mock()
        service.is_initialized = True
        service.is_ready = True
        service.is_connected = True
        service.graph_name = "test_graph"
        service.ready_at = Mock()
        service.ready_at.isoformat = Mock(return_value="2025-01-15T10:00:00Z")
        service.execute_query = AsyncMock(return_value={"columns": ["1"], "rows": [[1]], "row_count": 1})
        service.get_stats = AsyncMock(return_value={
            "node_counts": {"Person": 100, "Company": 50},
            "edge_counts": {"KNOWS": 200, "WORKS_AT": 75},
            "total_nodes": 150,
            "total_edges": 275,
            "memory_usage_bytes": 104857600,
            "memory_usage_mb": 100.0,
        })
        # Data load warnings (LOAD CSV feature)
        service.get_data_load_warnings = Mock(return_value=[])
        return service

    @pytest.fixture
    def lock_service(self):
        """Create a REAL lock service.

        LockService is NOT mocked because it has no external dependencies -
        it's pure in-memory Python with no I/O.
        """
        return LockService()

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings.

        Settings ARE mocked because they come from environment/config files.
        """
        settings = Mock()
        settings.wrapper = Mock()
        settings.wrapper.instance_id = "test-instance-id"
        settings.wrapper.snapshot_id = "test-snapshot-123"
        settings.wrapper.mapping_id = "test-mapping-456"
        settings.wrapper.owner_id = "test-owner"
        return settings

    @pytest.fixture
    def test_app(self, mock_database_service, lock_service, mock_settings):
        """Create a test FastAPI app with proper DI via app.state."""
        from wrapper.dependencies import (
            get_app_settings,
        )

        app = FastAPI()
        app.include_router(health.router)

        # Set up app state
        # - DatabaseService: MOCKED (external I/O)
        # - LockService: REAL (pure in-memory)
        app.state.db_service = mock_database_service
        app.state.lock_service = lock_service

        # Override settings dependency
        app.dependency_overrides[get_app_settings] = lambda: mock_settings

        return app

    @pytest.mark.unit
    def test_health_always_returns_200(self, test_app):
        """Test /health always returns 200 (liveness probe)."""
        client = TestClient(test_app)
        response = client.get("/health")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data

    @pytest.mark.unit
    def test_health_does_not_check_database(self, test_app, mock_database_service):
        """Test /health returns 200 even when database is not initialized."""
        # Even with database not initialized, health should return 200
        mock_database_service.is_initialized = False
        mock_database_service.is_ready = False

        client = TestClient(test_app)
        response = client.get("/health")

        # Liveness probe should always succeed if process is alive
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "healthy"

    @pytest.mark.unit
    def test_ready_when_ready(self, test_app, mock_database_service):
        """Test /ready returns 200 when database is ready."""
        mock_database_service.is_ready = True

        client = TestClient(test_app)
        response = client.get("/ready")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data

    @pytest.mark.unit
    def test_ready_when_not_ready(self, test_app, mock_database_service):
        """Test /ready returns 503 when database not ready."""
        mock_database_service.is_ready = False

        client = TestClient(test_app)
        response = client.get("/ready")

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    @pytest.mark.unit
    def test_status_endpoint(self, test_app, mock_database_service):
        """Test /status returns detailed information (flat structure)."""
        client = TestClient(test_app)
        response = client.get("/status")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Flat structure - no "data" wrapper
        assert "instance_id" in data
        assert "snapshot_id" in data
        assert "mapping_id" in data
        assert "owner_id" in data
        assert "status" in data
        assert "ready" in data
        assert "uptime_seconds" in data
        assert "memory_usage_bytes" in data
        assert "lock" in data

    @pytest.mark.unit
    def test_status_includes_graph_stats(self, test_app, mock_database_service):
        """Test /status includes graph statistics (flat fields)."""
        client = TestClient(test_app)
        response = client.get("/status")

        data = response.json()
        # Flat structure - node_count and edge_count at root level
        assert "node_count" in data
        assert "edge_count" in data
        assert "node_tables" in data
        assert "edge_tables" in data
        assert data["node_count"] == 150
        assert data["edge_count"] == 275

    @pytest.mark.unit
    def test_status_includes_lock_info(self, test_app):
        """Test /status includes lock information."""
        client = TestClient(test_app)
        response = client.get("/status")

        data = response.json()
        assert "lock" in data
        # Real LockService starts in unlocked state
        assert data["lock"]["locked"] is False

    @pytest.mark.unit
    def test_status_when_locked(self, test_app, lock_service):
        """Test /status shows lock details when instance is locked."""
        import asyncio

        # Actually acquire the lock using the real LockService
        asyncio.run(
            lock_service.acquire(
                user_id="user-1",
                user_name="testuser",
                algorithm_name="pagerank",
                algorithm_type="cypher",
            )
        )

        client = TestClient(test_app)
        response = client.get("/status")

        data = response.json()
        lock = data["lock"]
        assert lock["locked"] is True
        assert lock["holder_username"] == "testuser"
        assert lock["algorithm_name"] == "pagerank"
