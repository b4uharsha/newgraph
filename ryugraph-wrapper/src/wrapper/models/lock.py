"""Lock state model for algorithm execution locking.

Internal models for lock state management. API response models are
imported from graph-olap-schemas.
"""

from __future__ import annotations

from datetime import datetime

from graph_olap_schemas import LockInfo
from pydantic import BaseModel, ConfigDict, Field


class LockState(BaseModel):
    """Current lock state for the instance (internal model).

    Lock is implicit - acquired when algorithm starts, released when it completes.
    """

    model_config = ConfigDict(frozen=True)

    execution_id: str = Field(description="Unique execution identifier")
    holder_id: str = Field(description="User ID holding the lock")
    holder_username: str = Field(description="Username holding the lock")
    algorithm_name: str = Field(description="Name of the algorithm being executed")
    algorithm_type: str = Field(description="Type: 'native' or 'networkx'")
    acquired_at: datetime = Field(description="When the lock was acquired")

    def to_api_dict(self) -> dict[str, str | None]:
        """Convert to API response format.

        Returns:
            Dict with lock state for API response.
        """
        return {
            "execution_id": self.execution_id,
            "holder_id": self.holder_id,
            "holder_username": self.holder_username,
            "algorithm_name": self.algorithm_name,
            "algorithm_type": self.algorithm_type,
            "acquired_at": self.acquired_at.isoformat(),
        }


def lock_info_from_state(state: LockState | None) -> LockInfo:
    """Convert LockState to API LockInfo response model.

    Args:
        state: Current lock state or None if unlocked.

    Returns:
        LockInfo instance for API responses.
    """
    if state is None:
        return LockInfo(locked=False)
    return LockInfo(
        locked=True,
        execution_id=state.execution_id,
        holder_id=state.holder_id,
        holder_username=state.holder_username,
        algorithm_name=state.algorithm_name,
        algorithm_type=state.algorithm_type,
        acquired_at=state.acquired_at.isoformat(),
    )
