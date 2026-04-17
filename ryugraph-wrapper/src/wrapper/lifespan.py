"""Application lifecycle management.

Handles startup and shutdown sequences including:
- Service initialization
- Database loading from GCS
- Control Plane status reporting
- Metrics collection
- Graceful shutdown
"""

from __future__ import annotations

import asyncio
import traceback
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
from typing import TYPE_CHECKING

from fastapi import FastAPI

from wrapper.algorithms.native import register_native_algorithms
from wrapper.algorithms.networkx import register_common_algorithms
from wrapper.clients.control_plane import ControlPlaneClient
from wrapper.config import get_settings
from wrapper.exceptions import (
    ControlPlaneError,
    DatabaseError,
    DataLoadError,
    SchemaCreationError,
)
from wrapper.logging import get_logger
from wrapper.routers.health import set_startup_time
from wrapper.services.algorithm import AlgorithmService
from wrapper.services.database import DatabaseService
from wrapper.services.lock import LockService

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager.

    Handles startup initialization and shutdown cleanup.

    Startup sequence:
    1. Initialize logging and configuration
    2. Create service instances
    3. Connect to Control Plane
    4. Initialize database
    5. Create schema from mapping
    6. Load data from GCS
    7. Register algorithms
    8. Start metrics reporter
    9. Report ready status

    Shutdown sequence:
    1. Stop metrics reporter
    2. Force release any held locks
    3. Close database connection
    4. Report shutdown status
    5. Close HTTP clients
    """
    settings = get_settings()
    control_plane_client: ControlPlaneClient | None = None
    db_service: DatabaseService | None = None
    lock_service: LockService | None = None
    metrics_task: asyncio.Task[None] | None = None

    try:
        # Mark startup time
        set_startup_time()

        logger.info(
            "Starting Ryugraph Wrapper",
            instance_id=settings.wrapper.instance_id,
            snapshot_id=settings.wrapper.snapshot_id,
        )

        # =====================================================================
        # Initialize Control Plane Client
        # =====================================================================

        control_plane_client = ControlPlaneClient(
            base_url=settings.wrapper.control_plane_url,
            instance_id=settings.wrapper.instance_id,
        )
        app.state.control_plane_client = control_plane_client

        # Report starting status
        await control_plane_client.update_status(
            status="starting",
            pod_name=settings.wrapper.pod_name,
            pod_ip=settings.wrapper.pod_ip,
        )

        # =====================================================================
        # Initialize Services
        # =====================================================================

        lock_service = LockService()
        app.state.lock_service = lock_service

        db_service = DatabaseService(
            database_path=settings.ryugraph.database_path,
            buffer_pool_size=settings.ryugraph.buffer_pool_size,
            max_threads=settings.ryugraph.max_threads,
        )
        app.state.db_service = db_service

        algorithm_service = AlgorithmService(
            db_service=db_service,
            lock_service=lock_service,
        )
        app.state.algorithm_service = algorithm_service

        # =====================================================================
        # Initialize Database
        # =====================================================================

        await control_plane_client.update_progress(
            stage="initializing",
            current=1,
            total=4,
            message="Creating database",
        )

        await db_service.initialize()

        # =====================================================================
        # Fetch Mapping and Create Schema
        # =====================================================================

        await control_plane_client.update_progress(
            stage="schema",
            current=2,
            total=4,
            message="Fetching mapping definition",
        )

        mapping = await control_plane_client.get_mapping()

        await control_plane_client.update_progress(
            stage="schema",
            current=2,
            total=4,
            message="Creating database schema",
        )

        await db_service.create_schema(mapping)

        # =====================================================================
        # Load Data from GCS
        # =====================================================================

        await control_plane_client.update_progress(
            stage="loading",
            current=3,
            total=4,
            message="Loading data from GCS",
        )

        async def progress_callback(**kwargs: object) -> None:
            """Report loading progress to Control Plane."""
            stage = kwargs.get("stage", "loading")
            current = kwargs.get("current", 0)
            total = kwargs.get("total", 1)
            label = kwargs.get("label") or kwargs.get("type", "")

            await control_plane_client.update_progress(
                stage=str(stage),
                current=int(current),  # type: ignore[arg-type]
                total=int(total),  # type: ignore[arg-type]
                message=f"Loading {label}" if label else None,
            )

        load_result = await db_service.load_data(
            mapping=mapping,
            gcs_base_path=settings.wrapper.gcs_base_path,
            progress_callback=progress_callback,
        )

        # =====================================================================
        # Register Algorithms
        # =====================================================================

        register_native_algorithms()
        register_common_algorithms()

        # =====================================================================
        # Start Metrics Reporter
        # =====================================================================

        if settings.metrics.enabled:
            metrics_task = asyncio.create_task(
                _metrics_reporter(
                    control_plane_client=control_plane_client,
                    interval_seconds=settings.metrics.report_interval_seconds,
                )
            )

        # =====================================================================
        # Report Ready
        # =====================================================================

        # Build instance URL: prefer configured URL, fall back to pod IP
        instance_url = settings.wrapper.instance_url
        if not instance_url and settings.wrapper.pod_ip:
            instance_url = f"http://{settings.wrapper.pod_ip}:{settings.wrapper.port}"

        # Report ready progress phase
        await control_plane_client.update_progress(
            stage="ready",
            current=4,
            total=4,
            message="Ready to serve queries",
        )

        # Report running status with graph statistics
        await control_plane_client.update_status(
            status="running",
            instance_url=instance_url,
            node_count=load_result.get("nodes", 0),
            edge_count=load_result.get("edges", 0),
        )

        logger.info(
            "Ryugraph Wrapper started successfully",
            nodes_loaded=load_result.get("nodes", 0),
            edges_loaded=load_result.get("edges", 0),
        )

        # =====================================================================
        # Yield control to application
        # =====================================================================

        yield

    except Exception as e:
        logger.error(
            "Startup failed",
            error=str(e),
            traceback=traceback.format_exc(),
        )

        # Report error to Control Plane with consolidated error fields
        if control_plane_client:
            # Determine error code based on exception type
            error_code = _get_error_code(e)

            await control_plane_client.update_status(
                status="failed",
                error_code=error_code,
                error_message=str(e),
                stack_trace=traceback.format_exc(),
            )

        raise

    finally:
        # =====================================================================
        # Shutdown sequence
        # =====================================================================

        logger.info("Shutting down Ryugraph Wrapper")

        # Cancel metrics reporter
        if metrics_task:
            metrics_task.cancel()
            with suppress(asyncio.CancelledError):
                await metrics_task

        # Force release any locks
        if lock_service:
            released = await lock_service.force_release()
            if released:
                logger.warning(
                    "Force-released lock during shutdown",
                    holder=released.holder_username,
                    algorithm=released.algorithm_name,
                )

        # Report stopping status
        if control_plane_client:
            with suppress(Exception):
                await control_plane_client.update_status(status="stopping")

        # Close database
        if db_service:
            await db_service.close()

        # Close Control Plane client
        if control_plane_client:
            await control_plane_client.close()

        logger.info("Ryugraph Wrapper shutdown complete")


async def _metrics_reporter(
    control_plane_client: ControlPlaneClient,
    interval_seconds: int,
) -> None:
    """Background task to periodically report metrics.

    Args:
        control_plane_client: Client for Control Plane API.
        interval_seconds: Reporting interval.
    """
    import psutil

    logger.info("Starting metrics reporter", interval=interval_seconds)

    while True:
        try:
            await asyncio.sleep(interval_seconds)

            # Get resource usage
            process = psutil.Process()
            memory_info = process.memory_info()

            # Report resource metrics only
            # Note: Graph stats (node/edge counts) are reported via update_status
            # when status changes (per UpdateInstanceMetricsRequest schema)
            await control_plane_client.update_metrics(
                memory_usage_bytes=memory_info.rss,
            )

        except asyncio.CancelledError:
            logger.debug("Metrics reporter cancelled")
            break
        except Exception as e:
            logger.warning("Metrics reporting failed", error=str(e))


def _get_error_code(exc: Exception) -> str:
    """Map exception type to API error code.

    Maps wrapper exceptions to the standardized error codes
    defined in the API specification (api.internal.spec.md).

    Args:
        exc: The exception that occurred during startup.

    Returns:
        Error code string matching InstanceErrorCode enum values.
    """
    # Check for mapping fetch errors (ControlPlaneError during mapping retrieval)
    if isinstance(exc, ControlPlaneError):
        return "MAPPING_FETCH_ERROR"

    # Check for schema creation errors
    if isinstance(exc, SchemaCreationError):
        return "SCHEMA_CREATE_ERROR"

    # Check for data loading errors
    if isinstance(exc, DataLoadError):
        return "DATA_LOAD_ERROR"

    # Check for general database errors
    if isinstance(exc, DatabaseError):
        return "DATABASE_ERROR"

    # Default to generic startup failure
    return "STARTUP_FAILED"
