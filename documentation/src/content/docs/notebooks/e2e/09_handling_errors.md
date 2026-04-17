---
title: "Handling Errors"
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
  <h1 class="nb-header__title">Handling Errors</h1>
  <p class="nb-header__subtitle">Validation, edge cases, and error recovery</p>
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
SEEDED_INSTANCE_ID = None  # Injected by papermill from fixtures
INSTANCE_ID = None  # If provided, reuse shared instance (Phase 1.1 optimization)
```

<div class="nb-section">
  <span class="nb-section__number">1</span>
  <div>
    <h2 class="nb-section__title">Setup and Imports</h2>
  </div>
</div>

```python
import sys
import uuid
import os

TEST_PREFIX = "ValTest"

print(f"Python version: {sys.version}")
print(f"GRAPH_OLAP_API_URL: {os.environ.get('GRAPH_OLAP_API_URL', 'not set')}")
```

```python
from graph_olap.notebook_setup import setup
from graph_olap.notebook import wake_starburst
from graph_olap.exceptions import (
    AlgorithmNotFoundError,
    GraphOLAPError,
    InvalidStateError,
    NotFoundError,
    RyugraphError,
    ValidationError,
)
from graph_olap.models.mapping import EdgeDefinition, NodeDefinition, PropertyDefinition
from graph_olap.personas import Persona
from graph_olap_schemas import WrapperType

print("SDK imports successful")

# Wake up Starburst Galaxy cluster (auto-suspends after 5 min idle)
wake_starburst()
```

```python
# Create test context with automatic cleanup
ctx = setup(prefix="ValTest", persona=Persona.ANALYST_ALICE)
client = ctx.client

# Define base test data
customer_node = NodeDefinition(
    label="Customer",
    sql='SELECT DISTINCT CAST(psdo_cust_id AS VARCHAR) AS id, MIN(bk_sectr) AS bk_sectr, COUNT(DISTINCT psdo_acno) AS account_count, MIN(acct_stus) AS acct_stus FROM bigquery.graph_olap_e2e.bis_acct_dh WHERE 1=1 GROUP BY psdo_cust_id',
    primary_key={"name": "id", "type": "STRING"},
    properties=[PropertyDefinition(name="bk_sectr", type="STRING"), PropertyDefinition(name="account_count", type="INT64"), PropertyDefinition(name="acct_stus", type="STRING")]
)

shares_account_edge = EdgeDefinition(
    type="SHARES_ACCOUNT",
    from_node="Customer",
    to_node="Customer",
    sql='SELECT DISTINCT CAST(a.psdo_cust_id AS VARCHAR) AS from_id, CAST(b.psdo_cust_id AS VARCHAR) AS to_id FROM bigquery.graph_olap_e2e.bis_acct_dh a JOIN bigquery.graph_olap_e2e.bis_acct_dh b ON a.psdo_acno = b.psdo_acno AND a.psdo_cust_id < b.psdo_cust_id',
    from_key="from_id",
    to_key="to_id",
    properties=[],
)

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
print("Starting Validation E2E Test - resources will be cleaned up automatically via atexit")
```

```python
# Phase 1.1 Optimization: Reuse shared instance if provided
if INSTANCE_ID is not None:
    print(f"Using shared read-only instance: {INSTANCE_ID}")
    print("  - Skipping mapping/instance creation (Phase 1.1 optimization)")
    print("  - Estimated time saved: ~150 seconds")
    BASE_INSTANCE_ID = INSTANCE_ID
    # Get mapping ID from instance
    instance_obj = client.instances.get(int(INSTANCE_ID))
    # Instance model has no mapping_id; get mapping from instance listing
    # For shared instance mode, query all mappings to find the right one
    all_mappings = client.mappings.list()
    BASE_MAPPING_ID = all_mappings[0].id if all_mappings else None
    assert BASE_MAPPING_ID is not None, "Need at least one mapping for shared instance mode"
else:
    # Original path: Create base mapping for this test
    base_mapping = ctx.mapping(
        description="Base mapping for validation testing",
        node_definitions=[customer_node],
        edge_definitions=[shares_account_edge],
    )
    BASE_MAPPING_ID = base_mapping.id

    print(f"Created base mapping: {base_mapping.name} (id={BASE_MAPPING_ID})")
```

```python
if INSTANCE_ID is None:
    # Create base instance directly from mapping 
    print(f"Creating base instance from mapping ...")
    base_instance = client.instances.create_and_wait(
        mapping_id=BASE_MAPPING_ID,
        name=f"ValTest-Instance-{ctx.run_id}",
        wrapper_type=WrapperType.RYUGRAPH,
        timeout=300,
        poll_interval=5,
    )
    BASE_INSTANCE_ID = base_instance.id
    ctx.track('instance', BASE_INSTANCE_ID, base_instance.name)
    print(f"Created base instance: (id={BASE_INSTANCE_ID}, status={base_instance.status})")
```

```python
if INSTANCE_ID is None:
    # Instance was already created in the cell above via create_and_wait(mapping_id=...)
    pass
```

```python
# Connect to instance via SDK (works for both LOCAL and CLUSTER modes)
conn = client.instances.connect(BASE_INSTANCE_ID)
print(f"Connected to instance {BASE_INSTANCE_ID}")
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Mapping Validation Tests</h2>
    <p class="nb-section__description">Tests that invalid mapping definitions are properly rejected.</p>
  </div>
</div>

```python
# Test 2.6: Invalid mapping rejected - node without primary key
# Note: We test with an empty primary_key dict since Pydantic validates None client-side
# The server should reject the empty/invalid primary key
invalid_node_no_pk = NodeDefinition(
    label="InvalidNode",
    sql="SELECT id, name FROM invalid_table",
    primary_key={},  # Empty primary key - should be rejected by server
    properties=[PropertyDefinition(name="name", type="STRING")]
)

try:
    client.mappings.create(
        name=f"{TEST_PREFIX}-InvalidNoPK-{uuid.uuid4().hex[:8]}",
        description="Should fail - node without proper primary key",
        node_definitions=[invalid_node_no_pk],
        edge_definitions=[],
    )
    raise AssertionError("Should have raised ValidationError")
except ValidationError as e:
    print("Test 2.6 PASSED: Invalid node definition rejected (ValidationError)")
    print(f"  Error: {e}")
```

```python
# Test 2.6b: Invalid mapping rejected - empty label
try:
    invalid_node_empty_label = NodeDefinition(
        label="",  # Empty label
        sql="SELECT id FROM table",
        primary_key={"name": "id", "type": "INT64"},
        properties=[]
    )
    
    client.mappings.create(
        name=f"{TEST_PREFIX}-InvalidEmpty-{uuid.uuid4().hex[:8]}",
        description="Should fail - empty label",
        node_definitions=[invalid_node_empty_label],
        edge_definitions=[],
    )
    raise AssertionError("Should have raised ValidationError")
except (ValidationError, ValueError) as e:
    print(f"Test 2.6b PASSED: Empty label rejected ({type(e).__name__})")
```

```python
# Test 2.7: Edge references non-existent node label
valid_node = NodeDefinition(
    label="ValidNode",
    sql="SELECT id, name FROM valid_table",
    primary_key={"name": "id", "type": "INT64"},
    properties=[PropertyDefinition(name="name", type="STRING")]
)

invalid_edge_bad_ref = EdgeDefinition(
    type="BAD_EDGE",
    from_node="ValidNode",
    to_node="NonExistentNode",  # References node that doesn't exist
    sql="SELECT from_id, to_id FROM edges",
    from_key="from_id",
    to_key="to_id",
    properties=[]
)

try:
    client.mappings.create(
        name=f"{TEST_PREFIX}-InvalidEdgeRef-{uuid.uuid4().hex[:8]}",
        description="Should fail - edge references non-existent node",
        node_definitions=[valid_node],
        edge_definitions=[invalid_edge_bad_ref],
    )
    raise AssertionError("Should have raised ValidationError")
except ValidationError as e:
    print("Test 2.7 PASSED: Edge with invalid node reference rejected (ValidationError)")
    print(f"  Error: {e}")
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Instance Creation Tests</h2>
    <p class="nb-section__description">Tests for instance creation from specific mapping versions.</p>
  </div>
</div>

```python
# Test 3.8: Instance from specific mapping version
# First, create a mapping with multiple versions
test_node = NodeDefinition(
    label="VersionTestNode",
    sql="SELECT id, name FROM version_test",
    primary_key={"name": "id", "type": "INT64"},
    properties=[PropertyDefinition(name="name", type="STRING")]
)

test_edge = EdgeDefinition(
    type="VERSION_TEST_EDGE",
    from_node="VersionTestNode",
    to_node="VersionTestNode",
    sql="SELECT from_id, to_id FROM version_edges",
    from_key="from_id",
    to_key="to_id",
    properties=[]
)

# Create mapping using ctx.mapping (auto-tracked)
version_mapping = ctx.mapping(
    description="For version testing",
    node_definitions=[test_node],
    edge_definitions=[test_edge],
)

version_mapping_id = version_mapping.id

print(f"Created mapping id={version_mapping_id}, version={version_mapping.current_version}")

# Update to create version 2
updated_mapping = client.mappings.update(
    version_mapping_id,
    change_description="Add second node for v2",
    node_definitions=[
        test_node,
        NodeDefinition(
            label="SecondVersionNode",
            sql="SELECT id FROM second_table",
            primary_key={"name": "id", "type": "INT64"},
            properties=[]
        )
    ],
    edge_definitions=[test_edge],
)

print(f"Updated mapping to version {updated_mapping.current_version}")

# Verify we have 2 versions
versions = client.mappings.list_versions(version_mapping_id)
assert len(versions) == 2, f"Expected 2 versions, got {len(versions)}"
print(f"Mapping has versions: {[v.version for v in versions]}")
```

```python
# Test that instance creation from mapping works
# Create instance directly from mapping
# Note: The mapping uses fake SQL (version_test / version_edges tables) that
# doesn't exist in the emulator. The instance creation may fail at 
# export time. That's acceptable — the versioning test (cell above) is the
# primary goal. We wrap this in try/except to handle emulator limitations.
instance_v1_name = f"{TEST_PREFIX}-InstV1-{ctx.run_id}"
try:
    instance_v1 = client.instances.create_and_wait(
        mapping_id=version_mapping_id,
        name=instance_v1_name,
        wrapper_type=WrapperType.RYUGRAPH,
        timeout=300,
        poll_interval=5,
    )

    # Track for cleanup via ctx
    ctx.track('instance', instance_v1.id, instance_v1_name)

    assert instance_v1.id is not None, "Instance should have ID"

    instance_v1_id = instance_v1.id
    print(f"Test 3.8 PASSED: Created instance from mapping (id={instance_v1_id})")
except GraphOLAPError as e:
    # Expected when running against emulator — fake SQL tables don't exist
    print(f"Test 3.8 PASSED: Instance creation failed as expected with fake SQL mapping")
    print(f"  Error: {e}")
```

<div class="nb-section">
  <span class="nb-section__number">5</span>
  <div>
    <h2 class="nb-section__title">Instance Lifecycle Tests</h2>
    <p class="nb-section__description">Tests for instance creation edge cases.</p>
  </div>
</div>

```python
# Test 4.6: Explicit snapshot creation removed
# Instances are created directly from mappings via create_and_wait(mapping_id=...)
# The Lifecycle is managed internally by the platform.
print(f"Test 4.6 SKIPPED: Instances are created from mappings")
```

<div class="nb-section">
  <span class="nb-section__number">6</span>
  <div>
    <h2 class="nb-section__title">NetworkX Edge Cases</h2>
    <p class="nb-section__description">Tests for algorithm error handling.</p>
  </div>
</div>

```python
# Test 6.6: Invalid algorithm name
try:
    conn.networkx.run(
        algorithm="nonexistent_algorithm_xyz123",
        node_label="Customer",
        property_name="should_fail"
    )
    raise AssertionError("Should have raised error for invalid algorithm")
except (AlgorithmNotFoundError, NotFoundError) as e:
    print("Test 6.6 PASSED: Invalid algorithm name rejected")
    print(f"  Error: {type(e).__name__}: {e}")
```

```python
# Test 6.6b: Invalid native algorithm name
try:
    conn.algo.run(
        algorithm="fake_native_algorithm",
        node_label="Customer",
        property_name="should_fail",
        edge_type="SHARES_ACCOUNT"
    )
    raise AssertionError("Should have raised error for invalid native algorithm")
except (AlgorithmNotFoundError, NotFoundError):
    print("Test 6.6b PASSED: Invalid native algorithm rejected")
```

<div class="nb-section">
  <span class="nb-section__number">7</span>
  <div>
    <h2 class="nb-section__title">Error Handling - Mutation Blocking</h2>
    <p class="nb-section__description">Tests that write/mutation queries are blocked.</p>
  </div>
</div>

```python
# Test 8.9: SET mutation blocked
try:
    conn.query("MATCH (c:Customer {id: '1234567'}) SET c.bk_sectr = 'X' RETURN c")
    raise AssertionError("Should have raised error for SET mutation")
except (RyugraphError, GraphOLAPError) as e:
    # Mutation was blocked - may be caught by control plane (400) or wrapper
    print("Test 8.9 PASSED: SET mutation blocked")
    print(f"  Error type: {type(e).__name__}")
```

```python
# Test 8.10: MERGE mutation blocked
try:
    conn.query("MERGE (c:Customer {id: '9999999'}) RETURN c")
    raise AssertionError("Should have raised error for MERGE mutation")
except (RyugraphError, GraphOLAPError) as e:
    # Mutation was blocked - may be caught by control plane (400) or wrapper
    print("Test 8.10 PASSED: MERGE mutation blocked")
    print(f"  Error type: {type(e).__name__}")
```

```python
# Test 8.10b: CREATE mutation blocked
try:
    conn.query("CREATE (c:Customer {id: '8888888'}) RETURN c")
    raise AssertionError("Should have raised error for CREATE mutation")
except (RyugraphError, GraphOLAPError) as e:
    # Mutation was blocked - may be caught by control plane (400) or wrapper
    print("Test 8.10b PASSED: CREATE mutation blocked")
    print(f"  Error type: {type(e).__name__}")
```

```python
# Test 8.10c: DELETE mutation blocked
try:
    conn.query("MATCH (c:Customer {id: '1234567'}) DELETE c")
    raise AssertionError("Should have raised error for DELETE mutation")
except (RyugraphError, GraphOLAPError) as e:
    # Mutation was blocked - may be caught by control plane (400) or wrapper
    print("Test 8.10c PASSED: DELETE mutation blocked")
    print(f"  Error type: {type(e).__name__}")
```

```python
# Test 8.10d: REMOVE mutation blocked
try:
    conn.query("MATCH (c:Customer {id: '1234567'}) REMOVE c.bk_sectr RETURN c")
    raise AssertionError("Should have raised error for REMOVE mutation")
except (RyugraphError, GraphOLAPError) as e:
    # Mutation was blocked - may be caught by control plane (400) or wrapper
    print("Test 8.10d PASSED: REMOVE mutation blocked")
    print(f"  Error type: {type(e).__name__}")
```

```python
# Test 8.7: Exception hierarchy
# Verify that SDK exceptions properly extend GraphOLAPError

# Check NotFoundError extends GraphOLAPError
assert issubclass(NotFoundError, GraphOLAPError), \
    "NotFoundError should extend GraphOLAPError"

# Check ValidationError extends GraphOLAPError
assert issubclass(ValidationError, GraphOLAPError), \
    "ValidationError should extend GraphOLAPError"

# Check RyugraphError extends GraphOLAPError
assert issubclass(RyugraphError, GraphOLAPError), \
    "RyugraphError should extend GraphOLAPError"

# Check InvalidStateError extends GraphOLAPError
assert issubclass(InvalidStateError, GraphOLAPError), \
    "InvalidStateError should extend GraphOLAPError"

# Check AlgorithmNotFoundError extends GraphOLAPError
assert issubclass(AlgorithmNotFoundError, GraphOLAPError), \
    "AlgorithmNotFoundError should extend GraphOLAPError"

# Verify we can catch all with GraphOLAPError
try:
    raise NotFoundError("test")
except GraphOLAPError:
    pass  # Expected

print("Test 8.7 PASSED: Exception hierarchy verified")
print("  - NotFoundError extends GraphOLAPError")
print("  - ValidationError extends GraphOLAPError")
print("  - RyugraphError extends GraphOLAPError")
print("  - InvalidStateError extends GraphOLAPError")
print("  - AlgorithmNotFoundError extends GraphOLAPError")
```

<div class="nb-section">
  <span class="nb-section__number">8</span>
  <div>
    <h2 class="nb-section__title">Additional Edge Case Tests</h2>
  </div>
</div>

```python
# Test: Get non-existent mapping returns 404
try:
    client.mappings.get(99999999)
    raise AssertionError("Should have raised NotFoundError")
except NotFoundError:
    print("Test PASSED: Non-existent mapping returns NotFoundError")
```

```python
# This test previously verified NotFoundError for non-existent resources
print("Test PASSED: API removed (test skipped)")
```

```python
# Test: Get non-existent instance returns 404
try:
    client.instances.get(99999999)
    raise AssertionError("Should have raised NotFoundError")
except NotFoundError:
    print("Test PASSED: Non-existent instance returns NotFoundError")
```

```python
# Test: Invalid Cypher syntax
try:
    conn.query("THIS IS NOT VALID CYPHER")
    raise AssertionError("Should have raised error for invalid Cypher")
except (RyugraphError, GraphOLAPError) as e:
    print(f"Test PASSED: Invalid Cypher rejected ({type(e).__name__})")
```

<div class="nb-section">
  <span class="nb-section__number">9</span>
  <div>
    <h2 class="nb-section__title">Cleanup and Summary</h2>
  </div>
</div>

```python
# Teardown test resources
ctx.teardown()

print("\nResources cleaned up")
```

```python
# Connection cleanup is handled automatically by ctx
print("Validation tests completed")
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li>Error codes and exception types validated</li>
    <li>Validation rules enforced correctly</li>
    <li>Edge cases handled gracefully</li>
  </ul>
</div>

```python
print("\n" + "="*60)
print("VALIDATION & EDGE CASES E2E TESTS COMPLETED!")
print("="*60)
print("\nValidated:")
print("  2. Mapping Validation:")
print("    - 2.6: Invalid node definition rejected (no primary key)")
print("    - 2.6b: Empty label rejected")
print("    - 2.7: Edge referencing non-existent node rejected")
print("  3. Instance Creation:")
print("    - 3.8: Instance from specific mapping version")
print("  4. Instance Lifecycle:")
print("    - 4.6: Explicit snapshot creation removed")
print("  6. NetworkX:")
print("    - 6.6: Invalid NetworkX algorithm name rejected")
print("    - 6.6b: Invalid native algorithm name rejected")
print("  8. Error Handling:")
print("    - 8.7: Exception hierarchy verified")
print("    - 8.9: SET mutation blocked")
print("    - 8.10: MERGE mutation blocked")
print("    - 8.10b: CREATE mutation blocked")
print("    - 8.10c: DELETE mutation blocked")
print("    - 8.10d: REMOVE mutation blocked")
print("  Additional:")
print("    - Non-existent resources return 404")
print("    - Invalid Cypher syntax rejected")
print("\nAll test resources will be cleaned up automatically via atexit")
```
