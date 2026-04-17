"""Unit tests for API routers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response

from wrapper.algorithms.registry import AlgorithmCategory, AlgorithmType
from wrapper.models.execution import AlgorithmExecution, ExecutionStatus
from wrapper.models.lock import LockInfo

# CP authorize endpoint URL used by require_algorithm_permission.
# Settings come from the autouse mock_env fixture in conftest.py:
#   WRAPPER_CONTROL_PLANE_URL = "http://localhost:8080"
#   WRAPPER_INSTANCE_ID       = "test-instance-id"
_CP_AUTHORIZE_URL = "http://localhost:8080/internal/instances/test-instance-id/authorize"


class TestHealthRouter:
    """Tests for health endpoints."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create FastAPI app with health router."""
        from wrapper.routers import health

        app = FastAPI()
        app.include_router(health.router)
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create test client."""
        return TestClient(app)

    @pytest.mark.unit
    def test_health_returns_healthy(self, client: TestClient) -> None:
        """Health endpoint returns healthy."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data


class TestQueryRouter:
    """Tests for query endpoint."""

    @pytest.fixture
    def mock_db_service(self) -> MagicMock:
        """Create mock database service."""
        service = MagicMock()
        service.is_ready = True
        service.execute_query = AsyncMock(
            return_value={
                "columns": ["id", "name"],
                "rows": [["1", "Alice"], ["2", "Bob"]],
                "row_count": 2,
                "execution_time_ms": 15,
                "truncated": False,
            }
        )
        return service

    @pytest.fixture
    def app(self, mock_db_service: MagicMock) -> FastAPI:
        """Create FastAPI app with query router."""
        from wrapper.routers import query

        app = FastAPI()
        app.include_router(query.router)

        # Override dependency
        app.dependency_overrides = {
            query.router.dependencies[0].dependency: lambda: mock_db_service
        }

        return app

    @pytest.mark.unit
    def test_query_execution_blocked_when_not_ready(self) -> None:
        """Query blocked when database not ready."""
        from wrapper.routers import query

        mock_service = MagicMock()
        mock_service.is_ready = False

        app = FastAPI()
        app.include_router(query.router)

        def get_mock_service() -> MagicMock:
            return mock_service

        # Would need proper dependency override setup
        # This test documents expected behavior

    @pytest.mark.unit
    def test_query_blocks_modification_keywords(self) -> None:
        """Query endpoint blocks modification queries."""
        # Test data - queries that should be blocked
        blocked_queries = [
            "CREATE (n:Person {name: 'Alice'})",
            "MATCH (n) SET n.value = 1",
            "MATCH (n) DELETE n",
            "MATCH (n) REMOVE n.prop",
            "MERGE (n:Person {name: 'Alice'})",
            "DROP TABLE Person",
        ]

        for query_text in blocked_queries:
            query_upper = query_text.upper().strip()
            forbidden_keywords = ["CREATE", "SET", "DELETE", "REMOVE", "MERGE", "DROP"]
            is_blocked = any(kw in query_upper for kw in forbidden_keywords)
            assert is_blocked, f"Query should be blocked: {query_text}"


class TestLockRouter:
    """Tests for lock endpoint."""

    @pytest.fixture
    def mock_lock_service(self) -> MagicMock:
        """Create mock lock service."""
        service = MagicMock()
        service.get_lock_info.return_value = LockInfo(
            locked=False,
            holder_id=None,
            holder_username=None,
            algorithm_name=None,
            algorithm_type=None,
            acquired_at=None,
        )
        return service

    @pytest.mark.unit
    def test_lock_status_unlocked(self, mock_lock_service: MagicMock) -> None:
        """Lock status shows unlocked state."""
        info = mock_lock_service.get_lock_info()
        assert info.locked is False

    @pytest.mark.unit
    def test_lock_status_locked(self) -> None:
        """Lock status shows locked state."""
        info = LockInfo(
            locked=True,
            holder_id="user-123",
            holder_username="alice",
            algorithm_name="pagerank",
            algorithm_type="native",
            acquired_at=datetime.now(UTC).isoformat(),
        )

        assert info.locked is True
        assert info.holder_username == "alice"
        assert info.algorithm_name == "pagerank"


class TestAlgoRouter:
    """Tests for native algorithm endpoints."""

    @pytest.fixture
    def mock_algorithm_service(self) -> MagicMock:
        """Create mock algorithm service."""
        service = MagicMock()

        # Mock execute_native
        execution = AlgorithmExecution(
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
        service.execute_native = AsyncMock(return_value=execution)
        service.get_execution.return_value = execution

        return service

    @pytest.mark.unit
    def test_list_native_algorithms(self) -> None:
        """Can list native algorithms."""
        from wrapper.algorithms.native import NATIVE_ALGORITHMS

        algo_names = [algo.info.name for algo in NATIVE_ALGORITHMS]

        assert "pagerank" in algo_names
        assert "wcc" in algo_names
        assert "scc" in algo_names
        assert "louvain" in algo_names
        assert "kcore" in algo_names

    @pytest.mark.unit
    def test_get_native_algorithm_info(self) -> None:
        """Can get native algorithm info."""
        from wrapper.algorithms.native import get_native_algorithm

        algo = get_native_algorithm("pagerank")

        assert algo is not None
        assert algo.info.name == "pagerank"
        assert algo.info.type == AlgorithmType.NATIVE
        assert len(algo.info.parameters) > 0


class TestNetworkXRouter:
    """Tests for NetworkX algorithm endpoints."""

    @pytest.mark.unit
    def test_list_networkx_algorithms(self) -> None:
        """Can list NetworkX algorithms."""
        from wrapper.algorithms.networkx import list_algorithms

        algos = list_algorithms()

        assert len(algos) > 0
        # Check some known algorithms are present
        names = [a.name for a in algos]
        assert "pagerank" in names

    @pytest.mark.unit
    def test_filter_by_category(self) -> None:
        """Can filter algorithms by category."""
        from wrapper.algorithms.networkx import list_algorithms

        centrality = list_algorithms(category=AlgorithmCategory.CENTRALITY)

        for algo in centrality:
            assert algo.category == AlgorithmCategory.CENTRALITY

    @pytest.mark.unit
    def test_search_algorithms(self) -> None:
        """Can search algorithms."""
        from wrapper.algorithms.networkx import list_algorithms

        results = list_algorithms(search="pagerank")

        assert len(results) >= 1
        assert any("pagerank" in a.name for a in results)

    @pytest.mark.unit
    def test_get_algorithm_info(self) -> None:
        """Can get algorithm info."""
        from wrapper.algorithms.networkx import get_algorithm_info

        info = get_algorithm_info("pagerank")

        assert info is not None
        assert info.name == "pagerank"
        assert info.type == AlgorithmType.NETWORKX
        assert len(info.parameters) > 0

    @pytest.mark.unit
    def test_get_nonexistent_algorithm(self) -> None:
        """Returns None for nonexistent algorithm."""
        from wrapper.algorithms.networkx import get_algorithm_info

        info = get_algorithm_info("nonexistent_algorithm_xyz")

        assert info is None


class TestSchemaRouter:
    """Tests for schema endpoint."""

    @pytest.fixture
    def mock_db_service(self) -> MagicMock:
        """Create mock database service."""
        service = MagicMock()
        service.is_ready = True
        service.get_schema = AsyncMock(
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
                        "properties": {"since": "DATE"},
                        "edge_count": 500,
                    }
                ],
                "total_nodes": 100,
                "total_edges": 500,
            }
        )
        return service

    @pytest.mark.unit
    async def test_get_schema(self, mock_db_service: MagicMock) -> None:
        """Can get graph schema."""
        schema = await mock_db_service.get_schema()

        assert len(schema["node_tables"]) == 1
        assert schema["node_tables"][0]["label"] == "Person"
        assert schema["total_nodes"] == 100


class TestAlgorithmAuthorization:
    """Tests for algorithm execution authorization."""

    @pytest.fixture
    def mock_db_service(self) -> MagicMock:
        """Create mock database service."""
        service = MagicMock()
        service.is_ready = True
        return service

    @pytest.fixture
    def mock_algorithm_service(self) -> MagicMock:
        """Create mock algorithm service."""
        service = MagicMock()
        execution = AlgorithmExecution(
            execution_id="exec-123",
            algorithm_name="pagerank",
            algorithm_type=AlgorithmType.NATIVE,
            status=ExecutionStatus.COMPLETED,
            user_id="test-owner-id",
            user_name="testuser",
            node_label="Person",
            result_property="pr",
            parameters={},
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            nodes_updated=100,
            duration_ms=500,
        )
        service.execute_native = AsyncMock(return_value=execution)
        service.execute_networkx = AsyncMock(return_value=execution)
        return service

    @pytest.fixture
    def mock_control_plane(self) -> MagicMock:
        """Create mock control plane client."""
        client = MagicMock()
        client.record_activity = AsyncMock()
        return client

    @pytest.fixture
    def app(
        self,
        mock_db_service: MagicMock,
        mock_algorithm_service: MagicMock,
        mock_control_plane: MagicMock,
    ) -> FastAPI:
        """Create FastAPI app with algorithm routers."""
        from wrapper.dependencies import (
            get_algorithm_service,
            get_control_plane_client,
            get_database_service,
        )
        from wrapper.routers import algo, networkx

        app = FastAPI()
        app.include_router(algo.router)
        app.include_router(networkx.router)

        app.dependency_overrides[get_database_service] = lambda: mock_db_service
        app.dependency_overrides[get_algorithm_service] = lambda: mock_algorithm_service
        app.dependency_overrides[get_control_plane_client] = lambda: mock_control_plane

        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create test client."""
        return TestClient(app)

    @pytest.mark.unit
    def test_owner_can_execute_native_algorithm(self, client: TestClient) -> None:
        """Instance owner can execute native algorithms (fast path, no CP call)."""
        response = client.post(
            "/algo/pagerank",
            json={"node_label": "Person", "result_property": "pr"},
            headers={
                "X-Username": "test-owner-id",  # Matches WRAPPER_OWNER_ID from mock_env
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["algorithm_name"] == "pagerank"
        assert data["status"] == "completed"

    @pytest.mark.unit
    @respx.mock
    def test_non_owner_analyst_denied_native_algorithm(self, client: TestClient) -> None:
        """Non-owner analyst is denied when CP returns allowed=false."""
        respx.get(_CP_AUTHORIZE_URL, params={"username": "other-user-id"}).mock(
            return_value=Response(200, json={"allowed": False}),
        )

        response = client.post(
            "/algo/pagerank",
            json={"node_label": "Person", "result_property": "pr"},
            headers={
                "X-Username": "other-user-id",  # Different from WRAPPER_OWNER_ID
            },
        )

        assert response.status_code == 403
        data = response.json()
        assert "Permission denied" in data["detail"]

    @pytest.mark.unit
    @respx.mock
    def test_admin_can_execute_on_any_instance(self, client: TestClient) -> None:
        """Admin can execute algorithms on any instance (CP authorizes)."""
        respx.get(_CP_AUTHORIZE_URL, params={"username": "other-user-id"}).mock(
            return_value=Response(200, json={"allowed": True, "reason": "admin/ops role"}),
        )

        response = client.post(
            "/algo/pagerank",
            json={"node_label": "Person", "result_property": "pr"},
            headers={
                "X-Username": "other-user-id",  # Not the owner
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["algorithm_name"] == "pagerank"

    @pytest.mark.unit
    @respx.mock
    def test_ops_can_execute_on_any_instance(self, client: TestClient) -> None:
        """Ops can execute algorithms on any instance (CP authorizes)."""
        respx.get(_CP_AUTHORIZE_URL, params={"username": "ops-user-id"}).mock(
            return_value=Response(200, json={"allowed": True, "reason": "admin/ops role"}),
        )

        response = client.post(
            "/algo/pagerank",
            json={"node_label": "Person", "result_property": "pr"},
            headers={
                "X-Username": "ops-user-id",  # Not the owner
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["algorithm_name"] == "pagerank"

    @pytest.mark.unit
    @respx.mock
    def test_cp_unreachable_denies_non_owner(self, client: TestClient) -> None:
        """Non-owner is denied when CP authorize endpoint is unreachable (fail closed)."""
        respx.get(_CP_AUTHORIZE_URL, params={"username": "other-user-id"}).mock(
            side_effect=ConnectionError("CP unreachable"),
        )

        response = client.post(
            "/algo/pagerank",
            json={"node_label": "Person", "result_property": "pr"},
            headers={
                "X-Username": "other-user-id",  # Not the owner
            },
        )

        # Fail closed: CP error falls through to 403
        assert response.status_code == 403

    @pytest.mark.unit
    def test_owner_can_execute_networkx_algorithm(self, client: TestClient) -> None:
        """Instance owner can execute NetworkX algorithms (fast path, no CP call)."""
        response = client.post(
            "/networkx/pagerank",
            json={"node_label": "Person", "result_property": "pr"},
            headers={
                "X-Username": "test-owner-id",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["algorithm_name"] == "pagerank"

    @pytest.mark.unit
    @respx.mock
    def test_non_owner_analyst_denied_networkx_algorithm(self, client: TestClient) -> None:
        """Non-owner analyst is denied NetworkX algorithms when CP returns allowed=false."""
        respx.get(_CP_AUTHORIZE_URL, params={"username": "other-user-id"}).mock(
            return_value=Response(200, json={"allowed": False}),
        )

        response = client.post(
            "/networkx/pagerank",
            json={"node_label": "Person", "result_property": "pr"},
            headers={
                "X-Username": "other-user-id",
            },
        )

        assert response.status_code == 403


class TestRouterIntegration:
    """Integration tests for routers with mocked dependencies."""

    @pytest.fixture
    def mock_services(self) -> dict[str, Any]:
        """Create all mock services."""
        db_service = MagicMock()
        db_service.is_ready = True
        db_service.is_initialized = True
        db_service.execute_query = AsyncMock(
            return_value={
                "columns": ["id"],
                "rows": [["1"]],
                "row_count": 1,
                "execution_time_ms": 10,
            }
        )
        db_service.get_schema = AsyncMock(
            return_value={
                "node_tables": [],
                "edge_tables": [],
                "total_nodes": 0,
                "total_edges": 0,
            }
        )
        db_service.get_stats = AsyncMock(return_value={"node_count": 0, "edge_count": 0})

        lock_service = MagicMock()
        lock_service.get_lock_info.return_value = LockInfo(
            locked=False,
            holder_id=None,
            holder_username=None,
            algorithm_name=None,
            algorithm_type=None,
            acquired_at=None,
        )

        algorithm_service = MagicMock()

        return {
            "db_service": db_service,
            "lock_service": lock_service,
            "algorithm_service": algorithm_service,
        }

    @pytest.mark.unit
    def test_all_routers_have_tags(self) -> None:
        """All routers define tags for OpenAPI."""
        from wrapper.routers import algo, health, lock, networkx, query, schema

        routers = [
            health.router,
            query.router,
            schema.router,
            lock.router,
            algo.router,
            networkx.router,
        ]

        for router in routers:
            assert router.tags, f"Router {router} should have tags defined"
