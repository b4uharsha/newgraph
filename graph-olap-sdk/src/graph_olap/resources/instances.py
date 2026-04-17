"""Instance resource management."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from graph_olap_schemas import WrapperType

from graph_olap.exceptions import InstanceFailedError, TimeoutError
from graph_olap.models.common import PaginatedList
from graph_olap.models.instance import Instance, InstanceProgress

if TYPE_CHECKING:
    from graph_olap.config import Config
    from graph_olap.http import HTTPClient
    from graph_olap.instance.connection import InstanceConnection


def _normalize_duration(value: int | str | None) -> str | None:
    """Convert duration to ISO 8601 format.

    Args:
        value: Duration as integer hours, string hours, or ISO 8601 string

    Returns:
        ISO 8601 duration string or None

    Examples:
        48 -> "PT48H"
        "48" -> "PT48H"
        "PT48H" -> "PT48H"
    """
    if value is None:
        return None

    # Already ISO 8601 format
    if isinstance(value, str) and value.startswith("PT"):
        return value

    # Convert to integer hours
    try:
        hours = int(value)
        return f"PT{hours}H"
    except (ValueError, TypeError):
        # Invalid format, return as-is and let API validation fail
        return str(value)


class InstanceResource:
    """Manage graph instances.

    Instances are running graph databases loaded from snapshots.
    They support Cypher queries and graph algorithms.

    Example:
        >>> client = GraphOLAPClient(api_url=api_url, username="user@example.com")

        >>> # Create and wait for instance
        >>> instance = client.instances.create_and_wait(
        ...     snapshot_id=1,
        ...     name="Analysis Instance",
        ... )

        >>> # Connect for queries
        >>> conn = client.instances.connect(instance.id)
        >>> result = conn.query("MATCH (n) RETURN count(n)")
    """

    def __init__(self, http: HTTPClient, config: Config):
        """Initialize instance resource.

        Args:
            http: HTTP client for API requests
            config: Client configuration
        """
        self._http = http
        self._config = config

    def list(
        self,
        *,
        snapshot_id: int | None = None,
        owner: str | None = None,
        status: str | None = None,
        search: str | None = None,
        created_after: str | None = None,
        created_before: str | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        offset: int = 0,
        limit: int = 50,
    ) -> PaginatedList[Instance]:
        """List instances with optional filters.

        Args:
            snapshot_id: Filter by snapshot_id
            owner: Filter by owner_id
            status: Filter by status (starting, running, stopping, failed)
            search: Text search on name, description
            created_after: Filter by created_at >= timestamp (ISO 8601)
            created_before: Filter by created_at <= timestamp (ISO 8601)
            sort_by: Sort field (name, created_at, status, last_activity_at)
            sort_order: Sort direction (asc, desc)
            offset: Number of records to skip
            limit: Max records to return (max 100)

        Returns:
            Paginated list of Instance objects
        """
        params: dict[str, Any] = {
            "offset": offset,
            "limit": min(limit, 100),
            "sort_by": sort_by,
            "sort_order": sort_order,
        }
        if snapshot_id is not None:
            params["snapshot_id"] = snapshot_id
        if owner:
            params["owner"] = owner
        if status:
            params["status"] = status
        if search:
            params["search"] = search
        if created_after:
            params["created_after"] = created_after
        if created_before:
            params["created_before"] = created_before

        response = self._http.get("/api/instances", params=params)
        return PaginatedList(
            items=[Instance.from_api_response(i) for i in response["data"]],
            total=response["meta"]["total"],
            offset=response["meta"]["offset"],
            limit=response["meta"]["limit"],
        )

    def get(self, instance_id: int) -> Instance:
        """Get an instance by ID.

        Args:
            instance_id: Instance ID

        Returns:
            Instance object

        Raises:
            NotFoundError: If instance doesn't exist
        """
        response = self._http.get(f"/api/instances/{instance_id}")
        return Instance.from_api_response(response["data"])

    # =========================================================================
    # DEPRECATED: Use create_from_mapping() instead
    # Commented out as part of API simplification - 2025-01
    # =========================================================================
    # def create(
    #     self,
    #     snapshot_id: int,
    #     name: str,
    #     wrapper_type: WrapperType,
    #     *,
    #     description: str | None = None,
    #     ttl: int | str | None = None,
    #     inactivity_timeout: int | str | None = None,
    #     cpu_cores: int | None = None,
    # ) -> Instance:
    #     """Create a new graph instance from a snapshot.
    #
    #     Args:
    #         snapshot_id: Source snapshot ID (must be 'ready')
    #         name: Display name
    #         wrapper_type: Graph database wrapper type (REQUIRED - must be explicitly specified)
    #         description: Optional description
    #         ttl: Time-to-live (hours as int/str or ISO 8601 duration like "PT24H")
    #         inactivity_timeout: Inactivity timeout (hours as int/str or ISO 8601 duration)
    #         cpu_cores: CPU cores for the instance (1-8)
    #
    #     Returns:
    #         Instance object (status will be 'starting')
    #
    #     Raises:
    #         InvalidStateError: If snapshot is not 'ready'
    #         ConcurrencyLimitError: If instance limits exceeded
    #     """
    #     # Handle both WrapperType enum and string
    #     wrapper_type_str = wrapper_type.value if hasattr(wrapper_type, "value") else wrapper_type
    #     body: dict[str, Any] = {
    #         "snapshot_id": snapshot_id,
    #         "wrapper_type": wrapper_type_str,
    #         "name": name,
    #     }
    #     if description:
    #         body["description"] = description
    #
    #     # Normalize durations to ISO 8601 format
    #     normalized_ttl = _normalize_duration(ttl)
    #     if normalized_ttl:
    #         body["ttl"] = normalized_ttl
    #
    #     normalized_timeout = _normalize_duration(inactivity_timeout)
    #     if normalized_timeout:
    #         body["inactivity_timeout"] = normalized_timeout
    #
    #     if cpu_cores is not None:
    #         body["cpu_cores"] = cpu_cores
    #
    #     response = self._http.post("/api/instances", json=body)
    #     return Instance.from_api_response(response["data"])

    def update(
        self,
        instance_id: int,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> Instance:
        """Update instance metadata.

        Args:
            instance_id: Instance ID
            name: New name (optional)
            description: New description (optional)

        Returns:
            Updated Instance object

        Raises:
            NotFoundError: If instance doesn't exist
            PermissionDeniedError: If not owner or admin

        Example:
            >>> instance = client.instances.update(
            ...     instance_id=123,
            ...     name="Renamed Instance",
            ...     description="Updated description",
            ... )
        """
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description

        response = self._http.put(f"/api/instances/{instance_id}", json=body)
        return Instance.from_api_response(response["data"])

    def terminate(self, instance_id: int) -> None:
        """Terminate and delete an instance.

        Immediately deletes the K8s pod and removes the instance from the database.

        Args:
            instance_id: Instance ID to terminate

        Raises:
            NotFoundError: If instance doesn't exist
            PermissionDeniedError: If not owner or admin
            InvalidStateError: If instance is not running or starting
        """
        self._http.delete(f"/api/instances/{instance_id}")

    def set_lifecycle(
        self,
        instance_id: int,
        *,
        ttl: str | None = None,
        inactivity_timeout: str | None = None,
    ) -> Instance:
        """Set lifecycle parameters for an instance.

        Use this to extend or modify the TTL or inactivity timeout of a
        running instance after creation.

        Args:
            instance_id: Instance ID
            ttl: Time-to-live (ISO 8601 duration, e.g., "PT48H") or None to clear
            inactivity_timeout: Inactivity timeout (ISO 8601 duration) or None to clear

        Returns:
            Updated Instance object

        Example:
            >>> instance = client.instances.set_lifecycle(123, ttl="PT72H")
            >>> print(f"New expiry: {instance.expires_at}")
        """
        body: dict[str, Any] = {}
        if ttl is not None:
            body["ttl"] = ttl
        if inactivity_timeout is not None:
            body["inactivity_timeout"] = inactivity_timeout

        response = self._http.put(f"/api/instances/{instance_id}/lifecycle", json=body)
        return Instance.from_api_response(response["data"])

    def update_cpu(self, instance_id: int, cpu_cores: int) -> Instance:
        """Update CPU cores for a running instance.

        Args:
            instance_id: Instance ID
            cpu_cores: CPU cores (1-8)

        Returns:
            Updated Instance object

        Raises:
            InvalidStateError: If instance is not running

        Example:
            >>> instance = client.instances.update_cpu(123, cpu_cores=4)
            >>> print(f"Updated to {instance.cpu_cores} cores")
        """
        body = {"cpu_cores": cpu_cores}
        response = self._http.put(f"/api/instances/{instance_id}/cpu", json=body)
        return Instance.from_api_response(response["data"])

    def update_memory(self, instance_id: int, memory_gb: int) -> Instance:
        """Upgrade memory for a running instance.

        Uses K8s in-place resize (no restart required for increases).
        Only memory INCREASES are allowed - decreases would kill the process.

        Args:
            instance_id: Instance ID
            memory_gb: Memory in GB (2-32, must be >= current)

        Returns:
            Updated Instance object

        Raises:
            InvalidStateError: If instance is not running or memory decrease attempted
            ValidationError: If memory_gb exceeds maximum (32GB)

        Example:
            >>> instance = client.instances.update_memory(123, memory_gb=8)
            >>> print(f"Upgraded to {instance.memory_gb}GB")
        """
        body = {"memory_gb": memory_gb}
        response = self._http.put(f"/api/instances/{instance_id}/memory", json=body)
        return Instance.from_api_response(response["data"])

    def extend_ttl(self, instance_id: int, hours: int = 24) -> Instance:
        """Extend instance TTL by specified hours from current expiry.

        Convenience method matching UX "Extend TTL" button behavior.
        Calculates new expiry as current_expiry + hours.

        Args:
            instance_id: Instance ID
            hours: Hours to add to current TTL (default: 24)

        Returns:
            Updated Instance object

        Raises:
            ValidationError: If extension would exceed maximum TTL (7 days from creation)

        Example:
            >>> instance = client.instances.extend_ttl(123)  # +24 hours
            >>> instance = client.instances.extend_ttl(123, hours=48)  # +48 hours
        """
        instance = self.get(instance_id)

        if instance.expires_at is None:
            # No current TTL - set absolute expiry
            new_expiry = datetime.now(timezone.utc) + timedelta(hours=hours)
        else:
            # Extend from current expiry
            new_expiry = instance.expires_at + timedelta(hours=hours)

        # Calculate TTL duration from now
        ttl_seconds = int((new_expiry - datetime.now(timezone.utc)).total_seconds())
        ttl_hours = max(1, ttl_seconds // 3600)  # At least 1 hour

        return self.set_lifecycle(instance_id=instance_id, ttl=f"PT{ttl_hours}H")

    def get_progress(self, instance_id: int) -> InstanceProgress:
        """Get detailed startup progress for an instance.

        Args:
            instance_id: Instance ID

        Returns:
            InstanceProgress with phase, steps, and completion info
        """
        response = self._http.get(f"/api/instances/{instance_id}/progress")
        return InstanceProgress.from_api_response(response["data"])

    def get_health(self, instance_id: int, *, timeout: float = 5.0) -> dict[str, object]:
        """Get health status directly from the wrapper instance.

        This calls the wrapper's /health endpoint directly (not the control-plane API).
        Useful for verifying the wrapper is externally reachable and responding.

        Args:
            instance_id: Instance ID
            timeout: HTTP request timeout in seconds

        Returns:
            Health response from wrapper (typically {"status": "healthy", ...})

        Raises:
            InvalidStateError: If instance is not running or has no URL
            ConnectionError: If wrapper is not reachable

        Example:
            >>> health = client.instances.get_health(123)
            >>> print(health["status"])  # "healthy"
        """
        import os

        import httpx

        from graph_olap.exceptions import InvalidStateError

        instance = self.get(instance_id)

        if instance.status != "running":
            raise InvalidStateError(
                f"Instance {instance_id} is not running (status: {instance.status})"
            )

        # Construct health URL — prefer external URL, fall back to in-cluster DNS (S6)
        in_cluster_mode = os.environ.get("GRAPH_OLAP_IN_CLUSTER_MODE", "").lower() == "true"

        if instance.instance_url:
            # External: Use ingress URL (preferred — reachable from notebooks & CI)
            health_url = f"{instance.instance_url.rstrip('/')}/health"
        elif in_cluster_mode and instance.pod_name:
            # In-cluster fallback: Use direct service DNS
            url_slug = instance.pod_name.replace("wrapper-", "")
            namespace = os.environ.get("GRAPH_OLAP_NAMESPACE", "e2e-test")
            health_url = f"http://wrapper-{url_slug}.{namespace}.svc.cluster.local:8000/health"
        else:
            raise InvalidStateError(f"Instance {instance_id} has no URL available")

        headers = {}
        hc_kwargs: dict = {"timeout": timeout, "headers": headers, "verify": self._config.verify}
        if self._config.proxy:
            hc_kwargs["proxy"] = self._config.proxy

        try:
            response = httpx.get(health_url, **hc_kwargs)
            response.raise_for_status()
            return response.json()
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            raise ConnectionError(
                f"Cannot reach wrapper health endpoint for instance {instance_id} at {health_url}: {e}"
            ) from e
        except httpx.HTTPStatusError as e:
            raise ConnectionError(
                f"Wrapper health endpoint returned error {e.response.status_code} for instance {instance_id}"
            ) from e

    def check_health(self, instance_id: int, *, timeout: float = 5.0) -> bool:
        """Check if wrapper instance is healthy and reachable.

        Convenience method that returns True/False instead of raising exceptions.

        Args:
            instance_id: Instance ID
            timeout: HTTP request timeout in seconds

        Returns:
            True if wrapper is healthy and reachable, False otherwise

        Example:
            >>> if client.instances.check_health(123):
            ...     print("Instance is healthy!")
        """
        try:
            health = self.get_health(instance_id, timeout=timeout)
            return health.get("status") == "healthy"
        except Exception:
            return False

    def wait_until_running(
        self,
        instance_id: int,
        *,
        timeout: int = 300,
        poll_interval: int = 5,
    ) -> Instance:
        """Wait for an instance to become running.

        Use this method after create() to wait for the instance to finish
        starting. For convenience, you can also use create_and_wait() which
        combines both operations.

        Args:
            instance_id: Instance ID to wait for
            timeout: Maximum time to wait in seconds
            poll_interval: Time between status checks in seconds

        Returns:
            Instance object with status='running'

        Raises:
            TimeoutError: If instance doesn't start within timeout
            InstanceFailedError: If instance status becomes 'failed' or 'terminated'

        Example:
            >>> instance = client.instances.create(mapping_id=1, name="Test", ...)
            >>> instance = client.instances.wait_until_running(instance.id)
            >>> conn = client.instances.connect(instance.id)
        """
        start = time.time()

        while time.time() - start < timeout:
            instance = self.get(instance_id)

            if instance.status == "running":
                return instance

            if instance.status == "failed":
                raise InstanceFailedError(
                    f"Instance {instance_id} failed: {instance.error_message or 'Unknown error'}"
                )

            if instance.status == "terminated":
                raise InstanceFailedError(
                    f"Instance {instance_id} was terminated during startup"
                )

            time.sleep(poll_interval)

        raise TimeoutError(f"Instance {instance_id} did not start within {timeout}s")

    # =========================================================================
    # DEPRECATED: Use create_from_mapping_and_wait() instead
    # Commented out as part of API simplification - 2025-01
    # =========================================================================
    # def create_and_wait(
    #     self,
    #     snapshot_id: int,
    #     name: str,
    #     wrapper_type: WrapperType,
    #     *,
    #     description: str | None = None,
    #     ttl: int | str | None = None,
    #     inactivity_timeout: int | str | None = None,
    #     cpu_cores: int | None = None,
    #     timeout: int = 300,
    #     poll_interval: int = 5,
    #     on_progress: Callable[[str, int, int], None] | None = None,
    # ) -> Instance:
    #     """Create an instance and wait for it to become running.
    #
    #     Args:
    #         snapshot_id: Source snapshot ID
    #         name: Display name
    #         wrapper_type: Graph database wrapper type (REQUIRED - must be explicitly specified)
    #         description: Optional description
    #         ttl: Time-to-live (hours as int/str or ISO 8601 duration like "PT24H")
    #         inactivity_timeout: Inactivity timeout (hours as int/str or ISO 8601 duration)
    #         cpu_cores: CPU cores for the instance (1-8)
    #         timeout: Maximum wait time in seconds
    #         poll_interval: Time between status checks
    #         on_progress: Optional callback(phase, completed_steps, total_steps)
    #
    #     Returns:
    #         Instance object with status='running'
    #
    #     Example:
    #         >>> instance = client.instances.create_and_wait(
    #         ...     snapshot_id=1,
    #         ...     name="Quick Analysis",
    #         ...     wrapper_type=WrapperType.FALKORDB,
    #         ...     ttl=48  # 48 hours
    #         ... )
    #         >>> conn = client.instances.connect(instance.id)
    #     """
    #     instance = self.create(
    #         snapshot_id=snapshot_id,
    #         name=name,
    #         wrapper_type=wrapper_type,
    #         description=description,
    #         ttl=ttl,
    #         inactivity_timeout=inactivity_timeout,
    #         cpu_cores=cpu_cores,
    #     )
    #
    #     start = time.time()
    #
    #     # Phase 1: Wait for status="running" (wrapper has loaded data)
    #     while time.time() - start < timeout:
    #         # Get instance status from the instance object itself
    #         instance = self.get(instance.id)
    #
    #         # Get progress for progress callback
    #         if on_progress:
    #             progress = self.get_progress(instance.id)
    #             on_progress(progress.phase, progress.completed_steps, progress.total_steps)
    #
    #         if instance.status == "running":
    #             break  # Continue to Phase 2
    #
    #         if instance.status == "failed":
    #             error_msg = getattr(instance, "error_message", None) or "Unknown error"
    #             raise InstanceFailedError(
    #                 f"Instance {instance.id} failed: {error_msg}"
    #             )
    #
    #         time.sleep(poll_interval)
    #     else:
    #         # Timeout waiting for status="running"
    #         raise TimeoutError(f"Instance {instance.id} did not start within {timeout}s")
    #
    #     # Phase 2: Wait for wrapper HTTP service to be ready
    #     # Construct health check URL based on environment
    #     import os
    #
    #     import httpx
    #
    #     # Skip health check if configured (for remote cluster testing via port-forward)
    #     # When testing against a remote cluster, the external URL may not be reachable
    #     # but the instance is still valid and running
    #     skip_health_check = os.environ.get("GRAPH_OLAP_SKIP_HEALTH_CHECK", "").lower() == "true"
    #     if skip_health_check:
    #         return instance
    #
    #     in_cluster_mode = os.environ.get("GRAPH_OLAP_IN_CLUSTER_MODE", "").lower() == "true"
    #
    #     if in_cluster_mode and instance.pod_name:
    #         # In-cluster: Use direct service DNS
    #         # Extract URL slug from pod name (format: wrapper-{slug})
    #         url_slug = instance.pod_name.replace("wrapper-", "")
    #         namespace = os.environ.get("GRAPH_OLAP_NAMESPACE", "e2e-test")
    #         health_url = f"http://wrapper-{url_slug}.{namespace}.svc.cluster.local:8000/health"
    #     elif instance.instance_url:
    #         # External: Use ingress URL
    #         health_url = f"{instance.instance_url.rstrip('/')}/health"
    #     else:
    #         # No URL available - return immediately (shouldn't happen in normal operation)
    #         return instance
    #
    #     # Wait for wrapper HTTP service to respond
    #     max_retries = 10
    #     base_delay = 0.5  # 500ms initial delay
    #
    #     headers = {}
    #
    #     for attempt in range(max_retries):
    #         if time.time() - start >= timeout:
    #             mode = "in-cluster" if in_cluster_mode else "external"
    #             raise TimeoutError(
    #                 f"Instance {instance.id} is running but wrapper not reachable at {health_url} "
    #                 f"({mode} mode, timeout={timeout}s)"
    #             )
    #
    #         try:
    #             response = httpx.get(health_url, timeout=5.0, headers=headers)
    #             if response.status_code == 200:
    #                 # Wrapper HTTP service is fully ready
    #                 return instance
    #         except (httpx.ConnectError, httpx.TimeoutException):
    #             # Expected while wrapper initializes
    #             pass
    #
    #         # Exponential backoff
    #         if attempt < max_retries - 1:
    #             delay = min(base_delay * (2**attempt), 5.0)
    #             time.sleep(delay)
    #
    #     # Health check timeout
    #     mode = "in-cluster" if in_cluster_mode else "external"
    #     raise TimeoutError(
    #         f"Instance {instance.id} is running but wrapper not reachable at {health_url} ({mode} mode)"
    #     )

    def create(
        self,
        mapping_id: int,
        name: str,
        wrapper_type: WrapperType,
        *,
        mapping_version: int | None = None,
        description: str | None = None,
        ttl: int | str | None = None,
        inactivity_timeout: int | str | None = None,
        cpu_cores: int | None = None,
    ) -> Instance:
        """Create a new graph instance from a mapping.

        Creates a snapshot automatically and queues instance creation.
        The instance will initially have status='waiting_for_snapshot' while
        the snapshot is being created, then transition to 'starting' and
        finally 'running'.

        Args:
            mapping_id: Source mapping ID
            name: Display name for the instance
            wrapper_type: Graph database wrapper type (REQUIRED - must be explicitly specified)
            mapping_version: Mapping version to use (defaults to current)
            description: Optional description
            ttl: Time-to-live (hours as int/str or ISO 8601 duration like "PT24H")
            inactivity_timeout: Inactivity timeout (hours as int/str or ISO 8601 duration)
            cpu_cores: CPU cores for the instance (1-8)

        Returns:
            Instance object (status will be 'waiting_for_snapshot')

        Raises:
            NotFoundError: If mapping doesn't exist
            InvalidStateError: If mapping version doesn't exist
            ConcurrencyLimitError: If instance limits exceeded

        Example:
            >>> instance = client.instances.create(
            ...     mapping_id=1,
            ...     name="Quick Analysis",
            ...     wrapper_type=WrapperType.FALKORDB,
            ... )
            >>> # Poll for status or use create_and_wait()
        """
        # Handle both WrapperType enum and string
        wrapper_type_str = wrapper_type.value if hasattr(wrapper_type, "value") else wrapper_type
        body: dict[str, Any] = {
            "mapping_id": mapping_id,
            "wrapper_type": wrapper_type_str,
            "name": name,
        }
        if mapping_version is not None:
            body["mapping_version"] = mapping_version
        if description:
            body["description"] = description

        # Normalize durations to ISO 8601 format
        normalized_ttl = _normalize_duration(ttl)
        if normalized_ttl:
            body["ttl"] = normalized_ttl

        normalized_timeout = _normalize_duration(inactivity_timeout)
        if normalized_timeout:
            body["inactivity_timeout"] = normalized_timeout

        if cpu_cores is not None:
            body["cpu_cores"] = cpu_cores

        response = self._http.post("/api/instances", json=body)
        return Instance.from_api_response(response["data"])

    def create_and_wait(
        self,
        mapping_id: int,
        name: str,
        wrapper_type: WrapperType,
        *,
        mapping_version: int | None = None,
        description: str | None = None,
        ttl: int | str | None = None,
        inactivity_timeout: int | str | None = None,
        cpu_cores: int | None = None,
        timeout: int = 900,
        poll_interval: int = 5,
        health_check_timeout: int = 180,  # Must exceed K8s startup probe budget (150s)
        on_progress: Callable[[str, int, int], None] | None = None,
    ) -> Instance:
        """Create instance from mapping and wait until running.

        This combines create() with polling until the instance is running.
        It handles the full lifecycle: waiting_for_snapshot -> starting -> running.

        Two-phase design with SEPARATE budgets:
        - Phase 1 uses ``timeout`` to wait for status='running'
        - Phase 2 uses ``health_check_timeout`` to verify the wrapper is reachable
        Phase 2 gets its own clock so it always has enough time for retries,
        regardless of how long Phase 1 took.

        Args:
            mapping_id: Source mapping ID
            name: Display name for the instance
            wrapper_type: Graph database wrapper type (REQUIRED - must be explicitly specified)
            mapping_version: Mapping version to use (defaults to current)
            description: Optional description
            ttl: Time-to-live (hours as int/str or ISO 8601 duration like "PT24H")
            inactivity_timeout: Inactivity timeout (hours as int/str or ISO 8601 duration)
            cpu_cores: CPU cores for the instance (1-8)
            timeout: Phase 1 budget — max wait for status='running' (default 900s)
            poll_interval: Time between status checks in seconds
            health_check_timeout: Phase 2 budget — max wait for wrapper HTTP ready (default 120s)
            on_progress: Optional callback(phase, completed_steps, total_steps)

        Returns:
            Instance object with status='running'

        Raises:
            NotFoundError: If mapping doesn't exist
            InvalidStateError: If mapping version doesn't exist
            ConcurrencyLimitError: If instance limits exceeded
            TimeoutError: If instance doesn't start within timeout
            InstanceFailedError: If instance status becomes 'failed' or 'terminated'
            SnapshotFailedError: If the snapshot creation fails

        Example:
            >>> def show_progress(phase, completed, total):
            ...     print(f"{phase}: {completed}/{total}")
            >>> instance = client.instances.create_and_wait(
            ...     mapping_id=1,
            ...     name="Quick Analysis",
            ...     wrapper_type=WrapperType.FALKORDB,
            ...     on_progress=show_progress,
            ... )
            >>> conn = client.instances.connect(instance.id)
        """
        from graph_olap.exceptions import SnapshotFailedError

        instance = self.create(
            mapping_id=mapping_id,
            name=name,
            wrapper_type=wrapper_type,
            mapping_version=mapping_version,
            description=description,
            ttl=ttl,
            inactivity_timeout=inactivity_timeout,
            cpu_cores=cpu_cores,
        )

        start = time.time()

        # Phase 1: Wait for status to transition from waiting_for_snapshot
        # Then wait for status="running"
        while time.time() - start < timeout:
            instance = self.get(instance.id)

            # Get progress for progress callback
            if on_progress:
                progress = self.get_progress(instance.id)
                on_progress(progress.phase, progress.completed_steps, progress.total_steps)

            if instance.status == "running":
                break  # Continue to Phase 2 (health check)

            if instance.status == "failed":
                error_msg = getattr(instance, "error_message", None) or "Unknown error"
                # Check if the failure was during snapshot creation
                error_code = getattr(instance, "error_code", None)
                if error_code and "SNAPSHOT" in error_code.upper():
                    raise SnapshotFailedError(
                        f"Snapshot creation failed for instance {instance.id}: {error_msg}"
                    )
                raise InstanceFailedError(
                    f"Instance {instance.id} failed: {error_msg}"
                )

            if instance.status == "terminated":
                raise InstanceFailedError(
                    f"Instance {instance.id} was terminated during startup"
                )

            time.sleep(poll_interval)
        else:
            # Timeout — do one final check in case the instance failed
            # between the last poll and the timeout
            instance = self.get(instance.id)
            if instance.status == "failed":
                error_msg = getattr(instance, "error_message", None) or "Unknown error"
                raise InstanceFailedError(
                    f"Instance {instance.id} failed: {error_msg}"
                )
            if instance.status == "terminated":
                raise InstanceFailedError(
                    f"Instance {instance.id} was terminated during startup"
                )
            raise TimeoutError(
                f"Instance {instance.id} did not start within {timeout}s "
                f"(last status: {instance.status})"
            )

        # Phase 2: Wait for wrapper HTTP service to be ready (SEPARATE budget)
        import os

        import httpx

        # Skip health check if configured
        skip_health_check = os.environ.get("GRAPH_OLAP_SKIP_HEALTH_CHECK", "").lower() == "true"
        if skip_health_check:
            return instance

        in_cluster_mode = os.environ.get("GRAPH_OLAP_IN_CLUSTER_MODE", "").lower() == "true"

        if in_cluster_mode and instance.pod_name:
            url_slug = instance.pod_name.replace("wrapper-", "")
            namespace = os.environ.get("GRAPH_OLAP_NAMESPACE", "e2e-test")
            health_url = f"http://wrapper-{url_slug}.{namespace}.svc.cluster.local:8000/health"
        elif instance.instance_url:
            health_url = f"{instance.instance_url.rstrip('/')}/health"
        else:
            return instance

        # Simple poll with its own clock — no retry limit, no exponential backoff.
        # Keeps polling until the wrapper responds or health_check_timeout expires.
        # Small data: wrapper ready in 3s. Large data: may take 60-120s to load.
        health_start = time.time()
        mode = "in-cluster" if in_cluster_mode else "external"
        hc_kwargs: dict = {"timeout": 5.0, "verify": self._config.verify}
        if self._config.proxy:
            hc_kwargs["proxy"] = self._config.proxy

        health_poll_iter = 0
        while time.time() - health_start < health_check_timeout:
            health_poll_iter += 1

            # Every 4th iteration, check if the instance has failed in the
            # control plane.  Without this, a crashed wrapper burns the full
            # health_check_timeout before surfacing a misleading error.
            if health_poll_iter % 4 == 0:
                try:
                    instance = self.get(instance.id)
                except Exception:
                    pass  # Transient CP unreachability — continue polling wrapper health
                else:
                    if instance.status == "failed":
                        error_msg = getattr(instance, "error_message", None) or "Unknown error"
                        raise InstanceFailedError(
                            f"Instance {instance.id} failed during health check: {error_msg}"
                        )
                    if instance.status == "terminated":
                        raise InstanceFailedError(
                            f"Instance {instance.id} was terminated during health check"
                        )

            try:
                response = httpx.get(health_url, **hc_kwargs)
                if response.status_code == 200:
                    return instance
            except (httpx.ConnectError, httpx.TimeoutException):
                pass  # Expected while wrapper initializes or proxy routes propagate
            time.sleep(2)

        raise TimeoutError(
            f"Instance {instance.id} is running but wrapper not reachable at {health_url} "
            f"({mode} mode, health_check_timeout={health_check_timeout}s)"
        )

    def connect(self, instance_id: int) -> InstanceConnection:
        """Connect to a running instance for queries and algorithms.

        If you used create_and_wait() to create the instance, it will already be
        fully ready and this will succeed immediately. For instances that were
        created separately, this performs a basic health check.

        Args:
            instance_id: Instance ID to connect to

        Returns:
            InstanceConnection object for graph operations

        Raises:
            InvalidStateError: If instance is not 'running'
            ConnectionError: If instance is not reachable

        Example:
            >>> # Create and connect (recommended)
            >>> instance = client.instances.create_and_wait(snapshot_id=1, name="Analysis")
            >>> conn = client.instances.connect(instance.id)  # Immediate connection
            >>>
            >>> # Or connect to existing instance
            >>> conn = client.instances.connect(123)
            >>> result = conn.query("MATCH (n:Customer) RETURN n LIMIT 10")
        """
        from graph_olap.exceptions import InvalidStateError
        from graph_olap.instance.connection import InstanceConnection

        instance = self.get(instance_id)

        if instance.status != "running":
            raise InvalidStateError(
                f"Instance {instance_id} is not running (status: {instance.status})"
            )

        # Construct connection URL based on environment
        import os

        import httpx

        in_cluster_mode = os.environ.get("GRAPH_OLAP_IN_CLUSTER_MODE", "").lower() == "true"
        skip_health_check = os.environ.get("GRAPH_OLAP_SKIP_HEALTH_CHECK", "").lower() == "true"

        if instance.instance_url:
            # External: Use ingress URL (preferred — reachable from notebooks & CI)
            wrapper_url = instance.instance_url
            health_url = f"{wrapper_url.rstrip('/')}/health"
        elif in_cluster_mode and instance.pod_name:
            # In-cluster fallback: Use direct service DNS
            url_slug = instance.pod_name.replace("wrapper-", "")
            namespace = os.environ.get("GRAPH_OLAP_NAMESPACE", "e2e-test")
            wrapper_url = f"http://wrapper-{url_slug}.{namespace}.svc.cluster.local:8000"
            health_url = f"{wrapper_url}/health"
        else:
            raise InvalidStateError(f"Instance {instance_id} has no URL available")

        # Health check with retry to handle instances that are still loading data.
        # The instance status may be "running" (pod started) but the wrapper may
        # not be serving requests yet (data still loading from GCS). Retry a few
        # times before giving up.
        if not skip_health_check:
            import time as _time

            headers = {}
            max_retries = 6  # 6 × 5s = 30s max wait
            last_error = None

            for attempt in range(max_retries):
                try:
                    hc_kwargs: dict = {"timeout": 5.0, "headers": headers, "verify": self._config.verify}
                    if self._config.proxy:
                        hc_kwargs["proxy"] = self._config.proxy
                    response = httpx.get(health_url, **hc_kwargs)
                    if response.status_code == 200:
                        break  # Healthy
                    last_error = ConnectionError(
                        f"Instance {instance_id} returned unhealthy status: {response.status_code}"
                    )
                except (httpx.ConnectError, httpx.TimeoutException) as e:
                    last_error = ConnectionError(
                        f"Cannot reach instance {instance_id} at {health_url}. Error: {e}"
                    )

                if attempt < max_retries - 1:
                    _time.sleep(5)
            else:
                # All retries exhausted
                raise last_error

        return InstanceConnection(
            instance_url=wrapper_url,
            instance_id=instance_id,
            username=self._config.username,
            name=instance.name,
            status=instance.status,
            snapshot_id=instance.snapshot_id,
            use_case_id=self._config.use_case_id,
            proxy=self._config.proxy,
            verify=self._config.verify,
        )
