"""Algorithm execution endpoints for FalkorDB global analytics.

Provides async execution for long-running graph algorithms:
- POST /algo/{name} - Start algorithm execution
- GET /algo/status/{execution_id} - Poll execution status
- GET /algo/executions - List recent executions
- GET /algo/algorithms - List available algorithms
- GET /algo/algorithms/{name} - Get algorithm details
- DELETE /algo/executions/{execution_id} - Cancel execution
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from wrapper.dependencies import (
    AlgorithmServiceDep,
    DatabaseServiceDep,
    UserIdDep,
    UserNameDep,
)
from wrapper.models.execution import (
    ExecutionStatus,
)
from wrapper.services.algorithm import get_algorithm, list_algorithms

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/algo", tags=["Algorithms"])


def _compute_elapsed_ms(started_at: datetime) -> int:
    """Compute elapsed time in milliseconds since execution started."""
    now = datetime.now(UTC)
    # Handle timezone-aware vs naive datetimes
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=UTC)
    return int((now - started_at).total_seconds() * 1000)


def _build_execution_response(execution: Any) -> "AlgorithmExecutionResponse":
    """Build AlgorithmExecutionResponse from execution model.

    Computes elapsed_ms for running executions dynamically.
    """
    # Compute elapsed_ms for running executions
    elapsed_ms = None
    if execution.status in (ExecutionStatus.PENDING, ExecutionStatus.RUNNING):
        elapsed_ms = _compute_elapsed_ms(execution.started_at)

    return AlgorithmExecutionResponse(
        execution_id=execution.execution_id,
        algorithm_name=execution.algorithm_name,
        algorithm_type=execution.algorithm_type.value,
        status=execution.status.value,
        started_at=execution.started_at.isoformat(),
        completed_at=execution.completed_at.isoformat() if execution.completed_at else None,
        user_id=execution.user_id,
        user_name=execution.user_name,
        node_labels=execution.node_labels,
        relationship_types=execution.relationship_types,
        result_property=execution.result_property,
        write_back=execution.write_back,
        nodes_updated=execution.nodes_updated,
        elapsed_ms=elapsed_ms,
        duration_ms=execution.duration_ms,
        error_message=execution.error_message,
    )


# =============================================================================
# Request/Response Models
# =============================================================================


class AlgorithmExecuteRequest(BaseModel):
    """Request body for algorithm execution."""

    result_property: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Property name to store results on nodes",
    )
    node_labels: list[str] | None = Field(
        default=None,
        description="Node labels to include (None = all nodes)",
    )
    relationship_types: list[str] | None = Field(
        default=None,
        description="Relationship types to traverse (None = all)",
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Algorithm-specific parameters",
    )
    write_back: bool = Field(
        default=True,
        description="Write results to node properties (True) or just return count (False)",
    )
    timeout_ms: int | None = Field(
        default=None,
        ge=60_000,
        le=7_200_000,  # Max 2 hours
        description="Execution timeout in ms (default: algorithm-specific)",
    )


class AlgorithmExecutionResponse(BaseModel):
    """Response for algorithm execution and status endpoints.

    Duration fields:
    - elapsed_ms: Time since execution started (available while running)
    - duration_ms: Total execution time (set when completed)
    """

    execution_id: str
    algorithm_name: str
    algorithm_type: str
    status: str
    started_at: str
    completed_at: str | None = None
    user_id: str
    user_name: str
    node_labels: list[str] | None = None
    relationship_types: list[str] | None = None
    result_property: str | None = None
    write_back: bool = True
    nodes_updated: int | None = None
    elapsed_ms: int | None = None
    duration_ms: int | None = None
    error_message: str | None = None


class AlgorithmParameterResponse(BaseModel):
    """Parameter information for an algorithm."""

    name: str
    type: str
    required: bool
    default: Any = None
    description: str = ""


class AlgorithmInfoResponse(BaseModel):
    """Information about an available algorithm."""

    name: str
    display_name: str
    category: str
    description: str
    cypher_procedure: str
    supports_write_back: bool
    default_timeout_ms: int
    parameters: list[AlgorithmParameterResponse]


class AlgorithmListResponse(BaseModel):
    """Response for listing available algorithms."""

    algorithms: list[AlgorithmInfoResponse]
    total_count: int


class ExecutionListResponse(BaseModel):
    """Response for listing executions."""

    executions: list[AlgorithmExecutionResponse]
    total_count: int


# =============================================================================
# Endpoints
# =============================================================================


@router.post(
    "/{algorithm_name}",
    response_model=AlgorithmExecutionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Execute algorithm",
    description="Start async execution of a graph algorithm. Returns immediately with execution_id for polling.",
    responses={
        202: {"description": "Algorithm execution started (async)"},
        400: {"description": "Invalid algorithm name or parameters"},
        403: {"description": "Permission denied"},
        409: {"description": "Instance locked by another algorithm"},
        503: {"description": "Database not ready"},
    },
)
async def execute_algorithm(
    algorithm_name: str,
    request: AlgorithmExecuteRequest,
    algorithm_service: AlgorithmServiceDep,
    db_service: DatabaseServiceDep,
    user_id: UserIdDep,
    user_name: UserNameDep,
) -> AlgorithmExecutionResponse:
    """Start async algorithm execution.

    Supported algorithms:
    - pagerank: PageRank centrality scores
    - betweenness: Betweenness centrality scores
    - wcc: Weakly connected component IDs
    - cdlp: Community detection via label propagation

    The algorithm runs in the background. Use GET /algo/status/{execution_id}
    to poll for completion. Results are written to the specified property
    on each node.
    """
    if not db_service.is_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not ready",
        )

    # Validate algorithm exists
    algo_info = get_algorithm(algorithm_name)
    if algo_info is None:
        available = [a.name for a in list_algorithms()]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown algorithm: {algorithm_name}. Available: {available}",
        )

    logger.info(
        "Algorithm execution requested",
        algorithm=algorithm_name,
        user_id=user_id,
        result_property=request.result_property,
        write_back=request.write_back,
    )

    try:
        execution = await algorithm_service.execute(
            user_id=user_id,
            user_name=user_name,
            algorithm_name=algorithm_name,
            result_property=request.result_property,
            node_labels=request.node_labels,
            relationship_types=request.relationship_types,
            parameters=request.parameters,
            write_back=request.write_back,
            timeout_ms=request.timeout_ms,
        )

        return _build_execution_response(execution)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.get(
    "/status/{execution_id}",
    response_model=AlgorithmExecutionResponse,
    summary="Get execution status",
    description="Poll the status of an algorithm execution.",
    responses={
        404: {"description": "Execution not found"},
    },
)
async def get_execution_status(
    execution_id: str,
    algorithm_service: AlgorithmServiceDep,
) -> AlgorithmExecutionResponse:
    """Get status of an algorithm execution.

    Poll this endpoint to check if execution has completed.
    Terminal states: completed, failed, cancelled.
    """
    execution = algorithm_service.get_execution(execution_id)

    if execution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Execution not found: {execution_id}",
        )

    return _build_execution_response(execution)


@router.get(
    "/executions",
    response_model=ExecutionListResponse,
    summary="List executions",
    description="List recent algorithm executions.",
)
async def list_executions(
    algorithm_service: AlgorithmServiceDep,
    limit: int = 20,
    status_filter: ExecutionStatus | None = None,
) -> ExecutionListResponse:
    """List recent algorithm executions.

    Returns most recent first. Use status_filter to filter by status.
    """
    executions = algorithm_service.list_executions(limit=limit, status=status_filter)

    return ExecutionListResponse(
        executions=[_build_execution_response(e) for e in executions],
        total_count=len(executions),
    )


@router.delete(
    "/executions/{execution_id}",
    summary="Cancel execution",
    description="Cancel a running algorithm execution.",
    responses={
        404: {"description": "Execution not found or not running"},
    },
)
async def cancel_execution(
    execution_id: str,
    algorithm_service: AlgorithmServiceDep,
) -> dict[str, str]:
    """Cancel a running algorithm execution.

    Only works for executions in 'running' status.
    """
    success = await algorithm_service.cancel_execution(execution_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Execution not found or not running: {execution_id}",
        )

    return {"status": "cancelled", "execution_id": execution_id}


@router.get(
    "/algorithms",
    response_model=AlgorithmListResponse,
    summary="List algorithms",
    description="List all available graph algorithms.",
)
async def list_available_algorithms() -> AlgorithmListResponse:
    """List available algorithms.

    Returns information about each algorithm including parameters
    and default timeout.
    """
    algorithms = list_algorithms()

    return AlgorithmListResponse(
        algorithms=[
            AlgorithmInfoResponse(
                name=a.name,
                display_name=a.display_name,
                category=a.category.value,
                description=a.description,
                cypher_procedure=a.cypher_procedure,
                supports_write_back=a.supports_write_back,
                default_timeout_ms=a.default_timeout_ms,
                parameters=[
                    AlgorithmParameterResponse(
                        name=p.name,
                        type=p.type,
                        required=p.required,
                        default=p.default,
                        description=p.description,
                    )
                    for p in a.parameters
                ],
            )
            for a in algorithms
        ],
        total_count=len(algorithms),
    )


@router.get(
    "/algorithms/{algorithm_name}",
    response_model=AlgorithmInfoResponse,
    summary="Get algorithm details",
    description="Get detailed information about a specific algorithm.",
    responses={
        404: {"description": "Algorithm not found"},
    },
)
async def get_algorithm_info(algorithm_name: str) -> AlgorithmInfoResponse:
    """Get detailed information about an algorithm.

    Includes parameters, timeout, and description.
    """
    algo = get_algorithm(algorithm_name)

    if algo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Algorithm not found: {algorithm_name}",
        )

    return AlgorithmInfoResponse(
        name=algo.name,
        display_name=algo.display_name,
        category=algo.category.value,
        description=algo.description,
        cypher_procedure=algo.cypher_procedure,
        supports_write_back=algo.supports_write_back,
        default_timeout_ms=algo.default_timeout_ms,
        parameters=[
            AlgorithmParameterResponse(
                name=p.name,
                type=p.type,
                required=p.required,
                default=p.default,
                description=p.description,
            )
            for p in algo.parameters
        ],
    )
