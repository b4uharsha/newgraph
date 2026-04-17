"""
Domain models representing business entities.

These dataclasses are used internally by the control plane for database operations.
Field names match the authoritative documentation in docs/foundation/requirements.md.

For API validation and serialization, use the shared graph_olap_schemas package.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from graph_olap_schemas import (
    ExportJobStatus,
    InstanceErrorCode,
    InstanceStatus,
    SnapshotStatus,
    WrapperType,
)


class UserRole(str, Enum):
    """User roles with different permission levels."""

    ANALYST = "analyst"
    ADMIN = "admin"
    OPS = "ops"


@dataclass
class User:
    """User account stored in database.

    Role is stored in the database (ADR-104). The auth middleware reads
    the role from the DB record, not from request headers or JWT claims.
    """

    username: str
    email: str
    display_name: str
    role: UserRole = UserRole.ANALYST  # Default role for new users (ADR-104)
    role_changed_at: datetime | None = None
    role_changed_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_login_at: datetime | None = None
    is_active: bool = True


@dataclass
class RequestUser:
    """User context for a single request.

    Role comes from the database via auth middleware lookup (ADR-104).
    use_case_id comes from X-Use-Case-Id header (ADR-102).
    This is what gets passed to route handlers and services.
    """

    username: str
    role: UserRole  # From database (ADR-104)
    email: str
    display_name: str
    is_active: bool = True
    use_case_id: str | None = None  # From X-Use-Case-Id header (ADR-102)


@dataclass
class PropertyDefinition:
    """
    Property definition for nodes or edges.

    From requirements.md: {"name": "city", "type": "STRING"}
    """

    name: str
    type: str  # RyugraphType value

    def to_dict(self) -> dict[str, str]:
        """Convert to dictionary for JSON serialization."""
        return {"name": self.name, "type": self.type}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PropertyDefinition":
        """Create from dictionary."""
        return cls(name=data["name"], type=data["type"])


@dataclass
class PrimaryKeyDefinition:
    """
    Primary key definition for nodes.

    From requirements.md: "primary_key": {"name": "customer_id", "type": "STRING"}
    """

    name: str
    type: str  # RyugraphType value

    def to_dict(self) -> dict[str, str]:
        """Convert to dictionary for JSON serialization."""
        return {"name": self.name, "type": self.type}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PrimaryKeyDefinition":
        """Create from dictionary."""
        return cls(name=data["name"], type=data["type"])


@dataclass
class NodeDefinition:
    """
    Node definition in a mapping.

    From requirements.md:
    {
      "label": "Customer",
      "sql": "SELECT customer_id, name, city FROM analytics.customers",
      "primary_key": {"name": "customer_id", "type": "STRING"},
      "properties": [
        {"name": "name", "type": "STRING"},
        {"name": "city", "type": "STRING"}
      ]
    }
    """

    label: str
    sql: str
    primary_key: PrimaryKeyDefinition
    properties: list[PropertyDefinition] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "label": self.label,
            "sql": self.sql,
            "primary_key": self.primary_key.to_dict(),
            "properties": [p.to_dict() for p in self.properties],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NodeDefinition":
        """Create from dictionary."""
        return cls(
            label=data["label"],
            sql=data["sql"],
            primary_key=PrimaryKeyDefinition.from_dict(data["primary_key"]),
            properties=[PropertyDefinition.from_dict(p) for p in data.get("properties", [])],
        )


@dataclass
class EdgeDefinition:
    """
    Edge definition in a mapping.

    From requirements.md:
    {
      "type": "PURCHASED",
      "from_node": "Customer",
      "to_node": "Product",
      "sql": "SELECT customer_id, product_id, amount, purchase_date FROM analytics.transactions",
      "from_key": "customer_id",
      "to_key": "product_id",
      "properties": [
        {"name": "amount", "type": "DOUBLE"},
        {"name": "purchase_date", "type": "DATE"}
      ]
    }
    """

    type: str
    from_node: str
    to_node: str
    sql: str
    from_key: str
    to_key: str
    properties: list[PropertyDefinition] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "type": self.type,
            "from_node": self.from_node,
            "to_node": self.to_node,
            "sql": self.sql,
            "from_key": self.from_key,
            "to_key": self.to_key,
            "properties": [p.to_dict() for p in self.properties],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EdgeDefinition":
        """Create from dictionary."""
        return cls(
            type=data["type"],
            from_node=data["from_node"],
            to_node=data["to_node"],
            sql=data["sql"],
            from_key=data["from_key"],
            to_key=data["to_key"],
            properties=[PropertyDefinition.from_dict(p) for p in data.get("properties", [])],
        )


@dataclass
class MappingVersion:
    """Immutable version of a mapping."""

    mapping_id: int
    version: int
    node_definitions: list[NodeDefinition]
    edge_definitions: list[EdgeDefinition]
    change_description: str | None
    created_at: datetime
    created_by: str


@dataclass
class Mapping:
    """Graph mapping definition."""

    id: int
    owner_username: str
    name: str
    description: str | None
    current_version: int
    created_at: datetime | None = None
    updated_at: datetime | None = None
    ttl: str | None = None
    inactivity_timeout: str | None = None
    # Current version details (loaded with mapping)
    node_definitions: list[NodeDefinition] = field(default_factory=list)
    edge_definitions: list[EdgeDefinition] = field(default_factory=list)
    change_description: str | None = None
    version_created_at: datetime | None = None
    version_created_by: str | None = None


@dataclass
class Snapshot:
    """Data snapshot from a mapping export."""

    id: int
    mapping_id: int
    mapping_version: int
    owner_username: str
    name: str
    description: str | None
    gcs_path: str
    status: SnapshotStatus
    size_bytes: int | None = None
    node_counts: dict[str, int] | None = None
    edge_counts: dict[str, int] | None = None
    progress: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    ttl: str | None = None
    inactivity_timeout: str | None = None
    last_used_at: datetime | None = None


@dataclass
class Instance:
    """Running graph instance."""

    id: int
    snapshot_id: int
    owner_username: str
    wrapper_type: WrapperType
    name: str
    description: str | None
    status: InstanceStatus
    pending_snapshot_id: int | None = None  # Set when instance is waiting for snapshot
    url_slug: str | None = None  # UUID for external URL routing (e.g., /wrapper-{uuid})
    instance_url: str | None = None
    pod_name: str | None = None
    pod_ip: str | None = None
    progress: dict[str, Any] | None = None
    error_message: str | None = None
    error_code: InstanceErrorCode | None = None
    stack_trace: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    started_at: datetime | None = None
    last_activity_at: datetime | None = None
    ttl: str | None = None
    inactivity_timeout: str | None = None
    memory_usage_bytes: int | None = None
    disk_usage_bytes: int | None = None
    cpu_cores: int | None = None
    memory_gb: int | None = None  # Current memory allocation in GB (2-32)

    @property
    def expires_at(self) -> datetime | None:
        """Calculate expiration timestamp from created_at + ttl.

        Returns None if created_at or ttl is not set.
        """
        if not self.created_at or not self.ttl:
            return None

        from control_plane.jobs.lifecycle import _parse_iso8601_duration

        ttl_delta = _parse_iso8601_duration(self.ttl)
        if not ttl_delta:
            return None

        return self.created_at + ttl_delta


@dataclass
class ExportJob:
    """Individual export job for a node/edge type (ADR-025).

    Contains all information needed to execute and track the export,
    including denormalized SQL and stateless polling state.

    Status flow:
        pending → claimed → submitted → completed
                                      → failed
    """

    id: int
    snapshot_id: int
    job_type: str  # 'node' or 'edge'
    entity_name: str
    status: ExportJobStatus
    # Denormalized job definition (workers don't need separate mapping fetch)
    sql: str | None = None
    column_names: list[str] | None = None
    starburst_catalog: str | None = None
    starburst_role: str | None = None  # Use case ID for SET ROLE (ADR-102)
    # Claiming state (lease-based ownership)
    claimed_by: str | None = None
    claimed_at: datetime | None = None
    # Starburst tracking
    starburst_query_id: str | None = None
    next_uri: str | None = None
    # Stateless polling state
    next_poll_at: datetime | None = None
    poll_count: int = 0
    # Output and results
    gcs_path: str = ""
    row_count: int | None = None
    size_bytes: int | None = None
    submitted_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
