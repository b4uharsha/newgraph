"""Unit test fixtures with mocks.

This conftest provides mock fixtures for fast, isolated unit tests.
All mocks are function-scoped for proper test isolation.

Timeout: 10 seconds per test (unit tests should be fast).
"""

from __future__ import annotations

from collections.abc import Generator
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

import pytest

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

# Unit test timeout: 30 seconds (most tests complete in <1s, but some need more)
pytestmark = pytest.mark.timeout(30)


# =============================================================================
# Mock Ryugraph Fixtures
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


# =============================================================================
# Mock Service Fixtures
# =============================================================================


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
