"""FastAPI application entry point for FalkorDB wrapper.

This module creates the FastAPI application with:
- Proper lifespan management (startup/shutdown)
- Centralized exception handling
- Router registration
- Dependency injection via app.state
"""

from __future__ import annotations

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from wrapper.config import get_settings
from wrapper.exceptions import (
    DatabaseError,
    DatabaseNotInitializedError,
    QueryError,
    QuerySyntaxError,
    QueryTimeoutError,
    ResourceLockedError,
    WrapperError,
)
from wrapper.lifespan import lifespan
from wrapper.logging import configure_logging
from wrapper.routers import algo, health, lock, query, schema

logger = structlog.get_logger(__name__)


def _init_logging() -> None:
    """Initialize logging configuration."""
    try:
        settings = get_settings()
        configure_logging(settings.logging)
    except Exception:
        # During testing, settings may not be available
        pass


# Configure logging on module load (may fail during tests)
_init_logging()

# Create FastAPI app with lifespan
app = FastAPI(
    title="FalkorDB Wrapper",
    version="0.1.0",
    description="Graph OLAP wrapper for FalkorDB",
    lifespan=lifespan,
)

# Include routers
app.include_router(health.router)
app.include_router(query.router)
app.include_router(schema.router)
app.include_router(lock.router)
app.include_router(algo.router)


# =============================================================================
# Centralized Exception Handlers
# =============================================================================


@app.exception_handler(WrapperError)
async def wrapper_error_handler(request: Request, exc: WrapperError) -> JSONResponse:
    """Handle all WrapperError subclasses.

    Uses the http_status and error_code defined on each exception class.
    """
    logger.warning(
        "wrapper_error",
        error_code=exc.error_code,
        message=exc.message,
        details=exc.details,
        path=request.url.path,
    )
    return JSONResponse(
        status_code=exc.http_status,
        content=exc.to_dict(),
    )


@app.exception_handler(QuerySyntaxError)
async def query_syntax_error_handler(request: Request, exc: QuerySyntaxError) -> JSONResponse:
    """Handle Cypher syntax errors (400 Bad Request)."""
    logger.warning(
        "query_syntax_error",
        error=str(exc),
        details=exc.details,
        path=request.url.path,
    )
    return JSONResponse(
        status_code=400,
        content=exc.to_dict(),
    )


@app.exception_handler(QueryTimeoutError)
async def query_timeout_handler(request: Request, exc: QueryTimeoutError) -> JSONResponse:
    """Handle query timeout errors (408 Request Timeout)."""
    logger.warning(
        "query_timeout",
        timeout_ms=exc.timeout_ms,
        elapsed_ms=exc.elapsed_ms,
        path=request.url.path,
    )
    return JSONResponse(
        status_code=408,
        content=exc.to_dict(),
    )


@app.exception_handler(DatabaseNotInitializedError)
async def database_not_initialized_handler(
    request: Request, exc: DatabaseNotInitializedError
) -> JSONResponse:
    """Handle database not initialized errors (503 Service Unavailable)."""
    logger.error(
        "database_not_initialized",
        path=request.url.path,
    )
    return JSONResponse(
        status_code=503,
        content=exc.to_dict(),
    )


@app.exception_handler(ResourceLockedError)
async def resource_locked_handler(request: Request, exc: ResourceLockedError) -> JSONResponse:
    """Handle resource locked errors (409 Conflict)."""
    logger.warning(
        "resource_locked",
        error=str(exc),
        details=exc.details,
        path=request.url.path,
    )
    return JSONResponse(
        status_code=409,
        content=exc.to_dict(),
    )


@app.exception_handler(QueryError)
async def query_error_handler(request: Request, exc: QueryError) -> JSONResponse:
    """Handle general query errors (400 Bad Request)."""
    logger.error(
        "query_error",
        error_code=exc.error_code,
        message=exc.message,
        path=request.url.path,
    )
    return JSONResponse(
        status_code=400,
        content=exc.to_dict(),
    )


@app.exception_handler(DatabaseError)
async def database_error_handler(request: Request, exc: DatabaseError) -> JSONResponse:
    """Handle database errors (500 Internal Server Error)."""
    logger.error(
        "database_error",
        error_code=exc.error_code,
        message=exc.message,
        path=request.url.path,
    )
    return JSONResponse(
        status_code=500,
        content=exc.to_dict(),
    )


# =============================================================================
# Root Endpoint
# =============================================================================


@app.get("/")
async def root() -> JSONResponse:
    """API info endpoint."""
    settings = get_settings()
    return JSONResponse(
        {
            "name": "FalkorDB Wrapper",
            "version": "0.1.0",
            "instance_id": settings.wrapper.instance_id,
            "graph_name": f"graph_{settings.wrapper.snapshot_id}",
            "endpoints": {
                "health": "/health",
                "ready": "/ready",
                "status": "/status",
                "query": "/query",
                "schema": "/schema",
                "lock": "/lock",
                "algo": "/algo",
            },
        }
    )


# =============================================================================
# CLI Entry Point
# =============================================================================


def run() -> None:
    """Run the application (used by CLI)."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "wrapper.main:app",
        host=settings.wrapper.host,
        port=settings.wrapper.port,
        log_config=None,  # Use our structlog config
    )


if __name__ == "__main__":
    run()
