# =============================================================================
# SNAPSHOT FUNCTIONALITY DISABLED
# This file has been commented out as part of removing explicit snapshot APIs.
# Snapshots are now created implicitly when instances are created from mappings.
# =============================================================================

# """Snapshots API router."""
#
# from typing import Annotated, Any
#
# from fastapi import APIRouter, Depends, Query, Request, status
# from sqlalchemy.ext.asyncio import AsyncSession
#
# from control_plane.infrastructure.database import get_async_session
# from control_plane.middleware.identity import CurrentUser
# from control_plane.models import SnapshotStatus
# from control_plane.models.requests import (
#     CreateSnapshotRequest,
#     UpdateLifecycleRequest,
#     UpdateSnapshotRequest,
# )
# from control_plane.models.responses import (
#     DataResponse,
#     LifecycleResponse,
#     PaginatedResponse,
#     PaginationMeta,
#     SnapshotResponse,
# )
# from control_plane.repositories.config import GlobalConfigRepository
# from control_plane.repositories.export_jobs import ExportJobRepository
# from control_plane.repositories.favorites import FavoritesRepository
# from control_plane.repositories.mappings import MappingRepository
# from control_plane.repositories.snapshots import SnapshotRepository
# from control_plane.services.snapshot_service import SnapshotService
#
# router = APIRouter(prefix="/api/snapshots", tags=["Snapshots"])
#
#
# def get_snapshot_service(
#     request: Request,
#     session: AsyncSession = Depends(get_async_session),
# ) -> SnapshotService:
#     """Dependency to get snapshot service."""
#     settings = request.app.state.settings
#     gcs_bucket = settings.gcs_bucket if settings.gcs_bucket else None
#     return SnapshotService(
#         snapshot_repo=SnapshotRepository(session),
#         mapping_repo=MappingRepository(session),
#         export_job_repo=ExportJobRepository(session),
#         config_repo=GlobalConfigRepository(session),
#         favorites_repo=FavoritesRepository(session),
#         gcs_bucket=gcs_bucket,
#         starburst_catalog=settings.starburst_catalog,
#     )
#
#
# SnapshotServiceDep = Annotated[SnapshotService, Depends(get_snapshot_service)]
#
#
# def snapshot_to_response(snapshot) -> SnapshotResponse:
#     """Convert domain Snapshot to response model."""
#     return SnapshotResponse(
#         id=snapshot.id,
#         mapping_id=snapshot.mapping_id,
#         mapping_version=snapshot.mapping_version,
#         owner_username=snapshot.owner_username,
#         name=snapshot.name,
#         description=snapshot.description,
#         gcs_path=snapshot.gcs_path,
#         status=snapshot.status.value,
#         size_bytes=snapshot.size_bytes,
#         node_counts=snapshot.node_counts,
#         edge_counts=snapshot.edge_counts,
#         progress=snapshot.progress,
#         error_message=snapshot.error_message,
#         created_at=snapshot.created_at,
#         updated_at=snapshot.updated_at,
#         ttl=snapshot.ttl,
#         inactivity_timeout=snapshot.inactivity_timeout,
#         last_used_at=snapshot.last_used_at,
#     )
#
#
# @router.get("", response_model=PaginatedResponse[SnapshotResponse])
# async def list_snapshots(
#     user: CurrentUser,
#     service: SnapshotServiceDep,
#     owner: str | None = None,
#     mapping_id: int | None = None,
#     status_filter: SnapshotStatus | None = Query(None, alias="status"),
#     search: str | None = None,
#     sort_by: str = "created_at",
#     sort_order: str = "desc",
#     offset: int = Query(default=0, ge=0),
#     limit: int = Query(default=50, ge=1, le=100),
# ) -> PaginatedResponse[SnapshotResponse]:
#     """List snapshots with optional filters.
#
#     Args:
#         user: Current authenticated user
#         service: Snapshot service
#         owner: Filter by owner username
#         mapping_id: Filter by mapping ID
#         status_filter: Filter by status
#         search: Search in name/description
#         sort_by: Field to sort by
#         sort_order: Sort order (asc/desc)
#         offset: Pagination offset
#         limit: Pagination limit
#
#     Returns:
#         Paginated list of snapshots
#     """
#     snapshots, total = await service.list_snapshots(
#         user=user,
#         owner=owner,
#         mapping_id=mapping_id,
#         status=status_filter,
#         search=search,
#         limit=limit,
#         offset=offset,
#         sort_field=sort_by,
#         sort_order=sort_order,
#     )
#
#     return PaginatedResponse(
#         data=[snapshot_to_response(s) for s in snapshots],
#         meta=PaginationMeta(
#             total=total,
#             limit=limit,
#             offset=offset,
#         ),
#     )
#
#
# @router.post(
#     "",
#     response_model=DataResponse[SnapshotResponse],
#     status_code=status.HTTP_201_CREATED,
# )
# async def create_snapshot(
#     user: CurrentUser,
#     service: SnapshotServiceDep,
#     request: CreateSnapshotRequest,
# ) -> DataResponse[SnapshotResponse]:
#     """Create a new snapshot from a mapping.
#
#     The current user becomes the owner.
#
#     Args:
#         user: Current authenticated user
#         service: Snapshot service
#         request: Snapshot creation request
#
#     Returns:
#         Created snapshot with status='pending'
#     """
#     snapshot = await service.create_snapshot(user, request)
#     return DataResponse(data=snapshot_to_response(snapshot))
#
#
# @router.get("/{snapshot_id}", response_model=DataResponse[SnapshotResponse])
# async def get_snapshot(
#     snapshot_id: int,
#     user: CurrentUser,
#     service: SnapshotServiceDep,
# ) -> DataResponse[SnapshotResponse]:
#     """Get a snapshot by ID.
#
#     Args:
#         snapshot_id: Snapshot ID
#         user: Current authenticated user
#         service: Snapshot service
#
#     Returns:
#         Snapshot details
#     """
#     snapshot = await service.get_snapshot(snapshot_id)
#     return DataResponse(data=snapshot_to_response(snapshot))
#
#
# @router.delete("/{snapshot_id}", status_code=status.HTTP_204_NO_CONTENT)
# async def delete_snapshot(
#     snapshot_id: int,
#     user: CurrentUser,
#     service: SnapshotServiceDep,
# ) -> None:
#     """Delete a snapshot.
#
#     Cannot delete if active instances exist.
#
#     Args:
#         snapshot_id: Snapshot ID
#         user: Current authenticated user
#         service: Snapshot service
#     """
#     await service.delete_snapshot(user, snapshot_id)
#
#
# @router.post("/{snapshot_id}/retry", response_model=DataResponse[SnapshotResponse])
# async def retry_snapshot(
#     snapshot_id: int,
#     user: CurrentUser,
#     service: SnapshotServiceDep,
# ) -> DataResponse[SnapshotResponse]:
#     """Retry a failed snapshot export.
#
#     Args:
#         snapshot_id: Snapshot ID
#         user: Current authenticated user
#         service: Snapshot service
#
#     Returns:
#         Updated snapshot with status='pending'
#     """
#     snapshot = await service.retry_failed(user, snapshot_id)
#     return DataResponse(data=snapshot_to_response(snapshot))
#
#
# @router.get("/{snapshot_id}/progress", response_model=DataResponse[dict[str, Any]])
# async def get_snapshot_progress(
#     snapshot_id: int,
#     user: CurrentUser,
#     service: SnapshotServiceDep,
# ) -> DataResponse[dict[str, Any]]:
#     """Get detailed export progress for a snapshot.
#
#     Args:
#         snapshot_id: Snapshot ID
#         user: Current authenticated user
#         service: Snapshot service
#
#     Returns:
#         Progress details with individual job status
#     """
#     progress = await service.get_progress(snapshot_id)
#     return DataResponse(data=progress)
#
#
# @router.put("/{snapshot_id}", response_model=DataResponse[SnapshotResponse])
# async def update_snapshot(
#     snapshot_id: int,
#     user: CurrentUser,
#     service: SnapshotServiceDep,
#     request: UpdateSnapshotRequest,
# ) -> DataResponse[SnapshotResponse]:
#     """Update snapshot metadata (name, description).
#
#     Args:
#         snapshot_id: Snapshot ID
#         user: Current authenticated user
#         service: Snapshot service
#         request: Update request with new values
#
#     Returns:
#         Updated snapshot
#     """
#     snapshot = await service.update_snapshot(user, snapshot_id, request)
#     return DataResponse(data=snapshot_to_response(snapshot))
#
#
# @router.put("/{snapshot_id}/lifecycle", response_model=DataResponse[LifecycleResponse])
# async def update_snapshot_lifecycle(
#     snapshot_id: int,
#     user: CurrentUser,
#     service: SnapshotServiceDep,
#     request: UpdateLifecycleRequest,
# ) -> DataResponse[LifecycleResponse]:
#     """Update snapshot lifecycle settings (TTL, inactivity timeout).
#
#     Args:
#         snapshot_id: Snapshot ID
#         user: Current authenticated user
#         service: Snapshot service
#         request: Lifecycle update request
#
#     Returns:
#         Updated lifecycle settings
#     """
#     snapshot = await service.update_lifecycle(user, snapshot_id, request)
#     return DataResponse(
#         data=LifecycleResponse(
#             id=snapshot.id,
#             ttl=snapshot.ttl,
#             inactivity_timeout=snapshot.inactivity_timeout,
#             updated_at=snapshot.updated_at,
#         )
#     )
