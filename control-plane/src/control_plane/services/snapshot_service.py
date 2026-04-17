"""Snapshot service with business logic."""

from typing import Any

import structlog

from control_plane.clients.gcs import GCSClient
from control_plane.models import (
    InvalidStateError,
    Mapping,
    NotFoundError,
    PermissionDeniedError,
    Snapshot,
    SnapshotStatus,
    User,
    UserRole,
)
from control_plane.models.requests import (
    CreateSnapshotRequest,
    UpdateLifecycleRequest,
    UpdateSnapshotRequest,
)
from control_plane.repositories.config import GlobalConfigRepository
from control_plane.repositories.export_jobs import ExportJobRepository
from control_plane.repositories.favorites import FavoritesRepository
from control_plane.repositories.mappings import MappingRepository
from control_plane.repositories.snapshots import SnapshotFilters, SnapshotRepository

logger = structlog.get_logger()


def check_ownership(
    user: User,
    resource_owner: str,
    resource_type: str,
    resource_id: int,
) -> None:
    """Check if user can modify a resource."""
    if user.role in (UserRole.ADMIN, UserRole.OPS):
        return
    if user.username != resource_owner:
        raise PermissionDeniedError(resource_type, resource_id)


class SnapshotService:
    """Service for snapshot business operations."""

    DEFAULT_GCS_BUCKET = "graph-exports"

    def __init__(
        self,
        snapshot_repo: SnapshotRepository,
        mapping_repo: MappingRepository,
        export_job_repo: ExportJobRepository,
        config_repo: GlobalConfigRepository,
        favorites_repo: FavoritesRepository,
        gcs_client: GCSClient | None = None,
        gcs_bucket: str | None = None,
        starburst_catalog: str = "hsbc-244552-hkibishk-dev",
    ):
        """Initialize service with repositories.

        Args:
            snapshot_repo: Snapshot repository
            mapping_repo: Mapping repository
            export_job_repo: Export job repository
            config_repo: Global config repository
            favorites_repo: Favorites repository (for cascade delete)
            gcs_client: GCS client for file cleanup (optional for testing)
            gcs_bucket: GCS bucket name for exports (defaults to graph-exports)
            starburst_catalog: Starburst catalog name for export queries
        """
        self._snapshot_repo = snapshot_repo
        self._mapping_repo = mapping_repo
        self._export_job_repo = export_job_repo
        self._config_repo = config_repo
        self._favorites_repo = favorites_repo
        self._gcs_client = gcs_client
        self._gcs_bucket = gcs_bucket or self.DEFAULT_GCS_BUCKET
        self._starburst_catalog = starburst_catalog
        self._logger = logger.bind(component="snapshot_service")

    async def get_snapshot(self, snapshot_id: int) -> Snapshot:
        """Get a snapshot by ID.

        Args:
            snapshot_id: Snapshot ID

        Returns:
            Snapshot domain object

        Raises:
            NotFoundError: If snapshot not found
        """
        snapshot = await self._snapshot_repo.get_by_id(snapshot_id)
        if snapshot is None:
            raise NotFoundError("Snapshot", snapshot_id)
        return snapshot

    async def get_mapping(self, mapping_id: int) -> "Mapping":
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

    async def list_snapshots(
        self,
        user: User,
        owner: str | None = None,
        mapping_id: int | None = None,
        status: SnapshotStatus | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
        sort_field: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[list[Snapshot], int]:
        """List snapshots with filters.

        Args:
            user: Current user
            owner: Filter by owner username
            mapping_id: Filter by mapping ID
            status: Filter by status
            search: Search term for name/description
            limit: Maximum number of results
            offset: Number of results to skip
            sort_field: Field to sort by
            sort_order: Sort order (asc/desc)

        Returns:
            Tuple of (list of snapshots, total count)
        """
        filters = SnapshotFilters(
            owner=owner,
            mapping_id=mapping_id,
            status=status,
            search=search,
        )

        return await self._snapshot_repo.list_snapshots(
            filters=filters,
            limit=limit,
            offset=offset,
            sort_field=sort_field,
            sort_order=sort_order,
        )

    async def create_snapshot(
        self,
        user: User,
        request: CreateSnapshotRequest,
        starburst_catalog: str | None = None,
        starburst_role: str | None = None,
    ) -> Snapshot:
        """Create a new snapshot from a mapping.

        Creates export jobs for each node and edge definition with denormalized
        SQL and column names (ADR-025 database polling architecture).

        Args:
            user: Current user (becomes owner)
            request: Creation request
            starburst_catalog: Starburst catalog name for queries (uses service default if not specified)

        Returns:
            Created Snapshot with status='pending'

        Raises:
            NotFoundError: If mapping not found
        """
        # Verify mapping exists
        mapping = await self._mapping_repo.get_by_id(request.mapping_id)
        if mapping is None:
            raise NotFoundError("Mapping", request.mapping_id)

        # Use specified version or current version
        mapping_version = request.mapping_version or mapping.current_version

        # Verify version exists
        version = await self._mapping_repo.get_version(request.mapping_id, mapping_version)
        if version is None:
            raise NotFoundError("MappingVersion", f"{request.mapping_id}/v{mapping_version}")

        # Get default TTL if not specified
        ttl = request.ttl
        inactivity_timeout = request.inactivity_timeout

        if ttl is None or inactivity_timeout is None:
            lifecycle_config = await self._config_repo.get_lifecycle_config("snapshot")
            if ttl is None:
                ttl = lifecycle_config.get("default_ttl")
            if inactivity_timeout is None:
                inactivity_timeout = lifecycle_config.get("default_inactivity")

        # Build export path prefix (snapshot_id added after creation)
        # Path structure: gs://bucket/{owner}/{mapping_id}/v{version}/{snapshot_id}/
        gcs_path_prefix = (
            f"gs://{self._gcs_bucket}/{user.username}/{request.mapping_id}"
            f"/v{mapping_version}"
        )

        # Create snapshot with placeholder path (updated after we get the ID)
        snapshot = await self._snapshot_repo.create(
            mapping_id=request.mapping_id,
            mapping_version=mapping_version,
            owner_username=user.username,
            name=request.name,
            description=request.description,
            gcs_path=f"{gcs_path_prefix}/pending/",  # Placeholder
            ttl=ttl,
            inactivity_timeout=inactivity_timeout,
        )

        # Build final GCS path with snapshot ID
        gcs_path = f"{gcs_path_prefix}/{snapshot.id}/"

        # Update snapshot with correct GCS path
        snapshot = await self._snapshot_repo.update_gcs_path(snapshot.id, gcs_path)

        # Create export jobs for each node and edge (ADR-025: with denormalized fields)
        jobs = []
        effective_catalog = starburst_catalog or self._starburst_catalog

        for node_def in version.node_definitions:
            # Build column names: primary key first, then properties
            column_names = [node_def.primary_key.name] + [
                p.name for p in node_def.properties
            ]
            jobs.append(
                {
                    "job_type": "node",
                    "entity_name": node_def.label,
                    "gcs_path": f"{gcs_path}nodes/{node_def.label}/",
                    # ADR-025: Denormalized fields for stateless processing
                    "sql": node_def.sql,
                    "column_names": column_names,
                    "starburst_catalog": effective_catalog,
                    "starburst_role": starburst_role,
                }
            )

        for edge_def in version.edge_definitions:
            # Build column names: from_key, to_key, then properties
            column_names = [edge_def.from_key, edge_def.to_key] + [
                p.name for p in edge_def.properties
            ]
            jobs.append(
                {
                    "job_type": "edge",
                    "entity_name": edge_def.type,
                    "gcs_path": f"{gcs_path}edges/{edge_def.type}/",
                    # ADR-025: Denormalized fields for stateless processing
                    "sql": edge_def.sql,
                    "column_names": column_names,
                    "starburst_catalog": effective_catalog,
                    "starburst_role": starburst_role,
                }
            )

        if jobs:
            await self._export_job_repo.create_batch(snapshot.id, jobs)

        return snapshot

    async def update_status(
        self,
        snapshot_id: int,
        status: SnapshotStatus,
        error_message: str | None = None,
        progress: dict[str, Any] | None = None,
        node_counts: dict[str, int] | None = None,
        edge_counts: dict[str, int] | None = None,
        size_bytes: int | None = None,
    ) -> Snapshot:
        """Update snapshot status (internal API).

        Args:
            snapshot_id: Snapshot ID
            status: New status
            error_message: Error message (for failed status)
            progress: Progress information
            node_counts: Node counts by label
            edge_counts: Edge counts by type
            size_bytes: Total storage size

        Returns:
            Updated Snapshot

        Raises:
            NotFoundError: If snapshot not found
        """
        snapshot = await self._snapshot_repo.update_status(
            snapshot_id=snapshot_id,
            status=status,
            error_message=error_message,
            progress=progress,
            node_counts=node_counts,
            edge_counts=edge_counts,
            size_bytes=size_bytes,
        )

        if snapshot is None:
            raise NotFoundError("Snapshot", snapshot_id)

        return snapshot

    async def delete_snapshot(
        self,
        user: User,
        snapshot_id: int,
    ) -> None:
        """Delete a snapshot.

        NOTE: This method is currently NOT wired to any HTTP endpoint
        (see routers/api/snapshots.py — DELETE is commented out). Snapshot
        cleanup in production goes through instance_service.delete_instance
        cascade, which uses InstanceRepository.count_instances_referencing_snapshot
        as the single source of truth for "is this snapshot still in use".

        If this endpoint is re-enabled, the caller MUST inject an
        InstanceRepository and perform the same reference check before
        deleting — otherwise it will create dangling instance rows.

        Deletes GCS files before deleting database record.

        Args:
            user: Current user
            snapshot_id: Snapshot ID to delete

        Raises:
            NotFoundError: If snapshot not found
            PermissionDeniedError: If user cannot delete snapshot
        """
        # Get existing snapshot
        snapshot = await self.get_snapshot(snapshot_id)

        # Check permission
        check_ownership(user, snapshot.owner_username, "Snapshot", snapshot_id)

        # Delete GCS files if client is configured
        if self._gcs_client and snapshot.gcs_path:
            try:
                files_deleted, bytes_deleted = self._gcs_client.delete_path(snapshot.gcs_path)
                self._logger.info(
                    "Deleted snapshot GCS files",
                    snapshot_id=snapshot_id,
                    gcs_path=snapshot.gcs_path,
                    files_deleted=files_deleted,
                    bytes_deleted=bytes_deleted,
                )
            except Exception as e:
                # Log error but continue with DB deletion
                # We don't want to block snapshot deletion if GCS cleanup fails
                self._logger.error(
                    "Failed to delete snapshot GCS files",
                    snapshot_id=snapshot_id,
                    gcs_path=snapshot.gcs_path,
                    error=str(e),
                )
                # Increment GCS cleanup failure metric
                from control_plane.jobs import metrics
                metrics.snapshot_gcs_cleanup_failures_total.inc()

        # CASCADE: Delete all favorites referencing this snapshot (before delete commits)
        deleted_favorites = await self._favorites_repo.remove_for_resource(
            resource_type="snapshot",
            resource_id=snapshot_id,
        )

        if deleted_favorites > 0:
            self._logger.info(
                "Cascade deleted favorites for deleted snapshot",
                snapshot_id=snapshot_id,
                favorites_deleted=deleted_favorites,
            )

        # Delete snapshot (export jobs cascade) - commits transaction
        await self._snapshot_repo.delete(snapshot_id)

    async def retry_failed(
        self,
        user: User,
        snapshot_id: int,
    ) -> Snapshot:
        """Retry a failed snapshot export.

        Resets status to pending and clears error.

        Args:
            user: Current user
            snapshot_id: Snapshot ID to retry

        Returns:
            Updated Snapshot

        Raises:
            NotFoundError: If snapshot not found
            PermissionDeniedError: If user cannot modify snapshot
            InvalidStateError: If snapshot is not in failed state
        """
        # Get existing snapshot
        snapshot = await self.get_snapshot(snapshot_id)

        # Check permission
        check_ownership(user, snapshot.owner_username, "Snapshot", snapshot_id)

        # Check state
        if snapshot.status != SnapshotStatus.FAILED:
            raise InvalidStateError("Snapshot", snapshot_id, snapshot.status.value, "failed")

        # Reset to pending
        updated = await self._snapshot_repo.update_status(
            snapshot_id=snapshot_id,
            status=SnapshotStatus.PENDING,
            error_message=None,
            progress=None,
        )

        if updated is None:
            raise NotFoundError("Snapshot", snapshot_id)

        return updated

    async def get_progress(self, snapshot_id: int) -> dict[str, Any]:
        """Get detailed export progress for a snapshot.

        Args:
            snapshot_id: Snapshot ID

        Returns:
            Progress dictionary with job details

        Raises:
            NotFoundError: If snapshot not found
        """
        # Verify snapshot exists
        await self.get_snapshot(snapshot_id)

        # Get aggregated progress from export jobs
        progress = await self._export_job_repo.get_snapshot_progress(snapshot_id)

        # Get individual job status
        jobs = await self._export_job_repo.list_by_snapshot(snapshot_id)
        job_details = [
            {
                "name": job.entity_name,
                "type": job.job_type,
                "status": job.status.value,
                "row_count": job.row_count,
            }
            for job in jobs
        ]
        progress["jobs"] = job_details

        return progress

    async def update_snapshot(
        self,
        user: User,
        snapshot_id: int,
        request: UpdateSnapshotRequest,
    ) -> Snapshot:
        """Update snapshot metadata.

        Args:
            user: Current user
            snapshot_id: Snapshot ID to update
            request: Update request with new values

        Returns:
            Updated Snapshot

        Raises:
            NotFoundError: If snapshot not found
            PermissionDeniedError: If user cannot modify snapshot
        """
        # Get existing snapshot
        snapshot = await self.get_snapshot(snapshot_id)

        # Check permission
        check_ownership(user, snapshot.owner_username, "Snapshot", snapshot_id)

        # Update metadata
        updated = await self._snapshot_repo.update_metadata(
            snapshot_id=snapshot_id,
            name=request.name,
            description=request.description,
        )

        if updated is None:
            raise NotFoundError("Snapshot", snapshot_id)

        return updated

    async def update_lifecycle(
        self,
        user: User,
        snapshot_id: int,
        request: UpdateLifecycleRequest,
    ) -> Snapshot:
        """Update snapshot lifecycle settings.

        Args:
            user: Current user
            snapshot_id: Snapshot ID to update
            request: Lifecycle update request

        Returns:
            Updated Snapshot

        Raises:
            NotFoundError: If snapshot not found
            PermissionDeniedError: If user cannot modify snapshot
        """
        # Get existing snapshot
        snapshot = await self.get_snapshot(snapshot_id)

        # Check permission
        check_ownership(user, snapshot.owner_username, "Snapshot", snapshot_id)

        # Update lifecycle
        updated = await self._snapshot_repo.update_lifecycle(
            snapshot_id=snapshot_id,
            ttl=request.ttl,
            inactivity_timeout=request.inactivity_timeout,
        )

        if updated is None:
            raise NotFoundError("Snapshot", snapshot_id)

        return updated
