"""
API schemas for operational and administrative endpoints.

These schemas define the contract for:
- Background job management (trigger, status)
- System state monitoring
- Configuration management (lifecycle, concurrency, maintenance, export)
- Bulk operations (admin)

All structures are used by both the control plane API and SDK client.
"""

from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, Field

# =============================================================================
# Background Jobs
# =============================================================================


class JobStatus(BaseModel):
    """Status of a single background job.

    Used in GET /api/ops/jobs/status response.
    """

    name: str
    next_run: str | None = None


class JobsStatusResponse(BaseModel):
    """Status of all background jobs.

    From GET /api/ops/jobs/status response.
    """

    jobs: list[JobStatus]


class TriggerJobRequest(BaseModel):
    """Request to manually trigger a background job.

    From POST /api/ops/jobs/trigger request.
    """

    job_name: Annotated[
        str,
        Field(
            pattern=r"^(reconciliation|lifecycle|export_reconciliation|schema_cache)$",
            description="Job to trigger",
        ),
    ]
    reason: Annotated[
        str,
        Field(
            min_length=1,
            max_length=500,
            description="Reason for manual trigger (audit log)",
        ),
    ]


class TriggerJobResponse(BaseModel):
    """Response from triggering a job.

    From POST /api/ops/jobs/trigger response.
    """

    job_name: str
    triggered_at: str
    triggered_by: str
    reason: str
    status: str = "queued"


# =============================================================================
# System State
# =============================================================================


class SystemStateResponse(BaseModel):
    """System state summary.

    From GET /api/ops/state response.
    Contains resource counts by status and other metrics.
    """

    instances: dict[str, Any]
    snapshots: dict[str, Any]
    export_jobs: dict[str, Any]


class ExportJobSummary(BaseModel):
    """Export job summary for ops endpoints.

    Lightweight version for listing in GET /api/ops/export-jobs.
    Note: Different from internal ExportJobResponse which has more fields.
    """

    id: int
    snapshot_id: int
    entity_type: str
    entity_name: str
    status: str
    claimed_at: str | None = None
    claimed_by: str | None = None
    attempts: int = 0
    error_message: str | None = None
    starburst_role: str | None = None


class ExportJobsListResponse(BaseModel):
    """List of export jobs for ops debugging.

    From GET /api/ops/export-jobs response.
    """

    jobs: list[ExportJobSummary]


# =============================================================================
# Configuration: Lifecycle
# =============================================================================


class ResourceLifecycleConfig(BaseModel):
    """Lifecycle configuration for a single resource type.

    Used for mappings, snapshots, and instances.
    """

    default_ttl: Annotated[
        str | None,
        Field(
            default=None,
            description="Default TTL (ISO 8601 duration)",
            examples=["P30D", "PT24H"],
        ),
    ]

    default_inactivity: Annotated[
        str | None,
        Field(
            default=None,
            description="Default inactivity timeout (ISO 8601 duration)",
            examples=["PT4H", "P7D"],
        ),
    ]

    max_ttl: Annotated[
        str | None,
        Field(
            default=None,
            description="Maximum allowed TTL (ISO 8601 duration)",
            examples=["P90D", "P365D"],
        ),
    ]


class LifecycleConfigResponse(BaseModel):
    """Full lifecycle configuration for all resource types.

    From GET /api/config/lifecycle response.
    """

    mapping: ResourceLifecycleConfig
    snapshot: ResourceLifecycleConfig
    instance: ResourceLifecycleConfig


class LifecycleConfigRequest(BaseModel):
    """Request to update lifecycle configuration.

    From PUT /api/config/lifecycle request.
    Only provided fields are updated; omitted fields remain unchanged.
    """

    mapping: ResourceLifecycleConfig | None = None
    snapshot: ResourceLifecycleConfig | None = None
    instance: ResourceLifecycleConfig | None = None


# =============================================================================
# Configuration: Concurrency
# =============================================================================


class ConcurrencyConfig(BaseModel):
    """Concurrency limits configuration.

    From GET/PUT /api/config/concurrency.
    """

    per_analyst: Annotated[
        int,
        Field(
            ge=1,
            le=100,
            description="Max instances per analyst",
        ),
    ]

    cluster_total: Annotated[
        int,
        Field(
            ge=1,
            le=1000,
            description="Max instances cluster-wide",
        ),
    ]


class ConcurrencyConfigResponse(BaseModel):
    """Concurrency configuration response with metadata.

    From GET /api/config/concurrency response.
    """

    per_analyst: int
    cluster_total: int
    updated_at: datetime | None = None


# =============================================================================
# Configuration: Maintenance Mode
# =============================================================================


class MaintenanceModeRequest(BaseModel):
    """Request to set maintenance mode.

    From PUT /api/config/maintenance request.
    """

    enabled: bool
    message: Annotated[
        str,
        Field(
            default="",
            description="Message to display to users during maintenance",
        ),
    ]


class MaintenanceModeResponse(BaseModel):
    """Maintenance mode status.

    From GET /api/config/maintenance response.
    When enabled, new instance creation is blocked.
    """

    enabled: bool
    message: str
    updated_at: datetime | None = None
    updated_by: str | None = None


# =============================================================================
# Configuration: Export
# =============================================================================


class ExportConfigRequest(BaseModel):
    """Request to update export configuration.

    From PUT /api/config/export request.
    """

    max_duration_seconds: Annotated[
        int,
        Field(
            ge=60,
            le=86400,
            description="Max export job duration in seconds (1 min to 24 hours)",
        ),
    ]


class ExportConfigResponse(BaseModel):
    """Export configuration.

    From GET /api/config/export response.
    """

    max_duration_seconds: int
    updated_at: datetime | None = None
    updated_by: str | None = None


# =============================================================================
# Admin: Bulk Operations
# =============================================================================


class BulkDeleteFilters(BaseModel):
    """Filters for bulk delete operation.

    At least one filter is required (safety check).
    """

    name_prefix: Annotated[
        str | None,
        Field(
            default=None,
            min_length=1,
            max_length=255,
            description="Filter by name prefix",
        ),
    ]

    created_by: Annotated[
        str | None,
        Field(
            default=None,
            min_length=1,
            max_length=255,
            description="Filter by creator username",
        ),
    ]

    older_than_hours: Annotated[
        int | None,
        Field(
            default=None,
            ge=1,
            description="Filter by age in hours",
        ),
    ]

    status: Annotated[
        str | None,
        Field(
            default=None,
            description="Filter by status",
        ),
    ]


class BulkDeleteRequest(BaseModel):
    """Request to bulk delete resources.

    From DELETE /api/admin/resources/bulk request.

    Safety features:
    - Requires at least one filter
    - Max 100 deletions per request
    - Expected count validation
    - Dry run mode available
    """

    resource_type: Annotated[
        str,
        Field(
            pattern=r"^(instance|snapshot|mapping)$",
            description="Resource type to delete",
        ),
    ]

    filters: Annotated[
        BulkDeleteFilters,
        Field(description="Filters (at least one required)"),
    ]

    reason: Annotated[
        str,
        Field(
            min_length=1,
            max_length=500,
            description="Reason for deletion (audit log)",
        ),
    ]

    expected_count: Annotated[
        int | None,
        Field(
            default=None,
            ge=0,
            description="Expected number of resources to delete (safety check)",
        ),
    ]

    dry_run: Annotated[
        bool,
        Field(
            default=False,
            description="If true, return what would be deleted without deleting",
        ),
    ]


class BulkDeleteResponse(BaseModel):
    """Response from bulk delete operation.

    From DELETE /api/admin/resources/bulk response.
    """

    dry_run: bool
    matched_count: int
    deleted_count: int = 0
    deleted_ids: list[int] = []
    failed_ids: list[int] = []
    errors: dict[int, str] = {}
    matched_ids: list[int] = []  # For dry run mode


class E2ECleanupResponse(BaseModel):
    """Response from E2E test cleanup operation.

    From DELETE /api/admin/e2e-cleanup response.
    Deletes all resources owned by configured E2E test users.
    """

    users_processed: list[str] = []
    instances_deleted: int = 0
    snapshots_deleted: int = 0
    mappings_deleted: int = 0
    pods_terminated: int = 0
    gcs_files_deleted: int = 0
    gcs_bytes_deleted: int = 0
    errors: list[dict] = []
    success: bool = True
