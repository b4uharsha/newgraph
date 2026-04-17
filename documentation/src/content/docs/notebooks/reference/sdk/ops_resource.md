---
title: "OpsResource"
---

<div class="nb-header">
  <span class="nb-header__type">Reference</span>
  <h1 class="nb-header__title">OpsResource</h1>
  <p class="nb-header__subtitle">Platform operations and configuration</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">15 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--advanced">
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
      </span>
      Advanced
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">Reference</span><span class="nb-header__tag">API</span><span class="nb-header__tag">Ops</span></div>
</div>

## OpsResource

Accessed via `client.ops`, this resource manages platform-wide operational
configuration, cluster health monitoring, background jobs, and system state.
All operations require the Ops role.

Configuration changes follow a **read-modify-restore** pattern: read the
current value, apply your change, and restore the original when done.

<div class="nb-section">
  <span class="nb-section__number">1</span>
  <div>
    <h2 class="nb-section__title">Setup</h2>
    <p class="nb-section__description">Connect as an ops user</p>
  </div>
</div>

```python
# Cell 1 — Parameters
USERNAME = "_FILL_ME_IN_"  # Set your email before running
```

```python
# Cell 2 — Connect
from graph_olap import GraphOLAPClient
client = GraphOLAPClient(username=USERNAME)
```

```python
# Cell 3 — Provision
from notebook_setup import provision
personas, _ = provision(USERNAME)
analyst = personas["analyst"]
admin = personas["admin"]
ops = personas["ops"]
client = analyst
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Cluster Health</h2>
    <p class="nb-section__description">Monitor cluster and component status</p>
  </div>
</div>

### `get_cluster_health() -> ClusterHealth`

Check connectivity to all platform components (database, kubernetes, starburst).

**Returns:** `ClusterHealth` with `.status` (`healthy`, `degraded`, `unhealthy`)
and `.components` dict of `ComponentHealth` objects.

```python
health = ops.ops.get_cluster_health()

print(f"Cluster status: {health.status}")
print(f"Checked at:     {health.checked_at}\n")
for name, comp in health.components.items():
    print(f"  {name}: {comp.status} ({comp.latency_ms}ms)")
```

### `get_cluster_instances() -> ClusterInstances`

Get a cluster-wide summary of instances: totals, breakdowns by status and
owner, and current capacity limits.

**Returns:** `ClusterInstances` with `.total`, `.by_status`, `.by_owner`,
and `.limits` (`InstanceLimits`).

```python
instances = ops.ops.get_cluster_instances()

print(f"Total instances: {instances.total}")
print(f"By status:       {instances.by_status}")
print(f"Capacity:        {instances.limits.cluster_used}/{instances.limits.cluster_total}")
```

### `get_metrics() -> str`

Fetch Prometheus metrics from the control plane. Returns metrics for
background jobs, reconciliation loops, lifecycle enforcement, and general
system health in `text/plain` format.

```python
metrics = ops.ops.get_metrics()

# Show the first 5 lines
for line in metrics.splitlines()[:5]:
    print(line)
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Lifecycle Configuration</h2>
    <p class="nb-section__description">Manage default TTL and inactivity settings</p>
  </div>
</div>

### `get_lifecycle_config() -> LifecycleConfig`

Returns lifecycle defaults for all resource types (mapping, snapshot, instance).
Each has `default_ttl`, `default_inactivity`, and `max_ttl` fields.

### `update_lifecycle_config(*, mapping=None, snapshot=None, instance=None) -> bool`

Update lifecycle settings. Only provided values are changed; omitted values
remain unchanged. Accepts `ResourceLifecycleConfig` objects or plain dicts.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `mapping` | `dict \| ResourceLifecycleConfig \| None` | `None` | Lifecycle config for mappings |
| `snapshot` | `dict \| ResourceLifecycleConfig \| None` | `None` | Lifecycle config for snapshots |
| `instance` | `dict \| ResourceLifecycleConfig \| None` | `None` | Lifecycle config for instances |

**Returns:** `True` if update succeeded.

```python
# Read current config
original = ops.ops.get_lifecycle_config()

print("Current instance lifecycle:")
print(f"  default_ttl:        {original.instance.default_ttl}")
print(f"  default_inactivity: {original.instance.default_inactivity}")
print(f"  max_ttl:            {original.instance.max_ttl}")
```

```python
# Modify instance TTL
ops.ops.update_lifecycle_config(instance={"default_ttl": "PT12H"})

updated = ops.ops.get_lifecycle_config()
print(f"Updated default_ttl: {updated.instance.default_ttl}")

# Restore original
ops.ops.update_lifecycle_config(
    instance={
        "default_ttl": original.instance.default_ttl,
        "default_inactivity": original.instance.default_inactivity,
        "max_ttl": original.instance.max_ttl,
    }
)
print(f"Restored default_ttl: {original.instance.default_ttl}")
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Concurrency</h2>
    <p class="nb-section__description">Control per-analyst and cluster-wide instance limits</p>
  </div>
</div>

### `get_concurrency_config() -> ConcurrencyConfig`

Returns per-analyst and cluster-total instance limits.

### `update_concurrency_config(*, per_analyst, cluster_total) -> ConcurrencyConfig`

Update concurrency limits. Both parameters are required.

| Parameter | Type | Range | Description |
|-----------|------|-------|-------------|
| `per_analyst` | `int` | 1--100 | Max instances per analyst |
| `cluster_total` | `int` | 1--1000 | Max instances cluster-wide |

**Returns:** Updated `ConcurrencyConfig`.

```python
# Read current limits
original_conc = ops.ops.get_concurrency_config()

print(f"Per analyst:   {original_conc.per_analyst}")
print(f"Cluster total: {original_conc.cluster_total}")
```

```python
# Temporarily lower limits
updated_conc = ops.ops.update_concurrency_config(per_analyst=5, cluster_total=20)
print(f"Updated per_analyst: {updated_conc.per_analyst}")
print(f"Updated cluster_total: {updated_conc.cluster_total}")

# Restore original
ops.ops.update_concurrency_config(
    per_analyst=original_conc.per_analyst,
    cluster_total=original_conc.cluster_total,
)
print(f"Restored per_analyst: {original_conc.per_analyst}")
```

<div class="nb-section">
  <span class="nb-section__number">5</span>
  <div>
    <h2 class="nb-section__title">Maintenance Mode</h2>
    <p class="nb-section__description">Block new instance creation during maintenance</p>
  </div>
</div>

### `get_maintenance_mode() -> MaintenanceMode`

Returns current maintenance mode status.

### `set_maintenance_mode(enabled, message="") -> MaintenanceMode`

Enable or disable maintenance mode. When enabled, new instance creation is
blocked and users see the provided message.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enabled` | `bool` | *required* | Whether maintenance mode is active |
| `message` | `str` | `""` | Message displayed to users |

```python
# Check current status
maint = ops.ops.get_maintenance_mode()
print(f"Enabled: {maint.enabled}")
print(f"Message: {maint.message}")
```

```python
# Enable maintenance mode
ops.ops.set_maintenance_mode(
    enabled=True,
    message="Scheduled maintenance -- back at 14:00 UTC",
)

maint = ops.ops.get_maintenance_mode()
print(f"Enabled: {maint.enabled}")
print(f"Message: {maint.message}")

# Disable maintenance mode
ops.ops.set_maintenance_mode(enabled=False)
print(f"\nMaintenance disabled: {not ops.ops.get_maintenance_mode().enabled}")
```

<div class="nb-section">
  <span class="nb-section__number">6</span>
  <div>
    <h2 class="nb-section__title">Export Configuration</h2>
    <p class="nb-section__description">Control export job duration limits</p>
  </div>
</div>

### `get_export_config() -> ExportConfig`

Returns export configuration including the maximum job duration.

### `update_export_config(*, max_duration_seconds) -> ExportConfig`

Update the maximum duration for export jobs.

| Parameter | Type | Range | Description |
|-----------|------|-------|-------------|
| `max_duration_seconds` | `int` | 60--86400 | Max export job duration in seconds |

```python
# Read current config
original_export = ops.ops.get_export_config()
print(f"Max duration: {original_export.max_duration_seconds}s")

# Update
updated_export = ops.ops.update_export_config(max_duration_seconds=7200)
print(f"Updated:      {updated_export.max_duration_seconds}s")

# Restore original
ops.ops.update_export_config(
    max_duration_seconds=original_export.max_duration_seconds
)
print(f"Restored:     {original_export.max_duration_seconds}s")
```

<div class="nb-section">
  <span class="nb-section__number">7</span>
  <div>
    <h2 class="nb-section__title">Jobs</h2>
    <p class="nb-section__description">Trigger and monitor background jobs</p>
  </div>
</div>

### `trigger_job(job_name, reason="manual-trigger") -> dict`

Manually trigger a background job. Useful for smoke tests, manual
reconciliation after incidents, or debugging.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `job_name` | `str` | *required* | `"reconciliation"`, `"lifecycle"`, `"export_reconciliation"`, or `"schema_cache"` |
| `reason` | `str` | `"manual-trigger"` | Reason for trigger (audit log) |

**Rate limit:** 1 trigger per job per minute.

### `get_job_status() -> dict`

Get status of all background jobs including next scheduled run times.

```python
# Trigger reconciliation manually
result = ops.ops.trigger_job("reconciliation", reason="smoke-test")

print(f"Job:     {result['job_name']}")
print(f"Status:  {result['status']}")
```

```python
# Check all job statuses
status = ops.ops.get_job_status()

for job in status["jobs"]:
    print(f"  {job['name']}: next run at {job['next_run']}")
```

<div class="nb-section">
  <span class="nb-section__number">8</span>
  <div>
    <h2 class="nb-section__title">Platform State</h2>
    <p class="nb-section__description">Inspect system state and export jobs</p>
  </div>
</div>

### `get_state() -> dict`

Get a system state summary with counts of instances, snapshots, and
export jobs by status.

### `get_export_jobs(status=None, limit=100) -> list[dict]`

List export jobs for debugging. Filter by status to find stale or failed jobs.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `status` | `str \| None` | `None` | `"pending"`, `"claimed"`, `"completed"`, or `"failed"` |
| `limit` | `int` | `100` | Max jobs to return (max 1000) |

```python
state = ops.ops.get_state()

print(f"Instances: {state['instances']['total']}")
print(f"By status: {state['instances']['by_status']}")
```

```python
# Check for stale claimed export jobs
claimed = ops.ops.get_export_jobs(status="claimed")

print(f"Claimed export jobs: {len(claimed)}")
for job in claimed:
    print(f"  Job {job['id']} claimed by {job['claimed_by']}")
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li>Always <strong>read-modify-restore</strong> when changing config: save the original, make your change, then restore it</li>
    <li><code>get_cluster_health()</code> checks all platform components in one call</li>
    <li><code>get_cluster_instances()</code> shows capacity and per-owner breakdowns</li>
    <li>Use <code>trigger_job()</code> for manual reconciliation or smoke tests (rate-limited to 1/min per job)</li>
    <li><code>get_state()</code> and <code>get_export_jobs()</code> are essential for debugging platform issues</li>
  </ul>
</div>
