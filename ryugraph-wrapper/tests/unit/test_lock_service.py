"""Unit tests for the LockService."""

from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

from wrapper.exceptions import ResourceLockedError
from wrapper.models.lock import LockState
from wrapper.services.lock import LockService


class TestLockService:
    """Tests for LockService."""

    @pytest.fixture
    def lock_service(self) -> LockService:
        """Create a fresh LockService for each test."""
        return LockService()

    # =========================================================================
    # Basic Lock Operations
    # =========================================================================

    @pytest.mark.unit
    async def test_initial_state_is_unlocked(self, lock_service: LockService) -> None:
        """Lock service starts in unlocked state."""
        assert lock_service.is_locked() is False
        assert lock_service.get_status() is None

    @pytest.mark.unit
    async def test_acquire_lock_success(self, lock_service: LockService) -> None:
        """Successfully acquire lock when unlocked."""
        success, execution_id, existing = await lock_service.acquire(
            user_id="user-1",
            user_name="alice",
            algorithm_name="pagerank",
            algorithm_type="networkx",
        )

        assert success is True
        assert execution_id != ""
        assert existing is None
        assert lock_service.is_locked() is True

    @pytest.mark.unit
    async def test_acquire_lock_sets_correct_state(self, lock_service: LockService) -> None:
        """Lock state contains correct information after acquisition."""
        await lock_service.acquire(
            user_id="user-1",
            user_name="alice",
            algorithm_name="pagerank",
            algorithm_type="networkx",
        )

        state = lock_service.get_status()
        assert state is not None
        assert state.holder_id == "user-1"
        assert state.holder_username == "alice"
        assert state.algorithm_name == "pagerank"
        assert state.algorithm_type == "networkx"
        assert isinstance(state.acquired_at, datetime)

    @pytest.mark.unit
    async def test_acquire_lock_denied_when_held(self, lock_service: LockService) -> None:
        """Cannot acquire lock when already held by another user."""
        # First acquisition
        await lock_service.acquire(
            user_id="user-1",
            user_name="alice",
            algorithm_name="pagerank",
            algorithm_type="networkx",
        )

        # Second attempt should fail
        success, execution_id, existing = await lock_service.acquire(
            user_id="user-2",
            user_name="bob",
            algorithm_name="betweenness",
            algorithm_type="networkx",
        )

        assert success is False
        assert execution_id == ""
        assert existing is not None
        assert existing.holder_id == "user-1"
        assert existing.holder_username == "alice"

    @pytest.mark.unit
    async def test_acquire_or_raise_success(self, lock_service: LockService) -> None:
        """acquire_or_raise returns execution_id on success."""
        execution_id = await lock_service.acquire_or_raise(
            user_id="user-1",
            user_name="alice",
            algorithm_name="pagerank",
            algorithm_type="networkx",
        )

        assert execution_id != ""
        assert lock_service.is_locked() is True

    @pytest.mark.unit
    async def test_acquire_or_raise_raises_when_locked(self, lock_service: LockService) -> None:
        """acquire_or_raise raises ResourceLockedError when lock is held."""
        await lock_service.acquire(
            user_id="user-1",
            user_name="alice",
            algorithm_name="pagerank",
            algorithm_type="networkx",
        )

        with pytest.raises(ResourceLockedError) as exc_info:
            await lock_service.acquire_or_raise(
                user_id="user-2",
                user_name="bob",
                algorithm_name="betweenness",
                algorithm_type="networkx",
            )

        assert exc_info.value.error_code == "RESOURCE_LOCKED"
        assert "alice" in exc_info.value.message
        assert "pagerank" in exc_info.value.message

    # =========================================================================
    # Lock Release Operations
    # =========================================================================

    @pytest.mark.unit
    async def test_release_lock_success(self, lock_service: LockService) -> None:
        """Successfully release lock with correct execution_id."""
        _, execution_id, _ = await lock_service.acquire(
            user_id="user-1",
            user_name="alice",
            algorithm_name="pagerank",
            algorithm_type="networkx",
        )

        released = await lock_service.release(execution_id)

        assert released is True
        assert lock_service.is_locked() is False
        assert lock_service.get_status() is None

    @pytest.mark.unit
    async def test_release_wrong_execution_id_fails(self, lock_service: LockService) -> None:
        """Cannot release lock with wrong execution_id."""
        await lock_service.acquire(
            user_id="user-1",
            user_name="alice",
            algorithm_name="pagerank",
            algorithm_type="networkx",
        )

        released = await lock_service.release("wrong-execution-id")

        assert released is False
        assert lock_service.is_locked() is True  # Still locked

    @pytest.mark.unit
    async def test_release_when_unlocked_returns_false(self, lock_service: LockService) -> None:
        """Releasing when already unlocked returns False."""
        released = await lock_service.release("any-execution-id")

        assert released is False

    @pytest.mark.unit
    async def test_force_release_clears_lock(self, lock_service: LockService) -> None:
        """Force release clears the lock regardless of execution_id."""
        await lock_service.acquire(
            user_id="user-1",
            user_name="alice",
            algorithm_name="pagerank",
            algorithm_type="networkx",
        )

        released_state = await lock_service.force_release()

        assert released_state is not None
        assert released_state.holder_id == "user-1"
        assert lock_service.is_locked() is False

    @pytest.mark.unit
    async def test_force_release_when_unlocked_returns_none(
        self, lock_service: LockService
    ) -> None:
        """Force release when unlocked returns None."""
        released_state = await lock_service.force_release()

        assert released_state is None

    # =========================================================================
    # Lock Info API
    # =========================================================================

    @pytest.mark.unit
    async def test_get_lock_info_unlocked(self, lock_service: LockService) -> None:
        """get_lock_info returns unlocked state correctly."""
        info = lock_service.get_lock_info()

        assert info.locked is False
        assert info.holder_id is None
        assert info.algorithm_name is None

    @pytest.mark.unit
    async def test_get_lock_info_locked(self, lock_service: LockService) -> None:
        """get_lock_info returns locked state correctly."""
        await lock_service.acquire(
            user_id="user-1",
            user_name="alice",
            algorithm_name="pagerank",
            algorithm_type="networkx",
        )

        info = lock_service.get_lock_info()

        assert info.locked is True
        assert info.holder_id == "user-1"
        assert info.holder_username == "alice"
        assert info.algorithm_name == "pagerank"
        assert info.algorithm_type == "networkx"
        assert info.acquired_at is not None

    # =========================================================================
    # Concurrency Tests
    # =========================================================================

    @pytest.mark.unit
    async def test_concurrent_acquire_only_one_succeeds(self, lock_service: LockService) -> None:
        """When multiple users try to acquire simultaneously, only one succeeds."""
        results: list[tuple[bool, str, LockState | None]] = []

        async def try_acquire(user_id: str, user_name: str) -> None:
            result = await lock_service.acquire(
                user_id=user_id,
                user_name=user_name,
                algorithm_name="pagerank",
                algorithm_type="networkx",
            )
            results.append(result)

        # Start 10 concurrent acquisition attempts
        tasks = [try_acquire(f"user-{i}", f"user{i}") for i in range(10)]
        await asyncio.gather(*tasks)

        # Exactly one should succeed
        successes = [r for r in results if r[0] is True]
        failures = [r for r in results if r[0] is False]

        assert len(successes) == 1
        assert len(failures) == 9

        # All failures should reference the successful holder
        success_exec_id = successes[0][1]
        current_state = lock_service.get_status()
        assert current_state is not None
        assert current_state.execution_id == success_exec_id

    @pytest.mark.unit
    async def test_acquire_release_cycle(self, lock_service: LockService) -> None:
        """Lock can be acquired after previous holder releases."""
        # First user acquires and releases
        _, exec_id_1, _ = await lock_service.acquire(
            user_id="user-1",
            user_name="alice",
            algorithm_name="pagerank",
            algorithm_type="networkx",
        )
        await lock_service.release(exec_id_1)

        # Second user can now acquire
        success, exec_id_2, _ = await lock_service.acquire(
            user_id="user-2",
            user_name="bob",
            algorithm_name="betweenness",
            algorithm_type="networkx",
        )

        assert success is True
        assert exec_id_2 != exec_id_1
        state = lock_service.get_status()
        assert state is not None
        assert state.holder_id == "user-2"
