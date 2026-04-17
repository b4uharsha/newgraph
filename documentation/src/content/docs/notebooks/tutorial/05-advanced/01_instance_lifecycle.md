---
title: "Instance Lifecycle"
---

<div class="nb-header">
  <span class="nb-header__type">Tutorial</span>
  <h1 class="nb-header__title">Instance Lifecycle</h1>
  <p class="nb-header__subtitle">Understand TTL, health checks, and instance states</p>
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
  <div class="nb-header__tags"><span class="nb-header__tag">Instance</span><span class="nb-header__tag">Lifecycle</span><span class="nb-header__tag">TTL</span><span class="nb-header__tag">Health</span></div>
</div>

<div class="nb-objectives">
  <h3 class="nb-objectives__title">What You'll Learn</h3>
  <ul class="nb-objectives__list">
    <li><strong>Lifecycle States</strong> - pending → running → terminated</li>
    <li><strong>TTL Management</strong> - Automatic and manual termination</li>
    <li><strong>Health Monitoring</strong> - Liveness and readiness probes</li>
    <li><strong>Progress Tracking</strong> - Monitor long-running operations</li>
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
client = analyst

mapping = client.mappings.list(search="tutorial-customer-graph").items[0]
print(f"Connected to: {client._config.api_url}")
print(f"Using mapping: {mapping.name} (id={mapping.id})")
```

<div class="nb-section">
  <span class="nb-section__number">1</span>
  <div>
    <h2 class="nb-section__title">Instance States</h2>
    <p class="nb-section__description">Lifecycle state machine</p>
  </div>
</div>

```python
from graph_olap_schemas import WrapperType

# Instance state transitions
# ┌─────────┐    ┌──────────┐    ┌─────────┐    ┌────────────┐
# │ pending │───>│ starting │───>│ running │───>│ terminated │
# └─────────┘    └──────────┘    └─────────┘    └────────────┘
#                                     │
#                                     v
#                               ┌──────────┐
#                               │ stopping │
#                               └──────────┘

# Create an instance and observe its initial state
instance = client.instances.create_and_wait(
    mapping_id=mapping.id,
    name="lifecycle-demo",
    wrapper_type=WrapperType.RYUGRAPH,
    timeout=300,
    ttl="PT4H",  # 4-hour time-to-live
)

# Check the current state
print(f"Instance ID: {instance.id}")
print(f"Status:      {instance.status}")
print(f"Wrapper:     {instance.wrapper_type}")
print(f"Expires at:  {instance.expires_at}")
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">TTL and Termination</h2>
    <p class="nb-section__description">Automatic cleanup</p>
  </div>
</div>

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Health Checks</h2>
    <p class="nb-section__description">Monitoring instance health</p>
  </div>
</div>

```python
# Health checks — two flavours:

# 1. Detailed health info (returns dict with status details)
health = client.instances.get_health(instance.id)
print("Detailed health:")
for key, value in health.items():
    print(f"  {key}: {value}")

# 2. Quick boolean check
is_healthy = client.instances.check_health(instance.id)
print(f"\nHealthy? {is_healthy}")
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Progress Events</h2>
    <p class="nb-section__description">Track operation progress</p>
  </div>
</div>

```python
# Progress tracking for long-running operations
# (create_and_wait handles polling internally, but you can also
# check progress manually during instance creation)

progress = client.instances.get_progress(instance.id)
print(f"Phase:    {progress.phase}")
print(f"Progress: {progress.progress_percent}%")
print(f"Steps:    {progress.steps}")
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li>Instances transition: pending → starting → running → stopping → terminated</li>
    <li>Use <code>create_and_wait()</code> with a <code>ttl</code> (ISO 8601 duration) to auto-terminate</li>
    <li><code>extend_ttl(id, hours=N)</code> postpones automatic termination</li>
    <li><code>get_health()</code> returns detailed status; <code>check_health()</code> returns a boolean</li>
    <li><code>get_progress()</code> provides phase, progress_percent, and steps for long operations</li>
  </ul>
</div>

```python
# Cleanup: terminate the lifecycle-demo instance
try:
    client.instances.terminate(instance.id)
    print(f"Terminated instance {instance.id}")
except Exception as e:
    print(f"Instance cleanup: {e}")
```
