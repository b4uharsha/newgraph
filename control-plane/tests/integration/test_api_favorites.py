"""Integration tests for favorites API."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from control_plane.config import Settings
from control_plane.main import create_app

from tests.integration.conftest import seed_test_users


class TestFavoritesAPI:
    """Integration tests for /api/favorites endpoints."""

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
    def auth_headers(self) -> dict:
        return {
            "X-Username": "test.user",
        }

    @pytest.fixture
    def mapping_id(self, client: TestClient, auth_headers: dict) -> int:
        """Create a mapping and return its ID."""
        response = client.post(
            "/api/mappings",
            json={
                "name": "Favorite Test Mapping",
                "node_definitions": [
                    {
                        "label": "TestNode",
                        "sql": "SELECT id FROM test",
                        "primary_key": {"name": "id", "type": "STRING"},
                        "properties": [],
                    },
                ],
            },
            headers=auth_headers,
        )
        return response.json()["data"]["id"]

    def test_list_favorites_empty(self, client: TestClient, auth_headers: dict):
        """Test listing favorites when none exist."""
        response = client.get(
            "/api/favorites",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["data"] == []

    def test_add_favorite(self, client: TestClient, auth_headers: dict, mapping_id: int):
        """Test adding a resource to favorites."""
        response = client.post(
            "/api/favorites",
            json={
                "resource_type": "mapping",
                "resource_id": mapping_id,
            },
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["data"]["resource_type"] == "mapping"
        assert data["data"]["resource_id"] == mapping_id
        assert "created_at" in data["data"]

    def test_add_favorite_resource_not_found(self, client: TestClient, auth_headers: dict):
        """Test adding non-existent resource to favorites fails."""
        response = client.post(
            "/api/favorites",
            json={
                "resource_type": "mapping",
                "resource_id": 99999,
            },
            headers=auth_headers,
        )

        assert response.status_code == 404

    def test_add_favorite_already_exists(
        self, client: TestClient, auth_headers: dict, mapping_id: int
    ):
        """Test adding duplicate favorite fails."""
        # Add first time
        client.post(
            "/api/favorites",
            json={
                "resource_type": "mapping",
                "resource_id": mapping_id,
            },
            headers=auth_headers,
        )

        # Try to add again
        response = client.post(
            "/api/favorites",
            json={
                "resource_type": "mapping",
                "resource_id": mapping_id,
            },
            headers=auth_headers,
        )

        assert response.status_code == 409
        data = response.json()
        assert data["error"]["code"] == "ALREADY_EXISTS"

    def test_list_favorites(self, client: TestClient, auth_headers: dict, mapping_id: int):
        """Test listing favorites with resource metadata."""
        # Add favorite
        client.post(
            "/api/favorites",
            json={
                "resource_type": "mapping",
                "resource_id": mapping_id,
            },
            headers=auth_headers,
        )

        # List favorites
        response = client.get(
            "/api/favorites",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["resource_type"] == "mapping"
        assert data["data"][0]["resource_id"] == mapping_id
        assert data["data"][0]["resource_name"] == "Favorite Test Mapping"
        assert data["data"][0]["resource_owner"] == "test.user"
        assert data["data"][0]["resource_exists"] is True

    def test_list_favorites_filter_by_type(
        self, client: TestClient, auth_headers: dict, mapping_id: int
    ):
        """Test filtering favorites by resource type."""
        # Add mapping favorite
        client.post(
            "/api/favorites",
            json={
                "resource_type": "mapping",
                "resource_id": mapping_id,
            },
            headers=auth_headers,
        )

        # Filter by mapping
        response = client.get(
            "/api/favorites?resource_type=mapping",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 1

        # Filter by snapshot (should be empty)
        response = client.get(
            "/api/favorites?resource_type=snapshot",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 0

    def test_remove_favorite(self, client: TestClient, auth_headers: dict, mapping_id: int):
        """Test removing a favorite."""
        # Add favorite
        client.post(
            "/api/favorites",
            json={
                "resource_type": "mapping",
                "resource_id": mapping_id,
            },
            headers=auth_headers,
        )

        # Remove it
        response = client.delete(
            f"/api/favorites/mapping/{mapping_id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["deleted"] is True

        # Verify it's gone
        response = client.get(
            "/api/favorites",
            headers=auth_headers,
        )
        assert len(response.json()["data"]) == 0

    def test_remove_favorite_not_found(self, client: TestClient, auth_headers: dict):
        """Test removing non-existent favorite is idempotent (returns 200 OK)."""
        response = client.delete(
            "/api/favorites/mapping/99999",
            headers=auth_headers,
        )

        # Idempotent DELETE: returns 200 OK whether favorite exists or not
        assert response.status_code == 200
        assert response.json()["data"]["deleted"] is True

    def test_favorites_user_isolation(
        self, client: TestClient, auth_headers: dict, mapping_id: int
    ):
        """Test that users only see their own favorites."""
        # User 1 adds favorite
        client.post(
            "/api/favorites",
            json={
                "resource_type": "mapping",
                "resource_id": mapping_id,
            },
            headers=auth_headers,
        )

        # User 2 should not see it
        other_headers = {
            "X-Username": "other.user",
        }
        response = client.get(
            "/api/favorites",
            headers=other_headers,
        )

        assert response.status_code == 200
        assert len(response.json()["data"]) == 0

    def test_delete_mapping_cascades_favorites(
        self, client: TestClient, auth_headers: dict, mapping_id: int
    ):
        """Test that deleting a mapping also deletes its favorites."""
        # Add mapping to favorites (user 1)
        client.post(
            "/api/favorites",
            json={
                "resource_type": "mapping",
                "resource_id": mapping_id,
            },
            headers=auth_headers,
        )

        # Verify favorite was added
        response = client.get(
            "/api/favorites",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

        # Delete the mapping
        client.delete(
            f"/api/mappings/{mapping_id}",
            headers=auth_headers,
        )

        # List favorites - should be empty (cascade deleted)
        response = client.get(
            "/api/favorites",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 0  # Favorite was cascade deleted
