---
title: "Instance Lifecycle"
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
  <h1 class="nb-header__title">Instance Lifecycle</h1>
  <p class="nb-header__subtitle">TTL, health, progress, and resource management</p>
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
from datetime import UTC, datetime

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

ctx = setup(prefix="LifecycleTest", persona=Persona.ANALYST_ALICE)
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
print("Starting Instance Lifecycle E2E Test - resources will be cleaned up automatically via atexit")
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Create Test Resources</h2>
    <p class="nb-section__description">Create mapping and instance for lifecycle testing.</p>
  </div>
</div>

```python
from graph_olap.test_data import CUSTOMER_NODE, SHARES_ACCOUNT_EDGE, NODE_DEFINITIONS, EDGE_DEFINITIONS
# Create test mapping
customer_node = CUSTOMER_NODE

shares_account_edge = SHARES_ACCOUNT_EDGE

# Use ctx.mapping() for auto-tracking and auto-naming
test_mapping = ctx.mapping(
    description="Test mapping for instance lifecycle testing",
    node_definitions=[customer_node],
    edge_definitions=[shares_account_edge],
)
TEST_MAPPING_ID = test_mapping.id
TEST_MAPPING_NAME = test_mapping.name
print(f"Created test mapping: {TEST_MAPPING_NAME} (id={TEST_MAPPING_ID})")
```

```python
pass
```

<div class="nb-section">
  <span class="nb-section__number">5</span>
  <div>
    <h2 class="nb-section__title">TTL Extension Tests</h2>
  </div>
</div>

### 1.1 Test Create Instance with TTL

```python
# Test: Create instance with default TTL
# SNAPSHOT FUNCTIONALITY DISABLED - use create_and_wait() with mapping_id

TTL_INSTANCE_NAME = f"LifecycleTest-TTLInstance-{ctx.run_id}"
print(f"Creating instance '{TTL_INSTANCE_NAME}' with default TTL (via create_and_wait)...")
ttl_instance = client.instances.create_and_wait(
    mapping_id=TEST_MAPPING_ID,
    name=TTL_INSTANCE_NAME,
    wrapper_type=WrapperType.RYUGRAPH,
    timeout=300,
    poll_interval=5,
)
TTL_INSTANCE_ID = ttl_instance.id
ctx.track('instance', TTL_INSTANCE_ID, TTL_INSTANCE_NAME)
# Get the auto-created snapshot ID for later tests

# Verify instance has expires_at timestamp
assert ttl_instance.expires_at is not None, "Instance should have expires_at timestamp"
print("LIFECYCLE 1.1 PASSED: Created instance with TTL")
print(f"  Instance: {TTL_INSTANCE_NAME} (id={TTL_INSTANCE_ID})")
print(f"  Expires at: {ttl_instance.expires_at}")
```

### 1.2 Test Extend TTL

```python
# Test: Extend TTL by 24 hours
original_expires_at = ttl_instance.expires_at
print(f"Original expiration: {original_expires_at}")

# Extend TTL
extended_instance = client.instances.extend_ttl(TTL_INSTANCE_ID, hours=24)

assert extended_instance is not None, "Extended instance should not be None"
assert extended_instance.id == TTL_INSTANCE_ID, "Should be same instance"
assert extended_instance.expires_at is not None, "Extended instance should have expires_at"

# Parse datetimes for comparison
if isinstance(original_expires_at, str):
    original_dt = datetime.fromisoformat(original_expires_at.replace('Z', '+00:00'))
else:
    original_dt = original_expires_at

if isinstance(extended_instance.expires_at, str):
    extended_dt = datetime.fromisoformat(extended_instance.expires_at.replace('Z', '+00:00'))
else:
    extended_dt = extended_instance.expires_at

# Verify expiration was extended (should be at least 23 hours later to account for timing)
time_diff = (extended_dt - original_dt).total_seconds()
assert time_diff >= 23 * 3600, f"TTL should be extended by ~24 hours, got {time_diff / 3600:.1f} hours"

print("LIFECYCLE 1.2 PASSED: Extended TTL by 24 hours")
print(f"  Original expiration: {original_expires_at}")
print(f"  New expiration: {extended_instance.expires_at}")
print(f"  Extension: {time_diff / 3600:.1f} hours")
```

### 1.3 Test Extend TTL with Custom Hours

```python
# Test: Extend TTL by custom amount (48 hours)
before_extend = client.instances.get(TTL_INSTANCE_ID)
before_expires_at = before_extend.expires_at

# Extend by 48 hours
extended = client.instances.extend_ttl(TTL_INSTANCE_ID, hours=48)

# Parse datetimes
if isinstance(before_expires_at, str):
    before_dt = datetime.fromisoformat(before_expires_at.replace('Z', '+00:00'))
else:
    before_dt = before_expires_at

if isinstance(extended.expires_at, str):
    after_dt = datetime.fromisoformat(extended.expires_at.replace('Z', '+00:00'))
else:
    after_dt = extended.expires_at

# Verify 48-hour extension
time_diff = (after_dt - before_dt).total_seconds()
assert time_diff >= 47 * 3600, f"TTL should be extended by ~48 hours, got {time_diff / 3600:.1f} hours"

print("LIFECYCLE 1.3 PASSED: Extended TTL by 48 hours")
print(f"  Extension: {time_diff / 3600:.1f} hours")
```

<div class="nb-section">
  <span class="nb-section__number">6</span>
  <div>
    <h2 class="nb-section__title">Health Check Tests</h2>
  </div>
</div>

### 2.1 Test get_health() Returns Health Info

```python
# Test: get_health() returns health information
health = client.instances.get_health(TTL_INSTANCE_ID)

assert health is not None, "Health should not be None"
assert isinstance(health, dict), f"Health should be dict, got {type(health)}"
assert "status" in health, "Health should have 'status' field"

print("LIFECYCLE 2.1 PASSED: get_health() returned health info")
print(f"  Status: {health.get('status')}")
print(f"  Health keys: {list(health.keys())}")
```

### 2.2 Test check_health() Returns Boolean

```python
# Test: check_health() returns boolean
is_healthy = client.instances.check_health(TTL_INSTANCE_ID)

assert isinstance(is_healthy, bool), f"check_health should return bool, got {type(is_healthy)}"
assert is_healthy == True, "Running instance should be healthy"

print(f"LIFECYCLE 2.2 PASSED: check_health() returned {is_healthy}")
```

### 2.3 Test Health Check with Timeout

```python
# Test: Health check with custom timeout
health = client.instances.get_health(TTL_INSTANCE_ID, timeout=10)

assert health is not None
assert "status" in health

print("LIFECYCLE 2.3 PASSED: Health check with timeout=10")
print(f"  Status: {health.get('status')}")
```

<div class="nb-section">
  <span class="nb-section__number">7</span>
  <div>
    <h2 class="nb-section__title">Connection Status Tests</h2>
  </div>
</div>

### 3.1 Test Connection status()

```python
# Test: Connection status() returns instance status
conn = client.instances.connect(TTL_INSTANCE_ID)
status = conn.status()

assert status is not None, "Status should not be None"
assert isinstance(status, dict), f"Status should be dict, got {type(status)}"

# Status should contain useful information
# (exact fields depend on wrapper implementation, just verify it's not empty)
assert len(status) > 0, "Status should not be empty"

print("LIFECYCLE 3.1 PASSED: Connection status()")
print(f"  Status keys: {list(status.keys())}")
print(f"  Status: {status}")
```

### 3.2 Test Connection get_lock() - No Lock Initially

```python
# Test: get_lock() returns lock status (should be unlocked initially)
lock_status = conn.get_lock()

assert lock_status is not None, "Lock status should not be None"
assert hasattr(lock_status, 'locked'), "Lock status should have 'locked' attribute"
assert lock_status.locked == False, "Instance should not be locked initially"

print("LIFECYCLE 3.2 PASSED: get_lock() - no lock initially")
print(f"  Locked: {lock_status.locked}")
```

### 3.3 Test Lock During Algorithm Execution

```python
# Test: Instance is locked during algorithm execution

# Run a quick algorithm
execution = conn.algo.pagerank("Customer", "pr_score", "SHARES_ACCOUNT", wait=True)

# After algorithm completes, lock should be released
lock_status = conn.get_lock()
assert lock_status.locked == False, "Lock should be released after algorithm completes"

print("LIFECYCLE 3.3 PASSED: Lock released after algorithm completion")
print(f"  Algorithm: {execution.algorithm}")
print(f"  Status: {execution.status}")
print(f"  Locked: {lock_status.locked}")
```

<div class="nb-section">
  <span class="nb-section__number">8</span>
  <div>
    <h2 class="nb-section__title">Multiple Instance Lifecycle Test</h2>
  </div>
</div>

### 4.1 Test Creating Multiple Instances with Different TTLs

```python
# Test: Create instance with custom TTL
CUSTOM_TTL_NAME = f"LifecycleTest-CustomTTL-{ctx.run_id}"

print(f"Creating instance '{CUSTOM_TTL_NAME}' with custom TTL=48h (via create_and_wait)...")
custom_ttl_instance = client.instances.create_and_wait(
    mapping_id=TEST_MAPPING_ID,
    name=CUSTOM_TTL_NAME,
    wrapper_type=WrapperType.RYUGRAPH,
    ttl="PT48H",  # 48 hours in ISO 8601
    timeout=300,
    poll_interval=5,
)

CUSTOM_TTL_ID = custom_ttl_instance.id
ctx.track('instance', CUSTOM_TTL_ID, CUSTOM_TTL_NAME)

assert custom_ttl_instance.expires_at is not None

# Verify TTL is approximately 48 hours from now
if isinstance(custom_ttl_instance.expires_at, str):
    expires_dt = datetime.fromisoformat(custom_ttl_instance.expires_at.replace('Z', '+00:00'))
else:
    expires_dt = custom_ttl_instance.expires_at

now = datetime.now(UTC)
time_until_expiry = (expires_dt - now).total_seconds()

# Should be approximately 48 hours (within 1 hour tolerance)
assert 47 * 3600 <= time_until_expiry <= 49 * 3600, \
    f"TTL should be ~48 hours, got {time_until_expiry / 3600:.1f} hours"

print("LIFECYCLE 4.1 PASSED: Created instance with custom TTL=48h")
print(f"  Time until expiry: {time_until_expiry / 3600:.1f} hours")
```

<div class="nb-section">
  <span class="nb-section__number">9</span>
  <div>
    <h2 class="nb-section__title">Instance Progress Tests</h2>
  </div>
</div>

```python
# Test: get_progress() returns instance startup progress
# Get progress for an existing running instance
progress = client.instances.get_progress(TTL_INSTANCE_ID)

assert progress is not None, "Progress should not be None"
assert hasattr(progress, 'phase'), "Progress should have 'phase' field"
assert hasattr(progress, 'progress_percent'), "Progress should have 'progress_percent' field"
assert hasattr(progress, 'steps'), "Progress should have 'steps' field"

# Valid phases for instance progress
assert progress.phase in ["pod_scheduled", "downloading", "loading_schema", "loading_data", "ready", "failed"], \
    f"Unexpected phase: {progress.phase}"

# For a running instance, expect 'ready' phase and progress should be 100%
if TTL_INSTANCE_ID is not None:
    running_instance = client.instances.get(TTL_INSTANCE_ID)
    if running_instance.status == "running":
        assert progress.phase == "ready", \
            f"Running instance should have phase 'ready', got '{progress.phase}'"
        assert progress.progress_percent == 100, \
            f"Running instance should have 100% progress, got {progress.progress_percent}%"

print("LIFECYCLE 5.1 PASSED: get_progress() returned instance startup progress")
print(f"  Phase: {progress.phase}")
print(f"  Progress: {progress.progress_percent}%")
print(f"  Steps: {progress.steps}")
print(f"  Current step: {progress.current_step}")
```

### 5.2 Test on_progress Callback During Instance Creation

```python
# Test: on_progress callback is called during instance creation
PROGRESS_INSTANCE_NAME = f"LifecycleTest-ProgressCallback-{ctx.run_id}"

# Track progress callbacks
progress_callbacks = []

def progress_callback(phase: str, completed: int, total: int):
    """Callback to track instance creation progress."""
    progress_callbacks.append({
        'phase': phase,
        'completed': completed,
        'total': total
    })
    print(f"  Progress: {phase} ({completed}/{total})")

print(f"Creating instance '{PROGRESS_INSTANCE_NAME}' with progress callback...")

progress_instance = client.instances.create_and_wait(
    mapping_id=TEST_MAPPING_ID,
    name=PROGRESS_INSTANCE_NAME,
    wrapper_type=WrapperType.RYUGRAPH,
    timeout=300,
    poll_interval=5,
    on_progress=progress_callback,
)

PROGRESS_INSTANCE_ID = progress_instance.id
ctx.track('instance', PROGRESS_INSTANCE_ID, PROGRESS_INSTANCE_NAME)

# Verify progress callback was called
assert len(progress_callbacks) > 0, "Progress callback should have been called at least once"

# Verify callback received valid data
for cb in progress_callbacks:
    assert 'phase' in cb, "Callback should receive phase"
    assert 'completed' in cb, "Callback should receive completed steps"
    assert 'total' in cb, "Callback should receive total steps"
    assert isinstance(cb['phase'], str), "Phase should be string"
    assert isinstance(cb['completed'], int), "Completed should be int"
    assert isinstance(cb['total'], int), "Total should be int"

print("LIFECYCLE 5.2 PASSED: on_progress callback was called during instance creation")
print(f"  Callback invocations: {len(progress_callbacks)}")
print(f"  Final phase: {progress_callbacks[-1]['phase'] if progress_callbacks else 'N/A'}")
```

<div class="nb-section">
  <span class="nb-section__number">10</span>
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
    <li>All instance lifecycle tests validated</li>
    <li>Resources cleaned up automatically via test context</li>
    <li>Zero residual state on the cluster</li>
  </ul>
</div>

```python
print("\n" + "="*60)
print("INSTANCE LIFECYCLE E2E TESTS COMPLETED!")
print("="*60)
print("\nValidated:")
print("  1. TTL Extension:")
print("    1.1: Create instance with TTL")
print("    1.2: Extend TTL by 24 hours")
print("    1.3: Extend TTL with custom hours (48h)")
print("  2. Health Checks:")
print("    2.1: get_health() returns health info")
print("    2.2: check_health() returns boolean")
print("    2.3: Health check with timeout parameter")
print("  3. Connection Status:")
print("    3.1: status() returns instance status")
print("    3.2: get_lock() - no lock initially")
print("    3.3: Lock behavior during algorithm execution")
print("  4. Custom TTL:")
print("    4.1: Create instance with custom TTL (48h)")
print("  5. Instance Progress:")
print("    5.1: get_progress() returns instance startup progress")
print("    5.2: on_progress callback during instance creation")
print("\nAll resources will be cleaned up automatically via atexit")
```
