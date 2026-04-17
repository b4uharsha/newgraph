---
title: "GraphOLAPClient"
---

<div class="nb-header">
  <span class="nb-header__type">Reference</span>
  <h1 class="nb-header__title">GraphOLAPClient</h1>
  <p class="nb-header__subtitle">Client construction and lifecycle</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">10 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--beginner">
        <span class="nb-difficulty__dot"></span>
      </span>
      Beginner
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">Reference</span><span class="nb-header__tag">API</span></div>
</div>

## GraphOLAPClient

The top-level entry point for the Graph OLAP SDK. `GraphOLAPClient` holds
the HTTP transport, identity headers, and exposes every resource manager
(mappings, instances, schema, etc.) as typed attributes.

Most notebooks never construct the client directly -- `notebook_setup.setup()`
returns a context whose `.client` attribute is a fully configured instance.

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
print(f"Connected | {conn.query_scalar('MATCH (n) RETURN count(n)')} nodes")
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Client Construction</h2>
    <p class="nb-section__description">Creating a client instance</p>
  </div>
</div>

### `__init__(api_url, username=None, *, use_case_id=None, proxy=None, verify=True, timeout=30.0, max_retries=3)`

Create a client by providing the control-plane URL and an optional username.
The username is sent as the `X-Username` header on every request (ADR-104/105).
If omitted, the SDK falls back to `DEFAULT_USERNAME`.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `api_url` | `str` | *required* | Base URL for the control plane API |
| `username` | `str \| None` | `None` | Username for `X-Username` header |
| `use_case_id` | `str \| None` | `None` | Use case ID for `X-Use-Case-Id` header (ADR-102) |
| `proxy` | `str \| None` | `None` | HTTP proxy URL |
| `verify` | `bool` | `True` | Whether to verify SSL certificates |
| `timeout` | `float` | `30.0` | Request timeout in seconds |
| `max_retries` | `int` | `3` | Maximum retry attempts for transient failures |

**Returns:** `GraphOLAPClient`

```python
from graph_olap.client import GraphOLAPClient

# Direct construction (illustration only -- use notebook_setup in notebooks)
# client = GraphOLAPClient(
#     api_url="https://api.example.com",
#     username="analyst_alice",
#     timeout=60.0,
# )

# In practice, notebook_setup gives you a ready client:
print(f"API URL:  {client._config.api_url}")
print(f"Username: {client._config.username}")
print(f"Timeout:  {client._config.timeout}s")
```

### `from_env(api_url=None, username=None, **kwargs) -> GraphOLAPClient`

Factory method that reads connection details from environment variables.
Explicit arguments override the corresponding variable.

| Environment Variable | Description |
|----------------------|-------------|
| `GRAPH_OLAP_API_URL` | Base URL for the control plane API |
| `GRAPH_OLAP_USERNAME` | Username for `X-Username` header |
| `GRAPH_OLAP_USE_CASE_ID` | Use case ID for `X-Use-Case-Id` header |
| `GRAPH_OLAP_PROXY` | HTTP proxy URL |
| `GRAPH_OLAP_SSL_VERIFY` | Whether to verify SSL certificates |

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `api_url` | `str \| None` | `None` | Override `GRAPH_OLAP_API_URL` |
| `username` | `str \| None` | `None` | Override `GRAPH_OLAP_USERNAME` |
| `**kwargs` | | | Forwarded to `__init__` (`timeout`, `max_retries`, etc.) |

**Returns:** `GraphOLAPClient`

**Raises:** `ValueError` if `GRAPH_OLAP_API_URL` is not set and `api_url` is not provided.

```python
# from_env reads GRAPH_OLAP_* environment variables.
# In notebooks the environment is pre-configured by notebook_setup,
# so this is equivalent to what setup() already provides.
#
# client = GraphOLAPClient.from_env()
# client = GraphOLAPClient.from_env(timeout=60.0)

print("from_env() reads: GRAPH_OLAP_API_URL, GRAPH_OLAP_USERNAME, ...")
print(f"Current client type: {type(client).__name__}")
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Resource Attributes</h2>
    <p class="nb-section__description">Sub-resources exposed by the client</p>
  </div>
</div>

The client exposes every control-plane domain as a typed resource attribute.
Each resource provides its own set of CRUD and query methods.

```python
resources = {
    "mappings":  client.mappings,
    "instances": client.instances,
    "favorites": client.favorites,
    "schema":    client.schema,
    "ops":       client.ops,
    "admin":     client.admin,
    "health":    client.health,
    "users":     client.users,
}

for name, resource in resources.items():
    print(f"  client.{name:10s} -> {type(resource).__name__}")
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Quick Start</h2>
    <p class="nb-section__description">From mapping to connected instance in one call</p>
  </div>
</div>

### `quick_start(mapping_id, wrapper_type, *, instance_name=None, wait_timeout=900) -> InstanceConnection`

Convenience method that combines `instances.create_and_wait()` and
`instances.connect()` into a single call. Returns an `InstanceConnection`
ready for queries.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `mapping_id` | `int` | *required* | Source mapping ID |
| `wrapper_type` | `WrapperType` | *required* | `"falkordb"` or `"ryugraph"` |
| `instance_name` | `str \| None` | `None` | Name for the instance (defaults to `"Quick Instance"`) |
| `wait_timeout` | `int` | `900` | Max seconds to wait for instance creation |

**Returns:** `InstanceConnection` ready for queries.

Under the hood this method:
1. Calls `instances.create_and_wait()` with the given mapping and wrapper type
2. Calls `instances.connect()` on the resulting instance
3. Returns the live connection

```python
# quick_start() creates an instance and returns a connection in one call.
# It is NOT used in reference notebooks (setup() provides the connection),
# but it is ideal for scripts and one-off analyses.
#
# Example:
#   conn = client.quick_start(mapping_id=42, wrapper_type="falkordb")
#   result = conn.query("MATCH (n) RETURN count(n) AS total")
#   conn.close()

# In reference notebooks, setup() provides the connection directly:
result = conn.query("MATCH (n) RETURN count(n) AS total")
print(f"Nodes: {result.scalar()}")
```

<div class="nb-section">
  <span class="nb-section__number">5</span>
  <div>
    <h2 class="nb-section__title">Context Manager &amp; Cleanup</h2>
    <p class="nb-section__description">Managing client lifecycle</p>
  </div>
</div>

### `close() -> None`

Close the underlying HTTP transport and release resources. Always call
`close()` when you are done with the client, or use the context-manager
pattern below.

### `__enter__() -> GraphOLAPClient` / `__exit__(*args) -> None`

The client implements the context-manager protocol. Using `with` ensures
that `close()` is called automatically, even if an exception is raised.

```python
with GraphOLAPClient.from_env() as client:
    mappings = client.mappings.list()
    # ... work with the client ...
# client.close() is called automatically here
```

```python
# The context-manager pattern (illustration -- do not close the shared client)
#
# with GraphOLAPClient.from_env() as c:
#     print(c.health.ready())
#     mappings = c.mappings.list()
# # c.close() called automatically

print("Context manager ensures close() is called on exit.")
print(f"Client is open: {type(client._http).__name__}")
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li>Use <code>notebook_setup.setup()</code> in notebooks -- it returns a pre-configured <code>client</code> and <code>conn</code></li>
    <li><code>from_env()</code> is the recommended constructor for scripts and applications</li>
    <li>The client exposes eight resource attributes: <code>mappings</code>, <code>instances</code>, <code>favorites</code>, <code>schema</code>, <code>ops</code>, <code>admin</code>, <code>health</code>, <code>users</code></li>
    <li><code>quick_start()</code> goes from a mapping ID to a live query connection in a single call</li>
    <li>Always close the client via <code>close()</code> or a <code>with</code> block to release HTTP resources</li>
  </ul>
</div>
