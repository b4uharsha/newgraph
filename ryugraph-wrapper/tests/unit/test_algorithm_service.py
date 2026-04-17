"""Unit tests for the AlgorithmService."""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wrapper.exceptions import AlgorithmError, AlgorithmNotFoundError, ResourceLockedError
from wrapper.models.execution import ExecutionStatus
from wrapper.services.algorithm import AlgorithmService


class TestAlgorithmService:
    """Tests for AlgorithmService."""

    @pytest.fixture
    def mock_db_service(self) -> MagicMock:
        """Create mock database service."""
        service = MagicMock()
        service.execute_query = AsyncMock(return_value={"rows": [[100]], "columns": ["count"]})
        return service

    @pytest.fixture
    def mock_lock_service(self) -> MagicMock:
        """Create mock lock service."""
        service = MagicMock()
        service.acquire_or_raise = AsyncMock(return_value="exec-123")
        service.release = AsyncMock(return_value=True)
        return service

    @pytest.fixture
    def algorithm_service(
        self, mock_db_service: MagicMock, mock_lock_service: MagicMock
    ) -> AlgorithmService:
        """Create AlgorithmService with mocks."""
        return AlgorithmService(
            db_service=mock_db_service,
            lock_service=mock_lock_service,
        )

    # =========================================================================
    # Native Algorithm Execution Tests
    # =========================================================================

    @pytest.mark.unit
    async def test_execute_native_success(
        self, algorithm_service: AlgorithmService, mock_lock_service: MagicMock
    ) -> None:
        """Successfully execute native algorithm."""
        # Mock the native algorithm
        mock_algo = MagicMock()
        mock_algo.execute = AsyncMock(
            return_value={
                "nodes_updated": 100,
                "duration_ms": 500,
            }
        )

        with patch(
            "wrapper.services.algorithm.get_native_algorithm",
            return_value=mock_algo,
        ):
            result = await algorithm_service.execute_native(
                user_id="user-1",
                user_name="alice",
                algorithm_name="pagerank",
                node_label="Person",
                edge_type="KNOWS",
                result_property="pr_score",
                parameters={"damping_factor": 0.85},
            )

        assert result.status == ExecutionStatus.COMPLETED
        assert result.nodes_updated == 100
        assert result.duration_ms == 500
        assert result.algorithm_name == "pagerank"

        # Lock should be acquired and released
        mock_lock_service.acquire_or_raise.assert_called_once()
        mock_lock_service.release.assert_called_once_with("exec-123")

    @pytest.mark.unit
    async def test_execute_native_algorithm_not_found(
        self, algorithm_service: AlgorithmService
    ) -> None:
        """Raises error for unknown algorithm."""
        with (
            patch(
                "wrapper.services.algorithm.get_native_algorithm",
                return_value=None,
            ),
            pytest.raises(AlgorithmNotFoundError) as exc_info,
        ):
            await algorithm_service.execute_native(
                user_id="user-1",
                user_name="alice",
                algorithm_name="nonexistent",
                node_label=None,
                edge_type=None,
                result_property="result",
                parameters={},
            )

        assert "nonexistent" in str(exc_info.value)

    @pytest.mark.unit
    async def test_execute_native_lock_denied(
        self, algorithm_service: AlgorithmService, mock_lock_service: MagicMock
    ) -> None:
        """Raises error when lock cannot be acquired."""
        mock_lock_service.acquire_or_raise.side_effect = ResourceLockedError(
            holder_id="user-2",
            holder_username="bob",
            algorithm_name="other_algo",
            acquired_at=datetime.now(UTC),
        )

        mock_algo = MagicMock()
        with (
            patch(
                "wrapper.services.algorithm.get_native_algorithm",
                return_value=mock_algo,
            ),
            pytest.raises(ResourceLockedError),
        ):
            await algorithm_service.execute_native(
                user_id="user-1",
                user_name="alice",
                algorithm_name="pagerank",
                node_label=None,
                edge_type=None,
                result_property="result",
                parameters={},
            )

    @pytest.mark.unit
    async def test_execute_native_releases_lock_on_failure(
        self, algorithm_service: AlgorithmService, mock_lock_service: MagicMock
    ) -> None:
        """Lock is released even when algorithm fails."""
        mock_algo = MagicMock()
        mock_algo.execute = AsyncMock(side_effect=RuntimeError("Algorithm failed"))

        with (
            patch(
                "wrapper.services.algorithm.get_native_algorithm",
                return_value=mock_algo,
            ),
            pytest.raises(RuntimeError),
        ):
            await algorithm_service.execute_native(
                user_id="user-1",
                user_name="alice",
                algorithm_name="pagerank",
                node_label=None,
                edge_type=None,
                result_property="result",
                parameters={},
            )

        # Lock should still be released
        mock_lock_service.release.assert_called_once()

        # Execution should be marked as failed
        execution = algorithm_service.get_execution("exec-123")
        assert execution is not None
        assert execution.status == ExecutionStatus.FAILED

    # =========================================================================
    # NetworkX Algorithm Execution Tests
    # =========================================================================

    @pytest.mark.unit
    async def test_execute_networkx_success(
        self, algorithm_service: AlgorithmService, mock_lock_service: MagicMock
    ) -> None:
        """Successfully execute NetworkX algorithm."""
        mock_info = MagicMock()

        with (
            patch(
                "wrapper.services.algorithm.get_algorithm_info",
                return_value=mock_info,
            ),
            patch(
                "wrapper.services.algorithm.execute_networkx_algorithm",
                new_callable=AsyncMock,
                return_value={
                    "nodes_updated": 50,
                    "duration_ms": 1000,
                    "graph_nodes": 100,
                    "graph_edges": 200,
                },
            ),
        ):
            result = await algorithm_service.execute_networkx(
                user_id="user-1",
                user_name="alice",
                algorithm_name="betweenness_centrality",
                node_label="Person",
                edge_type="KNOWS",
                result_property="betweenness",
                parameters={},
            )

        assert result.status == ExecutionStatus.COMPLETED
        assert result.nodes_updated == 50
        assert result.algorithm_name == "betweenness_centrality"

    @pytest.mark.unit
    async def test_execute_networkx_not_found(self, algorithm_service: AlgorithmService) -> None:
        """Raises error for unknown NetworkX algorithm."""
        with (
            patch(
                "wrapper.services.algorithm.get_algorithm_info",
                return_value=None,
            ),
            pytest.raises(AlgorithmNotFoundError),
        ):
            await algorithm_service.execute_networkx(
                user_id="user-1",
                user_name="alice",
                algorithm_name="nonexistent_nx",
                node_label=None,
                edge_type=None,
                result_property="result",
                parameters={},
            )

    @pytest.mark.unit
    async def test_execute_networkx_with_timeout(self, algorithm_service: AlgorithmService) -> None:
        """NetworkX execution respects timeout."""
        import asyncio

        mock_info = MagicMock()

        async def slow_execution(*args: Any, **kwargs: Any) -> dict[str, Any]:
            await asyncio.sleep(10)
            return {"nodes_updated": 0, "duration_ms": 0}

        with (
            patch(
                "wrapper.services.algorithm.get_algorithm_info",
                return_value=mock_info,
            ),
            patch(
                "wrapper.services.algorithm.execute_networkx_algorithm",
                side_effect=slow_execution,
            ),
            pytest.raises(AlgorithmError) as exc_info,
        ):
            await algorithm_service.execute_networkx(
                user_id="user-1",
                user_name="alice",
                algorithm_name="slow_algo",
                node_label=None,
                edge_type=None,
                result_property="result",
                parameters={},
                timeout_ms=100,
            )

        assert "timed out" in str(exc_info.value)

    # =========================================================================
    # Execution History Tests
    # =========================================================================

    @pytest.mark.unit
    async def test_get_execution(self, algorithm_service: AlgorithmService) -> None:
        """Can retrieve execution by ID."""
        mock_algo = MagicMock()
        mock_algo.execute = AsyncMock(return_value={"nodes_updated": 10, "duration_ms": 100})

        with patch(
            "wrapper.services.algorithm.get_native_algorithm",
            return_value=mock_algo,
        ):
            result = await algorithm_service.execute_native(
                user_id="user-1",
                user_name="alice",
                algorithm_name="test",
                node_label=None,
                edge_type=None,
                result_property="r",
                parameters={},
            )

        retrieved = algorithm_service.get_execution(result.execution_id)
        assert retrieved is not None
        assert retrieved.execution_id == result.execution_id

    @pytest.mark.unit
    async def test_get_execution_not_found(self, algorithm_service: AlgorithmService) -> None:
        """Returns None for unknown execution ID."""
        result = algorithm_service.get_execution("nonexistent-id")
        assert result is None

    @pytest.mark.unit
    async def test_list_executions(self, algorithm_service: AlgorithmService) -> None:
        """Can list recent executions."""
        mock_algo = MagicMock()
        mock_algo.execute = AsyncMock(return_value={"nodes_updated": 10, "duration_ms": 100})

        # Create multiple executions
        execution_ids = []
        for i in range(3):
            with patch(
                "wrapper.services.algorithm.get_native_algorithm",
                return_value=mock_algo,
            ):
                # Reset mock for new execution ID
                algorithm_service._lock_service.acquire_or_raise = AsyncMock(
                    return_value=f"exec-{i}"
                )
                result = await algorithm_service.execute_native(
                    user_id=f"user-{i}",
                    user_name=f"user{i}",
                    algorithm_name="test",
                    node_label=None,
                    edge_type=None,
                    result_property="r",
                    parameters={},
                )
                execution_ids.append(result.execution_id)

        executions = algorithm_service.list_executions()
        assert len(executions) == 3

        # Most recent should be first
        assert executions[0].execution_id == "exec-2"

    @pytest.mark.unit
    async def test_list_executions_with_status_filter(
        self, algorithm_service: AlgorithmService
    ) -> None:
        """Can filter executions by status."""
        mock_algo = MagicMock()
        mock_algo.execute = AsyncMock(return_value={"nodes_updated": 10, "duration_ms": 100})

        # Create successful execution
        with patch(
            "wrapper.services.algorithm.get_native_algorithm",
            return_value=mock_algo,
        ):
            await algorithm_service.execute_native(
                user_id="user-1",
                user_name="alice",
                algorithm_name="test",
                node_label=None,
                edge_type=None,
                result_property="r",
                parameters={},
            )

        # Create failed execution
        mock_algo.execute = AsyncMock(side_effect=RuntimeError("Failed"))
        algorithm_service._lock_service.acquire_or_raise = AsyncMock(return_value="exec-fail")

        with patch(
            "wrapper.services.algorithm.get_native_algorithm",
            return_value=mock_algo,
        ):
            with contextlib.suppress(RuntimeError):
                await algorithm_service.execute_native(
                    user_id="user-2",
                    user_name="bob",
                    algorithm_name="test",
                    node_label=None,
                    edge_type=None,
                    result_property="r",
                    parameters={},
                )

        # Filter by status
        completed = algorithm_service.list_executions(status=ExecutionStatus.COMPLETED)
        failed = algorithm_service.list_executions(status=ExecutionStatus.FAILED)

        assert len(completed) == 1
        assert len(failed) == 1

    @pytest.mark.unit
    async def test_list_executions_limit(self, algorithm_service: AlgorithmService) -> None:
        """Respects limit parameter."""
        mock_algo = MagicMock()
        mock_algo.execute = AsyncMock(return_value={"nodes_updated": 10, "duration_ms": 100})

        for i in range(5):
            algorithm_service._lock_service.acquire_or_raise = AsyncMock(return_value=f"exec-{i}")
            with patch(
                "wrapper.services.algorithm.get_native_algorithm",
                return_value=mock_algo,
            ):
                await algorithm_service.execute_native(
                    user_id=f"user-{i}",
                    user_name=f"user{i}",
                    algorithm_name="test",
                    node_label=None,
                    edge_type=None,
                    result_property="r",
                    parameters={},
                )

        limited = algorithm_service.list_executions(limit=2)
        assert len(limited) == 2

    # =========================================================================
    # Async Execution Tests
    # =========================================================================

    @pytest.mark.unit
    async def test_execute_native_async(self, algorithm_service: AlgorithmService) -> None:
        """Can start async execution."""
        mock_algo = MagicMock()
        mock_algo.execute = AsyncMock(return_value={"nodes_updated": 100, "duration_ms": 500})

        with patch(
            "wrapper.services.algorithm.get_native_algorithm",
            return_value=mock_algo,
        ):
            execution_id = await algorithm_service.execute_native_async(
                user_id="user-1",
                user_name="alice",
                algorithm_name="pagerank",
                node_label=None,
                edge_type=None,
                result_property="pr",
                parameters={},
            )

        assert execution_id == "exec-123"

        # Execution should be created
        execution = algorithm_service.get_execution(execution_id)
        assert execution is not None
        assert execution.status in [ExecutionStatus.RUNNING, ExecutionStatus.COMPLETED]

    # =========================================================================
    # Cancellation Tests
    # =========================================================================

    @pytest.mark.unit
    async def test_cancel_execution_not_found(self, algorithm_service: AlgorithmService) -> None:
        """Cancelling nonexistent execution returns False."""
        result = await algorithm_service.cancel_execution("nonexistent")
        assert result is False

    @pytest.mark.unit
    async def test_execution_history_size_limit(self, algorithm_service: AlgorithmService) -> None:
        """Execution history respects size limit."""
        mock_algo = MagicMock()
        mock_algo.execute = AsyncMock(return_value={"nodes_updated": 1, "duration_ms": 10})

        # Create more than MAX_EXECUTION_HISTORY executions
        from wrapper.services.algorithm import MAX_EXECUTION_HISTORY

        for i in range(MAX_EXECUTION_HISTORY + 10):
            algorithm_service._lock_service.acquire_or_raise = AsyncMock(return_value=f"exec-{i}")
            with patch(
                "wrapper.services.algorithm.get_native_algorithm",
                return_value=mock_algo,
            ):
                await algorithm_service.execute_native(
                    user_id=f"user-{i}",
                    user_name=f"user{i}",
                    algorithm_name="test",
                    node_label=None,
                    edge_type=None,
                    result_property="r",
                    parameters={},
                )

        # Should not exceed limit
        assert len(algorithm_service._executions) <= MAX_EXECUTION_HISTORY
