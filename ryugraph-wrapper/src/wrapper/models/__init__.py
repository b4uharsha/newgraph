"""Pydantic models for requests, responses, and domain objects.

Shared schemas are imported from the graph-olap-schemas package.
Wrapper-specific models are defined locally.
"""

from __future__ import annotations

from graph_olap_schemas import (
    AlgorithmCategory,
    AlgorithmType,
    ExecutionStatus,
)

from wrapper.models.execution import AlgorithmExecution
from wrapper.models.lock import LockState, lock_info_from_state
from wrapper.models.mapping import (
    EdgeDefinition,
    MappingDefinition,
    NodeDefinition,
    PrimaryKeyDefinition,
    PropertyDefinition,
    RyugraphType,
)
from wrapper.models.requests import (
    AlgorithmRequest,
    NativeAlgorithmRequest,
    QueryRequest,
    SubgraphRequest,
)
from wrapper.models.responses import (
    AlgorithmInfoResponse,
    AlgorithmListResponse,
    AlgorithmParameterInfo,
    AlgorithmResponse,
    EdgeTableSchema,
    ErrorResponse,
    HealthResponse,
    LockInfo,
    LockStatusResponse,
    NodeTableSchema,
    QueryResponse,
    SchemaResponse,
    StatusResponse,
    WrapperLockStatusResponse,
    WrapperSchemaResponse,
)

__all__ = [
    # Algorithm types (from shared schemas)
    "AlgorithmCategory",
    "AlgorithmType",
    "ExecutionStatus",
    # Execution
    "AlgorithmExecution",
    # Algorithm responses (from shared schemas via responses.py)
    "AlgorithmInfoResponse",
    "AlgorithmListResponse",
    "AlgorithmParameterInfo",
    "AlgorithmResponse",
    # Common responses (from shared schemas)
    "ErrorResponse",
    # Requests (from shared schemas via requests.py)
    "AlgorithmRequest",
    "NativeAlgorithmRequest",
    "QueryRequest",
    "SubgraphRequest",
    # Shared wrapper schemas (from graph-olap-schemas via responses.py)
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
    # Lock state (internal model)
    "LockState",
    "lock_info_from_state",
    # Mapping models
    "MappingDefinition",
    "NodeDefinition",
    "EdgeDefinition",
    "PrimaryKeyDefinition",
    "PropertyDefinition",
    "RyugraphType",
]
