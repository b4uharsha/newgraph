"""Pytest configuration and fixtures for FalkorDB wrapper unit tests."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from graph_olap_schemas import (
    EdgeDefinition,
    InstanceMappingResponse,
    NodeDefinition,
    PrimaryKeyDefinition,
    PropertyDefinition,
)

# Mock redislite.async_falkordb_client module for unit tests
# This allows us to test DatabaseService without requiring FalkorDBLite to be installed
if "redislite" not in sys.modules:
    sys.modules["redislite"] = MagicMock()
    sys.modules["redislite.async_falkordb_client"] = MagicMock()


@pytest.fixture
def sample_mapping() -> InstanceMappingResponse:
    """Create a sample mapping for testing."""
    return InstanceMappingResponse(
        mapping_id="test-mapping-123",
        version=1,
        node_definitions=[
            NodeDefinition(
                label="Person",
                sql="SELECT person_id, name, age FROM people",
                primary_key=PrimaryKeyDefinition(name="person_id", type="STRING"),
                properties=[
                    PropertyDefinition(name="name", type="STRING"),
                    PropertyDefinition(name="age", type="INT64"),
                ],
            ),
            NodeDefinition(
                label="Company",
                sql="SELECT company_id, name FROM companies",
                primary_key=PrimaryKeyDefinition(name="company_id", type="STRING"),
                properties=[
                    PropertyDefinition(name="name", type="STRING"),
                ],
            ),
        ],
        edge_definitions=[
            EdgeDefinition(
                type="KNOWS",
                from_node="Person",
                to_node="Person",
                sql="SELECT from_id, to_id, since FROM relationships",
                from_key="from_id",
                to_key="to_id",
                properties=[
                    PropertyDefinition(name="since", type="INT64"),
                ],
            ),
            EdgeDefinition(
                type="WORKS_AT",
                from_node="Person",
                to_node="Company",
                sql="SELECT person_id, company_id FROM employment",
                from_key="person_id",
                to_key="company_id",
                properties=[],
            ),
        ],
    )


@pytest.fixture
def mock_falkordb_result():
    """Create a mock FalkorDB query result."""
    result = Mock()
    result.header = ["name", "age"]
    result.result_set = [["Alice", 30], ["Bob", 25]]
    result.run_time_ms = 5.2
    return result


@pytest.fixture
def mock_falkordb_graph(mock_falkordb_result):
    """Create a mock async FalkorDB graph object."""
    graph = Mock()
    # Async methods return coroutines
    graph.query = AsyncMock(return_value=mock_falkordb_result)
    graph.labels = AsyncMock(return_value=["Person", "Company"])
    graph.relationship_types = AsyncMock(return_value=["KNOWS", "WORKS_AT"])
    return graph


@pytest.fixture
def mock_falkordb_client(mock_falkordb_graph):
    """Create a mock async FalkorDB client."""
    client = Mock()
    client.select_graph = Mock(return_value=mock_falkordb_graph)
    client.close = AsyncMock()
    return client


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    """Create a temporary database path."""
    db_path = tmp_path / "test_db"
    db_path.mkdir(parents=True, exist_ok=True)
    return db_path


# =============================================================================
# Mock Service Fixtures
# =============================================================================


@pytest.fixture
def mock_db_service(mock_falkordb_result):
    """Create a mock DatabaseService for testing routers."""
    service = MagicMock()
    service.is_ready = True
    service.graph_name = "test_graph"

    # Async methods
    service.query = AsyncMock(return_value=mock_falkordb_result)
    service.get_schema = AsyncMock(
        return_value={
            "node_labels": ["Person", "Company"],
            "edge_types": ["KNOWS", "WORKS_AT"],
            "node_properties": {"Person": ["name", "age"], "Company": ["name"]},
            "edge_properties": {"KNOWS": ["since"], "WORKS_AT": []},
            "node_counts": {"Person": 100, "Company": 50},
            "edge_counts": {"KNOWS": 200, "WORKS_AT": 100},
        }
    )
    service.get_stats = AsyncMock(
        return_value={"total_nodes": 150, "total_edges": 300}
    )
    service.initialize = AsyncMock()
    service.close = AsyncMock()
    service.create_schema = AsyncMock()
    service.load_data = AsyncMock()
    service.mark_ready = MagicMock()

    return service


@pytest.fixture
def mock_lock_service():
    """Create a mock LockService for testing routers."""
    from wrapper.models.lock import LockInfo

    service = MagicMock()

    # Default: unlocked state
    service.is_locked.return_value = False
    service.get_status.return_value = None
    service.get_lock_info.return_value = LockInfo(locked=False)

    # Async methods
    service.acquire = AsyncMock(return_value=(True, "exec-12345", None))
    service.release = AsyncMock(return_value=True)
    service.force_release = AsyncMock(return_value=None)
    service.acquire_or_raise = AsyncMock(return_value="exec-12345")

    return service


@pytest.fixture
def mock_lock_service_locked(sample_mapping):
    """Create a mock LockService that is in locked state."""
    from datetime import UTC, datetime

    from wrapper.models.lock import LockInfo, LockState

    service = MagicMock()

    lock_state = LockState(
        execution_id="exec-existing",
        holder_id="other-user",
        holder_username="otheruser",
        algorithm_name="pagerank",
        algorithm_type="cypher",
        acquired_at=datetime.now(UTC),
    )

    service.is_locked.return_value = True
    service.get_status.return_value = lock_state
    service.get_lock_info.return_value = LockInfo.from_lock_state(lock_state)

    # Async methods - acquire fails because locked
    service.acquire = AsyncMock(return_value=(False, "", lock_state))
    service.release = AsyncMock(return_value=False)
    service.force_release = AsyncMock(return_value=lock_state)

    return service


@pytest.fixture
def mock_control_plane_client():
    """Create a mock ControlPlaneClient for testing."""
    client = MagicMock()

    # Async methods
    client.update_status = AsyncMock()
    client.update_progress = AsyncMock()
    client.update_metrics = AsyncMock()
    client.record_activity = AsyncMock()
    client.get_mapping = AsyncMock()
    client.close = AsyncMock()

    return client


@pytest.fixture
def mock_gcs_client():
    """Create a mock GCSClient for testing."""
    client = MagicMock()

    client.download_file = AsyncMock()
    client.list_files = AsyncMock(return_value=[])
    client.download_snapshot_data = AsyncMock(return_value=[])

    return client


# =============================================================================
# FastAPI Test App Fixtures
# =============================================================================


@pytest.fixture
def test_app_with_services(mock_db_service, mock_lock_service, mock_control_plane_client):
    """Create a FastAPI app with all mock services injected."""
    from fastapi import FastAPI

    from wrapper.routers import health, lock, query, schema

    app = FastAPI()

    # Register routers
    app.include_router(health.router)
    app.include_router(query.router)
    app.include_router(schema.router)
    app.include_router(lock.router)

    # Inject mock services
    app.state.db_service = mock_db_service
    app.state.lock_service = mock_lock_service
    app.state.control_plane_client = mock_control_plane_client

    return app


@pytest.fixture
def test_client(test_app_with_services):
    """Create a TestClient for the test app."""
    from starlette.testclient import TestClient

    return TestClient(test_app_with_services)
