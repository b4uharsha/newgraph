"""Unit tests for the LockService.

Tests cover:
- Initial state (unlocked)
- Lock acquisition and release
- Concurrent acquisition handling
- Force release functionality
- Error conditions
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from wrapper.exceptions import ResourceLockedError
from wrapper.models.lock import LockInfo, LockState
from wrapper.services.lock import LockService


class TestLockServiceInitialState:
    """Tests for LockService initial state."""

    def test_initial_state_unlocked(self):
        """Service starts in unlocked state."""
        service = LockService()
        assert service.is_locked() is False

    def test_initial_get_status_returns_none(self):
        """get_status returns None when unlocked."""
        service = LockService()
        assert service.get_status() is None

    def test_initial_get_lock_info_returns_unlocked(self):
        """get_lock_info returns LockInfo with locked=False when unlocked."""
        service = LockService()
        info = service.get_lock_info()
        assert isinstance(info, LockInfo)
        assert info.locked is False
        assert info.execution_id is None
        assert info.holder_id is None
        assert info.algorithm_name is None


class TestLockAcquisition:
    """Tests for lock acquisition."""

    @pytest.mark.asyncio
    async def test_acquire_success(self):
        """First acquire succeeds."""
        service = LockService()
        success, exec_id, existing = await service.acquire(
            user_id="user-001",
            user_name="testuser",
            algorithm_name="pagerank",
        )
        assert success is True
        assert exec_id != ""
        assert existing is None

    @pytest.mark.asyncio
    async def test_acquire_returns_execution_id(self):
        """Successful acquire returns a valid UUID execution_id."""
        service = LockService()
        success, exec_id, _ = await service.acquire(
            user_id="user-001",
            user_name="testuser",
            algorithm_name="pagerank",
        )
        assert success is True
        # UUID format check
        assert len(exec_id) == 36
        assert exec_id.count("-") == 4

    @pytest.mark.asyncio
    async def test_acquire_sets_lock_state(self):
        """Successful acquire sets the lock state correctly."""
        service = LockService()
        await service.acquire(
            user_id="user-001",
            user_name="testuser",
            algorithm_name="pagerank",
            algorithm_type="cypher",
        )

        assert service.is_locked() is True
        state = service.get_status()
        assert state is not None
        assert state.holder_id == "user-001"
        assert state.holder_username == "testuser"
        assert state.algorithm_name == "pagerank"
        assert state.algorithm_type == "cypher"
        assert isinstance(state.acquired_at, datetime)

    @pytest.mark.asyncio
    async def test_acquire_denied_when_locked(self):
        """Second acquire fails when already locked."""
        service = LockService()

        # First acquire succeeds
        success1, _, _ = await service.acquire(
            user_id="user-001",
            user_name="testuser",
            algorithm_name="pagerank",
        )
        assert success1 is True

        # Second acquire fails
        success2, exec_id, existing = await service.acquire(
            user_id="user-002",
            user_name="otheruser",
            algorithm_name="betweenness",
        )
        assert success2 is False
        assert exec_id == ""
        assert existing is not None

    @pytest.mark.asyncio
    async def test_acquire_returns_existing_lock_info(self):
        """Failed acquire returns existing lock holder info."""
        service = LockService()

        # First user acquires
        await service.acquire(
            user_id="user-001",
            user_name="testuser",
            algorithm_name="pagerank",
        )

        # Second user attempts acquire
        success, _, existing = await service.acquire(
            user_id="user-002",
            user_name="otheruser",
            algorithm_name="betweenness",
        )

        assert success is False
        assert existing is not None
        assert isinstance(existing, LockState)
        assert existing.holder_id == "user-001"
        assert existing.holder_username == "testuser"
        assert existing.algorithm_name == "pagerank"

    @pytest.mark.asyncio
    async def test_acquire_default_algorithm_type(self):
        """Acquire uses 'cypher' as default algorithm_type."""
        service = LockService()
        await service.acquire(
            user_id="user-001",
            user_name="testuser",
            algorithm_name="pagerank",
        )

        state = service.get_status()
        assert state is not None
        assert state.algorithm_type == "cypher"


class TestLockRelease:
    """Tests for lock release."""

    @pytest.mark.asyncio
    async def test_release_success(self):
        """Correct execution_id releases the lock."""
        service = LockService()

        success, exec_id, _ = await service.acquire(
            user_id="user-001",
            user_name="testuser",
            algorithm_name="pagerank",
        )
        assert success is True

        released = await service.release(exec_id)
        assert released is True
        assert service.is_locked() is False

    @pytest.mark.asyncio
    async def test_release_wrong_execution_id_fails(self):
        """Wrong execution_id does not release the lock."""
        service = LockService()

        await service.acquire(
            user_id="user-001",
            user_name="testuser",
            algorithm_name="pagerank",
        )

        released = await service.release("wrong-execution-id")
        assert released is False
        assert service.is_locked() is True

    @pytest.mark.asyncio
    async def test_release_when_not_locked_fails(self):
        """Release fails when no lock is held."""
        service = LockService()

        released = await service.release("any-execution-id")
        assert released is False


class TestForceRelease:
    """Tests for force release functionality."""

    @pytest.mark.asyncio
    async def test_force_release_success(self):
        """Force release releases the lock regardless of execution_id."""
        service = LockService()

        await service.acquire(
            user_id="user-001",
            user_name="testuser",
            algorithm_name="pagerank",
        )
        assert service.is_locked() is True

        released_state = await service.force_release()
        assert released_state is not None
        assert released_state.holder_id == "user-001"
        assert service.is_locked() is False

    @pytest.mark.asyncio
    async def test_force_release_when_not_locked(self):
        """Force release returns None when no lock is held."""
        service = LockService()

        released_state = await service.force_release()
        assert released_state is None


class TestGetLockInfo:
    """Tests for get_lock_info method."""

    def test_get_lock_info_when_unlocked(self):
        """get_lock_info returns LockInfo with locked=False when unlocked."""
        service = LockService()

        info = service.get_lock_info()
        assert info.locked is False
        assert info.execution_id is None
        assert info.holder_id is None
        assert info.holder_username is None
        assert info.algorithm_name is None
        assert info.algorithm_type is None
        assert info.acquired_at is None

    @pytest.mark.asyncio
    async def test_get_lock_info_when_locked(self):
        """get_lock_info returns full info when locked."""
        service = LockService()

        success, exec_id, _ = await service.acquire(
            user_id="user-001",
            user_name="testuser",
            algorithm_name="pagerank",
            algorithm_type="cypher",
        )
        assert success is True

        info = service.get_lock_info()
        assert info.locked is True
        assert info.execution_id == exec_id
        assert info.holder_id == "user-001"
        assert info.holder_username == "testuser"
        assert info.algorithm_name == "pagerank"
        assert info.algorithm_type == "cypher"
        assert info.acquired_at is not None


class TestAcquireOrRaise:
    """Tests for acquire_or_raise method."""

    @pytest.mark.asyncio
    async def test_acquire_or_raise_success(self):
        """acquire_or_raise returns execution_id when successful."""
        service = LockService()

        exec_id = await service.acquire_or_raise(
            user_id="user-001",
            user_name="testuser",
            algorithm_name="pagerank",
        )

        assert exec_id != ""
        assert len(exec_id) == 36

    @pytest.mark.asyncio
    async def test_acquire_or_raise_raises_when_locked(self):
        """acquire_or_raise raises ResourceLockedError when locked."""
        service = LockService()

        # First acquire
        await service.acquire(
            user_id="user-001",
            user_name="testuser",
            algorithm_name="pagerank",
        )

        # Second acquire_or_raise should raise
        with pytest.raises(ResourceLockedError) as exc_info:
            await service.acquire_or_raise(
                user_id="user-002",
                user_name="otheruser",
                algorithm_name="betweenness",
            )

        error = exc_info.value
        assert "user-001" in str(error.details)
        assert "testuser" in str(error.details) or "testuser" in str(error)
        assert "pagerank" in str(error.details) or "pagerank" in str(error)


class TestConcurrency:
    """Tests for concurrent lock access."""

    @pytest.mark.asyncio
    async def test_concurrent_acquire_only_one_succeeds(self):
        """Only one of many concurrent acquires succeeds."""
        service = LockService()

        async def try_acquire(user_num: int) -> tuple[bool, str]:
            success, exec_id, _ = await service.acquire(
                user_id=f"user-{user_num:03d}",
                user_name=f"user{user_num}",
                algorithm_name="pagerank",
            )
            return success, exec_id

        # Launch 10 concurrent acquire attempts
        results = await asyncio.gather(
            *[try_acquire(i) for i in range(10)]
        )

        # Exactly one should succeed
        successes = [r for r in results if r[0] is True]
        failures = [r for r in results if r[0] is False]

        assert len(successes) == 1
        assert len(failures) == 9

        # The lock should be held
        assert service.is_locked() is True

    @pytest.mark.asyncio
    async def test_acquire_release_cycle(self):
        """Lock can be reacquired after release."""
        service = LockService()

        # First acquire
        success1, exec_id1, _ = await service.acquire(
            user_id="user-001",
            user_name="testuser",
            algorithm_name="pagerank",
        )
        assert success1 is True

        # Release
        await service.release(exec_id1)
        assert service.is_locked() is False

        # Second acquire by different user
        success2, exec_id2, _ = await service.acquire(
            user_id="user-002",
            user_name="otheruser",
            algorithm_name="betweenness",
        )
        assert success2 is True
        assert exec_id2 != exec_id1

        state = service.get_status()
        assert state is not None
        assert state.holder_id == "user-002"
