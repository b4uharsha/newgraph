"""Database service for FalkorDB graph database.

This service manages the embedded FalkorDBLite instance, which runs as a subprocess
communicating via Unix sockets. It provides methods for initialization, query execution,
schema introspection, and graceful shutdown.

Architecture:
- FalkorDBLite spawns a Redis subprocess with FalkorDB module loaded
- Communication via Unix sockets (zero network latency)
- Schema-flexible (inferred from data, no explicit DDL needed)
- In-memory storage with RDB persistence
"""

from __future__ import annotations

import asyncio
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psutil
import structlog
from graph_olap_schemas import (
    EdgeDefinition,
    InstanceMappingResponse,
    NodeDefinition,
)

from wrapper.exceptions import (
    DatabaseConnectionError,
    DatabaseError,
    DatabaseNotInitializedError,
    DatabasePathError,
    DataLoadError,
    QueryExecutionError,
    QuerySyntaxError,
    QueryTimeoutError,
)
from wrapper.utils.csv_converter import ParquetReader

logger = structlog.get_logger(__name__)

# Batch loading configuration
# FalkorDBLite's LOAD CSV has file access limitations (subprocess isolation),
# so we use UNWIND batch loading instead. This provides excellent performance
# (~200k+ nodes/sec) without requiring file system access from the Redis subprocess.
BATCH_SIZE = 5000  # Number of rows per UNWIND batch (tuned for memory/performance balance)

# FalkorDBLite 0.6.0+ with native async API
try:
    from redislite.async_falkordb_client import AsyncFalkorDB
    FALKORDB_AVAILABLE = True
except ImportError as e:
    AsyncFalkorDB = None  # type: ignore[assignment,misc]
    FALKORDB_AVAILABLE = False
    logger.error(
        "FalkorDBLite import failed",
        error=str(e),
        error_type=type(e).__name__,
    )


class DatabaseService:
    """Service for managing FalkorDB database operations.

    This service wraps FalkorDBLite 0.6.0+ with native async API.

    Data Loading:
        Uses UNWIND batch loading for 100-200x performance improvement
        over row-by-row inserts. LOAD CSV doesn't work with FalkorDBLite
        due to subprocess isolation. Includes warning-based validation
        for partial data loads.
    """

    # Minimum success rate thresholds before failing the instance
    # Below these thresholds, the data is considered unusable
    MIN_NODE_SUCCESS_RATE = 10.0  # 10% for nodes
    MIN_EDGE_SUCCESS_RATE = 5.0   # 5% for edges (more missing is normal)

    def __init__(
        self,
        database_path: Path,
        graph_name: str,
        query_timeout_ms: int = 60_000,
    ) -> None:
        """Initialize database service.

        Args:
            database_path: Path to database directory
            graph_name: Name of the graph to create/use
            query_timeout_ms: Default query timeout in milliseconds (default: 60s)

        Raises:
            DatabaseError: If FalkorDBLite is not available

        Note:
            This follows the Ryugraph wrapper pattern (ADR-049): explicit parameters
            instead of Settings dependency. Caller must extract values from Settings
            and pass them explicitly.
        """
        if not FALKORDB_AVAILABLE:
            raise DatabaseError(
                "FalkorDBLite is not installed. Requires Python 3.12+ and "
                "'pip install FalkorDBLite>=0.6.0'",
                details={"python_version": "3.12+", "package": "FalkorDBLite>=0.6.0"},
            )

        # Store parameters (explicit, no fallbacks)
        self._database_path = database_path
        self._graph_name = graph_name
        self._query_timeout_ms = query_timeout_ms

        # FalkorDB instances (initialized during initialize())
        self._db: AsyncFalkorDB | None = None  # type: ignore[valid-type]
        self._graph: Any | None = None  # FalkorDB Graph object

        # State tracking
        self._is_initialized = False
        self._is_ready = False
        self._ready_at: datetime | None = None
        self._initialization_time: float | None = None

        # Data load warnings (populated during load_data)
        self._data_load_warnings: list[dict[str, Any]] = []

        logger.info(
            "database_service_created",
            database_path=str(database_path),
            graph_name=graph_name,
            query_timeout_ms=query_timeout_ms,
        )

    @property
    def is_initialized(self) -> bool:
        """Check if database has been initialized."""
        return self._is_initialized

    @property
    def is_ready(self) -> bool:
        """Check if database is ready for queries."""
        return self._is_ready

    @property
    def graph_name(self) -> str:
        """Get the graph name."""
        return self._graph_name

    @property
    def database_path(self) -> Path:
        """Get the database path."""
        return self._database_path

    @property
    def is_connected(self) -> bool:
        """Check if database connection is active."""
        return self._db is not None and self._graph is not None

    @property
    def ready_at(self) -> datetime | None:
        """Get timestamp when database became ready."""
        return self._ready_at

    async def initialize(self) -> None:
        """Initialize FalkorDBLite database and select graph.

        Spawns Redis subprocess with FalkorDB module and selects the graph.

        Raises:
            DatabaseConnectionError: If connection to FalkorDB fails
            DatabaseError: If initialization fails
        """
        if self._is_initialized:
            logger.warning("database_already_initialized", graph_name=self._graph_name)
            return

        start_time = time.time()
        logger.info("initializing_database", database_path=str(self._database_path))

        try:
            # Ensure database directory exists (parents=True creates /data/db if needed,
            # which handles emptyDir volumes mounted at /data by Kubernetes)
            self._database_path.mkdir(parents=True, exist_ok=True)

            # Initialize FalkorDBLite (spawns Redis subprocess)
            # IMPORTANT: AsyncFalkorDB expects an RDB filename, NOT a directory path.
            # If you pass a directory, Redis tries to load it as an RDB file and fails
            # with "Short read or OOM loading DB" / "Unexpected EOF reading RDB file".
            rdb_file = self._database_path / f"{self._graph_name}.rdb"
            self._db = AsyncFalkorDB(str(rdb_file))
            self._graph = self._db.select_graph(self._graph_name)

            self._is_initialized = True
            self._initialization_time = time.time() - start_time

            logger.info(
                "database_initialized",
                graph_name=self._graph_name,
                duration_seconds=round(self._initialization_time, 3),
            )

        except Exception as e:
            logger.error(
                "database_initialization_failed",
                error=str(e),
                error_type=type(e).__name__,
                database_path=str(self._database_path),
            )
            raise DatabaseConnectionError(
                f"Failed to initialize FalkorDB: {e}",
                details={"database_path": str(self._database_path), "error": str(e)},
            ) from e

    async def create_schema(self, mapping: InstanceMappingResponse) -> None:
        """Create graph schema from mapping definition.

        FalkorDB is schema-flexible, so this is a no-op. Schema is inferred
        from the first data rows during loading.

        Args:
            mapping: Mapping definition (used for validation only)

        Raises:
            DatabaseNotInitializedError: If database not initialized
            SchemaCreationError: If schema validation fails
        """
        if not self._is_initialized:
            raise DatabaseNotInitializedError()

        logger.info(
            "schema_validation_skipped",
            reason="FalkorDB is schema-flexible (infers from data)",
            node_count=len(mapping.node_definitions),
            edge_count=len(mapping.edge_definitions),
        )

        # Schema will be inferred during data load
        # We could validate type compatibility here, but that's done in control plane

    async def execute_query(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
        timeout_ms: int | None = None,
    ) -> dict[str, Any]:
        """Execute a Cypher query.

        Args:
            query: Cypher query string
            parameters: Query parameters (default: {})
            timeout_ms: Query timeout in milliseconds (default: service default)

        Returns:
            Query result with columns, rows, row_count, execution_time_ms

        Raises:
            DatabaseNotInitializedError: If database not initialized
            QuerySyntaxError: If query has syntax errors
            QueryTimeoutError: If query exceeds timeout
            QueryExecutionError: If query execution fails
        """
        if not self._is_initialized or self._graph is None:
            raise DatabaseNotInitializedError()

        timeout = timeout_ms or self._query_timeout_ms
        params = parameters or {}

        start_time = time.time()
        logger.debug(
            "executing_query",
            query=query[:200],  # Truncate long queries
            param_count=len(params),
            timeout_ms=timeout,
        )

        try:
            # Execute query with timeout (native async)
            result = await asyncio.wait_for(
                self._graph.query(query, params=params),
                timeout=timeout / 1000.0,  # Convert ms to seconds
            )

            execution_time_ms = round((time.time() - start_time) * 1000, 2)

            # Parse FalkorDB result
            # result.header: list of column names
            # result.result_set: list of rows (each row is a list of values)
            # result.run_time_ms: execution time from FalkorDB

            logger.debug(
                "query_executed",
                row_count=len(result.result_set),
                execution_time_ms=execution_time_ms,
            )

            # Parse columns - FalkorDB header is list of [type_code, name] pairs
            # Extract just the column names for response
            columns: list[str] = []
            if hasattr(result, "header"):
                for col in result.header:
                    if isinstance(col, (list, tuple)) and len(col) >= 2:
                        # FalkorDB format: [type_code, column_name]
                        columns.append(str(col[1]))
                    else:
                        # Fallback: column is already a string
                        columns.append(str(col))

            return {
                "columns": columns,
                "rows": result.result_set if hasattr(result, "result_set") else [],
                "row_count": len(result.result_set) if hasattr(result, "result_set") else 0,
                "execution_time_ms": (
                    result.run_time_ms if hasattr(result, "run_time_ms") else execution_time_ms
                ),
            }

        except TimeoutError as e:
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            logger.warning(
                "query_timeout",
                timeout_ms=timeout,
                elapsed_ms=elapsed_ms,
                query=query[:200],
            )
            raise QueryTimeoutError(
                timeout_ms=timeout, elapsed_ms=int(elapsed_ms), query=query[:500]
            ) from e

        except Exception as e:
            error_msg = str(e).lower()

            # Detect syntax errors
            if "syntax" in error_msg or "parse" in error_msg or "invalid" in error_msg:
                logger.warning("query_syntax_error", error=str(e), query=query[:200])
                raise QuerySyntaxError(
                    f"Cypher syntax error: {e}", query=query[:500]
                ) from e

            # Generic execution error
            logger.error(
                "query_execution_failed",
                error=str(e),
                error_type=type(e).__name__,
                query=query[:200],
            )
            raise QueryExecutionError(
                f"Query execution failed: {e}", details={"error": str(e)}
            ) from e

    async def _get_labels(self) -> list[str]:
        """Get all node labels via Cypher query.

        Returns:
            List of node labels
        """
        result = await self.execute_query("CALL db.labels()", timeout_ms=5000)
        return [row[0] for row in result["rows"]]

    async def _get_relationship_types(self) -> list[str]:
        """Get all relationship types via Cypher query.

        Returns:
            List of relationship types
        """
        result = await self.execute_query("CALL db.relationshipTypes()", timeout_ms=5000)
        return [row[0] for row in result["rows"]]

    async def get_schema(self) -> dict[str, Any]:
        """Get graph schema information.

        Returns:
            Schema info with node_labels, edge_types, node_properties, edge_properties

        Raises:
            DatabaseNotInitializedError: If database not initialized
        """
        if not self._is_initialized or self._graph is None:
            raise DatabaseNotInitializedError()

        logger.debug("fetching_schema")

        try:
            # Get node labels and relationship types via Cypher queries
            node_labels = await self._get_labels()
            edge_types = await self._get_relationship_types()

            # Get properties for each node label
            node_properties: dict[str, list[str]] = {}
            for label in node_labels:
                # Query to get property keys
                result = await self.execute_query(
                    f"MATCH (n:{label}) RETURN keys(n) LIMIT 1", timeout_ms=5000
                )
                if result["row_count"] > 0:
                    node_properties[label] = result["rows"][0][0]  # First row, first column

            # Get properties for each edge type
            edge_properties: dict[str, list[str]] = {}
            for edge_type in edge_types:
                result = await self.execute_query(
                    f"MATCH ()-[r:{edge_type}]->() RETURN keys(r) LIMIT 1", timeout_ms=5000
                )
                if result["row_count"] > 0:
                    edge_properties[edge_type] = result["rows"][0][0]

            logger.debug(
                "schema_fetched",
                node_label_count=len(node_labels),
                edge_type_count=len(edge_types),
            )

            return {
                "node_labels": node_labels,
                "edge_types": edge_types,
                "node_properties": node_properties,
                "edge_properties": edge_properties,
            }

        except DatabaseNotInitializedError:
            raise
        except Exception as e:
            logger.error("schema_fetch_failed", error=str(e), error_type=type(e).__name__)
            raise DatabaseError(f"Failed to fetch schema: {e}", details={"error": str(e)}) from e

    async def get_stats(self) -> dict[str, Any]:
        """Get database statistics.

        Returns:
            Statistics including node counts, edge counts, memory usage

        Raises:
            DatabaseNotInitializedError: If database not initialized
        """
        if not self._is_initialized or self._graph is None:
            raise DatabaseNotInitializedError()

        logger.debug("fetching_stats")

        try:
            # Get node counts by label via Cypher query
            node_counts: dict[str, int] = {}
            for label in await self._get_labels():
                result = await self.execute_query(
                    f"MATCH (n:{label}) RETURN count(n)", timeout_ms=10000
                )
                node_counts[label] = result["rows"][0][0] if result["row_count"] > 0 else 0

            # Get edge counts by type via Cypher query
            edge_counts: dict[str, int] = {}
            for edge_type in await self._get_relationship_types():
                result = await self.execute_query(
                    f"MATCH ()-[r:{edge_type}]->() RETURN count(r)", timeout_ms=10000
                )
                edge_counts[edge_type] = result["rows"][0][0] if result["row_count"] > 0 else 0

            # Get memory usage (process-level, FalkorDB is in-memory)
            process = psutil.Process()
            memory_info = process.memory_info()

            return {
                "node_counts": node_counts,
                "edge_counts": edge_counts,
                "total_nodes": sum(node_counts.values()),
                "total_edges": sum(edge_counts.values()),
                "memory_usage_bytes": memory_info.rss,
                "memory_usage_mb": round(memory_info.rss / (1024 * 1024), 2),
            }

        except DatabaseNotInitializedError:
            raise
        except Exception as e:
            logger.error("stats_fetch_failed", error=str(e), error_type=type(e).__name__)
            raise DatabaseError(
                f"Failed to fetch database stats: {e}", details={"error": str(e)}
            ) from e

    def mark_ready(self) -> None:
        """Mark database as ready for queries.

        Called after data loading is complete.
        """
        self._is_ready = True
        self._ready_at = datetime.now(UTC)
        logger.info(
            "database_marked_ready",
            graph_name=self._graph_name,
            ready_at=self._ready_at.isoformat(),
        )

    # =========================================================================
    # LOAD CSV - Type Conversion
    # =========================================================================

    def _get_type_conversion_expr(
        self,
        ryugraph_type: str,
        csv_column: str,
    ) -> str:
        """Generate FalkorDB type conversion expression for CSV column.

        CSV values are always strings. FalkorDB provides type conversion
        functions that gracefully handle errors (returning null on failure).

        Args:
            ryugraph_type: Type from schema (e.g., "INT64", "STRING", "DOUBLE")
            csv_column: CSV column reference (e.g., "row.customer_id")

        Returns:
            Cypher expression with type conversion if needed

        Examples:
            >>> self._get_type_conversion_expr("INT64", "row.age")
            'toInteger(row.age)'

            >>> self._get_type_conversion_expr("STRING", "row.name")
            'row.name'

            >>> self._get_type_conversion_expr("BOOL", "row.active")
            'toBoolean(row.active)'
        """
        # Normalize type name
        type_name = str(ryugraph_type).upper()

        # Integer types → toInteger()
        if type_name in ("INT64", "INT32", "INT16", "INT8", "INTEGER"):
            return f"toInteger({csv_column})"

        # Float types → toFloat()
        if type_name in ("DOUBLE", "FLOAT"):
            return f"toFloat({csv_column})"

        # Boolean → toBoolean()
        if type_name in ("BOOL", "BOOLEAN"):
            return f"toBoolean({csv_column})"

        # String-compatible types → no conversion
        if type_name in ("STRING", "DATE", "DATETIME", "TIMESTAMP", "UUID", "BLOB", "LIST", "MAP", "STRUCT"):
            return csv_column

        # Unknown type → default to string with warning
        logger.warning(
            "unknown_type_in_csv_conversion",
            type=type_name,
            csv_column=csv_column,
            defaulting_to="string",
        )
        return csv_column

    # =========================================================================
    # UNWIND Batch Loading - Query Builders
    # =========================================================================

    def _build_unwind_query_for_nodes(self, node_def: NodeDefinition) -> str:
        """Build UNWIND Cypher query for batch node creation.

        Uses map projection to create nodes from parameter dictionaries.
        Type conversion is handled by Polars during Parquet reading.

        Args:
            node_def: Node definition with label, primary_key, properties

        Returns:
            UNWIND Cypher query string

        Example Output:
            UNWIND $nodes AS node
            CREATE (:Customer {customer_id: node.customer_id, name: node.name, age: node.age})
        """
        # Build property list from primary key and additional properties
        all_properties = [node_def.primary_key.name]
        all_properties.extend(prop.name for prop in node_def.properties)

        # Create property assignment string: {prop1: node.prop1, prop2: node.prop2}
        prop_assignments = ", ".join(f"{p}: node.{p}" for p in all_properties)

        query = f"""
        UNWIND $nodes AS node
        CREATE (:{node_def.label} {{{prop_assignments}}})
        """

        return query.strip()

    def _build_unwind_query_for_edges(
        self,
        edge_def: EdgeDefinition,
        node_definitions: list[NodeDefinition],
    ) -> str:
        """Build UNWIND Cypher query for batch edge creation.

        Matches source and target nodes by primary key, then creates edge.

        Args:
            edge_def: Edge definition with type, from/to nodes, properties
            node_definitions: All node definitions (for primary key lookup)

        Returns:
            UNWIND Cypher query string

        Example Output:
            UNWIND $edges AS edge
            MATCH (src:Customer {customer_id: edge.customer_id})
            MATCH (dst:Product {product_id: edge.product_id})
            CREATE (src)-[:PURCHASED {amount: edge.amount}]->(dst)
        """
        # Find source and target node definitions
        from_node_def = next(
            (n for n in node_definitions if n.label == edge_def.from_node),
            None,
        )
        to_node_def = next(
            (n for n in node_definitions if n.label == edge_def.to_node),
            None,
        )

        if not from_node_def:
            raise ValueError(
                f"Edge '{edge_def.type}' references non-existent source node: "
                f"'{edge_def.from_node}'"
            )
        if not to_node_def:
            raise ValueError(
                f"Edge '{edge_def.type}' references non-existent target node: "
                f"'{edge_def.to_node}'"
            )

        # Get primary key names
        from_pk_name = from_node_def.primary_key.name
        to_pk_name = to_node_def.primary_key.name

        # Build edge properties (if any)
        if edge_def.properties:
            edge_props = ", ".join(f"{p.name}: edge.{p.name}" for p in edge_def.properties)
            prop_str = f" {{{edge_props}}}"
        else:
            prop_str = ""

        # Build query using edge CSV column names (from_key, to_key)
        query = f"""
        UNWIND $edges AS edge
        MATCH (src:{edge_def.from_node} {{{from_pk_name}: edge.{edge_def.from_key}}})
        MATCH (dst:{edge_def.to_node} {{{to_pk_name}: edge.{edge_def.to_key}}})
        CREATE (src)-[:{edge_def.type}{prop_str}]->(dst)
        """

        return query.strip()

    # =========================================================================
    # LOAD CSV - Query Builders (Legacy, kept for reference)
    # =========================================================================

    def _build_load_csv_query_for_nodes(
        self,
        node_def: NodeDefinition,
        csv_path: Path,
    ) -> str:
        """Build LOAD CSV Cypher query for node creation.

        Args:
            node_def: Node definition with label, primary_key, properties
            csv_path: Path to CSV file

        Returns:
            LOAD CSV Cypher query string

        Example Output:
            LOAD CSV WITH HEADERS FROM 'file:///tmp/Customer.csv' AS row
            CREATE (:Customer {
                customer_id: toInteger(row.customer_id),
                name: row.name,
                age: toInteger(row.age)
            })
        """
        properties = []

        # Primary key with type conversion
        pk_name = node_def.primary_key.name
        pk_type = node_def.primary_key.type
        pk_expr = self._get_type_conversion_expr(pk_type, f"row.{pk_name}")
        properties.append(f"{pk_name}: {pk_expr}")

        # Additional properties with type conversion
        for prop in node_def.properties:
            prop_expr = self._get_type_conversion_expr(prop.type, f"row.{prop.name}")
            properties.append(f"{prop.name}: {prop_expr}")

        prop_str = ", ".join(properties)

        query = f"""
        LOAD CSV WITH HEADERS FROM 'file://{csv_path}' AS row
        CREATE (:{node_def.label} {{{prop_str}}})
        """

        return query.strip()

    def _build_load_csv_query_for_edges(
        self,
        edge_def: EdgeDefinition,
        csv_path: Path,
        node_definitions: list[NodeDefinition],
    ) -> str:
        """Build LOAD CSV Cypher query for edge creation.

        CRITICAL IMPLEMENTATION NOTES:
        1. Uses correct EdgeDefinition field names: from_node, to_node, from_key, to_key
        2. Looks up PRIMARY KEY NAME from source/target node definitions
        3. Applies TYPE CONVERSION to foreign key columns in MATCH clause
           (CSV values are strings, but node PKs may be integers)

        Args:
            edge_def: Edge definition with type, from/to nodes, properties
            csv_path: Path to CSV file
            node_definitions: All node definitions (for primary key lookup)

        Returns:
            LOAD CSV Cypher query string

        Raises:
            ValueError: If edge references non-existent node labels

        Example Output:
            LOAD CSV WITH HEADERS FROM 'file:///tmp/PURCHASED.csv' AS row
            MATCH (src:Customer {customer_id: toInteger(row.customer_id)})
            MATCH (dst:Product {product_id: toInteger(row.product_id)})
            CREATE (src)-[:PURCHASED {amount: toFloat(row.amount)}]->(dst)
        """
        # Step 1: Find source and target node definitions
        from_node_def = next(
            (n for n in node_definitions if n.label == edge_def.from_node),
            None,
        )
        to_node_def = next(
            (n for n in node_definitions if n.label == edge_def.to_node),
            None,
        )

        if not from_node_def:
            raise ValueError(
                f"Edge '{edge_def.type}' references non-existent source node: "
                f"'{edge_def.from_node}'"
            )
        if not to_node_def:
            raise ValueError(
                f"Edge '{edge_def.type}' references non-existent target node: "
                f"'{edge_def.to_node}'"
            )

        # Step 2: Get primary key NAMES and TYPES from node definitions
        from_pk_name = from_node_def.primary_key.name
        from_pk_type = from_node_def.primary_key.type
        to_pk_name = to_node_def.primary_key.name
        to_pk_type = to_node_def.primary_key.type

        # Step 3: Build type-converted expressions for foreign keys
        # CRITICAL: CSV values are strings, but node PKs may be integers!
        # Without this conversion, MATCH will fail silently (no edges created).
        from_key_expr = self._get_type_conversion_expr(
            from_pk_type, f"row.{edge_def.from_key}"
        )
        to_key_expr = self._get_type_conversion_expr(
            to_pk_type, f"row.{edge_def.to_key}"
        )

        # Step 4: Build edge properties (if any)
        if edge_def.properties:
            edge_props = []
            for prop in edge_def.properties:
                prop_expr = self._get_type_conversion_expr(
                    prop.type, f"row.{prop.name}"
                )
                edge_props.append(f"{prop.name}: {prop_expr}")
            prop_str = " {" + ", ".join(edge_props) + "}"
        else:
            prop_str = ""

        # Step 5: Build complete query with correct field names
        query = f"""
        LOAD CSV WITH HEADERS FROM 'file://{csv_path}' AS row
        MATCH (src:{edge_def.from_node} {{{from_pk_name}: {from_key_expr}}})
        MATCH (dst:{edge_def.to_node} {{{to_pk_name}: {to_key_expr}}})
        CREATE (src)-[:{edge_def.type}{prop_str}]->(dst)
        """

        return query.strip()

    # =========================================================================
    # LOAD CSV - Index Creation
    # =========================================================================

    async def _create_indexes_for_edges(
        self,
        node_definitions: list[NodeDefinition],
    ) -> None:
        """Create indexes on node primary keys for fast edge loading.

        PERFORMANCE IMPACT:
        - Without indexes: Edge MATCH is O(N) per lookup → O(N²) total
        - With indexes: Edge MATCH is O(log N) per lookup → O(N log N) total
        - For 1M nodes × 1M edges: hours vs seconds

        This method MUST be called after loading all nodes and BEFORE
        loading any edges.

        Args:
            node_definitions: All node definitions from mapping
        """
        logger.info(
            "creating_indexes_for_edge_loading",
            node_count=len(node_definitions),
        )

        for node_def in node_definitions:
            pk_name = node_def.primary_key.name
            label = node_def.label

            index_query = f"CREATE INDEX ON :{label}({pk_name})"

            try:
                await self.execute_query(index_query, timeout_ms=120_000)
                logger.info(
                    "index_created",
                    label=label,
                    primary_key=pk_name,
                )

            except Exception as e:
                error_msg = str(e).lower()

                # Index already exists - not an error
                if "already exists" in error_msg or "already indexed" in error_msg:
                    logger.debug(
                        "index_already_exists",
                        label=label,
                        primary_key=pk_name,
                    )
                    continue

                # Syntax error - code bug, fatal
                if "syntax" in error_msg:
                    raise DataLoadError(
                        f"Index creation syntax error for {label}({pk_name}): {e}",
                        details={"label": label, "primary_key": pk_name, "error": str(e)},
                    ) from e

                # Connection/timeout errors - fatal
                if any(x in error_msg for x in ["connection", "timeout", "refused"]):
                    raise DataLoadError(
                        f"Fatal error during index creation: {e}",
                        details={"label": label, "primary_key": pk_name, "error": str(e)},
                    ) from e

                # Unknown error - warn but continue
                # Edge loading will just be slower
                logger.warning(
                    "index_creation_failed",
                    label=label,
                    primary_key=pk_name,
                    error=str(e),
                    impact="Edge loading may be slower",
                )

    # =========================================================================
    # LOAD CSV - Validation & Warnings
    # =========================================================================

    async def _validate_data_load(
        self,
        entity_name: str,
        entity_type: str,  # "node" or "edge"
        expected_rows: int,
        actual_rows: int,
        min_success_rate: float | None = None,
    ) -> None:
        """Validate data load and create warning or raise error.

        Philosophy: Partial data is useful. Minor mismatches should warn,
        not fail. But catastrophic data loss should fail the instance.

        Args:
            entity_name: Node label or edge type
            entity_type: "node" or "edge"
            expected_rows: Number of rows in CSV
            actual_rows: Number of entities in graph
            min_success_rate: Override default threshold

        Raises:
            DataLoadError: If success rate below minimum threshold
        """
        if expected_rows == 0:
            return  # Nothing to validate

        success_rate = (actual_rows / expected_rows) * 100
        missing = expected_rows - actual_rows

        # Determine threshold
        if min_success_rate is not None:
            threshold = min_success_rate
        elif entity_type == "edge":
            threshold = self.MIN_EDGE_SUCCESS_RATE
        else:
            threshold = self.MIN_NODE_SUCCESS_RATE

        # Catastrophic failure - instance is unusable
        if success_rate < threshold:
            raise DataLoadError(
                f"Catastrophic data loss for {entity_type} '{entity_name}': "
                f"only {actual_rows}/{expected_rows} loaded ({success_rate:.1f}%). "
                f"Minimum required: {threshold}%",
                details={
                    "entity_name": entity_name,
                    "entity_type": entity_type,
                    "expected": expected_rows,
                    "actual": actual_rows,
                    "success_rate_percent": round(success_rate, 2),
                    "threshold_percent": threshold,
                },
            )

        # Mismatch but acceptable - create warning
        if actual_rows != expected_rows:
            self._add_data_load_warning(
                warning_type="row_count_mismatch",
                entity=entity_name,
                entity_type=entity_type,
                expected=expected_rows,
                actual=actual_rows,
                message=(
                    f"{missing} {entity_type}(s) failed to load "
                    f"({success_rate:.2f}% success rate)"
                    if entity_type == "node"
                    else f"{missing} edge(s) skipped "
                    f"(likely missing source/target nodes, "
                    f"{success_rate:.2f}% success rate)"
                ),
            )

    def _add_data_load_warning(
        self,
        warning_type: str,
        entity: str,
        entity_type: str,
        expected: int,
        actual: int,
        message: str,
    ) -> None:
        """Add a data load warning to the warning list.

        Warnings are exposed via the /status endpoint but do NOT
        prevent the instance from becoming ready.

        Args:
            warning_type: Type of warning (e.g., "row_count_mismatch")
            entity: Entity name (node label or edge type)
            entity_type: "node" or "edge"
            expected: Expected count
            actual: Actual count
            message: Human-readable message
        """
        missing = expected - actual
        success_rate = (actual / expected * 100) if expected > 0 else 0

        warning = {
            "type": warning_type,
            "entity": entity,
            "entity_type": entity_type,
            "expected": expected,
            "actual": actual,
            "missing": missing,
            "success_rate_percent": round(success_rate, 4),
            "severity": "warning",
            "message": message,
        }

        self._data_load_warnings.append(warning)

        logger.warning(
            "data_load_warning",
            **warning,
        )

    def get_data_load_warnings(self) -> list[dict[str, Any]]:
        """Get all data load warnings.

        Returns:
            Copy of warnings list (safe to modify)
        """
        return self._data_load_warnings.copy()

    def clear_data_load_warnings(self) -> None:
        """Clear all data load warnings."""
        self._data_load_warnings.clear()

    # =========================================================================
    # Batch Loading - Main Orchestration
    # =========================================================================

    async def load_data(
        self,
        gcs_base_path: str,
        mapping: InstanceMappingResponse,
        gcs_client: Any,
        control_plane_client: Any,
    ) -> None:
        """Load all data from GCS Parquet files into FalkorDB.

        Uses UNWIND batch loading for ~200k+ rows/sec performance.
        This approach bypasses FalkorDBLite's file access limitations
        (the Redis subprocess cannot access local files via LOAD CSV).

        Execution Order (CRITICAL for correctness):
        1. Load all nodes (no dependencies)
        2. Create indexes on primary keys (for edge performance)
        3. Load all edges (depends on nodes existing)
        4. Report completion

        Args:
            gcs_base_path: GCS path prefix (gs://bucket/snapshot-123)
            mapping: Mapping definition with nodes and edges
            gcs_client: GCS client for downloading Parquet files
            control_plane_client: Control Plane client for status updates

        Raises:
            DataLoadError: If any catastrophic failure occurs

        Note:
            This follows the Ryugraph wrapper pattern (ADR-049): data loading
            as a method on DatabaseService, not a separate service class.
        """
        logger.info(
            "starting_data_load",
            gcs_base_path=gcs_base_path,
            node_count=len(mapping.node_definitions),
            edge_count=len(mapping.edge_definitions),
            method="UNWIND batch",
        )

        # Set memory limit (80% of available)
        available = psutil.virtual_memory().available
        memory_limit_bytes = int(available * 0.8)

        logger.info(
            "memory_limit_set",
            memory_limit_mb=round(memory_limit_bytes / (1024 * 1024), 2),
        )

        start_time = time.time()

        try:
            # Clear any warnings from previous load attempts
            self.clear_data_load_warnings()

            # ─────────────────────────────────────────────────────────────
            # PHASE 1: Load all nodes
            # ─────────────────────────────────────────────────────────────
            logger.info(
                "phase_1_loading_nodes",
                node_count=len(mapping.node_definitions),
            )

            for idx, node_def in enumerate(mapping.node_definitions, 1):
                await self._load_nodes_with_batch(
                    node_def=node_def,
                    gcs_base_path=gcs_base_path,
                    gcs_client=gcs_client,
                    memory_limit_bytes=memory_limit_bytes,
                )

                # Report progress
                if control_plane_client:
                    await control_plane_client.update_progress(
                        phase="loading_nodes",
                        current=idx,
                        total=len(mapping.node_definitions),
                    )

            # ─────────────────────────────────────────────────────────────
            # PHASE 2: Create indexes for edge performance
            # ─────────────────────────────────────────────────────────────
            logger.info("phase_2_creating_indexes")

            await self._create_indexes_for_edges(mapping.node_definitions)

            # ─────────────────────────────────────────────────────────────
            # PHASE 3: Load all edges
            # ─────────────────────────────────────────────────────────────
            logger.info(
                "phase_3_loading_edges",
                edge_count=len(mapping.edge_definitions),
            )

            for idx, edge_def in enumerate(mapping.edge_definitions, 1):
                await self._load_edges_with_batch(
                    edge_def=edge_def,
                    gcs_base_path=gcs_base_path,
                    gcs_client=gcs_client,
                    node_definitions=mapping.node_definitions,
                    memory_limit_bytes=memory_limit_bytes,
                )

                # Report progress
                if control_plane_client:
                    await control_plane_client.update_progress(
                        phase="loading_edges",
                        current=idx,
                        total=len(mapping.edge_definitions),
                    )

            # ─────────────────────────────────────────────────────────────
            # PHASE 4: Complete
            # ─────────────────────────────────────────────────────────────
            duration = time.time() - start_time
            warnings = self.get_data_load_warnings()

            logger.info(
                "data_load_complete",
                nodes_loaded=len(mapping.node_definitions),
                edges_loaded=len(mapping.edge_definitions),
                warning_count=len(warnings),
                duration_seconds=round(duration, 2),
            )

            if warnings:
                logger.warning(
                    "data_load_completed_with_warnings",
                    warnings=warnings,
                )

        except DataLoadError:
            # Already logged, re-raise for instance failure
            raise

        except Exception as e:
            logger.error(
                "data_load_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            raise DataLoadError(
                f"Data loading failed: {e}",
                details={"error": str(e), "error_type": type(e).__name__},
            ) from e

    async def _load_nodes_with_batch(
        self,
        node_def: NodeDefinition,
        gcs_base_path: str,
        gcs_client: Any,
        memory_limit_bytes: int,
    ) -> None:
        """Load node data from GCS using UNWIND batch loading.

        Performance: ~200,000+ rows/sec using parameter batching.
        This approach bypasses FalkorDBLite's file access limitations.

        Args:
            node_def: Node definition with label, primary_key, properties
            gcs_base_path: GCS base path
            gcs_client: GCS client for downloading
            memory_limit_bytes: Memory threshold for monitoring
        """
        gcs_prefix = f"{gcs_base_path}/nodes/{node_def.label}/"

        try:
            # Step 1: Download Parquet files from GCS
            parquet_dir = Path(f"/tmp/nodes_{node_def.label}")
            logger.info("downloading_node_parquet_directory", label=node_def.label, gcs_prefix=gcs_prefix)
            parquet_dir.mkdir(parents=True, exist_ok=True)

            gcs_files = await gcs_client.list_files(gcs_prefix)
            gcs_files = [f for f in gcs_files if not f.endswith("/")]

            if not gcs_files:
                logger.warning("no_parquet_files_found", label=node_def.label, gcs_prefix=gcs_prefix)
                return

            logger.info("found_parquet_files", label=node_def.label, file_count=len(gcs_files))
            for gcs_file in gcs_files:
                filename = Path(gcs_file).name
                local_file = parquet_dir / filename
                await gcs_client.download_file(gcs_file, local_file)

            # Step 2: Build UNWIND query for this node type
            query = self._build_unwind_query_for_nodes(node_def)

            logger.info(
                "loading_nodes_with_unwind",
                label=node_def.label,
                batch_size=BATCH_SIZE,
            )

            # Step 3: Read Parquet and load in batches
            load_start = time.time()
            total_rows = 0
            batches_processed = 0

            async for batch, expected_rows in ParquetReader.read_batches(
                parquet_dir, batch_size=BATCH_SIZE
            ):
                await self.execute_query(
                    query,
                    parameters={"nodes": batch},
                    timeout_ms=5 * 60 * 1000,  # 5 min per batch
                )
                batches_processed += 1
                total_rows = expected_rows  # Last value is the total

                # Log progress every 10 batches
                if batches_processed % 10 == 0:
                    logger.debug(
                        "node_batch_progress",
                        label=node_def.label,
                        batches=batches_processed,
                    )

            load_duration = time.time() - load_start

            if total_rows == 0:
                logger.warning(
                    "empty_node_file",
                    label=node_def.label,
                    message="Parquet has 0 rows, skipping load",
                )
                return

            # Step 4: Validate row count
            count_result = await self.execute_query(
                f"MATCH (n:{node_def.label}) RETURN count(n) as cnt"
            )
            actual_rows = count_result["rows"][0][0]

            # Step 5: Check for catastrophic failure or warning
            await self._validate_data_load(
                entity_name=node_def.label,
                entity_type="node",
                expected_rows=total_rows,
                actual_rows=actual_rows,
            )

            rows_per_sec = round(actual_rows / load_duration) if load_duration > 0 else 0
            logger.info(
                "batch_load_nodes_complete",
                label=node_def.label,
                expected=total_rows,
                actual=actual_rows,
                batches=batches_processed,
                duration_seconds=round(load_duration, 2),
                rows_per_second=rows_per_sec,
            )

            # Step 6: Check memory
            await self._check_memory(memory_limit_bytes)

        except DataLoadError:
            raise
        except Exception as e:
            raise DataLoadError(
                f"Failed to load node table '{node_def.label}': {e}",
                table_name=node_def.label,
                gcs_path=gcs_prefix,
            ) from e
        finally:
            shutil.rmtree(parquet_dir, ignore_errors=True)

    async def _load_edges_with_batch(
        self,
        edge_def: EdgeDefinition,
        gcs_base_path: str,
        gcs_client: Any,
        node_definitions: list[NodeDefinition],
        memory_limit_bytes: int,
    ) -> None:
        """Load edge data from GCS using UNWIND batch loading.

        Performance: ~50,000+ rows/sec using parameter batching.
        This approach bypasses FalkorDBLite's file access limitations.

        IMPORTANT: Indexes must be created on node primary keys BEFORE
        calling this method, otherwise performance is O(N²).

        Args:
            edge_def: Edge definition with type, from/to nodes, properties
            gcs_base_path: GCS base path
            gcs_client: GCS client for downloading
            node_definitions: All node definitions (for primary key lookup)
            memory_limit_bytes: Memory threshold for monitoring
        """
        gcs_prefix = f"{gcs_base_path}/edges/{edge_def.type}/"

        try:
            # Step 1: Download Parquet files from GCS
            parquet_dir = Path(f"/tmp/edges_{edge_def.type}")
            logger.info("downloading_edge_parquet_directory", edge_type=edge_def.type, gcs_prefix=gcs_prefix)
            parquet_dir.mkdir(parents=True, exist_ok=True)

            gcs_files = await gcs_client.list_files(gcs_prefix)
            gcs_files = [f for f in gcs_files if not f.endswith("/")]

            if not gcs_files:
                logger.warning("no_parquet_files_found", edge_type=edge_def.type, gcs_prefix=gcs_prefix)
                return

            logger.info("found_parquet_files", edge_type=edge_def.type, file_count=len(gcs_files))
            for gcs_file in gcs_files:
                filename = Path(gcs_file).name
                local_file = parquet_dir / filename
                await gcs_client.download_file(gcs_file, local_file)

            # Step 2: Build UNWIND query for this edge type
            query = self._build_unwind_query_for_edges(edge_def, node_definitions)

            logger.info(
                "loading_edges_with_unwind",
                edge_type=edge_def.type,
                batch_size=BATCH_SIZE,
            )

            # Step 3: Read Parquet and load in batches
            load_start = time.time()
            total_rows = 0
            batches_processed = 0

            async for batch, expected_rows in ParquetReader.read_batches(
                parquet_dir, batch_size=BATCH_SIZE
            ):
                await self.execute_query(
                    query,
                    parameters={"edges": batch},
                    timeout_ms=5 * 60 * 1000,  # 5 min per batch
                )
                batches_processed += 1
                total_rows = expected_rows

                # Log progress every 10 batches
                if batches_processed % 10 == 0:
                    logger.debug(
                        "edge_batch_progress",
                        edge_type=edge_def.type,
                        batches=batches_processed,
                    )

            load_duration = time.time() - load_start

            if total_rows == 0:
                logger.warning(
                    "empty_edge_file",
                    edge_type=edge_def.type,
                    message="Parquet has 0 rows, skipping load",
                )
                return

            # Step 4: Validate row count
            count_result = await self.execute_query(
                f"MATCH ()-[r:{edge_def.type}]->() RETURN count(r) as cnt"
            )
            actual_rows = count_result["rows"][0][0]

            # Step 5: Check for catastrophic failure or warning
            await self._validate_data_load(
                entity_name=edge_def.type,
                entity_type="edge",
                expected_rows=total_rows,
                actual_rows=actual_rows,
            )

            rows_per_sec = round(actual_rows / load_duration) if load_duration > 0 else 0
            logger.info(
                "batch_load_edges_complete",
                edge_type=edge_def.type,
                expected=total_rows,
                actual=actual_rows,
                skipped=total_rows - actual_rows,
                batches=batches_processed,
                duration_seconds=round(load_duration, 2),
                rows_per_second=rows_per_sec,
            )

            # Step 6: Check memory
            await self._check_memory(memory_limit_bytes)

        except DataLoadError:
            raise
        except Exception as e:
            raise DataLoadError(
                f"Failed to load edge table '{edge_def.type}': {e}",
                table_name=edge_def.type,
                gcs_path=gcs_prefix,
            ) from e
        finally:
            shutil.rmtree(parquet_dir, ignore_errors=True)

    async def _check_memory(self, memory_limit_bytes: int) -> None:
        """Check memory usage and raise if exceeding limit."""
        from wrapper.exceptions import OutOfMemoryError

        process = psutil.Process()
        memory_bytes = process.memory_info().rss

        if memory_bytes > memory_limit_bytes:
            memory_mb = round(memory_bytes / (1024 * 1024), 2)
            limit_mb = round(memory_limit_bytes / (1024 * 1024), 2)

            logger.error(
                "memory_limit_exceeded",
                memory_mb=memory_mb,
                limit_mb=limit_mb,
            )

            raise OutOfMemoryError(
                memory_limit_bytes=memory_limit_bytes,
                current_usage_bytes=memory_bytes,
            )

    async def close(self) -> None:
        """Close database connection and clean up resources."""
        if not self._is_initialized:
            logger.debug("database_not_initialized_skipping_close")
            return

        logger.info("closing_database", graph_name=self._graph_name)

        try:
            if self._db is not None:
                await self._db.close()

            self._graph = None
            self._db = None
            self._is_initialized = False
            self._is_ready = False
            self._ready_at = None

            logger.info("database_closed")

        except Exception as e:
            logger.error("database_close_failed", error=str(e), error_type=type(e).__name__)
