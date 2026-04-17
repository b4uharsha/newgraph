"""Instances API router.

Provides REST endpoints for instance lifecycle management:
- List, create, get, update, and delete instances
- Terminate running instances
- Update lifecycle settings (TTL, inactivity timeout)
- Get instance progress during startup
"""

from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.config import get_settings
from control_plane.infrastructure.database import get_async_session
from control_plane.middleware.identity import CurrentUser
from control_plane.models import InstanceStatus
from control_plane.models.requests import (
    CreateInstanceFromMappingRequest,
    CreateInstanceRequest,
    UpdateCpuRequest,
    UpdateInstanceRequest,
    UpdateLifecycleRequest,
    UpdateMemoryRequest,
)
from control_plane.models.responses import (
    DataResponse,
    InstanceResponse,
    PaginatedResponse,
    PaginationMeta,
)
from control_plane.clients.gcs import build_gcs_client_from_settings
from control_plane.repositories.config import GlobalConfigRepository
from control_plane.repositories.export_jobs import ExportJobRepository
from control_plane.repositories.favorites import FavoritesRepository
from control_plane.repositories.instances import InstanceRepository
from control_plane.repositories.mappings import MappingRepository
from control_plane.repositories.snapshots import SnapshotRepository
from control_plane.services.instance_service import InstanceService
from control_plane.services.k8s_service import get_k8s_service
from control_plane.services.snapshot_service import SnapshotService

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/instances", tags=["Instances"])


def get_instance_service(
    session: AsyncSession = Depends(get_async_session),
) -> InstanceService:
    """Dependency to get instance service."""
    # Get K8s service (will be None if K8s not available)
    settings = get_settings()
    k8s_service = None
    logger.debug("k8s_settings", namespace=settings.k8s_namespace, in_cluster=settings.k8s_in_cluster)
    if settings.k8s_in_cluster or settings.k8s_namespace:
        try:
            k8s_service = get_k8s_service(settings)
            logger.debug("k8s_service_initialized")
        except Exception as e:
            logger.warning("k8s_service_unavailable", error=str(e))

    # Create repositories
    snapshot_repo = SnapshotRepository(session)
    mapping_repo = MappingRepository(session)
    config_repo = GlobalConfigRepository(session)
    favorites_repo = FavoritesRepository(session)
    export_job_repo = ExportJobRepository(session)

    # Construct GCS client from settings. Raises if GCS is configured but the
    # client cannot be built — see build_gcs_client_from_settings for rationale.
    gcs_client = build_gcs_client_from_settings(settings)

    # Create snapshot service for create_from_mapping
    gcs_bucket = settings.gcs_bucket if settings.gcs_bucket else None
    snapshot_service = SnapshotService(
        snapshot_repo=snapshot_repo,
        mapping_repo=mapping_repo,
        export_job_repo=export_job_repo,
        config_repo=config_repo,
        favorites_repo=favorites_repo,
        gcs_client=gcs_client,
        gcs_bucket=gcs_bucket,
    )

    return InstanceService(
        instance_repo=InstanceRepository(session),
        snapshot_repo=snapshot_repo,
        config_repo=config_repo,
        favorites_repo=favorites_repo,
        k8s_service=k8s_service,
        mapping_repo=mapping_repo,
        snapshot_service=snapshot_service,
        gcs_client=gcs_client,
    )


InstanceServiceDep = Annotated[InstanceService, Depends(get_instance_service)]


def instance_to_response(instance) -> InstanceResponse:
    """Convert domain Instance to response model."""
    return InstanceResponse(
        id=instance.id,
        snapshot_id=instance.snapshot_id,
        owner_username=instance.owner_username,
        wrapper_type=instance.wrapper_type,
        name=instance.name,
        description=instance.description,
        status=instance.status.value,
        instance_url=instance.instance_url,
        pod_name=instance.pod_name,
        progress=instance.progress,
        error_code=instance.error_code.value if instance.error_code else None,
        error_message=instance.error_message,
        stack_trace=instance.stack_trace,
        created_at=instance.created_at,
        updated_at=instance.updated_at,
        started_at=instance.started_at,
        last_activity_at=instance.last_activity_at,
        expires_at=instance.expires_at,
        ttl=instance.ttl,
        inactivity_timeout=instance.inactivity_timeout,
        memory_usage_bytes=instance.memory_usage_bytes,
        disk_usage_bytes=instance.disk_usage_bytes,
        cpu_cores=instance.cpu_cores,
    )


@router.get("", response_model=PaginatedResponse[InstanceResponse])
async def list_instances(
    user: CurrentUser,
    service: InstanceServiceDep,
    owner: str | None = None,
    snapshot_id: int | None = None,
    status_filter: InstanceStatus | None = Query(None, alias="status"),
    search: str | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> PaginatedResponse[InstanceResponse]:
    """List instances with optional filters.

    Args:
        user: Current authenticated user
        service: Instance service
        owner: Filter by owner username
        snapshot_id: Filter by snapshot ID
        status_filter: Filter by status
        search: Search in name/description
        sort_by: Field to sort by
        sort_order: Sort order (asc/desc)
        offset: Pagination offset
        limit: Pagination limit

    Returns:
        Paginated list of instances
    """
    instances, total = await service.list_instances(
        user=user,
        owner=owner,
        snapshot_id=snapshot_id,
        status=status_filter,
        search=search,
        limit=limit,
        offset=offset,
        sort_field=sort_by,
        sort_order=sort_order,
    )

    return PaginatedResponse(
        data=[instance_to_response(i) for i in instances],
        meta=PaginationMeta(
            total=total,
            limit=limit,
            offset=offset,
        ),
    )


# =========================================================================
# DEPRECATED: Use POST /api/instances/from-mapping instead
# Commented out as part of API simplification - 2025-01
# =========================================================================
# @router.post(
#     "",
#     response_model=DataResponse[InstanceResponse],
#     status_code=status.HTTP_201_CREATED,
# )
# async def create_instance(
#     user: CurrentUser,
#     service: InstanceServiceDep,
#     request: CreateInstanceRequest,
# ) -> DataResponse[InstanceResponse]:
#     """Create a new instance from a snapshot.
#
#     The current user becomes the owner.
#
#     Args:
#         user: Current authenticated user
#         service: Instance service
#         request: Instance creation request
#
#     Returns:
#         Created instance with status='starting'
#     """
#     instance = await service.create_instance(user, request)
#     return DataResponse(data=instance_to_response(instance))


@router.post(
    "",
    response_model=DataResponse[InstanceResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_instance(
    user: CurrentUser,
    service: InstanceServiceDep,
    request: CreateInstanceFromMappingRequest,
) -> DataResponse[InstanceResponse]:
    """Create a new instance from a mapping.

    Creates a snapshot automatically and queues instance creation.
    The instance will have status='waiting_for_snapshot' until the
    snapshot export completes.

    Args:
        user: Current authenticated user
        service: Instance service
        request: Instance creation request with mapping_id

    Returns:
        Created instance with status='waiting_for_snapshot'

    Raises:
        404: If the mapping is not found
        409: If concurrency limits are exceeded
    """
    instance = await service.create_from_mapping(user, request)
    return DataResponse(data=instance_to_response(instance))


@router.get("/{instance_id}", response_model=DataResponse[InstanceResponse])
async def get_instance(
    instance_id: int,
    user: CurrentUser,
    service: InstanceServiceDep,
) -> DataResponse[InstanceResponse]:
    """Get an instance by ID.

    Args:
        instance_id: Instance ID
        user: Current authenticated user
        service: Instance service

    Returns:
        Instance details
    """
    instance = await service.get_instance(instance_id)
    return DataResponse(data=instance_to_response(instance))


@router.delete("/{instance_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_instance(
    instance_id: int,
    user: CurrentUser,
    service: InstanceServiceDep,
) -> None:
    """Delete an instance.

    Immediately deletes K8s resources and removes instance from database.

    Args:
        instance_id: Instance ID
        user: Current authenticated user
        service: Instance service
    """
    await service.delete_instance(instance_id, user)


@router.get("/user/status", response_model=DataResponse[dict[str, Any]])
async def get_user_status(
    user: CurrentUser,
    service: InstanceServiceDep,
) -> DataResponse[dict[str, Any]]:
    """Get instance status for the current user.

    Args:
        user: Current authenticated user
        service: Instance service

    Returns:
        User status with active instances and limits
    """
    status_info = await service.get_user_status(user.username)
    return DataResponse(data=status_info)


@router.put("/{instance_id}", response_model=DataResponse[InstanceResponse])
async def update_instance(
    instance_id: int,
    user: CurrentUser,
    service: InstanceServiceDep,
    request: UpdateInstanceRequest,
) -> DataResponse[InstanceResponse]:
    """Update instance metadata (name, description).

    Args:
        instance_id: Instance ID
        user: Current authenticated user
        service: Instance service
        request: Update request with new values

    Returns:
        Updated instance
    """
    instance = await service.update_instance(user, instance_id, request)
    return DataResponse(data=instance_to_response(instance))


@router.put("/{instance_id}/lifecycle", response_model=DataResponse[InstanceResponse])
async def update_instance_lifecycle(
    instance_id: int,
    user: CurrentUser,
    service: InstanceServiceDep,
    request: UpdateLifecycleRequest,
) -> DataResponse[InstanceResponse]:
    """Update instance lifecycle settings (TTL, inactivity timeout).

    Use this endpoint to extend the TTL or modify the inactivity timeout
    of a running instance after creation.

    Args:
        instance_id: Instance ID
        user: Current authenticated user
        service: Instance service
        request: Lifecycle update request

    Returns:
        Updated instance with new lifecycle settings
    """
    instance = await service.update_lifecycle(user, instance_id, request)
    return DataResponse(data=instance_to_response(instance))


@router.put("/{instance_id}/cpu", response_model=DataResponse[InstanceResponse])
async def update_instance_cpu(
    instance_id: int,
    user: CurrentUser,
    service: InstanceServiceDep,
    request: UpdateCpuRequest,
) -> DataResponse[InstanceResponse]:
    """Update instance CPU cores.

    Updates CPU allocation for a running instance using K8s in-place resize.
    CPU is specified as cores (1-8), with automatic 2x burst limit.

    Args:
        instance_id: Instance ID
        user: Current authenticated user
        service: Instance service
        request: CPU update request

    Returns:
        Updated instance with new CPU settings

    Raises:
        404: If instance not found
        409: If instance is not running
    """
    instance = await service.update_cpu(user, instance_id, request.cpu_cores)
    return DataResponse(data=instance_to_response(instance))


@router.put("/{instance_id}/memory", response_model=DataResponse[InstanceResponse])
async def update_instance_memory(
    instance_id: int,
    user: CurrentUser,
    service: InstanceServiceDep,
    request: UpdateMemoryRequest,
) -> DataResponse[InstanceResponse]:
    """Upgrade instance memory.

    Increases memory allocation for a running instance using K8s in-place resize.
    Only memory INCREASES are allowed (decreases would OOM-kill the process).

    Args:
        instance_id: Instance ID
        user: Current authenticated user
        service: Instance service
        request: Memory update request

    Returns:
        Updated instance with new memory settings

    Raises:
        404: If instance not found
        409: If instance is not running or memory decrease attempted
        400: If memory_gb exceeds maximum (32GB)
    """
    instance = await service.update_memory(user, instance_id, request.memory_gb)
    return DataResponse(data=instance_to_response(instance))


@router.get("/{instance_id}/progress", response_model=DataResponse[dict[str, Any]])
async def get_instance_progress(
    instance_id: int,
    user: CurrentUser,
    service: InstanceServiceDep,
) -> DataResponse[dict[str, Any]]:
    """Get instance loading progress.

    Args:
        instance_id: Instance ID
        user: Current authenticated user
        service: Instance service

    Returns:
        Progress details with phase and step information
    """
    progress = await service.get_progress(instance_id)
    return DataResponse(data=progress)


@router.get("/{instance_id}/events", response_model=PaginatedResponse[dict])
async def get_instance_events(
    instance_id: int,
    user: CurrentUser,
    session: AsyncSession = Depends(get_async_session),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> PaginatedResponse[dict]:
    """Get resource events for an instance.

    Returns events like memory upgrades, CPU updates, and OOM recoveries.

    Args:
        instance_id: Instance ID
        user: Current authenticated user
        session: Database session
        offset: Pagination offset
        limit: Pagination limit

    Returns:
        Paginated list of instance events
    """
    from control_plane.repositories.instance_events import InstanceEventsRepository

    repo = InstanceEventsRepository(session)
    events, total = await repo.list_by_instance(instance_id, limit=limit, offset=offset)

    return PaginatedResponse(
        data=[
            {
                "id": e.id,
                "event_type": e.event_type,
                "details": e.details,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in events
        ],
        meta=PaginationMeta(total=total, limit=limit, offset=offset),
    )
