"""Instance-related Pydantic models.

These models extend the shared graph-olap-schemas with SDK-specific
functionality for API parsing and Jupyter display.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

# Import shared enums
from graph_olap_schemas import InstanceStatus
from pydantic import BaseModel, ConfigDict


class InstanceProgress(BaseModel):
    """Detailed progress for instance startup."""

    model_config = ConfigDict(frozen=True)

    phase: str = "unknown"  # pod_scheduled, downloading, loading_schema, loading_data, ready, failed
    steps: list[dict[str, Any]] = []
    current_step: str | None = None
    progress_percent: int = 0
    error_message: str | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> InstanceProgress:
        """Create from API response data."""
        return cls(
            phase=data.get("phase", "unknown"),
            steps=data.get("steps", []),
            current_step=data.get("current_step"),
            progress_percent=data.get("progress_percent", 0),
            error_message=data.get("error_message"),
        )

    @property
    def completed_steps(self) -> int:
        """Number of completed steps."""
        return sum(1 for s in self.steps if s.get("status") == "completed")

    @property
    def total_steps(self) -> int:
        """Total number of steps."""
        return len(self.steps)


class LockStatus(BaseModel):
    """Instance lock status for algorithm execution.

    Field names are SDK-friendly aliases for the shared LockInfo schema:
    - holder_name maps to holder_username
    - algorithm maps to algorithm_name
    - locked_at maps to acquired_at
    """

    model_config = ConfigDict(frozen=True)

    locked: bool
    holder_id: str | None = None
    holder_name: str | None = None
    algorithm: str | None = None
    algorithm_type: str | None = None
    execution_id: str | None = None
    locked_at: datetime | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> LockStatus:
        """Create from API response data.

        Handles field name differences between SDK and shared schema:
        - holder_username -> holder_name
        - algorithm_name -> algorithm
        - acquired_at -> locked_at
        """
        # Handle both naming conventions (SDK uses friendlier names)
        holder_name = data.get("holder_name") or data.get("holder_username")
        algorithm = data.get("algorithm") or data.get("algorithm_name")
        locked_at_str = data.get("locked_at") or data.get("acquired_at")

        return cls(
            locked=data.get("locked", False),
            holder_id=data.get("holder_id"),
            holder_name=holder_name,
            algorithm=algorithm,
            algorithm_type=data.get("algorithm_type"),
            execution_id=data.get("execution_id"),
            locked_at=_parse_datetime(locked_at_str) if locked_at_str else None,
        )


class Instance(BaseModel):
    """Running graph instance.

    Matches InstanceResponse schema from graph_olap_schemas.
    """

    model_config = ConfigDict(frozen=True)

    id: int
    snapshot_id: int | None = None  # May be missing in lifecycle responses
    snapshot_name: str | None = None
    owner_username: str | None = None  # May be missing in lifecycle responses
    wrapper_type: str | None = None  # May be missing in lifecycle responses
    name: str | None = None  # May be missing in lifecycle responses
    description: str | None = None
    status: str | None = None  # May be missing in lifecycle responses
    instance_url: str | None = None
    explorer_url: str | None = None
    pod_name: str | None = None
    progress: dict[str, Any] | None = None
    error_code: str | None = None  # STARTUP_FAILED, MAPPING_FETCH_ERROR, etc.
    error_message: str | None = None
    stack_trace: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    started_at: datetime | None = None
    last_activity_at: datetime | None = None
    expires_at: datetime | None = None
    ttl: str | None = None
    inactivity_timeout: str | None = None
    memory_usage_bytes: int | None = None
    disk_usage_bytes: int | None = None
    cpu_cores: int | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> Instance:
        """Create from API response data."""
        return cls(
            id=data["id"],
            snapshot_id=data.get("snapshot_id"),  # Optional in lifecycle responses
            snapshot_name=data.get("snapshot_name"),
            owner_username=data.get("owner_username"),  # Optional in lifecycle responses
            wrapper_type=data.get("wrapper_type"),  # Optional in lifecycle responses
            name=data.get("name"),  # Optional in lifecycle responses
            description=data.get("description"),
            status=data.get("status"),  # Optional in lifecycle responses
            instance_url=data.get("instance_url"),
            explorer_url=data.get("explorer_url"),
            pod_name=data.get("pod_name"),
            progress=data.get("progress"),
            error_code=data.get("error_code"),
            error_message=data.get("error_message"),
            stack_trace=data.get("stack_trace"),
            created_at=_parse_datetime(data["created_at"]) if data.get("created_at") else None,
            updated_at=_parse_datetime(data["updated_at"]) if data.get("updated_at") else None,
            started_at=_parse_datetime(data["started_at"]) if data.get("started_at") else None,
            last_activity_at=(
                _parse_datetime(data["last_activity_at"]) if data.get("last_activity_at") else None
            ),
            expires_at=_parse_datetime(data["expires_at"]) if data.get("expires_at") else None,
            ttl=data.get("ttl"),
            inactivity_timeout=data.get("inactivity_timeout"),
            memory_usage_bytes=data.get("memory_usage_bytes"),
            disk_usage_bytes=data.get("disk_usage_bytes"),
            cpu_cores=data.get("cpu_cores"),
        )

    @property
    def is_running(self) -> bool:
        """Check if instance is running."""
        return self.status == "running"

    @property
    def memory_mb(self) -> float | None:
        """Memory usage in megabytes."""
        if self.memory_usage_bytes is None:
            return None
        return self.memory_usage_bytes / (1024 * 1024)

    @property
    def disk_mb(self) -> float | None:
        """Disk usage in megabytes."""
        if self.disk_usage_bytes is None:
            return None
        return self.disk_usage_bytes / (1024 * 1024)

    def _repr_html_(self) -> str:
        """Rich HTML display for Jupyter notebooks."""
        status_colors = {
            "running": "#28a745",
            "starting": "#007bff",
            "waiting_for_snapshot": "#17a2b8",  # Cyan for waiting state
            "stopping": "#ffc107",
            "failed": "#dc3545",
        }
        status_color = status_colors.get(self.status, "#6c757d")

        memory_str = f"{self.memory_mb:.1f} MB" if self.memory_mb else "N/A"

        url_row = ""
        if self.instance_url:
            url_row = f'<tr><td style="padding: 4px 12px 4px 0; color: #586069;"><strong>URL:</strong></td><td><a href="{self.instance_url}" target="_blank" style="color: #0366d6;">{self.instance_url}</a></td></tr>'

        explorer_row = ""
        if self.explorer_url:
            explorer_row = f'<tr><td style="padding: 4px 12px 4px 0; color: #586069;"><strong>Explorer:</strong></td><td><a href="{self.explorer_url}" target="_blank" style="color: #0366d6;">Open Explorer</a></td></tr>'

        # Display error information if instance failed
        error_section = ""
        if self.status == "failed" and (self.error_code or self.error_message):
            error_code_str = f"<strong>{self.error_code}</strong>" if self.error_code else ""
            error_msg_str = self.error_message or "Unknown error"
            error_section = f"""
            <div style="background: #fef2f2; border: 1px solid #fecaca; border-radius: 4px; padding: 8px; margin-top: 8px;">
                <div style="color: #991b1b; font-weight: 500; font-size: 12px;">{error_code_str}</div>
                <div style="color: #7f1d1d; font-size: 12px; margin-top: 4px;">{error_msg_str}</div>
            </div>
            """

        return f"""
        <div style="border: 1px solid #e1e4e8; padding: 12px; border-radius: 6px; margin: 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <h4 style="margin: 0; color: #24292e;">Instance: {self.name}</h4>
                <span style="background: {status_color}; color: white; padding: 2px 8px; border-radius: 12px; font-size: 12px; font-weight: 500;">{self.status.upper()}</span>
            </div>
            <table style="border-collapse: collapse; font-size: 13px;">
                <tr><td style="padding: 4px 12px 4px 0; color: #586069;"><strong>ID:</strong></td><td>{self.id}</td></tr>
                <tr><td style="padding: 4px 12px 4px 0; color: #586069;"><strong>Snapshot:</strong></td><td>{self.snapshot_name}</td></tr>
                <tr><td style="padding: 4px 12px 4px 0; color: #586069;"><strong>Owner:</strong></td><td>{self.owner_username}</td></tr>
                <tr><td style="padding: 4px 12px 4px 0; color: #586069;"><strong>Memory:</strong></td><td>{memory_str}</td></tr>
                {url_row}
                {explorer_row}
            </table>
            {error_section}
        </div>
        """


def _parse_datetime(value: str) -> datetime:
    """Parse ISO datetime string, handling Z suffix."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


# Re-export shared types for backward compatibility
__all__ = [
    "Instance",
    # SDK types
    "InstanceProgress",
    # From shared schemas (re-exported)
    "InstanceStatus",
    "LockStatus",
]
