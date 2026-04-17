"""Unit tests for mapping diff models.

Tests the NodeDiff, EdgeDiff, and MappingDiff models including:
- Model construction and validation
- Parsing from API responses
- Helper methods for filtering changes
- Jupyter HTML rendering
"""

from __future__ import annotations

from typing import Any

import pytest

from graph_olap.models.mapping import EdgeDiff, MappingDiff, NodeDiff


class TestNodeDiff:
    """Tests for NodeDiff model."""

    def test_create_added_node(self):
        """Test creating NodeDiff for an added node."""
        node_diff = NodeDiff(
            label="Customer",
            change_type="added",
            fields_changed=None,
            from_=None,
            to={"label": "Customer", "sql": "SELECT * FROM customers"},
        )

        assert node_diff.label == "Customer"
        assert node_diff.change_type == "added"
        assert node_diff.fields_changed is None
        assert node_diff.from_ is None
        assert node_diff.to is not None

    def test_create_removed_node(self):
        """Test creating NodeDiff for a removed node."""
        node_diff = NodeDiff(
            label="OldNode",
            change_type="removed",
            fields_changed=None,
            from_={"label": "OldNode", "sql": "SELECT * FROM old"},
            to=None,
        )

        assert node_diff.label == "OldNode"
        assert node_diff.change_type == "removed"
        assert node_diff.from_ is not None
        assert node_diff.to is None

    def test_create_modified_node(self):
        """Test creating NodeDiff for a modified node."""
        node_diff = NodeDiff(
            label="Customer",
            change_type="modified",
            fields_changed=["sql", "properties"],
            from_={"sql": "SELECT id, name FROM customers", "properties": []},
            to={"sql": "SELECT id, name, email FROM customers", "properties": []},
        )

        assert node_diff.label == "Customer"
        assert node_diff.change_type == "modified"
        assert node_diff.fields_changed == ["sql", "properties"]
        assert node_diff.from_ is not None
        assert node_diff.to is not None

    def test_from_api_response_added(self):
        """Test parsing added node from API response."""
        api_data = {
            "label": "Supplier",
            "change_type": "added",
            "fields_changed": None,
            "from": None,
            "to": {
                "label": "Supplier",
                "sql": "SELECT * FROM suppliers",
                "primary_key": {"name": "id", "type": "STRING"},
                "properties": [],
            },
        }

        node_diff = NodeDiff.from_api_response(api_data)

        assert node_diff.label == "Supplier"
        assert node_diff.change_type == "added"
        assert node_diff.from_ is None
        assert node_diff.to == api_data["to"]

    def test_from_api_response_modified(self):
        """Test parsing modified node from API response."""
        api_data = {
            "label": "Product",
            "change_type": "modified",
            "fields_changed": ["sql"],
            "from": {"sql": "SELECT id FROM products"},
            "to": {"sql": "SELECT id, name FROM products"},
        }

        node_diff = NodeDiff.from_api_response(api_data)

        assert node_diff.label == "Product"
        assert node_diff.change_type == "modified"
        assert node_diff.fields_changed == ["sql"]


class TestEdgeDiff:
    """Tests for EdgeDiff model."""

    def test_create_added_edge(self):
        """Test creating EdgeDiff for an added edge."""
        edge_diff = EdgeDiff(
            type="PURCHASED",
            change_type="added",
            fields_changed=None,
            from_=None,
            to={"type": "PURCHASED", "from_node": "Customer", "to_node": "Product"},
        )

        assert edge_diff.type == "PURCHASED"
        assert edge_diff.change_type == "added"
        assert edge_diff.to is not None

    def test_create_removed_edge(self):
        """Test creating EdgeDiff for a removed edge."""
        edge_diff = EdgeDiff(
            type="OLD_RELATIONSHIP",
            change_type="removed",
            fields_changed=None,
            from_={"type": "OLD_RELATIONSHIP", "from_node": "A", "to_node": "B"},
            to=None,
        )

        assert edge_diff.type == "OLD_RELATIONSHIP"
        assert edge_diff.change_type == "removed"
        assert edge_diff.from_ is not None
        assert edge_diff.to is None

    def test_create_modified_edge(self):
        """Test creating EdgeDiff for a modified edge."""
        edge_diff = EdgeDiff(
            type="PURCHASED",
            change_type="modified",
            fields_changed=["properties"],
            from_={"properties": [{"name": "amount", "type": "INT64"}]},
            to={"properties": [{"name": "amount", "type": "DOUBLE"}]},
        )

        assert edge_diff.type == "PURCHASED"
        assert edge_diff.change_type == "modified"
        assert edge_diff.fields_changed == ["properties"]

    def test_from_api_response(self):
        """Test parsing edge from API response."""
        api_data = {
            "type": "KNOWS",
            "change_type": "added",
            "fields_changed": None,
            "from": None,
            "to": {"type": "KNOWS", "from_node": "Person", "to_node": "Person"},
        }

        edge_diff = EdgeDiff.from_api_response(api_data)

        assert edge_diff.type == "KNOWS"
        assert edge_diff.change_type == "added"


class TestMappingDiff:
    """Tests for MappingDiff model."""

    @pytest.fixture
    def sample_diff_data(self) -> dict[str, Any]:
        """Sample diff data from API response."""
        return {
            "mapping_id": 1,
            "from_version": 1,
            "to_version": 2,
            "summary": {
                "nodes_added": 1,
                "nodes_removed": 0,
                "nodes_modified": 1,
                "edges_added": 0,
                "edges_removed": 0,
                "edges_modified": 1,
            },
            "changes": {
                "nodes": [
                    {
                        "label": "Customer",
                        "change_type": "modified",
                        "fields_changed": ["sql"],
                        "from": {"sql": "SELECT id FROM customers"},
                        "to": {"sql": "SELECT id, name FROM customers"},
                    },
                    {
                        "label": "Supplier",
                        "change_type": "added",
                        "fields_changed": None,
                        "from": None,
                        "to": {"label": "Supplier", "sql": "SELECT * FROM suppliers"},
                    },
                ],
                "edges": [
                    {
                        "type": "PURCHASED",
                        "change_type": "modified",
                        "fields_changed": ["properties"],
                        "from": {"properties": []},
                        "to": {"properties": [{"name": "amount", "type": "DOUBLE"}]},
                    }
                ],
            },
        }

    def test_from_api_response(self, sample_diff_data: dict[str, Any]):
        """Test parsing full diff from API response."""
        diff = MappingDiff.from_api_response(sample_diff_data)

        assert diff.mapping_id == 1
        assert diff.from_version == 1
        assert diff.to_version == 2
        assert diff.summary["nodes_added"] == 1
        assert diff.summary["nodes_modified"] == 1
        assert len(diff.changes["nodes"]) == 2
        assert len(diff.changes["edges"]) == 1

    def test_nodes_added_filter(self, sample_diff_data: dict[str, Any]):
        """Test filtering for added nodes."""
        diff = MappingDiff.from_api_response(sample_diff_data)
        added = diff.nodes_added()

        assert len(added) == 1
        assert added[0].label == "Supplier"
        assert added[0].change_type == "added"

    def test_nodes_removed_filter(self):
        """Test filtering for removed nodes."""
        diff_data = {
            "mapping_id": 1,
            "from_version": 1,
            "to_version": 2,
            "summary": {"nodes_removed": 1},
            "changes": {
                "nodes": [
                    {
                        "label": "OldNode",
                        "change_type": "removed",
                        "fields_changed": None,
                        "from": {"label": "OldNode"},
                        "to": None,
                    }
                ],
                "edges": [],
            },
        }

        diff = MappingDiff.from_api_response(diff_data)
        removed = diff.nodes_removed()

        assert len(removed) == 1
        assert removed[0].label == "OldNode"
        assert removed[0].change_type == "removed"

    def test_nodes_modified_filter(self, sample_diff_data: dict[str, Any]):
        """Test filtering for modified nodes."""
        diff = MappingDiff.from_api_response(sample_diff_data)
        modified = diff.nodes_modified()

        assert len(modified) == 1
        assert modified[0].label == "Customer"
        assert modified[0].change_type == "modified"
        assert "sql" in modified[0].fields_changed

    def test_edges_added_filter(self):
        """Test filtering for added edges."""
        diff_data = {
            "mapping_id": 1,
            "from_version": 1,
            "to_version": 2,
            "summary": {"edges_added": 1},
            "changes": {
                "nodes": [],
                "edges": [
                    {
                        "type": "KNOWS",
                        "change_type": "added",
                        "fields_changed": None,
                        "from": None,
                        "to": {"type": "KNOWS"},
                    }
                ],
            },
        }

        diff = MappingDiff.from_api_response(diff_data)
        added = diff.edges_added()

        assert len(added) == 1
        assert added[0].type == "KNOWS"

    def test_edges_removed_filter(self):
        """Test filtering for removed edges."""
        diff_data = {
            "mapping_id": 1,
            "from_version": 1,
            "to_version": 2,
            "summary": {"edges_removed": 1},
            "changes": {
                "nodes": [],
                "edges": [
                    {
                        "type": "OLD_REL",
                        "change_type": "removed",
                        "fields_changed": None,
                        "from": {"type": "OLD_REL"},
                        "to": None,
                    }
                ],
            },
        }

        diff = MappingDiff.from_api_response(diff_data)
        removed = diff.edges_removed()

        assert len(removed) == 1
        assert removed[0].type == "OLD_REL"

    def test_edges_modified_filter(self, sample_diff_data: dict[str, Any]):
        """Test filtering for modified edges."""
        diff = MappingDiff.from_api_response(sample_diff_data)
        modified = diff.edges_modified()

        assert len(modified) == 1
        assert modified[0].type == "PURCHASED"
        assert modified[0].change_type == "modified"

    def test_empty_diff(self):
        """Test diff with no changes."""
        diff_data = {
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
        }

        diff = MappingDiff.from_api_response(diff_data)

        assert len(diff.nodes_added()) == 0
        assert len(diff.nodes_removed()) == 0
        assert len(diff.nodes_modified()) == 0
        assert len(diff.edges_added()) == 0
        assert len(diff.edges_removed()) == 0
        assert len(diff.edges_modified()) == 0

    def test_repr_html_exists(self, sample_diff_data: dict[str, Any]):
        """Test that Jupyter HTML representation exists."""
        diff = MappingDiff.from_api_response(sample_diff_data)
        html = diff._repr_html_()

        assert isinstance(html, str)
        assert len(html) > 0
        assert "table" in html.lower()  # Should contain HTML table
        assert "v1" in html  # Should show version numbers
        assert "v2" in html

    def test_repr_html_shows_summary(self, sample_diff_data: dict[str, Any]):
        """Test that HTML representation includes summary counts."""
        diff = MappingDiff.from_api_response(sample_diff_data)
        html = diff._repr_html_()

        # Should show counts from summary
        assert "1" in html  # nodes_added: 1
        assert "0" in html  # nodes_removed: 0

    def test_multiple_filters_independent(self, sample_diff_data: dict[str, Any]):
        """Test that filter methods don't interfere with each other."""
        diff = MappingDiff.from_api_response(sample_diff_data)

        # Call filters multiple times
        added1 = diff.nodes_added()
        modified1 = diff.nodes_modified()
        added2 = diff.nodes_added()
        modified2 = diff.nodes_modified()

        # Should return same results
        assert len(added1) == len(added2)
        assert len(modified1) == len(modified2)
        assert added1[0].label == added2[0].label
