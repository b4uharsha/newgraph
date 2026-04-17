"""Algorithm service for orchestrating async graph algorithm execution.

Manages the execution lifecycle for FalkorDB's global analytics algorithms:
- PageRank
- Betweenness Centrality
- Weakly Connected Components (WCC)
- Community Detection Label Propagation (CDLP)

These algorithms run asynchronously with status polling support for large graphs.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

from wrapper.models.execution import (
    AlgorithmCategory,
    AlgorithmExecution,
    AlgorithmInfo,
    AlgorithmParameterInfo,
    AlgorithmType,
    ExecutionStatus,
)

if TYPE_CHECKING:
    from wrapper.services.database import DatabaseService
    from wrapper.services.lock import LockService

logger = structlog.get_logger(__name__)

# Maximum number of executions to keep in history
MAX_EXECUTION_HISTORY = 100


# =============================================================================
# Algorithm Registry - FalkorDB Global Analytics Algorithms
# =============================================================================

ALGORITHMS: dict[str, AlgorithmInfo] = {
    "pagerank": AlgorithmInfo(
        name="pagerank",
        display_name="PageRank",
        category=AlgorithmCategory.CENTRALITY,
        description="Measures node importance based on incoming links",
        cypher_procedure="pagerank.stream",
        result_field="score",
        supports_write_back=True,
        default_timeout_ms=300_000,  # 5 minutes
        parameters=[
            AlgorithmParameterInfo(
                name="node_label",
                type="string",
                required=False,
                default=None,
                description="Node label to filter (None = all nodes)",
            ),
            AlgorithmParameterInfo(
                name="relationship_type",
                type="string",
                required=False,
                default=None,
                description="Relationship type to traverse (None = all)",
            ),
        ],
    ),
    "betweenness": AlgorithmInfo(
        name="betweenness",
        display_name="Betweenness Centrality",
        category=AlgorithmCategory.CENTRALITY,
        description="Measures how often a node lies on shortest paths between other nodes",
        cypher_procedure="algo.betweenness",
        result_field="score",
        supports_write_back=True,
        default_timeout_ms=3_600_000,  # 1 hour - O(V*E) complexity
        parameters=[
            AlgorithmParameterInfo(
                name="node_labels",
                type="list[string]",
                required=False,
                default=None,
                description="Node labels to include",
            ),
            AlgorithmParameterInfo(
                name="relationship_types",
                type="list[string]",
                required=False,
                default=None,
                description="Relationship types to traverse",
            ),
        ],
    ),
    "wcc": AlgorithmInfo(
        name="wcc",
        display_name="Weakly Connected Components",
        category=AlgorithmCategory.COMMUNITY,
        description="Finds groups of nodes connected by any path (ignoring direction)",
        cypher_procedure="algo.WCC",
        result_field="componentId",
        supports_write_back=True,
        default_timeout_ms=300_000,  # 5 minutes
        parameters=[
            AlgorithmParameterInfo(
                name="node_labels",
                type="list[string]",
                required=False,
                default=None,
                description="Node labels to include",
            ),
            AlgorithmParameterInfo(
                name="relationship_types",
                type="list[string]",
                required=False,
                default=None,
                description="Relationship types to traverse",
            ),
        ],
    ),
    "cdlp": AlgorithmInfo(
        name="cdlp",
        display_name="Community Detection (Label Propagation)",
        category=AlgorithmCategory.COMMUNITY,
        description="Detects communities by propagating labels through the graph",
        cypher_procedure="algo.labelPropagation",
        result_field="communityId",
        supports_write_back=True,
        default_timeout_ms=300_000,  # 5 minutes
        parameters=[
            AlgorithmParameterInfo(
                name="max_iterations",
                type="int",
                required=False,
                default=10,
                description="Maximum iterations for convergence",
            ),
        ],
    ),
}


def get_algorithm(name: str) -> AlgorithmInfo | None:
    """Get algorithm info by name.

    Args:
        name: Algorithm name (case-insensitive).

    Returns:
        AlgorithmInfo or None if not found.
    """
    return ALGORITHMS.get(name.lower())


def list_algorithms() -> list[AlgorithmInfo]:
    """List all available algorithms.

    Returns:
        List of algorithm info objects.
    """
    return list(ALGORITHMS.values())


# =============================================================================
# Algorithm Service
# =============================================================================


class AlgorithmService:
    """Orchestrates async graph algorithm execution.

    Manages the full algorithm execution lifecycle:
    1. Lock acquisition (prevents concurrent algorithm runs)
    2. Cypher query construction with optional writeback
    3. Background execution with timeout
    4. Status tracking and history
    5. Lock release

    Thread-safe via asyncio primitives.
    """

    def __init__(
        self,
        db_service: DatabaseService,
        lock_service: LockService,
    ) -> None:
        """Initialize the algorithm service.

        Args:
            db_service: Database service for query execution.
            lock_service: Lock service for concurrency control.
        """
        self._db_service = db_service
        self._lock_service = lock_service
        self._executions: OrderedDict[str, AlgorithmExecution] = OrderedDict()
        self._running_tasks: dict[str, asyncio.Task[None]] = {}

        logger.debug("AlgorithmService initialized")

    def get_execution(self, execution_id: str) -> AlgorithmExecution | None:
        """Get execution by ID.

        Args:
            execution_id: Execution identifier.

        Returns:
            Execution record or None if not found.
        """
        return self._executions.get(execution_id)

    def list_executions(
        self,
        limit: int = 20,
        status: ExecutionStatus | None = None,
    ) -> list[AlgorithmExecution]:
        """List recent executions.

        Args:
            limit: Maximum number to return.
            status: Optional status filter.

        Returns:
            List of executions (most recent first).
        """
        executions = list(self._executions.values())

        if status is not None:
            executions = [e for e in executions if e.status == status]

        # Return most recent first
        executions.reverse()
        return executions[:limit]

    async def execute(
        self,
        user_id: str,
        user_name: str,
        algorithm_name: str,
        result_property: str,
        node_labels: list[str] | None = None,
        relationship_types: list[str] | None = None,
        parameters: dict[str, Any] | None = None,
        write_back: bool = True,
        timeout_ms: int | None = None,
    ) -> AlgorithmExecution:
        """Start async algorithm execution.

        Acquires lock, starts background task, returns immediately.
        Use get_execution() to poll status.

        Args:
            user_id: User requesting execution.
            user_name: Username for display.
            algorithm_name: Name of algorithm (pagerank, betweenness, wcc, cdlp).
            result_property: Property name to store results.
            node_labels: Node labels to include (None = all).
            relationship_types: Relationship types to traverse (None = all).
            parameters: Algorithm-specific parameters.
            write_back: Whether to write results to node properties.
            timeout_ms: Execution timeout (None = use algorithm default).

        Returns:
            Execution record with execution_id.

        Raises:
            ValueError: If algorithm not found.
            ResourceLockedError: If instance is locked.
        """
        # Validate algorithm
        algo_info = get_algorithm(algorithm_name)
        if algo_info is None:
            raise ValueError(f"Unknown algorithm: {algorithm_name}")

        # Acquire lock
        execution_id = await self._lock_service.acquire_or_raise(
            user_id=user_id,
            user_name=user_name,
            algorithm_name=algorithm_name,
            algorithm_type="native",
        )

        # Create execution record
        execution = AlgorithmExecution(
            execution_id=execution_id,
            algorithm_name=algorithm_name,
            algorithm_type=AlgorithmType.NATIVE,
            status=ExecutionStatus.RUNNING,
            started_at=datetime.now(UTC),
            user_id=user_id,
            user_name=user_name,
            node_labels=node_labels,
            relationship_types=relationship_types,
            result_property=result_property,
            parameters=parameters or {},
            write_back=write_back,
        )

        self._add_execution(execution)

        # Determine timeout
        effective_timeout = timeout_ms or algo_info.default_timeout_ms

        logger.info(
            "Starting algorithm execution",
            execution_id=execution_id,
            algorithm=algorithm_name,
            user_id=user_id,
            write_back=write_back,
            timeout_ms=effective_timeout,
        )

        # Start background task
        task = asyncio.create_task(
            self._run_algorithm_background(
                execution_id=execution_id,
                algo_info=algo_info,
                node_labels=node_labels,
                relationship_types=relationship_types,
                result_property=result_property,
                parameters=parameters or {},
                write_back=write_back,
                timeout_ms=effective_timeout,
            )
        )
        self._running_tasks[execution_id] = task

        return execution

    async def _run_algorithm_background(
        self,
        execution_id: str,
        algo_info: AlgorithmInfo,
        node_labels: list[str] | None,
        relationship_types: list[str] | None,
        result_property: str,
        parameters: dict[str, Any],
        write_back: bool,
        timeout_ms: int,
    ) -> None:
        """Background task for algorithm execution."""
        start_time = time.time()

        try:
            # Build and execute Cypher query
            cypher = self._build_algorithm_query(
                algo_info=algo_info,
                node_labels=node_labels,
                relationship_types=relationship_types,
                result_property=result_property,
                parameters=parameters,
                write_back=write_back,
            )

            logger.debug(
                "Executing algorithm query",
                execution_id=execution_id,
                cypher_length=len(cypher),
            )

            # Execute with timeout
            result = await asyncio.wait_for(
                self._db_service.execute_query(
                    query=cypher,
                    parameters={},
                    timeout_ms=timeout_ms,
                ),
                timeout=timeout_ms / 1000,
            )

            duration_ms = int((time.time() - start_time) * 1000)

            # Extract nodes_updated from result
            nodes_updated = 0
            if result.get("rows") and len(result["rows"]) > 0:
                first_row = result["rows"][0]
                if isinstance(first_row, list) and len(first_row) > 0:
                    nodes_updated = int(first_row[0]) if first_row[0] else 0

            # Update execution record
            execution = self._executions.get(execution_id)
            if execution:
                execution = execution.model_copy(
                    update={
                        "status": ExecutionStatus.COMPLETED,
                        "completed_at": datetime.now(UTC),
                        "nodes_updated": nodes_updated,
                        "duration_ms": duration_ms,
                    }
                )
                self._update_execution(execution)

            logger.info(
                "Algorithm completed",
                execution_id=execution_id,
                algorithm=algo_info.name,
                nodes_updated=nodes_updated,
                duration_ms=duration_ms,
            )

        except TimeoutError:
            duration_ms = int((time.time() - start_time) * 1000)

            execution = self._executions.get(execution_id)
            if execution:
                execution = execution.model_copy(
                    update={
                        "status": ExecutionStatus.FAILED,
                        "completed_at": datetime.now(UTC),
                        "duration_ms": duration_ms,
                        "error_message": f"Execution timed out after {timeout_ms}ms",
                    }
                )
                self._update_execution(execution)

            logger.error(
                "Algorithm timed out",
                execution_id=execution_id,
                timeout_ms=timeout_ms,
            )

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)

            execution = self._executions.get(execution_id)
            if execution:
                execution = execution.model_copy(
                    update={
                        "status": ExecutionStatus.FAILED,
                        "completed_at": datetime.now(UTC),
                        "duration_ms": duration_ms,
                        "error_message": str(e),
                    }
                )
                self._update_execution(execution)

            logger.error(
                "Algorithm failed",
                execution_id=execution_id,
                error=str(e),
            )

        finally:
            # Always release lock
            await self._lock_service.release(execution_id)
            self._running_tasks.pop(execution_id, None)

    def _build_algorithm_query(
        self,
        algo_info: AlgorithmInfo,
        node_labels: list[str] | None,
        relationship_types: list[str] | None,
        result_property: str,
        parameters: dict[str, Any],
        write_back: bool,
    ) -> str:
        """Build Cypher query for algorithm execution.

        Args:
            algo_info: Algorithm metadata.
            node_labels: Node labels to filter.
            relationship_types: Relationship types to filter.
            result_property: Property name for results.
            parameters: Algorithm parameters.
            write_back: Whether to write results to nodes.

        Returns:
            Complete Cypher query string.
        """
        # Build the procedure call based on algorithm type
        if algo_info.name == "pagerank":
            # pagerank.stream(label, relationship)
            label_arg = f"'{node_labels[0]}'" if node_labels else "null"
            rel_arg = f"'{relationship_types[0]}'" if relationship_types else "null"
            call_clause = f"CALL pagerank.stream({label_arg}, {rel_arg})"
            yield_clause = f"YIELD node, {algo_info.result_field}"

        elif algo_info.name == "betweenness":
            # algo.betweenness({nodeLabels: [...], relationshipTypes: [...]})
            config_parts = []
            if node_labels:
                labels_str = ", ".join(f"'{l}'" for l in node_labels)
                config_parts.append(f"nodeLabels: [{labels_str}]")
            if relationship_types:
                types_str = ", ".join(f"'{t}'" for t in relationship_types)
                config_parts.append(f"relationshipTypes: [{types_str}]")
            config = "{" + ", ".join(config_parts) + "}" if config_parts else "{}"
            call_clause = f"CALL algo.betweenness({config})"
            yield_clause = f"YIELD node, {algo_info.result_field}"

        elif algo_info.name == "wcc":
            # algo.WCC({nodeLabels: [...], relationshipTypes: [...]})
            config_parts = []
            if node_labels:
                labels_str = ", ".join(f"'{l}'" for l in node_labels)
                config_parts.append(f"nodeLabels: [{labels_str}]")
            if relationship_types:
                types_str = ", ".join(f"'{t}'" for t in relationship_types)
                config_parts.append(f"relationshipTypes: [{types_str}]")
            config = "{" + ", ".join(config_parts) + "}" if config_parts else "null"
            call_clause = f"CALL algo.WCC({config})"
            yield_clause = f"YIELD node, {algo_info.result_field}"

        elif algo_info.name == "cdlp":
            # algo.labelPropagation({maxIterations: N})
            config_parts = []
            if "max_iterations" in parameters:
                config_parts.append(f"maxIterations: {parameters['max_iterations']}")
            config = "{" + ", ".join(config_parts) + "}" if config_parts else ""
            call_clause = f"CALL algo.labelPropagation({config})"
            yield_clause = f"YIELD node, {algo_info.result_field}"

        else:
            raise ValueError(f"Unsupported algorithm: {algo_info.name}")

        # Build query with or without writeback
        if write_back:
            # Use CALL {} subquery pattern for side-effects
            query = f"""
CALL {{
  {call_clause}
  {yield_clause}
  SET node.{result_property} = {algo_info.result_field}
  RETURN count(*) AS updated
}}
RETURN updated
""".strip()
        else:
            # Just return results without writeback
            query = f"""
{call_clause}
{yield_clause}
RETURN count(node) AS total
""".strip()

        return query

    def _add_execution(self, execution: AlgorithmExecution) -> None:
        """Add execution to history with size limit."""
        self._executions[execution.execution_id] = execution

        # Enforce size limit
        while len(self._executions) > MAX_EXECUTION_HISTORY:
            self._executions.popitem(last=False)

    def _update_execution(self, execution: AlgorithmExecution) -> None:
        """Update existing execution record."""
        self._executions[execution.execution_id] = execution

    async def cancel_execution(self, execution_id: str) -> bool:
        """Cancel a running execution.

        Args:
            execution_id: Execution to cancel.

        Returns:
            True if cancelled, False if not found or not running.
        """
        task = self._running_tasks.get(execution_id)
        if task is None:
            return False

        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        execution = self._executions.get(execution_id)
        if execution and execution.status == ExecutionStatus.RUNNING:
            execution = execution.model_copy(
                update={
                    "status": ExecutionStatus.CANCELLED,
                    "completed_at": datetime.now(UTC),
                    "error_message": "Cancelled by user",
                }
            )
            self._update_execution(execution)

        await self._lock_service.release(execution_id)

        logger.info("Execution cancelled", execution_id=execution_id)
        return True
