"""Integration tests for cluster API."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from control_plane.config import Settings
from control_plane.main import create_app

from tests.integration.conftest import seed_test_users


class TestClusterAPI:
    """Integration tests for /api/cluster endpoints."""

    @pytest.fixture
    def app(self, settings: Settings, db_engine) -> FastAPI:
        """Use settings from conftest.py (PostgreSQL testcontainer).

        db_engine fixture ensures tables are created/dropped for each test.
        """
        return create_app(settings)

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        with TestClient(app) as client:
            yield client

    @pytest.fixture(autouse=True)
    def _provision_users(self, client: TestClient):
        """Provision test users in DB so identity middleware can resolve roles."""
        seed_test_users(client)

    @pytest.fixture
    def ops_headers(self) -> dict:
        return {
            "X-Username": "ops.user",
        }

    @pytest.fixture
    def analyst_headers(self) -> dict:
        return {
            "X-Username": "analyst.user",
        }

    @pytest.fixture
    def admin_headers(self) -> dict:
        """Headers for admin user (should NOT have access to cluster endpoints)."""
        return {
            "X-Username": "bob.admin",
        }

    @pytest.fixture
    def internal_headers(self) -> dict:
        return {
            "X-Internal-Api-Key": "test-internal-key",
        }

    # === Authorization tests: Admin rejected from cluster endpoints ===

    def test_get_cluster_health_rejects_admin(self, client: TestClient, admin_headers: dict):
        """Admin cannot access cluster health (ops-only)."""
        response = client.get("/api/cluster/health", headers=admin_headers)
        assert response.status_code == 403

    def test_get_cluster_instances_rejects_admin(self, client: TestClient, admin_headers: dict):
        """Admin cannot access cluster instances (ops-only)."""
        response = client.get("/api/cluster/instances", headers=admin_headers)
        assert response.status_code == 403

    # === Ops success tests ===

    def test_get_cluster_health(self, client: TestClient, ops_headers: dict):
        """Test getting cluster health."""
        response = client.get("/api/cluster/health", headers=ops_headers)

        assert response.status_code == 200
        data = response.json()
        assert "status" in data["data"]
        assert "components" in data["data"]
        assert "checked_at" in data["data"]
        # Database should be connected
        assert data["data"]["components"]["database"]["status"] == "connected"
        assert data["data"]["status"] == "healthy"

    def test_get_cluster_health_not_ops(self, client: TestClient, analyst_headers: dict):
        """Test analysts cannot access cluster health."""
        response = client.get("/api/cluster/health", headers=analyst_headers)

        assert response.status_code == 403

    def test_get_cluster_instances_empty(self, client: TestClient, ops_headers: dict):
        """Test getting cluster instances when empty."""
        response = client.get("/api/cluster/instances", headers=ops_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["total"] == 0
        assert data["data"]["by_status"] == {}
        assert data["data"]["by_owner"] == []
        assert "limits" in data["data"]
        assert data["data"]["limits"]["per_analyst"] == 10
        assert data["data"]["limits"]["cluster_total"] == 50

    def test_get_cluster_instances_not_ops(self, client: TestClient, analyst_headers: dict):
        """Test analysts cannot access cluster instances."""
        response = client.get("/api/cluster/instances", headers=analyst_headers)

        assert response.status_code == 403

    # =========================================================================
    # SNAPSHOT API TEST DISABLED
    # This test is commented out because it depends on the deprecated snapshot
    # API (POST /api/snapshots) which has been removed. Use create_from_mapping()
    # workflow instead.
    # =========================================================================
    # def test_get_cluster_instances_with_data(
    #     self,
    #     client: TestClient,
    #     ops_headers: dict,
    #     analyst_headers: dict,
    #     internal_headers: dict,
    # ):
    #     """Test getting cluster instances with some instances created."""
    #     # Create mapping and snapshot
    #     mapping_response = client.post(
    #         "/api/mappings",
    #         json={
    #             "name": "Test Mapping",
    #             "node_definitions": [
    #                 {
    #                     "label": "TestNode",
    #                     "sql": "SELECT id FROM test",
    #                     "primary_key": {"name": "id", "type": "STRING"},
    #                     "properties": [],
    #                 },
    #             ],
    #         },
    #         headers=analyst_headers,
    #     )
    #     mapping_id = mapping_response.json()["data"]["id"]
    #
    #     snapshot_response = client.post(
    #         "/api/snapshots",
    #         json={"mapping_id": mapping_id, "name": "Test Snapshot"},
    #         headers=analyst_headers,
    #     )
    #     snapshot_id = snapshot_response.json()["data"]["id"]
    #
    #     # Mark snapshot as ready
    #     client.patch(
    #         f"/api/internal/snapshots/{snapshot_id}/status",
    #         json={"status": "ready", "size_bytes": 1024},
    #         headers=internal_headers,
    #     )
    #
    #     # Create two instances
    #     for i in range(2):
    #         client.post(
    #             "/api/instances",
    #             json={
    #                 "snapshot_id": snapshot_id,
    #                 "name": f"Instance {i}",
    #                 "wrapper_type": "ryugraph",
    #             },
    #             headers=analyst_headers,
    #         )
    #
    #     # Get cluster instances
    #     response = client.get("/api/cluster/instances", headers=ops_headers)
    #
    #     assert response.status_code == 200
    #     data = response.json()
    #     assert data["data"]["total"] == 2
    #     assert "starting" in data["data"]["by_status"]
    #     assert data["data"]["by_status"]["starting"] == 2
    #     assert len(data["data"]["by_owner"]) == 1
    #     assert data["data"]["by_owner"][0]["owner_username"] == "analyst.user"
    #     assert data["data"]["by_owner"][0]["count"] == 2
    #     assert data["data"]["limits"]["cluster_used"] == 2
    #     assert data["data"]["limits"]["cluster_available"] == 48  # 50 - 2
