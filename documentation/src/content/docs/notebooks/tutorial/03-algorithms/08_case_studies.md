---
title: "Banking Use Cases"
---

<div class="nb-header">
  <span class="nb-header__type">Tutorial</span>
  <h1 class="nb-header__title">Banking Use Cases</h1>
  <p class="nb-header__subtitle">Apply graph algorithms to real-world banking scenarios</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">30 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--advanced">
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
      </span>
      Advanced
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">Algorithms</span><span class="nb-header__tag">Banking</span><span class="nb-header__tag">AML</span><span class="nb-header__tag">KYC</span></div>
</div>

<div class="nb-objectives">
  <h3 class="nb-objectives__title">What You'll Learn</h3>
  <ul class="nb-objectives__list">
    <li><strong>Use Case 1</strong> - Shared Account Network Analysis with PageRank</li>
    <li><strong>Use Case 2</strong> - Community Detection for AML with Louvain</li>
    <li><strong>Use Case 3</strong> - Path Analysis for Customer Due Diligence</li>
  </ul>
</div>

<div class="nb-callout nb-callout--info">
  <span class="nb-sr-only">Info:</span>
  <span class="nb-callout__icon" aria-hidden="true"></span>
  <div class="nb-callout__content">
    <div class="nb-callout__title">Prerequisites</div>
    <div class="nb-callout__body">Complete the earlier algorithm tutorials (01–07) to understand the individual algorithms used here.</div>
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
    <h2 class="nb-section__title">Use Case 1: Shared Account Network Analysis</h2>
    <p class="nb-section__description">Identify central customers using PageRank</p>
  </div>
</div>

**Scenario:** The compliance team needs to identify which customers are most
central in the shared-account network. Central customers connect to many
others through joint accounts and are natural starting points for
investigations.

**Approach:** Run PageRank to score every customer by their structural
importance, then rank them. Customers with the highest scores act as hubs
in the network — changes to their accounts ripple through many connections.

```python
# Use Case 1: PageRank to find central customers
result = conn.algo.pagerank(
    node_label="Customer",
    property_name="pr_score",
    edge_type="SHARES_ACCOUNT",
)
print(f"PageRank: {result.status} ({result.nodes_updated} nodes updated)")

# Rank customers by centrality
ranked = conn.query("""
    MATCH (c:Customer)
    RETURN c.id AS name, round(c.pr_score, 4) AS score
    ORDER BY c.pr_score DESC
""")

print("\nFinding: LAU and KWONG are equally central (degree 3 each).")
print("These two customers should be reviewed first in any network investigation.")

ranked.show()
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Use Case 2: Community Detection for AML</h2>
    <p class="nb-section__description">Group related customers with Louvain for Anti-Money Laundering review</p>
  </div>
</div>

**Scenario:** AML analysts need to identify clusters of customers who are
closely linked through shared accounts. Each cluster may represent a network
of related parties that should be reviewed together rather than individually.

**Approach:** Run Louvain community detection. Each community is a group of
customers more densely connected to each other than to the rest of the
network. Analysts can then treat each community as a single investigation
package.

```python
# Use Case 2: Louvain community detection for AML clustering
result = conn.algo.louvain(
    node_label="Customer",
    property_name="aml_community",
    edge_type="SHARES_ACCOUNT",
)
print(f"Louvain: {result.status} ({result.nodes_updated} nodes updated)")

# Report communities
communities = conn.query("""
    MATCH (c:Customer)
    RETURN c.aml_community AS comm, collect(c.id) AS members
    ORDER BY comm
""")

print(f"\nFinding: All {result.nodes_updated} customers form a single community.")
print("In production with thousands of customers, Louvain typically finds")
print("many smaller communities that can be assigned to individual analysts.")

communities.show()
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Use Case 3: Path Analysis for Due Diligence</h2>
    <p class="nb-section__description">Trace connection chains between customers for KYC review</p>
  </div>
</div>

**Scenario:** During enhanced due diligence (EDD), an analyst needs to
understand how two specific customers are connected. Are they directly
linked through a shared account, or is the connection indirect through
intermediary customers?

**Approach:** Use shortest-path analysis to find the chain of connections
between two customers. The path length tells the analyst whether the
relationship is direct (1 hop) or indirect (2+ hops), and the
intermediaries on the path may warrant their own review.

```python
# Use Case 3: Shortest path for due diligence
# First get node IDs
nodes = conn.query("""
    MATCH (c:Customer)
    RETURN id(c) AS nid, c.id AS name
""")
node_map = {row['name']: row['nid'] for row in nodes}

# Find path between two customers
src_name = "21804633"
tgt_name = "8984822"

result = conn.algo.shortest_path(
    source_id=node_map[src_name],
    target_id=node_map[tgt_name],
    relationship_types=["SHARES_ACCOUNT"],
    max_depth=5,
)

print(f"Due Diligence: {src_name} \u2192 {tgt_name}")

# AlgorithmExecution has .status and .result (a dict or None), not .path_length
if result.result is not None:
    path_data = result.result
    path_length = path_data.get("path_length", len(path_data.get("path_node_ids", [])) - 1)
    path_node_ids = path_data.get("path_node_ids", [])

    print(f"\nPath length: {path_length} hop(s)")

    # Resolve path to names
    if path_node_ids:
        id_list = ", ".join(str(i) for i in path_node_ids)
        path_rows = conn.query(f"""
            MATCH (c:Customer)
            WHERE id(c) IN [{id_list}]
            RETURN id(c) AS nid, c.id AS name
        """)
        id_to_name = {row['nid']: row['name'] for row in path_rows}
        ordered = [id_to_name[nid] for nid in path_node_ids]
        print(f"Connection chain: {' \u2192 '.join(ordered)}")

        if path_length == 1:
            print("\nAnalysis: Direct connection \u2014 these customers share an account.")
        else:
            intermediaries = ordered[1:-1]
            print(f"\nAnalysis:")
            print(f"  - These customers are NOT directly linked (no shared account)")
            print(f"  - They connect through intermediary: {', '.join(intermediaries)}")
            print(f"  - The intermediary should also be included in the EDD review")
else:
    print("\nNo path found between these customers.")
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li><strong>PageRank for network analysis</strong> — quickly identifies the most structurally important customers to prioritise for review</li>
    <li><strong>Louvain for AML</strong> — groups related customers into investigation packages that analysts can work through systematically</li>
    <li><strong>Shortest path for EDD</strong> — traces the chain of connections between customers, revealing intermediaries worth investigating</li>
    <li>These algorithms work on the same graph data — results accumulate as node properties and can be combined in a single query</li>
    <li>In production, scale these patterns from 5 customers to millions while keeping the same SDK API calls</li>
  </ul>
</div>
