"""Database service for Ryugraph operations.

Manages the embedded Ryugraph (KuzuDB fork) database, including:
- Database initialization and connection management
- Schema creation from mapping definitions
- Data loading from GCS Parquet files
- Query execution with timeout support
- Schema introspection and statistics
"""

from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING, Any

from graph_olap_schemas import InstanceMappingResponse

from wrapper.exceptions import (
    DatabaseError,
    DataLoadError,
    QueryError,
    QueryTimeoutError,
    SchemaCreationError,
    StartupError,
)
from wrapper.logging import get_logger
from wrapper.utils.ddl import (
    generate_edge_ddl,
    generate_node_ddl,
    get_edge_gcs_subpath,
    get_node_gcs_subpath,
)

if TYPE_CHECKING:
    pass

# Conditional import for Ryugraph
try:
    import ryugraph

    RYUGRAPH_AVAILABLE = True
except ImportError:
    ryugraph = None  # type: ignore[assignment]
    RYUGRAPH_AVAILABLE = False

logger = get_logger(__name__)

# Default query timeout (60 seconds)
DEFAULT_QUERY_TIMEOUT_MS = 60_000


class DatabaseService:
    """Manages the embedded Ryugraph database.

    Provides async interface to the synchronous Ryugraph operations
    using a thread pool executor. Handles database lifecycle, schema
    management, and query execution.
    """

    def __init__(
        self,
        database_path: str,
        buffer_pool_size: int = 2 * 1024 * 1024 * 1024,  # 2GB default
        max_threads: int = 16,
        read_only: bool = False,
    ) -> None:
        """Initialize the database service.

        Args:
            database_path: Path to the Ryugraph database directory.
            buffer_pool_size: Buffer pool size in bytes.
            max_threads: Maximum threads for query execution.
            read_only: Whether to open database in read-only mode.

        Raises:
            StartupError: If Ryugraph is not installed.
        """
        if not RYUGRAPH_AVAILABLE:
            raise StartupError("Ryugraph is not installed. Install with: pip install ryugraph")

        self._database_path = database_path
        self._buffer_pool_size = buffer_pool_size
        self._max_threads = max_threads
        self._read_only = read_only

        self._db: ryugraph.Database | None = None
        self._connection: ryugraph.Connection | None = None
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ryugraph")
        self._is_initialized = False
        self._is_ready = False

        logger.info(
            "DatabaseService created",
            database_path=database_path,
            buffer_pool_size=buffer_pool_size,
            max_threads=max_threads,
            read_only=read_only,
        )

    @property
    def is_initialized(self) -> bool:
        """Check if database has been initialized."""
        return self._is_initialized

    @property
    def is_ready(self) -> bool:
        """Check if database is ready for queries."""
        return self._is_ready

    async def initialize(self) -> None:
        """Initialize the database.

        Ensures the parent directory exists and opens the Ryugraph database.
        Note: Ryugraph requires the database path to NOT exist - it creates
        the database directory itself.

        Must be called before any other operations.

        Raises:
            DatabaseError: If initialization fails.
        """
        if self._is_initialized:
            logger.warning("Database already initialized, skipping")
            return

        try:
            # Ensure parent directory exists, but NOT the database directory itself
            # Ryugraph requires the database path to NOT exist - it creates it
            db_path = Path(self._database_path)
            db_path.parent.mkdir(parents=True, exist_ok=True)

            # Initialize database in thread pool
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(self._executor, self._init_database)

            self._is_initialized = True
            logger.info("Database initialized successfully")

        except Exception as e:
            logger.error("Failed to initialize database", error=str(e))
            raise DatabaseError(f"Failed to initialize database: {e}") from e

    def _init_database(self) -> None:
        """Initialize database (blocking, run in executor)."""
        self._db = ryugraph.Database(
            self._database_path,
            buffer_pool_size=self._buffer_pool_size,
            max_num_threads=self._max_threads,
            read_only=self._read_only,
        )
        self._connection = ryugraph.Connection(self._db)
        logger.debug("Ryugraph database and connection created")

        # Algo extension is baked into the Docker image at build time (ADR-138).
        # No network call, no extension server pod required.
        try:
            logger.info("Loading algo extension from local cache")
            self._connection.execute("LOAD algo")
            logger.info("Algo extension loaded successfully")
        except Exception as e:
            logger.error(
                "Failed to load algo extension - native algorithms will not work",
                error=str(e),
                error_type=type(e).__name__,
            )

    async def create_schema(self, mapping: InstanceMappingResponse) -> None:
        """Create database schema from mapping definition.

        Creates node and edge tables based on the mapping definition.
        Uses utility functions to generate DDL from shared schema types.

        Args:
            mapping: The mapping response from Control Plane (shared schema type).

        Raises:
            DatabaseError: If schema creation fails.
        """
        if not self._is_initialized:
            raise DatabaseError("Database not initialized")

        try:
            loop = asyncio.get_running_loop()

            # Create node tables first
            for node_def in mapping.node_definitions:
                stmt = generate_node_ddl(node_def)
                logger.debug("Creating node table", label=node_def.label, statement=stmt)
                await loop.run_in_executor(self._executor, self._execute_ddl, stmt)

            # Then create edge tables (depend on node tables)
            for edge_def in mapping.edge_definitions:
                stmt = generate_edge_ddl(edge_def)
                logger.debug(
                    "Creating edge table",
                    type=edge_def.type,
                    from_node=edge_def.from_node,
                    to_node=edge_def.to_node,
                    statement=stmt,
                )
                await loop.run_in_executor(self._executor, self._execute_ddl, stmt)

            logger.info(
                "Schema created",
                node_tables=len(mapping.node_definitions),
                edge_tables=len(mapping.edge_definitions),
            )

        except Exception as e:
            logger.error("Failed to create schema", error=str(e))
            raise SchemaCreationError(f"Failed to create schema: {e}") from e

    def _execute_ddl(self, statement: str) -> None:
        """Execute DDL statement (blocking, run in executor)."""
        if self._connection is None:
            raise DatabaseError("No database connection")
        self._connection.execute(statement)

    async def load_data(
        self,
        mapping: InstanceMappingResponse,
        gcs_base_path: str | None = None,
        progress_callback: Any | None = None,
    ) -> dict[str, int]:
        """Load data from GCS Parquet files into the database.

        Downloads Parquet files via the Python google-cloud-storage client
        (which supports GKE Workload Identity, service account keys, and
        STORAGE_EMULATOR_HOST for fake-gcs-server), then COPYs them from
        local paths into Ryugraph.

        Args:
            mapping: The mapping response from Control Plane (shared schema type).
            gcs_base_path: Base GCS path. If None, uses mapping.gcs_path.
            progress_callback: Optional callback for progress updates.

        Returns:
            Dict with counts: {"nodes": X, "edges": Y}

        Raises:
            DatabaseError: If data loading fails.
        """
        import os

        # Use gcs_path from mapping if not provided
        if gcs_base_path is None:
            gcs_base_path = mapping.gcs_path
        if not self._is_initialized:
            raise DatabaseError("Database not initialized")

        try:
            if not gcs_base_path.startswith("gs://"):
                raise DatabaseError(f"Invalid GCS path: {gcs_base_path}")

            storage_emulator_host = os.environ.get("STORAGE_EMULATOR_HOST")
            if storage_emulator_host:
                logger.info(
                    "Loading data via GCS emulator",
                    emulator_host=storage_emulator_host,
                    gcs_path=gcs_base_path,
                )
            else:
                logger.info(
                    "Loading data from GCS",
                    gcs_path=gcs_base_path,
                )

            return await self._load_data_via_download(
                mapping, gcs_base_path, progress_callback
            )

        except DatabaseError:
            raise
        except Exception as e:
            logger.error("Failed to load data", error=str(e))
            raise DataLoadError(f"Failed to load data: {e}") from e

    async def _load_data_via_download(
        self,
        mapping: InstanceMappingResponse,
        gcs_base_path: str,
        progress_callback: Any | None = None,
    ) -> dict[str, int]:
        """Local/E2E mode: Download from GCS emulator, then load locally.

        GCS emulators (fake-gcs-server, storage-testbench) only implement
        the JSON API, not the S3 interoperability mode that Ryugraph requires.
        So we download files using the Python GCS client (which supports
        STORAGE_EMULATOR_HOST), then load from local filesystem.

        Ryugraph still parallelizes reading within the local Parquet files.
        """
        import shutil
        import tempfile

        from google.cloud import storage

        loop = asyncio.get_running_loop()
        total_nodes = 0
        total_edges = 0

        # Parse bucket and prefix from gcs_base_path
        # Format: gs://bucket/prefix/...
        path_without_scheme = gcs_base_path[5:]  # Remove "gs://"
        parts = path_without_scheme.split("/", 1)
        bucket_name = parts[0]
        base_prefix = parts[1] if len(parts) > 1 else ""
        if base_prefix and not base_prefix.endswith("/"):
            base_prefix += "/"

        # Create GCS client (will use STORAGE_EMULATOR_HOST automatically)
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)

        # Create temporary directory for downloaded files
        temp_base_dir = tempfile.mkdtemp(prefix="ryugraph_data_")
        logger.info("Created temp directory for downloads", temp_dir=temp_base_dir)

        try:
            # Load node data - nodes must be loaded before edges
            for i, node_def in enumerate(mapping.node_definitions):
                gcs_subpath = get_node_gcs_subpath(node_def).rstrip("/")
                gcs_prefix = f"{base_prefix}{gcs_subpath}/"

                # Create local directory for this node type
                local_dir = Path(temp_base_dir) / "nodes" / node_def.label
                local_dir.mkdir(parents=True, exist_ok=True)

                # Download all files from this prefix
                logger.info(
                    "Downloading node data from GCS emulator",
                    label=node_def.label,
                    gcs_prefix=gcs_prefix,
                    local_dir=str(local_dir),
                )

                blobs = list(bucket.list_blobs(prefix=gcs_prefix))
                file_count = 0
                for blob in blobs:
                    # Skip directory markers
                    if blob.name.endswith("/") or blob.size == 0:
                        continue

                    # Extract filename from blob path
                    filename = blob.name.split("/")[-1]
                    local_path = local_dir / filename

                    blob.download_to_filename(str(local_path))
                    file_count += 1

                logger.info(
                    "Downloaded node files",
                    label=node_def.label,
                    file_count=file_count,
                )

                if file_count == 0:
                    logger.warning(
                        "No files found for node type",
                        label=node_def.label,
                        gcs_prefix=gcs_prefix,
                    )
                    continue

                # Load from local directory using glob pattern
                # Explicitly specify parquet format since Trino CTAS files have no extension
                copy_stmt = f"COPY {node_def.label} FROM '{local_dir}/*' (file_format='parquet', IGNORE_ERRORS=true)"

                result = await loop.run_in_executor(
                    self._executor, self._execute_copy, copy_stmt
                )

                if result is not None:
                    total_nodes += result

                logger.info("Node data loaded", label=node_def.label, rows=result)

                if progress_callback:
                    await progress_callback(
                        stage="loading_nodes",
                        current=i + 1,
                        total=len(mapping.node_definitions),
                        label=node_def.label,
                    )

            # Load edge data - edges reference node PKs so must come after nodes
            for i, edge_def in enumerate(mapping.edge_definitions):
                gcs_subpath = get_edge_gcs_subpath(edge_def).rstrip("/")
                gcs_prefix = f"{base_prefix}{gcs_subpath}/"

                # Create local directory for this edge type
                local_dir = Path(temp_base_dir) / "edges" / edge_def.type
                local_dir.mkdir(parents=True, exist_ok=True)

                # Download all files from this prefix
                logger.info(
                    "Downloading edge data from GCS emulator",
                    type=edge_def.type,
                    gcs_prefix=gcs_prefix,
                    local_dir=str(local_dir),
                )

                blobs = list(bucket.list_blobs(prefix=gcs_prefix))
                file_count = 0
                for blob in blobs:
                    # Skip directory markers
                    if blob.name.endswith("/") or blob.size == 0:
                        continue

                    # Extract filename from blob path
                    filename = blob.name.split("/")[-1]
                    local_path = local_dir / filename

                    blob.download_to_filename(str(local_path))
                    file_count += 1

                logger.info(
                    "Downloaded edge files",
                    type=edge_def.type,
                    file_count=file_count,
                )

                if file_count == 0:
                    logger.warning(
                        "No files found for edge type",
                        type=edge_def.type,
                        gcs_prefix=gcs_prefix,
                    )
                    continue

                # Load from local directory using glob pattern
                # Explicitly specify parquet format since Trino CTAS files have no extension
                copy_stmt = f"COPY {edge_def.type} FROM '{local_dir}/*' (file_format='parquet', IGNORE_ERRORS=true)"

                result = await loop.run_in_executor(
                    self._executor, self._execute_copy, copy_stmt
                )

                if result is not None:
                    total_edges += result

                logger.info("Edge data loaded", type=edge_def.type, rows=result)

                if progress_callback:
                    await progress_callback(
                        stage="loading_edges",
                        current=i + 1,
                        total=len(mapping.edge_definitions),
                        type=edge_def.type,
                    )

            self._is_ready = True
            logger.info(
                "Data loading complete (via download)",
                total_nodes=total_nodes,
                total_edges=total_edges,
            )

            return {"nodes": total_nodes, "edges": total_edges}

        finally:
            # Clean up temporary directory
            try:
                shutil.rmtree(temp_base_dir)
                logger.debug("Cleaned up temp directory", temp_dir=temp_base_dir)
            except Exception as e:
                logger.warning(
                    "Failed to clean up temp directory",
                    temp_dir=temp_base_dir,
                    error=str(e),
                )

    def _execute_copy(self, statement: str) -> int:
        """Execute COPY statement and return row count (blocking)."""
        if self._connection is None:
            raise DatabaseError("No database connection")

        result = self._connection.execute(statement)
        # Try to extract row count from result
        try:
            # Ryugraph may return affected rows differently
            return result.get_num_tuples() if hasattr(result, "get_num_tuples") else 0
        except Exception:
            return 0

    async def execute_query(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
        timeout_ms: int | None = None,
    ) -> dict[str, Any]:
        """Execute a Cypher query.

        Args:
            query: Cypher query string.
            parameters: Optional query parameters.
            timeout_ms: Query timeout in milliseconds (default: 60000).

        Returns:
            Dict containing:
                - columns: List of column names
                - rows: List of row data
                - row_count: Number of rows
                - execution_time_ms: Execution time in milliseconds

        Raises:
            QueryError: If query execution fails.
            QueryTimeoutError: If query times out.
        """
        if not self._is_initialized:
            raise QueryError("Database not initialized")

        timeout_ms = timeout_ms or DEFAULT_QUERY_TIMEOUT_MS
        timeout_seconds = timeout_ms / 1000

        start_time = time.perf_counter()

        try:
            loop = asyncio.get_running_loop()

            # Execute with timeout
            future = loop.run_in_executor(
                self._executor,
                self._execute_query_sync,
                query,
                parameters or {},
            )

            result = await asyncio.wait_for(future, timeout=timeout_seconds)

            execution_time_ms = int((time.perf_counter() - start_time) * 1000)

            logger.debug(
                "Query executed",
                query=query[:100] + "..." if len(query) > 100 else query,
                row_count=result["row_count"],
                execution_time_ms=execution_time_ms,
            )

            return {
                **result,
                "execution_time_ms": execution_time_ms,
            }

        except TimeoutError as e:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            logger.warning(
                "Query timed out",
                query=query[:100] + "..." if len(query) > 100 else query,
                timeout_ms=timeout_ms,
                elapsed_ms=elapsed_ms,
            )
            raise QueryTimeoutError(timeout_ms=timeout_ms, elapsed_ms=elapsed_ms) from e

        except Exception as e:
            logger.error(
                "Query execution failed",
                query=query[:100] + "..." if len(query) > 100 else query,
                error=str(e),
            )
            raise QueryError(f"Query execution failed: {e}") from e

    def _execute_query_sync(
        self,
        query: str,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute query synchronously (run in executor)."""
        if self._connection is None:
            raise QueryError("No database connection")

        # Execute query with parameters
        if parameters:
            result = self._connection.execute(query, parameters)
        else:
            result = self._connection.execute(query)

        # Extract columns and rows
        columns: list[str] = []
        rows: list[list[Any]] = []

        # Get column names from result
        if hasattr(result, "get_column_names"):
            columns = result.get_column_names()
        elif hasattr(result, "column_names"):
            columns = list(result.column_names)

        # Get rows using row-by-row iteration
        # Note: get_as_pl() has known issues with certain kuzu versions returning
        # empty DataFrames even when data exists, so we use has_next/get_next directly
        while result.has_next():
            rows.append(list(result.get_next()))

        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "truncated": False,
        }

    async def ensure_property_exists(
        self,
        table_name: str,
        property_name: str,
        property_type: str = "DOUBLE",
        default_value: str = "0.0",
    ) -> None:
        """Ensure a property exists on a table, creating it if needed.

        Uses ALTER TABLE to add the property if it doesn't exist.
        This is needed because Kuzu/Ryugraph requires properties to be
        defined in the schema before they can be used in SET operations.

        Args:
            table_name: Name of the node or edge table.
            property_name: Name of the property to ensure exists.
            property_type: Kuzu type (DOUBLE, INT64, STRING, etc.).
            default_value: Default value expression for the property.

        Raises:
            DatabaseError: If the operation fails.
        """
        if not self._is_initialized:
            raise DatabaseError("Database not initialized")

        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                self._executor,
                self._ensure_property_exists_sync,
                table_name,
                property_name,
                property_type,
                default_value,
            )
        except Exception as e:
            logger.error(
                "Failed to ensure property exists",
                table=table_name,
                property=property_name,
                error=str(e),
            )
            raise DatabaseError(f"Failed to ensure property exists: {e}") from e

    def _ensure_property_exists_sync(
        self,
        table_name: str,
        property_name: str,
        property_type: str,
        default_value: str,
    ) -> None:
        """Ensure property exists synchronously (run in executor)."""
        if self._connection is None:
            raise DatabaseError("No database connection")

        # Check if property already exists using table_info
        info_result = self._connection.execute(f"CALL table_info('{table_name}') RETURN *")

        existing_properties: set[str] = set()
        while info_result.has_next():
            row = info_result.get_next()
            # row[1] is the property name
            existing_properties.add(row[1])

        if property_name in existing_properties:
            logger.debug(
                "Property already exists",
                table=table_name,
                property=property_name,
            )
            return

        # Add the property using ALTER TABLE
        # Also add the temporary property for algorithms that need it
        alter_stmt = (
            f"ALTER TABLE {table_name} ADD {property_name} {property_type} DEFAULT {default_value}"
        )
        logger.info(
            "Adding property to table",
            table=table_name,
            property=property_name,
            type=property_type,
        )
        self._connection.execute(alter_stmt)

    async def get_schema(self) -> dict[str, Any]:
        """Get the database schema.

        Returns:
            Dict containing:
                - node_tables: List of node table schemas
                - edge_tables: List of edge table schemas
                - total_nodes: Total node count
                - total_edges: Total edge count

        Raises:
            DatabaseError: If schema retrieval fails.
        """
        if not self._is_initialized:
            raise DatabaseError("Database not initialized")

        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(self._executor, self._get_schema_sync)
        except Exception as e:
            logger.error("Failed to get schema", error=str(e))
            raise DatabaseError(f"Failed to get schema: {e}") from e

    def _get_schema_sync(self) -> dict[str, Any]:
        """Get schema synchronously (run in executor)."""
        if self._connection is None:
            raise DatabaseError("No database connection")

        node_tables: list[dict[str, Any]] = []
        edge_tables: list[dict[str, Any]] = []
        total_nodes = 0
        total_edges = 0

        # Query node tables
        # show_tables() returns: [id, name, type, database_name, comment]
        result = self._connection.execute("CALL show_tables() RETURN *")
        tables = []
        while result.has_next():
            row = result.get_next()
            # row[0] = id (int), row[1] = name, row[2] = type (NODE/REL)
            tables.append({"name": row[1], "type": row[2] if len(row) > 2 else "NODE"})

        for table in tables:
            table_name = table["name"]
            table_type = table["type"]

            # Get table info
            # table_info() returns: [property_id, name, type, default_expr, primary_key]
            info_result = self._connection.execute(f"CALL table_info('{table_name}') RETURN *")

            properties: dict[str, str] = {}
            primary_key = ""
            primary_key_type = ""

            while info_result.has_next():
                row = info_result.get_next()
                # row[0] = property_id (int), row[1] = name, row[2] = type, row[4] = is_pk
                prop_name = row[1]
                prop_type = row[2]
                is_pk = row[4] if len(row) > 4 else False

                properties[prop_name] = prop_type
                if is_pk:
                    primary_key = prop_name
                    primary_key_type = prop_type

            # Get count
            count_result = self._connection.execute(
                f"MATCH (n:{table_name}) RETURN count(n)"
                if table_type == "NODE"
                else f"MATCH ()-[r:{table_name}]->() RETURN count(r)"
            )
            count = 0
            if count_result.has_next():
                count = count_result.get_next()[0]

            if table_type == "NODE":
                node_tables.append(
                    {
                        "label": table_name,
                        "primary_key": primary_key,
                        "primary_key_type": primary_key_type,
                        "properties": properties,
                        "node_count": count,
                    }
                )
                total_nodes += count
            else:
                # Get from/to node types for edges
                edge_tables.append(
                    {
                        "type": table_name,
                        "from_node": "",  # Would need additional introspection
                        "to_node": "",
                        "properties": properties,
                        "edge_count": count,
                    }
                )
                total_edges += count

        return {
            "node_tables": node_tables,
            "edge_tables": edge_tables,
            "total_nodes": total_nodes,
            "total_edges": total_edges,
        }

    async def get_stats(self) -> dict[str, Any]:
        """Get database statistics.

        Returns:
            Dict with node_count, edge_count, and other metrics.

        Raises:
            DatabaseError: If stats retrieval fails.
        """
        if not self._is_initialized:
            raise DatabaseError("Database not initialized")

        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(self._executor, self._get_stats_sync)
        except Exception as e:
            logger.error("Failed to get stats", error=str(e))
            raise DatabaseError(f"Failed to get stats: {e}") from e

    def _get_stats_sync(self) -> dict[str, Any]:
        """Get stats synchronously (run in executor)."""
        if self._connection is None:
            raise DatabaseError("No database connection")

        # Get total node count
        node_result = self._connection.execute("MATCH (n) RETURN count(n)")
        node_count = node_result.get_next()[0] if node_result.has_next() else 0

        # Get total edge count
        edge_result = self._connection.execute("MATCH ()-[r]->() RETURN count(r)")
        edge_count = edge_result.get_next()[0] if edge_result.has_next() else 0

        return {
            "node_count": node_count,
            "edge_count": edge_count,
            "database_path": self._database_path,
            "buffer_pool_size": self._buffer_pool_size,
            "max_threads": self._max_threads,
            "is_ready": self._is_ready,
        }

    async def close(self) -> None:
        """Close the database connection and clean up resources."""
        logger.info("Closing database service")

        try:
            if self._connection is not None:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(self._executor, self._close_sync)
        except Exception as e:
            logger.error("Error closing database", error=str(e))
        finally:
            self._executor.shutdown(wait=False)
            self._is_initialized = False
            self._is_ready = False

        logger.info("Database service closed")

    def _close_sync(self) -> None:
        """Close database synchronously (run in executor)."""
        if self._connection is not None:
            # Ryugraph connections are automatically closed
            self._connection = None
        if self._db is not None:
            self._db.close()
            self._db = None
