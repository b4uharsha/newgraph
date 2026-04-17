"""Algorithm API schemas - request/response models for graph algorithm execution.

These schemas define the API contract for:
- Native Ryugraph algorithms (PageRank, WCC, Louvain, etc.)
- NetworkX algorithm bridge (500+ algorithms)
- Algorithm introspection endpoints

Used by both ryugraph-wrapper (API server) and graph-olap-sdk (Python client).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# =============================================================================
# Enums
# =============================================================================


class AlgorithmType(StrEnum):
    """Type of algorithm implementation."""

    NATIVE = "native"  # Built into Ryugraph
    NETWORKX = "networkx"  # Via NetworkX bridge


class ExecutionStatus(StrEnum):
    """Algorithm execution status."""

    PENDING = "pending"  # Queued but not started
    RUNNING = "running"  # Currently executing
    COMPLETED = "completed"  # Successfully finished
    FAILED = "failed"  # Execution failed
    CANCELLED = "cancelled"  # Cancelled by user


class AlgorithmCategory(StrEnum):
    """Algorithm category for grouping."""

    CENTRALITY = "centrality"  # PageRank, Betweenness, etc.
    COMMUNITY = "community"  # Louvain, Label Propagation, etc.
    PATHFINDING = "pathfinding"  # Shortest Path, etc.
    SIMILARITY = "similarity"  # Jaccard, Cosine, etc.
    TRAVERSAL = "traversal"  # BFS, DFS, etc.
    CLUSTERING = "clustering"  # K-Core, Triangles, etc.
    LINK_PREDICTION = "link_prediction"  # Common Neighbors, etc.
    OTHER = "other"  # Uncategorized


# =============================================================================
# Request Schemas
# =============================================================================


class NativeAlgorithmRequest(BaseModel):
    """Request body for native Ryugraph algorithm execution.

    Used with POST /algo/{algorithm_name} endpoint.
    """

    model_config = ConfigDict(frozen=True)

    # Target specification
    node_label: str | None = Field(
        default=None,
        description="Node label to run algorithm on (required for node algorithms)",
    )
    edge_type: str | None = Field(
        default=None,
        description="Edge type for relationship-based algorithms",
    )

    # Result configuration
    result_property: str = Field(
        min_length=1,
        max_length=64,
        description="Property name to store results",
    )

    # Algorithm-specific parameters (varies by algorithm)
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Algorithm-specific parameters",
    )


class NetworkXAlgorithmRequest(BaseModel):
    """Request body for NetworkX algorithm execution.

    Used with POST /networkx/{algorithm_name} endpoint.
    """

    model_config = ConfigDict(frozen=True)

    # Graph extraction
    node_label: str | None = Field(
        default=None,
        description="Node label to extract (None = all nodes)",
    )
    edge_type: str | None = Field(
        default=None,
        description="Edge type to extract (None = all edges)",
    )
    subgraph_query: str | None = Field(
        default=None,
        description="Optional Cypher query to select subgraph",
    )

    # Result configuration
    result_property: str = Field(
        min_length=1,
        max_length=64,
        description="Property name to store results on nodes",
    )

    # Algorithm parameters (discovered dynamically)
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Algorithm-specific parameters (see /networkx/algorithms/{name})",
    )

    # Execution options
    timeout_ms: int | None = Field(
        default=None,
        ge=60_000,
        le=3_600_000,
        description="Algorithm timeout in milliseconds (default: 1800000 = 30 min)",
    )


# =============================================================================
# Response Schemas
# =============================================================================


class AlgorithmExecutionResponse(BaseModel):
    """Response for algorithm execution endpoints.

    Returned by POST /algo/{name} and POST /networkx/{name}.

    Duration fields:
    - elapsed_ms: Time since execution started (used while running)
    - duration_ms: Total execution time (set when completed)
    """

    model_config = ConfigDict(frozen=True)

    execution_id: str = Field(description="Unique execution identifier")
    algorithm_name: str = Field(description="Name of the algorithm")
    algorithm_type: AlgorithmType = Field(description="Type: 'native' or 'networkx'")
    status: ExecutionStatus = Field(description="Execution status")
    started_at: str = Field(description="When execution started (ISO 8601)")
    completed_at: str | None = Field(default=None, description="When completed (ISO 8601)")
    result_property: str | None = Field(
        default=None,
        description="Property where results stored",
    )
    node_label: str | None = Field(default=None, description="Target node label")
    nodes_updated: int | None = Field(default=None, ge=0, description="Number of nodes updated")
    elapsed_ms: int | None = Field(
        default=None,
        ge=0,
        description="Elapsed time in milliseconds (available while running)",
    )
    duration_ms: int | None = Field(
        default=None,
        ge=0,
        description="Total execution duration in milliseconds (set when completed)",
    )
    error_message: str | None = Field(default=None, description="Error message if failed")
    result: dict[str, Any] | None = Field(
        default=None,
        description="Algorithm-specific result data (e.g., path for shortest_path)",
    )


class AlgorithmParameterInfo(BaseModel):
    """Information about an algorithm parameter."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Parameter name")
    type: str = Field(description="Parameter type (int, float, str, bool, list)")
    required: bool = Field(description="Whether the parameter is required")
    default: Any = Field(default=None, description="Default value if optional")
    description: str = Field(default="", description="Parameter description")


class AlgorithmInfoResponse(BaseModel):
    """Detailed information about an algorithm.

    Returned by GET /algo/algorithms/{name} and /networkx/algorithms/{name}.

    Unified metadata fields work across all wrapper types:
    - Ryugraph native algorithms
    - NetworkX bridge algorithms
    - FalkorDB Cypher procedure algorithms
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Algorithm name (identifier)")
    display_name: str | None = Field(
        default=None,
        description="Human-readable display name",
    )
    type: AlgorithmType = Field(description="Algorithm type: 'native' or 'networkx'")
    category: AlgorithmCategory | None = Field(default=None, description="Algorithm category")
    description: str = Field(default="", description="Algorithm description")
    long_description: str = Field(default="", description="Detailed description")
    parameters: list[AlgorithmParameterInfo] = Field(
        default_factory=list,
        description="Algorithm parameters",
    )
    returns: str = Field(default="", description="Return type description")
    supports_write_back: bool = Field(
        default=False,
        description="Whether algorithm supports writing results back to graph",
    )
    default_timeout_ms: int | None = Field(
        default=None,
        ge=1000,
        description="Default timeout in milliseconds (None = no default)",
    )


class AlgorithmListResponse(BaseModel):
    """Response for listing available algorithms.

    Returned by GET /algo/algorithms and GET /networkx/algorithms.
    """

    model_config = ConfigDict(frozen=True)

    algorithms: list[AlgorithmInfoResponse] = Field(description="Available algorithms")
    total_count: int = Field(ge=0, description="Total number of algorithms")
