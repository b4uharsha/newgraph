"""Integration tests for internal export jobs API."""

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
# class TestInternalExportJobsAPI:
#     """Integration tests for /api/internal export job endpoints."""
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
#     def snapshot_with_jobs(self, client: TestClient, auth_headers: dict) -> dict:
#         """Create a mapping and snapshot with export jobs, return snapshot and job info."""
#         # Create mapping with node and edge
#         response = client.post(
#             "/api/mappings",
#             json={
#                 "name": "Export Test Mapping",
#                 "node_definitions": [
#                     {
#                         "label": "Person",
#                         "sql": "SELECT id, name FROM people",
#                         "primary_key": {"name": "id", "type": "STRING"},
#                         "properties": [{"name": "name", "type": "STRING"}],
#                     },
#                 ],
#                 "edge_definitions": [
#                     {
#                         "type": "KNOWS",
#                         "sql": "SELECT src, tgt FROM knows",
#                         "from_node": "Person",
#                         "to_node": "Person",
#                         "from_key": "src",
#                         "to_key": "tgt",
#                         "properties": [],
#                     },
#                 ],
#             },
#             headers=auth_headers,
#         )
#         mapping_id = response.json()["data"]["id"]
#
#         # Create snapshot (this automatically creates export jobs)
#         response = client.post(
#             "/api/snapshots",
#             json={
#                 "mapping_id": mapping_id,
#                 "name": "Export Test Snapshot",
#             },
#             headers=auth_headers,
#         )
#         snapshot_id = response.json()["data"]["id"]
#
#         return {
#             "snapshot_id": snapshot_id,
#             "mapping_id": mapping_id,
#         }
#
#     def test_list_export_jobs(
#         self, client: TestClient, internal_headers: dict, snapshot_with_jobs: dict
#     ):
#         """Test listing export jobs for a snapshot."""
#         snapshot_id = snapshot_with_jobs["snapshot_id"]
#
#         response = client.get(
#             f"/api/internal/snapshots/{snapshot_id}/export-jobs",
#             headers=internal_headers,
#         )
#
#         assert response.status_code == 200
#         data = response.json()
#         # Should have 2 jobs: 1 node (Person) + 1 edge (KNOWS)
#         assert len(data["data"]) == 2
#
#         # Verify job types
#         job_types = {j["job_type"] for j in data["data"]}
#         assert job_types == {"node", "edge"}
#
#         # Verify entity names
#         entity_names = {j["entity_name"] for j in data["data"]}
#         assert entity_names == {"Person", "KNOWS"}
#
#         # All should be pending initially
#         for job in data["data"]:
#             assert job["status"] == "pending"
#
#     def test_list_export_jobs_filter_by_status(
#         self, client: TestClient, internal_headers: dict, snapshot_with_jobs: dict
#     ):
#         """Test filtering export jobs by status."""
#         snapshot_id = snapshot_with_jobs["snapshot_id"]
#
#         # Filter by pending (should return all)
#         response = client.get(
#             f"/api/internal/snapshots/{snapshot_id}/export-jobs?status_filter=pending",
#             headers=internal_headers,
#         )
#
#         assert response.status_code == 200
#         assert len(response.json()["data"]) == 2
#
#         # Filter by running (should be empty)
#         response = client.get(
#             f"/api/internal/snapshots/{snapshot_id}/export-jobs?status_filter=running",
#             headers=internal_headers,
#         )
#
#         assert response.status_code == 200
#         assert len(response.json()["data"]) == 0
#
#     def test_list_export_jobs_unauthorized(self, client: TestClient, snapshot_with_jobs: dict):
#         """Test listing export jobs without API key fails."""
#         snapshot_id = snapshot_with_jobs["snapshot_id"]
#
#         response = client.get(
#             f"/api/internal/snapshots/{snapshot_id}/export-jobs",
#             # No internal headers
#         )
#
#         assert response.status_code == 401
#
#     def test_update_export_job_to_running(
#         self, client: TestClient, internal_headers: dict, snapshot_with_jobs: dict
#     ):
#         """Test updating export job to submitted status.
#
#         Note: The API accepts both 'running' (legacy) and 'submitted' (ADR-025)
#         in the request, but always returns 'submitted' as the status.
#         """
#         snapshot_id = snapshot_with_jobs["snapshot_id"]
#
#         # Get the job IDs
#         list_response = client.get(
#             f"/api/internal/snapshots/{snapshot_id}/export-jobs",
#             headers=internal_headers,
#         )
#         job_id = list_response.json()["data"][0]["id"]
#
#         # Update to running (legacy) - API converts to 'submitted' per ADR-025
#         response = client.patch(
#             f"/api/internal/export-jobs/{job_id}",
#             json={
#                 "status": "running",
#                 "starburst_query_id": "query-123",
#                 "next_uri": "http://starburst/v1/query/123/1",
#             },
#             headers=internal_headers,
#         )
#
#         assert response.status_code == 200
#         data = response.json()
#         # ADR-025: 'running' is converted to 'submitted'
#         assert data["data"]["status"] == "submitted"
#         assert data["data"]["starburst_query_id"] == "query-123"
#         assert data["data"]["next_uri"] == "http://starburst/v1/query/123/1"
#         assert data["data"]["submitted_at"] is not None
#
#     def test_update_export_job_to_running_missing_fields(
#         self, client: TestClient, internal_headers: dict, snapshot_with_jobs: dict
#     ):
#         """Test updating to running without required fields fails."""
#         snapshot_id = snapshot_with_jobs["snapshot_id"]
#
#         # Get the job IDs
#         list_response = client.get(
#             f"/api/internal/snapshots/{snapshot_id}/export-jobs",
#             headers=internal_headers,
#         )
#         job_id = list_response.json()["data"][0]["id"]
#
#         # Try to update to running without query ID
#         response = client.patch(
#             f"/api/internal/export-jobs/{job_id}",
#             json={
#                 "status": "running",
#             },
#             headers=internal_headers,
#         )
#
#         assert response.status_code == 400
#         assert response.json()["detail"]["code"] == "INVALID_REQUEST"
#
#     def test_update_export_job_to_completed(
#         self, client: TestClient, internal_headers: dict, snapshot_with_jobs: dict
#     ):
#         """Test updating export job to completed status."""
#         snapshot_id = snapshot_with_jobs["snapshot_id"]
#
#         # Get the job IDs
#         list_response = client.get(
#             f"/api/internal/snapshots/{snapshot_id}/export-jobs",
#             headers=internal_headers,
#         )
#         job_id = list_response.json()["data"][0]["id"]
#
#         # First mark as running
#         client.patch(
#             f"/api/internal/export-jobs/{job_id}",
#             json={
#                 "status": "running",
#                 "starburst_query_id": "query-123",
#                 "next_uri": "http://starburst/v1/query/123/1",
#             },
#             headers=internal_headers,
#         )
#
#         # Then mark as completed
#         response = client.patch(
#             f"/api/internal/export-jobs/{job_id}",
#             json={
#                 "status": "completed",
#                 "row_count": 1000,
#                 "size_bytes": 50000,
#             },
#             headers=internal_headers,
#         )
#
#         assert response.status_code == 200
#         data = response.json()
#         assert data["data"]["status"] == "completed"
#         assert data["data"]["row_count"] == 1000
#         assert data["data"]["size_bytes"] == 50000
#         assert data["data"]["completed_at"] is not None
#
#     def test_update_export_job_to_completed_missing_fields(
#         self, client: TestClient, internal_headers: dict, snapshot_with_jobs: dict
#     ):
#         """Test updating to completed without required fields fails."""
#         snapshot_id = snapshot_with_jobs["snapshot_id"]
#
#         # Get the job IDs
#         list_response = client.get(
#             f"/api/internal/snapshots/{snapshot_id}/export-jobs",
#             headers=internal_headers,
#         )
#         job_id = list_response.json()["data"][0]["id"]
#
#         # Try to mark as completed without row_count
#         response = client.patch(
#             f"/api/internal/export-jobs/{job_id}",
#             json={
#                 "status": "completed",
#             },
#             headers=internal_headers,
#         )
#
#         assert response.status_code == 400
#         assert response.json()["detail"]["code"] == "INVALID_REQUEST"
#
#     def test_update_export_job_to_failed(
#         self, client: TestClient, internal_headers: dict, snapshot_with_jobs: dict
#     ):
#         """Test updating export job to failed status."""
#         snapshot_id = snapshot_with_jobs["snapshot_id"]
#
#         # Get the job IDs
#         list_response = client.get(
#             f"/api/internal/snapshots/{snapshot_id}/export-jobs",
#             headers=internal_headers,
#         )
#         job_id = list_response.json()["data"][0]["id"]
#
#         # Mark as failed
#         response = client.patch(
#             f"/api/internal/export-jobs/{job_id}",
#             json={
#                 "status": "failed",
#                 "error_message": "Query timed out",
#             },
#             headers=internal_headers,
#         )
#
#         assert response.status_code == 200
#         data = response.json()
#         assert data["data"]["status"] == "failed"
#         assert data["data"]["error_message"] == "Query timed out"
#         assert data["data"]["completed_at"] is not None
#
#     def test_update_export_job_not_found(self, client: TestClient, internal_headers: dict):
#         """Test updating non-existent export job fails."""
#         response = client.patch(
#             "/api/internal/export-jobs/99999",
#             json={
#                 "status": "running",
#                 "starburst_query_id": "query-123",
#                 "next_uri": "http://starburst/v1/query/123/1",
#             },
#             headers=internal_headers,
#         )
#
#         assert response.status_code == 404
#
#     def test_update_export_job_unauthorized(
#         self, client: TestClient, snapshot_with_jobs: dict, internal_headers: dict
#     ):
#         """Test updating export job without API key fails."""
#         snapshot_id = snapshot_with_jobs["snapshot_id"]
#
#         # Get the job IDs
#         list_response = client.get(
#             f"/api/internal/snapshots/{snapshot_id}/export-jobs",
#             headers=internal_headers,
#         )
#         job_id = list_response.json()["data"][0]["id"]
#
#         # Try to update without auth
#         response = client.patch(
#             f"/api/internal/export-jobs/{job_id}",
#             json={
#                 "status": "running",
#                 "starburst_query_id": "query-123",
#                 "next_uri": "http://starburst/v1/query/123/1",
#             },
#             # No internal headers
#         )
#
#         assert response.status_code == 401
#
#     def test_create_export_jobs_when_already_exist(
#         self, client: TestClient, internal_headers: dict, snapshot_with_jobs: dict
#     ):
#         """Test that creating export jobs fails when they already exist."""
#         snapshot_id = snapshot_with_jobs["snapshot_id"]
#
#         # Jobs were already created by snapshot creation, trying to create more should fail
#         response = client.post(
#             f"/api/internal/snapshots/{snapshot_id}/export-jobs",
#             json={
#                 "jobs": [
#                     {
#                         "job_type": "node",
#                         "entity_name": "AnotherNode",
#                         "starburst_query_id": "query_123",
#                         "next_uri": "http://starburst/v1/query/123/1",
#                         "gcs_path": "gs://bucket/snapshot/nodes/AnotherNode/",
#                     },
#                 ]
#             },
#             headers=internal_headers,
#         )
#
#         assert response.status_code == 409
#         assert response.json()["detail"]["code"] == "JOBS_ALREADY_EXIST"
