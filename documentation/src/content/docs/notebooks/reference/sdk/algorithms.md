---
title: "Algorithms"
---

<div class="nb-header">
  <span class="nb-header__type">Reference</span>
  <h1 class="nb-header__title">Algorithms</h1>
  <p class="nb-header__subtitle">Native and NetworkX graph algorithms</p>
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
  <div class="nb-header__tags"><span class="nb-header__tag">Reference</span><span class="nb-header__tag">API</span><span class="nb-header__tag">Algorithms</span></div>
</div>

## Algorithms

The SDK provides two algorithm managers accessible from any
`InstanceConnection`:

| Manager | Access | Engine | Algorithms |
|---------|--------|--------|------------|
| `AlgorithmManager` | `conn.algo` | Native Ryugraph | PageRank, WCC, SCC, Louvain, K-Core, Label Propagation, Triangle Count, Shortest Path |
| `NetworkXManager` | `conn.networkx` | NetworkX bridge | 500+ algorithms -- degree, betweenness, closeness, eigenvector centrality, clustering, and more |

Both managers support three usage patterns:

1. **Discovery** -- list and inspect available algorithms
2. **Convenience methods** -- typed, documented methods for common algorithms
3. **Generic `run()`** -- call any algorithm by name with arbitrary parameters

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
    <h2 class="nb-section__title">Algorithm Discovery</h2>
    <p class="nb-section__description">List and inspect available algorithms</p>
  </div>
</div>

### `conn.algo.algorithms(category=None) -> list[dict]`

List available native algorithms, optionally filtered by category.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `category` | `str \| None` | `None` | Filter by category (`centrality`, `community`, `path`, etc.) |

**Returns:** List of dicts with `name`, `category`, `description`.

```python
# List all native algorithms
algos = conn.algo.algorithms()
for algo in algos:
    print(f"{algo['name']:25s} {algo['category']}")

# Filter by category
centrality = conn.algo.algorithms(category="centrality")
print(f"\nCentrality algorithms: {len(centrality)}")
```

### `conn.algo.algorithm_info(algorithm) -> dict`

Get detailed information for a specific algorithm, including its parameters.

| Parameter | Type | Description |
|-----------|------|-------------|
| `algorithm` | `str` | Algorithm name |

**Returns:** Dict with `name`, `category`, `description`, `parameters`.

```python
# Inspect an algorithm's parameters
info = conn.algo.algorithm_info("pagerank")
print(f"Algorithm: {info['name']}")
print(f"Category:  {info['category']}")
print(f"\nParameters:")
for p in info.get("parameters", []):
    print(f"  {p['name']:20s} {p.get('type', ''):10s} {p.get('description', '')}")
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Native Convenience Methods</h2>
    <p class="nb-section__description">Typed methods via conn.algo</p>
  </div>
</div>

### Pattern 1: Convenience methods

Each convenience method wraps `conn.algo.run()` with typed parameters and
sensible defaults. Results are written to a node property.

### `conn.algo.pagerank(node_label, property_name, edge_type=None, *, damping=0.85, max_iterations=100, tolerance=1e-6, timeout=300, wait=True) -> AlgorithmExecution`

Run PageRank centrality. The damping factor controls the probability of
following an edge vs. jumping to a random node.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `node_label` | `str` | *required* | Target node label |
| `property_name` | `str` | *required* | Property to store the PageRank score |
| `edge_type` | `str \| None` | `None` | Relationship type to traverse |
| `damping` | `float` | `0.85` | Damping factor |
| `max_iterations` | `int` | `100` | Maximum iterations |
| `tolerance` | `float` | `1e-6` | Convergence tolerance |
| `timeout` | `int` | `300` | Max execution time in seconds |
| `wait` | `bool` | `True` | Block until completion |

**Returns:** `AlgorithmExecution` with `status`, `execution_id`, and result metadata.

```python
# Run PageRank on Customer nodes
result = conn.algo.pagerank(
    node_label="Customer",
    property_name="pr_score",
    edge_type="SHARES_ACCOUNT",
    damping=0.85,
    max_iterations=100,
)

print(f"Status:       {result.status}")
print(f"Execution ID: {result.execution_id}")

# Query the results
top = conn.query(
    "MATCH (c:Customer) WHERE c.pr_score IS NOT NULL "
    "RETURN c.id, c.pr_score ORDER BY c.pr_score DESC LIMIT 5"
)
for row in top:
    print(f"  {row['c.id']:20s} {row['c.pr_score']:.6f}")
```

### Other native convenience methods

All convenience methods follow the same signature pattern:
`(node_label, property_name, edge_type=None, *, <algo-specific params>, timeout=300, wait=True)`.

| Method | Algorithm | Key parameters |
|--------|-----------|----------------|
| `conn.algo.connected_components(...)` | Weakly Connected Components | -- |
| `conn.algo.scc(...)` | Strongly Connected Components (Tarjan) | -- |
| `conn.algo.scc_kosaraju(...)` | Strongly Connected Components (Kosaraju) | -- |
| `conn.algo.louvain(...)` | Louvain community detection | `resolution=1.0` |
| `conn.algo.kcore(...)` | K-Core decomposition | -- |
| `conn.algo.label_propagation(...)` | Label Propagation communities | `max_iterations=100` |
| `conn.algo.triangle_count(...)` | Triangle counting | -- |

### `conn.algo.shortest_path(source_id, target_id, *, relationship_types=None, max_depth=None, timeout=60) -> AlgorithmExecution`

`shortest_path` differs from the others: it takes source and target node IDs
and returns the path in the result rather than writing to a property.

```python
# Community detection with Louvain
louvain_result = conn.algo.louvain(
    node_label="Customer",
    edge_type="SHARES_ACCOUNT",
    property_name="community_id",
    resolution=1.0,
)
print(f"Louvain: {louvain_result.status}")

# Weakly Connected Components
wcc_result = conn.algo.connected_components(
    node_label="Customer",
    edge_type="SHARES_ACCOUNT",
    property_name="wcc_id",
)
print(f"WCC:     {wcc_result.status}")
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">NetworkX Methods</h2>
    <p class="nb-section__description">500+ algorithms via conn.networkx</p>
  </div>
</div>

### Pattern 2: NetworkX bridge

The `NetworkXManager` provides access to the full NetworkX algorithm library.
Discovery works identically to native algorithms.

### `conn.networkx.algorithms(category=None) -> list[dict]`

List available NetworkX algorithms.

### `conn.networkx.algorithm_info(algorithm) -> dict`

Get details for a specific NetworkX algorithm.

```python
# List NetworkX centrality algorithms
nx_centrality = conn.networkx.algorithms(category="centrality")
for algo in nx_centrality:
    print(f"{algo['name']:30s} {algo.get('description', '')[:60]}")
```

### `conn.networkx.degree_centrality(node_label, property_name, **kwargs) -> AlgorithmExecution`

Calculate degree centrality for each node. Degree centrality is the fraction
of nodes that a given node is connected to.

| Parameter | Type | Description |
|-----------|------|-------------|
| `node_label` | `str` | Target node label |
| `property_name` | `str` | Property to store result |
| `**kwargs` | | Forwarded to `run()` (`timeout`, `wait`) |

```python
# Degree centrality via NetworkX
result = conn.networkx.degree_centrality(
    node_label="Customer",
    property_name="degree_cent",
)

print(f"Status: {result.status}")

# Query results
top = conn.query(
    "MATCH (c:Customer) WHERE c.degree_cent IS NOT NULL "
    "RETURN c.id, c.degree_cent ORDER BY c.degree_cent DESC LIMIT 5"
)
for row in top:
    print(f"  {row['c.id']:20s} {row['c.degree_cent']:.4f}")
```

### Other NetworkX convenience methods

| Method | Algorithm | Key parameters |
|--------|-----------|----------------|
| `conn.networkx.betweenness_centrality(...)` | Betweenness centrality | `k=None` (sample size) |
| `conn.networkx.closeness_centrality(...)` | Closeness centrality | -- |
| `conn.networkx.eigenvector_centrality(...)` | Eigenvector centrality | `max_iter=100` |
| `conn.networkx.clustering_coefficient(...)` | Clustering coefficient | -- |

All accept `(node_label, property_name, **kwargs)` and return `AlgorithmExecution`.

<div class="nb-section">
  <span class="nb-section__number">5</span>
  <div>
    <h2 class="nb-section__title">Generic Run Method</h2>
    <p class="nb-section__description">Call any algorithm by name</p>
  </div>
</div>

### Pattern 3: Generic `run()`

When a convenience method does not exist for the algorithm you need, use
`run()` to call any algorithm by name with arbitrary parameters.

### `conn.algo.run(algorithm, node_label=None, property_name=None, edge_type=None, *, params=None, timeout=300, wait=True) -> AlgorithmExecution`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `algorithm` | `str` | *required* | Algorithm name (e.g. `"pagerank"`, `"wcc"`, `"louvain"`) |
| `node_label` | `str \| None` | `None` | Target node label |
| `property_name` | `str \| None` | `None` | Property to store result |
| `edge_type` | `str \| None` | `None` | Relationship type to traverse |
| `params` | `dict \| None` | `None` | Algorithm-specific parameters |
| `timeout` | `int` | `300` | Max execution time in seconds |
| `wait` | `bool` | `True` | Block until completion |

### `conn.networkx.run(algorithm, node_label=None, property_name=None, *, params=None, timeout=300, wait=True) -> AlgorithmExecution`

Same interface for NetworkX algorithms (no `edge_type` parameter).

```python
# Native: run Louvain with custom resolution via generic method
exec1 = conn.algo.run(
    "louvain",
    node_label="Customer",
    edge_type="SHARES_ACCOUNT",
    property_name="community_hi_res",
    params={"resolution": 2.0},
)
print(f"Native Louvain: {exec1.status}")

# NetworkX: run Katz centrality (no convenience method exists)
exec2 = conn.networkx.run(
    "katz_centrality",
    node_label="Customer",
    property_name="katz_score",
    params={"alpha": 0.1},
)
print(f"NetworkX Katz:  {exec2.status}")
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li><strong>Pattern 1 -- Convenience methods</strong> (<code>conn.algo.pagerank()</code>) provide typed parameters and sensible defaults for common algorithms</li>
    <li><strong>Pattern 2 -- NetworkX bridge</strong> (<code>conn.networkx.degree_centrality()</code>) gives access to 500+ algorithms from the NetworkX ecosystem</li>
    <li><strong>Pattern 3 -- Generic <code>run()</code></strong> calls any algorithm by name with arbitrary parameters when no convenience method exists</li>
    <li><code>algorithms()</code> and <code>algorithm_info()</code> let you discover what is available and inspect parameter schemas at runtime</li>
    <li>All algorithm results are written to node properties and can be queried with Cypher immediately after execution</li>
  </ul>
</div>
