"""Background jobs for lifecycle management and reconciliation.

This package contains all background jobs that run periodically to maintain
platform health and enforce lifecycle policies.

Jobs:
- scheduler: APScheduler setup and management
- reconciliation: Orphan pod cleanup, state drift detection
- lifecycle: TTL and inactivity timeout enforcement
- export_reconciliation: Export worker crash recovery
- schema_cache: Starburst schema metadata refresh
- instance_orchestration: waiting_for_snapshot -> starting transitions
- resource_monitor: Dynamic memory monitoring and proactive resize
"""

from control_plane.jobs.resource_monitor import run_resource_monitor_job
from control_plane.jobs.scheduler import BackgroundJobScheduler

__all__ = ["BackgroundJobScheduler", "run_resource_monitor_job"]
