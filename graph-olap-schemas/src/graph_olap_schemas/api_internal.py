"""
Internal API schemas for component-to-component communication.

These schemas define the contract between:
- Export Worker → Control Plane (status updates, export jobs)
- Wrapper Pod → Control Plane (status, metrics, progress)
- Control Plane → Wrapper Pod (shutdown)

All structures derived from docs/system-design/api/api.internal.spec.md.
"""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, Field

from graph_olap_schemas.api_resources import InstanceErrorCode
from graph_olap_schemas.constants import (
    ISO8601_TIMESTAMP_PATTERN,
    MAX_RESOURCE_NAME_LENGTH,
    MIN_NAME_LENGTH,
)
from graph_olap_schemas.definitions import EdgeDefinition, NodeDefinition


class ExportJobStatus(StrEnum):
    """Export job states (ADR-025).

    Status flow:
        pending → claimed → submitted → completed
                                      → failed
    """

    PENDING = "pending"
    CLAIMED = "claimed"  # Job claimed by a worker
    SUBMITTED = "submitted"  # Query submitted to Starburst, polling in progress
    COMPLETED = "completed"
    FAILED = "failed"


# =============================================================================
# Worker → Control Plane: Snapshot Status
# =============================================================================


class SnapshotProgress(BaseModel):
    """
    Progress information for snapshot creation.

    From api.internal.spec.md PUT /snapshots/:id/status request body.
    """

    current_step: Annotated[
        str | None,
        Field(
            default=None,
            description="Current entity being exported (node label or edge type)",
            examples=["Customer", "PURCHASED"],
        ),
    ]

    completed_steps: Annotated[
        int,
        Field(
            ge=0,
            description="Number of completed export steps",
            examples=[0, 2, 5],
        ),
    ]

    total_steps: Annotated[
        int,
        Field(
            ge=0,
            description="Total number of export steps",
            examples=[3, 5, 10],
        ),
    ]


class UpdateSnapshotStatusRequest(BaseModel):
    """
    Request to update snapshot status during processing.

    From api.internal.spec.md PUT /snapshots/:id/status.
    Called by Export Worker to update snapshot status.

    Status values: "pending", "creating", "ready", "failed"
    """

    status: Annotated[
        str,
        Field(
            pattern=r"^(pending|creating|ready|failed)$",
            description="New snapshot status",
            examples=["creating", "ready", "failed"],
        ),
    ]

    phase: Annotated[
        str | None,
        Field(
            default=None,
            description="Current export phase (when status=creating)",
            examples=["exporting_nodes", "exporting_edges"],
        ),
    ]

    progress: Annotated[
        SnapshotProgress | None,
        Field(
            default=None,
            description="Progress details (when status=creating)",
        ),
    ]

    size_bytes: Annotated[
        int | None,
        Field(
            default=None,
            ge=0,
            description="Total storage size (when status=ready)",
            examples=[1073741824],
        ),
    ]

    node_counts: Annotated[
        dict[str, int] | None,
        Field(
            default=None,
            description="Node counts by label (when status=ready)",
            examples=[{"Customer": 10000, "Product": 5000}],
        ),
    ]

    edge_counts: Annotated[
        dict[str, int] | None,
        Field(
            default=None,
            description="Edge counts by type (when status=ready)",
            examples=[{"PURCHASED": 50000}],
        ),
    ]

    error_message: Annotated[
        str | None,
        Field(
            default=None,
            description="Error details (when status=failed)",
            examples=["Starburst query timeout after 30 minutes"],
        ),
    ]

    failed_step: Annotated[
        str | None,
        Field(
            default=None,
            description="Entity name that failed (when status=failed)",
            examples=["PURCHASED"],
        ),
    ]

    partial_results: Annotated[
        dict[str, Any] | None,
        Field(
            default=None,
            description="Partial node/edge counts (when status=failed)",
            examples=[{"node_counts": {"Customer": 10000}, "edge_counts": {}}],
        ),
    ]


# =============================================================================
# Worker → Control Plane: Export Jobs
# =============================================================================


class ExportJobDefinition(BaseModel):
    """
    Single export job definition for batch creation.

    From api.internal.spec.md POST /snapshots/:id/export-jobs request.
    """

    job_type: Annotated[
        str,
        Field(
            pattern=r"^(node|edge)$",
            description="Type of export: 'node' or 'edge'",
            examples=["node", "edge"],
        ),
    ]

    entity_name: Annotated[
        str,
        Field(
            min_length=MIN_NAME_LENGTH,
            max_length=MAX_RESOURCE_NAME_LENGTH,
            description="Node label or edge type name",
            examples=["Customer", "PURCHASED"],
        ),
    ]

    starburst_query_id: Annotated[
        str,
        Field(
            min_length=1,
            description="Starburst query ID from submission",
            examples=["query_20250115_abc123"],
        ),
    ]

    next_uri: Annotated[
        str,
        Field(
            min_length=1,
            description="Starburst polling URI",
            examples=["https://starburst.example.com/v1/statement/query_20250115_abc123/1"],
        ),
    ]

    gcs_path: Annotated[
        str,
        Field(
            min_length=1,
            description="GCS destination path",
            examples=["gs://bucket/user/mapping/snapshot/nodes/Customer/"],
        ),
    ]

    status: Annotated[
        str,
        Field(
            default="running",
            pattern=r"^(pending|running)$",
            description="Initial status (default: 'running')",
        ),
    ]

    submitted_at: Annotated[
        str | None,
        Field(
            default=None,
            pattern=ISO8601_TIMESTAMP_PATTERN,
            description="When query was submitted (default: current time)",
            examples=["2025-01-15T10:30:00Z"],
        ),
    ]

    starburst_role: Annotated[
        str | None,
        Field(
            default=None,
            description="Use case ID for Starburst SET ROLE (e.g. uc_glh_dev)",
            examples=["uc_glh_dev"],
        ),
    ]


class CreateExportJobsRequest(BaseModel):
    """
    Request to create export jobs for a snapshot.

    From api.internal.spec.md POST /snapshots/:id/export-jobs.
    Called by Export Submitter after submitting UNLOAD queries to Starburst.
    """

    jobs: Annotated[
        list[ExportJobDefinition],
        Field(
            min_length=1,
            description="Export jobs to create (one per node/edge definition)",
        ),
    ]


class UpdateExportJobRequest(BaseModel):
    """
    Request to update a single export job's status.

    From api.internal.spec.md PATCH /export-jobs/:id.
    Called by Export Worker to update job status and results.

    ADR-025: Status transitions:
    - pending -> claimed (worker claims job)
    - claimed -> submitted (query submitted to Starburst)
    - submitted -> completed (query finished successfully)
    - submitted -> failed (query failed)
    - Any state -> failed (on error)
    """

    status: Annotated[
        str | None,
        Field(
            default=None,
            pattern=r"^(running|submitted|completed|failed)$",
            description="New status (running is legacy alias for submitted)",
            examples=["submitted", "completed", "failed"],
        ),
    ]

    starburst_query_id: Annotated[
        str | None,
        Field(
            default=None,
            description="Starburst query ID (required when status=submitted)",
            examples=["query_20250115_abc123"],
        ),
    ]

    next_uri: Annotated[
        str | None,
        Field(
            default=None,
            description="Updated Starburst polling URI",
            examples=["https://starburst.example.com/v1/statement/query_20250115_abc123/10"],
        ),
    ]

    next_poll_at: Annotated[
        str | None,
        Field(
            default=None,
            pattern=ISO8601_TIMESTAMP_PATTERN,
            description="When to poll Starburst next (ADR-025 Fibonacci backoff)",
            examples=["2025-01-15T10:32:00Z"],
        ),
    ]

    poll_count: Annotated[
        int | None,
        Field(
            default=None,
            ge=0,
            description="Number of times the job has been polled",
            examples=[1, 5, 10],
        ),
    ]

    submitted_at: Annotated[
        str | None,
        Field(
            default=None,
            pattern=ISO8601_TIMESTAMP_PATTERN,
            description="When query was submitted to Starburst",
            examples=["2025-01-15T10:30:00Z"],
        ),
    ]

    row_count: Annotated[
        int | None,
        Field(
            default=None,
            ge=0,
            description="Final row count (when completed)",
            examples=[10000],
        ),
    ]

    size_bytes: Annotated[
        int | None,
        Field(
            default=None,
            ge=0,
            description="Final size in bytes (when completed)",
            examples=[2097152],
        ),
    ]

    completed_at: Annotated[
        str | None,
        Field(
            default=None,
            pattern=ISO8601_TIMESTAMP_PATTERN,
            description="When job completed (default: current time if status=completed)",
            examples=["2025-01-15T10:35:00Z"],
        ),
    ]

    error_message: Annotated[
        str | None,
        Field(
            default=None,
            description="Error details (when failed)",
            examples=["Starburst query failed: QUERY_EXCEEDED_TIME_LIMIT"],
        ),
    ]


class ExportJobResponse(BaseModel):
    """
    Export job response.

    From api.internal.spec.md GET /snapshots/:id/export-jobs response.
    """

    id: int
    snapshot_id: int
    job_type: str
    entity_name: str
    status: ExportJobStatus
    starburst_query_id: str | None
    next_uri: str | None
    gcs_path: str
    row_count: int | None
    size_bytes: int | None
    submitted_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    starburst_role: str | None = None


class ExportJobsCreatedResponse(BaseModel):
    """
    Response after creating export jobs.

    From api.internal.spec.md POST /snapshots/:id/export-jobs response.
    """

    created: int
    jobs: list[dict[str, Any]]


# =============================================================================
# Wrapper Pod → Control Plane: Instance Status
# =============================================================================


class GraphStats(BaseModel):
    """Graph statistics for running instance."""

    node_count: Annotated[
        int,
        Field(ge=0, description="Total node count"),
    ]

    edge_count: Annotated[
        int,
        Field(ge=0, description="Total edge count"),
    ]


class UpdateInstanceStatusRequest(BaseModel):
    """
    Request to update instance status.

    From api.internal.spec.md PUT /instances/:id/status.
    Called by Wrapper Pod to report status changes.
    """

    status: Annotated[
        str,
        Field(
            pattern=r"^(starting|running|stopping|failed)$",
            description="New instance status",
            examples=["running", "failed"],
        ),
    ]

    pod_name: Annotated[
        str | None,
        Field(
            default=None,
            description="Kubernetes pod name (when running)",
            examples=["graph-instance-abc123"],
        ),
    ]

    pod_ip: Annotated[
        str | None,
        Field(
            default=None,
            description="Internal pod IP (when running)",
            examples=["10.0.0.42"],
        ),
    ]

    instance_url: Annotated[
        str | None,
        Field(
            default=None,
            description="Unique access URL (when running)",
            examples=["https://graph.example.com/instance-uuid/"],
        ),
    ]

    progress: Annotated[
        dict[str, Any] | None,
        Field(
            default=None,
            description="Loading progress details",
        ),
    ]

    graph_stats: Annotated[
        GraphStats | None,
        Field(
            default=None,
            description="Graph statistics (when running)",
        ),
    ]

    error_code: Annotated[
        InstanceErrorCode | None,
        Field(
            default=None,
            description="Machine-readable error code (when failed)",
            examples=["DATA_LOAD_ERROR", "STARTUP_FAILED"],
        ),
    ]

    error_message: Annotated[
        str | None,
        Field(
            default=None,
            description="Human-readable error details (when failed)",
            examples=["Failed to load edges: file not found"],
        ),
    ]

    failed_phase: Annotated[
        str | None,
        Field(
            default=None,
            description="Phase that failed (when failed)",
            examples=["loading_edges"],
        ),
    ]

    stack_trace: Annotated[
        str | None,
        Field(
            default=None,
            description="Stack trace for debugging (when failed)",
            examples=["Traceback (most recent call last):\n  File..."],
        ),
    ]


class UpdateInstanceMetricsRequest(BaseModel):
    """
    Request to update instance resource metrics.

    From api.internal.spec.md PUT /instances/:id/metrics.
    Called periodically by Wrapper Pod to report resource usage.
    """

    memory_usage_bytes: Annotated[
        int | None,
        Field(
            default=None,
            ge=0,
            description="Current memory consumption",
            examples=[536870912],
        ),
    ]

    disk_usage_bytes: Annotated[
        int | None,
        Field(
            default=None,
            ge=0,
            description="Current disk consumption",
            examples=[1073741824],
        ),
    ]

    last_activity_at: Annotated[
        str | None,
        Field(
            default=None,
            pattern=ISO8601_TIMESTAMP_PATTERN,
            description="Last activity timestamp",
            examples=["2025-01-15T14:00:00Z"],
        ),
    ]

    query_count_since_last: Annotated[
        int | None,
        Field(
            default=None,
            ge=0,
            description="Queries since last metrics update",
            examples=[15],
        ),
    ]

    avg_query_time_ms: Annotated[
        int | None,
        Field(
            default=None,
            ge=0,
            description="Average query time in milliseconds",
            examples=[25],
        ),
    ]


class InstanceProgressStep(BaseModel):
    """
    Single step in instance loading progress.

    From api.internal.spec.md PUT /instances/:id/progress request.
    """

    name: Annotated[
        str,
        Field(
            min_length=1,
            description="Step name (e.g., 'pod_scheduled', 'Customer', 'PURCHASED')",
            examples=["pod_scheduled", "Customer", "PURCHASED"],
        ),
    ]

    status: Annotated[
        str,
        Field(
            pattern=r"^(pending|in_progress|completed|failed)$",
            description="Step status",
            examples=["completed", "in_progress", "pending"],
        ),
    ]

    type: Annotated[
        str | None,
        Field(
            default=None,
            pattern=r"^(node|edge)$",
            description="Step type for data loading steps",
            examples=["node", "edge"],
        ),
    ]

    row_count: Annotated[
        int | None,
        Field(
            default=None,
            ge=0,
            description="Row count (when completed)",
            examples=[10000],
        ),
    ]


class UpdateInstanceProgressRequest(BaseModel):
    """
    Request to update instance loading progress.

    From api.internal.spec.md PUT /instances/:id/progress.
    Called during instance startup to report loading progress.
    """

    phase: Annotated[
        str,
        Field(
            description="Current loading phase",
            examples=["loading_nodes", "loading_edges"],
        ),
    ]

    steps: Annotated[
        list[InstanceProgressStep],
        Field(
            default_factory=list,
            description="Progress steps",
        ),
    ]


class InstanceMappingResponse(BaseModel):
    """
    Mapping definition response for instance startup.

    From api.internal.spec.md GET /instances/:id/mapping response.
    Called by Wrapper Pod during startup to retrieve the mapping for schema creation.
    Note: sql field included for schema creation (different from requirements.md note).
    """

    snapshot_id: int
    mapping_id: int
    mapping_version: int
    gcs_path: Annotated[
        str,
        Field(
            description="GCS location of Parquet files",
            examples=["gs://bucket/user-uuid/mapping-uuid/snapshot-uuid/"],
        ),
    ]
    node_definitions: list[NodeDefinition]
    edge_definitions: list[EdgeDefinition]


# =============================================================================
# Control Plane → Wrapper Pod: Shutdown
# =============================================================================


class ShutdownRequest(BaseModel):
    """
    Request to initiate graceful shutdown.

    From api.internal.spec.md POST /shutdown.
    Called by Control Plane when terminating an instance.
    """

    reason: Annotated[
        str,
        Field(
            description="Shutdown reason",
            examples=["user_terminated", "ttl_expired", "inactivity_timeout"],
        ),
    ]

    grace_period_seconds: Annotated[
        int,
        Field(
            default=30,
            ge=0,
            le=300,
            description="Grace period for shutdown",
            examples=[30],
        ),
    ]


class ShutdownResponse(BaseModel):
    """
    Response to shutdown request.

    From api.internal.spec.md POST /shutdown response.
    """

    acknowledged: bool = True

    active_queries: Annotated[
        int,
        Field(
            default=0,
            ge=0,
            description="Number of active queries",
        ),
    ]

    lock_held: Annotated[
        bool,
        Field(
            default=False,
            description="Whether an algorithm lock is held",
        ),
    ]


class ShutdownBlockedResponse(BaseModel):
    """
    Response when shutdown is blocked by algorithm lock.

    From api.internal.spec.md POST /shutdown 409 response.
    """

    code: str = "SHUTDOWN_BLOCKED"
    message: str
    details: dict[str, Any]


# =============================================================================
# Simple acknowledgment response
# =============================================================================


class UpdatedResponse(BaseModel):
    """
    Simple response for internal update operations.

    Used by PUT endpoints that just need to confirm success.
    """

    updated: bool = True
