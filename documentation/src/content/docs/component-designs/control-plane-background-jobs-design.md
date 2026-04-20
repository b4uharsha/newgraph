---
title: "Control Plane Background Jobs Design"
scope: hsbc
---

# Control Plane Background Jobs Design

## Overview

The background jobs subsystem provides automated lifecycle management, state reconciliation, and resource cleanup for the Graph OLAP Platform. Built on APScheduler, it runs six background jobs within the Control Plane process to detect and fix state drift between the database and Kubernetes, enforce TTL/inactivity policies, recover from worker crashes, and monitor pod resource usage (Resource Monitor). This system follows Google SRE reconciliation patterns with comprehensive Prometheus instrumentation for production observability.

## Prerequisites

Documents to read first:

- [foundation/requirements.md](--/foundation/requirements.md) - Lifecycle management requirements
- [foundation/architectural.guardrails.md](--/foundation/architectural.guardrails.md) - Architectural patterns and constraints
- [system-design/system.architecture.design.md](--/system-design/system.architecture.design.md) - System architecture overview
- [component-designs/control-plane.design.md](-/control-plane.design.md) - Control Plane core design
- [component-designs/instance-lifecycle-management.design.md](-/instance-lifecycle-management.design.md) - Pod tracking fix and reconciliation design
- [standards/python-logging-standards.md](--/standards/python-logging-standards.md) - Logging conventions

## Constraints

### Architectural Constraints

See [architectural.guardrails.md](--/foundation/architectural.guardrails.md#anti-patterns-must-not-do) for the authoritative list. Key sections relevant to background jobs:

- **Concurrency** - Single APScheduler instance per Control Plane pod (no distributed locking needed in single-replica mode)
- **State Management** - Database is source of truth; K8s state is reconciled to match
- **API Contracts** - All database updates follow existing repository patterns

### Component-Specific Constraints

1. **Job Execution Model**
   - Jobs run in the same process as the FastAPI application
   - Jobs MUST NOT block the event loop (use async/await)
   - Jobs MUST complete within their interval period (avoid overlapping executions)

2. **Resource Limits**
   - Jobs MUST paginate when querying large datasets
   - Memory usage MUST be bounded (no unbounded list accumulation)
   - K8s API calls MUST be rate-limited and retried

3. **Error Handling**
   - Job failures MUST be logged but MUST NOT crash the application
   - Partial failures MUST NOT prevent subsequent job executions
   - Metrics MUST track both successes and failures

4. **Observability**
   - All operations MUST emit structured logs via structlog
   - Critical operations MUST increment Prometheus counters
   - Job duration MUST be tracked via histograms

## Architecture

### System Context

```
┌─────────────────────────────────────────────────────────────┐
│ Control Plane (FastAPI Application)                        │
│                                                             │
│  ┌──────────────┐                                          │
│  │ FastAPI      │                                          │
│  │ REST API     │                                          │
│  └──────────────┘                                          │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Background Job Scheduler (APScheduler)               │  │
│  │                                                       │  │
│  │  ┌────────────────┐  ┌────────────────┐            │  │
│  │  │ Reconciliation │  │ Lifecycle      │            │  │
│  │  │ Job (5 min)    │  │ Job (5 min)    │            │  │
│  │  └────────────────┘  └────────────────┘            │  │
│  │                                                       │  │
│  │  ┌────────────────┐  ┌────────────────┐            │  │
│  │  │ Export Recon   │  │ Schema Cache   │            │  │
│  │  │ Job (5 sec)    │  │ Job (24 hrs)   │            │  │
│  │  └────────────────┘  └────────────────┘            │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────┐                                          │
│  │ Repositories │                                          │
│  │ (DB Access)  │                                          │
│  └──────────────┘                                          │
└─────────────────────────────────────────────────────────────┘
         │                          │
         │ Database                 │ Kubernetes API
         │ Queries                  │ (list/delete pods)
         ▼                          ▼
  ┌─────────────┐          ┌─────────────────┐
  │ PostgreSQL  │          │ K8s API Server  │
  │ (Source of  │          │ (Actual State)  │
  │  Truth)     │          │                 │
  └─────────────┘          └─────────────────┘
```

### Design Principles

1. **Reconciliation Loop Pattern** (Google SRE)
   - Compare desired state (database) with actual state (Kubernetes)
   - Detect drift
   - Fix drift
   - Record metrics

2. **Idempotency**
   - All operations are safe to retry
   - Jobs can be interrupted and restarted without data loss
   - No state is maintained between job executions

3. **Fail-Safe Defaults**
   - If uncertain, log and skip (don't delete)
   - Conservative timeouts prevent false positives
   - Metrics track skipped operations for investigation

4. **Observable by Default**
   - Every operation emits structured logs
   - Critical operations increment Prometheus counters
   - Duration histograms enable percentile analysis

### Job Scheduler

**Implementation:** APScheduler AsyncIOScheduler

**File:** `packages/control-plane/src/control_plane/jobs/scheduler.py`

**Lifecycle:**

1. **Startup** (main.py:56)
   - Instantiated before FastAPI lifespan context
   - Registers all jobs during `scheduler.start()`
   - APScheduler starts background thread
   - First job execution at `interval` seconds after startup

2. **Execution**
   - Jobs wrapped with error handling, logging, and metrics
   - Exceptions are caught and logged (don't crash app)
   - Metrics recorded: `background_job_execution_total{job_name, status}`
   - Duration tracked: `background_job_execution_duration_seconds{job_name}`

3. **Shutdown** (main.py:59)
   - `scheduler.stop()` called during FastAPI shutdown
   - APScheduler waits for running jobs to complete
   - Graceful shutdown guaranteed

**Configuration:**

```python
# APScheduler settings
job_defaults = {
    "coalesce": True,        # Combine missed executions (prevents backlog)
    "max_instances": 1,      # One execution at a time per job
    "misfire_grace_time": 60 # Allow 60s delay before considering misfire
}
```

**Job Registration:**

```python
# Reconciliation Job
scheduler.add_job(
    func=wrapped_run_reconciliation_job,
    trigger=IntervalTrigger(seconds=settings.reconciliation_job_interval_seconds),
    id="reconciliation",
    name="Reconciliation Job",
    replace_existing=True,
)
```

## Jobs

### 1. Reconciliation Job

**Purpose:** Detect and fix state drift between database instances and Kubernetes pods (**safety net / anomaly detector**)

**File:** `packages/control-plane/src/control_plane/jobs/reconciliation.py`

**Interval:** Every 5 minutes (configurable: `GRAPH_OLAP_RECONCILIATION_JOB_INTERVAL_SECONDS`)

**Role Change (ADR-043):**

This job's role has fundamentally changed from "primary cleanup mechanism" to "anomaly detector":

- **Before:** Expected to find and clean up orphaned pods every run (lazy cleanup pattern)
- **After:** Finding orphaned pods indicates a **BUG** in delete logic - should find zero orphans in normal operation
- **Monitoring:** Orphaned pod count metric should be zero; alerts trigger if count > 0

**Why the Change:**

DELETE operations now perform synchronous cleanup (see [ADR-43](--/--/process/adr/testing/adr-043-google-style-test-runner-cleanup-for-e2e-tests.md)):
- `InstanceService.delete()` removes K8s resources FIRST, database LAST
- Bulk delete calls `delete()` for each instance
- This ensures resources are GONE when DELETE returns 200, not "eventually gone"

**Current Role:** Safety net for edge cases:
- K8s API failures during delete
- Control-plane crashes mid-delete
- Manual K8s operations outside platform
- Bugs in delete logic (should be rare)

**Algorithm:**

```
1. Fetch all instances from database (instance_repo.list_all())
2. Fetch all wrapper pods from K8s (k8s_service.list_wrapper_pods())
3. Build lookup maps:
   - db_by_pod_name = {instance.pod_name: instance}
   - k8s_by_name = {pod.metadata.name: pod}

Phase 1: Detect Orphaned Pods (ANOMALY)
   for each pod_name in k8s_by_name:
       if pod_name NOT in db_by_pod_name:
           orphaned_pods.append(pod_name)
           # ← This should NOT happen in normal operation!

Phase 2: Detect Missing Pods
   for each instance in db_instances:
       if instance.pod_name AND instance.status IN (starting, running):
           if instance.pod_name NOT in k8s_by_name:
               missing_pods.append(instance)

Phase 3: Detect Status Drift
   for each instance in db_instances:
       if instance.pod_name AND instance.status == running:
           pod = k8s_by_name.get(instance.pod_name)
           if pod.status.phase in (Failed, Unknown):
               status_drift.append((instance, pod))

Phase 4: Execute Fixes (Safety Net)
   cleanup_orphaned_pods(orphaned_pods)     # ← Should be ZERO in normal ops
   handle_missing_pods(missing_pods)
   fix_status_drift(status_drift)

Phase 5: Record Metrics
   metrics.reconciliation_passes_total.inc()
   metrics.orphaned_pods_detected_total.inc(len(orphaned_pods))  # ← Should be ZERO
   metrics.reconciliation_pass_duration_seconds.observe(duration)
```

**Orphaned Pod Cleanup (Safety Net):**

```python
async def _cleanup_orphaned_pods(k8s_service, pod_names):
    """Delete pods that have no database instance.

    NOTE: In normal operation, this should find ZERO orphans.
    Finding orphans indicates a bug in InstanceService.delete() logic.
    """
    for pod_name in pod_names:
        # Log at ERROR level - this is anomalous
        logger.error(
            "orphaned_pod_detected",
            pod_name=pod_name,
            severity="BUG_INDICATOR",
            message="Delete logic should have removed this pod"
        )
        deleted = await k8s_service.delete_wrapper_pod_by_name(
            pod_name,
            grace_period_seconds=30
        )
        if deleted:
            metrics.orphaned_pods_cleaned_total.inc()
```

**Missing Pod Handling:**

```python
async def _handle_missing_pods(instance_repo, instances):
    """Mark instances as failed when pod disappears."""
    for instance in instances:
        logger.warning("missing_pod_detected", instance_id=instance.id)
        await instance_repo.update_status(
            instance_id=instance.id,
            status=InstanceStatus.FAILED,
            error_code=InstanceErrorCode.UNEXPECTED_TERMINATION,
            error_message=f"Pod {instance.pod_name} disappeared from Kubernetes"
        )
        metrics.missing_pods_handled_total.inc()
```

**Status Drift Fixing:**

```python
async def _fix_status_drift(instance_repo, drift_cases):
    """Update database to match K8s pod status."""
    for instance, pod in drift_cases:
        logger.warning("status_drift_detected",
                      instance_id=instance.id,
                      pod_phase=pod.status.phase)
        await instance_repo.update_status(
            instance_id=instance.id,
            status=InstanceStatus.FAILED,
            error_code=InstanceErrorCode.UNEXPECTED_TERMINATION,
            error_message=f"Pod entered {pod.status.phase} phase"
        )
        metrics.status_drift_fixed_total.inc()
```

**Metrics:**

- `reconciliation_passes_total` - Total reconciliation passes executed
- `reconciliation_pass_duration_seconds` - Duration histogram
- `orphaned_pods_detected_total` / `orphaned_pods_cleaned_total` - Orphan tracking
- `orphaned_pods_cleanup_failures_total` - Failed deletions
- `missing_pods_detected_total` / `missing_pods_handled_total` - Missing pod tracking
- `status_drift_detected_total` / `status_drift_fixed_total` - Drift tracking
- `orphaned_pods_detected_current` - Gauge showing current orphaned pods (before cleanup)

**Note:** Instance and snapshot status metrics (`instances_by_status_total`, `snapshots_by_status_total`) were REMOVED. System state queries belong in the REST API (`/api/ops/state`), not Prometheus metrics. Prometheus focuses on Four Golden Signals (Latency, Traffic, Errors, Saturation) for production observability.

**Error Handling:**

- K8s API failures: Logged, metrics incremented, continue with next pod
- Database failures: Logged, job execution fails but doesn't crash app
- Partial failures: Each pod/instance handled independently

---

### 2. Lifecycle Job

**Purpose:** Enforce TTL and inactivity timeout policies on instances, snapshots, and mappings

**File:** `packages/control-plane/src/control_plane/jobs/lifecycle.py`

**Interval:** Every 5 minutes (configurable: `GRAPH_OLAP_LIFECYCLE_JOB_INTERVAL_SECONDS`)

**Algorithm:**

```
Phase 1: TTL-Expired Instances
   instances = await instance_repo.find_expired(limit=100)
   for each instance:
       if _is_expired(instance.created_at, instance.ttl, now):
           await instance_service.delete_instance(instance.id, user=system_user)
           metrics.ttl_instances_terminated_total.inc()

Phase 2: Inactive Instances
   instances = await instance_repo.find_inactive(limit=100)
   for each instance:
       if _is_inactive(instance.last_activity_at, instance.inactivity_timeout, now):
           await instance_service.delete_instance(instance.id, user=system_user)
           metrics.inactive_instances_terminated_total.inc()

Phase 3: TTL-Expired Snapshots
   snapshots = await snapshot_repo.find_expired(limit=100)
   for each snapshot:
       if _is_expired(snapshot.created_at, snapshot.ttl, now):
           if snapshot.instance_count == 0:
               # Delete GCS files before deleting database record
               if snapshot.gcs_path:
                   gcs_client.delete_path(snapshot.gcs_path)
               await snapshot_repo.delete(snapshot.id)
               metrics.ttl_snapshots_deleted_total.inc()
               # Failures tracked by snapshot_gcs_cleanup_failures_total

Phase 4: TTL-Expired Mappings
   mappings = await mapping_repo.list_all()
   for each mapping:
       if _is_expired(mapping.created_at, mapping.ttl, now):
           if mapping.snapshot_count == 0:
               await mapping_repo.delete(mapping.id)
               metrics.ttl_mappings_deleted_total.inc()

Phase 5: Record Metrics
   metrics.lifecycle_passes_total.inc()
   metrics.lifecycle_pass_duration_seconds.observe(duration)
```

**ISO 8601 Duration Parsing:**

```python
def _parse_iso8601_duration(duration_str: str) -> timedelta | None:
    """Parse ISO 8601 duration string to timedelta.

    Supported formats:
    - PT<n>H - Hours (e.g., PT24H = 24 hours)
    - PT<n>M - Minutes (e.g., PT30M = 30 minutes)
    - P<n>D - Days (e.g., P7D = 7 days)
    - P<n>W - Weeks (e.g., P2W = 2 weeks)

    Examples:
    - "PT24H" -> 24 hours
    - "P7D" -> 7 days
    - "P30D" -> 30 days
    """
    if not duration_str or not duration_str.startswith("P"):
        return None

    # Hours: PT24H
    if duration_str.startswith("PT") and duration_str.endswith("H"):
        hours = int(duration_str[2:-1])
        return timedelta(hours=hours)

    # Minutes: PT30M
    if duration_str.startswith("PT") and duration_str.endswith("M"):
        minutes = int(duration_str[2:-1])
        return timedelta(minutes=minutes)

    # Days: P7D
    if duration_str.endswith("D"):
        days = int(duration_str[1:-1])
        return timedelta(days=days)

    # Weeks: P2W
    if duration_str.endswith("W"):
        weeks = int(duration_str[1:-1])
        return timedelta(weeks=weeks)

    return None
```

**Expiry Calculation:**

```python
def _is_expired(created_at: datetime, ttl: str | None, now: datetime) -> bool:
    """Check if resource has exceeded its TTL."""
    if not ttl:
        return False

    duration = _parse_iso8601_duration(ttl)
    if not duration:
        return False

    expiry_time = created_at + duration
    return now >= expiry_time
```

**Metrics:**

- `lifecycle_passes_total` - Total lifecycle enforcement passes
- `lifecycle_pass_duration_seconds` - Duration histogram
- `ttl_instances_terminated_total` - Instances terminated due to TTL
- `ttl_snapshots_deleted_total` - Snapshots deleted due to TTL
- `ttl_mappings_deleted_total` - Mappings deleted due to TTL
- `inactive_instances_terminated_total` - Instances terminated due to inactivity
- `lifecycle_termination_failures_total{resource_type}` - Failed terminations
- `snapshot_gcs_cleanup_failures_total` - Failed GCS file deletions (logs error, continues with DB deletion)

**Error Handling:**

- Termination failures: Logged, metrics incremented, continue with next resource
- Invalid TTL strings: Logged, resource skipped
- Database conflicts: Logged, retry on next pass

---

### 3. Export Reconciliation Job

**Purpose:** Recover from export worker crashes and finalize completed snapshots

**File:** `packages/control-plane/src/control_plane/jobs/export_reconciliation.py`

**Interval:** Every 5 seconds (deliberate exception to ADR-040: near-real-time export propagation requirement; APScheduler background job polls `export_jobs` table and calls Starburst Galaxy directly)

**Algorithm:**

```
Phase 1: Reset Stale Claims
   stale_threshold = now - timedelta(minutes=10)
   stale_jobs = await export_job_repo.list_all()

   for each job in stale_jobs:
       if job.status == claimed AND job.claimed_at < stale_threshold:
           await export_job_repo.reset_to_pending(job.id)
           metrics.stale_export_claims_reset_total.inc()

Phase 2: Finalize Snapshots
   snapshots = await snapshot_repo.list_all()

   for each snapshot in snapshots:
       if snapshot.status == creating:
           jobs = await export_job_repo.list_by_snapshot(snapshot.id)

           if all_jobs_completed(jobs):
               await snapshot_repo.update_status(
                   snapshot.id,
                   SnapshotStatus.READY
               )
               metrics.snapshots_finalized_total.inc()

Phase 3: Record Metrics
   metrics.export_reconciliation_passes_total.inc()
   metrics.export_reconciliation_pass_duration_seconds.observe(duration)
```

**Stale Claim Detection:**

```python
async def _find_stale_claimed_jobs(repo, now):
    """Find export jobs with stale claims.

    A claim is stale if:
    - status = 'claimed'
    - claimed_at > 10 minutes ago

    This indicates the worker crashed after claiming but before submission.
    """
    stale_threshold = now - timedelta(minutes=10)
    all_jobs = await repo.list_all()

    stale = []
    for job in all_jobs:
        if job.status == ExportJobStatus.CLAIMED:
            if job.claimed_at and job.claimed_at < stale_threshold:
                stale.append(job)

    return stale
```

**Snapshot Finalization:**

```python
async def _find_snapshots_ready_to_finalize(snapshot_repo, export_job_repo):
    """Find snapshots where all export jobs are completed."""
    ready = []

    snapshots = await snapshot_repo.list_all()
    for snapshot in snapshots:
        if snapshot.status != SnapshotStatus.CREATING:
            continue

        jobs = await export_job_repo.list_by_snapshot(snapshot.id)
        if not jobs:
            continue

        # Check if all jobs completed (none pending/claimed/submitted)
        all_completed = all(
            job.status in (ExportJobStatus.COMPLETED, ExportJobStatus.FAILED)
            for job in jobs
        )

        if all_completed:
            ready.append(snapshot)

    return ready
```

**Metrics:**

- `export_reconciliation_passes_total` - Total export reconciliation passes
- `export_reconciliation_pass_duration_seconds` - Duration histogram
- `stale_export_claims_detected_total` - Stale claims detected
- `stale_export_claims_reset_total` - Stale claims successfully reset
- `snapshots_ready_to_finalize_total` - Snapshots detected ready to finalize
- `snapshots_finalized_total` - Snapshots successfully finalized
- `snapshots_finalization_failures_total` - Failed finalizations

**Error Handling:**

- Database conflicts: Logged, retry on next pass
- Partial completion: Snapshots with mixed success/failure jobs remain in creating state
- Worker restarts: Resetting claims allows workers to retry

---

### 4. Schema Cache Job

**Purpose:** Refresh Starburst schema metadata cache for fast UI browsing

**File:** `packages/control-plane/src/control_plane/jobs/schema_cache.py`

**Interval:** Every 24 hours (configurable: `GRAPH_OLAP_SCHEMA_CACHE_JOB_INTERVAL_SECONDS`)

**Status:** Placeholder implementation (awaiting Starburst client)

**Algorithm (Planned):**

```
Phase 1: Fetch Metadata from Starburst
   catalogs = await starburst_client.execute("SELECT * FROM system.metadata.catalogs")
   schemas = await starburst_client.execute("SELECT * FROM system.metadata.schemas")
   tables = await starburst_client.execute("SELECT * FROM system.metadata.tables")
   columns = await starburst_client.execute("SELECT * FROM system.metadata.columns")

Phase 2: Update Cache
   for each catalog in catalogs:
       await schema_cache_repo.upsert_catalog(catalog, now)

   for each schema in schemas:
       await schema_cache_repo.upsert_schema(schema, now)

   for each table in tables:
       await schema_cache_repo.upsert_table(table, now)

   for each column in columns:
       await schema_cache_repo.upsert_column(column, now)

Phase 3: Expire Stale Entries
   cache_ttl_hours = await config_repo.get_int("cache.metadata.ttl_hours", 24)
   deleted_count = await schema_cache_repo.delete_stale_entries(cache_ttl_hours)

Phase 4: Record Metrics
   metrics.schema_cache_refreshes_total.labels(status="success").inc()
   metrics.schema_cache_entries_total.labels(entity_type="catalog").set(len(catalogs))
```

**Current Implementation:**

```python
async def run_schema_cache_job() -> None:
    """Refresh schema metadata cache from Starburst.

    PLACEHOLDER: Awaiting Starburst client implementation.
    """
    logger.warning(
        "schema_cache_refresh_skipped",
        reason="starburst_client_not_implemented",
        note="awaiting starburst client integration"
    )

    metrics.schema_cache_refreshes_total.labels(status="skipped").inc()
```

**Metrics:**

- `schema_cache_refreshes_total{status}` - Total refreshes (success, failed, skipped)
- `schema_cache_refresh_duration_seconds` - Duration histogram
- `schema_cache_entries_total{entity_type}` - Gauge for catalog/schema/table/column counts
- `schema_cache_stale_entries_deleted_total` - Expired entries deleted

**Implementation Notes:**

When Starburst client is implemented:

1. Create `schema_metadata_cache` table in database
2. Implement `SchemaCacheRepository` with upsert methods
3. Add Starburst client to job dependencies
4. Update job to query metadata and populate cache
5. Enable in production

---

### 5. Instance Orchestration Job

**Purpose:** Monitors instances in `waiting_for_snapshot` status and transitions them when their snapshots complete.

**File:** `packages/control-plane/src/control_plane/jobs/instance_orchestration.py`

**Interval:** Every 30 seconds (hardcoded in scheduler; not currently configurable via environment variable)

**Context:** Supports the "Create Instance from Mapping" API flow (see [ADR-093](--/process/adr/api-design/adr-093-instance-creation-from-mapping-api.md)) where instances are created before their snapshots are ready. These instances remain in `waiting_for_snapshot` status until the background job detects snapshot completion.

**Trigger Conditions:**

An instance transitions when:
- Instance has `status = waiting_for_snapshot`
- Instance has a valid `pending_snapshot_id` set
- The referenced snapshot has reached a terminal state (`ready`, `failed`, or `cancelled`)

**Algorithm:**

```
Phase 1: Find Waiting Instances
   instances = await instance_repo.get_waiting_for_snapshot()

Phase 2: Check Snapshot Status
   for each instance in instances:
       # Validate pending_snapshot_id exists
       if not instance.pending_snapshot_id:
           logger.warning("instance_missing_pending_snapshot_id")
           continue

       snapshot = await snapshot_repo.get_by_id(instance.pending_snapshot_id)

       # Handle deleted snapshot
       if snapshot is None:
           await instance_repo.update_status(
               instance_id=instance.id,
               status=InstanceStatus.FAILED,
               error_code=InstanceErrorCode.DATA_LOAD_ERROR,
               error_message="Pending snapshot was deleted before it could complete"
           )
           continue

       if snapshot.status == "ready":
           # Transition to starting, create K8s pod
           await instance_repo.transition_to_starting(instance.id)
           await k8s_service.create_wrapper_pod(...)
           metrics.instances_transitioned_to_starting_total.inc()

       elif snapshot.status == "failed":
           # Mark instance as failed with snapshot error
           await instance_repo.update_status(
               instance_id=instance.id,
               status=InstanceStatus.FAILED,
               error_code=InstanceErrorCode.DATA_LOAD_ERROR,
               error_message=f"Snapshot failed: {snapshot.error_message}"
           )
           metrics.instances_transitioned_to_failed_total.inc()

       elif snapshot.status == "cancelled":
           # Mark instance as failed (snapshot was cancelled)
           await instance_repo.update_status(
               instance_id=instance.id,
               status=InstanceStatus.FAILED,
               error_code=InstanceErrorCode.DATA_LOAD_ERROR,
               error_message="Snapshot creation was cancelled"
           )
           metrics.instances_transitioned_to_failed_total.inc()

       else:
           # Snapshot still pending/creating - skip
           continue

Phase 3: Record Metrics
   metrics.instance_orchestration_passes_total.inc()
   metrics.instance_orchestration_pass_duration_seconds.observe(duration)
```

**Instance Transition to Starting:**

```python
async def _transition_to_starting(instance_repo, k8s_service, instance, snapshot):
    """Transition instance from waiting_for_snapshot to starting.

    Updates database status, then creates K8s wrapper pod.
    """
    logger.info(
        "transitioning_instance_to_starting",
        instance_id=instance.id,
        snapshot_id=snapshot.id,
    )

    # Transition instance status in database
    updated_instance = await instance_repo.transition_to_starting(instance.id)

    if updated_instance and k8s_service and updated_instance.url_slug:
        try:
            # Create K8s pod (same pattern as instance_service.create_instance)
            pod_name, external_url = await k8s_service.create_wrapper_pod(
                instance_id=updated_instance.id,
                url_slug=updated_instance.url_slug,
                wrapper_type=updated_instance.wrapper_type,
                snapshot_id=snapshot.id,
                mapping_id=snapshot.mapping_id,
                mapping_version=snapshot.mapping_version,
                owner_username=updated_instance.owner_username,
                owner_email=updated_instance.owner_username,
                gcs_path=snapshot.gcs_path,
            )

            if pod_name:
                # Update instance with pod_name and instance_url
                await instance_repo.update_status(
                    instance_id=updated_instance.id,
                    status=InstanceStatus.STARTING,
                    pod_name=pod_name,
                    instance_url=external_url,
                )
        except Exception as e:
            # Log error but don't fail - reconciliation job will retry
            logger.exception("wrapper_pod_creation_failed", error=str(e))
```

**Error Handling:**

- **Missing `pending_snapshot_id`:** Logged as warning, instance skipped (should not happen in normal operation)
- **Deleted snapshot:** Instance marked as failed with `DATA_LOAD_ERROR`
- **K8s pod creation failure:** Logged but not fatal; reconciliation job will detect missing pod
- **Individual instance errors:** Don't stop processing of other instances
- **Database errors:** Logged with full context, retry on next pass

**Metrics:**

- `instance_orchestration_passes_total` - Counter for job executions
- `instance_orchestration_pass_duration_seconds` - Histogram for duration
- `instances_transitioned_to_starting_total` - Successful transitions from `waiting_for_snapshot` to `starting`
- `instances_transitioned_to_failed_total` - Transitions to `failed` (snapshot failed, cancelled, deleted, or pod creation failed)

**References:**

- [ADR-093: Instance Creation from Mapping API](--/process/adr/api-design/adr-093-instance-creation-from-mapping-api.md) - Defines the API and workflow
- [ADR-037: APScheduler for Background Jobs](--/process/adr/system-design/adr-037-apscheduler-for-background-jobs.md) - Background job framework

---

## Metrics & Observability

### Prometheus Metrics

**Endpoint:** `GET /metrics`

**File:** `packages/control-plane/src/control_plane/jobs/metrics.py`

**Metrics Registry:**

```python
from prometheus_client import Counter, Gauge, Histogram

# General Job Metrics
job_execution_total = Counter(
    "background_job_execution_total",
    "Total background job executions",
    ["job_name", "status"]  # status: success, failed
)

job_execution_duration_seconds = Histogram(
    "background_job_execution_duration_seconds",
    "Duration of background job execution",
    ["job_name"],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0]
)

# Reconciliation Metrics
reconciliation_passes_total = Counter(...)
orphaned_pods_detected_total = Counter(...)
orphaned_pods_cleaned_total = Counter(...)
missing_pods_detected_total = Counter(...)
status_drift_detected_total = Counter(...)
instances_without_pod_name = Gauge(...)

# Lifecycle Metrics
lifecycle_passes_total = Counter(...)
ttl_instances_terminated_total = Counter(...)
inactive_instances_terminated_total = Counter(...)

# Export Reconciliation Metrics
stale_export_claims_detected_total = Counter(...)
snapshots_finalized_total = Counter(...)

# Schema Cache Metrics
schema_cache_refreshes_total = Counter(...)
schema_cache_entries_total = Gauge(...)
```

**P0 Testing Support Metrics** (added in 2025-12 for E2E test optimization):

These gauge metrics enable E2E tests to poll for job completion instead of using timing-based waits, reducing test time by 93% (22 min → 1.5 min):

```python
# Job Health Tracking
job_last_success_timestamp_seconds = Gauge(
    "background_job_last_success_timestamp_seconds",
    "Unix timestamp of last successful job execution",
    ["job_name"],
)

job_health_status = Gauge(
    "background_job_health_status",
    "Job health status: 1=healthy, 0=unhealthy (3+ consecutive failures)",
    ["job_name"],
)

# Saturation Metrics (Fourth Golden Signal)
# NOTE: Updated by reconciliation job to monitor database connection pool health
database_connections = Gauge(
    "graph_olap_database_connections",
    "Database connection pool state",
    ["state"],  # available, in_use, total
)

# Export Pipeline Health
# NOTE: Updated by export_reconciliation job to monitor export queue backlog
export_queue_depth = Gauge(
    "graph_olap_export_queue_depth",
    "Number of pending exports in queue",
)

orphaned_pods_detected_current = Gauge(
    "orphaned_pods_detected_current",
    "Current number of orphaned pods detected (before cleanup)",
)

export_jobs_by_status_total = Gauge(
    "export_jobs_by_status_total",
    "Current number of export jobs by status",
    ["status"],
)
```

**Usage in E2E Tests:**

```python
# Bad: Timing-based wait (slow, flaky)
time.sleep(300)  # Wait 5 minutes for reconciliation job

# Good: Metrics-based wait (fast, reliable)
def wait_for_job_execution(job_name: str, timeout: int = 600):
    """Poll metrics until job executes."""
    start_time = time.time()
    initial_timestamp = get_metric(f'background_job_last_success_timestamp_seconds{{job_name="{job_name}"}}')

    while time.time() - start_time < timeout:
        current_timestamp = get_metric(f'background_job_last_success_timestamp_seconds{{job_name="{job_name}"}}')
        if current_timestamp > initial_timestamp:
            return  # Job executed!
        time.sleep(5)

    raise TimeoutError(f"Job {job_name} did not execute within {timeout}s")

# Example usage
wait_for_job_execution("reconciliation", timeout=120)  # Max 2 minutes (job runs every 5 min)
assert get_metric('orphaned_pods_detected_current') == 0  # Verify reconciliation cleaned up orphans
assert get_metric('graph_olap_database_connections{state="available"}') > 0  # Verify DB pool healthy
```

### Structured Logging

**Format:** JSON (structured logging to stdout, collected by the cluster logging stack)

**Context:** All logs include job name, timestamp, and request ID (if available)

**Example Log Entries:**

```json
{
  "event": "reconciliation_job_started",
  "timestamp": "2025-12-21T10:15:00Z",
  "logger": "control_plane.jobs.reconciliation",
  "level": "info"
}

{
  "event": "orphaned_pod_detected",
  "pod_name": "ryugraph-wrapper-abc123",
  "timestamp": "2025-12-21T10:15:02Z",
  "logger": "control_plane.jobs.reconciliation",
  "level": "warning"
}

{
  "event": "orphaned_pod_deleted",
  "pod_name": "ryugraph-wrapper-abc123",
  "timestamp": "2025-12-21T10:15:03Z",
  "logger": "control_plane.jobs.reconciliation",
  "level": "info"
}

{
  "event": "reconciliation_job_completed",
  "orphaned_pods_cleaned": 1,
  "missing_pods_handled": 0,
  "status_drift_fixed": 0,
  "duration_seconds": 3.24,
  "timestamp": "2025-12-21T10:15:03Z",
  "logger": "control_plane.jobs.reconciliation",
  "level": "info"
}
```

### Grafana Dashboards (Recommended)

**Dashboard: Background Jobs Overview**

Panels:
- Job execution rate (executions/min)
- Job success rate (% successful)
- Job duration (p50, p95, p99)
- Error rate by job

**Dashboard: Reconciliation**

Panels:
- Orphaned pods detected/cleaned over time
- Missing pods detected/handled over time
- Status drift detected/fixed over time
- Instances without pod_name gauge
- Cleanup failure rate

**Dashboard: Lifecycle**

Panels:
- TTL terminations by resource type
- Inactivity terminations over time
- Lifecycle enforcement lag (time between expiry and termination)

**Dashboard: Export Reconciliation**

Panels:
- Stale claims detected/reset over time
- Snapshots finalized over time
- Snapshot finalization lag (time from job completion to finalization)

---

## Configuration

### Environment Variables

All intervals are configurable via environment variables:

```bash
# Reconciliation Job (default: 300 seconds = 5 minutes)
GRAPH_OLAP_RECONCILIATION_JOB_INTERVAL_SECONDS=300

# Lifecycle Job (default: 300 seconds = 5 minutes)
GRAPH_OLAP_LIFECYCLE_JOB_INTERVAL_SECONDS=300

# Export Reconciliation Job (default: 5 seconds — deliberate exception to ADR-040 for near-real-time export propagation)
GRAPH_OLAP_EXPORT_RECONCILIATION_JOB_INTERVAL_SECONDS=5

# Schema Cache Job (default: 86400 seconds = 24 hours)
GRAPH_OLAP_SCHEMA_CACHE_JOB_INTERVAL_SECONDS=86400
```

### Settings Class

**File:** `packages/control-plane/src/control_plane/config.py`

```python
class Settings(BaseSettings):
    # Background Jobs
    lifecycle_job_interval_seconds: int = 300
    reconciliation_job_interval_seconds: int = 300
    export_reconciliation_job_interval_seconds: int = 5  # Near-real-time; deliberate exception to ADR-040
    schema_cache_job_interval_seconds: int = 86400
```

### Kubernetes ConfigMap

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: control-plane-config
data:
  GRAPH_OLAP_RECONCILIATION_JOB_INTERVAL_SECONDS: "300"
  GRAPH_OLAP_LIFECYCLE_JOB_INTERVAL_SECONDS: "300"
  GRAPH_OLAP_EXPORT_RECONCILIATION_JOB_INTERVAL_SECONDS: "5"
  GRAPH_OLAP_SCHEMA_CACHE_JOB_INTERVAL_SECONDS: "86400"
```

### Production Tuning

**Conservative Intervals (High-Volume):**
- Reconciliation: 600 seconds (10 minutes)
- Lifecycle: 600 seconds (10 minutes)

**Aggressive Intervals (Low-Volume):**
- Reconciliation: 60 seconds (1 minute)
- Lifecycle: 300 seconds (5 minutes)

**Recommendations:**
- Start conservative (10 minutes)
- Monitor metrics for orphan detection lag
- Gradually reduce intervals if acceptable
- Never go below 60 seconds (avoid API rate limits)

---

## Manual Job Triggering

### Ops Endpoints

Background jobs can be manually triggered via ops endpoints for debugging, smoke tests, and incident response.

**Endpoint:** `POST /api/ops/jobs/trigger`

**Authorization:** Requires `ops` or `admin` role

**Rate Limiting:** 1 request per minute per job (prevents accidental job spam)

**Implementation:** `packages/control-plane/src/control_plane/routers/api/ops.py`

**Request:**

```json
{
  "job_name": "reconciliation",
  "reason": "post-deployment smoke test"
}
```

**Response:**

```json
{
  "data": {
    "job_name": "reconciliation",
    "status": "queued",
    "triggered_at": "2025-12-21T10:30:00Z",
    "triggered_by": "ops.user",
    "reason": "post-deployment smoke test"
  }
}
```

### Use Cases

1. **Post-Deployment Smoke Tests** - Trigger jobs immediately after deployment to verify scheduler is working
2. **Debugging** - Trigger jobs on-demand to observe behavior in logs/metrics
3. **Incident Response** - Force cleanup of orphaned pods or stale claims without waiting for next scheduled run
4. **E2E Testing** - Trigger jobs in test environments to verify behavior

### Security Considerations

- **Role-based access** - Only ops/admin can trigger jobs
- **Rate limiting** - Prevents accidental job spam (1 per minute per job)
- **Audit logging** - All manual triggers logged with user, reason, timestamp
- **Validation** - Only valid job names accepted (reconciliation, lifecycle, export_reconciliation, schema_cache)

### Implementation Notes

**Rate Limiting Strategy:**

```python
# In-memory rate limiting per job
_last_trigger_times: dict[str, datetime] = {}

def can_trigger_job(job_name: str) -> tuple[bool, int]:
    """Check if job can be triggered (1 per minute per job).

    Returns:
        (can_trigger, retry_after_seconds)
    """
    if job_name not in _last_trigger_times:
        return (True, 0)

    last_trigger = _last_trigger_times[job_name]
    elapsed = (datetime.now(timezone.utc) - last_trigger).total_seconds()

    if elapsed < 60:
        return (False, int(60 - elapsed))

    return (True, 0)

def trigger_job(job_name: str, triggered_by: str, reason: str):
    """Manually trigger background job."""
    # Check rate limit
    can_trigger, retry_after = can_trigger_job(job_name)
    if not can_trigger:
        raise RateLimitError(f"Wait {retry_after}s before triggering again")

    # Trigger job via APScheduler
    scheduler = app.state.scheduler
    scheduler.add_job(
        func=get_job_function(job_name),
        trigger="date",  # Run once immediately
        run_date=datetime.now(timezone.utc),
        id=f"{job_name}_manual_{uuid.uuid4()}",
    )

    # Update rate limit tracking
    _last_trigger_times[job_name] = datetime.now(timezone.utc)

    # Audit log
    logger.info(
        "manual_job_trigger",
        job_name=job_name,
        triggered_by=triggered_by,
        reason=reason,
    )
```

**Important:** Manual triggers do NOT interfere with scheduled executions. Both can run independently.

---

## Error Handling

### Job Execution Failures

**Behavior:** Jobs are wrapped with try/catch that logs exceptions and records metrics

**Impact:** Individual job failures DO NOT crash the application

**Recovery:** Jobs retry on next scheduled execution

**Example:**

```python
async def wrapped():
    logger.info("job_started", job=job_name)
    start_time = time.time()
    status = "success"

    try:
        await job_func()
        logger.info("job_completed", job=job_name)
    except Exception as e:
        status = "failed"
        logger.exception("job_failed", job=job_name, error=str(e))
    finally:
        duration = time.time() - start_time
        metrics.job_execution_total.labels(job_name=job_name, status=status).inc()
        metrics.job_execution_duration_seconds.labels(job_name=job_name).observe(duration)
```

### Kubernetes API Failures

**Failure Mode:** K8s API unavailable or rate-limited

**Behavior:**
- Log error with context
- Increment failure metric
- Skip current operation
- Continue with next pod/instance
- Retry on next job execution

**Example:**

```python
try:
    deleted = await k8s_service.delete_wrapper_pod_by_name(pod_name)
    if deleted:
        metrics.orphaned_pods_cleaned_total.inc()
except Exception as e:
    logger.error("orphaned_pod_deletion_failed", pod_name=pod_name, error=str(e))
    metrics.orphaned_pods_cleanup_failures_total.inc()
```

### Database Failures

**Failure Mode:** Database connection lost or query timeout

**Behavior:**
- Log error with full stack trace
- Job execution fails (status="failed" metric)
- APScheduler reschedules job for next interval
- No data corruption (all operations are transactional)

### Partial Failures

**Scenario:** 10 orphaned pods detected, 8 deleted successfully, 2 failed

**Behavior:**
- Metrics show: `orphaned_pods_detected_total = 10`, `orphaned_pods_cleaned_total = 8`, `orphaned_pods_cleanup_failures_total = 2`
- Logs contain detailed error for each failure
- Job continues processing remaining pods
- Job completes with status="success" (partial success is success)

### APScheduler Failures

**Failure Mode:** APScheduler internal error (rare)

**Behavior:**
- Logged at CRITICAL level
- Application continues running (REST API unaffected)
- Scheduler may need manual restart via pod restart
- Kubernetes liveness probe ensures pod restart if needed

---

## Operational Runbook

### Monitoring Checklist

**Daily:**
- [ ] Check `/metrics` endpoint is accessible
- [ ] Verify job execution rate (should match configured intervals)
- [ ] Review error rate (should be <1%)

**Weekly:**
- [ ] Review Grafana dashboards for trends
- [ ] Check for increasing orphan pod detections (indicates pod tracking bug)
- [ ] Verify lifecycle enforcement is working (TTL terminations happening)

**Monthly:**
- [ ] Review job duration trends (detect performance degradation)
- [ ] Audit configuration (intervals still appropriate?)

### Troubleshooting

#### Problem: Jobs Not Running

**Symptoms:**
- No logs from background jobs
- `/metrics` shows `background_job_execution_total` not incrementing

**Investigation:**
```bash
# Check scheduler started
kubectl logs -n graph-olap-platform deployment/control-plane | grep scheduler_starting

# Check for errors during registration
kubectl logs -n graph-olap-platform deployment/control-plane | grep job_registered
```

**Resolution:**
1. Check Control Plane logs for startup errors
2. Verify APScheduler dependency installed
3. Restart Control Plane pod

#### Problem: High Orphan Pod Rate

**Symptoms:**
- `orphaned_pods_detected_total` increasing rapidly
- Many wrapper pods without database instances

**Investigation:**
```bash
# Check pod_name tracking in database
psql -c "SELECT COUNT(*) FROM instances WHERE pod_name IS NULL AND status IN ('starting', 'running');"

# Check wrapper startup logs
kubectl logs -n graph-olap-platform -l app=ryugraph-wrapper | grep pod_name
```

**Resolution:**
1. Verify pod_name tracking fix is deployed (instance_service.py:217-232)
2. Check wrapper is calling instance callbacks correctly
3. Review Control Plane logs for instance creation failures

#### Problem: Lifecycle Job Not Terminating Instances

**Symptoms:**
- Instances exceed TTL but remain running
- `ttl_instances_terminated_total` not incrementing

**Investigation:**
```bash
# Check for expired instances
psql -c "SELECT id, created_at, ttl FROM instances WHERE ttl IS NOT NULL;"

# Check lifecycle job logs
kubectl logs -n graph-olap-platform deployment/control-plane | grep lifecycle_job
```

**Resolution:**
1. Verify TTL strings are valid ISO 8601 (e.g., "PT24H", "P7D")
2. Check job is running (logs show lifecycle_job_started)
3. Review lifecycle termination failures metric

#### Problem: Export Reconciliation Not Finalizing Snapshots

**Symptoms:**
- Snapshots stuck in "creating" status
- All export jobs completed but snapshot not finalized

**Investigation:**
```bash
# Check snapshot and job status
psql -c "SELECT s.id, s.status, COUNT(e.id) as job_count
         FROM snapshots s
         LEFT JOIN export_jobs e ON s.id = e.snapshot_id
         WHERE s.status = 'creating'
         GROUP BY s.id;"

# Check export reconciliation logs
kubectl logs -n graph-olap-platform deployment/control-plane | grep export_reconciliation_job
```

**Resolution:**
1. Verify all export jobs have status "completed" or "failed"
2. Check export reconciliation job is running
3. Review snapshot finalization failures metric

#### Problem: High Job Duration

**Symptoms:**
- Job duration p95 > 30 seconds
- Jobs overlapping (misfire warnings in logs)

**Investigation:**
```bash
# Check job duration metrics
curl http://control-plane/metrics | grep background_job_execution_duration_seconds

# Check for database slow queries
psql -c "SELECT query, mean_exec_time FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 10;"
```

**Resolution:**
1. Increase job interval to prevent overlaps
2. Add pagination to repository queries (limit=100)
3. Optimize database queries (add indexes)
4. Consider splitting job into smaller sub-jobs

### Alerts (Prometheus AlertManager)

**Recommended Alerts:**

```yaml
groups:
  - name: background_jobs
    rules:
      - alert: BackgroundJobNotRunning
        expr: rate(background_job_execution_total[10m]) == 0
        for: 15m
        annotations:
          summary: "Background job {{ $labels.job_name }} has not run in 15 minutes"

      - alert: BackgroundJobHighFailureRate
        expr: rate(background_job_execution_total{status="failed"}[5m]) > 0.1
        for: 10m
        annotations:
          summary: "Background job {{ $labels.job_name }} has >10% failure rate"

      - alert: HighOrphanedPodRate
        expr: rate(orphaned_pods_detected_total[1h]) > 5
        for: 30m
        annotations:
          summary: "High orphaned pod detection rate (>5/hour)"

      - alert: InstancesWithoutPodName
        expr: instances_without_pod_name > 10
        for: 15m
        annotations:
          summary: "{{ $value }} instances without pod_name tracking"
```

---

## Testing Strategy

### Unit Tests

**Location:** `packages/control-plane/tests/unit/jobs/`

**Coverage:**

```python
# test_reconciliation.py
def test_detect_orphaned_pods():
    """Test orphaned pod detection logic."""

def test_detect_missing_pods():
    """Test missing pod detection logic."""

def test_cleanup_orphaned_pods():
    """Test pod deletion logic."""

# test_lifecycle.py
def test_parse_iso8601_duration():
    """Test ISO 8601 duration parsing."""
    assert _parse_iso8601_duration("PT24H") == timedelta(hours=24)
    assert _parse_iso8601_duration("P7D") == timedelta(days=7)

def test_is_expired():
    """Test expiry calculation."""
    created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    ttl = "PT24H"
    now = datetime(2025, 1, 2, tzinfo=timezone.utc)
    assert _is_expired(created_at, ttl, now) == True

# test_scheduler.py
def test_scheduler_lifecycle():
    """Test scheduler startup and shutdown."""

def test_job_wrapper_metrics():
    """Test job wrapper records metrics on success and failure."""
```

### Integration Tests

**Location:** `packages/control-plane/tests/integration/jobs/`

**Coverage:**

```python
# test_reconciliation_integration.py
@pytest.mark.asyncio
async def test_reconciliation_with_database(db_session, k8s_service):
    """Test reconciliation job with real database and mocked K8s."""
    # Create instance in database
    # Create pod in K8s (mocked)
    # Delete instance from database
    # Run reconciliation job
    # Verify pod was deleted
    # Verify metrics were recorded

# test_lifecycle_integration.py
@pytest.mark.asyncio
async def test_lifecycle_terminates_expired_instances(db_session, instance_service):
    """Test lifecycle job terminates TTL-expired instances."""
    # Create instance with TTL="PT1H"
    # Advance time by 2 hours
    # Run lifecycle job
    # Verify instance was terminated
    # Verify metrics were recorded
```

### E2E Tests

**Location:** `tests/e2e/test_background_jobs.py`

**Coverage:**

```python
@pytest.mark.e2e
def test_background_jobs_running_in_cluster(cluster, control_plane_pod):
    """Verify background jobs are running in deployed cluster."""
    # Query /metrics endpoint
    # Verify job_execution_total has values
    # Verify no job failures in last 5 minutes

@pytest.mark.e2e
def test_orphaned_pod_cleanup(cluster, kubectl):
    """Test reconciliation job cleans up orphaned pods."""
    # Create orphaned pod (pod without database instance)
    # Wait 6 minutes (1 reconciliation pass)
    # Verify pod was deleted
    # Verify metrics show orphan detection and cleanup
```

---

## Deployment

### Kubernetes Deployment

**Changes to Control Plane Deployment:**

No changes needed! Background jobs run in the same process as FastAPI.

**Verification:**

```bash
# Check scheduler started
kubectl logs -n graph-olap-platform deployment/control-plane | grep scheduler_starting

# Verify jobs registered
kubectl logs -n graph-olap-platform deployment/control-plane | grep job_registered

# Check metrics endpoint (from a pod in the same cluster)
curl http://control-plane.graph-olap-platform.svc.cluster.local:8080/metrics | grep background_job
```

### High Availability Considerations

**Single Replica Mode (Current):**
- One Control Plane pod
- One APScheduler instance
- No distributed locking needed
- Jobs run in-process

**Multi-Replica Mode (Future):**

If scaling Control Plane to multiple replicas:

**Option 1: Leader Election**
- Use Kubernetes leader election (via client-go)
- Only leader runs background jobs
- Followers remain passive

**Option 2: Distributed Locking**
- Use Redis for distributed locks
- Each job acquires lock before execution
- Prevents duplicate executions

**Option 3: Separate Job Pod**
- Deploy background jobs in dedicated pod
- Keep Control Plane stateless
- Use Deployment with replicas=1 for jobs

**Recommendation:** Start with single replica. If scaling needed, use Option 3 (separate job pod) for clean separation.

---

## Open Questions

**Q: Should we implement distributed locking for multi-replica deployments?**

**Status:** Deferred

**Context:** Current deployment uses single Control Plane replica. If scaling to multiple replicas, jobs would run multiple times (once per replica).

**Options:**
1. Kubernetes leader election (jobs only on leader)
2. Redis distributed locks (each job acquires lock)
3. Separate job pod (dedicated pod for background jobs)

**Recommendation:** Wait until multi-replica deployment is needed. Then implement Option 3 (separate job pod) for simplest architecture.

---

**Q: Should schema cache job query Starburst directly or use Control Plane Starburst client?**

**Status:** Pending Starburst client implementation

**Context:** Schema cache job needs to query Starburst metadata. Two options:

1. **Direct connection:** Job creates its own Starburst connection
   - Pros: Simple, no dependencies
   - Cons: Duplicate connection logic

2. **Reuse client:** Job uses Control Plane's Starburst client
   - Pros: Shared connection pooling, consistent error handling
   - Cons: Client must be initialized before jobs start

**Recommendation:** Use Option 2 (reuse client) for consistency and connection pooling.

---

## Anti-Patterns

### Architectural

See [architectural.guardrails.md](--/foundation/architectural.guardrails.md#anti-patterns-must-not-do) for the authoritative list. Key sections relevant to background jobs:

- **Database & Schema** - No raw SQL; use repository methods
- **Concurrency** - No threads; use async/await exclusively
- **Error Handling** - No silent failures; log and record metrics

### Component-Specific

These constraints are specific to background jobs:

1. **DO NOT** use blocking I/O in job functions
   - Why: Blocks event loop, prevents API requests
   - Instead: Use async/await for all database and K8s operations

2. **DO NOT** accumulate unbounded lists
   - Why: Memory exhaustion with large datasets
   - Instead: Paginate queries with LIMIT, process in batches

3. **DO NOT** fail loudly on single-resource errors
   - Why: One bad pod/instance shouldn't stop entire job
   - Instead: Log error, increment failure metric, continue

4. **DO NOT** use sleep() or time.sleep()
   - Why: Blocks event loop
   - Instead: Use asyncio.sleep() for delays

5. **DO NOT** query all instances/snapshots/mappings without LIMIT
   - Why: Performance degradation as dataset grows
   - Instead: Use LIMIT=100, paginate if needed

6. **DO NOT** create jobs without metrics
   - Why: Impossible to monitor in production
   - Instead: Increment counters for key operations, track duration

---

## Related Documents

- [instance-lifecycle-management.design.md](-/instance-lifecycle-management.design.md) - Pod tracking fix and reconciliation design
- [control-plane.design.md](-/control-plane.design.md) - Control Plane core design
- [control-plane.services.design.md](-/control-plane.services.design.md) - Service layer design
- [operations/observability.design.md](--/operations/observability.design.md) - Logging and metrics strategy
- [operations/deployment.design.md](--/operations/deployment.design.md) - Kubernetes deployment
- [standards/python-logging-standards.md](--/standards/python-logging-standards.md) - Logging conventions
- [ADR-088: Content-Addressable Notebook Sync Init Container](--/process/adr/infrastructure/adr-088-notebook-sync-init-container.md) - Notebook sync is an init container (not a background job); see ADR for architecture
- [ADR-093: Instance Creation from Mapping API](--/process/adr/api-design/adr-093-instance-creation-from-mapping-api.md) - Defines the `waiting_for_snapshot` workflow that Instance Orchestration Job supports
