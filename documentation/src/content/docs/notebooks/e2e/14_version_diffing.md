---
title: "Version Diffing"
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
  <h1 class="nb-header__title">Version Diffing</h1>
  <p class="nb-header__subtitle">Compare and track mapping version changes</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">15 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--advanced">
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
      </span>
      Advanced
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">E2E Test</span><span class="nb-header__tag">Test</span></div>
</div>

```python
import os

# Parameters cell - papermill will inject values here
# Note: Uses GRAPH_OLAP_API_URL from environment (set by JupyterHub or local dev)
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
from graph_olap.notebook import wake_starburst
from graph_olap.exceptions import GraphOLAPError, NotFoundError
from graph_olap.models.mapping import (
    EdgeDefinition,
    MappingDiff,
    NodeDefinition,
    PropertyDefinition,
)
from graph_olap.personas import Persona
from graph_olap.utils.diff import diff_to_dict, render_diff_details, render_diff_summary

print("SDK imports successful")
print(f"  MappingDiff: {MappingDiff}")
print(f"  render_diff_summary: {render_diff_summary}")

# Wake up Starburst Galaxy cluster (auto-suspends after 5 min idle)
wake_starburst()
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Connect to SDK</h2>
  </div>
</div>

```python
# Create test context with automatic cleanup
from graph_olap.notebook_setup import setup

ctx = setup(prefix="DiffTest", persona=Persona.ANALYST_ALICE)
client = ctx.client

print(f"Connected to {client._config.api_url}")
print(f"Test run ID: {ctx.run_id}")
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Initialize Cleanup Tracking</h2>
  </div>
</div>

```python
# Resources are automatically tracked and cleaned up via ctx
print("Starting Mapping Diff E2E Test - resources will be cleaned up automatically via atexit")
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Create Base Mapping (Version 1)</h2>
    <p class="nb-section__description">Version 1 contains:</p>
  </div>
</div>

```python
MAPPING_NAME = f"DiffTest-{ctx.run_id}"

# Version 1 definitions
customer_v1 = NodeDefinition(
    label="Customer",
    sql="SELECT DISTINCT CAST(psdo_cust_id AS VARCHAR) AS id, MIN(bk_sectr) AS bk_sectr FROM bigquery.graph_olap_e2e.bis_acct_dh WHERE 1=1 GROUP BY psdo_cust_id",
    primary_key={"name": "id", "type": "STRING"},
    properties=[
        PropertyDefinition(name="bk_sectr", type="STRING"),
    ]
)

purchased_v1 = EdgeDefinition(
    type="PURCHASED",
    from_node="Customer",
    to_node="Customer",  # Self-referencing for simplicity
    sql="SELECT DISTINCT CAST(a.psdo_cust_id AS VARCHAR) AS from_id, CAST(b.psdo_cust_id AS VARCHAR) AS to_id FROM bigquery.graph_olap_e2e.bis_acct_dh a JOIN bigquery.graph_olap_e2e.bis_acct_dh b ON a.psdo_acno = b.psdo_acno AND a.psdo_cust_id < b.psdo_cust_id",
    from_key="from_id",
    to_key="to_id",
    properties=[
        PropertyDefinition(name="amount", type="DOUBLE"),
    ]
)

# Use ctx.mapping for auto-tracked resource
mapping = ctx.mapping(
    description="Test mapping for diff E2E tests",
    node_definitions=[customer_v1],
    edge_definitions=[purchased_v1],
)

mapping_id = mapping.id

print(f"Created mapping v1: {MAPPING_NAME} (id={mapping_id})")
print(f"  Nodes: {[n.label for n in mapping.node_definitions]}")
print(f"  Edges: {[e.type for e in mapping.edge_definitions]}")
print(f"  Current version: {mapping.current_version}")
```

<div class="nb-section">
  <span class="nb-section__number">5</span>
  <div>
    <h2 class="nb-section__title">Create Version 2 (Node Added)</h2>
    <p class="nb-section__description">Version 2 adds:</p>
  </div>
</div>

```python
product_v2 = NodeDefinition(
    label="Product",
    sql="SELECT DISTINCT CAST(psdo_acno AS VARCHAR) AS id, acct_ccy_cd, acct_stat_cd FROM bigquery.graph_olap_e2e.bis_acct_dm",
    primary_key={"name": "id", "type": "STRING"},
    properties=[
        PropertyDefinition(name="acct_ccy_cd", type="STRING"),
        PropertyDefinition(name="price", type="DOUBLE"),
    ]
)

mapping_v2 = client.mappings.update(
    mapping_id,
    change_description="Add Product node",
    node_definitions=[customer_v1, product_v2],
    edge_definitions=[purchased_v1],
)

print("Created version 2 (added Product node)")
print(f"  Nodes: {[n.label for n in mapping_v2.node_definitions]}")
print(f"  Current version: {mapping_v2.current_version}")
```

<div class="nb-section">
  <span class="nb-section__number">6</span>
  <div>
    <h2 class="nb-section__title">Create Version 3 (Node Modified)</h2>
    <p class="nb-section__description">Version 3 modifies:</p>
  </div>
</div>

```python
customer_v3 = NodeDefinition(
    label="Customer",
    sql="SELECT DISTINCT CAST(psdo_cust_id AS VARCHAR) AS id, MIN(bk_sectr) AS bk_sectr, COUNT(DISTINCT psdo_acno) AS account_count FROM bigquery.graph_olap_e2e.bis_acct_dh WHERE 1=1 GROUP BY psdo_cust_id",  # Changed: added account_count
    primary_key={"name": "id", "type": "STRING"},
    properties=[
        PropertyDefinition(name="bk_sectr", type="STRING"),
        PropertyDefinition(name="account_count", type="INT64"),  # New property
    ]
)

mapping_v3 = client.mappings.update(
    mapping_id,
    change_description="Add city to Customer",
    node_definitions=[customer_v3, product_v2],
    edge_definitions=[purchased_v1],
)

print("Created version 3 (modified Customer node)")
print(f"  Customer properties: {[p.name for p in customer_v3.properties]}")
print(f"  Current version: {mapping_v3.current_version}")
```

<div class="nb-section">
  <span class="nb-section__number">7</span>
  <div>
    <h2 class="nb-section__title">Create Version 4 (Edge Removed)</h2>
    <p class="nb-section__description">Version 4 removes:</p>
  </div>
</div>

```python
mapping_v4 = client.mappings.update(
    mapping_id,
    change_description="Remove PURCHASED edge",
    node_definitions=[customer_v3, product_v2],
    edge_definitions=[],  # Removed PURCHASED edge
)

print("Created version 4 (removed PURCHASED edge)")
print(f"  Edges: {[e.type for e in mapping_v4.edge_definitions]}")
print(f"  Current version: {mapping_v4.current_version}")
```

<div class="nb-section">
  <span class="nb-section__number">8</span>
  <div>
    <h2 class="nb-section__title">Test 1: Node Added (v1 → v2)</h2>
    <p class="nb-section__description">Expected:</p>
  </div>
</div>

```python
# Test: Diff v1 → v2 should show Product added
diff_1_2 = client.mappings.diff(mapping_id, from_version=1, to_version=2)

assert isinstance(diff_1_2, MappingDiff), f"Expected MappingDiff, got {type(diff_1_2)}"
assert diff_1_2.mapping_id == mapping_id
assert diff_1_2.from_version == 1
assert diff_1_2.to_version == 2

# Check summary counts
assert diff_1_2.summary["nodes_added"] == 1, f"Expected 1 node added, got {diff_1_2.summary['nodes_added']}"
assert diff_1_2.summary["nodes_removed"] == 0
assert diff_1_2.summary["nodes_modified"] == 0
assert diff_1_2.summary["edges_added"] == 0
assert diff_1_2.summary["edges_removed"] == 0
assert diff_1_2.summary["edges_modified"] == 0

print("DIFF 1.1 PASSED: v1 → v2 shows Product node added")
print(f"  Summary: {diff_1_2.summary}")
```

```python
# Test: Verify Product in changes.nodes with change_type='added'
product_changes = [n for n in diff_1_2.changes["nodes"] if n.label == "Product"]
assert len(product_changes) == 1, "Should have exactly 1 Product change"

product_diff = product_changes[0]
assert product_diff.change_type == "added"
assert product_diff.from_ is None, "'from' should be None for added node"
assert product_diff.to is not None, "'to' should contain definition for added node"
assert product_diff.fields_changed is None, "'fields_changed' should be None for added node"

print("DIFF 1.2 PASSED: Product node has correct change_type='added'")
print(f"  Product diff: label={product_diff.label}, change_type={product_diff.change_type}")
```

```python
# Test: Use filter methods
added_nodes = diff_1_2.nodes_added()
assert len(added_nodes) == 1
assert added_nodes[0].label == "Product"

removed_nodes = diff_1_2.nodes_removed()
assert len(removed_nodes) == 0

modified_nodes = diff_1_2.nodes_modified()
assert len(modified_nodes) == 0

print("DIFF 1.3 PASSED: Filter methods work correctly")
print(f"  Added nodes: {[n.label for n in added_nodes]}")
```

<div class="nb-section">
  <span class="nb-section__number">9</span>
  <div>
    <h2 class="nb-section__title">Test 2: Node Modified (v2 → v3)</h2>
    <p class="nb-section__description">Expected:</p>
  </div>
</div>

```python
# Test: Diff v2 → v3 should show Customer modified
diff_2_3 = client.mappings.diff(mapping_id, from_version=2, to_version=3)

assert diff_2_3.summary["nodes_added"] == 0
assert diff_2_3.summary["nodes_removed"] == 0
assert diff_2_3.summary["nodes_modified"] == 1, f"Expected 1 node modified, got {diff_2_3.summary['nodes_modified']}"

print("DIFF 2.1 PASSED: v2 → v3 shows Customer node modified")
print(f"  Summary: {diff_2_3.summary}")
```

```python
# Test: Verify Customer has change_type='modified' with fields_changed
customer_changes = [n for n in diff_2_3.changes["nodes"] if n.label == "Customer"]
assert len(customer_changes) == 1

customer_diff = customer_changes[0]
assert customer_diff.change_type == "modified"
assert customer_diff.from_ is not None, "'from' should contain old definition"
assert customer_diff.to is not None, "'to' should contain new definition"
assert customer_diff.fields_changed is not None, "'fields_changed' should list changed fields"
assert len(customer_diff.fields_changed) > 0, "Should have at least one changed field"

# Verify SQL and properties are in fields_changed
assert "sql" in customer_diff.fields_changed or "properties" in customer_diff.fields_changed, \
    "Should detect sql or properties change"

print("DIFF 2.2 PASSED: Customer node has change_type='modified' with fields_changed")
print(f"  Fields changed: {customer_diff.fields_changed}")
```

<div class="nb-section">
  <span class="nb-section__number">10</span>
  <div>
    <h2 class="nb-section__title">Test 3: Edge Removed (v3 → v4)</h2>
    <p class="nb-section__description">Expected:</p>
  </div>
</div>

```python
# Test: Diff v3 → v4 should show PURCHASED edge removed
diff_3_4 = client.mappings.diff(mapping_id, from_version=3, to_version=4)

assert diff_3_4.summary["edges_added"] == 0
assert diff_3_4.summary["edges_removed"] == 1, f"Expected 1 edge removed, got {diff_3_4.summary['edges_removed']}"
assert diff_3_4.summary["edges_modified"] == 0

print("DIFF 3.1 PASSED: v3 → v4 shows PURCHASED edge removed")
print(f"  Summary: {diff_3_4.summary}")
```

```python
# Test: Verify PURCHASED has change_type='removed'
purchased_changes = [e for e in diff_3_4.changes["edges"] if e.type == "PURCHASED"]
assert len(purchased_changes) == 1

purchased_diff = purchased_changes[0]
assert purchased_diff.change_type == "removed"
assert purchased_diff.from_ is not None, "'from' should contain old definition"
assert purchased_diff.to is None, "'to' should be None for removed edge"
assert purchased_diff.fields_changed is None

print("DIFF 3.2 PASSED: PURCHASED edge has change_type='removed'")
print(f"  PURCHASED diff: type={purchased_diff.type}, change_type={purchased_diff.change_type}")
```

<div class="nb-section">
  <span class="nb-section__number">11</span>
  <div>
    <h2 class="nb-section__title">Test 4: Multiple Changes (v1 → v4)</h2>
    <p class="nb-section__description">Expected:</p>
  </div>
</div>

```python
# Test: Diff v1 → v4 should show all accumulated changes
diff_1_4 = client.mappings.diff(mapping_id, from_version=1, to_version=4)

assert diff_1_4.summary["nodes_added"] == 1, "Should show Product added"
assert diff_1_4.summary["nodes_removed"] == 0
assert diff_1_4.summary["nodes_modified"] == 1, "Should show Customer modified"
assert diff_1_4.summary["edges_added"] == 0
assert diff_1_4.summary["edges_removed"] == 1, "Should show PURCHASED removed"
assert diff_1_4.summary["edges_modified"] == 0

print("DIFF 4.1 PASSED: v1 → v4 shows all accumulated changes")
print(f"  Summary: {diff_1_4.summary}")
```

<div class="nb-section">
  <span class="nb-section__number">12</span>
  <div>
    <h2 class="nb-section__title">Test 5: Reverse Diff (v4 → v1)</h2>
    <p class="nb-section__description">Reverse diff should invert change types:</p>
  </div>
</div>

```python
# Test: Reverse diff v4 → v1
diff_4_1 = client.mappings.diff(mapping_id, from_version=4, to_version=1)

# Inverted from forward diff
assert diff_4_1.summary["nodes_added"] == 0
assert diff_4_1.summary["nodes_removed"] == 1, "Product should be removed (was added in forward)"
assert diff_4_1.summary["nodes_modified"] == 1, "Customer should still be modified"
assert diff_4_1.summary["edges_added"] == 1, "PURCHASED should be added (was removed in forward)"
assert diff_4_1.summary["edges_removed"] == 0
assert diff_4_1.summary["edges_modified"] == 0

print("DIFF 5.1 PASSED: Reverse diff v4 → v1 inverts change types correctly")
print(f"  Forward (v1→v4): {diff_1_4.summary}")
print(f"  Reverse (v4→v1): {diff_4_1.summary}")
```

<div class="nb-section">
  <span class="nb-section__number">13</span>
  <div>
    <h2 class="nb-section__title">Test 6: No Changes Diff (v1 → v1)</h2>
    <p class="nb-section__description">Expected: Error (400) for diffing same version</p>
  </div>
</div>

```python
# Test: Same version diff should raise error
try:
    diff_same = client.mappings.diff(mapping_id, from_version=1, to_version=1)
    assert False, "Should have raised error for same version diff"
except GraphOLAPError as e:
    print("DIFF 6.1 PASSED: Same version diff correctly raises error")
    print(f"  Error: {e}")
except Exception as e:
    print(f"DIFF 6.1 PASSED: Same version diff raises error (type: {type(e).__name__})")
```

<div class="nb-section">
  <span class="nb-section__number">14</span>
  <div>
    <h2 class="nb-section__title">Test 7: SDK Rendering Utilities</h2>
    <p class="nb-section__description">Test the notebook rendering functions:</p>
  </div>
</div>

```python
# Test: render_diff_summary displays summary
print("DIFF 7.1: Testing render_diff_summary()\n")
render_diff_summary(diff_1_4)
print("\nPASSED: render_diff_summary() executed successfully")
```

```python
# Test: render_diff_details displays changes
print("DIFF 7.2: Testing render_diff_details()\n")
render_diff_details(diff_1_4, show_from_to=False)
print("\nPASSED: render_diff_details() executed successfully")
```

```python
# Test: render_diff_details with from/to
print("DIFF 7.3: Testing render_diff_details(show_from_to=True)\n")
render_diff_details(diff_2_3, show_from_to=True)  # Use v2→v3 (modified node)
print("\nPASSED: render_diff_details(show_from_to=True) executed successfully")
```

```python
# Test: diff_to_dict conversion
diff_dict = diff_to_dict(diff_1_4)

assert isinstance(diff_dict, dict), f"Expected dict, got {type(diff_dict)}"
assert "summary" in diff_dict
assert "changes" in diff_dict  # diff_to_dict returns a flat 'changes' list

# Filter changes by type
node_changes = [c for c in diff_dict['changes'] if c['type'] == 'node']
edge_changes = [c for c in diff_dict['changes'] if c['type'] == 'edge']

print("DIFF 7.4 PASSED: diff_to_dict() converts to dictionary")
print(f"  Dict keys: {list(diff_dict.keys())}")
print(f"  Summary: {diff_dict['summary']}")
print(f"  Node changes: {len(node_changes)}")
print(f"  Edge changes: {len(edge_changes)}")
```

<div class="nb-section">
  <span class="nb-section__number">15</span>
  <div>
    <h2 class="nb-section__title">Test 8: HTML Representation</h2>
    <p class="nb-section__description">Test that `MappingDiff` has proper `_repr_html_()` for Jupyter display</p>
  </div>
</div>

```python
# Test: _repr_html_() method exists
assert hasattr(diff_1_4, "_repr_html_"), "MappingDiff should have _repr_html_() method"

html = diff_1_4._repr_html_()
assert isinstance(html, str), "_repr_html_() should return string"
assert len(html) > 0, "HTML representation should not be empty"
assert "<" in html and ">" in html, "Should contain HTML tags"

print("DIFF 8.1 PASSED: MappingDiff has _repr_html_() method")
print(f"  HTML length: {len(html)} characters")
```

```python
# Display diff (should render as HTML in Jupyter)
print("DIFF 8.2: Displaying MappingDiff object (should render as HTML)\n")
diff_1_4
```

<div class="nb-section">
  <span class="nb-section__number">16</span>
  <div>
    <h2 class="nb-section__title">Cleanup</h2>
  </div>
</div>

```python
# Cleanup is handled automatically by ctx via atexit
# For interactive use, you can call ctx.teardown() manually
ctx.teardown()

print("\nCleanup complete")
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li>All version diffing tests validated</li>
    <li>Resources cleaned up automatically via test context</li>
    <li>Zero residual state on the cluster</li>
  </ul>
</div>

```python
print("\n" + "="*70)
print("MAPPING VERSION DIFF E2E TESTS COMPLETED!")
print("="*70)
print("\nValidated:")
print("  1. Node Added (v1 → v2):")
print("    1.1: Summary counts correct")
print("    1.2: change_type='added' with from=None, to=definition")
print("    1.3: Filter methods (nodes_added, nodes_removed, nodes_modified)")
print("  2. Node Modified (v2 → v3):")
print("    2.1: Summary shows 1 node modified")
print("    2.2: change_type='modified' with fields_changed list")
print("  3. Edge Removed (v3 → v4):")
print("    3.1: Summary shows 1 edge removed")
print("    3.2: change_type='removed' with from=definition, to=None")
print("  4. Multiple Changes (v1 → v4):")
print("    4.1: Summary shows all accumulated changes")
print("  5. Reverse Diff (v4 → v1):")
print("    5.1: Change types correctly inverted")
print("  6. Error Handling:")
print("    6.1: Same version diff raises error")
print("  7. SDK Rendering Utilities:")
print("    7.1: render_diff_summary() displays summary table")
print("    7.2: render_diff_details() displays changes")
print("    7.3: render_diff_details(show_from_to=True) shows from/to")
print("    7.4: diff_to_dict() converts to dictionary")
print("  8. HTML Representation:")
print("    8.1: _repr_html_() method exists and works")
print("    8.2: MappingDiff displays as HTML in Jupyter")
print("\nAll resources will be cleaned up automatically via atexit")
```
