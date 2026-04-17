"""Tests for HTTP retry logic and error handling.

These tests verify the retry behavior with exponential backoff
for transient failures like connection errors and timeouts.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from graph_olap.exceptions import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ServerError,
    ServiceUnavailableError,
    ValidationError,
)
from graph_olap.http import HTTPClient

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def mock_httpx_client():
    """Create a mock httpx.Client."""
    with patch("graph_olap.http.httpx.Client") as mock:
        yield mock.return_value


# =============================================================================
# HTTPClient Error Response Handling
# =============================================================================


class TestHTTPClientErrorResponses:
    """Tests for HTTP error response handling."""

    def test_401_raises_authentication_error(self, mock_httpx_client: MagicMock):
        """401 response raises AuthenticationError."""
        response = MagicMock()
        response.status_code = 401
        response.json.return_value = {
            "error": {"code": "UNAUTHORIZED", "message": "Invalid API key"}
        }
        mock_httpx_client.get.return_value = response

        client = HTTPClient("https://api.example.com", username="test-user@example.com")

        with pytest.raises(AuthenticationError, match="Invalid API key"):
            client.get("/test")

    def test_403_raises_permission_denied_error(self, mock_httpx_client: MagicMock):
        """403 response raises PermissionDeniedError."""
        response = MagicMock()
        response.status_code = 403
        response.json.return_value = {
            "error": {"code": "FORBIDDEN", "message": "Access denied", "details": {}}
        }
        mock_httpx_client.get.return_value = response

        client = HTTPClient("https://api.example.com", username="test-user@example.com")

        with pytest.raises(PermissionDeniedError, match="Access denied"):
            client.get("/test")

    def test_404_raises_not_found_error(self, mock_httpx_client: MagicMock):
        """404 response raises NotFoundError."""
        response = MagicMock()
        response.status_code = 404
        response.json.return_value = {
            "error": {"code": "NOT_FOUND", "message": "Resource not found", "details": {}}
        }
        mock_httpx_client.get.return_value = response

        client = HTTPClient("https://api.example.com", username="test-user@example.com")

        with pytest.raises(NotFoundError, match="Resource not found"):
            client.get("/mappings/999")

    def test_409_raises_conflict_error(self, mock_httpx_client: MagicMock):
        """409 response raises ConflictError."""
        response = MagicMock()
        response.status_code = 409
        response.json.return_value = {
            "error": {
                "code": "CONFLICT",
                "message": "Name already exists",
                "details": {"field": "name"},
            }
        }
        mock_httpx_client.post.return_value = response

        client = HTTPClient("https://api.example.com", username="test-user@example.com")

        with pytest.raises(ConflictError, match="Name already exists"):
            client.post("/mappings", json={"name": "duplicate"})

    def test_422_raises_validation_error(self, mock_httpx_client: MagicMock):
        """422 response raises ValidationError."""
        response = MagicMock()
        response.status_code = 422
        response.json.return_value = {
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Invalid input",
                "details": {"field": "name", "reason": "too short"},
            }
        }
        mock_httpx_client.post.return_value = response

        client = HTTPClient("https://api.example.com", username="test-user@example.com")

        with pytest.raises(ValidationError, match="Invalid input"):
            client.post("/mappings", json={"name": "x"})

    def test_500_raises_server_error(self, mock_httpx_client: MagicMock):
        """500 response raises ServerError."""
        response = MagicMock()
        response.status_code = 500
        response.json.return_value = {
            "error": {"code": "INTERNAL_ERROR", "message": "Database error"}
        }
        mock_httpx_client.get.return_value = response

        client = HTTPClient("https://api.example.com", username="test-user@example.com")

        with pytest.raises(ServerError, match="Database error"):
            client.get("/test")

    def test_503_raises_service_unavailable_error(self, mock_httpx_client: MagicMock):
        """503 response raises ServiceUnavailableError."""
        response = MagicMock()
        response.status_code = 503
        response.json.return_value = {
            "error": {"code": "SERVICE_UNAVAILABLE", "message": "Maintenance in progress"}
        }
        mock_httpx_client.get.return_value = response

        client = HTTPClient("https://api.example.com", username="test-user@example.com")

        with pytest.raises(ServiceUnavailableError, match="Maintenance"):
            client.get("/test")

    def test_malformed_error_response_uses_text(self, mock_httpx_client: MagicMock):
        """Non-JSON error response falls back to text."""
        response = MagicMock()
        response.status_code = 500
        response.json.side_effect = Exception("Not JSON")
        response.text = "Internal Server Error"
        mock_httpx_client.get.return_value = response

        client = HTTPClient("https://api.example.com", username="test-user@example.com")

        with pytest.raises(ServerError, match="Internal Server Error"):
            client.get("/test")

    def test_empty_error_response(self, mock_httpx_client: MagicMock):
        """Empty error response creates message from status code."""
        response = MagicMock()
        response.status_code = 500
        response.json.side_effect = Exception("Empty")
        response.text = ""
        mock_httpx_client.get.return_value = response

        client = HTTPClient("https://api.example.com", username="test-user@example.com")

        with pytest.raises(ServerError, match="HTTP 500"):
            client.get("/test")


# =============================================================================
# HTTPClient Retry Behavior
# =============================================================================


class TestHTTPClientRetryBehavior:
    """Tests for retry behavior on transient failures."""

    def test_retries_on_connect_error(self, mock_httpx_client: MagicMock):
        """Retries on connection errors up to max_retries."""
        # First 2 calls fail, third succeeds
        success_response = MagicMock()
        success_response.status_code = 200
        success_response.content = b'{"data": "ok"}'
        success_response.json.return_value = {"data": "ok"}

        mock_httpx_client.get.side_effect = [
            httpx.ConnectError("Connection refused"),
            httpx.ConnectError("Connection refused"),
            success_response,
        ]

        client = HTTPClient("https://api.example.com", username="test-user@example.com", max_retries=3)

        with patch("tenacity.nap.sleep"):
            result = client.get("/test")

        assert result == {"data": "ok"}
        assert mock_httpx_client.get.call_count == 3

    def test_retries_on_read_timeout(self, mock_httpx_client: MagicMock):
        """Retries on read timeouts."""
        success_response = MagicMock()
        success_response.status_code = 200
        success_response.content = b'{"data": "ok"}'
        success_response.json.return_value = {"data": "ok"}

        mock_httpx_client.get.side_effect = [
            httpx.ReadTimeout("Read timed out"),
            success_response,
        ]

        client = HTTPClient("https://api.example.com", username="test-user@example.com", max_retries=3)

        with patch("tenacity.nap.sleep"):
            result = client.get("/test")

        assert result == {"data": "ok"}
        assert mock_httpx_client.get.call_count == 2

    def test_raises_after_max_retries_exceeded(self, mock_httpx_client: MagicMock):
        """Raises original exception after max retries exhausted."""
        mock_httpx_client.get.side_effect = httpx.ConnectError("Connection refused")

        client = HTTPClient("https://api.example.com", username="test-user@example.com", max_retries=3)

        with patch("tenacity.nap.sleep"):
            with pytest.raises(httpx.ConnectError, match="Connection refused"):
                client.get("/test")

        assert mock_httpx_client.get.call_count == 3

    def test_no_retry_on_non_transient_errors(self, mock_httpx_client: MagicMock):
        """Non-transient errors are not retried."""
        response = MagicMock()
        response.status_code = 400
        response.json.return_value = {"error": {"message": "Bad request"}}
        mock_httpx_client.post.return_value = response

        client = HTTPClient("https://api.example.com", username="test-user@example.com", max_retries=3)

        from graph_olap.exceptions import GraphOLAPError

        with pytest.raises(GraphOLAPError):
            client.post("/test", json={})

        # Should only try once - no retries for client errors
        assert mock_httpx_client.post.call_count == 1


# =============================================================================
# HTTPClient Success Response Handling
# =============================================================================


class TestHTTPClientSuccessResponses:
    """Tests for successful response handling."""

    def test_200_returns_json(self, mock_httpx_client: MagicMock):
        """200 response returns parsed JSON."""
        response = MagicMock()
        response.status_code = 200
        response.content = b'{"data": [1, 2, 3]}'
        response.json.return_value = {"data": [1, 2, 3]}
        mock_httpx_client.get.return_value = response

        client = HTTPClient("https://api.example.com", username="test-user@example.com")
        result = client.get("/test")

        assert result == {"data": [1, 2, 3]}

    def test_201_returns_json(self, mock_httpx_client: MagicMock):
        """201 response returns parsed JSON."""
        response = MagicMock()
        response.status_code = 201
        response.content = b'{"data": {"id": 1}}'
        response.json.return_value = {"data": {"id": 1}}
        mock_httpx_client.post.return_value = response

        client = HTTPClient("https://api.example.com", username="test-user@example.com")
        result = client.post("/test", json={"name": "test"})

        assert result == {"data": {"id": 1}}

    def test_202_returns_json(self, mock_httpx_client: MagicMock):
        """202 (accepted) response returns parsed JSON."""
        response = MagicMock()
        response.status_code = 202
        response.content = b'{"data": {"status": "pending"}}'
        response.json.return_value = {"data": {"status": "pending"}}
        mock_httpx_client.post.return_value = response

        client = HTTPClient("https://api.example.com", username="test-user@example.com")
        result = client.post("/test", json={})

        assert result == {"data": {"status": "pending"}}

    def test_204_returns_empty_dict(self, mock_httpx_client: MagicMock):
        """204 (no content) returns empty dict."""
        response = MagicMock()
        response.status_code = 204
        response.content = b""
        mock_httpx_client.request.return_value = response

        client = HTTPClient("https://api.example.com", username="test-user@example.com")
        result = client.delete("/test/1")

        assert result == {}

    def test_200_with_empty_content_returns_empty_dict(self, mock_httpx_client: MagicMock):
        """200 with empty body returns empty dict."""
        response = MagicMock()
        response.status_code = 200
        response.content = b""
        mock_httpx_client.request.return_value = response

        client = HTTPClient("https://api.example.com", username="test-user@example.com")
        result = client.delete("/test/1")

        assert result == {}


# =============================================================================
# HTTPClient Context Manager
# =============================================================================


class TestHTTPClientContextManager:
    """Tests for context manager support."""

    def test_context_manager_closes_client(self, mock_httpx_client: MagicMock):
        """Context manager closes the underlying client."""
        with HTTPClient("https://api.example.com", username="test-user@example.com") as client:
            assert client is not None

        mock_httpx_client.close.assert_called_once()

    def test_context_manager_closes_on_exception(self, mock_httpx_client: MagicMock):
        """Context manager closes client even on exception."""
        response = MagicMock()
        response.status_code = 500
        response.json.return_value = {"error": {"message": "Server error"}}
        mock_httpx_client.get.return_value = response

        with pytest.raises(ServerError):
            with HTTPClient("https://api.example.com", username="test-user@example.com") as client:
                client.get("/test")

        mock_httpx_client.close.assert_called_once()


# =============================================================================
# HTTPClient Headers Configuration
# =============================================================================


class TestHTTPClientHeaders:
    """Tests for header configuration."""

    def test_sets_username_header(self):
        """Sets X-Username header with username."""
        with patch("graph_olap.http.httpx.Client") as mock:
            HTTPClient("https://api.example.com", username="test-user@example.com")

            call_kwargs = mock.call_args[1]
            assert "X-Username" in call_kwargs["headers"]
            assert call_kwargs["headers"]["X-Username"] == "test-user@example.com"

    def test_sets_content_type_json(self):
        """Sets Content-Type to application/json."""
        with patch("graph_olap.http.httpx.Client") as mock:
            HTTPClient("https://api.example.com", username="test-user@example.com")

            call_kwargs = mock.call_args[1]
            assert call_kwargs["headers"]["Content-Type"] == "application/json"

    def test_sets_accept_json(self):
        """Sets Accept to application/json."""
        with patch("graph_olap.http.httpx.Client") as mock:
            HTTPClient("https://api.example.com", username="test-user@example.com")

            call_kwargs = mock.call_args[1]
            assert call_kwargs["headers"]["Accept"] == "application/json"

    def test_sets_user_agent(self):
        """Sets User-Agent header."""
        with patch("graph_olap.http.httpx.Client") as mock:
            HTTPClient("https://api.example.com", username="test-user@example.com")

            call_kwargs = mock.call_args[1]
            assert "User-Agent" in call_kwargs["headers"]
            assert "graph-olap-sdk" in call_kwargs["headers"]["User-Agent"]


# =============================================================================
# HTTPClient URL Handling
# =============================================================================


class TestHTTPClientURLHandling:
    """Tests for URL handling."""

    def test_strips_trailing_slash_from_base_url(self):
        """Strips trailing slash from base URL."""
        with patch("graph_olap.http.httpx.Client") as mock:
            HTTPClient("https://api.example.com/", username="test-user@example.com")

            call_kwargs = mock.call_args[1]
            assert call_kwargs["base_url"] == "https://api.example.com"

    def test_preserves_base_url_without_trailing_slash(self):
        """Preserves base URL without trailing slash."""
        with patch("graph_olap.http.httpx.Client") as mock:
            HTTPClient("https://api.example.com", username="test-user@example.com")

            call_kwargs = mock.call_args[1]
            assert call_kwargs["base_url"] == "https://api.example.com"
