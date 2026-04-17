"""Response models for API endpoints.

Shared schemas are imported from the graph-olap-schemas package.
Wrapper-specific models are defined locally.
"""

from __future__ import annotations

from graph_olap_schemas import AlgorithmExecutionResponse as AlgorithmResponse
from graph_olap_schemas import (
    AlgorithmInfoResponse,
    AlgorithmListResponse,
    AlgorithmParameterInfo,
    EdgeTableSchema,
    ErrorDetail,
    ErrorResponse,
    HealthResponse,
    LockInfo,
    NodeTableSchema,
    QueryResponse,
    StatusResponse,
    WrapperLockStatusResponse,
    WrapperSchemaResponse,
)

# Re-export shared schemas for backwards compatibility
# Local code can continue importing from wrapper.models.responses
__all__ = [
    # Algorithm responses (from graph-olap-schemas)
    "AlgorithmInfoResponse",
    "AlgorithmListResponse",
    "AlgorithmParameterInfo",
    "AlgorithmResponse",
    # Common responses (from graph-olap-schemas)
    "ErrorDetail",
    "ErrorResponse",
    # Shared wrapper schemas (from graph-olap-schemas)
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
]

# Backwards compatibility aliases
SchemaResponse = WrapperSchemaResponse
LockStatusResponse = WrapperLockStatusResponse


# Algorithm response schemas (AlgorithmResponse, AlgorithmParameterInfo,
# AlgorithmInfoResponse, AlgorithmListResponse) are imported from
# graph-olap-schemas at the top of this file.
