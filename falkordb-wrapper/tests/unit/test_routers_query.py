"""Unit tests for query router."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI, status
from fastapi.testclient import TestClient

from wrapper.exceptions import (
    DatabaseNotInitializedError,
    QuerySyntaxError,
    QueryTimeoutError,
)
from wrapper.main import (
    database_not_initialized_handler,
    query_syntax_error_handler,
    query_timeout_handler,
)
from wrapper.routers import query


class TestQueryRouter:
    """Tests for query router."""

    @pytest.fixture
    def mock_database_service(self):
        """Create a mock database service."""
        service = Mock()
        service.is_initialized = True
        service.is_ready = True
        service.execute_query = AsyncMock()
        return service

    @pytest.fixture
    def test_app(self, mock_database_service):
        """Create a test FastAPI app with proper DI via app.state."""
        app = FastAPI()
        app.include_router(query.router)

        # Set up app state (proper DI pattern)
        app.state.db_service = mock_database_service

        # Register exception handlers for proper error handling
        app.add_exception_handler(QuerySyntaxError, query_syntax_error_handler)
        app.add_exception_handler(QueryTimeoutError, query_timeout_handler)
        app.add_exception_handler(DatabaseNotInitializedError, database_not_initialized_handler)

        return app

    @pytest.mark.unit
    def test_query_success(self, test_app, mock_database_service):
        """Test successful query execution (flat response structure)."""
        mock_database_service.execute_query.return_value = {
            "columns": ["name", "age"],
            "rows": [["Alice", 30], ["Bob", 25]],
            "row_count": 2,
            "execution_time_ms": 10.5,
            "truncated": False,
        }

        client = TestClient(test_app)
        response = client.post(
            "/query",
            json={
                "cypher": "MATCH (n:Person) RETURN n.name, n.age",
                "parameters": {},
            },
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        # Flat response structure - no "data" wrapper
        assert data["columns"] == ["name", "age"]
        assert data["row_count"] == 2
        assert data["execution_time_ms"] == 10
        assert data["truncated"] is False

    @pytest.mark.unit
    def test_query_with_parameters(self, test_app, mock_database_service):
        """Test query with parameters."""
        mock_database_service.execute_query.return_value = {
            "columns": ["name"],
            "rows": [["Alice"]],
            "row_count": 1,
            "execution_time_ms": 5.0,
        }

        client = TestClient(test_app)
        response = client.post(
            "/query",
            json={
                "cypher": "MATCH (n:Person {name: $name}) RETURN n.name",
                "parameters": {"name": "Alice"},
            },
        )

        assert response.status_code == status.HTTP_200_OK
        # Verify parameters were passed
        mock_database_service.execute_query.assert_called_once()
        call_args = mock_database_service.execute_query.call_args
        assert call_args[1]["parameters"] == {"name": "Alice"}

    @pytest.mark.unit
    def test_query_syntax_error(self, test_app, mock_database_service):
        """Test query with syntax error returns 400."""
        mock_database_service.execute_query.side_effect = QuerySyntaxError(
            "Invalid Cypher syntax",
            query="INVALID CYPHER",
        )

        client = TestClient(test_app)
        response = client.post(
            "/query",
            json={"cypher": "INVALID CYPHER"},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert data["error"]["code"] == "QUERY_SYNTAX_ERROR"

    @pytest.mark.unit
    def test_query_timeout(self, test_app, mock_database_service):
        """Test query timeout returns 408."""
        mock_database_service.execute_query.side_effect = QueryTimeoutError(
            timeout_ms=5000,
            elapsed_ms=5100,
        )

        client = TestClient(test_app)
        response = client.post(
            "/query",
            json={"cypher": "MATCH (n) RETURN n", "timeout_ms": 5000},
        )

        assert response.status_code == status.HTTP_408_REQUEST_TIMEOUT
        data = response.json()
        assert data["error"]["code"] == "QUERY_TIMEOUT"

    @pytest.mark.unit
    def test_query_database_not_initialized(self, test_app, mock_database_service):
        """Test query when database not initialized returns 503."""
        mock_database_service.execute_query.side_effect = DatabaseNotInitializedError()

        client = TestClient(test_app)
        response = client.post(
            "/query",
            json={"cypher": "MATCH (n) RETURN n"},
        )

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        data = response.json()
        assert data["error"]["code"] == "DATABASE_NOT_INITIALIZED"

    @pytest.mark.unit
    def test_query_validation_missing_cypher(self, test_app):
        """Test query validation fails when cypher is missing."""
        client = TestClient(test_app)
        response = client.post(
            "/query",
            json={"parameters": {}},  # Missing cypher
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.unit
    def test_query_validation_empty_cypher(self, test_app):
        """Test query validation fails when cypher is empty."""
        client = TestClient(test_app)
        response = client.post(
            "/query",
            json={"cypher": ""},  # Empty string
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.unit
    def test_query_includes_truncated_field(self, test_app, mock_database_service):
        """Test query response includes truncated field."""
        mock_database_service.execute_query.return_value = {
            "columns": ["name"],
            "rows": [["Alice"]],
            "row_count": 1,
            "execution_time_ms": 5.0,
            "truncated": True,
        }

        client = TestClient(test_app)
        response = client.post(
            "/query",
            json={"cypher": "MATCH (n) RETURN n LIMIT 1000"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "truncated" in data
        assert data["truncated"] is True
