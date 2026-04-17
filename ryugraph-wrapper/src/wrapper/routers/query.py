"""Query execution endpoint.

Provides /query endpoint for executing Cypher queries against the graph.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from wrapper.dependencies import ControlPlaneClientDep, DatabaseServiceDep
from wrapper.logging import get_logger
from wrapper.models.requests import QueryRequest
from wrapper.models.responses import ErrorResponse, QueryResponse

logger = get_logger(__name__)

router = APIRouter(prefix="/query", tags=["Query"])


@router.post(
    "",
    response_model=QueryResponse,
    summary="Execute Cypher query",
    description="Execute a Cypher query against the graph database.",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid query"},
        408: {"model": ErrorResponse, "description": "Query timeout"},
        503: {"model": ErrorResponse, "description": "Database not ready"},
    },
)
async def execute_query(
    request: QueryRequest,
    db_service: DatabaseServiceDep,
    control_plane: ControlPlaneClientDep,
) -> QueryResponse:
    """Execute a Cypher query.

    The query is executed against the in-memory graph database.
    Results are returned as a list of columns and rows.

    Query execution respects the configured timeout. If the query
    takes longer than the timeout, it will be cancelled and a
    408 error returned.

    Note: This endpoint is read-only. Modification queries (CREATE,
    SET, DELETE) are not permitted via this endpoint.
    """
    if not db_service.is_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not ready",
        )

    # Basic validation - block modification queries
    query_upper = request.query.upper().strip()
    forbidden_keywords = ["CREATE", "SET", "DELETE", "REMOVE", "MERGE", "DROP"]
    for keyword in forbidden_keywords:
        if keyword in query_upper:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Modification queries not allowed via /query. "
                f"Found forbidden keyword: {keyword}",
            )

    logger.info(
        "Executing query",
        query_length=len(request.query),
        has_parameters=bool(request.parameters),
        timeout_ms=request.timeout_ms,
    )

    # QueryTimeoutError / QueryError propagate to the app-level
    # exception handlers registered in main.py, which return the
    # structured {"error": {"code", "message", "details"}} envelope.
    result = await db_service.execute_query(
        query=request.query,
        parameters=request.parameters,
        timeout_ms=request.timeout_ms,
    )

    # Record activity for inactivity timeout tracking
    await control_plane.record_activity()

    return QueryResponse(
        columns=result["columns"],
        rows=result["rows"],
        row_count=result["row_count"],
        execution_time_ms=result["execution_time_ms"],
        truncated=result.get("truncated", False),
    )
