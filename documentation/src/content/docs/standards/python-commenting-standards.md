---
title: "Python Commenting Standards"
scope: hsbc
---

# Python Commenting Standards

This document establishes coding standards for comments and docstrings in the Graph OLAP Platform, based on industry best practices from PEP 8, PEP 257, and the Google Python Style Guide.

## Table of Contents

1. [Guiding Principles](#guiding-principles)
2. [Inline Comments](#inline-comments)
3. [Block Comments](#block-comments)
4. [Docstrings](#docstrings)
5. [TODO Comments](#todo-comments)
6. [Anti-Patterns](#anti-patterns)

## Guiding Principles

### The Cardinal Rule

**Explain "why", not "what".** Code should be self-documenting through clear naming and structure. Comments exist to explain intent, rationale, and non-obvious behavior.

> "Comments that contradict the code are worse than no comments. Always make a priority of keeping the comments up-to-date when the code changes!" — PEP 8

### When to Comment

| Scenario | Action |
|----------|--------|
| Tricky or non-obvious logic | Comment the "why" |
| Business rule implementation | Document the rule |
| Workaround for external limitation | Explain the constraint |
| Algorithm with complexity considerations | Document complexity |
| Code that looks wrong but is intentional | Explain why it's correct |

### When NOT to Comment

| Scenario | Better Alternative |
|----------|-------------------|
| What the code does | Refactor for clarity |
| Obvious operations | Remove the comment |
| Repeating the code in English | Trust the reader |
| Apologizing for bad code | Refactor the code |

## Inline Comments

Inline comments appear on the same line as code. Use them **sparingly**.

### Formatting Rules

1. **Separation**: At least 2 spaces between code and `#`
2. **Spacing**: One space after `#` before comment text
3. **Case**: Start with a capital letter (unless the first word is a code identifier)
4. **Length**: Keep to a single line; use block comments for longer explanations

### Correct Usage

```python
# Good: Explains non-obvious behavior
x = x + 1  # Compensate for 1-based indexing in API response

# Good: Documents business rule
if i & (i - 1) == 0:  # True if i is 0 or a power of 2

# Good: Explains constraint
timeout = 30  # Maximum allowed by upstream rate limiter

# Good: Clarifies intentional behavior
results = []  # Intentionally empty; populated by callback
```

### Incorrect Usage

```python
# Bad: States the obvious
x = x + 1  # Increment x

# Bad: Redundant with clear variable name
user_count = len(users)  # Count the number of users

# Bad: Describes what, not why
for item in items:  # Loop through items
    process(item)

# Bad: Too long for inline
config = load_config()  # This loads the configuration from the environment variables and falls back to defaults if not found
```

## Block Comments

Block comments describe a section of code or explain complex logic.

### Formatting Rules

1. **Indentation**: Same level as the code they describe
2. **Structure**: Each line starts with `#` followed by a single space
3. **Paragraphs**: Separate with a line containing only `#`
4. **Placement**: Immediately before the code they describe

### Correct Usage

```python
# Calculate the weighted average using exponential smoothing.
# We use a decay factor of 0.9 based on empirical testing
# against historical data (see ADR-042 for analysis).
#
# Note: The first value is used as the initial estimate,
# which may cause slight inaccuracy for short sequences.
def exponential_smoothing(values: list[float], alpha: float = 0.9) -> float:
    ...
```

### Section Headers

Use block comments to delineate logical sections in longer modules:

```python
# -----------------------------------------------------------------------------
# Database Connection Management
# -----------------------------------------------------------------------------

def get_connection() -> Connection:
    ...

def release_connection(conn: Connection) -> None:
    ...


# -----------------------------------------------------------------------------
# Query Execution
# -----------------------------------------------------------------------------

def execute_query(query: str) -> Result:
    ...
```

## Docstrings

Docstrings are the primary documentation mechanism for Python code. This project uses **Google-style docstrings**.

### General Rules

1. **Format**: Triple double-quotes (`"""`)
2. **Summary**: First line is a concise summary ending with a period
3. **Blank line**: Separate summary from body with a blank line
4. **Imperative mood**: "Fetch rows" not "Fetches rows" or "This fetches rows"

### Module Docstrings

Every module requires a docstring describing its purpose.

```python
"""Database service for Ryugraph operations.

Manages the embedded Ryugraph database, including:
- Database initialization and connection management
- Schema creation from mapping definitions
- Query execution and result transformation

This module implements the repository pattern as defined in ADR-015.

Typical usage:
    service = DatabaseService(config)
    await service.initialize()
    results = await service.execute_query(cypher_query)
"""
```

### Function Docstrings

Required for:
- All public API functions
- Functions with non-trivial logic
- Functions with non-obvious parameters or return values

```python
def fetch_snapshot_data(
    snapshot_id: str,
    include_metadata: bool = False,
    timeout: float | None = None,
) -> SnapshotData:
    """Fetch snapshot data from the control plane.

    Retrieves the complete snapshot data including all entities and
    relationships. For large snapshots, consider using streaming
    endpoints instead.

    Args:
        snapshot_id: Unique identifier for the snapshot (UUID format).
        include_metadata: If True, includes creation timestamp and
            source mapping information in the response.
        timeout: Maximum seconds to wait for response. If None, uses
            the client's default timeout.

    Returns:
        SnapshotData containing entities, relationships, and optionally
        metadata. The data is validated against the schema version
        specified in the snapshot.

    Raises:
        SnapshotNotFoundError: The snapshot_id does not exist.
        SnapshotExpiredError: The snapshot has exceeded its TTL.
        TimeoutError: Request exceeded the specified timeout.
        ValidationError: Response failed schema validation.
    """
```

### Class Docstrings

Document the class purpose and public attributes.

```python
class ExportWorker:
    """Kubernetes-native worker for exporting graph data to Starburst.

    Implements a three-phase export architecture (claim, submit, poll)
    designed for stateless operation in Kubernetes environments.
    See ADR-025 for architectural rationale.

    The worker uses exponential backoff for polling and supports
    graceful shutdown via SIGTERM handling.

    Attributes:
        worker_id: Unique identifier for this worker instance.
        config: Worker configuration including timeouts and retry limits.
        metrics: Prometheus metrics collector for observability.

    Example:
        worker = ExportWorker.from_env()
        await worker.run()  # Runs until shutdown signal
    """
```

### Method Docstrings

```python
class SnapshotService:
    def create_snapshot(
        self,
        mapping_id: str,
        source_config: SourceConfig,
    ) -> Snapshot:
        """Create a new snapshot from the specified mapping.

        Initiates an asynchronous snapshot creation process. The returned
        Snapshot object will be in PENDING state; use wait_for_completion()
        to block until ready.

        Args:
            mapping_id: ID of the mapping definition to snapshot.
            source_config: Configuration for data source connection.

        Returns:
            Snapshot in PENDING state with assigned snapshot_id.

        Raises:
            MappingNotFoundError: The mapping_id does not exist.
            SourceConnectionError: Failed to connect to data source.
        """
```

### Property Docstrings

```python
@property
def is_ready(self) -> bool:
    """Whether the instance is ready to accept queries."""
    return self._state == InstanceState.READY
```

### Overridden Methods

Methods with `@override` decorator need no docstring unless behavior differs materially:

```python
from typing_extensions import override

class CustomHandler(BaseHandler):
    @override
    def handle(self, request: Request) -> Response:
        # No docstring needed - behavior matches base class
        ...
```

## TODO Comments

Use TODO comments to mark future work. Always include a trackable reference.

### Format

```python
# TODO: JIRA-123 - Add retry logic for transient failures

# TODO: github.com/org/repo/issues/456 - Optimize for large datasets
```

### Rules

1. **Always include a reference**: Link to a ticket, issue, or bug tracker
2. **Be specific**: Describe what needs to be done
3. **Avoid names**: Use issue trackers, not "TODO(john)" patterns

### Anti-Pattern

```python
# Bad: No tracking reference
# TODO: Fix this later

# Bad: References a person instead of ticket
# TODO(alice): Refactor this
```

## Anti-Patterns

### Commented-Out Code

**Never commit commented-out code.** Use version control for history.

```python
# Bad: Dead code
# def old_implementation():
#     return legacy_call()

# Good: Just delete it; git has history
```

### Redundant Comments

```python
# Bad: Repeats the code
def get_user(user_id: str) -> User:
    """Get a user by user ID."""  # Adds nothing
    return self.repo.get(user_id)

# Good: Adds value
def get_user(user_id: str) -> User:
    """Retrieve user with populated permissions.

    Fetches the user and eagerly loads role-based permissions
    to avoid N+1 queries in authorization checks.
    """
    return self.repo.get_with_permissions(user_id)
```

### Over-Commenting

```python
# Bad: Comment soup
# Initialize the counter
counter = 0  # Set to zero
# Loop through items
for item in items:  # Each item
    # Increment counter
    counter += 1  # Add one

# Good: Self-documenting code
item_count = len(items)
```

### Stale Comments

```python
# Bad: Comment doesn't match code
# Return the first item
return items[-1]  # Actually returns last!

# Good: Keep comments synchronized with code
return items[-1]  # Return most recent (last) item
```

## References

- [PEP 8 — Style Guide for Python Code](https://peps.python.org/pep-0008/)
- [PEP 257 — Docstring Conventions](https://peps.python.org/pep-0257/)
- [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)
