"""Control Plane API client.

Provides communication with the Control Plane service for:
- Instance status updates
- Progress reporting during startup
- Metrics reporting
- Fetching mapping definitions
- Activity recording for inactivity timeout tracking

Service-to-service calls use plain HTTP within the cluster (ADR-104).
All request payloads use shared Pydantic models from graph_olap_schemas
for compile-time validation of API contracts.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog
from graph_olap_schemas import (
    GraphStats,
    InstanceMappingResponse,
    InstanceProgressStep,
    UpdateInstanceMetricsRequest,
    UpdateInstanceProgressRequest,
    UpdateInstanceStatusRequest,
)
from graph_olap_schemas.api_resources import InstanceErrorCode
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from wrapper.exceptions import ControlPlaneError

logger = structlog.get_logger(__name__)

# Default timeout for HTTP requests
DEFAULT_TIMEOUT = 30.0


class ControlPlaneClient:
    """Client for Control Plane API communication.

    Service-to-service calls within the cluster; no authentication
    needed per ADR-104 (oauth2-proxy and ID tokens removed).
    """

    def __init__(
        self,
        base_url: str,
        instance_id: str,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        """Initialize the Control Plane client.

        Args:
            base_url: Base URL of the Control Plane API.
            instance_id: This instance's identifier.
            timeout: Request timeout in seconds.
        """
        self._base_url = base_url.rstrip("/")
        self._instance_id = instance_id
        self._timeout = timeout

        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={"Content-Type": "application/json"},
        )

        logger.info(
            "ControlPlaneClient initialized",
            base_url=self._base_url,
            instance_id=instance_id,
        )

    async def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make request to Control Plane.

        Args:
            method: HTTP method (GET, PUT, POST, etc.).
            path: API path (appended to base URL).
            json: Optional JSON body.

        Returns:
            Response JSON as dict.

        Raises:
            ControlPlaneError: If request fails.
        """
        url = f"{self._base_url}{path}"

        try:
            response = await self._client.request(
                method=method,
                url=url,
                json=json,
            )
            response.raise_for_status()

            if response.status_code == 204:
                return {}

            return response.json()

        except httpx.HTTPStatusError as e:
            logger.error(
                "Control Plane request failed",
                method=method,
                path=path,
                status_code=e.response.status_code,
                response_text=e.response.text[:500],
            )
            body = e.response.text[:200] if e.response.text else ""
            raise ControlPlaneError(
                f"Control Plane request failed: {e.response.status_code} {body}".strip(),
                status_code=e.response.status_code,
            ) from e

        except httpx.RequestError as e:
            logger.error(
                "Control Plane request error",
                method=method,
                path=path,
                error=str(e),
            )
            raise ControlPlaneError(f"Control Plane request error: {e}") from e

    @retry(
        retry=retry_if_exception_type(ControlPlaneError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def update_status(
        self,
        status: str,
        *,
        error_message: str | None = None,
        error_code: str | None = None,
        stack_trace: str | None = None,
        failed_phase: str | None = None,
        pod_name: str | None = None,
        pod_ip: str | None = None,
        instance_url: str | None = None,
        progress: dict[str, Any] | None = None,
        node_count: int | None = None,
        edge_count: int | None = None,
    ) -> None:
        """Update instance status in Control Plane.

        Uses UpdateInstanceStatusRequest from shared schemas for validation.

        Args:
            status: New status (starting, running, stopping, failed).
            error_message: Human-readable error details (when status=failed).
            error_code: Machine-readable error code (when status=failed).
                One of: STARTUP_FAILED, MAPPING_FETCH_ERROR, SCHEMA_CREATE_ERROR,
                DATA_LOAD_ERROR, DATABASE_ERROR, OOM_KILLED.
            stack_trace: Stack trace for debugging (when status=failed).
            failed_phase: Phase that failed, e.g. 'loading_nodes' (when status=failed).
            pod_name: Kubernetes pod name.
            pod_ip: Pod IP address.
            instance_url: Instance URL (when running).
            progress: Progress information dict.
            node_count: Total node count (when running, for graph_stats).
            edge_count: Total edge count (when running, for graph_stats).
        """
        path = f"/api/internal/instances/{self._instance_id}/status"

        # Build graph_stats if counts provided
        graph_stats: GraphStats | None = None
        if node_count is not None and edge_count is not None:
            graph_stats = GraphStats(node_count=node_count, edge_count=edge_count)

        # Convert error_code string to enum if provided
        error_code_enum: InstanceErrorCode | None = None
        if error_code:
            try:
                error_code_enum = InstanceErrorCode(error_code)
            except ValueError:
                logger.warning("unknown_error_code", error_code=error_code)
                # Fall back to string if not a valid enum value
                error_code_enum = None

        # Build request using shared Pydantic model for validation
        request = UpdateInstanceStatusRequest(
            status=status,
            error_message=error_message,
            error_code=error_code_enum,
            stack_trace=stack_trace,
            failed_phase=failed_phase,
            pod_name=pod_name,
            pod_ip=pod_ip,
            instance_url=instance_url,
            progress=progress,
            graph_stats=graph_stats,
        )

        logger.info(
            "Updating instance status",
            status=status,
            error_code=error_code,
        )

        # Use exclude_none to avoid sending null fields
        await self._request("PATCH", path, json=request.model_dump(exclude_none=True))

    @retry(
        retry=retry_if_exception_type(ControlPlaneError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def update_progress(
        self,
        phase: str | None = None,
        steps: list[InstanceProgressStep] | None = None,
        *,
        # Legacy parameters for backward compatibility during migration
        stage: str | None = None,
        current: int | None = None,
        total: int | None = None,
        message: str | None = None,
    ) -> None:
        """Update startup progress in Control Plane.

        Uses UpdateInstanceProgressRequest and InstanceProgressStep from shared
        schemas for validation.

        Args:
            phase: Current loading phase (e.g., "loading_nodes", "loading_edges").
            steps: List of progress steps with name, status, type, and row_count.

        Legacy Args (deprecated, for backward compatibility):
            stage: Alias for phase.
            current: Current step number (converted to step list).
            total: Total steps (used to build step list).
            message: Step name for current step.
        """
        path = f"/api/internal/instances/{self._instance_id}/progress"

        # Handle legacy parameters for backward compatibility
        actual_phase = phase or stage or "loading"
        if steps is None and current is not None and total is not None:
            # Convert legacy current/total to steps list
            step_list: list[InstanceProgressStep] = []
            step_name = message or actual_phase

            # Add completed steps
            for i in range(current):
                step_list.append(
                    InstanceProgressStep(
                        name=f"step_{i + 1}",
                        status="completed",
                    )
                )

            # Add current step as in_progress
            if current < total:
                step_list.append(
                    InstanceProgressStep(
                        name=step_name,
                        status="in_progress",
                    )
                )

            steps = step_list

        # Build request using shared Pydantic model for validation
        request = UpdateInstanceProgressRequest(
            phase=actual_phase,
            steps=steps or [],
        )

        logger.debug(
            "Updating startup progress",
            phase=actual_phase,
            steps_count=len(steps or []),
        )

        await self._request("PUT", path, json=request.model_dump(exclude_none=True))

    @retry(
        retry=retry_if_exception_type(ControlPlaneError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def update_metrics(
        self,
        memory_usage_bytes: int | None = None,
        disk_usage_bytes: int | None = None,
        last_activity_at: str | None = None,
        query_count_since_last: int | None = None,
        avg_query_time_ms: int | None = None,
    ) -> None:
        """Update instance resource metrics in Control Plane.

        Uses UpdateInstanceMetricsRequest from shared schemas for validation.

        Note: For graph statistics (node_count, edge_count), use update_status()
        with the node_count and edge_count parameters instead.

        Args:
            memory_usage_bytes: Current memory consumption.
            disk_usage_bytes: Current disk consumption.
            last_activity_at: Last activity timestamp (ISO8601).
            query_count_since_last: Queries executed since last metrics update.
            avg_query_time_ms: Average query execution time in milliseconds.
        """
        path = f"/api/internal/instances/{self._instance_id}/metrics"

        # Build request using shared Pydantic model for validation
        request = UpdateInstanceMetricsRequest(
            memory_usage_bytes=memory_usage_bytes,
            disk_usage_bytes=disk_usage_bytes,
            last_activity_at=last_activity_at,
            query_count_since_last=query_count_since_last,
            avg_query_time_ms=avg_query_time_ms,
        )

        logger.debug(
            "Updating instance metrics",
            memory_usage_bytes=memory_usage_bytes,
            disk_usage_bytes=disk_usage_bytes,
        )

        await self._request("PUT", path, json=request.model_dump(exclude_none=True))

    @retry(
        retry=retry_if_exception_type(ControlPlaneError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def get_mapping(self) -> InstanceMappingResponse:
        """Fetch mapping definition from Control Plane.

        Returns the shared InstanceMappingResponse type directly, following
        the architectural guardrail that shared schemas should not be extended.

        Returns:
            InstanceMappingResponse containing mapping definition and GCS path.

        Raises:
            ControlPlaneError: If fetch fails or response is invalid.
        """
        path = f"/api/internal/instances/{self._instance_id}/mapping"

        logger.info("Fetching mapping definition")

        response = await self._request("GET", path)

        try:
            # Validate against shared schema to ensure API contract compliance
            mapping = InstanceMappingResponse.model_validate(response)

            logger.info(
                "Mapping fetched",
                mapping_id=mapping.mapping_id,
                mapping_version=mapping.mapping_version,
                node_tables=len(mapping.node_definitions),
                edge_tables=len(mapping.edge_definitions),
                gcs_path=mapping.gcs_path,
            )
            return mapping

        except Exception as e:
            logger.error("Failed to parse mapping response", error=str(e))
            raise ControlPlaneError(f"Invalid mapping response: {e}") from e

    async def record_activity(self) -> None:
        """Record instance activity for inactivity timeout tracking.

        Called after query or algorithm execution to update last_activity_at.
        Failures are logged but don't raise exceptions (fire-and-forget).

        See api.internal.spec.md: POST /instances/:id/activity
        """
        path = f"/api/internal/instances/{self._instance_id}/activity"

        try:
            await self._request("POST", path)
        except ControlPlaneError:
            # Don't fail on activity recording failures
            logger.warning("Failed to record activity")

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()
        logger.debug("ControlPlaneClient closed")
