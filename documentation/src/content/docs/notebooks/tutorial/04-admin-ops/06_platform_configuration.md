---
title: "Deep Platform Configuration"
---

<div class="nb-header">
  <span class="nb-header__type">Tutorial</span>
  <h1 class="nb-header__title">Deep Platform Configuration</h1>
  <p class="nb-header__subtitle">Configure lifecycle, concurrency, maintenance, and background jobs</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">30 min</span>
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
  <div class="nb-header__tags"><span class="nb-header__tag">Configuration</span><span class="nb-header__tag">Lifecycle</span><span class="nb-header__tag">Maintenance</span><span class="nb-header__tag">Jobs</span><span class="nb-header__tag">Ops</span></div>
</div>

<div class="nb-objectives">
  <h3 class="nb-objectives__title">What You'll Learn</h3>
  <ul class="nb-objectives__list">
    <li><strong>Lifecycle Configuration</strong> — Read and modify TTLs for mappings, snapshots, and instances</li>
    <li><strong>Concurrency Limits</strong> — Adjust per-analyst and cluster-wide instance caps</li>
    <li><strong>Maintenance Mode</strong> — Enable/disable with custom messages</li>
    <li><strong>Export Configuration</strong> — Control export duration limits</li>
    <li><strong>Background Jobs</strong> — Trigger and monitor reconciliation, lifecycle, and cache jobs</li>
    <li><strong>Platform State</strong> — Inspect system state and export job history</li>
    <li><strong>Maintenance Workflow</strong> — Complete end-to-end maintenance window procedure</li>
  </ul>
</div>

<div class="nb-section">
  <span class="nb-section__number">1</span>
  <div>
    <h2 class="nb-section__title">Setup</h2>
    <p class="nb-section__description">Connect as Dave (ops persona)</p>
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

# Cell 3 — Provision
from notebook_setup import provision
personas, conn = provision(USERNAME)
analyst = personas["analyst"]
admin = personas["admin"]
ops = personas["ops"]

print(f"Connected to: {ops._config.api_url}")
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Lifecycle Configuration</h2>
    <p class="nb-section__description">TTLs and inactivity timeouts for mappings, snapshots, and instances</p>
  </div>
</div>

```python
# Read current lifecycle configuration
# Each resource type (mapping, snapshot, instance) has:
#   - default_ttl:        how long before automatic expiry
#   - default_inactivity: how long idle before cleanup
#   - max_ttl:            upper bound analysts can request
lifecycle = ops.ops.get_lifecycle_config()

print(f"{'Resource':<12} {'Default TTL':<14} {'Inactivity':<14} {'Max TTL':<10}")
print("-" * 52)
for name, cfg in [
    ("Mapping",  lifecycle.mapping),
    ("Snapshot", lifecycle.snapshot),
    ("Instance", lifecycle.instance),
]:
    ttl = str(cfg.default_ttl or "N/A")
    inact = str(cfg.default_inactivity or "N/A")
    max_t = str(cfg.max_ttl or "N/A")
    print(f"{name:<12} {ttl:<14} {inact:<14} {max_t:<10}")
```

```python
# Save original instance TTL, then modify it
original_instance_ttl = lifecycle.instance.default_ttl
print(f"Original instance TTL: {original_instance_ttl}")

# Extend instance TTL to 24 hours (ISO 8601 duration)
ops.ops.update_lifecycle_config(
    instance={"default_ttl": "PT24H"}
)

# Verify the change
updated = ops.ops.get_lifecycle_config()
print(f"Updated instance TTL:  {updated.instance.default_ttl}")

# Restore original
ops.ops.update_lifecycle_config(
    instance={"default_ttl": original_instance_ttl}
)
restored = ops.ops.get_lifecycle_config()
print(f"Restored instance TTL: {restored.instance.default_ttl}")
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Concurrency Limits</h2>
    <p class="nb-section__description">Per-analyst and cluster-wide instance caps</p>
  </div>
</div>

```python
# Read current concurrency limits
concurrency = ops.ops.get_concurrency_config()
original_per_analyst = concurrency.per_analyst
original_cluster_total = concurrency.cluster_total

print(f"Current per_analyst:   {original_per_analyst}")
print(f"Current cluster_total: {original_cluster_total}")

# Temporarily lower limits (e.g., during maintenance prep)
ops.ops.update_concurrency_config(
    per_analyst=2,
    cluster_total=20,
)
lowered = ops.ops.get_concurrency_config()
print(f"\nLowered per_analyst:   {lowered.per_analyst}")
print(f"Lowered cluster_total: {lowered.cluster_total}")

# Restore original limits
ops.ops.update_concurrency_config(
    per_analyst=original_per_analyst,
    cluster_total=original_cluster_total,
)
restored = ops.ops.get_concurrency_config()
print(f"\nRestored per_analyst:   {restored.per_analyst}")
print(f"Restored cluster_total: {restored.cluster_total}")
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Maintenance Mode</h2>
    <p class="nb-section__description">Block new instance creation during maintenance windows</p>
  </div>
</div>

```python
# Check current maintenance mode
maint = ops.ops.get_maintenance_mode()
print(f"Maintenance mode: {'ENABLED' if maint.enabled else 'DISABLED'}")

# Enable maintenance mode with a user-visible message
ops.ops.set_maintenance_mode(
    enabled=True,
    message="Scheduled maintenance — database upgrade in progress",
)
maint = ops.ops.get_maintenance_mode()
print(f"\nMaintenance mode: {'ENABLED' if maint.enabled else 'DISABLED'}")
print(f"Message:          {maint.message}")

# Disable maintenance mode
ops.ops.set_maintenance_mode(enabled=False, message="")
maint = ops.ops.get_maintenance_mode()
print(f"\nMaintenance mode: {'ENABLED' if maint.enabled else 'DISABLED'}")
```

<div class="nb-section">
  <span class="nb-section__number">5</span>
  <div>
    <h2 class="nb-section__title">Export Configuration</h2>
    <p class="nb-section__description">Control export duration limits</p>
  </div>
</div>

```python
# Read current export config
export = ops.ops.get_export_config()
original_max_duration = export.max_duration_seconds
print(f"Current max export duration: {original_max_duration}s")

# Increase to 2 hours for a large export window
ops.ops.update_export_config(max_duration_seconds=7200)
updated = ops.ops.get_export_config()
print(f"Updated max export duration: {updated.max_duration_seconds}s")

# Restore original
ops.ops.update_export_config(max_duration_seconds=original_max_duration)
restored = ops.ops.get_export_config()
print(f"Restored max export duration: {restored.max_duration_seconds}s")
```

<div class="nb-section">
  <span class="nb-section__number">6</span>
  <div>
    <h2 class="nb-section__title">Background Jobs</h2>
    <p class="nb-section__description">Trigger and monitor reconciliation, lifecycle, and cache jobs</p>
  </div>
</div>

```python
# View scheduled job statuses
# Each job has a name and next scheduled run time
job_status = ops.ops.get_job_status()

print(f"{'Job Name':<25} {'Next Run':>25}")
print("-" * 52)
for job in job_status["jobs"]:
    print(f"{job['name']:<25} {job['next_run']:>25}")
```

```python
# Manually trigger a reconciliation job
# Available jobs: reconciliation, lifecycle, export_reconciliation, schema_cache
# Rate-limited to 1 trigger per minute per job
result = ops.ops.trigger_job(
    job_name="reconciliation",
    reason="tutorial-demo",
)
print(f"Job:    {result['job_name']}")
print(f"Status: {result['status']}")
```

<div class="nb-section">
  <span class="nb-section__number">7</span>
  <div>
    <h2 class="nb-section__title">Platform State</h2>
    <p class="nb-section__description">System state summary and export job history</p>
  </div>
</div>

```python
# Get overall platform state -- nested dict with instance/snapshot/export counts
state = ops.ops.get_state()

print(f"Instances: {state['instances']['total']}")
print(f"By status: {state['instances']['by_status']}")
print(f"Snapshots: {state.get('snapshots', {}).get('total', 'N/A')}")
print(f"Exports:   {state.get('exports', {}).get('total', 'N/A')}")
```

```python
# Query export jobs by status
# Valid statuses: pending, claimed, completed, failed
completed_exports = ops.ops.get_export_jobs(status="completed", limit=5)
print(f"Recent completed exports: {len(completed_exports)}")
for job in completed_exports[:3]:
    print(f"  {job}")

# Check for any failed exports
failed_exports = ops.ops.get_export_jobs(status="failed", limit=10)
print(f"\nFailed exports: {len(failed_exports)}")
```

```python
# Prometheus metrics -- raw text/plain output from the control plane
metrics = ops.ops.get_metrics()

print("Prometheus metrics (first 5 lines):")
for line in metrics.splitlines()[:5]:
    print(f"  {line}")
```

<div class="nb-section">
  <span class="nb-section__number">8</span>
  <div>
    <h2 class="nb-section__title">Maintenance Window Workflow</h2>
    <p class="nb-section__description">Complete end-to-end maintenance procedure</p>
  </div>
</div>

```python
# Complete maintenance window workflow:
#   1. Save current settings
#   2. Lower concurrency limits
#   3. Enable maintenance mode
#   4. Trigger a background job
#   5. Verify platform state
#   6. Disable maintenance mode
#   7. Restore original settings

from graph_olap.exceptions import ConcurrencyLimitError

# --- Step 1: Save current settings ---
concurrency = ops.ops.get_concurrency_config()
saved_per_analyst = concurrency.per_analyst
saved_cluster_total = concurrency.cluster_total
print("Step 1: Saved current settings")
print(f"  per_analyst={saved_per_analyst}, cluster_total={saved_cluster_total}")

# --- Step 2: Lower concurrency limits ---
ops.ops.update_concurrency_config(per_analyst=1, cluster_total=10)
print("\nStep 2: Lowered concurrency limits")
lowered = ops.ops.get_concurrency_config()
print(f"  per_analyst={lowered.per_analyst}, cluster_total={lowered.cluster_total}")

# --- Step 3: Enable maintenance mode ---
ops.ops.set_maintenance_mode(
    enabled=True,
    message="Scheduled maintenance window — expect degraded service",
)
print("\nStep 3: Maintenance mode ENABLED")

# --- Step 4: Trigger a background job ---
# Use lifecycle (not reconciliation, which was triggered earlier and is rate-limited)
try:
    trigger = ops.ops.trigger_job(job_name="lifecycle", reason="maintenance-window")
    print(f"\nStep 4: Lifecycle job triggered (status={trigger['status']})")
except ConcurrencyLimitError:
    print("\nStep 4: Job rate-limited (already triggered recently) — skipping")

# --- Step 5: Verify platform state ---
state = ops.ops.get_state()
job_status = ops.ops.get_job_status()
print("\nStep 5: Platform state check")
print(f"  Instances: {state['instances']['total']}")
print(f"  By status: {state['instances']['by_status']}")
print(f"  Scheduled jobs: {len(job_status['jobs'])}")

# --- Step 6: Disable maintenance mode ---
ops.ops.set_maintenance_mode(enabled=False, message="")
print("\nStep 6: Maintenance mode DISABLED")

# --- Step 7: Restore original settings ---
ops.ops.update_concurrency_config(
    per_analyst=saved_per_analyst,
    cluster_total=saved_cluster_total,
)
restored = ops.ops.get_concurrency_config()
print("\nStep 7: Restored original settings")
print(f"  per_analyst={restored.per_analyst}, cluster_total={restored.cluster_total}")

print("\nMaintenance window complete.")
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li><code>get_lifecycle_config()</code> returns TTL settings for mappings, snapshots, and instances — use <code>update_lifecycle_config()</code> to modify</li>
    <li><code>update_concurrency_config()</code> sets <code>per_analyst</code> and <code>cluster_total</code> caps — lower during maintenance</li>
    <li><code>set_maintenance_mode()</code> blocks new instance creation and shows a message to users</li>
    <li><code>update_export_config()</code> controls the maximum export duration in seconds</li>
    <li><code>trigger_job()</code> manually fires reconciliation, lifecycle, export, or cache jobs (rate-limited 1/min/job)</li>
    <li><code>get_state()</code> and <code>get_export_jobs()</code> provide platform-wide visibility</li>
    <li>Always use the read-modify-restore pattern: save originals before changing, restore when done</li>
  </ul>
</div>
