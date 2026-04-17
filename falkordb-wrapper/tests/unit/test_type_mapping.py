"""Unit tests for type mapping utilities."""

from __future__ import annotations

import pytest
from graph_olap_schemas import NodeDefinition, PrimaryKeyDefinition, PropertyDefinition

from wrapper.utils.type_mapping import (
    validate_node_types,
)


class TestTypeMappingValidation:
    """Tests for type mapping validation."""

    @pytest.mark.unit
    def test_validate_node_with_supported_types(self):
        """Test validation passes for supported types."""
        node_def = NodeDefinition(
            label="Person",
            sql="SELECT id, name, age FROM people",
            primary_key=PrimaryKeyDefinition(name="id", type="STRING"),
            properties=[
                PropertyDefinition(name="name", type="STRING"),
                PropertyDefinition(name="age", type="INT64"),
            ],
        )

        errors = validate_node_types(node_def)

        assert len(errors) == 0

    @pytest.mark.unit
    def test_validate_node_with_unsupported_primary_key(self):
        """Test validation fails for unsupported primary key type."""
        node_def = NodeDefinition(
            label="Person",
            sql="SELECT id, name FROM people",
            primary_key=PrimaryKeyDefinition(name="id", type="UUID"),  # Unsupported
            properties=[
                PropertyDefinition(name="name", type="STRING"),
            ],
        )

        errors = validate_node_types(node_def)

        assert len(errors) == 1
        assert "UUID" in errors[0]
        assert "not supported" in errors[0]

    @pytest.mark.unit
    def test_validate_node_with_unsupported_property(self):
        """Test validation fails for unsupported property type."""
        node_def = NodeDefinition(
            label="Person",
            sql="SELECT id, data FROM people",
            primary_key=PrimaryKeyDefinition(name="id", type="STRING"),
            properties=[
                PropertyDefinition(name="data", type="BLOB"),  # Unsupported
            ],
        )

        errors = validate_node_types(node_def)

        assert len(errors) == 1
        assert "BLOB" in errors[0]
        assert "not supported" in errors[0]

    @pytest.mark.unit
    def test_validate_node_with_multiple_unsupported_types(self):
        """Test validation reports all unsupported types."""
        node_def = NodeDefinition(
            label="Complex",
            sql="SELECT id, uuid, tags, metadata FROM data",
            primary_key=PrimaryKeyDefinition(name="id", type="STRING"),
            properties=[
                PropertyDefinition(name="uuid", type="UUID"),  # Unsupported
                PropertyDefinition(name="tags", type="LIST"),  # Unsupported
                PropertyDefinition(name="metadata", type="MAP"),  # Unsupported
            ],
        )

        errors = validate_node_types(node_def)

        assert len(errors) == 3
        assert any("UUID" in e for e in errors)
        assert any("LIST" in e for e in errors)
        assert any("MAP" in e for e in errors)

    @pytest.mark.unit
    def test_all_supported_types_accepted(self):
        """Test all supported types are accepted."""
        for type_name in ["STRING", "INT64", "INT32", "DOUBLE", "FLOAT", "BOOL", "DATE", "TIMESTAMP"]:
            node_def = NodeDefinition(
                label="Test",
                sql="SELECT id FROM test",
                primary_key=PrimaryKeyDefinition(name="id", type=type_name),
                properties=[],
            )

            errors = validate_node_types(node_def)
            assert len(errors) == 0, f"Type {type_name} should be supported"

    @pytest.mark.unit
    def test_all_unsupported_types_rejected(self):
        """Test all unsupported types are rejected."""
        # Note: JSON is not in RyugraphType enum, so we skip it to avoid Pydantic validation error
        for type_name in ["BLOB", "UUID", "LIST", "MAP", "STRUCT"]:
            node_def = NodeDefinition(
                label="Test",
                sql="SELECT id FROM test",
                primary_key=PrimaryKeyDefinition(name="id", type=type_name),
                properties=[],
            )

            errors = validate_node_types(node_def)
            assert len(errors) > 0, f"Type {type_name} should be unsupported"

    @pytest.mark.unit
    def test_type_validation_with_blob(self):
        """Test BLOB type is properly rejected."""
        # BLOB is a valid RyugraphType but unsupported by FalkorDB
        node_def = NodeDefinition(
            label="Test",
            sql="SELECT id FROM test",
            primary_key=PrimaryKeyDefinition(name="id", type="BLOB"),
            properties=[],
        )

        errors = validate_node_types(node_def)
        assert len(errors) > 0
        assert "BLOB" in errors[0]
