"""Lock status endpoint.

Provides /lock endpoint for checking the current lock state.
"""

from __future__ import annotations

from fastapi import APIRouter

from wrapper.dependencies import LockServiceDep
from wrapper.models.responses import LockStatusResponse

router = APIRouter(prefix="/lock", tags=["Lock"])


@router.get(
    "",
    response_model=LockStatusResponse,
    summary="Get lock status",
    description="Returns the current lock state of the instance.",
)
async def get_lock_status(
    lock_service: LockServiceDep,
) -> LockStatusResponse:
    """Get current lock status.

    Returns information about whether the instance is currently locked
    for algorithm execution, and if so, details about the lock holder.

    The instance uses implicit locking - locks are acquired automatically
    when an algorithm starts and released when it completes. There is no
    explicit lock/unlock API.
    """
    return LockStatusResponse(lock=lock_service.get_lock_info())
