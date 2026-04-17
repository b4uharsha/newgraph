"""Exception hierarchy for Graph OLAP SDK.

All exceptions inherit from GraphOLAPError, allowing catch-all handling:

    try:
        client.mappings.get(999)
    except GraphOLAPError as e:
        print(f"SDK error: {e}")

Or specific exception handling:

    try:
        client.instances.create(snapshot_id=1, name="Test")
    except ConcurrencyLimitError as e:
        print(f"Limit reached: {e.current_count}/{e.max_allowed}")
    except InvalidStateError as e:
        print(f"Snapshot not ready: {e}")
"""

from __future__ import annotations


class GraphOLAPError(Exception):
    """Base exception for all Graph OLAP SDK errors."""

    pass


# =============================================================================
# Authentication Errors
# =============================================================================


class AuthenticationError(GraphOLAPError):
    """Invalid or missing API key."""

    pass


class PermissionDeniedError(GraphOLAPError):
    """User doesn't have permission for this operation."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.details = details or {}


class ForbiddenError(PermissionDeniedError):
    """Access forbidden (HTTP 403).

    Raised when user lacks required role (e.g., Ops role for config endpoints).
    """

    pass


# =============================================================================
# Resource Errors
# =============================================================================


class NotFoundError(GraphOLAPError):
    """Resource not found."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.details = details or {}


class ValidationError(GraphOLAPError):
    """Request validation failed."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.details = details or {}


# =============================================================================
# Conflict Errors
# =============================================================================


class ConflictError(GraphOLAPError):
    """Operation conflicts with current state."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.details = details or {}


class ResourceLockedError(ConflictError):
    """Instance is locked by an algorithm."""

    @property
    def holder_name(self) -> str | None:
        """Name of the user holding the lock."""
        return self.details.get("holder_name")

    @property
    def algorithm(self) -> str | None:
        """Name of the algorithm holding the lock."""
        return self.details.get("algorithm")


class ConcurrencyLimitError(ConflictError):
    """Instance creation limit exceeded."""

    @property
    def limit_type(self) -> str | None:
        """Type of limit exceeded (e.g., 'user', 'global')."""
        return self.details.get("limit_type")

    @property
    def current_count(self) -> int | None:
        """Current number of instances."""
        return self.details.get("current_count")

    @property
    def max_allowed(self) -> int | None:
        """Maximum allowed instances."""
        return self.details.get("max_allowed")


class DependencyError(ConflictError):
    """Resource has dependencies that prevent deletion."""

    pass


class InvalidStateError(ConflictError):
    """Operation invalid for current resource state."""

    pass


# =============================================================================
# Timeout Errors
# =============================================================================


class TimeoutError(GraphOLAPError):
    """Operation timed out."""

    pass


class QueryTimeoutError(TimeoutError):
    """Cypher query exceeded timeout."""

    pass


class AlgorithmTimeoutError(TimeoutError):
    """Algorithm execution exceeded timeout."""

    pass


# =============================================================================
# Graph Operation Errors
# =============================================================================


class RyugraphError(GraphOLAPError):
    """Ryugraph/Cypher error."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.details = details or {}


class AlgorithmNotFoundError(GraphOLAPError):
    """Unknown algorithm name."""

    pass


class AlgorithmFailedError(GraphOLAPError):
    """Algorithm execution failed."""

    pass


# =============================================================================
# Resource Lifecycle Errors
# =============================================================================


# =============================================================================
# SNAPSHOT FUNCTIONALITY DISABLED
# This exception is kept for backward compatibility but snapshot APIs are disabled.
# Snapshots are now created implicitly when instances are created from mappings.
# =============================================================================
class SnapshotFailedError(GraphOLAPError):
    """Snapshot export failed."""

    pass


class InstanceFailedError(GraphOLAPError):
    """Instance startup failed."""

    pass


# =============================================================================
# Server Errors
# =============================================================================


class ServerError(GraphOLAPError):
    """Server-side error (5xx)."""

    pass


class ServiceUnavailableError(ServerError):
    """Service temporarily unavailable."""

    pass


# =============================================================================
# HTTP Error Mapping
# =============================================================================

HTTP_STATUS_TO_EXCEPTION: dict[int, type[GraphOLAPError]] = {
    401: AuthenticationError,
    403: ForbiddenError,
    404: NotFoundError,
    409: ConflictError,
    422: ValidationError,
    429: ConcurrencyLimitError,
    500: ServerError,
    503: ServiceUnavailableError,
}


def exception_from_response(
    status_code: int,
    error_code: str | None,
    message: str,
    details: dict | None = None,
) -> GraphOLAPError:
    """Create appropriate exception from API error response.

    Args:
        status_code: HTTP status code
        error_code: API error code (e.g., 'RESOURCE_LOCKED', 'CONCURRENCY_LIMIT')
        message: Error message
        details: Additional error details

    Returns:
        Appropriate GraphOLAPError subclass instance
    """
    details = details or {}

    # Check for specific error codes first
    if error_code == "VALIDATION_FAILED":
        return ValidationError(message, details)
    if error_code == "RESOURCE_LOCKED":
        return ResourceLockedError(message, details)
    if error_code == "CONCURRENCY_LIMIT":
        return ConcurrencyLimitError(message, details)
    if error_code == "DEPENDENCY_EXISTS":
        return DependencyError(message, details)
    if error_code == "INVALID_STATE":
        return InvalidStateError(message, details)
    if error_code == "QUERY_TIMEOUT":
        return QueryTimeoutError(message)
    if error_code == "ALGORITHM_TIMEOUT":
        return AlgorithmTimeoutError(message)
    if error_code == "ALGORITHM_NOT_FOUND":
        return AlgorithmNotFoundError(message)
    if error_code == "ALGORITHM_FAILED":
        return AlgorithmFailedError(message)
    if error_code == "RYUGRAPH_ERROR":
        return RyugraphError(message, details)
    if error_code == "SNAPSHOT_FAILED":
        return SnapshotFailedError(message)
    if error_code == "INSTANCE_FAILED":
        return InstanceFailedError(message)

    # Fall back to HTTP status code mapping
    exc_class = HTTP_STATUS_TO_EXCEPTION.get(status_code, GraphOLAPError)

    # Handle exceptions that take details
    if exc_class in (
        PermissionDeniedError,
        ForbiddenError,
        NotFoundError,
        ValidationError,
        ConflictError,
    ):
        return exc_class(message, details)

    return exc_class(message)
