"""Instance orchestration job for managing waiting_for_snapshot instances.

Monitors instances in 'waiting_for_snapshot' status and transitions them
when their pending snapshot becomes ready (or marks them failed if snapshot fails).

This job runs every 30 seconds to provide responsive instance creation
when using the create-instance-from-mapping flow.
"""

import time

import structlog

from control_plane.infrastructure.database import get_session
from control_plane.jobs import metrics
from control_plane.models import InstanceErrorCode, InstanceStatus, SnapshotStatus
from control_plane.repositories.instances import InstanceRepository
from control_plane.repositories.mappings import MappingRepository
from control_plane.repositories.snapshots import SnapshotRepository
from control_plane.services.k8s_service import get_k8s_service

logger = structlog.get_logger(__name__)


async def run_instance_orchestration_job(session=None) -> None:
    """Check instances waiting for snapshots and transition when ready.

    For each instance with status='waiting_for_snapshot':
    1. Look up the snapshot by pending_snapshot_id
    2. If snapshot.status == 'ready': transition instance to 'starting', create K8s pod
    3. If snapshot.status == 'failed': mark instance as 'failed' with error message
    4. Otherwise: skip (snapshot still pending/creating)

    Args:
        session: Optional database session (for testing). If None, creates a new session.
    """
    logger.info("instance_orchestration_job_started")
    start_time = time.time()

    # Increment orchestration pass counter
    metrics.instance_orchestration_passes_total.inc()

    # Use provided session or create a new one
    if session is not None:
        await _run_orchestration_with_session(session, start_time)
    else:
        async with get_session() as session:
            await _run_orchestration_with_session(session, start_time)


async def run_instance_orchestration(
    instance_repo: InstanceRepository,
    snapshot_repo: SnapshotRepository,
    k8s_service,
    mapping_repo: MappingRepository | None = None,
) -> dict:
    """Testable orchestration logic with provided dependencies.

    Args:
        instance_repo: Instance repository
        snapshot_repo: Snapshot repository
        k8s_service: K8s service for pod operations
        mapping_repo: Optional mapping repository (for pod label enrichment)

    Returns:
        Dict with orchestration results:
        - processed: Number of instances processed
        - transitioned: Number transitioned to starting
        - failed: Number marked as failed
        - skipped: Number still waiting
        - errors: Number of errors encountered
    """
    return await _run_orchestration_logic(instance_repo, snapshot_repo, k8s_service, mapping_repo)


async def _run_orchestration_with_session(session, start_time: float) -> None:
    """Internal orchestration logic with provided session."""
    instance_repo = InstanceRepository(session)
    snapshot_repo = SnapshotRepository(session)
    mapping_repo = MappingRepository(session)
    k8s_service = get_k8s_service()

    await _run_orchestration_logic(instance_repo, snapshot_repo, k8s_service, mapping_repo)

    # Record pass duration
    duration = time.time() - start_time
    metrics.instance_orchestration_pass_duration_seconds.observe(duration)


async def _run_orchestration_logic(
    instance_repo: InstanceRepository,
    snapshot_repo: SnapshotRepository,
    k8s_service,
    mapping_repo: MappingRepository | None = None,
) -> dict:
    """Core orchestration logic."""

    # Get all instances waiting for snapshots
    waiting_instances = await instance_repo.get_waiting_for_snapshot()

    logger.info(
        "instance_orchestration_state_loaded",
        waiting_instances=len(waiting_instances),
    )

    transitioned_to_starting = 0
    transitioned_to_failed = 0
    still_waiting = 0
    errors = 0

    for instance in waiting_instances:
        try:
            # Get the pending snapshot
            if not instance.pending_snapshot_id:
                logger.warning(
                    "instance_missing_pending_snapshot_id",
                    instance_id=instance.id,
                )
                continue

            snapshot = await snapshot_repo.get_by_id(instance.pending_snapshot_id)
            if snapshot is None:
                # Snapshot was deleted - mark instance as failed
                logger.warning(
                    "pending_snapshot_not_found",
                    instance_id=instance.id,
                    pending_snapshot_id=instance.pending_snapshot_id,
                )
                await instance_repo.update_status(
                    instance_id=instance.id,
                    status=InstanceStatus.FAILED,
                    error_code=InstanceErrorCode.DATA_LOAD_ERROR,
                    error_message="Pending snapshot was deleted before it could complete",
                )
                transitioned_to_failed += 1
                continue

            if snapshot.status == SnapshotStatus.READY:
                # Snapshot is ready - transition instance to starting
                logger.info(
                    "transitioning_instance_to_starting",
                    instance_id=instance.id,
                    snapshot_id=snapshot.id,
                )

                # Transition instance to 'starting' status
                # The snapshot_id is already set when instance was created in waiting_for_snapshot
                updated_instance = await instance_repo.transition_to_starting(
                    instance_id=instance.id,
                )

                if updated_instance and k8s_service is not None and updated_instance.url_slug:
                    # Create K8s pod for the wrapper (same pattern as instance_service.create_instance)
                    try:
                        # owner_username is the email in this system
                        owner_email = updated_instance.owner_username or f"{updated_instance.owner_username}@auto.local"

                        # Look up mapping name for pod labels (best-effort)
                        mapping_name = ""
                        if mapping_repo:
                            try:
                                mapping = await mapping_repo.get_by_id(snapshot.mapping_id)
                                if mapping:
                                    mapping_name = mapping.name
                            except Exception:
                                pass  # Non-critical — label will be omitted

                        pod_name, external_url = await k8s_service.create_wrapper_pod(
                            instance_id=updated_instance.id,
                            url_slug=updated_instance.url_slug,
                            wrapper_type=updated_instance.wrapper_type,
                            snapshot_id=snapshot.id,
                            mapping_id=snapshot.mapping_id,
                            mapping_version=snapshot.mapping_version,
                            owner_username=updated_instance.owner_username,
                            owner_email=owner_email,
                            gcs_path=snapshot.gcs_path,
                            instance_name=updated_instance.name,
                            mapping_name=mapping_name,
                        )

                        if pod_name:
                            # Update instance with pod_name and instance_url
                            await instance_repo.update_status(
                                instance_id=updated_instance.id,
                                status=InstanceStatus.STARTING,
                                pod_name=pod_name,
                                instance_url=external_url if external_url else None,
                            )
                            logger.info(
                                "instance_pod_created",
                                instance_id=updated_instance.id,
                                pod_name=pod_name,
                                external_url=external_url,
                            )
                        else:
                            logger.warning(
                                "k8s_pod_not_created",
                                instance_id=updated_instance.id,
                                reason="k8s_not_available",
                            )
                    except Exception as e:
                        # Log error but don't fail - pod creation is best-effort
                        # The reconciliation job will retry failed pods
                        logger.exception(
                            "wrapper_pod_creation_failed",
                            instance_id=updated_instance.id,
                            error=str(e),
                        )

                transitioned_to_starting += 1
                logger.info(
                    "instance_transitioned_to_starting",
                    instance_id=instance.id,
                    snapshot_id=snapshot.id,
                )

            elif snapshot.status == SnapshotStatus.FAILED:
                # Snapshot failed - mark instance as failed too
                error_message = snapshot.error_message or "Snapshot creation failed"
                await instance_repo.update_status(
                    instance_id=instance.id,
                    status=InstanceStatus.FAILED,
                    error_code=InstanceErrorCode.DATA_LOAD_ERROR,
                    error_message=f"Snapshot failed: {error_message}",
                )
                transitioned_to_failed += 1
                logger.info(
                    "instance_transitioned_to_failed",
                    instance_id=instance.id,
                    snapshot_id=snapshot.id,
                    reason="snapshot_failed",
                    snapshot_error=error_message,
                )

            elif snapshot.status == SnapshotStatus.CANCELLED:
                # Snapshot was cancelled - mark instance as failed
                await instance_repo.update_status(
                    instance_id=instance.id,
                    status=InstanceStatus.FAILED,
                    error_code=InstanceErrorCode.DATA_LOAD_ERROR,
                    error_message="Snapshot creation was cancelled",
                )
                transitioned_to_failed += 1
                logger.info(
                    "instance_transitioned_to_failed",
                    instance_id=instance.id,
                    snapshot_id=snapshot.id,
                    reason="snapshot_cancelled",
                )

            else:
                # Snapshot still pending/creating - skip for now
                still_waiting += 1
                logger.debug(
                    "instance_still_waiting",
                    instance_id=instance.id,
                    snapshot_id=snapshot.id,
                    snapshot_status=snapshot.status.value,
                )

        except Exception as e:
            errors += 1
            logger.exception(
                "instance_orchestration_error",
                instance_id=instance.id,
                error=str(e),
            )

    # Record transition metrics
    if transitioned_to_starting > 0:
        metrics.instances_transitioned_to_starting_total.inc(transitioned_to_starting)
    if transitioned_to_failed > 0:
        metrics.instances_transitioned_to_failed_total.inc(transitioned_to_failed)

    logger.info(
        "instance_orchestration_completed",
        processed=len(waiting_instances),
        transitioned=transitioned_to_starting,
        failed=transitioned_to_failed,
        skipped=still_waiting,
        errors=errors,
    )

    return {
        "processed": len(waiting_instances),
        "transitioned": transitioned_to_starting,
        "failed": transitioned_to_failed,
        "skipped": still_waiting,
        "errors": errors,
    }
