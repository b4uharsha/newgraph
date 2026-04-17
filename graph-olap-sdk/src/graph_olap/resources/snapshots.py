# =============================================================================
# SNAPSHOT FUNCTIONALITY DISABLED
# This file has been commented out as part of removing explicit snapshot APIs.
# Snapshots are now created implicitly when instances are created from mappings.
# =============================================================================

# """Snapshot resource management."""
#
# from __future__ import annotations
#
# import time
# from collections.abc import Callable
# from typing import TYPE_CHECKING, Any
#
# from graph_olap.exceptions import SnapshotFailedError, TimeoutError
# from graph_olap.models.common import PaginatedList
# from graph_olap.models.snapshot import Snapshot, SnapshotProgress
#
# if TYPE_CHECKING:
#     from graph_olap.http import HTTPClient
#
#
# class SnapshotResource:
#     """Manage data snapshots.
#
#     Snapshots are point-in-time exports of data from Starburst based on a mapping.
#     Creating a snapshot triggers an async export process that may take minutes.
#
#     Example:
#         >>> client = GraphOLAPClient(api_url=api_url, username="user@example.com")
#
#         >>> # Create and wait for snapshot
#         >>> snapshot = client.snapshots.create_and_wait(
#         ...     mapping_id=1,
#         ...     name="Analysis Snapshot",
#         ... )
#
#         >>> # Check status
#         >>> progress = client.snapshots.get_progress(snapshot.id)
#         >>> print(f"Phase: {progress.phase}, Progress: {progress.progress_percent}%")
#     """
#
#     def __init__(self, http: HTTPClient):
#         """Initialize snapshot resource.
#
#         Args:
#             http: HTTP client for API requests
#         """
#         self._http = http
#
#     def list(
#         self,
#         *,
#         mapping_id: int | None = None,
#         mapping_version: int | None = None,
#         owner: str | None = None,
#         status: str | None = None,
#         search: str | None = None,
#         created_after: str | None = None,
#         created_before: str | None = None,
#         sort_by: str = "created_at",
#         sort_order: str = "desc",
#         offset: int = 0,
#         limit: int = 50,
#     ) -> PaginatedList[Snapshot]:
#         """List snapshots with optional filters.
#
#         Args:
#             mapping_id: Filter by mapping_id
#             mapping_version: Filter by mapping_version
#             owner: Filter by owner_id
#             status: Filter by status (pending, creating, ready, failed)
#             search: Text search on name, description
#             created_after: Filter by created_at >= timestamp (ISO 8601)
#             created_before: Filter by created_at <= timestamp (ISO 8601)
#             sort_by: Sort field (name, created_at, status, size_bytes)
#             sort_order: Sort direction (asc, desc)
#             offset: Number of records to skip
#             limit: Max records to return (max 100)
#
#         Returns:
#             Paginated list of Snapshot objects
#         """
#         params: dict[str, Any] = {
#             "offset": offset,
#             "limit": min(limit, 100),
#             "sort_by": sort_by,
#             "sort_order": sort_order,
#         }
#         if mapping_id is not None:
#             params["mapping_id"] = mapping_id
#         if mapping_version is not None:
#             params["mapping_version"] = mapping_version
#         if owner:
#             params["owner"] = owner
#         if status:
#             params["status"] = status
#         if search:
#             params["search"] = search
#         if created_after:
#             params["created_after"] = created_after
#         if created_before:
#             params["created_before"] = created_before
#
#         response = self._http.get("/api/snapshots", params=params)
#         return PaginatedList(
#             items=[Snapshot.from_api_response(s) for s in response["data"]],
#             total=response["meta"]["total"],
#             offset=response["meta"]["offset"],
#             limit=response["meta"]["limit"],
#         )
#
#     def get(self, snapshot_id: int) -> Snapshot:
#         """Get a snapshot by ID.
#
#         Args:
#             snapshot_id: Snapshot ID
#
#         Returns:
#             Snapshot object
#
#         Raises:
#             NotFoundError: If snapshot doesn't exist
#         """
#         response = self._http.get(f"/api/snapshots/{snapshot_id}")
#         return Snapshot.from_api_response(response["data"])
#
#     def create(
#         self,
#         mapping_id: int,
#         name: str,
#         *,
#         description: str | None = None,
#         mapping_version: int | None = None,
#         ttl: str | None = None,
#         inactivity_timeout: str | None = None,
#     ) -> Snapshot:
#         """Create a new snapshot.
#
#         Triggers async export from Starburst. The snapshot will initially
#         have status='pending', then 'creating', then 'ready' or 'failed'.
#
#         Args:
#             mapping_id: Source mapping ID
#             name: Snapshot name
#             description: Optional description
#             mapping_version: Mapping version to use (defaults to current)
#             ttl: Time-to-live (ISO 8601 duration)
#             inactivity_timeout: Inactivity timeout (ISO 8601 duration)
#
#         Returns:
#             Snapshot object (status will be 'pending')
#
#         Raises:
#             NotFoundError: If mapping doesn't exist
#             InvalidStateError: If mapping version doesn't exist
#         """
#         body: dict[str, Any] = {
#             "mapping_id": mapping_id,
#             "name": name,
#         }
#         if description:
#             body["description"] = description
#         if mapping_version is not None:
#             body["mapping_version"] = mapping_version
#         if ttl:
#             body["ttl"] = ttl
#         if inactivity_timeout:
#             body["inactivity_timeout"] = inactivity_timeout
#
#         response = self._http.post("/api/snapshots", json=body)
#         return Snapshot.from_api_response(response["data"])
#
#     def update(
#         self,
#         snapshot_id: int,
#         *,
#         name: str | None = None,
#         description: str | None = None,
#     ) -> Snapshot:
#         """Update snapshot metadata.
#
#         Args:
#             snapshot_id: Snapshot ID
#             name: New name (optional)
#             description: New description (optional)
#
#         Returns:
#             Updated Snapshot object
#         """
#         body: dict[str, Any] = {}
#         if name is not None:
#             body["name"] = name
#         if description is not None:
#             body["description"] = description
#
#         response = self._http.put(f"/api/snapshots/{snapshot_id}", json=body)
#         return Snapshot.from_api_response(response["data"])
#
#     def delete(self, snapshot_id: int) -> None:
#         """Delete a snapshot.
#
#         Args:
#             snapshot_id: Snapshot ID
#
#         Raises:
#             NotFoundError: If snapshot doesn't exist
#             DependencyError: If snapshot has instances
#         """
#         self._http.delete(f"/api/snapshots/{snapshot_id}")
#
#     def set_lifecycle(
#         self,
#         snapshot_id: int,
#         *,
#         ttl: str | None = None,
#         inactivity_timeout: str | None = None,
#     ) -> Snapshot:
#         """Set lifecycle parameters for a snapshot.
#
#         Args:
#             snapshot_id: Snapshot ID
#             ttl: Time-to-live (ISO 8601 duration) or None to clear
#             inactivity_timeout: Inactivity timeout (ISO 8601 duration) or None to clear
#
#         Returns:
#             Updated Snapshot object
#         """
#         body: dict[str, Any] = {}
#         if ttl is not None:
#             body["ttl"] = ttl
#         if inactivity_timeout is not None:
#             body["inactivity_timeout"] = inactivity_timeout
#
#         response = self._http.put(f"/api/snapshots/{snapshot_id}/lifecycle", json=body)
#         return Snapshot.from_api_response(response["data"])
#
#     def get_progress(self, snapshot_id: int) -> SnapshotProgress:
#         """Get detailed creation progress for a snapshot.
#
#         Args:
#             snapshot_id: Snapshot ID
#
#         Returns:
#             SnapshotProgress with phase, steps, and completion info
#         """
#         response = self._http.get(f"/api/snapshots/{snapshot_id}/progress")
#         return SnapshotProgress.from_api_response(response["data"])
#
#     def retry(self, snapshot_id: int) -> Snapshot:
#         """Retry a failed snapshot export.
#
#         Args:
#             snapshot_id: Snapshot ID (must be in 'failed' status)
#
#         Returns:
#             Snapshot object (status will be 'pending')
#
#         Raises:
#             InvalidStateError: If snapshot is not in 'failed' status
#         """
#         response = self._http.post(f"/api/snapshots/{snapshot_id}/retry")
#         return Snapshot.from_api_response(response["data"])
#
#     def wait_until_ready(
#         self,
#         snapshot_id: int,
#         *,
#         timeout: int = 600,
#         poll_interval: int = 5,
#     ) -> Snapshot:
#         """Wait for a snapshot to become ready.
#
#         Args:
#             snapshot_id: Snapshot ID to wait for
#             timeout: Maximum time to wait in seconds
#             poll_interval: Time between status checks in seconds
#
#         Returns:
#             Snapshot object with status='ready'
#
#         Raises:
#             TimeoutError: If snapshot doesn't complete within timeout
#             SnapshotFailedError: If snapshot status becomes 'failed'
#         """
#         start = time.time()
#
#         while time.time() - start < timeout:
#             snapshot = self.get(snapshot_id)
#
#             if snapshot.status == "ready":
#                 return snapshot
#
#             if snapshot.status == "failed":
#                 raise SnapshotFailedError(
#                     f"Snapshot {snapshot_id} failed: {snapshot.error_message}"
#                 )
#
#             time.sleep(poll_interval)
#
#         raise TimeoutError(f"Snapshot {snapshot_id} did not complete within {timeout}s")
#
#     def create_and_wait(
#         self,
#         mapping_id: int,
#         name: str,
#         *,
#         description: str | None = None,
#         mapping_version: int | None = None,
#         ttl: str | None = None,
#         inactivity_timeout: str | None = None,
#         timeout: int = 600,
#         poll_interval: int = 5,
#         on_progress: Callable[[str, int, int], None] | None = None,
#     ) -> Snapshot:
#         """Create a snapshot and wait for it to become ready.
#
#         Convenience method that combines create() and wait_until_ready().
#
#         Args:
#             mapping_id: Source mapping ID
#             name: Snapshot name
#             description: Optional description
#             mapping_version: Mapping version to use (defaults to current)
#             ttl: Time-to-live (ISO 8601 duration)
#             inactivity_timeout: Inactivity timeout (ISO 8601 duration)
#             timeout: Maximum wait time in seconds
#             poll_interval: Time between status checks
#             on_progress: Optional callback(phase, completed_steps, total_steps)
#
#         Returns:
#             Snapshot object with status='ready'
#
#         Example:
#             >>> def show_progress(phase, completed, total):
#             ...     print(f"{phase}: {completed}/{total}")
#             >>> snapshot = client.snapshots.create_and_wait(
#             ...     mapping_id=1,
#             ...     name="Analysis",
#             ...     on_progress=show_progress,
#             ... )
#         """
#         snapshot = self.create(
#             mapping_id=mapping_id,
#             name=name,
#             description=description,
#             mapping_version=mapping_version,
#             ttl=ttl,
#             inactivity_timeout=inactivity_timeout,
#         )
#
#         start = time.time()
#
#         while time.time() - start < timeout:
#             # Get snapshot status from the snapshot object itself
#             snapshot = self.get(snapshot.id)
#
#             # Get progress for progress callback
#             if on_progress:
#                 progress = self.get_progress(snapshot.id)
#                 completed = progress.jobs_completed
#                 total = progress.jobs_total
#                 phase = "exporting" if snapshot.status == "creating" else snapshot.status
#                 on_progress(phase, completed, total)
#
#             if snapshot.status == "ready":
#                 return snapshot
#
#             if snapshot.status == "failed":
#                 error_msg = getattr(snapshot, "error_message", None) or "Unknown error"
#                 raise SnapshotFailedError(
#                     f"Snapshot {snapshot.id} failed: {error_msg}"
#                 )
#
#             time.sleep(poll_interval)
#
#         raise TimeoutError(f"Snapshot {snapshot.id} did not complete within {timeout}s")
