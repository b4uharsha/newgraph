---
title: "Combining Algorithms"
---

<div class="nb-header">
  <span class="nb-header__type">Tutorial</span>
  <h1 class="nb-header__title">Combining Algorithms</h1>
  <p class="nb-header__subtitle">Layer centrality, community, and structural measures for richer insights</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">25 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--advanced">
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
      </span>
      Advanced
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">Algorithms</span><span class="nb-header__tag">Combined</span><span class="nb-header__tag">Analysis</span></div>
</div>

<div class="nb-objectives">
  <h3 class="nb-objectives__title">What You'll Learn</h3>
  <ul class="nb-objectives__list">
    <li><strong>Multi-Algorithm Pipeline</strong> - Run PageRank, Louvain, and degree centrality in sequence</li>
    <li><strong>Unified Query</strong> - Combine all results into a single DataFrame</li>
    <li><strong>Cross-Algorithm Insight</strong> - Identify influential members within communities</li>
  </ul>
</div>

<div class="nb-callout nb-callout--info">
  <span class="nb-sr-only">Info:</span>
  <span class="nb-callout__icon" aria-hidden="true"></span>
  <div class="nb-callout__content">
    <div class="nb-callout__title">Prerequisites</div>
    <div class="nb-callout__body">Complete <strong>02 Centrality</strong> and <strong>03 Community Detection</strong> first.</div>
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
    <h2 class="nb-section__title">Run Multiple Algorithms</h2>
    <p class="nb-section__description">Build a multi-dimensional node profile with three algorithms</p>
  </div>
</div>

No single algorithm tells the whole story. **PageRank** identifies globally
important nodes, **Louvain** groups nodes into communities, and **degree
centrality** counts direct connections. Running all three and querying the
results together reveals which customers are influential *within* their
community — a pattern that matters for AML case prioritisation.

```python
# 1. PageRank — global importance
pr = conn.algo.pagerank(
    node_label="Customer",
    property_name="pr",
    edge_type="SHARES_ACCOUNT",
)
print(f"PageRank:          {pr.status} ({pr.nodes_updated} nodes)")

# 2. Louvain — community assignment
lv = conn.algo.louvain(
    node_label="Customer",
    property_name="community",
    edge_type="SHARES_ACCOUNT",
)
print(f"Louvain:           {lv.status} ({lv.nodes_updated} nodes)")

# 3. Degree centrality — normalised connection count
dc = conn.networkx.degree_centrality(
    node_label="Customer",
    property_name="dc",
)
print(f"Degree Centrality: {dc.status}")

print("\nAll three algorithms stored results as node properties.")
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Unified Results Table</h2>
    <p class="nb-section__description">Query all algorithm results in a single DataFrame</p>
  </div>
</div>

```python
# Query all algorithm results together
df = conn.query_df("""
    MATCH (c:Customer)
    RETURN c.id AS name,
           round(c.pr, 3) AS pagerank,
           c.community AS community,
           round(c.dc, 2) AS degree
    ORDER BY c.pr DESC
""")
df
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Cross-Algorithm Insights</h2>
    <p class="nb-section__description">Identify influential members within each community</p>
  </div>
</div>

The real power of combining algorithms emerges when you layer the results:

- **Community + PageRank** → Who is the most influential person in each group?
- **Community + Degree** → Who has the most connections within their cluster?
- **PageRank + Degree** → Do well-connected nodes always rank highest?

In our small test graph, all customers are in one community and the hub nodes
(LAU, KWONG) dominate both PageRank and degree. In production graphs with
thousands of customers and multiple communities, this approach pinpoints the
key individuals to review first.

```python
# Find the leader of each community (highest PageRank within group)
# Query all customers with their algorithm results
df = conn.query_df("""
    MATCH (c:Customer)
    RETURN c.community AS comm, c.id AS name,
           c.pr AS pr, c.dc AS dc
    ORDER BY c.pr DESC
""")

# Group by community in Python (avoids Cypher list function limitations)
communities = {}
for row in df.iter_rows(named=True):
    comm = row["comm"]
    if comm not in communities:
        communities[comm] = []
    communities[comm].append(row)

print("Cross-algorithm insights:")
for comm, members in sorted(communities.items()):
    leader = members[0]  # Already sorted by PR desc
    most_connected = max(members, key=lambda m: m["dc"])
    print(f"\nCommunity {comm} ({len(members)} members):")
    print(f"  Leader (highest PageRank): {leader['name']} ({leader['pr']:.3f})")
    print(f"  Most connected (highest degree): {most_connected['name']} ({most_connected['dc']:.2f})")

df
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li>Run multiple algorithms in sequence — results accumulate as node properties</li>
    <li>A single Cypher query can fetch all algorithm outputs into one DataFrame</li>
    <li>Combining centrality with community detection reveals leaders within clusters</li>
    <li>In production, multi-algorithm profiles help prioritise AML investigations</li>
    <li>Divergence between measures (e.g. high PageRank but low degree) flags unusual node roles</li>
  </ul>
</div>
