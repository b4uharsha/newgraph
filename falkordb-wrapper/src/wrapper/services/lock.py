"""Lock service for algorithm execution concurrency control.

Implements implicit locking as defined in architectural.guardrails.md:
- Lock acquired automatically when algorithm starts
- Lock released automatically when algorithm completes (success or failure)
- No explicit lock/unlock API
- Atomic lock acquisition with mutex to prevent race conditions
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import structlog

from graph_olap_schemas import LockInfo
from wrapper.exceptions import ResourceLockedError
from wrapper.models.lock import LockState, lock_info_from_state

logger = structlog.get_logger(__name__)


class LockService:
    """Manages algorithm execution locking for an instance.

    Thread-safe lock management using asyncio.Lock for atomic operations.
    Lock state is held in memory (not persisted).
    """

    def __init__(self) -> None:
        """Initialize the lock service."""
        self._lock_state: LockState | None = None
        self._mutex = asyncio.Lock()
        logger.debug("LockService initialized")

    def get_status(self) -> LockState | None:
        """Get current lock state (non-blocking read).

        Returns:
            Current LockState or None if unlocked.
        """
        return self._lock_state

    def get_lock_info(self) -> LockInfo:
        """Get lock info for API responses.

        Returns:
            LockInfo instance representing current state.
        """
        return lock_info_from_state(self._lock_state)

    def is_locked(self) -> bool:
        """Check if the instance is currently locked.

        Returns:
            True if locked, False otherwise.
        """
        return self._lock_state is not None

    async def acquire(
        self,
        user_id: str,
        user_name: str,
        algorithm_name: str,
        algorithm_type: str = "cypher",
    ) -> tuple[bool, str, LockState | None]:
        """Attempt to acquire the lock atomically.

        Uses asyncio.Lock to ensure atomic check-and-set operation,
        preventing race conditions when concurrent requests arrive.

        Args:
            user_id: ID of user requesting the lock.
            user_name: Username requesting the lock.
            algorithm_name: Name of the algorithm to be executed.
            algorithm_type: Type of algorithm (default 'cypher' for FalkorDB).

        Returns:
            Tuple of (success, execution_id, existing_lock_state).
            - If success=True: execution_id contains new execution ID, existing=None
            - If success=False: execution_id is empty, existing contains current holder
        """
        async with self._mutex:
            if self._lock_state is not None:
                logger.info(
                    "Lock acquisition denied - already held",
                    holder_id=self._lock_state.holder_id,
                    holder_username=self._lock_state.holder_username,
                    algorithm=self._lock_state.algorithm_name,
                    requester_id=user_id,
                    requester_username=user_name,
                )
                return (False, "", self._lock_state)

            execution_id = str(uuid.uuid4())
            self._lock_state = LockState(
                execution_id=execution_id,
                holder_id=user_id,
                holder_username=user_name,
                algorithm_name=algorithm_name,
                algorithm_type=algorithm_type,
                acquired_at=datetime.now(UTC),
            )

            logger.info(
                "Lock acquired",
                execution_id=execution_id,
                holder_id=user_id,
                holder_username=user_name,
                algorithm=algorithm_name,
                algorithm_type=algorithm_type,
            )

            return (True, execution_id, None)

    async def acquire_or_raise(
        self,
        user_id: str,
        user_name: str,
        algorithm_name: str,
        algorithm_type: str = "cypher",
    ) -> str:
        """Acquire the lock or raise ResourceLockedError.

        Convenience method that raises an exception if lock cannot be acquired.

        Args:
            user_id: ID of user requesting the lock.
            user_name: Username requesting the lock.
            algorithm_name: Name of the algorithm to be executed.
            algorithm_type: Type of algorithm (default 'cypher' for FalkorDB).

        Returns:
            Execution ID if lock acquired successfully.

        Raises:
            ResourceLockedError: If lock is already held.
        """
        success, execution_id, existing = await self.acquire(
            user_id=user_id,
            user_name=user_name,
            algorithm_name=algorithm_name,
            algorithm_type=algorithm_type,
        )

        if not success and existing is not None:
            raise ResourceLockedError(
                holder_id=existing.holder_id,
                holder_username=existing.holder_username,
                algorithm_name=existing.algorithm_name,
                acquired_at=existing.acquired_at,
            )

        return execution_id

    async def release(self, execution_id: str) -> bool:
        """Release the lock for a specific execution.

        Only releases if the execution_id matches the current lock holder.
        This ensures that only the execution that acquired the lock can release it.

        Args:
            execution_id: Execution ID that acquired the lock.

        Returns:
            True if lock was released, False if execution_id doesn't match or no lock.
        """
        async with self._mutex:
            if self._lock_state is None:
                logger.warning(
                    "Attempted to release lock but no lock held",
                    execution_id=execution_id,
                )
                return False

            if self._lock_state.execution_id != execution_id:
                logger.warning(
                    "Attempted to release lock with wrong execution_id",
                    provided_execution_id=execution_id,
                    actual_execution_id=self._lock_state.execution_id,
                )
                return False

            released_state = self._lock_state
            self._lock_state = None

            logger.info(
                "Lock released",
                execution_id=execution_id,
                holder_id=released_state.holder_id,
                holder_username=released_state.holder_username,
                algorithm=released_state.algorithm_name,
                held_since=released_state.acquired_at.isoformat(),
            )

            return True

    async def force_release(self) -> LockState | None:
        """Force release the lock regardless of execution_id.

        Should only be used for cleanup during shutdown or error recovery.

        Returns:
            The released LockState, or None if no lock was held.
        """
        async with self._mutex:
            if self._lock_state is None:
                return None

            released_state = self._lock_state
            self._lock_state = None

            logger.warning(
                "Lock force-released",
                execution_id=released_state.execution_id,
                holder_id=released_state.holder_id,
                holder_username=released_state.holder_username,
                algorithm=released_state.algorithm_name,
            )

            return released_state
