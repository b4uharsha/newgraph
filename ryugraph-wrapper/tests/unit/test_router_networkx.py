"""Tests for NetworkX algorithm router endpoints."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from graph_olap_schemas import AlgorithmCategory

from wrapper.exceptions import AlgorithmNotFoundError, ResourceLockedError
from wrapper.models.requests import AlgorithmRequest
from wrapper.routers.networkx import (
    _serialize_default,
    execute_algorithm,
    get_networkx_algorithm_info,
    list_networkx_algorithms,
)


class TestSerializeDefault:
    """Tests for _serialize_default() helper."""

    def test_serialize_none(self):
        """Test serializing None."""
        assert _serialize_default(None) is None

    def test_serialize_primitives(self):
        """Test serializing primitive types."""
        assert _serialize_default("hello") == "hello"
        assert _serialize_default(42) == 42
        assert _serialize_default(3.14) == 3.14
        assert _serialize_default(True) is True

    def test_serialize_type(self):
        """Test serializing type objects."""
        assert _serialize_default(int) == "int"
        assert _serialize_default(str) == "str"

    def test_serialize_callable(self):
        """Test serializing callable objects."""

        def my_func():
            pass

        assert _serialize_default(my_func) == "my_func"

    def test_serialize_json_serializable(self):
        """Test serializing JSON-compatible objects."""
        assert _serialize_default([1, 2, 3]) == [1, 2, 3]
        assert _serialize_default({"key": "value"}) == {"key": "value"}

    def test_serialize_non_json_serializable(self):
        """Test serializing non-JSON objects falls back to str."""

        class CustomClass:
            def __repr__(self):
                return "CustomClass()"

        result = _serialize_default(CustomClass())
        assert "CustomClass" in result


class TestExecuteAlgorithm:
    """Tests for /networkx/{algorithm_name} endpoint."""

    @pytest.mark.asyncio
    async def test_execute_algorithm_success(self):
        """Test successful algorithm execution."""
        request = AlgorithmRequest(
            node_label="Person",
            edge_type="KNOWS",
            result_property="pagerank",
            parameters={"alpha": 0.85},
        )

        mock_db = MagicMock()
        mock_db.is_ready = True

        mock_execution = MagicMock()
        mock_execution.execution_id = "exec-123"
        mock_execution.algorithm_name = "pagerank"
        mock_execution.algorithm_type = "networkx"
        mock_execution.status = "completed"
        mock_execution.started_at = datetime.now(UTC)
        mock_execution.completed_at = datetime.now(UTC)
        mock_execution.result_property = "pagerank"
        mock_execution.node_label = "Person"
        mock_execution.nodes_updated = 1000
        mock_execution.duration_ms = 5000
        mock_execution.error_message = None

        mock_algo_service = MagicMock()
        mock_algo_service.execute_networkx = AsyncMock(return_value=mock_execution)

        mock_control_plane = MagicMock()
        mock_control_plane.record_activity = AsyncMock()

        response = await execute_algorithm(
            algorithm_name="pagerank",
            request=request,
            _authorized_user="user-123",
            algorithm_service=mock_algo_service,
            control_plane=mock_control_plane,
            db_service=mock_db,
            x_user_id="user-123",
            x_user_name="test-user",
        )

        assert response.execution_id == "exec-123"
        assert response.algorithm_name == "pagerank"
        assert response.status == "completed"
        assert response.nodes_updated == 1000
        mock_control_plane.record_activity.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_algorithm_database_not_ready(self):
        """Test algorithm execution when database not ready."""
        request = AlgorithmRequest(
            node_label="Person",
            result_property="pagerank",
        )

        mock_db = MagicMock()
        mock_db.is_ready = False

        mock_algo_service = MagicMock()
        mock_control_plane = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await execute_algorithm(
                algorithm_name="pagerank",
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
        request = AlgorithmRequest(
            node_label="Person",
            result_property="result",
        )

        mock_db = MagicMock()
        mock_db.is_ready = True

        mock_algo_service = MagicMock()
        mock_algo_service.execute_networkx = AsyncMock(
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

        request = AlgorithmRequest(
            node_label="Person",
            result_property="pagerank",
        )

        mock_db = MagicMock()
        mock_db.is_ready = True

        mock_algo_service = MagicMock()
        mock_algo_service.execute_networkx = AsyncMock(
            side_effect=ResourceLockedError(
                holder_id="user-789",
                algorithm_name="betweenness",
                holder_username="other-user",
                acquired_at=datetime.now(UTC),
            )
        )

        mock_control_plane = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await execute_algorithm(
                algorithm_name="pagerank",
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
        assert "other-user" in exc_info.value.detail
        assert "betweenness" in exc_info.value.detail


class TestListNetworkXAlgorithms:
    """Tests for /networkx/algorithms endpoint."""

    @pytest.mark.asyncio
    async def test_list_algorithms_no_filters(self):
        """Test listing all algorithms without filters."""
        from unittest.mock import patch

        mock_algo = MagicMock()
        mock_algo.name = "pagerank"
        mock_algo.type = "networkx"
        mock_algo.category = AlgorithmCategory.CENTRALITY
        mock_algo.description = "PageRank algorithm"
        mock_algo.long_description = "Compute PageRank centrality"
        mock_algo.parameters = []
        mock_algo.returns = "dict"

        with patch("wrapper.routers.networkx.list_algorithms", return_value=[mock_algo]):
            response = await list_networkx_algorithms()

            assert response.total_count == 1
            assert len(response.algorithms) == 1
            assert response.algorithms[0].name == "pagerank"
            assert response.algorithms[0].type == "networkx"
            assert response.algorithms[0].category == AlgorithmCategory.CENTRALITY

    @pytest.mark.asyncio
    async def test_list_algorithms_with_category_filter(self):
        """Test listing algorithms filtered by category."""
        from unittest.mock import patch

        mock_algo = MagicMock()
        mock_algo.name = "pagerank"
        mock_algo.type = "networkx"
        mock_algo.category = AlgorithmCategory.CENTRALITY
        mock_algo.description = "PageRank"
        mock_algo.long_description = "PageRank centrality"
        mock_algo.parameters = []
        mock_algo.returns = "dict"

        with patch("wrapper.routers.networkx.list_algorithms", return_value=[mock_algo]):
            response = await list_networkx_algorithms(category="centrality")

            assert response.total_count == 1

    @pytest.mark.asyncio
    async def test_list_algorithms_with_search_filter(self):
        """Test listing algorithms with search filter."""
        from unittest.mock import patch

        mock_algo = MagicMock()
        mock_algo.name = "pagerank"
        mock_algo.type = "networkx"
        mock_algo.category = AlgorithmCategory.CENTRALITY
        mock_algo.description = "PageRank"
        mock_algo.long_description = "PageRank centrality"
        mock_algo.parameters = []
        mock_algo.returns = "dict"

        with patch("wrapper.routers.networkx.list_algorithms", return_value=[mock_algo]):
            response = await list_networkx_algorithms(search="rank")

            assert response.total_count == 1

    @pytest.mark.asyncio
    async def test_list_algorithms_invalid_category(self):
        """Test listing algorithms with invalid category."""
        with pytest.raises(HTTPException) as exc_info:
            await list_networkx_algorithms(category="invalid_category")

        assert exc_info.value.status_code == 400
        assert "Invalid category" in exc_info.value.detail


class TestGetNetworkXAlgorithmInfo:
    """Tests for /networkx/algorithms/{algorithm_name} endpoint."""

    @pytest.mark.asyncio
    async def test_get_algorithm_info_success(self):
        """Test getting algorithm info successfully."""
        from unittest.mock import patch

        # Create a simple object with attributes instead of using nested MagicMock
        class MockParameter:
            def __init__(self):
                self.name = "alpha"
                self.type = "float"
                self.required = False
                self.default = 0.85
                self.description = "Damping parameter"

        class MockAlgorithmInfo:
            def __init__(self):
                self.name = "pagerank"
                self.type = "networkx"
                self.category = AlgorithmCategory.CENTRALITY
                self.description = "PageRank algorithm"
                self.long_description = "Compute PageRank centrality"
                self.parameters = [MockParameter()]
                self.returns = "dict"

        with patch(
            "wrapper.routers.networkx.get_algorithm_info",
            return_value=MockAlgorithmInfo(),
        ):
            response = await get_networkx_algorithm_info("pagerank")

            assert response.name == "pagerank"
            assert response.type == "networkx"
            assert len(response.parameters) == 1
            assert response.parameters[0].name == "alpha"
            assert response.parameters[0].default == 0.85

    @pytest.mark.asyncio
    async def test_get_algorithm_info_not_found(self):
        """Test getting info for unknown algorithm."""
        from unittest.mock import patch

        with patch("wrapper.routers.networkx.get_algorithm_info", return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                await get_networkx_algorithm_info("unknown_algo")

            assert exc_info.value.status_code == 404
            assert "not found" in exc_info.value.detail
