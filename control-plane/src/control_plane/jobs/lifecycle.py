"""Lifecycle job for TTL and inactivity timeout enforcement.

Enforces lifecycle policies on instances, snapshots, and mappings:
1. TTL expiry - Terminates/deletes resources past their time-to-live
2. Inactivity timeout - Terminates instances with no recent activity

Runs every 5 minutes (configurable via GRAPH_OLAP_LIFECYCLE_JOB_INTERVAL_SECONDS).
"""

from datetime import UTC, datetime, timedelta

import structlog

from control_plane.clients.gcs import GCSClient, build_gcs_client_from_settings
from control_plane.config import get_settings
from control_plane.infrastructure.database import get_session
from control_plane.models import InstanceStatus
from control_plane.repositories.instances import InstanceFilters, InstanceRepository
from control_plane.repositories.mappings import MappingRepository
from control_plane.repositories.snapshots import SnapshotRepository
from control_plane.services.instance_service import InstanceService
from control_plane.services.k8s_service import get_k8s_service

logger = structlog.get_logger(__name__)


async def run_lifecycle_job(session=None) -> None:
    """Enforce TTL and inactivity timeouts on all resources.

    Checks:
    - Instances past their TTL → terminate
    - Instances past inactivity timeout → terminate
    - Snapshots past their TTL → delete
    - Mappings past their TTL → delete

    Args:
        session: Optional database session (for testing). If None, creates a new session.
    """
    import time

    from control_plane.jobs import metrics

    logger.info("lifecycle_job_started")
    start_time = time.time()

    # Increment lifecycle pass counter
    metrics.lifecycle_passes_total.inc()

    # Use provided session or create a new one
    if session is not None:
        await _run_lifecycle_with_session(session, start_time)
    else:
        async with get_session() as session:
            await _run_lifecycle_with_session(session, start_time)


async def _run_lifecycle_with_session(session, start_time: float) -> None:
    """Internal lifecycle logic with provided session."""
    import time

    from control_plane.jobs import metrics

    # Initialize repositories and services
    instance_repo = InstanceRepository(session)
    snapshot_repo = SnapshotRepository(session)
    mapping_repo = MappingRepository(session)
    from control_plane.repositories.favorites import FavoritesRepository
    favorites_repo = FavoritesRepository(session)
    k8s_service = get_k8s_service()

    # Construct GCS client from settings. Raises if GCS is configured but
    # the client cannot be built — cascade deletes would otherwise silently
    # leak snapshot objects.
    settings = get_settings()
    gcs_client = build_gcs_client_from_settings(settings)

    instance_service = InstanceService(
        instance_repo=instance_repo,
        snapshot_repo=snapshot_repo,
        config_repo=None,  # Not needed for termination
        favorites_repo=favorites_repo,
        k8s_service=k8s_service,
        gcs_client=gcs_client,
    )

    now = datetime.now(UTC)

    # Phase 1: Find and terminate TTL-expired instances
    ttl_expired_instances = await _find_ttl_expired_instances(instance_repo, now)
    ttl_terminated = await _terminate_expired_instances(
        instance_service,
        ttl_expired_instances,
        "TTL expiry",
    )

    # Phase 2: Find and terminate inactive instances
    inactive_instances = await _find_inactive_instances(instance_repo, now)
    inactive_terminated = await _terminate_expired_instances(
        instance_service,
        inactive_instances,
        "inactivity timeout",
    )

    # Phase 3: Delete TTL-expired snapshots. This catches snapshots with no
    # instances referencing them (e.g. FAILED exports, or snapshots whose
    # instances were all deleted out-of-band) — the cascade-on-instance-delete
    # path cannot reach them.
    ttl_expired_snapshots = await _find_ttl_expired_snapshots(snapshot_repo, now)
    snapshots_deleted = await _delete_expired_snapshots(
        snapshot_repo,
        ttl_expired_snapshots,
        instance_repo,  # For cascade deletion of instances
        gcs_client,
    )

    # Phase 4: Delete TTL-expired mappings
    ttl_expired_mappings = await _find_ttl_expired_mappings(mapping_repo, now)
    mappings_deleted = await _delete_expired_mappings(
        mapping_repo,
        ttl_expired_mappings,
    )

    # Record pass duration
    duration = time.time() - start_time
    metrics.lifecycle_pass_duration_seconds.observe(duration)

    logger.info(
        "lifecycle_job_completed",
        ttl_instances_terminated=ttl_terminated,
        inactive_instances_terminated=inactive_terminated,
        ttl_snapshots_deleted=snapshots_deleted,
        ttl_mappings_deleted=mappings_deleted,
        duration_seconds=duration,
    )


async def _find_ttl_expired_instances(repo: InstanceRepository, now: datetime) -> list:
    """Find instances that have exceeded their TTL.

    Args:
        repo: Instance repository
        now: Current timestamp

    Returns:
        List of expired instances
    """
    # Get all active instances
    all_instances = await repo.list_all()

    expired = []
    for instance in all_instances:
        if instance.status == InstanceStatus.FAILED:
            continue  # Don't re-terminate failed instances

        if instance.ttl and instance.created_at:
            # Parse ISO 8601 duration (e.g., "PT24H", "P7D")
            ttl_delta = _parse_iso8601_duration(instance.ttl)
            if ttl_delta:
                expiry_time = instance.created_at + ttl_delta
                if now > expiry_time:
                    expired.append(instance)

    return expired


async def _find_inactive_instances(repo: InstanceRepository, now: datetime) -> list:
    """Find instances that have exceeded their inactivity timeout.

    Args:
        repo: Instance repository
        now: Current timestamp

    Returns:
        List of inactive instances
    """
    all_instances = await repo.list_all()

    inactive = []
    for instance in all_instances:
        if instance.status != InstanceStatus.RUNNING:
            continue  # Only check running instances

        if instance.inactivity_timeout and instance.last_activity_at:
            timeout_delta = _parse_iso8601_duration(instance.inactivity_timeout)
            if timeout_delta:
                inactive_deadline = instance.last_activity_at + timeout_delta
                if now > inactive_deadline:
                    inactive.append(instance)

    return inactive


async def _terminate_expired_instances(
    service: InstanceService,
    instances: list,
    reason: str,
) -> int:
    """Terminate expired instances.

    Args:
        service: Instance service
        instances: List of instances to terminate
        reason: Reason for termination (for logging)

    Returns:
        Number of instances successfully terminated
    """
    terminated_count = 0

    for instance in instances:
        try:
            logger.info(
                "lifecycle_instance_expired",
                instance_id=instance.id,
                reason=reason,
                ttl=instance.ttl,
                created_at=instance.created_at.isoformat() if instance.created_at else None,
                last_activity_at=instance.last_activity_at.isoformat() if instance.last_activity_at else None,
            )

            # Create a system user for termination (needs RequestUser with role)
            from control_plane.models import RequestUser, UserRole
            system_user = RequestUser(
                username="system",
                email="system@internal",
                display_name="System",
                role=UserRole.OPS,  # OPS role for lifecycle operations
                is_active=True,
            )

            # Delete instance
            await service.delete_instance(
                instance_id=instance.id,
                user=system_user,
            )

            logger.info("lifecycle_instance_terminated", instance_id=instance.id, reason=reason)
            terminated_count += 1

            # Increment appropriate metric based on reason
            if reason == "TTL expiry":
                from control_plane.jobs import metrics
                metrics.ttl_instances_terminated_total.inc()
            elif reason == "inactivity timeout":
                from control_plane.jobs import metrics
                metrics.inactive_instances_terminated_total.inc()

        except Exception as e:
            logger.error(
                "lifecycle_termination_failed",
                instance_id=instance.id,
                reason=reason,
                error=str(e),
            )
            from control_plane.jobs import metrics
            metrics.lifecycle_termination_failures_total.labels(resource_type="instance").inc()

    return terminated_count


async def _find_ttl_expired_snapshots(repo: SnapshotRepository, now: datetime) -> list:
    """Find snapshots that have exceeded their TTL.

    Args:
        repo: Snapshot repository
        now: Current timestamp

    Returns:
        List of expired snapshots
    """
    all_snapshots = await repo.list_all()

    expired = []
    for snapshot in all_snapshots:
        if snapshot.ttl and snapshot.created_at:
            ttl_delta = _parse_iso8601_duration(snapshot.ttl)
            if ttl_delta:
                expiry_time = snapshot.created_at + ttl_delta
                if now > expiry_time:
                    expired.append(snapshot)

    return expired


async def _delete_expired_snapshots(
    repo: SnapshotRepository,
    snapshots: list,
    instance_repo: InstanceRepository | None = None,
    gcs_client: GCSClient | None = None,
) -> int:
    """Delete TTL-expired snapshots.

    Cascade-deletes any instances referencing the snapshot first to avoid FK violations,
    then deletes GCS files before deleting database records.

    Args:
        repo: Snapshot repository
        snapshots: List of snapshots to delete
        instance_repo: Instance repository for cascade deletion
        gcs_client: GCS client for file cleanup (None skips GCS delete with a warning)

    Returns:
        Number of snapshots successfully deleted
    """
    deleted_count = 0

    for snapshot in snapshots:
        try:
            logger.info(
                "lifecycle_snapshot_expired",
                snapshot_id=snapshot.id,
                ttl=snapshot.ttl,
                created_at=snapshot.created_at.isoformat() if snapshot.created_at else None,
            )

            # Cascade delete instances referencing this snapshot to avoid FK violation
            if instance_repo:
                instances, _ = await instance_repo.list_instances(
                    InstanceFilters(snapshot_id=snapshot.id),
                    limit=1000,
                )
                for instance in instances:
                    try:
                        await instance_repo.delete(instance.id)
                        logger.info(
                            "lifecycle_instance_cascade_deleted",
                            instance_id=instance.id,
                            snapshot_id=snapshot.id,
                            reason="parent snapshot expired",
                        )
                    except Exception as e:
                        logger.error(
                            "lifecycle_instance_cascade_delete_failed",
                            instance_id=instance.id,
                            snapshot_id=snapshot.id,
                            error=str(e),
                        )

            # Delete GCS files if client is configured. When gcs_client is None
            # we log loudly and still delete the DB row — the bucket lifecycle
            # rule is the only backstop in that case.
            if gcs_client is None:
                logger.warning(
                    "lifecycle_snapshot_gcs_delete_skipped_no_client",
                    snapshot_id=snapshot.id,
                    gcs_path=snapshot.gcs_path,
                    reason="lifecycle job constructed without gcs_client",
                )
            elif snapshot.gcs_path:
                try:
                    files_deleted, bytes_deleted = gcs_client.delete_path(snapshot.gcs_path)
                    logger.info(
                        "lifecycle_snapshot_gcs_deleted",
                        snapshot_id=snapshot.id,
                        gcs_path=snapshot.gcs_path,
                        files_deleted=files_deleted,
                        bytes_deleted=bytes_deleted,
                    )
                except Exception as e:
                    # Log error but continue with DB deletion
                    logger.error(
                        "lifecycle_snapshot_gcs_deletion_failed",
                        snapshot_id=snapshot.id,
                        gcs_path=snapshot.gcs_path,
                        error=str(e),
                    )
                    # Increment GCS cleanup failure metric
                    from control_plane.jobs import metrics
                    metrics.snapshot_gcs_cleanup_failures_total.inc()
            else:
                # gcs_client is wired but the snapshot row has no path. Most
                # likely a FAILED snapshot that never got a path finalized.
                logger.warning(
                    "lifecycle_snapshot_gcs_delete_skipped_no_path",
                    snapshot_id=snapshot.id,
                    reason="snapshot row has empty gcs_path; nothing to delete",
                )

            # Delete snapshot from database
            await repo.delete(snapshot.id)

            logger.info("lifecycle_snapshot_deleted", snapshot_id=snapshot.id)
            deleted_count += 1

            # Increment metric
            from control_plane.jobs import metrics
            metrics.ttl_snapshots_deleted_total.inc()

        except Exception as e:
            logger.error(
                "lifecycle_snapshot_deletion_failed",
                snapshot_id=snapshot.id,
                error=str(e),
            )
            from control_plane.jobs import metrics
            metrics.lifecycle_termination_failures_total.labels(resource_type="snapshot").inc()

    return deleted_count


async def _find_ttl_expired_mappings(repo: MappingRepository, now: datetime) -> list:
    """Find mappings that have exceeded their TTL.

    Args:
        repo: Mapping repository
        now: Current timestamp

    Returns:
        List of expired mappings
    """
    all_mappings = await repo.list_all()

    expired = []
    for mapping in all_mappings:
        if mapping.ttl and mapping.created_at:
            ttl_delta = _parse_iso8601_duration(mapping.ttl)
            if ttl_delta:
                expiry_time = mapping.created_at + ttl_delta
                if now > expiry_time:
                    expired.append(mapping)

    return expired


async def _delete_expired_mappings(repo: MappingRepository, mappings: list) -> int:
    """Delete TTL-expired mappings.

    Args:
        repo: Mapping repository
        mappings: List of mappings to delete

    Returns:
        Number of mappings successfully deleted
    """
    deleted_count = 0

    for mapping in mappings:
        try:
            logger.info(
                "lifecycle_mapping_expired",
                mapping_id=mapping.id,
                ttl=mapping.ttl,
                created_at=mapping.created_at.isoformat() if mapping.created_at else None,
            )

            await repo.delete(mapping.id)

            logger.info("lifecycle_mapping_deleted", mapping_id=mapping.id)
            deleted_count += 1

            # Increment metric
            from control_plane.jobs import metrics
            metrics.ttl_mappings_deleted_total.inc()

        except Exception as e:
            logger.error(
                "lifecycle_mapping_deletion_failed",
                mapping_id=mapping.id,
                error=str(e),
            )
            from control_plane.jobs import metrics
            metrics.lifecycle_termination_failures_total.labels(resource_type="mapping").inc()

    return deleted_count


# NOTE: E2E test cleanup architecture (ADR-045)
# Layer 1: Test runner cleanup (try/finally) - PRIMARY ✅
# Layer 3: Pre-test cleanup (conftest.py) - SAFETY NET ✅
# Manual cleanup: tests/e2e/scripts/check_test_resources.py
# Decision: DO NOT re-add Layer 2 to lifecycle job (violates separation of concerns)


def _parse_iso8601_duration(duration_str: str) -> timedelta | None:
    """Parse ISO 8601 duration string to timedelta.

    Supports:
    - PT<n>H - hours (e.g., "PT24H" = 24 hours)
    - PT<n>M - minutes (e.g., "PT30M" = 30 minutes)
    - P<n>D - days (e.g., "P7D" = 7 days)

    Args:
        duration_str: ISO 8601 duration string

    Returns:
        timedelta object or None if parsing fails
    """
    try:
        if not duration_str or not duration_str.startswith("P"):
            return None

        # Remove "P" prefix
        duration = duration_str[1:]

        # Check if it's time-based (PT prefix)
        if duration.startswith("T"):
            duration = duration[1:]  # Remove "T"

            if duration.endswith("H"):
                hours = int(duration[:-1])
                if hours < 0:
                    return None  # Reject negative durations
                return timedelta(hours=hours)
            elif duration.endswith("M"):
                minutes = int(duration[:-1])
                if minutes < 0:
                    return None  # Reject negative durations
                return timedelta(minutes=minutes)
            elif duration.endswith("S"):
                seconds = int(duration[:-1])
                if seconds < 0:
                    return None  # Reject negative durations
                return timedelta(seconds=seconds)

        # Check if it's date-based
        elif duration.endswith("D"):
            days = int(duration[:-1])
            if days < 0:
                return None  # Reject negative durations
            return timedelta(days=days)
        elif duration.endswith("W"):
            weeks = int(duration[:-1])
            if weeks < 0:
                return None  # Reject negative durations
            return timedelta(weeks=weeks)

        return None

    except (ValueError, IndexError):
        logger.warning("iso8601_duration_parse_failed", duration_str=duration_str)
        return None
