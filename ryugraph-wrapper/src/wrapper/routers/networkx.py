"""NetworkX algorithm execution endpoints.

Provides endpoints for running NetworkX algorithms:
- POST /networkx/{name} - Execute algorithm
- GET /networkx/algorithms - List available algorithms
- GET /networkx/algorithms/{name} - Get algorithm details
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status
from graph_olap_schemas import AlgorithmCategory

from wrapper.algorithms.networkx import get_algorithm_info, list_algorithms
from wrapper.dependencies import (
    AlgorithmServiceDep,
    ControlPlaneClientDep,
    DatabaseServiceDep,
    UserIdDep,
    UserNameDep,
)
from wrapper.logging import get_logger
from wrapper.models.requests import AlgorithmRequest
from wrapper.models.responses import (
    AlgorithmInfoResponse,
    AlgorithmListResponse,
    AlgorithmParameterInfo,
    AlgorithmResponse,
    ErrorResponse,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/networkx", tags=["NetworkX Algorithms"])


def _serialize_default(val: Any) -> Any:
    """Convert default value to JSON-serializable form."""
    if val is None:
        return None
    if isinstance(val, (str, int, float, bool)):
        return val
    if isinstance(val, type):
        return val.__name__
    if callable(val):
        return getattr(val, "__name__", str(val))
    # For any other complex types, convert to string representation
    try:
        # Try to see if it's JSON-serializable as-is
        import json

        json.dumps(val)
        return val
    except (TypeError, ValueError):
        return str(val)


@router.post(
    "/{algorithm_name}",
    response_model=AlgorithmResponse,
    summary="Execute NetworkX algorithm",
    description="Execute a NetworkX graph algorithm.",
    responses={
        403: {"model": ErrorResponse, "description": "Permission denied"},
        404: {"model": ErrorResponse, "description": "Algorithm not found"},
        409: {"model": ErrorResponse, "description": "Instance locked"},
        503: {"model": ErrorResponse, "description": "Database not ready"},
    },
)
async def execute_algorithm(
    algorithm_name: str,
    request: AlgorithmRequest,
    algorithm_service: AlgorithmServiceDep,
    control_plane: ControlPlaneClientDep,
    db_service: DatabaseServiceDep,
    x_user_id: UserIdDep,
    x_user_name: UserNameDep,
) -> AlgorithmResponse:
    """Execute a NetworkX algorithm.

    NetworkX algorithms are executed by:
    1. Extracting graph data from Ryugraph to NetworkX format
    2. Running the algorithm in NetworkX
    3. Writing results back to node properties in Ryugraph

    The execution acquires an exclusive lock on the instance.
    Execution time depends on graph size and algorithm complexity.

    Use the subgraph_query parameter to run algorithms on a subset
    of the graph for better performance on large graphs.
    """
    if not db_service.is_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not ready",
        )

    logger.info(
        "Executing NetworkX algorithm",
        algorithm=algorithm_name,
        user_id=x_user_id,
        node_label=request.node_label,
        result_property=request.result_property,
    )

    execution = await algorithm_service.execute_networkx(
        user_id=x_user_id,
        user_name=x_user_name,
        algorithm_name=algorithm_name,
        node_label=request.node_label,
        edge_type=request.edge_type,
        result_property=request.result_property,
        parameters=request.parameters,
        subgraph_query=request.subgraph_query,
        timeout_ms=request.timeout_ms,
    )

    # Record activity for inactivity timeout tracking
    await control_plane.record_activity()

    return AlgorithmResponse(
        execution_id=execution.execution_id,
        algorithm_name=execution.algorithm_name,
        algorithm_type=execution.algorithm_type,
        status=execution.status,
        started_at=execution.started_at.isoformat(),
        completed_at=execution.completed_at.isoformat() if execution.completed_at else None,
        result_property=execution.result_property,
        node_label=execution.node_label,
        nodes_updated=execution.nodes_updated,
        duration_ms=execution.duration_ms,
        error_message=execution.error_message,
    )


@router.get(
    "/algorithms",
    response_model=AlgorithmListResponse,
    summary="List NetworkX algorithms",
    description="List available NetworkX algorithms with optional filtering.",
)
async def list_networkx_algorithms(
    category: Annotated[
        str | None,
        Query(description="Filter by category (centrality, community, path, etc.)"),
    ] = None,
    search: Annotated[
        str | None,
        Query(description="Search by name or description"),
    ] = None,
) -> AlgorithmListResponse:
    """List available NetworkX algorithms.

    NetworkX algorithms are discovered dynamically from the installed
    NetworkX package. Use the category and search parameters to filter
    results.

    Available categories:
    - centrality: PageRank, betweenness, closeness, etc.
    - community: Connected components, cliques, etc.
    - path: Shortest path algorithms
    - clustering: Clustering coefficients
    - similarity: Node similarity measures
    - link_prediction: Link prediction algorithms
    """
    # Convert category string to enum if provided
    category_enum: AlgorithmCategory | None = None
    if category:
        try:
            category_enum = AlgorithmCategory(category)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid category: {category}. Valid categories: "
                f"{[c.value for c in AlgorithmCategory]}",
            ) from e

    algos = list_algorithms(category=category_enum, search=search)

    algorithms = [
        AlgorithmInfoResponse(
            name=algo.name,
            type=algo.type,
            category=algo.category,
            description=algo.description,
            long_description=algo.long_description,
            parameters=[
                AlgorithmParameterInfo(
                    name=p.name,
                    type=p.type,
                    required=p.required,
                    default=_serialize_default(p.default),
                    description=p.description or "",
                )
                for p in algo.parameters
            ],
            returns=algo.returns,
        )
        for algo in algos
    ]

    return AlgorithmListResponse(
        algorithms=algorithms,
        total_count=len(algorithms),
    )


@router.get(
    "/algorithms/{algorithm_name}",
    response_model=AlgorithmInfoResponse,
    summary="Get algorithm details",
    description="Get detailed information about a NetworkX algorithm.",
    responses={
        404: {"model": ErrorResponse, "description": "Algorithm not found"},
    },
)
async def get_networkx_algorithm_info(algorithm_name: str) -> AlgorithmInfoResponse:
    """Get detailed information about a NetworkX algorithm.

    Returns the algorithm's parameters extracted from the NetworkX
    function signature and docstring.
    """
    algo_info = get_algorithm_info(algorithm_name)

    if algo_info is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Algorithm not found: {algorithm_name}",
        )

    return AlgorithmInfoResponse(
        name=algo_info.name,
        type=algo_info.type,
        category=algo_info.category,
        description=algo_info.description,
        long_description=algo_info.long_description,
        parameters=[
            AlgorithmParameterInfo(
                name=p.name,
                type=p.type,
                required=p.required,
                default=_serialize_default(p.default),
                description=p.description or "",
            )
            for p in algo_info.parameters
        ],
        returns=algo_info.returns,
    )
