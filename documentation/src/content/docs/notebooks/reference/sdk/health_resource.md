---
title: "HealthResource"
---

<div class="nb-header">
  <span class="nb-header__type">Reference</span>
  <h1 class="nb-header__title">HealthResource</h1>
  <p class="nb-header__subtitle">Platform health checks</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">5 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--beginner">
        <span class="nb-difficulty__dot"></span>
      </span>
      Beginner
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">Reference</span><span class="nb-header__tag">API</span></div>
</div>

## HealthResource

Accessed via `client.health`, this resource provides basic health and
readiness checks for the platform.

Both endpoints are unauthenticated -- they work without credentials and
are useful for connectivity verification and monitoring integrations.

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
personas, _ = provision(USERNAME)
analyst = personas["analyst"]
admin = personas["admin"]
ops = personas["ops"]
client = analyst
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Health Check</h2>
    <p class="nb-section__description">Verify platform availability</p>
  </div>
</div>

### `check() -> HealthStatus`

Basic health check. Returns simple health status without checking
dependencies. No authentication required.

**Returns:** `HealthStatus` with the following fields:

| Field | Type | Description |
|-------|------|-------------|
| `status` | `str` | Health status (e.g., `"ok"`) |
| `version` | `str \| None` | API version string |
| `database` | `str \| None` | Not set for basic health |

```python
health = client.health.check()

print(f"Status:  {health.status}")
print(f"Version: {health.version}")
```

### `ready() -> HealthStatus`

Readiness check with database connectivity. Checks database connectivity
in addition to basic health. No authentication required.

**Returns:** `HealthStatus` with all fields populated:

| Field | Type | Description |
|-------|------|-------------|
| `status` | `str` | Health status (e.g., `"ok"`) |
| `version` | `str \| None` | API version string |
| `database` | `str \| None` | Database status (e.g., `"ok"`) |

```python
ready = client.health.ready()

print(f"Status:   {ready.status}")
print(f"Version:  {ready.version}")
print(f"Database: {ready.database}")
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li><code>check()</code> is a lightweight liveness probe -- use it to verify the API is reachable</li>
    <li><code>ready()</code> also verifies database connectivity -- use it for deeper readiness checks</li>
    <li>Both endpoints are unauthenticated, making them safe for monitoring and load-balancer probes</li>
  </ul>
</div>
