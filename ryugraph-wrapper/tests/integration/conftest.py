"""Integration test fixtures with mocked Control Plane.

This module provides fixtures that mock Control Plane HTTP responses,
enabling integration testing of the wrapper's ControlPlaneClient without
requiring the actual control plane or its dependencies.

Architecture:
    Wrapper Client → httpx → respx mock → Mocked responses
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import pytest_asyncio
import respx

if TYPE_CHECKING:
    from fastapi import FastAPI


# =============================================================================
# Test Data Constants
# =============================================================================

TEST_INSTANCE_ID = 123
TEST_SNAPSHOT_ID = 456
TEST_MAPPING_ID = 789
TEST_MAPPING_VERSION = 1
TEST_INTERNAL_API_KEY = "test-internal-api-key"
TEST_CONTROL_PLANE_URL = "http://test-control-plane"


# =============================================================================
# Mocked Control Plane Fixtures
# =============================================================================


@pytest.fixture(scope="function")
def mock_control_plane_responses() -> dict[str, Any]:
    """Provide standard mock responses from Control Plane."""
    return {
        "instance": {
            "id": TEST_INSTANCE_ID,
            "snapshot_id": TEST_SNAPSHOT_ID,
            "name": "Integration Test Instance",
            "status": "pending",
            "owner_username": "test.user",
            "instance_url": None,
            "pod_name": None,
            "pod_ip": None,
            "error_code": None,
            "error_message": None,
            "stack_trace": None,
            "memory_usage_bytes": None,
            "disk_usage_bytes": None,
            "last_activity_at": None,
            "created_at": "2024-01-01T00:00:00Z",
        },
        "mapping": {
            "snapshot_id": TEST_SNAPSHOT_ID,
            "mapping_id": TEST_MAPPING_ID,
            "mapping_version": TEST_MAPPING_VERSION,
            "gcs_path": "gs://test-bucket/test.user/1/1/",
            "node_definitions": [
                {
                    "label": "Customer",
                    "sql": "SELECT id, name, city FROM customers",
                    "primary_key": {"name": "id", "type": "STRING"},
                    "properties": [
                        {"name": "name", "type": "STRING"},
                        {"name": "city", "type": "STRING"},
                    ],
                },
                {
                    "label": "Product",
                    "sql": "SELECT id, name, price FROM products",
                    "primary_key": {"name": "id", "type": "STRING"},
                    "properties": [
                        {"name": "name", "type": "STRING"},
                        {"name": "price", "type": "DOUBLE"},
                    ],
                },
            ],
            "edge_definitions": [
                {
                    "type": "PURCHASED",
                    "sql": "SELECT customer_id, product_id, amount FROM purchases",
                    "from_node": "Customer",
                    "to_node": "Product",
                    "from_key": "customer_id",
                    "to_key": "product_id",
                    "properties": [{"name": "amount", "type": "DOUBLE"}],
                },
            ],
        },
    }


@pytest.fixture(scope="function")
def seeded_control_plane(mock_control_plane_responses: dict[str, Any]) -> dict[str, Any]:
    """Provide seeded test data IDs for wrapper integration tests.

    Returns:
        Dictionary with test data IDs
    """
    return {
        "mapping_id": TEST_MAPPING_ID,
        "snapshot_id": TEST_SNAPSHOT_ID,
        "instance_id": TEST_INSTANCE_ID,
    }


@pytest.fixture(scope="function")
def control_plane_mock(
    mock_control_plane_responses: dict[str, Any],
) -> Generator[respx.MockRouter, None, None]:
    """Set up respx mock for Control Plane API.

    This fixture mocks all the internal API endpoints that the wrapper's
    ControlPlaneClient calls.
    """
    instance_data = mock_control_plane_responses["instance"].copy()

    with respx.mock(assert_all_called=False) as mock:
        # Mock GCP metadata server (token fetching)
        mock.get(url__startswith="http://metadata.google.internal/").mock(
            return_value=httpx.Response(404)
        )

        # Mock instance status update (PATCH /api/internal/instances/{id}/status)
        def update_status_handler(request: httpx.Request) -> httpx.Response:
            data = request.content
            import json

            body = json.loads(data)
            # Update instance data with request values
            instance_data.update({
                "status": body.get("status", instance_data["status"]),
                "pod_name": body.get("pod_name", instance_data["pod_name"]),
                "pod_ip": body.get("pod_ip", instance_data["pod_ip"]),
                "instance_url": body.get("instance_url", instance_data["instance_url"]),
                "error_code": body.get("error_code", instance_data["error_code"]),
                "error_message": body.get("error_message", instance_data["error_message"]),
                "stack_trace": body.get("stack_trace", instance_data["stack_trace"]),
            })
            return httpx.Response(200, json={"data": instance_data})

        mock.patch(f"{TEST_CONTROL_PLANE_URL}/api/internal/instances/{TEST_INSTANCE_ID}/status").mock(
            side_effect=update_status_handler
        )

        # Mock get instance (GET /api/instances/{id})
        def get_instance_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": instance_data})

        mock.get(f"{TEST_CONTROL_PLANE_URL}/api/instances/{TEST_INSTANCE_ID}").mock(
            side_effect=get_instance_handler
        )

        # Mock progress update (PUT /api/internal/instances/{id}/progress)
        mock.put(f"{TEST_CONTROL_PLANE_URL}/api/internal/instances/{TEST_INSTANCE_ID}/progress").mock(
            return_value=httpx.Response(200, json={"data": instance_data})
        )

        # Mock metrics update (PUT /api/internal/instances/{id}/metrics)
        def update_metrics_handler(request: httpx.Request) -> httpx.Response:
            import json

            body = json.loads(request.content)
            instance_data.update({
                "memory_usage_bytes": body.get("memory_usage_bytes"),
                "disk_usage_bytes": body.get("disk_usage_bytes"),
            })
            return httpx.Response(200, json={"data": instance_data})

        mock.put(f"{TEST_CONTROL_PLANE_URL}/api/internal/instances/{TEST_INSTANCE_ID}/metrics").mock(
            side_effect=update_metrics_handler
        )

        # Mock activity recording (POST /api/internal/instances/{id}/activity)
        mock.post(f"{TEST_CONTROL_PLANE_URL}/api/internal/instances/{TEST_INSTANCE_ID}/activity").mock(
            return_value=httpx.Response(200, json={"data": {"recorded": True}})
        )

        # Mock get mapping (GET /api/internal/instances/{id}/mapping)
        # Note: This endpoint returns InstanceMappingResponse directly, not wrapped in {"data": ...}
        mock.get(f"{TEST_CONTROL_PLANE_URL}/api/internal/instances/{TEST_INSTANCE_ID}/mapping").mock(
            return_value=httpx.Response(
                200, json=mock_control_plane_responses["mapping"]
            )
        )

        yield mock


# =============================================================================
# Wrapper Client Fixtures (using mocked Control Plane)
# =============================================================================


@pytest_asyncio.fixture(scope="function")
async def wrapper_control_plane_client(
    control_plane_mock: respx.MockRouter,
    seeded_control_plane: dict[str, Any],
) -> AsyncGenerator[Any, None]:
    """Create a ControlPlaneClient that uses mocked HTTP responses.

    This creates the wrapper's ControlPlaneClient and configures it to
    make real HTTP calls that are intercepted by respx.
    """
    from wrapper.clients.control_plane import ControlPlaneClient

    instance_id = str(seeded_control_plane["instance_id"])

    # Create client with test configuration
    client = ControlPlaneClient(
        base_url=TEST_CONTROL_PLANE_URL,
        instance_id=instance_id,
        timeout=30.0,
        internal_api_key=TEST_INTERNAL_API_KEY,
    )

    yield client

    # Cleanup
    await client.close()


@pytest_asyncio.fixture(scope="function")
async def control_plane_http_client(
    control_plane_mock: respx.MockRouter,
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Async HTTP client for direct Control Plane API calls in tests."""
    async with httpx.AsyncClient(base_url=TEST_CONTROL_PLANE_URL) as client:
        yield client


# =============================================================================
# Wrapper App Fixtures
# =============================================================================


@pytest.fixture(scope="function")
def integration_test_env(
    monkeypatch: pytest.MonkeyPatch,
    seeded_control_plane: dict[str, Any],
) -> dict[str, str]:
    """Set environment variables for wrapper integration tests."""
    instance_id = str(seeded_control_plane["instance_id"])
    snapshot_id = str(seeded_control_plane["snapshot_id"])
    mapping_id = str(seeded_control_plane["mapping_id"])

    env_vars = {
        "WRAPPER_INSTANCE_ID": instance_id,
        "WRAPPER_SNAPSHOT_ID": snapshot_id,
        "WRAPPER_MAPPING_ID": mapping_id,
        "WRAPPER_OWNER_ID": "test-owner-id",
        "WRAPPER_OWNER_USERNAME": "test.user",
        "WRAPPER_CONTROL_PLANE_URL": TEST_CONTROL_PLANE_URL,
        "WRAPPER_GCS_BASE_PATH": "gs://test-bucket/test.user/1/1/",
        "WRAPPER_POD_NAME": "test-wrapper-pod",
        "WRAPPER_POD_IP": "10.0.0.99",
        "RYUGRAPH_DATABASE_PATH": "/tmp/test_db",
        "RYUGRAPH_BUFFER_POOL_SIZE": "134217728",
        "RYUGRAPH_MAX_THREADS": "4",
        "LOG_LEVEL": "DEBUG",
        "LOG_FORMAT": "console",
        "ENVIRONMENT": "test",
    }

    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)

    return env_vars


@pytest.fixture(scope="function")
def wrapper_app_with_mocked_services(
    integration_test_env: dict[str, str],
) -> FastAPI:
    """Create wrapper app with mocked database/algorithm services.

    This creates the wrapper app with all services mocked for testing
    API endpoints without requiring actual database or Control Plane.
    """

    from wrapper.main import create_app
    from wrapper.models.lock import LockInfo
    from wrapper.services.algorithm import AlgorithmService
    from wrapper.services.database import DatabaseService
    from wrapper.services.lock import LockService

    app = create_app()

    # Mock database service
    mock_db = MagicMock(spec=DatabaseService)
    mock_db.is_initialized = True
    mock_db.is_ready = True
    mock_db.get_stats = AsyncMock(return_value={"node_count": 1000, "edge_count": 5000})
    mock_db.get_schema = AsyncMock(
        return_value={
            "node_tables": [
                {"label": "Customer", "node_count": 1000},
                {"label": "Product", "node_count": 500},
            ],
            "edge_tables": [{"type": "PURCHASED", "edge_count": 5000}],
            "total_nodes": 1500,
            "total_edges": 5000,
        }
    )
    mock_db.execute_query = AsyncMock(
        return_value={
            "columns": ["id", "name"],
            "rows": [["c1", "Alice"], ["c2", "Bob"]],
            "row_count": 2,
            "execution_time_ms": 10,
            "truncated": False,
        }
    )

    # Mock lock service
    mock_lock = MagicMock(spec=LockService)
    mock_lock.get_lock_info.return_value = LockInfo(
        locked=False,
        holder_id=None,
        holder_username=None,
        algorithm_name=None,
        algorithm_type=None,
        acquired_at=None,
    )

    # Mock algorithm service
    mock_algo = MagicMock(spec=AlgorithmService)

    # Mock control plane client
    mock_cp = MagicMock()
    mock_cp.record_activity = AsyncMock()

    # Attach services to app state
    app.state.db_service = mock_db
    app.state.lock_service = mock_lock
    app.state.algorithm_service = mock_algo
    app.state.control_plane_client = mock_cp

    return app


@pytest.fixture(scope="function")
def integration_client(wrapper_app_with_mocked_services: FastAPI) -> Generator[Any, None, None]:
    """Create test client for wrapper with mocked services."""
    from fastapi.testclient import TestClient

    with TestClient(wrapper_app_with_mocked_services, raise_server_exceptions=False) as client:
        yield client
