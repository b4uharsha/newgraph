"""Mapping service with business logic."""

import structlog
from graph_olap_schemas import (
    EdgeDefinition as EdgeDefinitionSchema,
)

# Type imports for Pydantic schema models
from graph_olap_schemas import (
    NodeDefinition as NodeDefinitionSchema,
)

from control_plane.models import (
    DependencyError,
    EdgeDefinition,
    Mapping,
    MappingVersion,
    NodeDefinition,
    NotFoundError,
    PermissionDeniedError,
    PrimaryKeyDefinition,
    PropertyDefinition,
    User,
    UserRole,
)
from control_plane.models.requests import CreateMappingRequest, UpdateMappingRequest
from control_plane.repositories.favorites import FavoritesRepository
from control_plane.repositories.instances import InstanceFilters
from control_plane.repositories.mappings import (
    MappingFilters,
    MappingRepository,
    Pagination,
    Sort,
)
from control_plane.repositories.snapshots import SnapshotRepository

logger = structlog.get_logger()


def check_ownership(
    user: User,
    resource_owner: str,
    resource_type: str,
    resource_id: int,
) -> None:
    """Check if user can modify a resource.

    Admins and Ops can modify any resource.
    Analysts can only modify their own resources.

    Args:
        user: Current user
        resource_owner: Username of resource owner
        resource_type: Type of resource (for error message)
        resource_id: ID of resource (for error message)

    Raises:
        PermissionDeniedError: If user cannot modify resource
    """
    if user.role in (UserRole.ADMIN, UserRole.OPS):
        return
    if user.username != resource_owner:
        raise PermissionDeniedError(resource_type, resource_id)


def schema_to_domain_node(schema: NodeDefinitionSchema) -> NodeDefinition:
    """Convert Pydantic schema NodeDefinition to domain dataclass.

    Args:
        schema: Pydantic NodeDefinition from request

    Returns:
        Domain NodeDefinition dataclass
    """
    return NodeDefinition(
        label=schema.label,
        sql=schema.sql,
        primary_key=PrimaryKeyDefinition(
            name=schema.primary_key.name,
            type=schema.primary_key.type.value,
        ),
        properties=[PropertyDefinition(name=p.name, type=p.type.value) for p in schema.properties],
    )


def schema_to_domain_edge(schema: EdgeDefinitionSchema) -> EdgeDefinition:
    """Convert Pydantic schema EdgeDefinition to domain dataclass.

    Args:
        schema: Pydantic EdgeDefinition from request

    Returns:
        Domain EdgeDefinition dataclass
    """
    return EdgeDefinition(
        type=schema.type,
        from_node=schema.from_node,
        to_node=schema.to_node,
        sql=schema.sql,
        from_key=schema.from_key,
        to_key=schema.to_key,
        properties=[PropertyDefinition(name=p.name, type=p.type.value) for p in schema.properties],
    )


class MappingService:
    """Service for mapping business operations."""

    def __init__(
        self,
        mapping_repo: MappingRepository,
        snapshot_repo: SnapshotRepository,
        favorites_repo: FavoritesRepository,
        instance_repo: "InstanceRepository | None" = None,
    ):
        """Initialize service with repositories.

        Args:
            mapping_repo: Mapping repository
            snapshot_repo: Snapshot repository (for dependency checks)
            favorites_repo: Favorites repository (for cascade delete)
            instance_repo: Instance repository (optional, for tree endpoint)
        """
        self._mapping_repo = mapping_repo
        self._snapshot_repo = snapshot_repo
        self._favorites_repo = favorites_repo
        self._instance_repo = instance_repo

    async def get_mapping(self, mapping_id: int) -> Mapping:
        """Get a mapping by ID.

        Args:
            mapping_id: Mapping ID

        Returns:
            Mapping domain object

        Raises:
            NotFoundError: If mapping not found
        """
        mapping = await self._mapping_repo.get_by_id(mapping_id)
        if mapping is None:
            raise NotFoundError("Mapping", mapping_id)
        return mapping

    async def get_tree(
        self,
        mapping_id: int,
        include_instances: bool = True,
        status_filter: str | None = None,
    ) -> dict:
        """Get resource hierarchy tree for a mapping.

        Returns mapping → versions → snapshots → instances hierarchy.

        Args:
            mapping_id: Mapping ID
            include_instances: Whether to include instance details
            status_filter: Filter snapshots by status

        Returns:
            Tree structure with versions, snapshots, and instances

        Raises:
            NotFoundError: If mapping not found
        """
        from graph_olap_schemas import (
            MappingTreeInstanceItem,
            MappingTreeResponse,
            MappingTreeSnapshotItem,
            MappingTreeTotals,
            MappingTreeVersionItem,
        )

        # Get mapping
        mapping = await self.get_mapping(mapping_id)

        # Get all versions for this mapping
        versions = await self._mapping_repo.list_versions(mapping_id)

        # Build version tree
        version_items = []
        total_snapshots = 0
        total_instances = 0

        for version in sorted(versions, key=lambda v: v.version, reverse=True):
            # Get snapshots for this version
            from control_plane.repositories.snapshots import SnapshotFilters, SnapshotStatus

            # Build filter with status if requested
            status_enum = SnapshotStatus(status_filter) if status_filter else None
            filters = SnapshotFilters(
                mapping_id=mapping_id,
                mapping_version=version.version,
                status=status_enum,
            )
            snapshots, _ = await self._snapshot_repo.list_snapshots(
                filters=filters,
                limit=1000,  # Get all snapshots for this version
            )

            # Build snapshot items
            snapshot_items = []
            for snapshot in sorted(snapshots, key=lambda s: s.created_at or "", reverse=True):
                instances = []
                instance_count = 0

                if include_instances:
                    # Get instances for this snapshot
                    filters = InstanceFilters(snapshot_id=snapshot.id)
                    snapshot_instances, _ = await self._instance_repo.list_instances(filters)
                    instance_count = len(snapshot_instances)
                    instances = [
                        MappingTreeInstanceItem(
                            id=inst.id,
                            name=inst.name,
                            status=inst.status.value,
                        )
                        for inst in sorted(snapshot_instances, key=lambda i: i.created_at or "", reverse=True)
                    ]

                snapshot_items.append(
                    MappingTreeSnapshotItem(
                        id=snapshot.id,
                        name=snapshot.name,
                        status=snapshot.status.value,
                        created_at=snapshot.created_at,
                        instance_count=instance_count,
                        instances=instances,
                    )
                )

            version_items.append(
                MappingTreeVersionItem(
                    version=version.version,
                    change_description=version.change_description,
                    created_at=version.created_at,
                    snapshot_count=len(snapshot_items),
                    snapshots=snapshot_items,
                )
            )

            total_snapshots += len(snapshot_items)
            if include_instances:
                for item in snapshot_items:
                    total_instances += item.instance_count

        response = MappingTreeResponse(
            id=mapping.id,
            name=mapping.name,
            owner_username=mapping.owner_username,
            current_version=mapping.current_version,
            versions=version_items,
            totals=MappingTreeTotals(
                version_count=len(version_items),
                snapshot_count=total_snapshots,
                instance_count=total_instances,
            ),
        )

        return response.model_dump()

    async def list_mappings(
        self,
        user: User,
        owner: str | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
        sort_field: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[list[Mapping], int]:
        """List mappings with filters.

        All users can see all mappings (no visibility restrictions).

        Args:
            user: Current user (for audit, not filtering)
            owner: Filter by owner username
            search: Search term for name/description
            limit: Maximum number of results
            offset: Number of results to skip
            sort_field: Field to sort by
            sort_order: Sort order (asc/desc)

        Returns:
            Tuple of (list of mappings, total count)
        """
        filters = MappingFilters(owner=owner, search=search)
        pagination = Pagination(offset=offset, limit=limit)
        sort = Sort(field=sort_field, order=sort_order)

        return await self._mapping_repo.list_mappings(filters, pagination, sort)

    async def create_mapping(
        self,
        user: User,
        request: CreateMappingRequest,
    ) -> Mapping:
        """Create a new mapping.

        The user becomes the owner of the mapping.

        Args:
            user: Current user (becomes owner)
            request: Creation request with mapping details

        Returns:
            Created Mapping
        """
        # Convert Pydantic schema definitions to domain dataclasses
        node_definitions = [schema_to_domain_node(nd) for nd in request.node_definitions]
        edge_definitions = [schema_to_domain_edge(ed) for ed in request.edge_definitions]

        return await self._mapping_repo.create(
            owner_username=user.username,
            name=request.name,
            description=request.description,
            node_definitions=node_definitions,
            edge_definitions=edge_definitions,
            ttl=request.ttl,
            inactivity_timeout=request.inactivity_timeout,
        )

    async def update_mapping(
        self,
        user: User,
        mapping_id: int,
        request: UpdateMappingRequest,
    ) -> Mapping:
        """Update an existing mapping.

        Creates a new version if node/edge definitions change.

        Args:
            user: Current user
            mapping_id: Mapping ID to update
            request: Update request

        Returns:
            Updated Mapping

        Raises:
            NotFoundError: If mapping not found
            PermissionDeniedError: If user cannot modify mapping
        """
        # Get existing mapping
        mapping = await self.get_mapping(mapping_id)

        # Check permission
        check_ownership(user, mapping.owner_username, "Mapping", mapping_id)

        # Convert Pydantic schema definitions to domain dataclasses if provided
        node_definitions = None
        if request.node_definitions is not None:
            node_definitions = [schema_to_domain_node(nd) for nd in request.node_definitions]

        edge_definitions = None
        if request.edge_definitions is not None:
            edge_definitions = [schema_to_domain_edge(ed) for ed in request.edge_definitions]

        updated = await self._mapping_repo.update(
            mapping_id=mapping_id,
            updated_by=user.username,
            name=request.name,
            description=request.description,
            node_definitions=node_definitions,
            edge_definitions=edge_definitions,
            change_description=request.change_description,
            ttl=request.ttl,
            inactivity_timeout=request.inactivity_timeout,
        )

        if updated is None:
            raise NotFoundError("Mapping", mapping_id)

        return updated

    async def delete_mapping(
        self,
        user: User,
        mapping_id: int,
    ) -> None:
        """Delete a mapping.

        Cannot delete if snapshots exist.

        Args:
            user: Current user
            mapping_id: Mapping ID to delete

        Raises:
            NotFoundError: If mapping not found
            PermissionDeniedError: If user cannot delete mapping
            DependencyError: If mapping has snapshots
        """
        # Get existing mapping
        mapping = await self.get_mapping(mapping_id)

        # Check permission
        check_ownership(user, mapping.owner_username, "Mapping", mapping_id)

        # Check for dependencies
        snapshot_count = await self._mapping_repo.get_snapshot_count(mapping_id)
        if snapshot_count > 0:
            raise DependencyError("Mapping", mapping_id, "snapshot", snapshot_count)

        # CASCADE: Delete all favorites referencing this mapping (before delete commits)
        deleted_favorites = await self._favorites_repo.remove_for_resource(
            resource_type="mapping",
            resource_id=mapping_id,
        )

        if deleted_favorites > 0:
            logger.info(
                "Cascade deleted favorites for deleted mapping",
                mapping_id=mapping_id,
                favorites_deleted=deleted_favorites,
            )

        # Delete mapping (versions cascade) - commits transaction
        await self._mapping_repo.delete(mapping_id)

    async def get_version(
        self,
        mapping_id: int,
        version: int,
    ) -> MappingVersion:
        """Get a specific mapping version.

        Args:
            mapping_id: Mapping ID
            version: Version number

        Returns:
            MappingVersion domain object

        Raises:
            NotFoundError: If mapping or version not found
        """
        # Verify mapping exists
        await self.get_mapping(mapping_id)

        mapping_version = await self._mapping_repo.get_version(mapping_id, version)
        if mapping_version is None:
            raise NotFoundError("MappingVersion", f"{mapping_id}/v{version}")

        return mapping_version

    async def list_versions(self, mapping_id: int) -> list[MappingVersion]:
        """List all versions for a mapping.

        Args:
            mapping_id: Mapping ID

        Returns:
            List of MappingVersion objects

        Raises:
            NotFoundError: If mapping not found
        """
        # Verify mapping exists
        await self.get_mapping(mapping_id)

        return await self._mapping_repo.list_versions(mapping_id)

    async def get_version_diff(
        self,
        mapping_id: int,
        from_version: int,
        to_version: int,
    ) -> "MappingDiffResult":
        """Compare two versions of a mapping.

        Args:
            mapping_id: Mapping ID
            from_version: Starting version number
            to_version: Ending version number

        Returns:
            MappingDiffResult with summary counts and detailed changes

        Raises:
            NotFoundError: If mapping or versions not found
            ValueError: If from_version == to_version
        """
        from control_plane.utils.diff import diff_mapping_versions

        # Validate version numbers
        if from_version == to_version:
            raise ValueError("Cannot diff a version with itself")

        # Fetch both versions (get_version checks mapping exists)
        v1 = await self.get_version(mapping_id, from_version)
        v2 = await self.get_version(mapping_id, to_version)

        # Compute diff
        return diff_mapping_versions(v1, v2)

    async def copy_mapping(
        self,
        user: User,
        source_mapping_id: int,
        new_name: str,
        new_description: str | None = None,
    ) -> Mapping:
        """Create a copy of an existing mapping.

        The current user becomes the owner of the copy.

        Args:
            user: Current user (becomes owner)
            source_mapping_id: ID of mapping to copy
            new_name: Name for the copy
            new_description: Optional description for the copy

        Returns:
            New Mapping (copy)

        Raises:
            NotFoundError: If source mapping not found
        """
        # Get source mapping
        source = await self.get_mapping(source_mapping_id)

        # Create copy with current user as owner
        return await self._mapping_repo.create(
            owner_username=user.username,
            name=new_name,
            description=new_description or source.description,
            node_definitions=source.node_definitions,
            edge_definitions=source.edge_definitions,
            ttl=source.ttl,
            inactivity_timeout=source.inactivity_timeout,
        )
