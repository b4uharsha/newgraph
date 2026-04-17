"""Unit tests for the algorithm router.

Tests the HTTP layer for algorithm execution endpoints.

Mocking strategy (Google testing best practices):
- AlgorithmService: MOCKED (already unit tested in test_services_algorithm.py)
- DatabaseService: MOCKED (required for db_service.is_ready check)
- Authorization dependencies: OVERRIDDEN for testing

This tests HTTP request/response handling, validation, and error cases.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, status
from fastapi.testclient import TestClient

from wrapper.models.execution import (
    AlgorithmCategory,
    AlgorithmExecution,
    AlgorithmType,
    ExecutionStatus,
)
from wrapper.routers import algo
from wrapper.services.algorithm import AlgorithmInfo, AlgorithmParameterInfo


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_algorithm_service():
    """Create mock AlgorithmService.

    AlgorithmService is mocked because it's already unit tested.
    This tests the HTTP layer in isolation.
    """
    service = MagicMock()

    # Default execution for tests
    service.get_execution.return_value = None

    # List executions returns empty by default
    service.list_executions.return_value = []

    # Execute returns a mock execution
    service.execute = AsyncMock(
        return_value=AlgorithmExecution(
            execution_id="exec-123",
            algorithm_name="pagerank",
            algorithm_type=AlgorithmType.NATIVE,
            status=ExecutionStatus.RUNNING,
            started_at=datetime.now(UTC),
            user_id="user-001",
            user_name="testuser",
            result_property="pr_score",
            write_back=True,
        )
    )

    # Cancel returns True by default
    service.cancel_execution = AsyncMock(return_value=True)

    return service


@pytest.fixture
def mock_db_service():
    """Create mock DatabaseService for is_ready check."""
    service = MagicMock()
    service.is_ready = True
    return service


@pytest.fixture
def test_app(mock_algorithm_service, mock_db_service):
    """Create FastAPI test app with mocked services."""
    app = FastAPI()
    app.include_router(algo.router)

    # Set up app state
    app.state.algorithm_service = mock_algorithm_service
    app.state.db_service = mock_db_service

    # Override authorization dependency to always pass
    from wrapper.dependencies import require_algorithm_permission

    app.dependency_overrides[require_algorithm_permission] = lambda: "user-001"

    return app


@pytest.fixture
def client(test_app):
    """Create test client."""
    return TestClient(test_app)


# =============================================================================
# Execute Algorithm Tests (POST /algo/{algorithm_name})
# =============================================================================


class TestExecuteAlgorithm:
    """Tests for POST /algo/{algorithm_name} endpoint."""

    @pytest.mark.unit
    def test_execute_algorithm_success(self, client, mock_algorithm_service):
        """POST /algo/pagerank returns execution response."""
        response = client.post(
            "/algo/pagerank",
            json={"result_property": "pr_score"},
            headers={"X-User-ID": "user-001", "X-User-Name": "testuser"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["execution_id"] == "exec-123"
        assert data["algorithm_name"] == "pagerank"
        assert data["status"] == "running"

    @pytest.mark.unit
    def test_execute_algorithm_with_all_parameters(self, client, mock_algorithm_service):
        """POST /algo/pagerank accepts all parameters."""
        response = client.post(
            "/algo/pagerank",
            json={
                "result_property": "pr_score",
                "node_labels": ["Person"],
                "relationship_types": ["KNOWS"],
                "parameters": {"damping_factor": 0.85},
                "write_back": True,
                "timeout_ms": 300000,
            },
            headers={"X-User-ID": "user-001", "X-User-Name": "testuser"},
        )

        assert response.status_code == status.HTTP_200_OK
        mock_algorithm_service.execute.assert_called_once()

    @pytest.mark.unit
    def test_execute_algorithm_missing_result_property(self, client):
        """POST /algo/pagerank returns 422 without result_property."""
        response = client.post(
            "/algo/pagerank",
            json={},  # Missing required field
            headers={"X-User-ID": "user-001"},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.unit
    def test_execute_algorithm_empty_result_property(self, client):
        """POST /algo/pagerank returns 422 with empty result_property."""
        response = client.post(
            "/algo/pagerank",
            json={"result_property": ""},
            headers={"X-User-ID": "user-001"},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.unit
    def test_execute_algorithm_result_property_too_long(self, client):
        """POST /algo/pagerank returns 422 with result_property > 64 chars."""
        response = client.post(
            "/algo/pagerank",
            json={"result_property": "x" * 65},
            headers={"X-User-ID": "user-001"},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.unit
    def test_execute_algorithm_timeout_too_short(self, client):
        """POST /algo/pagerank returns 422 with timeout < 60000."""
        response = client.post(
            "/algo/pagerank",
            json={"result_property": "pr_score", "timeout_ms": 1000},
            headers={"X-User-ID": "user-001"},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.unit
    def test_execute_algorithm_timeout_too_long(self, client):
        """POST /algo/pagerank returns 422 with timeout > 7200000."""
        response = client.post(
            "/algo/pagerank",
            json={"result_property": "pr_score", "timeout_ms": 8000000},
            headers={"X-User-ID": "user-001"},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.unit
    def test_execute_unknown_algorithm_returns_400(self, client):
        """POST /algo/unknown returns 400."""
        with patch("wrapper.routers.algo.get_algorithm", return_value=None):
            response = client.post(
                "/algo/unknown",
                json={"result_property": "score"},
                headers={"X-User-ID": "user-001"},
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Unknown algorithm" in response.json()["detail"]

    @pytest.mark.unit
    def test_execute_algorithm_db_not_ready_returns_503(self, client, mock_db_service):
        """POST /algo/pagerank returns 503 when DB not ready."""
        mock_db_service.is_ready = False

        response = client.post(
            "/algo/pagerank",
            json={"result_property": "pr_score"},
            headers={"X-User-ID": "user-001"},
        )

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    @pytest.mark.unit
    def test_execute_algorithm_value_error_returns_400(self, client, mock_algorithm_service):
        """POST /algo/pagerank returns 400 on ValueError."""
        mock_algorithm_service.execute = AsyncMock(
            side_effect=ValueError("Invalid parameter")
        )

        response = client.post(
            "/algo/pagerank",
            json={"result_property": "pr_score"},
            headers={"X-User-ID": "user-001"},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid parameter" in response.json()["detail"]


# =============================================================================
# Get Execution Status Tests (GET /algo/status/{execution_id})
# =============================================================================


class TestGetExecutionStatus:
    """Tests for GET /algo/status/{execution_id} endpoint."""

    @pytest.mark.unit
    def test_get_status_success(self, client, mock_algorithm_service):
        """GET /algo/status/exec-123 returns execution status."""
        mock_algorithm_service.get_execution.return_value = AlgorithmExecution(
            execution_id="exec-123",
            algorithm_name="pagerank",
            algorithm_type=AlgorithmType.NATIVE,
            status=ExecutionStatus.COMPLETED,
            started_at=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
            completed_at=datetime(2024, 1, 15, 10, 5, 0, tzinfo=UTC),
            user_id="user-001",
            user_name="testuser",
            result_property="pr_score",
            nodes_updated=1000,
            duration_ms=300000,
        )

        response = client.get("/algo/status/exec-123")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["execution_id"] == "exec-123"
        assert data["status"] == "completed"
        assert data["nodes_updated"] == 1000

    @pytest.mark.unit
    def test_get_status_not_found(self, client, mock_algorithm_service):
        """GET /algo/status/unknown returns 404."""
        mock_algorithm_service.get_execution.return_value = None

        response = client.get("/algo/status/unknown")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.unit
    def test_get_status_running(self, client, mock_algorithm_service):
        """GET /algo/status returns running status correctly."""
        mock_algorithm_service.get_execution.return_value = AlgorithmExecution(
            execution_id="exec-456",
            algorithm_name="betweenness",
            algorithm_type=AlgorithmType.NATIVE,
            status=ExecutionStatus.RUNNING,
            started_at=datetime.now(UTC),
            user_id="user-001",
            user_name="testuser",
            result_property="bc_score",
        )

        response = client.get("/algo/status/exec-456")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "running"
        assert data["completed_at"] is None

    @pytest.mark.unit
    def test_get_status_failed(self, client, mock_algorithm_service):
        """GET /algo/status returns failed status with error message."""
        mock_algorithm_service.get_execution.return_value = AlgorithmExecution(
            execution_id="exec-789",
            algorithm_name="wcc",
            algorithm_type=AlgorithmType.NATIVE,
            status=ExecutionStatus.FAILED,
            started_at=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
            completed_at=datetime(2024, 1, 15, 10, 1, 0, tzinfo=UTC),
            user_id="user-001",
            user_name="testuser",
            result_property="component_id",
            error_message="Query timeout",
        )

        response = client.get("/algo/status/exec-789")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "failed"
        assert data["error_message"] == "Query timeout"


# =============================================================================
# List Executions Tests (GET /algo/executions)
# =============================================================================


class TestListExecutions:
    """Tests for GET /algo/executions endpoint."""

    @pytest.mark.unit
    def test_list_executions_empty(self, client, mock_algorithm_service):
        """GET /algo/executions returns empty list."""
        mock_algorithm_service.list_executions.return_value = []

        response = client.get("/algo/executions")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["executions"] == []
        assert data["total_count"] == 0

    @pytest.mark.unit
    def test_list_executions_with_results(self, client, mock_algorithm_service):
        """GET /algo/executions returns execution list."""
        mock_algorithm_service.list_executions.return_value = [
            AlgorithmExecution(
                execution_id="exec-1",
                algorithm_name="pagerank",
                algorithm_type=AlgorithmType.NATIVE,
                status=ExecutionStatus.COMPLETED,
                started_at=datetime.now(UTC),
                user_id="user-001",
                user_name="testuser",
                result_property="pr",
            ),
            AlgorithmExecution(
                execution_id="exec-2",
                algorithm_name="wcc",
                algorithm_type=AlgorithmType.NATIVE,
                status=ExecutionStatus.RUNNING,
                started_at=datetime.now(UTC),
                user_id="user-002",
                user_name="other",
                result_property="cid",
            ),
        ]

        response = client.get("/algo/executions")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["executions"]) == 2
        assert data["total_count"] == 2

    @pytest.mark.unit
    def test_list_executions_with_limit(self, client, mock_algorithm_service):
        """GET /algo/executions?limit=5 passes limit to service."""
        response = client.get("/algo/executions?limit=5")

        assert response.status_code == status.HTTP_200_OK
        mock_algorithm_service.list_executions.assert_called_once_with(
            limit=5, status=None
        )

    @pytest.mark.unit
    def test_list_executions_with_status_filter(self, client, mock_algorithm_service):
        """GET /algo/executions?status_filter=completed filters by status."""
        response = client.get("/algo/executions?status_filter=completed")

        assert response.status_code == status.HTTP_200_OK
        mock_algorithm_service.list_executions.assert_called_once_with(
            limit=20, status=ExecutionStatus.COMPLETED
        )


# =============================================================================
# Cancel Execution Tests (DELETE /algo/executions/{execution_id})
# =============================================================================


class TestCancelExecution:
    """Tests for DELETE /algo/executions/{execution_id} endpoint."""

    @pytest.mark.unit
    def test_cancel_execution_success(self, client, mock_algorithm_service):
        """DELETE /algo/executions/exec-123 cancels execution."""
        mock_algorithm_service.cancel_execution = AsyncMock(return_value=True)

        response = client.delete("/algo/executions/exec-123")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "cancelled"
        assert data["execution_id"] == "exec-123"

    @pytest.mark.unit
    def test_cancel_execution_not_found(self, client, mock_algorithm_service):
        """DELETE /algo/executions/unknown returns 404."""
        mock_algorithm_service.cancel_execution = AsyncMock(return_value=False)

        response = client.delete("/algo/executions/unknown")

        assert response.status_code == status.HTTP_404_NOT_FOUND


# =============================================================================
# List Algorithms Tests (GET /algo/algorithms)
# =============================================================================


class TestListAlgorithms:
    """Tests for GET /algo/algorithms endpoint."""

    @pytest.mark.unit
    def test_list_algorithms(self, client):
        """GET /algo/algorithms returns algorithm list."""
        response = client.get("/algo/algorithms")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "algorithms" in data
        assert "total_count" in data
        assert data["total_count"] == 4

        # Check all algorithms present
        names = [a["name"] for a in data["algorithms"]]
        assert "pagerank" in names
        assert "betweenness" in names
        assert "wcc" in names
        assert "cdlp" in names

    @pytest.mark.unit
    def test_list_algorithms_structure(self, client):
        """GET /algo/algorithms returns correct structure."""
        response = client.get("/algo/algorithms")
        data = response.json()

        for algo in data["algorithms"]:
            assert "name" in algo
            assert "display_name" in algo
            assert "category" in algo
            assert "description" in algo
            assert "cypher_procedure" in algo
            assert "supports_write_back" in algo
            assert "default_timeout_ms" in algo
            assert "parameters" in algo


# =============================================================================
# Get Algorithm Info Tests (GET /algo/algorithms/{algorithm_name})
# =============================================================================


class TestGetAlgorithmInfo:
    """Tests for GET /algo/algorithms/{algorithm_name} endpoint."""

    @pytest.mark.unit
    def test_get_algorithm_info_pagerank(self, client):
        """GET /algo/algorithms/pagerank returns algorithm details."""
        response = client.get("/algo/algorithms/pagerank")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["name"] == "pagerank"
        assert data["display_name"] == "PageRank"
        assert data["category"] == "centrality"
        assert data["supports_write_back"] is True

    @pytest.mark.unit
    def test_get_algorithm_info_betweenness(self, client):
        """GET /algo/algorithms/betweenness returns algorithm details."""
        response = client.get("/algo/algorithms/betweenness")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["name"] == "betweenness"
        assert data["category"] == "centrality"

    @pytest.mark.unit
    def test_get_algorithm_info_wcc(self, client):
        """GET /algo/algorithms/wcc returns algorithm details."""
        response = client.get("/algo/algorithms/wcc")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["name"] == "wcc"
        assert data["category"] == "community"

    @pytest.mark.unit
    def test_get_algorithm_info_cdlp(self, client):
        """GET /algo/algorithms/cdlp returns algorithm details."""
        response = client.get("/algo/algorithms/cdlp")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["name"] == "cdlp"
        assert data["display_name"] == "Community Detection (Label Propagation)"

    @pytest.mark.unit
    def test_get_algorithm_info_not_found(self, client):
        """GET /algo/algorithms/unknown returns 404."""
        response = client.get("/algo/algorithms/unknown")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.unit
    def test_get_algorithm_info_includes_parameters(self, client):
        """GET /algo/algorithms/cdlp includes parameters."""
        response = client.get("/algo/algorithms/cdlp")
        data = response.json()

        assert "parameters" in data
        assert len(data["parameters"]) > 0

        param = data["parameters"][0]
        assert "name" in param
        assert "type" in param
        assert "required" in param


# =============================================================================
# Service Not Initialized Tests
# =============================================================================


class TestServiceNotInitialized:
    """Tests for when services are not initialized."""

    @pytest.mark.unit
    def test_execute_without_algorithm_service(self):
        """POST /algo/pagerank returns 503 when service not initialized."""
        app = FastAPI()
        app.include_router(algo.router)

        # Don't set app.state.algorithm_service
        app.state.db_service = MagicMock(is_ready=True)

        # Override auth
        from wrapper.dependencies import require_algorithm_permission

        app.dependency_overrides[require_algorithm_permission] = lambda: "user-001"

        client = TestClient(app)
        response = client.post(
            "/algo/pagerank",
            json={"result_property": "pr"},
        )

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    @pytest.mark.unit
    def test_get_status_without_algorithm_service(self):
        """GET /algo/status/exec-123 returns 503 when service not initialized."""
        app = FastAPI()
        app.include_router(algo.router)
        # Don't set app.state.algorithm_service

        client = TestClient(app)
        response = client.get("/algo/status/exec-123")

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


# =============================================================================
# Authorization Tests
# =============================================================================


class TestAuthorization:
    """Tests for algorithm execution authorization."""

    @pytest.mark.unit
    def test_execute_denied_without_permission(self, mock_algorithm_service, mock_db_service):
        """POST /algo/pagerank returns 403 when not authorized."""
        from fastapi import HTTPException

        from wrapper.dependencies import require_algorithm_permission

        app = FastAPI()
        app.include_router(algo.router)
        app.state.algorithm_service = mock_algorithm_service
        app.state.db_service = mock_db_service

        # Override to deny permission
        def deny_permission():
            raise HTTPException(status_code=403, detail="Permission denied")

        app.dependency_overrides[require_algorithm_permission] = deny_permission

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/algo/pagerank",
            json={"result_property": "pr"},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
