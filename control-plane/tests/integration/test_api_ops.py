"""Integration tests for /api/ops/* endpoints."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from control_plane.config import Settings
from control_plane.main import create_app

from tests.integration.conftest import seed_test_users


class TestOpsJobsAPI:
    """Integration tests for /api/ops/jobs/* endpoints."""

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
    def ops_headers(self) -> dict:
        """Headers for ops user."""
        return {
            "X-Username": "charlie.ops",
        }

    @pytest.fixture
    def analyst_headers(self) -> dict:
        """Headers for analyst user (should NOT have access)."""
        return {
            "X-Username": "alice.smith",
        }

    @pytest.fixture
    def admin_headers(self) -> dict:
        """Headers for admin user (should NOT have access to ops endpoints)."""
        return {
            "X-Username": "bob.admin",
        }

    # Authorization tests

    @pytest.mark.integration
    def test_trigger_job_requires_ops_role(self, client: TestClient, analyst_headers: dict):
        """Analyst cannot trigger jobs."""
        response = client.post(
            "/api/ops/jobs/trigger",
            json={"job_name": "reconciliation", "reason": "test"},
            headers=analyst_headers,
        )

        assert response.status_code == 403

    @pytest.mark.integration
    def test_get_job_status_requires_ops_role(self, client: TestClient, analyst_headers: dict):
        """Analyst cannot view job status."""
        response = client.get(
            "/api/ops/jobs/status",
            headers=analyst_headers,
        )

        assert response.status_code == 403

    @pytest.mark.integration
    def test_get_state_requires_ops_role(self, client: TestClient, analyst_headers: dict):
        """Analyst cannot view system state."""
        response = client.get(
            "/api/ops/state",
            headers=analyst_headers,
        )

        assert response.status_code == 403

    @pytest.mark.integration
    def test_get_export_jobs_requires_ops_role(self, client: TestClient, analyst_headers: dict):
        """Analyst cannot view export jobs."""
        response = client.get(
            "/api/ops/export-jobs",
            headers=analyst_headers,
        )

        assert response.status_code == 403

    @pytest.mark.integration
    def test_trigger_job_rejects_admin_role(self, client: TestClient, admin_headers: dict):
        """Admin cannot trigger ops jobs (ops-only)."""
        response = client.post(
            "/api/ops/jobs/trigger",
            json={"job_name": "reconciliation", "reason": "test"},
            headers=admin_headers,
        )

        assert response.status_code == 403

    @pytest.mark.integration
    def test_get_job_status_rejects_admin_role(self, client: TestClient, admin_headers: dict):
        """Admin cannot view ops job status (ops-only)."""
        response = client.get(
            "/api/ops/jobs/status",
            headers=admin_headers,
        )

        assert response.status_code == 403

    @pytest.mark.integration
    def test_get_state_rejects_admin_role(self, client: TestClient, admin_headers: dict):
        """Admin cannot view ops system state (ops-only)."""
        response = client.get(
            "/api/ops/state",
            headers=admin_headers,
        )

        assert response.status_code == 403

    @pytest.mark.integration
    def test_get_export_jobs_rejects_admin_role(self, client: TestClient, admin_headers: dict):
        """Admin cannot view ops export jobs (ops-only)."""
        response = client.get(
            "/api/ops/export-jobs",
            headers=admin_headers,
        )

        assert response.status_code == 403

    # Validation tests

    @pytest.mark.integration
    def test_trigger_job_invalid_name_returns_422(self, client: TestClient, ops_headers: dict):
        """Invalid job name is rejected by validation."""
        response = client.post(
            "/api/ops/jobs/trigger",
            json={"job_name": "invalid_job", "reason": "test"},
            headers=ops_headers,
        )

        # Pydantic validation rejects invalid job names with 422
        assert response.status_code == 422

    @pytest.mark.integration
    def test_trigger_job_missing_reason_returns_422(self, client: TestClient, ops_headers: dict):
        """Missing reason is rejected."""
        response = client.post(
            "/api/ops/jobs/trigger",
            json={"job_name": "reconciliation"},  # Missing reason
            headers=ops_headers,
        )

        assert response.status_code == 422

    # Success tests

    @pytest.mark.integration
    def test_trigger_job_success(self, client: TestClient, ops_headers: dict):
        """Ops can trigger job successfully."""
        response = client.post(
            "/api/ops/jobs/trigger",
            json={"job_name": "reconciliation", "reason": "integration-test"},
            headers=ops_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["job_name"] == "reconciliation"
        assert data["data"]["status"] == "queued"
        assert "triggered_at" in data["data"]
        assert data["data"]["triggered_by"] == "charlie.ops"
        assert data["data"]["reason"] == "integration-test"

    @pytest.mark.integration
    def test_get_job_status_returns_all_jobs(self, client: TestClient, ops_headers: dict):
        """Returns status of all 6 background jobs."""
        response = client.get(
            "/api/ops/jobs/status",
            headers=ops_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "jobs" in data["data"]
        assert len(data["data"]["jobs"]) == 6

        job_names = [j["name"] for j in data["data"]["jobs"]]
        expected_jobs = {
            "reconciliation",
            "lifecycle",
            "export_reconciliation",
            "schema_cache",
            "instance_orchestration",
            "resource_monitor",
        }
        assert set(job_names) == expected_jobs

        # Verify job structure
        for job in data["data"]["jobs"]:
            assert "name" in job
            assert "next_run" in job

    @pytest.mark.integration
    def test_get_state_returns_counts(self, client: TestClient, ops_headers: dict):
        """Returns system state counts."""
        response = client.get(
            "/api/ops/state",
            headers=ops_headers,
        )

        assert response.status_code == 200
        data = response.json()

        # Verify structure
        assert "instances" in data["data"]
        assert "snapshots" in data["data"]
        assert "export_jobs" in data["data"]

        # Verify instances structure
        assert "total" in data["data"]["instances"]
        assert "by_status" in data["data"]["instances"]
        assert "without_pod_name" in data["data"]["instances"]

        # Verify snapshots structure
        assert "total" in data["data"]["snapshots"]
        assert "by_status" in data["data"]["snapshots"]

        # Verify export_jobs structure
        assert "by_status" in data["data"]["export_jobs"]

        # Verify counts are non-negative
        assert data["data"]["instances"]["total"] >= 0
        assert data["data"]["snapshots"]["total"] >= 0

    @pytest.mark.integration
    def test_get_export_jobs_filters_by_status(self, client: TestClient, ops_headers: dict):
        """Filter export jobs by status."""
        # Test filtering by each status
        for status in ["pending", "claimed", "completed", "failed"]:
            response = client.get(
                f"/api/ops/export-jobs?status={status}",
                headers=ops_headers,
            )

            assert response.status_code == 200
            jobs = response.json()["data"]["jobs"]

            # All returned jobs should have the requested status
            for job in jobs:
                assert job["status"] == status

    @pytest.mark.integration
    def test_get_export_jobs_respects_limit(self, client: TestClient, ops_headers: dict):
        """Limit parameter works."""
        response = client.get(
            "/api/ops/export-jobs?limit=5",
            headers=ops_headers,
        )

        assert response.status_code == 200
        jobs = response.json()["data"]["jobs"]
        assert len(jobs) <= 5

    @pytest.mark.integration
    def test_get_export_jobs_structure(self, client: TestClient, ops_headers: dict):
        """Returns valid export job structure."""
        response = client.get(
            "/api/ops/export-jobs?limit=10",
            headers=ops_headers,
        )

        assert response.status_code == 200
        jobs = response.json()["data"]["jobs"]

        if len(jobs) > 0:
            # Verify first job has required fields
            job = jobs[0]
            required_fields = [
                "id",
                "snapshot_id",
                "entity_type",
                "entity_name",
                "status",
                "attempts",
            ]

            for field in required_fields:
                assert field in job, f"Export job missing required field: {field}"

            # Verify status is valid
            assert job["status"] in ["pending", "claimed", "completed", "failed"]

            # Verify attempts is non-negative
            assert job["attempts"] >= 0
