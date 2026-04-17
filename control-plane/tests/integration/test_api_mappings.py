"""Integration tests for mappings API."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from control_plane.config import Settings
from control_plane.main import create_app

from tests.integration.conftest import seed_test_users


# Helper to create a valid node definition matching the documentation schema
def make_node(label: str = "TestNode", sql: str = "SELECT id, name FROM test") -> dict:
    """Create a valid node definition.

    Note: Avoid using reserved Cypher keywords as labels (e.g., 'Node', 'Match', etc.)
    """
    return {
        "label": label,
        "sql": sql,
        "primary_key": {"name": "id", "type": "STRING"},
        "properties": [{"name": "name", "type": "STRING"}],
    }


# Helper to create a valid edge definition matching the documentation schema
def make_edge(
    edge_type: str,
    from_node: str,
    to_node: str,
    from_key: str = "from_id",
    to_key: str = "to_id",
) -> dict:
    """Create a valid edge definition."""
    return {
        "type": edge_type,
        "sql": f"SELECT {from_key}, {to_key} FROM {edge_type.lower()}",
        "from_node": from_node,
        "to_node": to_node,
        "from_key": from_key,
        "to_key": to_key,
        "properties": [],
    }


class TestMappingsAPI:
    """Integration tests for /api/mappings endpoints."""

    @pytest.fixture
    def app(self, settings: Settings, db_engine) -> FastAPI:
        """Create app with test database (PostgreSQL from conftest.py).

        db_engine fixture ensures tables are created/dropped for each test.
        """
        return create_app(settings)

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        # Use context manager to ensure lifespan events are called
        with TestClient(app) as client:
            yield client

    @pytest.fixture(autouse=True)
    def _provision_users(self, client: TestClient):
        """Provision test users in DB so identity middleware can resolve roles."""
        seed_test_users(client)

    @pytest.fixture
    def auth_headers(self) -> dict:
        """Headers for authenticated requests."""
        return {
            "X-Username": "test.user",
        }

    def test_create_mapping(self, client: TestClient, auth_headers: dict):
        """Test creating a new mapping."""
        response = client.post(
            "/api/mappings",
            json={
                "name": "Customer Graph",
                "description": "Customer and product relationships",
                "node_definitions": [
                    make_node("Customer", "SELECT id, name FROM customers"),
                    make_node("Product", "SELECT id, name FROM products"),
                ],
                "edge_definitions": [
                    make_edge("PURCHASED", "Customer", "Product", "customer_id", "product_id"),
                ],
            },
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["data"]["name"] == "Customer Graph"
        assert data["data"]["current_version"] == 1
        assert data["data"]["owner_username"] == "test.user"
        assert len(data["data"]["node_definitions"]) == 2
        assert len(data["data"]["edge_definitions"]) == 1

    def test_create_mapping_unauthenticated(self, client: TestClient):
        """Test creating mapping without auth fails."""
        response = client.post(
            "/api/mappings",
            json={
                "name": "Test",
                "node_definitions": [make_node()],
            },
        )

        assert response.status_code == 401

    def test_create_mapping_validation_error(self, client: TestClient, auth_headers: dict):
        """Test creating mapping with invalid data returns 400."""
        response = client.post(
            "/api/mappings",
            json={
                "name": "",  # Empty name should fail
                "node_definitions": [],  # Must have at least one node
            },
            headers=auth_headers,
        )

        assert response.status_code == 422

    def test_get_mapping(self, client: TestClient, auth_headers: dict):
        """Test getting a mapping by ID."""
        # First create a mapping
        create_response = client.post(
            "/api/mappings",
            json={
                "name": "Get Test",
                "node_definitions": [make_node()],
            },
            headers=auth_headers,
        )
        mapping_id = create_response.json()["data"]["id"]

        # Then get it
        response = client.get(
            f"/api/mappings/{mapping_id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["id"] == mapping_id
        assert data["data"]["name"] == "Get Test"

    def test_get_mapping_not_found(self, client: TestClient, auth_headers: dict):
        """Test getting non-existent mapping returns 404."""
        response = client.get(
            "/api/mappings/99999",
            headers=auth_headers,
        )

        assert response.status_code == 404
        data = response.json()
        assert data["error"]["code"] == "RESOURCE_NOT_FOUND"

    def test_list_mappings(self, client: TestClient, auth_headers: dict):
        """Test listing mappings with pagination."""
        # Create some mappings
        for i in range(5):
            client.post(
                "/api/mappings",
                json={
                    "name": f"Mapping {i}",
                    "node_definitions": [make_node()],
                },
                headers=auth_headers,
            )

        # List with pagination
        response = client.get(
            "/api/mappings?limit=3&offset=0",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 3
        assert data["meta"]["total"] == 5
        assert data["meta"]["limit"] == 3
        assert data["meta"]["offset"] == 0

    def test_list_mappings_filter_by_owner(self, client: TestClient, auth_headers: dict):
        """Test filtering mappings by owner."""
        # Create mappings as test.user
        client.post(
            "/api/mappings",
            json={
                "name": "My Mapping",
                "node_definitions": [make_node()],
            },
            headers=auth_headers,
        )

        # Filter by owner
        response = client.get(
            "/api/mappings?owner=test.user",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert all(m["owner_username"] == "test.user" for m in data["data"])

    def test_update_mapping(self, client: TestClient, auth_headers: dict):
        """Test updating a mapping creates new version."""
        # Create mapping
        create_response = client.post(
            "/api/mappings",
            json={
                "name": "Update Test",
                "node_definitions": [make_node()],
            },
            headers=auth_headers,
        )
        mapping_id = create_response.json()["data"]["id"]

        # Update with new node
        response = client.put(
            f"/api/mappings/{mapping_id}",
            json={
                "node_definitions": [
                    make_node(),
                    make_node("NewNode"),
                ],
                "change_description": "Added NewNode",
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["current_version"] == 2
        assert len(data["data"]["node_definitions"]) == 2

    def test_update_mapping_permission_denied(self, client: TestClient, auth_headers: dict):
        """Test other user cannot update mapping."""
        # Create mapping as test.user
        create_response = client.post(
            "/api/mappings",
            json={
                "name": "Permission Test",
                "node_definitions": [make_node()],
            },
            headers=auth_headers,
        )
        mapping_id = create_response.json()["data"]["id"]

        # Try to update as different user
        other_headers = {
            "X-Username": "other.user",
        }
        response = client.put(
            f"/api/mappings/{mapping_id}",
            json={
                "name": "Hacked",
                "change_description": "Unauthorized change",
            },
            headers=other_headers,
        )

        assert response.status_code == 403

    def test_delete_mapping(self, client: TestClient, auth_headers: dict):
        """Test deleting a mapping."""
        # Create mapping
        create_response = client.post(
            "/api/mappings",
            json={
                "name": "Delete Test",
                "node_definitions": [make_node()],
            },
            headers=auth_headers,
        )
        mapping_id = create_response.json()["data"]["id"]

        # Delete it
        response = client.delete(
            f"/api/mappings/{mapping_id}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verify it's gone
        get_response = client.get(
            f"/api/mappings/{mapping_id}",
            headers=auth_headers,
        )
        assert get_response.status_code == 404

    def test_copy_mapping(self, client: TestClient, auth_headers: dict):
        """Test copying a mapping."""
        # Create mapping
        create_response = client.post(
            "/api/mappings",
            json={
                "name": "Original Mapping",
                "description": "Original description",
                "node_definitions": [
                    make_node("Customer", "SELECT id, name FROM customers"),
                ],
            },
            headers=auth_headers,
        )
        mapping_id = create_response.json()["data"]["id"]

        # Copy as different user
        other_headers = {
            "X-Username": "other.user",
        }
        response = client.post(
            f"/api/mappings/{mapping_id}/copy",
            json={"name": "My Copy"},
            headers=other_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["data"]["name"] == "My Copy"
        assert data["data"]["owner_username"] == "other.user"
        assert data["data"]["current_version"] == 1
        assert data["data"]["description"] == "Original description"
        assert len(data["data"]["node_definitions"]) == 1

    def test_copy_mapping_not_found(self, client: TestClient, auth_headers: dict):
        """Test copying non-existent mapping fails."""
        response = client.post(
            "/api/mappings/99999/copy",
            json={"name": "Copy"},
            headers=auth_headers,
        )

        assert response.status_code == 404

    def test_update_mapping_lifecycle(self, client: TestClient, auth_headers: dict):
        """Test updating mapping lifecycle settings."""
        # Create mapping
        create_response = client.post(
            "/api/mappings",
            json={
                "name": "Lifecycle Test",
                "node_definitions": [make_node()],
            },
            headers=auth_headers,
        )
        mapping_id = create_response.json()["data"]["id"]

        # Update lifecycle
        response = client.put(
            f"/api/mappings/{mapping_id}/lifecycle",
            json={
                "ttl": "P30D",
                "inactivity_timeout": "P7D",
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["id"] == mapping_id
        assert data["data"]["ttl"] == "P30D"
        assert data["data"]["inactivity_timeout"] == "P7D"

    def test_update_mapping_lifecycle_permission_denied(
        self, client: TestClient, auth_headers: dict
    ):
        """Test other user cannot update lifecycle."""
        # Create mapping as test.user
        create_response = client.post(
            "/api/mappings",
            json={
                "name": "Lifecycle Permission Test",
                "node_definitions": [make_node()],
            },
            headers=auth_headers,
        )
        mapping_id = create_response.json()["data"]["id"]

        # Try to update as different user
        other_headers = {
            "X-Username": "other.user",
        }
        response = client.put(
            f"/api/mappings/{mapping_id}/lifecycle",
            json={"ttl": "P1D"},
            headers=other_headers,
        )

        assert response.status_code == 403

    def test_list_mapping_versions(self, client: TestClient, auth_headers: dict):
        """Test listing all versions of a mapping."""
        # Create mapping
        create_response = client.post(
            "/api/mappings",
            json={
                "name": "Versioned Mapping",
                "node_definitions": [make_node()],
            },
            headers=auth_headers,
        )
        mapping_id = create_response.json()["data"]["id"]

        # Create version 2
        client.put(
            f"/api/mappings/{mapping_id}",
            json={
                "node_definitions": [
                    make_node(),
                    make_node("NewNode"),
                ],
                "change_description": "Added NewNode",
            },
            headers=auth_headers,
        )

        # List versions
        response = client.get(
            f"/api/mappings/{mapping_id}/versions",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["meta"]["total"] == 2
        # Versions are in descending order
        assert data["data"][0]["version"] == 2
        assert data["data"][0]["change_description"] == "Added NewNode"
        assert data["data"][1]["version"] == 1

    def test_list_mapping_versions_not_found(self, client: TestClient, auth_headers: dict):
        """Test listing versions of non-existent mapping fails."""
        response = client.get(
            "/api/mappings/99999/versions",
            headers=auth_headers,
        )

        assert response.status_code == 404

    def test_get_mapping_version(self, client: TestClient, auth_headers: dict):
        """Test getting a specific version of a mapping."""
        # Create mapping
        create_response = client.post(
            "/api/mappings",
            json={
                "name": "Version Detail Test",
                "node_definitions": [make_node()],
            },
            headers=auth_headers,
        )
        mapping_id = create_response.json()["data"]["id"]

        # Create version 2 with different nodes
        client.put(
            f"/api/mappings/{mapping_id}",
            json={
                "node_definitions": [make_node("UpdatedNode")],
                "change_description": "Changed node",
            },
            headers=auth_headers,
        )

        # Get version 1
        response = client.get(
            f"/api/mappings/{mapping_id}/versions/1",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["version"] == 1
        assert data["data"]["node_definitions"][0]["label"] == "TestNode"

        # Get version 2
        response = client.get(
            f"/api/mappings/{mapping_id}/versions/2",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["version"] == 2
        assert data["data"]["node_definitions"][0]["label"] == "UpdatedNode"
        assert data["data"]["change_description"] == "Changed node"

    def test_get_mapping_version_not_found(self, client: TestClient, auth_headers: dict):
        """Test getting non-existent version fails."""
        # Create mapping
        create_response = client.post(
            "/api/mappings",
            json={
                "name": "Version Not Found Test",
                "node_definitions": [make_node()],
            },
            headers=auth_headers,
        )
        mapping_id = create_response.json()["data"]["id"]

        # Try to get version 99
        response = client.get(
            f"/api/mappings/{mapping_id}/versions/99",
            headers=auth_headers,
        )

        assert response.status_code == 404

    # =========================================================================
    # SNAPSHOT TESTS DISABLED
    # These tests are commented out as snapshot functionality has been disabled.
    # =========================================================================
    # def test_list_mapping_snapshots(self, client: TestClient, auth_headers: dict):
    #     """Test listing snapshots for a mapping."""
    #     # Create mapping
    #     create_response = client.post(
    #         "/api/mappings",
    #         json={
    #             "name": "Snapshots Test",
    #             "node_definitions": [make_node()],
    #         },
    #         headers=auth_headers,
    #     )
    #     mapping_id = create_response.json()["data"]["id"]
    #
    #     # Create some snapshots
    #     for i in range(3):
    #         client.post(
    #             "/api/snapshots",
    #             json={
    #                 "mapping_id": mapping_id,
    #                 "name": f"Snapshot {i}",
    #             },
    #             headers=auth_headers,
    #         )
    #
    #     # List snapshots for mapping
    #     response = client.get(
    #         f"/api/mappings/{mapping_id}/snapshots",
    #         headers=auth_headers,
    #     )
    #
    #     assert response.status_code == 200
    #     data = response.json()
    #     assert data["meta"]["total"] == 3
    #     assert len(data["data"]) == 3
    #     for snapshot in data["data"]:
    #         assert snapshot["mapping_id"] == mapping_id
    #
    # def test_list_mapping_snapshots_empty(self, client: TestClient, auth_headers: dict):
    #     """Test listing snapshots when none exist."""
    #     # Create mapping
    #     create_response = client.post(
    #         "/api/mappings",
    #         json={
    #             "name": "No Snapshots",
    #             "node_definitions": [make_node()],
    #         },
    #         headers=auth_headers,
    #     )
    #     mapping_id = create_response.json()["data"]["id"]
    #
    #     # List snapshots
    #     response = client.get(
    #         f"/api/mappings/{mapping_id}/snapshots",
    #         headers=auth_headers,
    #     )
    #
    #     assert response.status_code == 200
    #     data = response.json()
    #     assert data["meta"]["total"] == 0
    #     assert len(data["data"]) == 0
    #
    # def test_list_mapping_snapshots_not_found(self, client: TestClient, auth_headers: dict):
    #     """Test listing snapshots of non-existent mapping fails."""
    #     response = client.get(
    #         "/api/mappings/99999/snapshots",
    #         headers=auth_headers,
    #     )
    #
    #     assert response.status_code == 404

    def test_get_version_diff_node_added(self, client: TestClient, auth_headers: dict):
        """Test diff when a node is added in v2."""
        # Create mapping v1
        create_response = client.post(
            "/api/mappings",
            json={
                "name": "Diff Test",
                "node_definitions": [make_node("Customer")],
                "edge_definitions": [],
            },
            headers=auth_headers,
        )
        mapping_id = create_response.json()["data"]["id"]

        # Update to v2 (add node)
        client.put(
            f"/api/mappings/{mapping_id}",
            json={
                "node_definitions": [
                    make_node("Customer"),
                    make_node("Product"),  # Added
                ],
                "change_description": "Added Product node",
            },
            headers=auth_headers,
        )

        # Get diff
        response = client.get(
            f"/api/mappings/{mapping_id}/versions/1/diff/2",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["from_version"] == 1
        assert data["to_version"] == 2
        assert data["summary"]["nodes_added"] == 1
        assert data["summary"]["nodes_removed"] == 0
        assert data["summary"]["nodes_modified"] == 0

        # Check node changes
        assert len(data["changes"]["nodes"]) == 1
        added_node = data["changes"]["nodes"][0]
        assert added_node["label"] == "Product"
        assert added_node["change_type"] == "added"
        assert added_node["from"] is None
        assert added_node["to"] is not None

    def test_get_version_diff_node_removed(self, client: TestClient, auth_headers: dict):
        """Test diff when a node is removed in v2."""
        # Create mapping v1 with 2 nodes
        create_response = client.post(
            "/api/mappings",
            json={
                "name": "Diff Test Remove",
                "node_definitions": [
                    make_node("Customer"),
                    make_node("Product"),
                ],
                "edge_definitions": [],
            },
            headers=auth_headers,
        )
        mapping_id = create_response.json()["data"]["id"]

        # Update to v2 (remove Product)
        client.put(
            f"/api/mappings/{mapping_id}",
            json={
                "node_definitions": [make_node("Customer")],  # Product removed
                "change_description": "Removed Product node",
            },
            headers=auth_headers,
        )

        # Get diff
        response = client.get(
            f"/api/mappings/{mapping_id}/versions/1/diff/2",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["summary"]["nodes_removed"] == 1
        assert len(data["changes"]["nodes"]) == 1
        removed_node = data["changes"]["nodes"][0]
        assert removed_node["label"] == "Product"
        assert removed_node["change_type"] == "removed"

    def test_get_version_diff_node_modified(self, client: TestClient, auth_headers: dict):
        """Test diff when a node's properties change."""
        # Create mapping v1
        create_response = client.post(
            "/api/mappings",
            json={
                "name": "Diff Test Modify",
                "node_definitions": [
                    {
                        "label": "Customer",
                        "sql": "SELECT id, name FROM customers",
                        "primary_key": {"name": "id", "type": "STRING"},
                        "properties": [{"name": "name", "type": "STRING"}],
                    }
                ],
                "edge_definitions": [],
            },
            headers=auth_headers,
        )
        mapping_id = create_response.json()["data"]["id"]

        # Update to v2 (modify Customer)
        client.put(
            f"/api/mappings/{mapping_id}",
            json={
                "node_definitions": [
                    {
                        "label": "Customer",
                        "sql": "SELECT id, name, email FROM customers",  # Changed SQL
                        "primary_key": {"name": "id", "type": "STRING"},
                        "properties": [
                            {"name": "name", "type": "STRING"},
                            {"name": "email", "type": "STRING"},  # Added property
                        ],
                    }
                ],
                "change_description": "Added email to Customer",
            },
            headers=auth_headers,
        )

        # Get diff
        response = client.get(
            f"/api/mappings/{mapping_id}/versions/1/diff/2",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["summary"]["nodes_modified"] == 1
        modified_node = data["changes"]["nodes"][0]
        assert modified_node["label"] == "Customer"
        assert modified_node["change_type"] == "modified"
        assert "sql" in modified_node["fields_changed"] or "properties" in modified_node["fields_changed"]

    def test_get_version_diff_edge_modified(self, client: TestClient, auth_headers: dict):
        """Test diff when edge properties change."""
        # Create mapping v1
        create_response = client.post(
            "/api/mappings",
            json={
                "name": "Edge Diff Test",
                "node_definitions": [
                    make_node("Customer"),
                    make_node("Product"),
                ],
                "edge_definitions": [
                    {
                        "type": "PURCHASED",
                        "from_node": "Customer",
                        "to_node": "Product",
                        "sql": "SELECT customer_id, product_id FROM purchases",
                        "from_key": "customer_id",
                        "to_key": "product_id",
                        "properties": [],
                    }
                ],
            },
            headers=auth_headers,
        )
        mapping_id = create_response.json()["data"]["id"]

        # Update to v2 (modify edge)
        client.put(
            f"/api/mappings/{mapping_id}",
            json={
                "node_definitions": [
                    make_node("Customer"),
                    make_node("Product"),
                ],
                "edge_definitions": [
                    {
                        "type": "PURCHASED",
                        "from_node": "Customer",
                        "to_node": "Product",
                        "sql": "SELECT customer_id, product_id, amount FROM purchases",  # Changed SQL
                        "from_key": "customer_id",
                        "to_key": "product_id",
                        "properties": [{"name": "amount", "type": "DOUBLE"}],  # Added property
                    }
                ],
                "change_description": "Added amount to PURCHASED",
            },
            headers=auth_headers,
        )

        # Get diff
        response = client.get(
            f"/api/mappings/{mapping_id}/versions/1/diff/2",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["summary"]["edges_modified"] == 1
        modified_edge = data["changes"]["edges"][0]
        assert modified_edge["type"] == "PURCHASED"
        assert modified_edge["change_type"] == "modified"

    def test_get_version_diff_no_changes(self, client: TestClient, auth_headers: dict):
        """Test diff when versions have identical definitions (no changes)."""
        # Create mapping v1
        create_response = client.post(
            "/api/mappings",
            json={
                "name": "No Changes Test",
                "node_definitions": [make_node("Customer")],
                "edge_definitions": [],
            },
            headers=auth_headers,
        )
        mapping_id = create_response.json()["data"]["id"]

        # Update to v2 with same definitions (triggers version creation)
        client.put(
            f"/api/mappings/{mapping_id}",
            json={
                "node_definitions": [make_node("Customer")],  # Same as v1
                "edge_definitions": [],
                "change_description": "Re-saved with no actual changes",
            },
            headers=auth_headers,
        )

        # Get diff (definitions are identical)
        response = client.get(
            f"/api/mappings/{mapping_id}/versions/1/diff/2",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()["data"]
        # All counts should be zero since node/edge definitions are the same
        assert data["summary"]["nodes_added"] == 0
        assert data["summary"]["nodes_removed"] == 0
        assert data["summary"]["nodes_modified"] == 0
        assert data["summary"]["edges_added"] == 0
        assert data["summary"]["edges_removed"] == 0
        assert data["summary"]["edges_modified"] == 0

    def test_get_version_diff_same_version(self, client: TestClient, auth_headers: dict):
        """Test diff with same version returns 400."""
        # Create mapping
        create_response = client.post(
            "/api/mappings",
            json={
                "name": "Same Version Test",
                "node_definitions": [make_node("Customer")],
            },
            headers=auth_headers,
        )
        mapping_id = create_response.json()["data"]["id"]

        # Try to diff v1 with v1
        response = client.get(
            f"/api/mappings/{mapping_id}/versions/1/diff/1",
            headers=auth_headers,
        )

        assert response.status_code == 400

    def test_get_version_diff_version_not_found(self, client: TestClient, auth_headers: dict):
        """Test diff with non-existent version returns 404."""
        # Create mapping
        create_response = client.post(
            "/api/mappings",
            json={
                "name": "Not Found Test",
                "node_definitions": [make_node("Customer")],
            },
            headers=auth_headers,
        )
        mapping_id = create_response.json()["data"]["id"]

        # Try to diff with non-existent version
        response = client.get(
            f"/api/mappings/{mapping_id}/versions/1/diff/99",
            headers=auth_headers,
        )

        assert response.status_code == 404

    def test_get_version_diff_mapping_not_found(self, client: TestClient, auth_headers: dict):
        """Test diff with non-existent mapping returns 404."""
        response = client.get(
            "/api/mappings/99999/versions/1/diff/2",
            headers=auth_headers,
        )

        assert response.status_code == 404
