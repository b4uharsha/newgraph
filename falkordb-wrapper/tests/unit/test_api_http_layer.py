"""Unit tests for the FalkorDB Wrapper HTTP layer.

These tests verify the HTTP request/response handling through FastAPI,
including routing, request validation, response formatting, and exception
handling. All backend services are mocked since this tests the HTTP layer
in isolation.

Note: This file was previously named test_api_integration.py in the
integration/ directory. It was renamed because:
1. All services (DatabaseService, ControlPlaneClient, LockService) are mocked
2. No real service integration is tested
3. It tests HTTP layer behavior, not component integration

For true integration tests (with real services), see:
- tests/integration/test_control_plane_integration.py
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def create_test_app(
    mock_db_service: Any = None,
    mock_cp_client: Any = None,
    mock_lock_service: Any = None,
) -> FastAPI:
    """Create a FastAPI app without lifespan for testing.

    This bypasses the production lifespan which tries to connect to
    Control Plane and load data. Tests set up their own mocked state.

    Args:
        mock_db_service: Mocked database service
        mock_cp_client: Mocked control plane client
        mock_lock_service: Mocked lock service
    """
    from fastapi import Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse

    from wrapper.dependencies import get_database_service, get_lock_service
    from wrapper.exceptions import (
        DatabaseNotInitializedError,
        QuerySyntaxError,
        QueryTimeoutError,
        WrapperError,
    )
    from wrapper.routers import health, query

    @asynccontextmanager
    async def null_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        """No-op lifespan for tests."""
        yield

    app = FastAPI(
        title="FalkorDB Wrapper API (Test)",
        lifespan=null_lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register exception handlers (same as main.py)
    @app.exception_handler(WrapperError)
    async def wrapper_error_handler(request: Request, exc: WrapperError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content=exc.to_dict())

    @app.exception_handler(QuerySyntaxError)
    async def query_syntax_error_handler(
        request: Request, exc: QuerySyntaxError
    ) -> JSONResponse:
        return JSONResponse(status_code=400, content=exc.to_dict())

    @app.exception_handler(QueryTimeoutError)
    async def query_timeout_handler(
        request: Request, exc: QueryTimeoutError
    ) -> JSONResponse:
        return JSONResponse(status_code=408, content=exc.to_dict())

    @app.exception_handler(DatabaseNotInitializedError)
    async def database_not_initialized_handler(
        request: Request, exc: DatabaseNotInitializedError
    ) -> JSONResponse:
        return JSONResponse(status_code=503, content=exc.to_dict())

    app.include_router(health.router)
    app.include_router(query.router)

    # Override dependencies using FastAPI's dependency_overrides
    if mock_db_service:
        app.dependency_overrides[get_database_service] = lambda: mock_db_service
    if mock_lock_service:
        app.dependency_overrides[get_lock_service] = lambda: mock_lock_service

    # Store mocks in app state for test access
    if mock_db_service:
        app.state.db_service = mock_db_service
    if mock_cp_client:
        app.state.control_plane_client = mock_cp_client
    if mock_lock_service:
        app.state.lock_service = mock_lock_service

    @app.get("/", tags=["Root"])
    async def root() -> dict[str, str]:
        return {"name": "FalkorDB Wrapper API", "version": "1.0.0", "docs": "/docs"}

    return app


class TestHealthEndpoints:
    """Integration tests for health endpoints."""

    @pytest.fixture
    def app_with_mocks(self) -> FastAPI:
        """Create app with mocked services."""
        from unittest.mock import Mock

        from wrapper.dependencies import get_app_settings
        from wrapper.models.lock import LockInfo
        from wrapper.services.database import DatabaseService

        # Mock services
        mock_db = MagicMock(spec=DatabaseService)
        mock_db.is_initialized = True
        mock_db.is_ready = True
        mock_db.is_connected = True
        mock_db.graph_name = "test_graph"

        # Mock ready_at as a datetime-like object
        mock_ready_at = Mock()
        mock_ready_at.isoformat = Mock(return_value="2025-01-15T10:00:00Z")
        mock_db.ready_at = mock_ready_at

        mock_db.execute_query = AsyncMock(return_value={
            "columns": ["1"],
            "rows": [[1]],
            "row_count": 1,
        })
        mock_db.get_stats = AsyncMock(return_value={
            "node_counts": {"Person": 100},
            "edge_counts": {"KNOWS": 200},
            "total_nodes": 100,
            "total_edges": 200,
            "memory_usage_bytes": 104857600,
            "memory_usage_mb": 100.0,
        })

        # Mock lock service
        mock_lock = MagicMock()
        mock_lock.get_lock_info.return_value = LockInfo(locked=False)

        # Mock settings - needs to look like a real Settings object
        mock_settings = Mock()
        mock_settings.wrapper = Mock()
        mock_settings.wrapper.instance_id = "test-instance-id"
        mock_settings.wrapper.snapshot_id = "test-snapshot-123"
        mock_settings.wrapper.mapping_id = "test-mapping-id"
        mock_settings.wrapper.owner_id = "test-owner-id"

        app = create_test_app(mock_db_service=mock_db, mock_lock_service=mock_lock)

        # Override get_app_settings dependency (this is what SettingsDep uses)
        app.dependency_overrides[get_app_settings] = lambda: mock_settings

        return app

    @pytest.mark.unit
    def test_health_endpoint_when_healthy(self, app_with_mocks: FastAPI):
        """Test /health returns 200 - liveness probe always succeeds if process is running.

        Note: /health is a Kubernetes liveness probe that checks if the process is
        alive, NOT if the database is ready. It always returns 200 unless the
        process itself is dead.
        """
        client = TestClient(app_with_mocks)
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data  # ISO 8601 timestamp

    @pytest.mark.unit
    def test_health_endpoint_always_healthy(self, app_with_mocks: FastAPI):
        """Test /health returns 200 even when database not initialized.

        Liveness probes should only fail if the process is dead, not if the
        database isn't ready. Database readiness is checked by /ready.
        """
        # Override to not initialized - health should still return 200
        app_with_mocks.state.db_service.is_initialized = False

        client = TestClient(app_with_mocks)
        response = client.get("/health")

        # Liveness probe should still succeed - process is alive
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    @pytest.mark.unit
    def test_ready_endpoint_when_ready(self, app_with_mocks: FastAPI):
        """Test /ready returns 200 when database is ready."""
        client = TestClient(app_with_mocks)
        response = client.get("/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data

    @pytest.mark.unit
    def test_ready_endpoint_when_not_ready(self, app_with_mocks: FastAPI):
        """Test /ready returns 503 when database not ready."""
        # Override to not ready
        app_with_mocks.state.db_service.is_ready = False

        client = TestClient(app_with_mocks)
        response = client.get("/ready")

        assert response.status_code == 503
        # FastAPI returns error detail in 'detail' field for HTTPException
        data = response.json()
        assert "detail" in data

    @pytest.mark.unit
    def test_status_endpoint(self, app_with_mocks: FastAPI):
        """Test /status returns detailed information.

        Note: Response is flat (not wrapped in 'data' field) matching the
        actual implementation and Ryugraph consistency.
        """
        client = TestClient(app_with_mocks)
        response = client.get("/status")

        assert response.status_code == 200
        data = response.json()
        # Flat response structure - no 'data' wrapper
        assert "status" in data
        assert data["status"] == "running"
        assert "instance_id" in data
        assert data["instance_id"] == "test-instance-id"
        assert "uptime_seconds" in data
        assert "memory_usage_bytes" in data
        assert "lock" in data

    @pytest.mark.unit
    def test_status_includes_graph_stats(self, app_with_mocks: FastAPI):
        """Test /status includes graph statistics.

        Note: Stats are at the top level (node_count, edge_count, node_tables,
        edge_tables), not nested in a 'graph_stats' object.
        """
        client = TestClient(app_with_mocks)
        response = client.get("/status")

        data = response.json()
        # Stats are at top level, not in nested graph_stats
        assert "node_count" in data
        assert "edge_count" in data
        assert "node_tables" in data
        assert "edge_tables" in data
        assert data["node_count"] == 100
        assert data["edge_count"] == 200


class TestQueryEndpoints:
    """Integration tests for query endpoints."""

    @pytest.fixture
    def app_with_mocks(self) -> FastAPI:
        """Create app with mocked database service."""
        from wrapper.services.database import DatabaseService

        # Mock database service
        mock_db = MagicMock(spec=DatabaseService)
        mock_db.is_initialized = True
        mock_db.is_ready = True
        mock_db.execute_query = AsyncMock(return_value={
            "columns": ["name", "age"],
            "rows": [["Alice", 30], ["Bob", 25]],
            "row_count": 2,
            "execution_time_ms": 10.5,
        })

        # Mock control plane client
        mock_cp = MagicMock()
        mock_cp.record_activity = AsyncMock()

        app = create_test_app(mock_db_service=mock_db, mock_cp_client=mock_cp)

        return app

    @pytest.mark.unit
    def test_query_endpoint_success(self, app_with_mocks: FastAPI):
        """Test successful query execution.

        Note: Response is flat (not wrapped in 'data' field) matching the
        actual implementation and Ryugraph consistency.
        """
        client = TestClient(app_with_mocks)
        response = client.post(
            "/query",
            json={
                "cypher": "MATCH (n:Person) RETURN n.name, n.age",
                "parameters": {},
            },
        )

        assert response.status_code == 200
        data = response.json()
        # Flat response structure - no 'data' wrapper
        assert data["columns"] == ["name", "age"]
        assert data["row_count"] == 2
        assert data["execution_time_ms"] == 10
        assert len(data["rows"]) == 2

    @pytest.mark.unit
    def test_query_with_parameters(self, app_with_mocks: FastAPI):
        """Test query execution with parameters."""
        client = TestClient(app_with_mocks)
        response = client.post(
            "/query",
            json={
                "cypher": "MATCH (n:Person {name: $name}) RETURN n.name",
                "parameters": {"name": "Alice"},
            },
        )

        assert response.status_code == 200
        # Verify the mock was called with parameters
        app_with_mocks.state.db_service.execute_query.assert_called()

    @pytest.mark.unit
    def test_query_validation_missing_cypher(self, app_with_mocks: FastAPI):
        """Test query validation fails when cypher is missing."""
        client = TestClient(app_with_mocks)
        response = client.post(
            "/query",
            json={"parameters": {}},  # Missing cypher
        )

        assert response.status_code == 422  # Validation error

    @pytest.mark.unit
    def test_query_validation_empty_cypher(self, app_with_mocks: FastAPI):
        """Test query validation fails when cypher is empty."""
        client = TestClient(app_with_mocks)
        response = client.post(
            "/query",
            json={"cypher": ""},  # Empty string
        )

        assert response.status_code == 422  # Validation error

    @pytest.mark.unit
    def test_query_with_timeout(self, app_with_mocks: FastAPI):
        """Test query execution with custom timeout."""
        client = TestClient(app_with_mocks)
        response = client.post(
            "/query",
            json={
                "cypher": "MATCH (n) RETURN n",
                "timeout_ms": 5000,
            },
        )

        assert response.status_code == 200
        # Verify timeout was passed to database service
        call_kwargs = app_with_mocks.state.db_service.execute_query.call_args[1]
        assert call_kwargs["timeout_ms"] == 5000


class TestDatabaseNotInitialized:
    """Integration tests for when database is not initialized."""

    @pytest.fixture
    def app_with_uninitialized_db(self) -> FastAPI:
        """Create app with uninitialized database."""
        from wrapper.exceptions import DatabaseNotInitializedError
        from wrapper.services.database import DatabaseService

        # Mock database service as not initialized
        mock_db = MagicMock(spec=DatabaseService)
        mock_db.is_initialized = False
        mock_db.is_ready = False
        mock_db.execute_query = AsyncMock(side_effect=DatabaseNotInitializedError())

        app = create_test_app(mock_db_service=mock_db)

        return app

    @pytest.mark.unit
    def test_query_fails_when_db_not_initialized(self, app_with_uninitialized_db: FastAPI):
        """Test query returns 503 when database not initialized."""
        client = TestClient(app_with_uninitialized_db)
        response = client.post(
            "/query",
            json={"cypher": "MATCH (n) RETURN n"},
        )

        assert response.status_code == 503
        data = response.json()
        # Error format: {"error": {"code": "...", "message": "...", "details": {...}}}
        assert "error" in data
        assert data["error"]["code"] == "DATABASE_NOT_INITIALIZED"


class TestErrorHandling:
    """Integration tests for error handling."""

    @pytest.fixture
    def app_with_error_db(self) -> FastAPI:
        """Create app with database that raises errors."""
        from wrapper.exceptions import QuerySyntaxError, QueryTimeoutError
        from wrapper.services.database import DatabaseService

        # Mock database service
        mock_db = MagicMock(spec=DatabaseService)
        mock_db.is_initialized = True
        mock_db.is_ready = True

        # Different errors for different queries
        async def mock_execute(*args, **kwargs):
            query = kwargs.get("query", args[0] if args else "")
            if "INVALID" in query:
                raise QuerySyntaxError("Invalid Cypher syntax", query=query)
            elif "SLOW" in query:
                raise QueryTimeoutError(timeout_ms=1000, elapsed_ms=1500)
            else:
                return {
                    "columns": ["result"],
                    "rows": [["ok"]],
                    "row_count": 1,
                    "execution_time_ms": 5.0,
                }

        mock_db.execute_query = mock_execute

        app = create_test_app(mock_db_service=mock_db)

        return app

    @pytest.mark.unit
    def test_query_syntax_error_returns_400(self, app_with_error_db: FastAPI):
        """Test query with syntax error returns 400."""
        client = TestClient(app_with_error_db)
        response = client.post(
            "/query",
            json={"cypher": "INVALID SYNTAX"},
        )

        assert response.status_code == 400
        data = response.json()
        # Error format: {"error": {"code": "...", "message": "...", "details": {...}}}
        assert "error" in data
        assert data["error"]["code"] == "QUERY_SYNTAX_ERROR"

    @pytest.mark.unit
    def test_query_timeout_returns_408(self, app_with_error_db: FastAPI):
        """Test query timeout returns 408."""
        client = TestClient(app_with_error_db)
        response = client.post(
            "/query",
            json={"cypher": "SLOW QUERY"},
        )

        assert response.status_code == 408
        data = response.json()
        # Error format: {"error": {"code": "...", "message": "...", "details": {...}}}
        assert "error" in data
        assert data["error"]["code"] == "QUERY_TIMEOUT"
