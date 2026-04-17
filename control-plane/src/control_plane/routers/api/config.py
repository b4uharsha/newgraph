"""Config API router for Ops users."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from graph_olap_schemas import (
    ConcurrencyConfig,
    ConcurrencyConfigResponse,
    ExportConfigRequest,
    ExportConfigResponse,
    LifecycleConfigRequest,
    LifecycleConfigResponse,
    MaintenanceModeRequest,
    MaintenanceModeResponse,
    ResourceLifecycleConfig,
)
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.infrastructure.database import get_async_session
from control_plane.middleware.identity import CurrentUser
from control_plane.models import UserRole
from control_plane.models.errors import RoleRequiredError
from control_plane.models.responses import DataResponse
from control_plane.repositories.config import GlobalConfigRepository

router = APIRouter(prefix="/api/config", tags=["Config"])


def get_config_repo(
    session: AsyncSession = Depends(get_async_session),
) -> GlobalConfigRepository:
    """Dependency to get config repository."""
    return GlobalConfigRepository(session)


ConfigRepoDep = Annotated[GlobalConfigRepository, Depends(get_config_repo)]


def require_ops_role(user: CurrentUser) -> None:
    """Require ops role for config endpoints."""
    if user.role != UserRole.OPS:
        raise RoleRequiredError(required_role="ops", user_role=user.role.value)


# All request/response models are imported from graph_olap_schemas above
# except for UpdatedResponse which is config-specific


class UpdatedResponse(BaseModel):
    """Simple updated response for config updates."""

    updated: bool
    updated_at: datetime


# Endpoints


@router.get("/lifecycle", response_model=DataResponse[LifecycleConfigResponse])
async def get_lifecycle_config(
    user: CurrentUser,
    repo: ConfigRepoDep,
) -> DataResponse[LifecycleConfigResponse]:
    """Get lifecycle configuration for all resource types.

    Requires Ops role.
    """
    require_ops_role(user)

    mapping_config = await repo.get_lifecycle_config("mapping")
    snapshot_config = await repo.get_lifecycle_config("snapshot")
    instance_config = await repo.get_lifecycle_config("instance")

    return DataResponse(
        data=LifecycleConfigResponse(
            mapping=ResourceLifecycleConfig(
                default_ttl=mapping_config.get("default_ttl"),
                default_inactivity=mapping_config.get("default_inactivity"),
                max_ttl=mapping_config.get("max_ttl"),
            ),
            snapshot=ResourceLifecycleConfig(
                default_ttl=snapshot_config.get("default_ttl"),
                default_inactivity=snapshot_config.get("default_inactivity"),
                max_ttl=snapshot_config.get("max_ttl"),
            ),
            instance=ResourceLifecycleConfig(
                default_ttl=instance_config.get("default_ttl"),
                default_inactivity=instance_config.get("default_inactivity"),
                max_ttl=instance_config.get("max_ttl"),
            ),
        )
    )


@router.put("/lifecycle", response_model=DataResponse[UpdatedResponse])
async def update_lifecycle_config(
    user: CurrentUser,
    repo: ConfigRepoDep,
    request: LifecycleConfigRequest,
) -> DataResponse[UpdatedResponse]:
    """Update lifecycle configuration for resource types.

    Requires Ops role.
    """
    require_ops_role(user)

    now = datetime.utcnow()

    # Update mapping lifecycle if provided
    if request.mapping:
        if request.mapping.default_ttl is not None:
            await repo.set(
                "lifecycle.mapping.default_ttl", request.mapping.default_ttl, user.username
            )
        if request.mapping.default_inactivity is not None:
            await repo.set(
                "lifecycle.mapping.default_inactivity",
                request.mapping.default_inactivity,
                user.username,
            )
        if request.mapping.max_ttl is not None:
            await repo.set("lifecycle.mapping.max_ttl", request.mapping.max_ttl, user.username)

    # Update snapshot lifecycle if provided
    if request.snapshot:
        if request.snapshot.default_ttl is not None:
            await repo.set(
                "lifecycle.snapshot.default_ttl", request.snapshot.default_ttl, user.username
            )
        if request.snapshot.default_inactivity is not None:
            await repo.set(
                "lifecycle.snapshot.default_inactivity",
                request.snapshot.default_inactivity,
                user.username,
            )
        if request.snapshot.max_ttl is not None:
            await repo.set("lifecycle.snapshot.max_ttl", request.snapshot.max_ttl, user.username)

    # Update instance lifecycle if provided
    if request.instance:
        if request.instance.default_ttl is not None:
            await repo.set(
                "lifecycle.instance.default_ttl", request.instance.default_ttl, user.username
            )
        if request.instance.default_inactivity is not None:
            await repo.set(
                "lifecycle.instance.default_inactivity",
                request.instance.default_inactivity,
                user.username,
            )
        if request.instance.max_ttl is not None:
            await repo.set("lifecycle.instance.max_ttl", request.instance.max_ttl, user.username)

    return DataResponse(data=UpdatedResponse(updated=True, updated_at=now))


@router.get("/concurrency", response_model=DataResponse[ConcurrencyConfigResponse])
async def get_concurrency_config(
    user: CurrentUser,
    repo: ConfigRepoDep,
) -> DataResponse[ConcurrencyConfigResponse]:
    """Get concurrency limits configuration.

    Requires Ops role.
    """
    require_ops_role(user)

    limits = await repo.get_concurrency_limits()

    return DataResponse(
        data=ConcurrencyConfigResponse(
            per_analyst=limits["per_analyst"],
            cluster_total=limits["cluster_total"],
        )
    )


@router.put("/concurrency", response_model=DataResponse[ConcurrencyConfigResponse])
async def update_concurrency_config(
    user: CurrentUser,
    repo: ConfigRepoDep,
    request: ConcurrencyConfig,
) -> DataResponse[ConcurrencyConfigResponse]:
    """Update concurrency limits configuration.

    Requires Ops role.
    """
    require_ops_role(user)

    now = datetime.utcnow()

    await repo.set("concurrency.per_analyst", str(request.per_analyst), user.username)
    await repo.set("concurrency.cluster_total", str(request.cluster_total), user.username)

    return DataResponse(
        data=ConcurrencyConfigResponse(
            per_analyst=request.per_analyst,
            cluster_total=request.cluster_total,
            updated_at=now,
        )
    )


@router.get("/maintenance", response_model=DataResponse[MaintenanceModeResponse])
async def get_maintenance_mode(
    user: CurrentUser,
    repo: ConfigRepoDep,
) -> DataResponse[MaintenanceModeResponse]:
    """Get maintenance mode status.

    Requires Ops role.
    """
    require_ops_role(user)

    enabled = await repo.get_bool("maintenance.enabled", default=False)
    message = await repo.get_value("maintenance.message") or ""

    # Get metadata about when it was last updated
    config = await repo.get_config_with_metadata("maintenance.enabled")
    updated_at = config.get("updated_at") if config else None
    updated_by = config.get("updated_by") if config else None

    return DataResponse(
        data=MaintenanceModeResponse(
            enabled=enabled,
            message=message,
            updated_at=updated_at,
            updated_by=updated_by,
        )
    )


@router.put("/maintenance", response_model=DataResponse[MaintenanceModeResponse])
async def set_maintenance_mode(
    user: CurrentUser,
    repo: ConfigRepoDep,
    request: MaintenanceModeRequest,
) -> DataResponse[MaintenanceModeResponse]:
    """Set maintenance mode.

    Requires Ops role.
    """
    require_ops_role(user)

    now = datetime.utcnow()

    await repo.set("maintenance.enabled", "1" if request.enabled else "0", user.username)
    await repo.set("maintenance.message", request.message, user.username)

    return DataResponse(
        data=MaintenanceModeResponse(
            enabled=request.enabled,
            message=request.message,
            updated_at=now,
            updated_by=user.username,
        )
    )


@router.get("/export", response_model=DataResponse[ExportConfigResponse])
async def get_export_config(
    user: CurrentUser,
    repo: ConfigRepoDep,
) -> DataResponse[ExportConfigResponse]:
    """Get export configuration.

    Requires Ops role.
    """
    require_ops_role(user)

    config = await repo.get_export_config()

    return DataResponse(
        data=ExportConfigResponse(
            max_duration_seconds=config["max_duration_seconds"],
            updated_at=config.get("updated_at"),
            updated_by=config.get("updated_by"),
        )
    )


@router.put("/export", response_model=DataResponse[ExportConfigResponse])
async def update_export_config(
    user: CurrentUser,
    repo: ConfigRepoDep,
    request: ExportConfigRequest,
) -> DataResponse[ExportConfigResponse]:
    """Update export configuration.

    Requires Ops role.
    """
    require_ops_role(user)

    now = datetime.utcnow()

    await repo.set(
        "export.max_duration_seconds",
        str(request.max_duration_seconds),
        user.username,
        description="Max export job duration before timeout",
    )

    return DataResponse(
        data=ExportConfigResponse(
            max_duration_seconds=request.max_duration_seconds,
            updated_at=now,
            updated_by=user.username,
        )
    )
