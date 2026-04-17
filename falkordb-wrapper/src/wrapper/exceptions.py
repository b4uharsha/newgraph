"""Exception hierarchy for the FalkorDB Wrapper.

Exception categories:
- WrapperError: Base class for all wrapper exceptions
- DatabaseError: FalkorDB database operations
- QueryError: Query execution errors
- ControlPlaneError: Control Plane communication
- GCSDownloadError: GCS download failures
- OutOfMemoryError: Memory limit exceeded
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class WrapperError(Exception):
    """Base exception for all wrapper errors.

    All wrapper exceptions include:
    - error_code: Machine-readable error code
    - message: Human-readable message
    - details: Additional context dict
    """

    error_code: str = "WRAPPER_ERROR"
    http_status: int = 500

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message
        self.details = details or {}
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        """Convert exception to API error response dict."""
        return {
            "error": {
                "code": self.error_code,
                "message": self.message,
                "details": self.details,
            }
        }


# =============================================================================
# Database Errors
# =============================================================================


class DatabaseError(WrapperError):
    """Base class for database-related errors."""

    error_code = "DATABASE_ERROR"
    http_status = 500


class DatabaseNotInitializedError(DatabaseError):
    """Database has not been initialized."""

    error_code = "DATABASE_NOT_INITIALIZED"

    def __init__(self) -> None:
        super().__init__("Database has not been initialized")


class DatabaseConnectionError(DatabaseError):
    """Failed to connect to the database."""

    error_code = "DATABASE_CONNECTION_ERROR"


class DataLoadError(DatabaseError):
    """Failed to load data from GCS."""

    error_code = "DATA_LOAD_ERROR"

    def __init__(
        self,
        message: str,
        *,
        table_name: str | None = None,
        gcs_path: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        details = details or {}
        if table_name:
            details["table_name"] = table_name
        if gcs_path:
            details["gcs_path"] = gcs_path
        super().__init__(message, details=details)


class DatabasePathError(DatabaseError):
    """Database path is invalid or not writable."""

    error_code = "DATABASE_PATH_ERROR"

    def __init__(self, path: Path, reason: str) -> None:
        super().__init__(
            f"Database path '{path}' is invalid: {reason}",
            details={"path": str(path), "reason": reason},
        )


class SchemaCreationError(DatabaseError):
    """Failed to create graph schema."""

    error_code = "SCHEMA_CREATE_ERROR"

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details=details)


# =============================================================================
# Query Errors
# =============================================================================


class QueryError(WrapperError):
    """Base class for query execution errors."""

    error_code = "QUERY_ERROR"
    http_status = 400


class QuerySyntaxError(QueryError):
    """Invalid Cypher query syntax."""

    error_code = "QUERY_SYNTAX_ERROR"

    def __init__(
        self,
        message: str,
        *,
        query: str | None = None,
        position: int | None = None,
    ) -> None:
        details: dict[str, Any] = {}
        if query:
            details["query"] = query[:500]  # Truncate long queries
        if position is not None:
            details["position"] = position
        super().__init__(message, details=details)


class QueryTimeoutError(QueryError):
    """Query execution exceeded timeout."""

    error_code = "QUERY_TIMEOUT"
    http_status = 408

    def __init__(
        self,
        timeout_ms: int,
        *,
        elapsed_ms: int | None = None,
        query: str | None = None,
    ) -> None:
        self.timeout_ms = timeout_ms
        self.elapsed_ms = elapsed_ms
        details: dict[str, Any] = {"timeout_ms": timeout_ms}
        if elapsed_ms is not None:
            details["elapsed_ms"] = elapsed_ms
        if query:
            details["query"] = query[:500]
        super().__init__(
            f"Query execution exceeded timeout of {timeout_ms}ms",
            details=details,
        )


class QueryExecutionError(QueryError):
    """Query execution failed."""

    error_code = "QUERY_EXECUTION_ERROR"
    http_status = 500


# =============================================================================
# Control Plane Errors
# =============================================================================


class ControlPlaneError(WrapperError):
    """Error communicating with Control Plane."""

    error_code = "CONTROL_PLANE_ERROR"
    http_status = 502

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        details = details or {}
        if status_code is not None:
            details["status_code"] = status_code
        super().__init__(message, details=details)


# =============================================================================
# GCS Errors
# =============================================================================


class GCSDownloadError(WrapperError):
    """Failed to download from GCS."""

    error_code = "GCS_DOWNLOAD_ERROR"
    http_status = 502

    def __init__(self, gcs_path: str, error: str) -> None:
        super().__init__(
            f"Failed to download from {gcs_path}: {error}",
            details={"gcs_path": gcs_path, "error": error},
        )


# =============================================================================
# Resource Errors
# =============================================================================


class OutOfMemoryError(WrapperError):
    """Memory limit exceeded."""

    error_code = "OOM_KILLED"
    http_status = 507  # Insufficient Storage

    def __init__(self, memory_limit_bytes: int, current_usage_bytes: int) -> None:
        super().__init__(
            f"Memory usage ({current_usage_bytes} bytes) exceeds limit ({memory_limit_bytes} bytes)",
            details={
                "memory_limit_bytes": memory_limit_bytes,
                "current_usage_bytes": current_usage_bytes,
            },
        )


# =============================================================================
# Lock Errors
# =============================================================================


class ResourceLockedError(WrapperError):
    """Instance is locked by another algorithm execution."""

    error_code = "RESOURCE_LOCKED"
    http_status = 409  # Conflict

    def __init__(
        self,
        holder_id: str,
        holder_username: str,
        algorithm_name: str,
        acquired_at: Any,
    ) -> None:
        from datetime import datetime

        acquired_at_str = (
            acquired_at.isoformat()
            if isinstance(acquired_at, datetime)
            else str(acquired_at)
        )
        super().__init__(
            f"Instance is locked by {holder_username} running {algorithm_name}",
            details={
                "holder_id": holder_id,
                "holder_username": holder_username,
                "algorithm_name": algorithm_name,
                "acquired_at": acquired_at_str,
            },
        )
