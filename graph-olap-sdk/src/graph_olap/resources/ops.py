"""Ops resource for config and cluster management."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from graph_olap.models.ops import (
    ClusterHealth,
    ClusterInstances,
    ConcurrencyConfig,
    ExportConfig,
    LifecycleConfig,
    MaintenanceMode,
    ResourceLifecycleConfig,
)

if TYPE_CHECKING:
    from graph_olap.http import HTTPClient


class OpsResource:
    """Manage cluster configuration and health.

    Provides access to operational endpoints for config management,
    cluster health monitoring, and instance capacity tracking.
    All operations require Ops role.

    Example:
        >>> client = GraphOLAPClient(api_url=api_url, username="ops_user")

        >>> # Get lifecycle configuration
        >>> lifecycle = client.ops.get_lifecycle_config()
        >>> print(lifecycle.instance.default_ttl)

        >>> # Check cluster health
        >>> health = client.ops.get_cluster_health()
        >>> print(health.status)

        >>> # Get cluster instance summary
        >>> instances = client.ops.get_cluster_instances()
        >>> print(f"Total: {instances.total}, Available: {instances.limits.cluster_available}")
    """

    def __init__(self, http: HTTPClient):
        """Initialize ops resource.

        Args:
            http: HTTP client for API requests
        """
        self._http = http

    # Config: Lifecycle

    def get_lifecycle_config(self) -> LifecycleConfig:
        """Get lifecycle configuration for all resource types.

        Returns default TTL, inactivity timeout, and max TTL settings
        for mappings, snapshots, and instances.

        Returns:
            LifecycleConfig with settings for each resource type

        Raises:
            ForbiddenError: If user doesn't have Ops role
        """
        response = self._http.get("/api/config/lifecycle")
        return LifecycleConfig.from_api_response(response["data"])

    def update_lifecycle_config(
        self,
        *,
        mapping: ResourceLifecycleConfig | dict[str, Any] | None = None,
        snapshot: ResourceLifecycleConfig | dict[str, Any] | None = None,
        instance: ResourceLifecycleConfig | dict[str, Any] | None = None,
    ) -> bool:
        """Update lifecycle configuration for resource types.

        Only provided values are updated; omitted values remain unchanged.

        Args:
            mapping: Lifecycle config for mappings
            snapshot: Lifecycle config for snapshots
            instance: Lifecycle config for instances

        Returns:
            True if update succeeded

        Raises:
            ForbiddenError: If user doesn't have Ops role
            ValidationError: If values are invalid

        Example:
            >>> # Update instance default TTL
            >>> client.ops.update_lifecycle_config(
            ...     instance={"default_ttl": "PT24H"}
            ... )
        """
        body: dict[str, Any] = {}

        if mapping is not None:
            if isinstance(mapping, ResourceLifecycleConfig):
                body["mapping"] = {
                    "default_ttl": mapping.default_ttl,
                    "default_inactivity": mapping.default_inactivity,
                    "max_ttl": mapping.max_ttl,
                }
            else:
                body["mapping"] = mapping

        if snapshot is not None:
            if isinstance(snapshot, ResourceLifecycleConfig):
                body["snapshot"] = {
                    "default_ttl": snapshot.default_ttl,
                    "default_inactivity": snapshot.default_inactivity,
                    "max_ttl": snapshot.max_ttl,
                }
            else:
                body["snapshot"] = snapshot

        if instance is not None:
            if isinstance(instance, ResourceLifecycleConfig):
                body["instance"] = {
                    "default_ttl": instance.default_ttl,
                    "default_inactivity": instance.default_inactivity,
                    "max_ttl": instance.max_ttl,
                }
            else:
                body["instance"] = instance

        response = self._http.put("/api/config/lifecycle", json=body)
        return response["data"].get("updated", False)

    # Config: Concurrency

    def get_concurrency_config(self) -> ConcurrencyConfig:
        """Get concurrency limits configuration.

        Returns per-analyst and cluster-total instance limits.

        Returns:
            ConcurrencyConfig with limit values

        Raises:
            ForbiddenError: If user doesn't have Ops role
        """
        response = self._http.get("/api/config/concurrency")
        return ConcurrencyConfig.from_api_response(response["data"])

    def update_concurrency_config(
        self,
        *,
        per_analyst: int,
        cluster_total: int,
    ) -> ConcurrencyConfig:
        """Update concurrency limits configuration.

        Args:
            per_analyst: Max instances per analyst (1-100)
            cluster_total: Max instances cluster-wide (1-1000)

        Returns:
            Updated ConcurrencyConfig

        Raises:
            ForbiddenError: If user doesn't have Ops role
            ValidationError: If values out of range
        """
        response = self._http.put(
            "/api/config/concurrency",
            json={
                "per_analyst": per_analyst,
                "cluster_total": cluster_total,
            },
        )
        return ConcurrencyConfig.from_api_response(response["data"])

    # Config: Maintenance

    def get_maintenance_mode(self) -> MaintenanceMode:
        """Get maintenance mode status.

        Returns:
            MaintenanceMode with enabled status and message

        Raises:
            ForbiddenError: If user doesn't have Ops role
        """
        response = self._http.get("/api/config/maintenance")
        return MaintenanceMode.from_api_response(response["data"])

    def set_maintenance_mode(
        self,
        enabled: bool,
        message: str = "",
    ) -> MaintenanceMode:
        """Set maintenance mode.

        When enabled, new instance creation is blocked and users
        see the maintenance message.

        Args:
            enabled: Whether maintenance mode is active
            message: Message to display to users

        Returns:
            Updated MaintenanceMode

        Raises:
            ForbiddenError: If user doesn't have Ops role
        """
        response = self._http.put(
            "/api/config/maintenance",
            json={
                "enabled": enabled,
                "message": message,
            },
        )
        return MaintenanceMode.from_api_response(response["data"])

    # Config: Export

    def get_export_config(self) -> ExportConfig:
        """Get export configuration.

        Returns:
            ExportConfig with max duration settings

        Raises:
            ForbiddenError: If user doesn't have Ops role
        """
        response = self._http.get("/api/config/export")
        return ExportConfig.from_api_response(response["data"])

    def update_export_config(
        self,
        *,
        max_duration_seconds: int,
    ) -> ExportConfig:
        """Update export configuration.

        Args:
            max_duration_seconds: Max export job duration (60-86400 seconds)

        Returns:
            Updated ExportConfig

        Raises:
            ForbiddenError: If user doesn't have Ops role
            ValidationError: If duration out of range
        """
        response = self._http.put(
            "/api/config/export",
            json={"max_duration_seconds": max_duration_seconds},
        )
        return ExportConfig.from_api_response(response["data"])

    # Cluster

    def get_cluster_health(self) -> ClusterHealth:
        """Get cluster health status.

        Checks connectivity to database, kubernetes, and starburst.

        Returns:
            ClusterHealth with overall status and component details

        Raises:
            ForbiddenError: If user doesn't have Ops role
        """
        response = self._http.get("/api/cluster/health")
        return ClusterHealth.from_api_response(response["data"])

    def get_cluster_instances(self) -> ClusterInstances:
        """Get cluster-wide instance summary.

        Returns total instances, breakdowns by status and owner,
        and current capacity limits.

        Returns:
            ClusterInstances with counts and limits

        Raises:
            ForbiddenError: If user doesn't have Ops role
        """
        response = self._http.get("/api/cluster/instances")
        return ClusterInstances.from_api_response(response["data"])

    # Metrics

    def get_metrics(self) -> str:
        """Get Prometheus metrics from control plane.

        Returns metrics for background jobs, reconciliation loops,
        lifecycle enforcement, and general system health.

        Returns:
            Prometheus metrics in text/plain format

        Raises:
            ForbiddenError: If user doesn't have Ops role

        Example:
            >>> client = GraphOLAPClient(api_url, username="ops_user")
            >>> metrics = client.ops.get_metrics()
            >>> # Check if background jobs are running
            >>> assert 'job_name="reconciliation"' in metrics
            >>> assert 'job_name="lifecycle"' in metrics
        """
        return self._http.get_text("/metrics")

    # Background Jobs

    def trigger_job(self, job_name: str, reason: str = "manual-trigger") -> dict[str, Any]:
        """Manually trigger background job execution.

        Requires: Ops or admin role

        Use cases:
        - Production smoke tests
        - Manual reconciliation after incident
        - Debugging

        Rate limit: 1 trigger per job per minute

        Args:
            job_name: Job to trigger (reconciliation, lifecycle, export_reconciliation, schema_cache)
            reason: Reason for manual trigger (audit log)

        Returns:
            Job trigger confirmation with status

        Raises:
            ForbiddenError: If user doesn't have Ops or admin role
            RateLimitError: If job triggered too recently (< 60s)
            NotFoundError: If job name is invalid

        Example:
            >>> client = GraphOLAPClient(api_url=api_url, username="ops-user")
            >>> client.ops.trigger_job("reconciliation", reason="smoke-test")
            {'job_name': 'reconciliation', 'triggered_at': '...', 'status': 'queued'}
        """
        response = self._http.post(
            "/api/ops/jobs/trigger",
            json={"job_name": job_name, "reason": reason}
        )
        return response["data"]

    def get_job_status(self) -> dict[str, Any]:
        """Get status of all background jobs.

        Requires: Ops or admin role

        Returns:
            Job status information including next run times

        Raises:
            ForbiddenError: If user doesn't have Ops or admin role

        Example:
            >>> status = client.ops.get_job_status()
            >>> for job in status['jobs']:
            ...     print(f"{job['name']}: next run at {job['next_run']}")
        """
        response = self._http.get("/api/ops/jobs/status")
        return response["data"]

    def get_state(self) -> dict[str, Any]:
        """Get system state summary.

        Requires: Ops or admin role

        Returns counts of instances, snapshots, export jobs by status.

        Returns:
            System state with resource counts

        Raises:
            ForbiddenError: If user doesn't have Ops or admin role

        Example:
            >>> state = client.ops.get_state()
            >>> print(f"Instances: {state['instances']['total']}")
            >>> print(f"By status: {state['instances']['by_status']}")
            >>> print(f"Without pod: {state['instances']['without_pod_name']}")
        """
        response = self._http.get("/api/ops/state")
        return response["data"]

    def get_export_jobs(
        self,
        status: str | None = None,
        limit: int = 100
    ) -> list[dict[str, Any]]:
        """Get export jobs for debugging.

        Requires: Ops or admin role

        Args:
            status: Filter by status (pending, claimed, completed, failed)
            limit: Max jobs to return (default 100, max 1000)

        Returns:
            List of export job details

        Raises:
            ForbiddenError: If user doesn't have Ops or admin role
            ValidationError: If status is invalid

        Example:
            >>> # Check for stale claimed jobs
            >>> claimed = client.ops.get_export_jobs(status="claimed")
            >>> for job in claimed:
            ...     print(f"Job {job['id']} claimed by {job['claimed_by']}")
        """
        params: dict[str, Any] = {}
        if status:
            params["status"] = status
        if limit:
            params["limit"] = limit

        response = self._http.get("/api/ops/export-jobs", params=params)
        return response["data"]["jobs"]
