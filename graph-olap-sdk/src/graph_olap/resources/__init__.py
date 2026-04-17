"""Resource classes for Graph OLAP SDK."""

from graph_olap.resources.favorites import FavoriteResource
from graph_olap.resources.health import HealthResource
from graph_olap.resources.instances import InstanceResource
from graph_olap.resources.mappings import MappingResource
from graph_olap.resources.ops import OpsResource
from graph_olap.resources.schema import SchemaResource
from graph_olap.resources.users import UserResource

# =============================================================================
# SNAPSHOT FUNCTIONALITY DISABLED
# Snapshots are now created implicitly when instances are created from mappings.
# =============================================================================
# from graph_olap.resources.snapshots import SnapshotResource

__all__ = [
    "FavoriteResource",
    "HealthResource",
    "InstanceResource",
    "MappingResource",
    "OpsResource",
    "SchemaResource",
    "UserResource",
    # SNAPSHOT FUNCTIONALITY DISABLED
    # "SnapshotResource",
]
