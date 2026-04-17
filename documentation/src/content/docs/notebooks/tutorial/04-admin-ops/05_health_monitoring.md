---
title: "Health Monitoring"
---

<div class="nb-header">
  <span class="nb-header__type">Tutorial</span>
  <h1 class="nb-header__title">Health Monitoring</h1>
  <p class="nb-header__subtitle">Monitor platform health, cluster status, and instance capacity</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">20 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--intermediate">
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
      </span>
      Intermediate
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">Health</span><span class="nb-header__tag">Monitoring</span><span class="nb-header__tag">Cluster</span><span class="nb-header__tag">Ops</span></div>
</div>

<div class="nb-objectives">
  <h3 class="nb-objectives__title">What You'll Learn</h3>
  <ul class="nb-objectives__list">
    <li><strong>Liveness Probes</strong> — Basic health check with <code>client.health.check()</code></li>
    <li><strong>Readiness Probes</strong> — Full readiness including database with <code>client.health.ready()</code></li>
    <li><strong>Cluster Health</strong> — Per-component status with <code>ops.ops.get_cluster_health()</code></li>
    <li><strong>Instance Capacity</strong> — Cluster-wide limits and usage with <code>ops.ops.get_cluster_instances()</code></li>
    <li><strong>Prometheus Metrics</strong> — Raw metrics endpoint with <code>ops.ops.get_metrics()</code></li>
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
    <h2 class="nb-section__title">Liveness Probes</h2>
    <p class="nb-section__description">Basic health check — is the service running?</p>
  </div>
</div>

```python
# Liveness check — unauthenticated, returns status and version
# This is what Kubernetes uses for its liveness probe.
# A passing liveness check means the process is running and
# accepting HTTP connections — nothing more.
liveness = client.health.check()

print(f"Status:  {liveness.status}")
print(f"Version: {liveness.version}")
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Readiness Probes</h2>
    <p class="nb-section__description">Full readiness check including database connectivity</p>
  </div>
</div>

```python
# Readiness check — also unauthenticated, but verifies database
# connectivity. Kubernetes uses this for its readiness probe.
# A pod only receives traffic when the readiness probe passes.
#
# Liveness vs Readiness:
#   - Liveness:  "Is the process alive?"   → restart if failing
#   - Readiness: "Can it serve requests?"  → remove from LB if failing
readiness = client.health.ready()

print(f"Status:   {readiness.status}")
print(f"Version:  {readiness.version}")
print(f"Database: {readiness.database}")
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Cluster Health</h2>
    <p class="nb-section__description">Per-component health with latency data</p>
  </div>
</div>

```python
# Cluster health — requires ops role
# Returns overall status plus per-component breakdown with latency
health = ops.ops.get_cluster_health()

print(f"Overall status: {health.status}")
print(f"Checked at:     {health.checked_at}")
print()
print(f"{'Component':<20} {'Status':<12} {'Latency (ms)':>12}")
print("-" * 46)
for name, comp in health.components.items():
    latency = f"{comp.latency_ms:.1f}" if comp.latency_ms is not None else "N/A"
    print(f"{name:<20} {comp.status:<12} {latency:>12}")
```

```python
# Detect degraded or unhealthy components
# In production, you would alert on non-healthy components
unhealthy = [
    (name, comp)
    for name, comp in health.components.items()
    if comp.status != "healthy"
]

if unhealthy:
    print("WARNING: Non-healthy components detected:")
    for name, comp in unhealthy:
        print(f"  {name}: {comp.status} (latency: {comp.latency_ms}ms)")
else:
    print("All components healthy")
```

<div class="nb-section">
  <span class="nb-section__number">5</span>
  <div>
    <h2 class="nb-section__title">Instance Capacity</h2>
    <p class="nb-section__description">Track instance counts, ownership, and cluster limits</p>
  </div>
</div>

```python
# Cluster instance summary — requires ops role
instances = ops.ops.get_cluster_instances()

print(f"Total instances: {instances.total}")
print()

# Breakdown by status
print("By status:")
for status, count in instances.by_status.items():
    print(f"  {status:<15} {count}")
print()

# Breakdown by owner (list of OwnerInstanceCount objects)
print("By owner:")
for entry in instances.by_owner:
    print(f"  {entry}")
```

```python
# Cluster capacity limits
limits = instances.limits

print("Capacity limits:")
print(f"  Per analyst:       {limits.per_analyst}")
print(f"  Cluster total:     {limits.cluster_total}")
print(f"  Cluster used:      {limits.cluster_used}")
print(f"  Cluster available: {limits.cluster_available}")
print()

# Calculate utilisation percentage
utilisation = (limits.cluster_used / limits.cluster_total) * 100
print(f"Cluster utilisation: {utilisation:.0f}%")
```

<div class="nb-section">
  <span class="nb-section__number">6</span>
  <div>
    <h2 class="nb-section__title">Prometheus Metrics</h2>
    <p class="nb-section__description">Raw metrics for scraping and ad-hoc inspection</p>
  </div>
</div>

```python
# Prometheus metrics — returns raw text in Prometheus exposition format
# Typically scraped by Prometheus, but useful for ad-hoc inspection
metrics_text = ops.ops.get_metrics()

# Show the first 10 lines as a preview
lines = metrics_text.strip().splitlines()
print(f"Total metric lines: {len(lines)}")
print()
for line in lines[:10]:
    print(line)
```

<div class="nb-section">
  <span class="nb-section__number">7</span>
  <div>
    <h2 class="nb-section__title">Building a Health Dashboard</h2>
    <p class="nb-section__description">Combine health data into a single summary</p>
  </div>
</div>

```python
# Combine all health signals into a single dashboard summary
liveness  = client.health.check()
readiness = client.health.ready()
health    = ops.ops.get_cluster_health()
instances = ops.ops.get_cluster_instances()

dashboard = {
    "platform": {
        "liveness":  liveness.status,
        "readiness": readiness.status,
        "database":  readiness.database,
        "version":   liveness.version,
    },
    "cluster": {
        "status":     health.status,
        "checked_at": str(health.checked_at),
        "components": {
            name: {"status": c.status, "latency_ms": c.latency_ms}
            for name, c in health.components.items()
        },
    },
    "capacity": {
        "total":     instances.total,
        "running":   instances.by_status.get("running", 0),
        "available": instances.limits.cluster_available,
        "limit":     instances.limits.cluster_total,
    },
}

# Pretty-print the dashboard
import json
print(json.dumps(dashboard, indent=2))
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li><code>client.health.check()</code> is the liveness probe — unauthenticated, returns status and version</li>
    <li><code>client.health.ready()</code> is the readiness probe — also checks database connectivity</li>
    <li><code>ops.ops.get_cluster_health()</code> returns per-component status with latency — requires ops role</li>
    <li><code>ops.ops.get_cluster_instances()</code> gives instance counts by status/owner plus capacity limits</li>
    <li><code>ops.ops.get_metrics()</code> returns Prometheus-format text for scraping or ad-hoc inspection</li>
    <li>Combine all health signals into a single dashboard dict for unified monitoring</li>
  </ul>
</div>
