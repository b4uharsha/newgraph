"""Unit tests for diff rendering utilities.

Tests the utility functions for rendering diffs in various formats:
- render_diff_summary: compact text summary
- render_diff_details: detailed line-by-line output
- diff_to_dict: conversion to dictionary/pandas format
"""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch

import pytest

from graph_olap.models.mapping import MappingDiff
from graph_olap.utils.diff import diff_to_dict, render_diff_details, render_diff_summary


class TestRenderDiffSummary:
    """Tests for render_diff_summary function."""

    @pytest.fixture
    def sample_diff(self) -> MappingDiff:
        """Create sample diff for testing."""
        return MappingDiff.from_api_response({
            "mapping_id": 1,
            "from_version": 1,
            "to_version": 2,
            "summary": {
                "nodes_added": 1,
                "nodes_removed": 0,
                "nodes_modified": 1,
                "edges_added": 0,
                "edges_removed": 1,
                "edges_modified": 1,
            },
            "changes": {"nodes": [], "edges": []},
        })

    def test_renders_version_info(self, sample_diff: MappingDiff):
        """Test that summary includes version numbers."""
        with patch("sys.stdout", new=StringIO()) as fake_out:
            render_diff_summary(sample_diff)
            output = fake_out.getvalue()

        assert "v1" in output
        assert "v2" in output

    def test_renders_summary_counts(self, sample_diff: MappingDiff):
        """Test that summary shows correct counts."""
        with patch("sys.stdout", new=StringIO()) as fake_out:
            render_diff_summary(sample_diff)
            output = fake_out.getvalue()

        # Check nodes line
        assert "+1" in output  # nodes_added
        assert "-0" in output  # nodes_removed
        assert "~1" in output  # nodes_modified

        # Check edges line
        assert "-1" in output  # edges_removed
        assert "~1" in output  # edges_modified

    def test_renders_separator_line(self, sample_diff: MappingDiff):
        """Test that summary includes separator."""
        with patch("sys.stdout", new=StringIO()) as fake_out:
            render_diff_summary(sample_diff)
            output = fake_out.getvalue()

        assert "=" in output  # Should have separator line

    def test_empty_diff_shows_zeros(self):
        """Test rendering diff with no changes."""
        empty_diff = MappingDiff.from_api_response({
            "mapping_id": 1,
            "from_version": 1,
            "to_version": 2,
            "summary": {
                "nodes_added": 0,
                "nodes_removed": 0,
                "nodes_modified": 0,
                "edges_added": 0,
                "edges_removed": 0,
                "edges_modified": 0,
            },
            "changes": {"nodes": [], "edges": []},
        })

        with patch("sys.stdout", new=StringIO()) as fake_out:
            render_diff_summary(empty_diff)
            output = fake_out.getvalue()

        assert "+0" in output
        assert "-0" in output
        assert "~0" in output


class TestRenderDiffDetails:
    """Tests for render_diff_details function."""

    @pytest.fixture
    def diff_with_changes(self) -> MappingDiff:
        """Create diff with actual changes for testing."""
        return MappingDiff.from_api_response({
            "mapping_id": 1,
            "from_version": 1,
            "to_version": 2,
            "summary": {},
            "changes": {
                "nodes": [
                    {
                        "label": "Customer",
                        "change_type": "modified",
                        "fields_changed": ["sql", "properties"],
                        "from": {"sql": "SELECT id FROM customers"},
                        "to": {"sql": "SELECT id, name FROM customers"},
                    },
                    {
                        "label": "Supplier",
                        "change_type": "added",
                        "fields_changed": None,
                        "from": None,
                        "to": {"label": "Supplier"},
                    },
                    {
                        "label": "OldNode",
                        "change_type": "removed",
                        "fields_changed": None,
                        "from": {"label": "OldNode"},
                        "to": None,
                    },
                ],
                "edges": [
                    {
                        "type": "PURCHASED",
                        "change_type": "modified",
                        "fields_changed": ["properties"],
                        "from": {"properties": []},
                        "to": {"properties": [{"name": "amount"}]},
                    },
                    {
                        "type": "KNOWS",
                        "change_type": "added",
                        "fields_changed": None,
                        "from": None,
                        "to": {"type": "KNOWS"},
                    },
                ],
            },
        })

    def test_shows_added_nodes(self, diff_with_changes: MappingDiff):
        """Test that added nodes are displayed."""
        with patch("sys.stdout", new=StringIO()) as fake_out:
            render_diff_details(diff_with_changes)
            output = fake_out.getvalue()

        assert "+ Node: Supplier" in output

    def test_shows_removed_nodes(self, diff_with_changes: MappingDiff):
        """Test that removed nodes are displayed."""
        with patch("sys.stdout", new=StringIO()) as fake_out:
            render_diff_details(diff_with_changes)
            output = fake_out.getvalue()

        assert "- Node: OldNode" in output

    def test_shows_modified_nodes(self, diff_with_changes: MappingDiff):
        """Test that modified nodes are displayed with fields."""
        with patch("sys.stdout", new=StringIO()) as fake_out:
            render_diff_details(diff_with_changes)
            output = fake_out.getvalue()

        assert "~ Node: Customer" in output
        assert "sql" in output
        assert "properties" in output

    def test_shows_added_edges(self, diff_with_changes: MappingDiff):
        """Test that added edges are displayed."""
        with patch("sys.stdout", new=StringIO()) as fake_out:
            render_diff_details(diff_with_changes)
            output = fake_out.getvalue()

        assert "+ Edge: KNOWS" in output

    def test_shows_modified_edges(self, diff_with_changes: MappingDiff):
        """Test that modified edges are displayed."""
        with patch("sys.stdout", new=StringIO()) as fake_out:
            render_diff_details(diff_with_changes)
            output = fake_out.getvalue()

        assert "~ Edge: PURCHASED" in output
        assert "properties" in output

    def test_show_from_to_false_by_default(self, diff_with_changes: MappingDiff):
        """Test that before/after details are hidden by default."""
        with patch("sys.stdout", new=StringIO()) as fake_out:
            render_diff_details(diff_with_changes)
            output = fake_out.getvalue()

        # Should not show before/after when show_from_to=False (default)
        assert "Before:" not in output
        assert "After:" not in output

    def test_show_from_to_true_shows_details(self, diff_with_changes: MappingDiff):
        """Test that before/after details are shown when requested."""
        with patch("sys.stdout", new=StringIO()) as fake_out:
            render_diff_details(diff_with_changes, show_from_to=True)
            output = fake_out.getvalue()

        # Should show before/after for modified items
        assert "Before:" in output
        assert "After:" in output

    def test_empty_diff_produces_no_output(self):
        """Test that empty diff produces no output."""
        empty_diff = MappingDiff.from_api_response({
            "mapping_id": 1,
            "from_version": 1,
            "to_version": 2,
            "summary": {},
            "changes": {"nodes": [], "edges": []},
        })

        with patch("sys.stdout", new=StringIO()) as fake_out:
            render_diff_details(empty_diff)
            output = fake_out.getvalue()

        # Should be empty or only whitespace
        assert output.strip() == ""


class TestDiffToDict:
    """Tests for diff_to_dict function."""

    @pytest.fixture
    def complex_diff(self) -> MappingDiff:
        """Create complex diff for testing."""
        return MappingDiff.from_api_response({
            "mapping_id": 42,
            "from_version": 3,
            "to_version": 5,
            "summary": {
                "nodes_added": 2,
                "nodes_removed": 1,
                "nodes_modified": 1,
                "edges_added": 1,
                "edges_removed": 0,
                "edges_modified": 1,
            },
            "changes": {
                "nodes": [
                    {
                        "label": "A",
                        "change_type": "added",
                        "fields_changed": None,
                        "from": None,
                        "to": {},
                    },
                    {
                        "label": "B",
                        "change_type": "added",
                        "fields_changed": None,
                        "from": None,
                        "to": {},
                    },
                    {
                        "label": "C",
                        "change_type": "removed",
                        "fields_changed": None,
                        "from": {},
                        "to": None,
                    },
                    {
                        "label": "D",
                        "change_type": "modified",
                        "fields_changed": ["sql"],
                        "from": {},
                        "to": {},
                    },
                ],
                "edges": [
                    {
                        "type": "E1",
                        "change_type": "added",
                        "fields_changed": None,
                        "from": None,
                        "to": {},
                    },
                    {
                        "type": "E2",
                        "change_type": "modified",
                        "fields_changed": ["properties", "sql"],
                        "from": {},
                        "to": {},
                    },
                ],
            },
        })

    def test_returns_dict_with_correct_keys(self, complex_diff: MappingDiff):
        """Test that output has expected structure."""
        result = diff_to_dict(complex_diff)

        assert isinstance(result, dict)
        assert "mapping_id" in result
        assert "from_version" in result
        assert "to_version" in result
        assert "summary" in result
        assert "changes" in result

    def test_preserves_metadata(self, complex_diff: MappingDiff):
        """Test that metadata is preserved."""
        result = diff_to_dict(complex_diff)

        assert result["mapping_id"] == 42
        assert result["from_version"] == 3
        assert result["to_version"] == 5

    def test_changes_is_list(self, complex_diff: MappingDiff):
        """Test that changes is a flat list."""
        result = diff_to_dict(complex_diff)

        assert isinstance(result["changes"], list)

    def test_changes_count_matches_diff(self, complex_diff: MappingDiff):
        """Test that all changes are included."""
        result = diff_to_dict(complex_diff)

        # 4 nodes + 2 edges = 6 total changes
        assert len(result["changes"]) == 6

    def test_change_structure(self, complex_diff: MappingDiff):
        """Test that each change has correct structure."""
        result = diff_to_dict(complex_diff)

        for change in result["changes"]:
            assert "type" in change  # "node" or "edge"
            assert "name" in change  # label or type
            assert "change" in change  # "added", "removed", "modified"
            assert "fields" in change  # string of changed fields or None

    def test_node_changes(self, complex_diff: MappingDiff):
        """Test that node changes are correct."""
        result = diff_to_dict(complex_diff)

        node_changes = [c for c in result["changes"] if c["type"] == "node"]
        assert len(node_changes) == 4

        # Check added nodes
        added = [c for c in node_changes if c["change"] == "added"]
        assert len(added) == 2
        assert {c["name"] for c in added} == {"A", "B"}

        # Check removed nodes
        removed = [c for c in node_changes if c["change"] == "removed"]
        assert len(removed) == 1
        assert removed[0]["name"] == "C"

        # Check modified nodes
        modified = [c for c in node_changes if c["change"] == "modified"]
        assert len(modified) == 1
        assert modified[0]["name"] == "D"
        assert modified[0]["fields"] == "sql"

    def test_edge_changes(self, complex_diff: MappingDiff):
        """Test that edge changes are correct."""
        result = diff_to_dict(complex_diff)

        edge_changes = [c for c in result["changes"] if c["type"] == "edge"]
        assert len(edge_changes) == 2

        # Check modified edge
        modified = [c for c in edge_changes if c["change"] == "modified"]
        assert len(modified) == 1
        assert modified[0]["name"] == "E2"
        assert "properties" in modified[0]["fields"]
        assert "sql" in modified[0]["fields"]

    def test_added_removed_have_null_fields(self, complex_diff: MappingDiff):
        """Test that added/removed changes have None for fields."""
        result = diff_to_dict(complex_diff)

        added_removed = [
            c
            for c in result["changes"]
            if c["change"] in ("added", "removed")
        ]

        for change in added_removed:
            assert change["fields"] is None

    def test_empty_diff(self):
        """Test conversion of empty diff."""
        empty_diff = MappingDiff.from_api_response({
            "mapping_id": 1,
            "from_version": 1,
            "to_version": 2,
            "summary": {},
            "changes": {"nodes": [], "edges": []},
        })

        result = diff_to_dict(empty_diff)

        assert len(result["changes"]) == 0
        assert result["mapping_id"] == 1

    def test_pandas_compatible_structure(self, complex_diff: MappingDiff):
        """Test that output can be converted to DataFrame."""
        result = diff_to_dict(complex_diff)

        # Try importing pandas and creating DataFrame
        try:
            import pandas as pd

            df = pd.DataFrame(result["changes"])
            assert len(df) == 6
            assert set(df.columns) == {"type", "name", "change", "fields"}
        except ImportError:
            pytest.skip("pandas not installed")
