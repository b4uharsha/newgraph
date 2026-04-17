"""DDL generation and GCS path utilities.

These utility functions work with shared schema types from graph_olap_schemas.
They provide wrapper-specific functionality (DDL generation, GCS paths) without
extending the shared schema classes, following the architectural guardrail that
schemas must not be extended.

See: docs/foundation/architectural.guardrails.md - "Shared Schemas as Single Source of Truth"
"""

from graph_olap_schemas import EdgeDefinition, NodeDefinition


def generate_node_ddl(node: NodeDefinition) -> str:
    """Generate CREATE NODE TABLE statement for Ryugraph.

    Args:
        node: Node definition from shared schema.

    Returns:
        Cypher CREATE NODE TABLE statement.

    Example:
        >>> node = NodeDefinition(
        ...     label="Customer",
        ...     primary_key=PrimaryKeyDefinition(name="id", type="STRING"),
        ...     properties=[PropertyDefinition(name="name", type="STRING")]
        ... )
        >>> generate_node_ddl(node)
        "CREATE NODE TABLE Customer(id STRING PRIMARY KEY, name STRING)"
    """
    # Extract type value - handle both enum and string
    pk_type = (
        node.primary_key.type.value
        if hasattr(node.primary_key.type, "value")
        else node.primary_key.type
    )

    columns = [f"{node.primary_key.name} {pk_type} PRIMARY KEY"]

    for prop in node.properties:
        prop_type = prop.type.value if hasattr(prop.type, "value") else prop.type
        columns.append(f"{prop.name} {prop_type}")

    return f"CREATE NODE TABLE {node.label}({', '.join(columns)})"


def generate_edge_ddl(edge: EdgeDefinition) -> str:
    """Generate CREATE REL TABLE statement for Ryugraph.

    Args:
        edge: Edge definition from shared schema.

    Returns:
        Cypher CREATE REL TABLE statement.

    Example:
        >>> edge = EdgeDefinition(
        ...     type="PURCHASED",
        ...     from_node="Customer",
        ...     to_node="Product",
        ...     from_key="customer_id",
        ...     to_key="product_id",
        ...     properties=[PropertyDefinition(name="quantity", type="INT64")]
        ... )
        >>> generate_edge_ddl(edge)
        "CREATE REL TABLE PURCHASED(FROM Customer TO Product, quantity INT64)"
    """
    columns = [f"FROM {edge.from_node} TO {edge.to_node}"]

    for prop in edge.properties:
        prop_type = prop.type.value if hasattr(prop.type, "value") else prop.type
        columns.append(f"{prop.name} {prop_type}")

    return f"CREATE REL TABLE {edge.type}({', '.join(columns)})"


def get_node_gcs_subpath(node: NodeDefinition) -> str:
    """Get the GCS subpath for a node's Parquet files.

    Args:
        node: Node definition from shared schema.

    Returns:
        Relative path like 'nodes/Customer/'.
    """
    return f"nodes/{node.label}/"


def get_edge_gcs_subpath(edge: EdgeDefinition) -> str:
    """Get the GCS subpath for an edge's Parquet files.

    Args:
        edge: Edge definition from shared schema.

    Returns:
        Relative path like 'edges/PURCHASED/'.
    """
    return f"edges/{edge.type}/"
