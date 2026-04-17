# =============================================================================
# SNAPSHOT TESTS DISABLED
# These tests are commented out as snapshot functionality has been disabled.
# =============================================================================

# """Integration tests for snapshots API."""
#
# import pytest
# from fastapi import FastAPI
# from fastapi.testclient import TestClient
#
# from control_plane.config import Settings
# from control_plane.main import create_app
#
#
# class TestSnapshotsAPI:
#     """Integration tests for /api/snapshots endpoints."""
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
#     def mapping_id(self, client: TestClient, auth_headers: dict) -> int:
#         """Create a mapping and return its ID."""
#         response = client.post(
#             "/api/mappings",
#             json={
#                 "name": "Test Mapping",
#                 "node_definitions": [
#                     {
#                         "label": "Customer",
#                         "sql": "SELECT id, name FROM customers",
#                         "primary_key": {"name": "id", "type": "STRING"},
#                         "properties": [{"name": "name", "type": "STRING"}],
#                     },
#                 ],
#             },
#             headers=auth_headers,
#         )
#         return response.json()["data"]["id"]
#
#     def test_create_snapshot(self, client: TestClient, auth_headers: dict, mapping_id: int):
#         """Test creating a snapshot from a mapping."""
#         response = client.post(
#             "/api/snapshots",
#             json={
#                 "mapping_id": mapping_id,
#                 "name": "Test Snapshot",
#                 "description": "A test snapshot",
#             },
#             headers=auth_headers,
#         )
#
#         assert response.status_code == 201
#         data = response.json()
#         assert data["data"]["name"] == "Test Snapshot"
#         assert data["data"]["mapping_id"] == mapping_id
#         assert data["data"]["status"] == "pending"
#         assert data["data"]["owner_username"] == "test.user"
#
#     def test_create_snapshot_invalid_mapping(self, client: TestClient, auth_headers: dict):
#         """Test creating snapshot with invalid mapping fails."""
#         response = client.post(
#             "/api/snapshots",
#             json={
#                 "mapping_id": 99999,
#                 "name": "Invalid Snapshot",
#             },
#             headers=auth_headers,
#         )
#
#         assert response.status_code == 404
#
#     def test_get_snapshot(self, client: TestClient, auth_headers: dict, mapping_id: int):
#         """Test getting a snapshot by ID."""
#         # Create snapshot
#         create_response = client.post(
#             "/api/snapshots",
#             json={
#                 "mapping_id": mapping_id,
#                 "name": "Get Test",
#             },
#             headers=auth_headers,
#         )
#         snapshot_id = create_response.json()["data"]["id"]
#
#         # Get it
#         response = client.get(
#             f"/api/snapshots/{snapshot_id}",
#             headers=auth_headers,
#         )
#
#         assert response.status_code == 200
#         data = response.json()
#         assert data["data"]["id"] == snapshot_id
#         assert data["data"]["name"] == "Get Test"
#
#     def test_list_snapshots(self, client: TestClient, auth_headers: dict, mapping_id: int):
#         """Test listing snapshots."""
#         # Create snapshots
#         for i in range(3):
#             client.post(
#                 "/api/snapshots",
#                 json={
#                     "mapping_id": mapping_id,
#                     "name": f"Snapshot {i}",
#                 },
#                 headers=auth_headers,
#             )
#
#         # List all
#         response = client.get(
#             "/api/snapshots",
#             headers=auth_headers,
#         )
#
#         assert response.status_code == 200
#         data = response.json()
#         assert len(data["data"]) == 3
#
#     def test_list_snapshots_filter_by_mapping(
#         self, client: TestClient, auth_headers: dict, mapping_id: int
#     ):
#         """Test filtering snapshots by mapping ID."""
#         # Create snapshot
#         client.post(
#             "/api/snapshots",
#             json={
#                 "mapping_id": mapping_id,
#                 "name": "Filter Test",
#             },
#             headers=auth_headers,
#         )
#
#         # Filter by mapping
#         response = client.get(
#             f"/api/snapshots?mapping_id={mapping_id}",
#             headers=auth_headers,
#         )
#
#         assert response.status_code == 200
#         data = response.json()
#         assert all(s["mapping_id"] == mapping_id for s in data["data"])
#
#     def test_delete_snapshot(self, client: TestClient, auth_headers: dict, mapping_id: int):
#         """Test deleting a snapshot."""
#         # Create snapshot
#         create_response = client.post(
#             "/api/snapshots",
#             json={
#                 "mapping_id": mapping_id,
#                 "name": "Delete Test",
#             },
#             headers=auth_headers,
#         )
#         snapshot_id = create_response.json()["data"]["id"]
#
#         # Delete it
#         response = client.delete(
#             f"/api/snapshots/{snapshot_id}",
#             headers=auth_headers,
#         )
#
#         assert response.status_code == 204
#
#         # Verify gone
#         get_response = client.get(
#             f"/api/snapshots/{snapshot_id}",
#             headers=auth_headers,
#         )
#         assert get_response.status_code == 404
#
#     def test_delete_snapshot_permission_denied(
#         self, client: TestClient, auth_headers: dict, mapping_id: int
#     ):
#         """Test other user cannot delete snapshot."""
#         # Create snapshot
#         create_response = client.post(
#             "/api/snapshots",
#             json={
#                 "mapping_id": mapping_id,
#                 "name": "Permission Test",
#             },
#             headers=auth_headers,
#         )
#         snapshot_id = create_response.json()["data"]["id"]
#
#         # Try to delete as different user
#         other_headers = {
#             "X-Username": "other.user",
#             "X-User-Role": "analyst",
#         }
#         response = client.delete(
#             f"/api/snapshots/{snapshot_id}",
#             headers=other_headers,
#         )
#
#         assert response.status_code == 403
#
#     def test_update_snapshot(self, client: TestClient, auth_headers: dict, mapping_id: int):
#         """Test updating snapshot metadata."""
#         # Create snapshot
#         create_response = client.post(
#             "/api/snapshots",
#             json={
#                 "mapping_id": mapping_id,
#                 "name": "Original Name",
#                 "description": "Original description",
#             },
#             headers=auth_headers,
#         )
#         snapshot_id = create_response.json()["data"]["id"]
#
#         # Update it
#         response = client.put(
#             f"/api/snapshots/{snapshot_id}",
#             json={
#                 "name": "Updated Name",
#                 "description": "Updated description",
#             },
#             headers=auth_headers,
#         )
#
#         assert response.status_code == 200
#         data = response.json()
#         assert data["data"]["name"] == "Updated Name"
#         assert data["data"]["description"] == "Updated description"
#
#     def test_update_snapshot_permission_denied(
#         self, client: TestClient, auth_headers: dict, mapping_id: int
#     ):
#         """Test other user cannot update snapshot."""
#         # Create snapshot
#         create_response = client.post(
#             "/api/snapshots",
#             json={
#                 "mapping_id": mapping_id,
#                 "name": "Permission Test",
#             },
#             headers=auth_headers,
#         )
#         snapshot_id = create_response.json()["data"]["id"]
#
#         # Try to update as different user
#         other_headers = {
#             "X-Username": "other.user",
#             "X-User-Role": "analyst",
#         }
#         response = client.put(
#             f"/api/snapshots/{snapshot_id}",
#             json={"name": "Hacked Name"},
#             headers=other_headers,
#         )
#
#         assert response.status_code == 403
#
#     def test_update_snapshot_not_found(self, client: TestClient, auth_headers: dict):
#         """Test updating non-existent snapshot."""
#         response = client.put(
#             "/api/snapshots/99999",
#             json={"name": "Does Not Exist"},
#             headers=auth_headers,
#         )
#
#         assert response.status_code == 404
#
#     def test_update_snapshot_lifecycle(
#         self, client: TestClient, auth_headers: dict, mapping_id: int
#     ):
#         """Test updating snapshot lifecycle settings."""
#         # Create snapshot
#         create_response = client.post(
#             "/api/snapshots",
#             json={
#                 "mapping_id": mapping_id,
#                 "name": "Lifecycle Test",
#             },
#             headers=auth_headers,
#         )
#         snapshot_id = create_response.json()["data"]["id"]
#
#         # Update lifecycle
#         response = client.put(
#             f"/api/snapshots/{snapshot_id}/lifecycle",
#             json={
#                 "ttl": "P30D",
#                 "inactivity_timeout": "PT12H",
#             },
#             headers=auth_headers,
#         )
#
#         assert response.status_code == 200
#         data = response.json()
#         assert data["data"]["ttl"] == "P30D"
#         assert data["data"]["inactivity_timeout"] == "PT12H"
#
#     def test_update_snapshot_lifecycle_permission_denied(
#         self, client: TestClient, auth_headers: dict, mapping_id: int
#     ):
#         """Test other user cannot update snapshot lifecycle."""
#         # Create snapshot
#         create_response = client.post(
#             "/api/snapshots",
#             json={
#                 "mapping_id": mapping_id,
#                 "name": "Lifecycle Permission Test",
#             },
#             headers=auth_headers,
#         )
#         snapshot_id = create_response.json()["data"]["id"]
#
#         # Try to update as different user
#         other_headers = {
#             "X-Username": "other.user",
#             "X-User-Role": "analyst",
#         }
#         response = client.put(
#             f"/api/snapshots/{snapshot_id}/lifecycle",
#             json={"ttl": "P1D"},
#             headers=other_headers,
#         )
#
#         assert response.status_code == 403
