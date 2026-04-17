"""Integration tests for schema API."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from control_plane.cache.schema_cache import (
    Catalog,
    Column,
    Schema,
    SchemaMetadataCache,
    Table,
)
from control_plane.config import Settings
from control_plane.main import create_app

from tests.integration.conftest import seed_test_users


class TestSchemaAPI:
    """Integration tests for /api/schema endpoints."""

    @pytest.fixture
    def settings(self, postgres_container) -> Settings:
        """Override settings to add starburst_url for schema tests."""
        from testcontainers.postgres import PostgresContainer

        url = postgres_container.get_connection_url()
        async_url = url.replace("postgresql://", "postgresql+asyncpg://")
        return Settings(
            database_url=async_url,
            debug=True,
            internal_api_key="test-internal-key",
            starburst_url="https://starburst.test",  # Dummy URL for tests
        )

    @pytest.fixture
    def app(self, settings: Settings, db_engine) -> FastAPI:
        """Use settings with PostgreSQL testcontainer.

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
    def admin_headers(self) -> dict:
        return {
            "X-Username": "admin.user",
        }

    @pytest.fixture
    async def seed_cache(self, app: FastAPI):
        """Seed cache with test data."""
        cache: SchemaMetadataCache = app.state.schema_cache

        # Create test data
        col1 = Column("id", "bigint", False, 1, None)
        col2 = Column("name", "varchar", True, 2, None)
        col3 = Column("email", "varchar", True, 3, None)

        users_table = Table("users", "BASE TABLE", (col1, col2, col3))
        customers_table = Table("customers", "BASE TABLE", (col1, col2, col3))

        public_schema = Schema("public", {"users": users_table})
        sales_schema = Schema("sales", {"customers": customers_table})

        analytics_catalog = Catalog("analytics", {"public": public_schema})
        marketing_catalog = Catalog("marketing", {"sales": sales_schema})

        await cache.refresh({
            "analytics": analytics_catalog,
            "marketing": marketing_catalog,
        })

    def test_list_catalogs_empty(self, client: TestClient, auth_headers: dict):
        """Test listing catalogs when cache is empty."""
        response = client.get("/api/schema/catalogs", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["data"] == []

    @pytest.mark.asyncio
    async def test_list_catalogs(
        self, client: TestClient, auth_headers: dict, seed_cache
    ):
        """Test listing catalogs."""
        response = client.get("/api/schema/catalogs", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 2
        assert data["data"][0]["catalog_name"] == "analytics"
        assert data["data"][0]["schema_count"] == 1
        assert data["data"][1]["catalog_name"] == "marketing"

    @pytest.mark.asyncio
    async def test_list_schemas(
        self, client: TestClient, auth_headers: dict, seed_cache
    ):
        """Test listing schemas in a catalog."""
        response = client.get(
            "/api/schema/catalogs/analytics/schemas", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["schema_name"] == "public"
        assert data["data"][0]["catalog_name"] == "analytics"
        assert data["data"][0]["table_count"] == 1

    def test_list_schemas_catalog_not_found(
        self, client: TestClient, auth_headers: dict
    ):
        """Test listing schemas for non-existent catalog."""
        response = client.get(
            "/api/schema/catalogs/nonexistent/schemas", headers=auth_headers
        )

        assert response.status_code == 404
        assert "not found in cache" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_list_tables(
        self, client: TestClient, auth_headers: dict, seed_cache
    ):
        """Test listing tables in a schema."""
        response = client.get(
            "/api/schema/catalogs/analytics/schemas/public/tables",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["table_name"] == "users"
        assert data["data"][0]["table_type"] == "BASE TABLE"
        assert data["data"][0]["column_count"] == 3

    def test_list_tables_schema_not_found(
        self, client: TestClient, auth_headers: dict
    ):
        """Test listing tables for non-existent schema."""
        response = client.get(
            "/api/schema/catalogs/analytics/schemas/nonexistent/tables",
            headers=auth_headers,
        )

        assert response.status_code == 404
        assert "not found in cache" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_list_columns(
        self, client: TestClient, auth_headers: dict, seed_cache
    ):
        """Test listing columns for a table."""
        response = client.get(
            "/api/schema/catalogs/analytics/schemas/public/tables/users/columns",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 3
        assert data["data"][0]["column_name"] == "id"
        assert data["data"][0]["data_type"] == "bigint"
        assert data["data"][0]["is_nullable"] is False
        assert data["data"][1]["column_name"] == "name"
        assert data["data"][2]["column_name"] == "email"

    def test_list_columns_table_not_found(
        self, client: TestClient, auth_headers: dict
    ):
        """Test listing columns for non-existent table."""
        response = client.get(
            "/api/schema/catalogs/analytics/schemas/public/tables/nonexistent/columns",
            headers=auth_headers,
        )

        assert response.status_code == 404
        assert "not found in cache" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_search_tables(
        self, client: TestClient, auth_headers: dict, seed_cache
    ):
        """Test searching tables by name pattern."""
        response = client.get(
            "/api/schema/search/tables",
            params={"q": "user", "limit": 10},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["table_name"] == "users"

    @pytest.mark.asyncio
    async def test_search_tables_no_results(
        self, client: TestClient, auth_headers: dict, seed_cache
    ):
        """Test searching tables with no matches."""
        response = client.get(
            "/api/schema/search/tables",
            params={"q": "nonexistent", "limit": 10},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["data"] == []

    @pytest.mark.asyncio
    async def test_search_tables_with_limit(
        self, client: TestClient, auth_headers: dict, seed_cache
    ):
        """Test search tables respects limit parameter."""
        response = client.get(
            "/api/schema/search/tables",
            params={"q": "user", "limit": 1},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) <= 1

    @pytest.mark.asyncio
    async def test_search_columns(
        self, client: TestClient, auth_headers: dict, seed_cache
    ):
        """Test searching columns by name pattern."""
        response = client.get(
            "/api/schema/search/columns",
            params={"q": "email", "limit": 10},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 2  # email column in users and customers
        assert all(col["column_name"] == "email" for col in data["data"])

    @pytest.mark.asyncio
    async def test_search_columns_case_insensitive(
        self, client: TestClient, auth_headers: dict, seed_cache
    ):
        """Test column search is case-insensitive."""
        response = client.get(
            "/api/schema/search/columns",
            params={"q": "EMAIL", "limit": 10},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) >= 1

    def test_trigger_refresh_requires_admin(
        self, client: TestClient, auth_headers: dict
    ):
        """Test refresh endpoint requires admin role."""
        response = client.post(
            "/api/schema/admin/refresh", headers=auth_headers
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_trigger_refresh(
        self, client: TestClient, admin_headers: dict, seed_cache
    ):
        """Test manual cache refresh (admin only)."""
        # Mock the background job to avoid making real HTTP requests
        with patch("control_plane.routers.api.schema.run_schema_cache_job", new=AsyncMock()):
            response = client.post(
                "/api/schema/admin/refresh", headers=admin_headers
            )

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["status"] == "refresh triggered"

    def test_get_stats_requires_admin(
        self, client: TestClient, auth_headers: dict
    ):
        """Test stats endpoint requires admin role."""
        response = client.get("/api/schema/stats", headers=auth_headers)

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_get_stats(
        self, client: TestClient, admin_headers: dict, seed_cache
    ):
        """Test getting cache statistics (admin only)."""
        response = client.get("/api/schema/stats", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        stats = data["data"]
        assert stats["total_catalogs"] == 2
        assert stats["total_schemas"] == 2
        assert stats["total_tables"] == 2
        assert stats["total_columns"] == 6
        assert "last_refresh" in stats
        assert "index_size_bytes" in stats

    def test_search_tables_query_required(
        self, client: TestClient, auth_headers: dict
    ):
        """Test search tables requires query parameter."""
        response = client.get(
            "/api/schema/search/tables", headers=auth_headers
        )

        assert response.status_code in (400, 422)  # Validation error

    def test_search_columns_query_required(
        self, client: TestClient, auth_headers: dict
    ):
        """Test search columns requires query parameter."""
        response = client.get(
            "/api/schema/search/columns", headers=auth_headers
        )

        assert response.status_code in (400, 422)  # Validation error
