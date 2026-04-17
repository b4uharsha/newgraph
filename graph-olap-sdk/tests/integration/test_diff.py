"""Integration tests for mapping diff functionality.

Tests the full flow of calling the diff endpoint through the SDK client,
including HTTP request construction, response parsing, and error handling.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from respx import MockRouter

from graph_olap import GraphOLAPClient
from graph_olap.exceptions import GraphOLAPError, NotFoundError
from graph_olap.models.mapping import MappingDiff


class TestMappingDiff:
    """Integration tests for MappingResource.diff() method."""

    @pytest.fixture
    def sample_diff_response(self) -> dict[str, Any]:
        """Sample diff API response."""
        return {
            "data": {
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
                            "to": {
                                "label": "Supplier",
                                "sql": "SELECT * FROM suppliers",
                            },
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
        }

    def test_diff_makes_correct_request(
        self, client: GraphOLAPClient, mock_api: MockRouter, sample_diff_response: dict
    ):
        """Test that diff() makes correct HTTP request."""
        # Mock the diff endpoint
        route = mock_api.get(
            "/api/mappings/1/versions/1/diff/2"
        ).mock(return_value=httpx.Response(200, json=sample_diff_response))

        # Call diff
        diff = client.mappings.diff(mapping_id=1, from_version=1, to_version=2)

        # Verify request was made
        assert route.called
        assert route.call_count == 1

        # Verify response was parsed correctly
        assert isinstance(diff, MappingDiff)
        assert diff.mapping_id == 1
        assert diff.from_version == 1
        assert diff.to_version == 2

    def test_diff_parses_response_correctly(
        self, client: GraphOLAPClient, mock_api: MockRouter, sample_diff_response: dict
    ):
        """Test that diff response is parsed into MappingDiff object."""
        mock_api.get("/api/mappings/1/versions/1/diff/2").mock(
            return_value=httpx.Response(200, json=sample_diff_response)
        )

        diff = client.mappings.diff(mapping_id=1, from_version=1, to_version=2)

        # Check summary
        assert diff.summary["nodes_added"] == 1
        assert diff.summary["nodes_modified"] == 1
        assert diff.summary["edges_modified"] == 1

        # Check changes
        assert len(diff.changes["nodes"]) == 2
        assert len(diff.changes["edges"]) == 1

    def test_diff_helper_methods_work(
        self, client: GraphOLAPClient, mock_api: MockRouter, sample_diff_response: dict
    ):
        """Test that helper methods work on returned diff."""
        mock_api.get("/api/mappings/1/versions/1/diff/2").mock(
            return_value=httpx.Response(200, json=sample_diff_response)
        )

        diff = client.mappings.diff(mapping_id=1, from_version=1, to_version=2)

        # Test filter methods
        added = diff.nodes_added()
        assert len(added) == 1
        assert added[0].label == "Supplier"

        modified = diff.nodes_modified()
        assert len(modified) == 1
        assert modified[0].label == "Customer"

        edge_modified = diff.edges_modified()
        assert len(edge_modified) == 1
        assert edge_modified[0].type == "PURCHASED"

    def test_diff_empty_changes(
        self, client: GraphOLAPClient, mock_api: MockRouter
    ):
        """Test diff with no changes."""
        empty_diff_response = {
            "data": {
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
        }

        mock_api.get("/api/mappings/1/versions/1/diff/2").mock(
            return_value=httpx.Response(200, json=empty_diff_response)
        )

        diff = client.mappings.diff(mapping_id=1, from_version=1, to_version=2)

        assert diff.summary["nodes_added"] == 0
        assert len(diff.nodes_added()) == 0
        assert len(diff.edges_added()) == 0

    def test_diff_version_not_found(
        self, client: GraphOLAPClient, mock_api: MockRouter
    ):
        """Test diff when version doesn't exist."""
        error_response = {
            "error": {
                "message": "Version 999 not found",
                "code": "not_found",
            }
        }

        mock_api.get("/api/mappings/1/versions/1/diff/999").mock(
            return_value=httpx.Response(404, json=error_response)
        )

        with pytest.raises(NotFoundError) as exc_info:
            client.mappings.diff(mapping_id=1, from_version=1, to_version=999)

        assert "not found" in str(exc_info.value).lower()

    def test_diff_mapping_not_found(
        self, client: GraphOLAPClient, mock_api: MockRouter
    ):
        """Test diff when mapping doesn't exist."""
        error_response = {
            "error": {
                "message": "Mapping not found",
                "code": "not_found",
            }
        }

        mock_api.get("/api/mappings/9999/versions/1/diff/2").mock(
            return_value=httpx.Response(404, json=error_response)
        )

        with pytest.raises(NotFoundError):
            client.mappings.diff(mapping_id=9999, from_version=1, to_version=2)

    def test_diff_same_version_error(
        self, client: GraphOLAPClient, mock_api: MockRouter
    ):
        """Test diff when from_version == to_version."""
        error_response = {
            "error": {
                "message": "Cannot diff a version with itself",
                "code": "validation_error",
            }
        }

        mock_api.get("/api/mappings/1/versions/1/diff/1").mock(
            return_value=httpx.Response(400, json=error_response)
        )

        with pytest.raises(GraphOLAPError) as exc_info:
            client.mappings.diff(mapping_id=1, from_version=1, to_version=1)

        assert "itself" in str(exc_info.value).lower()

    def test_diff_with_large_version_numbers(
        self, client: GraphOLAPClient, mock_api: MockRouter
    ):
        """Test diff with large version numbers."""
        diff_response = {
            "data": {
                "mapping_id": 1,
                "from_version": 100,
                "to_version": 150,
                "summary": {
                    "nodes_added": 5,
                    "nodes_removed": 2,
                    "nodes_modified": 3,
                    "edges_added": 0,
                    "edges_removed": 0,
                    "edges_modified": 0,
                },
                "changes": {"nodes": [], "edges": []},
            }
        }

        mock_api.get("/api/mappings/1/versions/100/diff/150").mock(
            return_value=httpx.Response(200, json=diff_response)
        )

        diff = client.mappings.diff(mapping_id=1, from_version=100, to_version=150)

        assert diff.from_version == 100
        assert diff.to_version == 150

    def test_diff_with_many_changes(
        self, client: GraphOLAPClient, mock_api: MockRouter
    ):
        """Test diff with many nodes and edges changed."""
        many_nodes = [
            {
                "label": f"Node{i}",
                "change_type": "added",
                "fields_changed": None,
                "from": None,
                "to": {"label": f"Node{i}"},
            }
            for i in range(50)
        ]

        many_edges = [
            {
                "type": f"EDGE{i}",
                "change_type": "added",
                "fields_changed": None,
                "from": None,
                "to": {"type": f"EDGE{i}"},
            }
            for i in range(100)
        ]

        diff_response = {
            "data": {
                "mapping_id": 1,
                "from_version": 1,
                "to_version": 2,
                "summary": {
                    "nodes_added": 50,
                    "nodes_removed": 0,
                    "nodes_modified": 0,
                    "edges_added": 100,
                    "edges_removed": 0,
                    "edges_modified": 0,
                },
                "changes": {"nodes": many_nodes, "edges": many_edges},
            }
        }

        mock_api.get("/api/mappings/1/versions/1/diff/2").mock(
            return_value=httpx.Response(200, json=diff_response)
        )

        diff = client.mappings.diff(mapping_id=1, from_version=1, to_version=2)

        assert len(diff.nodes_added()) == 50
        assert len(diff.edges_added()) == 100

    def test_diff_url_construction(
        self, client: GraphOLAPClient, mock_api: MockRouter
    ):
        """Test that diff URL is constructed correctly with different IDs."""
        diff_response = {
            "data": {
                "mapping_id": 42,
                "from_version": 7,
                "to_version": 13,
                "summary": {},
                "changes": {"nodes": [], "edges": []},
            }
        }

        route = mock_api.get("/api/mappings/42/versions/7/diff/13").mock(
            return_value=httpx.Response(200, json=diff_response)
        )

        diff = client.mappings.diff(mapping_id=42, from_version=7, to_version=13)

        assert route.called
        assert diff.mapping_id == 42
        assert diff.from_version == 7
        assert diff.to_version == 13

    def test_diff_with_complex_field_changes(
        self, client: GraphOLAPClient, mock_api: MockRouter
    ):
        """Test diff with multiple fields changed on same node."""
        diff_response = {
            "data": {
                "mapping_id": 1,
                "from_version": 1,
                "to_version": 2,
                "summary": {
                    "nodes_added": 0,
                    "nodes_removed": 0,
                    "nodes_modified": 1,
                    "edges_added": 0,
                    "edges_removed": 0,
                    "edges_modified": 0,
                },
                "changes": {
                    "nodes": [
                        {
                            "label": "Customer",
                            "change_type": "modified",
                            "fields_changed": ["sql", "properties", "primary_key"],
                            "from": {
                                "sql": "SELECT id FROM customers",
                                "properties": [],
                                "primary_key": {"name": "id", "type": "INT64"},
                            },
                            "to": {
                                "sql": "SELECT customer_id, name FROM customers",
                                "properties": [{"name": "name", "type": "STRING"}],
                                "primary_key": {"name": "customer_id", "type": "STRING"},
                            },
                        }
                    ],
                    "edges": [],
                },
            }
        }

        mock_api.get("/api/mappings/1/versions/1/diff/2").mock(
            return_value=httpx.Response(200, json=diff_response)
        )

        diff = client.mappings.diff(mapping_id=1, from_version=1, to_version=2)

        modified = diff.nodes_modified()
        assert len(modified) == 1
        assert set(modified[0].fields_changed) == {"sql", "properties", "primary_key"}
