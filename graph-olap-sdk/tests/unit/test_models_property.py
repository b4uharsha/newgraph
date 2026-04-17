"""Property-based tests using Hypothesis.

These tests automatically generate edge cases that regular unit tests miss.
This is a Google-style testing approach for robust validation.
"""

from __future__ import annotations

from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from graph_olap.models.common import PaginatedList, QueryResult
from graph_olap.models.mapping import PropertyDefinition

# =============================================================================
# Strategies for generating test data
# =============================================================================

property_types = st.sampled_from(["STRING", "INT64", "DOUBLE", "BOOL", "DATE", "TIMESTAMP"])

property_definition_strategy = st.builds(
    PropertyDefinition,
    name=st.text(min_size=1, max_size=50).filter(lambda x: x.strip()),
    type=property_types,
)


# =============================================================================
# PaginatedList Property Tests
# =============================================================================


class TestPaginatedListProperties:
    """Property-based tests for PaginatedList."""

    @given(
        items=st.lists(st.integers(), min_size=0, max_size=100),
        total=st.integers(min_value=0, max_value=10000),
        offset=st.integers(min_value=0, max_value=1000),
        limit=st.integers(min_value=1, max_value=100),
    )
    def test_len_matches_items(self, items: list[int], total: int, offset: int, limit: int):
        """Length always equals number of items in current page."""
        paginated = PaginatedList(items=items, total=total, offset=offset, limit=limit)
        assert len(paginated) == len(items)

    @given(
        items=st.lists(st.integers(), min_size=0, max_size=100),
        total=st.integers(min_value=0, max_value=10000),
        offset=st.integers(min_value=0, max_value=1000),
        limit=st.integers(min_value=1, max_value=100),
    )
    def test_iteration_returns_all_items(
        self, items: list[int], total: int, offset: int, limit: int
    ):
        """Iteration returns all items in order."""
        paginated = PaginatedList(items=items, total=total, offset=offset, limit=limit)
        assert list(paginated) == items

    @given(
        items=st.lists(st.integers(), min_size=1, max_size=100),
        total=st.integers(min_value=1, max_value=10000),
        offset=st.integers(min_value=0, max_value=1000),
        limit=st.integers(min_value=1, max_value=100),
    )
    def test_has_more_logic(self, items: list[int], total: int, offset: int, limit: int):
        """has_more is True iff there are more items beyond current page."""
        paginated = PaginatedList(items=items, total=total, offset=offset, limit=limit)

        # has_more should be True if offset + len(items) < total
        # (based on actual items returned, not the limit requested)
        expected_has_more = offset + len(items) < total
        assert paginated.has_more == expected_has_more

    @given(
        total=st.integers(min_value=0, max_value=10000),
        limit=st.integers(min_value=1, max_value=100),
    )
    def test_page_count_calculation(self, total: int, limit: int):
        """Page count is ceiling division of total by limit."""
        paginated = PaginatedList(items=[], total=total, offset=0, limit=limit)

        expected_pages = (total + limit - 1) // limit if total > 0 else 0
        assert paginated.page_count == expected_pages


# =============================================================================
# QueryResult Property Tests
# =============================================================================


class TestQueryResultProperties:
    """Property-based tests for QueryResult."""

    @given(
        num_cols=st.integers(min_value=1, max_value=10),
        num_rows=st.integers(min_value=0, max_value=50),
    )
    @settings(max_examples=50)
    def test_to_dicts_column_count(self, num_cols: int, num_rows: int):
        """to_dicts returns dicts with correct number of keys."""
        columns = [f"col_{i}" for i in range(num_cols)]
        column_types = ["STRING"] * num_cols
        rows = [[f"val_{i}_{j}" for j in range(num_cols)] for i in range(num_rows)]

        result = QueryResult(
            columns=columns,
            column_types=column_types,
            rows=rows,
            row_count=num_rows,
            execution_time_ms=10,
        )

        dicts = result.to_dicts()
        assert len(dicts) == num_rows
        for d in dicts:
            assert len(d) == num_cols
            assert set(d.keys()) == set(columns)

    @given(
        value=st.one_of(
            st.integers(),
            st.floats(allow_nan=False, allow_infinity=False),
            st.text(max_size=50),
            st.booleans(),
        )
    )
    def test_scalar_returns_single_value(self, value: Any):
        """scalar() returns the single value from 1x1 result."""
        result = QueryResult(
            columns=["result"],
            column_types=["STRING"],
            rows=[[value]],
            row_count=1,
            execution_time_ms=5,
        )

        assert result.scalar() == value


# =============================================================================
# PropertyDefinition Property Tests
# =============================================================================


class TestPropertyDefinitionProperties:
    """Property-based tests for PropertyDefinition."""

    @given(
        name=st.text(min_size=1, max_size=100).filter(lambda x: x.strip()),
        prop_type=property_types,
    )
    def test_roundtrip(self, name: str, prop_type: str):
        """PropertyDefinition can be created and serialized."""
        prop = PropertyDefinition(name=name, type=prop_type)

        assert prop.name == name
        assert prop.type == prop_type

    @given(
        names=st.lists(
            st.text(min_size=1, max_size=50).filter(lambda x: x.strip()),
            min_size=1,
            max_size=20,
            unique=True,
        ),
    )
    def test_unique_property_names(self, names: list[str]):
        """Multiple properties with unique names can coexist."""
        properties = [PropertyDefinition(name=name, type="STRING") for name in names]

        assert len(properties) == len(names)
        assert len({p.name for p in properties}) == len(names)


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases that property-based testing helps find."""

    def test_empty_paginated_list(self):
        """Empty list handles correctly."""
        paginated = PaginatedList(items=[], total=0, offset=0, limit=50)

        assert len(paginated) == 0
        assert paginated.has_more is False
        assert paginated.page_count == 0
        assert list(paginated) == []

    def test_query_result_empty(self):
        """Empty query result handles correctly."""
        result = QueryResult(
            columns=["id", "name"],
            column_types=["INT64", "STRING"],
            rows=[],
            row_count=0,
            execution_time_ms=1,
        )

        assert result.row_count == 0
        assert result.to_dicts() == []
        assert list(result) == []

    def test_query_result_unicode(self):
        """Unicode in query results is handled."""
        result = QueryResult(
            columns=["name"],
            column_types=["STRING"],
            rows=[["日本語"], ["émoji 🎉"], ["中文"]],
            row_count=3,
            execution_time_ms=5,
        )

        dicts = result.to_dicts()
        assert dicts[0]["name"] == "日本語"
        assert dicts[1]["name"] == "émoji 🎉"
        assert dicts[2]["name"] == "中文"

    def test_large_numbers(self):
        """Large numbers are handled correctly."""
        big_int = 2**63 - 1  # Max signed 64-bit
        big_float = 1.7976931348623157e308  # Near max float64

        result = QueryResult(
            columns=["big_int", "big_float"],
            column_types=["INT64", "DOUBLE"],
            rows=[[big_int, big_float]],
            row_count=1,
            execution_time_ms=1,
        )

        assert result.rows[0][0] == big_int
        assert result.rows[0][1] == big_float
