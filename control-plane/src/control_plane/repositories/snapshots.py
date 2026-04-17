"""Snapshot repository for database operations."""

from dataclasses import dataclass
from typing import Any

from control_plane.models import Snapshot, SnapshotStatus
from control_plane.repositories.base import (
    BaseRepository,
    deserialize_json,
    parse_timestamp,
    serialize_json,
    utc_now,
)


@dataclass
class SnapshotFilters:
    """Filters for listing snapshots."""

    owner: str | None = None
    mapping_id: int | None = None
    mapping_version: int | None = None
    status: SnapshotStatus | None = None
    search: str | None = None


class SnapshotRepository(BaseRepository):
    """Repository for snapshot database operations."""

    async def get_by_id(self, snapshot_id: int) -> Snapshot | None:
        """Get snapshot by ID.

        Args:
            snapshot_id: Snapshot ID

        Returns:
            Snapshot domain object or None if not found
        """
        sql = """
            SELECT id, mapping_id, mapping_version, owner_username,
                   name, description, gcs_path, size_bytes,
                   node_counts, edge_counts, status, progress,
                   error_message, created_at, updated_at,
                   ttl, inactivity_timeout, last_used_at
            FROM snapshots
            WHERE id = :snapshot_id
        """
        row = await self._fetch_one(sql, {"snapshot_id": snapshot_id})
        if row is None:
            return None
        return self._row_to_snapshot(row)

    async def list_snapshots(
        self,
        filters: SnapshotFilters,
        limit: int = 50,
        offset: int = 0,
        sort_field: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[list[Snapshot], int]:
        """List snapshots with filters and pagination.

        Args:
            filters: Filter criteria
            limit: Maximum number of results
            offset: Number of results to skip
            sort_field: Field to sort by
            sort_order: Sort order (asc/desc)

        Returns:
            Tuple of (list of Snapshot objects, total count)
        """
        conditions = []
        params: dict[str, Any] = {"limit": limit, "offset": offset}

        if filters.owner:
            conditions.append("owner_username = :owner")
            params["owner"] = filters.owner

        if filters.mapping_id:
            conditions.append("mapping_id = :mapping_id")
            params["mapping_id"] = filters.mapping_id

        if filters.mapping_version:
            conditions.append("mapping_version = :mapping_version")
            params["mapping_version"] = filters.mapping_version

        if filters.status:
            conditions.append("status = :status")
            params["status"] = filters.status.value

        if filters.search:
            conditions.append("(name LIKE :search OR description LIKE :search)")
            params["search"] = f"%{filters.search}%"

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        # Validate sort field
        allowed_sort_fields = {"created_at", "updated_at", "name", "size_bytes"}
        sort_field = sort_field if sort_field in allowed_sort_fields else "created_at"
        sort_order = "ASC" if sort_order.lower() == "asc" else "DESC"

        # Get total count
        count_sql = f"SELECT COUNT(*) FROM snapshots WHERE {where_clause}"
        total = await self._fetch_scalar(count_sql, params)

        # Get paginated results
        sql = f"""
            SELECT id, mapping_id, mapping_version, owner_username,
                   name, description, gcs_path, size_bytes,
                   node_counts, edge_counts, status, progress,
                   error_message, created_at, updated_at,
                   ttl, inactivity_timeout, last_used_at
            FROM snapshots
            WHERE {where_clause}
            ORDER BY {sort_field} {sort_order}
            LIMIT :limit OFFSET :offset
        """
        rows = await self._fetch_all(sql, params)
        snapshots = [self._row_to_snapshot(row) for row in rows]

        return snapshots, total

    async def create(
        self,
        mapping_id: int,
        mapping_version: int,
        owner_username: str,
        name: str,
        description: str | None,
        gcs_path: str,
        ttl: str | None = None,
        inactivity_timeout: str | None = None,
    ) -> Snapshot:
        """Create a new snapshot.

        Args:
            mapping_id: ID of the source mapping
            mapping_version: Version of the mapping used
            owner_username: Username of the owner
            name: Snapshot name
            description: Optional description
            gcs_path: GCS storage path
            ttl: Optional TTL duration (ISO 8601)
            inactivity_timeout: Optional inactivity timeout (ISO 8601)

        Returns:
            Created Snapshot
        """
        now = utc_now()
        sql = """
            INSERT INTO snapshots (mapping_id, mapping_version, owner_username,
                                  name, description, gcs_path, status,
                                  created_at, updated_at, ttl, inactivity_timeout)
            VALUES (:mapping_id, :mapping_version, :owner_username,
                    :name, :description, :gcs_path, 'pending',
                    :created_at, :updated_at, :ttl, :inactivity_timeout)
            RETURNING id
        """
        snapshot_id = await self._insert_returning_id(
            sql,
            {
                "mapping_id": mapping_id,
                "mapping_version": mapping_version,
                "owner_username": owner_username,
                "name": name,
                "description": description,
                "gcs_path": gcs_path,
                "created_at": now,
                "updated_at": now,
                "ttl": ttl,
                "inactivity_timeout": inactivity_timeout,
            },
        )

        return Snapshot(
            id=snapshot_id,
            mapping_id=mapping_id,
            mapping_version=mapping_version,
            owner_username=owner_username,
            name=name,
            description=description,
            gcs_path=gcs_path,
            status=SnapshotStatus.PENDING,
            created_at=parse_timestamp(now),
            updated_at=parse_timestamp(now),
            ttl=ttl,
            inactivity_timeout=inactivity_timeout,
        )

    async def update_status(
        self,
        snapshot_id: int,
        status: SnapshotStatus,
        error_message: str | None = None,
        progress: dict[str, Any] | None = None,
        node_counts: dict[str, int] | None = None,
        edge_counts: dict[str, int] | None = None,
        size_bytes: int | None = None,
    ) -> Snapshot | None:
        """Update snapshot status and related fields.

        Args:
            snapshot_id: Snapshot ID
            status: New status
            error_message: Error message (for failed status)
            progress: Progress information
            node_counts: Node counts by label
            edge_counts: Edge counts by type
            size_bytes: Total storage size

        Returns:
            Updated Snapshot or None if not found
        """
        now = utc_now()
        sql = """
            UPDATE snapshots
            SET status = :status,
                error_message = COALESCE(:error_message, error_message),
                progress = COALESCE(:progress, progress),
                node_counts = COALESCE(:node_counts, node_counts),
                edge_counts = COALESCE(:edge_counts, edge_counts),
                size_bytes = COALESCE(:size_bytes, size_bytes),
                updated_at = :updated_at
            WHERE id = :snapshot_id
        """
        result = await self._execute(
            sql,
            {
                "snapshot_id": snapshot_id,
                "status": status.value,
                "error_message": error_message,
                "progress": serialize_json(progress),
                "node_counts": serialize_json(node_counts),
                "edge_counts": serialize_json(edge_counts),
                "size_bytes": size_bytes,
                "updated_at": now,
            },
        )
        if result.rowcount == 0:
            return None

        return await self.get_by_id(snapshot_id)

    async def update_last_used(self, snapshot_id: int) -> None:
        """Update snapshot's last_used_at timestamp.

        Args:
            snapshot_id: Snapshot ID
        """
        now = utc_now()
        sql = """
            UPDATE snapshots
            SET last_used_at = :last_used_at,
                updated_at = :updated_at
            WHERE id = :snapshot_id
        """
        await self._execute(
            sql,
            {
                "snapshot_id": snapshot_id,
                "last_used_at": now,
                "updated_at": now,
            },
        )

    async def delete(self, snapshot_id: int) -> bool:
        """Delete a snapshot.

        Args:
            snapshot_id: Snapshot ID to delete

        Returns:
            True if snapshot was deleted
        """
        sql = "DELETE FROM snapshots WHERE id = :snapshot_id"
        result = await self._execute(sql, {"snapshot_id": snapshot_id})
        return result.rowcount > 0

    async def exists(self, snapshot_id: int) -> bool:
        """Check if snapshot exists.

        Args:
            snapshot_id: Snapshot ID

        Returns:
            True if snapshot exists
        """
        sql = "SELECT 1 FROM snapshots WHERE id = :snapshot_id"
        row = await self._fetch_one(sql, {"snapshot_id": snapshot_id})
        return row is not None

    async def update_metadata(
        self,
        snapshot_id: int,
        name: str | None = None,
        description: str | None = None,
    ) -> Snapshot | None:
        """Update snapshot metadata (name, description).

        Args:
            snapshot_id: Snapshot ID
            name: New name (optional)
            description: New description (optional)

        Returns:
            Updated Snapshot or None if not found
        """
        now = utc_now()
        sql = """
            UPDATE snapshots
            SET name = COALESCE(:name, name),
                description = COALESCE(:description, description),
                updated_at = :updated_at
            WHERE id = :snapshot_id
        """
        result = await self._execute(
            sql,
            {
                "snapshot_id": snapshot_id,
                "name": name,
                "description": description,
                "updated_at": now,
            },
        )
        if result.rowcount == 0:
            return None
        return await self.get_by_id(snapshot_id)

    async def update_lifecycle(
        self,
        snapshot_id: int,
        ttl: str | None = None,
        inactivity_timeout: str | None = None,
    ) -> Snapshot | None:
        """Update snapshot lifecycle settings.

        Args:
            snapshot_id: Snapshot ID
            ttl: New TTL duration (ISO 8601)
            inactivity_timeout: New inactivity timeout (ISO 8601)

        Returns:
            Updated Snapshot or None if not found
        """
        now = utc_now()
        sql = """
            UPDATE snapshots
            SET ttl = COALESCE(:ttl, ttl),
                inactivity_timeout = COALESCE(:inactivity_timeout, inactivity_timeout),
                updated_at = :updated_at
            WHERE id = :snapshot_id
        """
        result = await self._execute(
            sql,
            {
                "snapshot_id": snapshot_id,
                "ttl": ttl,
                "inactivity_timeout": inactivity_timeout,
                "updated_at": now,
            },
        )
        if result.rowcount == 0:
            return None
        return await self.get_by_id(snapshot_id)

    async def update_gcs_path(
        self,
        snapshot_id: int,
        gcs_path: str,
    ) -> Snapshot | None:
        """Update snapshot GCS path.

        Called after snapshot creation to set the final path including snapshot_id.

        Args:
            snapshot_id: Snapshot ID
            gcs_path: Full GCS path (e.g., gs://bucket/{user}/{mapping}/v{version}/{snapshot}/)

        Returns:
            Updated Snapshot or None if not found
        """
        now = utc_now()
        sql = """
            UPDATE snapshots
            SET gcs_path = :gcs_path,
                updated_at = :updated_at
            WHERE id = :snapshot_id
        """
        result = await self._execute(
            sql,
            {
                "snapshot_id": snapshot_id,
                "gcs_path": gcs_path,
                "updated_at": now,
            },
        )
        if result.rowcount == 0:
            return None
        return await self.get_by_id(snapshot_id)

    async def find_ready_snapshot(
        self, mapping_id: int, mapping_version: int
    ) -> Snapshot | None:
        """Find an existing READY snapshot for a mapping version.

        Uses FOR UPDATE SKIP LOCKED to prevent TOCTOU race conditions
        when multiple concurrent requests try to create instances from
        the same mapping.

        Args:
            mapping_id: ID of the source mapping
            mapping_version: Version of the mapping

        Returns:
            The most recent READY snapshot, or None if no ready snapshot exists.
        """
        sql = """
            SELECT id, mapping_id, mapping_version, owner_username,
                   name, description, gcs_path, size_bytes,
                   node_counts, edge_counts, status, progress,
                   error_message, created_at, updated_at,
                   ttl, inactivity_timeout, last_used_at
            FROM snapshots
            WHERE mapping_id = :mapping_id
              AND mapping_version = :mapping_version
              AND status = 'ready'
            ORDER BY created_at DESC
            LIMIT 1
            FOR UPDATE SKIP LOCKED
        """
        row = await self._fetch_one(
            sql, {"mapping_id": mapping_id, "mapping_version": mapping_version}
        )
        if row is None:
            return None
        return self._row_to_snapshot(row)

    async def find_expired(self, limit: int = 100) -> list[Snapshot]:
        """Find snapshots that have exceeded their TTL.

        Args:
            limit: Maximum number to return

        Returns:
            List of expired snapshots
        """
        utc_now()
        # This is a simplified query; actual duration parsing would need
        # to be done in application code or with database-specific functions
        sql = """
            SELECT id, mapping_id, mapping_version, owner_username,
                   name, description, gcs_path, size_bytes,
                   node_counts, edge_counts, status, progress,
                   error_message, created_at, updated_at,
                   ttl, inactivity_timeout, last_used_at
            FROM snapshots
            WHERE ttl IS NOT NULL
              AND status = 'ready'
            LIMIT :limit
        """
        rows = await self._fetch_all(sql, {"limit": limit})
        return [self._row_to_snapshot(row) for row in rows]

    async def find_inactive(self, limit: int = 100) -> list[Snapshot]:
        """Find snapshots that have exceeded their inactivity timeout.

        Args:
            limit: Maximum number to return

        Returns:
            List of inactive snapshots
        """
        sql = """
            SELECT id, mapping_id, mapping_version, owner_username,
                   name, description, gcs_path, size_bytes,
                   node_counts, edge_counts, status, progress,
                   error_message, created_at, updated_at,
                   ttl, inactivity_timeout, last_used_at
            FROM snapshots
            WHERE inactivity_timeout IS NOT NULL
              AND status = 'ready'
              AND last_used_at IS NOT NULL
            LIMIT :limit
        """
        rows = await self._fetch_all(sql, {"limit": limit})
        return [self._row_to_snapshot(row) for row in rows]

    async def list_all(self) -> list[Snapshot]:
        """List all snapshots without pagination.

        Used by background jobs for lifecycle enforcement and export reconciliation.

        Returns:
            List of all Snapshot objects
        """
        sql = """
            SELECT id, mapping_id, mapping_version, owner_username,
                   name, description, gcs_path, size_bytes,
                   node_counts, edge_counts, status, progress,
                   error_message, created_at, updated_at,
                   ttl, inactivity_timeout, last_used_at
            FROM snapshots
            ORDER BY created_at DESC
        """
        rows = await self._fetch_all(sql, {})
        return [self._row_to_snapshot(row) for row in rows]

    def _row_to_snapshot(self, row) -> Snapshot:
        """Convert database row to Snapshot domain object."""
        return Snapshot(
            id=row.id,
            mapping_id=row.mapping_id,
            mapping_version=row.mapping_version,
            owner_username=row.owner_username,
            name=row.name,
            description=row.description,
            gcs_path=row.gcs_path,
            status=SnapshotStatus(row.status),
            size_bytes=row.size_bytes,
            node_counts=deserialize_json(row.node_counts),
            edge_counts=deserialize_json(row.edge_counts),
            progress=deserialize_json(row.progress),
            error_message=row.error_message,
            created_at=parse_timestamp(row.created_at),
            updated_at=parse_timestamp(row.updated_at),
            ttl=row.ttl,
            inactivity_timeout=row.inactivity_timeout,
            last_used_at=parse_timestamp(row.last_used_at),
        )
