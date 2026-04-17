"""Type mapping utilities for validating Starburst → FalkorDB type compatibility.

FalkorDB supports a subset of types compared to full graph databases.
This module validates that mapping definitions only use supported types.
"""

from __future__ import annotations

import structlog
from graph_olap_schemas import NodeDefinition

logger = structlog.get_logger(__name__)

# Supported types in FalkorDB (subset of full Cypher types)
SUPPORTED_TYPES = {
    "STRING",
    "INT64",
    "INT32",
    "INT16",
    "INT8",
    "DOUBLE",
    "FLOAT",
    "BOOL",
    "BOOLEAN",  # Alias for BOOL
    "DATE",
    "DATETIME",
    "TIMESTAMP",  # Alias for DATETIME
}

# Unsupported types that will cause errors
UNSUPPORTED_TYPES = {
    "BLOB",
    "UUID",
    "LIST",
    "ARRAY",  # Alias for LIST
    "MAP",
    "STRUCT",
    "JSON",
}


def validate_node_types(node_def: NodeDefinition) -> list[str]:
    """Validate that node definition uses only supported types.

    Args:
        node_def: Node definition to validate

    Returns:
        List of validation errors (empty if valid)
    """
    errors: list[str] = []

    # Check primary key type
    pk_type = node_def.primary_key.type.upper()
    if pk_type in UNSUPPORTED_TYPES:
        errors.append(
            f"Node '{node_def.label}': Primary key type '{pk_type}' not supported by FalkorDB"
        )

    # Check property types
    for prop in node_def.properties:
        prop_type = prop.type.upper()
        if prop_type in UNSUPPORTED_TYPES:
            errors.append(
                f"Node '{node_def.label}': Property '{prop.name}' type '{prop_type}' "
                "not supported by FalkorDB"
            )

    if errors:
        logger.warning(
            "node_type_validation_failed",
            label=node_def.label,
            error_count=len(errors),
        )
    else:
        logger.debug("node_type_validation_passed", label=node_def.label)

    return errors


def validate_edge_types(edge_def: Any) -> list[str]:
    """Validate that edge definition uses only supported types.

    Args:
        edge_def: Edge definition to validate

    Returns:
        List of validation errors (empty if valid)
    """
    errors: list[str] = []

    # Check property types
    for prop in edge_def.properties:
        prop_type = prop.type.upper()
        if prop_type in UNSUPPORTED_TYPES:
            errors.append(
                f"Edge '{edge_def.type}': Property '{prop.name}' type '{prop_type}' "
                "not supported by FalkorDB"
            )

    if errors:
        logger.warning(
            "edge_type_validation_failed",
            edge_type=edge_def.type,
            error_count=len(errors),
        )
    else:
        logger.debug("edge_type_validation_passed", edge_type=edge_def.type)

    return errors


def validate_mapping_types(mapping: Any) -> list[str]:
    """Validate entire mapping for type compatibility.

    Args:
        mapping: Mapping definition to validate

    Returns:
        List of all validation errors across nodes and edges
    """
    all_errors: list[str] = []

    # Validate all node definitions
    for node_def in mapping.node_definitions:
        errors = validate_node_types(node_def)
        all_errors.extend(errors)

    # Validate all edge definitions
    for edge_def in mapping.edge_definitions:
        errors = validate_edge_types(edge_def)
        all_errors.extend(errors)

    if all_errors:
        logger.error(
            "mapping_type_validation_failed",
            mapping_id=mapping.mapping_id,
            total_errors=len(all_errors),
        )
    else:
        logger.info(
            "mapping_type_validation_passed",
            mapping_id=mapping.mapping_id,
            node_count=len(mapping.node_definitions),
            edge_count=len(mapping.edge_definitions),
        )

    return all_errors
