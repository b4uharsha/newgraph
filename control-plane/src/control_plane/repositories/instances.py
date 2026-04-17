"""Instance repository for database operations."""

import uuid
from dataclasses import dataclass
from typing import Any

from graph_olap_schemas import WrapperType

from control_plane.models import Instance, InstanceErrorCode, InstanceStatus
from control_plane.models.errors import NotFoundError
from control_plane.repositories.base import (
    BaseRepository,
    deserialize_json,
    parse_timestamp,
    serialize_json,
    utc_now,
)


@dataclass
class InstanceFilters:
    """Filters for listing instances."""

    owner: str | None = None
    snapshot_id: int | None = None
    status: InstanceStatus | None = None
    search: str | None = None


class InstanceRepository(BaseRepository):
    """Repository for instance database operations."""

    async def get_by_id(self, instance_id: int) -> Instance | None:
        """Get instance by ID.

        Args:
            instance_id: Instance ID

        Returns:
            Instance domain object or None if not found
        """
        sql = """
            SELECT id, snapshot_id, pending_snapshot_id, owner_username, wrapper_type,
                   name, description, url_slug, instance_url, pod_name, pod_ip,
                   status, progress, error_message, error_code, stack_trace,
                   created_at, updated_at, started_at,
                   last_activity_at, ttl, inactivity_timeout,
                   memory_usage_bytes, disk_usage_bytes, cpu_cores, memory_gb
            FROM instances
            WHERE id = :instance_id
        """
        row = await self._fetch_one(sql, {"instance_id": instance_id})
        if row is None:
            return None
        return self._row_to_instance(row)

    async def get_by_url_slug(self, url_slug: str) -> Instance | None:
        """Get instance by URL slug.

        Args:
            url_slug: The UUID slug used for external URL routing

        Returns:
            Instance domain object or None if not found
        """
        sql = """
            SELECT id, snapshot_id, pending_snapshot_id, owner_username, wrapper_type,
                   name, description, url_slug, instance_url, pod_name, pod_ip,
                   status, progress, error_message, error_code, stack_trace,
                   created_at, updated_at, started_at,
                   last_activity_at, ttl, inactivity_timeout,
                   memory_usage_bytes, disk_usage_bytes, cpu_cores, memory_gb
            FROM instances
            WHERE url_slug = :url_slug
        """
        row = await self._fetch_one(sql, {"url_slug": url_slug})
        if row is None:
            return None
        return self._row_to_instance(row)

    async def list_instances(
        self,
        filters: InstanceFilters,
        limit: int = 50,
        offset: int = 0,
        sort_field: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[list[Instance], int]:
        """List instances with filters and pagination.

        Args:
            filters: Filter criteria
            limit: Maximum number of results
            offset: Number of results to skip
            sort_field: Field to sort by
            sort_order: Sort order (asc/desc)

        Returns:
            Tuple of (list of Instance objects, total count)
        """
        conditions = []
        params: dict[str, Any] = {"limit": limit, "offset": offset}

        if filters.owner:
            conditions.append("owner_username = :owner")
            params["owner"] = filters.owner

        if filters.snapshot_id:
            conditions.append("snapshot_id = :snapshot_id")
            params["snapshot_id"] = filters.snapshot_id

        if filters.status:
            conditions.append("status = :status")
            params["status"] = filters.status.value

        if filters.search:
            conditions.append("(name LIKE :search OR description LIKE :search)")
            params["search"] = f"%{filters.search}%"

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        # Validate sort field
        allowed_sort_fields = {"created_at", "updated_at", "name", "started_at"}
        sort_field = sort_field if sort_field in allowed_sort_fields else "created_at"
        sort_order = "ASC" if sort_order.lower() == "asc" else "DESC"

        # Get total count
        count_sql = f"SELECT COUNT(*) FROM instances WHERE {where_clause}"
        total = await self._fetch_scalar(count_sql, params)

        # Get paginated results
        sql = f"""
            SELECT id, snapshot_id, pending_snapshot_id, owner_username, wrapper_type,
                   name, description, url_slug, instance_url, pod_name, pod_ip,
                   status, progress, error_message, error_code, stack_trace,
                   created_at, updated_at, started_at,
                   last_activity_at, ttl, inactivity_timeout,
                   memory_usage_bytes, disk_usage_bytes, cpu_cores, memory_gb
            FROM instances
            WHERE {where_clause}
            ORDER BY {sort_field} {sort_order}
            LIMIT :limit OFFSET :offset
        """
        rows = await self._fetch_all(sql, params)
        instances = [self._row_to_instance(row) for row in rows]

        return instances, total

    async def create(
        self,
        snapshot_id: int,
        owner_username: str,
        wrapper_type: WrapperType,
        name: str,
        description: str | None,
        ttl: str | None = None,
        inactivity_timeout: str | None = None,
        cpu_cores: int | None = None,
    ) -> Instance:
        """Create a new instance.

        Args:
            snapshot_id: ID of the source snapshot
            owner_username: Username of the owner
            wrapper_type: Wrapper type (ryugraph, falkordb)
            name: Instance name
            description: Optional description
            ttl: Optional TTL duration (ISO 8601)
            inactivity_timeout: Optional inactivity timeout (ISO 8601)
            cpu_cores: Optional CPU cores (1-8)

        Returns:
            Created Instance
        """
        now = utc_now()
        url_slug = str(uuid.uuid4())  # Generate UUID for external URL routing
        sql = """
            INSERT INTO instances (snapshot_id, owner_username, wrapper_type, name, description,
                                  url_slug, status, created_at, updated_at,
                                  ttl, inactivity_timeout, cpu_cores)
            VALUES (:snapshot_id, :owner_username, :wrapper_type, :name, :description,
                    :url_slug, 'starting', :created_at, :updated_at,
                    :ttl, :inactivity_timeout, :cpu_cores)
            RETURNING id
        """
        instance_id = await self._insert_returning_id(
            sql,
            {
                "snapshot_id": snapshot_id,
                "owner_username": owner_username,
                "wrapper_type": wrapper_type.value,
                "name": name,
                "description": description,
                "url_slug": url_slug,
                "created_at": now,
                "updated_at": now,
                "ttl": ttl,
                "inactivity_timeout": inactivity_timeout,
                "cpu_cores": cpu_cores,
            },
        )

        return Instance(
            id=instance_id,
            snapshot_id=snapshot_id,
            owner_username=owner_username,
            wrapper_type=wrapper_type,
            name=name,
            description=description,
            url_slug=url_slug,
            status=InstanceStatus.STARTING,
            created_at=parse_timestamp(now),
            updated_at=parse_timestamp(now),
            ttl=ttl,
            inactivity_timeout=inactivity_timeout,
            cpu_cores=cpu_cores,
        )

    async def update_status(
        self,
        instance_id: int,
        status: InstanceStatus,
        error_message: str | None = None,
        error_code: InstanceErrorCode | None = None,
        stack_trace: str | None = None,
        pod_name: str | None = None,
        pod_ip: str | None = None,
        instance_url: str | None = None,
        progress: dict[str, Any] | None = None,
    ) -> Instance | None:
        """Update instance status and related fields.

        Args:
            instance_id: Instance ID
            status: New status
            error_message: Error message (for failed status)
            error_code: Machine-readable error code (for failed status)
            stack_trace: Stack trace for debugging (for failed status)
            pod_name: Kubernetes pod name
            pod_ip: Pod IP address
            instance_url: Instance URL (when running)
            progress: Progress information

        Returns:
            Updated Instance or None if not found
        """
        now = utc_now()

        # Set started_at when transitioning to running
        started_at_clause = ""
        if status == InstanceStatus.RUNNING:
            started_at_clause = ", started_at = COALESCE(started_at, :started_at)"

        sql = f"""
            UPDATE instances
            SET status = :status,
                error_message = COALESCE(:error_message, error_message),
                error_code = COALESCE(:error_code, error_code),
                stack_trace = COALESCE(:stack_trace, stack_trace),
                pod_name = COALESCE(:pod_name, pod_name),
                pod_ip = COALESCE(:pod_ip, pod_ip),
                instance_url = COALESCE(:instance_url, instance_url),
                progress = COALESCE(:progress, progress),
                updated_at = :updated_at
                {started_at_clause}
            WHERE id = :instance_id
        """
        params = {
            "instance_id": instance_id,
            "status": status.value,
            "error_message": error_message,
            "error_code": error_code.value if error_code else None,
            "stack_trace": stack_trace,
            "pod_name": pod_name,
            "pod_ip": pod_ip,
            "instance_url": instance_url,
            "progress": serialize_json(progress),
            "updated_at": now,
        }
        if status == InstanceStatus.RUNNING:
            params["started_at"] = now

        result = await self._execute(sql, params)
        if result.rowcount == 0:
            return None

        return await self.get_by_id(instance_id)

    async def update_activity(self, instance_id: int) -> None:
        """Update instance's last_activity_at timestamp.

        Args:
            instance_id: Instance ID
        """
        now = utc_now()
        sql = """
            UPDATE instances
            SET last_activity_at = :last_activity_at,
                updated_at = :updated_at
            WHERE id = :instance_id
        """
        await self._execute(
            sql,
            {
                "instance_id": instance_id,
                "last_activity_at": now,
                "updated_at": now,
            },
        )

    async def update_resource_usage(
        self,
        instance_id: int,
        memory_usage_bytes: int | None = None,
        disk_usage_bytes: int | None = None,
        last_activity_at: str | None = None,
    ) -> bool:
        """Update instance resource usage metrics.

        Args:
            instance_id: Instance ID
            memory_usage_bytes: Current memory usage
            disk_usage_bytes: Current disk usage
            last_activity_at: Optional activity timestamp

        Returns:
            True if instance was updated
        """
        now = utc_now()
        sql = """
            UPDATE instances
            SET memory_usage_bytes = COALESCE(:memory_usage_bytes, memory_usage_bytes),
                disk_usage_bytes = COALESCE(:disk_usage_bytes, disk_usage_bytes),
                last_activity_at = COALESCE(:last_activity_at, last_activity_at),
                updated_at = :updated_at
            WHERE id = :instance_id
        """
        result = await self._execute(
            sql,
            {
                "instance_id": instance_id,
                "memory_usage_bytes": memory_usage_bytes,
                "disk_usage_bytes": disk_usage_bytes,
                "last_activity_at": last_activity_at,
                "updated_at": now,
            },
        )
        return result.rowcount > 0

    async def update_cpu_cores(self, instance_id: int, cpu_cores: int) -> Instance:
        """Update CPU cores for an instance.

        Args:
            instance_id: Instance ID
            cpu_cores: New CPU cores value (1-8)

        Returns:
            Updated instance

        Raises:
            NotFoundError: If instance not found
        """
        now = utc_now()
        sql = """
            UPDATE instances
            SET cpu_cores = :cpu_cores,
                updated_at = :updated_at
            WHERE id = :instance_id
        """
        result = await self._execute(
            sql,
            {
                "instance_id": instance_id,
                "cpu_cores": cpu_cores,
                "updated_at": now,
            },
        )
        if result.rowcount == 0:
            raise NotFoundError(f"Instance {instance_id} not found")
        instance = await self.get_by_id(instance_id)
        # get_by_id returns None if not found, but we just confirmed it exists
        assert instance is not None
        return instance

    async def update_memory_gb(self, instance_id: int, memory_gb: int) -> Instance:
        """Update memory GB for an instance.

        Args:
            instance_id: Instance ID
            memory_gb: New memory value in GB (2-32)

        Returns:
            Updated instance

        Raises:
            NotFoundError: If instance not found
        """
        now = utc_now()
        sql = """
            UPDATE instances
            SET memory_gb = :memory_gb,
                updated_at = :updated_at
            WHERE id = :instance_id
        """
        result = await self._execute(
            sql,
            {
                "instance_id": instance_id,
                "memory_gb": memory_gb,
                "updated_at": now,
            },
        )
        if result.rowcount == 0:
            raise NotFoundError(f"Instance {instance_id} not found")
        instance = await self.get_by_id(instance_id)
        # get_by_id returns None if not found, but we just confirmed it exists
        assert instance is not None
        return instance

    async def update_progress(
        self,
        instance_id: int,
        progress: dict[str, Any],
    ) -> bool:
        """Update instance loading progress.

        Args:
            instance_id: Instance ID
            progress: Progress information (phase and steps)

        Returns:
            True if instance was updated
        """
        now = utc_now()
        sql = """
            UPDATE instances
            SET progress = :progress,
                updated_at = :updated_at
            WHERE id = :instance_id
        """
        result = await self._execute(
            sql,
            {
                "instance_id": instance_id,
                "progress": serialize_json(progress),
                "updated_at": now,
            },
        )
        return result.rowcount > 0

    async def delete(self, instance_id: int) -> bool:
        """Delete an instance.

        Args:
            instance_id: Instance ID to delete

        Returns:
            True if instance was deleted
        """
        sql = "DELETE FROM instances WHERE id = :instance_id"
        result = await self._execute(sql, {"instance_id": instance_id})
        return result.rowcount > 0

    async def count_by_owner(self, owner_username: str) -> int:
        """Count active instances for a user.

        Args:
            owner_username: User's username

        Returns:
            Number of active instances (waiting_for_snapshot, starting, or running)
        """
        sql = """
            SELECT COUNT(*) FROM instances
            WHERE owner_username = :owner_username
              AND status IN ('waiting_for_snapshot', 'starting', 'running')
        """
        return await self._fetch_scalar(sql, {"owner_username": owner_username}) or 0

    async def count_total_active(self) -> int:
        """Count total active instances cluster-wide.

        Returns:
            Total number of active instances (waiting_for_snapshot, starting, or running)
        """
        sql = """
            SELECT COUNT(*) FROM instances
            WHERE status IN ('waiting_for_snapshot', 'starting', 'running')
        """
        return await self._fetch_scalar(sql, {}) or 0

    async def count_instances_referencing_snapshot(self, snapshot_id: int) -> int:
        """Count ALL instances referencing a snapshot (via snapshot_id OR pending_snapshot_id).

        Used by cascade delete to verify a snapshot is truly orphaned before deleting.

        Counts instances regardless of status. The `instances.snapshot_id` foreign
        key has no ON DELETE CASCADE (see infrastructure/tables.py), so any
        instance row pointing at the snapshot — including `failed` ones — will
        cause a FK violation if we delete the snapshot out from under it. Failed
        instances also carry diagnostic state operators may want to inspect; we
        should not silently destroy their referenced snapshot.

        Args:
            snapshot_id: Snapshot ID to check

        Returns:
            Number of instances referencing this snapshot
        """
        sql = """
            SELECT COUNT(*) FROM instances
            WHERE snapshot_id = :snapshot_id OR pending_snapshot_id = :snapshot_id
        """
        return await self._fetch_scalar(sql, {"snapshot_id": snapshot_id}) or 0

    async def get_total_memory_by_owner(self, owner_username: str) -> float:
        """Get total allocated memory across all active instances for a user.

        Parses memory_request from instance resources. Since we don't store
        allocated memory in the DB yet, estimates from memory_usage_bytes
        or returns 0 (governance is best-effort until Phase 2 adds cpu_cores column).

        Args:
            owner_username: User's username

        Returns:
            Total memory in GiB across user's active instances
        """
        sql = """
            SELECT COALESCE(SUM(memory_usage_bytes), 0) FROM instances
            WHERE owner_username = :owner_username
              AND status IN ('waiting_for_snapshot', 'starting', 'running')
        """
        total_bytes = await self._fetch_scalar(sql, {"owner_username": owner_username}) or 0
        return total_bytes / (1024**3)

    async def get_total_cluster_memory(self) -> float:
        """Get total allocated memory across all active instances cluster-wide.

        Returns:
            Total memory in GiB across all active instances
        """
        sql = """
            SELECT COALESCE(SUM(memory_usage_bytes), 0) FROM instances
            WHERE status IN ('waiting_for_snapshot', 'starting', 'running')
        """
        total_bytes = await self._fetch_scalar(sql, {}) or 0
        return total_bytes / (1024**3)

    async def exists(self, instance_id: int) -> bool:
        """Check if instance exists.

        Args:
            instance_id: Instance ID

        Returns:
            True if instance exists
        """
        sql = "SELECT 1 FROM instances WHERE id = :instance_id"
        row = await self._fetch_one(sql, {"instance_id": instance_id})
        return row is not None

    async def update_metadata(
        self,
        instance_id: int,
        name: str | None = None,
        description: str | None = None,
    ) -> Instance | None:
        """Update instance metadata (name, description).

        Args:
            instance_id: Instance ID
            name: New name (optional)
            description: New description (optional)

        Returns:
            Updated Instance or None if not found
        """
        now = utc_now()
        sql = """
            UPDATE instances
            SET name = COALESCE(:name, name),
                description = COALESCE(:description, description),
                updated_at = :updated_at
            WHERE id = :instance_id
        """
        result = await self._execute(
            sql,
            {
                "instance_id": instance_id,
                "name": name,
                "description": description,
                "updated_at": now,
            },
        )
        if result.rowcount == 0:
            return None
        return await self.get_by_id(instance_id)

    async def update_lifecycle(
        self,
        instance_id: int,
        ttl: str | None = None,
        inactivity_timeout: str | None = None,
    ) -> Instance | None:
        """Update instance lifecycle settings.

        Args:
            instance_id: Instance ID
            ttl: New TTL duration (ISO 8601)
            inactivity_timeout: New inactivity timeout (ISO 8601)

        Returns:
            Updated Instance or None if not found
        """
        now = utc_now()
        sql = """
            UPDATE instances
            SET ttl = COALESCE(:ttl, ttl),
                inactivity_timeout = COALESCE(:inactivity_timeout, inactivity_timeout),
                updated_at = :updated_at
            WHERE id = :instance_id
        """
        result = await self._execute(
            sql,
            {
                "instance_id": instance_id,
                "ttl": ttl,
                "inactivity_timeout": inactivity_timeout,
                "updated_at": now,
            },
        )
        if result.rowcount == 0:
            return None
        return await self.get_by_id(instance_id)

    async def find_expired(self, limit: int = 100) -> list[Instance]:
        """Find instances that have exceeded their TTL.

        Args:
            limit: Maximum number to return

        Returns:
            List of expired instances
        """
        sql = """
            SELECT id, snapshot_id, pending_snapshot_id, owner_username, wrapper_type,
                   name, description, url_slug, instance_url, pod_name, pod_ip,
                   status, progress, error_message, error_code, stack_trace,
                   created_at, updated_at, started_at,
                   last_activity_at, ttl, inactivity_timeout,
                   memory_usage_bytes, disk_usage_bytes, cpu_cores, memory_gb
            FROM instances
            WHERE ttl IS NOT NULL
              AND status IN ('starting', 'running', 'waiting_for_snapshot')
            LIMIT :limit
        """
        rows = await self._fetch_all(sql, {"limit": limit})
        return [self._row_to_instance(row) for row in rows]

    async def find_inactive(self, limit: int = 100) -> list[Instance]:
        """Find instances that have exceeded their inactivity timeout.

        Args:
            limit: Maximum number to return

        Returns:
            List of inactive instances
        """
        sql = """
            SELECT id, snapshot_id, pending_snapshot_id, owner_username, wrapper_type,
                   name, description, url_slug, instance_url, pod_name, pod_ip,
                   status, progress, error_message, error_code, stack_trace,
                   created_at, updated_at, started_at,
                   last_activity_at, ttl, inactivity_timeout,
                   memory_usage_bytes, disk_usage_bytes, cpu_cores, memory_gb
            FROM instances
            WHERE inactivity_timeout IS NOT NULL
              AND status = 'running'
              AND last_activity_at IS NOT NULL
            LIMIT :limit
        """
        rows = await self._fetch_all(sql, {"limit": limit})
        return [self._row_to_instance(row) for row in rows]

    async def list_all(self) -> list[Instance]:
        """List all instances without pagination.

        Used by background jobs for reconciliation and lifecycle enforcement.

        Returns:
            List of all Instance objects
        """
        sql = """
            SELECT id, snapshot_id, pending_snapshot_id, owner_username, wrapper_type,
                   name, description, url_slug, instance_url, pod_name, pod_ip,
                   status, progress, error_message, error_code, stack_trace,
                   created_at, updated_at, started_at,
                   last_activity_at, ttl, inactivity_timeout,
                   memory_usage_bytes, disk_usage_bytes, cpu_cores, memory_gb
            FROM instances
            ORDER BY created_at DESC
        """
        rows = await self._fetch_all(sql, {})
        return [self._row_to_instance(row) for row in rows]

    async def get_waiting_for_snapshot(self) -> list[Instance]:
        """Get instances waiting for their snapshot to be ready.

        Used by the reconciliation job to check if pending snapshots
        have completed and instances can transition to 'starting'.

        Returns:
            List of instances with status='waiting_for_snapshot'
        """
        sql = """
            SELECT id, snapshot_id, pending_snapshot_id, owner_username, wrapper_type,
                   name, description, url_slug, instance_url, pod_name, pod_ip,
                   status, progress, error_message, error_code, stack_trace,
                   created_at, updated_at, started_at,
                   last_activity_at, ttl, inactivity_timeout,
                   memory_usage_bytes, disk_usage_bytes, cpu_cores, memory_gb
            FROM instances
            WHERE status = 'waiting_for_snapshot'
            ORDER BY created_at ASC
        """
        rows = await self._fetch_all(sql, {})
        return [self._row_to_instance(row) for row in rows]

    async def transition_to_starting(self, instance_id: int) -> Instance | None:
        """Transition instance from waiting_for_snapshot to starting.

        Called when the pending snapshot becomes ready. Clears the
        pending_snapshot_id and updates status to 'starting'.

        Args:
            instance_id: Instance ID to transition

        Returns:
            Updated Instance or None if not found
        """
        now = utc_now()
        sql = """
            UPDATE instances
            SET pending_snapshot_id = NULL,
                status = 'starting',
                updated_at = :updated_at
            WHERE id = :instance_id
        """
        result = await self._execute(
            sql,
            {
                "instance_id": instance_id,
                "updated_at": now,
            },
        )
        if result.rowcount == 0:
            return None
        return await self.get_by_id(instance_id)

    async def create_waiting_for_snapshot(
        self,
        snapshot_id: int,
        owner_username: str,
        wrapper_type: WrapperType,
        name: str,
        url_slug: str | None = None,
        description: str | None = None,
        ttl: str | None = None,
        inactivity_timeout: str | None = None,
        cpu_cores: int | None = None,
    ) -> Instance:
        """Create a new instance waiting for a snapshot to be ready.

        Used when creating an instance from a mapping. The snapshot is
        created first, and the instance waits for it to complete.

        Args:
            snapshot_id: ID of the snapshot (also used as pending_snapshot_id)
            owner_username: Username of the owner
            wrapper_type: Wrapper type (ryugraph, falkordb)
            name: Instance name
            url_slug: Optional URL slug (generated if not provided)
            description: Optional description
            ttl: Optional TTL duration (ISO 8601)
            inactivity_timeout: Optional inactivity timeout (ISO 8601)
            cpu_cores: Optional CPU cores (1-8)

        Returns:
            Created Instance with status='waiting_for_snapshot'
        """
        now = utc_now()
        if url_slug is None:
            url_slug = str(uuid.uuid4())  # Generate UUID for external URL routing
        sql = """
            INSERT INTO instances (snapshot_id, pending_snapshot_id, owner_username,
                                  wrapper_type, name, description, url_slug, status,
                                  created_at, updated_at, ttl, inactivity_timeout, cpu_cores)
            VALUES (:snapshot_id, :pending_snapshot_id, :owner_username,
                    :wrapper_type, :name, :description, :url_slug,
                    'waiting_for_snapshot', :created_at, :updated_at,
                    :ttl, :inactivity_timeout, :cpu_cores)
            RETURNING id
        """
        instance_id = await self._insert_returning_id(
            sql,
            {
                "snapshot_id": snapshot_id,
                "pending_snapshot_id": snapshot_id,  # Same as snapshot_id
                "owner_username": owner_username,
                "wrapper_type": wrapper_type.value,
                "name": name,
                "description": description,
                "url_slug": url_slug,
                "created_at": now,
                "updated_at": now,
                "ttl": ttl,
                "inactivity_timeout": inactivity_timeout,
                "cpu_cores": cpu_cores,
            },
        )

        return Instance(
            id=instance_id,
            snapshot_id=snapshot_id,
            pending_snapshot_id=snapshot_id,  # Same as snapshot_id
            owner_username=owner_username,
            wrapper_type=wrapper_type,
            name=name,
            description=description,
            url_slug=url_slug,
            status=InstanceStatus.WAITING_FOR_SNAPSHOT,
            created_at=parse_timestamp(now),
            updated_at=parse_timestamp(now),
            ttl=ttl,
            inactivity_timeout=inactivity_timeout,
            cpu_cores=cpu_cores,
        )

    async def list_by_mapping(
        self,
        mapping_id: int,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Instance], int]:
        """List instances created from a mapping (via snapshots).

        Args:
            mapping_id: Mapping ID to filter by
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            Tuple of (list of Instance objects, total count)
        """
        params: dict[str, Any] = {
            "mapping_id": mapping_id,
            "limit": limit,
            "offset": offset,
        }

        # Get total count
        count_sql = """
            SELECT COUNT(*)
            FROM instances i
            JOIN snapshots s ON i.snapshot_id = s.id
            WHERE s.mapping_id = :mapping_id
        """
        total = await self._fetch_scalar(count_sql, params)

        # Get paginated results
        sql = """
            SELECT i.id, i.snapshot_id, i.pending_snapshot_id, i.owner_username,
                   i.wrapper_type, i.name, i.description, i.url_slug, i.instance_url,
                   i.pod_name, i.pod_ip, i.status, i.progress, i.error_message,
                   i.error_code, i.stack_trace, i.created_at, i.updated_at,
                   i.started_at, i.last_activity_at, i.ttl, i.inactivity_timeout,
                   i.memory_usage_bytes, i.disk_usage_bytes, i.cpu_cores, i.memory_gb
            FROM instances i
            JOIN snapshots s ON i.snapshot_id = s.id
            WHERE s.mapping_id = :mapping_id
            ORDER BY i.created_at DESC
            LIMIT :limit OFFSET :offset
        """
        rows = await self._fetch_all(sql, params)
        instances = [self._row_to_instance(row) for row in rows]

        return instances, total or 0

    def _row_to_instance(self, row) -> Instance:
        """Convert database row to Instance domain object."""
        return Instance(
            id=row.id,
            snapshot_id=row.snapshot_id,
            pending_snapshot_id=getattr(row, "pending_snapshot_id", None),
            owner_username=row.owner_username,
            wrapper_type=WrapperType(row.wrapper_type),
            name=row.name,
            description=row.description,
            url_slug=row.url_slug,
            status=InstanceStatus(row.status),
            instance_url=row.instance_url,
            pod_name=row.pod_name,
            pod_ip=row.pod_ip,
            progress=deserialize_json(row.progress),
            error_message=row.error_message,
            error_code=InstanceErrorCode(row.error_code) if row.error_code else None,
            stack_trace=row.stack_trace,
            created_at=parse_timestamp(row.created_at),
            updated_at=parse_timestamp(row.updated_at),
            started_at=parse_timestamp(row.started_at),
            last_activity_at=parse_timestamp(row.last_activity_at),
            ttl=row.ttl,
            inactivity_timeout=row.inactivity_timeout,
            memory_usage_bytes=row.memory_usage_bytes,
            disk_usage_bytes=row.disk_usage_bytes,
            cpu_cores=row.cpu_cores,
            memory_gb=getattr(row, "memory_gb", None),
        )
