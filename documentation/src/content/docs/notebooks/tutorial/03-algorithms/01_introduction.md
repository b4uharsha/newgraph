---
title: "Algorithm Concepts"
---

<div class="nb-header">
  <span class="nb-header__type">Tutorial</span>
  <h1 class="nb-header__title">Algorithm Concepts</h1>
  <p class="nb-header__subtitle">Introduction to graph algorithms and when to use them</p>
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
  <div class="nb-header__tags"><span class="nb-header__tag">Algorithms</span><span class="nb-header__tag">Introduction</span></div>
</div>

<div class="nb-objectives">
  <h3 class="nb-objectives__title">What You'll Learn</h3>
  <ul class="nb-objectives__list">
    <li><strong>Algorithm Categories</strong> - Centrality, community detection, pathfinding, structural</li>
    <li><strong>When to Use</strong> - Choosing the right algorithm for your question</li>
    <li><strong>How Results Work</strong> - Properties stored on nodes after execution</li>
  </ul>
</div>

## Setup

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

print(f"Connected | {conn.query_scalar('MATCH (n) RETURN count(n)')} nodes")
```

<div class="nb-section">
  <span class="nb-section__number">1</span>
  <div>
    <h2 class="nb-section__title">What Are Graph Algorithms?</h2>
    <p class="nb-section__description">Categories and when to use them</p>
  </div>
</div>

Graph algorithms analyse the structure and relationships in a graph to surface insights that
simple queries cannot reveal. They fall into four main categories:

| Category | Purpose | Example |
|---|---|---|
| **Centrality** | Rank nodes by importance | PageRank, Degree Centrality |
| **Community Detection** | Find clusters of related nodes | Louvain, Label Propagation |
| **Pathfinding** | Discover shortest or optimal routes | Shortest Path, All Paths |
| **Structural** | Measure graph topology | Connected Components, Triangle Count |

In banking, these algorithms help identify influential customers, detect related-party networks,
find isolated account clusters, and map transaction flows.

```python
# Discover available native algorithms
algos = conn.algo.algorithms()
print("Available native algorithms:")
for name in algos:
    print(f"  - {name}")
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Running Your First Algorithm</h2>
    <p class="nb-section__description">Execute PageRank and understand the result object</p>
  </div>
</div>

Every algorithm call returns an `AlgorithmExecution` object with metadata about the run.
The algorithm writes its scores directly to a named property on each node.

```python
# Run PageRank — results are written to the "intro_pr" property on each Customer node
result = conn.algo.pagerank(
    node_label="Customer",
    property_name="intro_pr",
    edge_type="SHARES_ACCOUNT",
)

# Inspect the AlgorithmExecution result object
print(f"Algorithm : {result.algorithm}")
print(f"Status    : {result.status}")
print(f"Nodes     : {result.nodes_updated}")
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Reading Results</h2>
    <p class="nb-section__description">Query algorithm output with Cypher</p>
  </div>
</div>

Because algorithms store their output as node properties, you read the results using
standard Cypher queries. The `query_df` method returns a Polars DataFrame for
convenient tabular display.

```python
# Query the PageRank scores stored on each Customer node
df = conn.query_df("""
    MATCH (c:Customer)
    RETURN c.id AS name,
           round(c.intro_pr, 4) AS pagerank
    ORDER BY c.intro_pr DESC
""")

df
```

MR LAU XIAOMING and KWONG XIAO TONG score highest because they each have 3 shared-account
relationships (degree 3), giving them more incoming "votes" in the PageRank iteration.
The remaining three customers share 2 connections each.

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Native vs NetworkX Algorithms</h2>
    <p class="nb-section__description">conn.algo for speed, conn.networkx for breadth</p>
  </div>
</div>

The SDK provides two algorithm interfaces:

- **`conn.algo`** — Native algorithms executed inside the graph engine. Faster, but limited
  to a curated set (PageRank, Louvain, Connected Components, etc.).
- **`conn.networkx`** — Algorithms from the NetworkX library. The graph is exported to
  NetworkX, the algorithm runs in Python, and results are written back. Slower on large
  graphs, but provides access to 100+ algorithms (betweenness centrality, closeness
  centrality, clustering coefficient, and many more).

```python
# Compare the two interfaces
native_count = len(conn.algo.algorithms())
nx_algos = conn.networkx.algorithms()
print(f"Native algorithms  : {native_count}")
print(f"NetworkX algorithms: {len(nx_algos)}+")

# Run a NetworkX algorithm for comparison
print("\nExample NetworkX call \u2014 degree centrality:")
nx_result = conn.networkx.degree_centrality(
    node_label="Customer",
    property_name="intro_dc",
)
print(f"Status: {nx_result.status}, Nodes updated: {nx_result.nodes_updated}")
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li>Algorithms write results to <strong>node properties</strong> — query them with Cypher afterwards</li>
    <li>The <code>AlgorithmExecution</code> result gives you status, node count, and algorithm name</li>
    <li>Use <code>conn.algo</code> for fast native algorithms (PageRank, Louvain, WCC)</li>
    <li>Use <code>conn.networkx</code> for the full NetworkX library (100+ algorithms)</li>
  </ul>
</div>
