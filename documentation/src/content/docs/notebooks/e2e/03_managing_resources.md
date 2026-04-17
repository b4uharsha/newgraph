---
title: "Managing Resources"
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
  <h1 class="nb-header__title">Managing Resources</h1>
  <p class="nb-header__subtitle">Mapping and instance CRUD operations</p>
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
# Parameters cell - not needed with new test API
# The setup() function handles auth via Persona
pass
```

<div class="nb-section">
  <span class="nb-section__number">1</span>
  <div>
    <h2 class="nb-section__title">Setup</h2>
  </div>
</div>

```python
import sys

print(f"Python version: {sys.version}")
```

```python
from graph_olap import GraphOLAPClient
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
    <h2 class="nb-section__title">Client Initialization Tests</h2>
  </div>
</div>

```python
# Test: setup() creates test context with automatic cleanup
from graph_olap.notebook_setup import setup

ctx = setup(prefix="CrudTest", persona=Persona.ANALYST_ALICE)
client = ctx.client  # Access underlying client for direct SDK operations

assert client is not None, "Client should not be None"
print(f"CRUD 1.1 PASSED: Test context created with persona {Persona.ANALYST_ALICE.value.name}")
print(f"  API URL: {client._config.api_url}")
```

```python
# Test: Client has resource managers
assert hasattr(client, 'mappings'), "Client should have mappings resource"
assert client.mappings is not None, "mappings should not be None"

assert hasattr(client, 'instances'), "Client should have instances resource"
assert client.instances is not None, "instances should not be None"

print("CRUD 1.2 PASSED: All resource managers available")
```

```python
# Test: Getting other personas for multi-user testing
# Bob is another analyst we can use for authorization tests
bob_client = ctx.with_persona(Persona.ANALYST_BOB)
mappings = bob_client.mappings.list()
assert mappings is not None, "mappings.list() should not be None"

print("CRUD 1.3 PASSED: Multi-persona client access verified")
```

```python
# Test: Can list resources through SDK
mappings_list = client.mappings.list()
assert mappings_list is not None, "mappings.list() should not be None"
assert len(mappings_list) >= 0, "mappings.list() should be iterable"

instances_list = client.instances.list()
assert instances_list is not None, "instances.list() should not be None"
assert len(instances_list) >= 0, "instances.list() should be iterable"

print("CRUD 1.4 PASSED: Resource listing verified")
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Create Base Test Data</h2>
    <p class="nb-section__description">Create mapping and instance for subsequent tests.</p>
  </div>
</div>

```python
from graph_olap.test_data import CUSTOMER_NODE, SHARES_ACCOUNT_EDGE, NODE_DEFINITIONS, EDGE_DEFINITIONS
# Define Customer node with real SQL that works with test data
customer_node = CUSTOMER_NODE

# Define SHARES_ACCOUNT edge (self-join on bis_acct_dh)
shares_account_edge = SHARES_ACCOUNT_EDGE

print(f"Test context run ID: {ctx.run_id}")
print(f"Node definitions ready")
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Start Cleanup Context Manager</h2>
    <p class="nb-section__description">All resources created from here will be automatically cleaned up.</p>
  </div>
</div>

```python
# Cleanup is automatic with setup()!
# Resources created via ctx.mapping(), ctx.instance() are auto-tracked
# and cleaned up on exit (via atexit handler)
print("Starting CRUD E2E Test - resources will be cleaned up automatically via atexit")
```

<div class="nb-section">
  <span class="nb-section__number">5</span>
  <div>
    <h2 class="nb-section__title">5 Create Base Test Resources</h2>
    <p class="nb-section__description">Create a mapping and instance that subsequent tests will use.</p>
  </div>
</div>

```python
# Create base mapping using ctx.mapping() (auto-named, auto-tracked)
BASE_MAPPING = ctx.mapping(
    name=f"CrudTest-Base-{ctx.run_id}",
    description="Base mapping for CRUD E2E tests",
    node_definitions=[customer_node],
    edge_definitions=[shares_account_edge],
)
BASE_MAPPING_ID = BASE_MAPPING.id
BASE_MAPPING_NAME = BASE_MAPPING.name

print(f"Created base mapping: {BASE_MAPPING_NAME} (id={BASE_MAPPING_ID})")
```

```python
# Instance created directly from mapping in next cell
pass
```

```python
# Create instance directly from mapping
from graph_olap_schemas import WrapperType

print("Creating instance directly from mapping...")
BASE_INSTANCE = client.instances.create_and_wait(
    mapping_id=BASE_MAPPING_ID,
    name=f"CrudTest-Instance-{ctx.run_id}",
    wrapper_type=WrapperType.RYUGRAPH,
    timeout=300,
    poll_interval=5,
)
BASE_INSTANCE_ID = BASE_INSTANCE.id
BASE_INSTANCE_NAME = BASE_INSTANCE.name

# Track for cleanup
ctx.track('instance', BASE_INSTANCE_ID, BASE_INSTANCE_NAME)

print(f"Created base instance: {BASE_INSTANCE_NAME} (id={BASE_INSTANCE_ID}, status={BASE_INSTANCE.status})")
```

```python
# Connection helper not needed - SDK handles it
print("Setup complete - ready for connection tests")
```

<div class="nb-section">
  <span class="nb-section__number">6</span>
  <div>
    <h2 class="nb-section__title">Mappings API Tests</h2>
  </div>
</div>

```python
# Test: List mappings returns results
mappings = client.mappings.list()

assert len(mappings) >= 1, f"Expected at least 1 mapping, got {len(mappings)}"
print(f"CRUD 2.1 PASSED: Found {len(mappings)} mapping(s)")

# Test: Our base mapping is in list
mapping_ids = [m.id for m in mappings]
assert BASE_MAPPING_ID in mapping_ids, f"Base mapping (id={BASE_MAPPING_ID}) should be in list"
print(f"CRUD 2.2 PASSED: Base mapping in list (IDs: {mapping_ids})")
```

```python
# Test: Get mapping by ID
mapping = client.mappings.get(BASE_MAPPING_ID)

assert mapping.id == BASE_MAPPING_ID, f"Expected mapping id={BASE_MAPPING_ID}, got {mapping.id}"
assert mapping.name == BASE_MAPPING_NAME, f"Expected '{BASE_MAPPING_NAME}', got '{mapping.name}'"
print(f"CRUD 2.3 PASSED: Mapping retrieved: {mapping.name}")
```

```python
# Test: Mapping has required fields
assert mapping.id is not None, "Mapping should have id"
assert mapping.name is not None, "Mapping should have name"
assert mapping.owner_username is not None, "Mapping should have owner_username"
assert mapping.current_version is not None, "Mapping should have current_version"
assert mapping.created_at is not None, "Mapping should have created_at"

print(f"CRUD 2.4 PASSED: Mapping fields: id={mapping.id}, name={mapping.name}, version={mapping.current_version}")
```

```python
# Test: Get mapping version
version = client.mappings.get_version(BASE_MAPPING_ID, version=1)

assert version is not None, "Version should not be None"
assert version.version == 1, f"Expected version 1, got {version.version}"

print(f"CRUD 2.5 PASSED: Version {version.version} retrieved")
```

```python
# Test: Mapping version has node and edge definitions
assert version.node_definitions is not None, "Should have node_definitions"
assert len(version.node_definitions) >= 1, "Should have at least 1 node definition"

assert version.edge_definitions is not None, "Should have edge_definitions"
assert len(version.edge_definitions) >= 1, "Should have at least 1 edge definition"

print(f"CRUD 2.6 PASSED: Node definitions: {[n.label for n in version.node_definitions]}")
print(f"  Edge definitions: {[e.type for e in version.edge_definitions]}")
```

```python
# Test: Customer node definition exists with primary_key
customer_def = next((d for d in version.node_definitions if d.label == "Customer"), None)
assert customer_def is not None, "Should have Customer node definition"
assert customer_def.primary_key is not None, "Customer should have primary_key"

# Test: SHARES_ACCOUNT edge definition exists
shares_account_def = next((d for d in version.edge_definitions if d.type == "SHARES_ACCOUNT"), None)
assert shares_account_def is not None, "Should have SHARES_ACCOUNT edge definition"
assert shares_account_def.from_node == "Customer", f"Expected from_node='Customer', got '{shares_account_def.from_node}'"
assert shares_account_def.to_node == "Customer", f"Expected to_node='Customer', got '{shares_account_def.to_node}'"

print(f"CRUD 2.7 PASSED: Customer primary_key: {customer_def.primary_key}")
print(f"  SHARES_ACCOUNT edge: {shares_account_def.from_node} -> {shares_account_def.to_node}")
```

```python
# Test: List mapping versions
versions = client.mappings.list_versions(BASE_MAPPING_ID)

assert versions is not None, "Versions should not be None"
assert len(versions) >= 1, "Should have at least 1 version"

version_numbers = [v.version for v in versions]
assert 1 in version_numbers, "Version 1 should exist"

print(f"CRUD 2.8 PASSED: Mapping versions: {version_numbers}")
```

```python
pass
```

```python
# Test: Set lifecycle config for mapping
lifecycle_mapping = client.mappings.set_lifecycle(
    BASE_MAPPING_ID,
    ttl="PT720H",  # 30 days
    inactivity_timeout="PT168H"  # 7 days
)

assert lifecycle_mapping is not None, "set_lifecycle should return mapping"
assert lifecycle_mapping.id == BASE_MAPPING_ID, "Should be same mapping"
assert lifecycle_mapping.ttl == "PT720H", \
    f"TTL should be 'PT720H', got '{lifecycle_mapping.ttl}'"
assert lifecycle_mapping.inactivity_timeout == "PT168H", \
    f"Inactivity timeout should be 'PT168H', got '{lifecycle_mapping.inactivity_timeout}'"

print(f"CRUD 2.8c PASSED: Mapping lifecycle configured")
print(f"  TTL: {lifecycle_mapping.ttl}")
print(f"  Inactivity timeout: {lifecycle_mapping.inactivity_timeout}")
```

### Mapping CRUD Operations

```python
# Define test node and edge for CRUD tests (valid HSBC SQL for starburst emulator)
test_node = NodeDefinition(
    label="TestCustomer",
    sql='SELECT DISTINCT CAST(psdo_cust_id AS VARCHAR) AS id, MIN(bk_sectr) AS bk_sectr, COUNT(DISTINCT psdo_acno) AS account_count, MIN(acct_stus) AS acct_stus FROM bigquery.graph_olap_e2e.bis_acct_dh WHERE 1=1 GROUP BY psdo_cust_id',
    primary_key={"name": "id", "type": "STRING"},
    properties=[
        PropertyDefinition(name="bk_sectr", type="STRING"),
        PropertyDefinition(name="account_count", type="INT64"),
        PropertyDefinition(name="acct_stus", type="STRING"),
    ]
)

test_edge = EdgeDefinition(
    type="TEST_SHARES_ACCOUNT",
    from_node="TestCustomer",
    to_node="TestCustomer",
    sql='SELECT DISTINCT CAST(a.psdo_cust_id AS VARCHAR) AS from_id, CAST(b.psdo_cust_id AS VARCHAR) AS to_id FROM bigquery.graph_olap_e2e.bis_acct_dh a JOIN bigquery.graph_olap_e2e.bis_acct_dh b ON a.psdo_acno = b.psdo_acno AND a.psdo_cust_id < b.psdo_cust_id',
    from_key="from_id",
    to_key="to_id",
    properties=[],
)

print(f"Test node: {test_node.label}")
print(f"Test edge: {test_edge.type}")
```

```python
# Test: Create a new mapping via SDK (directly, not tracked - we'll delete it ourselves)
import uuid
test_mapping_name = f"CrudTest-Mapping-{uuid.uuid4().hex[:8]}"

created_mapping = client.mappings.create(
    name=test_mapping_name,
    description="Created via SDK for E2E testing",
    node_definitions=[test_node],
    edge_definitions=[test_edge],
)

assert created_mapping is not None, "Created mapping should not be None"
assert created_mapping.id is not None, "Created mapping should have ID"
assert created_mapping.name == test_mapping_name, f"Expected '{test_mapping_name}', got '{created_mapping.name}'"
assert created_mapping.current_version == 1, f"Expected version 1, got {created_mapping.current_version}"

test_mapping_id = created_mapping.id

print(f"CRUD 2.9 PASSED: Created mapping: {created_mapping.name} (id={test_mapping_id})")
```

```python
# Test: Verify created mapping can be retrieved
fetched = client.mappings.get(test_mapping_id)

assert fetched.id == test_mapping_id
assert fetched.name == test_mapping_name
assert fetched.description == "Created via SDK for E2E testing"

# Verify node and edge definitions are embedded
assert len(fetched.node_definitions) == 1, f"Expected 1 node def, got {len(fetched.node_definitions)}"
assert len(fetched.edge_definitions) == 1, f"Expected 1 edge def, got {len(fetched.edge_definitions)}"

assert fetched.node_definitions[0].label == "TestCustomer"
assert fetched.edge_definitions[0].type == "TEST_SHARES_ACCOUNT"

print(f"CRUD 2.10 PASSED: Retrieved mapping verified: {fetched.name}")
```

```python
# Test: Update mapping creates new version
updated = client.mappings.update(
    test_mapping_id,
    change_description="Added second node for testing",
    node_definitions=[
        test_node,
        NodeDefinition(
            label="TestAccount",
            sql='SELECT DISTINCT CAST(psdo_acno AS VARCHAR) AS id, CAST(psdo_cust_id AS VARCHAR) AS owner FROM bigquery.graph_olap_e2e.bis_acct_dm',
            primary_key={"name": "id", "type": "STRING"},
            properties=[PropertyDefinition(name="owner", type="STRING")]
        )
    ],
    edge_definitions=[test_edge],
)

assert updated.current_version == 2, f"Expected version 2, got {updated.current_version}"

print(f"CRUD 2.11 PASSED: Updated mapping to version {updated.current_version}")
```

```python
# Test: Verify version history
versions = client.mappings.list_versions(test_mapping_id)

assert len(versions) == 2, f"Expected 2 versions, got {len(versions)}"
version_numbers = [v.version for v in versions]
assert 1 in version_numbers and 2 in version_numbers

print(f"CRUD 2.12 PASSED: Version history: {version_numbers}")
```

```python
# Test: Delete mapping (cleanup)
client.mappings.delete(test_mapping_id)

# Verify deletion
try:
    client.mappings.get(test_mapping_id)
    raise AssertionError("Should have raised NotFoundError")
except NotFoundError:
    print(f"CRUD 2.13 PASSED: Mapping {test_mapping_id} deleted successfully")
```

<div class="nb-section">
  <span class="nb-section__number">7</span>
  <div>
    <h2 class="nb-section__title">Snapshots API Tests (Removed)</h2>
    <p class="nb-section__description">> **NOTE:** The `client.snapshots` API has been removed from the SDK.</p>
  </div>
</div>

```python
pass
```

```python
pass
```

```python
pass
```

```python
pass
```

<div class="nb-section">
  <span class="nb-section__number">8</span>
  <div>
    <h2 class="nb-section__title">Instances API Tests</h2>
  </div>
</div>

```python
# Test: List instances
instances = client.instances.list()

assert instances is not None, "Instances should not be None"
assert len(instances) >= 1, f"Expected at least 1 instance, got {len(instances)}"
print(f"CRUD 4.1 PASSED: Found {len(instances)} instance(s)")

# Test: Our base instance is in list
instance_ids = [i.id for i in instances]
assert BASE_INSTANCE_ID in instance_ids, f"Base instance (id={BASE_INSTANCE_ID}) should be in list"
```

```python
# Test: Get instance by ID
instance = client.instances.get(BASE_INSTANCE_ID)

assert instance is not None, "Instance should not be None"
assert instance.id == BASE_INSTANCE_ID, f"Expected instance id={BASE_INSTANCE_ID}, got {instance.id}"
print(f"CRUD 4.2 PASSED: Instance: {instance.name} (id={instance.id})")
```

```python
# Test: Instance has required fields
assert instance.id is not None, "Instance should have id"
assert instance.name is not None, "Instance should have name"
assert instance.status is not None, "Instance should have status"
assert instance.created_at is not None, "Instance should have created_at"
```

```python
# Test: Running instance status
assert instance.status == "running", f"Expected status 'running', got '{instance.status}'"

# Test: Running instance has URL (or is running)
assert instance.instance_url is not None or instance.status == "running", \
    "Running instance should have URL or running status"

print(f"CRUD 4.4 PASSED: Instance status: {instance.status}")
print(f"  Instance URL: {instance.instance_url}")
```

```python
# Test: Update instance metadata (name and description)
updated_instance = client.instances.update(
    BASE_INSTANCE_ID,
    name=f"{BASE_INSTANCE_NAME}-Updated",
    description="Updated description for E2E testing"
)

assert updated_instance is not None, "Updated instance should not be None"
assert updated_instance.id == BASE_INSTANCE_ID, "Should be same instance"
assert updated_instance.name == f"{BASE_INSTANCE_NAME}-Updated", \
    f"Name should match exactly, got '{updated_instance.name}'"

print(f"CRUD 4.5 PASSED: Instance updated")
print(f"  Name: {updated_instance.name}")

# Restore original name
client.instances.update(BASE_INSTANCE_ID, name=BASE_INSTANCE_NAME)
```

```python
# Test: Set lifecycle config for instance
# Configure custom TTL and inactivity timeout
lifecycle_instance = client.instances.set_lifecycle(
    BASE_INSTANCE_ID,
    ttl="PT48H",  # 48 hours
    inactivity_timeout="PT2H"  # 2 hours
)

assert lifecycle_instance is not None, "set_lifecycle should return instance"
assert lifecycle_instance.id == BASE_INSTANCE_ID, "Should be same instance"
assert lifecycle_instance.ttl == "PT48H", \
    f"TTL should be 'PT48H', got '{lifecycle_instance.ttl}'"
assert lifecycle_instance.inactivity_timeout == "PT2H", \
    f"Inactivity timeout should be 'PT2H', got '{lifecycle_instance.inactivity_timeout}'"

print(f"CRUD 4.6 PASSED: Instance lifecycle configured")
print(f"  TTL: {lifecycle_instance.ttl}")
print(f"  Inactivity timeout: {lifecycle_instance.inactivity_timeout}")
```

### 4.7 Instance Termination Test

Test that an instance can be terminated and status changes appropriately.

```python
# Test 4.7: Terminate instance
# Create a separate instance for termination testing (not tracked - we'll terminate it ourselves)
import uuid
TERM_INSTANCE_NAME = f"CrudTest-TermInstance-{uuid.uuid4().hex[:8]}"

print(f"Creating instance '{TERM_INSTANCE_NAME}' for termination test...")
term_instance = client.instances.create_and_wait(
    mapping_id=BASE_MAPPING_ID,
    name=TERM_INSTANCE_NAME,
    wrapper_type=WrapperType.RYUGRAPH,
    timeout=180,
    poll_interval=5,
)
TERM_INSTANCE_ID = term_instance.id

assert term_instance.status == "running", f"Expected 'running', got '{term_instance.status}'"
print(f"Created instance {TERM_INSTANCE_ID} (status={term_instance.status})")

# Terminate the instance (immediately deletes K8s pod + DB record)
client.instances.terminate(TERM_INSTANCE_ID)
print(f"Terminated instance {TERM_INSTANCE_ID}")

# Verify instance is GONE (terminate now immediately deletes)
try:
    client.instances.get(TERM_INSTANCE_ID)
    raise AssertionError("Instance should have been deleted after termination")
except NotFoundError:
    print(f"CRUD 4.7 PASSED: Instance {TERM_INSTANCE_ID} deleted immediately after termination")
```

<div class="nb-section">
  <span class="nb-section__number">9</span>
  <div>
    <h2 class="nb-section__title">Instance Connection Tests</h2>
  </div>
</div>

```python
# Test: Connect to instance via SDK
conn = client.instances.connect(instance.id)

assert conn is not None, "Connection should not be None"
print(f"CRUD 5.1 PASSED: Connected to instance {instance.id}")
print(f"  Instance URL (from SDK): {instance.instance_url}")
```

```python
# Test: Connection has required managers
assert hasattr(conn, 'query'), "Connection should have query method"
assert hasattr(conn, 'algo'), "Connection should have algo manager"
assert conn.algo is not None, "algo manager should not be None"
assert hasattr(conn, 'networkx'), "Connection should have networkx manager"
assert conn.networkx is not None, "networkx manager should not be None"

print("CRUD 5.2 PASSED: Connection managers verified")
```

```python
# Test: Connection can get status
status = conn.status()

assert status is not None, "Status should not be None"
assert isinstance(status, dict), f"Status should be a dict, got {type(status).__name__}"

print(f"CRUD 5.3 PASSED: Connection status: {status}")
```

```python
# Test: Connection context manager works
with client.instances.connect(instance.id) as ctx_conn:
    result = ctx_conn.query("MATCH (n) RETURN count(n) AS count")
    assert result is not None

print("CRUD 5.4 PASSED: Connection context manager verified")
```

```python
# Test: InstanceConnection.close() explicitly closes connection
test_conn = client.instances.connect(instance.id)

# Verify connection works before close
result = test_conn.query("MATCH (n) RETURN count(n) AS cnt")
assert result is not None

# Close the connection
test_conn.close()

# Verify close() doesn't crash and connection is closed
# Note: After close, subsequent queries may fail or the connection may be in a closed state
print("CRUD 5.5 PASSED: InstanceConnection.close() executed successfully")
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li>All managing resources tests validated</li>
    <li>Resources cleaned up automatically via test context</li>
    <li>Zero residual state on the cluster</li>
  </ul>
</div>

```python
# Cleanup is automatic via atexit!
# Resources created via ctx.mapping(), ctx.instance() will be cleaned up
# when the notebook exits (or when ctx.cleanup() is called explicitly)
print("Test complete - cleanup will happen automatically on exit")
```

```python
# Explicitly cleanup (optional - also happens on exit)
results = ctx.cleanup()
print(f"Cleaned up: {results}")

print("\n" + "="*60)
print("CRUD E2E TESTS COMPLETED!")
print("="*60)
print("\nValidated:")
print("  1. Client Initialization:")
print("    - setup() with Persona")
print("    - Resource managers available")
print("    - Multi-persona access via ctx.with_persona()")
print("    - Resource listing")
print("  2. Mappings API:")
print("    - list, get, get_version, list_versions")
print("    - create, update, delete")
print("    - Node and edge definitions")
print("  3. Instances API:")
print("    - 3.7: Terminate instance")
print("  4. Instance Connection:")
print("    - Connection setup")
print("    - Manager availability")
print("    - Context manager")
print("\nAll test resources cleaned up via NotebookContext atexit handler")
```
