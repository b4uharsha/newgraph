"""Request models for API endpoints.

Shared schemas are imported from graph-olap-schemas package.
Wrapper-specific models are defined locally.
"""

from __future__ import annotations

from typing import Any

from graph_olap_schemas import QueryRequest
from pydantic import BaseModel, Field

# Re-export shared schema
__all__ = ["QueryRequest", "AlgorithmRequest"]


class AlgorithmRequest(BaseModel):
    """Request body for algorithm execution (via Cypher CALL).

    This is FalkorDB-specific; Ryugraph uses different algorithm schemas.
    """

    parameters: dict[str, Any] = Field(
        default_factory=dict, description="Algorithm parameters"
    )
    timeout_ms: int | None = Field(
        default=None,
        description="Algorithm timeout in milliseconds (default: 30 minutes)",
        ge=1000,
        le=1_800_000,
    )
