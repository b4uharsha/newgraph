---
title: "Appendix D: Algorithm Reference"
scope: hsbc
---

# Appendix D: Algorithm Reference

This appendix provides a comprehensive reference for all graph algorithms available through the Graph OLAP SDK. Algorithms are organized by category and include both native (Ryugraph and FalkorDB) and NetworkX implementations.

> **Note: Algorithm Availability by Backend**
>
> - **Native Algorithms**: Available on both Ryugraph (`conn.algo.*`) and FalkorDB (`CALL algo.*()`) with different syntax
> - **NetworkX Algorithms**: Ryugraph ONLY - 100+ algorithms via `conn.networkx.*`

## Overview

The SDK provides algorithm interfaces that vary by backend:

- **Ryugraph Native Algorithms** (`conn.algo`): High-performance algorithms running directly in the Ryugraph database engine
- **FalkorDB Native Algorithms** (`CALL algo.*()`): Native Cypher procedures for graph analytics
- **NetworkX Algorithms** (`conn.networkx`): Access to 500+ NetworkX algorithms via a bridge interface (Ryugraph only)

Both interfaces support:
- Dynamic algorithm discovery via `.algorithms()` and `.algorithm_info()`
- Automatic result writeback to node properties
- Execution status tracking and timeout handling

## Algorithm Categories

| Category | Description | Examples |
|----------|-------------|----------|
| `centrality` | Node importance measures | PageRank, Betweenness, Closeness |
| `community` | Cluster/group detection | Louvain, WCC, SCC, Label Propagation |
| `pathfinding` | Path analysis | Shortest Path |
| `clustering` | Structural analysis | K-Core, Triangle Count |
| `similarity` | Node similarity measures | Jaccard, Cosine |
| `traversal` | Graph traversal | BFS, DFS |
| `link_prediction` | Predict new edges | Common Neighbors, Adamic-Adar |

## Native Algorithms Reference

Native algorithms run directly in the Ryugraph database engine for optimal performance.

### PageRank

**Category:** Centrality

**Description:** Computes PageRank centrality scores measuring node importance based on incoming links.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `node_label` | string | Yes | - | Target node label |
| `property_name` | string | Yes | - | Property to store results |
| `edge_type` | string | Yes | - | Relationship type to traverse |
| `damping` | float | No | 0.85 | Damping factor (0 to 1) |
| `max_iterations` | int | No | 100 | Maximum iterations |
| `tolerance` | float | No | 1e-6 | Convergence tolerance |
| `timeout` | int | No | 300 | Timeout in seconds |

**Result Property:** Float between 0 and 1

**Example:**
```python
# Using convenience method
result = conn.algo.pagerank(
    node_label="Customer",
    property_name="pr_score",
    edge_type="KNOWS",
    damping=0.85,
    max_iterations=100
)

# Using generic method
result = conn.algo.run(
    "pagerank",
    node_label="Customer",
    property_name="pr_score",
    edge_type="KNOWS",
    params={
        "damping_factor": 0.85,
        "max_iterations": 100,
        "tolerance": 1e-6
    }
)

print(f"Nodes updated: {result.nodes_updated}")
print(f"Duration: {result.duration_ms}ms")

# Query results
top_nodes = conn.query("""
    MATCH (c:Customer)
    WHERE c.pr_score IS NOT NULL
    RETURN c.name, c.pr_score
    ORDER BY c.pr_score DESC
    LIMIT 10
""")
```

---

### Weakly Connected Components (WCC)

**Category:** Community

**Description:** Finds connected components treating all edges as undirected. Each node is assigned a component ID.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `node_label` | string | Yes | - | Target node label |
| `property_name` | string | Yes | - | Property to store component ID |
| `edge_type` | string | Yes | - | Relationship type to traverse |
| `timeout` | int | No | 300 | Timeout in seconds |

**Result Property:** Integer (component ID)

**Example:**
```python
result = conn.algo.connected_components(
    node_label="Customer",
    property_name="component_id",
    edge_type="KNOWS"
)

print(f"Found {result.extra.get('components', 'N/A')} components")

# Find largest components
components = conn.query("""
    MATCH (c:Customer)
    WHERE c.component_id IS NOT NULL
    RETURN c.component_id, count(*) as size
    ORDER BY size DESC
    LIMIT 10
""")
```

---

### Strongly Connected Components (SCC)

**Category:** Community

**Description:** Finds strongly connected components where every pair of vertices is mutually reachable (respecting edge direction).

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `node_label` | string | Yes | - | Target node label |
| `property_name` | string | Yes | - | Property to store component ID |
| `edge_type` | string | Yes | - | Relationship type to traverse |
| `max_iterations` | int | No | 100 | Maximum iterations |
| `timeout` | int | No | 300 | Timeout in seconds |

**Result Property:** Integer (component ID)

**Example:**
```python
result = conn.algo.scc(
    node_label="Customer",
    property_name="scc_id",
    edge_type="REFERRED"
)

print(f"Found {result.extra.get('components', 'N/A')} strongly connected components")
```

---

### SCC Kosaraju

**Category:** Community

**Description:** Finds strongly connected components using Kosaraju's DFS-based algorithm. Recommended for very sparse graphs or graphs with high diameter.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `node_label` | string | Yes | - | Target node label |
| `property_name` | string | Yes | - | Property to store component ID |
| `edge_type` | string | Yes | - | Relationship type to traverse |
| `timeout` | int | No | 300 | Timeout in seconds |

**Result Property:** Integer (component ID)

**Example:**
```python
result = conn.algo.scc_kosaraju(
    node_label="Customer",
    property_name="scc_ko_id",
    edge_type="REFERRED"
)
```

---

### Louvain Community Detection

**Category:** Community

**Description:** Detects communities by maximizing modularity score using hierarchical clustering. Treats edges as undirected.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `node_label` | string | Yes | - | Target node label |
| `property_name` | string | Yes | - | Property to store community ID |
| `edge_type` | string | Yes | - | Relationship type to traverse |
| `resolution` | float | No | 1.0 | Resolution parameter (higher = more communities) |
| `timeout` | int | No | 300 | Timeout in seconds |

**Result Property:** Integer (community ID)

**Example:**
```python
result = conn.algo.louvain(
    node_label="Customer",
    property_name="community",
    edge_type="KNOWS",
    resolution=1.0
)

print(f"Found {result.extra.get('communities', 'N/A')} communities")

# Analyze community distribution
communities = conn.query("""
    MATCH (c:Customer)
    WHERE c.community IS NOT NULL
    RETURN c.community, count(*) as size
    ORDER BY size DESC
""")
```

---

### K-Core Decomposition

**Category:** Clustering

**Description:** Computes the k-core number for each node - the largest value k such that the node belongs to a k-core subgraph (where every node has degree at least k).

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `node_label` | string | Yes | - | Target node label |
| `property_name` | string | Yes | - | Property to store k-core degree |
| `edge_type` | string | Yes | - | Relationship type to traverse |
| `timeout` | int | No | 300 | Timeout in seconds |

**Result Property:** Integer (k-core degree)

**Example:**
```python
result = conn.algo.kcore(
    node_label="Customer",
    property_name="kcore_degree",
    edge_type="KNOWS"
)

print(f"Max k-core: {result.extra.get('max_k', 'N/A')}")

# Find highly connected core
core_nodes = conn.query("""
    MATCH (c:Customer)
    WHERE c.kcore_degree >= 5
    RETURN c.name, c.kcore_degree
    ORDER BY c.kcore_degree DESC
""")
```

---

### Label Propagation

**Category:** Community

**Description:** Detects communities by iteratively propagating labels from neighbors. Each node adopts the most common label among its neighbors.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `node_label` | string | Yes | - | Target node label |
| `property_name` | string | Yes | - | Property to store community label |
| `edge_type` | string | Yes | - | Relationship type to traverse |
| `max_iterations` | int | No | 100 | Maximum iterations |
| `timeout` | int | No | 300 | Timeout in seconds |

**Result Property:** Integer (community label)

**Example:**
```python
result = conn.algo.label_propagation(
    node_label="Customer",
    property_name="lp_community",
    edge_type="KNOWS",
    max_iterations=100
)
```

---

### Triangle Count

**Category:** Clustering

**Description:** Counts the number of triangles each node participates in. A triangle is a set of three mutually connected nodes.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `node_label` | string | Yes | - | Target node label |
| `property_name` | string | Yes | - | Property to store triangle count |
| `edge_type` | string | Yes | - | Relationship type to traverse |
| `timeout` | int | No | 300 | Timeout in seconds |

**Result Property:** Integer (triangle count)

**Example:**
```python
result = conn.algo.triangle_count(
    node_label="Customer",
    property_name="triangles",
    edge_type="KNOWS"
)

# Find nodes in tightly connected neighborhoods
clustered = conn.query("""
    MATCH (c:Customer)
    WHERE c.triangles > 10
    RETURN c.name, c.triangles
    ORDER BY c.triangles DESC
""")
```

---

### Shortest Path

**Category:** Pathfinding

**Description:** Finds the shortest path between two specific nodes.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `source_id` | any | Yes | - | Source node ID |
| `target_id` | any | Yes | - | Target node ID |
| `relationship_types` | list | No | None | Filter by relationship types |
| `max_depth` | int | No | None | Maximum path length |
| `timeout` | int | No | 60 | Timeout in seconds |

**Result:** Path information in execution result

**Example:**
```python
result = conn.algo.shortest_path(
    source_id="node_123",
    target_id="node_456",
    relationship_types=["KNOWS", "WORKS_WITH"],
    max_depth=6
)

if result.result:
    path = result.result.get("path", [])
    print(f"Path length: {len(path)}")
    print(f"Path: {' -> '.join(str(n) for n in path)}")
```

---

## NetworkX Algorithms Reference

NetworkX algorithms are available through the `conn.networkx` interface. The SDK provides convenience methods for common algorithms and a generic `run()` method for any of 500+ NetworkX algorithms.

### Degree Centrality

**Category:** Centrality

**Description:** Measures node importance by counting connections (normalized by maximum possible degree).

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `node_label` | string | Yes | - | Target node label |
| `property_name` | string | Yes | - | Property to store result |
| `timeout` | int | No | 300 | Timeout in seconds |

**Result Property:** Float between 0 and 1

**Example:**
```python
result = conn.networkx.degree_centrality(
    node_label="Customer",
    property_name="degree_cent"
)
```

---

### Betweenness Centrality

**Category:** Centrality

**Description:** Measures how often a node lies on shortest paths between other nodes. High betweenness nodes are important bridges.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `node_label` | string | Yes | - | Target node label |
| `property_name` | string | Yes | - | Property to store result |
| `k` | int | No | None | Number of sample nodes for approximation |
| `timeout` | int | No | 300 | Timeout in seconds |

**Result Property:** Float (normalized betweenness)

**Example:**
```python
# Exact computation
result = conn.networkx.betweenness_centrality(
    node_label="Customer",
    property_name="betweenness"
)

# Approximate (faster for large graphs)
result = conn.networkx.betweenness_centrality(
    node_label="Customer",
    property_name="betweenness_approx",
    k=100  # Sample 100 nodes
)
```

---

### Closeness Centrality

**Category:** Centrality

**Description:** Measures how close a node is to all other nodes (inverse of average shortest path length).

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `node_label` | string | Yes | - | Target node label |
| `property_name` | string | Yes | - | Property to store result |
| `timeout` | int | No | 300 | Timeout in seconds |

**Result Property:** Float between 0 and 1

**Example:**
```python
result = conn.networkx.closeness_centrality(
    node_label="Customer",
    property_name="closeness"
)
```

---

### Eigenvector Centrality

**Category:** Centrality

**Description:** Measures node influence based on the influence of neighbors. High scores indicate connections to other influential nodes.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `node_label` | string | Yes | - | Target node label |
| `property_name` | string | Yes | - | Property to store result |
| `max_iter` | int | No | 100 | Maximum iterations |
| `timeout` | int | No | 300 | Timeout in seconds |

**Result Property:** Float (eigenvector centrality score)

**Example:**
```python
result = conn.networkx.eigenvector_centrality(
    node_label="Customer",
    property_name="eigenvector",
    max_iter=200
)
```

---

### Clustering Coefficient

**Category:** Clustering

**Description:** Measures the degree to which nodes cluster together (ratio of actual triangles to possible triangles).

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `node_label` | string | Yes | - | Target node label |
| `property_name` | string | Yes | - | Property to store result |
| `timeout` | int | No | 300 | Timeout in seconds |

**Result Property:** Float between 0 and 1

**Example:**
```python
result = conn.networkx.clustering_coefficient(
    node_label="Customer",
    property_name="clustering"
)
```

---

### Generic NetworkX Algorithm Execution

Use the `run()` method to execute any NetworkX algorithm:

```python
# List available algorithms
algos = conn.networkx.algorithms(category="centrality")
for algo in algos:
    print(f"{algo['name']}: {algo['description']}")

# Get algorithm info
info = conn.networkx.algorithm_info("katz_centrality")
print(f"Parameters: {info['parameters']}")

# Run algorithm
result = conn.networkx.run(
    "katz_centrality",
    node_label="Customer",
    property_name="katz",
    params={"alpha": 0.1, "beta": 1.0}
)
```

## Algorithm Discovery

### List Available Algorithms

```python
# List all native algorithms
native_algos = conn.algo.algorithms()
print(f"Available native algorithms: {len(native_algos)}")
for algo in native_algos:
    print(f"  {algo['name']}: {algo['description']}")

# List by category
centrality_algos = conn.algo.algorithms(category="centrality")
community_algos = conn.algo.algorithms(category="community")

# List NetworkX algorithms
nx_algos = conn.networkx.algorithms()
print(f"Available NetworkX algorithms: {len(nx_algos)}")

# Filter NetworkX by category
nx_centrality = conn.networkx.algorithms(category="centrality")
```

### Get Algorithm Details

```python
# Native algorithm info
info = conn.algo.algorithm_info("pagerank")
print(f"Name: {info['name']}")
print(f"Category: {info['category']}")
print(f"Description: {info['description']}")
print("Parameters:")
for param in info['parameters']:
    print(f"  {param['name']}: {param['type']} (default: {param.get('default')})")

# NetworkX algorithm info
nx_info = conn.networkx.algorithm_info("betweenness_centrality")
```

## Algorithm Execution Patterns

### Basic Execution

```python
# Run algorithm and wait for completion
result = conn.algo.pagerank("Customer", "pr_score", edge_type="KNOWS")

# Check execution status
print(f"Status: {result.status}")
print(f"Nodes updated: {result.nodes_updated}")
print(f"Duration: {result.duration_ms}ms")
```

### Asynchronous Execution

```python
# Start algorithm without waiting
result = conn.algo.pagerank(
    "Customer",
    "pr_score",
    edge_type="KNOWS",
    wait=False
)

print(f"Started execution: {result.execution_id}")

# Check status manually later
# (implementation depends on wrapper API)
```

### Error Handling

```python
from graph_olap.exceptions import (
    AlgorithmNotFoundError,
    AlgorithmFailedError,
    AlgorithmTimeoutError,
    ResourceLockedError
)

try:
    result = conn.algo.pagerank(
        "Customer",
        "pr_score",
        edge_type="KNOWS",
        timeout=300
    )
except AlgorithmNotFoundError:
    print("Algorithm not available in this wrapper")
except AlgorithmTimeoutError:
    print("Algorithm timed out - try smaller dataset or longer timeout")
except ResourceLockedError as e:
    print(f"Instance locked by: {e.holder_name} running {e.algorithm}")
except AlgorithmFailedError as e:
    print(f"Algorithm failed: {e}")
```

## Algorithm Comparison

### Native vs NetworkX

| Aspect | Ryugraph Native | FalkorDB Native | NetworkX |
|--------|-----------------|-----------------|----------|
| Availability | Ryugraph only | FalkorDB only | Ryugraph only |
| Invocation | `conn.algo.*` | `CALL algo.*()` | `conn.networkx.*` |
| Algorithms | 8 | 4 | 100+ |
| Performance | Fast (in-database) | Fast (in-database) | Slower (graph extraction) |
| Memory | Efficient | Efficient | Higher (graph copy) |
| Large graphs | Preferred | Preferred | May timeout |

### Algorithm Selection Guide

| Use Case | Recommended Algorithm |
|----------|----------------------|
| Node importance | PageRank (native) |
| Influence measurement | Betweenness Centrality (NetworkX) |
| Find clusters | Louvain (native) |
| Find connected groups | WCC (native) |
| Directed component analysis | SCC (native) |
| Dense core detection | K-Core (native) |
| Path analysis | Shortest Path (native) |
| Local connectivity | Clustering Coefficient (NetworkX) |

## Native Algorithm Summary Table (Ryugraph)

| Algorithm | Name | Category | Parameters | Result Type |
|-----------|------|----------|------------|-------------|
| PageRank | `pagerank` | centrality | damping_factor, max_iterations, tolerance | Float (0-1) |
| WCC | `wcc` | community | max_iterations | Integer (component ID) |
| SCC | `scc` | community | max_iterations | Integer (component ID) |
| SCC Kosaraju | `scc_kosaraju` | community | (none) | Integer (component ID) |
| Louvain | `louvain` | community | max_phases, max_iterations | Integer (community ID) |
| K-Core | `kcore` | clustering | (none) | Integer (k-degree) |
| Label Propagation | `label_propagation` | community | max_iterations | Integer (label) |
| Triangle Count | `triangle_count` | clustering | (none) | Integer (count) |
| Shortest Path | `shortest_path` | pathfinding | source_id, target_id, relationship_types, max_depth | Path data |

## FalkorDB Native Algorithms

FalkorDB provides 4 native graph algorithms accessible via Cypher procedures. These algorithms write results directly to node properties.

### PageRank (FalkorDB)

**Category:** Centrality

**Description:** Computes PageRank centrality scores measuring node importance based on incoming links.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `damping_factor` | float | No | 0.85 | Damping factor (probability of following a link) |
| `max_iterations` | int | No | 20 | Maximum iterations before stopping |
| `tolerance` | float | No | 0.0001 | Convergence tolerance threshold |

**Writes to:** Node property `pagerank`

**Example:**

```cypher
// Run PageRank with default parameters
CALL algo.pagerank()

// Run PageRank with custom parameters
CALL algo.pagerank(0.85, 100, 0.00001)

// Query results
MATCH (n)
WHERE n.pagerank IS NOT NULL
RETURN n.name, n.pagerank
ORDER BY n.pagerank DESC
LIMIT 10
```

---

### Betweenness Centrality (FalkorDB)

**Category:** Centrality

**Description:** Measures how often a node lies on shortest paths between other nodes. High betweenness nodes are important bridges in the network.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `sample_size` | int | No | None | Number of sample nodes for approximation (omit for exact) |

**Writes to:** Node property `betweenness`

**Example:**

```cypher
// Exact betweenness computation
CALL algo.betweenness()

// Approximate betweenness (faster for large graphs)
CALL algo.betweenness(100)

// Query results
MATCH (n)
WHERE n.betweenness IS NOT NULL
RETURN n.name, n.betweenness
ORDER BY n.betweenness DESC
LIMIT 10
```

---

### Weakly Connected Components (FalkorDB)

**Category:** Community

**Description:** Finds connected components treating all edges as undirected. Each node is assigned a component ID identifying which connected subgraph it belongs to.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| (none) | - | - | - | No parameters required |

**Writes to:** Node property `component_id`

**Example:**

```cypher
// Run WCC
CALL algo.wcc()

// Find component sizes
MATCH (n)
WHERE n.component_id IS NOT NULL
RETURN n.component_id, count(*) as size
ORDER BY size DESC
LIMIT 10

// Find isolated components (size = 1)
MATCH (n)
WHERE n.component_id IS NOT NULL
WITH n.component_id as comp, count(*) as size
WHERE size = 1
RETURN comp, size
```

---

### Community Detection via Label Propagation (FalkorDB)

**Category:** Community

**Description:** Detects communities by iteratively propagating labels. Each node adopts the most common label among its neighbors until convergence.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `max_iterations` | int | No | 10 | Maximum iterations before stopping |

**Writes to:** Node property `community`

**Example:**

```cypher
// Run CDLP with default iterations
CALL algo.cdlp()

// Run with more iterations for better convergence
CALL algo.cdlp(50)

// Analyze community distribution
MATCH (n)
WHERE n.community IS NOT NULL
RETURN n.community, count(*) as size
ORDER BY size DESC

// Find nodes in the same community
MATCH (n)
WHERE n.community = 42
RETURN n.name, n.community
```

---

## FalkorDB Algorithm Summary Table

| Algorithm | Procedure | Category | Parameters | Result Property |
|-----------|-----------|----------|------------|-----------------|
| PageRank | `algo.pagerank()` | centrality | damping_factor, max_iterations, tolerance | `pagerank` |
| Betweenness | `algo.betweenness()` | centrality | sample_size (optional) | `betweenness` |
| WCC | `algo.wcc()` | community | (none) | `component_id` |
| CDLP | `algo.cdlp()` | community | max_iterations | `community` |

## See Also

- [Cypher Reference](-/c-cypher-reference.manual.md) - Query algorithm results
- [Error Codes](-/b-error-codes.manual.md) - Algorithm error handling
- [SDK Quick Start](--/01-getting-started.manual.html) - Getting started with algorithms
