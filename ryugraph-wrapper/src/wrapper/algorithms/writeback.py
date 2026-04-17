"""Result write-back utilities for algorithm outputs.

Provides efficient batch writing of algorithm results back to node/edge
properties in the Ryugraph database.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from wrapper.exceptions import DatabaseError
from wrapper.logging import get_logger

if TYPE_CHECKING:
    from wrapper.services.database import DatabaseService

logger = get_logger(__name__)

# Default batch size for write operations
DEFAULT_BATCH_SIZE = 1000


async def write_node_property(
    db_service: DatabaseService,
    node_label: str | None,
    property_name: str,
    values: dict[Any, Any],
    id_property: str = "id",
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> int:
    """Write values to a node property in batches.

    Args:
        db_service: Database service.
        node_label: Node label to update (None = all nodes).
        property_name: Property to set.
        values: Dict mapping node identifier -> value.
        id_property: Property used to identify nodes (default: "id").
        batch_size: Number of updates per batch.

    Returns:
        Total number of nodes updated.

    Raises:
        DatabaseError: If write operation fails.
    """
    if not values:
        return 0

    logger.info(
        "Writing node property",
        property=property_name,
        node_count=len(values),
        node_label=node_label,
    )

    try:
        updates = list(values.items())
        total_updated = 0

        node_match = f"(n:{node_label})" if node_label else "(n)"

        for i in range(0, len(updates), batch_size):
            batch = updates[i : i + batch_size]

            # Build parameterized query
            query = f"""
            UNWIND $updates AS update
            MATCH {node_match}
            WHERE n.{id_property} = update[0]
            SET n.{property_name} = update[1]
            RETURN count(n) as updated
            """

            result = await db_service.execute_query(
                query,
                {"updates": [[k, v] for k, v in batch]},
            )

            batch_updated = result["rows"][0][0] if result["rows"] else 0
            total_updated += batch_updated

            logger.debug(
                "Batch written",
                batch_number=i // batch_size + 1,
                batch_size=len(batch),
                updated=batch_updated,
            )

        logger.info(
            "Node property write complete",
            property=property_name,
            total_updated=total_updated,
        )

        return total_updated

    except Exception as e:
        logger.error(
            "Failed to write node property",
            property=property_name,
            error=str(e),
        )
        raise DatabaseError(f"Failed to write property {property_name}: {e}") from e


async def write_node_property_by_internal_id(
    db_service: DatabaseService,
    node_label: str | None,
    property_name: str,
    values: dict[int, Any],
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> int:
    """Write values to a node property using internal node IDs.

    Args:
        db_service: Database service.
        node_label: Node label to update (None = all nodes).
        property_name: Property to set.
        values: Dict mapping internal node ID -> value.
        batch_size: Number of updates per batch.

    Returns:
        Total number of nodes updated.

    Raises:
        DatabaseError: If write operation fails.
    """
    if not values:
        return 0

    logger.info(
        "Writing node property by internal ID",
        property=property_name,
        node_count=len(values),
    )

    try:
        updates = list(values.items())
        total_updated = 0

        node_match = f"(n:{node_label})" if node_label else "(n)"

        for i in range(0, len(updates), batch_size):
            batch = updates[i : i + batch_size]

            query = f"""
            UNWIND $updates AS update
            MATCH {node_match}
            WHERE id(n) = update[0]
            SET n.{property_name} = update[1]
            RETURN count(n) as updated
            """

            result = await db_service.execute_query(
                query,
                {"updates": [[k, v] for k, v in batch]},
            )

            batch_updated = result["rows"][0][0] if result["rows"] else 0
            total_updated += batch_updated

        logger.info(
            "Node property write complete (internal IDs)",
            property=property_name,
            total_updated=total_updated,
        )

        return total_updated

    except Exception as e:
        logger.error(
            "Failed to write node property (internal IDs)",
            property=property_name,
            error=str(e),
        )
        raise DatabaseError(f"Failed to write property {property_name}: {e}") from e


async def initialize_node_property(
    db_service: DatabaseService,
    node_label: str | None,
    property_name: str,
    default_value: Any,
) -> int:
    """Initialize a property on all matching nodes.

    Args:
        db_service: Database service.
        node_label: Node label to update (None = all nodes).
        property_name: Property to initialize.
        default_value: Default value to set.

    Returns:
        Number of nodes updated.

    Raises:
        DatabaseError: If initialization fails.
    """
    logger.info(
        "Initializing node property",
        property=property_name,
        default=default_value,
        node_label=node_label,
    )

    try:
        node_match = f"(n:{node_label})" if node_label else "(n)"

        query = f"""
        MATCH {node_match}
        SET n.{property_name} = $default_value
        RETURN count(n) as updated
        """

        result = await db_service.execute_query(
            query,
            {"default_value": default_value},
        )

        updated = result["rows"][0][0] if result["rows"] else 0

        logger.info(
            "Node property initialized",
            property=property_name,
            updated=updated,
        )

        return updated

    except Exception as e:
        logger.error(
            "Failed to initialize node property",
            property=property_name,
            error=str(e),
        )
        raise DatabaseError(f"Failed to initialize property {property_name}: {e}") from e


async def remove_node_property(
    db_service: DatabaseService,
    node_label: str | None,
    property_name: str,
) -> int:
    """Remove a property from all matching nodes.

    Args:
        db_service: Database service.
        node_label: Node label to update (None = all nodes).
        property_name: Property to remove.

    Returns:
        Number of nodes updated.

    Raises:
        DatabaseError: If removal fails.
    """
    logger.info(
        "Removing node property",
        property=property_name,
        node_label=node_label,
    )

    try:
        node_match = f"(n:{node_label})" if node_label else "(n)"

        query = f"""
        MATCH {node_match}
        WHERE n.{property_name} IS NOT NULL
        REMOVE n.{property_name}
        RETURN count(n) as updated
        """

        result = await db_service.execute_query(query)
        updated = result["rows"][0][0] if result["rows"] else 0

        logger.info(
            "Node property removed",
            property=property_name,
            updated=updated,
        )

        return updated

    except Exception as e:
        logger.error(
            "Failed to remove node property",
            property=property_name,
            error=str(e),
        )
        raise DatabaseError(f"Failed to remove property {property_name}: {e}") from e


async def write_edge_property(
    db_service: DatabaseService,
    edge_type: str | None,
    property_name: str,
    values: dict[tuple[Any, Any], Any],
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> int:
    """Write values to an edge property in batches.

    Args:
        db_service: Database service.
        edge_type: Edge type to update (None = all edges).
        property_name: Property to set.
        values: Dict mapping (source_id, target_id) -> value.
        batch_size: Number of updates per batch.

    Returns:
        Total number of edges updated.

    Raises:
        DatabaseError: If write operation fails.
    """
    if not values:
        return 0

    logger.info(
        "Writing edge property",
        property=property_name,
        edge_count=len(values),
        edge_type=edge_type,
    )

    try:
        updates = [(source, target, value) for (source, target), value in values.items()]
        total_updated = 0

        edge_match = f"-[r:{edge_type}]->" if edge_type else "-[r]->"

        for i in range(0, len(updates), batch_size):
            batch = updates[i : i + batch_size]

            query = f"""
            UNWIND $updates AS update
            MATCH (s){edge_match}(t)
            WHERE id(s) = update[0] AND id(t) = update[1]
            SET r.{property_name} = update[2]
            RETURN count(r) as updated
            """

            result = await db_service.execute_query(
                query,
                {"updates": [[s, t, v] for s, t, v in batch]},
            )

            batch_updated = result["rows"][0][0] if result["rows"] else 0
            total_updated += batch_updated

        logger.info(
            "Edge property write complete",
            property=property_name,
            total_updated=total_updated,
        )

        return total_updated

    except Exception as e:
        logger.error(
            "Failed to write edge property",
            property=property_name,
            error=str(e),
        )
        raise DatabaseError(f"Failed to write edge property {property_name}: {e}") from e
