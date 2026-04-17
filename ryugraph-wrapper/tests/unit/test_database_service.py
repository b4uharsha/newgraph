"""Unit tests for the DatabaseService."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from graph_olap_schemas import (
    EdgeDefinition,
    InstanceMappingResponse,
    NodeDefinition,
    PrimaryKeyDefinition,
    PropertyDefinition,
)

from wrapper.exceptions import DatabaseError, QueryError, QueryTimeoutError


class TestDatabaseServiceInit:
    """Tests for DatabaseService initialization."""

    @pytest.mark.unit
    def test_init_without_ryugraph_raises_error(self) -> None:
        """Initialization fails when ryugraph is not available."""
        with patch("wrapper.services.database.RYUGRAPH_AVAILABLE", False):
            from wrapper.exceptions import StartupError
            from wrapper.services.database import DatabaseService

            with pytest.raises(StartupError) as exc_info:
                DatabaseService(database_path="/tmp/test_db")

            assert "Ryugraph is not installed" in str(exc_info.value)

    @pytest.mark.unit
    def test_init_with_ryugraph_succeeds(self) -> None:
        """Initialization succeeds when ryugraph is available."""
        with patch("wrapper.services.database.RYUGRAPH_AVAILABLE", True):
            from wrapper.services.database import DatabaseService

            service = DatabaseService(
                database_path="/tmp/test_db",
                buffer_pool_size=1024 * 1024 * 1024,
                max_threads=8,
                read_only=False,
            )

            assert service._database_path == "/tmp/test_db"
            assert service._buffer_pool_size == 1024 * 1024 * 1024
            assert service._max_threads == 8
            assert service._read_only is False
            assert service.is_initialized is False
            assert service.is_ready is False


class TestDatabaseServiceOperations:
    """Tests for DatabaseService operations."""

    @pytest.fixture
    def mock_ryugraph(self) -> MagicMock:
        """Create mock ryugraph module."""
        mock_module = MagicMock()

        # Mock Database class
        mock_db = MagicMock()
        mock_module.Database.return_value = mock_db

        # Mock Connection class
        mock_conn = MagicMock()
        mock_module.Connection.return_value = mock_conn

        return mock_module

    @pytest.fixture
    def database_service(self, mock_ryugraph: MagicMock) -> Any:
        """Create DatabaseService with mocked ryugraph."""
        with patch.dict("sys.modules", {"ryugraph": mock_ryugraph}):
            with patch("wrapper.services.database.RYUGRAPH_AVAILABLE", True):
                with patch("wrapper.services.database.ryugraph", mock_ryugraph):
                    from wrapper.services.database import DatabaseService

                    service = DatabaseService(
                        database_path="/tmp/test_db",
                        buffer_pool_size=128 * 1024 * 1024,
                        max_threads=4,
                    )
                    # Inject mocks
                    service._db = mock_ryugraph.Database.return_value
                    service._connection = mock_ryugraph.Connection.return_value
                    service._is_initialized = True

                    return service

    @pytest.fixture
    def sample_mapping(self) -> InstanceMappingResponse:
        """Create a sample mapping definition for testing.

        Uses InstanceMappingResponse from shared schemas per architectural guardrails.
        """
        return InstanceMappingResponse(
            snapshot_id=1,
            mapping_id=1,
            mapping_version=1,
            gcs_path="gs://test-bucket/test-user/test-mapping/test-snapshot/",
            node_definitions=[
                NodeDefinition(
                    label="Customer",
                    sql="SELECT * FROM customers",
                    primary_key=PrimaryKeyDefinition(name="id", type="STRING"),
                    properties=[
                        PropertyDefinition(name="name", type="STRING"),
                        PropertyDefinition(name="age", type="INT64"),
                    ],
                ),
                NodeDefinition(
                    label="Product",
                    sql="SELECT * FROM products",
                    primary_key=PrimaryKeyDefinition(name="id", type="STRING"),
                    properties=[
                        PropertyDefinition(name="name", type="STRING"),
                        PropertyDefinition(name="price", type="DOUBLE"),
                    ],
                ),
            ],
            edge_definitions=[
                EdgeDefinition(
                    type="PURCHASED",
                    from_node="Customer",
                    to_node="Product",
                    sql="SELECT * FROM purchases",
                    from_key="customer_id",
                    to_key="product_id",
                    properties=[
                        PropertyDefinition(name="amount", type="INT64"),
                    ],
                ),
            ],
        )

    # =========================================================================
    # Initialization Tests
    # =========================================================================

    @pytest.mark.unit
    async def test_initialize_creates_database(
        self, mock_ryugraph: MagicMock, tmp_path: Any
    ) -> None:
        """Initialize creates database directory and opens connection."""
        with patch.dict("sys.modules", {"ryugraph": mock_ryugraph}):
            with patch("wrapper.services.database.RYUGRAPH_AVAILABLE", True):
                with patch("wrapper.services.database.ryugraph", mock_ryugraph):
                    from wrapper.services.database import DatabaseService

                    db_path = str(tmp_path / "test_db")
                    service = DatabaseService(database_path=db_path)

                    await service.initialize()

                    assert service.is_initialized is True
                    mock_ryugraph.Database.assert_called_once()
                    mock_ryugraph.Connection.assert_called_once()

    @pytest.mark.unit
    async def test_initialize_idempotent(self, database_service: Any) -> None:
        """Multiple initialize calls are safe."""
        # Already initialized in fixture
        assert database_service.is_initialized is True

        # Second call should be no-op
        await database_service.initialize()
        assert database_service.is_initialized is True

    # =========================================================================
    # Schema Creation Tests
    # =========================================================================

    @pytest.mark.unit
    async def test_create_schema_creates_tables(
        self, database_service: Any, sample_mapping: InstanceMappingResponse
    ) -> None:
        """create_schema creates node and edge tables."""
        await database_service.create_schema(sample_mapping)

        conn = database_service._connection
        # Should have been called for 2 node tables + 1 edge table = 3 DDL statements
        assert conn.execute.call_count == 3

        # Verify calls include CREATE statements
        calls = [str(call) for call in conn.execute.call_args_list]
        assert any("CREATE NODE TABLE Customer" in str(c) for c in calls)
        assert any("CREATE NODE TABLE Product" in str(c) for c in calls)
        assert any("CREATE REL TABLE PURCHASED" in str(c) for c in calls)

    @pytest.mark.unit
    async def test_create_schema_not_initialized_raises(
        self, mock_ryugraph: MagicMock, sample_mapping: InstanceMappingResponse
    ) -> None:
        """create_schema raises if database not initialized."""
        with patch.dict("sys.modules", {"ryugraph": mock_ryugraph}):
            with patch("wrapper.services.database.RYUGRAPH_AVAILABLE", True):
                with patch("wrapper.services.database.ryugraph", mock_ryugraph):
                    from wrapper.services.database import DatabaseService

                    service = DatabaseService(database_path="/tmp/test")

                    with pytest.raises(DatabaseError) as exc_info:
                        await service.create_schema(sample_mapping)

                    assert "not initialized" in str(exc_info.value)

    # =========================================================================
    # Data Loading Tests
    # =========================================================================

    @pytest.mark.unit
    async def test_load_data_executes_copy_statements(
        self, database_service: Any, sample_mapping: InstanceMappingResponse
    ) -> None:
        """load_data executes COPY statements for all tables."""
        # Setup mock to return a result with get_num_tuples
        mock_result = MagicMock()
        mock_result.get_num_tuples.return_value = 100
        database_service._connection.execute.return_value = mock_result

        # Create mock blobs for each table type
        mock_blob = MagicMock()
        mock_blob.name = "data/test.parquet"
        mock_blob.download_to_filename = MagicMock()

        # Mock GCS storage client to return blobs for COPY operations
        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = [mock_blob]  # Return blob for each table
        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket

        with patch("google.cloud.storage.Client", return_value=mock_storage_client):
            result = await database_service.load_data(
                mapping=sample_mapping,
                gcs_base_path="gs://test-bucket/data",
            )

        # COPY statements executed with mock data
        # Mock execute() returns 100 rows per call (2 nodes + 1 edge)
        assert result["nodes"] == 200  # 100 + 100 from mock
        assert result["edges"] == 100  # 100 from mock

        # Verify ready state
        assert database_service.is_ready is True

    @pytest.mark.unit
    async def test_load_data_with_progress_callback(
        self, database_service: Any, sample_mapping: InstanceMappingResponse
    ) -> None:
        """load_data calls progress callback during loading."""
        mock_result = MagicMock()
        mock_result.get_num_tuples.return_value = 50
        database_service._connection.execute.return_value = mock_result

        progress_calls: list[dict[str, Any]] = []

        async def progress_callback(**kwargs: Any) -> None:
            progress_calls.append(kwargs)

        # Create mock blobs for one node type and one edge type
        mock_blob = MagicMock()
        mock_blob.name = "data/test.parquet"
        mock_blob.download_to_filename = MagicMock()

        mock_bucket = MagicMock()
        # Return one blob for each table type to trigger progress callbacks
        mock_bucket.list_blobs.return_value = [mock_blob]
        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket

        with patch("google.cloud.storage.Client", return_value=mock_storage_client):
            await database_service.load_data(
                mapping=sample_mapping,
                gcs_base_path="gs://test-bucket/data",
                progress_callback=progress_callback,
            )

        # Should have 2 node progress calls + 1 edge progress call
        assert len(progress_calls) == 3

        # Verify progress stages
        node_calls = [p for p in progress_calls if p["stage"] == "loading_nodes"]
        edge_calls = [p for p in progress_calls if p["stage"] == "loading_edges"]
        assert len(node_calls) == 2
        assert len(edge_calls) == 1

    # =========================================================================
    # Query Execution Tests
    # =========================================================================

    @pytest.mark.unit
    async def test_execute_query_returns_results(self, database_service: Any) -> None:
        """execute_query returns query results."""
        # Setup mock result without get_as_pl to use row-by-row fallback
        mock_result = MagicMock(spec=["get_column_names", "has_next", "get_next"])
        mock_result.get_column_names.return_value = ["id", "name"]
        mock_result.has_next.side_effect = [True, True, False]
        mock_result.get_next.side_effect = [["1", "Alice"], ["2", "Bob"]]
        database_service._connection.execute.return_value = mock_result

        result = await database_service.execute_query(
            query="MATCH (n:Customer) RETURN n.id, n.name"
        )

        assert result["columns"] == ["id", "name"]
        assert result["rows"] == [["1", "Alice"], ["2", "Bob"]]
        assert result["row_count"] == 2
        assert "execution_time_ms" in result

    @pytest.mark.unit
    async def test_execute_query_with_parameters(self, database_service: Any) -> None:
        """execute_query passes parameters correctly."""
        mock_result = MagicMock()
        mock_result.get_column_names.return_value = ["name"]
        mock_result.has_next.side_effect = [True, False]
        mock_result.get_next.return_value = ["Alice"]
        database_service._connection.execute.return_value = mock_result

        await database_service.execute_query(
            query="MATCH (n:Customer {id: $id}) RETURN n.name",
            parameters={"id": "1"},
        )

        database_service._connection.execute.assert_called_once_with(
            "MATCH (n:Customer {id: $id}) RETURN n.name",
            {"id": "1"},
        )

    @pytest.mark.unit
    async def test_execute_query_timeout(self, database_service: Any) -> None:
        """execute_query raises QueryTimeoutError on timeout."""
        import time

        # Make execute block synchronously (since it runs in executor)
        def slow_execute(*args: Any, **kwargs: Any) -> None:
            time.sleep(10)

        database_service._connection.execute = slow_execute

        with pytest.raises(QueryTimeoutError) as exc_info:
            await database_service.execute_query(
                query="MATCH (n) RETURN n",
                timeout_ms=100,  # 100ms timeout
            )

        assert exc_info.value.error_code == "QUERY_TIMEOUT"

    @pytest.mark.unit
    async def test_execute_query_not_initialized_raises(self, mock_ryugraph: MagicMock) -> None:
        """execute_query raises if database not initialized."""
        with patch.dict("sys.modules", {"ryugraph": mock_ryugraph}):
            with patch("wrapper.services.database.RYUGRAPH_AVAILABLE", True):
                with patch("wrapper.services.database.ryugraph", mock_ryugraph):
                    from wrapper.services.database import DatabaseService

                    service = DatabaseService(database_path="/tmp/test")

                    with pytest.raises(QueryError) as exc_info:
                        await service.execute_query("MATCH (n) RETURN n")

                    assert "not initialized" in str(exc_info.value)

    @pytest.mark.unit
    async def test_execute_query_error_handling(self, database_service: Any) -> None:
        """execute_query wraps exceptions in QueryError."""
        database_service._connection.execute.side_effect = RuntimeError("Syntax error")

        with pytest.raises(QueryError) as exc_info:
            await database_service.execute_query("INVALID QUERY")

        assert "Syntax error" in str(exc_info.value)

    # =========================================================================
    # Schema Introspection Tests
    # =========================================================================

    @pytest.mark.unit
    async def test_get_schema_returns_tables(self, database_service: Any) -> None:
        """get_schema returns node and edge table information."""
        # Mock show_tables result
        # show_tables() returns: [id, name, type, database_name, comment]
        show_tables_result = MagicMock()
        show_tables_result.has_next.side_effect = [True, True, False]
        show_tables_result.get_next.side_effect = [
            [0, "Customer", "NODE", "default", ""],
            [1, "PURCHASED", "REL", "default", ""],
        ]

        # Mock table_info results
        # table_info() returns: [property_id, name, type, default_expr, primary_key]
        customer_info = MagicMock()
        customer_info.has_next.side_effect = [True, True, False]
        customer_info.get_next.side_effect = [
            [0, "id", "STRING", "", True],
            [1, "name", "STRING", "", False],
        ]

        purchased_info = MagicMock()
        purchased_info.has_next.side_effect = [True, False]
        purchased_info.get_next.side_effect = [
            [0, "amount", "INT64", "", False],
        ]

        # Mock count results
        node_count = MagicMock()
        node_count.has_next.side_effect = [True, False]
        node_count.get_next.return_value = [100]

        edge_count = MagicMock()
        edge_count.has_next.side_effect = [True, False]
        edge_count.get_next.return_value = [500]

        # Setup execute to return different results based on query
        def mock_execute(query: str) -> MagicMock:
            if "show_tables" in query:
                return show_tables_result
            elif "table_info('Customer')" in query:
                return customer_info
            elif "table_info('PURCHASED')" in query:
                return purchased_info
            elif "MATCH (n:Customer)" in query:
                return node_count
            elif "MATCH ()-[r:PURCHASED]->" in query:
                return edge_count
            # Return empty result for any unexpected queries
            empty_result = MagicMock()
            empty_result.has_next.return_value = False
            return empty_result

        database_service._connection.execute.side_effect = mock_execute

        result = await database_service.get_schema()

        assert len(result["node_tables"]) == 1
        assert len(result["edge_tables"]) == 1
        assert result["total_nodes"] == 100
        assert result["total_edges"] == 500

        # Verify node table details
        customer = result["node_tables"][0]
        assert customer["label"] == "Customer"
        assert customer["primary_key"] == "id"
        assert customer["node_count"] == 100

    # =========================================================================
    # Statistics Tests
    # =========================================================================

    @pytest.mark.unit
    async def test_get_stats_returns_counts(self, database_service: Any) -> None:
        """get_stats returns node and edge counts."""
        # Mock count results
        node_count = MagicMock()
        node_count.has_next.return_value = True
        node_count.get_next.return_value = [1000]

        edge_count = MagicMock()
        edge_count.has_next.return_value = True
        edge_count.get_next.return_value = [5000]

        def mock_execute(query: str) -> MagicMock:
            if "MATCH (n)" in query:
                return node_count
            elif "MATCH ()-[r]->" in query:
                return edge_count
            return MagicMock()

        database_service._connection.execute.side_effect = mock_execute

        result = await database_service.get_stats()

        assert result["node_count"] == 1000
        assert result["edge_count"] == 5000
        assert result["database_path"] == "/tmp/test_db"

    # =========================================================================
    # Cleanup Tests
    # =========================================================================

    @pytest.mark.unit
    async def test_close_cleans_up_resources(self, database_service: Any) -> None:
        """close cleans up database and connection."""
        mock_db = database_service._db

        await database_service.close()

        mock_db.close.assert_called_once()
        assert database_service.is_initialized is False
        assert database_service.is_ready is False

    @pytest.mark.unit
    async def test_close_handles_errors(self, database_service: Any) -> None:
        """close handles cleanup errors gracefully."""
        database_service._db.close.side_effect = RuntimeError("Close failed")

        # Should not raise
        await database_service.close()

        assert database_service.is_initialized is False


class TestDatabaseServiceWithPolars:
    """Tests for Polars DataFrame integration."""

    @pytest.fixture
    def database_service_with_polars(self) -> Any:
        """Create DatabaseService with Polars support mocked."""
        mock_module = MagicMock()
        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_module.Database.return_value = mock_db
        mock_module.Connection.return_value = mock_conn

        with patch.dict("sys.modules", {"ryugraph": mock_module}):
            with patch("wrapper.services.database.RYUGRAPH_AVAILABLE", True):
                with patch("wrapper.services.database.ryugraph", mock_module):
                    from wrapper.services.database import DatabaseService

                    service = DatabaseService(database_path="/tmp/test_db")
                    service._db = mock_db
                    service._connection = mock_conn
                    service._is_initialized = True

                    return service

    @pytest.mark.unit
    async def test_execute_query_iterates_results(
        self, database_service_with_polars: Any
    ) -> None:
        """execute_query iterates results using has_next/get_next."""
        # Mock result with row iteration (production code uses has_next/get_next,
        # not get_as_pl, due to known kuzu issues with empty DataFrames)
        mock_result = MagicMock()
        mock_result.get_column_names.return_value = ["id", "value"]

        # Simulate two rows of data
        call_count = [0]
        def has_next_side_effect():
            call_count[0] += 1
            return call_count[0] <= 2  # Return True twice, then False

        mock_result.has_next.side_effect = has_next_side_effect
        mock_result.get_next.side_effect = [[1, 100], [2, 200]]

        database_service_with_polars._connection.execute.return_value = mock_result

        result = await database_service_with_polars.execute_query(
            query="MATCH (n) RETURN n.id, n.value"
        )

        assert result["columns"] == ["id", "value"]
        assert result["rows"] == [[1, 100], [2, 200]]
        assert result["row_count"] == 2


class TestCopyStatementsIncludeIgnoreErrors:
    """Tests that all COPY statements include IGNORE_ERRORS=true (ADR-106 W3-alt-2)."""

    @pytest.fixture
    def mock_ryugraph(self) -> MagicMock:
        """Create mock ryugraph module."""
        mock_module = MagicMock()
        mock_db = MagicMock()
        mock_module.Database.return_value = mock_db
        mock_conn = MagicMock()
        mock_module.Connection.return_value = mock_conn
        return mock_module

    @pytest.fixture
    def database_service(self, mock_ryugraph: MagicMock) -> Any:
        """Create DatabaseService with mocked ryugraph."""
        with patch.dict("sys.modules", {"ryugraph": mock_ryugraph}):
            with patch("wrapper.services.database.RYUGRAPH_AVAILABLE", True):
                with patch("wrapper.services.database.ryugraph", mock_ryugraph):
                    from wrapper.services.database import DatabaseService

                    service = DatabaseService(
                        database_path="/tmp/test_db",
                        buffer_pool_size=128 * 1024 * 1024,
                        max_threads=4,
                    )
                    service._db = mock_ryugraph.Database.return_value
                    service._connection = mock_ryugraph.Connection.return_value
                    service._is_initialized = True

                    return service

    @pytest.fixture
    def sample_mapping(self) -> InstanceMappingResponse:
        """Create a sample mapping for COPY statement verification."""
        return InstanceMappingResponse(
            snapshot_id=1,
            mapping_id=1,
            mapping_version=1,
            gcs_path="gs://test-bucket/test-user/test-mapping/test-snapshot/",
            node_definitions=[
                NodeDefinition(
                    label="Customer",
                    sql="SELECT * FROM customers",
                    primary_key=PrimaryKeyDefinition(name="id", type="STRING"),
                    properties=[
                        PropertyDefinition(name="name", type="STRING"),
                    ],
                ),
            ],
            edge_definitions=[
                EdgeDefinition(
                    type="PURCHASED",
                    from_node="Customer",
                    to_node="Customer",
                    sql="SELECT * FROM purchases",
                    from_key="customer_id",
                    to_key="product_id",
                    properties=[
                        PropertyDefinition(name="amount", type="INT64"),
                    ],
                ),
            ],
        )

    @pytest.mark.unit
    async def test_copy_statements_include_ignore_errors(
        self, database_service: Any, sample_mapping: InstanceMappingResponse
    ) -> None:
        """All COPY statements must include IGNORE_ERRORS=true for resilient loading."""
        mock_result = MagicMock()
        mock_result.get_num_tuples.return_value = 10
        database_service._connection.execute.return_value = mock_result

        mock_blob = MagicMock()
        mock_blob.name = "data/test.parquet"
        mock_blob.download_to_filename = MagicMock()

        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = [mock_blob]
        mock_storage_client = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket

        with patch("google.cloud.storage.Client", return_value=mock_storage_client):
            await database_service.load_data(
                mapping=sample_mapping,
                gcs_base_path="gs://test-bucket/data",
            )

        # Collect all COPY statements from execute calls
        copy_calls = [
            str(call.args[0])
            for call in database_service._connection.execute.call_args_list
            if len(call.args) > 0 and str(call.args[0]).startswith("COPY")
        ]

        assert len(copy_calls) >= 2, f"Expected at least 2 COPY calls, got {len(copy_calls)}"

        for stmt in copy_calls:
            assert "IGNORE_ERRORS=true" in stmt, (
                f"COPY statement missing IGNORE_ERRORS=true: {stmt}"
            )
