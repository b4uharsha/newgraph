---
title: "Getting Started with Graph OLAP SDK"
---

<div class="nb-header">
  <span class="nb-header__type">Tutorial</span>
  <h1 class="nb-header__title">Getting Started with Graph OLAP SDK</h1>
  <p class="nb-header__subtitle">Install the SDK, connect to the platform, and run your first query</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">15 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--beginner">
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
      </span>
      Beginner
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">SDK</span><span class="nb-header__tag">Setup</span><span class="nb-header__tag">Quick Start</span></div>
</div>

<div class="nb-objectives">
  <h3 class="nb-objectives__title">What You'll Learn</h3>
  <ul class="nb-objectives__list">
    <li><strong>Installation</strong> - Install graph-olap SDK via pip</li>
    <li><strong>Connection</strong> - Connect to the Graph OLAP platform</li>
    <li><strong>First Query</strong> - Execute your first Cypher query</li>
    <li><strong>Quick Start</strong> - Use the quick_start() convenience method</li>
  </ul>
</div>

<div class="nb-section">
  <span class="nb-section__number">1</span>
  <div>
    <h2 class="nb-section__title">Installation</h2>
    <p class="nb-section__description">Install the SDK package</p>
  </div>
</div>

```python
# Install the SDK
# pip install graph-olap

# Verify installation
import graph_olap
print(f"SDK Version: {graph_olap.__version__}")
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Connecting to the Platform</h2>
    <p class="nb-section__description">Create a client and authenticate</p>
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

print(f"Connected! Graph has {conn.query_scalar('MATCH (n) RETURN count(n)')} nodes.")
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Your First Query</h2>
    <p class="nb-section__description">Run a Cypher query and inspect the results</p>
  </div>
</div>

```python
# Query the HSBC customer graph
result = conn.query("MATCH (c:Customer) RETURN c.id AS name, c.bk_sectr AS sector LIMIT 5")

result.show()
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Using Quick Start</h2>
    <p class="nb-section__description">One-line setup with quick_start()</p>
  </div>
</div>

```python
from graph_olap_schemas import WrapperType

# quick_start() is a convenience method that combines mapping lookup + instance creation + connect
# conn = client.quick_start(mapping_id=mapping.id, wrapper_type=WrapperType.RYUGRAPH)

# Since we're already connected, let's count nodes
total = conn.query_scalar("MATCH (n) RETURN count(n)")
print(f"Total nodes in graph: {total}")
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li>SDK installed via <code>pip install graph-olap</code></li>
    <li>Use <code>GraphOLAPClient.from_env()</code> to connect to the control plane</li>
    <li>Use <code>client.mappings.list()</code> / <code>client.mappings.create()</code> to manage graph schemas</li>
    <li>Use <code>client.instances.create_and_wait()</code> to deploy a queryable graph database</li>
    <li>Use <code>client.instances.connect()</code> to get a connection for running Cypher queries</li>
    <li><code>quick_start(mapping_id, wrapper_type)</code> combines instance creation and connection in one call</li>
  </ul>
</div>
