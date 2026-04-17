---
title: "Aggregation"
---

<div class="nb-header">
  <span class="nb-header__type">Tutorial</span>
  <h1 class="nb-header__title">Aggregation</h1>
  <p class="nb-header__subtitle">COUNT, SUM, AVG, COLLECT and grouping</p>
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
  <div class="nb-header__tags"><span class="nb-header__tag">Cypher</span><span class="nb-header__tag">Aggregation</span><span class="nb-header__tag">GROUP BY</span></div>
</div>

<div class="nb-objectives">
  <h3 class="nb-objectives__title">What You'll Learn</h3>
  <ul class="nb-objectives__list">
    <li><strong>Counting</strong> - COUNT rows and distinct values</li>
    <li><strong>Collecting</strong> - COLLECT into lists</li>
    <li><strong>Grouping</strong> - Implicit GROUP BY behaviour</li>
    <li><strong>Connection Degree</strong> - Count relationships per node</li>
  </ul>
</div>

<div class="nb-callout nb-callout--info">
  <span class="nb-sr-only">Info:</span>
  <span class="nb-callout__icon" aria-hidden="true"></span>
  <div class="nb-callout__content">
    <div class="nb-callout__title">Prerequisites</div>
    <div class="nb-callout__body">Complete 01_property_graphs before this tutorial.</div>
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
    <h2 class="nb-section__title">COUNT Function</h2>
    <p class="nb-section__description">Counting results</p>
  </div>
</div>

`COUNT(x)` returns the number of non-null values. Use `COUNT(DISTINCT x)` to
count only unique values. Without a `GROUP BY` clause, the count applies to the
entire result set.

```python
# Count all customers
total = conn.query_scalar("MATCH (c:Customer) RETURN count(c)")
print(f"Total customers: {total}")

# Count distinct sectors
distinct_sectors = conn.query_scalar(
    "MATCH (c:Customer) RETURN count(DISTINCT c.bk_sectr)"
)
print(f"Distinct sectors: {distinct_sectors}")
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">COLLECT Function</h2>
    <p class="nb-section__description">Building lists from results</p>
  </div>
</div>

`COLLECT()` gathers values into a list. When combined with a non-aggregated
column, it groups automatically — one list per group.

```python
# Collect all connections per customer into a list
result = conn.query("""
    MATCH (a:Customer)-[:SHARES_ACCOUNT]->(b:Customer)
    RETURN a.id AS customer, collect(b.id) AS connections
    ORDER BY customer
""")

result.show()
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Grouping Results</h2>
    <p class="nb-section__description">Implicit GROUP BY</p>
  </div>
</div>

Cypher has no explicit `GROUP BY` keyword. Instead, any non-aggregated column
in `RETURN` automatically becomes a grouping key. This is similar to SQL’s
implicit grouping.

```cypher
RETURN c.bk_sectr AS sector, count(c) AS count
--     ^^^^^^^^^^^            ^^^^^^^^
--     grouping key           aggregation
```

```python
# Group customers by sector
result = conn.query("""
    MATCH (c:Customer)
    RETURN c.bk_sectr AS sector, count(c) AS count
""")

result.show()

# Group by ID type
result = conn.query("""
    MATCH (c:Customer)
    RETURN c.acct_stus AS id_type, count(c) AS count
    ORDER BY count DESC
""")

result.show()
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Connection Degree</h2>
    <p class="nb-section__description">Counting relationships per node</p>
  </div>
</div>

A node’s **degree** is the number of relationships it has. Counting
relationships per node reveals the most-connected entities in the graph.

Using an undirected pattern `(c)-[r:SHARES_ACCOUNT]-()` counts both incoming
and outgoing edges.

```python
# Count connections per customer (degree)
result = conn.query("""
    MATCH (c:Customer)-[r:SHARES_ACCOUNT]-()
    RETURN c.id AS customer, count(r) AS degree
    ORDER BY degree DESC
""")

result.show()
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li><code>COUNT(c)</code> counts rows; <code>COUNT(DISTINCT c.x)</code> counts unique values</li>
    <li><code>COLLECT()</code> gathers grouped values into a list</li>
    <li>Non-aggregated columns in <code>RETURN</code> act as implicit <code>GROUP BY</code> keys</li>
    <li>Counting relationships per node reveals the most-connected entities</li>
  </ul>
</div>
