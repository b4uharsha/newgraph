---
title: "Instance Lifecycle Management & Reconciliation Design"
scope: hsbc
---

# Instance Lifecycle Management & Reconciliation Design

## Overview

This document proposes a comprehensive design for **graph instance** lifecycle management, addressing critical gaps discovered during production analysis where orphaned wrapper pods persist without database correlation, leading to unreclaimed resources and operational issues. This applies to all wrapper types (Ryugraph and FalkorDB).

## Implementation Status

**Status:** ✅ **IMPLEMENTED** (2025-12-21)

**Implemented Components:**
- ✅ Pod name persistence fix (instance_service.py:217-232, :355-370)
- ✅ K8s service enhancements (list_wrapper_pods, delete_wrapper_pod_by_name, get_pod_status_by_name)
- ✅ Background job scheduler (APScheduler integration)
- ✅ Reconciliation job (orphan pod cleanup, state drift detection)
- ✅ Lifecycle job (TTL/inactivity enforcement)
- ✅ Export reconciliation job (worker crash recovery)
- ✅ Schema cache job (placeholder, awaiting Starburst client)
- ✅ Prometheus metrics (comprehensive instrumentation)
- ✅ /metrics endpoint
- ✅ Repository methods (list_all, reset_to_pending)

**See Also:**
- [control-plane.background-jobs.design.md](-/control-plane.background-jobs.design.md) - Complete background jobs implementation design

## Prerequisites

- [ryugraph-wrapper.design.md](-/ryugraph-wrapper.design.md) - Wrapper lifecycle, startup sequence
- [control-plane.design.md](-/control-plane.design.md) - Control plane architecture
- [control-plane.services.design.md](-/control-plane.services.design.md) - Service layer patterns
- [api.instances.spec.md](--/system-design/api/api.instances.spec.md) - Instance API
- [api.internal.spec.md](--/system-design/api/api.internal.spec.md) - Internal wrapper→CP communication
- [data.model.spec.md](--/system-design/data.model.spec.md) - Database schema
- [architectural.guardrails.md](--/foundation/architectural.guardrails.md) - System constraints

## Problem Statement

### Critical Findings from Production Analysis

**Date**: 2025-12-21
**Environment**: k3d-graph-olap-dev (local dev cluster)
**Cluster Age**: 43 hours
**Discovery**: 6 orphaned wrapper pods (3 Running, 3 Failed) with zero database correlation

#### Root Cause Analysis

```
Database State:
- 9 instances in database (3 "running", 6 "stopping")
- pod_name = NULL for ALL 9 instances
- No pod tracking whatsoever

Kubernetes State:
- 6 wrapper pods exist (created 37-38h ago from e2e tests)
- Pod names: wrapper-{uuid} format
- No mechanism to correlate pods ↔ database instances

The Gap:
Control plane creates pods but NEVER persists pod_name to database.
Wrappers fail to call back via internal API during startup failures.
No reconciliation loop to detect and clean up orphaned resources.
```

#### Evidence Chain

1. **Pod Creation Code** (`control-plane/src/control_plane/services/instance_service.py:208-226`):
   ```python
   pod_name, external_url = await self._k8s_service.create_wrapper_pod(...)
   if pod_name:
       if external_url:
           instance = await self._instance_repo.update_status(
               instance_id=instance.id,
               status=InstanceStatus.STARTING,
               instance_url=external_url,  # ✅ Persisted
               # ❌ pod_name NOT included here!
           )
   ```

2. **Database Schema** (`instances` table):
   - `pod_name` column exists but is NEVER populated by control plane
   - Only populated IF wrapper successfully calls `/internal/instances/{id}/status`
   - Startup failures = pod never tracked

3. **Failure Mode**:
   - Control plane: Creates pod → does NOT persist pod_name
   - Wrapper: Fails during startup → does NOT call back
   - Database: Instance stuck in "starting" with pod_name=NULL
   - Kubernetes: Pod exists (possibly Failed) → no cleanup
   - Result: **Orphaned pod consuming resources forever**

### Severity Assessment

| Issue | Severity | Impact |
|-------|----------|--------|
| Resource leaks | **CRITICAL** | Memory/CPU waste, cost escalation in GKE |
| Operational visibility | **HIGH** | Cannot identify which pods belong to which instances |
| Instance cleanup failure | **CRITICAL** | DELETE /instances/:id cannot terminate pod (no pod_name) |
| Recovery impossible | **HIGH** | No way to detect or fix orphaned state |
| Cost impact | **HIGH** | Orphaned pods run indefinitely on billable infrastructure |

## Design Goals

1. **100% Pod-Instance Correlation**: Every Kubernetes pod MUST have a corresponding database instance with accurate pod_name tracking
2. **Fail-Safe Cleanup**: Orphaned pods (database entry deleted but pod still running) must be automatically detected and removed
3. **Observability**: Operators must be able to identify mismatches between database and Kubernetes state
4. **Reconciliation**: Automated background process to detect and fix state drift
5. **Idempotency**: All operations must be safe to retry
6. **Minimal MTTR**: Reduce mean time to recovery for orphaned resources from ∞ (never) to <5 minutes

## Architecture

### 1. Pod Name Persistence (Immediate Fix)

**Change Control Plane to persist pod_name IMMEDIATELY after pod creation**

```python
# control-plane/src/control_plane/services/instance_service.py

async def create_instance(self, ...) -> Instance:
    # ... existing code ...

    try:
        logger.info("k8s_pod_creating", instance_id=instance.id, url_slug=instance.url_slug)
        pod_name, external_url = await self._k8s_service.create_wrapper_pod(
            instance_id=instance.id,
            url_slug=instance.url_slug,
            snapshot_id=snapshot.id,
            mapping_id=snapshot.mapping_id,
            mapping_version=snapshot.mapping_version,
            owner_username=user.username,
            gcs_path=snapshot.gcs_path,
        )

        # ✅ FIX: Persist pod_name IMMEDIATELY after creation
        if pod_name:
            logger.info("wrapper_pod_created", pod_name=pod_name, instance_id=instance.id)
            instance = await self._instance_repo.update_status(
                instance_id=instance.id,
                status=InstanceStatus.STARTING,
                pod_name=pod_name,  # ✅ NOW TRACKED
                instance_url=external_url if external_url else None,
            )
        else:
            logger.warning("k8s_pod_not_created", instance_id=instance.id, reason="k8s_not_available")

    except Exception as e:
        # Pod creation failed - instance remains without pod_name (acceptable)
        logger.error("k8s_pod_creation_failed", instance_id=instance.id, error=str(e))
        # Don't fail the whole operation - reconciliation will handle cleanup
```

**Impact**:
- Pod tracking now occurs at creation time (not callback time)
- Survives wrapper startup failures
- Enables cleanup via DELETE /instances/:id
- Foundation for reconciliation

### 2. Wrapper Callback Enhancement

**Ensure wrapper always attempts to update pod_name even if already set**

```python
# ryugraph-wrapper/src/wrapper/lifespan.py

async def startup(app: FastAPI) -> None:
    """Initialize the wrapper on startup."""
    config = Config.from_env()
    cp_client = ControlPlaneClient(...)

    # Get pod metadata
    pod_name = os.getenv("HOSTNAME")  # Pod name from K8s
    pod_ip = get_pod_ip()

    try:
        # ✅ ALWAYS report pod_name + pod_ip at startup
        await cp_client.update_status(
            instance_id=config.instance_id,
            status="starting",
            pod_name=pod_name,      # ✅ Redundant but safe
            pod_ip=pod_ip,          # ✅ Track IP for debugging
        )

        # ... rest of startup logic ...

        # Report running status
        await cp_client.update_status(
            instance_id=config.instance_id,
            status="running",
            pod_name=pod_name,      # ✅ Confirm pod identity
            pod_ip=pod_ip,
            graph_stats=graph_stats,
        )

    except Exception as e:
        # ✅ ALWAYS report failure with pod metadata
        await cp_client.update_status(
            instance_id=config.instance_id,
            status="failed",
            pod_name=pod_name,      # ✅ Track failed pod
            pod_ip=pod_ip,
            error_message=str(e),
            error_code=classify_error(e),
            stack_trace=traceback.format_exc(),
        )
        raise
```

### 3. Reconciliation Service

**New background service to detect and fix state drift**

```python
# control-plane/src/control_plane/services/reconciliation_service.py

from typing import Protocol
import asyncio
import structlog
from datetime import datetime, timezone, timedelta

logger = structlog.get_logger(__name__)


class ReconciliationService:
    """Reconciles database instance state with Kubernetes pod state.

    Detects and fixes:
    1. Orphaned pods (pod exists but no database instance)
    2. Missing pods (database instance exists but pod missing)
    3. Status drift (database says "running" but pod is Failed)
    4. TTL expiry (instances past their ttl deadline)
    5. Inactivity timeout (instances with no activity)
    """

    def __init__(
        self,
        instance_repo: InstanceRepository,
        k8s_service: K8sService,
        interval_seconds: int = 300,  # 5 minutes
    ):
        self._instance_repo = instance_repo
        self._k8s = k8s_service
        self._interval = interval_seconds
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start reconciliation loop."""
        if self._running:
            logger.warning("reconciliation_already_running")
            return

        self._running = True
        self._task = asyncio.create_task(self._reconciliation_loop())
        logger.info("reconciliation_started", interval_seconds=self._interval)

    async def stop(self) -> None:
        """Stop reconciliation loop gracefully."""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("reconciliation_stopped")

    async def _reconciliation_loop(self) -> None:
        """Main reconciliation loop."""
        while self._running:
            try:
                await self._reconcile_once()
            except Exception as e:
                logger.exception("reconciliation_error", error=str(e))

            # Sleep until next cycle
            await asyncio.sleep(self._interval)

    async def _reconcile_once(self) -> None:
        """Single reconciliation pass."""
        logger.info("reconciliation_pass_started")

        # Get all instances from database
        db_instances = await self._instance_repo.list_all()

        # Get all wrapper pods from Kubernetes
        k8s_pods = await self._k8s.list_wrapper_pods()

        # Build lookup maps
        db_by_pod_name = {inst.pod_name: inst for inst in db_instances if inst.pod_name}
        db_by_id = {inst.id: inst for inst in db_instances}
        k8s_by_name = {pod.metadata.name: pod for pod in k8s_pods}

        # Detect orphaned pods (pod exists but no database instance)
        orphaned_pods = []
        for pod_name, pod in k8s_by_name.items():
            if pod_name not in db_by_pod_name:
                orphaned_pods.append(pod_name)

        # Detect missing pods (database instance exists but pod missing)
        missing_pods = []
        for instance in db_instances:
            if instance.pod_name and instance.pod_name not in k8s_by_name:
                if instance.status in [InstanceStatus.STARTING, InstanceStatus.RUNNING]:
                    missing_pods.append(instance)

        # Detect status drift
        status_drift = []
        for instance in db_instances:
            if not instance.pod_name:
                continue
            pod = k8s_by_name.get(instance.pod_name)
            if pod:
                pod_phase = pod.status.phase
                if instance.status == InstanceStatus.RUNNING and pod_phase == "Failed":
                    status_drift.append((instance, pod))

        # Detect TTL expiry
        ttl_expired = []
        now = datetime.now(timezone.utc)
        for instance in db_instances:
            if instance.ttl and instance.created_at:
                expiry_time = instance.created_at + instance.ttl
                if now > expiry_time and instance.status != InstanceStatus.FAILED:
                    ttl_expired.append(instance)

        # Detect inactivity timeout
        inactive = []
        for instance in db_instances:
            if instance.inactivity_timeout and instance.last_activity_at:
                inactive_deadline = instance.last_activity_at + instance.inactivity_timeout
                if now > inactive_deadline and instance.status == InstanceStatus.RUNNING:
                    inactive.append(instance)

        # Execute fixes
        await self._cleanup_orphaned_pods(orphaned_pods)
        await self._handle_missing_pods(missing_pods)
        await self._fix_status_drift(status_drift)
        await self._expire_ttl_instances(ttl_expired)
        await self._timeout_inactive_instances(inactive)

        logger.info(
            "reconciliation_pass_completed",
            orphaned_pods_cleaned=len(orphaned_pods),
            missing_pods_handled=len(missing_pods),
            status_drift_fixed=len(status_drift),
            ttl_expired=len(ttl_expired),
            inactive_terminated=len(inactive),
        )

    async def _cleanup_orphaned_pods(self, pod_names: list[str]) -> None:
        """Delete pods that have no database instance."""
        for pod_name in pod_names:
            try:
                logger.warning("orphaned_pod_detected", pod_name=pod_name)
                await self._k8s.delete_pod(pod_name, grace_period_seconds=30)
                logger.info("orphaned_pod_deleted", pod_name=pod_name)
            except Exception as e:
                logger.error("orphaned_pod_deletion_failed", pod_name=pod_name, error=str(e))

    async def _handle_missing_pods(self, instances: list[Instance]) -> None:
        """Handle instances where pod is missing but database expects it."""
        for instance in instances:
            try:
                logger.warning(
                    "missing_pod_detected",
                    instance_id=instance.id,
                    pod_name=instance.pod_name,
                    status=instance.status.value,
                )
                # Mark instance as failed since its pod is gone
                await self._instance_repo.update_status(
                    instance_id=instance.id,
                    status=InstanceStatus.FAILED,
                    error_code=InstanceErrorCode.UNEXPECTED_TERMINATION,
                    error_message=f"Pod {instance.pod_name} disappeared from Kubernetes",
                )
                logger.info("missing_pod_instance_failed", instance_id=instance.id)
            except Exception as e:
                logger.error("missing_pod_handling_failed", instance_id=instance.id, error=str(e))

    async def _fix_status_drift(self, drifts: list[tuple[Instance, Any]]) -> None:
        """Fix instances where database status doesn't match pod status."""
        for instance, pod in drifts:
            try:
                logger.warning(
                    "status_drift_detected",
                    instance_id=instance.id,
                    db_status=instance.status.value,
                    pod_phase=pod.status.phase,
                )
                await self._instance_repo.update_status(
                    instance_id=instance.id,
                    status=InstanceStatus.FAILED,
                    error_code=InstanceErrorCode.UNEXPECTED_TERMINATION,
                    error_message=f"Pod entered {pod.status.phase} phase",
                )
                logger.info("status_drift_fixed", instance_id=instance.id)
            except Exception as e:
                logger.error("status_drift_fix_failed", instance_id=instance.id, error=str(e))

    async def _expire_ttl_instances(self, instances: list[Instance]) -> None:
        """Terminate instances that have exceeded their TTL."""
        for instance in instances:
            try:
                logger.info("ttl_expired", instance_id=instance.id, ttl=instance.ttl)
                # Use instance service to properly terminate
                await self._instance_service.terminate_instance(instance.id)
                logger.info("ttl_instance_terminated", instance_id=instance.id)
            except Exception as e:
                logger.error("ttl_expiry_failed", instance_id=instance.id, error=str(e))

    async def _timeout_inactive_instances(self, instances: list[Instance]) -> None:
        """Terminate instances that have exceeded inactivity timeout."""
        for instance in instances:
            try:
                logger.info(
                    "inactivity_timeout",
                    instance_id=instance.id,
                    last_activity=instance.last_activity_at,
                    timeout=instance.inactivity_timeout,
                )
                await self._instance_service.terminate_instance(instance.id)
                logger.info("inactive_instance_terminated", instance_id=instance.id)
            except Exception as e:
                logger.error("inactivity_termination_failed", instance_id=instance.id, error=str(e))
```

### 4. K8s Service Enhancements

**Add methods to support reconciliation**

```python
# control-plane/src/control_plane/services/k8s_service.py

class K8sService:
    """Kubernetes operations service."""

    async def list_wrapper_pods(self, namespace: str | None = None) -> list[V1Pod]:
        """List all wrapper pods in the namespace.

        Returns pods with label selector matching any wrapper type.
        """
        namespace = namespace or self._namespace

        try:
            pods = await self._core_api.list_namespaced_pod(
                namespace=namespace,
                label_selector="app in (ryugraph-wrapper, falkordb-wrapper)",
            )
            return pods.items
        except ApiException as e:
            logger.error("list_pods_failed", namespace=namespace, error=str(e))
            return []

    async def get_pod_status(self, pod_name: str, namespace: str | None = None) -> dict:
        """Get detailed pod status.

        Returns:
            {
                "phase": "Running" | "Pending" | "Failed" | "Succeeded" | "Unknown",
                "ready": bool,
                "containers": [{"name": str, "ready": bool, "restart_count": int}],
            }
        """
        namespace = namespace or self._namespace

        try:
            pod = await self._core_api.read_namespaced_pod_status(
                name=pod_name,
                namespace=namespace,
            )
            return {
                "phase": pod.status.phase,
                "ready": all(
                    cond.status == "True"
                    for cond in pod.status.conditions or []
                    if cond.type == "Ready"
                ),
                "containers": [
                    {
                        "name": c.name,
                        "ready": c.ready,
                        "restart_count": c.restart_count,
                    }
                    for c in pod.status.container_statuses or []
                ],
            }
        except ApiException as e:
            if e.status == 404:
                return {"phase": "NotFound"}
            raise

    async def delete_pod(
        self,
        pod_name: str,
        namespace: str | None = None,
        grace_period_seconds: int = 30,
    ) -> bool:
        """Delete a pod.

        Args:
            pod_name: Pod name to delete
            namespace: Kubernetes namespace
            grace_period_seconds: Grace period for termination

        Returns:
            True if deleted, False if not found
        """
        namespace = namespace or self._namespace

        try:
            await self._core_api.delete_namespaced_pod(
                name=pod_name,
                namespace=namespace,
                body=client.V1DeleteOptions(grace_period_seconds=grace_period_seconds),
            )
            logger.info("k8s_pod_deleted", pod_name=pod_name)
            return True
        except ApiException as e:
            if e.status == 404:
                logger.warning("k8s_pod_not_found", pod_name=pod_name)
                return False
            logger.error("k8s_pod_deletion_failed", pod_name=pod_name, error=str(e))
            raise
```

### 5. Instance Termination Enhancement

**Ensure terminate uses pod_name from database**

```python
# control-plane/src/control_plane/services/instance_service.py

async def terminate_instance(self, instance_id: int, username: str) -> Instance:
    """Terminate a running instance.

    1. Verify ownership (unless ops role)
    2. Delete Kubernetes pod using tracked pod_name
    3. Delete service, ingress
    4. Update status to "stopping" -> eventual deletion by wrapper
    """
    instance = await self._instance_repo.get_by_id(instance_id)

    # Check authorization
    user = await self._user_repo.get_by_username(username)
    if user.role not in [UserRole.OPS, UserRole.ADMIN]:
        if instance.owner_username != username:
            raise PermissionDeniedError(f"User {username} cannot terminate instance owned by {instance.owner_username}")

    # Delete Kubernetes resources
    if instance.pod_name:
        # ✅ Use pod_name from database (now always tracked)
        await self._k8s_service.delete_wrapper_pod(
            url_slug=instance.url_slug,
            pod_name=instance.pod_name,  # ✅ Explicit pod name
        )
    else:
        # Fallback for legacy instances without pod_name
        logger.warning("terminate_instance_missing_pod_name", instance_id=instance_id)
        # Try deleting by url_slug convention
        await self._k8s_service.delete_wrapper_pod(url_slug=instance.url_slug)

    # Update status
    instance = await self._instance_repo.update_status(
        instance_id=instance_id,
        status=InstanceStatus.STOPPING,
    )

    logger.info("instance_termination_initiated", instance_id=instance_id, pod_name=instance.pod_name)
    return instance
```

### 6. Startup Integration

**Add reconciliation service to control plane lifespan**

```python
# control-plane/src/control_plane/main.py

from contextlib import asynccontextmanager
from control_plane.services.reconciliation_service import ReconciliationService

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("control_plane_starting")

    # Initialize database
    engine = create_engine(config.database_url)
    session_factory = create_session_factory(engine)

    # Initialize services
    instance_repo = InstanceRepository(session_factory)
    k8s_service = K8sService(config.k8s_namespace)
    instance_service = InstanceService(instance_repo, k8s_service, ...)

    # ✅ Initialize reconciliation service
    reconciliation_service = ReconciliationService(
        instance_repo=instance_repo,
        k8s_service=k8s_service,
        interval_seconds=config.reconciliation_interval_seconds,  # Default: 300
    )

    # Store in app state
    app.state.reconciliation_service = reconciliation_service

    # ✅ Start reconciliation loop
    await reconciliation_service.start()
    logger.info("reconciliation_service_started")

    yield

    # Shutdown
    logger.info("control_plane_stopping")

    # ✅ Stop reconciliation gracefully
    await reconciliation_service.stop()
    logger.info("reconciliation_service_stopped")

    await engine.dispose()
```

### 7. Configuration

**Add reconciliation settings to control plane config**

```python
# control-plane/src/control_plane/config.py

class Config(BaseSettings):
    # ... existing fields ...

    # Reconciliation settings
    reconciliation_enabled: bool = True
    reconciliation_interval_seconds: int = 300  # 5 minutes

    # Instance lifecycle settings
    enable_ttl_enforcement: bool = True
    enable_inactivity_timeout_enforcement: bool = True

    class Config:
        env_prefix = "CONTROL_PLANE_"
```

## Observability

### Metrics

```python
# control-plane/src/control_plane/services/reconciliation_service.py

from prometheus_client import Counter, Gauge, Histogram

# Reconciliation metrics
reconciliation_passes_total = Counter(
    "reconciliation_passes_total",
    "Total reconciliation passes executed",
)

reconciliation_pass_duration_seconds = Histogram(
    "reconciliation_pass_duration_seconds",
    "Duration of reconciliation pass",
)

orphaned_pods_detected_total = Counter(
    "orphaned_pods_detected_total",
    "Total orphaned pods detected and cleaned",
)

missing_pods_detected_total = Counter(
    "missing_pods_detected_total",
    "Total instances with missing pods",
)

status_drift_fixed_total = Counter(
    "status_drift_fixed_total",
    "Total instances with status drift fixed",
)

ttl_expired_instances_total = Counter(
    "ttl_expired_instances_total",
    "Total instances terminated due to TTL expiry",
)

inactive_instances_terminated_total = Counter(
    "inactive_instances_terminated_total",
    "Total instances terminated due to inactivity",
)

# State gauges
instances_without_pod_name_gauge = Gauge(
    "instances_without_pod_name",
    "Number of instances in database without pod_name tracked",
)

wrapper_pods_total_gauge = Gauge(
    "wrapper_pods_total",
    "Total wrapper pods in Kubernetes",
    ["phase"],  # Running, Failed, Pending, etc.
)
```

### Structured Logging

All reconciliation actions emit structured logs:

```json
{
  "event": "orphaned_pod_detected",
  "pod_name": "wrapper-abc123",
  "age_hours": 37,
  "namespace": "production"
}

{
  "event": "orphaned_pod_deleted",
  "pod_name": "wrapper-abc123",
  "duration_ms": 1234
}

{
  "event": "reconciliation_pass_completed",
  "orphaned_pods_cleaned": 6,
  "missing_pods_handled": 2,
  "status_drift_fixed": 1,
  "ttl_expired": 3,
  "inactive_terminated": 1,
  "duration_seconds": 8.7
}
```

### Dashboard

Grafana dashboard for instance lifecycle health:

**Panels**:
1. **Orphaned Pods Over Time** (graph: `orphaned_pods_detected_total`)
2. **Instances Without Pod Tracking** (gauge: `instances_without_pod_name_gauge`)
3. **Wrapper Pod Distribution by Phase** (pie chart: `wrapper_pods_total_gauge`)
4. **Reconciliation Pass Duration** (graph: `reconciliation_pass_duration_seconds`)
5. **TTL/Inactivity Cleanup Rate** (stacked graph: `ttl_expired_instances_total`, `inactive_instances_terminated_total`)

## Testing Strategy

### Unit Tests

```python
# control-plane/tests/unit/test_reconciliation_service.py

class TestReconciliationService:
    """Unit tests for ReconciliationService."""

    def test_detects_orphaned_pods(self, mock_instance_repo, mock_k8s_service):
        """Orphaned pods (in K8s but not in DB) are detected."""
        # Setup: K8s has wrapper-abc123, DB has no instances
        mock_k8s_service.list_wrapper_pods.return_value = [
            Mock(metadata=Mock(name="wrapper-abc123"))
        ]
        mock_instance_repo.list_all.return_value = []

        service = ReconciliationService(mock_instance_repo, mock_k8s_service)
        await service._reconcile_once()

        # Verify orphaned pod was deleted
        mock_k8s_service.delete_pod.assert_called_once_with("wrapper-abc123", grace_period_seconds=30)

    def test_detects_missing_pods(self, mock_instance_repo, mock_k8s_service):
        """Instances with pod_name but no K8s pod are marked as failed."""
        # Setup: DB has instance with pod_name, K8s has no pods
        instance = Mock(
            id=1,
            pod_name="wrapper-abc123",
            status=InstanceStatus.RUNNING,
        )
        mock_instance_repo.list_all.return_value = [instance]
        mock_k8s_service.list_wrapper_pods.return_value = []

        service = ReconciliationService(mock_instance_repo, mock_k8s_service)
        await service._reconcile_once()

        # Verify instance was marked as failed
        mock_instance_repo.update_status.assert_called_with(
            instance_id=1,
            status=InstanceStatus.FAILED,
            error_code=InstanceErrorCode.UNEXPECTED_TERMINATION,
            error_message=ANY,
        )

    def test_ttl_expiry(self, mock_instance_repo, mock_instance_service):
        """Instances past their TTL are terminated."""
        now = datetime.now(timezone.utc)
        instance = Mock(
            id=1,
            ttl=timedelta(hours=24),
            created_at=now - timedelta(hours=25),  # Expired
            status=InstanceStatus.RUNNING,
        )
        mock_instance_repo.list_all.return_value = [instance]

        service = ReconciliationService(mock_instance_repo, mock_k8s_service)
        await service._reconcile_once()

        # Verify instance was terminated
        mock_instance_service.terminate_instance.assert_called_once_with(1)
```

### Integration Tests

```python
# control-plane/tests/integration/test_reconciliation_integration.py

class TestReconciliationIntegration:
    """Integration tests for reconciliation with real database."""

    async def test_full_reconciliation_cycle(self, test_db, mock_k8s_service):
        """Full reconciliation cycle with database."""
        # Create instance in DB
        instance_repo = InstanceRepository(test_db)
        instance = await instance_repo.create(
            snapshot_id=1,
            owner_username="test-user",
            name="Test Instance",
        )

        # Simulate orphaned pod in K8s
        mock_k8s_service.list_wrapper_pods.return_value = [
            Mock(metadata=Mock(name="wrapper-orphan-123"))
        ]

        # Run reconciliation
        service = ReconciliationService(instance_repo, mock_k8s_service)
        await service._reconcile_once()

        # Verify orphaned pod was deleted
        assert mock_k8s_service.delete_pod.called
        assert "wrapper-orphan-123" in str(mock_k8s_service.delete_pod.call_args)
```

### E2E Tests

```python
# e2e-tests/notebooks/sdk_reconciliation_test.ipynb

# Test 1: Create instance, delete database record, verify pod cleanup
instance = client.instances.create(snapshot_id=1, name="Orphan Test")
instance_id = instance.id
pod_name = instance.pod_name

# Manually delete database record (simulating corruption)
# ... direct database manipulation ...

# Wait for reconciliation (max 5 minutes)
time.sleep(310)

# Verify pod was cleaned up
pods = k8s_client.list_namespaced_pod(namespace="e2e-test", label_selector="app in (ryugraph-wrapper, falkordb-wrapper)")
assert pod_name not in [p.metadata.name for p in pods.items]

# Test 2: Create instance, delete pod manually, verify database marked as failed
instance = client.instances.create(snapshot_id=1, name="Missing Pod Test")
pod_name = instance.pod_name

# Manually delete pod
k8s_client.delete_namespaced_pod(name=pod_name, namespace="e2e-test")

# Wait for reconciliation
time.sleep(310)

# Verify instance marked as failed
instance = client.instances.get(instance.id)
assert instance.status == "failed"
assert "disappeared" in instance.error_message.lower()
```

## Rollout Plan

### Phase 1: Pod Name Tracking (Week 1)

**Goal**: Fix immediate bug - persist pod_name at creation time

1. Update `instance_service.py` to persist pod_name immediately after pod creation
2. Update wrapper to always report pod_name in status callbacks
3. Deploy to staging
4. Run integration tests
5. Deploy to production
6. Monitor for 48 hours

**Success Criteria**:
- All new instances have pod_name tracked
- No regressions in instance creation

### Phase 2: Reconciliation Service (Week 2)

**Goal**: Add automated reconciliation

1. Implement `ReconciliationService` with unit tests
2. Add K8s service enhancements (`list_wrapper_pods`, `get_pod_status`)
3. Add integration tests
4. Deploy to staging with `reconciliation_enabled=false`
5. Manually trigger reconciliation to validate
6. Enable automatic reconciliation in staging
7. Monitor for 1 week

**Success Criteria**:
- Reconciliation detects and cleans orphaned pods
- No false positives (legitimate pods not deleted)
- Metrics show healthy operation

### Phase 3: Production Deployment (Week 3)

**Goal**: Enable in production with monitoring

1. Deploy to production with `reconciliation_enabled=true`
2. Set conservative interval (10 minutes initially)
3. Monitor metrics and logs
4. Gradually reduce interval to 5 minutes
5. Create Grafana dashboard
6. Set up alerts for reconciliation failures

**Success Criteria**:
- Zero orphaned pods after 24 hours
- All instances have pod_name tracked
- No incidents

### Phase 4: TTL/Inactivity Enforcement (Week 4)

**Goal**: Enforce lifecycle policies

1. Enable TTL enforcement in staging
2. Enable inactivity timeout in staging
3. Test with short TTLs (1 hour)
4. Monitor cleanup behavior
5. Deploy to production
6. Document user-facing behavior

**Success Criteria**:
- Instances automatically cleaned up after TTL
- Inactive instances terminated
- Users notified before termination

## Migration Strategy

### Handling Existing Orphaned Pods

**One-Time Cleanup Script**:

```python
# scripts/cleanup_orphaned_pods.py

async def cleanup_orphaned_pods():
    """One-time script to clean up existing orphaned pods."""
    k8s_service = K8sService(namespace="production")
    instance_repo = InstanceRepository(session_factory)

    # Get all pods
    pods = await k8s_service.list_wrapper_pods()

    # Get all instances
    instances = await instance_repo.list_all()
    instance_pod_names = {inst.pod_name for inst in instances if inst.pod_name}

    # Find orphans
    orphaned = [pod for pod in pods if pod.metadata.name not in instance_pod_names]

    print(f"Found {len(orphaned)} orphaned pods")

    # Prompt for confirmation
    if input("Delete orphaned pods? (yes/no): ") != "yes":
        print("Aborted")
        return

    # Delete orphans
    for pod in orphaned:
        print(f"Deleting {pod.metadata.name}...")
        await k8s_service.delete_pod(pod.metadata.name)

    print(f"Cleanup complete. Deleted {len(orphaned)} pods.")

# Run: python -m scripts.cleanup_orphaned_pods
```

### Backfilling pod_name for Existing Instances

For instances created before pod_name tracking:

```python
# scripts/backfill_pod_names.py

async def backfill_pod_names():
    """Backfill pod_name for instances created before tracking."""
    k8s_service = K8sService(namespace="production")
    instance_repo = InstanceRepository(session_factory)

    # Get all instances without pod_name
    instances = await instance_repo.list_all()
    missing_pod_name = [inst for inst in instances if not inst.pod_name and inst.status in ["starting", "running"]]

    print(f"Found {len(missing_pod_name)} instances without pod_name")

    # Try to correlate by url_slug
    pods = await k8s_service.list_wrapper_pods()
    for instance in missing_pod_name:
        expected_pod_name = f"wrapper-{instance.url_slug}"
        pod = next((p for p in pods if p.metadata.name == expected_pod_name), None)

        if pod:
            print(f"Found pod {expected_pod_name} for instance {instance.id}")
            await instance_repo.update_status(
                instance_id=instance.id,
                pod_name=expected_pod_name,
            )
        else:
            print(f"No pod found for instance {instance.id} (expected {expected_pod_name})")
            # Mark as failed since pod is missing
            await instance_repo.update_status(
                instance_id=instance.id,
                status=InstanceStatus.FAILED,
                error_code=InstanceErrorCode.UNEXPECTED_TERMINATION,
                error_message="Pod not found during backfill",
            )

    print("Backfill complete")
```

## Operational Runbook

### Detecting Orphaned Pods

**Via Metrics**:
```promql
# Orphaned pods detected in last hour
increase(orphaned_pods_detected_total[1h])

# Instances without pod tracking
instances_without_pod_name > 0
```

**Via CLI**:
```bash
# List all wrapper pods (both Ryugraph and FalkorDB)
kubectl get pods -n production -l 'app in (ryugraph-wrapper, falkordb-wrapper)'

# Query database for instances
psql -c "SELECT id, pod_name, status FROM instances WHERE status IN ('starting', 'running');"

# Find orphans
./scripts/find_orphaned_pods.py
```

### Manual Reconciliation Trigger

```bash
# Trigger immediate reconciliation (no need to wait for interval)
curl -X POST http://control-plane:8000/internal/reconcile \
  -H "Authorization: Bearer $SERVICE_ACCOUNT_TOKEN"
```

### Disabling Reconciliation

If reconciliation causes issues:

```bash
# Set environment variable
kubectl set env deployment/control-plane CONTROL_PLANE_RECONCILIATION_ENABLED=false -n production

# Or update Helm values
helm upgrade graph-olap ./helm/graph-olap \
  --set controlPlane.reconciliation.enabled=false
```

## Future Enhancements

### 1. Graceful Termination Notifications

Notify users before instance termination:

```python
async def notify_before_termination(instance: Instance, reason: str):
    """Send notification to instance owner before termination."""
    # Email notification
    await email_service.send(
        to=instance.owner_email,
        subject=f"Instance '{instance.name}' will be terminated",
        body=f"Your instance will be terminated in 15 minutes due to {reason}.",
    )

    # Slack notification (if configured)
    await slack_service.send(
        channel=instance.owner_slack_channel,
        message=f"⚠️ Instance `{instance.name}` will be terminated in 15 minutes ({reason})",
    )
```

### 2. Instance Hibernation

Instead of terminating, hibernate instances to save costs:

```python
async def hibernate_instance(instance_id: int):
    """Hibernate instance (delete pod but keep database record)."""
    # Export graph state to GCS
    # Delete pod
    # Mark instance as "hibernated"
    # Can be resumed later
```

### 3. Cost Tracking

Track and report instance costs:

```python
class InstanceCostService:
    """Track instance resource usage and costs."""

    async def calculate_cost(self, instance: Instance) -> float:
        """Calculate cost based on runtime and resource usage."""
        runtime_hours = (datetime.now(timezone.utc) - instance.created_at).total_seconds() / 3600
        memory_gb = instance.memory_usage_bytes / (1024 ** 3)
        cost_per_hour = self._calculate_hourly_cost(memory_gb)
        return runtime_hours * cost_per_hour
```

### 4. Auto-scaling Based on Usage

Scale down instances during low activity:

```python
async def auto_scale_instance(instance: Instance):
    """Scale instance resources based on usage."""
    if instance.last_activity_at and datetime.now(timezone.utc) - instance.last_activity_at > timedelta(hours=1):
        # Reduce memory allocation
        await k8s_service.scale_pod_memory(instance.pod_name, memory_gb=2)
```

## Summary

This design addresses the critical orphaned wrapper pod issue through:

1. **Immediate Fix**: Persist pod_name at creation time (control plane responsibility)
2. **Defense in Depth**: Wrapper always reports pod_name in callbacks
3. **Automated Reconciliation**: Background service detects and fixes state drift
4. **Lifecycle Enforcement**: Automated TTL and inactivity timeout cleanup
5. **Observability**: Comprehensive metrics, logs, and dashboards
6. **Safe Rollout**: Phased deployment with validation at each stage

**Impact**:
- **Before**: Orphaned pods run indefinitely, manual cleanup required
- **After**: Orphaned pods cleaned up within 5 minutes, zero manual intervention

**Cost Savings**:
- Eliminates wasted compute resources from orphaned pods
- Enforces TTL to prevent forgotten instances
- Automated cleanup reduces operational overhead

**Operational Excellence**:
- 100% pod-instance correlation
- Automated detection and remediation
- Clear observability and debugging tools
- Safe, gradual rollout plan
