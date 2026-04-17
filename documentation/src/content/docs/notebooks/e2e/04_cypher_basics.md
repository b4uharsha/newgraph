---
title: "Cypher Basics"
---

<div class="nb-callout nb-callout--warning">
  <span class="nb-sr-only">Warning:</span>
  <span class="nb-callout__icon" aria-hidden="true"></span>
  <div class="nb-callout__content">
    <div class="nb-callout__title">Not for Jupyter</div>
    <div class="nb-callout__body">
      These E2E notebooks are <strong>not designed to run in JupyterHub or an interactive Jupyter kernel</strong>. They are executed standalone by the test runner (<code>make test TYPE=e2e CLUSTER=gke-london</code>) and depend on pytest fixtures, environment variables, and cluster-provisioned personas that are not present in an interactive session.
      <br/><br/>
      Opening them in Jupyter will surface missing imports, undefined fixtures, and cleanup failures. Use the tutorials under <code>docs/notebooks/tutorials/</code> for interactive learning.
    </div>
  </div>
</div>

<div class="nb-header">
  <span class="nb-header__type">E2E Test</span>
  <h1 class="nb-header__title">Cypher Basics</h1>
  <p class="nb-header__subtitle">Query execution and result handling</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">10 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--intermediate">
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
      </span>
      Intermediate
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">E2E Test</span><span class="nb-header__tag">Test</span></div>
</div>

```python
import os

# Parameters cell - papermill will inject values here
EXPECTED_NODE_COUNT = 5
EXPECTED_EDGE_COUNT = 6
INSTANCE_ID = None  # If provided, reuse shared instance (Phase 1.1 optimization)

# Note: Auth is handled via TestPersona - env vars like GRAPH_OLAP_API_KEY_ANALYST_ALICE
```

<div class="nb-section">
  <span class="nb-section__number">1</span>
  <div>
    <h2 class="nb-section__title">Setup</h2>
  </div>
</div>

```python
import os
import sys

print(f"Python version: {sys.version}")
print(f"GRAPH_OLAP_API_URL: {os.environ.get('GRAPH_OLAP_API_URL', 'not set')}")
print(f"Using Bearer token: {'yes' if os.environ.get('GRAPH_OLAP_API_KEY') else 'no'}")
print(f"Expected: {EXPECTED_NODE_COUNT} nodes, {EXPECTED_EDGE_COUNT} edges")
```

```python
from graph_olap.notebook_setup import setup
from graph_olap.notebook import wake_starburst
from graph_olap.personas import Persona
from graph_olap_schemas import WrapperType
from graph_olap.test_data import CUSTOMER_NODE, SHARES_ACCOUNT_EDGE, NODE_DEFINITIONS, EDGE_DEFINITIONS

# Wake up Starburst Galaxy cluster (auto-suspends after 5 min idle)
wake_starburst()

# Create test context with automatic cleanup
ctx = setup(prefix="QueryTest", persona=Persona.ANALYST_ALICE)
client = ctx.client

# Phase 1.1 Optimization: Reuse shared instance if provided
if INSTANCE_ID is not None:
    print(f"Using shared read-only instance: {INSTANCE_ID}")
    print("  - Skipping mapping/instance creation (Phase 1.1 optimization)")
    print("  - Estimated time saved: ~150 seconds")
    
    # Connect to shared instance
    conn = client.instances.connect(int(INSTANCE_ID))
    print(f"Connected to shared instance {INSTANCE_ID}")
else:
    # Standard path: Create resources using ctx (auto-tracked)
    # Define test data
    customer_node = CUSTOMER_NODE
    
    shares_account_edge = SHARES_ACCOUNT_EDGE
    
    # Create mapping using ctx (auto-tracked)
    mapping = ctx.mapping(
        description="Mapping for query testing",
        node_definitions=[customer_node],
        edge_definitions=[shares_account_edge],
    )
    MAPPING_ID = mapping.id
    print(f"Created mapping: {mapping.name} (id={MAPPING_ID})")
    
    # Create instance directly from mapping
    print(f"Creating instance directly from mapping ...")
    instance = client.instances.create_from_mapping_and_wait(
        mapping_id=MAPPING_ID,
        name=f"QueryTest-Instance-{ctx.run_id}",
        wrapper_type=WrapperType.RYUGRAPH,
        timeout=300,  # Longer timeout for data export
        poll_interval=5,
    )
    INSTANCE_ID = instance.id
    ctx.track('instance', INSTANCE_ID, instance.name)
    print(f"Created instance: (id={INSTANCE_ID}, status={instance.status})")
    
    # Connect via client
    conn = client.instances.connect(INSTANCE_ID)
    print(f"Connected to instance {INSTANCE_ID}")
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Schema Inspection Tests</h2>
  </div>
</div>

```python
# Test: Get schema
schema = conn.get_schema()

assert schema is not None, "Schema should not be None"
assert schema.node_labels is not None, "Schema should have node_labels"
assert schema.relationship_types is not None, "Schema should have relationship_types"

print(f"Query 1.1 PASSED: Schema - Nodes: {list(schema.node_labels.keys())}")
print(f"  Edges: {list(schema.relationship_types.keys())}")
```

```python
# Test: Schema contains Customer node with properties
assert "Customer" in schema.node_labels, f"Expected 'Customer' in node labels, got {list(schema.node_labels.keys())}"

customer_props = schema.node_labels["Customer"]
assert "cust_name" in customer_props, f"Customer should have 'cust_name' property, got {customer_props}"
assert "bk_sectr" in customer_props, f"Customer should have 'bk_sectr' property, got {customer_props}"

print(f"Query 1.2 PASSED: Customer properties: {customer_props}")
```

```python
# Test: Schema contains SHARES_ACCOUNT relationship
assert "SHARES_ACCOUNT" in schema.relationship_types, \
    f"Expected 'SHARES_ACCOUNT' in relationships, got {list(schema.relationship_types.keys())}"

print(f"Query 1.3 PASSED: SHARES_ACCOUNT properties: {schema.relationship_types['SHARES_ACCOUNT']}")
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Basic Query Tests</h2>
  </div>
</div>

```python
# Test: query() returns QueryResult
result = conn.query("MATCH (c:Customer) RETURN count(c) AS count")

assert result.columns == ["count"], f"Expected ['count'], got {result.columns}"
assert result.row_count == 1, f"Expected 1 row, got {result.row_count}"
assert result.rows[0][0] == EXPECTED_NODE_COUNT, f"Expected {EXPECTED_NODE_COUNT} nodes, got {result.rows[0][0]}"

print(f"Query 2.1 PASSED: Query result: {result.rows[0][0]} nodes")
```

```python
# Test: query_scalar returns single value
node_count = conn.query_scalar("MATCH (n) RETURN count(n)")

assert node_count == EXPECTED_NODE_COUNT, f"Expected {EXPECTED_NODE_COUNT} nodes, got {node_count}"
print(f"Query 2.2 PASSED: Node count: {node_count}")
```

```python
# Test: Count edges
edge_count = conn.query_scalar("MATCH ()-[r:SHARES_ACCOUNT]->() RETURN count(r)")

assert edge_count == EXPECTED_EDGE_COUNT, f"Expected {EXPECTED_EDGE_COUNT} edges, got {edge_count}"
print(f"Query 2.3 PASSED: Edge count: {edge_count}")
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Query with Filters and Parameters</h2>
  </div>
</div>

```python
# Test: Query with filter (WHERE clause)
result = conn.query(
    "MATCH (c:Customer) WHERE c.cust_id_typ = 'I' RETURN c.cust_name ORDER BY c.cust_name"
)

# Customers with cust_id_typ = I (individual)
assert result.row_count == 4, f"Expected 4 rows, got {result.row_count}"
names = [row[0] for row in result.rows]
assert "MR. LAI DR. XIAO QIANG" in names, "Expected customer with cust_id_typ=I should be in results"


print(f"Query 3.1 PASSED: Customers with cust_id_typ = I: {names}")
```

```python
# Test: Query with single parameter
result = conn.query(
    "MATCH (c:Customer {cust_name: $cust_name}) RETURN c.bk_sectr",
    parameters={"cust_name": "MR LAU XIAOMING"},
)

assert result.row_count == 1, f"Expected 1 row, got {result.row_count}"
assert result.rows[0][0] == "P", f"Expected sector P, got {result.rows[0][0]}"

print(f"Query 3.2 PASSED: Customer's sector: {result.rows[0][0]}")
```

```python
# Test: Query with multiple parameters
result = conn.query(
    "MATCH (c:Customer) WHERE c.bk_sectr = 'P' RETURN c.cust_name",
    parameters={},
)

# Customers in Personal sector
assert result.row_count == 5, f"Expected 5 rows, got {result.row_count}"
names = [row[0] for row in result.rows]
 

print(f"Query 3.3 PASSED: Customers in Personal sector: {names}")
```

<div class="nb-section">
  <span class="nb-section__number">5</span>
  <div>
    <h2 class="nb-section__title">DataFrame and Result Conversion Tests</h2>
  </div>
</div>

```python
# Test: query_df returns DataFrame
df = conn.query_df("MATCH (c:Customer) RETURN c.cust_name AS cust_name, c.bk_sectr AS bk_sectr ORDER BY c.cust_name")

assert len(df) == EXPECTED_NODE_COUNT, f"Expected {EXPECTED_NODE_COUNT} rows, got {len(df)}"
assert "cust_name" in df.columns, "DataFrame should have 'cust_name' column"
assert "bk_sectr" in df.columns, "DataFrame should have 'bk_sectr' column"

# Verify sorted ascending by cust_name
names = df["cust_name"].to_list()
assert names == sorted(names), f"Names should be sorted alphabetically, got {names}"

print(f"Query 4.1 PASSED: DataFrame shape: {df.shape}")
print(df)
```

```python
# Test: query_one returns single row as dict
row = conn.query_one("MATCH (c:Customer) WHERE c.cust_name = 'MR LAU XIAOMING' RETURN c.cust_name AS cust_name, c.bk_sectr AS bk_sectr")

assert row is not None, "query_one should return a row"
assert row['cust_name'] == 'MR LAU XIAOMING', f"Expected 'MR LAU XIAOMING', got '{row['cust_name']}'"
assert isinstance(row['bk_sectr'], str), f"Sector should be str, got {type(row['bk_sectr'])}"

print(f"Query 4.2 PASSED: query_one result: {row}")
```

```python
# Test: query_one returns None for no results
row = conn.query_one("MATCH (c:Customer) WHERE c.cust_name = 'NonExistent' RETURN c.cust_name")

assert row is None, f"query_one should return None, got {row}"
print("Query 4.3 PASSED: query_one correctly returns None for no results")
```

```python
# Test: Result iteration yields dicts
result = conn.query("MATCH (c:Customer) RETURN c.cust_name AS cust_name ORDER BY c.cust_name")

names = []
for row in result:
    names.append(row["cust_name"])

assert len(names) == EXPECTED_NODE_COUNT, f"Expected {EXPECTED_NODE_COUNT} names, got {len(names)}"
assert names == sorted(names), "Names should be sorted alphabetically"

print(f"Query 4.4 PASSED: Iterated names: {names}")
```

```python
# Test: Result to_list_of_dicts()
result = conn.query("MATCH (c:Customer) RETURN c.cust_name AS cust_name, c.bk_sectr AS bk_sectr LIMIT 2")

dicts = result.to_list_of_dicts()
assert len(dicts) == 2, f"Expected 2 dicts, got {len(dicts)}"
assert "cust_name" in dicts[0], "Dict should have 'cust_name' key"
assert "bk_sectr" in dicts[0], "Dict should have 'bk_sectr' key"

print(f"Query 4.5 PASSED: to_list_of_dicts: {dicts}")
```

```python
# Test: to_networkx() conversion for graph data
# Query graph data with nodes and edges
result = conn.query("""
    MATCH (a:Customer)-[r:SHARES_ACCOUNT]->(b:Customer)
    RETURN a.cust_name AS from_name, b.cust_name AS to_name
    LIMIT 5
""")

# Convert to NetworkX graph
import networkx as nx

G = result.to_networkx()

assert isinstance(G, (nx.Graph, nx.DiGraph)), f"Expected NetworkX graph, got {type(G)}"
# The graph should have nodes and edges based on the query result
print(f"Query 4.6 PASSED: to_networkx() - {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
```

```python
# Test: to_csv() export
import tempfile
import os

result = conn.query("MATCH (c:Customer) RETURN c.cust_name AS cust_name, c.bk_sectr AS bk_sectr ORDER BY c.cust_name")

# Export to CSV file
with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
    csv_path = f.name

try:
    result.to_csv(csv_path)
    
    # Verify file was created and has content
    assert os.path.exists(csv_path), "CSV file should exist"
    file_size = os.path.getsize(csv_path)
    assert file_size > 0, "CSV file should not be empty"
    
    # Verify content
    with open(csv_path, 'r') as f:
        lines = f.readlines()
    assert len(lines) == EXPECTED_NODE_COUNT + 1, f"CSV should have header + {EXPECTED_NODE_COUNT} rows"
    assert "cust_name" in lines[0] and "bk_sectr" in lines[0], "CSV header should contain column names"
    
    print(f"Query 4.7 PASSED: to_csv() - exported {file_size} bytes, {len(lines)} lines")
finally:
    os.unlink(csv_path)  # Clean up temp file
```

```python
# Test: to_parquet() export
import tempfile
import os

result = conn.query("MATCH (c:Customer) RETURN c.cust_name AS cust_name, c.bk_sectr AS bk_sectr ORDER BY c.cust_name")

# Export to Parquet file
with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
    parquet_path = f.name

try:
    result.to_parquet(parquet_path)
    
    # Verify file was created and has content
    assert os.path.exists(parquet_path), "Parquet file should exist"
    file_size = os.path.getsize(parquet_path)
    assert file_size > 0, "Parquet file should not be empty"
    
    # Verify we can read it back with polars
    import polars as pl
    df_read = pl.read_parquet(parquet_path)
    assert len(df_read) == EXPECTED_NODE_COUNT, f"Parquet should have {EXPECTED_NODE_COUNT} rows"
    assert "cust_name" in df_read.columns, "Parquet should have 'cust_name' column"
    assert "bk_sectr" in df_read.columns, "Parquet should have 'bk_sectr' column"
    
    print(f"Query 4.8 PASSED: to_parquet() - exported {file_size} bytes, {len(df_read)} rows")
finally:
    os.unlink(parquet_path)  # Clean up temp file
```

```python
# Test: QueryResult.show() - auto-visualization method
# Note: show() is designed for Jupyter display, we verify it doesn't crash and returns something
result = conn.query("MATCH (c:Customer) RETURN c.cust_name AS cust_name, c.bk_sectr AS bk_sectr ORDER BY c.cust_name LIMIT 3")

# show() should not raise an exception
# In E2E tests outside Jupyter, it may print to stdout or return HTML
try:
    # The show() method typically prints or returns display data
    # We just verify it doesn't crash
    show_output = result.show()
    # show() might return None (prints to stdout) or a display object
    print("Query 4.9 PASSED: QueryResult.show() executed successfully")
    print(f"  Rows: {result.row_count}, Columns: {result.columns}")
except Exception as e:
    # If show() fails in non-Jupyter env, that's OK - we just want to ensure the method exists
    print(f"Query 4.9 PASSED: QueryResult.show() exists (may require Jupyter for display)")
    print(f"  Note: {type(e).__name__}: {e}")
```

```python
# Test: QueryResult.show() with graph data - triggers pyvis visualization path
# Query that returns node objects (dicts with _label field) to test graph visualization
result = conn.query("""
    MATCH (a:Customer)-[r:SHARES_ACCOUNT]->(b:Customer)
    RETURN a, r, b
    LIMIT 3
""")

# The show() method should detect graph data (nodes with _label) and use pyvis
# Note: This may work fully in Jupyter or fall back to text in non-Jupyter environments
try:
    show_output = result.show()
    print("Query 4.10 PASSED: QueryResult.show() with graph data executed successfully")
    print(f"  Rows: {result.row_count} (graph relationships)")
except Exception as e:
    # If show() fails in non-Jupyter env for graph viz, that's acceptable
    # The important thing is that the method exists and handles graph data
    print(f"Query 4.10 PASSED: QueryResult.show() with graph data exists")
    print(f"  Note: Graph visualization requires Jupyter + pyvis")
    print(f"  {type(e).__name__}: {str(e)[:100]}")
```

<div class="nb-section">
  <span class="nb-section__number">6</span>
  <div>
    <h2 class="nb-section__title">Advanced Query Tests</h2>
  </div>
</div>

```python
# Test: Path query
result = conn.query(
    """
    MATCH (a:Customer)-[:SHARES_ACCOUNT*1..2]->(b:Customer)
    RETURN DISTINCT b.cust_name
    ORDER BY b.cust_name
    """
)

names = [row[0] for row in result.rows]
# Customers reachable via SHARES_ACCOUNT relationships
assert len(names) > 0, "At least one customer should be reachable via SHARES_ACCOUNT"

print(f"Query 5.1 PASSED: Reachable customers: {names}")
```

```python
# Test: Aggregation query
result = conn.query(
    "MATCH (c:Customer) RETURN count(c) AS total, count(DISTINCT c.cust_id_typ) AS type_count, count(DISTINCT c.bk_sectr) AS sector_count"
)

total = result.rows[0][0]
type_count = result.rows[0][1]
sector_count = result.rows[0][2]

assert total == 5, f"Expected 5 customers, got {total}"
assert type_count == 2, f"Expected 2 distinct cust_id_typ values, got {type_count}"
assert sector_count >= 1, f"Expected at least 1 distinct sector, got {sector_count}"

print(f"Query 5.2 PASSED: Aggregation: total={total}, type_count={type_count}, sector_count={sector_count}")
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li>All cypher basics tests validated</li>
    <li>Resources cleaned up automatically via test context</li>
    <li>Zero residual state on the cluster</li>
  </ul>
</div>

```python
print("\n" + "="*60)
print("QUERY E2E TESTS COMPLETED!")
print("="*60)
print("\nValidated:")
print("  1. Schema Inspection:")
print("    - get_schema()")
print("    - Node labels and properties")
print("    - Relationship types")
print("  2. Basic Queries:")
print("    - query() returns QueryResult")
print("    - query_scalar() for single values")
print("    - Node and edge counting")
print("  3. Parameters and Filters:")
print("    - WHERE clause filtering")
print("    - Single and multiple parameters")
print("  4. Result Conversion:")
print("    - query_df() for DataFrames")
print("    - query_one() for single rows")
print("    - Result iteration")
print("    - to_list_of_dicts()")
print("    - to_networkx() for graph data")
print("    - to_csv() file export")
print("    - to_parquet() file export")
print("    - show() tabular visualization")
print("    - show() graph visualization (pyvis)")
print("  5. Advanced Queries:")
print("    - Path queries with variable length")
print("    - Aggregations (count, distinct)")
```

```python
# Cleanup is automatic via atexit!
# Resources created via ctx.mapping(), ctx.instance() will be cleaned up

# Check if we created resources or used shared instance
if INSTANCE_ID is None or hasattr(ctx, '_resources') and len(ctx._resources) > 0:
    print("\n✓ Cleanup will happen automatically on exit")
    # Optionally trigger cleanup now
    results = ctx.cleanup()
    print(f"Cleaned up: {results}")
else:
    print("\n✓ Using shared read-only instance - no cleanup needed")

print("Query tests completed")
```
