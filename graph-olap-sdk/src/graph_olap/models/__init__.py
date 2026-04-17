"""Pydantic models for Graph OLAP SDK resources.

These models extend the shared graph-olap-schemas with SDK-specific
functionality for API serialization, parsing, and Jupyter display.
"""

from graph_olap_schemas import (
    AlgorithmCategory,
    AlgorithmExecutionResponse,
    AlgorithmInfoResponse,
    AlgorithmListResponse,
    AlgorithmParameterInfo,
    AlgorithmType,
    ExecutionStatus,
    NativeAlgorithmRequest,
    NetworkXAlgorithmRequest,
)

from graph_olap.models.common import (
    AlgorithmExecution,
    Favorite,
    PaginatedList,
    QueryResult,
    Schema,
)
from graph_olap.models.instance import Instance, InstanceProgress, InstanceStatus, LockStatus
from graph_olap.models.mapping import (
    EdgeDefinition,
    EdgeDiff,
    Mapping,
    MappingDiff,
    MappingVersion,
    NodeDefinition,
    NodeDiff,
    PrimaryKeyDefinition,
    RyugraphType,
)
from graph_olap.models.ops import (
    ClusterHealth,
    ClusterInstances,
    ComponentHealth,
    ConcurrencyConfig,
    ExportConfig,
    HealthStatus,
    InstanceLimits,
    LifecycleConfig,
    MaintenanceMode,
    OwnerInstanceCount,
    ResourceLifecycleConfig,
)

# Note: Explicit snapshot creation APIs are deprecated. Snapshots are now
# created implicitly when instances are created via create_from_mapping().
# The Snapshot model is still used internally to represent snapshot data.
from graph_olap.models.snapshot import Snapshot, SnapshotProgress, SnapshotStatus

__all__ = [
    "AlgorithmCategory",
    "AlgorithmExecution",
    "AlgorithmExecutionResponse",
    "AlgorithmInfoResponse",
    "AlgorithmListResponse",
    "AlgorithmParameterInfo",
    # From shared schemas - algorithm types
    "AlgorithmType",
    "ClusterHealth",
    "ClusterInstances",
    "ComponentHealth",
    "ConcurrencyConfig",
    "EdgeDefinition",
    "EdgeDiff",
    "ExecutionStatus",
    "ExportConfig",
    "Favorite",
    "HealthStatus",
    # Instance
    "Instance",
    "InstanceLimits",
    "InstanceProgress",
    "InstanceStatus",
    "LifecycleConfig",
    "LockStatus",
    "MaintenanceMode",
    "Mapping",
    "MappingDiff",
    "MappingVersion",
    "NativeAlgorithmRequest",
    "NetworkXAlgorithmRequest",
    # Mapping
    "NodeDefinition",
    # Mapping Diff
    "NodeDiff",
    "OwnerInstanceCount",
    # Common
    "PaginatedList",
    # From shared schemas - other
    "PrimaryKeyDefinition",
    "QueryResult",
    # Ops
    "ResourceLifecycleConfig",
    "RyugraphType",
    "Schema",
    # Snapshot models (note: explicit snapshot creation APIs are deprecated)
    "Snapshot",
    "SnapshotProgress",
    "SnapshotStatus",
]
