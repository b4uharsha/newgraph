"""Integration tests for internal instances API."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from control_plane.config import Settings
from control_plane.main import create_app


# =============================================================================
# SNAPSHOT API TESTS DISABLED
# These tests are commented out because they depend on the deprecated snapshot
# API (POST /api/snapshots) which has been removed. Use create_from_mapping()
# workflow instead.
# =============================================================================
# class TestInternalInstancesAPI:
#     """Integration tests for /api/internal/instances endpoints."""
#
#     @pytest.fixture
#     def app(self, settings: Settings, db_engine) -> FastAPI:
#         """Use settings from conftest.py (PostgreSQL testcontainer).
#
#         db_engine fixture ensures tables are created/dropped for each test.
#         """
#         return create_app(settings)
#
#     @pytest.fixture
#     def client(self, app: FastAPI) -> TestClient:
#         with TestClient(app) as client:
#             yield client
#
#     @pytest.fixture
#     def auth_headers(self) -> dict:
#         return {
#             "X-Username": "test.user",
#             "X-User-Role": "analyst",
#         }
#
#     @pytest.fixture
#     def internal_headers(self) -> dict:
#         return {
#             "X-Internal-Api-Key": "test-internal-key",
#         }
#
#     @pytest.fixture
#     def instance_id(self, client: TestClient, auth_headers: dict) -> int:
#         """Create a mapping, snapshot, and instance, return instance ID."""
#         # Create mapping
#         response = client.post(
#             "/api/mappings",
#             json={
#                 "name": "Instance Test Mapping",
#                 "node_definitions": [
#                     {
#                         "label": "Person",
#                         "sql": "SELECT id, name FROM people",
#                         "primary_key": {"name": "id", "type": "STRING"},
#                         "properties": [{"name": "name", "type": "STRING"}],
#                     },
#                 ],
#             },
#             headers=auth_headers,
#         )
#         mapping_id = response.json()["data"]["id"]
#
#         # Create snapshot
#         response = client.post(
#             "/api/snapshots",
#             json={
#                 "mapping_id": mapping_id,
#                 "name": "Instance Test Snapshot",
#             },
#             headers=auth_headers,
#         )
#         snapshot_id = response.json()["data"]["id"]
#
#         # Mark snapshot as ready
#         client.patch(
#             f"/api/internal/snapshots/{snapshot_id}/status",
#             json={"status": "ready"},
#             headers={"X-Internal-Api-Key": "test-internal-key"},
#         )
#
#         # Create instance
#         response = client.post(
#             "/api/instances",
#             json={
#                 "snapshot_id": snapshot_id,
#                 "name": "Test Instance",
#                 "wrapper_type": "ryugraph",
#             },
#             headers=auth_headers,
#         )
#         return response.json()["data"]["id"]
#
#     def test_update_instance_metrics(
#         self, client: TestClient, internal_headers: dict, instance_id: int
#     ):
#         """Test updating instance metrics."""
#         response = client.put(
#             f"/api/internal/instances/{instance_id}/metrics",
#             json={
#                 "memory_usage_bytes": 536870912,
#                 "disk_usage_bytes": 1073741824,
#             },
#             headers=internal_headers,
#         )
#
#         assert response.status_code == 200
#         data = response.json()
#         assert data["data"]["updated"] is True
#
#         # Verify the update
#         get_response = client.get(
#             f"/api/instances/{instance_id}",
#             headers={"X-Username": "test.user", "X-User-Role": "analyst"},
#         )
#         instance_data = get_response.json()["data"]
#         assert instance_data["memory_usage_bytes"] == 536870912
#         assert instance_data["disk_usage_bytes"] == 1073741824
#
#     def test_update_instance_metrics_with_activity(
#         self, client: TestClient, internal_headers: dict, instance_id: int
#     ):
#         """Test updating instance metrics with activity timestamp."""
#         response = client.put(
#             f"/api/internal/instances/{instance_id}/metrics",
#             json={
#                 "memory_usage_bytes": 268435456,
#                 "last_activity_at": "2025-01-15T14:00:00Z",
#             },
#             headers=internal_headers,
#         )
#
#         assert response.status_code == 200
#         assert response.json()["data"]["updated"] is True
#
#     def test_update_instance_metrics_not_found(self, client: TestClient, internal_headers: dict):
#         """Test updating metrics for non-existent instance fails."""
#         response = client.put(
#             "/api/internal/instances/99999/metrics",
#             json={
#                 "memory_usage_bytes": 536870912,
#             },
#             headers=internal_headers,
#         )
#
#         assert response.status_code == 404
#
#     def test_update_instance_metrics_unauthorized(self, client: TestClient, instance_id: int):
#         """Test updating metrics without API key fails."""
#         response = client.put(
#             f"/api/internal/instances/{instance_id}/metrics",
#             json={
#                 "memory_usage_bytes": 536870912,
#             },
#             # No internal headers
#         )
#
#         assert response.status_code == 401
#
#     def test_update_instance_progress(
#         self, client: TestClient, internal_headers: dict, instance_id: int
#     ):
#         """Test updating instance loading progress."""
#         response = client.put(
#             f"/api/internal/instances/{instance_id}/progress",
#             json={
#                 "phase": "loading_nodes",
#                 "steps": [
#                     {"name": "pod_scheduled", "status": "completed"},
#                     {"name": "schema_created", "status": "completed"},
#                     {"name": "Person", "type": "node", "status": "in_progress"},
#                 ],
#             },
#             headers=internal_headers,
#         )
#
#         assert response.status_code == 200
#         data = response.json()
#         assert data["data"]["updated"] is True
#
#         # Verify the update
#         get_response = client.get(
#             f"/api/instances/{instance_id}",
#             headers={"X-Username": "test.user", "X-User-Role": "analyst"},
#         )
#         instance_data = get_response.json()["data"]
#         assert instance_data["progress"]["phase"] == "loading_nodes"
#         assert len(instance_data["progress"]["steps"]) == 3
#
#     def test_update_instance_progress_complete_loading(
#         self, client: TestClient, internal_headers: dict, instance_id: int
#     ):
#         """Test updating instance progress to show completed loading."""
#         response = client.put(
#             f"/api/internal/instances/{instance_id}/progress",
#             json={
#                 "phase": "ready",
#                 "steps": [
#                     {"name": "pod_scheduled", "status": "completed"},
#                     {"name": "schema_created", "status": "completed"},
#                     {"name": "Person", "type": "node", "status": "completed", "row_count": 10000},
#                 ],
#             },
#             headers=internal_headers,
#         )
#
#         assert response.status_code == 200
#         assert response.json()["data"]["updated"] is True
#
#     def test_update_instance_progress_not_found(self, client: TestClient, internal_headers: dict):
#         """Test updating progress for non-existent instance fails."""
#         response = client.put(
#             "/api/internal/instances/99999/progress",
#             json={
#                 "phase": "loading_nodes",
#                 "steps": [],
#             },
#             headers=internal_headers,
#         )
#
#         assert response.status_code == 404
#
#     def test_update_instance_progress_unauthorized(self, client: TestClient, instance_id: int):
#         """Test updating progress without API key fails."""
#         response = client.put(
#             f"/api/internal/instances/{instance_id}/progress",
#             json={
#                 "phase": "loading_nodes",
#                 "steps": [],
#             },
#             # No internal headers
#         )
#
#         assert response.status_code == 401
#
#     def test_update_instance_status(
#         self, client: TestClient, internal_headers: dict, instance_id: int
#     ):
#         """Test updating instance status."""
#         response = client.patch(
#             f"/api/internal/instances/{instance_id}/status",
#             json={
#                 "status": "running",
#                 "pod_name": "graph-instance-123",
#                 "pod_ip": "10.0.0.5",
#                 "instance_url": "http://10.0.0.5:8080",
#             },
#             headers=internal_headers,
#         )
#
#         assert response.status_code == 200
#         data = response.json()
#         assert data["data"]["status"] == "running"
#         assert data["data"]["pod_name"] == "graph-instance-123"
#         assert data["data"]["instance_url"] == "http://10.0.0.5:8080"
#         assert data["data"]["started_at"] is not None
#
#     def test_update_instance_status_to_failed(
#         self, client: TestClient, internal_headers: dict, instance_id: int
#     ):
#         """Test updating instance status to failed."""
#         response = client.patch(
#             f"/api/internal/instances/{instance_id}/status",
#             json={
#                 "status": "failed",
#                 "error_message": "Out of memory",
#             },
#             headers=internal_headers,
#         )
#
#         assert response.status_code == 200
#         data = response.json()
#         assert data["data"]["status"] == "failed"
#         assert data["data"]["error_message"] == "Out of memory"
