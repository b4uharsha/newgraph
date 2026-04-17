---
title: "Structural Analysis"
---

<div class="nb-header">
  <span class="nb-header__type">Tutorial</span>
  <h1 class="nb-header__title">Structural Analysis</h1>
  <p class="nb-header__subtitle">Analyse graph topology with K-Core, Triangle Count, and Clustering Coefficient</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">25 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--intermediate">
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
      </span>
      Intermediate
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">Algorithms</span><span class="nb-header__tag">Structural</span><span class="nb-header__tag">K-Core</span><span class="nb-header__tag">Triangles</span></div>
</div>

<div class="nb-objectives">
  <h3 class="nb-objectives__title">What You'll Learn</h3>
  <ul class="nb-objectives__list">
    <li><strong>K-Core Decomposition</strong> - Identify the densest subgraph cores</li>
    <li><strong>Triangle Count</strong> - Count closed triads per node</li>
    <li><strong>Clustering Coefficient</strong> - Measure how tightly neighbours are connected</li>
    <li><strong>Structural Comparison</strong> - Combine measures to characterise node roles</li>
  </ul>
</div>

<div class="nb-callout nb-callout--info">
  <span class="nb-sr-only">Info:</span>
  <span class="nb-callout__icon" aria-hidden="true"></span>
  <div class="nb-callout__content">
    <div class="nb-callout__title">Prerequisites</div>
    <div class="nb-callout__body">Complete <strong>01 Algorithm Concepts</strong> first.</div>
  </div>
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
    <h2 class="nb-section__title">K-Core Decomposition</h2>
    <p class="nb-section__description">Find the densest subgraph where every node has at least k connections</p>
  </div>
</div>

A **k-core** is a maximal subgraph where every node has degree at least *k*
within that subgraph. The *coreness* of a node is the highest k-core it belongs
to. Nodes with high coreness sit in the densely connected heart of the network.

In banking, high-coreness customers share accounts with many other
high-coreness customers — a pattern worth reviewing in AML investigations.

```python
# K-Core decomposition — assign coreness value to each node
result = conn.algo.kcore(
    node_label="Customer",
    property_name="kcore",
    edge_type="SHARES_ACCOUNT",
)
print(f"Status: {result.status}, Nodes updated: {result.nodes_updated}")

cores = conn.query("""
    MATCH (c:Customer)
    RETURN c.id AS name, c.kcore AS coreness
    ORDER BY c.kcore DESC, c.id
""")

print("\nAll nodes are in the 2-core: every customer connects to at least 2 others.")

cores.show()
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Triangle Count</h2>
    <p class="nb-section__description">Count closed triads to measure local density</p>
  </div>
</div>

A **triangle** is a set of three nodes that are all connected to each other.
The triangle count for a node tells you how many such closed triads it
participates in.

High triangle counts indicate tightly knit groups. In a shared-account
network, triangles mean three customers all share accounts with each other —
a potentially suspicious pattern worth investigating.

```python
# Triangle count — number of closed triads per node
result = conn.algo.triangle_count(
    node_label="Customer",
    property_name="triangles",
    edge_type="SHARES_ACCOUNT",
)
print(f"Status: {result.status}, Nodes updated: {result.nodes_updated}")

triangles = conn.query("""
    MATCH (c:Customer)
    RETURN c.id AS name, c.triangles AS tri
    ORDER BY c.triangles DESC, c.id
""")

print("\nLAU and KWONG participate in the most triangles (degree-3 hub nodes).")

triangles.show()
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Clustering Coefficient</h2>
    <p class="nb-section__description">How connected are a node's neighbours to each other?</p>
  </div>
</div>

The **clustering coefficient** of a node is the ratio of actual connections
between its neighbours to the maximum possible connections. A value of 1.0
means all neighbours know each other; 0.0 means none do.

This uses the NetworkX integration via `conn.networkx.clustering_coefficient()`.

```python
# Clustering coefficient via NetworkX integration
result = conn.networkx.clustering_coefficient(
    node_label="Customer",
    property_name="clustering",
)
print(f"Status: {result.status}")

clustering = conn.query("""
    MATCH (c:Customer)
    RETURN c.id AS name, round(c.clustering, 3) AS cc
    ORDER BY c.clustering, c.id
""")

print("\nDegree-2 nodes have clustering 1.0 (both neighbours connected).")
print("Degree-3 hub nodes have 0.667 (2 of 3 neighbour pairs connected).")

clustering.show()
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Comparing Structural Measures</h2>
    <p class="nb-section__description">Side-by-side view of K-Core, triangles, and clustering</p>
  </div>
</div>

```python
# Compare all structural measures side by side
df = conn.query_df("""
    MATCH (c:Customer)
    RETURN c.id AS name,
           c.kcore AS kcore,
           c.triangles AS triangles,
           round(c.clustering, 3) AS clustering
    ORDER BY c.triangles DESC, c.id
""")

print("Hub nodes (LAU, KWONG): high triangles, lower clustering (more neighbours to connect).")
print("Peripheral nodes: fewer triangles but perfect clustering (small tight group).")

df
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li><strong>K-Core</strong> reveals the densest core of the network — nodes that survive iterative pruning</li>
    <li><strong>Triangle Count</strong> measures local density; high counts indicate tightly knit groups</li>
    <li><strong>Clustering Coefficient</strong> normalises triangles by degree — high values mean neighbours are well-connected</li>
    <li>Hub nodes often have high triangle count but lower clustering (many neighbours, not all connected)</li>
    <li>Combining these measures characterises node roles: hubs vs. peripheral members</li>
  </ul>
</div>
