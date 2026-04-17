---
title: "Exporting Results"
---

<div class="nb-header">
  <span class="nb-header__type">Tutorial</span>
  <h1 class="nb-header__title">Exporting Results</h1>
  <p class="nb-header__subtitle">Export query results to CSV, Parquet, DataFrame, and NetworkX</p>
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
  <div class="nb-header__tags"><span class="nb-header__tag">Export</span><span class="nb-header__tag">CSV</span><span class="nb-header__tag">Parquet</span><span class="nb-header__tag">NetworkX</span></div>
</div>

<div class="nb-objectives">
  <h3 class="nb-objectives__title">What You'll Learn</h3>
  <ul class="nb-objectives__list">
    <li><strong>Export to CSV</strong> - Save query results as comma-separated files</li>
    <li><strong>Export to Parquet</strong> - Columnar format for efficient analytics</li>
    <li><strong>Export to DataFrame</strong> - Query directly into Polars DataFrames</li>
    <li><strong>Export to NetworkX</strong> - Convert results to a Python graph for analysis</li>
  </ul>
</div>

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
    <h2 class="nb-section__title">Export to CSV</h2>
    <p class="nb-section__description">Save query results as a CSV file</p>
  </div>
</div>

```python
# Run a query and export results to CSV
result = conn.query("MATCH (c:Customer) RETURN c.id LIMIT 10")
result.to_csv("customers.csv")
print("Exported to customers.csv")

# Preview what was written
import pathlib
print(pathlib.Path("customers.csv").read_text()[:500])
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Export to Parquet</h2>
    <p class="nb-section__description">Columnar format for analytics workloads</p>
  </div>
</div>

```python
# Parquet is ideal for large exports — smaller files, faster reads
result = conn.query("""
    MATCH (a:Customer)-[:SHARES_ACCOUNT]->(b:Customer)
    RETURN a.id AS from_customer, b.id AS to_customer
    LIMIT 20
""")
result.to_parquet("customer_accounts.parquet")
print("Exported to customer_accounts.parquet")

import os
size_kb = os.path.getsize("customer_accounts.parquet") / 1024
print(f"File size: {size_kb:.1f} KB")
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Export to DataFrame</h2>
    <p class="nb-section__description">Query directly into a Polars DataFrame</p>
  </div>
</div>

```python
# query_df() returns a Polars DataFrame directly — no intermediate step
df = conn.query_df("""
    MATCH (c:Customer)
    RETURN c.id AS name
    LIMIT 10
""")
df
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Export to NetworkX</h2>
    <p class="nb-section__description">Convert results to a Python graph for analysis</p>
  </div>
</div>

```python
# Convert query results to a NetworkX graph for Python-native analysis
result = conn.query("""
    MATCH (a:Customer)-[r:SHARES_ACCOUNT]->(b:Customer)
    RETURN a, r, b
    LIMIT 50
""")

G = result.to_networkx()
print(f"NetworkX graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
print(f"Node types: {set(dict(G.nodes(data='label', default='unknown')).values())}")
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li>Use <code>result.to_csv(path)</code> for simple, portable exports</li>
    <li>Use <code>result.to_parquet(path)</code> for compact, columnar storage</li>
    <li>Use <code>conn.query_df(cypher)</code> for direct Polars DataFrame access</li>
    <li>Use <code>result.to_networkx()</code> to build a Python graph for algorithms and visualization</li>
    <li>All exports work on query results — there is no separate export resource</li>
  </ul>
</div>
