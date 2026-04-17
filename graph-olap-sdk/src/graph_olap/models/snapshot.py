"""Snapshot-related Pydantic models.

These models extend the shared graph-olap-schemas with SDK-specific
functionality for API parsing and Jupyter display.

Note: Explicit snapshot creation APIs are deprecated. Snapshots are now
created implicitly when instances are created via create_from_mapping().
The Snapshot model is still used internally to represent snapshot data.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

# Import shared enums
from graph_olap_schemas import SnapshotStatus
from pydantic import BaseModel, ConfigDict


class ExportJobProgress(BaseModel):
    """Progress info for a single export job."""

    model_config = ConfigDict(frozen=True)

    name: str  # Entity name (node label or edge type)
    type: str  # "node" or "edge"
    status: str  # pending, claimed, submitted, completed, failed
    row_count: int | None = None


class SnapshotProgress(BaseModel):
    """Detailed progress for snapshot export."""

    model_config = ConfigDict(frozen=True)

    jobs_total: int = 0
    jobs_pending: int = 0
    jobs_claimed: int = 0
    jobs_submitted: int = 0
    jobs_completed: int = 0
    jobs_failed: int = 0
    jobs: list[ExportJobProgress] = []

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> SnapshotProgress:
        """Create from API response data."""
        jobs = [
            ExportJobProgress(
                name=j.get("name", "unknown"),
                type=j.get("type", "unknown"),
                status=j.get("status", "unknown"),
                row_count=j.get("row_count"),
            )
            for j in data.get("jobs", [])
        ]
        return cls(
            jobs_total=data.get("jobs_total", 0),
            jobs_pending=data.get("jobs_pending", 0),
            jobs_claimed=data.get("jobs_claimed", 0),
            jobs_submitted=data.get("jobs_submitted", 0),
            jobs_completed=data.get("jobs_completed", 0),
            jobs_failed=data.get("jobs_failed", 0),
            jobs=jobs,
        )

    @property
    def progress_percent(self) -> int:
        """Calculate percentage of jobs completed."""
        if self.jobs_total == 0:
            return 0
        return int((self.jobs_completed / self.jobs_total) * 100)

    @property
    def is_complete(self) -> bool:
        """Check if all jobs are completed."""
        return self.jobs_total > 0 and self.jobs_completed == self.jobs_total

    @property
    def has_failures(self) -> bool:
        """Check if any jobs have failed."""
        return self.jobs_failed > 0


class Snapshot(BaseModel):
    """Data snapshot from mapping export.

    Matches SnapshotResponse schema from graph_olap_schemas.

    Note: Users should not create snapshots directly. Use
    client.instances.create_from_mapping() which handles snapshot
    creation automatically.
    """

    model_config = ConfigDict(frozen=True)

    id: int
    mapping_id: int | None = None  # May be missing in lifecycle responses
    mapping_version: int | None = None  # May be missing in lifecycle responses
    owner_username: str | None = None  # May be missing in lifecycle responses
    name: str | None = None  # May be missing in lifecycle responses
    description: str | None = None
    gcs_path: str = ""
    status: str | None = None  # May be missing in lifecycle responses
    size_bytes: int | None = None
    node_counts: dict[str, int] | None = None
    edge_counts: dict[str, int] | None = None
    progress: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    ready_at: datetime | None = None
    expires_at: datetime | None = None
    ttl: str | None = None
    inactivity_timeout: str | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> Snapshot:
        """Create from API response data."""
        return cls(
            id=data["id"],
            mapping_id=data.get("mapping_id"),  # Optional in lifecycle responses
            mapping_version=data.get("mapping_version"),  # Optional in lifecycle responses
            owner_username=data.get("owner_username"),  # Optional in lifecycle responses
            name=data.get("name"),  # Optional in lifecycle responses
            description=data.get("description"),
            gcs_path=data.get("gcs_path") or "",
            status=data.get("status"),  # Optional in lifecycle responses
            size_bytes=data.get("size_bytes"),
            node_counts=data.get("node_counts"),
            edge_counts=data.get("edge_counts"),
            progress=data.get("progress"),
            error_message=data.get("error_message"),
            created_at=_parse_datetime(data["created_at"]) if data.get("created_at") else None,
            updated_at=_parse_datetime(data["updated_at"]) if data.get("updated_at") else None,
            ready_at=_parse_datetime(data["ready_at"]) if data.get("ready_at") else None,
            expires_at=_parse_datetime(data["expires_at"]) if data.get("expires_at") else None,
            ttl=data.get("ttl"),
            inactivity_timeout=data.get("inactivity_timeout"),
        )

    @property
    def is_ready(self) -> bool:
        """Check if snapshot is ready for instance creation."""
        return self.status == "ready"

    @property
    def size_mb(self) -> float | None:
        """Size in megabytes."""
        if self.size_bytes is None:
            return None
        return self.size_bytes / (1024 * 1024)

    def _repr_html_(self) -> str:
        """Rich HTML display for Jupyter notebooks."""
        status_colors = {
            "ready": "#28a745",
            "creating": "#007bff",
            "pending": "#6c757d",
            "failed": "#dc3545",
        }
        status_color = status_colors.get(self.status or "", "#6c757d")

        size_str = f"{self.size_mb:.1f} MB" if self.size_mb else "N/A"
        node_total = sum(self.node_counts.values()) if self.node_counts else 0
        edge_total = sum(self.edge_counts.values()) if self.edge_counts else 0

        return f"""
        <div style="border: 1px solid #e1e4e8; padding: 12px; border-radius: 6px; margin: 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <h4 style="margin: 0; color: #24292e;">Snapshot: {self.name}</h4>
                <span style="background: {status_color}; color: white; padding: 2px 8px; border-radius: 12px; font-size: 12px; font-weight: 500;">{(self.status or 'unknown').upper()}</span>
            </div>
            <table style="border-collapse: collapse; font-size: 13px;">
                <tr><td style="padding: 4px 12px 4px 0; color: #586069;"><strong>ID:</strong></td><td>{self.id}</td></tr>
                <tr><td style="padding: 4px 12px 4px 0; color: #586069;"><strong>Mapping:</strong></td><td>ID {self.mapping_id} (v{self.mapping_version})</td></tr>
                <tr><td style="padding: 4px 12px 4px 0; color: #586069;"><strong>Owner:</strong></td><td>{self.owner_username}</td></tr>
                <tr><td style="padding: 4px 12px 4px 0; color: #586069;"><strong>Size:</strong></td><td>{size_str}</td></tr>
                <tr><td style="padding: 4px 12px 4px 0; color: #586069;"><strong>Graph:</strong></td><td>{node_total:,} nodes, {edge_total:,} edges</td></tr>
            </table>
        </div>
        """


def _parse_datetime(value: str) -> datetime:
    """Parse ISO datetime string, handling Z suffix."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


# Re-export shared types for backward compatibility
__all__ = [
    "Snapshot",
    # SDK types
    "SnapshotProgress",
    "ExportJobProgress",
    # From shared schemas (re-exported)
    "SnapshotStatus",
]
