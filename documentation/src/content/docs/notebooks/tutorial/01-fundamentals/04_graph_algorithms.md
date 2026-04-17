---
title: "Running Graph Algorithms"
---

<div class="nb-header">
  <span class="nb-header__type">Tutorial</span>
  <h1 class="nb-header__title">Running Graph Algorithms</h1>
  <p class="nb-header__subtitle">Execute centrality, community detection, and pathfinding algorithms</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">35 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--intermediate">
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
      </span>
      Intermediate
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">Algorithms</span><span class="nb-header__tag">PageRank</span><span class="nb-header__tag">Community</span><span class="nb-header__tag">Centrality</span></div>
</div>

<div class="nb-objectives">
  <h3 class="nb-objectives__title">What You'll Learn</h3>
  <ul class="nb-objectives__list">
    <li><strong>Algorithm Categories</strong> - Understand centrality, community, pathfinding</li>
    <li><strong>Running Algorithms</strong> - Execute algorithms via SDK</li>
    <li><strong>Accessing Results</strong> - Query algorithm results from graph properties</li>
    <li><strong>NetworkX Integration</strong> - Use 100+ NetworkX algorithms</li>
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
    <h2 class="nb-section__title">Algorithm Overview</h2>
    <p class="nb-section__description">Categories and when to use them</p>
  </div>
</div>

```python
# Run PageRank to find the most important customers
result = conn.algo.pagerank(
    node_label="Customer",
    property_name="pagerank_score",
    edge_type="SHARES_ACCOUNT",
)
print(f"Status: {result.status}, Nodes updated: {result.nodes_updated}")

# Query results — scores are stored as node properties
top_customers = conn.query("""
    MATCH (c:Customer)
    RETURN c.id AS name, round(c.pagerank_score, 4) AS score
    ORDER BY c.pagerank_score DESC
""")
top_customers.show()
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Centrality Algorithms</h2>
    <p class="nb-section__description">Find important nodes</p>
  </div>
</div>

```python
# Run Louvain community detection
result = conn.algo.louvain(
    node_label="Customer",
    property_name="community_id",
    edge_type="SHARES_ACCOUNT",
)
print(f"Status: {result.status}, Nodes updated: {result.nodes_updated}")

# Find community assignments
communities = conn.query("""
    MATCH (c:Customer)
    RETURN c.community_id AS community, collect(c.id) AS members
    ORDER BY community
""")
communities.show()
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Community Detection</h2>
    <p class="nb-section__description">Discover clusters and groups</p>
  </div>
</div>

```python
# NetworkX algorithms — extended analytics library
# Degree centrality: normalized count of connections
result = conn.networkx.degree_centrality(
    node_label="Customer",
    property_name="degree_cent",
)
print(f"Degree centrality: {result.status}")

# Betweenness centrality: how often a node bridges paths
result = conn.networkx.betweenness_centrality(
    node_label="Customer",
    property_name="betweenness",
)
print(f"Betweenness centrality: {result.status}")

# Clustering coefficient: how connected a node's neighbors are
result = conn.networkx.clustering_coefficient(
    node_label="Customer",
    property_name="clustering",
)
print(f"Clustering coefficient: {result.status}")

# Query the NetworkX results
df = conn.query_df("""
    MATCH (p:Customer)
    RETURN p.id AS name,
           round(p.degree_cent, 4) AS degree,
           round(p.betweenness, 4) AS betweenness,
           round(p.clustering, 4) AS clustering
    ORDER BY p.degree_cent DESC
""")
df
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">NetworkX Algorithms</h2>
    <p class="nb-section__description">Extended algorithm library</p>
  </div>
</div>

```python
# Compare multiple centrality measures side by side
df = conn.query_df("""
    MATCH (c:Customer)
    RETURN c.id AS name,
           round(c.pagerank_score, 3) AS pagerank,
           round(c.degree_cent, 3) AS degree,
           round(c.betweenness, 3) AS betweenness,
           round(c.clustering, 3) AS clustering
    ORDER BY c.pagerank_score DESC
""")

df
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li>Centrality algorithms rank node importance (<code>conn.algo.pagerank()</code>, <code>conn.networkx.betweenness_centrality()</code>)</li>
    <li>Community detection finds clusters (<code>conn.algo.louvain()</code>)</li>
    <li>Results stored as node properties, queryable via Cypher</li>
    <li>NetworkX provides additional centrality and structural algorithms via <code>conn.networkx.*</code></li>
  </ul>
</div>
