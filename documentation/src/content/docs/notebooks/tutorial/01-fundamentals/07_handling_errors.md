---
title: "Handling Errors"
---

<div class="nb-header">
  <span class="nb-header__type">Tutorial</span>
  <h1 class="nb-header__title">Handling Errors</h1>
  <p class="nb-header__subtitle">Understand the exception hierarchy and implement robust error handling</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">20 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--intermediate">
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
      </span>
      Intermediate
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">Errors</span><span class="nb-header__tag">Exceptions</span><span class="nb-header__tag">Debugging</span><span class="nb-header__tag">Retry</span></div>
</div>

<div class="nb-objectives">
  <h3 class="nb-objectives__title">What You'll Learn</h3>
  <ul class="nb-objectives__list">
    <li><strong>Exception Hierarchy</strong> - Understand GraphOLAPError subtypes</li>
    <li><strong>Common Errors</strong> - Handle not-found, validation, and permission errors</li>
    <li><strong>Retry Logic</strong> - Implement retry for transient failures</li>
    <li><strong>Debugging</strong> - Use error details for troubleshooting</li>
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

print(f"Connected | {conn.query_scalar('MATCH (n) RETURN count(n)')} nodes")
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Exception Hierarchy</h2>
    <p class="nb-section__description">GraphOLAPError and its subtypes</p>
  </div>
</div>

```python
from graph_olap.exceptions import (
    GraphOLAPError,          # base class for all SDK errors
    PermissionDeniedError,   # insufficient permissions
    NotFoundError,           # resource does not exist
    ValidationError,         # invalid request parameters
    ConflictError,           # resource conflict
    ConcurrencyLimitError,   # too many concurrent requests
    InvalidStateError,       # wrong resource state
    ResourceLockedError,     # resource is locked by another operation
    QueryTimeoutError,       # query exceeded time limit
    AlgorithmTimeoutError,   # algorithm exceeded time limit
    ServerError,             # internal server error
    ServiceUnavailableError, # service temporarily unavailable
)

# Hierarchy:
# GraphOLAPError
#   +-- PermissionDeniedError
#   +-- NotFoundError
#   +-- ValidationError
#   +-- ConflictError
#   |     +-- ConcurrencyLimitError
#   |     +-- InvalidStateError
#   |     +-- ResourceLockedError
#   +-- TimeoutError
#   |     +-- QueryTimeoutError
#   |     +-- AlgorithmTimeoutError
#   +-- ServerError
#         +-- ServiceUnavailableError

print("Exception hierarchy loaded successfully")
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Handling Common Errors</h2>
    <p class="nb-section__description">Catch specific exceptions for robust code</p>
  </div>
</div>

```python
# Handle a NotFoundError when fetching a non-existent mapping
try:
    client.mappings.get(999999)
except NotFoundError as e:
    print(f"NotFoundError: {e}")
except GraphOLAPError as e:
    print(f"SDK error: {e}")

# Handle a ValidationError with an invalid mapping id
try:
    client.mappings.get(-1)
except ValidationError as e:
    print(f"ValidationError: {e}")
except GraphOLAPError as e:
    print(f"SDK error: {e}")

# Handle a NotFoundError when querying a non-existent graph instance
try:
    client.instances.get(888888)
except NotFoundError as e:
    print(f"NotFoundError: {e}")
except GraphOLAPError as e:
    print(f"SDK error: {e}")
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Retry Logic</h2>
    <p class="nb-section__description">Handle transient failures with exponential backoff</p>
  </div>
</div>

```python
import time

def with_retry(func, max_retries=3):
    """Retry a function with exponential backoff for transient errors."""
    for attempt in range(max_retries):
        try:
            return func()
        except (ConcurrencyLimitError, ServerError, ServiceUnavailableError) as e:
            if attempt == max_retries - 1:
                raise
            wait = 2 ** attempt
            print(f"Attempt {attempt + 1} failed: {e}. Retrying in {wait}s...")
            time.sleep(wait)

# Usage: retry-safe listing of Customer/SHARES_ACCOUNT mappings
mappings = with_retry(lambda: client.mappings.list())
print(f"Retrieved {len(mappings)} mappings with retry logic")
for m in mappings:
    print(f"  Mapping {m.id}: {m.name}")
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li>All SDK errors inherit from <code>GraphOLAPError</code> -- use it as a catch-all</li>
    <li>Use <code>NotFoundError</code> for missing resources and <code>ValidationError</code> for bad input</li>
    <li>Retry transient errors (<code>ConcurrencyLimitError</code>, <code>ServerError</code>, <code>ServiceUnavailableError</code>) with exponential backoff</li>
    <li>Catch specific exceptions first, then fall back to <code>GraphOLAPError</code></li>
  </ul>
</div>
