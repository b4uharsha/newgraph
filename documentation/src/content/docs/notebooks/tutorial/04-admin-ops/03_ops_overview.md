---
title: "Ops Overview"
---

<div class="nb-header">
  <span class="nb-header__type">Tutorial</span>
  <h1 class="nb-header__title">Ops Overview</h1>
  <p class="nb-header__subtitle">Platform operations and configuration management</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">15 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--intermediate">
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
      </span>
      Intermediate
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">Ops</span><span class="nb-header__tag">Platform</span><span class="nb-header__tag">Configuration</span></div>
</div>

<div class="nb-objectives">
  <h3 class="nb-objectives__title">What You'll Learn</h3>
  <ul class="nb-objectives__list">
    <li><strong>Lifecycle Config</strong> — View instance and snapshot TTL settings</li>
    <li><strong>Cluster Health</strong> — Check component-level platform health</li>
    <li><strong>Cluster Metrics</strong> — Instance counts and Prometheus metrics</li>
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
    <h2 class="nb-section__title">Lifecycle Configuration</h2>
    <p class="nb-section__description">Instance and snapshot TTL settings</p>
  </div>
</div>

```python
# View current lifecycle configuration
lifecycle = client.ops.get_lifecycle_config()

print("Instance settings:")
print(f"  Default TTL:    {lifecycle.instance.default_ttl}")
print(f"  Max TTL:        {lifecycle.instance.max_ttl}")

print("\nSnapshot settings:")
print(f"  Default TTL:    {lifecycle.snapshot.default_ttl}")

# Concurrency settings (separate endpoint)
concurrency = client.ops.get_concurrency_config()
print("\nConcurrency limits:")
print(f"  Per analyst:    {concurrency.per_analyst}")
print(f"  Cluster total:  {concurrency.cluster_total}")
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Cluster Health</h2>
    <p class="nb-section__description">Component-level health checks</p>
  </div>
</div>

```python
# Cluster health — returns overall status plus per-component breakdown
health = client.ops.get_cluster_health()

print(f"Overall status: {health.status}")
print("\nComponents:")
for name, comp in health.components.items():
    print(f"  {name}: {comp.status}")
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Cluster Metrics</h2>
    <p class="nb-section__description">Instance counts and Prometheus metrics</p>
  </div>
</div>

```python
# Instance summary — structured counts by status
instances = client.ops.get_cluster_instances()

print(f"Total instances: {instances.total}")
print(f"By status:       {instances.by_status}")

# Prometheus metrics — raw text format (for scraping or ad-hoc inspection)
metrics_text = client.ops.get_metrics()
# Show first 5 lines as a preview
for line in metrics_text.strip().splitlines()[:5]:
    print(line)
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li>Use <code>get_lifecycle_config()</code> and <code>get_concurrency_config()</code> to inspect platform settings</li>
    <li><code>get_cluster_health()</code> returns per-component status (control-plane, database, etc.)</li>
    <li><code>get_cluster_instances()</code> gives structured instance counts by status</li>
    <li><code>get_metrics()</code> returns raw Prometheus text for scraping or ad-hoc inspection</li>
  </ul>
</div>
