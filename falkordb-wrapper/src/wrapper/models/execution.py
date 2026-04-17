"""Algorithm execution models for tracking async algorithm runs.

These models track the state of long-running algorithm executions
that run in the background with status polling support.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExecutionStatus(str, Enum):
    """Algorithm execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AlgorithmType(str, Enum):
    """Type of algorithm - for FalkorDB, all are native Cypher procedures."""

    NATIVE = "native"  # Native FalkorDB algorithm via CALL algo.xxx()


class AlgorithmCategory(str, Enum):
    """Algorithm category for grouping."""

    CENTRALITY = "centrality"  # PageRank, Betweenness
    COMMUNITY = "community"  # WCC, CDLP
    PATHFINDING = "pathfinding"  # BFS, Shortest Path (sync only)


class AlgorithmExecution(BaseModel):
    """Represents an algorithm execution (in-progress or completed).

    Tracks the full lifecycle of an async algorithm execution including
    start time, completion, results, and any errors.
    """

    model_config = ConfigDict(frozen=True)

    execution_id: str = Field(description="Unique execution identifier")
    algorithm_name: str = Field(description="Name of the algorithm")
    algorithm_type: AlgorithmType = Field(
        default=AlgorithmType.NATIVE,
        description="Type: 'native' for FalkorDB",
    )
    status: ExecutionStatus = Field(description="Current execution status")
    started_at: datetime = Field(description="When execution started")
    completed_at: datetime | None = Field(
        default=None,
        description="When execution completed",
    )

    # User context
    user_id: str = Field(description="User who initiated the execution")
    user_name: str = Field(description="Username who initiated the execution")

    # Algorithm configuration
    node_labels: list[str] | None = Field(
        default=None,
        description="Node labels to include in algorithm",
    )
    relationship_types: list[str] | None = Field(
        default=None,
        description="Relationship types to traverse",
    )
    result_property: str | None = Field(
        default=None,
        description="Property name where results are written",
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Algorithm-specific parameters",
    )
    write_back: bool = Field(
        default=True,
        description="Whether to write results back to node properties",
    )

    # Results
    nodes_updated: int | None = Field(
        default=None,
        description="Number of nodes updated with results",
    )
    duration_ms: int | None = Field(
        default=None,
        description="Execution duration in milliseconds",
    )
    error_message: str | None = Field(
        default=None,
        description="Error message if execution failed",
    )
    result_metadata: dict[str, Any] | None = Field(
        default=None,
        description="Additional algorithm-specific result metadata",
    )

    def is_terminal(self) -> bool:
        """Check if execution is in a terminal state.

        Returns:
            True if completed, failed, or cancelled.
        """
        return self.status in (
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
            ExecutionStatus.CANCELLED,
        )


class AlgorithmInfo(BaseModel):
    """Information about an available algorithm."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Algorithm name")
    display_name: str = Field(description="Human-readable name")
    category: AlgorithmCategory = Field(description="Algorithm category")
    description: str = Field(description="Brief description")
    cypher_procedure: str = Field(description="FalkorDB procedure name")
    result_field: str = Field(description="Field name in YIELD for the result value")
    supports_write_back: bool = Field(
        default=True,
        description="Whether results can be written to node properties",
    )
    default_timeout_ms: int = Field(
        default=300_000,
        description="Default execution timeout in milliseconds",
    )
    parameters: list[AlgorithmParameterInfo] = Field(
        default_factory=list,
        description="Available parameters",
    )


class AlgorithmParameterInfo(BaseModel):
    """Information about an algorithm parameter."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Parameter name")
    type: str = Field(description="Parameter type")
    required: bool = Field(default=False, description="Whether required")
    default: Any = Field(default=None, description="Default value")
    description: str = Field(default="", description="Parameter description")
