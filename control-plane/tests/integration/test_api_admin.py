"""Integration tests for /api/admin/* endpoints."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from control_plane.config import Settings
from control_plane.main import create_app

from tests.integration.conftest import seed_test_users


class TestAdminBulkDeleteAPI:
    """Integration tests for /api/admin/resources/bulk endpoint."""

    @pytest.fixture
    def app(self, settings: Settings, db_engine) -> FastAPI:
        """Create app with test database (PostgreSQL from conftest.py).

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
    def admin_headers(self) -> dict:
        """Headers for admin user."""
        return {
            "X-Username": "bob.admin",
        }

    @pytest.fixture
    def ops_headers(self) -> dict:
        """Headers for ops user (inherits admin access via hierarchy)."""
        return {
            "X-Username": "charlie.ops",
        }

    @pytest.fixture
    def analyst_headers(self) -> dict:
        """Headers for analyst user."""
        return {
            "X-Username": "alice.smith",
        }

    # Authorization tests

    @pytest.mark.integration
    def test_bulk_delete_allows_ops_role(self, client: TestClient, ops_headers: dict):
        """Ops can bulk delete (inherits admin via hierarchy)."""
        response = client.request(
            "DELETE",
            "/api/admin/resources/bulk",
            json={
                "resource_type": "instance",
                "filters": {"name_prefix": "test"},
                "reason": "test",
                "dry_run": True,
            },
            headers=ops_headers,
        )

        # Ops inherits admin permissions - gets 200 (dry run, 0 matches)
        assert response.status_code == 200

    @pytest.mark.integration
    def test_bulk_delete_rejects_analyst(self, client: TestClient, analyst_headers: dict):
        """Analyst cannot bulk delete."""
        response = client.request(
            "DELETE",
            "/api/admin/resources/bulk",
            json={
                "resource_type": "instance",
                "filters": {"name_prefix": "test"},
                "reason": "test",
                "dry_run": True,
            },
            headers=analyst_headers,
        )

        assert response.status_code == 403

    # Validation - Safety checks

    @pytest.mark.integration
    def test_bulk_delete_requires_filters(self, client: TestClient, admin_headers: dict):
        """Empty filters are rejected."""
        response = client.request(
            "DELETE",
            "/api/admin/resources/bulk",
            json={
                "resource_type": "instance",
                "filters": {},  # No filters!
                "reason": "test",
                "dry_run": True,
            },
            headers=admin_headers,
        )

        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "VALIDATION_FAILED"
        assert "filter" in data["error"]["message"].lower()

    @pytest.mark.integration
    def test_bulk_delete_invalid_resource_type(self, client: TestClient, admin_headers: dict):
        """Invalid resource_type is rejected."""
        response = client.request(
            "DELETE",
            "/api/admin/resources/bulk",
            json={
                "resource_type": "invalid_type",
                "filters": {"name_prefix": "test"},
                "reason": "test",
            },
            headers=admin_headers,
        )

        assert response.status_code == 422  # Pydantic validation error

    @pytest.mark.integration
    def test_bulk_delete_missing_reason_returns_422(self, client: TestClient, admin_headers: dict):
        """Missing reason is rejected."""
        response = client.request(
            "DELETE",
            "/api/admin/resources/bulk",
            json={
                "resource_type": "instance",
                "filters": {"name_prefix": "test"},
                # Missing reason
            },
            headers=admin_headers,
        )

        assert response.status_code == 422  # Pydantic validation error

    # Dry run mode

    @pytest.mark.integration
    def test_bulk_delete_dry_run_returns_matches(self, client: TestClient, admin_headers: dict):
        """Dry run returns what would be deleted without deleting."""
        # Create some test instances first
        for i in range(3):
            client.post(
                "/api/mappings",
                json={
                    "name": f"BulkTest-Mapping-{i}",
                    "node_definitions": [
                        {
                            "label": "TestNode",
                            "sql": "SELECT id, name FROM test",
                            "primary_key": {"name": "id", "type": "STRING"},
                            "properties": [{"name": "name", "type": "STRING"}],
                        }
                    ],
                },
                headers=admin_headers,
            )

        # Dry run
        response = client.request(
            "DELETE",
            "/api/admin/resources/bulk",
            json={
                "resource_type": "mapping",
                "filters": {"name_prefix": "BulkTest-"},
                "reason": "dry-run-test",
                "dry_run": True,
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        data = response.json()["data"]

        # Verify dry run response
        assert data["dry_run"] is True
        assert data["matched_count"] == 3
        assert len(data["matched_ids"]) == 3
        assert data["deleted_count"] == 0
        assert len(data["deleted_ids"]) == 0

        # Verify nothing was actually deleted
        list_response = client.get("/api/mappings", headers=admin_headers)
        mappings = list_response.json()["data"]
        bulk_test_mappings = [m for m in mappings if m["name"].startswith("BulkTest-")]
        assert len(bulk_test_mappings) == 3

    # Expected count validation

    @pytest.mark.integration
    def test_bulk_delete_expected_count_mismatch_fails(self, client: TestClient, admin_headers: dict):
        """Wrong expected_count causes failure."""
        # Create test mappings
        for i in range(3):
            client.post(
                "/api/mappings",
                json={
                    "name": f"CountTest-Mapping-{i}",
                    "node_definitions": [
                        {
                            "label": "TestNode",
                            "sql": "SELECT id FROM test",
                            "primary_key": {"name": "id", "type": "STRING"},
                            "properties": [],
                        }
                    ],
                },
                headers=admin_headers,
            )

        # Try to delete with wrong expected_count
        response = client.request(
            "DELETE",
            "/api/admin/resources/bulk",
            json={
                "resource_type": "mapping",
                "filters": {"name_prefix": "CountTest-"},
                "reason": "test",
                "expected_count": 999,  # Wrong!
                "dry_run": False,
            },
            headers=admin_headers,
        )

        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "VALIDATION_FAILED"
        assert "expected" in data["error"]["message"].lower()

    # Success case

    @pytest.mark.integration
    def test_bulk_delete_success(self, client: TestClient, admin_headers: dict):
        """Bulk delete with correct expected_count succeeds."""
        # Create test mappings
        for i in range(3):
            client.post(
                "/api/mappings",
                json={
                    "name": f"DeleteTest-Mapping-{i}",
                    "node_definitions": [
                        {
                            "label": "TestNode",
                            "sql": "SELECT id FROM test",
                            "primary_key": {"name": "id", "type": "STRING"},
                            "properties": [],
                        }
                    ],
                },
                headers=admin_headers,
            )

        # Step 1: Dry run to get count
        dry_response = client.request(
            "DELETE",
            "/api/admin/resources/bulk",
            json={
                "resource_type": "mapping",
                "filters": {"name_prefix": "DeleteTest-"},
                "reason": "test-dry",
                "dry_run": True,
            },
            headers=admin_headers,
        )

        matched_count = dry_response.json()["data"]["matched_count"]
        assert matched_count == 3

        # Step 2: Delete with correct expected_count
        response = client.request(
            "DELETE",
            "/api/admin/resources/bulk",
            json={
                "resource_type": "mapping",
                "filters": {"name_prefix": "DeleteTest-"},
                "reason": "test-actual",
                "expected_count": matched_count,
                "dry_run": False,
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        data = response.json()["data"]

        # Verify response
        assert data["dry_run"] is False
        assert data["matched_count"] == 3
        assert data["deleted_count"] == 3
        assert len(data["failed_ids"]) == 0

        # Verify mappings are actually deleted
        list_response = client.get("/api/mappings", headers=admin_headers)
        mappings = list_response.json()["data"]
        delete_test_mappings = [m for m in mappings if m["name"].startswith("DeleteTest-")]
        assert len(delete_test_mappings) == 0

    # Filter tests

    @pytest.mark.integration
    def test_bulk_delete_filters_by_name_prefix(self, client: TestClient, admin_headers: dict):
        """name_prefix filter works correctly."""
        # Create mappings with different prefixes
        client.post(
            "/api/mappings",
            json={
                "name": "PrefixA-Mapping",
                "node_definitions": [
                    {
                        "label": "TestNode",
                        "sql": "SELECT id FROM test",
                        "primary_key": {"name": "id", "type": "STRING"},
                        "properties": [],
                    }
                ],
            },
            headers=admin_headers,
        )

        client.post(
            "/api/mappings",
            json={
                "name": "PrefixB-Mapping",
                "node_definitions": [
                    {
                        "label": "TestNode",
                        "sql": "SELECT id FROM test",
                        "primary_key": {"name": "id", "type": "STRING"},
                        "properties": [],
                    }
                ],
            },
            headers=admin_headers,
        )

        # Dry run filtering by PrefixA
        response = client.request(
            "DELETE",
            "/api/admin/resources/bulk",
            json={
                "resource_type": "mapping",
                "filters": {"name_prefix": "PrefixA-"},
                "reason": "test-filter",
                "dry_run": True,
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        data = response.json()["data"]

        # Should only match PrefixA mapping
        assert data["matched_count"] == 1

    @pytest.mark.integration
    def test_bulk_delete_filters_by_created_by(self, client: TestClient, admin_headers: dict):
        """created_by filter works correctly."""
        # Create mapping as admin
        client.post(
            "/api/mappings",
            json={
                "name": "AdminMapping",
                "node_definitions": [
                    {
                        "label": "TestNode",
                        "sql": "SELECT id FROM test",
                        "primary_key": {"name": "id", "type": "STRING"},
                        "properties": [],
                    }
                ],
            },
            headers=admin_headers,
        )

        # Dry run filtering by created_by
        response = client.request(
            "DELETE",
            "/api/admin/resources/bulk",
            json={
                "resource_type": "mapping",
                "filters": {"created_by": "bob.admin"},
                "reason": "test-filter",
                "dry_run": True,
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        data = response.json()["data"]

        # Should match mappings created by bob.admin
        assert data["matched_count"] >= 1
