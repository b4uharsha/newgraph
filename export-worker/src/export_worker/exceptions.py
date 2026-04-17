"""Custom exceptions for the Export Worker.

Exception hierarchy:
- ExportWorkerError (base)
  - RetryableError (triggers job retry via Control Plane)
    - ControlPlaneError
  - PermanentError (no retry, marks snapshot as failed)
    - StarburstError
    - GCSError
    - ValidationError
"""

from __future__ import annotations


class ExportWorkerError(Exception):
    """Base exception for export worker."""

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class RetryableError(ExportWorkerError):
    """Error that should trigger job retry.

    When raised during job processing, the worker updates the job status
    to allow retry according to the configured retry policy.
    """

    pass


class PermanentError(ExportWorkerError):
    """Error that should NOT be retried.

    When this error occurs, the worker marks the snapshot as failed
    and acks the message to prevent infinite retry loops.
    """

    pass


class StarburstError(PermanentError):
    """Starburst query or connection error.

    Examples:
    - Query syntax error
    - Table not found
    - Permission denied
    - Query timeout
    """

    def __init__(
        self,
        message: str,
        query: str | None = None,
        starburst_error_code: str | None = None,
    ) -> None:
        super().__init__(message, {"query": query, "error_code": starburst_error_code})
        self.query = query
        self.starburst_error_code = starburst_error_code


class GCSError(PermanentError):
    """GCS operation error.

    Examples:
    - Bucket not found
    - Permission denied
    - File not found (during row counting)
    """

    def __init__(self, message: str, gcs_path: str | None = None) -> None:
        super().__init__(message, {"gcs_path": gcs_path})
        self.gcs_path = gcs_path


class ControlPlaneError(RetryableError):
    """Control Plane API error.

    Typically transient (network issues, service restart), so retryable.
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response_body: str | None = None,
    ) -> None:
        super().__init__(message, {"status_code": status_code, "response_body": response_body})
        self.status_code = status_code
        self.response_body = response_body


class ValidationError(PermanentError):
    """Invalid input data error.

    Examples:
    - Missing required fields in message
    - Invalid column types
    - Empty node/edge definitions
    """

    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(message, {"field": field})
        self.field = field
