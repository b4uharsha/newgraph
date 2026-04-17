"""Tests for health router endpoints."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from wrapper.models.lock import LockInfo
from wrapper.routers.health import get_startup_time, get_status, health, ready, set_startup_time


class TestSetStartupTime:
    """Tests for set_startup_time() function."""

    def test_set_startup_time(self):
        """Test that set_startup_time sets the global startup time."""
        import wrapper.routers.health

        # Reset to None
        wrapper.routers.health._startup_time = None

        set_startup_time()

        assert wrapper.routers.health._startup_time is not None
        assert isinstance(wrapper.routers.health._startup_time, datetime)


class TestGetStartupTime:
    """Tests for get_startup_time() function."""

    def test_get_startup_time_when_set(self):
        """Test get_startup_time returns the set time."""
        import wrapper.routers.health

        now = datetime.now(UTC)
        wrapper.routers.health._startup_time = now

        result = get_startup_time()

        assert result == now

    def test_get_startup_time_when_not_set(self):
        """Test get_startup_time sets a default if not set."""
        import wrapper.routers.health

        wrapper.routers.health._startup_time = None

        result = get_startup_time()

        assert result is not None
        assert isinstance(result, datetime)


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    @pytest.mark.asyncio
    async def test_health_returns_healthy(self):
        """Test that health endpoint always returns healthy."""
        response = await health()

        assert response.status == "healthy"
        assert response.timestamp is not None


class TestReadyEndpoint:
    """Tests for /ready endpoint."""

    @pytest.mark.asyncio
    async def test_ready_when_service_ready(self):
        """Test ready endpoint returns healthy when service is ready."""
        mock_db = MagicMock()
        mock_db.is_ready = True

        response = await ready(db_service=mock_db)

        assert response.status == "healthy"
        assert response.timestamp is not None

    @pytest.mark.asyncio
    async def test_ready_when_service_not_ready(self):
        """Test ready endpoint raises 503 when service not ready."""
        mock_db = MagicMock()
        mock_db.is_ready = False

        with pytest.raises(HTTPException) as exc_info:
            await ready(db_service=mock_db)

        assert exc_info.value.status_code == 503
        assert "not ready" in exc_info.value.detail


class TestStatusEndpoint:
    """Tests for /status endpoint."""

    @pytest.mark.asyncio
    async def test_status_when_starting(self):
        """Test status endpoint when instance is starting."""
        mock_settings = MagicMock()
        mock_settings.wrapper.instance_id = "123"
        mock_settings.wrapper.snapshot_id = "456"
        mock_settings.wrapper.mapping_id = "789"
        mock_settings.wrapper.owner_id = "test-user"

        mock_db = MagicMock()
        mock_db.is_initialized = False
        mock_db.is_ready = False

        mock_lock = MagicMock()
        mock_lock_info = LockInfo(locked=False)
        mock_lock.get_lock_info.return_value = mock_lock_info

        with patch("wrapper.routers.health.psutil.Process") as mock_process:
            mock_memory = MagicMock()
            mock_memory.rss = 1024 * 1024 * 100  # 100 MB
            mock_process.return_value.memory_info.return_value = mock_memory

            response = await get_status(
                settings=mock_settings,
                db_service=mock_db,
                lock_service=mock_lock,
            )

        assert response.status == "starting"
        assert response.instance_id == "123"
        assert response.snapshot_id == "456"
        assert response.mapping_id == "789"
        assert response.owner_id == "test-user"
        assert response.ready is False
        assert response.memory_usage_bytes == 1024 * 1024 * 100

    @pytest.mark.asyncio
    async def test_status_when_loading(self):
        """Test status endpoint when instance is loading data."""
        mock_settings = MagicMock()
        mock_settings.wrapper.instance_id = "123"
        mock_settings.wrapper.snapshot_id = "456"
        mock_settings.wrapper.mapping_id = "789"
        mock_settings.wrapper.owner_id = "test-user"

        mock_db = MagicMock()
        mock_db.is_initialized = True
        mock_db.is_ready = False

        mock_lock = MagicMock()
        mock_lock_info = LockInfo(locked=False)
        mock_lock.get_lock_info.return_value = mock_lock_info

        with patch("wrapper.routers.health.psutil.Process") as mock_process:
            mock_memory = MagicMock()
            mock_memory.rss = 1024 * 1024 * 200
            mock_process.return_value.memory_info.return_value = mock_memory

            response = await get_status(
                settings=mock_settings,
                db_service=mock_db,
                lock_service=mock_lock,
            )

        assert response.status == "loading"
        assert response.ready is False

    @pytest.mark.asyncio
    async def test_status_when_running(self):
        """Test status endpoint when instance is running."""
        mock_settings = MagicMock()
        mock_settings.wrapper.instance_id = "123"
        mock_settings.wrapper.snapshot_id = "456"
        mock_settings.wrapper.mapping_id = "789"
        mock_settings.wrapper.owner_id = "test-user"

        mock_db = MagicMock()
        mock_db.is_initialized = True
        mock_db.is_ready = True
        mock_db.get_stats = AsyncMock(
            return_value={
                "node_count": 1000,
                "edge_count": 5000,
            }
        )
        mock_db.get_schema = AsyncMock(
            return_value={
                "node_tables": [{"label": "Person"}, {"label": "Company"}],
                "edge_tables": [{"type": "WORKS_AT"}],
            }
        )

        mock_lock = MagicMock()
        mock_lock_info = LockInfo(
            locked=True,
            execution_id="execution-123",
            holder_id="user-123",
            holder_username="test-user",
            algorithm_name="pagerank",
            algorithm_type="networkx",
        )
        mock_lock.get_lock_info.return_value = mock_lock_info

        with patch("wrapper.routers.health.psutil.Process") as mock_process:
            mock_memory = MagicMock()
            mock_memory.rss = 1024 * 1024 * 500
            mock_process.return_value.memory_info.return_value = mock_memory

            response = await get_status(
                settings=mock_settings,
                db_service=mock_db,
                lock_service=mock_lock,
            )

        assert response.status == "running"
        assert response.ready is True
        assert response.node_count == 1000
        assert response.edge_count == 5000
        assert response.node_tables == ["Person", "Company"]
        assert response.edge_tables == ["WORKS_AT"]
        assert response.lock is not None

    @pytest.mark.asyncio
    async def test_status_handles_stats_exception(self):
        """Test status endpoint handles stats errors gracefully."""
        mock_settings = MagicMock()
        mock_settings.wrapper.instance_id = "123"
        mock_settings.wrapper.snapshot_id = "456"
        mock_settings.wrapper.mapping_id = "789"
        mock_settings.wrapper.owner_id = "test-user"

        mock_db = MagicMock()
        mock_db.is_initialized = True
        mock_db.is_ready = True
        # Raise exception when getting stats
        mock_db.get_stats = AsyncMock(side_effect=Exception("Database error"))
        mock_db.get_schema = AsyncMock(
            return_value={"node_tables": [], "edge_tables": []}
        )

        mock_lock = MagicMock()
        mock_lock_info = LockInfo(locked=False)
        mock_lock.get_lock_info.return_value = mock_lock_info

        with patch("wrapper.routers.health.psutil.Process") as mock_process:
            mock_memory = MagicMock()
            mock_memory.rss = 1024 * 1024 * 100
            mock_process.return_value.memory_info.return_value = mock_memory

            response = await get_status(
                settings=mock_settings,
                db_service=mock_db,
                lock_service=mock_lock,
            )

        # Should still succeed but with null stats
        assert response.status == "running"
        assert response.node_count is None
        assert response.edge_count is None

    @pytest.mark.asyncio
    async def test_status_handles_schema_exception(self):
        """Test status endpoint handles schema errors gracefully."""
        mock_settings = MagicMock()
        mock_settings.wrapper.instance_id = "123"
        mock_settings.wrapper.snapshot_id = "456"
        mock_settings.wrapper.mapping_id = "789"
        mock_settings.wrapper.owner_id = "test-user"

        mock_db = MagicMock()
        mock_db.is_initialized = True
        mock_db.is_ready = True
        mock_db.get_stats = AsyncMock(return_value={"node_count": 100, "edge_count": 200})
        # Raise exception when getting schema
        mock_db.get_schema = AsyncMock(side_effect=Exception("Schema error"))

        mock_lock = MagicMock()
        mock_lock_info = LockInfo(locked=False)
        mock_lock.get_lock_info.return_value = mock_lock_info

        with patch("wrapper.routers.health.psutil.Process") as mock_process:
            mock_memory = MagicMock()
            mock_memory.rss = 1024 * 1024 * 100
            mock_process.return_value.memory_info.return_value = mock_memory

            response = await get_status(
                settings=mock_settings,
                db_service=mock_db,
                lock_service=mock_lock,
            )

        # Should still succeed but with empty table lists
        assert response.status == "running"
        assert response.node_tables == []
        assert response.edge_tables == []
