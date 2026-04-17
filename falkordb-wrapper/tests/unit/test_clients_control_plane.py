"""Unit tests for the Control Plane client.

Tests cover:
- Client initialization
- Status updates
- Progress updates
- Metrics updates
- Mapping fetching
- Activity recording
- Error handling
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx

from wrapper.clients.control_plane import ControlPlaneClient
from wrapper.exceptions import ControlPlaneError


@pytest.fixture
def client():
    """Create a ControlPlaneClient for testing."""
    return ControlPlaneClient(
        base_url="http://test-control-plane:8080",
        instance_id="test-instance-123",
        internal_api_key="test-api-key",
    )


@pytest.fixture
def sample_mapping_response() -> dict[str, Any]:
    """Sample mapping response from Control Plane."""
    return {
        "snapshot_id": 1,
        "mapping_id": 123,
        "mapping_version": 1,
        "gcs_path": "gs://test-bucket/mappings/mapping-123",
        "node_definitions": [
            {
                "label": "Person",
                "sql": "SELECT id, name FROM people",
                "primary_key": {"name": "id", "type": "STRING"},
                "properties": [{"name": "name", "type": "STRING"}],
            }
        ],
        "edge_definitions": [],
    }


class TestControlPlaneClientInit:
    """Tests for client initialization."""

    def test_client_initialization(self):
        """Client initializes with correct parameters."""
        client = ControlPlaneClient(
            base_url="http://localhost:8080",
            instance_id="instance-123",
            timeout=60.0,
            internal_api_key="my-key",
        )

        assert client._base_url == "http://localhost:8080"
        assert client._instance_id == "instance-123"
        assert client._timeout == 60.0
        assert client._internal_api_key == "my-key"

    def test_client_strips_trailing_slash(self):
        """Client strips trailing slash from base URL."""
        client = ControlPlaneClient(
            base_url="http://localhost:8080/",
            instance_id="instance-123",
        )

        assert client._base_url == "http://localhost:8080"


class TestUpdateStatus:
    """Tests for update_status method."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_update_status_to_running(self, client):
        """Update status to running succeeds."""
        route = respx.patch(
            "http://test-control-plane:8080/api/internal/instances/test-instance-123/status"
        ).respond(status_code=204)

        await client.update_status(status="running")

        assert route.called
        request = route.calls[0].request
        assert "X-Internal-API-Key" in request.headers

    @respx.mock
    @pytest.mark.asyncio
    async def test_update_status_to_failed_with_error(self, client):
        """Update status to failed includes error details."""
        route = respx.patch(
            "http://test-control-plane:8080/api/internal/instances/test-instance-123/status"
        ).respond(status_code=204)

        await client.update_status(
            status="failed",
            error_message="Database connection failed",
            error_code="DATABASE_ERROR",
            stack_trace="Traceback...",
        )

        assert route.called
        # Verify request body contains error info
        request = route.calls[0].request
        import json
        body = json.loads(request.content)
        assert body["status"] == "failed"
        assert body["error_message"] == "Database connection failed"

    @respx.mock
    @pytest.mark.asyncio
    async def test_update_status_with_graph_stats(self, client):
        """Update status includes graph stats when provided."""
        route = respx.patch(
            "http://test-control-plane:8080/api/internal/instances/test-instance-123/status"
        ).respond(status_code=204)

        await client.update_status(
            status="running",
            node_count=100,
            edge_count=200,
        )

        assert route.called
        import json
        body = json.loads(route.calls[0].request.content)
        assert body["graph_stats"]["node_count"] == 100
        assert body["graph_stats"]["edge_count"] == 200


class TestUpdateProgress:
    """Tests for update_progress method."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_update_progress_loading_nodes(self, client):
        """Update progress for loading nodes."""
        route = respx.put(
            "http://test-control-plane:8080/api/internal/instances/test-instance-123/progress"
        ).respond(status_code=204)

        await client.update_progress(
            stage="loading_nodes",
            current=5,
            total=10,
            message="Loading Person nodes",
        )

        assert route.called

    @respx.mock
    @pytest.mark.asyncio
    async def test_update_progress_with_steps(self, client):
        """Update progress with explicit steps list."""
        from graph_olap_schemas import InstanceProgressStep

        route = respx.put(
            "http://test-control-plane:8080/api/internal/instances/test-instance-123/progress"
        ).respond(status_code=204)

        steps = [
            InstanceProgressStep(name="Load Person", status="completed"),
            InstanceProgressStep(name="Load Company", status="in_progress"),
        ]

        await client.update_progress(
            phase="loading_nodes",
            steps=steps,
        )

        assert route.called


class TestUpdateMetrics:
    """Tests for update_metrics method."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_update_metrics_success(self, client):
        """Update metrics succeeds."""
        route = respx.put(
            "http://test-control-plane:8080/api/internal/instances/test-instance-123/metrics"
        ).respond(status_code=204)

        await client.update_metrics(
            memory_usage_bytes=1024 * 1024 * 100,
            disk_usage_bytes=1024 * 1024 * 500,
        )

        assert route.called
        import json
        body = json.loads(route.calls[0].request.content)
        assert body["memory_usage_bytes"] == 1024 * 1024 * 100


class TestGetMapping:
    """Tests for get_mapping method."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_mapping_success(self, client, sample_mapping_response):
        """Get mapping returns validated response."""
        route = respx.get(
            "http://test-control-plane:8080/api/internal/instances/test-instance-123/mapping"
        ).respond(json=sample_mapping_response)

        mapping = await client.get_mapping()

        assert route.called
        assert mapping.mapping_id == 123
        assert mapping.snapshot_id == 1
        assert len(mapping.node_definitions) == 1
        assert mapping.node_definitions[0].label == "Person"

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_mapping_not_found(self, client):
        """Get mapping raises error when not found."""
        route = respx.get(
            "http://test-control-plane:8080/api/internal/instances/test-instance-123/mapping"
        ).respond(status_code=404, json={"detail": "Not found"})

        with pytest.raises(ControlPlaneError) as exc_info:
            await client.get_mapping()

        assert exc_info.value.status_code == 404

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_mapping_invalid_response(self, client):
        """Get mapping raises error for invalid response."""
        route = respx.get(
            "http://test-control-plane:8080/api/internal/instances/test-instance-123/mapping"
        ).respond(json={"invalid": "response"})

        with pytest.raises(ControlPlaneError):
            await client.get_mapping()


class TestRecordActivity:
    """Tests for record_activity method."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_record_activity_success(self, client):
        """Record activity succeeds."""
        route = respx.post(
            "http://test-control-plane:8080/api/internal/instances/test-instance-123/activity"
        ).respond(status_code=204)

        await client.record_activity()

        assert route.called

    @respx.mock
    @pytest.mark.asyncio
    async def test_record_activity_silently_fails(self, client):
        """Record activity doesn't raise on failure."""
        route = respx.post(
            "http://test-control-plane:8080/api/internal/instances/test-instance-123/activity"
        ).respond(status_code=500)

        # Should not raise
        await client.record_activity()

        assert route.called


class TestClientClose:
    """Tests for client close method."""

    @pytest.mark.asyncio
    async def test_client_close(self, client):
        """Client closes HTTP client."""
        await client.close()

        # Verify client is closed (will raise if we try to use it)
        with pytest.raises(Exception):
            # This should fail because client is closed
            await client._client.get("http://example.com")


class TestClientHeaders:
    """Tests for request headers."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_client_headers_include_api_key(self, client):
        """Requests include X-Internal-API-Key header."""
        route = respx.patch(
            "http://test-control-plane:8080/api/internal/instances/test-instance-123/status"
        ).respond(status_code=204)

        await client.update_status(status="running")

        request = route.calls[0].request
        assert request.headers["X-Internal-API-Key"] == "test-api-key"

    @respx.mock
    @pytest.mark.asyncio
    async def test_client_headers_include_content_type(self):
        """Requests include Content-Type header."""
        client = ControlPlaneClient(
            base_url="http://test-control-plane:8080",
            instance_id="test-instance-123",
        )

        route = respx.patch(
            "http://test-control-plane:8080/api/internal/instances/test-instance-123/status"
        ).respond(status_code=204)

        await client.update_status(status="running")

        request = route.calls[0].request
        assert "application/json" in request.headers.get("Content-Type", "")


class TestErrorHandling:
    """Tests for error handling."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_http_error_raises_control_plane_error(self, client):
        """HTTP errors are converted to ControlPlaneError."""
        route = respx.patch(
            "http://test-control-plane:8080/api/internal/instances/test-instance-123/status"
        ).respond(status_code=500, json={"detail": "Internal error"})

        with pytest.raises(ControlPlaneError) as exc_info:
            await client.update_status(status="running")

        assert exc_info.value.status_code == 500

    @respx.mock
    @pytest.mark.asyncio
    async def test_network_error_raises_control_plane_error(self, client):
        """Network errors are converted to ControlPlaneError."""
        route = respx.patch(
            "http://test-control-plane:8080/api/internal/instances/test-instance-123/status"
        ).mock(side_effect=httpx.ConnectError("Connection refused"))

        with pytest.raises(ControlPlaneError):
            await client.update_status(status="running")


class TestTokenHandling:
    """Tests for token handling."""

    @pytest.mark.asyncio
    async def test_uses_preconfigured_token(self):
        """Client uses pre-configured service account token."""
        client = ControlPlaneClient(
            base_url="http://test-control-plane:8080",
            instance_id="test-instance-123",
            service_account_token="my-token",
        )

        token = await client._get_token()
        assert token == "my-token"

    @pytest.mark.asyncio
    async def test_empty_token_without_metadata_server(self):
        """Client returns empty token when metadata server unavailable."""
        client = ControlPlaneClient(
            base_url="http://test-control-plane:8080",
            instance_id="test-instance-123",
        )

        # Without a real metadata server, should return empty string
        token = await client._get_token()
        assert token == ""
