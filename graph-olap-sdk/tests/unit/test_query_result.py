"""Tests for QueryResult - a critical data structure."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from graph_olap.models.common import QueryResult


class TestQueryResultTypeCoercion:
    """Tests for automatic type coercion in QueryResult."""

    def test_date_coercion(self):
        """DATE strings are converted to date objects."""
        result = QueryResult.from_api_response(
            {
                "columns": ["birth_date"],
                "column_types": ["DATE"],
                "rows": [["2025-01-15"], ["2024-12-25"]],
                "row_count": 2,
                "execution_time_ms": 5,
            }
        )

        assert result.rows[0][0] == date(2025, 1, 15)
        assert result.rows[1][0] == date(2024, 12, 25)

    def test_timestamp_coercion(self):
        """TIMESTAMP strings are converted to datetime objects."""
        result = QueryResult.from_api_response(
            {
                "columns": ["created_at"],
                "column_types": ["TIMESTAMP"],
                "rows": [["2025-01-15T10:30:00Z"]],
                "row_count": 1,
                "execution_time_ms": 5,
            }
        )

        assert isinstance(result.rows[0][0], datetime)
        assert result.rows[0][0].year == 2025

    def test_timestamp_with_timezone(self):
        """TIMESTAMP with timezone offset is handled."""
        result = QueryResult.from_api_response(
            {
                "columns": ["ts"],
                "column_types": ["TIMESTAMP"],
                "rows": [["2025-01-15T10:30:00+05:30"]],
                "row_count": 1,
                "execution_time_ms": 5,
            }
        )

        assert isinstance(result.rows[0][0], datetime)

    def test_coercion_disabled(self):
        """Type coercion can be disabled."""
        result = QueryResult.from_api_response(
            {
                "columns": ["date"],
                "column_types": ["DATE"],
                "rows": [["2025-01-15"]],
                "row_count": 1,
                "execution_time_ms": 5,
            },
            coerce_types=False,
        )

        assert result.rows[0][0] == "2025-01-15"  # String, not date

    def test_null_values_preserved(self):
        """NULL values are preserved during coercion."""
        result = QueryResult.from_api_response(
            {
                "columns": ["date", "name"],
                "column_types": ["DATE", "STRING"],
                "rows": [[None, "Alice"], ["2025-01-15", None]],
                "row_count": 2,
                "execution_time_ms": 5,
            }
        )

        assert result.rows[0][0] is None
        assert result.rows[1][1] is None

    def test_mixed_types(self):
        """Multiple column types are handled correctly."""
        result = QueryResult.from_api_response(
            {
                "columns": ["id", "name", "amount", "active", "created"],
                "column_types": ["INT64", "STRING", "DOUBLE", "BOOL", "DATE"],
                "rows": [[1, "Alice", 99.99, True, "2025-01-15"]],
                "row_count": 1,
                "execution_time_ms": 10,
            }
        )

        row = result.rows[0]
        assert row[0] == 1
        assert row[1] == "Alice"
        assert row[2] == 99.99
        assert row[3] is True
        assert row[4] == date(2025, 1, 15)


class TestQueryResultIteration:
    """Tests for iterating over QueryResult."""

    def test_iteration_yields_dicts(self):
        """Iteration yields dict for each row."""
        result = QueryResult.from_api_response(
            {
                "columns": ["a", "b"],
                "column_types": ["INT64", "STRING"],
                "rows": [[1, "x"], [2, "y"]],
                "row_count": 2,
                "execution_time_ms": 5,
            }
        )

        rows = list(result)
        assert rows == [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}]

    def test_empty_result_iteration(self):
        """Empty result yields no rows."""
        result = QueryResult.from_api_response(
            {
                "columns": ["a"],
                "column_types": ["INT64"],
                "rows": [],
                "row_count": 0,
                "execution_time_ms": 1,
            }
        )

        assert list(result) == []


class TestQueryResultScalar:
    """Tests for scalar() method."""

    def test_scalar_returns_single_value(self):
        """scalar() returns the single value."""
        result = QueryResult.from_api_response(
            {
                "columns": ["count"],
                "column_types": ["INT64"],
                "rows": [[42]],
                "row_count": 1,
                "execution_time_ms": 5,
            }
        )

        assert result.scalar() == 42

    def test_scalar_raises_on_multiple_rows(self):
        """scalar() raises ValueError for multiple rows."""
        result = QueryResult.from_api_response(
            {
                "columns": ["count"],
                "column_types": ["INT64"],
                "rows": [[1], [2]],
                "row_count": 2,
                "execution_time_ms": 5,
            }
        )

        with pytest.raises(ValueError, match="Expected single value"):
            result.scalar()

    def test_scalar_raises_on_multiple_columns(self):
        """scalar() raises ValueError for multiple columns."""
        result = QueryResult.from_api_response(
            {
                "columns": ["a", "b"],
                "column_types": ["INT64", "INT64"],
                "rows": [[1, 2]],
                "row_count": 1,
                "execution_time_ms": 5,
            }
        )

        with pytest.raises(ValueError, match="Expected single value"):
            result.scalar()

    def test_scalar_raises_on_empty(self):
        """scalar() raises ValueError for empty result."""
        result = QueryResult.from_api_response(
            {
                "columns": ["count"],
                "column_types": ["INT64"],
                "rows": [],
                "row_count": 0,
                "execution_time_ms": 5,
            }
        )

        with pytest.raises(ValueError, match="Expected single value"):
            result.scalar()


class TestQueryResultToDicts:
    """Tests for to_dicts() method."""

    def test_to_dicts_basic(self):
        """to_dicts() returns list of dicts."""
        result = QueryResult.from_api_response(
            {
                "columns": ["name", "age"],
                "column_types": ["STRING", "INT64"],
                "rows": [["Alice", 30], ["Bob", 25]],
                "row_count": 2,
                "execution_time_ms": 5,
            }
        )

        dicts = result.to_dicts()
        assert dicts == [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
        ]

    def test_to_dicts_empty(self):
        """to_dicts() returns empty list for empty result."""
        result = QueryResult.from_api_response(
            {
                "columns": ["name"],
                "column_types": ["STRING"],
                "rows": [],
                "row_count": 0,
                "execution_time_ms": 1,
            }
        )

        assert result.to_dicts() == []

    def test_to_dicts_preserves_types(self):
        """to_dicts() preserves coerced types."""
        result = QueryResult.from_api_response(
            {
                "columns": ["date"],
                "column_types": ["DATE"],
                "rows": [["2025-01-15"]],
                "row_count": 1,
                "execution_time_ms": 5,
            }
        )

        dicts = result.to_dicts()
        assert dicts[0]["date"] == date(2025, 1, 15)
