"""Instance service with business logic.

Manages the lifecycle of graph database instances, including:
- Instance creation from snapshots with concurrency limit enforcement
- Instance creation from mappings (auto-creates snapshot)
- Instance termination and deletion with K8s pod cleanup
- Lifecycle settings management (TTL, inactivity timeout)
- Status tracking and progress reporting
"""

from typing import TYPE_CHECKING, Any

import structlog

from control_plane.models import (
    ConcurrencyLimitError,
    Instance,
    InstanceErrorCode,
    InstanceStatus,
    InvalidStateError,
    NotFoundError,
    PermissionDeniedError,
    SnapshotStatus,
    User,
    UserRole,
)
from control_plane.models.requests import (
    CreateInstanceFromMappingRequest,
    CreateInstanceRequest,
    CreateSnapshotRequest,
    UpdateInstanceRequest,
    UpdateLifecycleRequest,
)
from control_plane.config import get_settings
from control_plane.repositories.config import GlobalConfigRepository
from control_plane.repositories.favorites import FavoritesRepository
from control_plane.repositories.instances import InstanceFilters, InstanceRepository
from control_plane.repositories.mappings import MappingRepository
from control_plane.repositories.snapshots import SnapshotRepository
from graph_olap_schemas import WrapperType

if TYPE_CHECKING:
    from control_plane.clients.gcs import GCSClient
    from control_plane.services.k8s_service import K8sService
    from control_plane.services.snapshot_service import SnapshotService

logger = structlog.get_logger(__name__)


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


class InstanceService:
    """Service for instance business operations."""

    def __init__(
        self,
        instance_repo: InstanceRepository,
        snapshot_repo: SnapshotRepository,
        config_repo: GlobalConfigRepository,
        favorites_repo: FavoritesRepository,
        k8s_service: "K8sService | None" = None,
        mapping_repo: MappingRepository | None = None,
        snapshot_service: "SnapshotService | None" = None,
        gcs_client: "GCSClient | None" = None,
    ):
        """Initialize service with repositories.

        Args:
            instance_repo: Instance repository
            snapshot_repo: Snapshot repository
            config_repo: Global config repository
            favorites_repo: Favorites repository (for cascade delete)
            k8s_service: Optional K8s service for pod management
            mapping_repo: Optional mapping repository (for create_from_mapping)
            snapshot_service: Optional snapshot service (for create_from_mapping)
            gcs_client: GCS client for snapshot cascade cleanup. None is only
                valid in tests and dev runs without GCS configured — production
                DI sites MUST pass a working client (see clients.gcs.
                build_gcs_client_from_settings).
        """
        self._instance_repo = instance_repo
        self._snapshot_repo = snapshot_repo
        self._config_repo = config_repo
        self._favorites_repo = favorites_repo
        self._k8s_service = k8s_service
        self._mapping_repo = mapping_repo
        self._snapshot_service = snapshot_service
        self._gcs_client = gcs_client

    def _calculate_resources(
        self, snapshot_size_bytes: int | None, wrapper_type: WrapperType, cpu_cores: int = 2
    ) -> dict[str, str]:
        """Calculate pod resources from snapshot size.

        Memory is automatically sized based on snapshot data size and wrapper type.
        CPU uses a 2x burst model (request=cpu_cores, limit=cpu_cores*2).

        Args:
            snapshot_size_bytes: Snapshot size in bytes (None uses minimums)
            wrapper_type: Wrapper type (affects memory multiplier)
            cpu_cores: CPU cores (default 2, request=N, limit=2N)

        Returns:
            Dict with memory_request, memory_limit, cpu_request, cpu_limit, disk_size
        """
        settings = get_settings()

        size_bytes = snapshot_size_bytes or 0
        size_gb = size_bytes / (1024**3)

        # Wrapper-specific memory calculation
        if wrapper_type == WrapperType.FALKORDB:
            # In-memory graph: needs ~2x parquet size + 1GB base
            memory_gb = max(settings.sizing_min_memory_gb, size_gb * settings.sizing_falkordb_memory_multiplier + 1)
        else:
            # Disk-based graph (Ryugraph): needs ~1.2x parquet size + 0.5GB base
            memory_gb = max(settings.sizing_min_memory_gb, size_gb * settings.sizing_ryugraph_memory_multiplier + 0.5)

        # Apply headroom and cap
        memory_gb = min(memory_gb * settings.sizing_memory_headroom, settings.sizing_max_memory_gb)

        # Disk sizing
        disk_gb = max(settings.sizing_min_disk_gb, int(size_gb * settings.sizing_disk_multiplier) + 5)

        # Round memory up to nearest integer for clean K8s values
        memory_gi = int(memory_gb) if memory_gb == int(memory_gb) else int(memory_gb) + 1

        return {
            "memory_request": f"{memory_gi}Gi",
            "memory_limit": f"{memory_gi}Gi",  # Guaranteed QoS (request == limit)
            "cpu_request": str(cpu_cores),
            "cpu_limit": str(cpu_cores * 2),
            "disk_size": f"{disk_gb}Gi",
        }

    async def _check_resource_governance(
        self, memory_gi: int, owner_username: str
    ) -> None:
        """Check resource governance limits before creating/resizing a pod.

        Args:
            memory_gi: Requested memory in GiB
            owner_username: Owner username for per-user checks

        Raises:
            ConcurrencyLimitError: If any governance limit would be exceeded
        """
        settings = get_settings()

        # Per-instance cap
        if memory_gi > settings.sizing_max_memory_gb:
            raise ConcurrencyLimitError(
                "instance_memory", memory_gi, int(settings.sizing_max_memory_gb)
            )

        # Per-user memory cap
        user_total_memory_gb = await self._instance_repo.get_total_memory_by_owner(owner_username)
        if user_total_memory_gb + memory_gi > settings.sizing_per_user_max_memory_gb:
            raise ConcurrencyLimitError(
                "user_memory",
                int(user_total_memory_gb + memory_gi),
                int(settings.sizing_per_user_max_memory_gb),
            )

        # Cluster-wide soft limit
        cluster_total_memory_gb = await self._instance_repo.get_total_cluster_memory()
        if cluster_total_memory_gb + memory_gi > settings.sizing_cluster_memory_soft_limit_gb:
            raise ConcurrencyLimitError(
                "cluster_memory",
                int(cluster_total_memory_gb + memory_gi),
                int(settings.sizing_cluster_memory_soft_limit_gb),
            )

    async def _validate_instance_status(self, instance: Instance) -> Instance:
        """Validate instance status against Kubernetes pod readiness.

        This ensures clients see "running" only when the instance is actually
        reachable via ingress. The wrapper reports "running" when it finishes
        data loading, but Kubernetes may not have marked the pod Ready yet
        (readiness probe takes 2-5 seconds to pass after wrapper reports ready).

        If the pod isn't Ready, we return "starting" status so clients know
        to wait before attempting health checks.

        Args:
            instance: Instance to validate

        Returns:
            Instance with validated status (may be modified from DB value)
        """
        from dataclasses import replace

        # Only validate "running" status - other statuses don't need K8s check
        if instance.status != InstanceStatus.RUNNING:
            return instance

        # Need pod_name to check K8s status
        if not instance.pod_name:
            return instance

        # Need K8s service to check pod readiness
        if not self._k8s_service:
            return instance

        # Check if pod is Ready in Kubernetes
        pod_ready = await self._k8s_service.is_pod_ready(instance.pod_name)

        if not pod_ready:
            # Pod not ready yet - return "starting" so clients know to wait
            logger.info(
                "instance_status_adjusted",
                instance_id=instance.id,
                pod_name=instance.pod_name,
                db_status="running",
                client_status="starting",
                reason="pod_not_ready",
            )
            return replace(instance, status=InstanceStatus.STARTING)

        logger.debug(
            "instance_status_validated",
            instance_id=instance.id,
            pod_name=instance.pod_name,
            status="running",
            pod_ready=True,
        )

        return instance

    async def get_instance(self, instance_id: int) -> Instance:
        """Get an instance by ID.

        Args:
            instance_id: Instance ID

        Returns:
            Instance domain object with validated status

        Raises:
            NotFoundError: If instance not found
        """
        instance = await self._instance_repo.get_by_id(instance_id)
        if instance is None:
            raise NotFoundError("Instance", instance_id)

        # Validate status against pod readiness
        return await self._validate_instance_status(instance)

    async def list_instances(
        self,
        user: User,
        owner: str | None = None,
        snapshot_id: int | None = None,
        status: InstanceStatus | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
        sort_field: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[list[Instance], int]:
        """List instances with filters.

        Args:
            user: Current user
            owner: Filter by owner username
            snapshot_id: Filter by snapshot ID
            status: Filter by status
            search: Search term for name/description
            limit: Maximum number of results
            offset: Number of results to skip
            sort_field: Field to sort by
            sort_order: Sort order (asc/desc)

        Returns:
            Tuple of (list of instances with validated status, total count)
        """
        filters = InstanceFilters(
            owner=owner,
            snapshot_id=snapshot_id,
            status=status,
            search=search,
        )

        instances, total = await self._instance_repo.list_instances(
            filters=filters,
            limit=limit,
            offset=offset,
            sort_field=sort_field,
            sort_order=sort_order,
        )

        # Validate status for each instance against pod readiness
        # This ensures clients see "running" only when actually reachable
        validated_instances = [
            await self._validate_instance_status(instance) for instance in instances
        ]

        return validated_instances, total

    async def create_instance(
        self,
        user: User,
        request: CreateInstanceRequest,
    ) -> Instance:
        """Create a new instance from a snapshot.

        Checks concurrency limits before creation.

        Args:
            user: Current user (becomes owner)
            request: Creation request

        Returns:
            Created Instance with status='starting'

        Raises:
            NotFoundError: If snapshot not found
            InvalidStateError: If snapshot is not ready
            ConcurrencyLimitError: If user or cluster limit exceeded
        """
        # Verify snapshot exists and is ready
        snapshot = await self._snapshot_repo.get_by_id(request.snapshot_id)
        if snapshot is None:
            raise NotFoundError("Snapshot", request.snapshot_id)

        if snapshot.status != SnapshotStatus.READY:
            raise InvalidStateError("Snapshot", request.snapshot_id, snapshot.status.value, "ready")

        # Calculate resources from snapshot size
        settings = get_settings()
        resources = None
        cpu_cores = request.cpu_cores if request.cpu_cores is not None else settings.sizing_default_cpu_cores
        if settings.sizing_enabled:
            resources = self._calculate_resources(
                snapshot_size_bytes=snapshot.size_bytes,
                wrapper_type=request.wrapper_type,
                cpu_cores=cpu_cores,
            )
            # Parse memory for governance check
            memory_gi = int(resources["memory_request"].replace("Gi", ""))
            await self._check_resource_governance(memory_gi, user.username)

        # Check concurrency limits
        limits = await self._config_repo.get_concurrency_limits()

        # Per-user limit
        user_count = await self._instance_repo.count_by_owner(user.username)
        if user_count >= limits["per_analyst"]:
            raise ConcurrencyLimitError("per_analyst", user_count, limits["per_analyst"])

        # Cluster-wide limit
        total_count = await self._instance_repo.count_total_active()
        if total_count >= limits["cluster_total"]:
            raise ConcurrencyLimitError("cluster_total", total_count, limits["cluster_total"])

        # Get default TTL if not specified
        ttl = request.ttl
        inactivity_timeout = request.inactivity_timeout

        if ttl is None or inactivity_timeout is None:
            lifecycle_config = await self._config_repo.get_lifecycle_config("instance")
            if ttl is None:
                ttl = lifecycle_config.get("default_ttl")
            if inactivity_timeout is None:
                inactivity_timeout = lifecycle_config.get("default_inactivity")

        # Create instance
        instance = await self._instance_repo.create(
            snapshot_id=request.snapshot_id,
            owner_username=user.username,
            wrapper_type=request.wrapper_type,
            name=request.name,
            description=request.description,
            ttl=ttl,
            inactivity_timeout=inactivity_timeout,
            cpu_cores=cpu_cores,
        )

        # Update snapshot last_used_at
        await self._snapshot_repo.update_last_used(request.snapshot_id)

        # Look up mapping name for pod labels (best-effort)
        mapping_name = ""
        if self._mapping_repo:
            try:
                mapping = await self._mapping_repo.get_by_id(snapshot.mapping_id)
                if mapping:
                    mapping_name = mapping.name
            except Exception:
                pass  # Non-critical — label will be omitted

        # Create K8s pod for the wrapper (if K8s service available)
        logger.info("instance_created", instance_id=instance.id, k8s_available=self._k8s_service is not None)
        if self._k8s_service is not None and instance.url_slug:
            try:
                logger.info("k8s_pod_creating", instance_id=instance.id, url_slug=instance.url_slug)
                pod_name, external_url = await self._k8s_service.create_wrapper_pod(
                    instance_id=instance.id,
                    url_slug=instance.url_slug,
                    wrapper_type=request.wrapper_type,
                    snapshot_id=snapshot.id,
                    mapping_id=snapshot.mapping_id,
                    mapping_version=snapshot.mapping_version,
                    owner_username=user.username,
                    owner_email=user.email or f"{user.username}@auto.local",
                    gcs_path=snapshot.gcs_path,
                    resource_overrides=resources,
                    instance_name=request.name,
                    mapping_name=mapping_name,
                )
                if pod_name:
                    logger.info("wrapper_pod_created", pod_name=pod_name, instance_id=instance.id)
                    # FIX: Persist pod_name IMMEDIATELY after creation (not just external_url)
                    # This enables DELETE /instances/:id to work and enables reconciliation
                    instance = await self._instance_repo.update_status(
                        instance_id=instance.id,
                        status=InstanceStatus.STARTING,
                        pod_name=pod_name,  # Now tracked!
                        instance_url=external_url if external_url else None,
                    )
                    logger.info(
                        "pod_name_tracked",
                        instance_id=instance.id,
                        pod_name=pod_name,
                        external_url=external_url,
                    )
                else:
                    logger.warning("k8s_pod_not_created", instance_id=instance.id, reason="k8s_not_available")
            except Exception as e:
                # Log error but don't fail - pod creation is best-effort
                # The reconciliation job will retry failed pods
                logger.exception("wrapper_pod_creation_failed", instance_id=instance.id, error=str(e))
        else:
            logger.warning("k8s_service_unavailable", instance_id=instance.id)

        return instance

    async def create_from_mapping(
        self,
        user: User,
        request: CreateInstanceFromMappingRequest,
    ) -> Instance:
        """Create a new instance directly from a mapping.

        This method:
        1. Validates the mapping exists and user has access
        2. Checks concurrency limits BEFORE creating the snapshot
        3. Creates a snapshot via SnapshotService
        4. Creates an instance with status='waiting_for_snapshot'

        The instance will transition to 'starting' when the snapshot becomes ready
        (handled by the reconciliation job).

        Args:
            user: Current user (becomes owner)
            request: Instance from mapping creation request

        Returns:
            Created Instance with status='waiting_for_snapshot'

        Raises:
            NotFoundError: If mapping not found
            ConcurrencyLimitError: If user or cluster limit exceeded
            RuntimeError: If required services are not configured
        """
        # Validate required services
        if self._mapping_repo is None:
            raise RuntimeError("MappingRepository is required for create_from_mapping")
        if self._snapshot_service is None:
            raise RuntimeError("SnapshotService is required for create_from_mapping")

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

        # Check concurrency limits BEFORE creating snapshot
        limits = await self._config_repo.get_concurrency_limits()

        # Per-user limit
        user_count = await self._instance_repo.count_by_owner(user.username)
        if user_count >= limits["per_analyst"]:
            raise ConcurrencyLimitError("per_analyst", user_count, limits["per_analyst"])

        # Cluster-wide limit
        total_count = await self._instance_repo.count_total_active()
        if total_count >= limits["cluster_total"]:
            raise ConcurrencyLimitError("cluster_total", total_count, limits["cluster_total"])

        # Get default TTL if not specified
        settings = get_settings()
        ttl = request.ttl
        inactivity_timeout = request.inactivity_timeout
        cpu_cores = request.cpu_cores if request.cpu_cores is not None else settings.sizing_default_cpu_cores

        if ttl is None or inactivity_timeout is None:
            lifecycle_config = await self._config_repo.get_lifecycle_config("instance")
            if ttl is None:
                ttl = lifecycle_config.get("default_ttl")
            if inactivity_timeout is None:
                inactivity_timeout = lifecycle_config.get("default_inactivity")

        # Check for existing READY snapshot (ADR-119: snapshot reuse)
        existing_snapshot = await self._snapshot_repo.find_ready_snapshot(
            request.mapping_id, mapping_version
        )
        if existing_snapshot:
            snapshot = existing_snapshot
            logger.info(
                "reusing_existing_snapshot",
                snapshot_id=existing_snapshot.id,
                mapping_id=request.mapping_id,
                mapping_version=mapping_version,
            )
        else:
            # Create snapshot via SnapshotService (triggers Starburst export)
            # Generate a name for the auto-created snapshot
            snapshot_name = f"Auto-snapshot for {request.name}"
            snapshot_request = CreateSnapshotRequest(
                mapping_id=request.mapping_id,
                mapping_version=mapping_version,
                name=snapshot_name,
                description=f"Automatically created for instance '{request.name}'",
                ttl=ttl,
                inactivity_timeout=inactivity_timeout,
            )
            starburst_role = getattr(user, "use_case_id", None)
            snapshot = await self._snapshot_service.create_snapshot(
                user, snapshot_request, starburst_role=starburst_role
            )

        logger.info(
            "snapshot_created_for_instance",
            snapshot_id=snapshot.id,
            mapping_id=request.mapping_id,
            mapping_version=mapping_version,
            instance_name=request.name,
            user=user.username,
        )

        # Create instance with status='waiting_for_snapshot'
        instance = await self._instance_repo.create_waiting_for_snapshot(
            snapshot_id=snapshot.id,
            owner_username=user.username,
            wrapper_type=request.wrapper_type,
            name=request.name,
            description=request.description,
            ttl=ttl,
            inactivity_timeout=inactivity_timeout,
            cpu_cores=cpu_cores,
        )

        logger.info(
            "instance_created_from_mapping",
            instance_id=instance.id,
            snapshot_id=snapshot.id,
            mapping_id=request.mapping_id,
            status="waiting_for_snapshot",
            user=user.username,
        )

        return instance

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
    ) -> Instance:
        """Update instance status (internal API).

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
            Updated Instance

        Raises:
            NotFoundError: If instance not found
        """
        instance = await self._instance_repo.update_status(
            instance_id=instance_id,
            status=status,
            error_message=error_message,
            error_code=error_code,
            stack_trace=stack_trace,
            pod_name=pod_name,
            pod_ip=pod_ip,
            instance_url=instance_url,
            progress=progress,
        )

        if instance is None:
            raise NotFoundError("Instance", instance_id)

        return instance

    async def update_activity(self, instance_id: int) -> None:
        """Update instance activity timestamp.

        Called when a query or algorithm is executed.

        Args:
            instance_id: Instance ID

        Raises:
            NotFoundError: If instance not found
        """
        # Verify instance exists
        exists = await self._instance_repo.exists(instance_id)
        if not exists:
            raise NotFoundError("Instance", instance_id)

        await self._instance_repo.update_activity(instance_id)

    async def _cleanup_k8s_resources(self, instance: Instance) -> None:
        """Delete ALL K8s resources for an instance (pod, service, ingress).

        Internal method - idempotent, safe to call even if resources don't exist.

        Args:
            instance: Instance whose K8s resources should be deleted
        """
        if self._k8s_service is None or not instance.url_slug:
            return

        try:
            deleted = await self._k8s_service.delete_wrapper_pod(instance.url_slug)
            if deleted:
                logger.info(
                    "k8s_resources_deleted",
                    instance_id=instance.id,
                    url_slug=instance.url_slug,
                )
            else:
                logger.warning(
                    "k8s_resources_not_found",
                    instance_id=instance.id,
                    url_slug=instance.url_slug,
                )
        except Exception as e:
            # Log error but don't fail - deletion is best-effort
            # If K8s resources are already gone, that's acceptable
            logger.warning(
                "k8s_cleanup_error",
                instance_id=instance.id,
                url_slug=instance.url_slug,
                error=str(e),
            )

    async def delete_instance(
        self,
        instance_id: int,
        user: User,
    ) -> None:
        """Delete instance (permission-checked).

        Permission check: User must be owner OR admin
        No state restrictions - if user wants it deleted, delete it

        Deletion order:
        1. Delete K8s resources FIRST (pod, service, ingress)
        2. Delete from database LAST (prevents 404 errors)

        Args:
            instance_id: Instance to delete
            user: User performing deletion

        Raises:
            NotFoundError: If instance not found
            PermissionDeniedError: If user is not owner or admin
        """
        # Get existing instance
        instance = await self.get_instance(instance_id)

        # Permission check: owner OR admin/ops
        if user.role not in (UserRole.ADMIN, UserRole.OPS):
            check_ownership(user, instance.owner_username, "Instance", instance_id)

        logger.info(
            "instance_deletion_started",
            instance_id=instance_id,
            pod_name=instance.pod_name,
            url_slug=instance.url_slug,
            status=instance.status.value,
            deleted_by=user.username,
        )

        # Delete K8s resources FIRST (pod, service, ingress)
        await self._cleanup_k8s_resources(instance)

        # CASCADE: Delete all favorites referencing this instance (before delete commits)
        deleted_favorites = await self._favorites_repo.remove_for_resource(
            resource_type="instance",
            resource_id=instance_id,
        )

        if deleted_favorites > 0:
            logger.info(
                "Cascade deleted favorites for deleted instance",
                instance_id=instance_id,
                favorites_deleted=deleted_favorites,
            )

        # Delete instance from database
        snapshot_id = instance.snapshot_id
        deleted = await self._instance_repo.delete(instance_id)
        if deleted:
            logger.info(
                "instance_deleted",
                instance_id=instance_id,
                owner=instance.owner_username,
                deleted_by=user.username,
            )
        else:
            logger.warning("instance_already_deleted", instance_id=instance_id)

        # CASCADE: Delete the snapshot if no other instances reference it.
        # Snapshots may be shared between instances of the same mapping version
        # (ADR-119 snapshot reuse). Only delete if truly orphaned.
        if snapshot_id:
            try:
                # Check ALL references: snapshot_id and pending_snapshot_id, any active status
                remaining = await self._instance_repo.count_instances_referencing_snapshot(snapshot_id)
                if remaining == 0:
                    snapshot = await self._snapshot_repo.get_by_id(snapshot_id)
                    if snapshot:
                        # Delete GCS files. If gcs_client is None we log loudly
                        # and still delete the DB row — the bucket lifecycle rule
                        # is the only backstop in that case.
                        if self._gcs_client is None:
                            logger.warning(
                                "cascade_snapshot_gcs_delete_skipped_no_client",
                                instance_id=instance_id,
                                snapshot_id=snapshot_id,
                                gcs_path=snapshot.gcs_path,
                                reason="InstanceService constructed without gcs_client; "
                                       "GCS files will be orphaned unless a bucket lifecycle "
                                       "rule reaps them",
                            )
                        elif snapshot.gcs_path:
                            try:
                                files, bytes_ = self._gcs_client.delete_path(snapshot.gcs_path)
                                logger.info(
                                    "cascade_snapshot_gcs_deleted",
                                    snapshot_id=snapshot_id,
                                    files=files, bytes=bytes_,
                                )
                            except Exception as e:
                                logger.warning(
                                    "cascade_snapshot_gcs_delete_failed",
                                    snapshot_id=snapshot_id, error=str(e),
                                )
                        else:
                            # gcs_client is wired but the snapshot row has no path.
                            # Should not happen in production (all snapshots get a
                            # path at creation time), but log for observability.
                            logger.warning(
                                "cascade_snapshot_gcs_delete_skipped_no_path",
                                instance_id=instance_id,
                                snapshot_id=snapshot_id,
                                reason="snapshot row has empty gcs_path; nothing to delete",
                            )
                        # Delete snapshot DB record
                        await self._snapshot_repo.delete(snapshot_id)
                        logger.info(
                            "cascade_snapshot_deleted",
                            instance_id=instance_id,
                            snapshot_id=snapshot_id,
                        )
            except Exception as e:
                logger.warning(
                    "cascade_snapshot_delete_failed",
                    instance_id=instance_id,
                    snapshot_id=snapshot_id,
                    error=str(e),
                )

    async def get_cluster_status(self) -> dict[str, Any]:
        """Get cluster-wide instance status.

        Returns:
            Dictionary with instance counts and limits
        """
        limits = await self._config_repo.get_concurrency_limits()
        total_active = await self._instance_repo.count_total_active()

        return {
            "active_instances": total_active,
            "cluster_limit": limits["cluster_total"],
            "available_slots": max(0, limits["cluster_total"] - total_active),
        }

    async def get_user_status(self, username: str) -> dict[str, Any]:
        """Get instance status for a specific user.

        Args:
            username: User's username

        Returns:
            Dictionary with user's instance counts and limits
        """
        limits = await self._config_repo.get_concurrency_limits()
        user_active = await self._instance_repo.count_by_owner(username)

        return {
            "active_instances": user_active,
            "per_user_limit": limits["per_analyst"],
            "available_slots": max(0, limits["per_analyst"] - user_active),
        }

    async def update_instance(
        self,
        user: User,
        instance_id: int,
        request: UpdateInstanceRequest,
    ) -> Instance:
        """Update instance metadata.

        Args:
            user: Current user
            instance_id: Instance ID to update
            request: Update request with new values

        Returns:
            Updated Instance

        Raises:
            NotFoundError: If instance not found
            PermissionDeniedError: If user cannot modify instance
        """
        # Get existing instance
        instance = await self.get_instance(instance_id)

        # Check permission
        check_ownership(user, instance.owner_username, "Instance", instance_id)

        # Update metadata
        updated = await self._instance_repo.update_metadata(
            instance_id=instance_id,
            name=request.name,
            description=request.description,
        )

        if updated is None:
            raise NotFoundError("Instance", instance_id)

        return updated

    async def update_lifecycle(
        self,
        user: User,
        instance_id: int,
        request: UpdateLifecycleRequest,
    ) -> Instance:
        """Update instance lifecycle settings.

        Args:
            user: Current user
            instance_id: Instance ID to update
            request: Lifecycle update request

        Returns:
            Updated Instance

        Raises:
            NotFoundError: If instance not found
            PermissionDeniedError: If user cannot modify instance
        """
        # Get existing instance
        instance = await self.get_instance(instance_id)

        # Check permission
        check_ownership(user, instance.owner_username, "Instance", instance_id)

        # Update lifecycle
        updated = await self._instance_repo.update_lifecycle(
            instance_id=instance_id,
            ttl=request.ttl,
            inactivity_timeout=request.inactivity_timeout,
        )

        if updated is None:
            raise NotFoundError("Instance", instance_id)

        return updated

    async def update_cpu(
        self, user: User, instance_id: int, cpu_cores: int
    ) -> Instance:
        """Update CPU cores for a running instance.

        Performs K8s in-place resize to update CPU allocation.

        Args:
            user: Current user
            instance_id: Instance ID
            cpu_cores: New CPU cores (1-8)

        Returns:
            Updated instance

        Raises:
            NotFoundError: If instance not found
            InvalidStateError: If instance is not running
            PermissionDeniedError: If user is not owner/admin
        """
        instance = await self.get_instance(instance_id)

        # Check permissions - owner, admin, or ops
        if instance.owner_username != user.username and user.role not in (
            UserRole.ADMIN,
            UserRole.OPS,
        ):
            raise PermissionDeniedError("Instance", instance_id)

        # Check state - must be running
        if instance.status != InstanceStatus.RUNNING:
            raise InvalidStateError(
                "Instance",
                instance_id,
                instance.status.value,
                "running",
            )

        # Must have pod_name to resize
        if not instance.pod_name:
            raise InvalidStateError(
                "Instance",
                instance_id,
                "no_pod",
                "running with pod",
            )

        # Update K8s pod resources
        if self._k8s_service:
            await self._k8s_service.resize_pod_cpu(
                pod_name=instance.pod_name,
                cpu_request=str(cpu_cores),
                cpu_limit=str(cpu_cores * 2),
            )

        # Update database
        return await self._instance_repo.update_cpu_cores(instance_id, cpu_cores)

    async def update_memory(
        self, user: User, instance_id: int, memory_gb: int
    ) -> Instance:
        """Upgrade memory for a running instance.

        Performs K8s in-place resize to increase memory allocation.
        Only memory INCREASES are allowed (decreases would kill the process).

        Args:
            user: Current user
            instance_id: Instance ID
            memory_gb: New memory in GB (must be >= current, max 32)

        Returns:
            Updated instance

        Raises:
            NotFoundError: If instance not found
            InvalidStateError: If instance is not running or memory decrease attempted
            PermissionDeniedError: If user is not owner/admin/ops
        """
        instance = await self.get_instance(instance_id)

        # Check permissions - owner, admin, or ops
        if instance.owner_username != user.username and user.role not in (
            UserRole.ADMIN,
            UserRole.OPS,
        ):
            raise PermissionDeniedError("Instance", instance_id)

        # Check state - must be running
        if instance.status != InstanceStatus.RUNNING:
            raise InvalidStateError(
                "Instance",
                instance_id,
                instance.status.value,
                "running",
            )

        # Must have pod_name to resize
        if not instance.pod_name:
            raise InvalidStateError(
                "Instance",
                instance_id,
                "no_pod",
                "running with pod",
            )

        # CRITICAL: Validate memory_gb >= current memory (no decreases!)
        # Memory decreases require pod restart which would kill the process
        current_memory_gb = instance.memory_gb
        if current_memory_gb is not None and memory_gb < current_memory_gb:
            raise InvalidStateError(
                "Instance",
                instance_id,
                f"memory_decrease_not_allowed (current={current_memory_gb}GB, requested={memory_gb}GB)",
                "memory increase only",
            )

        # Check governance: memory_gb <= settings.sizing_max_memory_gb (32)
        settings = get_settings()
        if memory_gb > settings.sizing_max_memory_gb:
            raise InvalidStateError(
                "Instance",
                instance_id,
                f"memory_exceeds_max ({memory_gb}GB > {int(settings.sizing_max_memory_gb)}GB)",
                f"memory <= {int(settings.sizing_max_memory_gb)}GB",
            )

        # Update K8s pod resources (Guaranteed QoS: request == limit)
        if self._k8s_service:
            await self._k8s_service.resize_pod_memory(
                pod_name=instance.pod_name,
                memory_request=f"{memory_gb}Gi",
                memory_limit=f"{memory_gb}Gi",
            )

        # Update database
        return await self._instance_repo.update_memory_gb(instance_id, memory_gb)

    async def get_progress(self, instance_id: int) -> dict[str, Any]:
        """Get instance loading progress.

        Args:
            instance_id: Instance ID

        Returns:
            Progress dictionary with phase and step information

        Raises:
            NotFoundError: If instance not found
        """
        # Get instance (this also verifies it exists)
        instance = await self.get_instance(instance_id)

        # Return progress or empty dict
        return instance.progress or {"phase": "unknown", "steps": []}
