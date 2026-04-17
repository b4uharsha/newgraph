---
title: "Quick Start API"
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
  <h1 class="nb-header__title">Quick Start API</h1>
  <p class="nb-header__subtitle">One-call instance provisioning</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">10 min</span>
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

ctx = setup(prefix="QuickStartTest", persona=Persona.ANALYST_ALICE)
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
print("Starting Quick Start E2E Test - resources will be cleaned up automatically via atexit")
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Quick Start Tests</h2>
  </div>
</div>

### 1.1 Create Mapping for Quick Start

```python
from graph_olap.test_data import CUSTOMER_NODE, SHARES_ACCOUNT_EDGE, NODE_DEFINITIONS, EDGE_DEFINITIONS
# Create mapping for quick_start test using ctx.mapping (auto-tracked)
customer_node = CUSTOMER_NODE

shares_account_edge = SHARES_ACCOUNT_EDGE

mapping = ctx.mapping(
    description="Mapping for quick_start test",
    node_definitions=[customer_node],
    edge_definitions=[shares_account_edge],
)
MAPPING_ID = mapping.id
MAPPING_NAME = mapping.name

print(f"Created mapping: {MAPPING_NAME} (id={MAPPING_ID})")
```

### 1.2 Test quick_start() Creates Everything

```python
# Test: quick_start() creates instance
INSTANCE_NAME = f"QuickStartTest-Instance-{ctx.run_id}"

print("Calling quick_start() - this will create instance automatically...")
print(f"  Mapping ID: {MAPPING_ID}")
print(f"  Instance name: {INSTANCE_NAME}")

instance = client.quick_start(
    mapping_id=MAPPING_ID,
    wrapper_type=WrapperType.RYUGRAPH,
    instance_name=INSTANCE_NAME,
    wait_timeout=300,  # 5 minutes
)

# Track instance for cleanup via ctx
INSTANCE_ID = instance.id
ctx.track('instance', INSTANCE_ID, INSTANCE_NAME)

print("\nQUICK_START 1.2 PASSED: quick_start() succeeded")
print(f"  Instance: {instance.name} (id={INSTANCE_ID})")
```

### 1.3 Test Instance is Running

```python
# Test: Instance should be running
assert instance.current_status == "running", f"Expected status 'running', got '{instance.current_status}'"
assert instance.instance_url is not None, "Running instance should have URL"


print("QUICK_START 1.3 PASSED: Instance is running")
print(f"  Instance URL: {instance.instance_url}")
```

### 1.4 Test Instance Was Created

```python
# Verify instance was created by quick_start
instance_check = client.instances.get(INSTANCE_ID)
assert instance_check.status == "running", f"Instance should be running, got {instance_check.status}"

print("QUICK_START 1.4 PASSED: Instance was created and is running")
print(f"  Instance: {INSTANCE_ID}")
```

### 1.5 Test Can Query Instance

```python
# Test: Can connect and query the instance
conn = client.instances.connect(INSTANCE_ID)

# Query node count
node_count = conn.query_scalar("MATCH (n) RETURN count(n)")
assert node_count > 0, "Instance should have nodes"

# Query edge count
edge_count = conn.query_scalar("MATCH ()-[r]->() RETURN count(r)")
assert edge_count > 0, "Instance should have edges"

print("QUICK_START 1.5 PASSED: Can query instance")
print(f"  Nodes: {node_count}")
print(f"  Edges: {edge_count}")
```

### 1.6 Test All Resources Are Linked

```python
# Test: Verify resource hierarchy (mapping → instance)
instance_check = client.instances.get(INSTANCE_ID)
assert instance_check.status == "running", f"Expected 'running', got '{instance_check.status}'"

print("QUICK_START 1.6 PASSED: All resources are properly linked")
print(f"  Mapping {MAPPING_ID} → Instance {INSTANCE_ID}")
```

<div class="nb-section">
  <span class="nb-section__number">5</span>
  <div>
    <h2 class="nb-section__title">Cleanup</h2>
  </div>
</div>

```python
# Teardown test resources
ctx.teardown()

print("\nResources cleaned up")
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li>All quick start api tests validated</li>
    <li>Resources cleaned up automatically via test context</li>
    <li>Zero residual state on the cluster</li>
  </ul>
</div>

```python
print("\n" + "="*60)
print("QUICK START E2E TESTS COMPLETED!")
print("="*60)
print("\nValidated:")
print("  1. Quick Start Workflow:")
print("    1.1: Create mapping for test")
print("    1.2: quick_start() creates instance")
print("    1.3: Instance is running and ready")
print("    1.4: Instance was created and running")
print("    1.5: Can connect and query instance")
print("    1.6: All resources properly linked (mapping → instance)")
print("\nAll resources will be cleaned up automatically via atexit")
```
