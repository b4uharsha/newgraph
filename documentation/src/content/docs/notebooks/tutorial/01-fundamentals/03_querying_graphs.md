---
title: "Querying Your Graph"
---

<div class="nb-header">
  <span class="nb-header__type">Tutorial</span>
  <h1 class="nb-header__title">Querying Your Graph</h1>
  <p class="nb-header__subtitle">Execute Cypher queries and work with results</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">30 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--intermediate">
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
      </span>
      Intermediate
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">Cypher</span><span class="nb-header__tag">Queries</span><span class="nb-header__tag">Results</span><span class="nb-header__tag">DataFrames</span></div>
</div>

<div class="nb-objectives">
  <h3 class="nb-objectives__title">What You'll Learn</h3>
  <ul class="nb-objectives__list">
    <li><strong>Basic Queries</strong> - Execute MATCH and RETURN statements</li>
    <li><strong>Parameters</strong> - Use parameterized queries safely</li>
    <li><strong>Result Handling</strong> - Process query results as rows or DataFrames</li>
    <li><strong>Aggregations</strong> - Use COUNT, SUM, COLLECT and other aggregations</li>
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
    <h2 class="nb-section__title">Basic Query Execution</h2>
    <p class="nb-section__description">Using conn.query()</p>
  </div>
</div>

```python
# Basic query execution
result = conn.query("""
    MATCH (c:Customer)
    RETURN c.id AS name, c.bk_sectr AS sector
    ORDER BY c.id
    LIMIT 5
""")

result.show()
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Parameterized Queries</h2>
    <p class="nb-section__description">Safe parameter passing</p>
  </div>
</div>

```python
# Parameterized queries (safe from injection)
result = conn.query(
    "MATCH (c:Customer {id: $name}) RETURN c.bk_sectr AS sector",
    parameters={"name": "MR LAU XIAOMING"}
)
result.show()

# Never do this (Cypher injection risk):
# conn.query(f"MATCH (c) WHERE c.id = '{user_input}' RETURN c")
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Working with Results</h2>
    <p class="nb-section__description">Rows, scalars, and DataFrames</p>
  </div>
</div>

```python
# Get results as a Polars DataFrame
df = conn.query_df("""
    MATCH (a:Customer)-[:SHARES_ACCOUNT]->(b:Customer)
    RETURN a.id AS customer, b.id AS shares_account_with
    ORDER BY a.id
""")

df
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Aggregation Queries</h2>
    <p class="nb-section__description">Counting, summing, collecting</p>
  </div>
</div>

```python
# Get single value with query_scalar
total = conn.query_scalar("MATCH (c:Customer) RETURN count(c)")
print(f"Total customers: {total}")

# Multiple aggregations
result = conn.query("""
    MATCH (c:Customer)
    RETURN
        count(c) AS total,
        count(DISTINCT c.bk_sectr) AS sectors,
        count(DISTINCT c.acct_stus) AS id_types
""")
row = result.rows[0]
print(f"Customers: {row[0]}, Sectors: {row[1]}, ID types: {row[2]}")
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li><code>conn.query()</code> executes Cypher and returns <code>QueryResult</code></li>
    <li>Always use parameters for user input (prevents injection)</li>
    <li><code>query_df()</code> returns Polars DataFrame for analysis</li>
    <li><code>query_scalar()</code> returns single value for aggregations</li>
  </ul>
</div>
