---
title: "Graph Visualization"
---

<div class="nb-header">
  <span class="nb-header__type">Tutorial</span>
  <h1 class="nb-header__title">Graph Visualization</h1>
  <p class="nb-header__subtitle">Create interactive graph visualizations with pyvis and plotly</p>
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
  <div class="nb-header__tags"><span class="nb-header__tag">Visualization</span><span class="nb-header__tag">pyvis</span><span class="nb-header__tag">plotly</span><span class="nb-header__tag">NetworkX</span><span class="nb-header__tag">Charts</span></div>
</div>

<div class="nb-objectives">
  <h3 class="nb-objectives__title">What You'll Learn</h3>
  <ul class="nb-objectives__list">
    <li><strong>NetworkX Conversion</strong> - Build a NetworkX graph from query results</li>
    <li><strong>Interactive Visualization</strong> - Render graph networks with pyvis</li>
    <li><strong>Community Coloring</strong> - Color nodes by Louvain community membership</li>
    <li><strong>Centrality Sizing</strong> - Size nodes by PageRank score</li>
    <li><strong>Charts</strong> - Create analytical charts with plotly</li>
  </ul>
</div>

<div class="nb-section">
  <span class="nb-section__number">1</span>
  <div>
    <h2 class="nb-section__title">Setup</h2>
    <p class="nb-section__description">Connect to the platform and provision tutorial resources</p>
  </div>
</div>

```python
# Cell 1 — Parameters
USERNAME = "_FILL_ME_IN_"  # Set your email before running
```

```python
# Cell 2 — Connect and provision
from graph_olap import GraphOLAPClient
client = GraphOLAPClient(username=USERNAME)

from notebook_setup import provision
personas, conn = provision(USERNAME)
analyst = personas["analyst"]

print(f"Connected | {conn.query_scalar('MATCH (n) RETURN count(n)')} nodes")
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Converting to NetworkX</h2>
    <p class="nb-section__description">Build a NetworkX DiGraph from query results</p>
  </div>
</div>

```python
# Query nodes and edges, then convert to a NetworkX DiGraph
result = conn.query(
    "MATCH (a:Customer)-[r:SHARES_ACCOUNT]->(b:Customer) "
    "RETURN a.id AS src, a.id AS src_name, "
    "b.id AS dst, b.id AS dst_name LIMIT 50"
)

G = result.to_networkx()

print(f"NetworkX graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
print(f"Type: {type(G).__module__}.{type(G).__name__}")
print(f"Sample nodes: {list(G.nodes)[:5]}")
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Interactive Visualization with pyvis</h2>
    <p class="nb-section__description">Render an interactive graph network in the browser</p>
  </div>
</div>

```python
# Guard: check if pyvis is available
try:
    from pyvis.network import Network
    HAS_PYVIS = True
    print("pyvis is available")
except ImportError:
    HAS_PYVIS = False
    print("Install pyvis for interactive graphs: pip install pyvis")
```

```python
if HAS_PYVIS:
    net = Network(height="500px", width="100%", notebook=True, directed=True)

    # Add nodes with labels
    for node_id in G.nodes:
        label = G.nodes[node_id].get("src_name", node_id)
        net.add_node(node_id, label=str(label), title=f"Customer {node_id}")

    # Add edges
    for src, dst in G.edges:
        net.add_edge(src, dst)

    # Configure physics for layout
    net.toggle_physics(True)
    net.show("/tmp/graph_basic.html")
    print(f"Interactive graph saved to /tmp/graph_basic.html ({G.number_of_nodes()} nodes)")
else:
    print("Skipped: pyvis not installed")
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Coloring by Algorithm Results</h2>
    <p class="nb-section__description">Run Louvain community detection and color nodes by community</p>
  </div>
</div>

```python
# Run Louvain community detection via the SDK API
conn.algo.louvain(
    node_label="Customer",
    edge_type="SHARES_ACCOUNT",
    property_name="viz_community",
    resolution=1.0,
)

# Query community assignments via regular Cypher
communities = conn.query(
    "MATCH (c:Customer) WHERE c.viz_community IS NOT NULL "
    "RETURN c.id AS id, c.viz_community AS communityId LIMIT 50"
)

# Build a community lookup
community_map = {row["id"]: row["communityId"] for row in communities}
unique_communities = sorted(set(community_map.values()))
print(f"Detected {len(unique_communities)} communities across {len(community_map)} nodes")

# Assign colors per community
COLORS = ["#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f",
          "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac"]
color_map = {cid: COLORS[i % len(COLORS)] for i, cid in enumerate(unique_communities)}

if HAS_PYVIS:
    net = Network(height="500px", width="100%", notebook=True, directed=True)
    for node_id in G.nodes:
        cid = community_map.get(node_id, 0)
        color = color_map.get(cid, "#999999")
        net.add_node(node_id, label=str(node_id), color=color,
                     title=f"Customer {node_id} | Community {cid}")
    for src, dst in G.edges:
        net.add_edge(src, dst)
    net.toggle_physics(True)
    net.show("/tmp/graph_communities.html")
    print(f"Community-colored graph saved to /tmp/graph_communities.html")
else:
    print("Skipped: pyvis not installed")
```

<div class="nb-section">
  <span class="nb-section__number">5</span>
  <div>
    <h2 class="nb-section__title">Sizing by Centrality</h2>
    <p class="nb-section__description">Run PageRank and size nodes proportionally</p>
  </div>
</div>

```python
# Run PageRank via the SDK API
conn.algo.pagerank(
    node_label="Customer",
    edge_type="SHARES_ACCOUNT",
    property_name="viz_pr",
)

# Query scores via regular Cypher
pagerank = conn.query(
    "MATCH (c:Customer) WHERE c.viz_pr IS NOT NULL "
    "RETURN c.id AS id, c.viz_pr AS score "
    "ORDER BY c.viz_pr DESC LIMIT 50"
)

# Build a score lookup
score_map = {row["id"]: row["score"] for row in pagerank}
max_score = max(score_map.values()) if score_map else 1.0
print(f"PageRank scores for {len(score_map)} nodes (max={max_score:.4f})")

if HAS_PYVIS:
    net = Network(height="500px", width="100%", notebook=True, directed=True)
    for node_id in G.nodes:
        score = score_map.get(node_id, 0.0)
        cid = community_map.get(node_id, 0)
        color = color_map.get(cid, "#999999")
        # Scale node size: 10 (min) to 40 (max)
        size = 10 + 30 * (score / max_score)
        net.add_node(node_id, label=str(node_id), color=color, size=size,
                     title=f"Customer {node_id} | PR={score:.4f}")
    for src, dst in G.edges:
        net.add_edge(src, dst)
    net.toggle_physics(True)
    net.show("/tmp/graph_pagerank.html")
    print(f"PageRank-sized graph saved to /tmp/graph_pagerank.html")
else:
    print("Skipped: pyvis not installed")
```

<div class="nb-section">
  <span class="nb-section__number">6</span>
  <div>
    <h2 class="nb-section__title">Charts with plotly</h2>
    <p class="nb-section__description">Create analytical bar and scatter charts</p>
  </div>
</div>

```python
# Guard: check if plotly is available
try:
    import plotly.express as px
    HAS_PLOTLY = True
    print("plotly is available")
except ImportError:
    HAS_PLOTLY = False
    print("Install plotly for charts: pip install plotly")
```

```python
if HAS_PLOTLY:
    # Bar chart: top 10 nodes by PageRank (already computed as viz_pr property)
    pr_df = conn.query_df(
        "MATCH (c:Customer) WHERE c.viz_pr IS NOT NULL "
        "RETURN c.id AS id, c.id AS name, c.viz_pr AS score "
        "ORDER BY c.viz_pr DESC LIMIT 10",
        backend="pandas",
    )
    fig = px.bar(pr_df, x="name", y="score", title="Top 10 Customers by PageRank")
    fig.write_html("/tmp/chart_pagerank.html")
    print("Bar chart saved to /tmp/chart_pagerank.html")

    # Scatter chart: centrality vs degree
    degree_df = conn.query_df(
        "MATCH (c:Customer) WHERE c.viz_pr IS NOT NULL "
        "WITH c, c.viz_pr AS pagerank "
        "MATCH (c)-[r:SHARES_ACCOUNT]-() "
        "RETURN c.id AS id, pagerank, count(r) AS degree",
        backend="pandas",
    )
    fig2 = px.scatter(
        degree_df, x="degree", y="pagerank",
        hover_data=["id"],
        title="PageRank vs Degree (SHARES_ACCOUNT)",
    )
    fig2.write_html("/tmp/chart_scatter.html")
    print("Scatter chart saved to /tmp/chart_scatter.html")
else:
    print("Skipped: plotly not installed")
```

<div class="nb-section">
  <span class="nb-section__number">7</span>
  <div>
    <h2 class="nb-section__title">Using show()</h2>
    <p class="nb-section__description">Built-in auto-visualization for query results</p>
  </div>
</div>

```python
# show() automatically detects graph structure and renders appropriately
result = conn.query(
    "MATCH (a:Customer)-[:SHARES_ACCOUNT]->(b:Customer) "
    "RETURN a.id AS src, b.id AS dst LIMIT 10"
)
result.show()
print(f"\nshow() rendered {result.row_count} rows with auto-detection")
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li><code>to_networkx()</code> converts query results into a NetworkX DiGraph for graph analysis</li>
    <li>pyvis renders interactive, physics-enabled graph visualizations as HTML files</li>
    <li>Louvain community IDs can drive node coloring to reveal cluster structure</li>
    <li>PageRank scores can scale node sizes to highlight important nodes</li>
    <li>plotly creates publication-quality bar charts and scatter plots from query data</li>
    <li><code>show()</code> provides quick built-in visualization without extra dependencies</li>
  </ul>
</div>
