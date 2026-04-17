---
title: "Client Configuration"
---

<div class="nb-header">
  <span class="nb-header__type">Tutorial</span>
  <h1 class="nb-header__title">Client Configuration</h1>
  <p class="nb-header__subtitle">Configure the SDK for development, staging, and production environments</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">20 min</span>
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
  <div class="nb-header__tags"><span class="nb-header__tag">Client</span><span class="nb-header__tag">Configuration</span><span class="nb-header__tag">Environment</span><span class="nb-header__tag">SSL</span><span class="nb-header__tag">Proxy</span></div>
</div>

<div class="nb-objectives">
  <h3 class="nb-objectives__title">What You'll Learn</h3>
  <ul class="nb-objectives__list">
    <li><strong>Environment-based configuration</strong> - Use <code>from_env()</code> to configure the client from environment variables</li>
    <li><strong>Timeouts and retries</strong> - Set custom timeouts and retry policies for production</li>
    <li><strong>SSL and proxy</strong> - Configure SSL verification and proxy for corporate networks</li>
    <li><strong>Context managers</strong> - Use <code>with</code> blocks for automatic resource cleanup</li>
    <li><strong>Connection behavior</strong> - Understand connection pooling and HTTP client behavior</li>
    <li><strong>Quick start vs explicit setup</strong> - Use <code>quick_start()</code> for prototyping vs explicit setup for production</li>
  </ul>
</div>

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

# Cell 3 — Provision
from notebook_setup import provision
personas, conn = provision(USERNAME)
analyst = personas["analyst"]
admin = personas["admin"]
ops = personas["ops"]
client = analyst

print(f"Connected | API: {client._config.api_url}")
print(f"Timeout: {client._config.timeout}s | Username: {client._config.username}")
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Direct Construction</h2>
    <p class="nb-section__description">Understand <code>GraphOLAPClient.__init__()</code> parameters</p>
  </div>
</div>

Since ADR-126, `username` is the only required parameter. All other settings
are resolved from environment variables with baked-in defaults:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `username` | `str` | *required* | Username for `X-Username` header |
| `api_url` | `str \| None` | env / baked-in | Base URL (keyword-only, from `GRAPH_OLAP_API_URL`) |
| `use_case_id` | `str \| None` | env / baked-in | Use case ID (from `GRAPH_OLAP_USE_CASE_ID`) |
| `proxy` | `str \| None` | `None` | HTTP proxy URL |
| `verify` | `bool` | `True` | SSL certificate verification |
| `timeout` | `float` | `30.0` | Request timeout in seconds |
| `max_retries` | `int` | `3` | Max retry attempts |

The sentinel value `"_FILL_ME_IN_"` is rejected with a clear `ValueError`.

```python
# Direct construction with explicit parameters
# (illustration — the shared client is already connected)
print("GraphOLAPClient constructor parameters:")
print(f"  api_url:     {client._config.api_url}")
print(f"  username:    {client._config.username}")
print(f"  timeout:     {client._config.timeout}s")
print(f"  max_retries: {client._config.max_retries}")
print(f"  verify:      {client._config.verify}")
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Environment-Based Configuration</h2>
    <p class="nb-section__description">Use <code>from_env()</code> and <code>GRAPH_OLAP_*</code> environment variables</p>
  </div>
</div>

`GraphOLAPClient.from_env()` reads configuration from environment variables, making it
ideal for deployment scripts and CI/CD pipelines. Explicit keyword arguments override
any environment variable values. Extra `**kwargs` are forwarded to `__init__()`.

Since ADR-126, `from_env()` no longer raises `ValueError` when `GRAPH_OLAP_API_URL`
is unset -- the baked-in default is used instead.

```python
import os

# Show which environment variables from_env() reads
env_vars = [
    "GRAPH_OLAP_API_URL",
    "GRAPH_OLAP_USERNAME",
    "GRAPH_OLAP_USE_CASE_ID",
    "GRAPH_OLAP_PROXY",
    "GRAPH_OLAP_SSL_VERIFY",
]

print("Environment variables for from_env():")
for var in env_vars:
    value = os.environ.get(var, "(not set)")
    print(f"  {var}: {value}")

# from_env() reads these automatically:
# client = GraphOLAPClient.from_env()
# client = GraphOLAPClient.from_env(timeout=60.0)  # override timeout
print("\nfrom_env() is recommended for scripts and applications")
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Environment Profiles</h2>
    <p class="nb-section__description">Three configurations for development, staging, and production</p>
  </div>
</div>

Different environments have different priorities. Development favours fast feedback;
staging mirrors production behind a corporate proxy; production requires strict
verification and resilience.

```python
# Profile 1: Local development (relaxed settings)
# dev_client = GraphOLAPClient(
#     username="developer@local",
#     api_url="http://localhost:8080",  # override the default
#     timeout=60.0,       # Generous timeout for debugging
#     max_retries=1,       # Fail fast during development
#     verify=False,        # No SSL for local
# )

print("Development profile:")
print("  timeout=60s, max_retries=1, verify=False")
print("  Optimized for fast feedback during development")
```

```python
# Profile 2: Staging (corporate proxy + custom SSL)
# staging_client = GraphOLAPClient(
#     username="developer@corp.com",
#     api_url="https://staging.graph-olap.internal",
#     proxy="http://proxy.corp.com:8080",
#     verify=True,
#     timeout=30.0,
#     max_retries=3,
# )

print("Staging profile:")
print("  proxy=http://proxy.corp.com:8080, verify=True")
print("  Routes traffic through corporate proxy")
```

```python
# Profile 3: Production (strict, tuned)
# prod_client = GraphOLAPClient.from_env(
#     timeout=15.0,        # Tight timeout for responsive apps
#     max_retries=5,        # More retries for resilience
# )

print("Production profile:")
print("  timeout=15s, max_retries=5, verify=True (default)")
print("  Use from_env() so credentials stay in environment")
```

<div class="nb-section">
  <span class="nb-section__number">5</span>
  <div>
    <h2 class="nb-section__title">Context Manager Pattern</h2>
    <p class="nb-section__description">Automatic resource cleanup with <code>with</code> blocks</p>
  </div>
</div>

The client implements the context manager protocol. Using a `with` block guarantees
that `close()` is called when the block exits, even if an exception is raised. This
releases the underlying HTTP connection pool.

```python
# Context manager ensures close() is called automatically
with GraphOLAPClient(username=client._config.username) as temp_client:
    health = temp_client.health.check()
    print(f"Health check: {health.status}")
    mappings = temp_client.mappings.list(limit=1)
    print(f"Mappings: {mappings.total}")
# temp_client.close() called automatically here

print("Client closed — resources released")
```

<div class="nb-section">
  <span class="nb-section__number">6</span>
  <div>
    <h2 class="nb-section__title">Quick Start</h2>
    <p class="nb-section__description">Rapid prototyping with <code>quick_start()</code></p>
  </div>
</div>

`quick_start()` combines instance creation and connection into a single call.
It creates an instance from a mapping, waits for it to become ready, and returns
an `InstanceConnection` object ready for queries.

For production code, prefer the explicit two-step flow (`create_and_wait` then
`connect`) which gives you full control over instance lifecycle and error handling.

```python
# quick_start() creates an instance and returns a connection in one call
# Perfect for scripts and one-off analyses:
#
#   conn = client.quick_start(
#       mapping_id=42,
#       wrapper_type="ryugraph",
#       instance_name="analysis-run",
#       wait_timeout=900,
#   )
#   result = conn.query("MATCH (n) RETURN count(n)")
#   conn.close()

# Compare with explicit setup:
# 1. instance = client.instances.create_and_wait(mapping_id=42, ...)
# 2. conn = client.instances.connect(instance.id)
# 3. result = conn.query(...)
# 4. conn.close()

print("quick_start() = create_and_wait() + connect() in one call")
print("Use it for prototyping; use explicit setup for production control")
```

<div class="nb-section">
  <span class="nb-section__number">7</span>
  <div>
    <h2 class="nb-section__title">Resource Attributes</h2>
    <p class="nb-section__description">Overview of all client resource managers</p>
  </div>
</div>

The client exposes domain-specific resource managers as attributes. Each manager
provides CRUD operations for its resource type.

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

print("Client resource attributes:")
for name, resource in resources.items():
    print(f"  client.{name:10s} -> {type(resource).__name__}")
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li><code>username</code> is the only required parameter -- <code>api_url</code> and <code>use_case_id</code> have baked-in defaults (ADR-126)</li>
    <li>Use <code>from_env()</code> in production -- keeps credentials in environment variables</li>
    <li>Set <code>timeout</code> and <code>max_retries</code> based on your environment (generous for dev, tight for prod)</li>
    <li>Use <code>proxy</code> and <code>verify=False</code> only behind corporate proxies or in development</li>
    <li>Always close clients via <code>with</code> block or explicit <code>close()</code> call</li>
    <li><code>quick_start()</code> is ideal for prototyping; explicit setup gives more control in production</li>
  </ul>
</div>
