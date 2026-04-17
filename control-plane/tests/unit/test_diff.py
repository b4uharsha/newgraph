"""Unit tests for mapping version diff logic."""

from datetime import UTC, datetime

import pytest

from control_plane.models.domain import (
    EdgeDefinition,
    MappingVersion,
    NodeDefinition,
    PrimaryKeyDefinition,
    PropertyDefinition,
)
from control_plane.utils.diff import diff_mapping_versions


@pytest.fixture
def base_mapping_version() -> MappingVersion:
    """Create a base mapping version for testing."""
    return MappingVersion(
        mapping_id=1,
        version=1,
        node_definitions=[
            NodeDefinition(
                label="Customer",
                sql="SELECT customer_id, name FROM analytics.customers",
                primary_key=PrimaryKeyDefinition(name="customer_id", type="STRING"),
                properties=[PropertyDefinition(name="name", type="STRING")],
            ),
            NodeDefinition(
                label="Product",
                sql="SELECT product_id, title FROM analytics.products",
                primary_key=PrimaryKeyDefinition(name="product_id", type="STRING"),
                properties=[PropertyDefinition(name="title", type="STRING")],
            ),
        ],
        edge_definitions=[
            EdgeDefinition(
                type="PURCHASED",
                from_node="Customer",
                to_node="Product",
                sql="SELECT customer_id, product_id, amount FROM analytics.transactions",
                from_key="customer_id",
                to_key="product_id",
                properties=[PropertyDefinition(name="amount", type="DOUBLE")],
            ),
        ],
        change_description=None,
        created_at=datetime.now(UTC),
        created_by="test_user",
    )


def test_diff_no_changes(base_mapping_version):
    """Test diff between identical versions produces empty result."""
    v2 = MappingVersion(
        mapping_id=base_mapping_version.mapping_id,
        version=2,
        node_definitions=base_mapping_version.node_definitions,
        edge_definitions=base_mapping_version.edge_definitions,
        change_description="No changes",
        created_at=datetime.now(UTC),
        created_by="test_user",
    )

    result = diff_mapping_versions(base_mapping_version, v2)

    assert result.nodes_added == 0
    assert result.nodes_removed == 0
    assert result.nodes_modified == 0
    assert result.edges_added == 0
    assert result.edges_removed == 0
    assert result.edges_modified == 0
    assert len(result.node_diffs) == 0
    assert len(result.edge_diffs) == 0


def test_diff_node_added(base_mapping_version):
    """Test diff when a node is added in v2."""
    v2 = MappingVersion(
        mapping_id=base_mapping_version.mapping_id,
        version=2,
        node_definitions=[
            *base_mapping_version.node_definitions,
            NodeDefinition(
                label="Supplier",
                sql="SELECT supplier_id, name FROM analytics.suppliers",
                primary_key=PrimaryKeyDefinition(name="supplier_id", type="STRING"),
                properties=[PropertyDefinition(name="name", type="STRING")],
            ),
        ],
        edge_definitions=base_mapping_version.edge_definitions,
        change_description="Added Supplier node",
        created_at=datetime.now(UTC),
        created_by="test_user",
    )

    result = diff_mapping_versions(base_mapping_version, v2)

    assert result.nodes_added == 1
    assert result.nodes_removed == 0
    assert result.nodes_modified == 0
    assert len(result.node_diffs) == 1

    added_node = result.node_diffs[0]
    assert added_node.label == "Supplier"
    assert added_node.change_type == "added"
    assert added_node.fields_changed is None
    assert added_node.from_def is None
    assert added_node.to_def is not None
    assert added_node.to_def["label"] == "Supplier"


def test_diff_node_removed(base_mapping_version):
    """Test diff when a node is removed in v2."""
    v2 = MappingVersion(
        mapping_id=base_mapping_version.mapping_id,
        version=2,
        node_definitions=[
            base_mapping_version.node_definitions[0]  # Keep only Customer
        ],
        edge_definitions=[],  # Remove edge that references Product
        change_description="Removed Product node",
        created_at=datetime.now(UTC),
        created_by="test_user",
    )

    result = diff_mapping_versions(base_mapping_version, v2)

    assert result.nodes_added == 0
    assert result.nodes_removed == 1
    assert result.nodes_modified == 0
    assert len(result.node_diffs) == 1

    removed_node = result.node_diffs[0]
    assert removed_node.label == "Product"
    assert removed_node.change_type == "removed"
    assert removed_node.fields_changed is None
    assert removed_node.from_def is not None
    assert removed_node.to_def is None
    assert removed_node.from_def["label"] == "Product"


def test_diff_node_modified_sql(base_mapping_version):
    """Test diff when a node's SQL changes."""
    v2 = MappingVersion(
        mapping_id=base_mapping_version.mapping_id,
        version=2,
        node_definitions=[
            NodeDefinition(
                label="Customer",
                sql="SELECT customer_id, name, city FROM analytics.customers",  # Added city
                primary_key=PrimaryKeyDefinition(name="customer_id", type="STRING"),
                properties=[PropertyDefinition(name="name", type="STRING")],
            ),
            base_mapping_version.node_definitions[1],  # Product unchanged
        ],
        edge_definitions=base_mapping_version.edge_definitions,
        change_description="Updated Customer SQL",
        created_at=datetime.now(UTC),
        created_by="test_user",
    )

    result = diff_mapping_versions(base_mapping_version, v2)

    assert result.nodes_added == 0
    assert result.nodes_removed == 0
    assert result.nodes_modified == 1
    assert len(result.node_diffs) == 1

    modified_node = result.node_diffs[0]
    assert modified_node.label == "Customer"
    assert modified_node.change_type == "modified"
    assert "sql" in modified_node.fields_changed
    assert modified_node.from_def is not None
    assert modified_node.to_def is not None
    assert "city" not in modified_node.from_def["sql"]
    assert "city" in modified_node.to_def["sql"]


def test_diff_node_modified_properties(base_mapping_version):
    """Test diff when a node's properties change."""
    v2 = MappingVersion(
        mapping_id=base_mapping_version.mapping_id,
        version=2,
        node_definitions=[
            NodeDefinition(
                label="Customer",
                sql=base_mapping_version.node_definitions[0].sql,
                primary_key=base_mapping_version.node_definitions[0].primary_key,
                properties=[
                    PropertyDefinition(name="name", type="STRING"),
                    PropertyDefinition(name="city", type="STRING"),  # Added property
                ],
            ),
            base_mapping_version.node_definitions[1],  # Product unchanged
        ],
        edge_definitions=base_mapping_version.edge_definitions,
        change_description="Added city property to Customer",
        created_at=datetime.now(UTC),
        created_by="test_user",
    )

    result = diff_mapping_versions(base_mapping_version, v2)

    assert result.nodes_added == 0
    assert result.nodes_removed == 0
    assert result.nodes_modified == 1

    modified_node = result.node_diffs[0]
    assert modified_node.label == "Customer"
    assert "properties" in modified_node.fields_changed
    assert len(modified_node.from_def["properties"]) == 1
    assert len(modified_node.to_def["properties"]) == 2


def test_diff_edge_added(base_mapping_version):
    """Test diff when an edge is added."""
    v2 = MappingVersion(
        mapping_id=base_mapping_version.mapping_id,
        version=2,
        node_definitions=base_mapping_version.node_definitions,
        edge_definitions=[
            *base_mapping_version.edge_definitions,
            EdgeDefinition(
                type="REVIEWED",
                from_node="Customer",
                to_node="Product",
                sql="SELECT customer_id, product_id, rating FROM analytics.reviews",
                from_key="customer_id",
                to_key="product_id",
                properties=[PropertyDefinition(name="rating", type="INT32")],
            ),
        ],
        change_description="Added REVIEWED edge",
        created_at=datetime.now(UTC),
        created_by="test_user",
    )

    result = diff_mapping_versions(base_mapping_version, v2)

    assert result.edges_added == 1
    assert result.edges_removed == 0
    assert result.edges_modified == 0
    assert len(result.edge_diffs) == 1

    added_edge = result.edge_diffs[0]
    assert added_edge.type == "REVIEWED"
    assert added_edge.change_type == "added"
    assert added_edge.from_def is None
    assert added_edge.to_def is not None


def test_diff_edge_removed(base_mapping_version):
    """Test diff when an edge is removed."""
    v2 = MappingVersion(
        mapping_id=base_mapping_version.mapping_id,
        version=2,
        node_definitions=base_mapping_version.node_definitions,
        edge_definitions=[],  # Removed all edges
        change_description="Removed PURCHASED edge",
        created_at=datetime.now(UTC),
        created_by="test_user",
    )

    result = diff_mapping_versions(base_mapping_version, v2)

    assert result.edges_added == 0
    assert result.edges_removed == 1
    assert result.edges_modified == 0

    removed_edge = result.edge_diffs[0]
    assert removed_edge.type == "PURCHASED"
    assert removed_edge.change_type == "removed"


def test_diff_edge_modified_properties(base_mapping_version):
    """Test diff when an edge's properties change."""
    v2 = MappingVersion(
        mapping_id=base_mapping_version.mapping_id,
        version=2,
        node_definitions=base_mapping_version.node_definitions,
        edge_definitions=[
            EdgeDefinition(
                type="PURCHASED",
                from_node="Customer",
                to_node="Product",
                sql="SELECT customer_id, product_id, amount, purchase_date FROM analytics.transactions",
                from_key="customer_id",
                to_key="product_id",
                properties=[
                    PropertyDefinition(name="amount", type="DOUBLE"),
                    PropertyDefinition(name="purchase_date", type="DATE"),  # Added property
                ],
            ),
        ],
        change_description="Added purchase_date to PURCHASED edge",
        created_at=datetime.now(UTC),
        created_by="test_user",
    )

    result = diff_mapping_versions(base_mapping_version, v2)

    assert result.edges_added == 0
    assert result.edges_removed == 0
    assert result.edges_modified == 1

    modified_edge = result.edge_diffs[0]
    assert modified_edge.type == "PURCHASED"
    assert "properties" in modified_edge.fields_changed or "sql" in modified_edge.fields_changed
    assert len(modified_edge.to_def["properties"]) == 2


def test_diff_complex_scenario(base_mapping_version):
    """Test realistic scenario with multiple changes."""
    v2 = MappingVersion(
        mapping_id=base_mapping_version.mapping_id,
        version=2,
        node_definitions=[
            # Customer modified (added property)
            NodeDefinition(
                label="Customer",
                sql=base_mapping_version.node_definitions[0].sql,
                primary_key=base_mapping_version.node_definitions[0].primary_key,
                properties=[
                    PropertyDefinition(name="name", type="STRING"),
                    PropertyDefinition(name="email", type="STRING"),  # Added
                ],
            ),
            # Product unchanged
            base_mapping_version.node_definitions[1],
            # Supplier added
            NodeDefinition(
                label="Supplier",
                sql="SELECT supplier_id, name FROM analytics.suppliers",
                primary_key=PrimaryKeyDefinition(name="supplier_id", type="STRING"),
                properties=[PropertyDefinition(name="name", type="STRING")],
            ),
        ],
        edge_definitions=[
            # PURCHASED modified (added property)
            EdgeDefinition(
                type="PURCHASED",
                from_node="Customer",
                to_node="Product",
                sql="SELECT customer_id, product_id, amount, tax FROM analytics.transactions",
                from_key="customer_id",
                to_key="product_id",
                properties=[
                    PropertyDefinition(name="amount", type="DOUBLE"),
                    PropertyDefinition(name="tax", type="DOUBLE"),  # Added
                ],
            ),
        ],
        change_description="Multiple changes",
        created_at=datetime.now(UTC),
        created_by="test_user",
    )

    result = diff_mapping_versions(base_mapping_version, v2)

    # Summary counts
    assert result.nodes_added == 1  # Supplier
    assert result.nodes_removed == 0
    assert result.nodes_modified == 1  # Customer
    assert result.edges_added == 0
    assert result.edges_removed == 0
    assert result.edges_modified == 1  # PURCHASED

    # Check node diffs
    assert len(result.node_diffs) == 2
    node_labels = {nd.label for nd in result.node_diffs}
    assert "Customer" in node_labels
    assert "Supplier" in node_labels

    # Check edge diffs
    assert len(result.edge_diffs) == 1
    assert result.edge_diffs[0].type == "PURCHASED"
    assert result.edge_diffs[0].change_type == "modified"
