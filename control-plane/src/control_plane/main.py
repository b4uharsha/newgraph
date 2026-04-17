"""FastAPI application factory."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from control_plane.cache.schema_cache import SchemaMetadataCache
from control_plane.config import Settings, get_settings
from control_plane.infrastructure.database import DatabaseCommitMiddleware, DatabaseManager
from control_plane.jobs import BackgroundJobScheduler
from control_plane.middleware import RequestIdMiddleware, register_exception_handlers
from control_plane.routers import health_router
from control_plane.routers.api import (
    admin_router,
    cluster_router,
    config_router,
    export_jobs_router,
    favorites_router,
    instances_router,
    mappings_router,
    ops_router,
    schema_router,
    users_router,
    # SNAPSHOT FUNCTIONALITY DISABLED - snapshots are now created implicitly
    # snapshots_router,
)
from control_plane.routers.internal import (
    export_jobs_router as internal_export_jobs_router,
)
from control_plane.routers.internal import (
    instances_router as internal_instances_router,
)
from control_plane.routers.internal import (
    snapshots_router as internal_snapshots_router,
)
from control_plane.routers.metrics import router as metrics_router


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        settings: Optional settings override (for testing)

    Returns:
        Configured FastAPI application
    """
    if settings is None:
        settings = get_settings()

    # Database manager for lifecycle
    db_manager = DatabaseManager(settings)

    # Background job scheduler for lifecycle and reconciliation
    scheduler = BackgroundJobScheduler(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        """Application lifespan handler."""
        # Startup
        await db_manager.startup()
        # Initialize schema metadata cache
        schema_cache = SchemaMetadataCache()
        app.state.schema_cache = schema_cache
        # Give scheduler access to schema cache for background refresh job
        scheduler.set_schema_cache(schema_cache)
        await scheduler.start()
        # Store scheduler in app state for ops endpoints
        app.state.scheduler = scheduler
        yield
        # Shutdown
        await scheduler.stop()
        await db_manager.shutdown()

    app = FastAPI(
        title="Graph OLAP Control Plane",
        description="Control Plane API for Graph OLAP Platform",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    # Store settings in app state for access by dependencies
    app.state.settings = settings

    # Middleware (order matters - first added is outermost)
    app.add_middleware(RequestIdMiddleware)

    # CORS (configure as needed for your environment)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.debug else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Database commit middleware (innermost - runs just before response)
    # CRITICAL: This must be added LAST so it commits sessions before response is sent
    # Ensures read-after-write consistency for all mutations
    app.add_middleware(DatabaseCommitMiddleware)

    # Exception handlers
    register_exception_handlers(app)

    # Health check routes
    app.include_router(health_router)

    # Metrics endpoint (for Prometheus)
    app.include_router(metrics_router)

    # Public API routes
    app.include_router(mappings_router)
    # SNAPSHOT FUNCTIONALITY DISABLED - snapshots are now created implicitly
    # app.include_router(snapshots_router)
    app.include_router(instances_router)
    app.include_router(favorites_router)
    app.include_router(config_router)
    app.include_router(cluster_router)
    app.include_router(schema_router)
    app.include_router(ops_router)
    app.include_router(admin_router)
    app.include_router(export_jobs_router)
    app.include_router(users_router)

    # Internal API routes (for service-to-service)
    app.include_router(internal_snapshots_router)
    app.include_router(internal_instances_router)
    app.include_router(internal_export_jobs_router)

    return app


# Default application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "control_plane.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
