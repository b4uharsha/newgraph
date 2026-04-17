---
title: "Bookmarks & Favorites"
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
  <h1 class="nb-header__title">Bookmarks & Favorites</h1>
  <p class="nb-header__subtitle">Resource organisation and retrieval</p>
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
# Parameters cell - papermill will inject values here
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
import time

from graph_olap.notebook_setup import setup
from graph_olap.notebook import wake_starburst
from graph_olap.personas import Persona
from graph_olap.exceptions import ConflictError, NotFoundError, ValidationError
from graph_olap.models.mapping import EdgeDefinition, NodeDefinition, PropertyDefinition
from graph_olap_schemas import WrapperType

print(f"Python version: {sys.version}")
print(f"GRAPH_OLAP_API_URL: {os.environ.get('GRAPH_OLAP_API_URL', 'not set')}")

# Wake up Starburst Galaxy cluster (auto-suspends after 5 min idle)
wake_starburst()
```

```python
# Create test context as analyst Alice
ctx = setup(prefix="FavTest", persona=Persona.ANALYST_ALICE)
client = ctx.client

print(f"Connected to {client._config.api_url}")
print(f"Test run ID: {ctx.run_id}")
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Create Test Resources</h2>
    <p class="nb-section__description">Create mapping and instance to test favorites API.</p>
  </div>
</div>

```python
from graph_olap.test_data import CUSTOMER_NODE, SHARES_ACCOUNT_EDGE, NODE_DEFINITIONS, EDGE_DEFINITIONS
# Define node and edge for test mapping
customer_node = CUSTOMER_NODE

shares_account_edge = SHARES_ACCOUNT_EDGE

# Create test mapping (auto-named, auto-tracked)
test_mapping = ctx.mapping(
    node_definitions=[customer_node],
    edge_definitions=[shares_account_edge],
)
TEST_MAPPING_ID = test_mapping.id
TEST_MAPPING_NAME = test_mapping.name
print(f"Created test mapping: {TEST_MAPPING_NAME} (id={TEST_MAPPING_ID})")
```

```python
# Create test instance directly from mapping for favoriting
print(f"Creating instance from mapping for favorites testing...")
test_instance = client.instances.create_and_wait(
    mapping_id=TEST_MAPPING_ID,
    name=f"FavTest-Instance-{ctx.run_id}",
    wrapper_type=WrapperType.RYUGRAPH,
    timeout=300,
    poll_interval=5,
)
TEST_INSTANCE_ID = test_instance.id
TEST_INSTANCE_NAME = test_instance.name
# Track the instance for cleanup
ctx.track('instance', test_instance.id, test_instance.name)
print(f"Created test instance: {TEST_INSTANCE_NAME} (id={TEST_INSTANCE_ID}, status={test_instance.status})")
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Favorites API Tests</h2>
  </div>
</div>

### 1.1 Test Initial State - No Favorites

```python
# Test: Initially no favorites
all_favorites = client.favorites.list()
mapping_favorites = client.favorites.list(resource_type="mapping")
instance_favorites = client.favorites.list(resource_type="instance")

# Should have no favorites initially (clean state)
# Note: Other tests may have created favorites, so we just verify structure
assert all_favorites is not None, "Favorites list should not be None"
assert isinstance(all_favorites, list), "Favorites should be a list"
assert isinstance(mapping_favorites, list), "Mapping favorites should be a list"
assert isinstance(instance_favorites, list), "Instance favorites should be a list"

print(f"FAV 1.1 PASSED: Initial favorites count: {len(all_favorites)}")
print(f"  Mappings: {len(mapping_favorites)}, Instances: {len(instance_favorites)}")
```

### 1.2 Test Add Mapping Favorite

```python
# Test: Add mapping to favorites
initial_count = len(client.favorites.list(resource_type="mapping"))

favorite = client.favorites.add(resource_type="mapping", resource_id=TEST_MAPPING_ID)

assert favorite is not None, "Favorite should not be None"
assert favorite.resource_type == "mapping", f"Expected resource_type 'mapping', got '{favorite.resource_type}'"
assert favorite.resource_id == TEST_MAPPING_ID, f"Expected resource_id {TEST_MAPPING_ID}, got {favorite.resource_id}"

# Verify it appears in list
mapping_favorites = client.favorites.list(resource_type="mapping")
assert len(mapping_favorites) == initial_count + 1, f"Expected {initial_count + 1} mapping favorites, got {len(mapping_favorites)}"

mapping_ids = [f.resource_id for f in mapping_favorites]
assert TEST_MAPPING_ID in mapping_ids, f"Test mapping {TEST_MAPPING_ID} should be in favorites"

print(f"FAV 1.2 PASSED: Added mapping {TEST_MAPPING_ID} to favorites")
```

### 1.4 Test Add Instance Favorite

```python
# Test: Add instance to favorites
initial_count = len(client.favorites.list(resource_type="instance"))

favorite = client.favorites.add(resource_type="instance", resource_id=TEST_INSTANCE_ID)

assert favorite is not None
assert favorite.resource_type == "instance"
assert favorite.resource_id == TEST_INSTANCE_ID

# Verify it appears in list
instance_favorites = client.favorites.list(resource_type="instance")
assert len(instance_favorites) == initial_count + 1

instance_ids = [f.resource_id for f in instance_favorites]
assert TEST_INSTANCE_ID in instance_ids

print(f"FAV 1.4 PASSED: Added instance {TEST_INSTANCE_ID} to favorites")
```

### 1.5 Test List All Favorites

```python
# Test: List all favorites (no filter)
all_favorites = client.favorites.list()

assert all_favorites is not None
assert len(all_favorites) >= 2, f"Expected at least 2 favorites, got {len(all_favorites)}"

# Verify all our test resources are in the list (by resource_type + resource_id)
favorites_by_key = {(f.resource_type, f.resource_id): f for f in all_favorites}

# Check each test resource is in favorites with correct type
mapping_key = ("mapping", TEST_MAPPING_ID)
instance_key = ("instance", TEST_INSTANCE_ID)

assert mapping_key in favorites_by_key, f"Test mapping ({TEST_MAPPING_ID}) should be in all favorites. Keys: {[k for k in favorites_by_key.keys() if k[1] == TEST_MAPPING_ID]}"
assert instance_key in favorites_by_key, f"Test instance ({TEST_INSTANCE_ID}) should be in all favorites. Keys: {[k for k in favorites_by_key.keys() if k[1] == TEST_INSTANCE_ID]}"

# Verify the resource_type is correctly set on each favorite
assert favorites_by_key[mapping_key].resource_type == "mapping"
assert favorites_by_key[instance_key].resource_type == "instance"

print(f"FAV 1.5 PASSED: Listed all favorites (found {len(all_favorites)} total)")
print(f"  All test resources present with correct types")
```

### 1.6 Test Add Duplicate (Should Raise ConflictError)

```python
# Test: Adding duplicate favorite returns ConflictError
initial_count = len(client.favorites.list(resource_type="mapping"))

# Add the same mapping again - should raise ConflictError
try:
    favorite = client.favorites.add(resource_type="mapping", resource_id=TEST_MAPPING_ID)
    raise AssertionError("Expected ConflictError when adding duplicate favorite, but call succeeded")
except ConflictError as e:
    # Expected behavior per API spec
    pass

# Count should not change
final_count = len(client.favorites.list(resource_type="mapping"))
assert final_count == initial_count, f"Duplicate add should not change count: {initial_count} -> {final_count}"

print(f"FAV 1.6 PASSED: Adding duplicate favorite correctly raises ConflictError (count stayed at {final_count})")
```

### 1.7 Test Remove Mapping Favorite

```python
# Test: Remove mapping favorite
initial_count = len(client.favorites.list(resource_type="mapping"))

client.favorites.remove(resource_type="mapping", resource_id=TEST_MAPPING_ID)

# Verify it's removed from list
mapping_favorites = client.favorites.list(resource_type="mapping")
assert len(mapping_favorites) == initial_count - 1, f"Expected {initial_count - 1} favorites, got {len(mapping_favorites)}"

mapping_ids = [f.resource_id for f in mapping_favorites]
assert TEST_MAPPING_ID not in mapping_ids, f"Mapping {TEST_MAPPING_ID} should not be in favorites after removal"

print(f"FAV 1.7 PASSED: Removed mapping {TEST_MAPPING_ID} from favorites")
```

### 1.9 Test Remove Instance Favorite

```python
# Test: Remove instance favorite
initial_count = len(client.favorites.list(resource_type="instance"))

client.favorites.remove(resource_type="instance", resource_id=TEST_INSTANCE_ID)

instance_favorites = client.favorites.list(resource_type="instance")
assert len(instance_favorites) == initial_count - 1

instance_ids = [f.resource_id for f in instance_favorites]
assert TEST_INSTANCE_ID not in instance_ids

print(f"FAV 1.9 PASSED: Removed instance {TEST_INSTANCE_ID} from favorites")
```

### 1.10 Test Remove Non-Existent Favorite (Idempotency)

```python
# Test: Removing non-existent favorite is idempotent (should not error)
initial_count = len(client.favorites.list(resource_type="mapping"))

# Try to remove the already-removed mapping favorite again
client.favorites.remove(resource_type="mapping", resource_id=TEST_MAPPING_ID)

final_count = len(client.favorites.list(resource_type="mapping"))
assert final_count == initial_count, f"Remove should be idempotent: {initial_count} -> {final_count}"

print(f"FAV 1.10 PASSED: Removing non-existent favorite is idempotent")
```

### 1.11 Test Cascade Delete - Deleting Resource Deletes Favorites

```python
# Test: Cascade delete - deleting instance should delete its favorites
# Re-add instance to favorites (we removed it in test 1.9)
client.favorites.add(resource_type="instance", resource_id=TEST_INSTANCE_ID)

# Verify favorite exists
instance_favorites_before = client.favorites.list(resource_type="instance")
instance_ids_before = [f.resource_id for f in instance_favorites_before]
assert TEST_INSTANCE_ID in instance_ids_before, "Instance should be in favorites before delete"

# Terminate the instance (will be removed from ctx tracking)
print(f"Terminating instance {TEST_INSTANCE_ID} to test cascade delete...")
client.instances.terminate(TEST_INSTANCE_ID)

# Wait for instance to be fully terminated (async operation)
# Cascade delete of favorites happens when instance record is deleted from DB
max_wait = 60
poll_interval = 2
waited = 0
terminated = False

while waited < max_wait:
    try:
        instance = client.instances.get(TEST_INSTANCE_ID)
        if instance.status in ("terminated", "stopped"):
            print(f"Instance marked as terminated after {waited}s (status={instance.status})")
            # Continue waiting for full deletion
        else:
            print(f"Waiting for instance termination... (status={instance.status})")
    except NotFoundError:
        # Instance no longer exists - termination complete
        print(f"Instance fully deleted after {waited}s")
        terminated = True
        break
    time.sleep(poll_interval)
    waited += poll_interval

# Small grace period for cascade delete to propagate to favorites table
time.sleep(1)

# Verify favorite was CASCADE DELETED (not just marked as non-existent)
instance_favorites_after = client.favorites.list(resource_type="instance")
instance_ids_after = [f.resource_id for f in instance_favorites_after]
assert TEST_INSTANCE_ID not in instance_ids_after, "Instance favorite should be CASCADE DELETED when instance is terminated"

print(f"FAV 1.11 PASSED: Cascade delete works - favorite was deleted when instance was terminated")
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li>All bookmarks & favorites tests validated</li>
    <li>Resources cleaned up automatically via test context</li>
    <li>Zero residual state on the cluster</li>
  </ul>
</div>

```python
# Teardown test resources
ctx.teardown()
client.close()

print("\n" + "="*60)
print("FAVORITES E2E TESTS COMPLETED!")
print("="*60)
print("\nValidated:")
print("  1. Favorites API:")
print("    1.1: Initial state verification")
print("    1.2: Add mapping favorite")
print("    1.4: Add instance favorite")
print("    1.5: List all favorites (with type filtering)")
print("    1.6: Add duplicate (idempotency)")
print("    1.7: Remove mapping favorite")
print("    1.9: Remove instance favorite")
print("    1.10: Remove non-existent (idempotency)")
print("    1.11: Cascade delete (deleting resource deletes favorites)")
print("\nAll test resources cleaned up")
```
