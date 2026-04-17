"""E2E Test Cleanup Service.

Provides centralized cleanup of all resources owned by E2E test users.
Called via DELETE /api/admin/e2e-cleanup before and after E2E test runs.
"""

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import structlog

from control_plane.config import get_settings
from control_plane.models import User, UserRole

if TYPE_CHECKING:
    from control_plane.clients.gcs import GCSClient
    from control_plane.repositories.instances import InstanceRepository
    from control_plane.repositories.mappings import MappingRepository
    from control_plane.repositories.snapshots import SnapshotRepository
    from control_plane.repositories.users import UserRepository
    from control_plane.services.k8s_service import K8sService

logger = structlog.get_logger(__name__)


@dataclass
class CleanupResult:
    """Result of E2E cleanup operation."""

    users_processed: list[str] = field(default_factory=list)
    instances_deleted: int = 0
    snapshots_deleted: int = 0
    mappings_deleted: int = 0
    pods_terminated: int = 0
    gcs_files_deleted: int = 0
    gcs_bytes_deleted: int = 0
    errors: list[dict] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """Check if cleanup completed without critical errors."""
        # Cleanup is successful if no critical errors occurred
        # (warnings about already-deleted resources are acceptable)
        return not any(e.get("critical", False) for e in self.errors)

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "users_processed": self.users_processed,
            "instances_deleted": self.instances_deleted,
            "snapshots_deleted": self.snapshots_deleted,
            "mappings_deleted": self.mappings_deleted,
            "pods_terminated": self.pods_terminated,
            "gcs_files_deleted": self.gcs_files_deleted,
            "gcs_bytes_deleted": self.gcs_bytes_deleted,
            "errors": self.errors,
            "success": self.success,
        }


class E2ECleanupService:
    """Service for cleaning up E2E test resources.

    Deletes all resources (instances, snapshots, mappings) owned by configured
    E2E test users. Also force-terminates orphaned K8s pods that may have been
    left behind.
    """

    def __init__(
        self,
        user_repo: "UserRepository",
        instance_repo: "InstanceRepository",
        snapshot_repo: "SnapshotRepository",
        mapping_repo: "MappingRepository",
        k8s_service: "K8sService | None" = None,
        gcs_client: "GCSClient | None" = None,
    ):
        """Initialize cleanup service.

        Args:
            user_repo: User repository for email -> username lookup
            instance_repo: Instance repository for instance deletion
            snapshot_repo: Snapshot repository for snapshot deletion
            mapping_repo: Mapping repository for mapping deletion
            k8s_service: Optional K8s service for pod cleanup
            gcs_client: Optional GCS client for file cleanup
        """
        self._user_repo = user_repo
        self._instance_repo = instance_repo
        self._snapshot_repo = snapshot_repo
        self._mapping_repo = mapping_repo
        self._k8s_service = k8s_service
        self._gcs_client = gcs_client
        self._logger = logger.bind(component="e2e_cleanup")

    async def cleanup_all_test_resources(self, requesting_user: User) -> CleanupResult:
        """Delete ALL resources owned by E2E test users.

        Deletion order:
        1. Instances (+ K8s pods via cascade)
        2. Snapshots (+ GCS files)
        3. Mappings
        4. Force-terminate orphaned pods by owner-email label

        Args:
            requesting_user: User performing the cleanup (for audit logging)

        Returns:
            CleanupResult with summary of deleted resources
        """
        settings = get_settings()
        result = CleanupResult()

        # Get configured test user emails
        test_emails = settings.e2e_test_user_emails
        if not test_emails:
            self._logger.warning("e2e_cleanup_no_users", message="No test user emails configured")
            return result

        self._logger.info(
            "e2e_cleanup_started",
            test_emails=test_emails,
            requested_by=requesting_user.username,
        )

        # Resolve emails to usernames
        usernames_by_email: dict[str, str] = {}
        for email in test_emails:
            user = await self._user_repo.get_by_email(email)
            if user:
                usernames_by_email[email] = user.username
                result.users_processed.append(email)
            else:
                self._logger.debug("e2e_cleanup_user_not_found", email=email)

        if not usernames_by_email:
            self._logger.info("e2e_cleanup_no_users_found", test_emails=test_emails)
            return result

        # Phase 1: Delete instances (cascades to K8s pods)
        for email, username in usernames_by_email.items():
            try:
                deleted = await self._delete_user_instances(username)
                result.instances_deleted += deleted
            except Exception as e:
                result.errors.append({
                    "phase": "instances",
                    "user": username,
                    "error": str(e),
                    "critical": True,
                })
                self._logger.exception(
                    "e2e_cleanup_instance_error",
                    username=username,
                    error=str(e),
                )

        # TODO: Snapshot functionality disabled - Phase 2 snapshot deletion commented out
        # Phase 2: Delete snapshots (cascades to GCS files)
        # for email, username in usernames_by_email.items():
        #     try:
        #         deleted, files, bytes_del = await self._delete_user_snapshots(username)
        #         result.snapshots_deleted += deleted
        #         result.gcs_files_deleted += files
        #         result.gcs_bytes_deleted += bytes_del
        #     except Exception as e:
        #         result.errors.append({
        #             "phase": "snapshots",
        #             "user": username,
        #             "error": str(e),
        #             "critical": True,
        #         })
        #         self._logger.exception(
        #             "e2e_cleanup_snapshot_error",
        #             username=username,
        #             error=str(e),
        #         )

        # Phase 3: Delete mappings
        for email, username in usernames_by_email.items():
            try:
                deleted = await self._delete_user_mappings(username)
                result.mappings_deleted += deleted
            except Exception as e:
                result.errors.append({
                    "phase": "mappings",
                    "user": username,
                    "error": str(e),
                    "critical": True,
                })
                self._logger.exception(
                    "e2e_cleanup_mapping_error",
                    username=username,
                    error=str(e),
                )

        # Phase 4: Force-terminate orphaned pods by owner-email label
        if self._k8s_service:
            for email in test_emails:
                try:
                    terminated = await self._terminate_orphaned_pods(email)
                    result.pods_terminated += terminated
                except Exception as e:
                    result.errors.append({
                        "phase": "pods",
                        "email": email,
                        "error": str(e),
                        "critical": False,  # Pod cleanup failures are non-critical
                    })
                    self._logger.warning(
                        "e2e_cleanup_pod_error",
                        email=email,
                        error=str(e),
                    )

        self._logger.info(
            "e2e_cleanup_completed",
            result=result.to_dict(),
            requested_by=requesting_user.username,
        )

        return result

    async def _delete_user_instances(self, username: str) -> int:
        """Delete all instances owned by a user.

        Cascade: after deleting an instance, checks if its snapshot is
        orphaned (no other instances reference it). If so, deletes the
        snapshot from DB and GCS.

        Args:
            username: Owner username

        Returns:
            Number of instances deleted
        """
        from control_plane.repositories.instances import InstanceFilters

        instances, _ = await self._instance_repo.list_instances(
            filters=InstanceFilters(owner=username),
            limit=1000,
            offset=0,
        )

        deleted = 0
        for instance in instances:
            snapshot_id = instance.snapshot_id
            try:
                # Delete K8s resources first (if available)
                if self._k8s_service and instance.url_slug:
                    await self._k8s_service.delete_wrapper_pod(instance.url_slug)

                # Delete instance from database
                await self._instance_repo.delete(instance.id)
                deleted += 1
                self._logger.debug(
                    "e2e_cleanup_instance_deleted",
                    instance_id=instance.id,
                    username=username,
                )

                # Cascade: delete orphaned snapshot (no other instances reference it).
                # Use the instance-repo query (single source of truth) so we match
                # the semantics of instance_service.delete_instance — checks BOTH
                # snapshot_id and pending_snapshot_id, and does NOT exclude waiting
                # instances. This prevents deleting a snapshot that a `waiting_for_snapshot`
                # instance still needs.
                if snapshot_id and self._snapshot_repo:
                    try:
                        ref_count = await self._instance_repo.count_instances_referencing_snapshot(
                            snapshot_id,
                        )
                        if ref_count == 0:
                            # Delete GCS files
                            if self._gcs_client:
                                snapshot = await self._snapshot_repo.get_by_id(snapshot_id)
                                if snapshot and snapshot.gcs_path:
                                    try:
                                        self._gcs_client.delete_path(snapshot.gcs_path)
                                        self._logger.debug(
                                            "e2e_cleanup_snapshot_gcs_deleted",
                                            snapshot_id=snapshot_id,
                                        )
                                    except Exception:
                                        pass  # GCS cleanup is best-effort
                            # Delete snapshot DB record
                            await self._snapshot_repo.delete(snapshot_id)
                            self._logger.debug(
                                "e2e_cleanup_snapshot_cascaded",
                                snapshot_id=snapshot_id,
                                instance_id=instance.id,
                            )
                    except Exception as e:
                        self._logger.warning(
                            "e2e_cleanup_snapshot_cascade_failed",
                            snapshot_id=snapshot_id,
                            error=str(e),
                        )

            except Exception as e:
                self._logger.warning(
                    "e2e_cleanup_instance_delete_failed",
                    instance_id=instance.id,
                    error=str(e),
                )

        return deleted

    # TODO: Snapshot functionality disabled - _delete_user_snapshots method commented out
    # async def _delete_user_snapshots(self, username: str) -> tuple[int, int, int]:
    #     """Delete all snapshots owned by a user.
    #
    #     Args:
    #         username: Owner username
    #
    #     Returns:
    #         Tuple of (snapshots_deleted, gcs_files_deleted, gcs_bytes_deleted)
    #     """
    #     from control_plane.repositories.snapshots import SnapshotFilters
    #
    #     snapshots, _ = await self._snapshot_repo.list_snapshots(
    #         filters=SnapshotFilters(owner=username),
    #         limit=1000,
    #         offset=0,
    #     )
    #
    #     deleted = 0
    #     gcs_files = 0
    #     gcs_bytes = 0
    #
    #     for snapshot in snapshots:
    #         try:
    #             # Delete GCS files first (if client available)
    #             if self._gcs_client and snapshot.gcs_path:
    #                 try:
    #                     files, bytes_del = self._gcs_client.delete_path(snapshot.gcs_path)
    #                     gcs_files += files
    #                     gcs_bytes += bytes_del
    #                 except Exception as e:
    #                     self._logger.warning(
    #                         "e2e_cleanup_gcs_delete_failed",
    #                         snapshot_id=snapshot.id,
    #                         gcs_path=snapshot.gcs_path,
    #                         error=str(e),
    #                     )
    #
    #             # Delete from database (export jobs cascade)
    #             await self._snapshot_repo.delete(snapshot.id)
    #             deleted += 1
    #             self._logger.debug(
    #                 "e2e_cleanup_snapshot_deleted",
    #                 snapshot_id=snapshot.id,
    #                 username=username,
    #             )
    #         except Exception as e:
    #             self._logger.warning(
    #                 "e2e_cleanup_snapshot_delete_failed",
    #                 snapshot_id=snapshot.id,
    #                 error=str(e),
    #             )
    #
    #     return deleted, gcs_files, gcs_bytes

    async def _delete_user_mappings(self, username: str) -> int:
        """Delete all mappings owned by a user.

        Args:
            username: Owner username

        Returns:
            Number of mappings deleted
        """
        from control_plane.repositories.mappings import MappingFilters, Pagination, Sort

        mappings, _ = await self._mapping_repo.list_mappings(
            filters=MappingFilters(owner=username),
            pagination=Pagination(offset=0, limit=1000),
            sort=Sort(),
        )

        deleted = 0
        for mapping in mappings:
            try:
                # Delete mapping (versions cascade)
                await self._mapping_repo.delete(mapping.id)
                deleted += 1
                self._logger.debug(
                    "e2e_cleanup_mapping_deleted",
                    mapping_id=mapping.id,
                    username=username,
                )
            except Exception as e:
                self._logger.warning(
                    "e2e_cleanup_mapping_delete_failed",
                    mapping_id=mapping.id,
                    error=str(e),
                )

        return deleted

    async def _terminate_orphaned_pods(self, owner_email: str) -> int:
        """Force-terminate any remaining pods owned by email.

        This catches pods that may have been orphaned due to:
        - Database cleanup without K8s cleanup
        - Previous incomplete cleanup operations
        - Reconciliation issues

        Args:
            owner_email: Owner email to filter by

        Returns:
            Number of pods terminated
        """
        if not self._k8s_service:
            return 0

        pods = await self._k8s_service.list_pods_by_owner_email(owner_email)

        terminated = 0
        for pod in pods:
            try:
                pod_name = pod.metadata.name
                deleted = await self._k8s_service.delete_wrapper_pod_by_name(
                    pod_name=pod_name,
                    grace_period_seconds=0,  # Force immediate termination
                )
                if deleted:
                    terminated += 1
                    self._logger.debug(
                        "e2e_cleanup_orphaned_pod_terminated",
                        pod_name=pod_name,
                        owner_email=owner_email,
                    )
            except Exception as e:
                self._logger.warning(
                    "e2e_cleanup_pod_terminate_failed",
                    pod_name=pod.metadata.name,
                    error=str(e),
                )

        return terminated
