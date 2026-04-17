"""FastAPI application entrypoint.

The Ryugraph Wrapper provides a REST API for:
- Cypher query execution
- Native Ryugraph algorithm execution
- NetworkX algorithm execution
- Graph schema inspection
- Instance status and health monitoring
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from wrapper.config import get_settings
from wrapper.exceptions import (
    AlgorithmNotFoundError,
    QueryTimeoutError,
    ResourceLockedError,
    WrapperError,
)
from wrapper.lifespan import lifespan
from wrapper.logging import configure_logging, get_logger
from wrapper.routers import algo, health, lock, networkx, query, schema

# Configure logging on module load
settings = get_settings()
configure_logging(settings.logging)

logger = get_logger(__name__)

# =============================================================================
# Application Factory
# =============================================================================


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance.
    """
    app = FastAPI(
        title="Ryugraph Wrapper API",
        description=(
            "REST API for executing Cypher queries and graph algorithms "
            "against an embedded Ryugraph (KuzuDB fork) database instance."
        ),
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # =========================================================================
    # Middleware
    # =========================================================================

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # =========================================================================
    # Exception Handlers
    # =========================================================================

    @app.exception_handler(WrapperError)
    async def wrapper_error_handler(request: Request, exc: WrapperError) -> JSONResponse:
        """Handle custom wrapper exceptions."""
        return JSONResponse(
            status_code=exc.http_status,
            content=exc.to_dict(),  # Uses structured format: {"error": {"code", "message", "details"}}
        )

    @app.exception_handler(ResourceLockedError)
    async def resource_locked_handler(request: Request, exc: ResourceLockedError) -> JSONResponse:
        """Handle resource locked exceptions."""
        return JSONResponse(
            status_code=exc.http_status,
            content=exc.to_dict(),
        )

    @app.exception_handler(AlgorithmNotFoundError)
    async def algorithm_not_found_handler(
        request: Request, exc: AlgorithmNotFoundError
    ) -> JSONResponse:
        """Handle algorithm not found exceptions."""
        return JSONResponse(
            status_code=exc.http_status,
            content=exc.to_dict(),
        )

    @app.exception_handler(QueryTimeoutError)
    async def query_timeout_handler(request: Request, exc: QueryTimeoutError) -> JSONResponse:
        """Handle query timeout exceptions."""
        return JSONResponse(
            status_code=exc.http_status,
            content=exc.to_dict(),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Handle request validation errors."""
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed",
                    "details": {"errors": exc.errors()},
                }
            },
        )

    # =========================================================================
    # Routers
    # =========================================================================

    # Health endpoints (no prefix)
    app.include_router(health.router)

    # API endpoints
    app.include_router(query.router)
    app.include_router(schema.router)
    app.include_router(lock.router)
    app.include_router(algo.router)
    app.include_router(networkx.router)

    # =========================================================================
    # Root endpoint
    # =========================================================================

    @app.get("/", tags=["Root"])
    async def root() -> dict[str, str]:
        """API root endpoint."""
        return {
            "name": "Ryugraph Wrapper API",
            "version": "1.0.0",
            "docs": "/docs",
        }

    return app


# =============================================================================
# Application Instance
# =============================================================================

app = create_app()


# =============================================================================
# CLI Entry Point
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "wrapper.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.wrapper.environment == "local",
        log_level=settings.logging.level.lower(),
    )
