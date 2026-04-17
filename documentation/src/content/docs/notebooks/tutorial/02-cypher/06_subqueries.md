---
title: "Subqueries"
---

<div class="nb-header">
  <span class="nb-header__type">Tutorial</span>
  <h1 class="nb-header__title">Subqueries</h1>
  <p class="nb-header__subtitle">CALL, UNION, and subquery patterns</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">35 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--advanced">
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
      </span>
      Advanced
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">Cypher</span><span class="nb-header__tag">Subqueries</span><span class="nb-header__tag">UNION</span></div>
</div>

<div class="nb-objectives">
  <h3 class="nb-objectives__title">What You'll Learn</h3>
  <ul class="nb-objectives__list">
    <li><strong>CALL Subqueries</strong> - Nested query execution</li>
    <li><strong>UNION</strong> - Combine result sets</li>
    <li><strong>EXISTS Subqueries</strong> - Conditional pattern checks</li>
    <li><strong>Correlated Subqueries</strong> - Reference outer scope</li>
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

<div class="nb-callout nb-callout--info">
  <span class="nb-sr-only">Info:</span>
  <span class="nb-callout__icon" aria-hidden="true"></span>
  <div class="nb-callout__content">
    <div class="nb-callout__title">Prerequisites</div>
    <div class="nb-callout__body">Complete G1_property_graphs before this tutorial.</div>
  </div>
</div>

`CALL { ... }` lets you run a subquery inside a larger query. The subquery executes in its own
scope, and only the variables it explicitly `RETURN`s are visible to the outer query.

**Why use subqueries?**

- **Isolation** -- the subquery has its own variable namespace, avoiding conflicts.
- **Post-processing** -- aggregate inside the subquery, then continue processing outside.
- **Per-row execution** -- when placed after a `WITH`, the subquery runs once per input row.

**Basic syntax:**

```cypher
CALL {
    MATCH (p:Person)
    RETURN p.name AS name, p.age AS age
}
RETURN name, age
ORDER BY age DESC
```

The outer query can only see `name` and `age` -- not `p` itself.

**Important:** a `CALL` subquery MUST end with a `RETURN` clause. Everything that is not
returned is invisible to the outer scope.

```python
# --- Basic CALL subquery ---
# The subquery finds nodes and returns selected fields; the outer query just sorts
df = conn.query_df("""
    CALL {
        MATCH (n)
        RETURN labels(n)[0] AS label, n.name AS name
        LIMIT 20
    }
    RETURN label, name
    ORDER BY label, name
""")
df
```

```python
# --- Subquery with aggregation ---
# The subquery counts nodes per label; the outer query filters to labels with many nodes
df = conn.query_df("""
    CALL {
        MATCH (n)
        RETURN labels(n)[0] AS label, count(n) AS cnt
    }
    WITH label, cnt
    WHERE cnt >= 2
    RETURN label, cnt
    ORDER BY cnt DESC
""")
df
```

`UNION` combines the results of two or more queries into a single result set.

- **`UNION`** removes duplicate rows (like SQL `UNION`).
- **`UNION ALL`** keeps all rows, including duplicates (faster -- no deduplication).

Both sides of a `UNION` must return the **same column names**.

```cypher
MATCH (p:Person) RETURN p.name AS name
UNION
MATCH (c:Company) RETURN c.name AS name
```

`UNION` is also frequently used inside `CALL { }` subqueries to combine different
query branches:

```cypher
CALL {
    MATCH (p:Person) RETURN p.name AS name
    UNION ALL
    MATCH (c:Company) RETURN c.name AS name
}
RETURN name
```

**`OPTIONAL MATCH`** is a related concept -- it works like `MATCH`, but returns `null` for
unmatched patterns instead of eliminating the row:

```cypher
MATCH (p:Person)
OPTIONAL MATCH (p)-[:MANAGES]->(sub:Person)
RETURN p.name, sub.name
```

If a person manages nobody, `sub.name` is `null` but the row for `p` still appears.

```python
# --- UNION ALL: combine results from different labels ---
df = conn.query_df("""
    MATCH (n)
    WHERE 'Person' IN labels(n)
    RETURN n.name AS name, 'Person' AS type
    LIMIT 5
    UNION ALL
    MATCH (n)
    WHERE 'Company' IN labels(n)
    RETURN n.name AS name, 'Company' AS type
    LIMIT 5
""")
df
```

```python
# --- OPTIONAL MATCH: keep rows even when no match is found ---
# Compare MATCH (drops unmatched rows) vs OPTIONAL MATCH (keeps them with nulls)
df = conn.query_df("""
    MATCH (a)
    OPTIONAL MATCH (a)-[r]->(b)
    RETURN
        a.name AS source,
        type(r) AS relationship,
        b.name AS target
    LIMIT 10
""")
df
```

`EXISTS { ... }` is a boolean subquery that checks whether a pattern exists in the graph.
It returns `true` or `false` without actually returning the matched data.

This is useful for **filtering** -- keep only nodes that have (or lack) a certain pattern:

```cypher
MATCH (p:Person)
WHERE EXISTS { MATCH (p)-[:WORKS_AT]->(:Company) }
RETURN p.name
```

This returns only people who work at a company.

**Negation** -- use `NOT EXISTS` to find nodes that lack a pattern:

```cypher
MATCH (p:Person)
WHERE NOT EXISTS { MATCH (p)-[:WORKS_AT]->() }
RETURN p.name AS unemployed
```

`EXISTS` subqueries are more readable than the older pattern-predicate syntax and can
express more complex conditions (multi-hop patterns, aggregation checks, etc.).

```python
# --- EXISTS: find nodes that have outgoing relationships ---
df = conn.query_df("""
    MATCH (n)
    WHERE EXISTS { MATCH (n)-[]->() }
    RETURN n.name AS has_outgoing, labels(n)[0] AS label
    LIMIT 10
""")
df
```

```python
# --- NOT EXISTS: find nodes with no outgoing relationships (leaf nodes) ---
df = conn.query_df("""
    MATCH (n)
    WHERE NOT EXISTS { MATCH (n)-[]->() }
    RETURN n.name AS leaf_node, labels(n)[0] AS label
    LIMIT 10
""")
df
```

A **correlated subquery** references variables from the outer query. This is what makes
`CALL { }` subqueries truly powerful -- you can pass context from the outer query into
the subquery using `WITH`.

```cypher
MATCH (p:Person)
CALL {
    WITH p                        -- import p from the outer scope
    MATCH (p)-[r]->()
    RETURN count(r) AS rel_count
}
RETURN p.name, rel_count
ORDER BY rel_count DESC
```

**How it works:**

1. The outer `MATCH` produces one row per `Person`.
2. For each row, the `CALL` subquery runs with that specific `p`.
3. The subquery counts relationships for that person and returns the count.
4. The outer query combines `p.name` with `rel_count`.

**Key rule:** inside a correlated subquery, only variables imported via `WITH` from the outer
scope are visible. All other outer variables are hidden.

**`WITH` for chaining** is a related technique -- even outside subqueries, `WITH` acts as a
pipeline separator that lets you reshape results mid-query:

```cypher
MATCH (n)
WITH labels(n)[0] AS label, count(n) AS cnt
WHERE cnt > 5
RETURN label, cnt
ORDER BY cnt DESC
```

```python
# --- Correlated subquery: count relationships per node ---
df = conn.query_df("""
    MATCH (n)
    CALL {
        WITH n
        MATCH (n)-[r]->()
        RETURN count(r) AS out_degree
    }
    RETURN n.name AS node, labels(n)[0] AS label, out_degree
    ORDER BY out_degree DESC
    LIMIT 10
""")
df
```

```python
# --- WITH chaining: aggregate, filter, then return ---
df = conn.query_df("""
    MATCH (n)-[r]->()
    WITH labels(n)[0] AS label, type(r) AS rel_type, count(*) AS cnt
    WHERE cnt >= 2
    RETURN label, rel_type, cnt
    ORDER BY cnt DESC
    LIMIT 10
""")
df
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li>CALL {} executes subqueries in isolated scope</li>
    <li>UNION combines results (UNION ALL keeps duplicates)</li>
    <li>EXISTS checks for pattern existence</li>
    <li>Correlated subqueries reference outer variables</li>
  </ul>
</div>
