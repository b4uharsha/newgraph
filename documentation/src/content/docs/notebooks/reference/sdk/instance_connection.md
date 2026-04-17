---
title: "InstanceConnection"
---

<div class="nb-header">
  <span class="nb-header__type">Reference</span>
  <h1 class="nb-header__title">InstanceConnection</h1>
  <p class="nb-header__subtitle">Query execution and data access</p>
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
  <div class="nb-header__tags"><span class="nb-header__tag">Reference</span><span class="nb-header__tag">API</span></div>
</div>

## InstanceConnection

Returned by `client.instances.connect(instance_id)` or the convenience
helper `ctx.connect()`, this object is the primary interface for querying
a running graph instance.

It provides four query methods (`query`, `query_df`, `query_scalar`,
`query_one`), rich result-conversion helpers on `QueryResult`, schema
inspection, lock monitoring, and connection lifecycle management.

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
    <h2 class="nb-section__title">Query Methods</h2>
    <p class="nb-section__description">Execute Cypher queries in different modes</p>
  </div>
</div>

### `query(cypher, parameters, *, timeout, coerce_types) -> QueryResult`

Execute a Cypher query and return a `QueryResult` with multiple conversion
options. Results are iterable as dicts.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `cypher` | `str` | *required* | Cypher query string |
| `parameters` | `dict[str, Any] \| None` | `None` | Query parameters |
| `timeout` | `float \| None` | `None` | Override default timeout (seconds) |
| `coerce_types` | `bool` | `True` | Convert DATE/TIMESTAMP to Python types |

**Returns:** `QueryResult` (iterable, convertible to DataFrame/NetworkX/CSV/Parquet).

**Raises:** `RyugraphError` on query failure; `QueryTimeoutError` on timeout.

```python
# Basic query -- iterate rows as dicts
result = conn.query("MATCH (c:Customer) RETURN c.id, c.acct_stus LIMIT 5")
for row in result:
    print(f"  {row['c.id']} ({row['c.acct_stus']})")
```

```python
# Get a real customer ID first
first_id = conn.query_scalar("MATCH (c:Customer) RETURN c.id LIMIT 1")

# Parameterized query
result = conn.query(
    "MATCH (c:Customer) WHERE c.acct_stus = $id RETURN c.id, c.acct_stus",
    parameters={"id": first_id},
)
for row in result:
    print(f"  {row['c.id']} ({row['c.acct_stus']})")
```

### `query_df(cypher, parameters, *, backend) -> DataFrame`

Execute a query and return a Polars or Pandas DataFrame directly.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `cypher` | `str` | *required* | Cypher query string |
| `parameters` | `dict[str, Any] \| None` | `None` | Query parameters |
| `backend` | `str` | `"polars"` | `"polars"` or `"pandas"` |

**Returns:** `polars.DataFrame` (default) or `pandas.DataFrame`.

```python
# DataFrame conversion (default: Polars)
df = conn.query_df("MATCH (c:Customer) RETURN c.id, c.acct_stus LIMIT 10")
print(df)
```

```python
# Pandas backend
pdf = conn.query_df(
    "MATCH (c:Customer) RETURN c.id, c.acct_stus LIMIT 5",
    backend="pandas",
)
print(pdf)
```

### `query_scalar(cypher, parameters) -> Any`

Execute a query that returns a single value.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `cypher` | `str` | *required* | Cypher returning one row, one column |
| `parameters` | `dict[str, Any] \| None` | `None` | Query parameters |

**Returns:** Single value (`int`, `float`, `str`, etc.).

**Raises:** `ValueError` if the result has more than one row or column.

```python
# Scalar query
count = conn.query_scalar("MATCH (n) RETURN count(n)")
print(f"Total nodes: {count}")
```

### `query_one(cypher, parameters) -> dict | None`

Execute a query and return the first row as a dict, or `None` if the result
is empty.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `cypher` | `str` | *required* | Cypher query string |
| `parameters` | `dict[str, Any] \| None` | `None` | Query parameters |

**Returns:** `dict[str, Any]` or `None`.

```python
# Get a real customer ID first
first_id = conn.query_scalar("MATCH (c:Customer) RETURN c.id LIMIT 1")

# Single-row lookup
customer = conn.query_one(
    "MATCH (c:Customer {id: $id}) RETURN c.id, c.acct_stus",
    parameters={"id": first_id},
)
if customer:
    print(f"Found: {customer}")
else:
    print("Not found")
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Result Conversion</h2>
    <p class="nb-section__description">QueryResult output formats</p>
  </div>
</div>

The `QueryResult` returned by `query()` supports several conversion methods:

| Method | Returns | Description |
|--------|---------|-------------|
| `to_polars()` | `polars.DataFrame` | Convert to Polars DataFrame |
| `to_pandas()` | `pandas.DataFrame` | Convert to Pandas DataFrame |
| `to_networkx()` | `networkx.DiGraph` | Build graph from node/edge results |
| `to_csv(path)` | `None` | Export to CSV file |
| `to_parquet(path)` | `None` | Export to Parquet file |
| `to_dicts()` | `list[dict]` | Convert to list of row dicts |
| `scalar()` | `Any` | Extract single scalar value |
| `show()` | display | Auto-select table or graph visualization |

```python
# Polars DataFrame
result = conn.query("MATCH (c:Customer) RETURN c.id, c.acct_stus LIMIT 5")
pl_df = result.to_polars()
print(pl_df)
```

```python
# Pandas DataFrame
pd_df = result.to_pandas()
print(pd_df)
```

```python
# List of dicts
rows = result.to_dicts()
for row in rows:
    print(row)
```

```python
# Export to file
result.to_csv("/tmp/customers.csv")
result.to_parquet("/tmp/customers.parquet")
print("Exported to /tmp/customers.csv and /tmp/customers.parquet")
```

```python
# Auto-visualization in Jupyter
# Tabular data -> interactive table; graph data -> pyvis network
result.show()
```

```python
# Scalar extraction
count_result = conn.query("MATCH (n) RETURN count(n)")
print(count_result.scalar())
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Schema &amp; Status</h2>
    <p class="nb-section__description">Inspect the graph structure and connection state</p>
  </div>
</div>

### `get_schema() -> Schema`

Return the graph schema with node labels, relationship types, and their
properties.

**Returns:** `Schema` with `node_labels`, `relationship_types`, `node_count`, `relationship_count`.

```python
schema = conn.get_schema()

print(f"Nodes: {schema.node_count:,}  Relationships: {schema.relationship_count:,}\n")

print("Node labels:")
for label, props in schema.node_labels.items():
    joined = ", ".join(props)
    print(f"  :{label}  ({joined})")

print("\nRelationship types:")
for rel_type, props in schema.relationship_types.items():
    joined = ", ".join(props) if props else "no properties"
    print(f"  [:{rel_type}]  ({joined})")
```

### `get_lock() -> LockStatus`

Check whether the instance is locked by a running algorithm.

**Returns:** `LockStatus` with `locked`, `holder_name`, `algorithm`,
`execution_id`, `locked_at`.

```python
lock = conn.get_lock()
if lock.locked:
    print(f"Locked by {lock.holder_name}, running {lock.algorithm}")
else:
    print("Instance is unlocked")
```

### `status() -> dict`

Get live instance status including resource usage.

**Returns:** `dict` with `memory_usage`, `disk_usage`, `uptime`, `lock_status`.

```python
info = conn.status()
for key, val in info.items():
    print(f"  {key}: {val}")
```

### Connection Properties

| Property | Type | Description |
|----------|------|-------------|
| `id` | `int \| None` | Instance ID |
| `name` | `str \| None` | Instance name |
| `snapshot_id` | `int \| None` | Snapshot ID |
| `current_status` | `str \| None` | Cached status string (use `status()` for live data) |

```python
print(f"ID:          {conn.id}")
print(f"Name:        {conn.name}")
print(f"Snapshot ID: {conn.snapshot_id}")
print(f"Status:      {conn.current_status}")
```

<div class="nb-section">
  <span class="nb-section__number">5</span>
  <div>
    <h2 class="nb-section__title">Connection Lifecycle</h2>
    <p class="nb-section__description">Open and close connections</p>
  </div>
</div>

### `close()`

Close the underlying HTTP connection. After calling `close()`, further
queries will fail.

### Context Manager

`InstanceConnection` implements `__enter__` / `__exit__`, so you can use
it in a `with` block for automatic cleanup.

```python
# Explicit close
tmp_conn = client.instances.connect(conn.id)
count = tmp_conn.query_scalar("MATCH (n) RETURN count(n)")
print(f"Nodes: {count}")
tmp_conn.close()
```

```python
# Context manager -- connection closes automatically
with client.instances.connect(conn.id) as c:
    count = c.query_scalar("MATCH (n) RETURN count(n)")
    print(f"Nodes: {count}")
# c is closed here
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li><code>query()</code> returns a <code>QueryResult</code> that is iterable as dicts and convertible to Polars, Pandas, NetworkX, CSV, and Parquet</li>
    <li><code>query_df()</code> is a shortcut that returns a DataFrame directly (Polars by default)</li>
    <li><code>query_scalar()</code> and <code>query_one()</code> simplify single-value and single-row lookups</li>
    <li><code>get_schema()</code> reveals node labels, relationship types, and their properties</li>
    <li>Use the context manager (<code>with</code>) to ensure connections are closed automatically</li>
  </ul>
</div>
