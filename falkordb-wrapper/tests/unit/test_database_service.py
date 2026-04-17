"""Unit tests for DatabaseService."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from wrapper.exceptions import (
    DatabaseError,
    DatabaseNotInitializedError,
    QuerySyntaxError,
    QueryTimeoutError,
)


class TestDatabaseServiceInit:
    """Tests for DatabaseService initialization."""

    @pytest.mark.unit
    def test_init_without_falkordb_raises_error(self, temp_db_path: Path) -> None:
        """Test initialization fails when FalkorDB is not available."""
        with patch("wrapper.services.database.FALKORDB_AVAILABLE", False):
            from wrapper.services.database import DatabaseService

            with pytest.raises(DatabaseError) as exc_info:
                DatabaseService(
                    database_path=temp_db_path,
                    graph_name="test_graph",
                )

            assert "FalkorDBLite is not installed" in str(exc_info.value)
            assert exc_info.value.error_code == "DATABASE_ERROR"

    @pytest.mark.unit
    def test_init_with_falkordb_succeeds(self, temp_db_path: Path) -> None:
        """Test initialization succeeds when FalkorDB is available."""
        with patch("wrapper.services.database.FALKORDB_AVAILABLE", True):
            from wrapper.services.database import DatabaseService

            service = DatabaseService(
                database_path=temp_db_path,
                graph_name="test_graph",
                query_timeout_ms=30000,
            )

            assert service._database_path == temp_db_path
            assert service._graph_name == "test_graph"
            assert service._query_timeout_ms == 30000
            assert service.is_initialized is False
            assert service.is_ready is False

    @pytest.mark.unit
    def test_graph_name_property(self, temp_db_path: Path) -> None:
        """Test graph_name property."""
        with patch("wrapper.services.database.FALKORDB_AVAILABLE", True):
            from wrapper.services.database import DatabaseService

            service = DatabaseService(
                database_path=temp_db_path,
                graph_name="my_graph",
            )

            assert service.graph_name == "my_graph"


class TestDatabaseServiceOperations:
    """Tests for DatabaseService operations."""

    @pytest.fixture
    def database_service(self, temp_db_path: Path, mock_falkordb_client, mock_falkordb_graph):
        """Create a DatabaseService with mocked FalkorDB."""
        with patch("wrapper.services.database.FALKORDB_AVAILABLE", True):
            with patch("wrapper.services.database.AsyncFalkorDB", return_value=mock_falkordb_client):
                from wrapper.services.database import DatabaseService

                service = DatabaseService(
                    database_path=temp_db_path,
                    graph_name="test_graph",
                )
                # Inject mocks
                service._db = mock_falkordb_client
                service._graph = mock_falkordb_graph
                service._is_initialized = True

                return service

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_initialize_success(self, temp_db_path: Path, mock_falkordb_client, mock_falkordb_graph):
        """Test successful database initialization."""
        with patch("wrapper.services.database.FALKORDB_AVAILABLE", True):
            with patch("wrapper.services.database.AsyncFalkorDB", return_value=mock_falkordb_client):
                from wrapper.services.database import DatabaseService

                service = DatabaseService(
                    database_path=temp_db_path,
                    graph_name="test_graph",
                )

                await service.initialize()

                assert service.is_initialized is True
                assert service._db is not None
                assert service._graph is not None
                assert service._initialization_time is not None
                assert service._initialization_time > 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_initialize_idempotent(self, database_service):
        """Test initialize is idempotent (calling twice is safe)."""
        # Already initialized in fixture
        assert database_service.is_initialized is True

        # Call again
        await database_service.initialize()

        # Still initialized
        assert database_service.is_initialized is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_query_success(self, database_service, mock_falkordb_result):
        """Test successful query execution."""
        result = await database_service.execute_query(
            query="MATCH (n:Person) RETURN n.name, n.age",
            parameters={},
        )

        assert result["columns"] == ["name", "age"]
        assert result["rows"] == [["Alice", 30], ["Bob", 25]]
        assert result["row_count"] == 2
        assert result["execution_time_ms"] > 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_query_with_parameters(self, database_service):
        """Test query execution with parameters."""
        result = await database_service.execute_query(
            query="MATCH (n:Person {name: $name}) RETURN n",
            parameters={"name": "Alice"},
        )

        assert result["row_count"] == 2
        database_service._graph.query.assert_called()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_query_not_initialized_raises_error(self, temp_db_path: Path):
        """Test query execution fails when database not initialized."""
        with patch("wrapper.services.database.FALKORDB_AVAILABLE", True):
            from wrapper.services.database import DatabaseService

            service = DatabaseService(
                database_path=temp_db_path,
                graph_name="test_graph",
            )

            with pytest.raises(DatabaseNotInitializedError):
                await service.execute_query("MATCH (n) RETURN n")

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_query_syntax_error(self, database_service):
        """Test query execution with syntax error."""
        database_service._graph.query.side_effect = Exception("Cypher syntax error at position 10")

        with pytest.raises(QuerySyntaxError) as exc_info:
            await database_service.execute_query("INVALID CYPHER")

        assert "syntax error" in str(exc_info.value).lower()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_query_timeout(self, database_service):
        """Test query execution timeout."""
        import asyncio

        async def slow_query(*args, **kwargs):
            await asyncio.sleep(10)  # Longer than timeout

        # With FalkorDBLite 0.6.0 native async API, we need to mock the graph.query method
        database_service._graph.query = slow_query

        with pytest.raises(QueryTimeoutError) as exc_info:
            await database_service.execute_query(
                "MATCH (n) RETURN n",
                timeout_ms=100,  # Short timeout
            )

        assert exc_info.value.timeout_ms == 100

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_schema_success(self, database_service):
        """Test successful schema retrieval."""
        # Mock execute_query for property queries
        async def mock_execute(*args, **kwargs):
            query = args[0]
            if "Person" in query:
                return {"rows": [[["person_id", "name", "age"]]], "row_count": 1}
            elif "Company" in query:
                return {"rows": [[["company_id", "name"]]], "row_count": 1}
            elif "KNOWS" in query:
                return {"rows": [[["since"]]], "row_count": 1}
            elif "WORKS_AT" in query:
                return {"rows": [[[]]], "row_count": 1}
            return {"rows": [], "row_count": 0}

        database_service.execute_query = mock_execute

        schema = await database_service.get_schema()

        assert "node_labels" in schema
        assert "edge_types" in schema
        assert "node_properties" in schema
        assert "edge_properties" in schema
        assert "Person" in schema["node_labels"]
        assert "Company" in schema["node_labels"]
        assert "KNOWS" in schema["edge_types"]
        assert "WORKS_AT" in schema["edge_types"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_stats_success(self, database_service):
        """Test successful stats retrieval."""
        # Mock execute_query for count queries
        async def mock_execute(*args, **kwargs):
            query = args[0]
            if "count(n)" in query:
                return {"rows": [[100]], "row_count": 1}
            elif "count(r)" in query:
                return {"rows": [[50]], "row_count": 1}
            return {"rows": [[0]], "row_count": 1}

        database_service.execute_query = mock_execute

        stats = await database_service.get_stats()

        assert "node_counts" in stats
        assert "edge_counts" in stats
        assert "total_nodes" in stats
        assert "total_edges" in stats
        assert "memory_usage_bytes" in stats
        assert stats["total_nodes"] == 200  # 2 labels * 100 each
        assert stats["total_edges"] == 100  # 2 types * 50 each

    @pytest.mark.unit
    def test_mark_ready(self, database_service):
        """Test marking database as ready."""
        assert database_service.is_ready is False

        database_service.mark_ready()

        assert database_service.is_ready is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_close_success(self, database_service):
        """Test successful database close."""
        assert database_service.is_initialized is True

        await database_service.close()

        assert database_service.is_initialized is False
        assert database_service.is_ready is False
        assert database_service._db is None
        assert database_service._graph is None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_close_not_initialized(self, temp_db_path: Path):
        """Test closing database that was never initialized."""
        with patch("wrapper.services.database.FALKORDB_AVAILABLE", True):
            from wrapper.services.database import DatabaseService

            service = DatabaseService(
                database_path=temp_db_path,
                graph_name="test_graph",
            )

            # Should not raise
            await service.close()

            assert service.is_initialized is False
