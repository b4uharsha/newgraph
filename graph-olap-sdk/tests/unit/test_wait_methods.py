"""Tests for wait_until_ready and create_and_wait methods.

These are critical paths that poll for resource readiness.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from graph_olap.exceptions import InstanceFailedError, SnapshotFailedError, TimeoutError
from graph_olap.resources.instances import InstanceResource

# SnapshotResource is deprecated - explicit snapshot creation APIs are no longer available
# from graph_olap.resources.snapshots import SnapshotResource


# =============================================================================
# SNAPSHOT TESTS DISABLED
# These tests are commented out as snapshot functionality has been disabled.
# =============================================================================
# class TestSnapshotWaitUntilReady:
#     """Tests for SnapshotResource.wait_until_ready()."""
#
#     @pytest.fixture
#     def mock_http(self) -> MagicMock:
#         return MagicMock()
#
#     @pytest.fixture
#     def resource(self, mock_http: MagicMock) -> SnapshotResource:
#         return SnapshotResource(mock_http)
#
#     def test_returns_immediately_if_ready(self, resource: SnapshotResource, mock_http: MagicMock):
#         """Returns immediately if snapshot is already ready."""
#         mock_http.get.return_value = {
#             "data": {
#                 "id": 1,
#                 "mapping_id": 1,
#                 "mapping_version": 1,
#                 "owner_username": "test_user",
#                 "name": "Test",
#                 "status": "ready",
#                 "created_at": "2025-01-15T10:00:00Z",
#                 "updated_at": "2025-01-15T10:05:00Z",
#             }
#         }
#
#         result = resource.wait_until_ready(1, timeout=10, poll_interval=1)
#
#         assert result.status == "ready"
#         assert mock_http.get.call_count == 1
#
#     @patch("time.sleep")
#     def test_polls_until_ready(
#         self, mock_sleep: MagicMock, resource: SnapshotResource, mock_http: MagicMock
#     ):
#         """Polls until snapshot becomes ready."""
#         creating_response = {
#             "data": {
#                 "id": 1,
#                 "mapping_id": 1,
#                 "mapping_version": 1,
#                 "owner_username": "test_user",
#                 "name": "Test",
#                 "status": "creating",
#                 "created_at": "2025-01-15T10:00:00Z",
#                 "updated_at": "2025-01-15T10:05:00Z",
#             }
#         }
#         ready_response = {
#             "data": {
#                 "id": 1,
#                 "mapping_id": 1,
#                 "mapping_version": 1,
#                 "owner_username": "test_user",
#                 "name": "Test",
#                 "status": "ready",
#                 "created_at": "2025-01-15T10:00:00Z",
#                 "updated_at": "2025-01-15T10:05:00Z",
#             }
#         }
#
#         mock_http.get.side_effect = [creating_response, creating_response, ready_response]
#
#         result = resource.wait_until_ready(1, timeout=60, poll_interval=1)
#
#         assert result.status == "ready"
#         assert mock_http.get.call_count == 3
#         assert mock_sleep.call_count == 2
#
#     def test_raises_on_failed(self, resource: SnapshotResource, mock_http: MagicMock):
#         """Raises SnapshotFailedError if snapshot fails."""
#         mock_http.get.return_value = {
#             "data": {
#                 "id": 1,
#                 "mapping_id": 1,
#                 "mapping_version": 1,
#                 "owner_username": "test_user",
#                 "name": "Test",
#                 "status": "failed",
#                 "error_message": "Export failed: connection refused",
#                 "created_at": "2025-01-15T10:00:00Z",
#                 "updated_at": "2025-01-15T10:05:00Z",
#             }
#         }
#
#         with pytest.raises(SnapshotFailedError, match="connection refused"):
#             resource.wait_until_ready(1, timeout=10)
#
#     @patch("time.time")
#     @patch("time.sleep")
#     def test_raises_on_timeout(
#         self,
#         mock_sleep: MagicMock,
#         mock_time: MagicMock,
#         resource: SnapshotResource,
#         mock_http: MagicMock,
#     ):
#         """Raises TimeoutError if timeout exceeded."""
#         # Simulate time passing beyond timeout
#         mock_time.side_effect = [0, 5, 15]  # Start, first check, second check (past 10s timeout)
#
#         mock_http.get.return_value = {
#             "data": {
#                 "id": 1,
#                 "mapping_id": 1,
#                 "mapping_version": 1,
#                 "owner_username": "test_user",
#                 "name": "Test",
#                 "status": "creating",
#                 "created_at": "2025-01-15T10:00:00Z",
#                 "updated_at": "2025-01-15T10:05:00Z",
#             }
#         }
#
#         with pytest.raises(TimeoutError, match="did not complete within 10s"):
#             resource.wait_until_ready(1, timeout=10, poll_interval=5)


class TestInstanceWaitUntilRunning:
    """Tests for InstanceResource.wait_until_running()."""

    @pytest.fixture
    def mock_http(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def mock_config(self) -> MagicMock:
        config = MagicMock()
        config.username = "test-user@example.com"
        return config

    @pytest.fixture
    def resource(self, mock_http: MagicMock, mock_config: MagicMock) -> InstanceResource:
        return InstanceResource(mock_http, mock_config)

    def test_returns_immediately_if_running(self, resource: InstanceResource, mock_http: MagicMock):
        """Returns immediately if instance is already running."""
        mock_http.get.return_value = {
            "data": {
                "id": 1,
                "snapshot_id": 1,
                "owner_username": "test_user",
                "wrapper_type": "ryugraph",
                "name": "Test",
                "status": "running",
                "instance_url": "https://instance-1.example.com",
                "created_at": "2025-01-15T10:00:00Z",
                "updated_at": "2025-01-15T10:05:00Z",
            }
        }

        result = resource.wait_until_running(1, timeout=10, poll_interval=1)

        assert result.status == "running"

    def test_raises_on_failed(self, resource: InstanceResource, mock_http: MagicMock):
        """Raises InstanceFailedError if instance fails."""
        mock_http.get.return_value = {
            "data": {
                "id": 1,
                "snapshot_id": 1,
                "owner_username": "test_user",
                "wrapper_type": "ryugraph",
                "name": "Test",
                "status": "failed",
                "error_message": "OOM: out of memory",
                "created_at": "2025-01-15T10:00:00Z",
                "updated_at": "2025-01-15T10:05:00Z",
            }
        }

        with pytest.raises(InstanceFailedError, match="OOM"):
            resource.wait_until_running(1, timeout=10)


# =============================================================================
# SNAPSHOT TESTS DISABLED
# These tests are commented out as snapshot functionality has been disabled.
# =============================================================================
# class TestSnapshotProgressPolling:
#     """Tests for create_and_wait progress polling."""
#
#     @pytest.fixture
#     def mock_http(self) -> MagicMock:
#         return MagicMock()
#
#     @pytest.fixture
#     def resource(self, mock_http: MagicMock) -> SnapshotResource:
#         return SnapshotResource(mock_http)
#
#     @patch("time.sleep")
#     @patch("time.time")
#     def test_create_and_wait_calls_progress_callback(
#         self,
#         mock_time: MagicMock,
#         mock_sleep: MagicMock,
#         resource: SnapshotResource,
#         mock_http: MagicMock,
#     ):
#         """create_and_wait calls on_progress callback."""
#         mock_time.side_effect = [0, 1, 2, 3]
#
#         # Create returns pending snapshot
#         mock_http.post.return_value = {
#             "data": {
#                 "id": 1,
#                 "mapping_id": 1,
#                 "mapping_version": 1,
#                 "owner_username": "test_user",
#                 "name": "Test",
#                 "status": "pending",
#                 "created_at": "2025-01-15T10:00:00Z",
#                 "updated_at": "2025-01-15T10:00:00Z",
#             }
#         }
#
#         # Snapshot in creating state (for get())
#         snapshot_creating = {
#             "data": {
#                 "id": 1,
#                 "mapping_id": 1,
#                 "mapping_version": 1,
#                 "owner_username": "test_user",
#                 "name": "Test",
#                 "status": "creating",
#                 "created_at": "2025-01-15T10:00:00Z",
#                 "updated_at": "2025-01-15T10:01:00Z",
#             }
#         }
#         # Progress data (for get_progress())
#         progress_exporting = {
#             "data": {
#                 "jobs_total": 2,
#                 "jobs_pending": 0,
#                 "jobs_claimed": 0,
#                 "jobs_submitted": 1,
#                 "jobs_completed": 1,
#                 "jobs_failed": 0,
#                 "jobs": [],
#             }
#         }
#         # Final snapshot ready (for get())
#         snapshot_ready = {
#             "data": {
#                 "id": 1,
#                 "mapping_id": 1,
#                 "mapping_version": 1,
#                 "owner_username": "test_user",
#                 "name": "Test",
#                 "status": "ready",
#                 "created_at": "2025-01-15T10:00:00Z",
#                 "updated_at": "2025-01-15T10:05:00Z",
#             }
#         }
#         # Progress when ready (for get_progress())
#         progress_ready = {
#             "data": {
#                 "jobs_total": 2,
#                 "jobs_pending": 0,
#                 "jobs_claimed": 0,
#                 "jobs_submitted": 0,
#                 "jobs_completed": 2,
#                 "jobs_failed": 0,
#                 "jobs": [],
#             }
#         }
#
#         # Order: get() -> get_progress() -> get() -> get_progress()
#         mock_http.get.side_effect = [snapshot_creating, progress_exporting, snapshot_ready, progress_ready]
#
#         # Track progress calls
#         progress_calls = []
#
#         def on_progress(phase: str, completed: int, total: int):
#             progress_calls.append((phase, completed, total))
#
#         result = resource.create_and_wait(
#             mapping_id=1,
#             name="Test",
#             timeout=60,
#             poll_interval=1,
#             on_progress=on_progress,
#         )
#
#         assert result.status == "ready"
#         assert len(progress_calls) == 2
#         assert progress_calls[0][0] == "exporting"
#         assert progress_calls[1][0] == "ready"
