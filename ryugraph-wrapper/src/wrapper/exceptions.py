"""Exception hierarchy for the Ryugraph Wrapper.

Exception categories:
- WrapperError: Base class for all wrapper exceptions
- DatabaseError: Ryugraph database operations
- QueryError: Query execution errors
- AlgorithmError: Algorithm execution errors
- ResourceLockedError: Lock contention
- ControlPlaneError: Control Plane communication
- ValidationError: Request validation
"""

from __future__ import annotations

from datetime import datetime
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


class SchemaCreationError(DatabaseError):
    """Failed to create database schema."""

    error_code = "SCHEMA_CREATION_ERROR"


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
# Algorithm Errors
# =============================================================================


class AlgorithmError(WrapperError):
    """Base class for algorithm execution errors."""

    error_code = "ALGORITHM_ERROR"
    http_status = 500

    def __init__(
        self,
        message: str,
        *,
        algorithm_name: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.algorithm_name = algorithm_name
        details = details or {}
        if algorithm_name:
            details["algorithm_name"] = algorithm_name
        super().__init__(message, details=details)


class AlgorithmNotFoundError(AlgorithmError):
    """Requested algorithm does not exist."""

    error_code = "ALGORITHM_NOT_FOUND"
    http_status = 404

    def __init__(self, algorithm_name: str, algorithm_type: str = "unknown") -> None:
        super().__init__(
            f"Algorithm '{algorithm_name}' not found",
            algorithm_name=algorithm_name,
            details={"algorithm_type": algorithm_type},
        )


class AlgorithmExecutionError(AlgorithmError):
    """Algorithm execution failed."""

    error_code = "ALGORITHM_EXECUTION_ERROR"

    def __init__(
        self,
        message: str,
        *,
        algorithm_name: str | None = None,
        execution_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        details = details or {}
        if algorithm_name:
            details["algorithm_name"] = algorithm_name
        if execution_id:
            details["execution_id"] = execution_id
        super().__init__(message, details=details)


class AlgorithmTimeoutError(AlgorithmError):
    """Algorithm execution exceeded timeout."""

    error_code = "ALGORITHM_TIMEOUT"
    http_status = 408

    def __init__(
        self,
        timeout_ms: int,
        *,
        algorithm_name: str | None = None,
        execution_id: str | None = None,
    ) -> None:
        details: dict[str, Any] = {"timeout_ms": timeout_ms}
        if algorithm_name:
            details["algorithm_name"] = algorithm_name
        if execution_id:
            details["execution_id"] = execution_id
        super().__init__(
            f"Algorithm execution exceeded timeout of {timeout_ms}ms",
            details=details,
        )


class InvalidAlgorithmParametersError(AlgorithmError):
    """Invalid algorithm parameters."""

    error_code = "INVALID_ALGORITHM_PARAMETERS"
    http_status = 400

    def __init__(
        self,
        message: str,
        *,
        algorithm_name: str | None = None,
        invalid_params: list[str] | None = None,
    ) -> None:
        details: dict[str, Any] = {}
        if algorithm_name:
            details["algorithm_name"] = algorithm_name
        if invalid_params:
            details["invalid_params"] = invalid_params
        super().__init__(message, details=details)


# =============================================================================
# Lock Errors
# =============================================================================


class ResourceLockedError(WrapperError):
    """Resource is locked by another operation."""

    error_code = "RESOURCE_LOCKED"
    http_status = 409

    def __init__(
        self,
        *,
        holder_id: str,
        holder_username: str,
        algorithm_name: str,
        acquired_at: datetime,
    ) -> None:
        self.holder_id = holder_id
        self.holder_username = holder_username
        self.algorithm_name = algorithm_name
        self.acquired_at = acquired_at
        message = (
            f"Instance locked by {holder_username} running '{algorithm_name}' "
            f"since {acquired_at.isoformat()}"
        )
        super().__init__(
            message,
            details={
                "holder_id": holder_id,
                "holder_username": holder_username,
                "algorithm_name": algorithm_name,
                "acquired_at": acquired_at.isoformat(),
            },
        )


class LockAcquisitionError(WrapperError):
    """Failed to acquire lock."""

    error_code = "LOCK_ACQUISITION_ERROR"
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


class ControlPlaneConnectionError(ControlPlaneError):
    """Failed to connect to Control Plane."""

    error_code = "CONTROL_PLANE_CONNECTION_ERROR"


class ControlPlaneTimeoutError(ControlPlaneError):
    """Control Plane request timed out."""

    error_code = "CONTROL_PLANE_TIMEOUT"
    http_status = 504


# =============================================================================
# Validation Errors
# =============================================================================


class ValidationError(WrapperError):
    """Request validation failed."""

    error_code = "VALIDATION_ERROR"
    http_status = 400


# =============================================================================
# Startup Errors
# =============================================================================


class StartupError(WrapperError):
    """Error during application startup."""

    error_code = "STARTUP_ERROR"
    http_status = 503


class MappingNotFoundError(StartupError):
    """Mapping definition not found."""

    error_code = "MAPPING_NOT_FOUND"
    http_status = 404

    def __init__(self, mapping_id: str) -> None:
        super().__init__(
            f"Mapping '{mapping_id}' not found",
            details={"mapping_id": mapping_id},
        )
