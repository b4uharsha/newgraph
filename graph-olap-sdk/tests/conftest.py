"""Pytest fixtures for Graph OLAP SDK tests."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
import respx

from graph_olap import GraphOLAPClient
from graph_olap.http import HTTPClient


@pytest.fixture
def api_url() -> str:
    """Base API URL for tests."""
    return "https://api.test.example.com"


@pytest.fixture
def username() -> str:
    """Username for tests."""
    return "test-user@example.com"


@pytest.fixture
def mock_api(api_url: str) -> Generator[respx.MockRouter, None, None]:
    """Mock API router."""
    with respx.mock(base_url=api_url) as router:
        yield router


@pytest.fixture
def http_client(api_url: str, username: str) -> Generator[HTTPClient, None, None]:
    """HTTP client for tests."""
    client = HTTPClient(base_url=api_url, username=username)
    yield client
    client.close()


@pytest.fixture
def client(api_url: str, username: str) -> Generator[GraphOLAPClient, None, None]:
    """Graph OLAP client for tests."""
    client = GraphOLAPClient(api_url=api_url, username=username)
    yield client
    client.close()


# =============================================================================
# Sample Response Data
# =============================================================================


@pytest.fixture
def sample_mapping_data() -> dict[str, Any]:
    """Sample mapping response data."""
    return {
        "id": 1,
        "owner_username": "test_user",
        "name": "Customer Graph",
        "description": "Customer and order relationships",
        "current_version": 1,
        "created_at": "2025-01-15T10:30:00Z",
        "updated_at": "2025-01-15T10:30:00Z",
        "ttl": None,
        "inactivity_timeout": None,
        "snapshot_count": 2,
        "version": {
            "mapping_id": 1,
            "version": 1,
            "change_description": "Initial version",
            "node_definitions": [
                {
                    "label": "Customer",
                    "sql": "SELECT * FROM customers",
                    "primary_key": {"name": "id", "type": "STRING"},
                    "properties": [
                        {"name": "name", "type": "STRING"},
                        {"name": "age", "type": "INT64"},
                    ],
                }
            ],
            "edge_definitions": [
                {
                    "type": "PURCHASED",
                    "from_node": "Customer",
                    "to_node": "Product",
                    "sql": "SELECT * FROM orders",
                    "from_key": "customer_id",
                    "to_key": "product_id",
                    "properties": [{"name": "amount", "type": "DOUBLE"}],
                }
            ],
            "created_at": "2025-01-15T10:30:00Z",
            "created_by": "user-123",
            "created_by_name": "Test User",
        },
    }


@pytest.fixture
def sample_snapshot_data() -> dict[str, Any]:
    """Sample snapshot response data."""
    return {
        "id": 1,
        "mapping_id": 1,
        "mapping_name": "Customer Graph",
        "mapping_version": 1,
        "owner_username": "test_user",
        "name": "Analysis Snapshot",
        "description": "For analysis",
        "gcs_path": "gs://bucket/snapshots/1",
        "size_bytes": 1024 * 1024 * 100,  # 100 MB
        "node_counts": {"Customer": 10000, "Product": 5000},
        "edge_counts": {"PURCHASED": 50000},
        "status": "ready",
        "error_message": None,
        "created_at": "2025-01-15T10:30:00Z",
        "updated_at": "2025-01-15T10:35:00Z",
        "ttl": "P7D",
        "inactivity_timeout": "PT24H",
        "instance_count": 1,
    }


@pytest.fixture
def sample_instance_data() -> dict[str, Any]:
    """Sample instance response data."""
    return {
        "id": 1,
        "snapshot_id": 1,
        "snapshot_name": "Analysis Snapshot",
        "owner_username": "test_user",
        "wrapper_type": "ryugraph",
        "name": "Analysis Instance",
        "description": "For analysis",
        "instance_url": "https://instance-1.example.com",
        "explorer_url": "https://instance-1.example.com/explorer",
        "status": "running",
        "error_message": None,
        "created_at": "2025-01-15T10:30:00Z",
        "updated_at": "2025-01-15T10:35:00Z",
        "started_at": "2025-01-15T10:35:00Z",
        "last_activity_at": "2025-01-15T11:00:00Z",
        "ttl": "PT24H",
        "inactivity_timeout": "PT8H",
        "memory_usage_bytes": 512 * 1024 * 1024,  # 512 MB
        "disk_usage_bytes": 1024 * 1024 * 1024,  # 1 GB
    }


@pytest.fixture
def sample_query_result_data() -> dict[str, Any]:
    """Sample query result response data."""
    return {
        "columns": ["name", "age", "city"],
        "column_types": ["STRING", "INT64", "STRING"],
        "rows": [
            ["Alice", 30, "London"],
            ["Bob", 25, "Paris"],
            ["Charlie", 35, "Berlin"],
        ],
        "row_count": 3,
        "execution_time_ms": 42,
    }


@pytest.fixture
def sample_paginated_response() -> dict[str, Any]:
    """Sample paginated response structure."""
    return {
        "data": [],
        "meta": {
            "total": 100,
            "offset": 0,
            "limit": 50,
        },
    }


@pytest.fixture
def sample_diff_data() -> dict[str, Any]:
    """Sample mapping diff response data."""
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
                    "fields_changed": ["sql", "properties"],
                    "from": {
                        "sql": "SELECT id FROM customers",
                        "properties": [],
                    },
                    "to": {
                        "sql": "SELECT id, name FROM customers",
                        "properties": [{"name": "name", "type": "STRING"}],
                    },
                },
                {
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


@pytest.fixture
def empty_diff_data() -> dict[str, Any]:
    """Sample diff with no changes."""
    return {
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
