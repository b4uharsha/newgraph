"""Unit tests for AlgorithmService.

Tests the algorithm execution service that orchestrates async graph algorithm runs.

Mocking strategy (Google testing best practices):
- LockService: REAL (pure in-memory, no external dependencies)
- DatabaseService: MOCKED (requires FalkorDB - external I/O boundary)

This tests the service logic in isolation without actual database operations.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from wrapper.models.execution import (
    AlgorithmCategory,
    AlgorithmType,
    ExecutionStatus,
)
from wrapper.services.algorithm import (
    ALGORITHMS,
    AlgorithmService,
    get_algorithm,
    list_algorithms,
)
from wrapper.services.lock import LockService


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def lock_service():
    """Create REAL LockService.

    LockService is NOT mocked because it has no external dependencies -
    it's pure in-memory Python with no I/O.
    """
    return LockService()


@pytest.fixture
def mock_db_service():
    """Create mock DatabaseService.

    DatabaseService IS mocked because it requires FalkorDB (external I/O).
    """
    service = MagicMock()
    service.is_ready = True
    service.execute_query = AsyncMock(
        return_value={
            "columns": ["updated"],
            "rows": [[42]],
            "row_count": 1,
            "execution_time_ms": 100,
        }
    )
    return service


@pytest.fixture
def algorithm_service(mock_db_service, lock_service):
    """Create AlgorithmService with real LockService and mocked DatabaseService."""
    return AlgorithmService(
        db_service=mock_db_service,
        lock_service=lock_service,
    )


# =============================================================================
# Algorithm Registry Tests
# =============================================================================


class TestAlgorithmRegistry:
    """Tests for algorithm registry functions."""

    @pytest.mark.unit
    def test_list_algorithms_returns_all(self):
        """list_algorithms returns all registered algorithms."""
        algorithms = list_algorithms()

        assert len(algorithms) == 4
        names = [a.name for a in algorithms]
        assert "pagerank" in names
        assert "betweenness" in names
        assert "wcc" in names
        assert "cdlp" in names

    @pytest.mark.unit
    def test_get_algorithm_by_name(self):
        """get_algorithm returns correct algorithm info."""
        algo = get_algorithm("pagerank")

        assert algo is not None
        assert algo.name == "pagerank"
        assert algo.display_name == "PageRank"
        assert algo.category == AlgorithmCategory.CENTRALITY
        assert algo.supports_write_back is True

    @pytest.mark.unit
    def test_get_algorithm_case_insensitive(self):
        """get_algorithm is case-insensitive."""
        algo1 = get_algorithm("PageRank")
        algo2 = get_algorithm("PAGERANK")
        algo3 = get_algorithm("pagerank")

        assert algo1 is not None
        assert algo2 is not None
        assert algo3 is not None
        assert algo1.name == algo2.name == algo3.name

    @pytest.mark.unit
    def test_get_algorithm_unknown_returns_none(self):
        """get_algorithm returns None for unknown algorithm."""
        algo = get_algorithm("unknown_algo")

        assert algo is None

    @pytest.mark.unit
    def test_algorithms_have_required_fields(self):
        """All algorithms have required fields."""
        for algo in list_algorithms():
            assert algo.name
            assert algo.display_name
            assert algo.category
            assert algo.description
            assert algo.cypher_procedure
            assert algo.result_field
            assert algo.default_timeout_ms > 0

    @pytest.mark.unit
    def test_centrality_algorithms_exist(self):
        """Centrality algorithms are registered."""
        pagerank = get_algorithm("pagerank")
        betweenness = get_algorithm("betweenness")

        assert pagerank is not None
        assert pagerank.category == AlgorithmCategory.CENTRALITY
        assert betweenness is not None
        assert betweenness.category == AlgorithmCategory.CENTRALITY

    @pytest.mark.unit
    def test_community_algorithms_exist(self):
        """Community detection algorithms are registered."""
        wcc = get_algorithm("wcc")
        cdlp = get_algorithm("cdlp")

        assert wcc is not None
        assert wcc.category == AlgorithmCategory.COMMUNITY
        assert cdlp is not None
        assert cdlp.category == AlgorithmCategory.COMMUNITY


# =============================================================================
# AlgorithmService Initialization Tests
# =============================================================================


class TestAlgorithmServiceInit:
    """Tests for AlgorithmService initialization."""

    @pytest.mark.unit
    def test_init_creates_empty_state(self, algorithm_service):
        """Service initializes with empty execution history."""
        assert algorithm_service.list_executions() == []

    @pytest.mark.unit
    def test_init_with_services(self, mock_db_service, lock_service):
        """Service initializes with injected services."""
        service = AlgorithmService(
            db_service=mock_db_service,
            lock_service=lock_service,
        )

        assert service._db_service is mock_db_service
        assert service._lock_service is lock_service


# =============================================================================
# Execution Management Tests
# =============================================================================


class TestExecutionManagement:
    """Tests for execution tracking and management."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_creates_execution(self, algorithm_service):
        """execute() creates an execution record."""
        execution = await algorithm_service.execute(
            user_id="user-001",
            user_name="testuser",
            algorithm_name="pagerank",
            result_property="pr_score",
        )

        assert execution.execution_id is not None
        assert len(execution.execution_id) == 36  # UUID format
        assert execution.algorithm_name == "pagerank"
        assert execution.user_id == "user-001"
        assert execution.user_name == "testuser"
        assert execution.result_property == "pr_score"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_returns_running_status(self, algorithm_service):
        """execute() returns execution with running status."""
        execution = await algorithm_service.execute(
            user_id="user-001",
            user_name="testuser",
            algorithm_name="pagerank",
            result_property="pr_score",
        )

        assert execution.status == ExecutionStatus.RUNNING
        assert execution.started_at is not None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_acquires_lock(self, algorithm_service, lock_service):
        """execute() acquires lock before starting."""
        assert lock_service.is_locked() is False

        execution = await algorithm_service.execute(
            user_id="user-001",
            user_name="testuser",
            algorithm_name="pagerank",
            result_property="pr_score",
        )

        # Lock should be held during execution
        assert lock_service.is_locked() is True
        lock_info = lock_service.get_lock_info()
        assert lock_info.execution_id == execution.execution_id

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_sets_algorithm_type(self, algorithm_service):
        """execute() sets algorithm type to native."""
        execution = await algorithm_service.execute(
            user_id="user-001",
            user_name="testuser",
            algorithm_name="pagerank",
            result_property="pr_score",
        )

        assert execution.algorithm_type == AlgorithmType.NATIVE

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_with_node_labels(self, algorithm_service):
        """execute() accepts node label filter."""
        execution = await algorithm_service.execute(
            user_id="user-001",
            user_name="testuser",
            algorithm_name="pagerank",
            result_property="pr_score",
            node_labels=["Person"],
        )

        assert execution.node_labels == ["Person"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_with_relationship_types(self, algorithm_service):
        """execute() accepts relationship type filter."""
        execution = await algorithm_service.execute(
            user_id="user-001",
            user_name="testuser",
            algorithm_name="pagerank",
            result_property="pr_score",
            relationship_types=["KNOWS"],
        )

        assert execution.relationship_types == ["KNOWS"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_with_write_back_false(self, algorithm_service):
        """execute() accepts write_back=False."""
        execution = await algorithm_service.execute(
            user_id="user-001",
            user_name="testuser",
            algorithm_name="pagerank",
            result_property="pr_score",
            write_back=False,
        )

        assert execution.write_back is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_unknown_algorithm_raises(self, algorithm_service):
        """execute() raises ValueError for unknown algorithm."""
        with pytest.raises(ValueError, match="Unknown algorithm"):
            await algorithm_service.execute(
                user_id="user-001",
                user_name="testuser",
                algorithm_name="unknown_algo",
                result_property="score",
            )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_concurrent_raises_lock_error(self, algorithm_service):
        """Second concurrent execute() raises ResourceLockedError."""
        from wrapper.exceptions import ResourceLockedError

        # First execution acquires lock
        await algorithm_service.execute(
            user_id="user-001",
            user_name="testuser",
            algorithm_name="pagerank",
            result_property="pr_score",
        )

        # Second execution should fail
        with pytest.raises(ResourceLockedError):
            await algorithm_service.execute(
                user_id="user-002",
                user_name="otheruser",
                algorithm_name="betweenness",
                result_property="bc_score",
            )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_execution_returns_execution(self, algorithm_service):
        """get_execution() returns execution by ID."""
        execution = await algorithm_service.execute(
            user_id="user-001",
            user_name="testuser",
            algorithm_name="pagerank",
            result_property="pr_score",
        )

        retrieved = algorithm_service.get_execution(execution.execution_id)

        assert retrieved is not None
        assert retrieved.execution_id == execution.execution_id

    @pytest.mark.unit
    def test_get_execution_unknown_returns_none(self, algorithm_service):
        """get_execution() returns None for unknown ID."""
        result = algorithm_service.get_execution("unknown-id")

        assert result is None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_list_executions_returns_recent_first(self, algorithm_service, mock_db_service):
        """list_executions() returns most recent first."""
        # Execute first algorithm and wait for completion
        exec1 = await algorithm_service.execute(
            user_id="user-001",
            user_name="testuser",
            algorithm_name="pagerank",
            result_property="pr1",
        )

        # Wait for completion
        await asyncio.sleep(0.1)

        # Release lock to allow second execution
        await algorithm_service._lock_service.release(exec1.execution_id)

        exec2 = await algorithm_service.execute(
            user_id="user-001",
            user_name="testuser",
            algorithm_name="wcc",
            result_property="wcc1",
        )

        executions = algorithm_service.list_executions(limit=10)

        assert len(executions) >= 2
        # Most recent first
        assert executions[0].execution_id == exec2.execution_id

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_list_executions_with_status_filter(self, algorithm_service):
        """list_executions() filters by status."""
        execution = await algorithm_service.execute(
            user_id="user-001",
            user_name="testuser",
            algorithm_name="pagerank",
            result_property="pr_score",
        )

        running = algorithm_service.list_executions(status=ExecutionStatus.RUNNING)
        completed = algorithm_service.list_executions(status=ExecutionStatus.COMPLETED)

        assert len(running) >= 1
        assert execution.execution_id in [e.execution_id for e in running]
        # Completed may be empty or have entries depending on background task timing

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_list_executions_respects_limit(self, algorithm_service):
        """list_executions() respects limit parameter."""
        executions = algorithm_service.list_executions(limit=5)

        assert len(executions) <= 5


# =============================================================================
# Cancellation Tests
# =============================================================================


class TestCancellation:
    """Tests for execution cancellation."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_cancel_running_execution(self, algorithm_service, mock_db_service):
        """cancel_execution() cancels a running execution."""
        # Make DB slow so we can cancel
        async def slow_query(*args, **kwargs):
            await asyncio.sleep(10)
            return {"columns": ["count"], "rows": [[1]], "row_count": 1}

        mock_db_service.execute_query = slow_query

        execution = await algorithm_service.execute(
            user_id="user-001",
            user_name="testuser",
            algorithm_name="pagerank",
            result_property="pr_score",
        )

        # Give background task time to start
        await asyncio.sleep(0.05)

        success = await algorithm_service.cancel_execution(execution.execution_id)

        assert success is True

        # Check status is cancelled
        cancelled = algorithm_service.get_execution(execution.execution_id)
        assert cancelled is not None
        assert cancelled.status == ExecutionStatus.CANCELLED

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_cancel_unknown_execution_returns_false(self, algorithm_service):
        """cancel_execution() returns False for unknown ID."""
        success = await algorithm_service.cancel_execution("unknown-id")

        assert success is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_cancel_releases_lock(self, algorithm_service, lock_service, mock_db_service):
        """cancel_execution() releases the lock."""
        async def slow_query(*args, **kwargs):
            await asyncio.sleep(10)
            return {"columns": ["count"], "rows": [[1]], "row_count": 1}

        mock_db_service.execute_query = slow_query

        execution = await algorithm_service.execute(
            user_id="user-001",
            user_name="testuser",
            algorithm_name="pagerank",
            result_property="pr_score",
        )

        assert lock_service.is_locked() is True

        await asyncio.sleep(0.05)
        await algorithm_service.cancel_execution(execution.execution_id)

        # Give time for cleanup
        await asyncio.sleep(0.05)
        assert lock_service.is_locked() is False


# =============================================================================
# Query Building Tests
# =============================================================================


class TestQueryBuilding:
    """Tests for Cypher query construction."""

    @pytest.mark.unit
    def test_build_pagerank_query_with_writeback(self, algorithm_service):
        """Builds correct PageRank query with writeback."""
        algo_info = get_algorithm("pagerank")
        assert algo_info is not None

        query = algorithm_service._build_algorithm_query(
            algo_info=algo_info,
            node_labels=None,
            relationship_types=None,
            result_property="pr_score",
            parameters={},
            write_back=True,
        )

        assert "pagerank.stream" in query
        assert "SET node.pr_score" in query
        assert "CALL {" in query

    @pytest.mark.unit
    def test_build_pagerank_query_without_writeback(self, algorithm_service):
        """Builds correct PageRank query without writeback."""
        algo_info = get_algorithm("pagerank")
        assert algo_info is not None

        query = algorithm_service._build_algorithm_query(
            algo_info=algo_info,
            node_labels=None,
            relationship_types=None,
            result_property="pr_score",
            parameters={},
            write_back=False,
        )

        assert "pagerank.stream" in query
        assert "SET" not in query
        assert "count(node)" in query

    @pytest.mark.unit
    def test_build_pagerank_query_with_label_filter(self, algorithm_service):
        """Builds PageRank query with node label filter."""
        algo_info = get_algorithm("pagerank")
        assert algo_info is not None

        query = algorithm_service._build_algorithm_query(
            algo_info=algo_info,
            node_labels=["Person"],
            relationship_types=None,
            result_property="pr_score",
            parameters={},
            write_back=True,
        )

        assert "'Person'" in query

    @pytest.mark.unit
    def test_build_betweenness_query(self, algorithm_service):
        """Builds correct Betweenness query."""
        algo_info = get_algorithm("betweenness")
        assert algo_info is not None

        query = algorithm_service._build_algorithm_query(
            algo_info=algo_info,
            node_labels=["Person", "Company"],
            relationship_types=["KNOWS"],
            result_property="bc_score",
            parameters={},
            write_back=True,
        )

        assert "algo.betweenness" in query
        assert "nodeLabels:" in query
        assert "'Person'" in query
        assert "'Company'" in query
        assert "relationshipTypes:" in query
        assert "'KNOWS'" in query

    @pytest.mark.unit
    def test_build_wcc_query(self, algorithm_service):
        """Builds correct WCC query."""
        algo_info = get_algorithm("wcc")
        assert algo_info is not None

        query = algorithm_service._build_algorithm_query(
            algo_info=algo_info,
            node_labels=None,
            relationship_types=None,
            result_property="component_id",
            parameters={},
            write_back=True,
        )

        assert "algo.WCC" in query
        assert "componentId" in query
        assert "SET node.component_id" in query

    @pytest.mark.unit
    def test_build_cdlp_query_with_iterations(self, algorithm_service):
        """Builds correct CDLP query with max_iterations parameter."""
        algo_info = get_algorithm("cdlp")
        assert algo_info is not None

        query = algorithm_service._build_algorithm_query(
            algo_info=algo_info,
            node_labels=None,
            relationship_types=None,
            result_property="community_id",
            parameters={"max_iterations": 20},
            write_back=True,
        )

        assert "algo.labelPropagation" in query
        assert "maxIterations: 20" in query


# =============================================================================
# Background Execution Tests
# =============================================================================


class TestBackgroundExecution:
    """Tests for background algorithm execution."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_successful_execution_updates_status(self, algorithm_service, mock_db_service):
        """Successful execution updates status to completed."""
        execution = await algorithm_service.execute(
            user_id="user-001",
            user_name="testuser",
            algorithm_name="pagerank",
            result_property="pr_score",
        )

        # Wait for background task to complete
        await asyncio.sleep(0.2)

        updated = algorithm_service.get_execution(execution.execution_id)
        assert updated is not None
        assert updated.status == ExecutionStatus.COMPLETED
        assert updated.completed_at is not None
        assert updated.nodes_updated == 42  # From mock
        assert updated.duration_ms is not None
        # duration_ms >= 0 because mock executes very fast (sub-millisecond)
        assert updated.duration_ms >= 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_successful_execution_releases_lock(self, algorithm_service, lock_service):
        """Successful execution releases the lock."""
        await algorithm_service.execute(
            user_id="user-001",
            user_name="testuser",
            algorithm_name="pagerank",
            result_property="pr_score",
        )

        # Wait for background task to complete
        await asyncio.sleep(0.2)

        assert lock_service.is_locked() is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_failed_execution_updates_status(self, algorithm_service, mock_db_service):
        """Failed execution updates status with error message."""
        mock_db_service.execute_query = AsyncMock(
            side_effect=Exception("Database error")
        )

        execution = await algorithm_service.execute(
            user_id="user-001",
            user_name="testuser",
            algorithm_name="pagerank",
            result_property="pr_score",
        )

        # Wait for background task to complete
        await asyncio.sleep(0.2)

        updated = algorithm_service.get_execution(execution.execution_id)
        assert updated is not None
        assert updated.status == ExecutionStatus.FAILED
        assert updated.error_message is not None
        assert "Database error" in updated.error_message

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_failed_execution_releases_lock(self, algorithm_service, lock_service, mock_db_service):
        """Failed execution releases the lock."""
        mock_db_service.execute_query = AsyncMock(
            side_effect=Exception("Database error")
        )

        await algorithm_service.execute(
            user_id="user-001",
            user_name="testuser",
            algorithm_name="pagerank",
            result_property="pr_score",
        )

        # Wait for background task to complete
        await asyncio.sleep(0.2)

        assert lock_service.is_locked() is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_timeout_updates_status(self, algorithm_service, mock_db_service):
        """Timed out execution updates status."""
        async def slow_query(*args, **kwargs):
            await asyncio.sleep(10)
            return {"columns": ["count"], "rows": [[1]], "row_count": 1}

        mock_db_service.execute_query = slow_query

        execution = await algorithm_service.execute(
            user_id="user-001",
            user_name="testuser",
            algorithm_name="pagerank",
            result_property="pr_score",
            timeout_ms=100,  # Very short timeout
        )

        # Wait for timeout
        await asyncio.sleep(0.3)

        updated = algorithm_service.get_execution(execution.execution_id)
        assert updated is not None
        assert updated.status == ExecutionStatus.FAILED
        assert updated.error_message is not None
        assert "timed out" in updated.error_message.lower()


# =============================================================================
# Execution History Tests
# =============================================================================


class TestExecutionHistory:
    """Tests for execution history management."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execution_history_limit(self, mock_db_service, lock_service):
        """Execution history is limited to MAX_EXECUTION_HISTORY."""
        from wrapper.services.algorithm import MAX_EXECUTION_HISTORY

        service = AlgorithmService(
            db_service=mock_db_service,
            lock_service=lock_service,
        )

        # Add more executions than limit
        for i in range(MAX_EXECUTION_HISTORY + 10):
            execution = await service.execute(
                user_id="user-001",
                user_name="testuser",
                algorithm_name="pagerank",
                result_property=f"pr_{i}",
            )
            # Wait for completion and lock release
            await asyncio.sleep(0.05)
            await service._lock_service.release(execution.execution_id)

        # Should not exceed limit
        assert len(service._executions) <= MAX_EXECUTION_HISTORY
