"""Mappings API router."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from graph_olap_schemas import (
    EdgeDefinition as EdgeDefinitionSchema,
)
from graph_olap_schemas import (
    NodeDefinition as NodeDefinitionSchema,
)
from graph_olap_schemas import (
    PrimaryKeyDefinition as PrimaryKeyDefinitionSchema,
)
from graph_olap_schemas import (
    PropertyDefinition as PropertyDefinitionSchema,
)
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.infrastructure.database import get_async_session
from control_plane.middleware.identity import CurrentUser
from control_plane.models.errors import NotFoundError
from control_plane.models.requests import (
    CopyMappingRequest,
    CreateMappingRequest,
    UpdateLifecycleRequest,
    UpdateMappingRequest,
)
from control_plane.models.responses import (
    DataResponse,
    InstanceResponse,
    LifecycleResponse,
    MappingResponse,
    MappingSummaryResponse,
    MappingVersionResponse,
    MappingVersionSummaryResponse,
    PaginatedResponse,
    PaginationMeta,
    SnapshotResponse,
)
from control_plane.repositories.favorites import FavoritesRepository
from control_plane.repositories.mappings import MappingRepository
from control_plane.repositories.snapshots import SnapshotFilters, SnapshotRepository
from control_plane.services.mapping_service import MappingService, check_ownership

router = APIRouter(prefix="/api/mappings", tags=["Mappings"])


def get_mapping_service(
    session: AsyncSession = Depends(get_async_session),
) -> MappingService:
    """Dependency to get mapping service."""
    from control_plane.repositories.instances import InstanceRepository

    return MappingService(
        mapping_repo=MappingRepository(session),
        snapshot_repo=SnapshotRepository(session),
        favorites_repo=FavoritesRepository(session),
        instance_repo=InstanceRepository(session),
    )


def get_mapping_repo(
    session: AsyncSession = Depends(get_async_session),
) -> MappingRepository:
    """Dependency to get mapping repository."""
    return MappingRepository(session)


def get_snapshot_repo(
    session: AsyncSession = Depends(get_async_session),
) -> SnapshotRepository:
    """Dependency to get snapshot repository."""
    return SnapshotRepository(session)


def get_instance_repo(
    session: AsyncSession = Depends(get_async_session),
):
    """Dependency to get instance repository."""
    from control_plane.repositories.instances import InstanceRepository

    return InstanceRepository(session)


MappingServiceDep = Annotated[MappingService, Depends(get_mapping_service)]
MappingRepoDep = Annotated[MappingRepository, Depends(get_mapping_repo)]
SnapshotRepoDep = Annotated[SnapshotRepository, Depends(get_snapshot_repo)]
InstanceRepoDep = Annotated["InstanceRepository", Depends(get_instance_repo)]


def domain_node_to_schema(nd) -> NodeDefinitionSchema:
    """Convert domain NodeDefinition to schema model for response."""
    return NodeDefinitionSchema(
        label=nd.label,
        sql=nd.sql,
        primary_key=PrimaryKeyDefinitionSchema(
            name=nd.primary_key.name,
            type=nd.primary_key.type,
        ),
        properties=[PropertyDefinitionSchema(name=p.name, type=p.type) for p in nd.properties],
    )


def domain_edge_to_schema(ed) -> EdgeDefinitionSchema:
    """Convert domain EdgeDefinition to schema model for response."""
    return EdgeDefinitionSchema(
        type=ed.type,
        from_node=ed.from_node,
        to_node=ed.to_node,
        sql=ed.sql,
        from_key=ed.from_key,
        to_key=ed.to_key,
        properties=[PropertyDefinitionSchema(name=p.name, type=p.type) for p in ed.properties],
    )


def mapping_to_response(mapping) -> MappingResponse:
    """Convert domain Mapping to response model."""
    return MappingResponse(
        id=mapping.id,
        owner_username=mapping.owner_username,
        name=mapping.name,
        description=mapping.description,
        current_version=mapping.current_version,
        created_at=mapping.created_at,
        updated_at=mapping.updated_at,
        ttl=mapping.ttl,
        inactivity_timeout=mapping.inactivity_timeout,
        node_definitions=[domain_node_to_schema(nd) for nd in mapping.node_definitions],
        edge_definitions=[domain_edge_to_schema(ed) for ed in mapping.edge_definitions],
        change_description=mapping.change_description,
        version_created_at=mapping.version_created_at,
        version_created_by=mapping.version_created_by,
    )


def mapping_to_summary(mapping) -> MappingSummaryResponse:
    """Convert domain Mapping to summary response model."""
    return MappingSummaryResponse(
        id=mapping.id,
        owner_username=mapping.owner_username,
        name=mapping.name,
        description=mapping.description,
        current_version=mapping.current_version,
        created_at=mapping.created_at,
        updated_at=mapping.updated_at,
        node_count=len(mapping.node_definitions),
        edge_type_count=len(mapping.edge_definitions),
    )


@router.get("", response_model=PaginatedResponse[MappingSummaryResponse])
async def list_mappings(
    user: CurrentUser,
    service: MappingServiceDep,
    owner: str | None = None,
    search: str | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> PaginatedResponse[MappingSummaryResponse]:
    """List mappings with optional filters.

    Args:
        user: Current authenticated user
        service: Mapping service
        owner: Filter by owner username
        search: Search in name/description
        sort_by: Field to sort by
        sort_order: Sort order (asc/desc)
        offset: Pagination offset
        limit: Pagination limit

    Returns:
        Paginated list of mapping summaries
    """
    mappings, total = await service.list_mappings(
        user=user,
        owner=owner,
        search=search,
        limit=limit,
        offset=offset,
        sort_field=sort_by,
        sort_order=sort_order,
    )

    return PaginatedResponse(
        data=[mapping_to_summary(m) for m in mappings],
        meta=PaginationMeta(
            total=total,
            limit=limit,
            offset=offset,
        ),
    )


@router.post(
    "",
    response_model=DataResponse[MappingResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_mapping(
    user: CurrentUser,
    service: MappingServiceDep,
    request: CreateMappingRequest,
) -> DataResponse[MappingResponse]:
    """Create a new mapping.

    The current user becomes the owner.

    Args:
        user: Current authenticated user
        service: Mapping service
        request: Mapping creation request

    Returns:
        Created mapping
    """
    mapping = await service.create_mapping(user, request)
    return DataResponse(data=mapping_to_response(mapping))


@router.get("/{mapping_id}", response_model=DataResponse[MappingResponse])
async def get_mapping(
    mapping_id: int,
    user: CurrentUser,
    service: MappingServiceDep,
) -> DataResponse[MappingResponse]:
    """Get a mapping by ID.

    Args:
        mapping_id: Mapping ID
        user: Current authenticated user
        service: Mapping service

    Returns:
        Mapping with current version details
    """
    mapping = await service.get_mapping(mapping_id)
    return DataResponse(data=mapping_to_response(mapping))


@router.get("/{mapping_id}/tree", response_model=DataResponse[dict])
async def get_mapping_tree(
    mapping_id: int,
    user: CurrentUser,
    service: MappingServiceDep,
    include_instances: bool = True,
    status: str | None = None,
) -> DataResponse[dict]:
    """Get resource tree showing version → snapshot → instance hierarchy.

    Args:
        mapping_id: Mapping ID
        user: Current authenticated user
        service: Mapping service
        include_instances: Include instance details (default: true)
        status: Filter snapshots by status

    Returns:
        Tree structure with versions, snapshots, and instances
    """
    tree = await service.get_tree(
        mapping_id=mapping_id,
        include_instances=include_instances,
        status_filter=status,
    )
    return DataResponse(data=tree)


@router.put("/{mapping_id}", response_model=DataResponse[MappingResponse])
async def update_mapping(
    mapping_id: int,
    user: CurrentUser,
    service: MappingServiceDep,
    request: UpdateMappingRequest,
) -> DataResponse[MappingResponse]:
    """Update a mapping.

    Creates a new version if node/edge definitions change.

    Args:
        mapping_id: Mapping ID
        user: Current authenticated user
        service: Mapping service
        request: Update request

    Returns:
        Updated mapping
    """
    mapping = await service.update_mapping(user, mapping_id, request)
    return DataResponse(data=mapping_to_response(mapping))


@router.delete("/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mapping(
    mapping_id: int,
    user: CurrentUser,
    service: MappingServiceDep,
) -> None:
    """Delete a mapping.

    Cannot delete if snapshots exist.

    Args:
        mapping_id: Mapping ID
        user: Current authenticated user
        service: Mapping service
    """
    await service.delete_mapping(user, mapping_id)


@router.post(
    "/{mapping_id}/copy",
    response_model=DataResponse[MappingResponse],
    status_code=status.HTTP_201_CREATED,
)
async def copy_mapping(
    mapping_id: int,
    user: CurrentUser,
    repo: MappingRepoDep,
    request: CopyMappingRequest,
) -> DataResponse[MappingResponse]:
    """Copy a mapping.

    Creates a new mapping with the current version's definitions.
    The current user becomes the owner.

    Args:
        mapping_id: Source mapping ID
        user: Current authenticated user (becomes owner)
        repo: Mapping repository
        request: Copy request with new name

    Returns:
        Created mapping

    Raises:
        404: Source mapping not found
    """
    # Get source mapping
    source = await repo.get_by_id(mapping_id)
    if source is None:
        raise NotFoundError("mapping", mapping_id)

    # Create copy with current user as owner
    copied = await repo.create(
        owner_username=user.username,
        name=request.name,
        description=source.description,
        node_definitions=source.node_definitions,
        edge_definitions=source.edge_definitions,
        ttl=source.ttl,
        inactivity_timeout=source.inactivity_timeout,
    )
    return DataResponse(data=mapping_to_response(copied))


@router.put("/{mapping_id}/lifecycle", response_model=DataResponse[LifecycleResponse])
async def update_mapping_lifecycle(
    mapping_id: int,
    user: CurrentUser,
    service: MappingServiceDep,
    repo: MappingRepoDep,
    request: UpdateLifecycleRequest,
) -> DataResponse[LifecycleResponse]:
    """Update mapping lifecycle settings.

    Args:
        mapping_id: Mapping ID
        user: Current authenticated user
        service: Mapping service (for permission check)
        repo: Mapping repository
        request: Lifecycle update request

    Returns:
        Updated lifecycle settings

    Raises:
        404: Mapping not found
        403: Permission denied
    """
    # Check mapping exists and user has permission
    mapping = await service.get_mapping(mapping_id)
    check_ownership(user, mapping.owner_username, "Mapping", mapping_id)

    # Update lifecycle
    updated = await repo.update_lifecycle(
        mapping_id=mapping_id,
        ttl=request.ttl,
        inactivity_timeout=request.inactivity_timeout,
    )
    if updated is None:
        raise NotFoundError("mapping", mapping_id)

    return DataResponse(
        data=LifecycleResponse(
            id=updated.id,
            ttl=updated.ttl,
            inactivity_timeout=updated.inactivity_timeout,
            updated_at=updated.updated_at,
        )
    )


@router.get(
    "/{mapping_id}/versions",
    response_model=PaginatedResponse[MappingVersionSummaryResponse],
)
async def list_mapping_versions(
    mapping_id: int,
    user: CurrentUser,
    repo: MappingRepoDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> PaginatedResponse[MappingVersionSummaryResponse]:
    """List all versions of a mapping.

    Args:
        mapping_id: Mapping ID
        user: Current authenticated user
        repo: Mapping repository
        offset: Pagination offset
        limit: Pagination limit

    Returns:
        Paginated list of version summaries

    Raises:
        404: Mapping not found
    """
    # Verify mapping exists
    if not await repo.exists(mapping_id):
        raise NotFoundError("mapping", mapping_id)

    versions = await repo.list_versions(mapping_id)

    # Apply pagination manually (repo returns all versions)
    total = len(versions)
    paginated = versions[offset : offset + limit]

    return PaginatedResponse(
        data=[
            MappingVersionSummaryResponse(
                version=v.version,
                change_description=v.change_description,
                created_at=v.created_at,
                created_by=v.created_by,
            )
            for v in paginated
        ],
        meta=PaginationMeta(
            total=total,
            limit=limit,
            offset=offset,
        ),
    )


@router.get(
    "/{mapping_id}/versions/{version}",
    response_model=DataResponse[MappingVersionResponse],
)
async def get_mapping_version(
    mapping_id: int,
    version: int,
    user: CurrentUser,
    repo: MappingRepoDep,
) -> DataResponse[MappingVersionResponse]:
    """Get a specific version of a mapping.

    Args:
        mapping_id: Mapping ID
        version: Version number
        user: Current authenticated user
        repo: Mapping repository

    Returns:
        Full version details with definitions

    Raises:
        404: Mapping or version not found
    """
    # Verify mapping exists
    if not await repo.exists(mapping_id):
        raise NotFoundError("mapping", mapping_id)

    mapping_version = await repo.get_version(mapping_id, version)
    if mapping_version is None:
        raise NotFoundError("mapping_version", f"{mapping_id}/v{version}")

    return DataResponse(
        data=MappingVersionResponse(
            mapping_id=mapping_version.mapping_id,
            version=mapping_version.version,
            change_description=mapping_version.change_description,
            node_definitions=[domain_node_to_schema(nd) for nd in mapping_version.node_definitions],
            edge_definitions=[domain_edge_to_schema(ed) for ed in mapping_version.edge_definitions],
            created_at=mapping_version.created_at,
            created_by=mapping_version.created_by,
        )
    )


@router.get(
    "/{mapping_id}/versions/{from_version}/diff/{to_version}",
)
async def get_mapping_version_diff(
    mapping_id: int,
    from_version: int,
    to_version: int,
    user: CurrentUser,
    service: MappingServiceDep,
) -> DataResponse:
    """Compare two versions of a mapping.

    Returns a semantic diff showing added, removed, and modified nodes/edges
    between two versions.

    Args:
        mapping_id: Mapping ID
        from_version: Starting version number
        to_version: Ending version number
        user: Current authenticated user
        service: Mapping service

    Returns:
        Structured diff with summary counts and detailed changes

    Raises:
        404: Mapping or version not found
        400: Invalid version numbers (e.g., same version)
    """
    from fastapi import HTTPException
    from graph_olap_schemas import (
        EdgeDiffResponse,
        MappingDiffChangesResponse,
        MappingDiffDataResponse,
        MappingDiffResponse,
        MappingDiffSummaryResponse,
        NodeDiffResponse,
    )

    try:
        diff_result = await service.get_version_diff(mapping_id, from_version, to_version)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    # Convert domain model to response model
    response = MappingDiffResponse(
        data=MappingDiffDataResponse(
            mapping_id=diff_result.mapping_id,
            from_version=diff_result.from_version,
            to_version=diff_result.to_version,
            summary=MappingDiffSummaryResponse(
                nodes_added=diff_result.nodes_added,
                nodes_removed=diff_result.nodes_removed,
                nodes_modified=diff_result.nodes_modified,
                edges_added=diff_result.edges_added,
                edges_removed=diff_result.edges_removed,
                edges_modified=diff_result.edges_modified,
            ),
            changes=MappingDiffChangesResponse(
                nodes=[
                    NodeDiffResponse(
                        label=nd.label,
                        change_type=nd.change_type,
                        fields_changed=nd.fields_changed,
                        from_=nd.from_def,
                        to=nd.to_def,
                    )
                    for nd in diff_result.node_diffs
                ],
                edges=[
                    EdgeDiffResponse(
                        type=ed.type,
                        change_type=ed.change_type,
                        fields_changed=ed.fields_changed,
                        from_=ed.from_def,
                        to=ed.to_def,
                    )
                    for ed in diff_result.edge_diffs
                ],
            ),
        )
    )

    return DataResponse(data=response.data)


@router.get(
    "/{mapping_id}/snapshots",
    response_model=PaginatedResponse[SnapshotResponse],
)
async def list_mapping_snapshots(
    mapping_id: int,
    user: CurrentUser,
    mapping_repo: MappingRepoDep,
    snapshot_repo: SnapshotRepoDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> PaginatedResponse[SnapshotResponse]:
    """List all snapshots for a mapping.

    Returns snapshots across all versions of this mapping.

    Args:
        mapping_id: Mapping ID
        user: Current authenticated user
        mapping_repo: Mapping repository
        snapshot_repo: Snapshot repository
        offset: Pagination offset
        limit: Pagination limit

    Returns:
        Paginated list of snapshots

    Raises:
        404: Mapping not found
    """
    # Verify mapping exists
    if not await mapping_repo.exists(mapping_id):
        raise NotFoundError("mapping", mapping_id)

    snapshots, total = await snapshot_repo.list_snapshots(
        filters=SnapshotFilters(mapping_id=mapping_id),
        limit=limit,
        offset=offset,
    )

    return PaginatedResponse(
        data=[
            SnapshotResponse(
                id=s.id,
                mapping_id=s.mapping_id,
                mapping_version=s.mapping_version,
                owner_username=s.owner_username,
                name=s.name,
                description=s.description,
                gcs_path=s.gcs_path,
                status=s.status.value,
                size_bytes=s.size_bytes,
                node_counts=s.node_counts,
                edge_counts=s.edge_counts,
                progress=s.progress,
                error_message=s.error_message,
                created_at=s.created_at,
                updated_at=s.updated_at,
                ttl=s.ttl,
                inactivity_timeout=s.inactivity_timeout,
                last_used_at=s.last_used_at,
            )
            for s in snapshots
        ],
        meta=PaginationMeta(
            total=total,
            limit=limit,
            offset=offset,
        ),
    )


@router.get(
    "/{mapping_id}/instances",
    response_model=PaginatedResponse[InstanceResponse],
)
async def list_mapping_instances(
    mapping_id: int,
    user: CurrentUser,
    mapping_repo: MappingRepoDep,
    instance_repo: InstanceRepoDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> PaginatedResponse[InstanceResponse]:
    """List all instances created from this mapping.

    Returns instances created from any snapshot of this mapping.

    Args:
        mapping_id: Mapping ID
        user: Current authenticated user
        mapping_repo: Mapping repository
        instance_repo: Instance repository
        offset: Pagination offset
        limit: Pagination limit

    Returns:
        Paginated list of instances

    Raises:
        404: Mapping not found
    """
    # Import here to avoid circular import
    from control_plane.routers.api.instances import instance_to_response

    # Verify mapping exists
    if not await mapping_repo.exists(mapping_id):
        raise NotFoundError("Mapping", mapping_id)

    instances, total = await instance_repo.list_by_mapping(
        mapping_id=mapping_id,
        limit=limit,
        offset=offset,
    )

    return PaginatedResponse(
        data=[instance_to_response(i) for i in instances],
        meta=PaginationMeta(
            total=total,
            limit=limit,
            offset=offset,
        ),
    )
