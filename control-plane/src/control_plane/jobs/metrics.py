"""Prometheus metrics for background jobs.

Tracks background job execution, reconciliation, and lifecycle enforcement.
"""

from prometheus_client import Counter, Gauge, Histogram

# ============================================================================
# General Job Metrics
# ============================================================================

job_execution_total = Counter(
    "background_job_execution_total",
    "Total background job executions",
    ["job_name", "status"],  # status: success, failed
)

job_execution_duration_seconds = Histogram(
    "background_job_execution_duration_seconds",
    "Duration of background job execution",
    ["job_name"],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0],
)

# P0 metrics for testing support
job_last_success_timestamp_seconds = Gauge(
    "background_job_last_success_timestamp_seconds",
    "Unix timestamp of last successful job execution",
    ["job_name"],
)

job_health_status = Gauge(
    "background_job_health_status",
    "Job health status: 1=healthy, 0=unhealthy (3+ consecutive failures)",
    ["job_name"],
)

# ============================================================================
# Reconciliation Job Metrics
# ============================================================================

reconciliation_passes_total = Counter(
    "reconciliation_passes_total",
    "Total reconciliation passes executed",
)

reconciliation_pass_duration_seconds = Histogram(
    "reconciliation_pass_duration_seconds",
    "Duration of reconciliation pass",
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

# Orphaned pod detection
orphaned_pods_detected_total = Counter(
    "orphaned_pods_detected_total",
    "Total orphaned pods detected",
)

orphaned_pods_cleaned_total = Counter(
    "orphaned_pods_cleaned_total",
    "Total orphaned pods successfully cleaned",
)

orphaned_pods_cleanup_failures_total = Counter(
    "orphaned_pods_cleanup_failures_total",
    "Total orphaned pod cleanup failures",
)

# Missing pod detection
missing_pods_detected_total = Counter(
    "missing_pods_detected_total",
    "Total instances with missing pods detected",
)

missing_pods_handled_total = Counter(
    "missing_pods_handled_total",
    "Total instances with missing pods successfully handled",
)

# Status drift detection
status_drift_detected_total = Counter(
    "status_drift_detected_total",
    "Total status drift cases detected",
)

status_drift_fixed_total = Counter(
    "status_drift_fixed_total",
    "Total status drift cases successfully fixed",
)

# Current state gauges
instances_without_pod_name = Gauge(
    "instances_without_pod_name",
    "Number of instances without pod_name tracked",
)

# Saturation metrics (Fourth Golden Signal)
database_connections = Gauge(
    "graph_olap_database_connections",
    "Database connection pool state",
    ["state"],  # available, in_use, total
)

# Export pipeline health
export_queue_depth = Gauge(
    "graph_olap_export_queue_depth",
    "Number of pending exports in queue",
)

orphaned_pods_detected_current = Gauge(
    "orphaned_pods_detected_current",
    "Current number of orphaned pods detected (before cleanup)",
)

# ============================================================================
# Lifecycle Job Metrics
# ============================================================================

lifecycle_passes_total = Counter(
    "lifecycle_passes_total",
    "Total lifecycle enforcement passes executed",
)

lifecycle_pass_duration_seconds = Histogram(
    "lifecycle_pass_duration_seconds",
    "Duration of lifecycle enforcement pass",
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

# TTL expiry
ttl_instances_terminated_total = Counter(
    "ttl_instances_terminated_total",
    "Total instances terminated due to TTL expiry",
)

ttl_snapshots_deleted_total = Counter(
    "ttl_snapshots_deleted_total",
    "Total snapshots deleted due to TTL expiry",
)

ttl_mappings_deleted_total = Counter(
    "ttl_mappings_deleted_total",
    "Total mappings deleted due to TTL expiry",
)

# Inactivity timeout
inactive_instances_terminated_total = Counter(
    "inactive_instances_terminated_total",
    "Total instances terminated due to inactivity timeout",
)

# Lifecycle failures
lifecycle_termination_failures_total = Counter(
    "lifecycle_termination_failures_total",
    "Total lifecycle termination failures",
    ["resource_type"],  # instance, snapshot, mapping
)

# GCS cleanup failures
snapshot_gcs_cleanup_failures_total = Counter(
    "snapshot_gcs_cleanup_failures_total",
    "Total snapshot GCS file cleanup failures",
)

# ============================================================================
# Export Reconciliation Job Metrics
# ============================================================================

export_reconciliation_passes_total = Counter(
    "export_reconciliation_passes_total",
    "Total export reconciliation passes executed",
)

export_reconciliation_pass_duration_seconds = Histogram(
    "export_reconciliation_pass_duration_seconds",
    "Duration of export reconciliation pass",
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0],
)

# Stale claim detection
stale_export_claims_detected_total = Counter(
    "stale_export_claims_detected_total",
    "Total stale export job claims detected",
)

stale_export_claims_reset_total = Counter(
    "stale_export_claims_reset_total",
    "Total stale export job claims successfully reset",
)

# Snapshot finalization
snapshots_ready_to_finalize_total = Counter(
    "snapshots_ready_to_finalize_total",
    "Total snapshots detected ready to finalize",
)

snapshots_finalized_total = Counter(
    "snapshots_finalized_total",
    "Total snapshots successfully finalized",
)

snapshots_finalization_failures_total = Counter(
    "snapshots_finalization_failures_total",
    "Total snapshot finalization failures",
)

# Export queue depth
export_jobs_by_status_total = Gauge(
    "export_jobs_by_status_total",
    "Current number of export jobs by status",
    ["status"],
)

# ============================================================================
# Schema Cache Job Metrics
# ============================================================================

schema_cache_refreshes_total = Counter(
    "schema_cache_refreshes_total",
    "Total schema cache refresh executions",
    ["status"],  # success, failed, skipped
)

schema_cache_refresh_duration_seconds = Histogram(
    "schema_cache_refresh_duration_seconds",
    "Duration of schema cache refresh",
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0],
)

schema_cache_entries_total = Gauge(
    "schema_cache_entries_total",
    "Total number of schema cache entries",
    ["entity_type"],  # catalog, schema, table, column
)

schema_cache_stale_entries_deleted_total = Counter(
    "schema_cache_stale_entries_deleted_total",
    "Total stale schema cache entries deleted",
)

# ============================================================================
# Instance Orchestration Job Metrics
# ============================================================================

instance_orchestration_passes_total = Counter(
    "instance_orchestration_passes_total",
    "Total instance orchestration passes executed",
)

instance_orchestration_pass_duration_seconds = Histogram(
    "instance_orchestration_pass_duration_seconds",
    "Duration of instance orchestration pass",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
)

# Instance transitions
instances_transitioned_to_starting_total = Counter(
    "instances_transitioned_to_starting_total",
    "Total instances transitioned from waiting_for_snapshot to starting",
)

instances_transitioned_to_failed_total = Counter(
    "instances_transitioned_to_failed_total",
    "Total instances transitioned from waiting_for_snapshot to failed",
)

# ============================================================================
# Resource Monitor Job Metrics
# ============================================================================

resource_monitor_passes_total = Counter(
    "resource_monitor_passes_total",
    "Total resource monitor passes executed",
)

resource_monitor_pass_duration_seconds = Histogram(
    "resource_monitor_pass_duration_seconds",
    "Duration of resource monitor pass",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
)

resource_monitor_proactive_resizes_total = Counter(
    "resource_monitor_proactive_resizes_total",
    "Total proactive memory resizes triggered (>80% usage)",
)

resource_monitor_urgent_resizes_total = Counter(
    "resource_monitor_urgent_resizes_total",
    "Total urgent memory resizes triggered (>90% usage)",
)

resource_monitor_failures_total = Counter(
    "resource_monitor_failures_total",
    "Total resource monitor failures",
)
