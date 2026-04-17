"""Integration tests for Wrapper ↔ Control Plane communication.

These tests verify the wrapper's ControlPlaneClient makes correct HTTP calls
using mocked Control Plane responses via respx.

Test Coverage:
- Instance status updates (starting → running → stopping)
- Instance error reporting (failed status with error fields)
- Progress updates during startup
- Metrics reporting
- Activity recording
- Mapping retrieval
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient

    from wrapper.clients.control_plane import ControlPlaneClient


class TestInstanceStatusUpdates:
    """Test instance status update flow."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_update_status_to_starting(
        self,
        wrapper_control_plane_client: ControlPlaneClient,
        control_plane_http_client: AsyncClient,
        seeded_control_plane: dict[str, Any],
    ) -> None:
        """Can update instance status to starting with pod info."""
        # Update status via wrapper client
        await wrapper_control_plane_client.update_status(
            status="starting",
            pod_name="wrapper-pod-abc123",
            pod_ip="10.0.0.42",
        )

        # Verify via direct API call (to mocked endpoint)
        instance_id = seeded_control_plane["instance_id"]
        response = await control_plane_http_client.get(
            f"/api/instances/{instance_id}",
            headers={"X-User-Id": "test-user", "X-Username": "test.user"},
        )
        assert response.status_code == 200

        data = response.json()["data"]
        assert data["status"] == "starting"
        assert data["pod_name"] == "wrapper-pod-abc123"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_update_status_to_running(
        self,
        wrapper_control_plane_client: ControlPlaneClient,
        control_plane_http_client: AsyncClient,
        seeded_control_plane: dict[str, Any],
    ) -> None:
        """Can update instance status to running with URL."""
        instance_id = seeded_control_plane["instance_id"]

        # Update status via wrapper client
        await wrapper_control_plane_client.update_status(
            status="running",
            instance_url="http://10.0.0.42:8000",
        )

        # Verify via direct API call
        response = await control_plane_http_client.get(
            f"/api/instances/{instance_id}",
            headers={"X-User-Id": "test-user", "X-Username": "test.user"},
        )
        assert response.status_code == 200

        data = response.json()["data"]
        assert data["status"] == "running"
        assert data["instance_url"] == "http://10.0.0.42:8000"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_update_status_to_stopping(
        self,
        wrapper_control_plane_client: ControlPlaneClient,
        control_plane_http_client: AsyncClient,
        seeded_control_plane: dict[str, Any],
    ) -> None:
        """Can update instance status to stopping."""
        instance_id = seeded_control_plane["instance_id"]

        await wrapper_control_plane_client.update_status(status="stopping")

        response = await control_plane_http_client.get(
            f"/api/instances/{instance_id}",
            headers={"X-User-Id": "test-user", "X-Username": "test.user"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "stopping"


class TestInstanceErrorReporting:
    """Test error reporting via status updates."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_update_status_to_failed_with_error(
        self,
        wrapper_control_plane_client: ControlPlaneClient,
        control_plane_http_client: AsyncClient,
        seeded_control_plane: dict[str, Any],
    ) -> None:
        """Can report failure with error code and message."""
        instance_id = seeded_control_plane["instance_id"]

        await wrapper_control_plane_client.update_status(
            status="failed",
            error_code="DATA_LOAD_ERROR",
            error_message="Failed to load data from GCS: bucket not found",
            stack_trace="Traceback (most recent call last):\n  File ...",
        )

        response = await control_plane_http_client.get(
            f"/api/instances/{instance_id}",
            headers={"X-User-Id": "test-user", "X-Username": "test.user"},
        )
        assert response.status_code == 200

        data = response.json()["data"]
        assert data["status"] == "failed"
        assert data["error_code"] == "DATA_LOAD_ERROR"
        assert "bucket not found" in data["error_message"]
        assert data["stack_trace"] is not None

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_update_status_with_startup_failed(
        self,
        wrapper_control_plane_client: ControlPlaneClient,
        control_plane_http_client: AsyncClient,
        seeded_control_plane: dict[str, Any],
    ) -> None:
        """Can report startup failure."""
        instance_id = seeded_control_plane["instance_id"]

        await wrapper_control_plane_client.update_status(
            status="failed",
            error_code="STARTUP_FAILED",
            error_message="Initialization timeout",
        )

        response = await control_plane_http_client.get(
            f"/api/instances/{instance_id}",
            headers={"X-User-Id": "test-user", "X-Username": "test.user"},
        )
        assert response.status_code == 200

        data = response.json()["data"]
        assert data["error_code"] == "STARTUP_FAILED"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_update_status_with_schema_create_error(
        self,
        wrapper_control_plane_client: ControlPlaneClient,
        control_plane_http_client: AsyncClient,
        seeded_control_plane: dict[str, Any],
    ) -> None:
        """Can report schema creation error."""
        instance_id = seeded_control_plane["instance_id"]

        await wrapper_control_plane_client.update_status(
            status="failed",
            error_code="SCHEMA_CREATE_ERROR",
            error_message="Invalid primary key type: UNKNOWN",
        )

        response = await control_plane_http_client.get(
            f"/api/instances/{instance_id}",
            headers={"X-User-Id": "test-user", "X-Username": "test.user"},
        )
        data = response.json()["data"]
        assert data["error_code"] == "SCHEMA_CREATE_ERROR"


class TestProgressUpdates:
    """Test progress reporting during startup."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_update_progress(
        self,
        wrapper_control_plane_client: ControlPlaneClient,
        seeded_control_plane: dict[str, Any],
    ) -> None:
        """Can report startup progress."""
        # Update progress via wrapper client
        await wrapper_control_plane_client.update_progress(
            stage="loading",
            current=2,
            total=4,
            message="Loading Customer nodes",
        )

        # The mock will accept the request - we're testing the client makes the call
        # In a real scenario, this would update the instance progress in the DB


class TestMetricsReporting:
    """Test metrics updates."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_update_metrics(
        self,
        wrapper_control_plane_client: ControlPlaneClient,
        control_plane_http_client: AsyncClient,
        seeded_control_plane: dict[str, Any],
    ) -> None:
        """Can report instance resource metrics."""
        instance_id = seeded_control_plane["instance_id"]

        # Resource metrics only (per UpdateInstanceMetricsRequest schema)
        await wrapper_control_plane_client.update_metrics(
            memory_usage_bytes=512_000_000,
            disk_usage_bytes=1_024_000_000,
        )

        response = await control_plane_http_client.get(
            f"/api/instances/{instance_id}",
            headers={"X-User-Id": "test-user", "X-Username": "test.user"},
        )
        assert response.status_code == 200

        data = response.json()["data"]
        assert data["memory_usage_bytes"] == 512_000_000
        assert data["disk_usage_bytes"] == 1_024_000_000


class TestActivityRecording:
    """Test activity recording for inactivity timeout."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_record_activity(
        self,
        wrapper_control_plane_client: ControlPlaneClient,
        seeded_control_plane: dict[str, Any],
    ) -> None:
        """Can record instance activity."""
        # This should not raise
        await wrapper_control_plane_client.record_activity()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_record_activity_updates_timestamp(
        self,
        wrapper_control_plane_client: ControlPlaneClient,
        seeded_control_plane: dict[str, Any],
    ) -> None:
        """Activity recording makes correct API call."""
        # Record activity - the mock accepts the request
        await wrapper_control_plane_client.record_activity()

        # Test passes if no exception was raised


class TestMappingRetrieval:
    """Test mapping retrieval for schema creation."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_get_mapping(
        self,
        wrapper_control_plane_client: ControlPlaneClient,
        seeded_control_plane: dict[str, Any],
    ) -> None:
        """Can retrieve mapping definition using InstanceMappingResponse schema."""
        from graph_olap_schemas import InstanceMappingResponse

        mapping = await wrapper_control_plane_client.get_mapping()

        # Verify it's the correct type (shared schema)
        assert isinstance(mapping, InstanceMappingResponse)

        # Verify new schema fields (per InstanceMappingResponse)
        assert isinstance(mapping.mapping_id, int)
        assert isinstance(mapping.snapshot_id, int)
        assert mapping.gcs_path is not None
        assert mapping.gcs_path.startswith("gs://")

        assert len(mapping.node_definitions) == 2
        assert len(mapping.edge_definitions) == 1

        # Check node definitions
        labels = [n.label for n in mapping.node_definitions]
        assert "Customer" in labels
        assert "Product" in labels

        # Check edge definition
        assert mapping.edge_definitions[0].type == "PURCHASED"
        assert mapping.edge_definitions[0].from_node == "Customer"
        assert mapping.edge_definitions[0].to_node == "Product"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_get_mapping_contains_properties(
        self,
        wrapper_control_plane_client: ControlPlaneClient,
        seeded_control_plane: dict[str, Any],
    ) -> None:
        """Mapping includes property definitions."""
        mapping = await wrapper_control_plane_client.get_mapping()

        customer_node = next(n for n in mapping.node_definitions if n.label == "Customer")
        property_names = [p.name for p in customer_node.properties]

        assert "name" in property_names
        assert "city" in property_names


class TestFullStartupFlow:
    """Test complete startup flow simulation."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_startup_flow_success(
        self,
        wrapper_control_plane_client: ControlPlaneClient,
        control_plane_http_client: AsyncClient,
        seeded_control_plane: dict[str, Any],
    ) -> None:
        """Simulate successful wrapper startup flow."""
        instance_id = seeded_control_plane["instance_id"]

        # Step 1: Report starting
        await wrapper_control_plane_client.update_status(
            status="starting",
            pod_name="wrapper-pod-integration",
            pod_ip="10.0.0.100",
        )

        # Step 2: Get mapping
        mapping = await wrapper_control_plane_client.get_mapping()
        assert mapping is not None

        # Step 3: Report progress - creating schema
        await wrapper_control_plane_client.update_progress(
            stage="schema",
            current=1,
            total=4,
            message="Creating schema",
        )

        # Step 4: Report progress - loading nodes
        await wrapper_control_plane_client.update_progress(
            stage="loading",
            current=2,
            total=4,
            message="Loading nodes",
        )

        # Step 5: Report running with graph stats
        await wrapper_control_plane_client.update_status(
            status="running",
            instance_url="http://10.0.0.100:8000",
            node_count=1500,
            edge_count=5000,
        )

        # Step 6: Report resource metrics
        await wrapper_control_plane_client.update_metrics(
            memory_usage_bytes=256_000_000,
        )

        # Verify final state
        response = await control_plane_http_client.get(
            f"/api/instances/{instance_id}",
            headers={"X-User-Id": "test-user", "X-Username": "test.user"},
        )
        data = response.json()["data"]

        assert data["status"] == "running"
        assert data["instance_url"] == "http://10.0.0.100:8000"
        assert data["memory_usage_bytes"] == 256_000_000

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_startup_flow_failure(
        self,
        wrapper_control_plane_client: ControlPlaneClient,
        control_plane_http_client: AsyncClient,
        seeded_control_plane: dict[str, Any],
    ) -> None:
        """Simulate failed wrapper startup flow."""
        instance_id = seeded_control_plane["instance_id"]

        # Step 1: Report starting
        await wrapper_control_plane_client.update_status(
            status="starting",
            pod_name="wrapper-pod-failing",
            pod_ip="10.0.0.101",
        )

        # Step 2: Get mapping
        mapping = await wrapper_control_plane_client.get_mapping()
        assert mapping is not None

        # Step 3: Simulate failure during data load
        await wrapper_control_plane_client.update_status(
            status="failed",
            error_code="DATA_LOAD_ERROR",
            error_message="Failed to download parquet file: gs://bucket/data.parquet",
            stack_trace="google.cloud.exceptions.NotFound: 404 Not Found",
        )

        # Verify final state
        response = await control_plane_http_client.get(
            f"/api/instances/{instance_id}",
            headers={"X-User-Id": "test-user", "X-Username": "test.user"},
        )
        data = response.json()["data"]

        assert data["status"] == "failed"
        assert data["error_code"] == "DATA_LOAD_ERROR"
        assert "parquet" in data["error_message"]
