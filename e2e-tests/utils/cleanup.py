"""Test resource cleanup utilities.

This module provides robust cleanup mechanisms for E2E tests to ensure
resources are properly cleaned up even when tests fail, while being
production-safe and idempotent.

Design Principles:
1. Tests are responsible for cleaning up their own resources
2. Cleanup happens in try/finally blocks (always executes)
3. Cleanup is idempotent - deleting non-existent resources just warns
4. Cleanup failures are collected and reported, causing test failure
5. Resources deleted in reverse creation order (instances → snapshots → mappings)
6. All cleanup attempts are logged for debugging

Usage:
    with ResourceTracker(client) as tracker:
        mapping = tracker.create_mapping(name="Test-Mapping")
        snapshot = tracker.create_snapshot(mapping_id=mapping.id, ...)
        instance = tracker.create_instance(snapshot_id=snapshot.id, ...)

        # Test code here...

    # Cleanup happens automatically in reverse order
    # If any cleanup fails, exception is raised with details
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from graph_olap import GraphOLAPClient
    from graph_olap.instance.connection import InstanceConnection

logger = logging.getLogger(__name__)


class ResourceType(Enum):
    """Types of resources that can be tracked for cleanup."""

    INSTANCE = "instance"
    SNAPSHOT = "snapshot"
    MAPPING = "mapping"
    GRAPH_PROPERTIES = "graph_properties"  # Algorithm properties on nodes


@dataclass
class TrackedResource:
    """A resource tracked for cleanup."""

    resource_type: ResourceType
    resource_id: int | str | None
    metadata: dict[str, Any]
    created_at: float  # timestamp

    def __repr__(self) -> str:
        return f"{self.resource_type.value}:{resource_id}"


@dataclass
class CleanupResult:
    """Result of attempting to clean up a resource."""

    resource: TrackedResource
    success: bool
    error: str | None = None
    skipped: bool = False  # True if resource didn't exist


class ResourceTracker:
    """Tracks resources created during tests and cleans them up.

    Example:
        with ResourceTracker(client) as tracker:
            mapping = tracker.create_mapping(name="TestMapping")
            # ... test code ...
        # Cleanup happens automatically
    """

    def __init__(
        self,
        client: GraphOLAPClient,
        username: str | None = None,
        fail_on_cleanup_error: bool = True,
    ):
        """Initialize resource tracker.

        Args:
            client: GraphOLAP client instance
            username: Username for filtering resources (optional)
            fail_on_cleanup_error: If True, raise exception if cleanup fails
        """
        self.client = client
        self.username = username
        self.fail_on_cleanup_error = fail_on_cleanup_error
        self.resources: list[TrackedResource] = []
        self.cleanup_results: list[CleanupResult] = []

    def __enter__(self) -> ResourceTracker:
        """Enter context - return self for use in with statement."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context - perform cleanup regardless of success/failure."""
        self.cleanup_all()

        # If cleanup had errors and we should fail on errors
        if self.fail_on_cleanup_error:
            failed = [r for r in self.cleanup_results if not r.success and not r.skipped]
            if failed:
                error_details = "\n".join(
                    f"  - {r.resource.resource_type.value} {r.resource.resource_id}: {r.error}"
                    for r in failed
                )
                raise CleanupError(f"Failed to cleanup {len(failed)} resource(s):\n{error_details}")

    def track(
        self,
        resource_type: ResourceType,
        resource_id: int | str | None,
        **metadata: Any,
    ) -> None:
        """Manually track a resource for cleanup.

        Notebooks should create resources using the SDK directly, then track them here.

        Example:
            # Create using SDK (test the real API)
            snapshot = client.snapshots.create_and_wait(mapping_id=1, name="Test")

            # Track for cleanup (test infrastructure)
            tracker.track(ResourceType.SNAPSHOT, snapshot.id, name="Test")

        Args:
            resource_type: Type of resource
            resource_id: ID of resource (or None for graph properties)
            **metadata: Additional metadata about the resource
        """
        resource = TrackedResource(
            resource_type=resource_type,
            resource_id=resource_id,
            metadata=metadata,
            created_at=time.time(),
        )
        self.resources.append(resource)
        logger.info(f"Tracking resource: {resource_type.value} {resource_id}")

    def track_graph_properties(
        self,
        conn: InstanceConnection,
        node_label: str,
        property_names: list[str],
    ) -> None:
        """Track graph properties written by algorithms for cleanup.

        Args:
            conn: Connection to instance
            node_label: Label of nodes that have the properties
            property_names: Names of properties to remove during cleanup
        """
        self.track(
            ResourceType.GRAPH_PROPERTIES,
            None,
            connection=conn,
            node_label=node_label,
            property_names=property_names,
        )

    def cleanup_all(self) -> list[CleanupResult]:
        """Clean up all tracked resources in reverse order.

        Returns:
            List of cleanup results for each resource
        """
        logger.info(f"Starting cleanup of {len(self.resources)} resource(s)")
        self.cleanup_results = []

        # Clean up in reverse order (instances before snapshots before mappings)
        for resource in reversed(self.resources):
            result = self._cleanup_resource(resource)
            self.cleanup_results.append(result)

        # Log summary
        successful = sum(1 for r in self.cleanup_results if r.success)
        skipped = sum(1 for r in self.cleanup_results if r.skipped)
        failed = sum(1 for r in self.cleanup_results if not r.success and not r.skipped)

        logger.info(
            f"Cleanup complete: {successful} deleted, {skipped} already gone, {failed} failed"
        )

        return self.cleanup_results

    def _cleanup_resource(self, resource: TrackedResource) -> CleanupResult:
        """Clean up a single resource.

        Args:
            resource: Resource to clean up

        Returns:
            Cleanup result indicating success/failure
        """
        logger.info(f"Cleaning up {resource.resource_type.value} {resource.resource_id}")

        try:
            if resource.resource_type == ResourceType.INSTANCE:
                return self._cleanup_instance(resource)
            elif resource.resource_type == ResourceType.SNAPSHOT:
                return self._cleanup_snapshot(resource)
            elif resource.resource_type == ResourceType.MAPPING:
                return self._cleanup_mapping(resource)
            elif resource.resource_type == ResourceType.GRAPH_PROPERTIES:
                return self._cleanup_graph_properties(resource)
            else:
                return CleanupResult(
                    resource=resource,
                    success=False,
                    error=f"Unknown resource type: {resource.resource_type}",
                )
        except Exception as e:
            logger.error(f"Cleanup failed for {resource.resource_type.value} {resource.resource_id}: {e}")
            return CleanupResult(resource=resource, success=False, error=str(e))

    def _cleanup_instance(self, resource: TrackedResource) -> CleanupResult:
        """Clean up an instance."""
        from graph_olap.exceptions import NotFoundError

        try:
            # Terminate immediately deletes the instance (K8s pod + DB record)
            logger.info(f"Terminating instance {resource.resource_id}")
            self.client.instances.terminate(resource.resource_id)

            # Verify deletion
            self._verify_resource_deleted(
                lambda: self.client.instances.get(resource.resource_id),
                resource,
            )

            return CleanupResult(resource=resource, success=True)

        except NotFoundError:
            logger.warning(f"Instance {resource.resource_id} already deleted (OK)")
            return CleanupResult(resource=resource, success=True, skipped=True)

    def _cleanup_snapshot(self, resource: TrackedResource) -> CleanupResult:
        """Clean up a snapshot."""
        from graph_olap.exceptions import NotFoundError

        try:
            # Check for dependent instances first
            instances = self.client.instances.list(snapshot_id=resource.resource_id)
            if instances:
                error_msg = (
                    f"Cannot delete snapshot {resource.resource_id}: "
                    f"{len(instances)} instance(s) still exist. "
                    f"Instance IDs: {[i.id for i in instances]}"
                )
                logger.error(error_msg)
                return CleanupResult(resource=resource, success=False, error=error_msg)

            self.client.snapshots.delete(resource.resource_id)
            logger.info(f"Deleted snapshot {resource.resource_id}")

            # Verify deletion
            self._verify_resource_deleted(
                lambda: self.client.snapshots.get(resource.resource_id),
                resource,
            )

            return CleanupResult(resource=resource, success=True)

        except NotFoundError:
            logger.warning(f"Snapshot {resource.resource_id} already deleted (OK)")
            return CleanupResult(resource=resource, success=True, skipped=True)

    def _cleanup_mapping(self, resource: TrackedResource) -> CleanupResult:
        """Clean up a mapping."""
        from graph_olap.exceptions import NotFoundError

        try:
            # Check for dependent snapshots first
            snapshots = self.client.snapshots.list(mapping_id=resource.resource_id)
            if snapshots:
                error_msg = (
                    f"Cannot delete mapping {resource.resource_id}: "
                    f"{len(snapshots)} snapshot(s) still exist. "
                    f"Snapshot IDs: {[s.id for s in snapshots]}"
                )
                logger.error(error_msg)
                return CleanupResult(resource=resource, success=False, error=error_msg)

            self.client.mappings.delete(resource.resource_id)
            logger.info(f"Deleted mapping {resource.resource_id}")

            # Verify deletion
            self._verify_resource_deleted(
                lambda: self.client.mappings.get(resource.resource_id),
                resource,
            )

            return CleanupResult(resource=resource, success=True)

        except NotFoundError:
            logger.warning(f"Mapping {resource.resource_id} already deleted (OK)")
            return CleanupResult(resource=resource, success=True, skipped=True)

    def _cleanup_graph_properties(self, resource: TrackedResource) -> CleanupResult:
        """Clean up algorithm properties from graph nodes.

        Note: Graph properties cleanup is best-effort. Failures are logged but
        marked as successful since they don't cause resource leaks or quota issues.
        """
        try:
            conn = resource.metadata["connection"]
            node_label = resource.metadata["node_label"]
            property_names = resource.metadata["property_names"]

            # Build REMOVE clause
            remove_clause = ", ".join(f"n.{prop}" for prop in property_names)
            query = f"MATCH (n:{node_label}) REMOVE {remove_clause} RETURN count(n) as count"

            result = conn.query_scalar(query)
            logger.info(
                f"Removed properties {property_names} from {result} {node_label} node(s)"
            )

            return CleanupResult(resource=resource, success=True)

        except Exception as e:
            # Graph properties cleanup is best-effort - log but don't fail
            logger.warning(f"Could not remove graph properties (non-fatal): {e}")
            return CleanupResult(resource=resource, success=True, skipped=True)

    def _verify_resource_deleted(self, get_func, resource: TrackedResource) -> None:
        """Verify a resource was actually deleted.

        Args:
            get_func: Function to call that should raise NotFoundError
            resource: Resource that should be deleted

        Raises:
            AssertionError: If resource still exists
        """
        from graph_olap.exceptions import NotFoundError

        try:
            get_func()
            raise AssertionError(
                f"{resource.resource_type.value} {resource.resource_id} still exists after deletion!"
            )
        except NotFoundError:
            pass  # Good - resource is gone


class CleanupError(Exception):
    """Raised when resource cleanup fails."""

    pass


@contextmanager
def notebook_cleanup(
    client: GraphOLAPClient,
    test_name: str,
    fail_on_cleanup_error: bool = True,
):
    """Context manager for notebook test cleanup.

    Use this in notebooks to ensure cleanup happens even if cells fail.

    Example in notebook:
        from utils.cleanup import notebook_cleanup

        with notebook_cleanup(client, "CRUD Test") as tracker:
            mapping = tracker.create_mapping(name="TestMapping")
            # ... test code ...
        # Cleanup happens automatically

    Args:
        client: GraphOLAP client
        test_name: Name of test (for logging)
        fail_on_cleanup_error: Whether to raise exception on cleanup failure
    """
    tracker = ResourceTracker(client, fail_on_cleanup_error=fail_on_cleanup_error)

    logger.info(f"Starting test: {test_name}")
    try:
        yield tracker
        logger.info(f"Test completed: {test_name}")
    except Exception as e:
        logger.error(f"Test failed: {test_name} - {e}")
        raise
    finally:
        # Always cleanup, even if test failed
        logger.info(f"Cleaning up test: {test_name}")
        try:
            tracker.cleanup_all()
        except CleanupError as e:
            logger.error(f"Cleanup failed for {test_name}: {e}")
            if fail_on_cleanup_error:
                raise
