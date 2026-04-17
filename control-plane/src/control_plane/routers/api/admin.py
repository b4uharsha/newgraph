"""Admin API router for privileged operations."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends
from graph_olap_schemas import BulkDeleteResponse, E2ECleanupResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.clients.gcs import build_gcs_client_from_settings
from control_plane.config import get_settings
from control_plane.infrastructure import tables
from control_plane.infrastructure.database import get_async_session
from control_plane.middleware.identity import CurrentUser
from control_plane.models import UserRole
from control_plane.models.errors import RoleRequiredError, ValidationError
from control_plane.models.requests import BulkDeleteRequest
from control_plane.models.responses import DataResponse
from control_plane.repositories.config import GlobalConfigRepository
from control_plane.repositories.instances import InstanceRepository
from control_plane.repositories.snapshots import SnapshotRepository
from control_plane.services.e2e_cleanup_service import E2ECleanupService
from control_plane.services.instance_service import InstanceService
from control_plane.services.k8s_service import get_k8s_service

router = APIRouter(prefix="/api/admin", tags=["Admin"])

logger = structlog.get_logger(__name__)


def require_admin_role(user: CurrentUser) -> None:
    """Require admin or ops role for admin endpoints (ops inherits admin)."""
    if user.role not in (UserRole.ADMIN, UserRole.OPS):
        raise RoleRequiredError(required_role="admin", user_role=user.role.value)


def require_admin_or_ops_role(user: CurrentUser) -> None:
    """Require admin or ops role for privileged operations."""
    if user.role not in (UserRole.ADMIN, UserRole.OPS):
        raise RoleRequiredError(required_role="admin or ops", user_role=user.role.value)


async def get_instance_service(
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

    from control_plane.repositories.favorites import FavoritesRepository

    # Construct GCS client from settings. Raises if GCS is configured but the
    # client cannot be built — prevents silent cascade-delete GCS leaks.
    gcs_client = build_gcs_client_from_settings(settings)

    return InstanceService(
        instance_repo=InstanceRepository(session),
        snapshot_repo=SnapshotRepository(session),
        config_repo=GlobalConfigRepository(session),
        favorites_repo=FavoritesRepository(session),
        k8s_service=k8s_service,
        gcs_client=gcs_client,
    )


InstanceServiceDep = Annotated[InstanceService, Depends(get_instance_service)]


async def get_e2e_cleanup_service(
    session: AsyncSession = Depends(get_async_session),
) -> E2ECleanupService:
    """Dependency to get E2E cleanup service."""
    from control_plane.repositories.mappings import MappingRepository
    from control_plane.repositories.users import UserRepository

    settings = get_settings()

    # Get K8s service (will be None if K8s not available)
    k8s_service = None
    if settings.k8s_in_cluster or settings.k8s_namespace:
        try:
            k8s_service = get_k8s_service(settings)
        except Exception as e:
            logger.warning("k8s_service_unavailable_for_cleanup", error=str(e))

    # Construct GCS client from settings. Raises if GCS is configured but the
    # client cannot be built — prevents silent cascade-delete GCS leaks.
    gcs_client = build_gcs_client_from_settings(settings)

    return E2ECleanupService(
        user_repo=UserRepository(session),
        instance_repo=InstanceRepository(session),
        snapshot_repo=SnapshotRepository(session),
        mapping_repo=MappingRepository(session),
        k8s_service=k8s_service,
        gcs_client=gcs_client,
    )


E2ECleanupServiceDep = Annotated[E2ECleanupService, Depends(get_e2e_cleanup_service)]


# All response models are imported from graph_olap_schemas above


# Endpoints


@router.delete("/resources/bulk", response_model=DataResponse[BulkDeleteResponse])
async def bulk_delete_resources(
    request: BulkDeleteRequest,
    user: CurrentUser,
    instance_service: InstanceServiceDep,
    session: AsyncSession = Depends(get_async_session),
) -> DataResponse[BulkDeleteResponse]:
    """Bulk delete resources with safety filters.

    Requires: Admin role

    Safety features:
    - Requires at least one filter
    - Max 100 deletions per request
    - Expected count validation (must match dry run result)
    - Dry run mode available
    - Full audit logging

    Args:
        request: Bulk delete request with filters
        user: Current user (must be admin)
        session: Database session

    Returns:
        Results of bulk delete operation
    """
    require_admin_role(user)

    # Validate filters - at least one required
    if not any([
        request.filters.name_prefix,
        request.filters.created_by,
        request.filters.older_than_hours,
        request.filters.status,
    ]):
        raise ValidationError(
            field="filters",
            message="At least one filter required (safety check)"
        )

    # Build query based on resource type
    if request.resource_type == "instance":
        resource_table = tables.instances
    elif request.resource_type == "snapshot":
        resource_table = tables.snapshots
    elif request.resource_type == "mapping":
        resource_table = tables.mappings
    else:
        raise ValidationError(
            field="resource_type",
            message=f"Invalid resource_type: {request.resource_type}. Must be 'instance', 'snapshot', or 'mapping'."
        )

    query = select(resource_table)

    # Apply filters
    if request.filters.name_prefix:
        query = query.where(resource_table.c.name.like(f"{request.filters.name_prefix}%"))

    if request.filters.created_by:
        # All resource tables (mappings, instances, snapshots) use owner_username.
        # The created_by column only exists on mapping_versions.
        query = query.where(resource_table.c.owner_username == request.filters.created_by)

    if request.filters.older_than_hours:
        cutoff = datetime.now(UTC) - timedelta(hours=request.filters.older_than_hours)
        cutoff_str = cutoff.isoformat()
        query = query.where(resource_table.c.created_at < cutoff_str)

    if request.filters.status:
        # Just filter by status string directly (tables use TEXT columns)
        query = query.where(resource_table.c.status == request.filters.status)

    # Get matching resources
    result = await session.execute(query)
    rows = result.all()

    # Check limit
    if len(rows) > 100:
        raise ValidationError(
            field="filters",
            message=f"Matched {len(rows)} resources, max 100 per request. Refine filters."
        )

    # Validate expected count (safety check)
    if request.expected_count is not None and len(rows) != request.expected_count:
        raise ValidationError(
            field="expected_count",
            message=(
                f"Expected {request.expected_count} resources but matched {len(rows)}. "
                f"Run with dry_run=True first to get actual count, then pass as expected_count."
            )
        )

    # Dry run mode - just return what would be deleted
    if request.dry_run:
        return DataResponse(
            data=BulkDeleteResponse(
                dry_run=True,
                matched_count=len(rows),
                matched_ids=[row.id for row in rows],
            )
        )

    # Audit log start
    logger.warning(
        "bulk_delete_started",
        resource_type=request.resource_type,
        matched_count=len(rows),
        filters={
            "name_prefix": request.filters.name_prefix,
            "created_by": request.filters.created_by,
            "older_than_hours": request.filters.older_than_hours,
            "status": request.filters.status,
        },
        deleted_by=user.username,
        reason=request.reason,
    )

    # Delete resources
    deleted_ids = []
    failed_ids = []
    errors = {}

    if request.resource_type == "instance":
        # For instances: use proper cleanup that deletes K8s resources
        # Delete in parallel with concurrency limit (10 at a time)
        sem = asyncio.Semaphore(10)

        async def delete_one_instance(instance_id: int):
            async with sem:
                try:
                    await instance_service.delete_instance(
                        instance_id=instance_id,
                        user=user,
                    )
                    deleted_ids.append(instance_id)
                except Exception as e:
                    failed_ids.append(instance_id)
                    errors[instance_id] = str(e)
                    logger.error(
                        "bulk_delete_item_failed",
                        resource_type="instance",
                        instance_id=instance_id,
                        error=str(e),
                    )

        # Execute all deletions in parallel
        await asyncio.gather(*[delete_one_instance(row.id) for row in rows])

    elif request.resource_type in ("snapshot", "mapping"):
        # For snapshots and mappings: simple SQL delete (no K8s resources)
        for row in rows:
            try:
                from sqlalchemy import delete

                await session.execute(
                    delete(resource_table).where(resource_table.c.id == row.id)
                )
                await session.flush()
                deleted_ids.append(row.id)

            except Exception as e:
                failed_ids.append(row.id)
                errors[row.id] = str(e)
                logger.error(
                    "bulk_delete_item_failed",
                    resource_type=request.resource_type,
                    resource_id=row.id,
                    error=str(e),
                )

        # Commit transaction for SQL deletes
        await session.commit()

    # Audit log completion
    logger.info(
        "bulk_delete_completed",
        resource_type=request.resource_type,
        matched_count=len(rows),
        deleted_count=len(deleted_ids),
        failed_count=len(failed_ids),
        deleted_by=user.username,
    )

    return DataResponse(
        data=BulkDeleteResponse(
            dry_run=False,
            matched_count=len(rows),
            deleted_count=len(deleted_ids),
            deleted_ids=deleted_ids,
            failed_ids=failed_ids,
            errors=errors,
        )
    )


@router.delete("/e2e-cleanup", response_model=DataResponse[E2ECleanupResponse])
async def e2e_cleanup(
    user: CurrentUser,
    cleanup_service: E2ECleanupServiceDep,
) -> DataResponse[E2ECleanupResponse]:
    """Delete ALL resources owned by E2E test users.

    This endpoint is called before and after E2E test runs to ensure
    a clean state. It deletes all resources (instances, snapshots, mappings)
    owned by users configured in E2E_TEST_USER_EMAILS.

    Requires: Admin or Ops role

    Cleanup order:
    1. Instances (including K8s wrapper pods)
    2. Snapshots (including GCS files)
    3. Mappings
    4. Force-terminate any orphaned K8s pods by owner-email label

    Returns:
        Summary of deleted resources and any errors
    """
    require_admin_or_ops_role(user)

    logger.info(
        "e2e_cleanup_api_called",
        requested_by=user.username,
        user_role=user.role.value,
    )

    result = await cleanup_service.cleanup_all_test_resources(user)

    return DataResponse(
        data=E2ECleanupResponse(
            users_processed=result.users_processed,
            instances_deleted=result.instances_deleted,
            snapshots_deleted=result.snapshots_deleted,
            mappings_deleted=result.mappings_deleted,
            pods_terminated=result.pods_terminated,
            gcs_files_deleted=result.gcs_files_deleted,
            gcs_bytes_deleted=result.gcs_bytes_deleted,
            errors=result.errors,
            success=result.success,
        )
    )
