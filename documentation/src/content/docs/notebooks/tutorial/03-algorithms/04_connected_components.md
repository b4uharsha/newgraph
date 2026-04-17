---
title: "Connected Components"
---

<div class="nb-header">
  <span class="nb-header__type">Tutorial</span>
  <h1 class="nb-header__title">Connected Components</h1>
  <p class="nb-header__subtitle">Find disconnected subgraphs with WCC, SCC, and Kosaraju algorithms</p>
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
  <div class="nb-header__tags"><span class="nb-header__tag">Algorithms</span><span class="nb-header__tag">Components</span><span class="nb-header__tag">Connectivity</span></div>
</div>

<div class="nb-objectives">
  <h3 class="nb-objectives__title">What You'll Learn</h3>
  <ul class="nb-objectives__list">
    <li><strong>Weakly Connected Components</strong> - Find connected subgraphs ignoring edge direction</li>
    <li><strong>Strongly Connected Components</strong> - Find subgraphs where every node reaches every other</li>
    <li><strong>Kosaraju SCC</strong> - An alternative SCC algorithm using two-pass DFS</li>
    <li><strong>Comparison</strong> - When WCC and SCC differ and what that means</li>
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
    <h2 class="nb-section__title">Weakly Connected Components (WCC)</h2>
    <p class="nb-section__description">Group nodes that can reach each other when edge direction is ignored</p>
  </div>
</div>

A **weakly connected component** is a maximal set of nodes where every pair is
connected by some path, ignoring the direction of edges. In a banking context,
WCC reveals clusters of customers linked through shared accounts — even if the
account relationship only points one way.

If the entire graph is one component, every customer is reachable from every
other through some chain of shared accounts.

```python
# Weakly Connected Components — ignores edge direction
result = conn.algo.connected_components(
    node_label="Customer",
    property_name="wcc",
    edge_type="SHARES_ACCOUNT",
)
print(f"Status: {result.status}, Nodes updated: {result.nodes_updated}")

# Group customers by their component ID
components = conn.query("""
    MATCH (c:Customer)
    RETURN c.wcc AS component, collect(c.id) AS members
    ORDER BY component
""")

node_count = result.nodes_updated
num_components = len(components)
print(f"\nAll {node_count} customers belong to {num_components} component — the graph is fully connected.")

components.show()
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Strongly Connected Components (SCC)</h2>
    <p class="nb-section__description">Find subgraphs where every node can reach every other following edge direction</p>
  </div>
</div>

A **strongly connected component** is stricter than WCC: every node must be
reachable from every other node *following the direction of edges*. In a
directed graph, SCC can split what WCC considers one component into several
smaller ones.

For our test data the SHARES_ACCOUNT edges create bidirectional reachability
among all five customers, so SCC produces the same single component as WCC.

```python
# Strongly Connected Components — respects edge direction
result = conn.algo.scc(
    node_label="Customer",
    property_name="scc",
    edge_type="SHARES_ACCOUNT",
)
print(f"Status: {result.status}, Nodes updated: {result.nodes_updated}")

scc_components = conn.query("""
    MATCH (c:Customer)
    RETURN c.scc AS component, collect(c.id) AS members
    ORDER BY component
""")

print(f"\nSCC found {len(scc_components)} component(s) — same as WCC for this fully connected graph.")

scc_components.show()
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">SCC — Kosaraju Algorithm</h2>
    <p class="nb-section__description">An alternative two-pass depth-first search approach</p>
  </div>
</div>

**Kosaraju's algorithm** finds the same strongly connected components using a
different strategy: two depth-first traversals, one on the original graph and
one on the transposed (reversed) graph. It produces identical results to the
default SCC but may perform differently on certain graph shapes.

Use `conn.algo.scc_kosaraju()` when you want an alternative implementation for
validation or benchmarking.

```python
# Kosaraju SCC — alternative two-pass DFS algorithm
result = conn.algo.scc_kosaraju(
    node_label="Customer",
    property_name="scc_k",
    edge_type="SHARES_ACCOUNT",
)
print(f"Status: {result.status}, Nodes updated: {result.nodes_updated}")

kosaraju = conn.query("""
    MATCH (c:Customer)
    RETURN c.scc_k AS component, collect(c.id) AS members
    ORDER BY component
""")

kosaraju.show()
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Comparing Results</h2>
    <p class="nb-section__description">Side-by-side view of all three algorithms</p>
  </div>
</div>

```python
# Compare all three component algorithms side by side
df = conn.query_df("""
    MATCH (c:Customer)
    RETURN c.id AS name,
           c.wcc AS wcc,
           c.scc AS scc,
           c.scc_k AS kosaraju
    ORDER BY c.id
""")

print("All three algorithms agree: 1 component containing all 5 customers.")
print("In a graph with one-way edges or disconnected clusters, SCC and WCC would diverge.")

df
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li><strong>WCC</strong> ignores edge direction — use it to find clusters of related entities</li>
    <li><strong>SCC</strong> respects direction — use it when mutual reachability matters (e.g. circular fund flows)</li>
    <li><strong>Kosaraju</strong> is an alternative SCC algorithm for validation or benchmarking</li>
    <li>In our test graph all 5 customers form a single component under all three algorithms</li>
    <li>In production, multiple components reveal distinct customer networks for segmented analysis</li>
  </ul>
</div>
