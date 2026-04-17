---
title: "Models"
---

<div class="nb-header">
  <span class="nb-header__type">Reference</span>
  <h1 class="nb-header__title">Models</h1>
  <p class="nb-header__subtitle">Data classes and type definitions</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">10 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--beginner">
        <span class="nb-difficulty__dot"></span>
      </span>
      Beginner
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">Reference</span><span class="nb-header__tag">API</span><span class="nb-header__tag">Models</span></div>
</div>

## Models

The SDK uses immutable Pydantic models (and dataclasses for ops) to represent
every API response. All models live in `graph_olap.models` and are re-exported
from the top-level package.

This notebook walks through every model family, showing how to access attributes
on real objects returned by the API.

<div class="nb-section">
  <span class="nb-section__number">1</span>
  <div>
    <h2 class="nb-section__title">Setup</h2>
    <p class="nb-section__description">Connect to the platform</p>
  </div>
</div>

```python
# Cell 1 — Parameters
USERNAME = "_FILL_ME_IN_"  # Set your email before running
```

```python
# Cell 2 — Connect
from graph_olap import GraphOLAPClient
client = GraphOLAPClient(username=USERNAME)
```

```python
# Cell 3 — Provision
from notebook_setup import provision
personas, conn = provision(USERNAME)
analyst = personas["analyst"]
admin = personas["admin"]
ops = personas["ops"]
client = analyst
print(f"Connected to {conn.name} | {conn.query_scalar('MATCH (n) RETURN count(n)')} nodes")
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Instance Models</h2>
    <p class="nb-section__description">Instance, InstanceProgress, InstanceStatus, LockStatus</p>
  </div>
</div>

### `Instance`

Returned by `client.instances.get()`, `.list()`, `.create()`, and related
methods. Key attributes:

| Attribute | Type | Description |
|-----------|------|-------------|
| `id` | `int` | Unique instance ID |
| `name` | `str \| None` | Human-readable name |
| `status` | `str \| None` | Lifecycle state (`running`, `starting`, `failed`, ...) |
| `wrapper_type` | `str \| None` | `"falkordb"` or `"ryugraph"` |
| `owner_username` | `str \| None` | Owner of this instance |
| `snapshot_id` | `int \| None` | Source snapshot ID |
| `created_at` | `datetime \| None` | Creation timestamp |
| `updated_at` | `datetime \| None` | Last update timestamp |
| `expires_at` | `datetime \| None` | TTL expiry |
| `ttl` | `str \| None` | ISO 8601 duration |
| `inactivity_timeout` | `str \| None` | Auto-terminate after idle |
| `memory_usage_bytes` | `int \| None` | Memory consumption |
| `cpu_cores` | `int \| None` | CPU allocation |

Properties: `is_running`, `memory_mb`, `disk_mb`.

```python
# Fetch a running instance and inspect its attributes
instances = client.instances.list(status="running", limit=1)
inst = instances.items[0]

print(f"id:             {inst.id}")
print(f"name:           {inst.name}")
print(f"status:         {inst.status}")
print(f"wrapper_type:   {inst.wrapper_type}")
print(f"owner_username: {inst.owner_username}")
print(f"created_at:     {inst.created_at}")
print(f"is_running:     {inst.is_running}")
print(f"memory_mb:      {inst.memory_mb}")
```

### `InstanceStatus`

Enum of valid instance lifecycle states, re-exported from `graph_olap_schemas`.

| Value | Description |
|-------|-------------|
| `WAITING_FOR_SNAPSHOT` | Pending snapshot creation |
| `STARTING` | Pod is being provisioned |
| `RUNNING` | Ready for queries |
| `STOPPING` | Being terminated |
| `FAILED` | Startup or runtime failure |

```python
from graph_olap.models import InstanceStatus

print("All statuses:")
for s in InstanceStatus:
    print(f"  {s.name} = {s.value!r}")

# Compare with a live instance
print(f"\nInstance status matches RUNNING: {inst.status == InstanceStatus.RUNNING}")
```

### `InstanceProgress`

Returned by `client.instances.get_progress()`. Tracks startup phases.

| Attribute | Type | Description |
|-----------|------|-------------|
| `phase` | `str` | Current phase (`pod_scheduled`, `downloading`, `loading_data`, `ready`, ...) |
| `progress_percent` | `int` | 0--100 completion percentage |
| `current_step` | `str \| None` | Human-readable step description |
| `steps` | `list[dict]` | Detailed step list |
| `error_message` | `str \| None` | Error details if failed |

Properties: `completed_steps`, `total_steps`.

```python
progress = client.instances.get_progress(inst.id)

print(f"phase:            {progress.phase}")
print(f"progress_percent: {progress.progress_percent}%")
print(f"current_step:     {progress.current_step}")
print(f"completed_steps:  {progress.completed_steps}/{progress.total_steps}")
```

### `LockStatus`

Returned by lock-related instance methods. Shows whether an instance is locked
for algorithm execution.

| Attribute | Type | Description |
|-----------|------|-------------|
| `locked` | `bool` | Whether the instance is locked |
| `holder_id` | `str \| None` | ID of the lock holder |
| `holder_name` | `str \| None` | Username of the lock holder |
| `algorithm` | `str \| None` | Algorithm holding the lock |
| `algorithm_type` | `str \| None` | `"native"` or `"networkx"` |
| `execution_id` | `str \| None` | Execution that holds the lock |
| `locked_at` | `datetime \| None` | When the lock was acquired |

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Mapping Models</h2>
    <p class="nb-section__description">Mapping, MappingVersion, MappingDiff, NodeDefinition, EdgeDefinition</p>
  </div>
</div>

### `Mapping`

Returned by `client.mappings.get()` and `.list()`. Represents a graph-to-SQL
mapping definition.

| Attribute | Type | Description |
|-----------|------|-------------|
| `id` | `int` | Mapping ID |
| `name` | `str \| None` | Mapping name |
| `description` | `str \| None` | Human-readable description |
| `owner_username` | `str \| None` | Owner |
| `current_version` | `int \| None` | Latest version number |
| `node_count` | `int \| None` | Number of node types (list endpoint) |
| `edge_type_count` | `int \| None` | Number of edge types (list endpoint) |
| `node_definitions` | `list[NodeDefinition]` | Node definitions (detail endpoint) |
| `edge_definitions` | `list[EdgeDefinition]` | Edge definitions (detail endpoint) |
| `created_at` | `datetime \| None` | Creation timestamp |
| `updated_at` | `datetime \| None` | Last update timestamp |

```python
mappings = client.mappings.list(limit=1)
m = mappings.items[0]

print(f"id:              {m.id}")
print(f"name:            {m.name}")
print(f"owner_username:  {m.owner_username}")
print(f"current_version: {m.current_version}")
print(f"node_count:      {m.node_count}")
print(f"edge_type_count: {m.edge_type_count}")
print(f"created_at:      {m.created_at}")
```

### `MappingVersion`

An immutable snapshot of a mapping at a specific version.

| Attribute | Type | Description |
|-----------|------|-------------|
| `mapping_id` | `int \| None` | Parent mapping ID |
| `version` | `int` | Version number |
| `change_description` | `str \| None` | What changed |
| `node_definitions` | `list[NodeDefinition]` | Node definitions |
| `edge_definitions` | `list[EdgeDefinition]` | Edge definitions |
| `created_at` | `datetime \| None` | When this version was created |
| `created_by` | `str \| None` | Who created it |

### `NodeDefinition` and `EdgeDefinition`

Describe nodes and edges within a mapping version.

**NodeDefinition:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `label` | `str` | Node label |
| `sql` | `str` | SQL query to populate this node |
| `primary_key` | `dict[str, str]` | `{"name": ..., "type": ...}` |
| `properties` | `list[PropertyDefinition]` | Property definitions |

**EdgeDefinition:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `type` | `str` | Relationship type |
| `from_node` | `str` | Source node label |
| `to_node` | `str` | Target node label |
| `sql` | `str` | SQL query |
| `from_key` | `str` | Foreign key on source side |
| `to_key` | `str` | Foreign key on target side |
| `properties` | `list[PropertyDefinition]` | Property definitions |

```python
# Fetch full mapping detail to see definitions
mapping_detail = client.mappings.get(m.id)

for node in mapping_detail.node_definitions:
    print(f"Node: {node.label}")
    print(f"  primary_key: {node.primary_key}")
    print(f"  properties:  {[p.name for p in node.properties]}")
    print(f"  sql:         {node.sql[:60]}...")

print()
for edge in mapping_detail.edge_definitions:
    print(f"Edge: {edge.from_node} --[{edge.type}]--> {edge.to_node}")
    print(f"  from_key: {edge.from_key}, to_key: {edge.to_key}")
```

### `MappingDiff`

Returned by `client.mappings.diff()`. Semantic comparison between two mapping
versions.

| Attribute | Type | Description |
|-----------|------|-------------|
| `mapping_id` | `int` | Mapping ID |
| `from_version` | `int` | Base version |
| `to_version` | `int` | Target version |
| `summary` | `dict[str, int]` | Counts of added/removed/modified nodes and edges |
| `changes` | `dict` | Detailed `NodeDiff` and `EdgeDiff` objects |

Helper methods: `nodes_added()`, `nodes_removed()`, `nodes_modified()`,
`edges_added()`, `edges_removed()`, `edges_modified()`.

### `PrimaryKeyDefinition` and `RyugraphType`

Re-exported from `graph_olap_schemas`:

- `PrimaryKeyDefinition` -- primary key definition with `name` and `type` fields.
- `RyugraphType` -- enum of supported data types (`STRING`, `INT64`, `DOUBLE`,
  `BOOL`, `DATE`, `TIMESTAMP`, etc.).

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Query &amp; Schema Models</h2>
    <p class="nb-section__description">QueryResult, Schema, AlgorithmExecution, Favorite</p>
  </div>
</div>

### `QueryResult`

Returned by `conn.query()`. Supports iteration as dicts, conversion to
DataFrames, and single-value extraction.

| Attribute | Type | Description |
|-----------|------|-------------|
| `columns` | `list[str]` | Column names |
| `column_types` | `list[str]` | Ryugraph types (`STRING`, `INT64`, ...) |
| `rows` | `list[list]` | Raw row data |
| `row_count` | `int` | Number of rows |
| `execution_time_ms` | `int` | Query execution time |

Key methods: `to_polars()`, `to_pandas()`, `to_networkx()`, `scalar()`,
`to_dicts()`, `to_csv(path)`, `to_parquet(path)`, `show()`.

```python
result = conn.query(
    "MATCH (c:Customer) RETURN c.id AS name, c.bk_sectr AS sector LIMIT 3"
)

print(f"columns:          {result.columns}")
print(f"row_count:        {result.row_count}")
print(f"execution_time:   {result.execution_time_ms}ms")
print()

# Iterate as dicts
print("Rows (dict iteration):")
for row in result:
    print(f"  {row['name']} ({row['sector']})")
```

```python
# scalar() -- extract a single value
count = conn.query("MATCH (c:Customer) RETURN count(c) AS cnt").scalar()
print(f"Customer count: {count}")

# to_polars()
df = result.to_polars()
print(f"\nPolars DataFrame:\n{df}")
```

### `Schema`

Returned by `conn.schema()`. Describes the graph structure of a running
instance.

| Attribute | Type | Description |
|-----------|------|-------------|
| `node_labels` | `dict[str, list[str]]` | Label to property names |
| `relationship_types` | `dict[str, list[str]]` | Rel type to property names |
| `node_count` | `int` | Total nodes in the graph |
| `relationship_count` | `int` | Total relationships |

```python
schema = conn.get_schema()

print(f"Nodes: {schema.node_count:,}, Relationships: {schema.relationship_count:,}")
print()
print("Node labels:")
for label, props in schema.node_labels.items():
    print(f"  :{label} -> {props}")
print()
print("Relationship types:")
for rel_type, props in schema.relationship_types.items():
    print(f"  :{rel_type} -> {props}")
```

### `AlgorithmExecution`

Returned by algorithm execution methods. Tracks the status and result of a
graph algorithm run.

| Attribute | Type | Description |
|-----------|------|-------------|
| `execution_id` | `str` | Unique execution ID |
| `algorithm` | `str` | Algorithm name |
| `algorithm_type` | `str \| None` | `"native"` or `"networkx"` |
| `status` | `str` | `"pending"`, `"running"`, `"completed"`, `"failed"`, `"cancelled"` |
| `started_at` | `datetime` | Execution start time |
| `completed_at` | `datetime \| None` | Completion time |
| `duration_ms` | `int \| None` | Total execution time |
| `nodes_updated` | `int \| None` | Nodes written to |
| `result` | `dict \| None` | Algorithm-specific result data |
| `error_message` | `str \| None` | Error details if failed |

### `Favorite`

Represents a user bookmark for a mapping or instance.

| Attribute | Type | Description |
|-----------|------|-------------|
| `resource_type` | `str` | `"mapping"` or `"instance"` |
| `resource_id` | `int` | ID of the bookmarked resource |
| `resource_name` | `str` | Name of the bookmarked resource |
| `created_at` | `datetime` | When the bookmark was created |

<div class="nb-section">
  <span class="nb-section__number">5</span>
  <div>
    <h2 class="nb-section__title">Pagination</h2>
    <p class="nb-section__description">PaginatedList for all list endpoints</p>
  </div>
</div>

### `PaginatedList[T]`

All list endpoints return `PaginatedList`. It wraps a page of results with
metadata for navigating through large result sets.

| Attribute | Type | Description |
|-----------|------|-------------|
| `items` | `list[T]` | Current page of items |
| `total` | `int` | Total number of items across all pages |
| `offset` | `int` | Current page offset |
| `limit` | `int` | Page size |

Properties: `has_more`, `page_count`.

Supports `len()`, iteration, and indexing.

```python
page = client.instances.list(status="running", limit=2, offset=0)

print(f"items:      {len(page.items)} items on this page")
print(f"total:      {page.total} total across all pages")
print(f"offset:     {page.offset}")
print(f"limit:      {page.limit}")
print(f"has_more:   {page.has_more}")
print(f"page_count: {page.page_count}")
print()

# Iterate directly
print("Iteration:")
for inst in page:
    print(f"  [{inst.id}] {inst.name}")

# Index access
print(f"\nFirst item via index: {page[0].name}")
```

<div class="nb-section">
  <span class="nb-section__number">6</span>
  <div>
    <h2 class="nb-section__title">Ops Models</h2>
    <p class="nb-section__description">Cluster health, configuration, and limits (ops role required)</p>
  </div>
</div>

The following models are returned by `client.ops.*` methods and require the
**ops** role. They are documented here for completeness but cannot be
demonstrated without ops credentials.

### `ClusterHealth`

| Attribute | Type | Description |
|-----------|------|-------------|
| `status` | `str` | `"healthy"`, `"degraded"`, `"unhealthy"` |
| `components` | `dict[str, ComponentHealth]` | Per-component health |
| `checked_at` | `datetime` | When health was last checked |

### `ComponentHealth`

| Attribute | Type | Description |
|-----------|------|-------------|
| `status` | `str` | Component status |
| `latency_ms` | `int \| None` | Response latency |
| `error` | `str \| None` | Error message if unhealthy |

### `ClusterInstances`

| Attribute | Type | Description |
|-----------|------|-------------|
| `total` | `int` | Total instances across the cluster |
| `by_status` | `dict[str, int]` | Instance counts per status |
| `by_owner` | `list[OwnerInstanceCount]` | Instance counts per user |
| `limits` | `InstanceLimits` | Current limits |

### `InstanceLimits`

| Attribute | Type | Description |
|-----------|------|-------------|
| `per_analyst` | `int` | Max instances per analyst |
| `cluster_total` | `int` | Max instances cluster-wide |
| `cluster_used` | `int` | Currently used |
| `cluster_available` | `int` | Available capacity |

### `ConcurrencyConfig`

| Attribute | Type | Description |
|-----------|------|-------------|
| `per_analyst` | `int` | Max concurrent instances per analyst |
| `cluster_total` | `int` | Max concurrent instances cluster-wide |
| `updated_at` | `datetime \| None` | Last configuration change |

### `LifecycleConfig`

| Attribute | Type | Description |
|-----------|------|-------------|
| `mapping` | `ResourceLifecycleConfig` | Mapping lifecycle defaults |
| `snapshot` | `ResourceLifecycleConfig` | Snapshot lifecycle defaults |
| `instance` | `ResourceLifecycleConfig` | Instance lifecycle defaults |

Each `ResourceLifecycleConfig` has: `default_ttl`, `default_inactivity`, `max_ttl`.

### `ExportConfig`

| Attribute | Type | Description |
|-----------|------|-------------|
| `max_duration_seconds` | `int` | Maximum export job duration |
| `updated_at` | `datetime \| None` | Last change |
| `updated_by` | `str \| None` | Who changed it |

### `MaintenanceMode`

| Attribute | Type | Description |
|-----------|------|-------------|
| `enabled` | `bool` | Whether maintenance mode is active |
| `message` | `str` | Message shown to users |
| `updated_at` | `datetime \| None` | Last toggle |
| `updated_by` | `str \| None` | Who toggled it |

### `HealthStatus`

| Attribute | Type | Description |
|-----------|------|-------------|
| `status` | `str` | `"ok"` or error state |
| `version` | `str \| None` | API version |
| `database` | `str \| None` | Database connection status |

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li>All models are <strong>immutable</strong> (frozen Pydantic models or frozen dataclasses)</li>
    <li><code>QueryResult</code> supports multiple output formats: dict iteration, <code>to_polars()</code>, <code>to_pandas()</code>, <code>scalar()</code></li>
    <li><code>PaginatedList</code> wraps every list endpoint with <code>.total</code>, <code>.has_more</code>, and direct iteration</li>
    <li>Instance and mapping models carry rich metadata -- timestamps, resource usage, lifecycle state</li>
    <li>Ops models require the <code>ops</code> role and are used for cluster administration</li>
  </ul>
</div>
