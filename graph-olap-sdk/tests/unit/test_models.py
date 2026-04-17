"""Unit tests for Pydantic models."""

from __future__ import annotations

from datetime import datetime

import pytest

from graph_olap.models import (
    Instance,
    LockStatus,
    Mapping,
    NodeDefinition,
    PaginatedList,
    QueryResult,
    Schema,
    Snapshot,
)
from graph_olap.models.mapping import PropertyDefinition


class TestNodeDefinition:
    """Tests for NodeDefinition model."""

    def test_create_from_api_dict(self):
        """Test creating NodeDefinition from API response."""
        data = {
            "label": "Customer",
            "sql": "SELECT * FROM customers",
            "primary_key": {"name": "id", "type": "STRING"},
            "properties": [
                {"name": "name", "type": "STRING"},
                {"name": "age", "type": "INT64"},
            ],
        }

        node = NodeDefinition(
            label=data["label"],
            sql=data["sql"],
            primary_key=data["primary_key"],
            properties=[PropertyDefinition(**p) for p in data["properties"]],
        )

        assert node.label == "Customer"
        assert node.sql == "SELECT * FROM customers"
        assert node.primary_key == {"name": "id", "type": "STRING"}
        assert len(node.properties) == 2

    def test_to_api_dict(self):
        """Test converting NodeDefinition to API format."""
        node = NodeDefinition(
            label="Customer",
            sql="SELECT * FROM customers",
            primary_key={"name": "id", "type": "STRING"},
            properties=[
                PropertyDefinition(name="name", type="STRING"),
                PropertyDefinition(name="age", type="INT64"),
            ],
        )

        result = node.to_api_dict()

        assert result["label"] == "Customer"
        assert result["sql"] == "SELECT * FROM customers"
        assert len(result["properties"]) == 2


class TestMapping:
    """Tests for Mapping model."""

    def test_from_api_response(self, sample_mapping_data):
        """Test creating Mapping from API response."""
        mapping = Mapping.from_api_response(sample_mapping_data)

        assert mapping.id == 1
        assert mapping.name == "Customer Graph"
        assert mapping.owner_username == "test_user"
        assert mapping.current_version == 1
        assert mapping.snapshot_count == 2
        assert mapping.version is not None
        assert mapping.version.version == 1
        assert len(mapping.version.node_definitions) == 1
        assert len(mapping.version.edge_definitions) == 1

    def test_repr_html(self, sample_mapping_data):
        """Test HTML representation for Jupyter."""
        mapping = Mapping.from_api_response(sample_mapping_data)

        html = mapping._repr_html_()

        assert "Customer Graph" in html
        assert "test_user" in html
        assert "v1" in html


# =============================================================================
# SNAPSHOT TESTS DISABLED
# These tests are commented out as snapshot functionality has been disabled.
# =============================================================================
# class TestSnapshot:
#     """Tests for Snapshot model."""
#
#     def test_from_api_response(self, sample_snapshot_data):
#         """Test creating Snapshot from API response."""
#         snapshot = Snapshot.from_api_response(sample_snapshot_data)
#
#         assert snapshot.id == 1
#         assert snapshot.name == "Analysis Snapshot"
#         assert snapshot.status == "ready"
#         assert snapshot.is_ready is True
#         assert snapshot.size_mb == pytest.approx(100.0, rel=0.01)
#         assert snapshot.node_counts["Customer"] == 10000
#
#     def test_is_ready(self):
#         """Test is_ready property."""
#         ready = Snapshot.from_api_response(
#             {
#                 "id": 1,
#                 "mapping_id": 1,
#                 "mapping_version": 1,
#                 "owner_username": "test_user",
#                 "name": "Test",
#                 "status": "ready",
#                 "created_at": "2025-01-15T10:30:00Z",
#                 "updated_at": "2025-01-15T10:30:00Z",
#             }
#         )
#         assert ready.is_ready is True
#
#         creating = Snapshot.from_api_response(
#             {
#                 "id": 1,
#                 "mapping_id": 1,
#                 "mapping_version": 1,
#                 "owner_username": "test_user",
#                 "name": "Test",
#                 "status": "creating",
#                 "created_at": "2025-01-15T10:30:00Z",
#                 "updated_at": "2025-01-15T10:30:00Z",
#             }
#         )
#         assert creating.is_ready is False


class TestInstance:
    """Tests for Instance model."""

    def test_from_api_response(self, sample_instance_data):
        """Test creating Instance from API response."""
        instance = Instance.from_api_response(sample_instance_data)

        assert instance.id == 1
        assert instance.name == "Analysis Instance"
        assert instance.status == "running"
        assert instance.is_running is True
        assert instance.memory_mb == pytest.approx(512.0, rel=0.01)

    def test_repr_html(self, sample_instance_data):
        """Test HTML representation for Jupyter."""
        instance = Instance.from_api_response(sample_instance_data)

        html = instance._repr_html_()

        assert "Analysis Instance" in html
        assert "running" in html.lower()


class TestQueryResult:
    """Tests for QueryResult model."""

    def test_from_api_response(self, sample_query_result_data):
        """Test creating QueryResult from API response."""
        result = QueryResult.from_api_response(sample_query_result_data)

        assert result.columns == ["name", "age", "city"]
        assert result.row_count == 3
        assert len(result.rows) == 3

    def test_iteration(self, sample_query_result_data):
        """Test iterating over results as dicts."""
        result = QueryResult.from_api_response(sample_query_result_data)

        rows = list(result)

        assert len(rows) == 3
        assert rows[0] == {"name": "Alice", "age": 30, "city": "London"}
        assert rows[1] == {"name": "Bob", "age": 25, "city": "Paris"}

    def test_to_dicts(self, sample_query_result_data):
        """Test converting to list of dicts."""
        result = QueryResult.from_api_response(sample_query_result_data)

        dicts = result.to_dicts()

        assert len(dicts) == 3
        assert dicts[0]["name"] == "Alice"

    def test_scalar(self):
        """Test extracting scalar value."""
        data = {
            "columns": ["count"],
            "column_types": ["INT64"],
            "rows": [[42]],
            "row_count": 1,
            "execution_time_ms": 5,
        }
        result = QueryResult.from_api_response(data)

        assert result.scalar() == 42

    def test_scalar_raises_on_multiple_values(self, sample_query_result_data):
        """Test scalar raises ValueError for multiple rows/columns."""
        result = QueryResult.from_api_response(sample_query_result_data)

        with pytest.raises(ValueError, match="Expected single value"):
            result.scalar()

    def test_type_coercion_date(self):
        """Test automatic type coercion for DATE."""
        data = {
            "columns": ["date"],
            "column_types": ["DATE"],
            "rows": [["2025-01-15"]],
            "row_count": 1,
            "execution_time_ms": 5,
        }
        result = QueryResult.from_api_response(data)

        from datetime import date

        assert result.rows[0][0] == date(2025, 1, 15)

    def test_type_coercion_timestamp(self):
        """Test automatic type coercion for TIMESTAMP."""
        data = {
            "columns": ["ts"],
            "column_types": ["TIMESTAMP"],
            "rows": [["2025-01-15T10:30:00Z"]],
            "row_count": 1,
            "execution_time_ms": 5,
        }
        result = QueryResult.from_api_response(data)

        assert isinstance(result.rows[0][0], datetime)
        assert result.rows[0][0].year == 2025

    def test_type_coercion_disabled(self):
        """Test disabling type coercion."""
        data = {
            "columns": ["date"],
            "column_types": ["DATE"],
            "rows": [["2025-01-15"]],
            "row_count": 1,
            "execution_time_ms": 5,
        }
        result = QueryResult.from_api_response(data, coerce_types=False)

        assert result.rows[0][0] == "2025-01-15"  # String, not date


class TestPaginatedList:
    """Tests for PaginatedList model."""

    def test_basic_properties(self):
        """Test basic PaginatedList properties."""
        items = [1, 2, 3]
        paginated = PaginatedList(items=items, total=100, offset=0, limit=50)

        assert len(paginated) == 3
        assert paginated.total == 100
        assert paginated.has_more is True
        assert paginated.page_count == 2

    def test_iteration(self):
        """Test iterating over PaginatedList."""
        items = ["a", "b", "c"]
        paginated = PaginatedList(items=items, total=3, offset=0, limit=50)

        result = list(paginated)
        assert result == ["a", "b", "c"]

    def test_indexing(self):
        """Test indexing PaginatedList."""
        items = ["a", "b", "c"]
        paginated = PaginatedList(items=items, total=3, offset=0, limit=50)

        assert paginated[0] == "a"
        assert paginated[2] == "c"


class TestLockStatus:
    """Tests for LockStatus model."""

    def test_unlocked(self):
        """Test unlocked status."""
        data = {"locked": False}
        status = LockStatus.from_api_response(data)

        assert status.locked is False
        assert status.holder_name is None
        assert status.algorithm is None

    def test_locked(self):
        """Test locked status."""
        data = {
            "locked": True,
            "holder_id": "user-123",
            "holder_name": "Test User",
            "algorithm": "pagerank",
            "locked_at": "2025-01-15T10:30:00Z",
        }
        status = LockStatus.from_api_response(data)

        assert status.locked is True
        assert status.holder_name == "Test User"
        assert status.algorithm == "pagerank"


class TestSchema:
    """Tests for Schema model."""

    def test_from_api_response(self):
        """Test creating Schema from API response."""
        data = {
            "node_labels": {
                "Customer": ["id", "name", "age"],
                "Product": ["id", "name", "price"],
            },
            "relationship_types": {
                "PURCHASED": ["amount", "date"],
            },
            "node_count": 15000,
            "relationship_count": 50000,
        }
        schema = Schema.from_api_response(data)

        assert len(schema.node_labels) == 2
        assert "Customer" in schema.node_labels
        assert schema.node_count == 15000

    def test_repr_html(self):
        """Test HTML representation for Jupyter."""
        data = {
            "node_labels": {"Customer": ["id", "name"]},
            "relationship_types": {"PURCHASED": ["amount"]},
            "node_count": 100,
            "relationship_count": 200,
        }
        schema = Schema.from_api_response(data)

        html = schema._repr_html_()

        assert "Customer" in html
        assert "PURCHASED" in html
