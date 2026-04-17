"""Schema router for graph schema introspection."""

from __future__ import annotations

import structlog
from fastapi import APIRouter

from wrapper.dependencies import DatabaseServiceDep
from wrapper.models import EdgeTableSchema, NodeTableSchema, SchemaResponse

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["Schema"])


@router.get(
    "/schema",
    response_model=SchemaResponse,
    summary="Get graph schema",
    description="Returns the schema of the graph including node and edge tables.",
)
async def get_schema(
    db_service: DatabaseServiceDep,
) -> SchemaResponse:
    """Get graph schema information.

    Returns node labels, edge types, and properties for all labels/types.
    Uses flat response structure matching Ryugraph.

    Args:
        db_service: Database service (injected via DI)

    Returns:
        Schema information with node_tables, edge_tables, total counts

    Note: Exception handling is done centrally in main.py exception handlers.
    """
    logger.info("schema_request")

    schema = await db_service.get_schema()

    logger.info(
        "schema_fetched",
        node_label_count=len(schema.get("node_labels", [])),
        edge_type_count=len(schema.get("edge_types", [])),
    )

    # Build node table schemas
    node_tables = []
    node_labels = schema.get("node_labels", [])
    node_properties = schema.get("node_properties", {})
    node_counts = schema.get("node_counts", {})

    for label in node_labels:
        props = node_properties.get(label, [])
        # Convert property list to dict (FalkorDB returns list, Ryugraph expects dict)
        prop_dict = dict.fromkeys(props, "STRING") if isinstance(props, list) else props
        node_tables.append(
            NodeTableSchema(
                label=label,
                primary_key="id",  # FalkorDB uses internal IDs
                primary_key_type="INTEGER",
                properties=prop_dict,
                node_count=node_counts.get(label, 0),
            )
        )

    # Build edge table schemas
    edge_tables = []
    edge_types = schema.get("edge_types", [])
    edge_properties = schema.get("edge_properties", {})
    edge_counts = schema.get("edge_counts", {})

    for edge_type in edge_types:
        props = edge_properties.get(edge_type, [])
        prop_dict = dict.fromkeys(props, "STRING") if isinstance(props, list) else props
        edge_tables.append(
            EdgeTableSchema(
                type=edge_type,
                from_node="*",  # FalkorDB doesn't enforce source/target labels
                to_node="*",
                properties=prop_dict,
                edge_count=edge_counts.get(edge_type, 0),
            )
        )

    # Calculate totals
    total_nodes = sum(t.node_count for t in node_tables)
    total_edges = sum(t.edge_count for t in edge_tables)

    return SchemaResponse(
        node_tables=node_tables,
        edge_tables=edge_tables,
        total_nodes=total_nodes,
        total_edges=total_edges,
    )
