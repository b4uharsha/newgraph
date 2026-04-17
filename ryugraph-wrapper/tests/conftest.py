"""Shared test fixtures for unit and integration tests.

This is the root conftest.py that provides:
1. Auto-marker application based on test directory
2. Shared sample data fixtures
3. Environment setup

Mock fixtures for unit tests are in tests/unit/conftest.py.
Integration fixtures are in tests/integration/conftest.py.
E2E fixtures are in tests/e2e/conftest.py.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import respx
from httpx import Response

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


# =============================================================================
# Auto-Marker Application
# =============================================================================


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Auto-apply markers based on test directory.

    This eliminates the need for manual @pytest.mark.unit decorators.
    Tests in tests/unit/ get the 'unit' marker automatically, etc.
    """
    for item in items:
        test_path = str(item.fspath)
        if "/unit/" in test_path:
            item.add_marker(pytest.mark.unit)
        elif "/integration/" in test_path:
            item.add_marker(pytest.mark.integration)
        elif "/e2e/" in test_path:
            item.add_marker(pytest.mark.e2e)


# =============================================================================
# Environment Setup
# =============================================================================


@pytest.fixture(autouse=True)
def mock_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set required environment variables for tests."""
    env_vars = {
        "WRAPPER_INSTANCE_ID": "test-instance-id",
        "WRAPPER_SNAPSHOT_ID": "test-snapshot-id",
        "WRAPPER_MAPPING_ID": "test-mapping-id",
        "WRAPPER_OWNER_ID": "test-owner-id",
        "WRAPPER_OWNER_USERNAME": "testuser",
        "WRAPPER_CONTROL_PLANE_URL": "http://localhost:8080",
        "WRAPPER_GCS_BASE_PATH": "gs://test-bucket/user/mapping/snapshot",
        "RYUGRAPH_DATABASE_PATH": "/tmp/test_db",
        "RYUGRAPH_BUFFER_POOL_SIZE": "134217728",  # 128MB for tests
        "RYUGRAPH_MAX_THREADS": "4",
        "LOG_LEVEL": "DEBUG",
        "LOG_FORMAT": "console",
        "ENVIRONMENT": "local",
    }
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)


# =============================================================================
# Sample Data Fixtures
# =============================================================================


@pytest.fixture
def sample_node_definition() -> dict[str, Any]:
    """Sample node definition."""
    return {
        "label": "Customer",
        "sql": "SELECT customer_id, name, city FROM customers",
        "primary_key": {"name": "customer_id", "type": "STRING"},
        "properties": [
            {"name": "name", "type": "STRING"},
            {"name": "city", "type": "STRING"},
        ],
    }


@pytest.fixture
def sample_edge_definition() -> dict[str, Any]:
    """Sample edge definition."""
    return {
        "type": "PURCHASED",
        "from_node": "Customer",
        "to_node": "Product",
        "sql": "SELECT customer_id, product_id, amount FROM transactions",
        "from_key": "customer_id",
        "to_key": "product_id",
        "properties": [{"name": "amount", "type": "DOUBLE"}],
    }


@pytest.fixture
def sample_mapping_definition(
    sample_node_definition: dict[str, Any],
    sample_edge_definition: dict[str, Any],
) -> dict[str, Any]:
    """Sample complete mapping definition."""
    product_node = {
        "label": "Product",
        "sql": "SELECT product_id, name, price FROM products",
        "primary_key": {"name": "product_id", "type": "STRING"},
        "properties": [
            {"name": "name", "type": "STRING"},
            {"name": "price", "type": "DOUBLE"},
        ],
    }
    return {
        "mapping_id": "test-mapping-id",
        "mapping_version": 1,
        "node_definitions": [sample_node_definition, product_node],
        "edge_definitions": [sample_edge_definition],
    }


@pytest.fixture
def sample_query_result() -> dict[str, Any]:
    """Sample query result."""
    return {
        "columns": ["customer_id", "name", "city"],
        "rows": [
            ["c1", "Alice", "New York"],
            ["c2", "Bob", "Los Angeles"],
            ["c3", "Charlie", "Chicago"],
        ],
        "row_count": 3,
        "execution_time_ms": 15,
        "truncated": False,
    }


@pytest.fixture
def sample_lock_state() -> dict[str, Any]:
    """Sample lock state."""
    return {
        "execution_id": "exec-123",
        "holder_id": "user-456",
        "holder_username": "alice",
        "algorithm_name": "pagerank",
        "algorithm_type": "networkx",
        "acquired_at": datetime.now(UTC).isoformat(),
    }


# =============================================================================
# Mock Service Fixtures
# =============================================================================


@pytest.fixture
def mock_ryugraph_database() -> MagicMock:
    """Mock Ryugraph Database object."""
    db = MagicMock()
    db.close = MagicMock()
    return db


@pytest.fixture
def mock_ryugraph_connection() -> MagicMock:
    """Mock Ryugraph Connection object."""
    conn = MagicMock()
    conn.execute = MagicMock(return_value=MagicMock(get_as_pl=MagicMock()))
    return conn


@pytest.fixture
def mock_database_service(
    mock_ryugraph_database: MagicMock,
    mock_ryugraph_connection: MagicMock,
) -> MagicMock:
    """Mock DatabaseService for unit tests."""
    from wrapper.services.database import DatabaseService

    service = MagicMock(spec=DatabaseService)
    service.is_initialized = True
    service.is_ready = True
    service._db = mock_ryugraph_database
    service._connection = mock_ryugraph_connection

    # Mock async methods
    service.initialize = AsyncMock()
    service.execute_query = AsyncMock(
        return_value={
            "columns": ["id", "name"],
            "rows": [["1", "test"]],
            "row_count": 1,
            "execution_time_ms": 10,
        }
    )
    service.get_schema = AsyncMock(
        return_value={
            "node_tables": [],
            "edge_tables": [],
            "total_nodes": 0,
            "total_edges": 0,
        }
    )
    service.get_stats = AsyncMock(return_value={"node_count": 100, "edge_count": 500})
    service.close = AsyncMock()

    return service


@pytest.fixture
def mock_lock_service() -> MagicMock:
    """Mock LockService for unit tests."""
    from wrapper.services.lock import LockService

    service = MagicMock(spec=LockService)
    service.get_status = MagicMock(return_value=None)
    service.acquire = AsyncMock(return_value=(True, "exec-123", None))
    service.release = AsyncMock(return_value=True)

    return service


@pytest.fixture
def mock_algorithm_service() -> MagicMock:
    """Mock AlgorithmService for unit tests."""
    from wrapper.services.algorithm import AlgorithmService

    service = MagicMock(spec=AlgorithmService)
    service.execute_native = AsyncMock()
    service.execute_networkx = AsyncMock()
    service.get_execution = MagicMock(return_value=None)
    service.list_executions = MagicMock(return_value=[])

    return service


@pytest.fixture
def mock_control_plane_client() -> MagicMock:
    """Mock ControlPlaneClient for unit tests."""
    from wrapper.clients.control_plane import ControlPlaneClient

    client = MagicMock(spec=ControlPlaneClient)
    client.update_status = AsyncMock()
    client.update_progress = AsyncMock()
    client.update_metrics = AsyncMock()
    client.get_mapping = AsyncMock(
        return_value={
            "mapping_id": "test-mapping-id",
            "mapping_version": 1,
            "node_definitions": [],
            "edge_definitions": [],
        }
    )
    client.record_activity = AsyncMock()
    client.report_error = AsyncMock()
    client.close = AsyncMock()

    return client


# =============================================================================
# HTTP Mocking Fixtures
# =============================================================================


@pytest.fixture
def mock_control_plane_api() -> Generator[respx.MockRouter, None, None]:
    """Mock Control Plane API with respx."""
    with respx.mock(assert_all_called=False) as respx_mock:
        # Status update endpoint
        respx_mock.patch(url__regex=r".*/api/internal/instances/.*/status").mock(
            return_value=Response(200, json={"status": "ok"})
        )

        # Progress update endpoint
        respx_mock.put(url__regex=r".*/api/internal/instances/.*/progress").mock(
            return_value=Response(200, json={"status": "ok"})
        )

        # Metrics update endpoint
        respx_mock.put(url__regex=r".*/api/internal/instances/.*/metrics").mock(
            return_value=Response(200, json={"status": "ok"})
        )

        # Get mapping endpoint
        respx_mock.get(url__regex=r".*/api/internal/instances/.*/mapping").mock(
            return_value=Response(
                200,
                json={
                    "mapping_id": "test-mapping-id",
                    "mapping_version": 1,
                    "node_definitions": [],
                    "edge_definitions": [],
                },
            )
        )

        # Activity recording endpoint
        respx_mock.post(url__regex=r".*/api/internal/instances/.*/activity").mock(
            return_value=Response(204)
        )

        # Error reporting endpoint
        respx_mock.post(url__regex=r".*/api/internal/instances/.*/errors").mock(
            return_value=Response(200, json={"status": "ok"})
        )

        yield respx_mock


# =============================================================================
# FastAPI TestClient Fixtures
# =============================================================================


@pytest.fixture
def app_with_mocks(
    mock_database_service: MagicMock,
    mock_lock_service: MagicMock,
    mock_algorithm_service: MagicMock,
    mock_control_plane_client: MagicMock,
) -> Any:
    """Create FastAPI app with mocked services."""
    from fastapi import FastAPI

    from wrapper.dependencies import (
        get_algorithm_service,
        get_control_plane_client,
        get_database_service,
        get_lock_service,
    )
    from wrapper.routers import algo, health, lock, networkx, query, schema

    app = FastAPI()

    # Override dependencies
    app.dependency_overrides[get_database_service] = lambda: mock_database_service
    app.dependency_overrides[get_lock_service] = lambda: mock_lock_service
    app.dependency_overrides[get_algorithm_service] = lambda: mock_algorithm_service
    app.dependency_overrides[get_control_plane_client] = lambda: mock_control_plane_client

    # Include routers
    app.include_router(health.router)
    app.include_router(query.router)
    app.include_router(schema.router)
    app.include_router(lock.router)
    app.include_router(algo.router)
    app.include_router(networkx.router)

    return app


@pytest.fixture
def test_client(app_with_mocks: Any) -> Generator[TestClient, None, None]:
    """Create TestClient with mocked services."""
    from fastapi.testclient import TestClient

    with TestClient(app_with_mocks) as client:
        yield client


# =============================================================================
# Testcontainers Fixtures (Integration Tests)
# =============================================================================


@pytest.fixture(scope="session")
def gcs_emulator() -> Generator[str, None, None]:
    """Start fake-gcs-server for integration tests.

    Requires Docker to be running.
    """
    pytest.importorskip("testcontainers")
    from testcontainers.core.container import DockerContainer

    container = DockerContainer("fsouza/fake-gcs-server:latest")
    container.with_exposed_ports(4443)
    container.with_command("-scheme http -port 4443")

    try:
        container.start()
        host = container.get_container_host_ip()
        port = container.get_exposed_port(4443)
        emulator_url = f"http://{host}:{port}"

        # Set environment variable for GCS client
        os.environ["STORAGE_EMULATOR_HOST"] = emulator_url

        yield emulator_url
    finally:
        container.stop()


@pytest.fixture(scope="function")
def temp_database_path(tmp_path: Any) -> str:
    """Provide temporary database path for testing.

    Note: Ryugraph requires the path to NOT exist - it creates the directory.
    We only provide the path, not the actual directory.
    """
    db_path = tmp_path / "test_ryugraph_db"
    # Don't create the directory - Ryugraph will create it
    return str(db_path)


# =============================================================================
# User Context Fixtures
# =============================================================================


@pytest.fixture
def test_user() -> dict[str, str]:
    """Test user context."""
    return {
        "user_id": "test-user-123",
        "username": "testuser",
    }


@pytest.fixture
def admin_user() -> dict[str, str]:
    """Admin user context."""
    return {
        "user_id": "admin-user-456",
        "username": "admin",
    }
