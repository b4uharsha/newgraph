"""Response models for API endpoints.

Shared schemas are imported from graph-olap-schemas package.
Wrapper-specific models are defined locally.

Aligned with Ryugraph wrapper and API specification for consistent
multi-wrapper architecture (ADR-049).
"""

from __future__ import annotations

from graph_olap_schemas import (
    EdgeTableSchema,
    HealthResponse,
    LockInfo,
    NodeTableSchema,
    QueryResponse,
    StatusResponse,
    WrapperLockStatusResponse,
    WrapperSchemaResponse,
)
from pydantic import BaseModel, ConfigDict, Field

# Re-export shared schemas for backwards compatibility
# Local code can continue importing from wrapper.models.responses
__all__ = [
    # Shared schemas (from graph-olap-schemas)
    "QueryResponse",
    "HealthResponse",
    "StatusResponse",
    "NodeTableSchema",
    "EdgeTableSchema",
    "WrapperSchemaResponse",
    "WrapperLockStatusResponse",
    "LockInfo",
    # Aliases for backwards compatibility
    "SchemaResponse",
    "LockStatusResponse",
    # Local models
    "ReadyResponse",
    "GraphStats",
    "DataLoadWarning",
]

# Backwards compatibility aliases
SchemaResponse = WrapperSchemaResponse
LockStatusResponse = WrapperLockStatusResponse


class ReadyResponse(BaseModel):
    """Response for /ready endpoint (readiness probe).

    Note: For consistency with Ryugraph, we use HealthResponse for /ready.
    This model is kept for backwards compatibility but /ready should return
    HealthResponse.
    """

    model_config = ConfigDict(frozen=True)

    ready: bool = Field(..., description="Whether the database is ready for queries")
    loaded_at: str | None = Field(default=None, description="ISO timestamp when data was loaded")


# Legacy models - kept for backwards compatibility but deprecated
# New code should use the flat models above


class GraphStats(BaseModel):
    """Graph statistics (deprecated - use StatusResponse fields directly)."""

    model_config = ConfigDict(frozen=True)

    node_counts: dict[str, int] = Field(..., description="Node counts by label")
    edge_counts: dict[str, int] = Field(..., description="Edge counts by type")
    total_nodes: int
    total_edges: int


class DataLoadWarning(BaseModel):
    """Warning about data load discrepancy.

    Warnings indicate some data failed to load but the instance is still
    operational and queryable. Users should check these warnings to
    understand any discrepancies in their data.
    """

    model_config = ConfigDict(frozen=True)

    type: str = Field(
        ...,
        description="Warning type (e.g., 'row_count_mismatch')",
    )
    entity: str = Field(
        ...,
        description="Entity name (node label or edge type)",
    )
    entity_type: str = Field(
        ...,
        description="'node' or 'edge'",
    )
    expected: int = Field(
        ...,
        description="Expected row count from source CSV",
    )
    actual: int = Field(
        ...,
        description="Actual count in graph",
    )
    missing: int = Field(
        ...,
        description="Number of rows that failed to load",
    )
    success_rate_percent: float = Field(
        ...,
        description="Percentage of rows loaded successfully",
    )
    severity: str = Field(
        default="warning",
        description="'warning' (instance still ready)",
    )
    message: str = Field(
        ...,
        description="Human-readable description of the issue",
    )
