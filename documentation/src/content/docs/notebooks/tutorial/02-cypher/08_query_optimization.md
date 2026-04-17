---
title: "Query Optimization"
---

<div class="nb-header">
  <span class="nb-header__type">Tutorial</span>
  <h1 class="nb-header__title">Query Optimization</h1>
  <p class="nb-header__subtitle">Query planning, indexing, and performance</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">45 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--advanced">
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
      </span>
      Advanced
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">Performance</span><span class="nb-header__tag">Optimization</span><span class="nb-header__tag">Indexing</span></div>
</div>

<div class="nb-objectives">
  <h3 class="nb-objectives__title">What You'll Learn</h3>
  <ul class="nb-objectives__list">
    <li><strong>Query Planning</strong> - EXPLAIN and PROFILE</li>
    <li><strong>Indexing</strong> - Speed up lookups</li>
    <li><strong>Query Patterns</strong> - Efficient patterns</li>
    <li><strong>Common Pitfalls</strong> - Avoid performance traps</li>
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

Cypher provides two tools for understanding how the query engine executes your query:

- **`EXPLAIN`** -- shows the **planned** execution steps without actually running the query.
  Use it to check whether the planner chose a good strategy before executing.
- **`PROFILE`** -- runs the query AND shows the execution plan with **actual** row counts
  and timing for each step. Use it to find bottlenecks in slow queries.

**Reading the output:**

The plan is a tree of operations. Each operation shows:

- **Operator** -- the type of step (e.g. `NodeByLabelScan`, `Filter`, `ProduceResults`).
- **Rows** -- how many rows flowed through that step (PROFILE only).
- **DB Hits** -- how many low-level storage lookups were performed (fewer is better).

**When to use which:**

| Tool | Runs query? | Shows actual stats? | Use case |
|------|:-----------:|:-------------------:|----------|
| `EXPLAIN` | No | No | Quick check before running expensive queries |
| `PROFILE` | Yes | Yes | Diagnosing slow queries after the fact |

```python
# --- EXPLAIN: view the execution plan without running the query ---
result = conn.query("EXPLAIN MATCH (n:Person)-[r]->(m) RETURN n.name, type(r), m.name")
result.show()
```

```python
# --- PROFILE: run the query and see actual execution statistics ---
result = conn.query("PROFILE MATCH (n:Person)-[r]->(m) RETURN n.name, type(r), m.name")
result.show()
```

```python
# --- Compare: PROFILE a query with and without a label filter ---
# Without label: scans all nodes
result = conn.query("PROFILE MATCH (n) WHERE n.name IS NOT NULL RETURN n.name LIMIT 5")
result.show()
```

```python
# With label: scans only Person nodes (fewer DB hits)
result = conn.query("PROFILE MATCH (n:Person) WHERE n.name IS NOT NULL RETURN n.name LIMIT 5")
result.show()
```

**Indexes** speed up property lookups from O(n) scans to O(log n) or O(1) lookups.

**When to create an index:**

- A property is used in `WHERE` equality or range filters.
- A property is used in `MERGE` for finding existing nodes.
- A query is slow and PROFILE shows `NodeByLabelScan` + `Filter` instead of `NodeIndexSeek`.

**Index types:**

| Type | Syntax | Use case |
|------|--------|----------|
| **Range index** | `CREATE INDEX FOR (n:Label) ON (n.property)` | Equality, range, prefix lookups |
| **Composite** | `CREATE INDEX FOR (n:Label) ON (n.prop1, n.prop2)` | Multi-property filters |
| **Full-text** | `CREATE FULLTEXT INDEX ...` | Text search with tokenization |

**Rules of thumb:**

- Index properties that appear in `WHERE` clauses.
- Do not over-index -- each index adds write overhead.
- Composite indexes help when you always filter on multiple properties together.
- After creating an index, re-run `PROFILE` to confirm the planner uses it.

```python
# --- List existing indexes ---
df = conn.query_df("CALL db.indexes()")
df
```

```python
# --- Create an index on Person.name (if one does not already exist) ---
conn.query("CREATE INDEX IF NOT EXISTS FOR (p:Person) ON (p.name)")
print("Index on Person.name ensured.")
```

```python
# --- PROFILE after indexing: the planner should now use NodeIndexSeek ---
result = conn.query("PROFILE MATCH (p:Person) WHERE p.name = 'Alice' RETURN p")
result.show()
```

Writing efficient Cypher is about helping the query planner reduce work early.

**Tip 1: Always specify labels.**

```cypher
-- Slow: scans every node
MATCH (n) WHERE n.name = 'Alice' RETURN n

-- Fast: scans only Person nodes
MATCH (n:Person) WHERE n.name = 'Alice' RETURN n
```

**Tip 2: Filter early with `WITH` + `WHERE`.**

Push filters as close to the `MATCH` as possible so that fewer rows flow downstream:

```cypher
MATCH (p:Person)-[r]->(m)
WITH p, count(r) AS rels
WHERE rels > 3
RETURN p.name, rels
```

**Tip 3: Use `LIMIT` early.**

If you only need the top N results, add `LIMIT` as soon as possible:

```cypher
MATCH (p:Person)
WITH p ORDER BY p.name LIMIT 10
MATCH (p)-[r]->(m)
RETURN p.name, count(r) AS rels
```

**Tip 4: Use `count { }` instead of expanding + counting.**

```cypher
-- Instead of expanding all relationships then counting:
MATCH (p:Person)-[r]->() RETURN p.name, count(r)

-- Use a count subquery (avoids materializing every relationship):
MATCH (p:Person) RETURN p.name, count { (p)-[]->() } AS rels
```

```python
# --- Tip 1: Label filtering reduces scanned nodes ---
# Count nodes with vs without label
total = conn.query_scalar("MATCH (n) RETURN count(n)")
persons = conn.query_scalar("MATCH (n:Person) RETURN count(n)")
print(f"All nodes: {total}  |  Person nodes: {persons}")
print(f"Label filter skips {total - persons} irrelevant nodes.")
```

```python
# --- Tip 2 + 3: Filter early and LIMIT early ---
df = conn.query_df("""
    MATCH (n)
    WITH n ORDER BY n.name LIMIT 5
    OPTIONAL MATCH (n)-[r]->()
    RETURN n.name AS node, count(r) AS outgoing_rels
""")
df
```

Certain query patterns can cause dramatic slowdowns. Learn to recognize and avoid them.

**Pitfall 1: Cartesian products.**

When two `MATCH` clauses share no variables, every row from the first is paired with
every row from the second -- an N x M explosion:

```cypher
-- DANGER: this creates |Person| x |Company| rows!
MATCH (p:Person), (c:Company)
RETURN p.name, c.name
```

Fix: always connect patterns with a relationship or use `WITH` to pipeline.

**Pitfall 2: Unbounded variable-length paths.**

```cypher
-- DANGER: [*] explores every possible path in the graph!
MATCH (a)-[*]->(b) RETURN a, b
```

Fix: always set an upper bound -- `[*..5]` or `[*1..3]`.

**Pitfall 3: Missing labels on relationship endpoints.**

```cypher
-- Slow: both a and b scan all nodes
MATCH (a)-[:WORKS_AT]->(b) RETURN a.name, b.name

-- Fast: labels help the planner start from a smaller set
MATCH (a:Person)-[:WORKS_AT]->(b:Company) RETURN a.name, b.name
```

**Pitfall 4: Collecting then filtering (instead of filtering then collecting).**

```cypher
-- Slow: collects all names, then filters
MATCH (p:Person)
WITH COLLECT(p.name) AS names
RETURN [n IN names WHERE n STARTS WITH 'A']

-- Fast: filter first, then collect
MATCH (p:Person)
WHERE p.name STARTS WITH 'A'
RETURN COLLECT(p.name)
```

```python
# --- Pitfall demo: Cartesian product (use with caution on large graphs) ---
# See how the row count explodes when MATCH clauses share no variables
result = conn.query("""
    PROFILE
    MATCH (a:Person), (b:Person)
    WHERE a <> b
    RETURN count(*) AS cartesian_pairs
""")
result.show()
```

```python
# --- Safe alternative: bounded variable-length path ---
df = conn.query_df("""
    MATCH (a:Person)
    WITH a LIMIT 1
    MATCH path = (a)-[*1..3]-(b:Person)
    WHERE a <> b
    RETURN
        a.name AS start,
        b.name AS end,
        length(path) AS hops
    LIMIT 10
""")
df
```

```python
# --- Best practice: filter first, then collect (not the other way around) ---
df = conn.query_df("""
    MATCH (n)
    WHERE n.name IS NOT NULL AND n.name STARTS WITH 'A'
    RETURN labels(n)[0] AS label, COLLECT(n.name) AS a_names
""")
df
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li>PROFILE shows actual execution statistics</li>
    <li>Index properties used in WHERE clauses</li>
    <li>Start MATCH with most selective pattern</li>
    <li>Avoid Cartesian products and unbounded paths</li>
  </ul>
</div>
