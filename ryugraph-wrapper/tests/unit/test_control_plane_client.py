"""Unit tests for the ControlPlaneClient."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from wrapper.clients.control_plane import ControlPlaneClient
from wrapper.exceptions import ControlPlaneError


class TestControlPlaneClient:
    """Tests for ControlPlaneClient."""

    @pytest.fixture
    def client(self) -> ControlPlaneClient:
        """Create client with test token."""
        return ControlPlaneClient(
            base_url="http://localhost:8080",
            instance_id="test-instance-123",
            service_account_token="test-token",
        )

    # =========================================================================
    # Status Update Tests
    # =========================================================================

    @pytest.mark.unit
    @respx.mock
    async def test_update_status_success(self, client: ControlPlaneClient) -> None:
        """Successfully update instance status."""
        route = respx.patch(
            "http://localhost:8080/api/internal/instances/test-instance-123/status"
        ).mock(return_value=Response(200, json={"status": "ok"}))

        await client.update_status(
            status="running",
            instance_url="http://10.0.0.1:8000",
        )

        assert route.called
        request = route.calls[0].request
        assert request.headers["Authorization"] == "Bearer test-token"

    @pytest.mark.unit
    @respx.mock
    async def test_update_status_with_error_fields(self, client: ControlPlaneClient) -> None:
        """Successfully update status with error fields."""
        route = respx.patch(
            "http://localhost:8080/api/internal/instances/test-instance-123/status"
        ).mock(return_value=Response(200, json={"status": "ok"}))

        await client.update_status(
            status="failed",
            error_code="DATA_LOAD_ERROR",
            error_message="Failed to load data from GCS",
            stack_trace="Traceback...",
        )

        assert route.called
        request_body = route.calls[0].request.content
        assert b"failed" in request_body
        assert b"DATA_LOAD_ERROR" in request_body
        assert b"Failed to load data from GCS" in request_body

    @pytest.mark.unit
    @respx.mock
    async def test_update_status_retries_on_failure(self, client: ControlPlaneClient) -> None:
        """Retries on transient failures."""
        # First two calls fail, third succeeds
        route = respx.patch(
            "http://localhost:8080/api/internal/instances/test-instance-123/status"
        ).mock(
            side_effect=[
                Response(500),
                Response(500),
                Response(200, json={"status": "ok"}),
            ]
        )

        await client.update_status(status="running")

        assert route.call_count == 3

    @pytest.mark.unit
    @respx.mock
    async def test_update_status_raises_after_max_retries(self, client: ControlPlaneClient) -> None:
        """Raises after exhausting retries."""
        respx.patch("http://localhost:8080/api/internal/instances/test-instance-123/status").mock(
            return_value=Response(500)
        )

        with pytest.raises(ControlPlaneError):
            await client.update_status(status="running")

    # =========================================================================
    # Progress Update Tests
    # =========================================================================

    @pytest.mark.unit
    @respx.mock
    async def test_update_progress_success(self, client: ControlPlaneClient) -> None:
        """Successfully update progress using shared schema."""
        from graph_olap_schemas import InstanceProgressStep

        route = respx.put(
            "http://localhost:8080/api/internal/instances/test-instance-123/progress"
        ).mock(return_value=Response(200, json={}))

        # Use new schema-compliant API with phase and steps
        steps = [
            InstanceProgressStep(name="Customer", status="completed", type="node"),
            InstanceProgressStep(name="Product", status="in_progress", type="node"),
        ]
        await client.update_progress(phase="loading_nodes", steps=steps)

        assert route.called
        request_body = route.calls[0].request.content
        assert b"loading_nodes" in request_body
        assert b"Customer" in request_body

    @pytest.mark.unit
    @respx.mock
    async def test_update_progress_legacy_params(self, client: ControlPlaneClient) -> None:
        """Backward compatible progress update with legacy current/total params."""
        route = respx.put(
            "http://localhost:8080/api/internal/instances/test-instance-123/progress"
        ).mock(return_value=Response(200, json={}))

        # Use legacy parameters for backward compatibility
        await client.update_progress(
            phase="loading_nodes",
            stage="loading_nodes",
            current=5,
            total=10,
            message="Loading Customer nodes",
        )

        assert route.called
        request_body = route.calls[0].request.content
        assert b"loading_nodes" in request_body

    # =========================================================================
    # Metrics Update Tests
    # =========================================================================

    @pytest.mark.unit
    @respx.mock
    async def test_update_metrics_success(self, client: ControlPlaneClient) -> None:
        """Successfully update resource metrics using shared schema."""
        route = respx.put(
            "http://localhost:8080/api/internal/instances/test-instance-123/metrics"
        ).mock(return_value=Response(200, json={}))

        # UpdateInstanceMetricsRequest schema: memory, disk, last_activity, query_count_since_last, avg_query_time
        await client.update_metrics(
            memory_usage_bytes=1024 * 1024 * 512,
            disk_usage_bytes=1024 * 1024 * 100,
        )

        assert route.called
        request_body = route.calls[0].request.content
        assert b"memory_usage_bytes" in request_body
        assert b"disk_usage_bytes" in request_body

    @pytest.mark.unit
    @respx.mock
    async def test_update_metrics_partial(self, client: ControlPlaneClient) -> None:
        """Can update only some metrics."""
        route = respx.put(
            "http://localhost:8080/api/internal/instances/test-instance-123/metrics"
        ).mock(return_value=Response(200, json={}))

        # Only memory usage
        await client.update_metrics(memory_usage_bytes=1024 * 1024 * 256)

        assert route.called

    @pytest.mark.unit
    @respx.mock
    async def test_update_status_with_graph_stats(self, client: ControlPlaneClient) -> None:
        """Graph statistics are sent via update_status, not update_metrics."""
        route = respx.patch(
            "http://localhost:8080/api/internal/instances/test-instance-123/status"
        ).mock(return_value=Response(200, json={"status": "ok"}))

        await client.update_status(
            status="running",
            node_count=1000,
            edge_count=5000,
        )

        assert route.called
        request_body = route.calls[0].request.content
        assert b"graph_stats" in request_body
        assert b"node_count" in request_body
        assert b"edge_count" in request_body

    # =========================================================================
    # Get Mapping Tests
    # =========================================================================

    @pytest.mark.unit
    @respx.mock
    async def test_get_mapping_success(self, client: ControlPlaneClient) -> None:
        """Successfully fetch mapping - returns InstanceMappingResponse directly."""
        from graph_olap_schemas import InstanceMappingResponse

        # Response must match InstanceMappingResponse schema exactly
        mapping_response = {
            "snapshot_id": 456,
            "mapping_id": 123,
            "mapping_version": 1,
            "gcs_path": "gs://bucket/user/mapping/snapshot/",
            "node_definitions": [
                {
                    "label": "Customer",
                    "sql": "SELECT * FROM customers",
                    "primary_key": {"name": "id", "type": "STRING"},
                    "properties": [{"name": "name", "type": "STRING"}],
                }
            ],
            "edge_definitions": [],
        }

        respx.get("http://localhost:8080/api/internal/instances/test-instance-123/mapping").mock(
            return_value=Response(200, json=mapping_response)
        )

        mapping = await client.get_mapping()

        # Returns InstanceMappingResponse directly (shared schema type)
        assert isinstance(mapping, InstanceMappingResponse)
        assert mapping.mapping_id == 123
        assert mapping.snapshot_id == 456
        assert mapping.gcs_path == "gs://bucket/user/mapping/snapshot/"
        assert len(mapping.node_definitions) == 1
        assert mapping.node_definitions[0].label == "Customer"

    @pytest.mark.unit
    @respx.mock
    async def test_get_mapping_invalid_response(self, client: ControlPlaneClient) -> None:
        """Raises on invalid mapping response."""
        # Missing required fields
        invalid_response = {"mapping_id": "map-123"}

        respx.get("http://localhost:8080/api/internal/instances/test-instance-123/mapping").mock(
            return_value=Response(200, json=invalid_response)
        )

        with pytest.raises(ControlPlaneError) as exc_info:
            await client.get_mapping()

        assert "Invalid mapping response" in str(exc_info.value)

    @pytest.mark.unit
    @respx.mock
    async def test_get_mapping_not_found(self, client: ControlPlaneClient) -> None:
        """Raises on 404."""
        respx.get("http://localhost:8080/api/internal/instances/test-instance-123/mapping").mock(
            return_value=Response(404, json={"error": "Not found"})
        )

        with pytest.raises(ControlPlaneError) as exc_info:
            await client.get_mapping()

        assert exc_info.value.status_code == 404

    # =========================================================================
    # Activity Recording Tests
    # =========================================================================

    @pytest.mark.unit
    @respx.mock
    async def test_record_activity_success(self, client: ControlPlaneClient) -> None:
        """Successfully record activity."""
        route = respx.post(
            "http://localhost:8080/api/internal/instances/test-instance-123/activity"
        ).mock(return_value=Response(204))

        await client.record_activity()

        assert route.called

    @pytest.mark.unit
    @respx.mock
    async def test_record_activity_silent_failure(self, client: ControlPlaneClient) -> None:
        """Activity recording failures are silent (fire-and-forget)."""
        respx.post("http://localhost:8080/api/internal/instances/test-instance-123/activity").mock(
            return_value=Response(500)
        )

        # Should not raise
        await client.record_activity()

    # =========================================================================
    # Authentication Tests
    # =========================================================================

    @pytest.mark.unit
    @respx.mock
    async def test_uses_provided_token(self, client: ControlPlaneClient) -> None:
        """Uses provided service account token."""
        route = respx.patch(
            "http://localhost:8080/api/internal/instances/test-instance-123/status"
        ).mock(return_value=Response(200, json={}))

        await client.update_status(status="running")

        request = route.calls[0].request
        assert request.headers["Authorization"] == "Bearer test-token"

    @pytest.mark.unit
    @respx.mock
    async def test_no_token_when_none_provided(self) -> None:
        """Works without token when none available."""
        # Create client without token
        client = ControlPlaneClient(
            base_url="http://localhost:8080",
            instance_id="test-instance",
            service_account_token=None,
        )

        route = respx.patch(
            "http://localhost:8080/api/internal/instances/test-instance/status"
        ).mock(return_value=Response(200, json={}))

        await client.update_status(status="running")

        # Should have made the request (with or without Authorization header)
        assert route.called

    # =========================================================================
    # Cleanup Tests
    # =========================================================================

    @pytest.mark.unit
    async def test_close(self, client: ControlPlaneClient) -> None:
        """Can close the client."""
        await client.close()
        # Should not raise


class TestControlPlaneClientTokenRefresh:
    """Tests for token refresh behavior."""

    @pytest.mark.unit
    @respx.mock
    async def test_caches_token(self) -> None:
        """Token is cached between requests."""
        client = ControlPlaneClient(
            base_url="http://localhost:8080",
            instance_id="test-instance",
            service_account_token="cached-token",
        )

        route = respx.patch(url__regex=r".*/status").mock(return_value=Response(200, json={}))

        # Make two requests
        await client.update_status(status="running")
        await client.update_status(status="running")

        # Both should use same token
        assert route.call_count == 2
        for call in route.calls:
            assert call.request.headers["Authorization"] == "Bearer cached-token"

        await client.close()
