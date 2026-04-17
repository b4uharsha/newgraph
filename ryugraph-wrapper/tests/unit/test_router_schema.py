"""Tests for schema router endpoints."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from wrapper.exceptions import DatabaseError
from wrapper.routers.schema import get_schema


class TestGetSchema:
    """Tests for /schema endpoint."""

    @pytest.mark.asyncio
    async def test_get_schema_success(self):
        """Test successful schema retrieval."""
        mock_db = MagicMock()
        mock_db.is_ready = True
        mock_db.get_schema = AsyncMock(
            return_value={
                "node_tables": [
                    {
                        "label": "Person",
                        "primary_key": "id",
                        "primary_key_type": "INT64",
                        "properties": {"name": "STRING", "age": "INT64"},
                        "node_count": 1000,
                    },
                    {
                        "label": "Company",
                        "primary_key": "company_id",
                        "primary_key_type": "STRING",
                        "properties": {"name": "STRING", "industry": "STRING"},
                        "node_count": 500,
                    },
                ],
                "edge_tables": [
                    {
                        "type": "WORKS_AT",
                        "from_node": "Person",
                        "to_node": "Company",
                        "properties": {"since": "DATE", "role": "STRING"},
                        "edge_count": 800,
                    },
                ],
                "total_nodes": 1500,
                "total_edges": 800,
            }
        )

        response = await get_schema(db_service=mock_db)

        assert len(response.node_tables) == 2
        assert len(response.edge_tables) == 1

        # Check Person node table
        person = response.node_tables[0]
        assert person.label == "Person"
        assert person.primary_key == "id"
        assert person.primary_key_type == "INT64"
        assert person.properties == {"name": "STRING", "age": "INT64"}
        assert person.node_count == 1000

        # Check Company node table
        company = response.node_tables[1]
        assert company.label == "Company"
        assert company.node_count == 500

        # Check WORKS_AT edge table
        works_at = response.edge_tables[0]
        assert works_at.type == "WORKS_AT"
        assert works_at.from_node == "Person"
        assert works_at.to_node == "Company"
        assert works_at.edge_count == 800

        # Check totals
        assert response.total_nodes == 1500
        assert response.total_edges == 800

    @pytest.mark.asyncio
    async def test_get_schema_empty_graph(self):
        """Test schema retrieval for empty graph."""
        mock_db = MagicMock()
        mock_db.is_ready = True
        mock_db.get_schema = AsyncMock(
            return_value={
                "node_tables": [],
                "edge_tables": [],
                "total_nodes": 0,
                "total_edges": 0,
            }
        )

        response = await get_schema(db_service=mock_db)

        assert len(response.node_tables) == 0
        assert len(response.edge_tables) == 0
        assert response.total_nodes == 0
        assert response.total_edges == 0

    @pytest.mark.asyncio
    async def test_get_schema_database_not_ready(self):
        """Test schema retrieval when database not ready."""
        mock_db = MagicMock()
        mock_db.is_ready = False

        with pytest.raises(HTTPException) as exc_info:
            await get_schema(db_service=mock_db)

        assert exc_info.value.status_code == 503
        assert "not ready" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_schema_database_error(self):
        """Test schema retrieval with database error."""
        mock_db = MagicMock()
        mock_db.is_ready = True
        mock_db.get_schema = AsyncMock(
            side_effect=DatabaseError("Failed to query schema tables")
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_schema(db_service=mock_db)

        assert exc_info.value.status_code == 500
        assert "Failed to query schema tables" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_schema_with_defaults(self):
        """Test schema retrieval with missing optional fields."""
        mock_db = MagicMock()
        mock_db.is_ready = True
        mock_db.get_schema = AsyncMock(
            return_value={
                "node_tables": [
                    {
                        "label": "Person",
                        # Missing primary_key, primary_key_type, properties, node_count
                    },
                ],
                "edge_tables": [
                    {
                        "type": "KNOWS",
                        # Missing from_node, to_node, properties, edge_count
                    },
                ],
                # Missing total_nodes, total_edges
            }
        )

        response = await get_schema(db_service=mock_db)

        # Should use defaults
        person = response.node_tables[0]
        assert person.label == "Person"
        assert person.primary_key == ""
        assert person.primary_key_type == "STRING"
        assert person.properties == {}
        assert person.node_count == 0

        knows = response.edge_tables[0]
        assert knows.type == "KNOWS"
        assert knows.from_node == ""
        assert knows.to_node == ""
        assert knows.properties == {}
        assert knows.edge_count == 0

        assert response.total_nodes == 0
        assert response.total_edges == 0

    @pytest.mark.asyncio
    async def test_get_schema_complex_properties(self):
        """Test schema with complex property types."""
        mock_db = MagicMock()
        mock_db.is_ready = True
        mock_db.get_schema = AsyncMock(
            return_value={
                "node_tables": [
                    {
                        "label": "Event",
                        "primary_key": "event_id",
                        "primary_key_type": "STRING",
                        "properties": {
                            "name": "STRING",
                            "timestamp": "TIMESTAMP",
                            "location": "GEOMETRY",
                            "metadata": "JSON",
                            "tags": "ARRAY<STRING>",
                        },
                        "node_count": 250,
                    },
                ],
                "edge_tables": [],
                "total_nodes": 250,
                "total_edges": 0,
            }
        )

        response = await get_schema(db_service=mock_db)

        event = response.node_tables[0]
        assert event.properties["timestamp"] == "TIMESTAMP"
        assert event.properties["location"] == "GEOMETRY"
        assert event.properties["metadata"] == "JSON"
        assert event.properties["tags"] == "ARRAY<STRING>"
