"""
Pydantic request models for API validation.

This module re-exports request models from the shared graph_olap_schemas package
and defines any control-plane-specific request models.

All models match the authoritative documentation in docs/system-design/api/.
"""

# Re-export shared request schemas from graph_olap_schemas
# Re-export internal API schemas
from graph_olap_schemas import (
    CreateExportJobsRequest,
    CreateInstanceFromMappingRequest,
    CreateInstanceRequest,
    CreateMappingRequest,
    CreateSnapshotRequest,
    ExportJobDefinition,
    InstanceErrorCode,
    InstanceProgressStep,
    TriggerJobRequest,
    UpdateExportJobRequest,
    UpdateInstanceMetricsRequest,
    UpdateInstanceProgressRequest,
    UpdateInstanceStatusRequest,
    UpdateLifecycleRequest,
    UpdateMappingRequest,
    UpdateSnapshotStatusRequest,
)

# Re-export definition schemas (used for type hints)
from graph_olap_schemas import (
    EdgeDefinition as EdgeDefinitionSchema,
)
from graph_olap_schemas import (
    NodeDefinition as NodeDefinitionSchema,
)
from graph_olap_schemas import (
    PrimaryKeyDefinition as PrimaryKeyDefinitionSchema,
)
from graph_olap_schemas import (
    PropertyDefinition as PropertyDefinitionSchema,
)
from pydantic import BaseModel, Field

# Control-plane specific request models (not in shared schemas)


class AddFavoriteRequest(BaseModel):
    """Request to add a resource to favorites."""

    resource_type: str = Field(..., pattern=r"^(mapping|instance)$")
    resource_id: int = Field(..., gt=0)


class CopyMappingRequest(BaseModel):
    """Request to copy a mapping."""

    name: str = Field(..., min_length=1, max_length=255)


class UpdateSnapshotRequest(BaseModel):
    """Request to update snapshot metadata."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=4000)


class UpdateInstanceRequest(BaseModel):
    """Request to update instance metadata."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=4000)


class BulkDeleteFilters(BaseModel):
    """Filters for bulk delete operation."""

    name_prefix: str | None = Field(None, min_length=1, max_length=255)
    created_by: str | None = Field(None, min_length=1, max_length=255)
    older_than_hours: int | None = Field(None, ge=1)
    status: str | None = None


class BulkDeleteRequest(BaseModel):
    """Request to bulk delete resources."""

    resource_type: str = Field(..., pattern=r"^(instance|snapshot|mapping)$", description="Resource type")
    filters: BulkDeleteFilters = Field(..., description="At least one filter required")
    reason: str = Field(..., min_length=1, max_length=500, description="Reason for deletion (audit log)")
    expected_count: int | None = Field(None, ge=0, description="Expected number of resources to delete (safety check)")
    dry_run: bool = Field(False, description="If true, return what would be deleted without deleting")


class UpdateCpuRequest(BaseModel):
    """Request to update instance CPU cores."""

    cpu_cores: int = Field(..., ge=1, le=8, description="CPU cores (1-8)")


class UpdateMemoryRequest(BaseModel):
    """Request to update instance memory."""

    memory_gb: int = Field(..., ge=2, le=32, description="Memory in GB (2-32)")


__all__ = [
    # Control-plane specific
    "AddFavoriteRequest",
    "BulkDeleteFilters",
    "BulkDeleteRequest",
    "CopyMappingRequest",
    "CreateExportJobsRequest",
    "UpdateCpuRequest",
    "UpdateMemoryRequest",
    "CreateInstanceFromMappingRequest",
    "CreateInstanceRequest",
    # From graph_olap_schemas - Public API
    "CreateMappingRequest",
    "CreateSnapshotRequest",
    "EdgeDefinitionSchema",
    "ExportJobDefinition",
    "InstanceErrorCode",
    "InstanceProgressStep",
    # From graph_olap_schemas - Definition schemas
    "NodeDefinitionSchema",
    "PrimaryKeyDefinitionSchema",
    "PropertyDefinitionSchema",
    # From graph_olap_schemas - Ops API
    "TriggerJobRequest",
    "UpdateExportJobRequest",
    "UpdateInstanceMetricsRequest",
    "UpdateInstanceProgressRequest",
    "UpdateInstanceRequest",
    "UpdateInstanceStatusRequest",
    "UpdateLifecycleRequest",
    "UpdateMappingRequest",
    "UpdateSnapshotRequest",
    # From graph_olap_schemas - Internal API
    "UpdateSnapshotStatusRequest",
]
