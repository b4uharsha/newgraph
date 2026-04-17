"""Tests for native algorithm router endpoints."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from graph_olap_schemas import AlgorithmCategory

from wrapper.exceptions import AlgorithmNotFoundError, ResourceLockedError
from wrapper.models.requests import NativeAlgorithmRequest, ShortestPathRequest
from wrapper.routers.algo import (
    execute_algorithm,
    find_shortest_path,
    get_algorithm_info,
    get_execution_status,
    list_algorithms,
)


class TestExecuteAlgorithm:
    """Tests for /algo/{algorithm_name} endpoint."""

    @pytest.mark.asyncio
    async def test_execute_algorithm_success(self):
        """Test successful native algorithm execution."""
        request = NativeAlgorithmRequest(
            node_label="Person",
            edge_type="KNOWS",
            result_property="centrality",
            parameters={"damping": 0.85},
        )

        mock_db = MagicMock()
        mock_db.is_ready = True

        mock_execution = MagicMock()
        mock_execution.execution_id = "exec-456"
        mock_execution.algorithm_name = "native_pagerank"
        mock_execution.algorithm_type = "native"
        mock_execution.status = "completed"
        mock_execution.started_at = datetime.now(UTC)
        mock_execution.completed_at = datetime.now(UTC)
        mock_execution.result_property = "centrality"
        mock_execution.node_label = "Person"
        mock_execution.nodes_updated = 500
        mock_execution.duration_ms = 2000
        mock_execution.error_message = None

        mock_algo_service = MagicMock()
        mock_algo_service.execute_native = AsyncMock(return_value=mock_execution)

        mock_control_plane = MagicMock()
        mock_control_plane.record_activity = AsyncMock()

        response = await execute_algorithm(
            algorithm_name="native_pagerank",
            request=request,
            _authorized_user="user-456",
            algorithm_service=mock_algo_service,
            control_plane=mock_control_plane,
            db_service=mock_db,
            x_user_id="user-456",
            x_user_name="test-user",
        )

        assert response.execution_id == "exec-456"
        assert response.algorithm_name == "native_pagerank"
        assert response.algorithm_type == "native"
        assert response.status == "completed"
        assert response.nodes_updated == 500
        assert response.duration_ms == 2000
        mock_control_plane.record_activity.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_algorithm_database_not_ready(self):
        """Test algorithm execution when database not ready."""
        request = NativeAlgorithmRequest(
            node_label="Person",
            result_property="centrality",
        )

        mock_db = MagicMock()
        mock_db.is_ready = False

        mock_algo_service = MagicMock()
        mock_control_plane = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await execute_algorithm(
                algorithm_name="native_pagerank",
                request=request,
                _authorized_user="user-123",
                algorithm_service=mock_algo_service,
                control_plane=mock_control_plane,
                db_service=mock_db,
                x_user_id="user-123",
                x_user_name="test-user",
            )

        assert exc_info.value.status_code == 503
        assert "not ready" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_execute_algorithm_not_found(self):
        """Test algorithm execution with unknown algorithm."""
        request = NativeAlgorithmRequest(
            node_label="Person",
            result_property="result",
        )

        mock_db = MagicMock()
        mock_db.is_ready = True

        mock_algo_service = MagicMock()
        mock_algo_service.execute_native = AsyncMock(
            side_effect=AlgorithmNotFoundError("Algorithm not found: unknown_algo")
        )

        mock_control_plane = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await execute_algorithm(
                algorithm_name="unknown_algo",
                request=request,
                _authorized_user="user-123",
                algorithm_service=mock_algo_service,
                control_plane=mock_control_plane,
                db_service=mock_db,
                x_user_id="user-123",
                x_user_name="test-user",
            )

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_execute_algorithm_resource_locked(self):
        """Test algorithm execution when instance is locked."""
        from datetime import UTC, datetime

        request = NativeAlgorithmRequest(
            node_label="Person",
            result_property="centrality",
        )

        mock_db = MagicMock()
        mock_db.is_ready = True

        mock_algo_service = MagicMock()
        mock_algo_service.execute_native = AsyncMock(
            side_effect=ResourceLockedError(
                holder_id="user-999",
                algorithm_name="betweenness",
                holder_username="another-user",
                acquired_at=datetime.now(UTC),
            )
        )

        mock_control_plane = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await execute_algorithm(
                algorithm_name="native_pagerank",
                request=request,
                _authorized_user="user-123",
                algorithm_service=mock_algo_service,
                control_plane=mock_control_plane,
                db_service=mock_db,
                x_user_id="user-123",
                x_user_name="test-user",
            )

        assert exc_info.value.status_code == 409
        assert "locked" in exc_info.value.detail
        assert "another-user" in exc_info.value.detail
        assert "betweenness" in exc_info.value.detail


class TestGetExecutionStatus:
    """Tests for /algo/status/{execution_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_execution_status_success(self):
        """Test getting execution status successfully."""
        mock_execution = MagicMock()
        mock_execution.execution_id = "exec-789"
        mock_execution.algorithm_name = "native_pagerank"
        mock_execution.algorithm_type = "native"
        mock_execution.status = "completed"
        mock_execution.started_at = datetime.now(UTC)
        mock_execution.completed_at = datetime.now(UTC)
        mock_execution.result_property = "centrality"
        mock_execution.node_label = "Person"
        mock_execution.nodes_updated = 1000
        mock_execution.duration_ms = 3000
        mock_execution.error_message = None

        mock_algo_service = MagicMock()
        mock_algo_service.get_execution = MagicMock(return_value=mock_execution)

        response = await get_execution_status(
            execution_id="exec-789",
            algorithm_service=mock_algo_service,
        )

        assert response.execution_id == "exec-789"
        assert response.algorithm_name == "native_pagerank"
        assert response.status == "completed"
        assert response.nodes_updated == 1000
        mock_algo_service.get_execution.assert_called_once_with("exec-789")

    @pytest.mark.asyncio
    async def test_get_execution_status_not_found(self):
        """Test getting status for non-existent execution."""
        mock_algo_service = MagicMock()
        mock_algo_service.get_execution = MagicMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await get_execution_status(
                execution_id="unknown-exec",
                algorithm_service=mock_algo_service,
            )

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail
        assert "unknown-exec" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_execution_status_running(self):
        """Test getting status for running execution."""
        mock_execution = MagicMock()
        mock_execution.execution_id = "exec-running"
        mock_execution.algorithm_name = "native_pagerank"
        mock_execution.algorithm_type = "native"
        mock_execution.status = "running"
        mock_execution.started_at = datetime.now(UTC)
        mock_execution.completed_at = None
        mock_execution.result_property = "centrality"
        mock_execution.node_label = "Person"
        mock_execution.nodes_updated = 0
        mock_execution.duration_ms = None
        mock_execution.error_message = None

        mock_algo_service = MagicMock()
        mock_algo_service.get_execution = MagicMock(return_value=mock_execution)

        response = await get_execution_status(
            execution_id="exec-running",
            algorithm_service=mock_algo_service,
        )

        assert response.status == "running"
        assert response.completed_at is None
        assert response.duration_ms is None


class TestListAlgorithms:
    """Tests for /algo/algorithms endpoint."""

    @pytest.mark.asyncio
    async def test_list_algorithms_success(self):
        """Test listing native algorithms."""
        mock_param = MagicMock()
        mock_param.name = "damping"
        mock_param.type = "float"
        mock_param.required = False
        mock_param.default = 0.85
        mock_param.description = "Damping factor"

        mock_info = MagicMock()
        mock_info.name = "native_pagerank"
        mock_info.type = "native"
        mock_info.category = AlgorithmCategory.CENTRALITY
        mock_info.description = "Native PageRank"
        mock_info.long_description = "Native PageRank implementation"
        mock_info.parameters = [mock_param]
        mock_info.returns = "dict"

        mock_algo = MagicMock()
        mock_algo.info = mock_info

        with patch("wrapper.routers.algo.NATIVE_ALGORITHMS", [mock_algo]):
            response = await list_algorithms()

            assert response.total_count == 1
            assert len(response.algorithms) == 1
            assert response.algorithms[0].name == "native_pagerank"
            assert response.algorithms[0].type == "native"
            assert len(response.algorithms[0].parameters) == 1
            assert response.algorithms[0].parameters[0].name == "damping"

    @pytest.mark.asyncio
    async def test_list_algorithms_empty(self):
        """Test listing when no algorithms are available."""
        with patch("wrapper.routers.algo.NATIVE_ALGORITHMS", []):
            response = await list_algorithms()

            assert response.total_count == 0
            assert len(response.algorithms) == 0


class TestGetAlgorithmInfo:
    """Tests for /algo/algorithms/{algorithm_name} endpoint."""

    @pytest.mark.asyncio
    async def test_get_algorithm_info_success(self):
        """Test getting algorithm info successfully."""
        mock_param = MagicMock()
        mock_param.name = "iterations"
        mock_param.type = "int"
        mock_param.required = False
        mock_param.default = 100
        mock_param.description = "Number of iterations"

        mock_info = MagicMock()
        mock_info.name = "native_betweenness"
        mock_info.type = "native"
        mock_info.category = AlgorithmCategory.CENTRALITY
        mock_info.description = "Betweenness centrality"
        mock_info.long_description = "Calculate betweenness centrality"
        mock_info.parameters = [mock_param]
        mock_info.returns = "dict"

        mock_algo = MagicMock()
        mock_algo.info = mock_info

        with patch("wrapper.routers.algo.get_native_algorithm", return_value=mock_algo):
            response = await get_algorithm_info("native_betweenness")

            assert response.name == "native_betweenness"
            assert response.type == "native"
            assert response.category == AlgorithmCategory.CENTRALITY
            assert len(response.parameters) == 1
            assert response.parameters[0].name == "iterations"
            assert response.parameters[0].default == 100

    @pytest.mark.asyncio
    async def test_get_algorithm_info_not_found(self):
        """Test getting info for unknown algorithm."""
        with patch("wrapper.routers.algo.get_native_algorithm", return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                await get_algorithm_info("unknown_algo")

            assert exc_info.value.status_code == 404
            assert "not found" in exc_info.value.detail
            assert "unknown_algo" in exc_info.value.detail


class TestFindShortestPath:
    """Tests for /algo/shortest_path endpoint."""

    def _make_mocks(self, rows):
        """Build the db_service / control_plane mocks used by every test."""
        mock_db = MagicMock()
        mock_db.is_ready = True
        mock_db.execute_query = AsyncMock(
            return_value={
                "columns": ["path_ids", "path_length"],
                "rows": rows,
                "row_count": len(rows),
                "execution_time_ms": 1,
                "truncated": False,
            }
        )

        mock_control_plane = MagicMock()
        mock_control_plane.record_activity = AsyncMock()

        return mock_db, mock_control_plane

    @pytest.mark.asyncio
    async def test_two_hop_path_returns_real_length_and_intermediate(self):
        """A 2-hop path must report length=2 and include the intermediate node."""
        request = ShortestPathRequest(source_id="a", target_id="c", max_depth=10)

        # Simulated driver result for: shortestPath((a)-[*]-(c)) via b.
        mock_db, mock_control_plane = self._make_mocks(rows=[[["a", "b", "c"], 2]])

        response = await find_shortest_path(
            request=request,
            control_plane=mock_control_plane,
            db_service=mock_db,
            x_user_id="user-123",
            x_user_name="test-user",
        )

        assert response.algorithm_name == "shortest_path"
        assert response.status == "completed"
        assert response.result is not None
        assert response.result["found"] is True
        assert response.result["length"] == 2
        assert response.result["path"] == ["a", "b", "c"]
        # Intermediate node present between source and target.
        assert "b" in response.result["path"]
        assert response.result["source_id"] == "a"
        assert response.result["target_id"] == "c"
        mock_control_plane.record_activity.assert_called_once()

        # Cypher must actually request the path and its length.
        issued_query = mock_db.execute_query.await_args.args[0]
        assert "shortestPath" in issued_query
        assert "nodes(p)" in issued_query
        assert "length(p)" in issued_query

    @pytest.mark.asyncio
    async def test_no_path_returns_found_false(self):
        """When no rows are returned the response must signal not-found cleanly."""
        request = ShortestPathRequest(source_id="a", target_id="z")
        mock_db, mock_control_plane = self._make_mocks(rows=[])

        response = await find_shortest_path(
            request=request,
            control_plane=mock_control_plane,
            db_service=mock_db,
            x_user_id="user-123",
            x_user_name="test-user",
        )

        assert response.result is not None
        assert response.result["found"] is False
        assert response.result["path"] == []
        assert response.result["length"] == 0

    @pytest.mark.asyncio
    async def test_database_not_ready_returns_503(self):
        """When the database is not ready we must 503 before querying."""
        request = ShortestPathRequest(source_id="a", target_id="b")
        mock_db = MagicMock()
        mock_db.is_ready = False
        mock_db.execute_query = AsyncMock()
        mock_control_plane = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await find_shortest_path(
                request=request,
                control_plane=mock_control_plane,
                db_service=mock_db,
                x_user_id="user-123",
                x_user_name="test-user",
            )

        assert exc_info.value.status_code == 503
        mock_db.execute_query.assert_not_called()
