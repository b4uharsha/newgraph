---
title: "Understanding Resources"
---

<div class="nb-header">
  <span class="nb-header__type">Tutorial</span>
  <h1 class="nb-header__title">Understanding Resources</h1>
  <p class="nb-header__subtitle">Learn the Mapping → Instance resource model</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">25 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--beginner">
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
      </span>
      Beginner
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">Resources</span><span class="nb-header__tag">Mapping</span><span class="nb-header__tag">Instance</span><span class="nb-header__tag">Lifecycle</span></div>
</div>

<div class="nb-objectives">
  <h3 class="nb-objectives__title">What You'll Learn</h3>
  <ul class="nb-objectives__list">
    <li><strong>Resource Model</strong> - Understand the Mapping → Instance flow</li>
    <li><strong>Mappings</strong> - Browse and inspect graph schema definitions</li>
    <li><strong>Instances</strong> - Create, connect, and manage graph databases</li>
    <li><strong>Lifecycle</strong> - Extend TTL and terminate instances</li>
  </ul>
</div>

<div class="nb-section">
  <span class="nb-section__number">1</span>
  <div>
    <h2 class="nb-section__title">Setup</h2>
    <p class="nb-section__description">Connect to the Graph OLAP platform</p>
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
client = analyst

print(f"Connected to: {client._config.api_url}")
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Working with Mappings</h2>
    <p class="nb-section__description">Browse available graph schema definitions</p>
  </div>
</div>

```python
# List all available mappings
mappings = client.mappings.list()
print(f"Available mappings: {len(mappings)}")
for m in mappings:
    print(f"  [{m.id}] {m.name}")

# Find the tutorial mapping by name (not by index — parallel CI has multiple)
tutorial_mappings = [m for m in mappings if "tutorial-customer-graph" in m.name]
mapping = tutorial_mappings[0] if tutorial_mappings else mappings[0]
mapping_detail = client.mappings.get(mapping.id)
print(f"\nMapping detail: {mapping_detail.name} (id={mapping_detail.id})")
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Creating Instances</h2>
    <p class="nb-section__description">Deploy a queryable graph database from a mapping</p>
  </div>
</div>

```python
from graph_olap_schemas import WrapperType

# Create an instance directly from the tutorial mapping
instance = client.instances.create_and_wait(
    mapping_id=mapping.id,
    name="resources-demo",
    wrapper_type=WrapperType.RYUGRAPH,
    ttl="PT1H",
)
print(f"Instance: {instance.name} (status={instance.status})")

# Connect to OUR instance and query it to prove it works
demo_conn = client.instances.connect(instance.id)
result = demo_conn.query("MATCH (c:Customer) RETURN c.id AS name LIMIT 3")
result.show()
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Instance Lifecycle</h2>
    <p class="nb-section__description">Extend TTL and terminate instances</p>
  </div>
</div>

```python
# Extend instance TTL to keep it running longer
client.instances.extend_ttl(instance.id, hours=24)
print(f"Extended TTL for instance {instance.name} by 24 hours")
```

```python
# Clean up the demo instance we created
try:
    client.instances.terminate(instance.id)
    print(f"Terminated instance: {instance.name}")
except Exception as e:
    print(f"Cleanup: {e}")
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li>Mappings define the graph schema (nodes, edges, properties from warehouse tables)</li>
    <li>Instances are created directly from mappings using <code>create_and_wait()</code></li>
    <li>Use <code>extend_ttl()</code> to keep instances running and <code>terminate()</code> to free resources</li>
    <li>Resource lifecycle: pending → running → terminated</li>
  </ul>
</div>
