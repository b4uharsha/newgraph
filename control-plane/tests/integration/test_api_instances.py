"""Integration tests for instances API."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from control_plane.config import Settings
from control_plane.main import create_app


# =============================================================================
# SNAPSHOT API TESTS DISABLED
# These tests are commented out because they depend on the deprecated snapshot
# API (POST /api/snapshots) which has been removed. Use create_from_mapping()
# workflow instead (see TestInstancesFromMappingAPI below).
# =============================================================================
# class TestInstancesAPI:
#     """Integration tests for /api/instances endpoints."""
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
#     def ready_snapshot_id(
#         self, client: TestClient, auth_headers: dict, internal_headers: dict
#     ) -> int:
#         """Create a mapping and ready snapshot, return snapshot ID."""
#         # Create mapping
#         mapping_response = client.post(
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
#         mapping_id = mapping_response.json()["data"]["id"]
#
#         # Create snapshot
#         snapshot_response = client.post(
#             "/api/snapshots",
#             json={
#                 "mapping_id": mapping_id,
#                 "name": "Test Snapshot",
#             },
#             headers=auth_headers,
#         )
#         snapshot_id = snapshot_response.json()["data"]["id"]
#
#         # Mark as ready via internal API
#         client.patch(
#             f"/api/internal/snapshots/{snapshot_id}/status",
#             json={
#                 "status": "ready",
#                 "size_bytes": 1024000,
#                 "node_counts": {"Customer": 1000},
#             },
#             headers=internal_headers,
#         )
#
#         return snapshot_id
#
#     def test_create_instance(self, client: TestClient, auth_headers: dict, ready_snapshot_id: int):
#         """Test creating an instance from a ready snapshot with ryugraph wrapper."""
#         response = client.post(
#             "/api/instances",
#             json={
#                 "snapshot_id": ready_snapshot_id,
#                 "wrapper_type": "ryugraph",
#                 "name": "Test Instance",
#                 "description": "A test instance",
#             },
#             headers=auth_headers,
#         )
#
#         assert response.status_code == 201
#         data = response.json()
#         assert data["data"]["name"] == "Test Instance"
#         assert data["data"]["snapshot_id"] == ready_snapshot_id
#         assert data["data"]["status"] == "starting"
#         assert data["data"]["owner_username"] == "test.user"
#         assert data["data"]["wrapper_type"] == "ryugraph"
#
#     def test_create_instance_with_falkordb_wrapper(
#         self, client: TestClient, auth_headers: dict, ready_snapshot_id: int
#     ):
#         """Test creating an instance with FalkorDB wrapper type."""
#         response = client.post(
#             "/api/instances",
#             json={
#                 "snapshot_id": ready_snapshot_id,
#                 "name": "FalkorDB Instance",
#                 "description": "Test FalkorDB wrapper",
#                 "wrapper_type": "falkordb",
#             },
#             headers=auth_headers,
#         )
#
#         assert response.status_code == 201
#         data = response.json()
#         assert data["data"]["name"] == "FalkorDB Instance"
#         assert data["data"]["wrapper_type"] == "falkordb"
#         assert data["data"]["status"] == "starting"
#
#     def test_create_instance_snapshot_not_ready(self, client: TestClient, auth_headers: dict):
#         """Test creating instance from pending snapshot fails."""
#         # Create mapping
#         mapping_response = client.post(
#             "/api/mappings",
#             json={
#                 "name": "Pending Mapping",
#                 "node_definitions": [
#                     {
#                         "label": "TestNode",
#                         "sql": "SELECT id FROM test",
#                         "primary_key": {"name": "id", "type": "STRING"},
#                         "properties": [],
#                     },
#                 ],
#             },
#             headers=auth_headers,
#         )
#         mapping_id = mapping_response.json()["data"]["id"]
#
#         # Create snapshot (stays pending)
#         snapshot_response = client.post(
#             "/api/snapshots",
#             json={
#                 "mapping_id": mapping_id,
#                 "name": "Pending Snapshot",
#             },
#             headers=auth_headers,
#         )
#         snapshot_id = snapshot_response.json()["data"]["id"]
#
#         # Try to create instance
#         response = client.post(
#             "/api/instances",
#             json={
#                 "snapshot_id": snapshot_id,
#                 "name": "Bad Instance",
#                 "wrapper_type": "ryugraph",
#             },
#             headers=auth_headers,
#         )
#
#         assert response.status_code == 409
#         assert response.json()["error"]["code"] == "INVALID_STATE"
#
#     def test_get_instance(self, client: TestClient, auth_headers: dict, ready_snapshot_id: int):
#         """Test getting an instance by ID."""
#         # Create instance
#         create_response = client.post(
#             "/api/instances",
#             json={
#                 "snapshot_id": ready_snapshot_id,
#                 "name": "Get Test",
#                 "wrapper_type": "ryugraph",
#             },
#             headers=auth_headers,
#         )
#         instance_id = create_response.json()["data"]["id"]
#
#         # Get it
#         response = client.get(
#             f"/api/instances/{instance_id}",
#             headers=auth_headers,
#         )
#
#         assert response.status_code == 200
#         data = response.json()
#         assert data["data"]["id"] == instance_id
#         assert data["data"]["name"] == "Get Test"
#
#     def test_list_instances(self, client: TestClient, auth_headers: dict, ready_snapshot_id: int):
#         """Test listing instances."""
#         # Create instances
#         for i in range(3):
#             client.post(
#                 "/api/instances",
#                 json={
#                     "snapshot_id": ready_snapshot_id,
#                     "name": f"Instance {i}",
#                     "wrapper_type": "ryugraph",
#                 },
#                 headers=auth_headers,
#             )
#
#         # List all
#         response = client.get(
#             "/api/instances",
#             headers=auth_headers,
#         )
#
#         assert response.status_code == 200
#         data = response.json()
#         assert len(data["data"]) == 3
#
#     def test_terminate_instance(
#         self,
#         client: TestClient,
#         auth_headers: dict,
#         internal_headers: dict,
#         ready_snapshot_id: int,
#     ):
#         """Test terminating a running instance."""
#         # Create instance
#         create_response = client.post(
#             "/api/instances",
#             json={
#                 "snapshot_id": ready_snapshot_id,
#                 "name": "Terminate Test",
#                 "wrapper_type": "ryugraph",
#             },
#             headers=auth_headers,
#         )
#         instance_id = create_response.json()["data"]["id"]
#
#         # Mark as running via internal API
#         client.patch(
#             f"/api/internal/instances/{instance_id}/status",
#             json={
#                 "status": "running",
#                 "pod_name": "test-pod",
#                 "instance_url": "https://test.example.com/",
#             },
#             headers=internal_headers,
#         )
#
#         # Delete instance (REST: DELETE /api/instances/{id})
#         response = client.delete(
#             f"/api/instances/{instance_id}",
#             headers=auth_headers,
#         )
#
#         assert response.status_code == 204
#
#     def test_get_user_status(self, client: TestClient, auth_headers: dict, ready_snapshot_id: int):
#         """Test getting user's instance status."""
#         # Create instance
#         client.post(
#             "/api/instances",
#             json={
#                 "snapshot_id": ready_snapshot_id,
#                 "name": "User Status Test",
#                 "wrapper_type": "ryugraph",
#             },
#             headers=auth_headers,
#         )
#
#         # Get user status
#         response = client.get(
#             "/api/instances/user/status",
#             headers=auth_headers,
#         )
#
#         assert response.status_code == 200
#         data = response.json()
#         assert "active_instances" in data["data"]
#         assert "per_user_limit" in data["data"]
#         assert data["data"]["active_instances"] == 1
#
#     def test_update_instance(self, client: TestClient, auth_headers: dict, ready_snapshot_id: int):
#         """Test updating instance metadata."""
#         # Create instance
#         create_response = client.post(
#             "/api/instances",
#             json={
#                 "snapshot_id": ready_snapshot_id,
#                 "name": "Original Name",
#                 "description": "Original description",
#                 "wrapper_type": "ryugraph",
#             },
#             headers=auth_headers,
#         )
#         instance_id = create_response.json()["data"]["id"]
#
#         # Update it
#         response = client.put(
#             f"/api/instances/{instance_id}",
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
#     def test_update_instance_permission_denied(
#         self, client: TestClient, auth_headers: dict, ready_snapshot_id: int
#     ):
#         """Test other user cannot update instance."""
#         # Create instance
#         create_response = client.post(
#             "/api/instances",
#             json={
#                 "snapshot_id": ready_snapshot_id,
#                 "name": "Permission Test",
#                 "wrapper_type": "ryugraph",
#             },
#             headers=auth_headers,
#         )
#         instance_id = create_response.json()["data"]["id"]
#
#         # Try to update as different user
#         other_headers = {
#             "X-Username": "other.user",
#             "X-User-Role": "analyst",
#         }
#         response = client.put(
#             f"/api/instances/{instance_id}",
#             json={"name": "Hacked Name"},
#             headers=other_headers,
#         )
#
#         assert response.status_code == 403
#
#     def test_update_instance_not_found(self, client: TestClient, auth_headers: dict):
#         """Test updating non-existent instance."""
#         response = client.put(
#             "/api/instances/99999",
#             json={"name": "Does Not Exist"},
#             headers=auth_headers,
#         )
#
#         assert response.status_code == 404
#
#     def test_update_instance_lifecycle(
#         self, client: TestClient, auth_headers: dict, ready_snapshot_id: int
#     ):
#         """Test updating instance lifecycle settings."""
#         # Create instance
#         create_response = client.post(
#             "/api/instances",
#             json={
#                 "snapshot_id": ready_snapshot_id,
#                 "name": "Lifecycle Test",
#                 "wrapper_type": "ryugraph",
#             },
#             headers=auth_headers,
#         )
#         instance_id = create_response.json()["data"]["id"]
#
#         # Update lifecycle
#         response = client.put(
#             f"/api/instances/{instance_id}/lifecycle",
#             json={
#                 "ttl": "P7D",
#                 "inactivity_timeout": "PT2H",
#             },
#             headers=auth_headers,
#         )
#
#         assert response.status_code == 200
#         data = response.json()
#         assert data["data"]["ttl"] == "P7D"
#         assert data["data"]["inactivity_timeout"] == "PT2H"
#
#     def test_update_instance_lifecycle_permission_denied(
#         self, client: TestClient, auth_headers: dict, ready_snapshot_id: int
#     ):
#         """Test other user cannot update instance lifecycle."""
#         # Create instance
#         create_response = client.post(
#             "/api/instances",
#             json={
#                 "snapshot_id": ready_snapshot_id,
#                 "name": "Lifecycle Permission Test",
#                 "wrapper_type": "ryugraph",
#             },
#             headers=auth_headers,
#         )
#         instance_id = create_response.json()["data"]["id"]
#
#         # Try to update as different user
#         other_headers = {
#             "X-Username": "other.user",
#             "X-User-Role": "analyst",
#         }
#         response = client.put(
#             f"/api/instances/{instance_id}/lifecycle",
#             json={"ttl": "P1D"},
#             headers=other_headers,
#         )
#
#         assert response.status_code == 403
#
#     def test_get_instance_progress(
#         self,
#         client: TestClient,
#         auth_headers: dict,
#         internal_headers: dict,
#         ready_snapshot_id: int,
#     ):
#         """Test getting instance loading progress."""
#         # Create instance
#         create_response = client.post(
#             "/api/instances",
#             json={
#                 "snapshot_id": ready_snapshot_id,
#                 "name": "Progress Test",
#                 "wrapper_type": "ryugraph",
#             },
#             headers=auth_headers,
#         )
#         instance_id = create_response.json()["data"]["id"]
#
#         # Update progress via internal API
#         client.put(
#             f"/api/internal/instances/{instance_id}/progress",
#             json={
#                 "phase": "loading_nodes",
#                 "steps": [
#                     {"name": "Customer", "status": "in_progress", "type": "node"},
#                 ],
#             },
#             headers=internal_headers,
#         )
#
#         # Get progress
#         response = client.get(
#             f"/api/instances/{instance_id}/progress",
#             headers=auth_headers,
#         )
#
#         assert response.status_code == 200
#         data = response.json()
#         assert data["data"]["phase"] == "loading_nodes"
#         assert len(data["data"]["steps"]) == 1
#
#     def test_get_instance_progress_not_found(self, client: TestClient, auth_headers: dict):
#         """Test getting progress for non-existent instance."""
#         response = client.get(
#             "/api/instances/99999/progress",
#             headers=auth_headers,
#         )
#
#         assert response.status_code == 404


class TestInstancesFromMappingAPI:
    """Integration tests for POST /api/instances endpoint.

    This endpoint creates an instance directly from a mapping by:
    1. Creating a snapshot from the mapping
    2. Creating an instance with status=waiting_for_snapshot
    3. The orchestration job then transitions to starting when snapshot is ready
    """

    @pytest.fixture
    def app(self, settings, db_engine):
        """Use settings from conftest.py (PostgreSQL testcontainer)."""
        from control_plane.main import create_app

        return create_app(settings)

    @pytest.fixture
    def client(self, app):
        with TestClient(app) as client:
            yield client

    @pytest.fixture
    def auth_headers(self) -> dict:
        return {
            "X-Username": "test.user",
        }

    @pytest.fixture
    def internal_headers(self) -> dict:
        return {
            "X-Internal-Api-Key": "test-internal-key",
        }

    @pytest.fixture
    def mapping_id(self, client: TestClient, auth_headers: dict) -> int:
        """Create a mapping and return its ID."""
        response = client.post(
            "/api/mappings",
            json={
                "name": "From Mapping Test",
                "node_definitions": [
                    {
                        "label": "Customer",
                        "sql": "SELECT id, name FROM customers",
                        "primary_key": {"name": "id", "type": "STRING"},
                        "properties": [{"name": "name", "type": "STRING"}],
                    },
                ],
            },
            headers=auth_headers,
        )
        return response.json()["data"]["id"]

    def test_create_instance_from_mapping_happy_path(
        self, client: TestClient, auth_headers: dict, mapping_id: int
    ):
        """Test creating instance directly from mapping."""
        response = client.post(
            "/api/instances",
            json={
                "mapping_id": mapping_id,
                "name": "Instance From Mapping",
                "wrapper_type": "falkordb",
                "description": "Created directly from mapping",
            },
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["data"]["name"] == "Instance From Mapping"
        assert data["data"]["wrapper_type"] == "falkordb"
        # Status should be waiting_for_snapshot since snapshot is being created
        assert data["data"]["status"] == "waiting_for_snapshot"
        assert data["data"]["owner_username"] == "test.user"
        # Should have a snapshot_id (the newly created snapshot)
        assert data["data"]["snapshot_id"] is not None

    def test_create_instance_from_mapping_with_specific_version(
        self, client: TestClient, auth_headers: dict, mapping_id: int
    ):
        """Test creating instance with specific mapping version."""
        # First update the mapping to create version 2
        client.put(
            f"/api/mappings/{mapping_id}",
            json={
                "node_definitions": [
                    {
                        "label": "Customer",
                        "sql": "SELECT id, name, email FROM customers",
                        "primary_key": {"name": "id", "type": "STRING"},
                        "properties": [
                            {"name": "name", "type": "STRING"},
                            {"name": "email", "type": "STRING"},
                        ],
                    },
                ],
                "change_description": "Added email field",
            },
            headers=auth_headers,
        )

        # Create instance from version 1 (not current version)
        response = client.post(
            "/api/instances",
            json={
                "mapping_id": mapping_id,
                "name": "Instance From Version 1",
                "wrapper_type": "ryugraph",
                "mapping_version": 1,
            },
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["data"]["status"] == "waiting_for_snapshot"

    def test_create_instance_from_mapping_not_found(
        self, client: TestClient, auth_headers: dict
    ):
        """Test 404 when mapping doesn't exist."""
        response = client.post(
            "/api/instances",
            json={
                "mapping_id": 99999,
                "name": "Instance From Missing Mapping",
                "wrapper_type": "falkordb",
            },
            headers=auth_headers,
        )

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
        assert "Mapping" in response.json()["error"]["message"]

    def test_create_instance_from_mapping_version_not_found(
        self, client: TestClient, auth_headers: dict, mapping_id: int
    ):
        """Test 404 when mapping version doesn't exist."""
        response = client.post(
            "/api/instances",
            json={
                "mapping_id": mapping_id,
                "name": "Instance From Missing Version",
                "wrapper_type": "falkordb",
                "mapping_version": 99,  # Version doesn't exist
            },
            headers=auth_headers,
        )

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
        assert "MappingVersion" in response.json()["error"]["message"]

    def test_create_instance_from_mapping_concurrency_limit(
        self, client: TestClient, auth_headers: dict, internal_headers: dict, mapping_id: int
    ):
        """Test 409 when per-analyst instance limit exceeded."""
        # First, set per_analyst limit to 1 via config endpoint
        ops_headers = {
            "X-Username": "ops.user",
        }
        client.put(
            "/api/config/concurrency",
            json={
                "per_analyst": 1,
                "cluster_total": 100,
            },
            headers=ops_headers,
        )

        # Create first instance (should succeed)
        response1 = client.post(
            "/api/instances",
            json={
                "mapping_id": mapping_id,
                "name": "First Instance",
                "wrapper_type": "falkordb",
            },
            headers=auth_headers,
        )
        assert response1.status_code == 201

        # Create second instance (should fail - limit exceeded)
        response2 = client.post(
            "/api/instances",
            json={
                "mapping_id": mapping_id,
                "name": "Second Instance",
                "wrapper_type": "falkordb",
            },
            headers=auth_headers,
        )

        assert response2.status_code == 409
        assert response2.json()["error"]["code"] == "CONCURRENCY_LIMIT_EXCEEDED"

    def test_create_instance_from_mapping_with_lifecycle_settings(
        self, client: TestClient, auth_headers: dict, mapping_id: int
    ):
        """Test creating instance with custom lifecycle settings."""
        response = client.post(
            "/api/instances",
            json={
                "mapping_id": mapping_id,
                "name": "Instance With Lifecycle",
                "wrapper_type": "falkordb",
                "ttl": "PT48H",
                "inactivity_timeout": "PT12H",
            },
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["data"]["ttl"] == "PT48H"
        assert data["data"]["inactivity_timeout"] == "PT12H"

    # =========================================================================
    # SNAPSHOT API TEST DISABLED
    # This test is commented out because it depends on GET /api/snapshots/{id}
    # which has been removed. The snapshot is still created internally.
    # =========================================================================
    # def test_create_instance_from_mapping_creates_snapshot(
    #     self, client: TestClient, auth_headers: dict, mapping_id: int
    # ):
    #     """Test that creating instance from mapping also creates a snapshot."""
    #     # Create instance
    #     response = client.post(
    #         "/api/instances/from-mapping",
    #         json={
    #             "mapping_id": mapping_id,
    #             "name": "Instance With New Snapshot",
    #             "wrapper_type": "falkordb",
    #         },
    #         headers=auth_headers,
    #     )
    #
    #     assert response.status_code == 201
    #     instance_data = response.json()["data"]
    #     snapshot_id = instance_data["snapshot_id"]
    #
    #     # Verify snapshot was created
    #     snapshot_response = client.get(
    #         f"/api/snapshots/{snapshot_id}",
    #         headers=auth_headers,
    #     )
    #
    #     assert snapshot_response.status_code == 200
    #     snapshot_data = snapshot_response.json()["data"]
    #     assert snapshot_data["mapping_id"] == mapping_id
    #     # Snapshot should be pending (export in progress)
    #     assert snapshot_data["status"] in ["pending", "creating"]

    def test_create_instance_from_mapping_lists_correctly(
        self, client: TestClient, auth_headers: dict, mapping_id: int
    ):
        """Test that from-mapping instances appear in list with correct status."""
        # Create instance
        client.post(
            "/api/instances",
            json={
                "mapping_id": mapping_id,
                "name": "Listed Instance",
                "wrapper_type": "falkordb",
            },
            headers=auth_headers,
        )

        # List instances
        response = client.get(
            "/api/instances",
            headers=auth_headers,
        )

        assert response.status_code == 200
        instances = response.json()["data"]
        assert len(instances) >= 1

        # Find our instance
        waiting_instances = [i for i in instances if i["status"] == "waiting_for_snapshot"]
        assert len(waiting_instances) >= 1
        assert waiting_instances[0]["name"] == "Listed Instance"

    def test_create_instance_from_mapping_user_status_reflects_waiting(
        self, client: TestClient, auth_headers: dict, mapping_id: int
    ):
        """Test that waiting_for_snapshot instances count toward user limits."""
        # Create instance
        client.post(
            "/api/instances",
            json={
                "mapping_id": mapping_id,
                "name": "Counted Instance",
                "wrapper_type": "falkordb",
            },
            headers=auth_headers,
        )

        # Get user status
        response = client.get(
            "/api/instances/user/status",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()["data"]
        # waiting_for_snapshot should count as active
        assert data["active_instances"] >= 1

    def test_update_instance_name_and_description(
        self, client: TestClient, auth_headers: dict, mapping_id: int
    ):
        """Test updating instance name and description."""
        # Create instance
        create_response = client.post(
            "/api/instances",
            json={
                "mapping_id": mapping_id,
                "name": "Original Name",
                "wrapper_type": "falkordb",
                "description": "Original description",
            },
            headers=auth_headers,
        )
        assert create_response.status_code == 201
        instance_id = create_response.json()["data"]["id"]

        # Update name and description
        response = client.put(
            f"/api/instances/{instance_id}",
            json={
                "name": "Updated Name",
                "description": "Updated description",
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["name"] == "Updated Name"
        assert data["description"] == "Updated description"

    def test_update_instance_name_only(
        self, client: TestClient, auth_headers: dict, mapping_id: int
    ):
        """Test updating only instance name."""
        # Create instance
        create_response = client.post(
            "/api/instances",
            json={
                "mapping_id": mapping_id,
                "name": "Name Only Test",
                "wrapper_type": "falkordb",
                "description": "Keep this description",
            },
            headers=auth_headers,
        )
        instance_id = create_response.json()["data"]["id"]

        # Update only name
        response = client.put(
            f"/api/instances/{instance_id}",
            json={"name": "New Name Only"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["name"] == "New Name Only"
        # Description should be unchanged
        assert data["description"] == "Keep this description"

    def test_update_instance_permission_denied(
        self, client: TestClient, auth_headers: dict, mapping_id: int
    ):
        """Test that other users cannot update instance."""
        # Create instance
        create_response = client.post(
            "/api/instances",
            json={
                "mapping_id": mapping_id,
                "name": "Permission Test",
                "wrapper_type": "falkordb",
            },
            headers=auth_headers,
        )
        instance_id = create_response.json()["data"]["id"]

        # Try to update as different user
        other_headers = {
            "X-Username": "other.user",
        }
        response = client.put(
            f"/api/instances/{instance_id}",
            json={"name": "Hacked Name"},
            headers=other_headers,
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "PERMISSION_DENIED"

    def test_update_instance_not_found(
        self, client: TestClient, auth_headers: dict
    ):
        """Test updating non-existent instance returns 404."""
        response = client.put(
            "/api/instances/99999",
            json={"name": "Does Not Exist"},
            headers=auth_headers,
        )

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"

    def test_list_mapping_instances(
        self, client: TestClient, auth_headers: dict, mapping_id: int
    ):
        """Test listing instances created from a mapping."""
        # Create multiple instances from the same mapping
        for i in range(3):
            client.post(
                "/api/instances",
                json={
                    "mapping_id": mapping_id,
                    "name": f"Mapping Instance {i}",
                    "wrapper_type": "falkordb",
                },
                headers=auth_headers,
            )

        # List instances for the mapping
        response = client.get(
            f"/api/mappings/{mapping_id}/instances",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["meta"]["total"] >= 3
        assert len(data["data"]) >= 3

        # Verify all returned instances are from our mapping
        for instance in data["data"]:
            assert instance["owner_username"] == "test.user"
            assert "Mapping Instance" in instance["name"]

    def test_list_mapping_instances_with_pagination(
        self, client: TestClient, auth_headers: dict, mapping_id: int
    ):
        """Test pagination for listing instances by mapping."""
        # Create 5 instances
        for i in range(5):
            client.post(
                "/api/instances",
                json={
                    "mapping_id": mapping_id,
                    "name": f"Paginated Instance {i}",
                    "wrapper_type": "falkordb",
                },
                headers=auth_headers,
            )

        # Get first page
        response = client.get(
            f"/api/mappings/{mapping_id}/instances",
            params={"limit": 2, "offset": 0},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 2
        assert data["meta"]["offset"] == 0
        assert data["meta"]["limit"] == 2
        assert data["meta"]["total"] >= 5

    def test_list_mapping_instances_not_found(
        self, client: TestClient, auth_headers: dict
    ):
        """Test 404 when mapping doesn't exist."""
        response = client.get(
            "/api/mappings/99999/instances",
            headers=auth_headers,
        )

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
