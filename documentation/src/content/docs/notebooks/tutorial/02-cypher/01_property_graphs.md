---
title: "Property Graphs"
---

<div class="nb-header">
  <span class="nb-header__type">Tutorial</span>
  <h1 class="nb-header__title">Property Graphs</h1>
  <p class="nb-header__subtitle">Understand nodes, relationships, properties, and labels</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">20 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--beginner">
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
      </span>
      Beginner
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">Cypher</span><span class="nb-header__tag">Graphs</span><span class="nb-header__tag">Fundamentals</span></div>
</div>

<div class="nb-objectives">
  <h3 class="nb-objectives__title">What You'll Learn</h3>
  <ul class="nb-objectives__list">
    <li><strong>Graph Model</strong> - Nodes, relationships, and properties</li>
    <li><strong>Labels</strong> - Categorize nodes with labels</li>
    <li><strong>Relationship Types</strong> - Connect nodes with typed edges</li>
    <li><strong>Properties</strong> - Store data on nodes and relationships</li>
  </ul>
</div>

<div class="nb-callout nb-callout--info">
  <span class="nb-sr-only">Info:</span>
  <span class="nb-callout__icon" aria-hidden="true"></span>
  <div class="nb-callout__content">
    <div class="nb-callout__title">Prerequisites</div>
    <div class="nb-callout__body">No prerequisites - start here!</div>
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
    <h2 class="nb-section__title">What is a Property Graph?</h2>
    <p class="nb-section__description">Core concepts</p>
  </div>
</div>

A **property graph** stores data as:

- **Nodes** (vertices) — entities like customers, accounts, or transactions.
- **Relationships** (edges) — directed connections between nodes, e.g. `SHARES_ACCOUNT`.
- **Labels** — categories that group nodes by type, e.g. `Customer`.
- **Properties** — key-value pairs stored on both nodes and relationships, e.g. `id`, `bk_sectr`.

Unlike relational tables, a property graph makes connections first-class citizens.
Traversing a relationship is a single pointer hop, no matter how large the graph is.

```python
# Retrieve a few customer nodes to see the graph data
result = conn.query("""
    MATCH (c:Customer)
    RETURN c.id AS name, c.bk_sectr AS sector
    LIMIT 5
""")

result.show()
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Nodes and Labels</h2>
    <p class="nb-section__description">Entities in your graph</p>
  </div>
</div>

Every node carries one or more **labels** that describe its type.
Labels let Cypher target specific kinds of nodes: `MATCH (c:Customer)` only matches
nodes with the `Customer` label.

Use `get_schema()` to discover which labels exist in the loaded graph.

```python
# Explore node labels via the schema API
schema = conn.get_schema()

print("Node labels in graph:")
for label in schema.node_labels:
    print(f"  {label}")
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Relationships</h2>
    <p class="nb-section__description">Connections between nodes</p>
  </div>
</div>

**Relationships** connect two nodes and always have:

1. A **direction** — from a source node to a target node.
2. A **type** — a label like `SHARES_ACCOUNT` that describes the connection.
3. Optional **properties** — key-value data on the edge itself.

In Cypher, relationships are written inside square brackets:
`(a)-[:SHARES_ACCOUNT]->(b)`.

```python
# Explore relationship types via the schema API
print("Relationship types in graph:")
for rel_type in schema.relationship_types:
    print(f"  {rel_type}")
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Properties</h2>
    <p class="nb-section__description">Data attributes</p>
  </div>
</div>

**Properties** are key-value pairs attached to nodes or relationships.
They store the actual data — names, identifiers, sector codes, and so on.

Let's fetch a single Customer node and inspect all its properties.

```python
# Inspect the properties of a single node
result = conn.query("MATCH (c:Customer) RETURN c.id, c.bk_sectr, c.acct_stus LIMIT 1")

result.show()
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li>A property graph has <strong>nodes</strong> (entities) connected by <strong>relationships</strong> (edges)</li>
    <li><strong>Labels</strong> categorize nodes (e.g. <code>Customer</code>)</li>
    <li>Relationships have a <strong>direction</strong> and a <strong>type</strong> (e.g. <code>SHARES_ACCOUNT</code>)</li>
    <li><strong>Properties</strong> store key-value data on both nodes and relationships</li>
  </ul>
</div>
