---
title: "Community Detection"
---

<div class="nb-header">
  <span class="nb-header__type">Tutorial</span>
  <h1 class="nb-header__title">Community Detection</h1>
  <p class="nb-header__subtitle">Find clusters and groups with Louvain and Label Propagation</p>
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
  <div class="nb-header__tags"><span class="nb-header__tag">Algorithms</span><span class="nb-header__tag">Community</span><span class="nb-header__tag">Louvain</span></div>
</div>

<div class="nb-objectives">
  <h3 class="nb-objectives__title">What You'll Learn</h3>
  <ul class="nb-objectives__list">
    <li><strong>Louvain</strong> - Modularity-based community detection</li>
    <li><strong>Label Propagation</strong> - Fast iterative community assignment</li>
    <li><strong>Comparison</strong> - When to use each algorithm</li>
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
    <h2 class="nb-section__title">Louvain Community Detection</h2>
    <p class="nb-section__description">Find communities by optimising modularity</p>
  </div>
</div>

The Louvain algorithm detects communities by maximising *modularity* — a measure of
how densely connected nodes are within a community compared to connections between
communities. It works in two phases: first assigning each node to the community that
gives the largest modularity gain, then collapsing communities into super-nodes and
repeating.

In our test graph, all 5 customers share accounts with each other through 6 edges,
forming a single tightly-connected cluster. Louvain correctly assigns them all to
the same community.

```python
# Run Louvain community detection
result = conn.algo.louvain(
    node_label="Customer",
    property_name="comm_louvain",
    edge_type="SHARES_ACCOUNT",
)
print(f"Louvain {result.status} \u2014 {result.nodes_updated} nodes assigned to communities")
```

```python
# View community assignments
df = conn.query_df("""
    MATCH (c:Customer)
    RETURN c.id AS name,
           c.comm_louvain AS community
    ORDER BY c.comm_louvain, c.id
""")
df
```

All 5 customers are assigned to community 0. This is expected: the test graph is
small and densely connected, so there is no natural split into separate groups.

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Label Propagation</h2>
    <p class="nb-section__description">Fast community detection through neighbour voting</p>
  </div>
</div>

Label Propagation works differently from Louvain. Each node starts with a unique label,
then iteratively adopts the most common label among its neighbours. The process
converges when no node wants to change its label.

Label Propagation is faster than Louvain (near-linear time complexity) but less
deterministic — different runs may produce slightly different community assignments.
It is a good choice when speed matters more than precision, especially on very large
graphs.

```python
# Run Label Propagation
result = conn.algo.label_propagation(
    node_label="Customer",
    property_name="comm_lp",
    edge_type="SHARES_ACCOUNT",
    max_iterations=100,
)
print(f"Label Propagation {result.status} — {result.nodes_updated} nodes assigned to communities")

df = conn.query_df("""
    MATCH (c:Customer)
    RETURN c.id AS name,
           c.comm_lp AS community
    ORDER BY c.comm_lp, c.id
""")
df
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Comparing Methods</h2>
    <p class="nb-section__description">Louvain vs Label Propagation side by side</p>
  </div>
</div>

Both algorithms assigned all customers to the same community in our test graph.
Let us compare the assignments side by side and discuss when to choose which.

| Criterion | Louvain | Label Propagation |
|---|---|---|
| **Quality** | Higher (modularity-optimised) | Good but non-deterministic |
| **Speed** | O(n log n) | Near-linear O(n) |
| **Best for** | Production analysis | Exploratory / large graphs |
| **Deterministic** | Yes | No (may vary between runs) |

```python
# Compare both community assignments in one table
df = conn.query_df("""
    MATCH (c:Customer)
    RETURN c.id AS name,
           c.comm_louvain AS louvain,
           c.comm_lp AS label_propagation
    ORDER BY c.id
""")
df
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Tuning with Resolution</h2>
    <p class="nb-section__description">Control community granularity with parameters</p>
  </div>
</div>

The Louvain algorithm accepts a `resolution` parameter that controls community
granularity:

- **resolution < 1.0** — Fewer, larger communities (merge small groups)
- **resolution = 1.0** — Default behaviour
- **resolution > 1.0** — More, smaller communities (split large groups)

Higher resolution values make the algorithm more aggressive about splitting nodes
into separate communities. On our small test graph the effect is limited, but on
larger production graphs this parameter is essential for tuning results.

```python
# Run Louvain with higher resolution to produce finer-grained communities
result = conn.algo.louvain(
    node_label="Customer",
    property_name="comm_louvain_hi",
    edge_type="SHARES_ACCOUNT",
    resolution=2.0,
)
print(f"Louvain (resolution=2.0) {result.status} — {result.nodes_updated} nodes assigned")

# Compare default vs high-resolution communities
df = conn.query_df("""
    MATCH (c:Customer)
    RETURN c.id AS name,
           c.comm_louvain AS default_res_1_0,
           c.comm_louvain_hi AS high_res_2_0
    ORDER BY c.id
""")
df
```

With the default resolution (1.0), all customers form a single community. Increasing
the resolution to 2.0 causes Louvain to split the graph into two communities —
MR LAU XIAOMING and KWONG XIAO TONG (the higher-degree nodes) remain together, while
the three lower-degree customers form a separate group.

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li><strong>Louvain</strong> finds high-quality communities by optimising modularity (<code>conn.algo.louvain</code>)</li>
    <li><strong>Label Propagation</strong> is faster but non-deterministic — good for large-scale exploration (<code>conn.algo.label_propagation</code>)</li>
    <li>The <strong>resolution</strong> parameter controls community granularity — higher values produce smaller, more numerous communities</li>
    <li>In banking, communities reveal shared-account networks and related parties</li>
  </ul>
</div>
