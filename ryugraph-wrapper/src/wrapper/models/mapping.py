"""Mapping definition types - re-exports from shared schemas.

This module re-exports shared schema types for backward compatibility.
All types are from graph_olap_schemas - we do NOT extend them here.

See: docs/foundation/architectural.guardrails.md - "Shared Schemas as Single Source of Truth"

For DDL generation and GCS path utilities, use wrapper.utils.ddl module.
"""

# Re-export shared types for backward compatibility
from graph_olap_schemas import (
    EdgeDefinition,
    InstanceMappingResponse,
    NodeDefinition,
    PrimaryKeyDefinition,
    PropertyDefinition,
    RyugraphType,
)

# Alias for backward compatibility - use InstanceMappingResponse for new code
MappingDefinition = InstanceMappingResponse

__all__ = [
    "EdgeDefinition",
    "InstanceMappingResponse",
    # Backward compatibility alias
    "MappingDefinition",
    "NodeDefinition",
    "PrimaryKeyDefinition",
    # From shared schemas
    "PropertyDefinition",
    "RyugraphType",
]
