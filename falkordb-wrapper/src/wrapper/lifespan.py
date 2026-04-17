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

import structlog
from fastapi import FastAPI

from wrapper.clients.control_plane import ControlPlaneClient
from wrapper.clients.gcs import GCSClient
from wrapper.config import get_settings
from wrapper.exceptions import GCSDownloadError, OutOfMemoryError
from wrapper.routers.health import set_startup_time
from wrapper.services.algorithm import AlgorithmService
from wrapper.services.database import DatabaseService
from wrapper.services.lock import LockService

logger = structlog.get_logger(__name__)


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
    7. Start metrics reporter
    8. Report ready status

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
    algorithm_service: AlgorithmService | None = None
    metrics_task: asyncio.Task[None] | None = None

    try:
        # Mark startup time
        set_startup_time()

        logger.info(
            "Starting FalkorDB Wrapper",
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
            database_path=settings.falkordb.database_path / f"graph_{settings.wrapper.snapshot_id}",
            graph_name=f"graph_{settings.wrapper.snapshot_id}",
            query_timeout_ms=settings.falkordb.query_timeout_ms,
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

        logger.info("database_initialized", graph_name=db_service.graph_name)

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
        logger.info(
            "Mapping fetched",
            mapping_id=mapping.mapping_id,
            mapping_version=mapping.mapping_version,
            node_tables=len(mapping.node_definitions),
            edge_tables=len(mapping.edge_definitions),
            gcs_path=mapping.gcs_path,
        )

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
            message="Loading data",
        )

        gcs_client = GCSClient()
        logger.info("starting_data_load", gcs_path=settings.wrapper.gcs_base_path)

        try:
            await db_service.load_data(
                gcs_base_path=settings.wrapper.gcs_base_path,
                mapping=mapping,
                gcs_client=gcs_client,
                control_plane_client=control_plane_client,
            )

            logger.info("data_load_completed_successfully")
            db_service.mark_ready()

        except OutOfMemoryError as e:
            logger.error("oom_during_data_load", error=str(e))
            await control_plane_client.update_status(
                status="failed",
                error_code="OOM_KILLED",
                error_message=str(e),
            )
            raise

        except GCSDownloadError as e:
            logger.error("gcs_download_failed", error=str(e))
            await control_plane_client.update_status(
                status="failed",
                error_code="GCS_DOWNLOAD_ERROR",
                error_message=str(e),
            )
            raise

        except Exception as e:
            logger.error("data_load_failed", error=str(e), exc_info=True)
            await control_plane_client.update_status(
                status="failed",
                error_code="DATA_LOAD_ERROR",
                error_message=str(e),
                stack_trace=traceback.format_exc(),
            )
            raise

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

        # Get stats for status report
        stats = await db_service.get_stats()

        # Report ready progress phase
        await control_plane_client.update_progress(
            stage="ready",
            current=4,
            total=4,
            message="Ready to serve queries",
        )

        await control_plane_client.update_status(
            status="running",
            instance_url=instance_url,
            node_count=stats.get("total_nodes", 0),
            edge_count=stats.get("total_edges", 0),
        )

        logger.info(
            "FalkorDB Wrapper started successfully",
            nodes_loaded=stats.get("total_nodes", 0),
            edges_loaded=stats.get("total_edges", 0),
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

        # Report error to Control Plane
        if control_plane_client:
            error_code = _get_error_code(e)
            with suppress(Exception):
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

        logger.info("Shutting down FalkorDB Wrapper")

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

        logger.info("FalkorDB Wrapper shutdown complete")


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

            # Report resource metrics
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

    Args:
        exc: The exception that occurred during startup.

    Returns:
        Error code string matching InstanceErrorCode enum values.
    """
    from wrapper.exceptions import (
        ControlPlaneError,
        DatabaseError,
        DataLoadError,
    )

    if isinstance(exc, ControlPlaneError):
        return "MAPPING_FETCH_ERROR"

    if isinstance(exc, DataLoadError):
        return "DATA_LOAD_ERROR"

    if isinstance(exc, DatabaseError):
        return "DATABASE_ERROR"

    return "STARTUP_FAILED"
