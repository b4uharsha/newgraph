"""Unit tests for ControlPlaneClient."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
import respx

from export_worker.clients import ControlPlaneClient
from export_worker.exceptions import ControlPlaneError
from export_worker.models import ExportPhase, SnapshotProgress, SnapshotStatus


# =============================================================================
# SNAPSHOT TESTS DISABLED
# These tests are commented out as snapshot functionality has been disabled.
# =============================================================================
# class TestControlPlaneClient:
#     """Tests for ControlPlaneClient."""
#
#     @pytest.fixture
#     def client(self) -> ControlPlaneClient:
#         """Create client for testing (no ID token auth)."""
#         return ControlPlaneClient(
#             base_url="http://control-plane.test:8080",
#             timeout=10,
#             max_retries=3,
#             use_id_token=False,  # Disable for testing
#         )
#
#     @respx.mock
#     def test_update_snapshot_status_success(
#         self,
#         client: ControlPlaneClient,
#     ) -> None:
#         """Test successful status update."""
#         respx.patch("http://control-plane.test:8080/api/internal/snapshots/123/status").mock(
#             return_value=httpx.Response(200, json={"success": True})
#         )
#
#         # Should not raise
#         client.update_snapshot_status(
#             snapshot_id=123,
#             status=SnapshotStatus.CREATING,
#         )
#
#     @respx.mock
#     def test_update_snapshot_status_with_progress(
#         self,
#         client: ControlPlaneClient,
#     ) -> None:
#         """Test status update with progress information."""
#         route = respx.patch("http://control-plane.test:8080/api/internal/snapshots/123/status").mock(
#             return_value=httpx.Response(200, json={"success": True})
#         )
#
#         progress = SnapshotProgress()
#         progress.phase = ExportPhase.EXPORTING_NODES
#
#         client.update_snapshot_status(
#             snapshot_id=123,
#             status=SnapshotStatus.CREATING,
#             progress=progress,
#         )
#
#         # Verify progress was included in request
#         request_json = route.calls.last.request.content
#         assert b"progress" in request_json
#
#     @respx.mock
#     def test_update_snapshot_status_ready_with_counts(
#         self,
#         client: ControlPlaneClient,
#     ) -> None:
#         """Test status update to READY with counts and size."""
#         route = respx.patch("http://control-plane.test:8080/api/internal/snapshots/123/status").mock(
#             return_value=httpx.Response(200, json={"success": True})
#         )
#
#         client.update_snapshot_status(
#             snapshot_id=123,
#             status=SnapshotStatus.READY,
#             size_bytes=1024 * 1024,
#             node_counts={"Customer": 1000, "Product": 500},
#             edge_counts={"PURCHASED": 5000},
#         )
#
#         # Verify all fields were included
#         import json
#
#         request_body = json.loads(route.calls.last.request.content)
#         assert request_body["status"] == "ready"
#         assert request_body["size_bytes"] == 1024 * 1024
#         assert request_body["node_counts"] == {"Customer": 1000, "Product": 500}
#         assert request_body["edge_counts"] == {"PURCHASED": 5000}
#
#     @respx.mock
#     def test_update_snapshot_status_failed_with_error(
#         self,
#         client: ControlPlaneClient,
#     ) -> None:
#         """Test status update to FAILED with error details."""
#         route = respx.patch("http://control-plane.test:8080/api/internal/snapshots/123/status").mock(
#             return_value=httpx.Response(200, json={"success": True})
#         )
#
#         client.update_snapshot_status(
#             snapshot_id=123,
#             status=SnapshotStatus.FAILED,
#             error_message="Query timeout after 30 minutes",
#             failed_step="Customer",
#         )
#
#         import json
#
#         request_body = json.loads(route.calls.last.request.content)
#         assert request_body["status"] == "failed"
#         assert request_body["error_message"] == "Query timeout after 30 minutes"
#         assert request_body["failed_step"] == "Customer"
#
#     @respx.mock
#     def test_update_snapshot_status_http_error(
#         self,
#         client: ControlPlaneClient,
#     ) -> None:
#         """Test handling HTTP error during status update."""
#         respx.patch("http://control-plane.test:8080/api/internal/snapshots/123/status").mock(
#             return_value=httpx.Response(500, text="Internal Server Error")
#         )
#
#         with pytest.raises(ControlPlaneError) as exc_info:
#             client.update_snapshot_status(
#                 snapshot_id=123,
#                 status=SnapshotStatus.CREATING,
#             )
#
#         assert "500" in str(exc_info.value)
#
#     @respx.mock
#     def test_update_snapshot_status_string_status(
#         self,
#         client: ControlPlaneClient,
#     ) -> None:
#         """Test status update with string status value."""
#         route = respx.patch("http://control-plane.test:8080/api/internal/snapshots/123/status").mock(
#             return_value=httpx.Response(200, json={"success": True})
#         )
#
#         client.update_snapshot_status(
#             snapshot_id=123,
#             status="creating",  # String instead of enum
#         )
#
#         import json
#
#         request_body = json.loads(route.calls.last.request.content)
#         assert request_body["status"] == "creating"
#
#     @respx.mock
#     def test_get_snapshot_status_success(
#         self,
#         client: ControlPlaneClient,
#     ) -> None:
#         """Test successful status retrieval."""
#         respx.get("http://control-plane.test:8080/api/internal/snapshots/123/status").mock(
#             return_value=httpx.Response(
#                 200,
#                 json={"data": {"status": "creating"}},
#             )
#         )
#
#         status = client.get_snapshot_status(123)
#
#         assert status == SnapshotStatus.CREATING
#
#     @respx.mock
#     def test_get_snapshot_status_cancelled(
#         self,
#         client: ControlPlaneClient,
#     ) -> None:
#         """Test retrieval of cancelled status."""
#         respx.get("http://control-plane.test:8080/api/internal/snapshots/123/status").mock(
#             return_value=httpx.Response(
#                 200,
#                 json={"data": {"status": "cancelled"}},
#             )
#         )
#
#         status = client.get_snapshot_status(123)
#
#         assert status == SnapshotStatus.CANCELLED
#
#     @respx.mock
#     def test_get_snapshot_status_http_error(
#         self,
#         client: ControlPlaneClient,
#     ) -> None:
#         """Test handling HTTP error during status retrieval."""
#         respx.get("http://control-plane.test:8080/api/internal/snapshots/123/status").mock(
#             return_value=httpx.Response(404, text="Not Found")
#         )
#
#         with pytest.raises(ControlPlaneError) as exc_info:
#             client.get_snapshot_status(123)
#
#         assert "404" in str(exc_info.value)
#
#     @respx.mock
#     def test_get_snapshot_status_invalid_response(
#         self,
#         client: ControlPlaneClient,
#     ) -> None:
#         """Test handling invalid response format."""
#         respx.get("http://control-plane.test:8080/api/internal/snapshots/123/status").mock(
#             return_value=httpx.Response(
#                 200,
#                 json={"invalid": "format"},  # Missing data.status
#             )
#         )
#
#         with pytest.raises(ControlPlaneError) as exc_info:
#             client.get_snapshot_status(123)
#
#         assert "missing status" in str(exc_info.value)
#
#     @respx.mock
#     def test_is_cancelled_true(
#         self,
#         client: ControlPlaneClient,
#     ) -> None:
#         """Test is_cancelled returns True for cancelled snapshot."""
#         respx.get("http://control-plane.test:8080/api/internal/snapshots/123/status").mock(
#             return_value=httpx.Response(
#                 200,
#                 json={"data": {"status": "cancelled"}},
#             )
#         )
#
#         assert client.is_cancelled(123) is True
#
#     @respx.mock
#     def test_is_cancelled_false(
#         self,
#         client: ControlPlaneClient,
#     ) -> None:
#         """Test is_cancelled returns False for non-cancelled snapshot."""
#         respx.get("http://control-plane.test:8080/api/internal/snapshots/123/status").mock(
#             return_value=httpx.Response(
#                 200,
#                 json={"data": {"status": "creating"}},
#             )
#         )
#
#         assert client.is_cancelled(123) is False
#
#     @respx.mock
#     def test_is_cancelled_on_error(
#         self,
#         client: ControlPlaneClient,
#     ) -> None:
#         """Test is_cancelled returns False on error (fail open)."""
#         respx.get("http://control-plane.test:8080/api/internal/snapshots/123/status").mock(
#             return_value=httpx.Response(500)
#         )
#
#         # Should return False on error, not raise
#         assert client.is_cancelled(123) is False


class TestControlPlaneClientAuth:
    """Tests for ControlPlaneClient authentication."""

    def test_headers_without_id_token(self) -> None:
        """Test headers when ID token is disabled."""
        client = ControlPlaneClient(
            base_url="http://control-plane.test:8080",
            use_id_token=False,
        )

        headers = client._get_headers()

        assert "Authorization" not in headers
        assert headers["Content-Type"] == "application/json"
        assert headers["X-Component"] == "worker"

    def test_headers_with_id_token(self) -> None:
        """Test headers when ID token is enabled."""
        client = ControlPlaneClient(
            base_url="http://control-plane.test:8080",
            use_id_token=True,
        )

        with patch("export_worker.clients.control_plane.id_token.fetch_id_token") as mock_fetch:
            mock_fetch.return_value = "test-id-token"

            headers = client._get_headers()

            assert headers["Authorization"] == "Bearer test-id-token"
            mock_fetch.assert_called_once()

    def test_id_token_caching(self) -> None:
        """Test that ID token is cached."""
        client = ControlPlaneClient(
            base_url="http://control-plane.test:8080",
            use_id_token=True,
        )

        with patch("export_worker.clients.control_plane.id_token.fetch_id_token") as mock_fetch:
            mock_fetch.return_value = "test-id-token"

            # Call twice
            client._get_headers()
            client._get_headers()

            # Should only fetch once
            assert mock_fetch.call_count == 1

    def test_id_token_fetch_failure(self) -> None:
        """Test graceful handling of ID token fetch failure."""
        client = ControlPlaneClient(
            base_url="http://control-plane.test:8080",
            use_id_token=True,
        )

        with patch("export_worker.clients.control_plane.id_token.fetch_id_token") as mock_fetch:
            mock_fetch.side_effect = Exception("Metadata server unavailable")

            headers = client._get_headers()

            # Should proceed without auth header
            assert "Authorization" not in headers


class TestControlPlaneClientExportJobs:
    """Tests for ControlPlaneClient export job methods."""

    @pytest.fixture
    def client(self) -> ControlPlaneClient:
        """Create client for testing."""
        return ControlPlaneClient(
            base_url="http://control-plane.test:8080",
            timeout=10,
            use_id_token=False,
        )

    @respx.mock
    def test_get_pending_export_jobs_success(self, client: ControlPlaneClient) -> None:
        """Test successful retrieval of pending export jobs."""
        respx.get("http://control-plane.test:8080/api/internal/snapshots/123/export-jobs").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": 1,
                            "snapshot_id": 123,
                            "job_type": "node",
                            "entity_name": "Customer",
                            "status": "pending",
                            "gcs_path": "gs://bucket/path/",
                        },
                        {
                            "id": 2,
                            "snapshot_id": 123,
                            "job_type": "edge",
                            "entity_name": "PURCHASED",
                            "status": "pending",
                            "gcs_path": "gs://bucket/path/",
                        },
                    ]
                },
            )
        )

        result = client.get_pending_export_jobs(123)

        assert len(result) == 2
        assert result[0].entity_name == "Customer"
        assert result[1].entity_name == "PURCHASED"

    @respx.mock
    def test_start_export_job_success(self, client: ControlPlaneClient) -> None:
        """Test successful export job start."""
        respx.patch("http://control-plane.test:8080/api/internal/export-jobs/1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "id": 1,
                        "snapshot_id": 123,
                        "job_type": "node",
                        "entity_name": "Customer",
                        "status": "submitted",  # ADR-025
                        "gcs_path": "gs://bucket/path/",
                        "starburst_query_id": "query-123",
                        "next_uri": "http://starburst/v1/query/123",
                        "submitted_at": "2024-01-01T00:00:00Z",
                    }
                },
            )
        )

        result = client.start_export_job(
            job_id=1,
            starburst_query_id="query-123",
            next_uri="http://starburst/v1/query/123",
            submitted_at="2024-01-01T00:00:00Z",
        )

        assert result.id == 1
        assert result.starburst_query_id == "query-123"

    @respx.mock
    def test_update_export_job_success(self, client: ControlPlaneClient) -> None:
        """Test successful export job update."""
        from export_worker.models import ExportJobStatus

        respx.patch("http://control-plane.test:8080/api/internal/export-jobs/1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "id": 1,
                        "snapshot_id": 123,
                        "job_type": "node",
                        "entity_name": "Customer",
                        "status": "completed",
                        "gcs_path": "gs://bucket/path/",
                        "row_count": 1000,
                        "size_bytes": 1024,
                    }
                },
            )
        )

        result = client.update_export_job(
            job_id=1,
            status=ExportJobStatus.COMPLETED,
            row_count=1000,
            size_bytes=1024,
        )

        assert result.status == ExportJobStatus.COMPLETED
        assert result.row_count == 1000

    @respx.mock
    def test_get_export_job_success(self, client: ControlPlaneClient) -> None:
        """Test successful export job retrieval."""
        respx.get("http://control-plane.test:8080/api/internal/export-jobs/1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "id": 1,
                        "snapshot_id": 123,
                        "job_type": "node",
                        "entity_name": "Customer",
                        "status": "submitted",  # ADR-025
                        "gcs_path": "gs://bucket/path/",
                    }
                },
            )
        )

        result = client.get_export_job(1)

        assert result.id == 1
        assert result.entity_name == "Customer"

    @respx.mock
    def test_check_all_jobs_complete_all_done(self, client: ControlPlaneClient) -> None:
        """Test checking if all jobs complete - all done."""
        respx.get("http://control-plane.test:8080/api/internal/snapshots/123/export-jobs").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": 1,
                            "status": "completed",
                            "snapshot_id": 123,
                            "job_type": "node",
                            "entity_name": "A",
                            "gcs_path": "gs://b/p/",
                        },
                        {
                            "id": 2,
                            "status": "completed",
                            "snapshot_id": 123,
                            "job_type": "node",
                            "entity_name": "B",
                            "gcs_path": "gs://b/p/",
                        },
                    ]
                },
            )
        )

        all_complete, any_failed = client.check_all_jobs_complete(123)

        assert all_complete is True
        assert any_failed is False

    @respx.mock
    def test_check_all_jobs_complete_some_failed(self, client: ControlPlaneClient) -> None:
        """Test checking if all jobs complete - some failed."""
        respx.get("http://control-plane.test:8080/api/internal/snapshots/123/export-jobs").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": 1,
                            "status": "completed",
                            "snapshot_id": 123,
                            "job_type": "node",
                            "entity_name": "A",
                            "gcs_path": "gs://b/p/",
                        },
                        {
                            "id": 2,
                            "status": "failed",
                            "snapshot_id": 123,
                            "job_type": "node",
                            "entity_name": "B",
                            "gcs_path": "gs://b/p/",
                        },
                    ]
                },
            )
        )

        all_complete, any_failed = client.check_all_jobs_complete(123)

        assert all_complete is True
        assert any_failed is True

    # =============================================================================
    # SNAPSHOT TESTS DISABLED
    # These tests are commented out as snapshot functionality has been disabled.
    # =============================================================================
    # @respx.mock
    # def test_finalize_snapshot_success(self, client: ControlPlaneClient) -> None:
    #     """Test successful snapshot finalization."""
    #     respx.patch("http://control-plane.test:8080/api/internal/snapshots/123/status").mock(
    #         return_value=httpx.Response(200, json={"success": True})
    #     )
    #
    #     # Should not raise
    #     client.finalize_snapshot(
    #         123,
    #         success=True,
    #         node_counts={"Customer": 100},
    #         edge_counts={"PURCHASED": 500},
    #         size_bytes=1024,
    #     )
    #
    # @respx.mock
    # def test_finalize_snapshot_failure(self, client: ControlPlaneClient) -> None:
    #     """Test snapshot finalization on failure."""
    #     respx.patch("http://control-plane.test:8080/api/internal/snapshots/123/status").mock(
    #         return_value=httpx.Response(200, json={"success": True})
    #     )
    #
    #     # Should not raise
    #     client.finalize_snapshot(
    #         123,
    #         success=False,
    #         error_message="Export failed",
    #     )


class TestControlPlaneClientFromConfig:
    """Tests for ControlPlaneClient.from_config()."""

    def test_from_config_creates_client(self, mock_env: None) -> None:
        """Test that from_config creates properly configured client."""
        from export_worker.config import ControlPlaneConfig

        config = ControlPlaneConfig()
        client = ControlPlaneClient.from_config(config)

        assert client.base_url == "http://control-plane.test:8080"
