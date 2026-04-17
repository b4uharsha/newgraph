"""Integration tests for InstanceConnection with mocked API."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from graph_olap.instance.connection import InstanceConnection
from graph_olap.models.common import QueryResult, Schema


class TestInstanceConnectionQuery:
    """Integration tests for InstanceConnection query methods."""

    @pytest.fixture
    def connection(self) -> InstanceConnection:
        """Create instance connection for tests."""
        return InstanceConnection(
            instance_url="https://instance-1.example.com",
            username="test-user@example.com",
        )

    @respx.mock
    def test_query_returns_query_result(self, connection: InstanceConnection):
        """Test query returns QueryResult object."""
        respx.post("https://instance-1.example.com/query").mock(
            return_value=httpx.Response(
                200,
                json={
                    "columns": ["name", "age"],
                    "column_types": ["STRING", "INT64"],
                    "rows": [
                        ["Alice", 30],
                        ["Bob", 25],
                    ],
                    "row_count": 2,
                    "execution_time_ms": 15,
                },
            )
        )

        result = connection.query("MATCH (n:Customer) RETURN n.name, n.age")

        assert isinstance(result, QueryResult)
        assert result.columns == ["name", "age"]
        assert result.row_count == 2
        assert result.execution_time_ms == 15
        connection.close()

    @respx.mock
    def test_query_with_parameters(self, connection: InstanceConnection):
        """Test query with parameters."""
        route = respx.post("https://instance-1.example.com/query").mock(
            return_value=httpx.Response(
                200,
                json={
                    "columns": ["name"],
                    "column_types": ["STRING"],
                    "rows": [["Alice"]],
                    "row_count": 1,
                    "execution_time_ms": 10,
                },
            )
        )

        result = connection.query(
            "MATCH (n:Customer {name: $name}) RETURN n.name",
            parameters={"name": "Alice"},
        )

        request = route.calls[0].request
        body_data = json.loads(request.content)
        assert body_data["parameters"] == {"name": "Alice"}
        assert result.row_count == 1
        connection.close()

    @respx.mock
    def test_query_scalar_single_value(self, connection: InstanceConnection):
        """Test query_scalar returns single value."""
        respx.post("https://instance-1.example.com/query").mock(
            return_value=httpx.Response(
                200,
                json={
                    "columns": ["count"],
                    "column_types": ["INT64"],
                    "rows": [[42]],
                    "row_count": 1,
                    "execution_time_ms": 5,
                },
            )
        )

        result = connection.query_scalar("MATCH (n) RETURN count(n)")

        assert result == 42
        connection.close()

    @respx.mock
    def test_query_iteration(self, connection: InstanceConnection):
        """Test iterating over query results as dicts."""
        respx.post("https://instance-1.example.com/query").mock(
            return_value=httpx.Response(
                200,
                json={
                    "columns": ["name", "age"],
                    "column_types": ["STRING", "INT64"],
                    "rows": [
                        ["Alice", 30],
                        ["Bob", 25],
                    ],
                    "row_count": 2,
                    "execution_time_ms": 15,
                },
            )
        )

        result = connection.query("MATCH (n) RETURN n.name, n.age")
        rows = list(result)

        assert len(rows) == 2
        assert rows[0] == {"name": "Alice", "age": 30}
        assert rows[1] == {"name": "Bob", "age": 25}
        connection.close()


class TestInstanceConnectionSchema:
    """Integration tests for InstanceConnection schema methods."""

    @pytest.fixture
    def connection(self) -> InstanceConnection:
        """Create instance connection for tests."""
        return InstanceConnection(
            instance_url="https://instance-1.example.com",
            username="test-user@example.com",
        )

    @respx.mock
    def test_get_schema(self, connection: InstanceConnection):
        """Test get_schema returns schema info."""
        respx.get("https://instance-1.example.com/schema").mock(
            return_value=httpx.Response(
                200,
                json={
                    "node_labels": {
                        "Customer": ["id", "name", "age"],
                        "Product": ["id", "name", "price"],
                    },
                    "relationship_types": {
                        "PURCHASED": ["amount", "date"],
                    },
                    "node_count": 15000,
                    "relationship_count": 50000,
                },
            )
        )

        schema = connection.get_schema()

        assert isinstance(schema, Schema)
        assert "Customer" in schema.node_labels
        assert "Product" in schema.node_labels
        assert "PURCHASED" in schema.relationship_types
        assert schema.node_count == 15000
        assert schema.relationship_count == 50000
        connection.close()


class TestInstanceConnectionLock:
    """Integration tests for InstanceConnection lock methods."""

    @pytest.fixture
    def connection(self) -> InstanceConnection:
        """Create instance connection for tests."""
        return InstanceConnection(
            instance_url="https://instance-1.example.com",
            username="test-user@example.com",
        )

    @respx.mock
    def test_get_lock_status_unlocked(self, connection: InstanceConnection):
        """Test getting lock status when unlocked."""
        respx.get("https://instance-1.example.com/lock").mock(
            return_value=httpx.Response(
                200,
                json={"lock": {"locked": False}},
            )
        )

        status = connection.get_lock()

        assert status.locked is False
        assert status.holder_name is None
        connection.close()

    @respx.mock
    def test_get_lock_status_locked(self, connection: InstanceConnection):
        """Test getting lock status when locked."""
        respx.get("https://instance-1.example.com/lock").mock(
            return_value=httpx.Response(
                200,
                json={
                    "lock": {
                        "locked": True,
                        "holder_id": "user-123",
                        "holder_name": "Test User",
                        "algorithm": "pagerank",
                        "locked_at": "2025-01-15T10:30:00Z",
                    }
                },
            )
        )

        status = connection.get_lock()

        assert status.locked is True
        assert status.holder_name == "Test User"
        assert status.algorithm == "pagerank"
        connection.close()


class TestInstanceConnectionDataFrame:
    """Integration tests for DataFrame conversion."""

    @pytest.fixture
    def connection(self) -> InstanceConnection:
        """Create instance connection for tests."""
        return InstanceConnection(
            instance_url="https://instance-1.example.com",
            username="test-user@example.com",
        )

    @respx.mock
    def test_query_to_dicts(self, connection: InstanceConnection):
        """Test converting query results to list of dicts."""
        respx.post("https://instance-1.example.com/query").mock(
            return_value=httpx.Response(
                200,
                json={
                    "columns": ["name", "age", "city"],
                    "column_types": ["STRING", "INT64", "STRING"],
                    "rows": [
                        ["Alice", 30, "London"],
                        ["Bob", 25, "Paris"],
                        ["Charlie", 35, "Berlin"],
                    ],
                    "row_count": 3,
                    "execution_time_ms": 20,
                },
            )
        )

        result = connection.query("MATCH (n) RETURN n.name, n.age, n.city")
        dicts = result.to_dicts()

        assert len(dicts) == 3
        assert dicts[0] == {"name": "Alice", "age": 30, "city": "London"}
        assert dicts[1] == {"name": "Bob", "age": 25, "city": "Paris"}
        connection.close()


class TestInstanceConnectionTypeCoercion:
    """Integration tests for automatic type coercion."""

    @pytest.fixture
    def connection(self) -> InstanceConnection:
        """Create instance connection for tests."""
        return InstanceConnection(
            instance_url="https://instance-1.example.com",
            username="test-user@example.com",
        )

    @respx.mock
    def test_date_type_coercion(self, connection: InstanceConnection):
        """Test DATE type is coerced to date object."""
        from datetime import date

        respx.post("https://instance-1.example.com/query").mock(
            return_value=httpx.Response(
                200,
                json={
                    "columns": ["birth_date"],
                    "column_types": ["DATE"],
                    "rows": [["2025-01-15"]],
                    "row_count": 1,
                    "execution_time_ms": 5,
                },
            )
        )

        result = connection.query("MATCH (n) RETURN n.birth_date")

        assert result.rows[0][0] == date(2025, 1, 15)
        connection.close()

    @respx.mock
    def test_timestamp_type_coercion(self, connection: InstanceConnection):
        """Test TIMESTAMP type is coerced to datetime object."""
        from datetime import datetime

        respx.post("https://instance-1.example.com/query").mock(
            return_value=httpx.Response(
                200,
                json={
                    "columns": ["created_at"],
                    "column_types": ["TIMESTAMP"],
                    "rows": [["2025-01-15T10:30:00Z"]],
                    "row_count": 1,
                    "execution_time_ms": 5,
                },
            )
        )

        result = connection.query("MATCH (n) RETURN n.created_at")

        assert isinstance(result.rows[0][0], datetime)
        assert result.rows[0][0].year == 2025
        assert result.rows[0][0].month == 1
        assert result.rows[0][0].day == 15
        connection.close()
