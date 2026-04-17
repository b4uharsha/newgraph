"""Native algorithm execution endpoints.

Provides endpoints for running native Ryugraph algorithms:
- POST /algo/shortest_path - Find shortest path between nodes
- POST /algo/{name} - Execute algorithm
- GET /algo/status/{execution_id} - Check execution status
- GET /algo/algorithms - List available algorithms
- GET /algo/algorithms/{name} - Get algorithm details
"""

from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, HTTPException, status

from wrapper.algorithms.native import NATIVE_ALGORITHMS, get_native_algorithm
from wrapper.dependencies import (
    AlgorithmServiceDep,
    ControlPlaneClientDep,
    DatabaseServiceDep,
    UserIdDep,
    UserNameDep,
)
from wrapper.exceptions import WrapperError
from wrapper.logging import get_logger
from wrapper.models.requests import NativeAlgorithmRequest, ShortestPathRequest
from wrapper.models.responses import (
    AlgorithmInfoResponse,
    AlgorithmListResponse,
    AlgorithmParameterInfo,
    AlgorithmResponse,
    ErrorResponse,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/algo", tags=["Native Algorithms"])


@router.post(
    "/shortest_path",
    response_model=AlgorithmResponse,
    summary="Find shortest path",
    description="Find the shortest path between two nodes.",
    responses={
        404: {"model": ErrorResponse, "description": "Node not found"},
        503: {"model": ErrorResponse, "description": "Database not ready"},
    },
)
async def find_shortest_path(
    request: ShortestPathRequest,
    control_plane: ControlPlaneClientDep,
    db_service: DatabaseServiceDep,
    x_user_id: UserIdDep,
    x_user_name: UserNameDep,
) -> AlgorithmResponse:
    """Find the shortest path between two nodes.

    Uses Cypher's shortest path pattern to find the shortest path
    between the source and target nodes. Returns the path as a list
    of node IDs.

    Args:
        source_id: Source node ID
        target_id: Target node ID
        relationship_types: Optional list of relationship types to traverse
        max_depth: Maximum path depth (default: 10)
    """
    if not db_service.is_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not ready",
        )

    # Extract parameters from request (now directly on request, not in parameters dict)
    source_id = request.source_id
    target_id = request.target_id
    relationship_types = request.relationship_types
    max_depth = request.max_depth

    start_time = time.perf_counter()
    execution_id = str(uuid.uuid4())[:8]

    logger.info(
        "Finding shortest path",
        source_id=source_id,
        target_id=target_id,
        max_depth=max_depth,
        user_id=x_user_id,
    )

    try:
        # Build relationship pattern - the type and length must be inside the same brackets
        if relationship_types:
            # e.g., [:KNOWS|:FOLLOWS*1..5]
            rel_types = "|".join(f":{rt}" for rt in relationship_types)
            rel_pattern = f"[{rel_types}*1..{max_depth}]"
        else:
            # Any relationship type
            rel_pattern = f"[*1..{max_depth}]"

        # Use Cypher's shortestPath with variable-length relationships.
        # Returning `[n IN nodes(p) | n.id]` gives us a plain list of scalar
        # IDs (avoids depending on how the driver materialises node structs).
        query = f"""
        MATCH (source), (target)
        WHERE source.id = $source_id AND target.id = $target_id
        MATCH p = shortestPath((source)-{rel_pattern}-(target))
        RETURN [n IN nodes(p) | n.id] AS path_ids, length(p) AS path_length
        LIMIT 1
        """

        result = await db_service.execute_query(
            query,
            {"source_id": str(source_id), "target_id": str(target_id)},
        )

        duration_ms = int((time.perf_counter() - start_time) * 1000)

        path_result: dict | None = None
        if result["rows"]:
            row = result["rows"][0]
            path_ids_raw, path_length_raw = row[0], row[1]
            path_ids = [str(node_id) for node_id in (path_ids_raw or [])]
            path_result = {
                "path": path_ids,
                "length": int(path_length_raw) if path_length_raw is not None else 0,
                "source_id": source_id,
                "target_id": target_id,
                "found": True,
            }
        else:
            path_result = {
                "path": [],
                "length": 0,
                "source_id": source_id,
                "target_id": target_id,
                "found": False,
            }

        # Record activity
        await control_plane.record_activity()

        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()

        return AlgorithmResponse(
            execution_id=execution_id,
            algorithm_name="shortest_path",
            algorithm_type="native",
            status="completed",
            started_at=now,
            completed_at=now,
            result_property=None,
            node_label=None,
            nodes_updated=None,
            duration_ms=duration_ms,
            error_message=None,
            result=path_result,
        )

    except WrapperError:
        raise
    except Exception as e:
        logger.error("Shortest path failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Shortest path failed: {e!s}",
        ) from e


@router.post(
    "/{algorithm_name}",
    response_model=AlgorithmResponse,
    summary="Execute native algorithm",
    description="Execute a native Ryugraph algorithm.",
    responses={
        403: {"model": ErrorResponse, "description": "Permission denied"},
        404: {"model": ErrorResponse, "description": "Algorithm not found"},
        409: {"model": ErrorResponse, "description": "Instance locked"},
        503: {"model": ErrorResponse, "description": "Database not ready"},
    },
)
async def execute_algorithm(
    algorithm_name: str,
    request: NativeAlgorithmRequest,
    algorithm_service: AlgorithmServiceDep,
    control_plane: ControlPlaneClientDep,
    db_service: DatabaseServiceDep,
    x_user_id: UserIdDep,
    x_user_name: UserNameDep,
) -> AlgorithmResponse:
    """Execute a native Ryugraph algorithm.

    The algorithm runs synchronously and acquires an exclusive lock
    on the instance while executing. Only one algorithm can run at
    a time.

    Results are written to the specified result_property on each
    node. The property persists until overwritten by another
    algorithm execution.
    """
    if not db_service.is_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not ready",
        )

    logger.info(
        "Executing native algorithm",
        algorithm=algorithm_name,
        user_id=x_user_id,
        node_label=request.node_label,
        result_property=request.result_property,
    )

    execution = await algorithm_service.execute_native(
        user_id=x_user_id,
        user_name=x_user_name,
        algorithm_name=algorithm_name,
        node_label=request.node_label,
        edge_type=request.edge_type,
        result_property=request.result_property,
        parameters=request.parameters,
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
    "/status/{execution_id}",
    response_model=AlgorithmResponse,
    summary="Get execution status",
    description="Get the status of an algorithm execution.",
    responses={
        404: {"model": ErrorResponse, "description": "Execution not found"},
    },
)
async def get_execution_status(
    execution_id: str,
    algorithm_service: AlgorithmServiceDep,
) -> AlgorithmResponse:
    """Get status of an algorithm execution.

    Use this endpoint to poll the status of asynchronous algorithm
    executions or to retrieve details of past executions.
    """
    execution = algorithm_service.get_execution(execution_id)

    if execution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Execution not found: {execution_id}",
        )

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
    summary="List native algorithms",
    description="List all available native Ryugraph algorithms.",
)
async def list_algorithms() -> AlgorithmListResponse:
    """List available native algorithms.

    Returns information about all native algorithms including
    their parameters and descriptions.
    """
    algorithms = [
        AlgorithmInfoResponse(
            name=algo.info.name,
            type=algo.info.type,
            category=algo.info.category,
            description=algo.info.description,
            long_description=algo.info.long_description,
            parameters=[
                AlgorithmParameterInfo(
                    name=p.name,
                    type=p.type,
                    required=p.required,
                    default=p.default,
                    description=p.description or "",
                )
                for p in algo.info.parameters
            ],
            returns=algo.info.returns,
        )
        for algo in NATIVE_ALGORITHMS
    ]

    return AlgorithmListResponse(
        algorithms=algorithms,
        total_count=len(algorithms),
    )


@router.get(
    "/algorithms/{algorithm_name}",
    response_model=AlgorithmInfoResponse,
    summary="Get algorithm details",
    description="Get detailed information about a native algorithm.",
    responses={
        404: {"model": ErrorResponse, "description": "Algorithm not found"},
    },
)
async def get_algorithm_info(algorithm_name: str) -> AlgorithmInfoResponse:
    """Get detailed information about a native algorithm.

    Returns the algorithm's parameters, description, and return type.
    """
    algo = get_native_algorithm(algorithm_name)

    if algo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Algorithm not found: {algorithm_name}",
        )

    return AlgorithmInfoResponse(
        name=algo.info.name,
        type=algo.info.type,
        category=algo.info.category,
        description=algo.info.description,
        long_description=algo.info.long_description,
        parameters=[
            AlgorithmParameterInfo(
                name=p.name,
                type=p.type,
                required=p.required,
                default=p.default,
                description=p.description or "",
            )
            for p in algo.info.parameters
        ],
        returns=algo.info.returns,
    )
