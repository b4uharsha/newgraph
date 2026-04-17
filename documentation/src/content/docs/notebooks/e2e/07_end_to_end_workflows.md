---
title: "End-to-End Workflows"
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
  <h1 class="nb-header__title">End-to-End Workflows</h1>
  <p class="nb-header__subtitle">Complete multi-step user journeys</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">15 min</span>
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
# Note: Uses GRAPH_OLAP_API_URL from environment (set by JupyterHub or local dev)
EXPECTED_NODE_COUNT = 5
EXPECTED_EDGE_COUNT = 6
```

<div class="nb-section">
  <span class="nb-section__number">1</span>
  <div>
    <h2 class="nb-section__title">Setup</h2>
  </div>
</div>

```python
import sys
import os

print(f"Python version: {sys.version}")
print(f"GRAPH_OLAP_API_URL: {os.environ.get('GRAPH_OLAP_API_URL', 'not set')}")
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
ctx = setup(prefix="WorkflowTest", persona=Persona.ANALYST_ALICE)
client = ctx.client

# Define test data
customer_node = CUSTOMER_NODE

shares_account_edge = SHARES_ACCOUNT_EDGE

print(f"Test run ID: {ctx.run_id}")
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Start Cleanup Context Manager</h2>
    <p class="nb-section__description">All resources created from here will be automatically cleaned up.</p>
  </div>
</div>

```python
# Resources are automatically tracked and cleaned up via ctx
print("Starting Workflow E2E Test - resources will be cleaned up automatically via atexit")
```

```python
# Create base mapping using ctx.mapping (auto-tracked)
mapping = ctx.mapping(
    description="Mapping for workflow testing",
    node_definitions=[customer_node],
    edge_definitions=[shares_account_edge],
)
MAPPING_ID = mapping.id
MAPPING_NAME = mapping.name

print(f"Created mapping: {MAPPING_NAME} (id={MAPPING_ID})")
```

```python
# Create instance directly from mapping
print(f"Creating instance directly from mapping ...")

instance = client.instances.create_and_wait(
    mapping_id=MAPPING_ID,
    name=f"WorkflowTest-Instance-{ctx.run_id}",
    wrapper_type=WrapperType.RYUGRAPH,
    timeout=300,  # Longer timeout for data export
    poll_interval=5,
)
INSTANCE_ID = instance.id
INSTANCE_NAME = instance.name
ctx.track('instance', INSTANCE_ID, INSTANCE_NAME)

print(f"Created instance: {INSTANCE_NAME} (id={INSTANCE_ID}, status={instance.status})")
```

```python
# This cell is kept for compatibility but the work is done in the previous cell
print(f"Instance already created: {INSTANCE_NAME} (id={INSTANCE_ID}, status={instance.status})")
```

```python
# Connect to instance via ctx
conn = ctx.connect(instance)
print(f"Connected to instance {INSTANCE_ID}")
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Complete Analyst Workflow</h2>
    <p class="nb-section__description">Simulates a typical analyst journey: mapping -> instance -> query -> algorithm</p>
  </div>
</div>

```python
# Step 1: List mappings
mappings = client.mappings.list()
assert len(mappings) > 0, "Should have at least one mapping"
print(f"WF 1.1: Found {len(mappings)} mapping(s)")

# Step 2: Get our mapping
mapping_fetched = client.mappings.get(MAPPING_ID)
assert mapping_fetched.name == MAPPING_NAME
print(f"WF 1.2: Got mapping '{mapping_fetched.name}'")

# Step 3: Get mapping version to understand schema
version = client.mappings.get_version(MAPPING_ID, version=1)
assert len(version.node_definitions) >= 1
assert len(version.edge_definitions) >= 1
print(f"WF 1.3: Mapping has {len(version.node_definitions)} node(s), {len(version.edge_definitions)} edge(s)")

# Step 4: Verify instance is running
instance_check = client.instances.get(INSTANCE_ID)
assert instance_check.status == "running", f"Expected 'running', got '{instance_check.status}'"
print(f"WF 1.4: Instance '{instance_check.name}' is {instance_check.status}")

# Step 5: Query the graph
count = conn.query_scalar("MATCH (c:Customer) RETURN count(c)")
assert count == EXPECTED_NODE_COUNT
print(f"WF 1.5: Graph has {count} Customer nodes")

# Step 6: Run algorithm
execution = conn.algo.pagerank(
    node_label="Customer",
    property_name="wf_analyst_pr",
    edge_type="SHARES_ACCOUNT"
)
assert execution.status == "completed"
print(f"WF 1.6: PageRank completed, {execution.nodes_updated} nodes updated")

# Track algorithm property for cleanup
ctx.track('graph_properties', conn, {'node_label': 'Customer', 'property_names': ['wf_analyst_pr']})

# Step 7: Query algorithm results
df = conn.query_df("""
    MATCH (c:Customer)
    RETURN c.id AS id, c.wf_analyst_pr AS pagerank
    ORDER BY c.wf_analyst_pr DESC
""")
assert len(df) == EXPECTED_NODE_COUNT
print("WF 1.7: Retrieved PageRank results")

print("\nWorkflow 1 PASSED: Complete analyst workflow verified")
print(df)
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Data Exploration Workflow</h2>
    <p class="nb-section__description">Simulates exploring an unfamiliar graph: schema -> counts -> samples -> stats</p>
  </div>
</div>

```python
# Step 1: Get schema
schema = conn.get_schema()
assert len(schema.node_labels) >= 1
assert len(schema.relationship_types) >= 1
print(f"WF 2.1: Schema has {len(schema.node_labels)} node label(s), {len(schema.relationship_types)} relationship type(s)")
print(f"  Node labels: {list(schema.node_labels.keys())}")
print(f"  Relationships: {list(schema.relationship_types.keys())}")

# Step 2: Count nodes and edges
node_count = conn.query_scalar("MATCH (n) RETURN count(n)")
edge_count = conn.query_scalar("MATCH ()-[r]->() RETURN count(r)")
assert node_count == EXPECTED_NODE_COUNT
assert edge_count == EXPECTED_EDGE_COUNT
print(f"WF 2.2: Graph size: {node_count} nodes, {edge_count} edges")

# Step 3: Sample data
sample = conn.query("MATCH (c:Customer) RETURN c.id, c.bk_sectr LIMIT 3")
assert sample.row_count == 3
print("WF 2.3: Sample data:")
for row in sample.rows:
    print(f"  {row[0]}: sector {row[1]}")

# Step 4: Aggregations with stats
# NOTE: Only bk_sectr, account_count, and acct_stus are declared in the mapping properties,
# so acct_stus is NOT available in the graph even though it appears in the SQL SELECT.
# Use only mapped properties for Cypher queries.
stats = conn.query("""
    MATCH (c:Customer)
    RETURN
        count(DISTINCT c.bk_sectr) AS distinct_sectors,
        count(c) AS total_customers,
        count(DISTINCT c.id) AS distinct_ids,
        count(c) AS total
""")
assert stats.row_count == 1
row = stats.rows[0]
assert row[0] >= 1, f"Expected at least 1 distinct sector, got {row[0]}"
assert row[1] >= 1, f"Expected at least 1 customer, got {row[1]}"
assert row[3] == EXPECTED_NODE_COUNT
print(f"WF 2.4: Data stats: sectors={row[0]}, customers={row[1]}, ids={row[2]}, count={row[3]}")

print("\nWorkflow 2 PASSED: Data exploration workflow verified")
```

<div class="nb-section">
  <span class="nb-section__number">5</span>
  <div>
    <h2 class="nb-section__title">Chained Operations Pattern</h2>
    <p class="nb-section__description">Tests that operations can be chained together fluently</p>
  </div>
</div>

```python
# Run algorithm and immediately query results
conn.algo.pagerank("Customer", "wf_chain_pr", edge_type="SHARES_ACCOUNT")

# Track algorithm property for cleanup
ctx.track('graph_properties', conn, {'node_label': 'Customer', 'property_names': ['wf_chain_pr']})

top_score = conn.query_scalar("""
    MATCH (c:Customer)
    RETURN max(c.wf_chain_pr)
""")
assert top_score > 0

print(f"Workflow 3 PASSED: Chained operations (top score: {top_score:.4f})")
```

<div class="nb-section">
  <span class="nb-section__number">6</span>
  <div>
    <h2 class="nb-section__title">DataFrame-Centric Workflow</h2>
    <p class="nb-section__description">Tests working primarily with DataFrames for data analysis</p>
  </div>
</div>

```python
# Get data as DataFrame
df = conn.query_df("MATCH (c:Customer) RETURN c.id AS id, c.bk_sectr AS bk_sectr")

assert len(df) == EXPECTED_NODE_COUNT
assert "id" in df.columns
assert "bk_sectr" in df.columns

# Basic DataFrame operations
# bk_sectr is STRING, use count instead
customer_count = len(df)
sector_count = df["bk_sectr"].n_unique()
type_count = df.get_column("acct_stus").n_unique() if "acct_stus" in df.columns else 0

print("Workflow 4 PASSED: DataFrame-centric workflow")
print(f"  Shape: {df.shape}")
print(f"  Data stats: customers={customer_count}, sectors={sector_count}")
print(df)
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li>All end-to-end workflows tests validated</li>
    <li>Resources cleaned up automatically via test context</li>
    <li>Zero residual state on the cluster</li>
  </ul>
</div>

```python
# Teardown test resources
ctx.teardown()

print("\nResources cleaned up")
```

```python
# Workflow tests completed
print("Workflow tests completed")
```

```python
print("\n" + "="*60)
print("WORKFLOW E2E TESTS COMPLETED!")
print("="*60)
print("\nValidated:")
print("  1. Complete Analyst Workflow:")
print("    - Mapping -> Instance -> Query -> Algorithm")
print("  2. Data Exploration Workflow:")
print("    - Schema -> Counts -> Samples -> Stats")
print("  3. Chained Operations Pattern:")
print("    - Algorithm execution followed by query")
print("  4. DataFrame-Centric Workflow:")
print("    - Query to DataFrame -> Analysis")
print("\nNote: Centrality and community detection algorithms are")
print("      tested in sdk_algorithm_test.ipynb")
print("\nAll resources will be cleaned up automatically via atexit")
```
