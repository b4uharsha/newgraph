"""Integration tests for the Ryugraph Wrapper API.

These tests use mocked external services (Control Plane, GCS) but test
the full request/response flow through the FastAPI application.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from wrapper.models.lock import LockInfo


def create_test_app() -> FastAPI:
    """Create a FastAPI app without lifespan for testing.

    This bypasses the production lifespan which tries to connect to
    Control Plane and load data. Tests set up their own mocked state.
    """
    from fastapi.middleware.cors import CORSMiddleware

    from wrapper.routers import algo, health, lock, networkx, query, schema

    @asynccontextmanager
    async def null_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        """No-op lifespan for tests."""
        yield

    app = FastAPI(
        title="Ryugraph Wrapper API (Test)",
        lifespan=null_lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(query.router)
    app.include_router(schema.router)
    app.include_router(lock.router)
    app.include_router(algo.router)
    app.include_router(networkx.router)

    @app.get("/", tags=["Root"])
    async def root() -> dict[str, str]:
        return {"name": "Ryugraph Wrapper API", "version": "1.0.0", "docs": "/docs"}

    return app


class TestHealthEndpoints:
    """Integration tests for health endpoints."""

    @pytest.fixture
    def app_with_mocks(self) -> FastAPI:
        """Create app with mocked services."""
        from wrapper.services.database import DatabaseService
        from wrapper.services.lock import LockService

        app = create_test_app()

        # Mock services
        mock_db = MagicMock(spec=DatabaseService)
        mock_db.is_initialized = True
        mock_db.is_ready = True
        mock_db.get_stats = AsyncMock(return_value={"node_count": 100, "edge_count": 500})
        mock_db.get_schema = AsyncMock(
            return_value={
                "node_tables": [],
                "edge_tables": [],
                "total_nodes": 100,
                "total_edges": 500,
            }
        )

        mock_lock = MagicMock(spec=LockService)
        mock_lock.get_lock_info.return_value = LockInfo(
            locked=False,
            holder_id=None,
            holder_username=None,
            algorithm_name=None,
            algorithm_type=None,
            acquired_at=None,
        )

        # Attach to app state
        app.state.db_service = mock_db
        app.state.lock_service = mock_lock
        app.state.algorithm_service = MagicMock()
        app.state.control_plane_client = MagicMock()

        return app

    @pytest.fixture
    def client(self, app_with_mocks: FastAPI) -> Generator[TestClient, None, None]:
        """Create test client."""
        with TestClient(app_with_mocks, raise_server_exceptions=False) as client:
            yield client

    @pytest.mark.integration
    def test_health_endpoint(self, client: TestClient) -> None:
        """Health endpoint returns 200."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    @pytest.mark.integration
    def test_ready_endpoint_when_ready(self, client: TestClient) -> None:
        """Ready endpoint returns 200 when database is ready."""
        response = client.get("/ready")

        assert response.status_code == 200

    @pytest.mark.integration
    def test_status_endpoint(self, client: TestClient) -> None:
        """Status endpoint returns detailed info."""
        response = client.get("/status")

        assert response.status_code == 200
        data = response.json()
        assert "instance_id" in data
        assert "ready" in data
        assert "lock" in data


class TestQueryEndpoint:
    """Integration tests for query endpoint."""

    @pytest.fixture
    def app_with_mocks(self) -> FastAPI:
        """Create app with mocked services."""
        from wrapper.services.database import DatabaseService

        app = create_test_app()

        mock_db = MagicMock(spec=DatabaseService)
        mock_db.is_initialized = True
        mock_db.is_ready = True
        mock_db.execute_query = AsyncMock(
            return_value={
                "columns": ["name", "age"],
                "rows": [["Alice", 30], ["Bob", 25]],
                "row_count": 2,
                "execution_time_ms": 15,
                "truncated": False,
            }
        )

        # Mock control plane with async methods
        mock_control_plane = MagicMock()
        mock_control_plane.record_activity = AsyncMock()

        app.state.db_service = mock_db
        app.state.lock_service = MagicMock()
        app.state.algorithm_service = MagicMock()
        app.state.control_plane_client = mock_control_plane

        return app

    @pytest.fixture
    def client(self, app_with_mocks: FastAPI) -> Generator[TestClient, None, None]:
        """Create test client."""
        with TestClient(app_with_mocks, raise_server_exceptions=False) as client:
            yield client

    @pytest.mark.integration
    def test_query_execution(self, client: TestClient) -> None:
        """Can execute a Cypher query."""
        response = client.post(
            "/query",
            json={"query": "MATCH (n:Person) RETURN n.name, n.age"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["columns"] == ["name", "age"]
        assert len(data["rows"]) == 2
        assert data["row_count"] == 2

    @pytest.mark.integration
    def test_query_blocks_modification(self, client: TestClient) -> None:
        """Query endpoint blocks modification queries."""
        response = client.post(
            "/query",
            json={"query": "CREATE (n:Person {name: 'Alice'})"},
        )

        assert response.status_code == 400
        assert "forbidden" in response.json()["detail"].lower()

    @pytest.mark.integration
    def test_query_with_parameters(self, client: TestClient) -> None:
        """Can execute query with parameters."""
        response = client.post(
            "/query",
            json={
                "query": "MATCH (n:Person {name: $name}) RETURN n",
                "parameters": {"name": "Alice"},
            },
        )

        assert response.status_code == 200


class TestLockEndpoint:
    """Integration tests for lock endpoint."""

    @pytest.fixture
    def app_with_mocks(self) -> FastAPI:
        """Create app with mocked services."""
        from wrapper.services.lock import LockService

        app = create_test_app()

        mock_lock = MagicMock(spec=LockService)
        mock_lock.get_lock_info.return_value = LockInfo(
            locked=True,
            holder_id="user-123",
            holder_username="alice",
            algorithm_name="pagerank",
            algorithm_type="native",
            acquired_at=datetime.now(UTC).isoformat(),
        )

        app.state.db_service = MagicMock()
        app.state.lock_service = mock_lock
        app.state.algorithm_service = MagicMock()
        app.state.control_plane_client = MagicMock()

        return app

    @pytest.fixture
    def client(self, app_with_mocks: FastAPI) -> Generator[TestClient, None, None]:
        """Create test client."""
        with TestClient(app_with_mocks, raise_server_exceptions=False) as client:
            yield client

    @pytest.mark.integration
    def test_lock_status(self, client: TestClient) -> None:
        """Can get lock status."""
        response = client.get("/lock")

        assert response.status_code == 200
        data = response.json()
        assert data["lock"]["locked"] is True
        assert data["lock"]["holder_username"] == "alice"
        assert data["lock"]["algorithm_name"] == "pagerank"


class TestSchemaEndpoint:
    """Integration tests for schema endpoint."""

    @pytest.fixture
    def app_with_mocks(self) -> FastAPI:
        """Create app with mocked services."""
        from wrapper.services.database import DatabaseService

        app = create_test_app()

        mock_db = MagicMock(spec=DatabaseService)
        mock_db.is_initialized = True
        mock_db.is_ready = True
        mock_db.get_schema = AsyncMock(
            return_value={
                "node_tables": [
                    {
                        "label": "Person",
                        "primary_key": "id",
                        "primary_key_type": "STRING",
                        "properties": {"name": "STRING", "age": "INT64"},
                        "node_count": 100,
                    }
                ],
                "edge_tables": [
                    {
                        "type": "KNOWS",
                        "from_node": "Person",
                        "to_node": "Person",
                        "properties": {},
                        "edge_count": 500,
                    }
                ],
                "total_nodes": 100,
                "total_edges": 500,
            }
        )

        app.state.db_service = mock_db
        app.state.lock_service = MagicMock()
        app.state.algorithm_service = MagicMock()
        app.state.control_plane_client = MagicMock()

        return app

    @pytest.fixture
    def client(self, app_with_mocks: FastAPI) -> Generator[TestClient, None, None]:
        """Create test client."""
        with TestClient(app_with_mocks, raise_server_exceptions=False) as client:
            yield client

    @pytest.mark.integration
    def test_get_schema(self, client: TestClient) -> None:
        """Can get graph schema."""
        response = client.get("/schema")

        assert response.status_code == 200
        data = response.json()
        assert len(data["node_tables"]) == 1
        assert data["node_tables"][0]["label"] == "Person"
        assert data["total_nodes"] == 100
        assert data["total_edges"] == 500


class TestAlgorithmEndpoints:
    """Integration tests for algorithm endpoints."""

    @pytest.fixture
    def app_with_mocks(self) -> FastAPI:
        """Create app with mocked services."""
        from wrapper.algorithms.registry import AlgorithmType
        from wrapper.models.execution import AlgorithmExecution, ExecutionStatus
        from wrapper.services.algorithm import AlgorithmService
        from wrapper.services.database import DatabaseService

        app = create_test_app()

        mock_db = MagicMock(spec=DatabaseService)
        mock_db.is_initialized = True
        mock_db.is_ready = True

        mock_algo = MagicMock(spec=AlgorithmService)
        mock_execution = AlgorithmExecution(
            execution_id="exec-123",
            algorithm_name="pagerank",
            algorithm_type=AlgorithmType.NATIVE,
            status=ExecutionStatus.COMPLETED,
            user_id="user-1",
            user_name="alice",
            node_label="Person",
            result_property="pr",
            parameters={},
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            nodes_updated=100,
            duration_ms=500,
        )
        mock_algo.execute_native = AsyncMock(return_value=mock_execution)
        mock_algo.execute_networkx = AsyncMock(return_value=mock_execution)
        mock_algo.get_execution.return_value = mock_execution

        app.state.db_service = mock_db
        app.state.lock_service = MagicMock()
        app.state.algorithm_service = mock_algo
        app.state.control_plane_client = MagicMock()

        return app

    @pytest.fixture
    def client(self, app_with_mocks: FastAPI) -> Generator[TestClient, None, None]:
        """Create test client."""
        with TestClient(app_with_mocks, raise_server_exceptions=False) as client:
            yield client

    @pytest.mark.integration
    def test_list_native_algorithms(self, client: TestClient) -> None:
        """Can list native algorithms."""
        response = client.get("/algo/algorithms")

        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] > 0
        names = [a["name"] for a in data["algorithms"]]
        assert "pagerank" in names

    @pytest.mark.integration
    def test_get_native_algorithm_info(self, client: TestClient) -> None:
        """Can get native algorithm info."""
        response = client.get("/algo/algorithms/pagerank")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "pagerank"
        assert data["type"] == "native"

    @pytest.mark.integration
    def test_list_networkx_algorithms(self, client: TestClient) -> None:
        """Can list NetworkX algorithms."""
        response = client.get("/networkx/algorithms")

        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] > 0

    @pytest.mark.integration
    def test_filter_networkx_by_category(self, client: TestClient) -> None:
        """Can filter NetworkX algorithms by category."""
        response = client.get("/networkx/algorithms?category=centrality")

        assert response.status_code == 200
        data = response.json()
        for algo in data["algorithms"]:
            assert algo["category"] == "centrality"

    @pytest.mark.integration
    def test_search_networkx_algorithms(self, client: TestClient) -> None:
        """Can search NetworkX algorithms."""
        response = client.get("/networkx/algorithms?search=pagerank")

        assert response.status_code == 200
        data = response.json()
        assert any("pagerank" in a["name"].lower() for a in data["algorithms"])


class TestOpenAPI:
    """Tests for OpenAPI documentation."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create app."""
        app = create_test_app()
        app.state.db_service = MagicMock()
        app.state.lock_service = MagicMock()
        app.state.algorithm_service = MagicMock()
        app.state.control_plane_client = MagicMock()
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> Generator[TestClient, None, None]:
        """Create test client."""
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client

    @pytest.mark.integration
    def test_openapi_available(self, client: TestClient) -> None:
        """OpenAPI schema is available."""
        response = client.get("/openapi.json")

        assert response.status_code == 200
        data = response.json()
        assert "paths" in data
        assert "/health" in data["paths"]
        assert "/query" in data["paths"]

    @pytest.mark.integration
    def test_docs_available(self, client: TestClient) -> None:
        """Swagger docs are available."""
        response = client.get("/docs")

        assert response.status_code == 200

    @pytest.mark.integration
    def test_root_endpoint(self, client: TestClient) -> None:
        """Root endpoint returns API info."""
        response = client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data
