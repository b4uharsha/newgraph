"""Shared test fixtures for unit, integration, and e2e tests.

This is the root conftest.py that provides:
1. Auto-marker application based on test directory
2. Shared sample data fixtures
3. Environment setup for all tests

Mock fixtures for unit tests are in tests/unit/conftest.py.
Integration fixtures are in tests/integration/conftest.py.
E2E fixtures are in tests/e2e/conftest.py.
"""

from __future__ import annotations

from typing import Any

import pytest

# =============================================================================
# Auto-Marker Application
# =============================================================================


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Auto-apply markers based on test directory.

    This eliminates the need for manual @pytest.mark.unit decorators.
    Tests in tests/unit/ get the 'unit' marker automatically, etc.
    """
    for item in items:
        test_path = str(item.fspath)
        if "/unit/" in test_path:
            item.add_marker(pytest.mark.unit)
        elif "/integration/" in test_path:
            item.add_marker(pytest.mark.integration)
        elif "/e2e/" in test_path:
            item.add_marker(pytest.mark.e2e)


# =============================================================================
# Environment Setup (Auto-applied to ALL tests)
# =============================================================================


@pytest.fixture(autouse=True)
def mock_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set required environment variables for all tests.

    This fixture runs automatically for every test, ensuring that
    Settings can be loaded without requiring real environment variables.
    """
    env_vars = {
        "WRAPPER_INSTANCE_ID": "test-instance-id",
        "WRAPPER_SNAPSHOT_ID": "test-snapshot-123",
        "WRAPPER_MAPPING_ID": "test-mapping-id",
        "WRAPPER_OWNER_ID": "test-owner-id",
        "WRAPPER_OWNER_USERNAME": "testuser",
        "WRAPPER_CONTROL_PLANE_URL": "http://localhost:8080",
        "WRAPPER_GCS_BASE_PATH": "gs://test-bucket/user/mapping/snapshot",
        "WRAPPER_INTERNAL_API_KEY": "test-api-key",
        "FALKORDB_DATABASE_PATH": "/tmp/test_falkordb",
        "FALKORDB_QUERY_TIMEOUT_MS": "60000",
        "LOG_LEVEL": "DEBUG",
        "LOG_FORMAT": "human",
        "ENVIRONMENT": "local",
    }
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)


# =============================================================================
# Sample Data Fixtures
# =============================================================================


@pytest.fixture
def sample_node_definition() -> dict[str, Any]:
    """Sample node definition."""
    return {
        "label": "Customer",
        "sql": "SELECT customer_id, name, city FROM customers",
        "primary_key": {"name": "customer_id", "type": "STRING"},
        "properties": [
            {"name": "name", "type": "STRING"},
            {"name": "city", "type": "STRING"},
        ],
    }


@pytest.fixture
def sample_edge_definition() -> dict[str, Any]:
    """Sample edge definition."""
    return {
        "type": "PURCHASED",
        "from_node": "Customer",
        "to_node": "Product",
        "sql": "SELECT customer_id, product_id, amount FROM transactions",
        "from_key": "customer_id",
        "to_key": "product_id",
        "properties": [{"name": "amount", "type": "DOUBLE"}],
    }


@pytest.fixture
def sample_mapping_definition(
    sample_node_definition: dict[str, Any],
    sample_edge_definition: dict[str, Any],
) -> dict[str, Any]:
    """Sample complete mapping definition."""
    product_node = {
        "label": "Product",
        "sql": "SELECT product_id, name, price FROM products",
        "primary_key": {"name": "product_id", "type": "STRING"},
        "properties": [
            {"name": "name", "type": "STRING"},
            {"name": "price", "type": "DOUBLE"},
        ],
    }
    return {
        "mapping_id": "test-mapping-id",
        "mapping_version": 1,
        "node_definitions": [sample_node_definition, product_node],
        "edge_definitions": [sample_edge_definition],
    }


# =============================================================================
# Schema Fixtures
# =============================================================================


@pytest.fixture
def sample_schema_response() -> dict[str, Any]:
    """Sample schema data returned by DatabaseService.get_schema()."""
    return {
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


@pytest.fixture
def empty_schema_response() -> dict[str, Any]:
    """Empty schema for testing edge cases."""
    return {
        "node_labels": [],
        "edge_types": [],
        "node_properties": {},
        "edge_properties": {},
        "node_counts": {},
        "edge_counts": {},
    }


# =============================================================================
# Lock State Fixtures
# =============================================================================


@pytest.fixture
def sample_lock_state() -> dict[str, Any]:
    """Sample lock state for testing."""
    from datetime import UTC, datetime

    return {
        "execution_id": "exec-12345",
        "holder_id": "user-001",
        "holder_username": "testuser",
        "algorithm_name": "pagerank",
        "algorithm_type": "cypher",
        "acquired_at": datetime.now(UTC),
    }


# =============================================================================
# Control Plane Response Fixtures
# =============================================================================


@pytest.fixture
def sample_mapping_response() -> dict[str, Any]:
    """Sample response from Control Plane /mapping endpoint."""
    return {
        "mapping_id": "test-mapping-123",
        "mapping_version": 1,
        "id": 1,
        "name": "test-mapping",
        "gcs_path": "gs://test-bucket/mappings/test-mapping-123",
        "node_definitions": [
            {
                "label": "Person",
                "sql": "SELECT person_id, name, age FROM people",
                "primary_key": {"name": "person_id", "type": "STRING"},
                "properties": [
                    {"name": "name", "type": "STRING"},
                    {"name": "age", "type": "INT64"},
                ],
            },
        ],
        "edge_definitions": [
            {
                "type": "KNOWS",
                "from_node": "Person",
                "to_node": "Person",
                "sql": "SELECT from_id, to_id, since FROM relationships",
                "from_key": "from_id",
                "to_key": "to_id",
                "properties": [{"name": "since", "type": "INT64"}],
            },
        ],
    }
