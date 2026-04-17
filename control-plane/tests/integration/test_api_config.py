"""Integration tests for config API."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from control_plane.config import Settings
from control_plane.main import create_app

from tests.integration.conftest import seed_test_users


class TestConfigAPI:
    """Integration tests for /api/config endpoints."""

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
        """Headers for admin user (should NOT have access to config endpoints)."""
        return {
            "X-Username": "bob.admin",
        }

    # === Authorization tests: Admin rejected from config endpoints ===

    def test_get_lifecycle_config_rejects_admin(self, client: TestClient, admin_headers: dict):
        """Admin cannot access lifecycle config (ops-only)."""
        response = client.get("/api/config/lifecycle", headers=admin_headers)
        assert response.status_code == 403

    def test_get_concurrency_config_rejects_admin(self, client: TestClient, admin_headers: dict):
        """Admin cannot access concurrency config (ops-only)."""
        response = client.get("/api/config/concurrency", headers=admin_headers)
        assert response.status_code == 403

    def test_get_maintenance_mode_rejects_admin(self, client: TestClient, admin_headers: dict):
        """Admin cannot access maintenance mode (ops-only)."""
        response = client.get("/api/config/maintenance", headers=admin_headers)
        assert response.status_code == 403

    def test_get_export_config_rejects_admin(self, client: TestClient, admin_headers: dict):
        """Admin cannot access export config (ops-only)."""
        response = client.get("/api/config/export", headers=admin_headers)
        assert response.status_code == 403

    # === Ops success tests ===

    def test_get_lifecycle_config(self, client: TestClient, ops_headers: dict):
        """Test getting lifecycle configuration."""
        response = client.get("/api/config/lifecycle", headers=ops_headers)

        assert response.status_code == 200
        data = response.json()
        assert "mapping" in data["data"]
        assert "snapshot" in data["data"]
        assert "instance" in data["data"]
        # Check default values are present
        assert data["data"]["instance"]["default_ttl"] == "PT24H"
        assert data["data"]["snapshot"]["default_ttl"] == "P7D"

    def test_get_lifecycle_config_not_ops(self, client: TestClient, analyst_headers: dict):
        """Test analysts cannot access lifecycle config."""
        response = client.get("/api/config/lifecycle", headers=analyst_headers)

        assert response.status_code == 403

    def test_update_lifecycle_config(self, client: TestClient, ops_headers: dict):
        """Test updating lifecycle configuration."""
        response = client.put(
            "/api/config/lifecycle",
            json={
                "instance": {
                    "default_ttl": "PT48H",
                    "default_inactivity": "PT8H",
                }
            },
            headers=ops_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["updated"] is True

        # Verify the update
        get_response = client.get("/api/config/lifecycle", headers=ops_headers)
        assert get_response.json()["data"]["instance"]["default_ttl"] == "PT48H"

    def test_get_concurrency_config(self, client: TestClient, ops_headers: dict):
        """Test getting concurrency configuration."""
        response = client.get("/api/config/concurrency", headers=ops_headers)

        assert response.status_code == 200
        data = response.json()
        assert "per_analyst" in data["data"]
        assert "cluster_total" in data["data"]
        # Check default values (from config.py defaults)
        assert data["data"]["per_analyst"] == 10
        assert data["data"]["cluster_total"] == 50

    def test_get_concurrency_config_not_ops(self, client: TestClient, analyst_headers: dict):
        """Test analysts cannot access concurrency config."""
        response = client.get("/api/config/concurrency", headers=analyst_headers)

        assert response.status_code == 403

    def test_update_concurrency_config(self, client: TestClient, ops_headers: dict):
        """Test updating concurrency configuration."""
        response = client.put(
            "/api/config/concurrency",
            json={
                "per_analyst": 10,
                "cluster_total": 100,
            },
            headers=ops_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["per_analyst"] == 10
        assert data["data"]["cluster_total"] == 100

        # Verify the update
        get_response = client.get("/api/config/concurrency", headers=ops_headers)
        assert get_response.json()["data"]["per_analyst"] == 10

    def test_update_concurrency_config_validation(self, client: TestClient, ops_headers: dict):
        """Test concurrency config validation."""
        response = client.put(
            "/api/config/concurrency",
            json={
                "per_analyst": 0,  # Invalid - must be >= 1
                "cluster_total": 50,
            },
            headers=ops_headers,
        )

        assert response.status_code == 422

    def test_get_maintenance_mode(self, client: TestClient, ops_headers: dict):
        """Test getting maintenance mode status."""
        response = client.get("/api/config/maintenance", headers=ops_headers)

        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data["data"]
        assert "message" in data["data"]
        # Default is disabled
        assert data["data"]["enabled"] is False

    def test_get_maintenance_mode_not_ops(self, client: TestClient, analyst_headers: dict):
        """Test analysts cannot access maintenance mode."""
        response = client.get("/api/config/maintenance", headers=analyst_headers)

        assert response.status_code == 403

    def test_set_maintenance_mode(self, client: TestClient, ops_headers: dict):
        """Test enabling maintenance mode."""
        response = client.put(
            "/api/config/maintenance",
            json={
                "enabled": True,
                "message": "Scheduled maintenance",
            },
            headers=ops_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["enabled"] is True
        assert data["data"]["message"] == "Scheduled maintenance"
        assert data["data"]["updated_by"] == "ops.user"

        # Verify the update
        get_response = client.get("/api/config/maintenance", headers=ops_headers)
        assert get_response.json()["data"]["enabled"] is True

    def test_disable_maintenance_mode(self, client: TestClient, ops_headers: dict):
        """Test disabling maintenance mode."""
        # First enable it
        client.put(
            "/api/config/maintenance",
            json={"enabled": True, "message": "Maintenance"},
            headers=ops_headers,
        )

        # Then disable it
        response = client.put(
            "/api/config/maintenance",
            json={"enabled": False, "message": ""},
            headers=ops_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["enabled"] is False

        # Verify
        get_response = client.get("/api/config/maintenance", headers=ops_headers)
        assert get_response.json()["data"]["enabled"] is False

    def test_get_export_config(self, client: TestClient, ops_headers: dict):
        """Test getting export configuration."""
        response = client.get("/api/config/export", headers=ops_headers)

        assert response.status_code == 200
        data = response.json()
        assert "max_duration_seconds" in data["data"]
        # Check default value
        assert data["data"]["max_duration_seconds"] == 3600

    def test_get_export_config_not_ops(self, client: TestClient, analyst_headers: dict):
        """Test analysts cannot access export config."""
        response = client.get("/api/config/export", headers=analyst_headers)

        assert response.status_code == 403

    def test_update_export_config(self, client: TestClient, ops_headers: dict):
        """Test updating export configuration."""
        response = client.put(
            "/api/config/export",
            json={"max_duration_seconds": 7200},
            headers=ops_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["max_duration_seconds"] == 7200
        assert data["data"]["updated_by"] == "ops.user"

        # Verify the update
        get_response = client.get("/api/config/export", headers=ops_headers)
        assert get_response.json()["data"]["max_duration_seconds"] == 7200

    def test_update_export_config_validation_min(self, client: TestClient, ops_headers: dict):
        """Test export config validation - minimum value."""
        response = client.put(
            "/api/config/export",
            json={"max_duration_seconds": 30},  # Invalid - must be >= 60
            headers=ops_headers,
        )

        assert response.status_code == 422

    def test_update_export_config_validation_max(self, client: TestClient, ops_headers: dict):
        """Test export config validation - maximum value."""
        response = client.put(
            "/api/config/export",
            json={"max_duration_seconds": 100000},  # Invalid - must be <= 86400
            headers=ops_headers,
        )

        assert response.status_code == 422
