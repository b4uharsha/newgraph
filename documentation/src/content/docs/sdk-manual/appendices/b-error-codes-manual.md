---
title: "Appendix B: Error Codes Reference"
scope: hsbc
---

<!-- Verified against code on 2026-04-20 -->

# Appendix B: Error Codes Reference

This appendix is a comprehensive reference for the exceptions **actually
raised by the Graph OLAP SDK** (`graph_olap.exceptions`) and the server
error codes that the SDK maps to them.

Only exception classes and error-code strings that appear in the SDK source
(`packages/graph-olap-sdk/src/graph_olap/exceptions.py`) are documented
here. If a name is not in this appendix, the SDK does not raise it.

## Overview

Every SDK-raised exception inherits from `GraphOLAPError`. You can handle
all SDK errors generically by catching that base class, or catch specific
subclasses for finer-grained handling.

## Exception Hierarchy (as exported by `graph_olap.exceptions`)

```
GraphOLAPError                  (base for all SDK exceptions)
  AuthenticationError           (HTTP 401 — username not recognised by the control plane; ADR-104/105)
  PermissionDeniedError         (carries .details)
    ForbiddenError              (HTTP 403 — user lacks required role)
  NotFoundError                 (HTTP 404 — carries .details)
  ValidationError               (HTTP 422, or any status with error_code=VALIDATION_FAILED — carries .details)
  ConflictError                 (HTTP 409 — carries .details)
    ResourceLockedError         (another algorithm holds the instance lock)
    ConcurrencyLimitError       (HTTP 429 — per-user / cluster-wide cap hit)
    DependencyError             (resource still has dependents)
    InvalidStateError           (operation invalid for current state)
  TimeoutError                  (base class for SDK timeout exceptions)
    QueryTimeoutError           (Cypher query exceeded its budget)
    AlgorithmTimeoutError       (algorithm exceeded its budget)
  RyugraphError                 (Cypher / Ryugraph engine error — carries .details)
  AlgorithmNotFoundError        (unknown algorithm name)
  AlgorithmFailedError          (algorithm execution failed server-side)
  SnapshotFailedError           (implicit snapshot export failed)
  InstanceFailedError           (instance startup failed)
  ServerError                   (HTTP 500 catch-all)
    ServiceUnavailableError     (HTTP 503)
```

> The SDK has no API key. The control plane trusts `X-Username` set by the
> edge proxy (ADR-104/105). `AuthenticationError` therefore means "username
> not recognised" — not "invalid API key".

## HTTP Status → Exception Mapping

These are the mappings in `HTTP_STATUS_TO_EXCEPTION` (used as the fallback
when the server does not return a specific error code):

| HTTP | Exception |
|------|-----------|
| 401 | `AuthenticationError` |
| 403 | `ForbiddenError` |
| 404 | `NotFoundError` |
| 409 | `ConflictError` (or a subclass, if `error_code` is set — see below) |
| 422 | `ValidationError` |
| 429 | `ConcurrencyLimitError` |
| 500 | `ServerError` |
| 503 | `ServiceUnavailableError` |

Other 4xx/5xx responses fall through to the base `GraphOLAPError`.

## Server Error Codes → Exception Mapping

The server returns a structured error body with an `error.code` field. The
SDK function `exception_from_response` maps these codes to exceptions.
**These are the only error codes the SDK recognises**:

| `error.code` | Exception raised | Notes |
|--------------|------------------|-------|
| `VALIDATION_FAILED` | `ValidationError` | `.details` contains field-level info |
| `RESOURCE_LOCKED` | `ResourceLockedError` | `.holder_name`, `.algorithm` populated from `.details` |
| `CONCURRENCY_LIMIT` | `ConcurrencyLimitError` | `.limit_type`, `.current_count`, `.max_allowed` populated from `.details` |
| `DEPENDENCY_EXISTS` | `DependencyError` | Resource still has dependents |
| `INVALID_STATE` | `InvalidStateError` | e.g. operating on a non-running instance |
| `QUERY_TIMEOUT` | `QueryTimeoutError` | Cypher query exceeded server-side timeout |
| `ALGORITHM_TIMEOUT` | `AlgorithmTimeoutError` | Algorithm exceeded server-side timeout |
| `ALGORITHM_NOT_FOUND` | `AlgorithmNotFoundError` | Unknown algorithm name |
| `ALGORITHM_FAILED` | `AlgorithmFailedError` | Algorithm execution error |
| `RYUGRAPH_ERROR` | `RyugraphError` | Cypher/engine error; `.details` has engine info |
| `SNAPSHOT_FAILED` | `SnapshotFailedError` | Implicit snapshot export failed |
| `INSTANCE_FAILED` | `InstanceFailedError` | Instance startup failed |

If the server returns a code not in this table, the SDK falls back to the
HTTP-status mapping above. Any other codes you may have seen in older
drafts (`AUTH_REQUIRED`, `TOKEN_EXPIRED`, `INVALID_TOKEN`, `INVALID_CYPHER`,
`INVALID_MAPPING`, `MAPPING_NOT_FOUND`, `SNAPSHOT_NOT_FOUND`,
`INSTANCE_NOT_FOUND`, `RESOURCE_NOT_FOUND`, `PERMISSION_DENIED`,
`FORBIDDEN`, `ROLE_REQUIRED`, `GATEWAY_TIMEOUT`, `INTERNAL_ERROR`,
`STARBURST_ERROR`, `SERVICE_UNAVAILABLE`) are **not** emitted by the
control plane at the `error.code` level — they were fabricated.

## Exception Details

### Exceptions with a `.details` attribute

These exceptions expose `.details` (a dict) so you can extract structured
server-side context:

- `PermissionDeniedError`, `ForbiddenError`
- `NotFoundError`
- `ValidationError`
- `ConflictError`, `ResourceLockedError`, `ConcurrencyLimitError`, `DependencyError`, `InvalidStateError`
- `RyugraphError`

### `ResourceLockedError` convenience properties

```python
from graph_olap.exceptions import ResourceLockedError

try:
    conn.algo.pagerank("Customer", "pr_score")
except ResourceLockedError as e:
    print(e.holder_name)   # username of the lock holder, or None
    print(e.algorithm)     # algorithm currently holding the lock, or None
```

### `ConcurrencyLimitError` convenience properties

```python
from graph_olap.exceptions import ConcurrencyLimitError

try:
    instance = client.instances.create_and_wait(
        mapping_id=1, name="Analysis", wrapper_type=WrapperType.RYUGRAPH
    )
except ConcurrencyLimitError as e:
    print(e.limit_type)      # "user" or "global"
    print(e.current_count)   # current instance count for that scope
    print(e.max_allowed)     # configured cap
```

## Error Handling Patterns

### Catch-all

```python
from graph_olap.exceptions import GraphOLAPError

try:
    client = GraphOLAPClient.from_env()
    mappings = client.mappings.list()
except GraphOLAPError as e:
    print(f"SDK error: {type(e).__name__}: {e}")
```

### Specific exceptions

```python
from graph_olap_schemas import WrapperType
from graph_olap.exceptions import (
    AuthenticationError,
    NotFoundError,
    ValidationError,
    ConcurrencyLimitError,
    InvalidStateError,
    GraphOLAPError,
)

try:
    instance = client.instances.create_and_wait(
        mapping_id=mapping_id,
        name="Analysis",
        wrapper_type=WrapperType.RYUGRAPH,
    )
except AuthenticationError:
    print("Username not recognised by the control plane (X-Username rejected)")
    raise
except NotFoundError:
    print(f"Mapping {mapping_id} not found")
    raise
except ValidationError as e:
    print(f"Invalid request: {e.details}")
    raise
except ConcurrencyLimitError as e:
    print(f"At capacity ({e.current_count}/{e.max_allowed})")
    raise
except InvalidStateError as e:
    print(f"Mapping version unusable: {e}")
    raise
except GraphOLAPError as e:
    print(f"Unexpected SDK error: {e}")
    raise
```

### Context manager pattern

```python
from graph_olap_schemas import WrapperType
from graph_olap.exceptions import GraphOLAPError

try:
    with GraphOLAPClient.from_env() as client:
        instance = client.instances.create_and_wait(
            mapping_id=1,
            name="Graph",
            wrapper_type=WrapperType.RYUGRAPH,
        )
        try:
            conn = client.instances.connect(instance.id)
            result = conn.query("MATCH (n) RETURN count(n)")
        finally:
            client.instances.terminate(instance.id)
except GraphOLAPError as e:
    print(f"Operation failed: {e}")
```

### Retry with back-off for transient 5xx

```python
import time
from graph_olap.exceptions import ServiceUnavailableError, ServerError

def retry_with_backoff(func, max_retries: int = 3):
    for attempt in range(max_retries):
        try:
            return func()
        except ServiceUnavailableError:
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)
        except ServerError:
            # Non-retryable 5xx — re-raise
            raise

mappings = retry_with_backoff(lambda: client.mappings.list())
```

## Algorithm-specific example

```python
from graph_olap.exceptions import (
    AlgorithmNotFoundError,
    AlgorithmFailedError,
    AlgorithmTimeoutError,
    ResourceLockedError,
    RyugraphError,
)

try:
    conn.algo.pagerank(
        node_label="Customer",
        property_name="pr_score",
        timeout=300,
    )
except AlgorithmNotFoundError as e:
    print(f"Algorithm not available in this wrapper: {e}")
    algos = conn.algo.algorithms()
    print(f"Available: {[a['name'] for a in algos]}")
except ResourceLockedError as e:
    print(f"Instance locked by {e.holder_name} running {e.algorithm}")
except AlgorithmTimeoutError:
    print("Algorithm timed out — try a smaller dataset or longer timeout")
except AlgorithmFailedError as e:
    print(f"Algorithm failed: {e}")
except RyugraphError as e:
    print(f"Engine error: {e} (details: {e.details})")
```

## Lifecycle errors

`create_and_wait()` can surface either a snapshot-phase or instance-phase
failure:

```python
from graph_olap_schemas import WrapperType
from graph_olap.exceptions import SnapshotFailedError, InstanceFailedError

try:
    instance = client.instances.create_and_wait(
        mapping_id=1,
        name="Graph Instance",
        wrapper_type=WrapperType.RYUGRAPH,
    )
except SnapshotFailedError as e:
    print(f"Implicit snapshot export failed: {e}")
except InstanceFailedError as e:
    print(f"Instance startup failed: {e}")
```

## See Also

- [01-getting-started.manual.md](--/01-getting-started.manual.md) — Quick start
- [Appendix A: Environment Variables](-/a-environment-variables.manual.md) — Configuration reference
- [Appendix C: Cypher Reference](-/c-cypher-reference.manual.md) — Query patterns
