"""SQLAlchemy Core table definitions.

All tables use portable types that work with both PostgreSQL and SQLite:
- TEXT for strings, timestamps (ISO 8601), durations (ISO 8601), JSON
- INTEGER for auto-incrementing IDs and booleans (0/1)

No ORM models - these are SQLAlchemy Core Table objects for raw SQL execution.
"""

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
    UniqueConstraint,
)

# Metadata container for all tables
metadata = MetaData()

# =============================================================================
# Users
# =============================================================================

users = Table(
    "users",
    metadata,
    Column("username", Text, primary_key=True),
    Column("email", Text, nullable=False, unique=True),
    Column("display_name", Text, nullable=False),
    Column(
        "role",
        Text,
        CheckConstraint("role IN ('analyst', 'admin', 'ops')"),
        nullable=False,
        default="analyst",
    ),  # ADR-104: role stored in DB, not from headers
    Column("role_changed_at", Text, nullable=True),  # ISO 8601
    Column("role_changed_by", Text, nullable=True),  # username who changed role
    Column("created_at", Text, nullable=False),  # ISO 8601
    Column("updated_at", Text, nullable=False),  # ISO 8601
    Column("last_login_at", Text, nullable=True),  # ISO 8601
    Column("is_active", Integer, nullable=False, default=1),  # 0 or 1
    Index("idx_users_email", "email"),
)

# =============================================================================
# Mappings and Versions
# =============================================================================

mappings = Table(
    "mappings",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "owner_username",
        Text,
        ForeignKey("users.username"),
        nullable=False,
    ),
    Column("name", Text, nullable=False),
    Column("description", Text, nullable=True),
    Column("current_version", Integer, nullable=False, default=1),
    Column("created_at", Text, nullable=False),  # ISO 8601
    Column("updated_at", Text, nullable=False),  # ISO 8601
    Column("ttl", Text, nullable=True),  # ISO 8601 duration
    Column("inactivity_timeout", Text, nullable=True),  # ISO 8601 duration
    Index("idx_mappings_owner", "owner_username"),
    Index("idx_mappings_created_at", "created_at"),
    Index("idx_mappings_name", "name"),
)

mapping_versions = Table(
    "mapping_versions",
    metadata,
    Column(
        "mapping_id",
        Integer,
        ForeignKey("mappings.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("version", Integer, primary_key=True),
    Column("change_description", Text, nullable=True),  # NULL for version 1
    Column("node_definitions", Text, nullable=False),  # JSON array
    Column("edge_definitions", Text, nullable=False),  # JSON array
    Column("created_at", Text, nullable=False),  # ISO 8601
    Column(
        "created_by",
        Text,
        ForeignKey("users.username"),
        nullable=False,
    ),
    Index("idx_mapping_versions_created_at", "created_at"),
)

# =============================================================================
# Snapshots
# =============================================================================

snapshots = Table(
    "snapshots",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("mapping_id", Integer, ForeignKey("mappings.id"), nullable=False),
    Column("mapping_version", Integer, nullable=False),
    Column(
        "owner_username",
        Text,
        ForeignKey("users.username"),
        nullable=False,
    ),
    Column("name", Text, nullable=False),
    Column("description", Text, nullable=True),
    Column("gcs_path", Text, nullable=False),
    Column("size_bytes", Integer, nullable=True),
    Column("node_counts", Text, nullable=True),  # JSON object
    Column("edge_counts", Text, nullable=True),  # JSON object
    Column(
        "status",
        Text,
        CheckConstraint("status IN ('pending', 'creating', 'ready', 'failed', 'cancelled')"),
        nullable=False,
    ),
    Column("progress", Text, nullable=True),  # JSON object
    Column("error_message", Text, nullable=True),
    Column("created_at", Text, nullable=False),  # ISO 8601
    Column("updated_at", Text, nullable=False),  # ISO 8601
    Column("ttl", Text, nullable=True),  # ISO 8601 duration
    Column("inactivity_timeout", Text, nullable=True),  # ISO 8601 duration
    Column("last_used_at", Text, nullable=True),  # ISO 8601
    # Composite foreign key to mapping_versions
    ForeignKeyConstraint(
        ["mapping_id", "mapping_version"],
        ["mapping_versions.mapping_id", "mapping_versions.version"],
    ),
    Index("idx_snapshots_mapping_id", "mapping_id"),
    Index("idx_snapshots_owner", "owner_username"),
    Index("idx_snapshots_status", "status"),
    Index("idx_snapshots_created_at", "created_at"),
)

# =============================================================================
# Instances
# =============================================================================

instances = Table(
    "instances",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "snapshot_id",
        Integer,
        ForeignKey("snapshots.id"),
        nullable=False,
    ),
    Column(
        "pending_snapshot_id",
        Integer,
        ForeignKey("snapshots.id"),
        nullable=True,
    ),  # Set when instance is waiting for snapshot to be created
    Column(
        "owner_username",
        Text,
        ForeignKey("users.username"),
        nullable=False,
    ),
    Column("wrapper_type", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("description", Text, nullable=True),
    Column("url_slug", Text, nullable=True, unique=True),  # UUID for external URL routing
    Column("instance_url", Text, nullable=True),
    Column("pod_name", Text, nullable=True),
    Column("pod_ip", Text, nullable=True),
    Column(
        "status",
        Text,
        CheckConstraint(
            "status IN ('waiting_for_snapshot', 'starting', 'running', 'stopping', 'failed')"
        ),
        nullable=False,
    ),
    Column("progress", Text, nullable=True),  # JSON object
    Column("error_message", Text, nullable=True),
    Column(
        "error_code",
        Text,
        CheckConstraint(
            "error_code IS NULL OR error_code IN ("
            "'STARTUP_FAILED', 'MAPPING_FETCH_ERROR', 'SCHEMA_CREATE_ERROR', "
            "'DATA_LOAD_ERROR', 'DATABASE_ERROR', 'OOM_KILLED', 'UNEXPECTED_TERMINATION')"
        ),
        nullable=True,
    ),
    Column("stack_trace", Text, nullable=True),
    Column("created_at", Text, nullable=False),  # ISO 8601
    Column("updated_at", Text, nullable=False),  # ISO 8601
    Column("started_at", Text, nullable=True),  # ISO 8601
    Column("last_activity_at", Text, nullable=True),  # ISO 8601
    Column("ttl", Text, nullable=True),  # ISO 8601 duration
    Column("inactivity_timeout", Text, nullable=True),  # ISO 8601 duration
    Column("memory_usage_bytes", Integer, nullable=True),
    Column("disk_usage_bytes", Integer, nullable=True),
    Column("cpu_cores", Integer, nullable=True, default=2),
    Column("memory_gb", Integer, nullable=True),  # Current memory allocation in GB
    Index("idx_instances_snapshot_id", "snapshot_id"),
    Index("idx_instances_owner", "owner_username"),
    Index("idx_instances_wrapper_type", "wrapper_type"),
    Index("idx_instances_status", "status"),
    Index("idx_instances_created_at", "created_at"),
    Index("idx_instances_url_slug", "url_slug"),
)

# =============================================================================
# Instance Events (Resource Monitoring - Phase 3)
# =============================================================================

instance_events = Table(
    "instance_events",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "instance_id",
        Integer,
        ForeignKey("instances.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "event_type",
        Text,
        CheckConstraint(
            "event_type IN ('memory_upgraded', 'cpu_updated', 'oom_recovered', 'resize_failed')"
        ),
        nullable=False,
    ),
    Column("details", Text, nullable=True),  # JSON with old/new values
    Column("created_at", Text, nullable=False),  # ISO 8601
    Index("idx_instance_events_instance_id", "instance_id"),
    Index("idx_instance_events_type", "event_type"),
    Index("idx_instance_events_created_at", "created_at"),
)

# =============================================================================
# Export Jobs (ADR-025: Database Polling Architecture)
# =============================================================================

export_jobs = Table(
    "export_jobs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "snapshot_id",
        Integer,
        ForeignKey("snapshots.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "job_type",
        Text,
        CheckConstraint("job_type IN ('node', 'edge')"),
        nullable=False,
    ),
    Column("entity_name", Text, nullable=False),
    Column(
        "status",
        Text,
        CheckConstraint("status IN ('pending', 'claimed', 'submitted', 'completed', 'failed')"),
        nullable=False,
        default="pending",
    ),
    # Denormalized job definition (workers don't need separate mapping fetch)
    Column("sql", Text, nullable=True),  # SELECT query to export
    Column("column_names", Text, nullable=True),  # JSON array of column names
    Column("starburst_catalog", Text, nullable=True),  # Catalog name for query
    Column("starburst_role", Text, nullable=True),  # Use case ID for SET ROLE (ADR-102)
    # Claiming state (lease-based ownership)
    Column("claimed_by", Text, nullable=True),  # Worker ID that claimed this job
    Column("claimed_at", Text, nullable=True),  # ISO 8601 when claimed
    # Starburst tracking
    Column("starburst_query_id", Text, nullable=True),
    Column("next_uri", Text, nullable=True),
    # Stateless polling state (persisted in database)
    Column("next_poll_at", Text, nullable=True),  # ISO 8601 when to poll next
    Column("poll_count", Integer, nullable=False, default=0),  # For Fibonacci backoff
    # Output and results
    Column("gcs_path", Text, nullable=False),
    Column("row_count", Integer, nullable=True),
    Column("size_bytes", Integer, nullable=True),
    Column("submitted_at", Text, nullable=True),  # ISO 8601
    Column("completed_at", Text, nullable=True),  # ISO 8601
    Column("error_message", Text, nullable=True),
    Column("created_at", Text, nullable=False),  # ISO 8601
    Column("updated_at", Text, nullable=False),  # ISO 8601
    Index("idx_export_jobs_snapshot_id", "snapshot_id"),
    Index("idx_export_jobs_status", "status"),
    Index("idx_export_jobs_snapshot_status", "snapshot_id", "status"),
    Index("idx_export_jobs_next_poll_at", "next_poll_at"),  # For pollable query
    Index("idx_export_jobs_claimed_by", "claimed_by"),  # For worker lookup
)

# =============================================================================
# Global Configuration
# =============================================================================

global_config = Table(
    "global_config",
    metadata,
    Column("key", Text, primary_key=True),
    Column("value", Text, nullable=False),
    Column("description", Text, nullable=True),
    Column("updated_at", Text, nullable=False),  # ISO 8601
    Column(
        "updated_by",
        Text,
        ForeignKey("users.username"),
        nullable=False,
    ),
)

# =============================================================================
# User Favorites
# =============================================================================

user_favorites = Table(
    "user_favorites",
    metadata,
    Column(
        "username",
        Text,
        ForeignKey("users.username", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "resource_type",
        Text,
        CheckConstraint("resource_type IN ('mapping', 'snapshot', 'instance')"),
        primary_key=True,
    ),
    Column("resource_id", Integer, primary_key=True),
    Column("created_at", Text, nullable=False),  # ISO 8601
    Index("idx_user_favorites_username", "username"),
    Index("idx_user_favorites_resource", "resource_type", "resource_id"),
)

# =============================================================================
# Schema Browser (Allowed Catalogs/Schemas)
# =============================================================================

allowed_catalogs = Table(
    "allowed_catalogs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("catalog_name", Text, nullable=False, unique=True),
    Column("enabled", Integer, nullable=False, default=1),  # 0 or 1
    Column("created_at", Text, nullable=False),  # ISO 8601
    Column("updated_at", Text, nullable=False),  # ISO 8601
)

allowed_schemas = Table(
    "allowed_schemas",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "catalog_id",
        Integer,
        ForeignKey("allowed_catalogs.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("schema_name", Text, nullable=False),
    Column("enabled", Integer, nullable=False, default=1),  # 0 or 1
    Column("created_at", Text, nullable=False),  # ISO 8601
    Column("updated_at", Text, nullable=False),  # ISO 8601
    UniqueConstraint("catalog_id", "schema_name", name="uq_allowed_schemas_catalog_schema"),
)

schema_metadata_cache = Table(
    "schema_metadata_cache",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "schema_id",
        Integer,
        ForeignKey("allowed_schemas.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("table_name", Text, nullable=False),
    Column("columns", Text, nullable=False),  # JSON array
    Column("cached_at", Text, nullable=False),  # ISO 8601
    UniqueConstraint("schema_id", "table_name", name="uq_schema_metadata_cache_schema_table"),
)
