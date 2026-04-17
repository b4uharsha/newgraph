"""Tests for exception classes."""

from datetime import UTC, datetime

from wrapper.exceptions import (
    AlgorithmError,
    AlgorithmExecutionError,
    AlgorithmNotFoundError,
    AlgorithmTimeoutError,
    ControlPlaneConnectionError,
    ControlPlaneError,
    ControlPlaneTimeoutError,
    DatabaseConnectionError,
    DatabaseError,
    DatabaseNotInitializedError,
    DataLoadError,
    InvalidAlgorithmParametersError,
    LockAcquisitionError,
    MappingNotFoundError,
    QueryError,
    QueryExecutionError,
    QuerySyntaxError,
    QueryTimeoutError,
    ResourceLockedError,
    SchemaCreationError,
    StartupError,
    ValidationError,
    WrapperError,
)


class TestWrapperError:
    """Tests for base WrapperError."""

    def test_wrapper_error_basic(self):
        """Test basic WrapperError creation."""
        error = WrapperError("Test error")
        assert error.message == "Test error"
        assert error.error_code == "WRAPPER_ERROR"
        assert error.http_status == 500
        assert error.details == {}

    def test_wrapper_error_with_details(self):
        """Test WrapperError with details."""
        error = WrapperError("Test error", details={"key": "value"})
        assert error.details == {"key": "value"}

    def test_wrapper_error_to_dict(self):
        """Test WrapperError to_dict conversion."""
        error = WrapperError("Test error", details={"key": "value"})
        result = error.to_dict()
        assert result == {
            "error": {
                "code": "WRAPPER_ERROR",
                "message": "Test error",
                "details": {"key": "value"},
            }
        }


class TestDatabaseErrors:
    """Tests for database-related errors."""

    def test_database_error(self):
        """Test DatabaseError."""
        error = DatabaseError("DB error")
        assert error.error_code == "DATABASE_ERROR"
        assert error.http_status == 500

    def test_database_not_initialized_error(self):
        """Test DatabaseNotInitializedError."""
        error = DatabaseNotInitializedError()
        assert error.message == "Database has not been initialized"
        assert error.error_code == "DATABASE_NOT_INITIALIZED"

    def test_database_connection_error(self):
        """Test DatabaseConnectionError."""
        error = DatabaseConnectionError("Connection failed")
        assert error.error_code == "DATABASE_CONNECTION_ERROR"

    def test_schema_creation_error(self):
        """Test SchemaCreationError."""
        error = SchemaCreationError("Failed to create schema")
        assert error.error_code == "SCHEMA_CREATION_ERROR"

    def test_data_load_error_basic(self):
        """Test DataLoadError without optional fields."""
        error = DataLoadError("Load failed")
        assert error.error_code == "DATA_LOAD_ERROR"
        assert error.message == "Load failed"

    def test_data_load_error_with_table_and_path(self):
        """Test DataLoadError with table name and GCS path."""
        error = DataLoadError(
            "Load failed",
            table_name="person",
            gcs_path="gs://bucket/data.parquet",
        )
        assert error.details["table_name"] == "person"
        assert error.details["gcs_path"] == "gs://bucket/data.parquet"

    def test_data_load_error_with_existing_details(self):
        """Test DataLoadError merges with existing details."""
        error = DataLoadError(
            "Load failed",
            table_name="person",
            details={"extra": "info"},
        )
        assert error.details["table_name"] == "person"
        assert error.details["extra"] == "info"


class TestQueryErrors:
    """Tests for query-related errors."""

    def test_query_error(self):
        """Test QueryError."""
        error = QueryError("Query failed")
        assert error.error_code == "QUERY_ERROR"
        assert error.http_status == 400

    def test_query_syntax_error_basic(self):
        """Test QuerySyntaxError without optional fields."""
        error = QuerySyntaxError("Syntax error")
        assert error.error_code == "QUERY_SYNTAX_ERROR"
        assert error.message == "Syntax error"

    def test_query_syntax_error_with_query(self):
        """Test QuerySyntaxError with query."""
        error = QuerySyntaxError(
            "Syntax error",
            query="MATCH (n) RETURN n",
        )
        assert error.details["query"] == "MATCH (n) RETURN n"

    def test_query_syntax_error_with_position(self):
        """Test QuerySyntaxError with position."""
        error = QuerySyntaxError(
            "Syntax error",
            query="MATCH (n) RETURN n",
            position=10,
        )
        assert error.details["position"] == 10

    def test_query_syntax_error_truncates_long_query(self):
        """Test QuerySyntaxError truncates long queries."""
        long_query = "A" * 1000
        error = QuerySyntaxError("Syntax error", query=long_query)
        assert len(error.details["query"]) == 500

    def test_query_timeout_error_basic(self):
        """Test QueryTimeoutError."""
        error = QueryTimeoutError(timeout_ms=5000)
        assert error.error_code == "QUERY_TIMEOUT"
        assert error.http_status == 408
        assert error.timeout_ms == 5000
        assert "5000ms" in error.message

    def test_query_timeout_error_with_elapsed(self):
        """Test QueryTimeoutError with elapsed time."""
        error = QueryTimeoutError(timeout_ms=5000, elapsed_ms=5100)
        assert error.elapsed_ms == 5100
        assert error.details["elapsed_ms"] == 5100

    def test_query_timeout_error_with_query(self):
        """Test QueryTimeoutError with query."""
        error = QueryTimeoutError(
            timeout_ms=5000,
            query="MATCH (n) RETURN n",
        )
        assert error.details["query"] == "MATCH (n) RETURN n"

    def test_query_execution_error(self):
        """Test QueryExecutionError."""
        error = QueryExecutionError("Execution failed")
        assert error.error_code == "QUERY_EXECUTION_ERROR"
        assert error.http_status == 500


class TestAlgorithmErrors:
    """Tests for algorithm-related errors."""

    def test_algorithm_error_basic(self):
        """Test AlgorithmError without algorithm name."""
        error = AlgorithmError("Algorithm failed")
        assert error.error_code == "ALGORITHM_ERROR"
        assert error.http_status == 500
        assert error.algorithm_name is None

    def test_algorithm_error_with_name(self):
        """Test AlgorithmError with algorithm name."""
        error = AlgorithmError("Failed", algorithm_name="pagerank")
        assert error.algorithm_name == "pagerank"
        assert error.details["algorithm_name"] == "pagerank"

    def test_algorithm_not_found_error(self):
        """Test AlgorithmNotFoundError."""
        error = AlgorithmNotFoundError("pagerank", "networkx")
        assert error.error_code == "ALGORITHM_NOT_FOUND"
        assert error.http_status == 404
        assert "pagerank" in error.message
        assert error.details["algorithm_type"] == "networkx"

    def test_algorithm_not_found_error_default_type(self):
        """Test AlgorithmNotFoundError with default type."""
        error = AlgorithmNotFoundError("pagerank")
        assert error.details["algorithm_type"] == "unknown"

    def test_algorithm_execution_error_basic(self):
        """Test AlgorithmExecutionError."""
        error = AlgorithmExecutionError("Execution failed")
        assert error.error_code == "ALGORITHM_EXECUTION_ERROR"

    def test_algorithm_execution_error_with_details(self):
        """Test AlgorithmExecutionError with algorithm and execution ID."""
        error = AlgorithmExecutionError(
            "Failed",
            algorithm_name="pagerank",
            execution_id="exec-123",
        )
        assert error.details["algorithm_name"] == "pagerank"
        assert error.details["execution_id"] == "exec-123"

    def test_algorithm_timeout_error_basic(self):
        """Test AlgorithmTimeoutError."""
        error = AlgorithmTimeoutError(timeout_ms=30000)
        assert error.error_code == "ALGORITHM_TIMEOUT"
        assert error.http_status == 408
        assert "30000ms" in error.message

    def test_algorithm_timeout_error_with_details(self):
        """Test AlgorithmTimeoutError with algorithm and execution ID."""
        error = AlgorithmTimeoutError(
            timeout_ms=30000,
            algorithm_name="pagerank",
            execution_id="exec-456",
        )
        assert error.details["algorithm_name"] == "pagerank"
        assert error.details["execution_id"] == "exec-456"

    def test_invalid_algorithm_parameters_error_basic(self):
        """Test InvalidAlgorithmParametersError."""
        error = InvalidAlgorithmParametersError("Invalid params")
        assert error.error_code == "INVALID_ALGORITHM_PARAMETERS"
        assert error.http_status == 400

    def test_invalid_algorithm_parameters_error_with_details(self):
        """Test InvalidAlgorithmParametersError with algorithm and params."""
        error = InvalidAlgorithmParametersError(
            "Invalid params",
            algorithm_name="pagerank",
            invalid_params=["alpha", "beta"],
        )
        assert error.details["algorithm_name"] == "pagerank"
        assert error.details["invalid_params"] == ["alpha", "beta"]


class TestLockErrors:
    """Tests for lock-related errors."""

    def test_resource_locked_error(self):
        """Test ResourceLockedError."""
        now = datetime.now(UTC)
        error = ResourceLockedError(
            holder_id="user-123",
            holder_username="test-user",
            algorithm_name="pagerank",
            acquired_at=now,
        )
        assert error.error_code == "RESOURCE_LOCKED"
        assert error.http_status == 409
        assert error.holder_id == "user-123"
        assert error.holder_username == "test-user"
        assert error.algorithm_name == "pagerank"
        assert error.acquired_at == now
        assert "test-user" in error.message
        assert "pagerank" in error.message

    def test_lock_acquisition_error(self):
        """Test LockAcquisitionError."""
        error = LockAcquisitionError("Failed to acquire lock")
        assert error.error_code == "LOCK_ACQUISITION_ERROR"
        assert error.http_status == 500


class TestControlPlaneErrors:
    """Tests for Control Plane-related errors."""

    def test_control_plane_error_basic(self):
        """Test ControlPlaneError."""
        error = ControlPlaneError("Control plane error")
        assert error.error_code == "CONTROL_PLANE_ERROR"
        assert error.http_status == 502
        assert error.status_code is None

    def test_control_plane_error_with_status_code(self):
        """Test ControlPlaneError with status code."""
        error = ControlPlaneError("Error", status_code=404)
        assert error.status_code == 404
        assert error.details["status_code"] == 404

    def test_control_plane_connection_error(self):
        """Test ControlPlaneConnectionError."""
        error = ControlPlaneConnectionError("Connection failed")
        assert error.error_code == "CONTROL_PLANE_CONNECTION_ERROR"

    def test_control_plane_timeout_error(self):
        """Test ControlPlaneTimeoutError."""
        error = ControlPlaneTimeoutError("Timeout")
        assert error.error_code == "CONTROL_PLANE_TIMEOUT"
        assert error.http_status == 504


class TestValidationErrors:
    """Tests for validation errors."""

    def test_validation_error(self):
        """Test ValidationError."""
        error = ValidationError("Validation failed")
        assert error.error_code == "VALIDATION_ERROR"
        assert error.http_status == 400


class TestStartupErrors:
    """Tests for startup errors."""

    def test_startup_error(self):
        """Test StartupError."""
        error = StartupError("Startup failed")
        assert error.error_code == "STARTUP_ERROR"
        assert error.http_status == 503

    def test_mapping_not_found_error(self):
        """Test MappingNotFoundError."""
        error = MappingNotFoundError("mapping-123")
        assert error.error_code == "MAPPING_NOT_FOUND"
        assert error.http_status == 404
        assert "mapping-123" in error.message
        assert error.details["mapping_id"] == "mapping-123"
