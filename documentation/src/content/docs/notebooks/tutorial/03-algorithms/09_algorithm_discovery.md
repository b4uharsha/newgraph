---
title: "Algorithm Discovery"
---

<div class="nb-header">
  <span class="nb-header__type">Tutorial</span>
  <h1 class="nb-header__title">Algorithm Discovery</h1>
  <p class="nb-header__subtitle">Find, inspect, and run any algorithm by name</p>
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
  <div class="nb-header__tags"><span class="nb-header__tag">Algorithms</span><span class="nb-header__tag">Discovery</span><span class="nb-header__tag">NetworkX</span><span class="nb-header__tag">Execution</span></div>
</div>

<div class="nb-objectives">
  <h3 class="nb-objectives__title">What You'll Learn</h3>
  <ul class="nb-objectives__list">
    <li><strong>List native algorithms</strong> - Browse all available algorithms and filter by category</li>
    <li><strong>List NetworkX algorithms</strong> - Discover additional algorithms from the NetworkX library</li>
    <li><strong>Inspect parameters</strong> - Use <code>algorithm_info()</code> to see parameter names, types, and descriptions</li>
    <li><strong>Run by name</strong> - Execute any algorithm via <code>run()</code> when no convenience method exists</li>
    <li><strong>Control execution</strong> - Choose synchronous (<code>wait=True</code>) vs asynchronous (<code>wait=False</code>) mode</li>
    <li><strong>Handle lock conflicts</strong> - Check locks and handle <code>ResourceLockedError</code> during concurrent execution</li>
  </ul>
</div>

<div class="nb-section">
  <span class="nb-section__number">1</span>
  <div>
    <h2 class="nb-section__title">Setup</h2>
    <p class="nb-section__description">Connect to the platform and provision a tutorial graph</p>
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

print(f"Connected to {conn.name} | {conn.query_scalar('MATCH (n) RETURN count(n)')} nodes")
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Discovering Native Algorithms</h2>
    <p class="nb-section__description">List and filter the built-in algorithm catalogue</p>
  </div>
</div>

```python
algos = conn.algo.algorithms()
print(f"Available native algorithms: {len(algos)}\n")
for algo in algos:
    print(f"  {algo['name']:25s} {algo['category']}")
```

```python
centrality = conn.algo.algorithms(category="centrality")
print(f"Centrality algorithms: {len(centrality)}")
for algo in centrality:
    print(f"  {algo['name']}: {algo.get('description', '')}")
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Inspecting Algorithm Parameters</h2>
    <p class="nb-section__description">Use <code>algorithm_info()</code> to understand inputs before running</p>
  </div>
</div>

```python
info = conn.algo.algorithm_info("pagerank")
print(f"Algorithm: {info['name']}")
print(f"Category:  {info['category']}")
print(f"\nParameters:")
for p in info.get("parameters", []):
    print(f"  {p['name']:20s} {p.get('type', ''):10s} {p.get('description', '')}")
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Discovering NetworkX Algorithms</h2>
    <p class="nb-section__description">Browse the extended algorithm library powered by NetworkX</p>
  </div>
</div>

```python
nx_centrality = conn.networkx.algorithms(category="centrality")
print(f"NetworkX centrality algorithms: {len(nx_centrality)}\n")
for algo in nx_centrality:
    print(f"  {algo['name']:30s} {algo.get('description', '')[:50]}")
```

```python
info = conn.networkx.algorithm_info("katz_centrality")
print(f"Algorithm: {info['name']}")
print(f"\nParameters:")
for p in info.get("parameters", []):
    print(f"  {p['name']:20s} {p.get('type', ''):10s} {p.get('description', '')}")
```

<div class="nb-section">
  <span class="nb-section__number">5</span>
  <div>
    <h2 class="nb-section__title">Running Algorithms with <code>run()</code></h2>
    <p class="nb-section__description">Execute any algorithm by name -- no convenience method needed</p>
  </div>
</div>

```python
# Run Louvain community detection via generic run()
result = conn.algo.run(
    "louvain",
    node_label="Customer",
    edge_type="SHARES_ACCOUNT",
    property_name="discovery_community",
    params={"resolution": 1.5},
)

print(f"Algorithm:    {result.algorithm}")
print(f"Status:       {result.status}")
print(f"Execution ID: {result.execution_id}")
print(f"Duration:     {result.duration_ms}ms")
print(f"Nodes updated: {result.nodes_updated}")
```

```python
# Run Katz centrality (no convenience method for this one)
result = conn.networkx.run(
    "katz_centrality",
    node_label="Customer",
    property_name="katz_score",
    params={"alpha": 0.1},
)

print(f"Algorithm:    {result.algorithm}")
print(f"Type:         {result.algorithm_type}")
print(f"Status:       {result.status}")

# Query results
top = conn.query(
    "MATCH (c:Customer) WHERE c.katz_score IS NOT NULL "
    "RETURN c.id, c.katz_score ORDER BY c.katz_score DESC LIMIT 5"
)
for row in top:
    print(f"  {row['c.id']:20s} {row['c.katz_score']:.4f}")
```

<div class="nb-section">
  <span class="nb-section__number">6</span>
  <div>
    <h2 class="nb-section__title">Synchronous vs Asynchronous Execution</h2>
    <p class="nb-section__description">Choose blocking or non-blocking algorithm runs</p>
  </div>
</div>

```python
# Asynchronous: returns immediately
exec_async = conn.algo.run(
    "pagerank",
    node_label="Customer",
    edge_type="SHARES_ACCOUNT",
    property_name="pr_async",
    wait=False,  # Don't block
)
print(f"Submitted:    {exec_async.execution_id}")
print(f"Status:       {exec_async.status}")  # "pending" or "running"

# In practice, you would poll or wait. For this tutorial,
# the algorithm completes quickly on our small graph.
import time
time.sleep(2)

# Re-run with wait=True to verify it completed
exec_sync = conn.algo.run(
    "pagerank",
    node_label="Customer",
    edge_type="SHARES_ACCOUNT",
    property_name="pr_sync",
    wait=True,  # Block until done
)
print(f"\nSynchronous:  {exec_sync.status}")
print(f"Duration:     {exec_sync.duration_ms}ms")
```

<div class="nb-section">
  <span class="nb-section__number">7</span>
  <div>
    <h2 class="nb-section__title">Handling Lock Conflicts</h2>
    <p class="nb-section__description">Check instance locks before running algorithms</p>
  </div>
</div>

```python
from graph_olap.exceptions import ResourceLockedError

# Check lock before running
lock = conn.get_lock()
if lock.locked:
    print(f"Instance locked by {lock.holder_name}, running {lock.algorithm}")
else:
    print("Instance is unlocked — safe to run algorithms")

# Handle lock conflicts gracefully
try:
    result = conn.algo.run(
        "wcc",
        node_label="Customer",
        edge_type="SHARES_ACCOUNT",
        property_name="wcc_discovery",
    )
    print(f"WCC completed: {result.status}")
except ResourceLockedError as e:
    print(f"Lock conflict: {e}")
    print("Wait for the current algorithm to complete, then retry")
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li><code>algorithms()</code> lists all available algorithms; filter by <code>category</code> to narrow results</li>
    <li><code>algorithm_info()</code> reveals parameter names, types, and descriptions before you run</li>
    <li><code>run()</code> executes any algorithm by name -- use it when no convenience method exists</li>
    <li>Use <code>wait=True</code> (default) for synchronous execution, <code>wait=False</code> for async</li>
    <li>Check <code>conn.get_lock()</code> before running to avoid <code>ResourceLockedError</code></li>
    <li><code>AlgorithmExecution</code> provides metadata: <code>execution_id</code>, <code>duration_ms</code>, <code>nodes_updated</code></li>
  </ul>
</div>
