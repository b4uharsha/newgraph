"""Request body models for API endpoints.

Shared schemas are imported from the graph-olap-schemas package.
Wrapper-specific models are defined locally.
"""

from __future__ import annotations

from typing import Any

from graph_olap_schemas import NativeAlgorithmRequest
from graph_olap_schemas import NetworkXAlgorithmRequest as AlgorithmRequest
from graph_olap_schemas import QueryRequest
from pydantic import BaseModel, ConfigDict, Field

# Re-export shared schemas
__all__ = [
    "AlgorithmRequest",
    "NativeAlgorithmRequest",
    "QueryRequest",
    "ShortestPathRequest",
    "SubgraphRequest",
]


class SubgraphRequest(BaseModel):
    """Request body for subgraph extraction."""

    model_config = ConfigDict(frozen=True)

    query: str = Field(
        min_length=1,
        max_length=100_000,
        description="Cypher query to select nodes/edges for subgraph",
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Query parameters",
    )
    include_properties: bool = Field(
        default=True,
        description="Include node/edge properties in result",
    )


class ShortestPathRequest(BaseModel):
    """Request body for shortest path algorithm."""

    model_config = ConfigDict(frozen=True)

    source_id: str = Field(
        description="ID of the source node",
    )
    target_id: str = Field(
        description="ID of the target node",
    )
    relationship_types: list[str] | None = Field(
        default=None,
        description="Relationship types to traverse (None = all)",
    )
    max_depth: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum path depth",
    )
