---
title: "First Cypher Queries"
---

<div class="nb-header">
  <span class="nb-header__type">Tutorial</span>
  <h1 class="nb-header__title">First Cypher Queries</h1>
  <p class="nb-header__subtitle">Learn MATCH, RETURN, and WHERE clauses</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">30 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--beginner">
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
      </span>
      Beginner
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">Cypher</span><span class="nb-header__tag">MATCH</span><span class="nb-header__tag">WHERE</span><span class="nb-header__tag">RETURN</span></div>
</div>

<div class="nb-objectives">
  <h3 class="nb-objectives__title">What You'll Learn</h3>
  <ul class="nb-objectives__list">
    <li><strong>MATCH</strong> - Find patterns in the graph</li>
    <li><strong>RETURN</strong> - Specify what to return</li>
    <li><strong>WHERE</strong> - Filter results with conditions</li>
    <li><strong>LIMIT</strong> - Control result size</li>
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
    <h2 class="nb-section__title">MATCH and RETURN</h2>
    <p class="nb-section__description">Finding nodes and selecting output</p>
  </div>
</div>

Every Cypher query starts with `MATCH`, which describes the **pattern** to find
in the graph. `RETURN` then selects which parts of the match to include in the
result set.

```cypher
MATCH (c:Customer)
RETURN c.id
LIMIT 5
```

- `(c:Customer)` binds each `Customer` node to the variable `c`.
- `c.id` reads the `id` property.
- `LIMIT 5` caps the output at five rows.

```python
# MATCH all Customer nodes and RETURN their names
result = conn.query("MATCH (c:Customer) RETURN c.id LIMIT 5")

result.show()
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Counting Results</h2>
    <p class="nb-section__description">Aggregation with count()</p>
  </div>
</div>

`count()` is an aggregation function that returns the number of matched items.
`query_scalar()` is a convenience method that returns a single value directly,
perfect for queries that produce one row with one column.

```python
# Count all Customer nodes using query_scalar()
total = conn.query_scalar("MATCH (c:Customer) RETURN count(c)")
print(f"Total customers: {total}")
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Ordering Results</h2>
    <p class="nb-section__description">Sorting with ORDER BY</p>
  </div>
</div>

`ORDER BY` sorts results by one or more expressions. Add `DESC` for descending order.
Combine with `LIMIT` to get "top N" results.

```python
# Order customer names alphabetically
result = conn.query("""
    MATCH (c:Customer)
    RETURN c.id AS name
    ORDER BY c.id
""")

result.show()
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Displaying Results</h2>
    <p class="nb-section__description">Using result.show()</p>
  </div>
</div>

The `show()` method renders query results as a formatted table inside Jupyter.
It auto-detects whether to display tabular data or a graph visualisation.

```python
# Display a richer result set with show()
result = conn.query("""
    MATCH (c:Customer)
    RETURN c.id AS name, c.bk_sectr AS sector, c.acct_stus AS id_type
    ORDER BY c.id
""")

result.show()
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li><code>MATCH</code> finds patterns in the graph; <code>RETURN</code> selects what to output</li>
    <li><code>query_scalar()</code> returns a single value (ideal for <code>count()</code>)</li>
    <li><code>ORDER BY</code> sorts results; <code>LIMIT</code> restricts row count</li>
    <li><code>result.show()</code> renders a formatted table in Jupyter</li>
  </ul>
</div>
