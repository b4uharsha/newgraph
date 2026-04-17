"""Tests for lock models."""

from datetime import UTC, datetime

from wrapper.models.lock import LockState, lock_info_from_state
from graph_olap_schemas import LockInfo


class TestLockState:
    """Tests for LockState model."""

    def test_lock_state_creation(self):
        """Test creating a LockState."""
        now = datetime.now(UTC)
        state = LockState(
            execution_id="exec-123",
            holder_id="user-456",
            holder_username="test-user",
            algorithm_name="pagerank",
            algorithm_type="networkx",
            acquired_at=now,
        )

        assert state.execution_id == "exec-123"
        assert state.holder_id == "user-456"
        assert state.holder_username == "test-user"
        assert state.algorithm_name == "pagerank"
        assert state.algorithm_type == "networkx"
        assert state.acquired_at == now

    def test_lock_state_to_api_dict(self):
        """Test LockState to_api_dict conversion."""
        now = datetime.now(UTC)
        state = LockState(
            execution_id="exec-123",
            holder_id="user-456",
            holder_username="test-user",
            algorithm_name="pagerank",
            algorithm_type="networkx",
            acquired_at=now,
        )

        result = state.to_api_dict()

        assert result["execution_id"] == "exec-123"
        assert result["holder_id"] == "user-456"
        assert result["holder_username"] == "test-user"
        assert result["algorithm_name"] == "pagerank"
        assert result["algorithm_type"] == "networkx"
        assert result["acquired_at"] == now.isoformat()


class TestLockInfo:
    """Tests for LockInfo model."""

    def test_lock_info_unlocked(self):
        """Test creating unlocked LockInfo."""
        info = LockInfo(locked=False)

        assert info.locked is False
        assert info.execution_id is None
        assert info.holder_id is None
        assert info.holder_username is None
        assert info.algorithm_name is None
        assert info.algorithm_type is None
        assert info.acquired_at is None

    def test_lock_info_locked(self):
        """Test creating locked LockInfo."""
        info = LockInfo(
            locked=True,
            execution_id="exec-123",
            holder_id="user-456",
            holder_username="test-user",
            algorithm_name="pagerank",
            algorithm_type="networkx",
            acquired_at="2024-01-01T00:00:00Z",
        )

        assert info.locked is True
        assert info.execution_id == "exec-123"
        assert info.holder_id == "user-456"
        assert info.holder_username == "test-user"
        assert info.algorithm_name == "pagerank"
        assert info.algorithm_type == "networkx"
        assert info.acquired_at == "2024-01-01T00:00:00Z"

    def test_lock_info_from_none_lock_state(self):
        """Test creating LockInfo from None (unlocked)."""
        info = lock_info_from_state(None)

        assert info.locked is False
        assert info.execution_id is None

    def test_lock_info_from_lock_state(self):
        """Test creating LockInfo from LockState."""
        now = datetime.now(UTC)
        state = LockState(
            execution_id="exec-789",
            holder_id="user-999",
            holder_username="other-user",
            algorithm_name="betweenness",
            algorithm_type="native",
            acquired_at=now,
        )

        info = lock_info_from_state(state)

        assert info.locked is True
        assert info.execution_id == "exec-789"
        assert info.holder_id == "user-999"
        assert info.holder_username == "other-user"
        assert info.algorithm_name == "betweenness"
        assert info.algorithm_type == "native"
        assert info.acquired_at == now.isoformat()
