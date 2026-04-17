"""Unit tests for Starburst metadata client."""

import httpx
import pytest
import respx

from control_plane.clients.starburst_metadata import (
    StarburstError,
    StarburstMetadataClient,
    StarburstQueryError,
    StarburstTimeoutError,
)
from control_plane.config import Settings


@pytest.fixture
def client():
    """Create Starburst client for testing."""
    return StarburstMetadataClient(
        url="https://starburst.test",
        user="test-user",
        password="test-pass",
        timeout=30.0,
    )


@pytest.fixture
def settings():
    """Create test settings."""
    return Settings(
        starburst_url="https://starburst.test",
        starburst_user="test-user",
        starburst_password="test-pass",  # type: ignore
        starburst_timeout_seconds=30,
    )


class TestStarburstMetadataClient:
    """Tests for StarburstMetadataClient."""

    def test_from_config(self, settings):
        """Test from_config() factory method."""
        client = StarburstMetadataClient.from_config(settings)

        assert client.url == "https://starburst.test"
        assert client.auth == ("test-user", "test-pass")
        assert client.timeout == 30.0

    @pytest.mark.asyncio
    async def test_context_manager(self, client):
        """Test async context manager."""
        async with client:
            assert client._client is not None

        # After exit, client should be closed
        assert client._client is None

    @pytest.mark.asyncio
    async def test_close(self, client):
        """Test explicit close()."""
        async with client:
            assert client._client is not None

        await client.close()
        assert client._client is None

    @pytest.mark.asyncio
    @respx.mock
    async def test_execute_query_success(self, client):
        """Test successful query execution."""
        # Mock query submission
        submit_route = respx.post("https://starburst.test/v1/statement").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "query-123",
                    "nextUri": "https://starburst.test/v1/statement/query-123/1",
                },
            )
        )

        # Mock polling response with results
        poll_route = respx.get(
            "https://starburst.test/v1/statement/query-123/1"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "query-123",
                    "columns": [{"name": "catalog_name"}],
                    "data": [["analytics"], ["sales"]],
                },
            )
        )

        async with client:
            results = await client.execute_query(
                "SELECT catalog_name FROM system.metadata.catalogs"
            )

        assert len(results) == 2
        assert results[0] == {"catalog_name": "analytics"}
        assert results[1] == {"catalog_name": "sales"}

        # Verify requests were made
        assert submit_route.called
        assert poll_route.called

    @pytest.mark.asyncio
    @respx.mock
    async def test_execute_query_with_multiple_polls(self, client):
        """Test query requiring multiple polls."""
        # Mock submission
        respx.post("https://starburst.test/v1/statement").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "query-123",
                    "nextUri": "https://starburst.test/v1/statement/query-123/1",
                },
            )
        )

        # First poll - still running
        respx.get("https://starburst.test/v1/statement/query-123/1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "query-123",
                    "nextUri": "https://starburst.test/v1/statement/query-123/2",
                },
            )
        )

        # Second poll - results ready
        respx.get("https://starburst.test/v1/statement/query-123/2").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "query-123",
                    "columns": [{"name": "schema_name"}],
                    "data": [["public"], ["staging"]],
                },
            )
        )

        async with client:
            results = await client.execute_query(
                "SELECT schema_name FROM system.metadata.schemas"
            )

        assert len(results) == 2
        assert results[0]["schema_name"] == "public"
        assert results[1]["schema_name"] == "staging"

    @pytest.mark.asyncio
    @respx.mock
    async def test_execute_query_error(self, client):
        """Test query execution error."""
        respx.post("https://starburst.test/v1/statement").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "query-123",
                    "error": {"message": "Table not found: invalid_table"},
                },
            )
        )

        async with client:
            with pytest.raises(StarburstQueryError, match="Table not found"):
                await client.execute_query("SELECT * FROM invalid_table")

    @pytest.mark.asyncio
    @respx.mock
    async def test_http_error(self, client):
        """Test HTTP error handling."""
        respx.post("https://starburst.test/v1/statement").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )

        async with client:
            with pytest.raises(StarburstError, match="HTTP 500"):
                await client.execute_query("SELECT * FROM catalogs")

    @pytest.mark.asyncio
    @respx.mock
    async def test_timeout_on_submission(self, client):
        """Test timeout during query submission."""
        respx.post("https://starburst.test/v1/statement").mock(
            side_effect=httpx.TimeoutException("Request timeout")
        )

        async with client:
            with pytest.raises(StarburstTimeoutError, match="Query submission timeout"):
                await client.execute_query("SELECT * FROM catalogs")

    @pytest.mark.asyncio
    @respx.mock
    async def test_timeout_during_polling(self, client):
        """Test timeout during polling."""
        # Submission succeeds
        respx.post("https://starburst.test/v1/statement").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "query-123",
                    "nextUri": "https://starburst.test/v1/statement/query-123/1",
                },
            )
        )

        # Polling times out
        respx.get("https://starburst.test/v1/statement/query-123/1").mock(
            side_effect=httpx.TimeoutException("Polling timeout")
        )

        async with client:
            with pytest.raises(StarburstTimeoutError, match="Query polling timeout"):
                await client.execute_query("SELECT * FROM catalogs")

    @pytest.mark.asyncio
    @respx.mock
    async def test_retry_on_connection_error(self, client):
        """Test automatic retry on connection errors."""
        # First attempt fails, second succeeds
        submit_route = respx.post("https://starburst.test/v1/statement").mock(
            side_effect=[
                httpx.ConnectError("Connection refused"),
                httpx.Response(
                    200,
                    json={
                        "id": "query-123",
                        "columns": [{"name": "catalog_name"}],
                        "data": [["analytics"]],
                    },
                ),
            ]
        )

        async with client:
            results = await client.execute_query("SELECT * FROM catalogs")

        assert len(results) == 1
        assert submit_route.call_count == 2  # Retried once

    @pytest.mark.asyncio
    async def test_client_not_initialized(self, client):
        """Test error when client not initialized."""
        # Don't use context manager
        with pytest.raises(StarburstError, match="Client not initialized"):
            await client.execute_query("SELECT * FROM catalogs")

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_catalogs(self, client):
        """Test fetch_catalogs() helper."""
        respx.post("https://starburst.test/v1/statement").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "query-123",
                    "columns": [{"name": "catalog_name"}],
                    "data": [["analytics"], ["sales"], ["marketing"]],
                },
            )
        )

        async with client:
            catalogs = await client.fetch_catalogs()

        assert len(catalogs) == 3
        assert catalogs[0]["catalog_name"] == "analytics"
        assert catalogs[1]["catalog_name"] == "sales"
        assert catalogs[2]["catalog_name"] == "marketing"

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_schemas(self, client):
        """Test fetch_schemas() helper."""
        respx.post("https://starburst.test/v1/statement").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "query-123",
                    "columns": [{"name": "schema_name"}],
                    "data": [["public"], ["staging"]],
                },
            )
        )

        async with client:
            schemas = await client.fetch_schemas("analytics")

        assert len(schemas) == 2
        assert schemas[0]["schema_name"] == "public"
        assert schemas[1]["schema_name"] == "staging"

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_tables(self, client):
        """Test fetch_tables() helper."""
        respx.post("https://starburst.test/v1/statement").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "query-123",
                    "columns": [{"name": "table_name"}, {"name": "table_type"}],
                    "data": [
                        ["users", "BASE TABLE"],
                        ["orders", "BASE TABLE"],
                        ["user_orders_view", "VIEW"],
                    ],
                },
            )
        )

        async with client:
            tables = await client.fetch_tables("analytics", "public")

        assert len(tables) == 3
        assert tables[0] == {"table_name": "users", "table_type": "BASE TABLE"}
        assert tables[2]["table_type"] == "VIEW"

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_columns(self, client):
        """Test fetch_columns() helper."""
        respx.post("https://starburst.test/v1/statement").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "query-123",
                    "columns": [
                        {"name": "column_name"},
                        {"name": "data_type"},
                        {"name": "is_nullable"},
                        {"name": "column_default"},
                        {"name": "ordinal_position"},
                    ],
                    "data": [
                        ["id", "bigint", "NO", None, 1],
                        ["email", "varchar", "YES", None, 2],
                        ["created_at", "timestamp", "NO", "now()", 3],
                    ],
                },
            )
        )

        async with client:
            columns = await client.fetch_columns("analytics", "public", "users")

        assert len(columns) == 3
        assert columns[0]["column_name"] == "id"
        assert columns[0]["is_nullable"] == "NO"
        assert columns[2]["column_default"] == "now()"
        assert columns[2]["ordinal_position"] == 3

    @pytest.mark.asyncio
    @respx.mock
    async def test_max_polls_exceeded(self, client):
        """Test error when max polls exceeded."""
        respx.post("https://starburst.test/v1/statement").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "query-123",
                    "nextUri": "https://starburst.test/v1/statement/query-123/1",
                },
            )
        )

        # Always return nextUri (never complete) - use regex pattern
        respx.get(url__regex=r"https://starburst\.test/v1/statement/query-123/.*").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "query-123",
                    "nextUri": "https://starburst.test/v1/statement/query-123/999",
                },
            )
        )

        async with client:
            with pytest.raises(StarburstTimeoutError, match="exceeded 100 polls"):
                await client.execute_query("SELECT * FROM slow_table")
