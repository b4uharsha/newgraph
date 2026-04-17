---
title: "Ops Configuration"
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
  <h1 class="nb-header__title">Ops Configuration</h1>
  <p class="nb-header__subtitle">System settings, concurrency, and maintenance</p>
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
# Parameters cell - papermill will inject values here
ANALYST_USER = 'analyst-user'
ADMIN_USER = 'admin-user'
OPS_USER = 'ops-user'
SEEDED_INSTANCE_ID = None  # Injected by papermill from fixtures
```

```python
import sys
import uuid

from graph_olap.notebook_setup import setup
from graph_olap.notebook import wake_starburst
from graph_olap.personas import Persona

# Wake up Starburst Galaxy cluster (auto-suspends after 5 min idle)
wake_starburst()

# Create test context as Ops Dave (primary user for ops tests)
ctx = setup(prefix="OpsTest", persona=Persona.OPS_DAVE)

# Get clients for different roles
ops_client = ctx.client  # Dave (ops)
analyst_client = ctx.with_persona(Persona.ANALYST_ALICE)
admin_client = ctx.with_persona(Persona.ADMIN_CAROL)

print(f"Python version: {sys.version}")
print(f"Test run ID: {ctx.run_id}")
print(f"Primary persona: OPS_DAVE")
print(f"Additional personas: ANALYST_ALICE, ADMIN_CAROL")
```

<div class="nb-section">
  <span class="nb-section__number">1</span>
  <div>
    <h2 class="nb-section__title">Setup and Imports</h2>
  </div>
</div>

```python
from graph_olap.exceptions import (
    ForbiddenError,
    GraphOLAPError,
    NotFoundError,
    PermissionDeniedError,
)
from graph_olap.models import EdgeDefinition, NodeDefinition
from graph_olap.models.mapping import PropertyDefinition
from graph_olap_schemas import WrapperType

print("SDK imports successful")
```

```python
from graph_olap.test_data import CUSTOMER_NODE, SHARES_ACCOUNT_EDGE, NODE_DEFINITIONS, EDGE_DEFINITIONS
# Define test data
customer_node = CUSTOMER_NODE

shares_account_edge = SHARES_ACCOUNT_EDGE

print("Test data schema defined")
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Create Base Test Data</h2>
  </div>
</div>

```python
# Create base mapping using ctx (auto-tracked)
base_mapping = ctx.mapping(
    name=f"{ctx.prefix}-BaseMapping-{ctx.run_id}",
    description="Base mapping for ops testing",
    node_definitions=[customer_node],
    edge_definitions=[shares_account_edge],
)
BASE_MAPPING_ID = base_mapping.id
print(f"Created base mapping: {base_mapping.name} (id={BASE_MAPPING_ID})")
```

```python
# Create base instance from mapping
print(f"Creating base instance from mapping...")

base_instance = ops_client.instances.create_and_wait(
    mapping_id=BASE_MAPPING_ID,
    name=f"{ctx.prefix}-BaseInstance-{ctx.run_id}",
    wrapper_type=WrapperType.RYUGRAPH,
    timeout=300,
    poll_interval=5,
)
BASE_INSTANCE_ID = base_instance.id
ctx.track('instance', BASE_INSTANCE_ID, base_instance.name)

print(f"Created base instance: {base_instance.name} (id={BASE_INSTANCE_ID}, status={base_instance.status})")
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">4 Ops - Config Endpoint Tests</h2>
    <p class="nb-section__description">Tests for ops-only config management endpoints.</p>
  </div>
</div>

```python
# Test 9.4.1: Ops gets lifecycle config
lifecycle = ops_client.ops.get_lifecycle_config()

assert lifecycle is not None, "Lifecycle config should not be None"
assert hasattr(lifecycle, 'mapping'), "Should have mapping config"
assert hasattr(lifecycle, 'snapshot'), "Should have snapshot config"
assert hasattr(lifecycle, 'instance'), "Should have instance config"

print("Test 9.4.1 PASSED: Ops got lifecycle config")
print(f"  Mapping: ttl={lifecycle.mapping.default_ttl}, inactivity={lifecycle.mapping.default_inactivity}")
print(f"  Snapshot: ttl={lifecycle.snapshot.default_ttl}")
print(f"  Instance: ttl={lifecycle.instance.default_ttl}")
```

```python
# Test 9.4.2: Ops updates lifecycle config
# Save original for restoration
original_lifecycle = ops_client.ops.get_lifecycle_config()

# Update instance default TTL
update_result = ops_client.ops.update_lifecycle_config(
    instance={"default_ttl": "PT24H"}
)

assert update_result, "Update should return True"

# Verify update
updated = ops_client.ops.get_lifecycle_config()
assert updated.instance.default_ttl == "PT24H", \
    f"Expected 'PT24H', got '{updated.instance.default_ttl}'"

print("Test 9.4.2 PASSED: Ops updated lifecycle config (instance.default_ttl=PT24H)")

# Restore original
ops_client.ops.update_lifecycle_config(
    instance={"default_ttl": original_lifecycle.instance.default_ttl}
)
```

```python
# Test 9.4.3: Ops gets concurrency config
concurrency = ops_client.ops.get_concurrency_config()

assert concurrency is not None, "Concurrency config should not be None"
assert concurrency.per_analyst > 0, f"per_analyst should be > 0, got {concurrency.per_analyst}"
assert concurrency.cluster_total > 0, f"cluster_total should be > 0, got {concurrency.cluster_total}"

print("Test 9.4.3 PASSED: Ops got concurrency config")
print(f"  per_analyst={concurrency.per_analyst}, cluster_total={concurrency.cluster_total}")
```

```python
# Test 9.4.4: Ops updates concurrency config
# Save original
original_concurrency = ops_client.ops.get_concurrency_config()

# Update
updated_concurrency = ops_client.ops.update_concurrency_config(
    per_analyst=10,
    cluster_total=200,
)

assert updated_concurrency.per_analyst == 10, \
    f"Expected per_analyst=10, got {updated_concurrency.per_analyst}"
assert updated_concurrency.cluster_total == 200, \
    f"Expected cluster_total=200, got {updated_concurrency.cluster_total}"

print("Test 9.4.4 PASSED: Ops updated concurrency config")
print(f"  per_analyst={updated_concurrency.per_analyst}, cluster_total={updated_concurrency.cluster_total}")

# Restore original
ops_client.ops.update_concurrency_config(
    per_analyst=original_concurrency.per_analyst,
    cluster_total=original_concurrency.cluster_total,
)
```

```python
# Test 9.4.5: Ops enables/disables maintenance mode
# Get current state
original_maintenance = ops_client.ops.get_maintenance_mode()

# Enable maintenance mode
enabled = ops_client.ops.set_maintenance_mode(
    enabled=True,
    message="E2E Test - Maintenance mode enabled"
)

assert enabled.enabled, f"Expected enabled=True, got {enabled.enabled}"
assert "E2E Test" in enabled.message, "Expected message to contain 'E2E Test'"

print("Test 9.4.5a PASSED: Ops enabled maintenance mode")
print(f"  enabled={enabled.enabled}, message='{enabled.message}'")

# Disable maintenance mode
disabled = ops_client.ops.set_maintenance_mode(
    enabled=False,
    message=""
)

assert not disabled.enabled, f"Expected enabled=False, got {disabled.enabled}"

print("Test 9.4.5b PASSED: Ops disabled maintenance mode")
```

```python
# Test 9.4.5c: Ops gets/updates export config
export_config = ops_client.ops.get_export_config()

assert export_config is not None, "Export config should not be None"
assert export_config.max_duration_seconds > 0, \
    f"max_duration_seconds should be > 0, got {export_config.max_duration_seconds}"

print("Test 9.4.5c PASSED: Ops got export config")
print(f"  max_duration_seconds={export_config.max_duration_seconds}")

# Update export config
original_export = export_config.max_duration_seconds
updated_export = ops_client.ops.update_export_config(max_duration_seconds=7200)

assert updated_export.max_duration_seconds == 7200, \
    f"Expected 7200, got {updated_export.max_duration_seconds}"

print("Test 9.4.5d PASSED: Ops updated export config to 7200s")

# Restore
ops_client.ops.update_export_config(max_duration_seconds=original_export)
```

```python
# Test 9.4.6: Analyst cannot access config endpoints
try:
    analyst_client.ops.get_lifecycle_config()
    raise AssertionError("Should have raised PermissionDeniedError")
except PermissionDeniedError:
    print("Test 9.4.6 PASSED: Analyst correctly blocked from config endpoints")
except GraphOLAPError as e:
    if isinstance(e, ForbiddenError) or "ops role" in str(e).lower():
        print(f"Test 9.4.6 PASSED: Analyst blocked from config endpoints ({type(e).__name__})")
    else:
        raise
```

```python
# Test 9.4.7: Admin cannot access config endpoints
try:
    admin_client.ops.get_lifecycle_config()
    raise AssertionError("Should have raised PermissionDeniedError")
except PermissionDeniedError:
    print("Test 9.4.7 PASSED: Admin correctly blocked from config endpoints")
except GraphOLAPError as e:
    if isinstance(e, ForbiddenError) or "ops role" in str(e).lower():
        print(f"Test 9.4.7 PASSED: Admin blocked from config endpoints ({type(e).__name__})")
    else:
        raise
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">5 Ops - Cluster Endpoint Tests</h2>
    <p class="nb-section__description">Tests for ops-only cluster monitoring and management endpoints.</p>
  </div>
</div>

```python
# Test 9.5.1: Ops gets cluster health
cluster_health = ops_client.ops.get_cluster_health()

assert cluster_health is not None, "Cluster health should not be None"
assert cluster_health.status in ["healthy", "degraded", "unhealthy"], \
    f"Unexpected status: '{cluster_health.status}'"
assert cluster_health.components is not None, "Should have components dict"
assert cluster_health.checked_at is not None, "Should have checked_at timestamp"

print("Test 9.5.1 PASSED: Ops got cluster health")
print(f"  status={cluster_health.status}")
print(f"  components: {list(cluster_health.components.keys())}")
for name, comp in cluster_health.components.items():
    print(f"    {name}: status={comp.status}, latency={comp.latency_ms}ms")
```

```python
# Test 9.5.2: Ops gets cluster instances summary
cluster_instances = ops_client.ops.get_cluster_instances()

assert cluster_instances is not None, "Cluster instances should not be None"
assert cluster_instances.total >= 0, f"total should be >= 0, got {cluster_instances.total}"
assert cluster_instances.by_status is not None, "Should have by_status dict"
assert cluster_instances.by_owner is not None, "Should have by_owner list"
assert cluster_instances.limits is not None, "Should have limits"

print("Test 9.5.2 PASSED: Ops got cluster instances summary")
print(f"  total={cluster_instances.total}")
print(f"  by_status={cluster_instances.by_status}")
print(f"  limits: per_analyst={cluster_instances.limits.per_analyst}, "
      f"cluster_total={cluster_instances.limits.cluster_total}, "
      f"used={cluster_instances.limits.cluster_used}, "
      f"available={cluster_instances.limits.cluster_available}")
```

```python
# Test 9.5.3: Ops gets cluster metrics
# Cluster metrics are exposed via get_cluster_instances() which includes:
# - Instance counts by status and owner
# - Capacity metrics: limits, used, available

# Re-fetch to verify metrics fields
cluster_metrics = ops_client.ops.get_cluster_instances()

# Validate capacity metrics
assert cluster_metrics.limits is not None, "Should have limits (capacity metrics)"
assert cluster_metrics.limits.per_analyst >= 1, \
    f"per_analyst should be >= 1, got {cluster_metrics.limits.per_analyst}"
assert cluster_metrics.limits.cluster_total >= 1, \
    f"cluster_total should be >= 1, got {cluster_metrics.limits.cluster_total}"
assert cluster_metrics.limits.cluster_used >= 0, \
    f"cluster_used should be >= 0, got {cluster_metrics.limits.cluster_used}"
assert cluster_metrics.limits.cluster_available >= 0, \
    f"cluster_available should be >= 0, got {cluster_metrics.limits.cluster_available}"

# Validate usage metrics (by_status shows instance distribution)
assert cluster_metrics.by_status is not None, "Should have by_status metrics"
assert cluster_metrics.by_owner is not None, "Should have by_owner metrics"

# Validate metrics consistency
assert cluster_metrics.limits.cluster_used + cluster_metrics.limits.cluster_available == \
    cluster_metrics.limits.cluster_total, \
    "used + available should equal total capacity"

print("Test 9.5.3 PASSED: Ops got cluster metrics")
print(f"  Capacity: {cluster_metrics.limits.cluster_used}/{cluster_metrics.limits.cluster_total} "
      f"({cluster_metrics.limits.cluster_available} available)")
print(f"  Per-analyst limit: {cluster_metrics.limits.per_analyst}")
print(f"  Instance distribution: {cluster_metrics.by_status}")
```

```python
# Test 9.5.3b: Ops gets raw Prometheus metrics
prometheus_metrics = ops_client.ops.get_metrics()

assert prometheus_metrics is not None, "get_metrics should return data"
assert isinstance(prometheus_metrics, str), f"Expected string (Prometheus format), got {type(prometheus_metrics)}"
assert len(prometheus_metrics) > 0, "Metrics should not be empty"

# Prometheus metrics format should contain HELP or TYPE comments
# or metric lines with labels
assert "# " in prometheus_metrics or "\n" in prometheus_metrics, \
    "Response should be Prometheus text format"

# Count approximate number of metric lines
metric_lines = [line for line in prometheus_metrics.split('\n') if line and not line.startswith('#')]
metric_count = len(metric_lines)

print("Test 9.5.3b PASSED: Ops got raw Prometheus metrics")
print(f"  Response length: {len(prometheus_metrics)} characters")
print(f"  Approximate metric lines: {metric_count}")
print(f"  Sample (first 200 chars): {prometheus_metrics[:200]}...")
```

```python
# Test 9.5.4: Ops force terminates instance
# Create instance using ctx (auto-tracked)
test_instance = ctx.instance(
    base_mapping,
    name=f"{ctx.prefix}-ForceInst-{uuid.uuid4().hex[:8]}",
    wrapper_type=WrapperType.RYUGRAPH,
    timeout=300,
)

print(f"Created instance {test_instance.id}")

# Force terminate via regular terminate (ops has elevated permissions)
ops_client.instances.terminate(test_instance.id)

# Verify instance is GONE (terminate now immediately deletes)
try:
    ops_client.instances.get(test_instance.id)
    raise AssertionError("Instance should have been deleted after termination")
except NotFoundError:
    # Remove from cleanup list since we just deleted it
    ctx._resources = [(t, i, n) for t, i, n in ctx._resources if not (t == 'instance' and i == test_instance.id)]
    print(f"Test 9.5.4 PASSED: Ops force terminated instance (id={test_instance.id}, immediately deleted)")
```

```python
# Test 9.5.5: Analyst cannot access cluster endpoints
try:
    analyst_client.ops.get_cluster_health()
    raise AssertionError("Should have raised PermissionDeniedError")
except PermissionDeniedError:
    print("Test 9.5.5 PASSED: Analyst correctly blocked from cluster endpoints")
except GraphOLAPError as e:
    if isinstance(e, ForbiddenError) or "ops role" in str(e).lower():
        print(f"Test 9.5.5 PASSED: Analyst blocked from cluster endpoints ({type(e).__name__})")
    else:
        raise
```

```python
# Test 9.5.6: Admin cannot access cluster endpoints
try:
    admin_client.ops.get_cluster_health()
    raise AssertionError("Should have raised PermissionDeniedError")
except PermissionDeniedError:
    print("Test 9.5.6 PASSED: Admin correctly blocked from cluster endpoints")
except GraphOLAPError as e:
    if isinstance(e, ForbiddenError) or "ops role" in str(e).lower():
        print(f"Test 9.5.6 PASSED: Admin blocked from cluster endpoints ({type(e).__name__})")
    else:
        raise
```

<div class="nb-section">
  <span class="nb-section__number">5</span>
  <div>
    <h2 class="nb-section__title">6 Ops - Background Job Management</h2>
    <p class="nb-section__description">Tests for ops job trigger, status query, system state, and export jobs endpoints</p>
  </div>
</div>

```python
# Test 9.6.1: Ops triggers background job
result = ops_client.ops.trigger_job("reconciliation", reason="e2e-test")
assert result["status"] == "queued", f"Expected status='queued', got '{result['status']}'"

print("Test 9.6.1 PASSED: Ops triggered reconciliation job")
print(f"  job={result.get('job')}, status={result['status']}")
```

```python
# Test 9.6.2: Ops validates job name (invalid job name rejected)
try:
    ops_client.ops.trigger_job("invalid_job_name", reason="test")
    raise AssertionError("Should reject invalid job name")
except GraphOLAPError as e:
    # Should get ValidationError for invalid job_name field
    assert "validation" in str(e).lower() or "pattern" in str(e).lower(), \
        f"Expected validation error, got: {e}"

print("Test 9.6.2 PASSED: Invalid job name correctly rejected")
```

```python
# Test 9.6.3: Rate limiting (1 per minute per job)
# First trigger should succeed
result1 = ops_client.ops.trigger_job("lifecycle", reason="rate-limit-test-1")
assert result1["status"] == "queued", f"Expected status='queued', got '{result1['status']}'"

# Immediate second trigger should be rate limited
try:
    ops_client.ops.trigger_job("lifecycle", reason="rate-limit-test-2")
    raise AssertionError("Should enforce rate limiting")
except GraphOLAPError as e:
    assert "429" in str(e) or "rate" in str(e).lower() or "too" in str(e).lower(), \
        f"Expected 429/rate limit error, got: {e}"

print("Test 9.6.3 PASSED: Rate limiting correctly enforced (1 trigger/min/job)")
```

```python
# Test 9.6.4: Ops gets job status
status = ops_client.ops.get_job_status()

assert "jobs" in status, "Response should have 'jobs' field"
assert isinstance(status["jobs"], list), "jobs should be a list"
assert len(status["jobs"]) > 0, "Should have at least one job"

# Verify each job has required fields
for job in status["jobs"]:
    assert "name" in job, "Job should have 'name' field"
    assert job["name"] in ["reconciliation", "lifecycle", "export_reconciliation", "schema_cache", "instance_orchestration", "resource_monitor"], \
        f"Unexpected job name: {job['name']}"

print("Test 9.6.4 PASSED: Job status structure valid")
print(f"  Found {len(status['jobs'])} background jobs: {[j['name'] for j in status['jobs']]}")
```

```python
# Test 9.6.5: Ops gets system state (counts consistency)
state = ops_client.ops.get_state()

# Verify structure
assert "instances" in state, "State should have 'instances'"
assert "snapshots" in state, "State should have 'snapshots'"

# Verify instances counts consistency
instances = state["instances"]
total_instances = instances["total"]
by_status_sum = sum(instances["by_status"].values())
assert total_instances == by_status_sum, \
    f"Instance total ({total_instances}) != sum of by_status ({by_status_sum})"

# Verify snapshots counts consistency
snapshots = state["snapshots"]
total_snapshots = snapshots["total"]
by_status_sum = sum(snapshots["by_status"].values())
assert total_snapshots == by_status_sum, \
    f"Snapshot total ({total_snapshots}) != sum of by_status ({by_status_sum})"

print("Test 9.6.5 PASSED: System state counts are consistent")
print(f"  Instances: total={instances['total']}, by_status={instances['by_status']}")
print(f"  Snapshots: total={snapshots['total']}, by_status={snapshots['by_status']}")
```

```python
# Test 9.6.6: Ops gets export jobs (basic query)
export_jobs = ops_client.ops.get_export_jobs(limit=10)

assert isinstance(export_jobs, list), "export_jobs should be a list"

# If we have jobs, verify structure
if len(export_jobs) > 0:
    job = export_jobs[0]
    required_fields = ["id", "snapshot_id", "entity_type", "entity_name", "status", "attempts"]
    for field in required_fields:
        assert field in job, f"Export job missing required field: {field}"
    
    # Verify status is valid
    assert job["status"] in ["pending", "claimed", "submitted", "completed", "failed"], \
        f"Invalid status: {job['status']}"
    
    # Verify attempts is non-negative
    assert job["attempts"] >= 0, f"attempts should be >= 0, got {job['attempts']}"

print(f"Test 9.6.6 PASSED: Export jobs query returned {len(export_jobs)} jobs")
```

```python
# Test 9.6.7: Ops filters export jobs by status
# Try filtering by each possible status
for status_filter in ["pending", "claimed", "submitted", "completed", "failed"]:
    filtered_jobs = ops_client.ops.get_export_jobs(status=status_filter, limit=100)
    assert isinstance(filtered_jobs, list), f"Filtered jobs should be a list for status={status_filter}"
    
    # All returned jobs should have the requested status
    for job in filtered_jobs:
        assert job["status"] == status_filter, \
            f"Job {job['id']} has status '{job['status']}', expected '{status_filter}'"

print("Test 9.6.7 PASSED: Export jobs status filtering works correctly")
print("  Tested filters: pending, claimed, completed, failed")
```

```python
# Test 9.6.8: Analyst cannot access ops endpoints (authorization)
# Test trigger_job
try:
    analyst_client.ops.trigger_job("reconciliation", reason="test")
    raise AssertionError("Analyst should not access ops.trigger_job")
except (PermissionDeniedError, GraphOLAPError) as e:
    assert isinstance(e, ForbiddenError), \
        f"Expected ForbiddenError, got: {e}"

# Test get_job_status
try:
    analyst_client.ops.get_job_status()
    raise AssertionError("Analyst should not access ops.get_job_status")
except (PermissionDeniedError, GraphOLAPError) as e:
    assert isinstance(e, ForbiddenError), \
        f"Expected ForbiddenError, got: {e}"

# Test get_state
try:
    analyst_client.ops.get_state()
    raise AssertionError("Analyst should not access ops.get_state")
except (PermissionDeniedError, GraphOLAPError) as e:
    assert isinstance(e, ForbiddenError), \
        f"Expected ForbiddenError, got: {e}"

# Test get_export_jobs
try:
    analyst_client.ops.get_export_jobs()
    raise AssertionError("Analyst should not access ops.get_export_jobs")
except (PermissionDeniedError, GraphOLAPError) as e:
    assert isinstance(e, ForbiddenError), \
        f"Expected ForbiddenError, got: {e}"

print("Test 9.6.8 PASSED: Analyst correctly blocked from all ops job/state endpoints")
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li>All ops configuration tests validated</li>
    <li>Resources cleaned up automatically via test context</li>
    <li>Zero residual state on the cluster</li>
  </ul>
</div>

```python
ctx.teardown()

print("\n" + "="*60)
print("OPS E2E TESTS COMPLETED!")
print("="*60)
print("\nValidated:")
print("  9.4 Ops - Config Endpoints:")
print("    - 9.4.1: Ops gets lifecycle config")
print("    - 9.4.2: Ops updates lifecycle config")
print("    - 9.4.3: Ops gets concurrency config")
print("    - 9.4.4: Ops updates concurrency config")
print("    - 9.4.5: Ops manages maintenance mode")
print("    - 9.4.5c/d: Ops gets/updates export config")
print("    - 9.4.6: Analyst cannot access config")
print("    - 9.4.7: Admin cannot access config")
print("  9.5 Ops - Cluster Endpoints:")
print("    - 9.5.1: Ops gets cluster health")
print("    - 9.5.2: Ops gets cluster instances")
print("    - 9.5.3: Ops gets cluster metrics (capacity & distribution)")
print("    - 9.5.4: Ops force terminates instance")
print("    - 9.5.5: Analyst cannot access cluster")
print("    - 9.5.6: Admin cannot access cluster")
print("  9.6 Ops - Background Job Management:")
print("    - 9.6.1: Ops triggers background job")
print("    - 9.6.2: Invalid job name rejected")
print("    - 9.6.3: Rate limiting enforced (1/min/job)")
print("    - 9.6.4: Job status structure valid")
print("    - 9.6.5: System state counts consistent")
print("    - 9.6.6: Export jobs query works")
print("    - 9.6.7: Export jobs status filtering works")
print("    - 9.6.8: Analyst blocked from ops endpoints")
print("\nNote: Health checks (10.x) are in sdk_smoke_test.ipynb")
print("\nAll resources will be cleaned up automatically via atexit")
```
