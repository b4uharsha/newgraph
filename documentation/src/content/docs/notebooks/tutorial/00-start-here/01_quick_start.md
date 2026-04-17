---
title: "Quick Start"
---

<div class="nb-header">
    <div class="nb-title">Quick Start</div>
    <div class="nb-subtitle">Create your first graph from HSBC banking data</div>
    <div class="nb-metadata">
        <span class="nb-duration">5 min</span>
        <span class="nb-difficulty nb-difficulty--beginner">Beginner</span>
    </div>
</div>

## Step 1: Connect to the Tutorial Graph

The Graph OLAP SDK has two parts: a **control plane** (manages resources) and **wrapper instances** (run queries). The `setup()` helper connects to the control plane and finds or creates the shared tutorial instance.

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

print(f"Connected! Graph has {conn.query_scalar('MATCH (n) RETURN count(n)')} nodes.")
```

## Step 2: Query Your Graph

Now use `conn.query()` to run Cypher queries against the graph instance.

```python
# List all customers in the graph
result = conn.query("""
    MATCH (c:Customer)
    RETURN c.id AS name, c.bk_sectr AS sector
    ORDER BY c.id
""")
result.show()
```

## Step 3: Find Connections

Discover which customers share accounts.

```python
# Find customers who share bank accounts
result = conn.query("""
    MATCH (a:Customer)-[:SHARES_ACCOUNT]->(b:Customer)
    RETURN a.id AS customer_1, b.id AS customer_2
    ORDER BY a.id
""")

result.show()
```

## Step 4: Run an Algorithm

Use PageRank to find the most connected customers.

```python
# Run PageRank to find the most connected customers
result = conn.algo.pagerank(
    node_label="Customer",
    property_name="pr_score",
    edge_type="SHARES_ACCOUNT",
)
print(f"Algorithm status: {result.status}")
print(f"Nodes updated: {result.nodes_updated}")

# Query the results
df = conn.query_df("""
    MATCH (c:Customer)
    RETURN c.id AS name, round(c.pr_score, 4) AS pagerank
    ORDER BY c.pr_score DESC
""")
df
```

## Cleanup

The tutorial instance has a **TTL** (time-to-live) and will be automatically deleted when it expires. No manual cleanup is needed.

To delete it early, use `client.instances.delete(instance.id)`.

<div class="nb-navigation">
  <div class="nb-navigation__title">Next Steps</div>
  <div class="nb-card-grid">
    <a href="../02-cypher/01_property_graphs/" class="nb-card">
      <div class="nb-card__title">Learn Cypher</div>
      <div class="nb-card__description">Understand property graphs and write your first queries</div>
      <div class="nb-card__meta">20 min · Beginner</div>
    </a>
    <a href="../03-algorithms/01_introduction/" class="nb-card">
      <div class="nb-card__title">Run Algorithms</div>
      <div class="nb-card__description">Introduction to graph algorithms and analytics</div>
      <div class="nb-card__meta">15 min · Beginner</div>
    </a>
    <a href="../01-fundamentals/01_getting_started/" class="nb-card">
      <div class="nb-card__title">Explore the SDK</div>
      <div class="nb-card__description">Deep dive into the Graph OLAP SDK fundamentals</div>
      <div class="nb-card__meta">15 min · Beginner</div>
    </a>
  </div>
</div>
