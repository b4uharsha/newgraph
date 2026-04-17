"""Custom exception hierarchy for the Control Plane."""

from typing import Any


class AppError(Exception):
    """Base application error with structured error info."""

    def __init__(
        self,
        code: str,
        status: int,
        message: str,
        details: dict[str, Any] | None = None,
    ):
        self.code = code
        self.status = status
        self.message = message
        self.details = details or {}
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON response."""
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


class NotFoundError(AppError):
    """Resource not found."""

    def __init__(self, resource_type: str, resource_id: int | str):
        super().__init__(
            code="RESOURCE_NOT_FOUND",
            status=404,
            message=f"{resource_type} {resource_id} not found",
            details={"resource_type": resource_type, "resource_id": resource_id},
        )


class UnauthorizedError(AppError):
    """Authentication required."""

    def __init__(self, message: str = "Authentication required"):
        super().__init__(code="UNAUTHORIZED", status=401, message=message)


class PermissionDeniedError(AppError):
    """Permission denied."""

    def __init__(self, resource_type: str, resource_id: int | str):
        super().__init__(
            code="PERMISSION_DENIED",
            status=403,
            message=f"Permission denied for {resource_type} {resource_id}",
            details={"resource_type": resource_type, "resource_id": resource_id},
        )


class ValidationError(AppError):
    """Validation failed."""

    def __init__(self, field: str, message: str):
        super().__init__(
            code="VALIDATION_FAILED",
            status=400,
            message=message,
            details={"field": field},
        )


class DependencyError(AppError):
    """Resource has dependencies preventing deletion."""

    def __init__(
        self,
        resource_type: str,
        resource_id: int,
        dependent_type: str,
        dependent_count: int,
    ):
        super().__init__(
            code="RESOURCE_HAS_DEPENDENCIES",
            status=409,
            message=f"Cannot delete {resource_type} {resource_id}: has {dependent_count} {dependent_type}(s)",
            details={
                "resource_type": resource_type,
                "resource_id": resource_id,
                "dependent_type": dependent_type,
                "dependent_count": dependent_count,
            },
        )


class ConcurrencyLimitError(AppError):
    """Concurrency limit exceeded."""

    def __init__(self, limit_type: str, current_count: int, max_allowed: int):
        super().__init__(
            code="CONCURRENCY_LIMIT_EXCEEDED",
            status=409,
            message=f"Cannot create instance: {limit_type} limit exceeded ({current_count}/{max_allowed})",
            details={
                "limit_type": limit_type,
                "current_count": current_count,
                "max_allowed": max_allowed,
            },
        )


class InvalidStateError(AppError):
    """Resource is in invalid state for operation."""

    def __init__(self, resource: str, resource_id: int, current: str, required: str):
        super().__init__(
            code="INVALID_STATE",
            status=409,
            message=f"{resource} {resource_id} is in state '{current}', required '{required}'",
            details={
                "resource": resource,
                "resource_id": resource_id,
                "current_state": current,
                "required_state": required,
            },
        )


class MaintenanceError(AppError):
    """System is in maintenance mode."""

    def __init__(self, message: str = "System is under maintenance"):
        super().__init__(
            code="SERVICE_UNAVAILABLE",
            status=503,
            message=message,
        )


class AlreadyExistsError(AppError):
    """Resource already exists."""

    def __init__(self, resource_type: str, message: str = "Resource already exists"):
        super().__init__(
            code="ALREADY_EXISTS",
            status=409,
            message=message,
            details={"resource_type": resource_type},
        )


class RoleRequiredError(AppError):
    """User lacks required role for operation."""

    def __init__(self, required_role: str, user_role: str):
        super().__init__(
            code="INSUFFICIENT_ROLE",
            status=403,
            message=f"Role '{required_role}' required, user has '{user_role}'",
            details={"required_role": required_role, "user_role": user_role},
        )


class RateLimitError(AppError):
    """Rate limit exceeded."""

    def __init__(self, resource: str, retry_after_seconds: int):
        super().__init__(
            code="RATE_LIMIT_EXCEEDED",
            status=429,
            message=f"{resource} rate limit exceeded, retry after {retry_after_seconds}s",
            details={"resource": resource, "retry_after_seconds": retry_after_seconds},
        )


class ServiceUnavailableError(AppError):
    """Service or component not available."""

    def __init__(self, service: str, message: str):
        super().__init__(
            code="SERVICE_UNAVAILABLE",
            status=503,
            message=message,
            details={"service": service},
        )
