---
title: "Advanced Mappings"
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
  <h1 class="nb-header__title">Advanced Mappings</h1>
  <p class="nb-header__subtitle">Copy, tree view, and lifecycle configuration</p>
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
# Note: Uses GRAPH_OLAP_API_URL from environment (set by JupyterHub or local dev)
SEEDED_MAPPING_ID = None  # Injected by papermill from fixtures
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
from graph_olap.exceptions import NotFoundError
from graph_olap.models.mapping import EdgeDefinition, NodeDefinition, PropertyDefinition
from graph_olap.personas import Persona
from graph_olap_schemas import WrapperType

print("SDK imports successful")

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

ctx = setup(prefix="MappingAdvTest", persona=Persona.ANALYST_ALICE)
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
print("Starting Mapping Advanced Features E2E Test - resources will be cleaned up automatically via atexit")
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Create Base Mapping</h2>
    <p class="nb-section__description">Create a mapping with initial version for testing advanced features.</p>
  </div>
</div>

```python
from graph_olap.test_data import CUSTOMER_NODE, SHARES_ACCOUNT_EDGE, NODE_DEFINITIONS, EDGE_DEFINITIONS
# Create base mapping using ctx.mapping (auto-tracked)
customer_node = CUSTOMER_NODE

shares_account_edge = SHARES_ACCOUNT_EDGE

base_mapping = ctx.mapping(
    description="Base mapping for advanced features test",
    node_definitions=[customer_node],
    edge_definitions=[shares_account_edge],
)
BASE_MAPPING_ID = base_mapping.id
BASE_MAPPING_NAME = base_mapping.name

print(f"Created base mapping: {BASE_MAPPING_NAME} (id={BASE_MAPPING_ID}, version={base_mapping.current_version})")
```

<div class="nb-section">
  <span class="nb-section__number">5</span>
  <div>
    <h2 class="nb-section__title">Test Mapping Copy</h2>
  </div>
</div>

### 1.1 Test copy() Creates New Mapping

```python
# Test: Copy mapping
COPY_NAME = f"MappingAdvTest-Copy-{ctx.run_id}"

copied_mapping = client.mappings.copy(BASE_MAPPING_ID, new_name=COPY_NAME)

assert copied_mapping is not None, "Copied mapping should not be None"
assert copied_mapping.id != BASE_MAPPING_ID, "Copy should have different ID"
assert copied_mapping.name == COPY_NAME, f"Expected name '{COPY_NAME}', got '{copied_mapping.name}'"
assert copied_mapping.current_version == 1, f"Copy should start at version 1, got {copied_mapping.current_version}"

COPIED_MAPPING_ID = copied_mapping.id
# Track copied mapping for cleanup via ctx
ctx.track('mapping', COPIED_MAPPING_ID, COPY_NAME)

print(f"MAPPING_ADV 1.1 PASSED: Copied mapping {BASE_MAPPING_ID} -> {COPIED_MAPPING_ID}")
print(f"  Original: {base_mapping.name}")
print(f"  Copy: {copied_mapping.name}")
```

### 1.2 Test Copy Has Same Schema

```python
# Test: Verify copy has same node and edge definitions
assert len(copied_mapping.node_definitions) == len(base_mapping.node_definitions), \
    "Copy should have same number of node definitions"
assert len(copied_mapping.edge_definitions) == len(base_mapping.edge_definitions), \
    "Copy should have same number of edge definitions"

# Verify node labels match
base_node_labels = {n.label for n in base_mapping.node_definitions}
copied_node_labels = {n.label for n in copied_mapping.node_definitions}
assert base_node_labels == copied_node_labels, "Node labels should match"

# Verify edge types match
base_edge_types = {e.type for e in base_mapping.edge_definitions}
copied_edge_types = {e.type for e in copied_mapping.edge_definitions}
assert base_edge_types == copied_edge_types, "Edge types should match"

print("MAPPING_ADV 1.2 PASSED: Copy has identical schema")
print(f"  Node labels: {copied_node_labels}")
print(f"  Edge types: {copied_edge_types}")
```

### 1.3 Test Copy is Independent

```python
# Test: Modifying copy doesn't affect original
company_node = NodeDefinition(
    label="Company",
    sql="SELECT 'ACME' as id, 'ACME Corp' as name",
    primary_key={"name": "id", "type": "STRING"},
    properties=[PropertyDefinition(name="cust_name", type="STRING")],
)

updated_copy = client.mappings.update(
    COPIED_MAPPING_ID,
    change_description="Add Company node to copy",
    node_definitions=copied_mapping.node_definitions + [company_node],
    edge_definitions=copied_mapping.edge_definitions,
)

assert updated_copy.current_version == 2, "Copy should be at version 2"

# Verify original is unchanged
original_fresh = client.mappings.get(BASE_MAPPING_ID)
assert original_fresh.current_version == 1, "Original should still be at version 1"
assert len(original_fresh.node_definitions) == 1, "Original should still have 1 node"

print("MAPPING_ADV 1.3 PASSED: Copy is independent")
print(f"  Copy version: {updated_copy.current_version} (2 nodes)")
print(f"  Original version: {original_fresh.current_version} (1 node)")
```

<div class="nb-section">
  <span class="nb-section__number">6</span>
  <div>
    <h2 class="nb-section__title">Test Mapping Hierarchy Tree</h2>
  </div>
</div>

### 2.1 Test get_tree() Returns Hierarchy

```python
# Test: Get mapping tree (version → instance hierarchy)
tree = client.mappings.get_tree(BASE_MAPPING_ID)

assert tree is not None, "Tree should not be None"
assert isinstance(tree, dict), f"Tree should be dict, got {type(tree)}"
assert 1 in tree, "Tree should contain version 1"

# Version 1 should exist
version_1 = tree[1]
assert "name" in version_1, "Version should have name"
assert "snapshots" in version_1, "Version should have snapshots list"

print("MAPPING_ADV 2.1 PASSED: get_tree() returned hierarchy")
print(f"  Versions: {list(tree.keys())}")
print(f"  Version 1: {version_1['name']}")
```

### 2.2 Test Tree With Instances

```python
# Create an instance to populate the tree (snapshot auto-created)
INSTANCE_NAME = f"MappingAdvTest-TreeInstance-{ctx.run_id}"

print(f"Creating instance from mapping to populate tree...")
tree_instance = client.instances.create_and_wait(
    mapping_id=BASE_MAPPING_ID,
    name=INSTANCE_NAME,
    wrapper_type=WrapperType.RYUGRAPH,
    timeout=300,
    poll_interval=5,
)
INSTANCE_ID = tree_instance.id
SNAPSHOT_ID = tree_instance.snapshot_id
ctx.track('instance', INSTANCE_ID, INSTANCE_NAME)

print(f"Created instance: {INSTANCE_NAME} (id={INSTANCE_ID})")
print(f"Auto-created snapshot: id={SNAPSHOT_ID}")

# Get tree again (should now include snapshot)
tree_with_snapshot = client.mappings.get_tree(BASE_MAPPING_ID, include_instances=False)

version_1 = tree_with_snapshot[1]
assert len(version_1["snapshots"]) >= 1, "Version 1 should have at least 1 snapshot"

# Find our snapshot
our_snapshot = next((s for s in version_1["snapshots"] if s["id"] == SNAPSHOT_ID), None)
assert our_snapshot is not None, f"Snapshot {SNAPSHOT_ID} should be in tree"

print("MAPPING_ADV 2.2 PASSED: Tree includes snapshots")
print(f"  Version 1 snapshots: {len(version_1['snapshots'])}")
```

### 2.3 Test Tree With Instances

```python
# Instance and snapshot were already created in test 2.2 above
# Get tree with instances
tree_full = client.mappings.get_tree(BASE_MAPPING_ID, include_instances=True)

# Find our snapshot and verify it has instances
version_1 = tree_full[1]
our_snapshot = next((s for s in version_1["snapshots"] if s["id"] == SNAPSHOT_ID), None)
assert our_snapshot is not None
assert "instances" in our_snapshot, "Snapshot should have instances list"

# Verify our instance is in the tree
our_instance = next((i for i in our_snapshot["instances"] if i["id"] == INSTANCE_ID), None)
assert our_instance is not None, f"Instance {INSTANCE_ID} should be in tree"
assert our_instance["name"] == INSTANCE_NAME

print("MAPPING_ADV 2.3 PASSED: Tree includes instances")
print(f"  Snapshot {SNAPSHOT_ID} instances: {len(our_snapshot['instances'])}")
```

<div class="nb-section">
  <span class="nb-section__number">7</span>
  <div>
    <h2 class="nb-section__title">Test Version Diff</h2>
  </div>
</div>

### 3.1 Create Version 2 for Diff Testing

```python
# Update base mapping to create version 2
print(f"BASE_MAPPING_ID={BASE_MAPPING_ID}")

# Fetch current state first to ensure we have latest definitions
current_base = client.mappings.get(BASE_MAPPING_ID)
print(f"Current base mapping: id={current_base.id}, version={current_base.current_version}, name={current_base.name}")
print(f"  Nodes: {[n.label for n in current_base.node_definitions]}")
print(f"  Edges: {[e.type for e in current_base.edge_definitions]}")

# Add Location node
location_node = NodeDefinition(
    label="Location",
    sql="SELECT 'NYC' as id, 'New York City' as name",
    primary_key={"name": "id", "type": "STRING"},
    properties=[PropertyDefinition(name="cust_name", type="STRING")],
)

print(f"\nUpdating with {len(current_base.node_definitions) + 1} nodes...")
updated_mapping = client.mappings.update(
    BASE_MAPPING_ID,
    change_description="Add Location node for diff test",
    node_definitions=current_base.node_definitions + [location_node],
    edge_definitions=current_base.edge_definitions,
)

print(f"\nAfter update: id={updated_mapping.id}, version={updated_mapping.current_version}")
print(f"  Nodes: {[n.label for n in updated_mapping.node_definitions]}")

assert updated_mapping.id == BASE_MAPPING_ID, f"Mapping ID changed: {BASE_MAPPING_ID} → {updated_mapping.id}"
assert updated_mapping.current_version == 2, f"Expected version 2, got {updated_mapping.current_version}"

print("\n✓ Successfully created version 2")
print(f"  Version 1: {len(current_base.node_definitions)} node(s), {len(current_base.edge_definitions)} edge(s)")
print(f"  Version 2: {len(updated_mapping.node_definitions)} node(s), {len(updated_mapping.edge_definitions)} edge(s)")
```

### 3.2 Test diff_versions() Shows Changes

```python
# Test: Diff versions 1 and 2
diff = client.mappings.diff(BASE_MAPPING_ID, from_version=1, to_version=2)

assert diff is not None, "Diff should not be None"

# Verify diff structure
assert hasattr(diff, 'summary'), "Diff should have summary"
assert hasattr(diff, 'changes'), "Diff should have changes"

# Verify summary shows the added Location node
assert diff.summary["nodes_added"] == 1, f"Expected 1 node added, got {diff.summary['nodes_added']}"
assert diff.summary["nodes_removed"] == 0, f"Expected 0 nodes removed, got {diff.summary['nodes_removed']}"
assert diff.summary["nodes_modified"] == 0, f"Expected 0 nodes modified, got {diff.summary['nodes_modified']}"

# Verify changes list contains Location node
added_nodes = [n for n in diff.changes["nodes"] if n.change_type == "added"]
assert len(added_nodes) == 1, f"Expected 1 added node in changes, got {len(added_nodes)}"
assert added_nodes[0].label == "Location", f"Expected Location node, got {added_nodes[0].label}"

print("MAPPING_ADV 3.2 PASSED: diff() shows changes correctly")
print(f"  Summary: +{diff.summary['nodes_added']} nodes, -{diff.summary['nodes_removed']} nodes")
print(f"  Added node: {added_nodes[0].label}")
```

### 3.3 Test Diff From Version 2 to 1 (Reverse)

```python
# Test: Reverse diff (2 → 1 should show removed node)
reverse_diff = client.mappings.diff(BASE_MAPPING_ID, from_version=2, to_version=1)

assert reverse_diff is not None

# Verify reverse diff shows opposite changes
assert reverse_diff.summary["nodes_added"] == 0, f"Expected 0 nodes added, got {reverse_diff.summary['nodes_added']}"
assert reverse_diff.summary["nodes_removed"] == 1, f"Expected 1 node removed, got {reverse_diff.summary['nodes_removed']}"
assert reverse_diff.summary["nodes_modified"] == 0, f"Expected 0 nodes modified, got {reverse_diff.summary['nodes_modified']}"

# Verify changes list contains Location node as removed
removed_nodes = [n for n in reverse_diff.changes["nodes"] if n.change_type == "removed"]
assert len(removed_nodes) == 1, f"Expected 1 removed node in changes, got {len(removed_nodes)}"
assert removed_nodes[0].label == "Location", f"Expected Location node, got {removed_nodes[0].label}"

print("MAPPING_ADV 3.3 PASSED: Reverse diff works correctly")
print(f"  Forward (1→2): +{diff.summary['nodes_added']} nodes")
print(f"  Reverse (2→1): -{reverse_diff.summary['nodes_removed']} nodes")
```

<div class="nb-section">
  <span class="nb-section__number">8</span>
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
    <li>All advanced mappings tests validated</li>
    <li>Resources cleaned up automatically via test context</li>
    <li>Zero residual state on the cluster</li>
  </ul>
</div>

```python
print("\n" + "="*60)
print("MAPPING ADVANCED FEATURES E2E TESTS COMPLETED!")
print("="*60)
print("\nValidated:")
print("  1. Mapping Copy:")
print("    1.1: copy() creates new mapping")
print("    1.2: Copy has identical schema")
print("    1.3: Copy is independent of original")
print("  2. Mapping Hierarchy Tree:")
print("    2.1: get_tree() returns version hierarchy")
print("    2.2: Tree includes instances")
print("    2.3: Tree includes instances (when include_instances=True)")
print("  3. Version Diff:")
print("    3.1: Create version 2 for testing")
print("    3.2: diff_versions() shows changes between versions")
print("    3.3: Reverse diff works (from newer to older)")
print("\nAll resources will be cleaned up automatically via atexit")
```
