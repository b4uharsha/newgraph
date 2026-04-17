"""
Pydantic response models for API serialization.

This module re-exports response models from the shared graph_olap_schemas package
and defines any control-plane-specific response models.

All models match the authoritative documentation in docs/system-design/api/.
"""

from datetime import datetime
from typing import Any, TypeVar

# Re-export shared response schemas from graph_olap_schemas
# Re-export internal API responses
from graph_olap_schemas import (
    CacheStatsResponse,
    CatalogResponse,
    ColumnResponse,
    DataResponse,
    ErrorDetail,
    ErrorResponse,
    ExportJobResponse,
    InstanceMappingResponse,
    InstanceResponse,
    LifecycleResponse,
    LockStatusResponse,
    MappingResponse,
    MappingSummaryResponse,
    MappingVersionResponse,
    MappingVersionSummaryResponse,
    Meta,
    PaginatedResponse,
    PaginationMeta,
    SchemaResponse,
    ShutdownResponse,
    SnapshotResponse,
    TableResponse,
    UpdatedResponse,
)
from pydantic import BaseModel

T = TypeVar("T")

# Note: Definition response models (PropertyDefinition, NodeDefinition, etc.)
# are imported from graph_olap_schemas and re-exported above.
# Use those directly instead of creating duplicate response models.

# Control-plane specific response models


class UserResponse(BaseModel):
    """User in response."""

    username: str
    email: str
    display_name: str
    role: str
    created_at: datetime | None
    is_active: bool


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    database: str = "unknown"
    version: str = "0.1.0"


class FavoriteResponse(BaseModel):
    """Favorite in response."""

    resource_type: str
    resource_id: int
    resource_name: str
    resource_owner: str | None
    created_at: datetime | None
    resource_exists: bool


class FavoriteCreatedResponse(BaseModel):
    """Response after adding a favorite."""

    resource_type: str
    resource_id: int
    created_at: datetime | None


class FavoriteDeletedResponse(BaseModel):
    """Response after removing a favorite."""

    deleted: bool = True


class ExportJobsCreatedResponse(BaseModel):
    """Response after creating export jobs."""

    created: int
    jobs: list[dict[str, Any]]


class ClaimExportJobsRequest(BaseModel):
    """Request to claim pending export jobs (ADR-025)."""

    worker_id: str
    limit: int = 10


class ClaimExportJobsResponse(BaseModel):
    """Response from claiming export jobs (ADR-025)."""

    jobs: list[dict[str, Any]]


class PollableExportJobsResponse(BaseModel):
    """Response with pollable export jobs (ADR-025)."""

    jobs: list[dict[str, Any]]


class ExportJobWithDefinitionResponse(BaseModel):
    """Export job with denormalized definition fields (ADR-025).

    Extends base export job with fields needed for stateless processing:
    - sql, column_names, starburst_catalog for query execution
    - claimed_by, claimed_at for ownership tracking
    - next_poll_at, poll_count for polling schedule
    """

    id: int
    snapshot_id: int
    job_type: str
    entity_name: str
    status: str
    # Denormalized definition
    sql: str | None = None
    column_names: list[str] | None = None
    starburst_catalog: str | None = None
    # Claiming state
    claimed_by: str | None = None
    claimed_at: datetime | None = None
    # Starburst tracking
    starburst_query_id: str | None = None
    next_uri: str | None = None
    # Polling state
    next_poll_at: datetime | None = None
    poll_count: int = 0
    # Output
    gcs_path: str
    row_count: int | None = None
    size_bytes: int | None = None
    submitted_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


__all__ = [
    "CacheStatsResponse",
    # From graph_olap_schemas - Schema metadata
    "CatalogResponse",
    # ADR-025: Database polling
    "ClaimExportJobsRequest",
    "ClaimExportJobsResponse",
    "ColumnResponse",
    "DataResponse",
    "ErrorDetail",
    "ErrorResponse",
    # From graph_olap_schemas - Internal
    "ExportJobResponse",
    "ExportJobWithDefinitionResponse",
    "ExportJobsCreatedResponse",
    "FavoriteCreatedResponse",
    "FavoriteDeletedResponse",
    "FavoriteResponse",
    "HealthResponse",
    "InstanceMappingResponse",
    "InstanceResponse",
    "LifecycleResponse",
    "LockStatusResponse",
    # From graph_olap_schemas - Resources
    "MappingResponse",
    "MappingSummaryResponse",
    "MappingVersionResponse",
    "MappingVersionSummaryResponse",
    # From graph_olap_schemas - Common
    "Meta",
    "PaginatedResponse",
    "PaginationMeta",
    "PollableExportJobsResponse",
    "SchemaResponse",
    "ShutdownResponse",
    "SnapshotResponse",
    "TableResponse",
    "UpdatedResponse",
    # Control-plane specific
    "UserResponse",
]
