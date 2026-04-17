---
title: "Centrality Algorithms"
---

<div class="nb-header">
  <span class="nb-header__type">Tutorial</span>
  <h1 class="nb-header__title">Centrality Algorithms</h1>
  <p class="nb-header__subtitle">Identify influential nodes with PageRank, degree, betweenness, and eigenvector centrality</p>
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
  <div class="nb-header__tags"><span class="nb-header__tag">Algorithms</span><span class="nb-header__tag">Centrality</span><span class="nb-header__tag">PageRank</span></div>
</div>

<div class="nb-objectives">
  <h3 class="nb-objectives__title">What You'll Learn</h3>
  <ul class="nb-objectives__list">
    <li><strong>PageRank</strong> - Find globally important nodes</li>
    <li><strong>Degree Centrality</strong> - Measure direct connections</li>
    <li><strong>Betweenness Centrality</strong> - Identify bridge nodes</li>
    <li><strong>Comparison</strong> - Combine measures for a complete picture</li>
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
    <h2 class="nb-section__title">PageRank</h2>
    <p class="nb-section__description">Measure influence through link structure</p>
  </div>
</div>

PageRank assigns each node a score based on how many other nodes link to it and how
important those linking nodes are. Originally designed for web pages, it works equally
well on banking graphs: a customer who shares accounts with many highly-connected
customers receives a higher PageRank score.

In our test graph, MR LAU XIAOMING and KWONG XIAO TONG each participate in 3
shared-account relationships (degree 3), so they receive the highest PageRank scores.

```python
# Run PageRank on Customer nodes connected by SHARES_ACCOUNT edges
result = conn.algo.pagerank(
    node_label="Customer",
    property_name="cent_pr",
    edge_type="SHARES_ACCOUNT",
)
print(f"PageRank {result.status} \u2014 {result.nodes_updated} nodes scored")
```

```python
# View PageRank results ordered by score
df = conn.query_df("""
    MATCH (c:Customer)
    RETURN c.id AS name,
           round(c.cent_pr, 4) AS pagerank
    ORDER BY c.cent_pr DESC
""")
df
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Degree Centrality</h2>
    <p class="nb-section__description">Normalised connection count</p>
  </div>
</div>

Degree centrality is the simplest centrality measure: it counts a node's connections and
normalises by the maximum possible connections (N-1). A score of 1.0 means the node is
connected to every other node in the graph.

This uses the NetworkX interface (`conn.networkx`) because degree centrality is not
one of the built-in native algorithms.

```python
# Degree centrality via NetworkX
result = conn.networkx.degree_centrality(
    node_label="Customer",
    property_name="cent_dc",
)
print(f"Degree centrality {result.status} — {result.nodes_updated} nodes scored")

df = conn.query_df("""
    MATCH (c:Customer)
    RETURN c.id AS name,
           round(c.cent_dc, 4) AS degree_centrality
    ORDER BY c.cent_dc DESC
""")
df
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Betweenness Centrality</h2>
    <p class="nb-section__description">Find nodes that bridge shortest paths</p>
  </div>
</div>

Betweenness centrality measures how often a node lies on the shortest path between
other pairs of nodes. High-betweenness nodes act as bridges or brokers: removing them
would disconnect parts of the network.

In anti-money-laundering, a high-betweenness customer may be the single link between
two otherwise separate account clusters — a pattern worth investigating.

```python
# Betweenness centrality via NetworkX
result = conn.networkx.betweenness_centrality(
    node_label="Customer",
    property_name="cent_bc",
)
print(f"Betweenness centrality {result.status} — {result.nodes_updated} nodes scored")

df = conn.query_df("""
    MATCH (c:Customer)
    RETURN c.id AS name,
           round(c.cent_bc, 4) AS betweenness
    ORDER BY c.cent_bc DESC
""")
df
```

MR LAU XIAOMING and KWONG XIAO TONG have non-zero betweenness because some shortest
paths between the other three customers pass through them. The remaining customers
have betweenness of 0 — they do not serve as bridges.

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Comparing Centrality Measures</h2>
    <p class="nb-section__description">Side-by-side view of all three metrics</p>
  </div>
</div>

Different centrality measures answer different questions. Comparing them side by side
reveals which customers are important and *why*:

- **PageRank** — Who is important because of who they are connected to?
- **Degree** — Who has the most connections?
- **Betweenness** — Who bridges otherwise separate parts of the network?

```python
# Compare all three centrality measures in one table
df = conn.query_df("""
    MATCH (c:Customer)
    RETURN c.id AS name,
           round(c.cent_pr, 4) AS pagerank,
           round(c.cent_dc, 4) AS degree,
           round(c.cent_bc, 4) AS betweenness
    ORDER BY c.cent_pr DESC
""")
df
```

In this small test graph the rankings are consistent across all three measures.
In larger production graphs, you will often see customers who rank high on one
measure but low on another — for example, a customer with few direct connections
(low degree) who nonetheless bridges two large clusters (high betweenness).

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li><strong>PageRank</strong> measures influence through iterative link-based scoring (<code>conn.algo.pagerank</code>)</li>
    <li><strong>Degree centrality</strong> counts normalised connections (<code>conn.networkx.degree_centrality</code>)</li>
    <li><strong>Betweenness centrality</strong> finds bridge nodes on shortest paths (<code>conn.networkx.betweenness_centrality</code>)</li>
    <li>Combining multiple centrality measures gives a richer picture of node importance</li>
  </ul>
</div>
