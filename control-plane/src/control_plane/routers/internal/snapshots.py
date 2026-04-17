"""Internal API for snapshot status updates from export worker.

ADR-104/105: Internal API key verification removed. Internal endpoints
are protected by network policy (pod-to-pod only within the cluster).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.infrastructure.database import get_async_session
from control_plane.models import SnapshotStatus
from control_plane.models.requests import UpdateSnapshotStatusRequest
from control_plane.models.responses import DataResponse, SnapshotResponse
from control_plane.repositories.config import GlobalConfigRepository
from control_plane.repositories.export_jobs import ExportJobRepository
from control_plane.repositories.mappings import MappingRepository
from control_plane.repositories.snapshots import SnapshotRepository
from control_plane.services.snapshot_service import SnapshotService

router = APIRouter(prefix="/api/internal/snapshots", tags=["Internal - Snapshots"])


def get_snapshot_service(
    session: AsyncSession = Depends(get_async_session),
) -> SnapshotService:
    """Dependency to get snapshot service."""
    from control_plane.repositories.favorites import FavoritesRepository

    return SnapshotService(
        snapshot_repo=SnapshotRepository(session),
        mapping_repo=MappingRepository(session),
        export_job_repo=ExportJobRepository(session),
        config_repo=GlobalConfigRepository(session),
        favorites_repo=FavoritesRepository(session),
    )


SnapshotServiceDep = Annotated[SnapshotService, Depends(get_snapshot_service)]


def snapshot_to_response(snapshot) -> SnapshotResponse:
    """Convert domain Snapshot to response model."""
    return SnapshotResponse(
        id=snapshot.id,
        mapping_id=snapshot.mapping_id,
        mapping_version=snapshot.mapping_version,
        owner_username=snapshot.owner_username,
        name=snapshot.name,
        description=snapshot.description,
        gcs_path=snapshot.gcs_path,
        status=snapshot.status.value,
        size_bytes=snapshot.size_bytes,
        node_counts=snapshot.node_counts,
        edge_counts=snapshot.edge_counts,
        progress=snapshot.progress,
        error_message=snapshot.error_message,
        created_at=snapshot.created_at,
        updated_at=snapshot.updated_at,
        ttl=snapshot.ttl,
        inactivity_timeout=snapshot.inactivity_timeout,
        last_used_at=snapshot.last_used_at,
    )


@router.get(
    "/{snapshot_id}/status",
    response_model=DataResponse[dict],
)
async def get_snapshot_status(
    snapshot_id: int,
    service: SnapshotServiceDep,
) -> DataResponse[dict]:
    """Get snapshot status.

    Called by export worker to check cancellation status.

    Args:
        snapshot_id: Snapshot ID
        service: Snapshot service

    Returns:
        Snapshot status
    """
    snapshot = await service.get_snapshot(snapshot_id)
    return DataResponse(data={"status": snapshot.status.value})


@router.patch(
    "/{snapshot_id}/status",
    response_model=DataResponse[SnapshotResponse],
)
async def update_snapshot_status(
    snapshot_id: int,
    request: UpdateSnapshotStatusRequest,
    service: SnapshotServiceDep,
) -> DataResponse[SnapshotResponse]:
    """Update snapshot status from export worker.

    Called by export worker to report progress and completion.

    Args:
        snapshot_id: Snapshot ID
        request: Status update request
        service: Snapshot service

    Returns:
        Updated snapshot
    """
    snapshot = await service.update_status(
        snapshot_id=snapshot_id,
        status=SnapshotStatus(request.status),
        error_message=request.error_message,
        progress=request.progress,
        node_counts=request.node_counts,
        edge_counts=request.edge_counts,
        size_bytes=request.size_bytes,
    )
    return DataResponse(data=snapshot_to_response(snapshot))
