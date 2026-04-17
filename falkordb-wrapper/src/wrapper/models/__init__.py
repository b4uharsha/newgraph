"""Models module for request/response schemas.

Shared schemas are imported from graph-olap-schemas package.
Wrapper-specific models are defined locally.
"""

from wrapper.models.lock import LockState, lock_info_from_state
from wrapper.models.requests import AlgorithmRequest, QueryRequest
from wrapper.models.responses import (
    DataLoadWarning,
    EdgeTableSchema,
    GraphStats,
    HealthResponse,
    LockInfo,
    LockStatusResponse,
    NodeTableSchema,
    QueryResponse,
    ReadyResponse,
    SchemaResponse,
    StatusResponse,
    WrapperLockStatusResponse,
    WrapperSchemaResponse,
)

__all__ = [
    # Requests
    "AlgorithmRequest",
    "QueryRequest",
    # Shared response models (from graph-olap-schemas via responses.py)
    "QueryResponse",
    "HealthResponse",
    "StatusResponse",
    "NodeTableSchema",
    "EdgeTableSchema",
    "WrapperSchemaResponse",
    "WrapperLockStatusResponse",
    "LockInfo",
    # Backwards compatibility aliases
    "SchemaResponse",
    "LockStatusResponse",
    # Local response models
    "ReadyResponse",
    "DataLoadWarning",
    "GraphStats",
    # Lock state (internal model)
    "LockState",
    "lock_info_from_state",
]
