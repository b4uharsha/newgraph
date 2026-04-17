"""Tests for query router endpoints."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from wrapper.exceptions import QueryError, QueryTimeoutError
from wrapper.models.requests import QueryRequest
from wrapper.routers.query import execute_query


class TestExecuteQuery:
    """Tests for /query endpoint."""

    @pytest.mark.asyncio
    async def test_execute_query_success(self):
        """Test successful query execution."""
        request = QueryRequest(
            query="MATCH (n:Person) RETURN n.name LIMIT 10",
            parameters={},
            timeout_ms=30000,
        )

        mock_db = MagicMock()
        mock_db.is_ready = True
        mock_db.execute_query = AsyncMock(
            return_value={
                "columns": ["n.name"],
                "rows": [["Alice"], ["Bob"], ["Charlie"]],
                "row_count": 3,
                "execution_time_ms": 150,
                "truncated": False,
            }
        )

        mock_control_plane = MagicMock()
        mock_control_plane.record_activity = AsyncMock()

        response = await execute_query(
            request=request,
            db_service=mock_db,
            control_plane=mock_control_plane,
        )

        assert response.columns == ["n.name"]
        assert response.rows == [["Alice"], ["Bob"], ["Charlie"]]
        assert response.row_count == 3
        assert response.execution_time_ms == 150
        assert response.truncated is False

        # Should record activity
        mock_control_plane.record_activity.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_query_with_parameters(self):
        """Test query execution with parameters."""
        request = QueryRequest(
            query="MATCH (n:Person {age: $age}) RETURN n.name",
            parameters={"age": 30},
            timeout_ms=30000,
        )

        mock_db = MagicMock()
        mock_db.is_ready = True
        mock_db.execute_query = AsyncMock(
            return_value={
                "columns": ["n.name"],
                "rows": [["Alice"]],
                "row_count": 1,
                "execution_time_ms": 100,
            }
        )

        mock_control_plane = MagicMock()
        mock_control_plane.record_activity = AsyncMock()

        response = await execute_query(
            request=request,
            db_service=mock_db,
            control_plane=mock_control_plane,
        )

        assert response.row_count == 1
        mock_db.execute_query.assert_called_once_with(
            query=request.query,
            parameters={"age": 30},
            timeout_ms=30000,
        )

    @pytest.mark.asyncio
    async def test_execute_query_database_not_ready(self):
        """Test query execution when database not ready."""
        request = QueryRequest(
            query="MATCH (n) RETURN n LIMIT 1",
            parameters={},
            timeout_ms=30000,
        )

        mock_db = MagicMock()
        mock_db.is_ready = False

        mock_control_plane = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await execute_query(
                request=request,
                db_service=mock_db,
                control_plane=mock_control_plane,
            )

        assert exc_info.value.status_code == 503
        assert "not ready" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_execute_query_blocks_create(self):
        """Test that CREATE queries are blocked."""
        request = QueryRequest(
            query="CREATE (n:Person {name: 'Alice'})",
            parameters={},
            timeout_ms=30000,
        )

        mock_db = MagicMock()
        mock_db.is_ready = True

        mock_control_plane = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await execute_query(
                request=request,
                db_service=mock_db,
                control_plane=mock_control_plane,
            )

        assert exc_info.value.status_code == 400
        assert "Modification queries not allowed" in exc_info.value.detail
        assert "CREATE" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_execute_query_blocks_set(self):
        """Test that SET queries are blocked."""
        request = QueryRequest(
            query="MATCH (n:Person) SET n.age = 30",
            parameters={},
            timeout_ms=30000,
        )

        mock_db = MagicMock()
        mock_db.is_ready = True

        mock_control_plane = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await execute_query(
                request=request,
                db_service=mock_db,
                control_plane=mock_control_plane,
            )

        assert exc_info.value.status_code == 400
        assert "SET" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_execute_query_blocks_delete(self):
        """Test that DELETE queries are blocked."""
        request = QueryRequest(
            query="MATCH (n:Person) DELETE n",
            parameters={},
            timeout_ms=30000,
        )

        mock_db = MagicMock()
        mock_db.is_ready = True

        mock_control_plane = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await execute_query(
                request=request,
                db_service=mock_db,
                control_plane=mock_control_plane,
            )

        assert exc_info.value.status_code == 400
        assert "DELETE" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_execute_query_blocks_remove(self):
        """Test that REMOVE queries are blocked."""
        request = QueryRequest(
            query="MATCH (n:Person) REMOVE n.age",
            parameters={},
            timeout_ms=30000,
        )

        mock_db = MagicMock()
        mock_db.is_ready = True

        mock_control_plane = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await execute_query(
                request=request,
                db_service=mock_db,
                control_plane=mock_control_plane,
            )

        assert exc_info.value.status_code == 400
        assert "REMOVE" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_execute_query_blocks_merge(self):
        """Test that MERGE queries are blocked."""
        request = QueryRequest(
            query="MERGE (n:Person {name: 'Alice'})",
            parameters={},
            timeout_ms=30000,
        )

        mock_db = MagicMock()
        mock_db.is_ready = True

        mock_control_plane = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await execute_query(
                request=request,
                db_service=mock_db,
                control_plane=mock_control_plane,
            )

        assert exc_info.value.status_code == 400
        assert "MERGE" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_execute_query_blocks_drop(self):
        """Test that DROP queries are blocked."""
        request = QueryRequest(
            query="DROP INDEX person_name",
            parameters={},
            timeout_ms=30000,
        )

        mock_db = MagicMock()
        mock_db.is_ready = True

        mock_control_plane = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await execute_query(
                request=request,
                db_service=mock_db,
                control_plane=mock_control_plane,
            )

        assert exc_info.value.status_code == 400
        assert "DROP" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_execute_query_timeout_error(self):
        """Test query timeout propagates to app-level handler."""
        request = QueryRequest(
            query="MATCH (n) RETURN n",
            parameters={},
            timeout_ms=5000,
        )

        mock_db = MagicMock()
        mock_db.is_ready = True
        mock_db.execute_query = AsyncMock(
            side_effect=QueryTimeoutError(
                timeout_ms=5000,
                elapsed_ms=5100,
            )
        )

        mock_control_plane = MagicMock()

        with pytest.raises(QueryTimeoutError) as exc_info:
            await execute_query(
                request=request,
                db_service=mock_db,
                control_plane=mock_control_plane,
            )

        assert exc_info.value.timeout_ms == 5000

    @pytest.mark.asyncio
    async def test_execute_query_error(self):
        """Test query error propagates to app-level handler."""
        request = QueryRequest(
            query="INVALID QUERY SYNTAX",
            parameters={},
            timeout_ms=30000,
        )

        mock_db = MagicMock()
        mock_db.is_ready = True
        mock_db.execute_query = AsyncMock(
            side_effect=QueryError("Syntax error in query")
        )

        mock_control_plane = MagicMock()

        with pytest.raises(QueryError) as exc_info:
            await execute_query(
                request=request,
                db_service=mock_db,
                control_plane=mock_control_plane,
            )

        assert "Syntax error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_execute_query_truncated_result(self):
        """Test query with truncated results."""
        request = QueryRequest(
            query="MATCH (n) RETURN n LIMIT 100000",
            parameters={},
            timeout_ms=30000,
        )

        mock_db = MagicMock()
        mock_db.is_ready = True
        mock_db.execute_query = AsyncMock(
            return_value={
                "columns": ["n"],
                "rows": [[{"id": i}] for i in range(10000)],
                "row_count": 10000,
                "execution_time_ms": 2000,
                "truncated": True,
            }
        )

        mock_control_plane = MagicMock()
        mock_control_plane.record_activity = AsyncMock()

        response = await execute_query(
            request=request,
            db_service=mock_db,
            control_plane=mock_control_plane,
        )

        assert response.truncated is True
        assert response.row_count == 10000
