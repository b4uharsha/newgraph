"""
API schemas for resource operations (mappings, snapshots, instances).

Request and response models for the public API endpoints.
All structures derived from docs/system-design/api/ specifications.
"""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Self

from pydantic import BaseModel, Field, model_validator

from graph_olap_schemas.constants import (
    ISO8601_DURATION_PATTERN,
    MAX_DESCRIPTION_LENGTH,
    MAX_RESOURCE_NAME_LENGTH,
    MIN_NAME_LENGTH,
    ChangeType,
)
from graph_olap_schemas.definitions import EdgeDefinition, NodeDefinition
from graph_olap_schemas.wrapper_interface import WrapperType


class SnapshotStatus(StrEnum):
    """
    Snapshot lifecycle states.

    From requirements.md: "status | enum | pending, creating, ready, failed, cancelled"
    """

    PENDING = "pending"
    CREATING = "creating"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"


class InstanceStatus(StrEnum):
    """
    Instance lifecycle states.

    From requirements.md: "status | enum | starting, running, stopping, failed"
    Note: "stopping = terminating, instance deleted when complete"
    Additional: "waiting_for_snapshot" for instances created from mapping (pending snapshot creation)
    """

    WAITING_FOR_SNAPSHOT = "waiting_for_snapshot"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    FAILED = "failed"


class InstanceErrorCode(StrEnum):
    """
    Machine-readable error codes for instance failures.

    From api.internal.spec.md PUT /instances/:id/status.
    Used to categorize failure types for debugging and display.
    """

    STARTUP_FAILED = "STARTUP_FAILED"
    MAPPING_FETCH_ERROR = "MAPPING_FETCH_ERROR"
    SCHEMA_CREATE_ERROR = "SCHEMA_CREATE_ERROR"
    DATA_LOAD_ERROR = "DATA_LOAD_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
    OOM_KILLED = "OOM_KILLED"
    UNEXPECTED_TERMINATION = "UNEXPECTED_TERMINATION"


# =============================================================================
# Mapping Schemas
# =============================================================================


class CreateMappingRequest(BaseModel):
    """
    Request to create a new mapping.

    From api.mappings.spec.md POST /api/mappings.
    Creates mapping with initial version (v1).
    """

    name: Annotated[
        str,
        Field(
            min_length=MIN_NAME_LENGTH,
            max_length=MAX_RESOURCE_NAME_LENGTH,
            description="Display name for the mapping",
            examples=["Customer Analysis", "Transaction Graph"],
        ),
    ]

    description: Annotated[
        str | None,
        Field(
            default=None,
            max_length=MAX_DESCRIPTION_LENGTH,
            description="General description of the mapping",
            examples=["Graph mapping for customer transaction analysis"],
        ),
    ]

    node_definitions: Annotated[
        list[NodeDefinition],
        Field(
            min_length=1,
            description="Node definitions (at least one required)",
        ),
    ]

    edge_definitions: Annotated[
        list[EdgeDefinition],
        Field(
            default_factory=list,
            description="Edge definitions (optional)",
        ),
    ]

    ttl: Annotated[
        str | None,
        Field(
            default=None,
            pattern=ISO8601_DURATION_PATTERN,
            description="Time-to-live (ISO 8601 duration)",
            examples=["P30D", "P7D", "PT24H"],
        ),
    ]

    inactivity_timeout: Annotated[
        str | None,
        Field(
            default=None,
            pattern=ISO8601_DURATION_PATTERN,
            description="Delete after no snapshots created (ISO 8601 duration)",
            examples=["P30D", "P7D"],
        ),
    ]

    @model_validator(mode="after")
    def validate_unique_labels(self) -> Self:
        """Ensure node labels are unique within the mapping."""
        labels = [n.label for n in self.node_definitions]
        if len(labels) != len(set(labels)):
            raise ValueError("Node labels must be unique within a mapping")
        return self

    @model_validator(mode="after")
    def validate_unique_edge_types(self) -> Self:
        """Ensure edge types are unique within the mapping."""
        types = [e.type for e in self.edge_definitions]
        if len(types) != len(set(types)):
            raise ValueError("Edge types must be unique within a mapping")
        return self

    @model_validator(mode="after")
    def validate_edge_references(self) -> Self:
        """Ensure edge from_node/to_node reference existing node labels."""
        labels = {n.label for n in self.node_definitions}
        for edge in self.edge_definitions:
            if edge.from_node not in labels:
                raise ValueError(
                    f"Edge '{edge.type}' references unknown from_node '{edge.from_node}'"
                )
            if edge.to_node not in labels:
                raise ValueError(f"Edge '{edge.type}' references unknown to_node '{edge.to_node}'")
        return self


class UpdateMappingRequest(BaseModel):
    """
    Request to update a mapping.

    From api.mappings.spec.md PUT /api/mappings/:id.
    Creates a new version if definitions changed. Requires change_description.
    """

    name: Annotated[
        str | None,
        Field(
            default=None,
            min_length=MIN_NAME_LENGTH,
            max_length=MAX_RESOURCE_NAME_LENGTH,
            description="Updated display name",
        ),
    ]

    description: Annotated[
        str | None,
        Field(
            default=None,
            max_length=MAX_DESCRIPTION_LENGTH,
            description="Updated description",
        ),
    ]

    node_definitions: Annotated[
        list[NodeDefinition] | None,
        Field(
            default=None,
            description="Updated node definitions (creates new version)",
        ),
    ]

    edge_definitions: Annotated[
        list[EdgeDefinition] | None,
        Field(
            default=None,
            description="Updated edge definitions (creates new version)",
        ),
    ]

    change_description: Annotated[
        str,
        Field(
            min_length=1,
            max_length=1000,
            description="Description of changes (required for updates)",
            examples=["Added city property to Customer node"],
        ),
    ]

    ttl: Annotated[
        str | None,
        Field(
            default=None,
            pattern=ISO8601_DURATION_PATTERN,
            description="Updated time-to-live",
        ),
    ]

    inactivity_timeout: Annotated[
        str | None,
        Field(
            default=None,
            pattern=ISO8601_DURATION_PATTERN,
            description="Updated inactivity timeout",
        ),
    ]


class MappingResponse(BaseModel):
    """
    Full mapping response with current version details.

    From api.mappings.spec.md GET /api/mappings/:id response.
    """

    id: int
    owner_username: str
    name: str
    description: str | None
    current_version: int
    created_at: datetime | None
    updated_at: datetime | None
    ttl: str | None
    inactivity_timeout: str | None
    node_definitions: list[NodeDefinition]
    edge_definitions: list[EdgeDefinition]
    change_description: str | None
    version_created_at: datetime | None
    version_created_by: str | None


class MappingSummaryResponse(BaseModel):
    """
    Mapping summary for list responses.

    Lightweight version without full definitions.
    """

    id: int
    owner_username: str
    name: str
    description: str | None
    current_version: int
    created_at: datetime | None
    updated_at: datetime | None
    node_count: int
    edge_type_count: int


class MappingVersionResponse(BaseModel):
    """
    Full version details response.

    From api.mappings.spec.md GET /api/mappings/:id/versions/:v response.
    """

    mapping_id: int
    version: int
    change_description: str | None
    node_definitions: list[NodeDefinition]
    edge_definitions: list[EdgeDefinition]
    created_at: datetime | None
    created_by: str


class MappingVersionSummaryResponse(BaseModel):
    """
    Version summary for list responses.

    From api.mappings.spec.md GET /api/mappings/:id/versions response.
    """

    version: int
    change_description: str | None
    created_at: datetime | None
    created_by: str


class NodeDiffResponse(BaseModel):
    """
    Node definition diff item.

    From api.mappings.spec.md GET /api/mappings/:id/versions/:v1/diff/:v2 response.
    """

    label: str
    change_type: ChangeType
    fields_changed: list[str] | None = None
    from_: dict[str, Any] | None = Field(None, alias="from")
    to: dict[str, Any] | None = None

    model_config = {"populate_by_name": True}


class EdgeDiffResponse(BaseModel):
    """
    Edge definition diff item.

    From api.mappings.spec.md GET /api/mappings/:id/versions/:v1/diff/:v2 response.
    """

    type: str
    change_type: ChangeType
    fields_changed: list[str] | None = None
    from_: dict[str, Any] | None = Field(None, alias="from")
    to: dict[str, Any] | None = None

    model_config = {"populate_by_name": True}


class MappingDiffSummaryResponse(BaseModel):
    """
    Summary counts for diff result.

    From api.mappings.spec.md GET /api/mappings/:id/versions/:v1/diff/:v2 response.
    """

    nodes_added: int
    nodes_removed: int
    nodes_modified: int
    edges_added: int
    edges_removed: int
    edges_modified: int


class MappingDiffChangesResponse(BaseModel):
    """
    Detailed changes in diff result.

    From api.mappings.spec.md GET /api/mappings/:id/versions/:v1/diff/:v2 response.
    """

    nodes: list[NodeDiffResponse]
    edges: list[EdgeDiffResponse]


class MappingDiffDataResponse(BaseModel):
    """
    Data payload for diff response.

    From api.mappings.spec.md GET /api/mappings/:id/versions/:v1/diff/:v2 response.
    """

    mapping_id: int
    from_version: int
    to_version: int
    summary: MappingDiffSummaryResponse
    changes: MappingDiffChangesResponse


class MappingDiffResponse(BaseModel):
    """
    Complete diff response.

    From api.mappings.spec.md GET /api/mappings/:id/versions/:v1/diff/:v2 response.
    """

    data: MappingDiffDataResponse


# =============================================================================
# Snapshot Schemas
# =============================================================================


class CreateSnapshotRequest(BaseModel):
    """
    Request to create a snapshot from a mapping.

    From api.snapshots.spec.md POST /api/snapshots.
    """

    mapping_id: Annotated[
        int,
        Field(
            gt=0,
            description="Source mapping ID",
        ),
    ]

    mapping_version: Annotated[
        int | None,
        Field(
            default=None,
            gt=0,
            description="Mapping version (defaults to current_version)",
        ),
    ]

    name: Annotated[
        str,
        Field(
            min_length=MIN_NAME_LENGTH,
            max_length=MAX_RESOURCE_NAME_LENGTH,
            description="Display name for the snapshot",
            examples=["Daily Export 2025-01-15"],
        ),
    ]

    description: Annotated[
        str | None,
        Field(
            default=None,
            max_length=MAX_DESCRIPTION_LENGTH,
            description="Optional description",
        ),
    ]

    ttl: Annotated[
        str | None,
        Field(
            default=None,
            pattern=ISO8601_DURATION_PATTERN,
            description="Time-to-live (ISO 8601 duration)",
            examples=["P7D", "P1D"],
        ),
    ]

    inactivity_timeout: Annotated[
        str | None,
        Field(
            default=None,
            pattern=ISO8601_DURATION_PATTERN,
            description="Delete after no instances created",
            examples=["P3D"],
        ),
    ]


class SnapshotResponse(BaseModel):
    """
    Snapshot response.

    From api.snapshots.spec.md GET /api/snapshots/:id response.
    """

    id: int
    mapping_id: int
    mapping_version: int
    owner_username: str
    name: str
    description: str | None
    gcs_path: str
    status: SnapshotStatus
    size_bytes: int | None
    node_counts: dict[str, int] | None
    edge_counts: dict[str, int] | None
    progress: dict[str, Any] | None
    error_message: str | None
    created_at: datetime | None
    updated_at: datetime | None
    ttl: str | None
    inactivity_timeout: str | None
    last_used_at: datetime | None


# =============================================================================
# Instance Schemas
# =============================================================================


class CreateInstanceRequest(BaseModel):
    """
    Request to create an instance from a snapshot.

    From api.instances.spec.md POST /api/instances.
    """

    snapshot_id: Annotated[
        int,
        Field(
            gt=0,
            description="Source snapshot ID",
        ),
    ]

    wrapper_type: Annotated[
        WrapperType,
        Field(
            description="Graph database wrapper type (ryugraph, falkordb). REQUIRED - must be explicitly specified.",
            examples=["ryugraph", "falkordb"],
        ),
    ]

    name: Annotated[
        str,
        Field(
            min_length=MIN_NAME_LENGTH,
            max_length=MAX_RESOURCE_NAME_LENGTH,
            description="Display name for the instance",
            examples=["Analysis Session"],
        ),
    ]

    description: Annotated[
        str | None,
        Field(
            default=None,
            max_length=MAX_DESCRIPTION_LENGTH,
            description="Optional description",
        ),
    ]

    ttl: Annotated[
        str | None,
        Field(
            default=None,
            pattern=ISO8601_DURATION_PATTERN,
            description="Time-to-live (ISO 8601 duration)",
            examples=["PT24H", "PT4H"],
        ),
    ]

    inactivity_timeout: Annotated[
        str | None,
        Field(
            default=None,
            pattern=ISO8601_DURATION_PATTERN,
            description="Terminate after no activity",
            examples=["PT4H", "PT1H"],
        ),
    ]

    cpu_cores: Annotated[
        int | None,
        Field(
            default=None,
            ge=1,
            le=8,
            description="CPU cores for the instance (default: 2, max: 8). Sets request=N, limit=2N for burst capacity.",
            examples=[2, 4],
        ),
    ]


class CreateInstanceFromMappingRequest(BaseModel):
    """
    Request to create an instance directly from a mapping.

    This creates a snapshot automatically and links the instance to it.
    The instance will be in 'waiting_for_snapshot' status until the snapshot is ready.
    """

    mapping_id: Annotated[
        int,
        Field(
            gt=0,
            description="Source mapping ID",
        ),
    ]

    mapping_version: Annotated[
        int | None,
        Field(
            default=None,
            gt=0,
            description="Mapping version (defaults to current)",
        ),
    ]

    wrapper_type: Annotated[
        WrapperType,
        Field(
            description="Graph database wrapper type (ryugraph, falkordb). REQUIRED - must be explicitly specified.",
            examples=["ryugraph", "falkordb"],
        ),
    ]

    name: Annotated[
        str,
        Field(
            min_length=MIN_NAME_LENGTH,
            max_length=MAX_RESOURCE_NAME_LENGTH,
            description="Display name for the instance",
            examples=["Analysis Session"],
        ),
    ]

    description: Annotated[
        str | None,
        Field(
            default=None,
            max_length=MAX_DESCRIPTION_LENGTH,
            description="Optional description",
        ),
    ]

    ttl: Annotated[
        str | None,
        Field(
            default=None,
            pattern=ISO8601_DURATION_PATTERN,
            description="Time-to-live (ISO 8601 duration)",
            examples=["PT24H", "PT4H"],
        ),
    ]

    inactivity_timeout: Annotated[
        str | None,
        Field(
            default=None,
            pattern=ISO8601_DURATION_PATTERN,
            description="Terminate after no activity",
            examples=["PT4H", "PT1H"],
        ),
    ]

    cpu_cores: Annotated[
        int | None,
        Field(
            default=None,
            ge=1,
            le=8,
            description="CPU cores for the instance (default: 2, max: 8). Sets request=N, limit=2N for burst capacity.",
            examples=[2, 4],
        ),
    ]


class InstanceResponse(BaseModel):
    """
    Instance response.

    From api.instances.spec.md GET /api/instances/:id response.
    """

    id: int
    snapshot_id: int
    owner_username: str
    wrapper_type: WrapperType
    name: str
    description: str | None
    status: InstanceStatus
    instance_url: str | None
    pod_name: str | None
    progress: dict[str, Any] | None
    error_code: InstanceErrorCode | None = None
    error_message: str | None
    stack_trace: str | None = None
    created_at: datetime | None
    updated_at: datetime | None
    started_at: datetime | None
    last_activity_at: datetime | None
    expires_at: datetime | None
    ttl: str | None
    inactivity_timeout: str | None
    memory_usage_bytes: int | None
    disk_usage_bytes: int | None
    cpu_cores: int | None = None


class LockStatusResponse(BaseModel):
    """
    Instance lock status response.

    From api.instances.spec.md GET /api/instances/:id/lock.
    Lock is implicit - created when algorithm starts, released when it finishes.
    """

    locked: bool
    lock_holder_username: str | None = None
    algorithm: str | None = None
    locked_at: datetime | None = None


# =============================================================================
# Lifecycle Schemas
# =============================================================================


class UpdateLifecycleRequest(BaseModel):
    """
    Request to update lifecycle settings.

    From api.mappings.spec.md PUT /api/mappings/:id/lifecycle.
    Also used for snapshots and instances.
    """

    ttl: Annotated[
        str | None,
        Field(
            default=None,
            pattern=ISO8601_DURATION_PATTERN,
            description="Time-to-live (ISO 8601 duration)",
        ),
    ]

    inactivity_timeout: Annotated[
        str | None,
        Field(
            default=None,
            pattern=ISO8601_DURATION_PATTERN,
            description="Inactivity timeout (ISO 8601 duration)",
        ),
    ]


class LifecycleResponse(BaseModel):
    """
    Lifecycle settings response.
    """

    id: int
    ttl: str | None
    inactivity_timeout: str | None
    updated_at: datetime | None


# =============================================================================
# Mapping Tree Schemas
# =============================================================================


class MappingTreeInstanceItem(BaseModel):
    """Instance item in mapping tree."""

    id: int
    name: str
    status: str


class MappingTreeSnapshotItem(BaseModel):
    """Snapshot item in mapping tree version."""

    id: int
    name: str
    status: str
    created_at: datetime | None
    instance_count: int
    instances: list[MappingTreeInstanceItem]


class MappingTreeVersionItem(BaseModel):
    """Version item in mapping tree."""

    version: int
    change_description: str | None
    created_at: datetime | None
    snapshot_count: int
    snapshots: list[MappingTreeSnapshotItem]


class MappingTreeTotals(BaseModel):
    """Aggregated counts for mapping tree."""

    version_count: int
    snapshot_count: int
    instance_count: int


class MappingTreeResponse(BaseModel):
    """
    Mapping tree response showing version → snapshot → instance hierarchy.

    From api.mappings.spec.md GET /api/mappings/:id/tree.
    """

    id: int
    name: str
    owner_username: str
    current_version: int
    versions: list[MappingTreeVersionItem]
    totals: MappingTreeTotals
