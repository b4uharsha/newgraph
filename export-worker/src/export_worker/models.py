"""Pydantic models for the Export Worker.

These models define the structure of:
- Export job payloads (from Control Plane API)
- Node and edge definitions from mappings (extended from shared schemas)
- Progress tracking during export
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

# Import base types from shared schemas
from graph_olap_schemas import (
    EdgeDefinition as BaseEdgeDefinition,
)
from graph_olap_schemas import (
    ExportJobStatus,
    PrimaryKeyDefinition,
    PropertyDefinition,
    SnapshotStatus,
)
from graph_olap_schemas import (
    NodeDefinition as BaseNodeDefinition,
)
from pydantic import BaseModel, Field, field_validator


class NodeDefinition(BaseNodeDefinition):
    """Extended NodeDefinition with export worker utilities.

    Inherits validation from shared schemas and adds worker-specific
    methods for query generation.
    """

    @property
    def column_names(self) -> list[str]:
        """Get ordered column names for the UNLOAD query.

        Returns column names in the order expected by Starburst UNLOAD:
        primary key first, then properties.
        """
        return [self.primary_key.name] + [p.name for p in self.properties]


class EdgeDefinition(BaseEdgeDefinition):
    """Extended EdgeDefinition with export worker utilities.

    Inherits validation from shared schemas and adds worker-specific
    methods for query generation.
    """

    @property
    def column_names(self) -> list[str]:
        """Get ordered column names for the UNLOAD query.

        Returns column names in the order expected by Starburst UNLOAD:
        from_key, to_key, then properties.
        """
        return [self.from_key, self.to_key] + [p.name for p in self.properties]


class SnapshotRequest(BaseModel):
    """Export job payload for snapshot export requests.

    Schema defined in system.architecture.design.md (authoritative source).
    Note: Previously used for Pub/Sub messages, now used for database polling.
    """

    snapshot_id: int = Field(gt=0, description="Snapshot ID")
    mapping_id: int = Field(gt=0, description="Mapping ID")
    mapping_version: int = Field(gt=0, description="Mapping version number")
    gcs_base_path: str = Field(min_length=1, description="GCS base path for Parquet files")
    node_definitions: list[NodeDefinition] = Field(
        min_length=1, description="Node definitions to export"
    )
    edge_definitions: list[EdgeDefinition] = Field(
        default_factory=list, description="Edge definitions to export"
    )
    starburst_catalog: str = Field(min_length=1, description="Starburst catalog to query")
    created_at: str = Field(description="ISO 8601 timestamp")

    @field_validator("gcs_base_path")
    @classmethod
    def validate_gcs_path(cls, v: str) -> str:
        """Ensure GCS path has correct format."""
        if not v.startswith("gs://"):
            raise ValueError("GCS path must start with gs://")
        # Ensure trailing slash
        return v if v.endswith("/") else f"{v}/"

    def get_node_gcs_path(self, label: str) -> str:
        """Get GCS path for a node type's Parquet files."""
        return f"{self.gcs_base_path}nodes/{label}/"

    def get_edge_gcs_path(self, edge_type: str) -> str:
        """Get GCS path for an edge type's Parquet files."""
        return f"{self.gcs_base_path}edges/{edge_type}/"


class StepStatus(str, Enum):
    """Status of an individual export step."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class ProgressStep(BaseModel):
    """Progress information for a single node or edge export."""

    name: str = Field(description="Node label or edge type")
    step_type: str = Field(description="'node' or 'edge'")
    status: StepStatus = Field(default=StepStatus.PENDING)
    row_count: int | None = Field(default=None, description="Rows exported (when completed)")
    error: str | None = Field(default=None, description="Error message (when failed)")
    started_at: datetime | None = Field(default=None)
    completed_at: datetime | None = Field(default=None)


class ExportPhase(str, Enum):
    """Current phase of the export process."""

    INITIALIZING = "initializing"
    EXPORTING_NODES = "exporting_nodes"
    EXPORTING_EDGES = "exporting_edges"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    FAILED = "failed"


class SnapshotProgress(BaseModel):
    """Progress tracking for the entire snapshot export."""

    phase: ExportPhase = Field(default=ExportPhase.INITIALIZING)
    started_at: datetime = Field(default_factory=datetime.utcnow)
    current_step: str | None = Field(default=None)
    steps: list[ProgressStep] = Field(default_factory=list)
    completed_at: datetime | None = Field(default=None)

    def to_api_dict(self) -> dict[str, Any]:
        """Convert to dict format expected by Control Plane API."""
        return {
            "phase": self.phase.value,
            "started_at": self.started_at.isoformat() + "Z",
            "current_step": self.current_step,
            "steps": [
                {
                    "name": step.name,
                    "type": step.step_type,
                    "status": step.status.value,
                    "row_count": step.row_count,
                }
                for step in self.steps
            ],
        }

    def get_node_counts(self) -> dict[str, int]:
        """Get completed node counts by label."""
        return {
            step.name: step.row_count
            for step in self.steps
            if step.step_type == "node" and step.row_count is not None
        }

    def get_edge_counts(self) -> dict[str, int]:
        """Get completed edge counts by type."""
        return {
            step.name: step.row_count
            for step in self.steps
            if step.step_type == "edge" and step.row_count is not None
        }

    def mark_step_started(self, name: str) -> None:
        """Mark a step as in progress."""
        for step in self.steps:
            if step.name == name:
                step.status = StepStatus.IN_PROGRESS
                step.started_at = datetime.utcnow()
                self.current_step = name
                break

    def mark_step_completed(self, name: str, row_count: int) -> None:
        """Mark a step as completed with row count."""
        for step in self.steps:
            if step.name == name:
                step.status = StepStatus.COMPLETED
                step.row_count = row_count
                step.completed_at = datetime.utcnow()
                self.current_step = None
                break

    def mark_step_failed(self, name: str, error: str) -> None:
        """Mark a step as failed with error message."""
        for step in self.steps:
            if step.name == name:
                step.status = StepStatus.FAILED
                step.error = error
                step.completed_at = datetime.utcnow()
                self.current_step = None
                break


class ExportJob(BaseModel):
    """Export job tracking for stateless database polling architecture.

    One ExportJob per node/edge type per snapshot. Contains all information
    needed to execute and track the export, including denormalized SQL and
    stateless polling state.

    See ADR-025 for architecture details.

    Status flow:
        pending → claimed → submitted → completed
                                      → failed
    """

    id: int | None = Field(default=None, description="Database ID (set after creation)")
    snapshot_id: int = Field(description="Parent snapshot ID")
    job_type: str = Field(description="'node' or 'edge'")
    entity_name: str = Field(description="Node label or edge type name")
    status: ExportJobStatus = Field(default=ExportJobStatus.PENDING)

    # Denormalized job definition (so workers don't need separate mapping fetch)
    sql: str | None = Field(default=None, description="SELECT query to export")
    column_names: list[str] = Field(default_factory=list, description="Column names for UNLOAD")
    starburst_catalog: str | None = Field(default=None, description="Starburst catalog name")
    starburst_role: str | None = Field(default=None, description="Use case ID for Starburst SET ROLE")
    gcs_path: str = Field(description="GCS destination for Parquet files")

    # Claiming state (lease-based ownership)
    claimed_by: str | None = Field(default=None, description="Worker ID that claimed this job")
    claimed_at: str | None = Field(default=None, description="ISO 8601 when claimed")

    # Starburst tracking
    starburst_query_id: str | None = Field(default=None, description="Query ID from Starburst")
    next_uri: str | None = Field(default=None, description="Polling URI for query status")

    # Stateless polling state (persisted in database, not in-memory)
    next_poll_at: str | None = Field(default=None, description="ISO 8601 when to poll next")
    poll_count: int = Field(default=0, description="Current poll count for Fibonacci backoff")

    # Results (set on completion)
    row_count: int | None = Field(default=None, description="Row count (when completed)")
    size_bytes: int | None = Field(default=None, description="Size in bytes (when completed)")

    # Timestamps
    submitted_at: str | None = Field(default=None, description="ISO 8601 when submitted")
    completed_at: str | None = Field(default=None, description="ISO 8601 when completed/failed")
    error_message: str | None = Field(default=None, description="Error details (when failed)")

    def to_api_dict(self) -> dict[str, Any]:
        """Convert to dict format for Control Plane API."""
        return {
            "snapshot_id": self.snapshot_id,
            "job_type": self.job_type,
            "entity_name": self.entity_name,
            "status": self.status.value,
            "sql": self.sql,
            "column_names": self.column_names,
            "starburst_catalog": self.starburst_catalog,
            "starburst_role": self.starburst_role,
            "gcs_path": self.gcs_path,
            "claimed_by": self.claimed_by,
            "claimed_at": self.claimed_at,
            "starburst_query_id": self.starburst_query_id,
            "next_uri": self.next_uri,
            "next_poll_at": self.next_poll_at,
            "poll_count": self.poll_count,
            "row_count": self.row_count,
            "size_bytes": self.size_bytes,
            "submitted_at": self.submitted_at,
            "completed_at": self.completed_at,
            "error_message": self.error_message,
        }

    @classmethod
    def from_api_dict(cls, data: dict[str, Any]) -> ExportJob:
        """Create from Control Plane API response."""
        return cls(
            id=data.get("id"),
            snapshot_id=data["snapshot_id"],
            job_type=data["job_type"],
            entity_name=data["entity_name"],
            status=ExportJobStatus(data["status"]),
            sql=data.get("sql"),
            column_names=data.get("column_names", []),
            starburst_catalog=data.get("starburst_catalog"),
            starburst_role=data.get("starburst_role"),
            gcs_path=data["gcs_path"],
            claimed_by=data.get("claimed_by"),
            claimed_at=data.get("claimed_at"),
            starburst_query_id=data.get("starburst_query_id"),
            next_uri=data.get("next_uri"),
            next_poll_at=data.get("next_poll_at"),
            poll_count=data.get("poll_count", 0),
            row_count=data.get("row_count"),
            size_bytes=data.get("size_bytes"),
            submitted_at=data.get("submitted_at"),
            completed_at=data.get("completed_at"),
            error_message=data.get("error_message"),
        )


class SnapshotJobsResult(BaseModel):
    """Result from checking if all snapshot jobs are complete.

    Used by worker to determine if snapshot can be finalized.
    """

    all_complete: bool = Field(description="True if all jobs are completed or failed")
    any_failed: bool = Field(description="True if any job failed")
    first_error: str | None = Field(default=None, description="First error message (if any failed)")
    node_counts: dict[str, int] = Field(default_factory=dict, description="Row counts by node label")
    edge_counts: dict[str, int] = Field(default_factory=dict, description="Row counts by edge type")
    total_size: int = Field(default=0, description="Total size in bytes")


# Re-export shared types for backward compatibility
__all__ = [
    "EdgeDefinition",
    "ExportJob",
    "ExportJobStatus",
    "ExportPhase",
    # Extended types
    "NodeDefinition",
    "PrimaryKeyDefinition",
    "ProgressStep",
    # From shared schemas
    "PropertyDefinition",
    "SnapshotJobsResult",
    "SnapshotProgress",
    # Worker-specific types
    "SnapshotRequest",
    "SnapshotStatus",
    "StepStatus",
]
