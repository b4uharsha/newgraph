"""Schema inspection endpoint.

Provides /schema endpoint for introspecting the graph schema.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from wrapper.dependencies import DatabaseServiceDep
from wrapper.exceptions import DatabaseError
from wrapper.logging import get_logger
from wrapper.models.responses import EdgeTableSchema, NodeTableSchema, SchemaResponse

logger = get_logger(__name__)

router = APIRouter(prefix="/schema", tags=["Schema"])


@router.get(
    "",
    response_model=SchemaResponse,
    summary="Get graph schema",
    description="Returns the schema of the loaded graph including node and edge tables.",
    responses={
        503: {"description": "Database not ready"},
    },
)
async def get_schema(
    db_service: DatabaseServiceDep,
) -> SchemaResponse:
    """Get the graph database schema.

    Returns detailed information about:
    - Node tables (labels, properties, counts)
    - Edge tables (types, source/target nodes, properties, counts)
    - Total node and edge counts
    """
    if not db_service.is_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not ready",
        )

    logger.debug("Fetching graph schema")

    try:
        schema = await db_service.get_schema()

        # Convert to response models
        node_tables = [
            NodeTableSchema(
                label=table["label"],
                primary_key=table.get("primary_key", ""),
                primary_key_type=table.get("primary_key_type", "STRING"),
                properties=table.get("properties", {}),
                node_count=table.get("node_count", 0),
            )
            for table in schema.get("node_tables", [])
        ]

        edge_tables = [
            EdgeTableSchema(
                type=table["type"],
                from_node=table.get("from_node", ""),
                to_node=table.get("to_node", ""),
                properties=table.get("properties", {}),
                edge_count=table.get("edge_count", 0),
            )
            for table in schema.get("edge_tables", [])
        ]

        return SchemaResponse(
            node_tables=node_tables,
            edge_tables=edge_tables,
            total_nodes=schema.get("total_nodes", 0),
            total_edges=schema.get("total_edges", 0),
        )

    except DatabaseError as e:
        logger.error("Failed to get schema", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from e
