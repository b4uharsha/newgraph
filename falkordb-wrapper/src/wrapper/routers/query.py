"""Query router for Cypher query execution."""

from __future__ import annotations

import structlog
from fastapi import APIRouter

from wrapper.dependencies import DatabaseServiceDep
from wrapper.models import QueryRequest, QueryResponse

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["Query"])


@router.post(
    "/query",
    response_model=QueryResponse,
    summary="Execute Cypher query",
    description="Execute a Cypher query against the graph database.",
)
async def execute_query(
    request: QueryRequest,
    db_service: DatabaseServiceDep,
) -> QueryResponse:
    """Execute a Cypher query.

    Supports:
    - READ queries (MATCH, RETURN)
    - Aggregations (COUNT, SUM, AVG)
    - Algorithm calls (CALL algo.xxx())
    - Parameterized queries

    Args:
        request: Query request with cypher, parameters, timeout_ms
        db_service: Database service (injected via DI)

    Returns:
        Query results with columns, rows, row_count, execution_time_ms, truncated

    Note: Exception handling is done centrally in main.py exception handlers.
    """
    logger.info(
        "query_request",
        query_length=len(request.query),
        param_count=len(request.parameters),
        timeout_ms=request.timeout_ms,
    )

    result = await db_service.execute_query(
        query=request.query,
        parameters=request.parameters,
        timeout_ms=request.timeout_ms,
    )

    logger.info(
        "query_completed",
        row_count=result["row_count"],
        execution_time_ms=result["execution_time_ms"],
    )

    # Flat response structure matching Ryugraph
    return QueryResponse(
        columns=result["columns"],
        rows=result["rows"],
        row_count=result["row_count"],
        execution_time_ms=int(result["execution_time_ms"]),
        truncated=result.get("truncated", False),
    )
