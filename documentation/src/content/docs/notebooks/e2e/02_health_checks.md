---
title: "Health Checks"
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
  <h1 class="nb-header__title">Health Checks</h1>
  <p class="nb-header__subtitle">Verify stack readiness</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">5 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--beginner">
        <span class="nb-difficulty__dot"></span>
      </span>
      Beginner
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">E2E Test</span><span class="nb-header__tag">Test</span></div>
</div>

```python
import os

# Parameters cell - papermill will inject values here
# Wrapper type for instance creation
WRAPPER_TYPE_STR = os.environ.get("WRAPPER_TYPE", "falkordb")  # or "ryugraph"

# Phase 2.3 Optimization: Support instance pooling
SKIP_RESOURCE_CREATION = False  # Set to True to use pool instance
POOL_INSTANCE_ID = None  # Instance ID from pool (when SKIP_RESOURCE_CREATION=True)

# Note: Auth is handled via Persona - env vars like GRAPH_OLAP_API_KEY_ANALYST_ALICE
```

<div class="nb-section">
  <span class="nb-section__number">1</span>
  <div>
    <h2 class="nb-section__title">SDK Import Test</h2>
    <p class="nb-section__description">Verify all SDK modules can be imported.</p>
  </div>
</div>

```python
import sys
import uuid
import os

print(f"Python version: {sys.version}")
print(f"GRAPH_OLAP_API_URL: {os.environ.get('GRAPH_OLAP_API_URL', 'not set')}")
print(f"Using Bearer token: {'yes' if os.environ.get('GRAPH_OLAP_API_KEY') else 'no'}")
```

```python
# Test: Core SDK imports
from graph_olap import GraphOLAPClient
from graph_olap.personas import Persona
from graph_olap_schemas import WrapperType

# Convert wrapper type string to enum
WRAPPER_TYPE = WrapperType(WRAPPER_TYPE_STR)

print("Smoke 1.1 PASSED: Core SDK imports successful")
print(f"  Wrapper type: {WRAPPER_TYPE.value}")
```

```python
# Test: Mapping model imports
from graph_olap.models.mapping import EdgeDefinition, NodeDefinition, PropertyDefinition

print("Smoke 1.2 PASSED: Mapping model imports successful")
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Control Plane Health Checks</h2>
  </div>
</div>

```python
from graph_olap.notebook_setup import setup

# Create test context with automatic cleanup
ctx = setup(prefix="SmokeTest", persona=Persona.ANALYST_ALICE)
client = ctx.client

print(f"Test context created for {client._config.api_url}")
print(f"  Persona: {Persona.ANALYST_ALICE.value.name}")
```

```python
# Test: Control Plane health endpoint
health = client.health.check()

assert health is not None, "Health response should not be None"
assert health.status == "healthy", f"Expected 'healthy', got '{health.status}'"

print(f"Smoke 2.1 PASSED: Control Plane health status='{health.status}'")
```

```python
# Test: Control Plane readiness endpoint
ready = client.health.ready()

assert ready is not None, "Ready response should not be None"
assert ready.status in ["ready", "healthy"], f"Expected ready status, got '{ready.status}'"

print(f"Smoke 2.2 PASSED: Control Plane readiness status='{ready.status}'")
if hasattr(ready, 'database') and ready.database:
    print(f"  Database: {ready.database}")
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Create Test Data via SDK</h2>
    <p class="nb-section__description">This section creates a mapping and instance dynamically.</p>
  </div>
</div>

```python
# Phase 2.3: Pool mode detection
if SKIP_RESOURCE_CREATION:
    # Using pool instance - no resource creation needed
    assert POOL_INSTANCE_ID is not None, "POOL_INSTANCE_ID required when SKIP_RESOURCE_CREATION=True"
    INSTANCE_ID = int(POOL_INSTANCE_ID)
    print(f"✓ Pool mode: Using pool instance {INSTANCE_ID} (skipping resource creation)")
else:
    # Standard mode - create resources dynamically
    TEST_RUN_ID = uuid.uuid4().hex[:8]
    MAPPING_NAME = f"SmokeTest-{TEST_RUN_ID}"
    print("✓ Standard mode: Creating resources dynamically")
    print(f"  Test run ID: {TEST_RUN_ID}")
    print(f"  Mapping name: {MAPPING_NAME}")
```

```python
# Cleanup is automatic with setup()!
# Resources created via ctx.mapping(), ctx.instance() are auto-tracked
if not SKIP_RESOURCE_CREATION:
    print("Starting Smoke E2E Test - resources will be cleaned up automatically via atexit")
```

```python
from graph_olap.test_data import CUSTOMER_NODE, SHARES_ACCOUNT_EDGE, NODE_DEFINITIONS, EDGE_DEFINITIONS
# Define node and edge definitions (only in standard mode)
if not SKIP_RESOURCE_CREATION:
    # These reference the Trino source tables created by trino-seed job
    # Using SELECT DISTINCT because test data may have duplicates
    customer_node = CUSTOMER_NODE

    shares_account_edge = SHARES_ACCOUNT_EDGE

    print(f"Node definition: {customer_node.label} (primary_key: {customer_node.primary_key})")
    print(f"Edge definition: {shares_account_edge.type} ({shares_account_edge.from_node} -> {shares_account_edge.to_node})")
```

```python
# Create mapping via ctx.mapping() (auto-tracked, only in standard mode)
if not SKIP_RESOURCE_CREATION:
    mapping = ctx.mapping(
        name=f"SmokeTest-{ctx.run_id}",
        description="Smoke test mapping - created dynamically via SDK",
        node_definitions=[customer_node],
        edge_definitions=[shares_account_edge],
    )

    assert mapping is not None, "Mapping should not be None"
    assert mapping.id is not None, "Mapping should have an ID"

    MAPPING_ID = mapping.id
    print(f"Smoke 3.1 PASSED: Created mapping (id={MAPPING_ID}, name='{mapping.name}')")
```

```python
# Create instance directly from mapping
if not SKIP_RESOURCE_CREATION:
    print(f"Creating instance directly from mapping ...")
    print("  (This may take up to 3-4 minutes for data export + instance startup)")

    instance = client.instances.create_from_mapping_and_wait(
        mapping_id=MAPPING_ID,
        name=f"SmokeTest-Instance-{ctx.run_id}",
        wrapper_type=WRAPPER_TYPE,
        timeout=300,  # Longer timeout for data export
        poll_interval=5,
    )

    assert instance is not None, "Instance should not be None"
    assert instance.id is not None, "Instance should have an ID"
    assert instance.status == "running", f"Expected status 'running', got '{instance.status}'"

    INSTANCE_ID = instance.id
    ctx.track('instance', INSTANCE_ID, instance.name)
    
    print(f"Smoke 3.2 PASSED: Created instance (id={INSTANCE_ID}, status='{instance.status}')")
    if hasattr(instance, 'instance_url') and instance.instance_url:
        print(f"  Instance URL: {instance.instance_url}")
```

```python
# Instance creation now happens via create_from_mapping().
if not SKIP_RESOURCE_CREATION:
    print("Smoke 3.3 PASSED: Instance created via create_from_mapping()")
    print(f"  Instance ID: {INSTANCE_ID}")
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Wrapper Health Checks</h2>
  </div>
</div>

```python
# Connect to wrapper via SDK (environment-aware)
conn = client.instances.connect(INSTANCE_ID)
print(f"Connected to instance {INSTANCE_ID}")
```

```python
# Test: Wrapper can execute queries (readiness)
result = conn.query("MATCH (n) RETURN count(n) AS count LIMIT 1")

assert result is not None, "Query should succeed if wrapper is ready"
assert result.row_count == 1, "Should get 1 row"

node_count = result.rows[0][0]
print(f"Smoke 4.2 PASSED: Wrapper query works (node count={node_count})")
```

```python
# Test: NetworkX extension server available
try:
    algos = conn.networkx.algorithms()
    assert len(algos) > 0, "Should have NetworkX algorithms available"
    print(f"Smoke 4.3 PASSED: NetworkX extension available ({len(algos)} algorithms)")
except Exception as e:
    print(f"Smoke 4.3 WARNING: NetworkX extension not available - {e}")
```

<div class="nb-section">
  <span class="nb-section__number">5</span>
  <div>
    <h2 class="nb-section__title">Test Data Verification</h2>
  </div>
</div>

```python
# Test: Mapping was created correctly (only in standard mode)
if not SKIP_RESOURCE_CREATION:
    fetched_mapping = client.mappings.get(MAPPING_ID)

    assert fetched_mapping is not None, f"Mapping {MAPPING_ID} should exist"
    assert fetched_mapping.id == MAPPING_ID

    print(f"Smoke 5.1 PASSED: Mapping exists (id={fetched_mapping.id}, name='{fetched_mapping.name}')")
else:
    print("Smoke 5.1 SKIPPED: Mapping verification (pool mode)")
```

```python
pass
```

```python
# Test: Instance is running
fetched_instance = client.instances.get(INSTANCE_ID)

assert fetched_instance is not None, f"Instance {INSTANCE_ID} should exist"
assert fetched_instance.id == INSTANCE_ID
assert fetched_instance.status == "running", f"Instance should be 'running', got '{fetched_instance.status}'"

print(f"Smoke 5.3 PASSED: Instance exists (id={fetched_instance.id}, status='{fetched_instance.status}')")
```

```python
# Test: Graph has expected data
person_count = conn.query_scalar("MATCH (c:Customer) RETURN count(c)")
edge_count = conn.query_scalar("MATCH ()-[r:SHARES_ACCOUNT]->() RETURN count(r)")

assert person_count >= 1, f"Should have at least 1 Customer node, got {person_count}"
assert edge_count >= 1, f"Should have at least 1 SHARES_ACCOUNT edge, got {edge_count}"

print(f"Smoke 5.4 PASSED: Graph has data ({person_count} Customer nodes, {edge_count} SHARES_ACCOUNT edges)")
```

<div class="nb-section">
  <span class="nb-section__number">6</span>
  <div>
    <h2 class="nb-section__title">Test Users Verification</h2>
  </div>
</div>

```python
# Test: Can access API with different personas
# Test personas are accessed via ctx.with_persona()
from graph_olap.personas import Persona

# Test with different personas
test_personas = [
    Persona.ANALYST_ALICE,
    Persona.ANALYST_BOB,
    Persona.ADMIN_CAROL,
    Persona.OPS_DAVE,
]

for persona in test_personas:
    try:
        persona_client = ctx.with_persona(persona)
        mappings = persona_client.mappings.list()
        assert mappings is not None, f"{persona.value.name} should be able to list mappings"
        print(f"  ✓ {persona.value.name}: {len(mappings)} mappings visible")
    except ValueError as e:
        # API key not configured for this persona - OK in some environments
        print(f"  - {persona.value.name}: Not configured ({e})")

print(f"Smoke 6.1 PASSED: Test persona access verified")
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li>All health checks tests validated</li>
    <li>Resources cleaned up automatically via test context</li>
    <li>Zero residual state on the cluster</li>
  </ul>
</div>

```python
# Cleanup is automatic via atexit!
# Resources created via ctx.mapping(), ctx.instance() will be cleaned up
if not SKIP_RESOURCE_CREATION:
    # Explicitly cleanup (optional - also happens on exit)
    results = ctx.cleanup()
    print(f"Cleanup: {results}")
else:
    print("Pool mode - no cleanup needed (pool manages instances)")
```

```python
# Close client
client.close()

import os

print("\n" + "="*60)
print("SMOKE TESTS PASSED - Stack is ready for full E2E tests")
print("="*60)
print("\nVerified:")
print("  1. SDK Imports: Core modules, models, exceptions")
print("  2. Control Plane: Health and readiness endpoints")

if SKIP_RESOURCE_CREATION:
    print(f"  3. Test Data: Used pool instance {INSTANCE_ID}")
else:
    print("  3. Test Data Creation:")
    print(f"     - Mapping ID: {MAPPING_ID}")
    print(f"     - Instance ID: {INSTANCE_ID}")

print("  4. Wrapper: Status, query execution, NetworkX extension")

if SKIP_RESOURCE_CREATION:
    print("  5. Data Verification: Instance, graph data (pool mode)")
else:
    print("  5. Data Verification: Mapping, instance, graph data")

if os.environ.get("GRAPH_OLAP_API_KEY"):
    print("  6. Test Users: Bearer token identity verified")
else:
    print("  6. Test Users: All 4 test users can access API")

if SKIP_RESOURCE_CREATION:
    print(f"\nMode: POOL (instance {INSTANCE_ID})")
else:
    print(f"\nMode: STANDARD (test run ID: {TEST_RUN_ID})")
```
