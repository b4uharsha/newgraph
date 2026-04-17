---
title: "Appendix B: Error Codes Reference"
scope: hsbc
---

# Appendix B: Error Codes Reference

This appendix provides a comprehensive reference for all error codes, exceptions, and error handling patterns in the Graph OLAP SDK.

## Overview

The SDK uses a hierarchical exception system where all exceptions inherit from `GraphOLAPError`. This enables both catch-all error handling and fine-grained exception handling for specific error types.

## Exception Hierarchy

```
GraphOLAPError (base)
├── AuthenticationError (401)
├── PermissionDeniedError (403)
│   └── ForbiddenError (403)
├── NotFoundError (404)
├── ValidationError (422)
├── ConflictError (409)
│   ├── ResourceLockedError
│   ├── ConcurrencyLimitError (429)
│   ├── DependencyError
│   └── InvalidStateError
├── TimeoutError
│   ├── QueryTimeoutError
│   └── AlgorithmTimeoutError
├── RyugraphError
├── AlgorithmNotFoundError
├── AlgorithmFailedError
├── SnapshotFailedError
├── InstanceFailedError
└── ServerError (5xx)
    └── ServiceUnavailableError (503)
```

## Error Code Reference

### Authentication Errors

| HTTP | Error Code | Exception | Description | Recovery |
|------|------------|-----------|-------------|----------|
| 401 | `AUTH_REQUIRED` | `AuthenticationError` | Missing or invalid authentication | Provide valid API key |
| 401 | `TOKEN_EXPIRED` | `AuthenticationError` | API key has expired | Refresh or regenerate API key |
| 401 | `INVALID_TOKEN` | `AuthenticationError` | Malformed or invalid token | Check API key format |

**Example:**
```python
from graph_olap.exceptions import AuthenticationError

try:
    client = GraphOLAPClient.from_env()
    mappings = client.mappings.list()
except AuthenticationError as e:
    print(f"Authentication failed: {e}")
    print("Check your GRAPH_OLAP_USERNAME environment variable")
```

### Authorization Errors

| HTTP | Error Code | Exception | Description | Recovery |
|------|------------|-----------|-------------|----------|
| 403 | `PERMISSION_DENIED` | `PermissionDeniedError` | User lacks permission for operation | Request appropriate role/permissions |
| 403 | `FORBIDDEN` | `ForbiddenError` | Access to resource forbidden | Check required role (e.g., Ops, Admin) |
| 403 | `ROLE_REQUIRED` | `ForbiddenError` | Operation requires specific role | Contact administrator for role assignment |

**Example:**
```python
from graph_olap.exceptions import ForbiddenError, PermissionDeniedError

try:
    # Ops-only endpoint
    config = client.ops.get_config()
except ForbiddenError as e:
    print(f"Access denied: {e}")
    print("This endpoint requires the Ops role")
except PermissionDeniedError as e:
    print(f"Permission denied: {e.details}")
```

### Resource Errors

| HTTP | Error Code | Exception | Description | Recovery |
|------|------------|-----------|-------------|----------|
| 404 | `RESOURCE_NOT_FOUND` | `NotFoundError` | Requested resource does not exist | Verify resource ID exists |
| 404 | `MAPPING_NOT_FOUND` | `NotFoundError` | Mapping with given ID not found | Check mapping ID |
| 404 | `SNAPSHOT_NOT_FOUND` | `NotFoundError` | Snapshot with given ID not found | Check snapshot ID |
| 404 | `INSTANCE_NOT_FOUND` | `NotFoundError` | Instance with given ID not found | Check instance ID |

**Example:**
```python
from graph_olap.exceptions import NotFoundError

try:
    mapping = client.mappings.get(mapping_id=999)
except NotFoundError as e:
    print(f"Mapping not found: {e}")
    # List available mappings
    mappings = client.mappings.list()
    print(f"Available mappings: {[m.id for m in mappings]}")
```

### Validation Errors

| HTTP | Error Code | Exception | Description | Recovery |
|------|------------|-----------|-------------|----------|
| 422 | `VALIDATION_FAILED` | `ValidationError` | Request validation failed | Fix request parameters per error details |
| 422 | `INVALID_MAPPING` | `ValidationError` | Invalid mapping configuration | Check mapping YAML/JSON syntax |
| 422 | `INVALID_CYPHER` | `ValidationError` | Invalid Cypher query syntax | Fix Cypher query |

**Example:**
```python
from graph_olap.exceptions import ValidationError

try:
    snapshot = client.snapshots.create(
        mapping_id=1,
        name="",  # Invalid: empty name
    )
except ValidationError as e:
    print(f"Validation error: {e}")
    print(f"Details: {e.details}")
    # Details might contain: {"field": "name", "message": "Name cannot be empty"}
```

### Conflict Errors

| HTTP | Error Code | Exception | Description | Recovery |
|------|------------|-----------|-------------|----------|
| 409 | `RESOURCE_LOCKED` | `ResourceLockedError` | Resource is locked by another operation | Wait for lock release, then retry |
| 409 | `DEPENDENCY_EXISTS` | `DependencyError` | Resource has dependencies preventing deletion | Delete dependent resources first |
| 409 | `INVALID_STATE` | `InvalidStateError` | Operation invalid for current state | Wait for correct state or check workflow |
| 429 | `CONCURRENCY_LIMIT` | `ConcurrencyLimitError` | Too many concurrent instances | Terminate unused instances, then retry |

**ResourceLockedError Example:**
```python
from graph_olap.exceptions import ResourceLockedError
import time

try:
    result = conn.algo.pagerank("Customer", "pr_score")
except ResourceLockedError as e:
    print(f"Instance locked by: {e.holder_name}")
    print(f"Running algorithm: {e.algorithm}")
    # Wait and retry
    time.sleep(30)
    result = conn.algo.pagerank("Customer", "pr_score")
```

**ConcurrencyLimitError Example:**
```python
from graph_olap.exceptions import ConcurrencyLimitError

try:
    instance = client.instances.create_from_mapping_and_wait(
        mapping_id=1,
        name="New Instance",
        wrapper_type=WrapperType.RYUGRAPH,
    )
except ConcurrencyLimitError as e:
    print(f"Limit type: {e.limit_type}")  # 'user' or 'global'
    print(f"Current: {e.current_count} / Max: {e.max_allowed}")
    # Terminate unused instances
    instances = client.instances.list()
    for inst in instances:
        if inst.status == "running" and inst.name.startswith("temp-"):
            client.instances.terminate(inst.id)
```

### Timeout Errors

| HTTP | Error Code | Exception | Description | Recovery |
|------|------------|-----------|-------------|----------|
| 408 | `QUERY_TIMEOUT` | `QueryTimeoutError` | Cypher query exceeded timeout | Optimize query or increase timeout |
| 408 | `ALGORITHM_TIMEOUT` | `AlgorithmTimeoutError` | Algorithm execution exceeded timeout | Use smaller dataset or increase timeout |
| 504 | `GATEWAY_TIMEOUT` | `TimeoutError` | Gateway timeout | Retry with exponential backoff |

**Example:**
```python
from graph_olap.exceptions import QueryTimeoutError, AlgorithmTimeoutError

try:
    # Complex query might timeout
    result = conn.query(
        "MATCH (a)-[*1..10]->(b) RETURN count(*)",
        timeout=60
    )
except QueryTimeoutError as e:
    print(f"Query timed out: {e}")
    print("Consider adding query limits or indexes")

try:
    # Algorithm on large graph
    exec_result = conn.algo.pagerank(
        "Customer",
        "pr_score",
        timeout=600
    )
except AlgorithmTimeoutError as e:
    print(f"Algorithm timed out: {e}")
    print("Consider sampling or running on smaller subgraph")
```

### Algorithm Errors

| HTTP | Error Code | Exception | Description | Recovery |
|------|------------|-----------|-------------|----------|
| 404 | `ALGORITHM_NOT_FOUND` | `AlgorithmNotFoundError` | Unknown algorithm name | Check available algorithms via `.algorithms()` |
| 500 | `ALGORITHM_FAILED` | `AlgorithmFailedError` | Algorithm execution failed | Check error message, verify parameters |
| 500 | `RYUGRAPH_ERROR` | `RyugraphError` | Database engine error | Check Cypher syntax, verify graph state |

**Example:**
```python
from graph_olap.exceptions import (
    AlgorithmNotFoundError,
    AlgorithmFailedError,
    RyugraphError
)

try:
    result = conn.algo.run("unknown_algo", node_label="Customer")
except AlgorithmNotFoundError as e:
    print(f"Algorithm not found: {e}")
    # List available algorithms
    algos = conn.algo.algorithms()
    print(f"Available: {[a['name'] for a in algos]}")

try:
    result = conn.algo.pagerank("NonExistentLabel", "pr_score")
except AlgorithmFailedError as e:
    print(f"Algorithm failed: {e}")
except RyugraphError as e:
    print(f"Database error: {e}")
    print(f"Details: {e.details}")
```

### Lifecycle Errors

| HTTP | Error Code | Exception | Description | Recovery |
|------|------------|-----------|-------------|----------|
| 500 | `SNAPSHOT_FAILED` | `SnapshotFailedError` | Snapshot export failed | Check Starburst connectivity, retry |
| 500 | `INSTANCE_FAILED` | `InstanceFailedError` | Instance startup failed | Check logs, verify resources, retry |

**Example:**
```python
from graph_olap.exceptions import SnapshotFailedError, InstanceFailedError

# Recommended: create_from_mapping_and_wait handles both snapshot and instance creation
# It will raise SnapshotFailedError if the internal snapshot export fails
# or InstanceFailedError if the instance startup fails
try:
    instance = client.instances.create_from_mapping_and_wait(
        mapping_id=1,
        name="Graph Instance",
        wrapper_type=WrapperType.RYUGRAPH,
    )
except SnapshotFailedError as e:
    print(f"Snapshot export failed: {e}")
    # The internal snapshot failed during export from Starburst
except InstanceFailedError as e:
    print(f"Instance startup failed: {e}")
    # The instance failed to start (e.g., data loading error)
```

### Server Errors

| HTTP | Error Code | Exception | Description | Recovery |
|------|------------|-----------|-------------|----------|
| 500 | `INTERNAL_ERROR` | `ServerError` | Internal server error | Retry with backoff, contact support |
| 500 | `STARBURST_ERROR` | `ServerError` | Starburst backend error | Check Starburst cluster status |
| 503 | `SERVICE_UNAVAILABLE` | `ServiceUnavailableError` | Service temporarily unavailable | Retry with exponential backoff |

**Example:**
```python
from graph_olap.exceptions import ServerError, ServiceUnavailableError
import time

def retry_with_backoff(func, max_retries=3):
    """Retry function with exponential backoff."""
    for attempt in range(max_retries):
        try:
            return func()
        except ServiceUnavailableError as e:
            if attempt == max_retries - 1:
                raise
            wait_time = 2 ** attempt
            print(f"Service unavailable, retrying in {wait_time}s...")
            time.sleep(wait_time)
        except ServerError as e:
            print(f"Server error: {e}")
            raise

# Usage
mappings = retry_with_backoff(lambda: client.mappings.list())
```

## Error Handling Patterns

### Catch-All Pattern

Handle all SDK errors with a single handler:

```python
from graph_olap.exceptions import GraphOLAPError

try:
    client = GraphOLAPClient.from_env()
    # ... operations
except GraphOLAPError as e:
    print(f"SDK error: {type(e).__name__}: {e}")
    # Log and handle appropriately
```

### Specific Exception Pattern

Handle specific errors differently:

```python
from graph_olap.exceptions import (
    AuthenticationError,
    NotFoundError,
    ValidationError,
    ConcurrencyLimitError,
    GraphOLAPError,
)

try:
    instance = client.instances.create_from_mapping_and_wait(
        mapping_id=mapping_id,
        name="Analysis",
        wrapper_type=WrapperType.RYUGRAPH,
    )
except AuthenticationError:
    print("Invalid credentials - check API key")
    raise
except NotFoundError:
    print(f"Snapshot {snapshot_id} not found")
    raise
except ValidationError as e:
    print(f"Invalid request: {e.details}")
    raise
except ConcurrencyLimitError as e:
    print(f"At capacity ({e.current_count}/{e.max_allowed})")
    # Could implement auto-cleanup here
    raise
except GraphOLAPError as e:
    print(f"Unexpected error: {e}")
    raise
```

### Context Manager Pattern

Use context managers for automatic cleanup:

```python
from graph_olap.exceptions import GraphOLAPError

try:
    with GraphOLAPClient.from_env() as client:
        # Create instance directly from mapping (snapshot managed internally)
        instance = client.instances.create_from_mapping_and_wait(
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

## HTTP Status Code Mapping

| HTTP Status | Exception Class | When Raised |
|-------------|-----------------|-------------|
| 400 | `ValidationError` | Malformed request |
| 401 | `AuthenticationError` | Missing/invalid authentication |
| 403 | `ForbiddenError` | Insufficient permissions |
| 404 | `NotFoundError` | Resource not found |
| 408 | `TimeoutError` | Request timeout |
| 409 | `ConflictError` | State conflict |
| 422 | `ValidationError` | Validation failed |
| 429 | `ConcurrencyLimitError` | Rate/concurrency limit |
| 500 | `ServerError` | Internal server error |
| 503 | `ServiceUnavailableError` | Service unavailable |
| 504 | `TimeoutError` | Gateway timeout |

## Accessing Error Details

Many exceptions provide additional context through the `details` attribute:

```python
from graph_olap.exceptions import ValidationError, ConcurrencyLimitError

try:
    # Operation that might fail
    pass
except ValidationError as e:
    print(f"Message: {e}")
    print(f"Details: {e.details}")
    # e.details might be: {"field": "name", "constraint": "max_length", "value": 100}

except ConcurrencyLimitError as e:
    print(f"Limit type: {e.limit_type}")     # 'user' or 'global'
    print(f"Current count: {e.current_count}")
    print(f"Max allowed: {e.max_allowed}")
```

## See Also

- [SDK Quick Start](--/01-getting-started.manual.html) - Getting started guide
- [Appendix A: Environment Variables](-/a-environment-variables.manual.md) - Configuration reference
- [Appendix C: Cypher Reference](-/c-cypher-reference.manual.md) - Query patterns
