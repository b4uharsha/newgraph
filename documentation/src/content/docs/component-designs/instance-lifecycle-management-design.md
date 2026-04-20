---
title: "Instance Lifecycle Management & Reconciliation Design"
scope: hsbc
---

<!-- Verified against code on 2026-04-20 -->

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
| Resource leaks | **CRITICAL** | Memory/CPU waste on the cluster |
| Operational visibility | **HIGH** | Cannot identify which pods belong to which instances |
| Instance cleanup failure | **CRITICAL** | DELETE /instances/:id cannot terminate pod (no pod_name) |
| Recovery impossible | **HIGH** | No way to detect or fix orphaned state |
| Resource consumption | **HIGH** | Orphaned pods consume node capacity indefinitely |

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

### 3. Reconciliation Job

**Module-level async function, scheduled by APScheduler**

Reconciliation is **not** implemented as a long-lived `ReconciliationService`
class with its own loop. Instead it is a plain async function in
`control_plane/jobs/reconciliation.py` that does a single pass when invoked,
and is registered with `BackgroundJobScheduler` (APScheduler) in
`control_plane/jobs/scheduler.py`. All Prometheus metrics live in
`control_plane/jobs/metrics.py` (not inline in the reconciliation function).

The job covers three concerns (orphaned pods, missing pods, status drift);
TTL expiry and inactivity timeouts are handled by the separate `lifecycle.py`
job and are not part of reconciliation.

```python
# control_plane/jobs/reconciliation.py
import time

import structlog

from control_plane.infrastructure.database import get_session
from control_plane.jobs import metrics
from control_plane.models import InstanceErrorCode, InstanceStatus
from control_plane.repositories.instances import InstanceRepository
from control_plane.services.k8s_service import get_k8s_service

logger = structlog.get_logger(__name__)


async def run_reconciliation_job(session=None) -> None:
    """One reconciliation pass — does NOT loop.

    Reconciles database instance state with Kubernetes pod state:
      1. Orphaned pods (pod exists but no database instance)
      2. Missing pods (database instance exists but pod missing)
      3. Status drift (database says "running" but pod is Failed)

    Scheduling / periodicity is the ``BackgroundJobScheduler``'s job — this
    function is invoked once per interval by APScheduler. Interval is
    controlled via ``GRAPH_OLAP_RECONCILIATION_JOB_INTERVAL_SECONDS``.

    Args:
        session: Optional database session (for testing). If None, a new
            session is opened via ``get_session()``.
    """
    logger.info("reconciliation_job_started")
    start_time = time.time()

    metrics.reconciliation_passes_total.inc()

    if session is not None:
        await _run_reconciliation_with_session(session, start_time)
    else:
        async with get_session() as session:
            await _run_reconciliation_with_session(session, start_time)


async def _run_reconciliation_with_session(session, start_time: float) -> None:
    """Single-pass logic bound to a provided session."""
    instance_repo = InstanceRepository(session)
    k8s_service = get_k8s_service()

    # Load all instances from the database and all wrapper pods from K8s.
    # list_wrapper_pods() filters by the ``wrapper-type`` label (any value),
    # which matches every wrapper (ryugraph, falkordb, ...) — no name-based
    # scanning for ``graph-instance-*``.
    db_instances = await instance_repo.list_all()
    k8s_pods = await k8s_service.list_wrapper_pods()

    db_by_pod_name = {inst.pod_name: inst for inst in db_instances if inst.pod_name}
    k8s_by_name = {pod.metadata.name: pod for pod in k8s_pods}

    # Phase 1: Orphaned pods (pod exists but no database instance points to it)
    orphaned_pods = [
        pod_name for pod_name in k8s_by_name if pod_name not in db_by_pod_name
    ]

    # Phase 2: Missing pods (DB instance is alive-ish but pod is gone)
    missing_pods = [
        inst for inst in db_instances
        if inst.pod_name
        and inst.pod_name not in k8s_by_name
        and inst.status in [InstanceStatus.STARTING, InstanceStatus.RUNNING, InstanceStatus.STOPPING]
    ]

    # Phase 3: Status drift (DB says Running but pod is Failed)
    status_drift = [
        (inst, k8s_by_name[inst.pod_name])
        for inst in db_instances
        if inst.pod_name
        and inst.pod_name in k8s_by_name
        and inst.status == InstanceStatus.RUNNING
        and k8s_by_name[inst.pod_name].status.phase == "Failed"
    ]

    metrics.orphaned_pods_detected_current.set(len(orphaned_pods))

    orphaned_cleaned = await _cleanup_orphaned_pods(k8s_service, orphaned_pods)
    missing_handled = await _handle_missing_pods(instance_repo, missing_pods)
    drift_fixed = await _fix_status_drift(instance_repo, status_drift)

    metrics.orphaned_pods_detected_current.set(0)
    metrics.orphaned_pods_detected_total.inc(len(orphaned_pods))
    metrics.missing_pods_detected_total.inc(len(missing_pods))
    metrics.status_drift_detected_total.inc(len(status_drift))
    metrics.reconciliation_pass_duration_seconds.observe(time.time() - start_time)

    logger.info(
        "reconciliation_job_completed",
        orphaned_pods_cleaned=orphaned_cleaned,
        missing_pods_handled=missing_handled,
        status_drift_fixed=drift_fixed,
    )


async def _cleanup_orphaned_pods(k8s_service, pod_names: list[str]) -> int:
    """Delete pods that have no database instance, by exact pod name."""
    deleted = 0
    for pod_name in pod_names:
        try:
            logger.warning("orphaned_pod_detected", pod_name=pod_name)
            # Note: delete by exact pod_name (reconciliation doesn't know url_slug)
            if await k8s_service.delete_wrapper_pod_by_name(pod_name, grace_period_seconds=30):
                logger.info("orphaned_pod_deleted", pod_name=pod_name)
                deleted += 1
                metrics.orphaned_pods_cleaned_total.inc()
        except Exception as e:
            logger.error("orphaned_pod_deletion_failed", pod_name=pod_name, error=str(e))
            metrics.orphaned_pods_cleanup_failures_total.inc()
    return deleted


async def _handle_missing_pods(instance_repo: InstanceRepository, instances: list) -> int:
    """Instance exists in DB, pod is gone.

    - STOPPING instances: pod termination completed → delete DB row.
    - STARTING/RUNNING: unexpected loss → capture diagnostics, mark FAILED.
    """
    handled = 0
    k8s_service = get_k8s_service()
    for instance in instances:
        try:
            logger.warning(
                "missing_pod_detected",
                instance_id=instance.id,
                pod_name=instance.pod_name,
                status=instance.status.value,
            )
            if instance.status == InstanceStatus.STOPPING:
                if await instance_repo.delete(instance.id):
                    handled += 1
            else:
                failure_info = await k8s_service.get_pod_failure_info(instance.pod_name)
                error_msg = f"Pod {instance.pod_name} disappeared: {failure_info}"[:4000]
                if await instance_repo.update_status(
                    instance_id=instance.id,
                    status=InstanceStatus.FAILED,
                    error_code=InstanceErrorCode.UNEXPECTED_TERMINATION,
                    error_message=error_msg,
                ):
                    handled += 1
            metrics.missing_pods_handled_total.inc()
        except Exception as e:
            logger.error("missing_pod_handling_failed", instance_id=instance.id, error=str(e))
    return handled


async def _fix_status_drift(instance_repo: InstanceRepository, drifts: list[tuple]) -> int:
    """DB says Running but pod is Failed — capture diagnostics, mark FAILED."""
    fixed = 0
    k8s_service = get_k8s_service()
    for instance, pod in drifts:
        try:
            failure_info = await k8s_service.get_pod_failure_info(instance.pod_name)
            error_msg = f"Pod entered {pod.status.phase} phase: {failure_info}"[:4000]
            if await instance_repo.update_status(
                instance_id=instance.id,
                status=InstanceStatus.FAILED,
                error_code=InstanceErrorCode.UNEXPECTED_TERMINATION,
                error_message=error_msg,
            ):
                fixed += 1
                metrics.status_drift_fixed_total.inc()
        except Exception as e:
            logger.error("status_drift_fix_failed", instance_id=instance.id, error=str(e))
    return fixed
```

### 4. K8s Service Enhancements

**Methods in `K8sService` that reconciliation relies on**

```python
# control-plane/src/control_plane/services/k8s_service.py
# (stateful service — namespace is configured at construction; sync kubernetes
# client, so methods are async wrappers over blocking calls)

class K8sService:
    """Kubernetes operations service."""

    async def list_wrapper_pods(self) -> list[Any]:
        """List all wrapper pods in the namespace.

        Uses the ``wrapper-type`` label (any value) to match every wrapper type
        (ryugraph, falkordb, ...) with a single selector.
        """
        self._ensure_initialized()
        if self._core_api is None:
            return []
        try:
            pod_list = self._core_api.list_namespaced_pod(
                namespace=self._namespace,
                label_selector="wrapper-type",  # key-exists selector, any value
            )
            return pod_list.items
        except ApiException as e:
            logger.error("k8s_list_pods_failed", namespace=self._namespace, error=str(e))
            return []

    async def get_pod_status_by_name(self, pod_name: str) -> dict[str, Any] | None:
        """Get detailed pod status by explicit pod name.

        Returns ``{"phase", "ready", "containers", "created_at"}`` or None if
        K8s is unavailable. Returns ``{"phase": "NotFound"}`` if pod is gone.
        """

    async def delete_wrapper_pod_by_name(
        self,
        pod_name: str,
        grace_period_seconds: int = 30,
    ) -> bool:
        """Delete a wrapper pod by **exact** pod name (reconciliation path).

        Used when we have the pod_name but not the url_slug (e.g. orphan
        cleanup). Does NOT delete the associated Service — callers that know
        the url_slug should use ``delete_wrapper_pod(url_slug)`` instead.
        """

    async def get_pod_failure_info(self, pod_name: str) -> str:
        """Human-readable diagnostic summary (exit codes, termination reasons,
        last 20 log lines) — used to populate ``error_message`` on FAILED
        instances before the pod object is garbage-collected."""
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

**Register all periodic jobs with `BackgroundJobScheduler` (APScheduler)**

The control plane does **not** spin up a bespoke reconciliation service — it
owns a single `BackgroundJobScheduler` (in `control_plane/jobs/scheduler.py`)
backed by APScheduler's `AsyncIOScheduler`. The scheduler registers the full
set of periodic jobs shipped under `control_plane/jobs/`:

| Job module | Purpose |
|------------|---------|
| `jobs/reconciliation.py` (`run_reconciliation_job`) | Pod / DB drift + orphan cleanup |
| `jobs/lifecycle.py` | TTL / inactivity termination |
| `jobs/export_reconciliation.py` | Export worker crash recovery |
| `jobs/schema_cache.py` | Starburst schema metadata refresh |
| `jobs/resource_monitor.py` | Dynamic memory monitoring + proactive resize |
| `jobs/instance_orchestration.py` | ``waiting_for_snapshot → starting`` transitions |

```python
# control_plane/main.py
from contextlib import asynccontextmanager
from control_plane.config import Settings
from control_plane.jobs.scheduler import BackgroundJobScheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    settings = Settings()
    logger.info("control_plane_starting")

    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)

    # Single scheduler owns all periodic jobs
    scheduler = BackgroundJobScheduler(settings)
    scheduler.set_schema_cache(app.state.schema_cache)   # wired by schema_cache init
    await scheduler.start()

    app.state.scheduler = scheduler

    yield

    # Shutdown
    await scheduler.stop()
    await engine.dispose()
```

Internally, ``BackgroundJobScheduler.start()`` calls ``_register_jobs()``
which adds one APScheduler ``IntervalTrigger`` per job above, honouring the
``GRAPH_OLAP_*_JOB_INTERVAL_SECONDS`` settings (see §7).

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
        env_prefix = "GRAPH_OLAP_"   # e.g. GRAPH_OLAP_RECONCILIATION_ENABLED
```

## Observability

### Metrics

```python
# control_plane/jobs/metrics.py  (single source of truth — NOT inline in jobs)

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
  "namespace": "graph-olap-platform"
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
    k8s_service = K8sService(namespace="graph-olap-platform")
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
    k8s_service = K8sService(namespace="graph-olap-platform")
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
kubectl get pods -n graph-olap-platform -l 'app in (ryugraph-wrapper, falkordb-wrapper)'

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
# Patch the control-plane Deployment to disable reconciliation
kubectl -n graph-olap-platform set env deployment/control-plane \
  GRAPH_OLAP_RECONCILIATION_ENABLED=false
```

For a permanent change, update the `control-plane` Deployment manifest (`env:` block) and re-apply with `kubectl apply -f`.

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
