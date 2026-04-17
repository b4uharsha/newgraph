"""Unit tests for exception hierarchy."""

from __future__ import annotations

from graph_olap.exceptions import (
    AlgorithmFailedError,
    AlgorithmNotFoundError,
    AlgorithmTimeoutError,
    AuthenticationError,
    ConcurrencyLimitError,
    ConflictError,
    DependencyError,
    GraphOLAPError,
    InstanceFailedError,
    InvalidStateError,
    NotFoundError,
    PermissionDeniedError,
    QueryTimeoutError,
    ResourceLockedError,
    RyugraphError,
    ServerError,
    ServiceUnavailableError,
    SnapshotFailedError,
    TimeoutError,
    ValidationError,
    exception_from_response,
)


class TestExceptionHierarchy:
    """Tests for exception class hierarchy."""

    def test_all_exceptions_inherit_from_base(self):
        """Test all custom exceptions inherit from GraphOLAPError."""
        exceptions = [
            AuthenticationError,
            PermissionDeniedError,
            NotFoundError,
            ValidationError,
            ConflictError,
            ResourceLockedError,
            ConcurrencyLimitError,
            DependencyError,
            InvalidStateError,
            TimeoutError,
            QueryTimeoutError,
            AlgorithmTimeoutError,
            RyugraphError,
            AlgorithmNotFoundError,
            AlgorithmFailedError,
            SnapshotFailedError,
            InstanceFailedError,
            ServerError,
            ServiceUnavailableError,
        ]

        for exc_class in exceptions:
            assert issubclass(exc_class, GraphOLAPError)
            assert issubclass(exc_class, Exception)

    def test_conflict_error_subclasses(self):
        """Test conflict error hierarchy."""
        assert issubclass(ResourceLockedError, ConflictError)
        assert issubclass(ConcurrencyLimitError, ConflictError)
        assert issubclass(DependencyError, ConflictError)
        assert issubclass(InvalidStateError, ConflictError)

    def test_timeout_error_subclasses(self):
        """Test timeout error hierarchy."""
        assert issubclass(QueryTimeoutError, TimeoutError)
        assert issubclass(AlgorithmTimeoutError, TimeoutError)

    def test_server_error_subclasses(self):
        """Test server error hierarchy."""
        assert issubclass(ServiceUnavailableError, ServerError)

    def test_base_exception_message(self):
        """Test GraphOLAPError stores message correctly."""
        exc = GraphOLAPError("Test error message")
        assert str(exc) == "Test error message"


class TestExceptionWithDetails:
    """Tests for exceptions that store details."""

    def test_not_found_error_with_details(self):
        """Test NotFoundError stores details."""
        details = {"resource_type": "mapping", "id": 123}
        exc = NotFoundError("Mapping not found", details)

        assert str(exc) == "Mapping not found"
        assert exc.details == details

    def test_validation_error_with_details(self):
        """Test ValidationError stores details."""
        details = {"field": "name", "error": "required"}
        exc = ValidationError("Validation failed", details)

        assert exc.details == details

    def test_permission_denied_with_details(self):
        """Test PermissionDeniedError stores details."""
        details = {"required_role": "admin"}
        exc = PermissionDeniedError("Access denied", details)

        assert exc.details == details

    def test_ryugraph_error_with_details(self):
        """Test RyugraphError stores details."""
        details = {"query": "MATCH (n) RETURN n", "position": 5}
        exc = RyugraphError("Syntax error", details)

        assert exc.details == details


class TestResourceLockedError:
    """Tests for ResourceLockedError exception."""

    def test_locked_error_properties(self):
        """Test ResourceLockedError property accessors."""
        details = {
            "holder_name": "Test User",
            "algorithm": "pagerank",
        }
        exc = ResourceLockedError("Instance locked", details)

        assert exc.holder_name == "Test User"
        assert exc.algorithm == "pagerank"

    def test_locked_error_without_details(self):
        """Test ResourceLockedError with empty details."""
        exc = ResourceLockedError("Resource is locked", {})

        assert exc.holder_name is None
        assert exc.algorithm is None


class TestConcurrencyLimitError:
    """Tests for ConcurrencyLimitError exception."""

    def test_concurrency_error_properties(self):
        """Test ConcurrencyLimitError property accessors."""
        details = {
            "limit_type": "user",
            "current_count": 5,
            "max_allowed": 5,
        }
        exc = ConcurrencyLimitError("Limit reached", details)

        assert exc.limit_type == "user"
        assert exc.current_count == 5
        assert exc.max_allowed == 5

    def test_concurrency_error_without_details(self):
        """Test ConcurrencyLimitError with empty details."""
        exc = ConcurrencyLimitError("Too many instances", {})

        assert exc.limit_type is None
        assert exc.current_count is None
        assert exc.max_allowed is None


class TestExceptionFromResponse:
    """Tests for exception_from_response factory function."""

    def test_401_returns_authentication_error(self):
        """Test 401 status returns AuthenticationError."""
        exc = exception_from_response(
            status_code=401,
            error_code=None,
            message="Invalid API key",
        )

        assert isinstance(exc, AuthenticationError)

    def test_403_returns_permission_denied_error(self):
        """Test 403 status returns PermissionDeniedError."""
        exc = exception_from_response(
            status_code=403,
            error_code=None,
            message="Forbidden",
            details={"required_role": "admin"},
        )

        assert isinstance(exc, PermissionDeniedError)
        assert exc.details["required_role"] == "admin"

    def test_404_returns_not_found_error(self):
        """Test 404 status returns NotFoundError."""
        exc = exception_from_response(
            status_code=404,
            error_code=None,
            message="Mapping not found",
        )

        assert isinstance(exc, NotFoundError)

    def test_422_returns_validation_error(self):
        """Test 422 status returns ValidationError."""
        exc = exception_from_response(
            status_code=422,
            error_code=None,
            message="Invalid parameter",
            details={"name": "required"},
        )

        assert isinstance(exc, ValidationError)
        assert exc.details["name"] == "required"

    def test_409_returns_conflict_error(self):
        """Test 409 status returns ConflictError."""
        exc = exception_from_response(
            status_code=409,
            error_code=None,
            message="Conflict",
        )

        assert isinstance(exc, ConflictError)

    def test_429_returns_concurrency_limit_error(self):
        """Test 429 status returns ConcurrencyLimitError."""
        exc = exception_from_response(
            status_code=429,
            error_code=None,
            message="Rate limit exceeded",
        )

        assert isinstance(exc, ConcurrencyLimitError)

    def test_500_returns_server_error(self):
        """Test 500 status returns ServerError."""
        exc = exception_from_response(
            status_code=500,
            error_code=None,
            message="Internal server error",
        )

        assert isinstance(exc, ServerError)

    def test_503_returns_service_unavailable_error(self):
        """Test 503 status returns ServiceUnavailableError."""
        exc = exception_from_response(
            status_code=503,
            error_code=None,
            message="Service unavailable",
        )

        assert isinstance(exc, ServiceUnavailableError)

    def test_unknown_status_returns_base_error(self):
        """Test unknown status returns GraphOLAPError."""
        exc = exception_from_response(
            status_code=418,
            error_code=None,
            message="I'm a teapot",
        )

        assert type(exc) is GraphOLAPError

    def test_resource_locked_error_code(self):
        """Test RESOURCE_LOCKED error code returns ResourceLockedError."""
        exc = exception_from_response(
            status_code=409,
            error_code="RESOURCE_LOCKED",
            message="Instance is locked",
            details={"holder_name": "User", "algorithm": "pagerank"},
        )

        assert isinstance(exc, ResourceLockedError)
        assert exc.holder_name == "User"
        assert exc.algorithm == "pagerank"

    def test_concurrency_limit_error_code(self):
        """Test CONCURRENCY_LIMIT error code returns ConcurrencyLimitError."""
        exc = exception_from_response(
            status_code=409,
            error_code="CONCURRENCY_LIMIT",
            message="Limit reached",
            details={"current_count": 5, "max_allowed": 5},
        )

        assert isinstance(exc, ConcurrencyLimitError)
        assert exc.current_count == 5
        assert exc.max_allowed == 5

    def test_dependency_exists_error_code(self):
        """Test DEPENDENCY_EXISTS error code returns DependencyError."""
        exc = exception_from_response(
            status_code=409,
            error_code="DEPENDENCY_EXISTS",
            message="Cannot delete mapping with snapshots",
        )

        assert isinstance(exc, DependencyError)

    def test_invalid_state_error_code(self):
        """Test INVALID_STATE error code returns InvalidStateError."""
        exc = exception_from_response(
            status_code=409,
            error_code="INVALID_STATE",
            message="Snapshot not ready",
        )

        assert isinstance(exc, InvalidStateError)

    def test_query_timeout_error_code(self):
        """Test QUERY_TIMEOUT error code returns QueryTimeoutError."""
        exc = exception_from_response(
            status_code=408,
            error_code="QUERY_TIMEOUT",
            message="Query timed out",
        )

        assert isinstance(exc, QueryTimeoutError)

    def test_algorithm_timeout_error_code(self):
        """Test ALGORITHM_TIMEOUT error code returns AlgorithmTimeoutError."""
        exc = exception_from_response(
            status_code=408,
            error_code="ALGORITHM_TIMEOUT",
            message="Algorithm timed out",
        )

        assert isinstance(exc, AlgorithmTimeoutError)

    def test_algorithm_not_found_error_code(self):
        """Test ALGORITHM_NOT_FOUND error code returns AlgorithmNotFoundError."""
        exc = exception_from_response(
            status_code=404,
            error_code="ALGORITHM_NOT_FOUND",
            message="Unknown algorithm: foo",
        )

        assert isinstance(exc, AlgorithmNotFoundError)

    def test_algorithm_failed_error_code(self):
        """Test ALGORITHM_FAILED error code returns AlgorithmFailedError."""
        exc = exception_from_response(
            status_code=500,
            error_code="ALGORITHM_FAILED",
            message="Algorithm execution failed",
        )

        assert isinstance(exc, AlgorithmFailedError)

    def test_ryugraph_error_code(self):
        """Test RYUGRAPH_ERROR error code returns RyugraphError."""
        exc = exception_from_response(
            status_code=400,
            error_code="RYUGRAPH_ERROR",
            message="Syntax error",
            details={"query": "MATCH (n) RETURN", "position": 15},
        )

        assert isinstance(exc, RyugraphError)
        assert exc.details["query"] == "MATCH (n) RETURN"

    # =============================================================================
    # SNAPSHOT TESTS DISABLED
    # These tests are commented out as snapshot functionality has been disabled.
    # =============================================================================
    # def test_snapshot_failed_error_code(self):
    #     """Test SNAPSHOT_FAILED error code returns SnapshotFailedError."""
    #     exc = exception_from_response(
    #         status_code=500,
    #         error_code="SNAPSHOT_FAILED",
    #         message="Snapshot export failed",
    #     )
    #
    #     assert isinstance(exc, SnapshotFailedError)

    def test_instance_failed_error_code(self):
        """Test INSTANCE_FAILED error code returns InstanceFailedError."""
        exc = exception_from_response(
            status_code=500,
            error_code="INSTANCE_FAILED",
            message="Instance startup failed",
        )

        assert isinstance(exc, InstanceFailedError)
