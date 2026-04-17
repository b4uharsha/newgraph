"""Unit tests for the schema router.

Tests cover:
- GET /schema endpoint
- Schema response structure
- Empty graph handling
- Property type conversion
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from wrapper.routers import schema


@pytest.fixture
def mock_db_with_schema():
    """Create a mock DatabaseService with schema data."""
    service = MagicMock()
    service.is_ready = True
    service.get_schema = AsyncMock(
        return_value={
            "node_labels": ["Person", "Company"],
            "edge_types": ["KNOWS", "WORKS_AT"],
            "node_properties": {
                "Person": ["name", "age"],
                "Company": ["name", "founded"],
            },
            "edge_properties": {
                "KNOWS": ["since"],
                "WORKS_AT": ["role"],
            },
            "node_counts": {"Person": 100, "Company": 50},
            "edge_counts": {"KNOWS": 200, "WORKS_AT": 100},
        }
    )
    return service


@pytest.fixture
def mock_db_empty_schema():
    """Create a mock DatabaseService with empty schema."""
    service = MagicMock()
    service.is_ready = True
    service.get_schema = AsyncMock(
        return_value={
            "node_labels": [],
            "edge_types": [],
            "node_properties": {},
            "edge_properties": {},
            "node_counts": {},
            "edge_counts": {},
        }
    )
    return service


@pytest.fixture
def app_with_schema(mock_db_with_schema):
    """Create a FastAPI app with mock database service."""
    app = FastAPI()
    app.include_router(schema.router)
    app.state.db_service = mock_db_with_schema
    return app


@pytest.fixture
def app_with_empty_schema(mock_db_empty_schema):
    """Create a FastAPI app with empty schema."""
    app = FastAPI()
    app.include_router(schema.router)
    app.state.db_service = mock_db_empty_schema
    return app


class TestGetSchema:
    """Tests for GET /schema endpoint."""

    def test_get_schema_success(self, app_with_schema):
        """GET /schema returns schema successfully."""
        client = TestClient(app_with_schema)

        response = client.get("/schema")

        assert response.status_code == 200
        data = response.json()
        assert "node_tables" in data
        assert "edge_tables" in data
        assert "total_nodes" in data
        assert "total_edges" in data

    def test_get_schema_node_tables_structure(self, app_with_schema):
        """GET /schema returns correct node table structure."""
        client = TestClient(app_with_schema)

        response = client.get("/schema")
        data = response.json()

        assert len(data["node_tables"]) == 2

        # Find Person node table
        person_table = next(
            (t for t in data["node_tables"] if t["label"] == "Person"),
            None,
        )
        assert person_table is not None
        assert person_table["primary_key"] == "id"
        assert person_table["primary_key_type"] == "INTEGER"
        assert person_table["node_count"] == 100
        assert "name" in person_table["properties"]
        assert "age" in person_table["properties"]

    def test_get_schema_edge_tables_structure(self, app_with_schema):
        """GET /schema returns correct edge table structure."""
        client = TestClient(app_with_schema)

        response = client.get("/schema")
        data = response.json()

        assert len(data["edge_tables"]) == 2

        # Find KNOWS edge table
        knows_table = next(
            (t for t in data["edge_tables"] if t["type"] == "KNOWS"),
            None,
        )
        assert knows_table is not None
        assert knows_table["from_node"] == "*"
        assert knows_table["to_node"] == "*"
        assert knows_table["edge_count"] == 200
        assert "since" in knows_table["properties"]

    def test_get_schema_total_counts(self, app_with_schema):
        """GET /schema returns correct total counts."""
        client = TestClient(app_with_schema)

        response = client.get("/schema")
        data = response.json()

        # Person: 100 + Company: 50 = 150
        assert data["total_nodes"] == 150
        # KNOWS: 200 + WORKS_AT: 100 = 300
        assert data["total_edges"] == 300

    def test_get_schema_empty_graph(self, app_with_empty_schema):
        """GET /schema handles empty graph correctly."""
        client = TestClient(app_with_empty_schema)

        response = client.get("/schema")

        assert response.status_code == 200
        data = response.json()
        assert data["node_tables"] == []
        assert data["edge_tables"] == []
        assert data["total_nodes"] == 0
        assert data["total_edges"] == 0

    def test_get_schema_property_conversion(self, app_with_schema):
        """GET /schema converts property lists to dicts with STRING type."""
        client = TestClient(app_with_schema)

        response = client.get("/schema")
        data = response.json()

        person_table = next(
            (t for t in data["node_tables"] if t["label"] == "Person"),
            None,
        )
        assert person_table is not None

        # Properties should be dict with STRING as default type
        assert person_table["properties"]["name"] == "STRING"
        assert person_table["properties"]["age"] == "STRING"


class TestSchemaEndpointServiceNotInitialized:
    """Tests for when database service is not initialized."""

    def test_returns_503_when_service_not_initialized(self):
        """GET /schema returns 503 when database service not in app state."""
        app = FastAPI()
        app.include_router(schema.router)
        # Don't set app.state.db_service

        client = TestClient(app)
        response = client.get("/schema")

        assert response.status_code == 503
        assert "not initialized" in response.json()["detail"].lower()


class TestSchemaWithDictProperties:
    """Tests for schema with dict-format properties (already typed)."""

    def test_get_schema_with_dict_properties(self):
        """GET /schema handles dict properties correctly (no conversion needed)."""
        mock_service = MagicMock()
        mock_service.is_ready = True
        mock_service.get_schema = AsyncMock(
            return_value={
                "node_labels": ["Node"],
                "edge_types": [],
                "node_properties": {
                    "Node": {"id": "INTEGER", "name": "STRING", "value": "DOUBLE"},
                },
                "edge_properties": {},
                "node_counts": {"Node": 10},
                "edge_counts": {},
            }
        )

        app = FastAPI()
        app.include_router(schema.router)
        app.state.db_service = mock_service

        client = TestClient(app)
        response = client.get("/schema")

        assert response.status_code == 200
        data = response.json()

        node_table = data["node_tables"][0]
        # Dict properties should be preserved
        assert node_table["properties"]["id"] == "INTEGER"
        assert node_table["properties"]["name"] == "STRING"
        assert node_table["properties"]["value"] == "DOUBLE"
