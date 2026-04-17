"""Mapping repository for database operations."""

from dataclasses import dataclass
from typing import Any

from control_plane.models import (
    EdgeDefinition,
    Mapping,
    MappingVersion,
    NodeDefinition,
)
from control_plane.repositories.base import (
    BaseRepository,
    deserialize_json,
    parse_timestamp,
    serialize_json,
    utc_now,
)


@dataclass
class MappingFilters:
    """Filters for listing mappings."""

    owner: str | None = None
    search: str | None = None


@dataclass
class Pagination:
    """Pagination parameters."""

    offset: int = 0
    limit: int = 50


@dataclass
class Sort:
    """Sort parameters."""

    field: str = "created_at"
    order: str = "desc"


class MappingRepository(BaseRepository):
    """Repository for mapping database operations."""

    async def get_by_id(self, mapping_id: int) -> Mapping | None:
        """Get mapping by ID with current version details.

        Args:
            mapping_id: Mapping ID

        Returns:
            Mapping domain object or None if not found
        """
        sql = """
            SELECT m.id, m.owner_username, m.name, m.description,
                   m.current_version, m.created_at, m.updated_at,
                   m.ttl, m.inactivity_timeout,
                   mv.node_definitions, mv.edge_definitions,
                   mv.change_description, mv.created_at as version_created_at,
                   mv.created_by as version_created_by
            FROM mappings m
            JOIN mapping_versions mv
                ON m.id = mv.mapping_id AND m.current_version = mv.version
            WHERE m.id = :mapping_id
        """
        row = await self._fetch_one(sql, {"mapping_id": mapping_id})
        if row is None:
            return None
        return self._row_to_mapping(row)

    async def list_mappings(
        self,
        filters: MappingFilters,
        pagination: Pagination,
        sort: Sort,
    ) -> tuple[list[Mapping], int]:
        """List mappings with filters and pagination.

        Args:
            filters: Filter criteria
            pagination: Pagination parameters
            sort: Sort parameters

        Returns:
            Tuple of (list of Mapping objects, total count)
        """
        conditions = []
        params: dict[str, Any] = {
            "limit": pagination.limit,
            "offset": pagination.offset,
        }

        if filters.owner:
            conditions.append("m.owner_username = :owner")
            params["owner"] = filters.owner

        if filters.search:
            conditions.append("(m.name LIKE :search OR m.description LIKE :search)")
            params["search"] = f"%{filters.search}%"

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        # Validate sort field to prevent SQL injection
        allowed_sort_fields = {"created_at", "updated_at", "name"}
        sort_field = sort.field if sort.field in allowed_sort_fields else "created_at"
        sort_order = "ASC" if sort.order.lower() == "asc" else "DESC"

        # Get total count
        count_sql = f"SELECT COUNT(*) FROM mappings m WHERE {where_clause}"
        total = await self._fetch_scalar(count_sql, params)

        # Get paginated results with version info
        sql = f"""
            SELECT m.id, m.owner_username, m.name, m.description,
                   m.current_version, m.created_at, m.updated_at,
                   m.ttl, m.inactivity_timeout,
                   mv.node_definitions, mv.edge_definitions,
                   mv.change_description, mv.created_at as version_created_at,
                   mv.created_by as version_created_by
            FROM mappings m
            JOIN mapping_versions mv
                ON m.id = mv.mapping_id AND m.current_version = mv.version
            WHERE {where_clause}
            ORDER BY m.{sort_field} {sort_order}
            LIMIT :limit OFFSET :offset
        """
        rows = await self._fetch_all(sql, params)
        mappings = [self._row_to_mapping(row) for row in rows]

        return mappings, total

    async def create(
        self,
        owner_username: str,
        name: str,
        description: str | None,
        node_definitions: list[NodeDefinition],
        edge_definitions: list[EdgeDefinition],
        ttl: str | None = None,
        inactivity_timeout: str | None = None,
    ) -> Mapping:
        """Create a new mapping with initial version.

        Args:
            owner_username: Username of the owner
            name: Mapping name
            description: Optional description
            node_definitions: List of node definitions
            edge_definitions: List of edge definitions
            ttl: Optional TTL duration (ISO 8601)
            inactivity_timeout: Optional inactivity timeout (ISO 8601)

        Returns:
            Created Mapping with version details
        """
        now = utc_now()

        # Insert mapping header
        mapping_sql = """
            INSERT INTO mappings (owner_username, name, description,
                                 current_version, created_at, updated_at,
                                 ttl, inactivity_timeout)
            VALUES (:owner_username, :name, :description,
                    1, :created_at, :updated_at,
                    :ttl, :inactivity_timeout)
            RETURNING id
        """
        mapping_id = await self._insert_returning_id(
            mapping_sql,
            {
                "owner_username": owner_username,
                "name": name,
                "description": description,
                "created_at": now,
                "updated_at": now,
                "ttl": ttl,
                "inactivity_timeout": inactivity_timeout,
            },
        )

        # Insert version 1
        version_sql = """
            INSERT INTO mapping_versions (mapping_id, version, change_description,
                                         node_definitions, edge_definitions,
                                         created_at, created_by)
            VALUES (:mapping_id, 1, NULL,
                    :node_definitions, :edge_definitions,
                    :created_at, :created_by)
        """
        await self._execute(
            version_sql,
            {
                "mapping_id": mapping_id,
                "node_definitions": serialize_json([nd.to_dict() for nd in node_definitions]),
                "edge_definitions": serialize_json([ed.to_dict() for ed in edge_definitions]),
                "created_at": now,
                "created_by": owner_username,
            },
        )

        return Mapping(
            id=mapping_id,
            owner_username=owner_username,
            name=name,
            description=description,
            current_version=1,
            created_at=parse_timestamp(now),
            updated_at=parse_timestamp(now),
            ttl=ttl,
            inactivity_timeout=inactivity_timeout,
            node_definitions=node_definitions,
            edge_definitions=edge_definitions,
            change_description=None,
            version_created_at=parse_timestamp(now),
            version_created_by=owner_username,
        )

    async def update(
        self,
        mapping_id: int,
        updated_by: str,
        name: str | None = None,
        description: str | None = None,
        node_definitions: list[NodeDefinition] | None = None,
        edge_definitions: list[EdgeDefinition] | None = None,
        change_description: str | None = None,
        ttl: str | None = None,
        inactivity_timeout: str | None = None,
    ) -> Mapping | None:
        """Update a mapping, creating a new version if definitions change.

        Args:
            mapping_id: Mapping ID to update
            updated_by: Username making the update
            name: New name (optional)
            description: New description (optional)
            node_definitions: New node definitions (optional, creates new version)
            edge_definitions: New edge definitions (optional, creates new version)
            change_description: Required if definitions change
            ttl: New TTL (optional)
            inactivity_timeout: New inactivity timeout (optional)

        Returns:
            Updated Mapping or None if not found
        """
        # Get current mapping
        current = await self.get_by_id(mapping_id)
        if current is None:
            return None

        now = utc_now()
        needs_new_version = node_definitions is not None or edge_definitions is not None

        if needs_new_version:
            # Create new version
            new_version = current.current_version + 1
            version_sql = """
                INSERT INTO mapping_versions (mapping_id, version, change_description,
                                             node_definitions, edge_definitions,
                                             created_at, created_by)
                VALUES (:mapping_id, :version, :change_description,
                        :node_definitions, :edge_definitions,
                        :created_at, :created_by)
            """
            # Use provided definitions if not None, otherwise fall back to current
            # Note: We use `is not None` instead of `or` because `[]` is a valid value
            # (meaning "remove all edges/nodes") but is falsy in Python
            effective_nodes = node_definitions if node_definitions is not None else current.node_definitions
            effective_edges = edge_definitions if edge_definitions is not None else current.edge_definitions

            await self._execute(
                version_sql,
                {
                    "mapping_id": mapping_id,
                    "version": new_version,
                    "change_description": change_description,
                    "node_definitions": serialize_json(
                        [nd.to_dict() for nd in effective_nodes]
                    ),
                    "edge_definitions": serialize_json(
                        [ed.to_dict() for ed in effective_edges]
                    ),
                    "created_at": now,
                    "created_by": updated_by,
                },
            )

            # Update mapping header with new version
            update_sql = """
                UPDATE mappings
                SET name = COALESCE(:name, name),
                    description = COALESCE(:description, description),
                    current_version = :current_version,
                    updated_at = :updated_at,
                    ttl = COALESCE(:ttl, ttl),
                    inactivity_timeout = COALESCE(:inactivity_timeout, inactivity_timeout)
                WHERE id = :mapping_id
            """
            await self._execute(
                update_sql,
                {
                    "mapping_id": mapping_id,
                    "name": name,
                    "description": description,
                    "current_version": new_version,
                    "updated_at": now,
                    "ttl": ttl,
                    "inactivity_timeout": inactivity_timeout,
                },
            )
        else:
            # Just update header fields
            update_sql = """
                UPDATE mappings
                SET name = COALESCE(:name, name),
                    description = COALESCE(:description, description),
                    updated_at = :updated_at,
                    ttl = COALESCE(:ttl, ttl),
                    inactivity_timeout = COALESCE(:inactivity_timeout, inactivity_timeout)
                WHERE id = :mapping_id
            """
            await self._execute(
                update_sql,
                {
                    "mapping_id": mapping_id,
                    "name": name,
                    "description": description,
                    "updated_at": now,
                    "ttl": ttl,
                    "inactivity_timeout": inactivity_timeout,
                },
            )

        # Return updated mapping
        return await self.get_by_id(mapping_id)

    async def delete(self, mapping_id: int) -> bool:
        """Delete a mapping and all its versions.

        Args:
            mapping_id: Mapping ID to delete

        Returns:
            True if mapping was deleted
        """
        # Versions are cascade-deleted via foreign key
        sql = "DELETE FROM mappings WHERE id = :mapping_id"
        result = await self._execute(sql, {"mapping_id": mapping_id})
        return result.rowcount > 0

    async def get_snapshot_count(self, mapping_id: int) -> int:
        """Get count of snapshots for a mapping.

        Args:
            mapping_id: Mapping ID

        Returns:
            Number of snapshots
        """
        sql = "SELECT COUNT(*) FROM snapshots WHERE mapping_id = :mapping_id"
        return await self._fetch_scalar(sql, {"mapping_id": mapping_id}) or 0

    async def get_version(self, mapping_id: int, version: int) -> MappingVersion | None:
        """Get a specific mapping version.

        Args:
            mapping_id: Mapping ID
            version: Version number

        Returns:
            MappingVersion or None if not found
        """
        sql = """
            SELECT mapping_id, version, change_description,
                   node_definitions, edge_definitions,
                   created_at, created_by
            FROM mapping_versions
            WHERE mapping_id = :mapping_id AND version = :version
        """
        row = await self._fetch_one(sql, {"mapping_id": mapping_id, "version": version})
        if row is None:
            return None
        return self._row_to_version(row)

    async def list_versions(self, mapping_id: int) -> list[MappingVersion]:
        """List all versions for a mapping.

        Args:
            mapping_id: Mapping ID

        Returns:
            List of MappingVersion objects ordered by version descending
        """
        sql = """
            SELECT mapping_id, version, change_description,
                   node_definitions, edge_definitions,
                   created_at, created_by
            FROM mapping_versions
            WHERE mapping_id = :mapping_id
            ORDER BY version DESC
        """
        rows = await self._fetch_all(sql, {"mapping_id": mapping_id})
        return [self._row_to_version(row) for row in rows]

    async def exists(self, mapping_id: int) -> bool:
        """Check if mapping exists.

        Args:
            mapping_id: Mapping ID

        Returns:
            True if mapping exists
        """
        sql = "SELECT 1 FROM mappings WHERE id = :mapping_id"
        row = await self._fetch_one(sql, {"mapping_id": mapping_id})
        return row is not None

    async def update_lifecycle(
        self,
        mapping_id: int,
        ttl: str | None = None,
        inactivity_timeout: str | None = None,
    ) -> Mapping | None:
        """Update mapping lifecycle settings only.

        Args:
            mapping_id: Mapping ID
            ttl: New TTL duration (ISO 8601)
            inactivity_timeout: New inactivity timeout (ISO 8601)

        Returns:
            Updated Mapping or None if not found
        """
        now = utc_now()
        sql = """
            UPDATE mappings
            SET ttl = COALESCE(:ttl, ttl),
                inactivity_timeout = COALESCE(:inactivity_timeout, inactivity_timeout),
                updated_at = :updated_at
            WHERE id = :mapping_id
        """
        result = await self._execute(
            sql,
            {
                "mapping_id": mapping_id,
                "ttl": ttl,
                "inactivity_timeout": inactivity_timeout,
                "updated_at": now,
            },
        )
        if result.rowcount == 0:
            return None
        return await self.get_by_id(mapping_id)

    async def list_all(self) -> list[Mapping]:
        """List all mappings without pagination.

        Used by background jobs for lifecycle enforcement.

        Returns:
            List of all Mapping objects
        """
        sql = """
            SELECT m.id, m.owner_username, m.name, m.description,
                   m.current_version, m.created_at, m.updated_at,
                   m.ttl, m.inactivity_timeout,
                   mv.node_definitions, mv.edge_definitions,
                   mv.change_description, mv.created_at as version_created_at,
                   mv.created_by as version_created_by
            FROM mappings m
            JOIN mapping_versions mv
                ON m.id = mv.mapping_id AND m.current_version = mv.version
            ORDER BY m.created_at DESC
        """
        rows = await self._fetch_all(sql, {})
        return [self._row_to_mapping(row) for row in rows]

    def _row_to_mapping(self, row) -> Mapping:
        """Convert database row to Mapping domain object."""
        node_defs_json = deserialize_json(row.node_definitions) or []
        edge_defs_json = deserialize_json(row.edge_definitions) or []

        return Mapping(
            id=row.id,
            owner_username=row.owner_username,
            name=row.name,
            description=row.description,
            current_version=row.current_version,
            created_at=parse_timestamp(row.created_at),
            updated_at=parse_timestamp(row.updated_at),
            ttl=row.ttl,
            inactivity_timeout=row.inactivity_timeout,
            node_definitions=[NodeDefinition.from_dict(nd) for nd in node_defs_json],
            edge_definitions=[EdgeDefinition.from_dict(ed) for ed in edge_defs_json],
            change_description=row.change_description,
            version_created_at=parse_timestamp(row.version_created_at),
            version_created_by=row.version_created_by,
        )

    def _row_to_version(self, row) -> MappingVersion:
        """Convert database row to MappingVersion domain object."""
        node_defs_json = deserialize_json(row.node_definitions) or []
        edge_defs_json = deserialize_json(row.edge_definitions) or []

        return MappingVersion(
            mapping_id=row.mapping_id,
            version=row.version,
            node_definitions=[NodeDefinition.from_dict(nd) for nd in node_defs_json],
            edge_definitions=[EdgeDefinition.from_dict(ed) for ed in edge_defs_json],
            change_description=row.change_description,
            created_at=parse_timestamp(row.created_at),
            created_by=row.created_by,
        )
