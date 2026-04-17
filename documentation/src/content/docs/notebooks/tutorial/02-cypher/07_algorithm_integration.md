---
title: "Algorithm Concepts"
---

<div class="nb-header">
  <span class="nb-header__type">Tutorial</span>
  <h1 class="nb-header__title">Algorithm Concepts</h1>
  <p class="nb-header__subtitle">Centrality, community detection, and pathfinding theory</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">40 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--advanced">
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
      </span>
      Advanced
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">Algorithms</span><span class="nb-header__tag">Theory</span><span class="nb-header__tag">Concepts</span></div>
</div>

<div class="nb-objectives">
  <h3 class="nb-objectives__title">What You'll Learn</h3>
  <ul class="nb-objectives__list">
    <li><strong>Centrality</strong> - Measuring node importance</li>
    <li><strong>Community Detection</strong> - Finding clusters</li>
    <li><strong>Pathfinding</strong> - Shortest paths and traversal</li>
    <li><strong>When to Use Which</strong> - Algorithm selection</li>
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

**Centrality algorithms** measure how important or influential a node is within a graph.
The most common centrality measures are:

- **PageRank** -- ranks nodes by the number and quality of incoming links. A node is
  important if it is pointed to by other important nodes. Originally designed for web
  page ranking, it applies to any directed graph.
- **Betweenness Centrality** -- measures how often a node lies on the shortest path
  between other pairs of nodes. High-betweenness nodes are "bridges" or "brokers".

**The pattern** for running algorithms with `graph_olap` is always:

1. **Run the algorithm** -- `conn.algo.<algorithm>(...)` computes scores and writes them
   as properties on the nodes.
2. **Query the results** -- use a standard Cypher query to read the computed properties.

This two-step approach keeps algorithm execution separate from result analysis, and lets
you re-query computed scores without re-running the algorithm.

```python
# --- List available algorithms ---
algos = conn.algo.algorithms()
print("Available algorithms:")
for algo in algos:
    print(f"  - {algo}")
```

```python
# --- Step 1: Run PageRank ---
# This writes a "pr_score" property onto every matched node
conn.algo.pagerank(node_label="Person", property_name="pr_score")
print("PageRank computed -- scores written to pr_score property.")
```

```python
# --- Step 2: Query PageRank results ---
# The pr_score property is now available for querying like any other node property
df = conn.query_df("""
    MATCH (p:Person)
    WHERE p.pr_score IS NOT NULL
    RETURN p.name AS person, round(p.pr_score, 4) AS pagerank
    ORDER BY p.pr_score DESC
    LIMIT 10
""")
df
```

**Community detection** algorithms identify clusters of densely connected nodes. They
assign each node to a community (group), usually represented by an integer ID.

Common algorithms:

- **Louvain** -- optimizes modularity to find communities. Works well on large graphs
  and naturally discovers hierarchical community structure.
- **Label Propagation** -- each node adopts the most common label among its neighbours.
  Very fast but non-deterministic (results may vary between runs).

After running community detection, you can:

- Query which community a node belongs to.
- Count the size of each community.
- Find nodes that bridge multiple communities.

```python
# --- Run community detection (Louvain) ---
conn.algo.louvain(node_label="Person", property_name="community_id")
print("Louvain community detection computed -- IDs written to community_id property.")
```

```python
# --- Query community sizes ---
df = conn.query_df("""
    MATCH (p:Person)
    WHERE p.community_id IS NOT NULL
    RETURN p.community_id AS community, count(p) AS size
    ORDER BY size DESC
""")
df
```

```python
# --- Query members of each community ---
df = conn.query_df("""
    MATCH (p:Person)
    WHERE p.community_id IS NOT NULL
    RETURN p.community_id AS community, COLLECT(p.name) AS members
    ORDER BY size(COLLECT(p.name)) DESC
""")
df
```

**Pathfinding** algorithms find routes between nodes. Cypher has built-in support for
shortest-path queries without needing the algorithm API:

- **`shortestPath()`** -- finds a single shortest path between two nodes.
- **`allShortestPaths()`** -- finds all shortest paths of equal length.

```cypher
MATCH p = shortestPath((a)-[*]-(b))
WHERE a.name = 'Alice' AND b.name = 'Bob'
RETURN p
```

The `[*]` means "any number of hops". You can constrain it with `[*1..5]` for a
maximum depth.

For **weighted shortest paths** (e.g. minimizing cost or distance), you would use
the algorithm API or NetworkX integration, which supports Dijkstra and other
weighted algorithms.

```python
# --- Shortest path with Cypher ---
# Find the shortest path between any two connected nodes
df = conn.query_df("""
    MATCH (a), (b)
    WHERE a <> b AND a.name IS NOT NULL AND b.name IS NOT NULL
    WITH a, b LIMIT 1
    MATCH p = shortestPath((a)-[*..5]-(b))
    RETURN
        a.name AS start,
        b.name AS end,
        length(p) AS hops,
        [n IN nodes(p) | n.name] AS path_nodes
""")
df
```

```python
# --- Variable-length paths: find all nodes within N hops ---
df = conn.query_df("""
    MATCH (start)
    WHERE start.name IS NOT NULL
    WITH start LIMIT 1
    MATCH (start)-[*1..2]-(neighbour)
    RETURN DISTINCT
        start.name AS origin,
        neighbour.name AS reachable,
        labels(neighbour)[0] AS label
    LIMIT 10
""")
df
```

Choosing the right algorithm depends on the question you are asking:

| Question | Algorithm Family | Example |
|----------|-----------------|---------|
| **Who is most important?** | Centrality | PageRank, Betweenness |
| **What groups exist?** | Community Detection | Louvain, Label Propagation |
| **How are two nodes connected?** | Pathfinding | Shortest Path, BFS |
| **How similar are two nodes?** | Similarity | Jaccard, Cosine |

**Decision framework:**

1. **Start with the business question** -- "Who are the key influencers?" maps to PageRank.
   "Which teams form naturally?" maps to Louvain.
2. **Consider the graph structure** -- directed vs undirected, weighted vs unweighted.
3. **Check scale** -- some algorithms (Label Propagation) scale to millions of nodes;
   others (Betweenness Centrality) are more expensive.
4. **Combine algorithms** -- run PageRank + Louvain together to find "the most important
   person in each community".

The cell below demonstrates this combination pattern.

```python
# --- Combining algorithms: top-ranked person per community ---
# Both pr_score and community_id were computed in earlier cells
df = conn.query_df("""
    MATCH (p:Person)
    WHERE p.pr_score IS NOT NULL AND p.community_id IS NOT NULL
    WITH p.community_id AS community, p
    ORDER BY p.pr_score DESC
    WITH community, head(COLLECT(p.name)) AS top_person,
         head(COLLECT(round(p.pr_score, 4))) AS top_score,
         count(p) AS community_size
    RETURN community, top_person, top_score, community_size
    ORDER BY community_size DESC
""")
df
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li>Centrality: PageRank (influence), Betweenness (bridges)</li>
    <li>Community: Louvain (modularity), Label Prop (fast)</li>
    <li>Pathfinding: BFS (unweighted), Dijkstra (weighted)</li>
    <li>Choose based on question: who, what group, how connected</li>
  </ul>
</div>
