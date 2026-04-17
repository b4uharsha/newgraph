"""Algorithm service for orchestrating graph algorithm execution.

Coordinates lock acquisition, algorithm execution, result writeback,
and execution history tracking.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import OrderedDict
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from wrapper.algorithms.native import get_native_algorithm
from wrapper.algorithms.networkx import execute_networkx_algorithm, get_algorithm_info
from wrapper.algorithms.registry import AlgorithmType
from wrapper.exceptions import (
    AlgorithmError,
    AlgorithmNotFoundError,
)
from wrapper.logging import get_logger
from wrapper.models.execution import AlgorithmExecution, ExecutionStatus

if TYPE_CHECKING:
    from wrapper.services.database import DatabaseService
    from wrapper.services.lock import LockService

logger = get_logger(__name__)

# Maximum number of executions to keep in history
MAX_EXECUTION_HISTORY = 100


class AlgorithmService:
    """Orchestrates graph algorithm execution.

    Manages the full algorithm execution lifecycle:
    1. Lock acquisition
    2. Algorithm execution (native or NetworkX)
    3. Result writeback to graph
    4. Lock release
    5. Execution history tracking
    """

    def __init__(
        self,
        db_service: DatabaseService,
        lock_service: LockService,
    ) -> None:
        """Initialize the algorithm service.

        Args:
            db_service: Database service for graph operations.
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

    async def execute_native(
        self,
        user_id: str,
        user_name: str,
        algorithm_name: str,
        node_label: str | None,
        edge_type: str | None,
        result_property: str,
        parameters: dict[str, Any],
    ) -> AlgorithmExecution:
        """Execute a native Ryugraph algorithm.

        Acquires lock, runs the algorithm, and releases lock.

        Args:
            user_id: User requesting execution.
            user_name: Username for display.
            algorithm_name: Name of the native algorithm.
            node_label: Target node label (None = all).
            edge_type: Target edge type (None = all).
            result_property: Property to store results.
            parameters: Algorithm parameters.

        Returns:
            Execution record.

        Raises:
            AlgorithmNotFoundError: If algorithm doesn't exist.
            ResourceLockedError: If instance is locked.
            AlgorithmError: If execution fails.
        """
        # Validate algorithm exists
        algo = get_native_algorithm(algorithm_name)
        if algo is None:
            raise AlgorithmNotFoundError(algorithm_name)

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
            user_id=user_id,
            user_name=user_name,
            node_label=node_label,
            edge_type=edge_type,
            result_property=result_property,
            parameters=parameters,
            started_at=datetime.now(UTC),
        )

        self._add_execution(execution)

        logger.info(
            "Starting native algorithm execution",
            execution_id=execution_id,
            algorithm=algorithm_name,
            user_id=user_id,
        )

        try:
            # Execute algorithm
            result = await algo.execute(
                db_service=self._db_service,
                node_label=node_label,
                edge_type=edge_type,
                result_property=result_property,
                parameters=parameters,
            )

            # Update execution record
            execution = execution.model_copy(
                update={
                    "status": ExecutionStatus.COMPLETED,
                    "completed_at": datetime.now(UTC),
                    "nodes_updated": result.get("nodes_updated", 0),
                    "duration_ms": result.get("duration_ms", 0),
                    "result_metadata": result,
                }
            )
            self._update_execution(execution)

            logger.info(
                "Native algorithm completed",
                execution_id=execution_id,
                nodes_updated=result.get("nodes_updated", 0),
                duration_ms=result.get("duration_ms", 0),
            )

        except Exception as e:
            # Update execution with error
            execution = execution.model_copy(
                update={
                    "status": ExecutionStatus.FAILED,
                    "completed_at": datetime.now(UTC),
                    "error_message": str(e),
                }
            )
            self._update_execution(execution)

            logger.error(
                "Native algorithm failed",
                execution_id=execution_id,
                error=str(e),
            )
            raise

        finally:
            # Always release lock
            await self._lock_service.release(execution_id)

        return execution

    async def execute_networkx(
        self,
        user_id: str,
        user_name: str,
        algorithm_name: str,
        node_label: str | None,
        edge_type: str | None,
        result_property: str,
        parameters: dict[str, Any],
        subgraph_query: str | None = None,
        timeout_ms: int | None = None,
    ) -> AlgorithmExecution:
        """Execute a NetworkX algorithm.

        Acquires lock, extracts graph, runs algorithm, writes back results.

        Args:
            user_id: User requesting execution.
            user_name: Username for display.
            algorithm_name: Name of the NetworkX algorithm.
            node_label: Target node label (None = all).
            edge_type: Target edge type (None = all).
            result_property: Property to store results.
            parameters: Algorithm parameters.
            subgraph_query: Optional Cypher query for subgraph selection.
            timeout_ms: Execution timeout in milliseconds.

        Returns:
            Execution record.

        Raises:
            AlgorithmNotFoundError: If algorithm doesn't exist.
            ResourceLockedError: If instance is locked.
            AlgorithmError: If execution fails.
        """
        # Validate algorithm exists
        algo_info = get_algorithm_info(algorithm_name)
        if algo_info is None:
            raise AlgorithmNotFoundError(algorithm_name)

        # Acquire lock
        execution_id = await self._lock_service.acquire_or_raise(
            user_id=user_id,
            user_name=user_name,
            algorithm_name=algorithm_name,
            algorithm_type="networkx",
        )

        # Create execution record
        execution = AlgorithmExecution(
            execution_id=execution_id,
            algorithm_name=algorithm_name,
            algorithm_type=AlgorithmType.NETWORKX,
            status=ExecutionStatus.RUNNING,
            user_id=user_id,
            user_name=user_name,
            node_label=node_label,
            edge_type=edge_type,
            result_property=result_property,
            parameters=parameters,
            started_at=datetime.now(UTC),
        )

        self._add_execution(execution)

        logger.info(
            "Starting NetworkX algorithm execution",
            execution_id=execution_id,
            algorithm=algorithm_name,
            user_id=user_id,
        )

        try:
            # Execute with optional timeout
            if timeout_ms:
                timeout_seconds = timeout_ms / 1000
                result = await asyncio.wait_for(
                    execute_networkx_algorithm(
                        db_service=self._db_service,
                        algorithm_name=algorithm_name,
                        node_label=node_label,
                        edge_type=edge_type,
                        result_property=result_property,
                        parameters=parameters,
                        subgraph_query=subgraph_query,
                    ),
                    timeout=timeout_seconds,
                )
            else:
                result = await execute_networkx_algorithm(
                    db_service=self._db_service,
                    algorithm_name=algorithm_name,
                    node_label=node_label,
                    edge_type=edge_type,
                    result_property=result_property,
                    parameters=parameters,
                    subgraph_query=subgraph_query,
                )

            # Update execution record
            execution = execution.model_copy(
                update={
                    "status": ExecutionStatus.COMPLETED,
                    "completed_at": datetime.now(UTC),
                    "nodes_updated": result.get("nodes_updated", 0),
                    "duration_ms": result.get("duration_ms", 0),
                    "result_metadata": result,
                }
            )
            self._update_execution(execution)

            logger.info(
                "NetworkX algorithm completed",
                execution_id=execution_id,
                nodes_updated=result.get("nodes_updated", 0),
                duration_ms=result.get("duration_ms", 0),
            )

        except TimeoutError as e:
            execution = execution.model_copy(
                update={
                    "status": ExecutionStatus.FAILED,
                    "completed_at": datetime.now(UTC),
                    "error_message": f"Execution timed out after {timeout_ms}ms",
                }
            )
            self._update_execution(execution)

            logger.error(
                "NetworkX algorithm timed out",
                execution_id=execution_id,
                timeout_ms=timeout_ms,
            )
            raise AlgorithmError(
                f"Algorithm execution timed out after {timeout_ms}ms",
                algorithm_name=algorithm_name,
            ) from e

        except Exception as e:
            execution = execution.model_copy(
                update={
                    "status": ExecutionStatus.FAILED,
                    "completed_at": datetime.now(UTC),
                    "error_message": str(e),
                }
            )
            self._update_execution(execution)

            logger.error(
                "NetworkX algorithm failed",
                execution_id=execution_id,
                error=str(e),
            )
            raise

        finally:
            # Always release lock
            await self._lock_service.release(execution_id)

        return execution

    async def execute_native_async(
        self,
        user_id: str,
        user_name: str,
        algorithm_name: str,
        node_label: str | None,
        edge_type: str | None,
        result_property: str,
        parameters: dict[str, Any],
    ) -> str:
        """Start native algorithm execution in background.

        Returns immediately with execution ID. Use get_execution()
        to check status.

        Args:
            user_id: User requesting execution.
            user_name: Username for display.
            algorithm_name: Algorithm name.
            node_label: Target node label.
            edge_type: Target edge type.
            result_property: Property for results.
            parameters: Algorithm parameters.

        Returns:
            Execution ID.

        Raises:
            AlgorithmNotFoundError: If algorithm doesn't exist.
            ResourceLockedError: If instance is locked.
        """
        # Validate algorithm
        algo = get_native_algorithm(algorithm_name)
        if algo is None:
            raise AlgorithmNotFoundError(algorithm_name)

        # Acquire lock first (this validates the request)
        execution_id = await self._lock_service.acquire_or_raise(
            user_id=user_id,
            user_name=user_name,
            algorithm_name=algorithm_name,
            algorithm_type="native",
        )

        # Create pending execution
        execution = AlgorithmExecution(
            execution_id=execution_id,
            algorithm_name=algorithm_name,
            algorithm_type=AlgorithmType.NATIVE,
            status=ExecutionStatus.RUNNING,
            user_id=user_id,
            user_name=user_name,
            node_label=node_label,
            edge_type=edge_type,
            result_property=result_property,
            parameters=parameters,
            started_at=datetime.now(UTC),
        )
        self._add_execution(execution)

        # Start background task
        task = asyncio.create_task(
            self._run_native_background(
                execution_id=execution_id,
                algo=algo,
                node_label=node_label,
                edge_type=edge_type,
                result_property=result_property,
                parameters=parameters,
            )
        )
        self._running_tasks[execution_id] = task

        logger.info(
            "Started background native algorithm",
            execution_id=execution_id,
            algorithm=algorithm_name,
        )

        return execution_id

    async def _run_native_background(
        self,
        execution_id: str,
        algo: Any,
        node_label: str | None,
        edge_type: str | None,
        result_property: str,
        parameters: dict[str, Any],
    ) -> None:
        """Background task for native algorithm execution."""
        try:
            result = await algo.execute(
                db_service=self._db_service,
                node_label=node_label,
                edge_type=edge_type,
                result_property=result_property,
                parameters=parameters,
            )

            execution = self._executions.get(execution_id)
            if execution:
                execution = execution.model_copy(
                    update={
                        "status": ExecutionStatus.COMPLETED,
                        "completed_at": datetime.now(UTC),
                        "nodes_updated": result.get("nodes_updated", 0),
                        "duration_ms": result.get("duration_ms", 0),
                        "result_metadata": result,
                    }
                )
                self._update_execution(execution)

            logger.info(
                "Background native algorithm completed",
                execution_id=execution_id,
            )

        except Exception as e:
            execution = self._executions.get(execution_id)
            if execution:
                execution = execution.model_copy(
                    update={
                        "status": ExecutionStatus.FAILED,
                        "completed_at": datetime.now(UTC),
                        "error_message": str(e),
                    }
                )
                self._update_execution(execution)

            logger.error(
                "Background native algorithm failed",
                execution_id=execution_id,
                error=str(e),
            )

        finally:
            await self._lock_service.release(execution_id)
            self._running_tasks.pop(execution_id, None)

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
            with contextlib.suppress(asyncio.CancelledError):
                await task

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
