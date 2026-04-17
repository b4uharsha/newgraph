"""Integration tests for /api/export-jobs (role-scoped) endpoint."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from control_plane.config import Settings
from control_plane.main import create_app

from tests.integration.conftest import seed_test_users


class TestExportJobsAPI:
    """Integration tests for /api/export-jobs with role-scoped access."""

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
    def analyst_headers(self) -> dict:
        """Headers for analyst user (sees own exports only)."""
        return {
            "X-Username": "alice.smith",
        }

    @pytest.fixture
    def admin_headers(self) -> dict:
        """Headers for admin user (sees all exports)."""
        return {
            "X-Username": "bob.admin",
        }

    @pytest.fixture
    def ops_headers(self) -> dict:
        """Headers for ops user (sees all exports)."""
        return {
            "X-Username": "charlie.ops",
        }

    # Authorization tests

    @pytest.mark.integration
    def test_unauthenticated_rejected(self, client: TestClient):
        """Unauthenticated request is rejected."""
        response = client.get("/api/export-jobs")

        assert response.status_code == 401

    @pytest.mark.integration
    def test_analyst_can_access(self, client: TestClient, analyst_headers: dict):
        """Analyst can access scoped export jobs endpoint."""
        response = client.get("/api/export-jobs", headers=analyst_headers)

        assert response.status_code == 200
        data = response.json()
        assert "jobs" in data["data"]

    @pytest.mark.integration
    def test_admin_can_access(self, client: TestClient, admin_headers: dict):
        """Admin can access export jobs endpoint."""
        response = client.get("/api/export-jobs", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert "jobs" in data["data"]

    @pytest.mark.integration
    def test_ops_can_access(self, client: TestClient, ops_headers: dict):
        """Ops can access export jobs endpoint."""
        response = client.get("/api/export-jobs", headers=ops_headers)

        assert response.status_code == 200
        data = response.json()
        assert "jobs" in data["data"]

    # Filtering tests

    @pytest.mark.integration
    def test_status_filter(self, client: TestClient, ops_headers: dict):
        """Status filter parameter works."""
        for status in ["pending", "claimed", "completed", "failed"]:
            response = client.get(
                f"/api/export-jobs?status={status}",
                headers=ops_headers,
            )

            assert response.status_code == 200
            jobs = response.json()["data"]["jobs"]

            for job in jobs:
                assert job["status"] == status

    @pytest.mark.integration
    def test_limit_parameter(self, client: TestClient, ops_headers: dict):
        """Limit parameter caps results."""
        response = client.get(
            "/api/export-jobs?limit=5",
            headers=ops_headers,
        )

        assert response.status_code == 200
        jobs = response.json()["data"]["jobs"]
        assert len(jobs) <= 5
