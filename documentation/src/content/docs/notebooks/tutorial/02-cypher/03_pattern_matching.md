---
title: "Pattern Matching"
---

<div class="nb-header">
  <span class="nb-header__type">Tutorial</span>
  <h1 class="nb-header__title">Pattern Matching</h1>
  <p class="nb-header__subtitle">Variable-length paths and complex patterns</p>
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
  <div class="nb-header__tags"><span class="nb-header__tag">Cypher</span><span class="nb-header__tag">Patterns</span><span class="nb-header__tag">Paths</span></div>
</div>

<div class="nb-objectives">
  <h3 class="nb-objectives__title">What You'll Learn</h3>
  <ul class="nb-objectives__list">
    <li><strong>Simple Patterns</strong> - Match node-relationship-node triples</li>
    <li><strong>WHERE Filters</strong> - Narrow results with conditions</li>
    <li><strong>Variable-Length Paths</strong> - Traverse multiple hops</li>
    <li><strong>Parameterized Queries</strong> - Pass values safely</li>
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
    <h2 class="nb-section__title">Simple Patterns</h2>
    <p class="nb-section__description">Matching relationships between nodes</p>
  </div>
</div>

A pattern in Cypher describes the shape you want to find in the graph.
The simplest relationship pattern connects two nodes:

```cypher
(a:Customer)-[:SHARES_ACCOUNT]->(b:Customer)
```

This matches every directed `SHARES_ACCOUNT` edge from one customer to another.

```python
# Find all SHARES_ACCOUNT relationships
result = conn.query("""
    MATCH (a:Customer)-[:SHARES_ACCOUNT]->(b:Customer)
    RETURN a.id AS from_customer, b.id AS to_customer
""")

result.show()
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">WHERE Filters</h2>
    <p class="nb-section__description">Narrowing results with conditions</p>
  </div>
</div>

The `WHERE` clause filters matched patterns by property values, string
operations, or boolean logic. Only rows satisfying the condition are returned.

```python
# Filter customers by sector
result = conn.query("""
    MATCH (c:Customer)
    WHERE c.bk_sectr = 'P'
    RETURN c.id AS name
""")

result.show()
```

```python
# String filtering with CONTAINS
result = conn.query("""
    MATCH (c:Customer)
    WHERE c.id CONTAINS 'XIAO'
    RETURN c.id AS name
""")

result.show()
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Variable-Length Paths</h2>
    <p class="nb-section__description">Traversing multiple hops</p>
  </div>
</div>

The `*1..2` syntax on a relationship matches paths of length 1 **or** 2.
This lets you discover indirect connections — customers linked through
an intermediate shared account.

```cypher
(a)-[:SHARES_ACCOUNT*1..2]->(b)
```

Use `DISTINCT` to de-duplicate results when multiple paths reach the same node.

```python
# Variable-length path: find customers within 2 hops of MR LAU XIAOMING
result = conn.query("""
    MATCH (a:Customer {id: 'MR LAU XIAOMING'})-[:SHARES_ACCOUNT*1..2]->(b:Customer)
    RETURN DISTINCT b.id AS reachable
    ORDER BY reachable
""")

result.show()
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Parameterized Queries</h2>
    <p class="nb-section__description">Safe value passing</p>
  </div>
</div>

Hard-coding values in a Cypher string is a security risk (Cypher injection)
and prevents query plan caching. Use the `parameters` argument instead:

```python
conn.query("MATCH (c {id: $name}) RETURN c", parameters={"name": value})
```

The `$name` placeholder is replaced safely by the engine.

```python
# Parameterized query -- safe and cache-friendly
result = conn.query(
    "MATCH (c:Customer {id: $name}) RETURN c.id AS name, c.bk_sectr AS sector, c.acct_stus AS id_type",
    parameters={"name": "MR LAU XIAOMING"}
)

result.show()
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li>Patterns like <code>(a)-[:REL]-&gt;(b)</code> describe the graph shape to find</li>
    <li><code>WHERE</code> filters results by property values or string operations</li>
    <li><code>*1..2</code> matches variable-length paths for multi-hop traversal</li>
    <li>Always use <code>parameters={}</code> instead of string interpolation for safety</li>
  </ul>
</div>
