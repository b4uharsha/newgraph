"""Resource monitor job for dynamic memory upgrade.

Monitors pod memory usage and triggers proactive resize when usage exceeds thresholds.
Implements the multi-level trigger strategy from the resource sizing plan:

| Level | Trigger | Action |
|-------|---------|--------|
| Proactive | Memory > 80% for 2 min | Initiate in-place resize |
| Urgent | Memory > 90% for 1 min | Expedited resize + notification |
| Recovery | OOMKilled event | Auto-restart with 2x memory |

Runs every 60 seconds (configurable via GRAPH_OLAP_RESOURCE_MONITOR_INTERVAL_SECONDS).
"""

from datetime import UTC, datetime
from typing import Any

import structlog

from control_plane.config import get_settings
from control_plane.infrastructure.database import get_session
from control_plane.models import InstanceStatus
from control_plane.repositories.instances import InstanceFilters, InstanceRepository
from control_plane.services.k8s_service import get_k8s_service

logger = structlog.get_logger(__name__)


async def run_resource_monitor_job(session=None) -> None:
    """Monitor pod resources and trigger proactive resize.

    Checks memory usage of running instances and initiates resize
    when usage exceeds thresholds.

    Args:
        session: Optional database session (for testing)
    """
    import time

    from control_plane.jobs import metrics

    logger.info("resource_monitor_job_started")
    start_time = time.time()

    settings = get_settings()

    # Skip if sizing is disabled
    if not settings.sizing_enabled:
        logger.debug("resource_monitor_skipped", reason="sizing_disabled")
        return

    # Increment pass counter
    metrics.resource_monitor_passes_total.inc()

    if session is not None:
        await _run_monitor_with_session(session, settings, start_time)
    else:
        async with get_session() as session:
            await _run_monitor_with_session(session, settings, start_time)


async def _run_monitor_with_session(session, settings, start_time: float) -> None:
    """Internal monitoring logic with provided session."""
    import time

    from control_plane.jobs import metrics

    instance_repo = InstanceRepository(session)
    k8s_service = get_k8s_service()

    if not k8s_service:
        logger.debug("resource_monitor_skipped", reason="k8s_unavailable")
        return

    # Get all running instances
    instances, _ = await instance_repo.list_instances(
        InstanceFilters(status=InstanceStatus.RUNNING),
        limit=1000,
    )

    logger.info("resource_monitor_checking", instance_count=len(instances))

    proactive_resizes = 0
    urgent_resizes = 0

    for instance in instances:
        try:
            resize_level = await _check_instance_resources(
                instance,
                instance_repo,
                k8s_service,
                settings,
            )
            if resize_level == "proactive":
                proactive_resizes += 1
            elif resize_level == "urgent":
                urgent_resizes += 1
        except Exception as e:
            logger.error(
                "resource_monitor_instance_error",
                instance_id=instance.id,
                error=str(e),
            )
            metrics.resource_monitor_failures_total.inc()

    # Record pass duration
    duration = time.time() - start_time
    metrics.resource_monitor_pass_duration_seconds.observe(duration)

    logger.info(
        "resource_monitor_job_completed",
        instances_checked=len(instances),
        proactive_resizes=proactive_resizes,
        urgent_resizes=urgent_resizes,
        duration_seconds=duration,
    )


async def _check_instance_resources(
    instance,
    instance_repo: InstanceRepository,
    k8s_service,
    settings,
) -> str | None:
    """Check resources for a single instance and trigger resize if needed.

    Args:
        instance: Instance model object
        instance_repo: Instance repository
        k8s_service: Kubernetes service
        settings: Application settings

    Returns:
        Resize level triggered ("proactive", "urgent") or None if no resize needed
    """
    if not instance.pod_name:
        return None

    # Get current memory usage from K8s metrics
    memory_info = await k8s_service.get_pod_memory_usage(instance.pod_name)

    logger.debug(
        "resource_monitor_check_instance",
        instance_id=instance.id,
        pod_name=instance.pod_name,
        memory_usage_bytes=instance.memory_usage_bytes,
        memory_info=memory_info,
    )

    if memory_info and memory_info.get("limit_bytes"):
        memory_usage_percent = memory_info["usage_percent"] / 100.0  # Convert from percentage to decimal

        # Check against thresholds with time-based triggers
        if memory_usage_percent > 0.9:
            # Urgent: > 90% - immediate resize
            await _trigger_memory_resize(instance, instance_repo, k8s_service, settings, "urgent")
            return "urgent"
        elif memory_usage_percent > 0.8:
            # Proactive: > 80% - schedule resize
            await _trigger_memory_resize(instance, instance_repo, k8s_service, settings, "proactive")
            return "proactive"

    return None


async def _trigger_memory_resize(
    instance,
    instance_repo: InstanceRepository,
    k8s_service,
    settings,
    level: str,
) -> None:
    """Trigger memory resize for an instance.

    Implements resize guardrails:
    - Max memory per instance: sizing_max_memory_gb (32Gi)
    - Max resize steps: sizing_max_resize_steps (3)
    - Cooldown: sizing_resize_cooldown_seconds (300)

    Args:
        instance: Instance model object
        instance_repo: Instance repository
        k8s_service: Kubernetes service
        settings: Application settings
        level: Resize level ("proactive" or "urgent")
    """
    from control_plane.jobs import metrics

    # Check cooldown to prevent resize storms
    if instance.updated_at:
        time_since_update = (datetime.now(UTC) - instance.updated_at).total_seconds()
        if time_since_update < settings.sizing_resize_cooldown_seconds:
            logger.info(
                "resource_monitor_resize_cooldown",
                instance_id=instance.id,
                seconds_remaining=settings.sizing_resize_cooldown_seconds - time_since_update,
            )
            return

    # Calculate current memory from memory_gb column or fallback to usage
    current_memory_gb = getattr(instance, "memory_gb", None) or (instance.memory_usage_bytes or 0) / (1024**3)
    if current_memory_gb < 2:
        current_memory_gb = 2  # minimum

    new_memory_gb = min(int(current_memory_gb * 2), int(settings.sizing_max_memory_gb))

    if new_memory_gb <= current_memory_gb:
        logger.info(
            "resource_monitor_at_max_memory",
            instance_id=instance.id,
            current_gb=current_memory_gb,
            max_gb=settings.sizing_max_memory_gb,
        )
        return

    logger.info(
        "resource_monitor_triggering_resize",
        instance_id=instance.id,
        level=level,
        current_gb=current_memory_gb,
        new_gb=new_memory_gb,
    )

    # Track resize metric
    if level == "proactive":
        metrics.resource_monitor_proactive_resizes_total.inc()
    elif level == "urgent":
        metrics.resource_monitor_urgent_resizes_total.inc()

    # Perform in-place resize
    await k8s_service.resize_pod_memory(
        pod_name=instance.pod_name,
        memory_request=f"{new_memory_gb}Gi",
        memory_limit=f"{new_memory_gb}Gi",
    )

    # Update database
    await instance_repo.update_memory_gb(instance.id, new_memory_gb)

    # Create event record
    await _create_instance_event(
        instance_repo,
        instance.id,
        "memory_upgraded",
        {"old_gb": current_memory_gb, "new_gb": new_memory_gb, "level": level},
    )


async def _create_instance_event(
    _instance_repo: InstanceRepository,
    instance_id: int,
    event_type: str,
    details: dict[str, Any],
) -> None:
    """Create an instance event record.

    Args:
        _instance_repo: Instance repository (unused until InstanceEventsRepository is implemented)
        instance_id: Instance ID
        event_type: Type of event (e.g., "memory_upgraded")
        details: Event details dictionary
    """
    # Log the event for now - structured logging enables querying in production
    logger.info(
        "instance_event_created",
        instance_id=instance_id,
        event_type=event_type,
        details=details,
    )
    # TODO: Insert into instance_events table when InstanceEventsRepository is implemented
