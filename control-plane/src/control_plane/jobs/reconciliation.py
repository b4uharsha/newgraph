"""Reconciliation job for detecting and fixing state drift.

Reconciles database instance state with Kubernetes pod state to detect and fix:
1. Orphaned pods (pod exists but no database instance)
2. Missing pods (database instance exists but pod missing)
3. Status drift (database says "running" but pod is Failed)

Runs every 5 minutes (configurable via GRAPH_OLAP_RECONCILIATION_JOB_INTERVAL_SECONDS).
"""

import time

import structlog

from control_plane.infrastructure.database import get_session
from control_plane.jobs import metrics
from control_plane.models import InstanceErrorCode, InstanceStatus
from control_plane.repositories.instances import InstanceRepository
from control_plane.services.k8s_service import get_k8s_service

logger = structlog.get_logger(__name__)


async def run_reconciliation_job(session=None) -> None:
    """Reconcile database state with Kubernetes state.

    Detects and fixes:
    - Orphaned pods (K8s pod exists but no database instance)
    - Missing pods (database instance exists but pod missing)
    - Status drift (database status doesn't match pod status)

    Args:
        session: Optional database session (for testing). If None, creates a new session.
    """
    logger.info("reconciliation_job_started")
    start_time = time.time()

    # Increment reconciliation pass counter
    metrics.reconciliation_passes_total.inc()

    # Use provided session or create a new one
    if session is not None:
        await _run_reconciliation_with_session(session, start_time)
    else:
        async with get_session() as session:
            await _run_reconciliation_with_session(session, start_time)


async def _run_reconciliation_with_session(session, start_time: float) -> None:
    """Internal reconciliation logic with provided session."""
    instance_repo = InstanceRepository(session)
    k8s_service = get_k8s_service()

    # Get all instances from database
    db_instances = await instance_repo.list_all()

    # Get all wrapper pods from Kubernetes
    k8s_pods = await k8s_service.list_wrapper_pods()

    # Build lookup maps
    db_by_pod_name = {inst.pod_name: inst for inst in db_instances if inst.pod_name}
    k8s_by_name = {pod.metadata.name: pod for pod in k8s_pods}

    logger.info(
        "reconciliation_state_loaded",
        db_instances=len(db_instances),
        k8s_pods=len(k8s_pods),
        tracked_pod_names=len(db_by_pod_name),
    )

    # Phase 1: Detect orphaned pods (pod exists but no database instance)
    orphaned_pods = []
    for pod_name, _pod in k8s_by_name.items():
        if pod_name not in db_by_pod_name:
            orphaned_pods.append(pod_name)

    # Phase 2: Detect missing pods (database instance exists but pod missing)
    missing_pods = []
    for instance in db_instances:
        if (
            instance.pod_name
            and instance.pod_name not in k8s_by_name
            and instance.status in [InstanceStatus.STARTING, InstanceStatus.RUNNING, InstanceStatus.STOPPING]
        ):
            missing_pods.append(instance)

    # Phase 3: Detect status drift
    status_drift = []
    for instance in db_instances:
        if not instance.pod_name:
            continue
        pod = k8s_by_name.get(instance.pod_name)
        if pod:
            pod_phase = pod.status.phase
            # Database says running but pod is failed
            if instance.status == InstanceStatus.RUNNING and pod_phase == "Failed":
                status_drift.append((instance, pod))

    # Update current state gauges (before cleanup)
    metrics.orphaned_pods_detected_current.set(len(orphaned_pods))

    # Execute fixes
    orphaned_cleaned = await _cleanup_orphaned_pods(k8s_service, orphaned_pods)
    missing_handled = await _handle_missing_pods(instance_repo, missing_pods)
    drift_fixed = await _fix_status_drift(instance_repo, status_drift)

    # Update state gauges after cleanup
    metrics.orphaned_pods_detected_current.set(0)  # All cleaned

    # System state metrics removed from Prometheus - use /api/ops/state REST endpoint instead
    # Prometheus metrics focus on Four Golden Signals (Latency, Traffic, Errors, Saturation)
    # Point-in-time system state queries belong in REST APIs, not time-series metrics

    # Record pass duration
    duration = time.time() - start_time
    metrics.reconciliation_pass_duration_seconds.observe(duration)

    # Record specific metrics
    metrics.orphaned_pods_detected_total.inc(len(orphaned_pods))
    metrics.missing_pods_detected_total.inc(len(missing_pods))
    metrics.status_drift_detected_total.inc(len(status_drift))

    # Update database connection pool metrics (Saturation - Fourth Golden Signal)
    from control_plane.infrastructure.database import get_engine

    engine = get_engine()
    pool = engine.pool
    metrics.database_connections.labels(state="total").set(pool.size())
    metrics.database_connections.labels(state="in_use").set(pool.checkedout())
    metrics.database_connections.labels(state="available").set(pool.size() - pool.checkedout())

    logger.info(
        "reconciliation_job_completed",
        orphaned_pods_cleaned=orphaned_cleaned,
        missing_pods_handled=missing_handled,
        status_drift_fixed=drift_fixed,
        duration_seconds=duration,
    )


async def _cleanup_orphaned_pods(k8s_service: any, pod_names: list[str]) -> int:
    """Delete pods that have no database instance.

    Args:
        k8s_service: K8s service instance
        pod_names: List of orphaned pod names

    Returns:
        Number of pods successfully deleted
    """
    deleted_count = 0

    for pod_name in pod_names:
        try:
            logger.warning("orphaned_pod_detected", pod_name=pod_name)
            deleted = await k8s_service.delete_wrapper_pod_by_name(pod_name, grace_period_seconds=30)
            if deleted:
                logger.info("orphaned_pod_deleted", pod_name=pod_name)
                deleted_count += 1
                metrics.orphaned_pods_cleaned_total.inc()
        except Exception as e:
            logger.error("orphaned_pod_deletion_failed", pod_name=pod_name, error=str(e))
            metrics.orphaned_pods_cleanup_failures_total.inc()

    return deleted_count


async def _handle_missing_pods(instance_repo: InstanceRepository, instances: list) -> int:
    """Handle instances where pod is missing but database expects it.

    For STOPPING instances: Deletes the DB record (termination completed)
    For STARTING/RUNNING instances: Captures pod logs/diagnostics, then marks as failed

    Args:
        instance_repo: Instance repository
        instances: List of instances with missing pods

    Returns:
        Number of instances successfully handled
    """
    handled_count = 0
    k8s_service = get_k8s_service()

    for instance in instances:
        try:
            logger.warning(
                "missing_pod_detected",
                instance_id=instance.id,
                pod_name=instance.pod_name,
                status=instance.status.value,
            )

            # For STOPPING instances: Delete DB record (termination was called, pod is gone)
            if instance.status == InstanceStatus.STOPPING:
                deleted = await instance_repo.delete(instance.id)
                if deleted:
                    logger.info(
                        "stopping_instance_cleaned_up",
                        instance_id=instance.id,
                        pod_name=instance.pod_name,
                    )
                    handled_count += 1
                    metrics.missing_pods_handled_total.inc()
            else:
                # Capture diagnostics before the pod is garbage-collected
                failure_info = await k8s_service.get_pod_failure_info(instance.pod_name)
                logger.error(
                    "pod_failure_diagnostics",
                    instance_id=instance.id,
                    pod_name=instance.pod_name,
                    diagnostics=failure_info,
                )

                # For STARTING/RUNNING: Mark as failed (unexpected pod loss)
                error_msg = f"Pod {instance.pod_name} disappeared: {failure_info}"
                # Truncate to fit in error_message column (typically 4096 chars)
                if len(error_msg) > 4000:
                    error_msg = error_msg[:4000] + "..."
                updated = await instance_repo.update_status(
                    instance_id=instance.id,
                    status=InstanceStatus.FAILED,
                    error_code=InstanceErrorCode.UNEXPECTED_TERMINATION,
                    error_message=error_msg,
                )
                if updated:
                    logger.info("missing_pod_instance_failed", instance_id=instance.id)
                    handled_count += 1
                    metrics.missing_pods_handled_total.inc()
        except Exception as e:
            logger.error("missing_pod_handling_failed", instance_id=instance.id, error=str(e))

    return handled_count


async def _fix_status_drift(instance_repo: InstanceRepository, drifts: list[tuple]) -> int:
    """Fix instances where database status doesn't match pod status.

    Captures pod diagnostics (container exit codes, termination reasons,
    last log lines) before marking the instance as failed.

    Args:
        instance_repo: Instance repository
        drifts: List of (instance, pod) tuples with status drift

    Returns:
        Number of drifts successfully fixed
    """
    fixed_count = 0
    k8s_service = get_k8s_service()

    for instance, pod in drifts:
        try:
            # Capture diagnostics while the pod still exists
            failure_info = await k8s_service.get_pod_failure_info(instance.pod_name)
            logger.error(
                "status_drift_detected",
                instance_id=instance.id,
                db_status=instance.status.value,
                pod_phase=pod.status.phase,
                diagnostics=failure_info,
            )
            error_msg = f"Pod entered {pod.status.phase} phase: {failure_info}"
            if len(error_msg) > 4000:
                error_msg = error_msg[:4000] + "..."
            updated = await instance_repo.update_status(
                instance_id=instance.id,
                status=InstanceStatus.FAILED,
                error_code=InstanceErrorCode.UNEXPECTED_TERMINATION,
                error_message=error_msg,
            )
            if updated:
                logger.info("status_drift_fixed", instance_id=instance.id)
                fixed_count += 1
                metrics.status_drift_fixed_total.inc()
        except Exception as e:
            logger.error("status_drift_fix_failed", instance_id=instance.id, error=str(e))

    return fixed_count
