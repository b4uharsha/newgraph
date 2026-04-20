---
title: "Python Logging Standards"
scope: hsbc
---

# Python Logging Standards

This document establishes coding standards for logging in the Graph OLAP Platform, based on industry best practices from Python's logging documentation, structlog, and the 12-Factor App methodology.

## Table of Contents

1. [Guiding Principles](#guiding-principles)
2. [Log Levels](#log-levels)
3. [Structured Logging with structlog](#structured-logging-with-structlog)
4. [Logger Configuration](#logger-configuration)
5. [Logging Patterns](#logging-patterns)
6. [Production Considerations](#production-considerations)
7. [Anti-Patterns](#anti-patterns)

## Guiding Principles

### Core Philosophy

1. **Structured over unstructured**: Use key-value pairs for machine-parseable logs
2. **Context-rich**: Include correlation IDs, request context, and relevant metadata
3. **Appropriate verbosity**: Log what's necessary, not everything possible
4. **Environment-aware**: Human-readable in development, JSON in production

### The 12-Factor App Approach

> "Logs should be treated as event streams... a twelve-factor app never concerns itself with routing or storage of its output stream."

- Log to stdout/stderr (unbuffered)
- Let orchestration layer (Kubernetes) handle aggregation
- Use structured format (JSON) for log aggregators

## Log Levels

### Level Hierarchy

| Level | Value | Purpose | Production Visibility |
|-------|-------|---------|----------------------|
| **DEBUG** | 10 | Detailed diagnostic information for development | Hidden |
| **INFO** | 20 | Confirmation of normal operation | Visible |
| **WARNING** | 30 | Something unexpected; degraded but functional | Visible |
| **ERROR** | 40 | Serious problem; operation failed | Visible |
| **CRITICAL** | 50 | System may be unable to continue | Visible + Alert |

### When to Use Each Level

#### DEBUG

Use for detailed diagnostic information during development.

```python
logger.debug(
    "cache_lookup",
    key=cache_key,
    hit=cache_hit,
    ttl_remaining=ttl,
)
```

**Use for:**
- Variable values during debugging
- Function entry/exit tracing
- Cache hits/misses
- Query parameters
- Internal state transitions

#### INFO

Use to confirm normal operation and significant events.

```python
logger.info(
    "snapshot_created",
    snapshot_id=snapshot.id,
    mapping_id=mapping.id,
    entity_count=len(entities),
)
```

**Use for:**
- Service startup/shutdown
- Successful completion of significant operations
- Configuration loaded
- External connections established
- Scheduled job execution
- User actions (login, API calls)

#### WARNING

Use when something unexpected happens but the system can continue.

```python
logger.warning(
    "retry_attempt",
    attempt=attempt_num,
    max_attempts=max_retries,
    error=str(e),
    backoff_seconds=backoff,
)
```

**Use for:**
- Retry attempts
- Deprecation warnings
- Configuration falling back to defaults
- Resource thresholds approaching limits
- Recoverable errors
- Unexpected but handled conditions

#### ERROR

Use when an operation fails but the system continues.

```python
logger.error(
    "export_failed",
    job_id=job.id,
    error_type=type(e).__name__,
    error_message=str(e),
    exc_info=True,
)
```

**Use for:**
- Failed operations (API calls, database queries)
- Caught exceptions that prevent completing a task
- External service failures
- Validation failures
- Permission denied errors

#### CRITICAL

Use when the system may not be able to continue.

```python
logger.critical(
    "database_connection_lost",
    host=db_host,
    error=str(e),
    exc_info=True,
)
```

**Use for:**
- Database connection loss
- Required configuration missing
- Critical resource exhaustion
- Unrecoverable state corruption
- Security breaches detected

### Decision Matrix

| Scenario | Level |
|----------|-------|
| Starting HTTP server on port 8080 | INFO |
| Request completed successfully | DEBUG or INFO |
| Retrying failed request (attempt 2/3) | WARNING |
| Request failed after all retries | ERROR |
| Cannot connect to database on startup | CRITICAL |
| Cache miss, falling back to database | DEBUG |
| Rate limit approaching (80% used) | WARNING |
| Rate limit exceeded | ERROR |
| User authentication successful | INFO |
| Invalid credentials provided | WARNING |
| API key revoked mid-request | ERROR |

## Structured Logging with structlog

This project uses **structlog** for structured logging. All new code must use structlog.

### Logger Initialization

```python
import structlog

logger = structlog.get_logger(__name__)
```

### Basic Usage

```python
# Correct: Key-value pairs
logger.info("user_authenticated", user_id=user.id, method="oauth")

# Incorrect: Unstructured message
logger.info(f"User {user.id} authenticated via oauth")
```

### Context Binding

Use bound loggers to add persistent context:

```python
# Bind context for a request
request_logger = logger.bind(
    request_id=request.headers.get("X-Request-ID"),
    user_id=current_user.id,
)

# All subsequent logs include this context
request_logger.info("processing_started", endpoint="/api/snapshots")
request_logger.debug("validation_complete", schema_version="v2")
request_logger.info("processing_complete", duration_ms=elapsed)
```

### Exception Logging

```python
try:
    result = await external_api.call()
except ExternalAPIError as e:
    logger.exception(
        "external_api_failed",
        api_name="starburst",
        endpoint=endpoint,
        status_code=e.status_code,
    )
    raise
```

### Event Naming Convention

Use `snake_case` event names that describe what happened:

```python
# Good: Action-oriented event names
logger.info("snapshot_created", ...)
logger.info("query_executed", ...)
logger.info("connection_established", ...)
logger.warning("retry_scheduled", ...)
logger.error("export_failed", ...)

# Bad: Vague or inconsistent naming
logger.info("done", ...)
logger.info("Processing complete", ...)
logger.info("SNAPSHOT_CREATED", ...)
```

## Logger Configuration

### Development Configuration

Human-readable output with colors:

```python
import structlog

def configure_logging_dev() -> None:
    """Configure structlog for development (human-readable output)."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.UnicodeDecoder(),
            structlog.dev.ConsoleRenderer(colors=True),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
```

### Production Configuration

JSON output for log aggregators:

```python
import structlog

def configure_logging_prod() -> None:
    """Configure structlog for production (JSON output)."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.UnicodeDecoder(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Mute noisy third-party libraries to WARNING (matches ryugraph-wrapper/src/wrapper/logging.py)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
```

### Environment-Aware Configuration

```python
import os
import structlog

def configure_logging() -> None:
    """Configure logging based on environment."""
    env = os.getenv("ENVIRONMENT", "development")

    if env == "production":
        configure_logging_prod()
    else:
        configure_logging_dev()
```

### Standard Processors

Always include these processors in order:

1. `merge_contextvars` - Merge context variables (async-safe)
2. `add_log_level` - Add log level to event dict
3. `TimeStamper(fmt="iso")` - ISO 8601 timestamps
4. `StackInfoRenderer()` - Include stack info when requested
5. `format_exc_info` - Format exception tracebacks
6. Renderer (Console or JSON)

## Logging Patterns

### Request Context

For web services, bind request context at the start of each request:

```python
from starlette.middleware.base import BaseHTTPMiddleware
import structlog

class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request.headers.get("X-Request-ID", str(uuid4())),
            method=request.method,
            path=request.url.path,
        )

        logger = structlog.get_logger()
        logger.info("request_started")

        response = await call_next(request)

        logger.info("request_completed", status_code=response.status_code)
        return response
```

### Background Jobs

For background workers, bind job context:

```python
async def process_export_job(job: ExportJob) -> None:
    job_logger = logger.bind(
        job_id=job.id,
        snapshot_id=job.snapshot_id,
        entity_name=job.entity_name,
    )

    job_logger.info("job_started")
    try:
        result = await execute_export(job)
        job_logger.info("job_completed", rows_exported=result.row_count)
    except Exception as e:
        job_logger.exception("job_failed")
        raise
```

### Duration Logging

Log operation durations for performance monitoring:

```python
import time

async def execute_query(query: str) -> Result:
    start = time.perf_counter()
    try:
        result = await db.execute(query)
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "query_executed",
            duration_ms=round(duration_ms, 2),
            row_count=len(result),
        )
        return result
    except Exception as e:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.error(
            "query_failed",
            duration_ms=round(duration_ms, 2),
            error=str(e),
        )
        raise
```

### Metrics Logging

For logs that will be used to generate metrics:

```python
# Use consistent field names for metric extraction
logger.info(
    "http_request",
    method=request.method,
    path=request.url.path,
    status_code=response.status_code,
    duration_ms=duration,
    # Metric tags
    service="control-plane",
    environment=config.environment,
)
```

## Production Considerations

### Performance

1. **Avoid expensive operations in log calls**:

```python
# Bad: expensive_func() called even if debug is disabled
logger.debug("data", value=expensive_func())

# Good: Check level first
if logger.isEnabledFor(logging.DEBUG):
    logger.debug("data", value=expensive_func())
```

2. **Use lazy evaluation for computed values**:

```python
# structlog handles this automatically with callables
logger.debug("data", value=lambda: expensive_func())
```

### Security

**Never log sensitive information:**

```python
# Bad: Logging credentials
logger.info("connecting", password=password)

# Bad: Logging PII
logger.info("user_created", email=user.email, ssn=user.ssn)

# Good: Log identifiers only
logger.info("user_created", user_id=user.id)

# Good: Mask sensitive data if needed
logger.info("api_call", api_key=f"...{api_key[-4:]}")
```

**Sensitive fields to never log:**
- Passwords and secrets
- API keys and tokens
- Credit card numbers
- Social Security Numbers
- Personal health information
- Private keys and certificates

### Log Rotation

For file-based logging (rarely needed with Kubernetes):

```python
from logging.handlers import RotatingFileHandler

handler = RotatingFileHandler(
    "app.log",
    maxBytes=10_000_000,  # 10 MB
    backupCount=5,
)
```

### Error Handling

Suppress logging errors in production:

```python
import logging

# Production: Don't let logging errors crash the app
logging.raiseExceptions = False
```

## Anti-Patterns

### Using print() Instead of Logging

```python
# Bad
print(f"Processing user {user_id}")

# Good
logger.info("processing_user", user_id=user_id)
```

### Logging Without Context

```python
# Bad: No context
logger.error("Failed")

# Good: Rich context
logger.error(
    "snapshot_creation_failed",
    snapshot_id=snapshot_id,
    mapping_id=mapping_id,
    error=str(e),
    exc_info=True,
)
```

### Over-Logging

```python
# Bad: Too verbose
for item in items:
    logger.debug("processing_item", item=item)

# Good: Log summary
logger.debug("processing_items", count=len(items))
# ... process items ...
logger.info("items_processed", count=len(items), duration_ms=elapsed)
```

### Inconsistent Event Names

```python
# Bad: Inconsistent naming
logger.info("user logged in")
logger.info("UserLoggedOut")
logger.info("authentication_failed")

# Good: Consistent snake_case
logger.info("user_logged_in")
logger.info("user_logged_out")
logger.info("authentication_failed")
```

### String Interpolation in Log Messages

```python
# Bad: Eager string interpolation
logger.info(f"User {user_id} logged in")

# Good: Structured fields
logger.info("user_logged_in", user_id=user_id)

# For standard logging module, use %-formatting
logging.info("User %s logged in", user_id)
```

### Catching and Silencing Exceptions

```python
# Bad: Silent failure
try:
    risky_operation()
except Exception:
    pass

# Good: Log the failure
try:
    risky_operation()
except Exception:
    logger.exception("risky_operation_failed")
    raise  # or handle appropriately
```

## Migration from Standard Logging

If migrating from standard `logging` to `structlog`:

### Before

```python
import logging

logger = logging.getLogger(__name__)

logger.info(f"Processing snapshot {snapshot_id}")
logger.error(f"Failed to process: {error}", exc_info=True)
```

### After

```python
import structlog

logger = structlog.get_logger(__name__)

logger.info("processing_snapshot", snapshot_id=snapshot_id)
logger.exception("processing_failed", snapshot_id=snapshot_id)
```

## References

- [Python Logging HOWTO](https://docs.python.org/3/howto/logging.html)
- [structlog Documentation](https://www.structlog.org/)
- [The Twelve-Factor App: Logs](https://12factor.net/logs)
- [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)
- [Better Stack Python Logging Guide](https://betterstack.com/community/guides/logging/structlog/)
