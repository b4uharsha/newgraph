"""Tests for error models."""

from control_plane.models.errors import (
    AlreadyExistsError,
    AppError,
    ConcurrencyLimitError,
    DependencyError,
    InvalidStateError,
    MaintenanceError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    RoleRequiredError,
    ServiceUnavailableError,
    UnauthorizedError,
    ValidationError,
)


class TestAppError:
    """Tests for base AppError."""

    def test_app_error_basic(self):
        """Test basic AppError creation."""
        error = AppError(
            code="TEST_ERROR",
            status=500,
            message="Test error message",
        )

        assert error.code == "TEST_ERROR"
        assert error.status == 500
        assert error.message == "Test error message"
        assert error.details == {}

    def test_app_error_with_details(self):
        """Test AppError with details."""
        error = AppError(
            code="TEST_ERROR",
            status=400,
            message="Error message",
            details={"field": "value", "count": 5},
        )

        assert error.details == {"field": "value", "count": 5}

    def test_app_error_to_dict(self):
        """Test AppError to_dict conversion."""
        error = AppError(
            code="TEST_ERROR",
            status=500,
            message="Test message",
            details={"key": "value"},
        )

        result = error.to_dict()

        assert result == {
            "code": "TEST_ERROR",
            "message": "Test message",
            "details": {"key": "value"},
        }


class TestNotFoundError:
    """Tests for NotFoundError."""

    def test_not_found_error_with_string_id(self):
        """Test NotFoundError with string resource ID."""
        error = NotFoundError("Snapshot", "snapshot-123")

        assert error.code == "RESOURCE_NOT_FOUND"
        assert error.status == 404
        assert "Snapshot" in error.message
        assert "snapshot-123" in error.message
        assert error.details["resource_type"] == "Snapshot"
        assert error.details["resource_id"] == "snapshot-123"

    def test_not_found_error_with_int_id(self):
        """Test NotFoundError with integer resource ID."""
        error = NotFoundError("Instance", 42)

        assert error.status == 404
        assert "Instance" in error.message
        assert "42" in error.message
        assert error.details["resource_id"] == 42


class TestUnauthorizedError:
    """Tests for UnauthorizedError."""

    def test_unauthorized_error_default_message(self):
        """Test UnauthorizedError with default message."""
        error = UnauthorizedError()

        assert error.code == "UNAUTHORIZED"
        assert error.status == 401
        assert error.message == "Authentication required"

    def test_unauthorized_error_custom_message(self):
        """Test UnauthorizedError with custom message."""
        error = UnauthorizedError("Invalid token provided")

        assert error.status == 401
        assert error.message == "Invalid token provided"


class TestPermissionDeniedError:
    """Tests for PermissionDeniedError."""

    def test_permission_denied_error(self):
        """Test PermissionDeniedError."""
        error = PermissionDeniedError("Instance", 123)

        assert error.code == "PERMISSION_DENIED"
        assert error.status == 403
        assert "Instance" in error.message
        assert "123" in error.message
        assert error.details["resource_type"] == "Instance"
        assert error.details["resource_id"] == 123


class TestValidationError:
    """Tests for ValidationError."""

    def test_validation_error(self):
        """Test ValidationError."""
        error = ValidationError("email", "Invalid email format")

        assert error.code == "VALIDATION_FAILED"
        assert error.status == 400
        assert error.message == "Invalid email format"
        assert error.details["field"] == "email"


class TestDependencyError:
    """Tests for DependencyError."""

    def test_dependency_error(self):
        """Test DependencyError."""
        error = DependencyError(
            resource_type="Snapshot",
            resource_id=5,
            dependent_type="Instance",
            dependent_count=3,
        )

        assert error.code == "RESOURCE_HAS_DEPENDENCIES"
        assert error.status == 409
        assert "Snapshot" in error.message
        assert "5" in error.message
        assert "3" in error.message
        assert "Instance" in error.message
        assert error.details["resource_type"] == "Snapshot"
        assert error.details["resource_id"] == 5
        assert error.details["dependent_type"] == "Instance"
        assert error.details["dependent_count"] == 3


class TestConcurrencyLimitError:
    """Tests for ConcurrencyLimitError."""

    def test_concurrency_limit_error(self):
        """Test ConcurrencyLimitError."""
        error = ConcurrencyLimitError(
            limit_type="per_user_instances",
            current_count=10,
            max_allowed=10,
        )

        assert error.code == "CONCURRENCY_LIMIT_EXCEEDED"
        assert error.status == 409
        assert "per_user_instances" in error.message
        assert "10/10" in error.message
        assert error.details["limit_type"] == "per_user_instances"
        assert error.details["current_count"] == 10
        assert error.details["max_allowed"] == 10


class TestInvalidStateError:
    """Tests for InvalidStateError."""

    def test_invalid_state_error(self):
        """Test InvalidStateError."""
        error = InvalidStateError(
            resource="Instance",
            resource_id=7,
            current="running",
            required="stopped",
        )

        assert error.code == "INVALID_STATE"
        assert error.status == 409
        assert "Instance" in error.message
        assert "7" in error.message
        assert "running" in error.message
        assert "stopped" in error.message
        assert error.details["resource"] == "Instance"
        assert error.details["resource_id"] == 7
        assert error.details["current_state"] == "running"
        assert error.details["required_state"] == "stopped"


class TestMaintenanceError:
    """Tests for MaintenanceError."""

    def test_maintenance_error_default_message(self):
        """Test MaintenanceError with default message."""
        error = MaintenanceError()

        assert error.code == "SERVICE_UNAVAILABLE"
        assert error.status == 503
        assert "maintenance" in error.message.lower()

    def test_maintenance_error_custom_message(self):
        """Test MaintenanceError with custom message."""
        error = MaintenanceError("Scheduled maintenance in progress")

        assert error.status == 503
        assert error.message == "Scheduled maintenance in progress"


class TestAlreadyExistsError:
    """Tests for AlreadyExistsError."""

    def test_already_exists_error_default_message(self):
        """Test AlreadyExistsError with default message."""
        error = AlreadyExistsError("Snapshot")

        assert error.code == "ALREADY_EXISTS"
        assert error.status == 409
        assert error.message == "Resource already exists"
        assert error.details["resource_type"] == "Snapshot"

    def test_already_exists_error_custom_message(self):
        """Test AlreadyExistsError with custom message."""
        error = AlreadyExistsError(
            "Mapping",
            message="Mapping with this name already exists",
        )

        assert error.status == 409
        assert error.message == "Mapping with this name already exists"
        assert error.details["resource_type"] == "Mapping"


class TestRoleRequiredError:
    """Tests for RoleRequiredError."""

    def test_role_required_error_admin(self):
        """Test RoleRequiredError for admin role."""
        error = RoleRequiredError(required_role="admin", user_role="analyst")

        assert error.code == "INSUFFICIENT_ROLE"
        assert error.status == 403
        assert "admin" in error.message
        assert "analyst" in error.message
        assert error.details["required_role"] == "admin"
        assert error.details["user_role"] == "analyst"

    def test_role_required_error_ops(self):
        """Test RoleRequiredError for ops role."""
        error = RoleRequiredError(required_role="ops", user_role="analyst")

        assert error.code == "INSUFFICIENT_ROLE"
        assert error.status == 403
        assert "ops" in error.message
        assert "analyst" in error.message

    def test_role_required_error_multiple_roles(self):
        """Test RoleRequiredError for multiple acceptable roles."""
        error = RoleRequiredError(required_role="ops or admin", user_role="analyst")

        assert error.code == "INSUFFICIENT_ROLE"
        assert error.status == 403
        assert "ops or admin" in error.message
        assert error.details["required_role"] == "ops or admin"

    def test_role_required_error_to_dict(self):
        """Test RoleRequiredError to_dict conversion."""
        error = RoleRequiredError(required_role="admin", user_role="analyst")

        result = error.to_dict()

        assert result["code"] == "INSUFFICIENT_ROLE"
        assert result["message"] == "Role 'admin' required, user has 'analyst'"
        assert result["details"]["required_role"] == "admin"
        assert result["details"]["user_role"] == "analyst"


class TestRateLimitError:
    """Tests for RateLimitError."""

    def test_rate_limit_error_job_trigger(self):
        """Test RateLimitError for job trigger."""
        error = RateLimitError(
            resource="job_trigger:reconciliation",
            retry_after_seconds=60,
        )

        assert error.code == "RATE_LIMIT_EXCEEDED"
        assert error.status == 429
        assert "job_trigger:reconciliation" in error.message
        assert "60" in error.message
        assert error.details["resource"] == "job_trigger:reconciliation"
        assert error.details["retry_after_seconds"] == 60

    def test_rate_limit_error_api_calls(self):
        """Test RateLimitError for API rate limiting."""
        error = RateLimitError(
            resource="api:/instances",
            retry_after_seconds=120,
        )

        assert error.code == "RATE_LIMIT_EXCEEDED"
        assert error.status == 429
        assert "120" in error.message
        assert error.details["retry_after_seconds"] == 120

    def test_rate_limit_error_to_dict(self):
        """Test RateLimitError to_dict conversion."""
        error = RateLimitError(
            resource="test_resource",
            retry_after_seconds=30,
        )

        result = error.to_dict()

        assert result["code"] == "RATE_LIMIT_EXCEEDED"
        assert "test_resource" in result["message"]
        assert result["details"]["retry_after_seconds"] == 30


class TestServiceUnavailableError:
    """Tests for ServiceUnavailableError."""

    def test_service_unavailable_error_scheduler(self):
        """Test ServiceUnavailableError for scheduler."""
        error = ServiceUnavailableError(
            service="background_job_scheduler",
            message="Scheduler not running",
        )

        assert error.code == "SERVICE_UNAVAILABLE"
        assert error.status == 503
        assert error.message == "Scheduler not running"
        assert error.details["service"] == "background_job_scheduler"

    def test_service_unavailable_error_database(self):
        """Test ServiceUnavailableError for database."""
        error = ServiceUnavailableError(
            service="database",
            message="Database connection pool exhausted",
        )

        assert error.code == "SERVICE_UNAVAILABLE"
        assert error.status == 503
        assert "Database" in error.message
        assert error.details["service"] == "database"

    def test_service_unavailable_error_initialization(self):
        """Test ServiceUnavailableError for uninitialized service."""
        error = ServiceUnavailableError(
            service="background_job_scheduler",
            message="Background job scheduler not initialized",
        )

        assert error.code == "SERVICE_UNAVAILABLE"
        assert error.status == 503
        assert "not initialized" in error.message

    def test_service_unavailable_error_to_dict(self):
        """Test ServiceUnavailableError to_dict conversion."""
        error = ServiceUnavailableError(
            service="test_service",
            message="Test service down",
        )

        result = error.to_dict()

        assert result["code"] == "SERVICE_UNAVAILABLE"
        assert result["message"] == "Test service down"
        assert result["details"]["service"] == "test_service"
