"""Algorithm execution models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from graph_olap_schemas import ExecutionStatus
from pydantic import BaseModel, ConfigDict, Field


class AlgorithmExecution(BaseModel):
    """Represents an algorithm execution (in-progress or completed)."""

    model_config = ConfigDict(frozen=True)

    execution_id: str = Field(description="Unique execution identifier")
    algorithm_name: str = Field(description="Name of the algorithm")
    algorithm_type: str = Field(description="Type: 'native' or 'networkx'")
    status: ExecutionStatus = Field(description="Current execution status")
    started_at: datetime = Field(description="When execution started")
    completed_at: datetime | None = Field(default=None, description="When execution completed")
    user_id: str = Field(description="User who initiated the execution")
    user_name: str = Field(description="Username who initiated the execution")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Algorithm parameters")
    result_property: str | None = Field(
        default=None,
        description="Property name where results were written",
    )
    error_message: str | None = Field(default=None, description="Error message if failed")
    node_label: str | None = Field(default=None, description="Target node label for results")
    nodes_updated: int | None = Field(default=None, description="Number of nodes updated")
    duration_ms: int | None = Field(default=None, description="Execution duration in milliseconds")

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

    def to_api_dict(self) -> dict[str, Any]:
        """Convert to API response format.

        Returns:
            Dict for API response.
        """
        result: dict[str, Any] = {
            "execution_id": self.execution_id,
            "algorithm_name": self.algorithm_name,
            "algorithm_type": self.algorithm_type,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "user_id": self.user_id,
            "user_name": self.user_name,
            "parameters": self.parameters,
        }
        if self.completed_at:
            result["completed_at"] = self.completed_at.isoformat()
        if self.result_property:
            result["result_property"] = self.result_property
        if self.error_message:
            result["error_message"] = self.error_message
        if self.node_label:
            result["node_label"] = self.node_label
        if self.nodes_updated is not None:
            result["nodes_updated"] = self.nodes_updated
        if self.duration_ms is not None:
            result["duration_ms"] = self.duration_ms
        return result


class ExecutionProgress(BaseModel):
    """Progress update during algorithm execution."""

    model_config = ConfigDict(frozen=True)

    execution_id: str = Field(description="Execution identifier")
    phase: str = Field(description="Current phase (e.g., 'extracting', 'computing', 'writing')")
    progress_percent: int | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Progress percentage if known",
    )
    message: str | None = Field(default=None, description="Human-readable status message")
