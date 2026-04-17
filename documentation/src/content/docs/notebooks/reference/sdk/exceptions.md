---
title: "Exceptions"
---

<div class="nb-header">
  <span class="nb-header__type">Reference</span>
  <h1 class="nb-header__title">Exceptions</h1>
  <p class="nb-header__subtitle">Error handling and exception hierarchy</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">10 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--intermediate">
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
      </span>
      Intermediate
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">Reference</span><span class="nb-header__tag">API</span><span class="nb-header__tag">Errors</span></div>
</div>

## Exceptions

The SDK defines a structured exception hierarchy rooted at `GraphOLAPError`.
Every API error is mapped to a specific exception class, making it easy to
handle different failure modes with standard `try`/`except` patterns.

All exceptions carry a human-readable `.message` and many include a `.details`
dict with machine-readable context (status codes, resource IDs, limits, etc.).

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

```python
import graph_olap.exceptions as exc
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Exception Hierarchy</h2>
    <p class="nb-section__description">The full class tree</p>
  </div>
</div>

All SDK exceptions inherit from `GraphOLAPError`, which itself extends
Python's built-in `Exception`.

```
GraphOLAPError
  ├── AuthenticationError
  ├── PermissionDeniedError
  │     └── ForbiddenError
  ├── NotFoundError
  ├── ValidationError
  ├── ConflictError
  │     ├── ResourceLockedError
  │     ├── ConcurrencyLimitError
  │     ├── DependencyError
  │     └── InvalidStateError
  ├── TimeoutError
  │     ├── QueryTimeoutError
  │     └── AlgorithmTimeoutError
  ├── RyugraphError
  ├── AlgorithmNotFoundError
  ├── AlgorithmFailedError
  ├── SnapshotFailedError
  ├── InstanceFailedError
  └── ServerError
        └── ServiceUnavailableError
```

Catching `GraphOLAPError` will catch **every** SDK exception. Catch more
specific subclasses first when you need differentiated handling.

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Catching Specific Exceptions</h2>
    <p class="nb-section__description">Try/except patterns for common errors</p>
  </div>
</div>

### NotFoundError

Raised when a requested resource does not exist (HTTP 404).

```python
try:
    client.instances.get(999999)
except exc.NotFoundError as e:
    print(f"Caught NotFoundError: {e}")
    print(f"Details: {e.details}")
```

### ValidationError

Raised when request parameters fail server-side validation (HTTP 422).

```python
try:
    client.instances.create(
        mapping_id=-1,
        name="",
        wrapper_type="falkordb",
    )
except exc.ValidationError as e:
    print(f"Caught ValidationError: {e}")
    print(f"Details: {e.details}")
```

### Accessing exception attributes

Most exceptions expose:

| Attribute | Type | Description |
|-----------|------|-------------|
| `args[0]` | `str` | The error message (also returned by `str(e)`) |
| `.details` | `dict` | Machine-readable context (present on most subclasses) |

Some subclasses add convenience properties. For example, `ConcurrencyLimitError`
exposes `.current_count`, `.max_allowed`, and `.limit_type`.

```python
# Demonstrate attribute access on a caught exception
try:
    client.instances.get(999999)
except exc.NotFoundError as e:
    print(f"Message:     {e}")
    print(f"Details:     {e.details}")
    print(f"Is SDK error: {isinstance(e, exc.GraphOLAPError)}")
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">HTTP Status Mapping</h2>
    <p class="nb-section__description">How API responses become exceptions</p>
  </div>
</div>

### `exception_from_response(status_code, error_code, message, details=None) -> GraphOLAPError`

The SDK uses this factory function internally to convert HTTP error responses
into the appropriate exception class. You normally don't call it directly, but
it is useful for understanding the mapping.

| HTTP Status | Default Exception | Refinements via `error_code` |
|-------------|-------------------|------------------------------|
| 401 | `AuthenticationError` | -- |
| 403 | `ForbiddenError` | -- |
| 404 | `NotFoundError` | -- |
| 409 | `ConflictError` | `RESOURCE_LOCKED`, `DEPENDENCY_EXISTS`, `INVALID_STATE` |
| 422 | `ValidationError` | `VALIDATION_FAILED` |
| 429 | `ConcurrencyLimitError` | `CONCURRENCY_LIMIT` |
| 500 | `ServerError` | `RYUGRAPH_ERROR`, `ALGORITHM_FAILED`, `SNAPSHOT_FAILED`, `INSTANCE_FAILED` |
| 503 | `ServiceUnavailableError` | -- |

When an `error_code` is present, it takes precedence over the HTTP status.

```python
# Factory function in action
e1 = exc.exception_from_response(404, None, "Mapping 42 not found")
print(f"404 -> {type(e1).__name__}: {e1}")

e2 = exc.exception_from_response(409, "RESOURCE_LOCKED", "Instance locked",
                                  {"holder_name": "analyst@bank.com", "algorithm": "PageRank"})
print(f"409 RESOURCE_LOCKED -> {type(e2).__name__}: {e2}")
print(f"  holder: {e2.holder_name}, algorithm: {e2.algorithm}")

e3 = exc.exception_from_response(429, "CONCURRENCY_LIMIT", "Limit exceeded",
                                  {"limit_type": "user", "current_count": 5, "max_allowed": 5})
print(f"429 CONCURRENCY_LIMIT -> {type(e3).__name__}: {e3}")
print(f"  {e3.current_count}/{e3.max_allowed} ({e3.limit_type})")
```

<div class="nb-section">
  <span class="nb-section__number">5</span>
  <div>
    <h2 class="nb-section__title">Best Practices</h2>
    <p class="nb-section__description">Guidelines for robust error handling</p>
  </div>
</div>

1. **Catch specific exceptions before general ones.** Python matches the first
   `except` clause, so place narrow types (`NotFoundError`) before broad ones
   (`GraphOLAPError`).

2. **Use `GraphOLAPError` as a catch-all.** It covers every SDK exception,
   making it ideal for logging or generic fallback handlers.

3. **Inspect `.details` for programmatic decisions.** The dict often contains
   structured data (field names, limits, lock holders) that you can act on
   without parsing the message string.

4. **Let `ConflictError` subtypes guide retry logic.**
   - `ResourceLockedError` -- wait for the lock to release, then retry.
   - `ConcurrencyLimitError` -- terminate an idle instance before creating a new one.
   - `InvalidStateError` -- the resource is in the wrong lifecycle state; check status.

5. **Handle `TimeoutError` separately from server errors.** Timeouts usually
   mean the operation is still running server-side; retrying immediately may
   cause duplicates.

```python
# Recommended pattern: specific-to-general
def safe_get_instance(instance_id: int):
    try:
        return client.instances.get(instance_id)
    except exc.NotFoundError:
        print(f"Instance {instance_id} does not exist")
        return None
    except exc.AuthenticationError:
        print("Session expired -- re-authenticate")
        raise
    except exc.GraphOLAPError as e:
        print(f"Unexpected SDK error: {e}")
        raise

result = safe_get_instance(999999)
print(f"Result: {result}")
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li>All SDK exceptions inherit from <code>GraphOLAPError</code> -- use it as a catch-all</li>
    <li><code>NotFoundError</code>, <code>ValidationError</code>, and <code>ConflictError</code> are the most common in day-to-day use</li>
    <li>Access <code>.details</code> for structured error context beyond the message string</li>
    <li><code>exception_from_response()</code> maps HTTP status codes and API error codes to exception classes</li>
    <li>Catch specific exceptions before <code>GraphOLAPError</code> to handle different failures appropriately</li>
  </ul>
</div>
