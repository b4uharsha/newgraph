"""Unit tests for HTTP client."""

from __future__ import annotations

import httpx
import pytest
import respx

from graph_olap.exceptions import (
    AuthenticationError,
    NotFoundError,
    ServerError,
    ValidationError,
)
from graph_olap.http import AsyncHTTPClient, HTTPClient


class TestHTTPClientInit:
    """Tests for HTTPClient initialization."""

    def test_init_with_username(self):
        """Test client initialization with username."""
        client = HTTPClient(
            base_url="https://api.example.com",
            username="test-user@example.com",
            timeout=60.0,
            max_retries=5,
        )

        assert client.base_url == "https://api.example.com"
        assert client.username == "test-user@example.com"
        assert client.timeout == 60.0
        assert client.max_retries == 5

        client.close()

    def test_strips_trailing_slash(self):
        """Test trailing slash is stripped from base URL."""
        client = HTTPClient(
            base_url="https://api.example.com/",
            username="test@example.com",
        )

        assert client.base_url == "https://api.example.com"

        client.close()

    def test_context_manager(self):
        """Test client works as context manager."""
        with HTTPClient(
            base_url="https://api.example.com",
            username="test@example.com",
        ) as client:
            assert isinstance(client, HTTPClient)

    def test_set_username(self):
        """Test set_username updates header for subsequent requests."""
        client = HTTPClient(
            base_url="https://api.example.com",
            username="alice@example.com",
        )

        assert client.username == "alice@example.com"
        assert client._client.headers["X-Username"] == "alice@example.com"

        client.set_username("bob@example.com")

        assert client.username == "bob@example.com"
        assert client._client.headers["X-Username"] == "bob@example.com"

        client.close()


class TestHTTPClientRequests:
    """Tests for HTTPClient request methods."""

    @pytest.fixture
    def client(self) -> HTTPClient:
        """Create HTTP client for tests."""
        client = HTTPClient(
            base_url="https://api.example.com",
            username="test-user@example.com",
        )
        yield client
        client.close()

    @respx.mock
    def test_get_request_success(self, client: HTTPClient):
        """Test successful GET request."""
        respx.get("https://api.example.com/api/mappings").mock(
            return_value=httpx.Response(
                200,
                json={"data": [{"id": 1, "name": "Test"}]},
            )
        )

        result = client.get("/api/mappings")

        assert result == {"data": [{"id": 1, "name": "Test"}]}

    @respx.mock
    def test_get_request_with_params(self, client: HTTPClient):
        """Test GET request with query parameters."""
        route = respx.get("https://api.example.com/api/mappings").mock(
            return_value=httpx.Response(200, json={"data": []})
        )

        client.get("/api/mappings", params={"limit": 10, "offset": 0})

        assert route.called
        request = route.calls[0].request
        assert "limit=10" in str(request.url)
        assert "offset=0" in str(request.url)

    @respx.mock
    def test_post_request_success(self, client: HTTPClient):
        """Test successful POST request."""
        respx.post("https://api.example.com/api/mappings").mock(
            return_value=httpx.Response(
                201,
                json={"id": 1, "name": "New Mapping"},
            )
        )

        result = client.post("/api/mappings", json={"name": "New Mapping"})

        assert result == {"id": 1, "name": "New Mapping"}

    @respx.mock
    def test_put_request_success(self, client: HTTPClient):
        """Test successful PUT request."""
        respx.put("https://api.example.com/api/mappings/1").mock(
            return_value=httpx.Response(
                200,
                json={"id": 1, "name": "Updated Mapping"},
            )
        )

        result = client.put("/api/mappings/1", json={"name": "Updated Mapping"})

        assert result == {"id": 1, "name": "Updated Mapping"}

    @respx.mock
    def test_delete_request_success(self, client: HTTPClient):
        """Test successful DELETE request."""
        respx.delete("https://api.example.com/api/mappings/1").mock(
            return_value=httpx.Response(204)
        )

        result = client.delete("/api/mappings/1")

        assert result == {}

    @respx.mock
    def test_202_accepted_response(self, client: HTTPClient):
        """Test 202 Accepted response."""
        respx.post("https://api.example.com/api/snapshots").mock(
            return_value=httpx.Response(
                202,
                json={"id": 1, "status": "creating"},
            )
        )

        result = client.post("/api/snapshots", json={"name": "New Snapshot"})

        assert result == {"id": 1, "status": "creating"}


class TestHTTPClientTextResponses:
    """Tests for HTTPClient text response handling."""

    @pytest.fixture
    def client(self) -> HTTPClient:
        """Create HTTP client for tests."""
        client = HTTPClient(
            base_url="https://api.example.com",
            username="test-user@example.com",
        )
        yield client
        client.close()

    @respx.mock
    def test_get_text_request_success(self, client: HTTPClient):
        """Test successful GET request for text response."""
        respx.get("https://api.example.com/metrics").mock(
            return_value=httpx.Response(
                200,
                content=b"# HELP metric_name Description\n# TYPE metric_name counter\nmetric_name 42.0\n",
                headers={"Content-Type": "text/plain; charset=utf-8"},
            )
        )

        result = client.get_text("/metrics")

        assert isinstance(result, str)
        assert "# HELP metric_name" in result
        assert "metric_name 42.0" in result

    @respx.mock
    def test_get_text_request_with_params(self, client: HTTPClient):
        """Test GET text request with query parameters."""
        route = respx.get("https://api.example.com/metrics").mock(
            return_value=httpx.Response(200, content=b"metric_value 1.0")
        )

        client.get_text("/metrics", params={"job": "test"})

        assert route.called
        request = route.calls[0].request
        assert "job=test" in str(request.url)

    @respx.mock
    def test_get_text_error_response(self, client: HTTPClient):
        """Test get_text handles error responses correctly."""
        respx.get("https://api.example.com/metrics").mock(
            return_value=httpx.Response(
                403,
                json={
                    "error": {
                        "code": "FORBIDDEN",
                        "message": "Insufficient permissions",
                    }
                },
            )
        )

        from graph_olap.exceptions import ForbiddenError

        with pytest.raises(ForbiddenError):
            client.get_text("/metrics")

    @respx.mock
    def test_get_text_non_json_error(self, client: HTTPClient):
        """Test get_text handles non-JSON error responses."""
        respx.get("https://api.example.com/metrics").mock(
            return_value=httpx.Response(
                500,
                content=b"Internal Server Error",
            )
        )

        with pytest.raises(ServerError) as exc_info:
            client.get_text("/metrics")

        assert "Internal Server Error" in str(exc_info.value)


class TestHTTPClientErrorHandling:
    """Tests for HTTPClient error handling."""

    @pytest.fixture
    def client(self) -> HTTPClient:
        """Create HTTP client for tests."""
        client = HTTPClient(
            base_url="https://api.example.com",
            username="test-user@example.com",
        )
        yield client
        client.close()

    @respx.mock
    def test_401_raises_authentication_error(self, client: HTTPClient):
        """Test 401 response raises AuthenticationError."""
        respx.get("https://api.example.com/api/mappings").mock(
            return_value=httpx.Response(
                401,
                json={
                    "error": {
                        "code": "UNAUTHORIZED",
                        "message": "Invalid API key",
                    }
                },
            )
        )

        with pytest.raises(AuthenticationError):
            client.get("/api/mappings")

    @respx.mock
    def test_404_raises_not_found_error(self, client: HTTPClient):
        """Test 404 response raises NotFoundError."""
        respx.get("https://api.example.com/api/mappings/999").mock(
            return_value=httpx.Response(
                404,
                json={
                    "error": {
                        "code": "NOT_FOUND",
                        "message": "Mapping not found",
                    }
                },
            )
        )

        with pytest.raises(NotFoundError):
            client.get("/api/mappings/999")

    @respx.mock
    def test_422_raises_validation_error(self, client: HTTPClient):
        """Test 422 response raises ValidationError."""
        respx.post("https://api.example.com/api/mappings").mock(
            return_value=httpx.Response(
                422,
                json={
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "Invalid request",
                        "details": {"name": "required"},
                    }
                },
            )
        )

        with pytest.raises(ValidationError):
            client.post("/api/mappings", json={})

    @respx.mock
    def test_500_raises_server_error(self, client: HTTPClient):
        """Test 500 response raises ServerError."""
        respx.get("https://api.example.com/api/mappings").mock(
            return_value=httpx.Response(
                500,
                json={
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": "Internal server error",
                    }
                },
            )
        )

        with pytest.raises(ServerError):
            client.get("/api/mappings")

    @respx.mock
    def test_non_json_error_response(self, client: HTTPClient):
        """Test handling of non-JSON error response."""
        respx.get("https://api.example.com/api/mappings").mock(
            return_value=httpx.Response(
                500,
                content=b"Internal Server Error",
            )
        )

        with pytest.raises(ServerError) as exc_info:
            client.get("/api/mappings")

        assert "Internal Server Error" in str(exc_info.value)


class TestHTTPClientHeaders:
    """Tests for HTTPClient request headers."""

    @respx.mock
    def test_username_header_set(self):
        """Test X-Username header is set when username provided."""
        route = respx.get("https://api.example.com/api/test").mock(
            return_value=httpx.Response(200, json={})
        )

        with HTTPClient(
            base_url="https://api.example.com",
            username="test-user@example.com",
        ) as client:
            client.get("/api/test")

        request = route.calls[0].request
        assert request.headers["X-Username"] == "test-user@example.com"

    @respx.mock
    def test_content_type_header_set(self):
        """Test Content-Type header is set."""
        route = respx.get("https://api.example.com/api/test").mock(
            return_value=httpx.Response(200, json={})
        )

        with HTTPClient(
            base_url="https://api.example.com",
            username="test-user@example.com",
        ) as client:
            client.get("/api/test")

        request = route.calls[0].request
        assert request.headers["Content-Type"] == "application/json"

    @respx.mock
    def test_user_agent_header_set(self):
        """Test User-Agent header is set."""
        route = respx.get("https://api.example.com/api/test").mock(
            return_value=httpx.Response(200, json={})
        )

        with HTTPClient(
            base_url="https://api.example.com",
            username="test-user@example.com",
        ) as client:
            client.get("/api/test")

        request = route.calls[0].request
        assert "graph-olap-sdk" in request.headers["User-Agent"]


class TestAsyncHTTPClient:
    """Tests for AsyncHTTPClient."""

    @pytest.fixture
    def async_client(self) -> AsyncHTTPClient:
        """Create async HTTP client for tests."""
        return AsyncHTTPClient(
            base_url="https://api.example.com",
            username="test-user@example.com",
        )

    def test_init_with_username(self, async_client: AsyncHTTPClient):
        """Test async client initialization."""
        assert async_client.base_url == "https://api.example.com"
        assert async_client.username == "test-user@example.com"

    @pytest.mark.asyncio
    @respx.mock
    async def test_async_get_request(self, async_client: AsyncHTTPClient):
        """Test async GET request."""
        respx.get("https://api.example.com/api/mappings").mock(
            return_value=httpx.Response(
                200,
                json={"data": [{"id": 1}]},
            )
        )

        result = await async_client.get("/api/mappings")

        assert result == {"data": [{"id": 1}]}
        await async_client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_async_post_request(self, async_client: AsyncHTTPClient):
        """Test async POST request."""
        respx.post("https://api.example.com/api/mappings").mock(
            return_value=httpx.Response(
                201,
                json={"id": 1, "name": "Test"},
            )
        )

        result = await async_client.post("/api/mappings", json={"name": "Test"})

        assert result == {"id": 1, "name": "Test"}
        await async_client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_async_context_manager(self):
        """Test async client as context manager."""
        respx.get("https://api.example.com/api/test").mock(
            return_value=httpx.Response(200, json={})
        )

        async with AsyncHTTPClient(base_url="https://api.example.com", username="test@example.com") as client:
            result = await client.get("/api/test")
            assert result == {}

    @pytest.mark.asyncio
    @respx.mock
    async def test_async_error_handling(self, async_client: AsyncHTTPClient):
        """Test async error handling."""
        respx.get("https://api.example.com/api/mappings/999").mock(
            return_value=httpx.Response(
                404,
                json={
                    "error": {
                        "code": "NOT_FOUND",
                        "message": "Not found",
                    }
                },
            )
        )

        with pytest.raises(NotFoundError):
            await async_client.get("/api/mappings/999")

        await async_client.close()
