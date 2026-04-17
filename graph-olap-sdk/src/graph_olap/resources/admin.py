"""Admin resource for privileged operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from graph_olap.http import HTTPClient


class AdminResource:
    """Admin-only privileged operations.

    Requires admin role. Used for:
    - Bulk resource deletion (test cleanup, ops maintenance)
    - Other privileged operations

    Example:
        >>> client = GraphOLAPClient(api_url=api_url, username="admin-user")
        >>>
        >>> # Dry run to see what would be deleted
        >>> result = client.admin.bulk_delete(
        ...     resource_type="instance",
        ...     filters={"created_by": "e2e-test-user"},
        ...     reason="test-cleanup",
        ...     dry_run=True
        ... )
        >>> print(f"Would delete {result['matched_count']} instances")
        >>> print(f"IDs: {result['matched_ids']}")
        >>>
        >>> # Actually delete with expected_count safety check
        >>> result = client.admin.bulk_delete(
        ...     resource_type="instance",
        ...     filters={"created_by": "e2e-test-user"},
        ...     reason="test-cleanup",
        ...     expected_count=result['matched_count'],
        ...     dry_run=False
        ... )
        >>> print(f"Deleted {result['deleted_count']} instances")
    """

    def __init__(self, http: HTTPClient):
        """Initialize admin resource.

        Args:
            http: HTTP client for API requests
        """
        self._http = http

    def bulk_delete(
        self,
        resource_type: str,
        filters: dict[str, Any],
        reason: str,
        expected_count: int | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Bulk delete resources with safety filters.

        Requires: Admin role

        Safety features:
        - At least one filter required
        - Max 100 deletions per request
        - Expected count validation
        - Dry run mode available
        - Full audit logging

        Args:
            resource_type: Resource type (instance, snapshot, mapping)
            filters: Filters to match resources (at least one required):
                - name_prefix: Match resources starting with prefix
                - created_by: Match resources created by username
                - older_than_hours: Match resources older than N hours
                - status: Match resources with specific status
            reason: Reason for deletion (audit log)
            expected_count: Expected number of resources to delete (safety check).
                Must match actual count or operation fails. Get from dry_run first.
            dry_run: If True, return what would be deleted without deleting

        Returns:
            Deletion results with counts and IDs

        Raises:
            ForbiddenError: If user doesn't have Admin role
            ValidationError: If no filters provided, matched > 100, or count mismatch

        Example:
            >>> # Step 1: Dry run to get count
            >>> result = client.admin.bulk_delete(
            ...     resource_type="instance",
            ...     filters={
            ...         "name_prefix": "E2ETest-",
            ...         "older_than_hours": 24
            ...     },
            ...     reason="cleanup-old-test-instances",
            ...     dry_run=True
            ... )
            >>> print(f"Would delete {result['matched_count']} instances")
            >>>
            >>> # Step 2: Actually delete with expected_count
            >>> result = client.admin.bulk_delete(
            ...     resource_type="instance",
            ...     filters={
            ...         "name_prefix": "E2ETest-",
            ...         "older_than_hours": 24
            ...     },
            ...     reason="cleanup-old-test-instances",
            ...     expected_count=result['matched_count'],  # Safety check!
            ...     dry_run=False
            ... )
            >>> print(f"Deleted: {result['deleted_count']}")
            >>> print(f"Failed: {result['failed_count']}")
        """
        response = self._http.delete(
            "/api/admin/resources/bulk",
            json={
                "resource_type": resource_type,
                "filters": filters,
                "reason": reason,
                "expected_count": expected_count,
                "dry_run": dry_run,
            }
        )
        return response["data"]
