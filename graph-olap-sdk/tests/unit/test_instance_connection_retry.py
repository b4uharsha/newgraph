"""Tests for InstanceConnection retry logic.

These tests verify that InstanceConnection retries on transient network
failures when querying running graph instances.
"""

from __future__ import annotations

from unittest.mock import Mock, patch

import httpx
import pytest

from graph_olap.instance.connection import InstanceConnection


class TestInstanceConnectionRetryBehavior:
    """Tests for retry behavior on InstanceConnection._request()."""

    def test_retries_on_connect_error_and_succeeds(self):
        """InstanceConnection retries on ConnectError and succeeds on 3rd attempt."""
        conn = InstanceConnection(
            instance_url="http://localhost:9999",
            username="test-user@example.com",
            instance_id=123,
        )

        # Mock responses: fail twice, then succeed
        success_response = Mock()
        success_response.status_code = 200
        success_response.json.return_value = {
            "columns": ["count"],
            "column_types": ["INTEGER"],
            "rows": [[42]],
            "row_count": 1,
            "execution_time_ms": 5,
        }

        with patch.object(conn._client, "request") as mock_request:
            mock_request.side_effect = [
                httpx.ConnectError("Connection refused"),
                httpx.ConnectError("Connection refused"),
                success_response,
            ]

            # Mock tenacity sleep to speed up test
            with patch("tenacity.nap.sleep"):
                result = conn.query("MATCH (n) RETURN count(n)")

            # Should have succeeded on 3rd attempt
            assert mock_request.call_count == 3
            assert result.row_count == 1

    def test_retries_on_read_timeout_and_succeeds(self):
        """InstanceConnection retries on ReadTimeout and succeeds."""
        conn = InstanceConnection(
            instance_url="http://localhost:9999",
            username="test-user@example.com",
            instance_id=123,
        )

        success_response = Mock()
        success_response.status_code = 200
        success_response.json.return_value = {
            "columns": ["result"],
            "column_types": ["STRING"],
            "rows": [["ok"]],
            "row_count": 1,
            "execution_time_ms": 5,
        }

        with patch.object(conn._client, "request") as mock_request:
            mock_request.side_effect = [
                httpx.ReadTimeout("Read timed out"),
                success_response,
            ]

            with patch("tenacity.nap.sleep"):
                result = conn.query("MATCH (n) RETURN 'ok' as result")

            # Should succeed on 2nd attempt
            assert mock_request.call_count == 2
            assert result.row_count == 1

    def test_fails_after_max_retries_exceeded(self):
        """InstanceConnection fails after 3 retry attempts."""
        conn = InstanceConnection(
            instance_url="http://localhost:9999",
            username="test-user@example.com",
            instance_id=123,
        )

        with patch.object(conn._client, "request") as mock_request:
            # All attempts fail
            mock_request.side_effect = httpx.ConnectError("Connection refused")

            with patch("tenacity.nap.sleep"):
                with pytest.raises(httpx.ConnectError, match="Connection refused"):
                    conn.query("MATCH (n) RETURN n")

            # Should have tried exactly 3 times
            assert mock_request.call_count == 3

    def test_no_retry_on_http_error_responses(self):
        """InstanceConnection does NOT retry on HTTP error responses (404, 500, etc)."""
        conn = InstanceConnection(
            instance_url="http://localhost:9999",
            username="test-user@example.com",
            instance_id=123,
        )

        # 404 error response - should NOT retry
        error_response = Mock()
        error_response.status_code = 404
        error_response.json.return_value = {
            "error": {"code": "NOT_FOUND", "message": "Instance not found"}
        }

        with patch.object(conn._client, "request") as mock_request:
            mock_request.return_value = error_response

            from graph_olap.exceptions import NotFoundError

            with pytest.raises(NotFoundError):
                conn.query("MATCH (n) RETURN n")

            # Should only try once - no retries for application errors
            assert mock_request.call_count == 1

    def test_retries_on_connect_error_for_schema_request(self):
        """InstanceConnection retries on ConnectError for get_schema()."""
        conn = InstanceConnection(
            instance_url="http://localhost:9999",
            username="test-user@example.com",
            instance_id=123,
        )

        success_response = Mock()
        success_response.status_code = 200
        success_response.json.return_value = {
            "node_labels": {"Person": ["name", "age"]},
            "relationship_types": {"KNOWS": ["since"]},
        }

        with patch.object(conn._client, "request") as mock_request:
            mock_request.side_effect = [
                httpx.ConnectError("Connection refused"),
                success_response,
            ]

            with patch("tenacity.nap.sleep"):
                schema = conn.get_schema()

            # Should succeed on 2nd attempt
            assert mock_request.call_count == 2
            assert "Person" in schema.node_labels

    def test_retries_on_connect_error_for_status_request(self):
        """InstanceConnection retries on ConnectError for status()."""
        conn = InstanceConnection(
            instance_url="http://localhost:9999",
            username="test-user@example.com",
            instance_id=123,
        )

        success_response = Mock()
        success_response.status_code = 200
        success_response.json.return_value = {
            "memory_usage": {"used_mb": 100},
            "uptime": "1h",
        }

        with patch.object(conn._client, "request") as mock_request:
            mock_request.side_effect = [
                httpx.ReadTimeout("Timeout"),
                success_response,
            ]

            with patch("tenacity.nap.sleep"):
                status = conn.status()

            # Should succeed on 2nd attempt
            assert mock_request.call_count == 2
            assert status["memory_usage"]["used_mb"] == 100

