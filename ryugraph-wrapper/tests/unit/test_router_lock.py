"""Tests for lock router endpoints."""

from unittest.mock import MagicMock

import pytest

from wrapper.models.lock import LockInfo
from wrapper.routers.lock import get_lock_status


class TestGetLockStatus:
    """Tests for /lock endpoint."""

    @pytest.mark.asyncio
    async def test_get_lock_status_unlocked(self):
        """Test getting lock status when unlocked."""
        mock_lock_service = MagicMock()
        mock_lock_info = LockInfo(locked=False)
        mock_lock_service.get_lock_info.return_value = mock_lock_info

        response = await get_lock_status(lock_service=mock_lock_service)

        assert response.lock.locked is False
        mock_lock_service.get_lock_info.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_lock_status_locked(self):
        """Test getting lock status when locked."""
        mock_lock_service = MagicMock()
        mock_lock_info = LockInfo(
            locked=True,
            execution_id="exec-123",
            holder_id="user-456",
            holder_username="test-user",
            algorithm_name="pagerank",
            algorithm_type="networkx",
            acquired_at="2024-01-01T00:00:00Z",
        )
        mock_lock_service.get_lock_info.return_value = mock_lock_info

        response = await get_lock_status(lock_service=mock_lock_service)

        assert response.lock.locked is True
        assert response.lock.execution_id == "exec-123"
        assert response.lock.holder_username == "test-user"
        assert response.lock.algorithm_name == "pagerank"
