"""Public API routers."""

from control_plane.routers.api.admin import router as admin_router
from control_plane.routers.api.cluster import router as cluster_router
from control_plane.routers.api.config import router as config_router
from control_plane.routers.api.export_jobs import router as export_jobs_router
from control_plane.routers.api.favorites import router as favorites_router
from control_plane.routers.api.instances import router as instances_router
from control_plane.routers.api.mappings import router as mappings_router
from control_plane.routers.api.ops import router as ops_router
from control_plane.routers.api.schema import router as schema_router
from control_plane.routers.api.users import router as users_router
# SNAPSHOT FUNCTIONALITY DISABLED - snapshots are now created implicitly
# from control_plane.routers.api.snapshots import router as snapshots_router

__all__ = [
    "admin_router",
    "cluster_router",
    "config_router",
    "export_jobs_router",
    "favorites_router",
    "instances_router",
    "mappings_router",
    "ops_router",
    "schema_router",
    "users_router",
    # SNAPSHOT FUNCTIONALITY DISABLED
    # "snapshots_router",
]
