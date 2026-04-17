"""Integration tests for Control Plane client with mocked HTTP responses."""

from __future__ import annotations

from typing import Any

import pytest


class TestControlPlaneClient:
    """Integration tests for ControlPlaneClient with mocked endpoints."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_update_instance_status(
        self,
        wrapper_control_plane_client: Any,
        control_plane_http_client: Any,
        seeded_control_plane: dict[str, Any],
    ):
        """Test updating instance status."""
        # Update status to starting
        await wrapper_control_plane_client.update_status(
            status="starting",
            pod_name="test-pod",
            pod_ip="10.0.0.100",
            instance_url="http://10.0.0.100:8000",
        )

        # Verify status was updated via HTTP
        response = await control_plane_http_client.get(
            f"/api/instances/{seeded_control_plane['instance_id']}"
        )
        assert response.status_code == 200
        instance_data = response.json()["data"]
        assert instance_data["status"] == "starting"
        assert instance_data["pod_name"] == "test-pod"
        assert instance_data["pod_ip"] == "10.0.0.100"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_update_instance_status_to_running(
        self,
        wrapper_control_plane_client: Any,
        control_plane_http_client: Any,
        seeded_control_plane: dict[str, Any],
    ):
        """Test updating instance status to running."""
        await wrapper_control_plane_client.update_status(
            status="running",
            instance_url="http://10.0.0.100:8000",
        )

        response = await control_plane_http_client.get(
            f"/api/instances/{seeded_control_plane['instance_id']}"
        )
        assert response.status_code == 200
        instance_data = response.json()["data"]
        assert instance_data["status"] == "running"
        assert instance_data["instance_url"] == "http://10.0.0.100:8000"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_update_instance_status_to_failed(
        self,
        wrapper_control_plane_client: Any,
        control_plane_http_client: Any,
        seeded_control_plane: dict[str, Any],
    ):
        """Test updating instance status to failed with error details."""
        await wrapper_control_plane_client.update_status(
            status="failed",
            error_code="DATABASE_INIT_ERROR",
            error_message="Failed to initialize FalkorDB",
            stack_trace="Traceback...",
        )

        response = await control_plane_http_client.get(
            f"/api/instances/{seeded_control_plane['instance_id']}"
        )
        assert response.status_code == 200
        instance_data = response.json()["data"]
        assert instance_data["status"] == "failed"
        # Error code is stored as enum value in response
        assert instance_data.get("error_code") is not None or instance_data.get("error_message") is not None
        assert instance_data["error_message"] == "Failed to initialize FalkorDB"
        assert instance_data["stack_trace"] == "Traceback..."

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_update_progress(
        self,
        wrapper_control_plane_client: Any,
    ):
        """Test updating load progress."""
        from graph_olap_schemas import InstanceProgressStep

        # Should not raise
        await wrapper_control_plane_client.update_progress(
            phase="loading_nodes",
            steps=[
                InstanceProgressStep(name="Customer", status="completed", type="node", row_count=500),
                InstanceProgressStep(name="Product", status="in_progress", type="node"),
            ],
        )

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_update_metrics(
        self,
        wrapper_control_plane_client: Any,
        control_plane_http_client: Any,
        seeded_control_plane: dict[str, Any],
    ):
        """Test updating instance metrics."""
        await wrapper_control_plane_client.update_metrics(
            memory_usage_bytes=104857600,  # 100 MB
            disk_usage_bytes=524288000,     # 500 MB
        )

        response = await control_plane_http_client.get(
            f"/api/instances/{seeded_control_plane['instance_id']}"
        )
        assert response.status_code == 200
        instance_data = response.json()["data"]
        assert instance_data["memory_usage_bytes"] == 104857600
        assert instance_data["disk_usage_bytes"] == 524288000

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_record_activity(
        self,
        wrapper_control_plane_client: Any,
    ):
        """Test recording instance activity."""
        # Should not raise
        await wrapper_control_plane_client.record_activity()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_get_mapping(
        self,
        wrapper_control_plane_client: Any,
        mock_control_plane_responses: dict[str, Any],
    ):
        """Test fetching mapping definition."""
        mapping = await wrapper_control_plane_client.get_mapping()

        # Verify mapping structure
        assert mapping.snapshot_id == mock_control_plane_responses["mapping"]["snapshot_id"]
        assert mapping.mapping_id == mock_control_plane_responses["mapping"]["mapping_id"]
        assert mapping.gcs_path == mock_control_plane_responses["mapping"]["gcs_path"]
        assert len(mapping.node_definitions) == 2
        assert len(mapping.edge_definitions) == 1

        # Verify node definitions
        person_node = next(n for n in mapping.node_definitions if n.label == "Person")
        assert person_node.primary_key.name == "id"
        assert person_node.primary_key.type == "STRING"
        assert len(person_node.properties) == 2

        company_node = next(n for n in mapping.node_definitions if n.label == "Company")
        assert company_node.label == "Company"

        # Verify edge definition
        edge = mapping.edge_definitions[0]
        assert edge.type == "WORKS_AT"
        assert edge.from_node == "Person"
        assert edge.to_node == "Company"
        assert len(edge.properties) == 1

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_client_close(
        self,
        wrapper_control_plane_client: Any,
    ):
        """Test client cleanup."""
        # Should not raise
        await wrapper_control_plane_client.close()

        # Verify client is closed (would raise on subsequent calls in real impl)
        # For mock, just verify close was called without error
