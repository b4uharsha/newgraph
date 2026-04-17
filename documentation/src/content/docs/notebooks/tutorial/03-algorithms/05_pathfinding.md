---
title: "Pathfinding"
---

<div class="nb-header">
  <span class="nb-header__type">Tutorial</span>
  <h1 class="nb-header__title">Pathfinding</h1>
  <p class="nb-header__subtitle">Discover shortest paths between customers in a shared-account network</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">20 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--intermediate">
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
      </span>
      Intermediate
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">Algorithms</span><span class="nb-header__tag">Pathfinding</span><span class="nb-header__tag">Shortest Path</span></div>
</div>

<div class="nb-objectives">
  <h3 class="nb-objectives__title">What You'll Learn</h3>
  <ul class="nb-objectives__list">
    <li><strong>Node IDs</strong> - How to retrieve internal graph node identifiers</li>
    <li><strong>Shortest Path</strong> - Find the shortest route between two customers</li>
    <li><strong>Path Length</strong> - Interpret hop counts in a banking network</li>
    <li><strong>Multiple Paths</strong> - Compare paths between different customer pairs</li>
  </ul>
</div>

<div class="nb-callout nb-callout--info">
  <span class="nb-sr-only">Info:</span>
  <span class="nb-callout__icon" aria-hidden="true"></span>
  <div class="nb-callout__content">
    <div class="nb-callout__title">Prerequisites</div>
    <div class="nb-callout__body">Complete <strong>01 Algorithm Concepts</strong> first.</div>
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
    <h2 class="nb-section__title">Retrieve Node IDs</h2>
    <p class="nb-section__description">Get internal identifiers needed for pathfinding</p>
  </div>
</div>

The shortest-path algorithm needs internal node IDs as inputs. These are
assigned by the graph engine and differ from any business key. We query them
first so we can pass them to `conn.algo.shortest_path()`.

```python
# Retrieve internal node IDs for all customers
nodes = conn.query("""
    MATCH (c:Customer)
    RETURN id(c) AS node_id, c.id AS name
    ORDER BY c.id
""")

# Store IDs for use in pathfinding
node_map = {row['name']: row['node_id'] for row in nodes}

nodes.show()
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Shortest Path Between Two Customers</h2>
    <p class="nb-section__description">Find the shortest route through shared accounts</p>
  </div>
</div>

The `shortest_path` algorithm finds the path with the fewest hops between a
source and target node. In our fully connected test graph most customers are
1–2 hops apart.

**Banking relevance:** Path length between two customers indicates how closely
they are linked through shared accounts. Short paths (1 hop) mean direct
account sharing; longer paths suggest indirect relationships worth
investigating in KYC or AML workflows.

```python
# Shortest path between the first and last customer in our list
names = list(node_map.keys())
src_name = names[0]
tgt_name = names[-1]

src = node_map[src_name]
tgt = node_map[tgt_name]

result = conn.algo.shortest_path(
    source_id=src,
    target_id=tgt,
    relationship_types=["SHARES_ACCOUNT"],
    max_depth=5,
)

print(f"Shortest path: {src_name} \u2192 {tgt_name}")
print(f"  Status: {result.status}")

# AlgorithmExecution returns .result (a dict or None), not .path_length
if result.result:
    path_length = result.result.get("path_length", len(result.result.get("path_node_ids", [])) - 1)
    path_node_ids = result.result.get("path_node_ids", [])
    print(f"  Path length: {path_length} hop(s)")
    print(f"  Node IDs on path: {path_node_ids}")
else:
    print("  No path found")
    path_node_ids = []
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Resolve Path to Customer Names</h2>
    <p class="nb-section__description">Convert node IDs back to readable names</p>
  </div>
</div>

```python
# Resolve path node IDs to customer names
if result.result:
    path_node_ids = result.result.get("path_node_ids", [])
else:
    path_node_ids = []

if path_node_ids:
    id_list = ", ".join(str(i) for i in path_node_ids)

    path_names = conn.query(f"""
        MATCH (c:Customer)
        WHERE id(c) IN [{id_list}]
        RETURN id(c) AS nid, c.id AS name
    """)

    # Build ordered name list
    id_to_name = {row['nid']: row['name'] for row in path_names}
    ordered = [id_to_name[nid] for nid in path_node_ids]
    print(f"Path: {' \u2192 '.join(ordered)}")
else:
    print("No path to resolve")
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Compare Multiple Paths</h2>
    <p class="nb-section__description">Check distances between several customer pairs</p>
  </div>
</div>

```python
# Compare shortest paths between several pairs
# Use names dynamically from the node_map to avoid KeyError on exact name mismatches
names = list(node_map.keys())

# Build pairs from available names
pairs = []
if len(names) >= 2:
    pairs.append((names[0], names[1]))
if len(names) >= 3:
    pairs.append((names[0], names[2]))
if len(names) >= 4:
    pairs.append((names[2], names[3]))
if len(names) >= 5:
    pairs.append((names[3], names[-1]))

print("Path distances:")
for src_name, tgt_name in pairs:
    r = conn.algo.shortest_path(
        source_id=node_map[src_name],
        target_id=node_map[tgt_name],
        relationship_types=["SHARES_ACCOUNT"],
        max_depth=5,
    )
    if r.result:
        hops = r.result.get("path_length", len(r.result.get("path_node_ids", [])) - 1)
        print(f"  {src_name:<25s} \u2192 {tgt_name:<25s}: {hops} hop(s)")
    else:
        print(f"  {src_name:<25s} \u2192 {tgt_name:<25s}: no path found")

print("\nIn this fully connected graph, all customers are 1\u20132 hops apart.")
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li><strong>shortest_path</strong> requires internal node IDs — query them with <code>id(c)</code> first</li>
    <li>Path length measures the number of relationship hops between two nodes</li>
    <li>1 hop = direct shared account; 2+ hops = indirect relationship chain</li>
    <li>In banking, short paths indicate closely linked customers worth reviewing together</li>
    <li>Use <code>max_depth</code> to limit search scope in large production graphs</li>
  </ul>
</div>
