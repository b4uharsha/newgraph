---
title: "InstanceResource"
---

<div class="nb-header">
  <span class="nb-header__type">Reference</span>
  <h1 class="nb-header__title">InstanceResource</h1>
  <p class="nb-header__subtitle">Instance management operations</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">10 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--intermediate">
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
      </span>
      Intermediate
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">Reference</span><span class="nb-header__tag">API</span></div>
</div>

## InstanceResource

Accessed via `client.instances`, this resource manages the full lifecycle of graph
database instances -- from creation through connection to termination.

Each instance is backed by a graph engine (FalkorDB or RyuGraph) and is populated
from a mapping definition.

<div class="nb-section">
  <span class="nb-section__number">1</span>
  <div>
    <h2 class="nb-section__title">Setup</h2>
    <p class="nb-section__description">Connect to the platform</p>
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
from notebook_setup import provision, CUSTOMER_NODE, SHARES_ACCOUNT_EDGE, MAPPING_NAME, make_namespace
personas, conn = provision(USERNAME)
analyst = personas["analyst"]
admin = personas["admin"]
ops = personas["ops"]
client = analyst

# Look up the provisioned mapping and instance
namespace = make_namespace(USERNAME)
ref_mapping = client.mappings.list(search=f"{MAPPING_NAME}-{namespace}", limit=1).items[0]
mapping_id = ref_mapping.id
inst_id = conn.id
print(f"Using mapping [{mapping_id}] and instance [{inst_id}]")
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Creating Instances</h2>
    <p class="nb-section__description">Provision new graph instances</p>
  </div>
</div>

### `create(mapping_id, name, wrapper_type, *, mapping_version=None, description=None, ttl=None, inactivity_timeout=None, cpu_cores=None) -> Instance`

Create a new instance asynchronously. The instance starts in `PROVISIONING` state and
transitions to `LOADING` then `RUNNING`. Use `wait_until_running()` or `create_and_wait()`
to block until ready.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `mapping_id` | `int` | *required* | Source mapping ID |
| `name` | `str` | *required* | Human-readable instance name |
| `wrapper_type` | `str` | *required* | `"falkordb"` or `"ryugraph"` |
| `mapping_version` | `int \| None` | `None` | Pin to a specific mapping version |
| `description` | `str \| None` | `None` | Optional description |
| `ttl` | `int \| None` | `None` | Time-to-live in seconds |
| `inactivity_timeout` | `int \| None` | `None` | Auto-terminate after N seconds idle |
| `cpu_cores` | `int \| None` | `None` | CPU allocation override |

**Returns:** `Instance` object in `PROVISIONING` state.

```python
# Use the reference mapping from the provision step (cell 3)
instance = client.instances.create_and_wait(
    mapping_id=mapping_id,
    name="Customer-SHARES_ACCOUNT-analysis",
    wrapper_type="falkordb",
    description="Ad-hoc analysis of customer share accounts",
    ttl="PT30M",
)

print(f"ID:     {instance.id}")
print(f"Name:   {instance.name}")
print(f"Status: {instance.status}")
```

### `create_and_wait(mapping_id, name, wrapper_type, *, timeout=900, poll_interval=5, on_progress=None, ...) -> Instance`

Create an instance and block until it reaches `RUNNING` state. Accepts all the same
parameters as `create()` plus polling controls.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `timeout` | `int` | `900` | Max seconds to wait |
| `poll_interval` | `int` | `5` | Seconds between status checks |
| `on_progress` | `callable \| None` | `None` | Callback receiving `InstanceProgress` on each poll |

**Returns:** `Instance` in `RUNNING` state.

**Raises:** `TimeoutError` if the instance does not reach RUNNING within the timeout.

```python
# Use the mapping_id from the previous cell
instance = client.instances.create_and_wait(
    mapping_id=mapping_id,
    name="Customer-SHARES_ACCOUNT-wait-demo",
    wrapper_type="falkordb",
    ttl="PT30M",
    timeout=600,
    poll_interval=10,
    on_progress=lambda phase, completed, total: print(f"  {phase}: {completed}/{total}"),
)

print(f"\nReady! Instance {instance.id} is {instance.status}")
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Retrieving Instances</h2>
    <p class="nb-section__description">Get and list existing instances</p>
  </div>
</div>

### `get(instance_id) -> Instance`

Retrieve a single instance by ID.

| Parameter | Type | Description |
|-----------|------|-------------|
| `instance_id` | `int` | Instance ID |

**Returns:** `Instance` object.

**Raises:** `NotFoundError` if the instance does not exist.

```python
instance = client.instances.get(inst_id)

print(f"Name:        {instance.name}")
print(f"Status:      {instance.status}")
print(f"Wrapper:     {instance.wrapper_type}")
print(f"Created:     {instance.created_at}")
```

### `list(*, owner=None, status=None, search=None, offset=0, limit=50) -> PaginatedList[Instance]`

List instances with optional filters. Returns a `PaginatedList` that supports iteration
and provides `.total` for the full count.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `owner` | `str \| None` | `None` | Filter by owner username |
| `status` | `str \| None` | `None` | Filter by status (`RUNNING`, `STOPPED`, etc.) |
| `search` | `str \| None` | `None` | Free-text search on name/description |
| `offset` | `int` | `0` | Pagination offset |
| `limit` | `int` | `50` | Max results per page |

```python
running = client.instances.list(status="running", limit=5)

print(f"Total running instances: {running.total}\n")
for inst in running:
    print(f"  [{inst.id}] {inst.name} ({inst.wrapper_type})")
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Connecting &amp; Health</h2>
    <p class="nb-section__description">Work with running instances</p>
  </div>
</div>

### `connect(instance_id) -> InstanceConnection`

Open a query connection to a running instance. The returned `InstanceConnection`
provides `.query()`, `.call()`, and other data-access methods.

| Parameter | Type | Description |
|-----------|------|-------------|
| `instance_id` | `int` | ID of a RUNNING instance |

**Returns:** `InstanceConnection`

**Raises:** `InstanceNotRunningError` if the instance is not in RUNNING state.

```python
conn = client.instances.connect(inst_id)

result = conn.query("MATCH (c:Customer)-[:SHARES_ACCOUNT]->(a:Customer) RETURN c.id, a.id LIMIT 3")
for row in result:
    print(f"  {row['c.id']} -> {row['a.id']}")
```

### `wait_until_running(instance_id, *, timeout=300, poll_interval=5) -> Instance`

Block until an instance reaches `RUNNING` state. Useful after calling `create()` directly.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `instance_id` | `int` | *required* | Instance to wait for |
| `timeout` | `int` | `300` | Max seconds to wait |
| `poll_interval` | `int` | `5` | Seconds between polls |

**Returns:** `Instance` in `RUNNING` state.

```python
# Wait for a previously created instance
instance = client.instances.wait_until_running(inst_id, timeout=120)
print(f"{instance.name} is {instance.status}")
```

### `get_health(instance_id, *, timeout=5.0) -> dict`

Get detailed health information for a specific instance.

### `check_health(instance_id, *, timeout=5.0) -> bool`

Simple boolean health check -- returns `True` if the instance is healthy.

```python
# Detailed health
health = client.instances.get_health(inst_id)
print("Health details:")
for key, val in health.items():
    print(f"  {key}: {val}")

# Simple boolean check
is_healthy = client.instances.check_health(inst_id)
print(f"\nHealthy: {is_healthy}")
```

### `get_progress(instance_id) -> InstanceProgress`

Check loading progress for an instance that is being provisioned.

**Returns:** `InstanceProgress` with `.phase`, `.percent`, and `.message` attributes.

```python
progress = client.instances.get_progress(inst_id)
print(f"Phase:   {progress.phase}")
print(f"Percent: {progress.progress_percent}%")
print(f"Message: {progress.phase}")
```

<div class="nb-section">
  <span class="nb-section__number">5</span>
  <div>
    <h2 class="nb-section__title">Updating &amp; Lifecycle</h2>
    <p class="nb-section__description">Modify instances and manage TTL</p>
  </div>
</div>

### `update(instance_id, *, name=None, description=None) -> Instance`

Update mutable instance metadata.

### `set_lifecycle(instance_id, *, ttl=None, inactivity_timeout=None) -> Instance`

Adjust the TTL or inactivity timeout for a running instance.

### `extend_ttl(instance_id, hours=24) -> Instance`

Extend the time-to-live by the specified number of hours (default 24).

```python
# Update metadata
updated = client.instances.update(inst_id, description="Updated for Q1 analysis")
print(f"Description: {updated.description}")

# Extend TTL by 12 hours
extended = client.instances.extend_ttl(inst_id, hours=12)
print(f"New TTL expiry: {extended.expires_at}")

# Set lifecycle parameters
lifecycle = client.instances.set_lifecycle(inst_id, inactivity_timeout="PT30M")
print(f"Inactivity timeout: {lifecycle.inactivity_timeout}")
```

<div class="nb-section">
  <span class="nb-section__number">6</span>
  <div>
    <h2 class="nb-section__title">Termination</h2>
    <p class="nb-section__description">Clean up instances</p>
  </div>
</div>

### `terminate(instance_id) -> None`

Terminate a running instance and release its resources. This action is irreversible.

| Parameter | Type | Description |
|-----------|------|-------------|
| `instance_id` | `int` | Instance to terminate |

```python
client.instances.terminate(inst_id)
print("Instance terminated.")

# Verify it is gone from the running list
running = client.instances.list(status="running")
print(f"Running instances: {running.total}")
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li><code>create_and_wait()</code> is the easiest way to provision -- it blocks until the instance is ready</li>
    <li><code>connect()</code> returns an <code>InstanceConnection</code> for running queries</li>
    <li>Use <code>list(status="running")</code> to find active instances</li>
    <li><code>extend_ttl()</code> and <code>set_lifecycle()</code> let you manage instance lifetimes without recreation</li>
    <li>Always <code>terminate()</code> instances you no longer need to free cluster resources</li>
  </ul>
</div>
