"""Integration test fixtures with mocked Control Plane for FalkorDB wrapper.

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
            "name": "FalkorDB Integration Test Instance",
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
                    "label": "Person",
                    "sql": "SELECT id, name, age FROM people",
                    "primary_key": {"name": "id", "type": "STRING"},
                    "properties": [
                        {"name": "name", "type": "STRING"},
                        {"name": "age", "type": "INT64"},
                    ],
                },
                {
                    "label": "Company",
                    "sql": "SELECT id, name FROM companies",
                    "primary_key": {"name": "id", "type": "STRING"},
                    "properties": [
                        {"name": "name", "type": "STRING"},
                    ],
                },
            ],
            "edge_definitions": [
                {
                    "type": "WORKS_AT",
                    "sql": "SELECT person_id, company_id, since FROM employment",
                    "from_node": "Person",
                    "to_node": "Company",
                    "from_key": "person_id",
                    "to_key": "company_id",
                    "properties": [{"name": "since", "type": "DATE"}],
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
    tmp_path: Any,
) -> dict[str, str]:
    """Set environment variables for wrapper integration tests."""
    instance_id = str(seeded_control_plane["instance_id"])
    snapshot_id = str(seeded_control_plane["snapshot_id"])
    mapping_id = str(seeded_control_plane["mapping_id"])

    # Use temp path for FalkorDB database
    db_path = tmp_path / "falkordb_test.db"

    env_vars = {
        "WRAPPER_INSTANCE_ID": instance_id,
        "WRAPPER_SNAPSHOT_ID": snapshot_id,
        "WRAPPER_MAPPING_ID": mapping_id,
        "WRAPPER_OWNER_ID": "test-owner-id",
        "WRAPPER_OWNER_USERNAME": "test.user",
        "WRAPPER_CONTROL_PLANE_URL": TEST_CONTROL_PLANE_URL,
        "WRAPPER_GCS_BASE_PATH": "gs://test-bucket/test.user/1/1/",
        "WRAPPER_POD_NAME": "test-falkordb-wrapper-pod",
        "WRAPPER_POD_IP": "10.0.0.100",
        "FALKORDB_DATABASE_PATH": str(db_path),
        "FALKORDB_GRAPH_NAME": "test_graph",
        "LOG_LEVEL": "DEBUG",
        "LOG_FORMAT": "human",
        "ENVIRONMENT": "test",
    }

    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)

    return env_vars


@pytest.fixture(scope="function")
def wrapper_app_with_mocked_services(
    integration_test_env: dict[str, str],
) -> FastAPI:
    """Create wrapper app with mocked database service.

    This creates the wrapper app with database service mocked for testing
    API endpoints without requiring actual FalkorDB.
    """

    from wrapper.main import app as main_app
    from wrapper.services.database import DatabaseService

    # Mock database service
    mock_db = MagicMock(spec=DatabaseService)
    mock_db.is_initialized = True
    mock_db.is_ready = True
    mock_db.graph_name = "test_graph"
    mock_db.get_stats = AsyncMock(return_value={
        "node_counts": {"Person": 100, "Company": 50},
        "edge_counts": {"WORKS_AT": 75},
        "total_nodes": 150,
        "total_edges": 75,
        "memory_usage_bytes": 104857600,
        "memory_usage_mb": 100.0,
    })
    mock_db.get_schema = AsyncMock(
        return_value={
            "node_labels": ["Person", "Company"],
            "edge_types": ["WORKS_AT"],
            "node_properties": {
                "Person": ["id", "name", "age"],
                "Company": ["id", "name"],
            },
            "edge_properties": {
                "WORKS_AT": ["since"],
            },
        }
    )
    mock_db.execute_query = AsyncMock(
        return_value={
            "columns": ["name", "age"],
            "rows": [["Alice", 30], ["Bob", 25]],
            "row_count": 2,
            "execution_time_ms": 10.5,
        }
    )

    # Mock control plane client
    mock_cp = MagicMock()
    mock_cp.record_activity = AsyncMock()

    # Attach services to app state
    main_app.state.db_service = mock_db
    main_app.state.control_plane_client = mock_cp

    return main_app


@pytest.fixture(scope="function")
def integration_client(wrapper_app_with_mocked_services: FastAPI) -> Generator[Any, None, None]:
    """Create test client for wrapper with mocked services."""
    from fastapi.testclient import TestClient

    with TestClient(wrapper_app_with_mocked_services, raise_server_exceptions=False) as client:
        yield client
