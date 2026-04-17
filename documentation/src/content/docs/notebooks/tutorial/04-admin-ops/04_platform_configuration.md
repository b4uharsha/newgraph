---
title: "Platform Configuration"
---

<div class="nb-header">
  <span class="nb-header__type">Tutorial</span>
  <h1 class="nb-header__title">Platform Configuration</h1>
  <p class="nb-header__subtitle">Configure TTLs, limits, and platform behavior</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">30 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--advanced">
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
      </span>
      Advanced
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">Ops</span><span class="nb-header__tag">Configuration</span><span class="nb-header__tag">TTL</span><span class="nb-header__tag">Limits</span></div>
</div>

<div class="nb-objectives">
  <h3 class="nb-objectives__title">What You'll Learn</h3>
  <ul class="nb-objectives__list">
    <li><strong>TTL Settings</strong> — Configure instance/snapshot TTLs with ISO 8601 durations</li>
    <li><strong>Concurrency Limits</strong> — Set per-analyst and cluster-wide caps</li>
    <li><strong>Maintenance Mode</strong> — Enable/disable platform maintenance windows</li>
    <li><strong>Export Config</strong> — Control export duration and behaviour</li>
  </ul>
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

client = ops
print(f"Connected to: {ops._config.api_url}")
```

<div class="nb-section">
  <span class="nb-section__number">1</span>
  <div>
    <h2 class="nb-section__title">TTL Configuration</h2>
    <p class="nb-section__description">Automatic cleanup with ISO 8601 durations</p>
  </div>
</div>

```python
# View current lifecycle settings
lifecycle = client.ops.get_lifecycle_config()
print(f"Current instance TTL: {lifecycle.instance.default_ttl}")

# Update instance TTL to 24 hours (ISO 8601 duration format)
# Common formats: PT1H (1 hour), PT24H (24 hours), P7D (7 days)
client.ops.update_lifecycle_config(
    instance={"default_ttl": "PT24H"}
)

# Verify the change
lifecycle = client.ops.get_lifecycle_config()
print(f"Updated instance TTL: {lifecycle.instance.default_ttl}")
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Concurrency Limits</h2>
    <p class="nb-section__description">Per-analyst and cluster-wide caps</p>
  </div>
</div>

```python
# View current concurrency limits
concurrency = client.ops.get_concurrency_config()
print(f"Per analyst:   {concurrency.per_analyst}")
print(f"Cluster total: {concurrency.cluster_total}")

# Update concurrency limits
client.ops.update_concurrency_config(
    per_analyst=10,
    cluster_total=200,
)

# Verify
concurrency = client.ops.get_concurrency_config()
print(f"\nUpdated per analyst:   {concurrency.per_analyst}")
print(f"Updated cluster total: {concurrency.cluster_total}")
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Maintenance Mode</h2>
    <p class="nb-section__description">Enable/disable scheduled maintenance windows</p>
  </div>
</div>

```python
# Check current maintenance mode status
maint = client.ops.get_maintenance_mode()
print(f"Maintenance mode: {'ENABLED' if maint.enabled else 'DISABLED'}")
if maint.enabled:
    print(f"Message: {maint.message}")

# Enable maintenance mode (blocks new instance creation)
client.ops.set_maintenance_mode(
    enabled=True,
    message="Scheduled maintenance — upgrading database cluster",
)
print("\nMaintenance mode enabled.")

# Disable maintenance mode
client.ops.set_maintenance_mode(enabled=False, message="")
print("Maintenance mode disabled.")
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Export Configuration</h2>
    <p class="nb-section__description">Control export duration limits</p>
  </div>
</div>

```python
# View current export settings
export = client.ops.get_export_config()
print(f"Max export duration: {export.max_duration_seconds}s")

# Update max export duration to 2 hours
client.ops.update_export_config(max_duration_seconds=7200)

# Verify
export = client.ops.get_export_config()
print(f"Updated max duration: {export.max_duration_seconds}s")
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li>TTLs use ISO 8601 duration format (<code>PT24H</code>, <code>P7D</code>) via <code>update_lifecycle_config()</code></li>
    <li>Concurrency is split into <code>per_analyst</code> and <code>cluster_total</code> via <code>update_concurrency_config()</code></li>
    <li><code>set_maintenance_mode()</code> blocks new instance creation during maintenance windows</li>
    <li><code>update_export_config()</code> controls max export duration in seconds</li>
    <li>All configuration changes require ops-level permissions and take effect immediately</li>
  </ul>
</div>
