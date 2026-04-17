"""
Wrapper API schemas for SDK ↔ Wrapper communication.

Defines shared request/response models for endpoints that both Ryugraph and FalkorDB
wrappers implement. These schemas ensure consistency between SDK requests and wrapper
expectations.

Common endpoints (both wrappers):
- POST /query - Execute Cypher query
- GET /health - Health check (liveness probe)
- GET /ready - Readiness check
- GET /status - Detailed instance status
- GET /schema - Graph schema
- GET /lock - Algorithm lock status

All structures derived from docs/system-design/api/api.wrapper.spec.md.
"""

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

# =============================================================================
# Request Models
# =============================================================================


class QueryRequest(BaseModel):
    """Request body for POST /query endpoint.

    Used by SDK to send Cypher queries to wrapper instances.
    Field name is 'query' (not 'cypher') for consistency across wrappers.
    """

    model_config = ConfigDict(frozen=True)

    query: Annotated[
        str,
        Field(
            min_length=1,
            max_length=100_000,
            description="Cypher query to execute",
            examples=["MATCH (n:Customer) RETURN n.name LIMIT 10"],
        ),
    ]

    parameters: Annotated[
        dict[str, Any],
        Field(
            default_factory=dict,
            description="Query parameters for parameterized queries",
            examples=[{"name": "Alice", "limit": 10}],
        ),
    ]

    timeout_ms: Annotated[
        int | None,
        Field(
            default=None,
            ge=1_000,
            le=1_800_000,  # Max 30 minutes
            description="Query timeout in milliseconds (default: service default)",
            examples=[60000],
        ),
    ]


# =============================================================================
# Response Models
# =============================================================================


class QueryResponse(BaseModel):
    """Response for POST /query endpoint.

    Flat structure (no 'data' wrapper) matching api.wrapper.spec.md.
    """

    model_config = ConfigDict(frozen=True)

    columns: Annotated[
        list[str],
        Field(
            description="Column names in result",
            examples=[["name", "age", "city"]],
        ),
    ]

    column_types: Annotated[
        list[str],
        Field(
            default_factory=list,
            description="Data types for each column (STRING, INT64, DOUBLE, BOOL, DATE, etc.)",
            examples=[["STRING", "INT64", "STRING"]],
        ),
    ]

    rows: Annotated[
        list[list[Any]],
        Field(
            description="Result rows (list of lists)",
            examples=[[["Alice", 32, "London"], ["Bob", 28, "Paris"]]],
        ),
    ]

    row_count: Annotated[
        int,
        Field(
            ge=0,
            description="Number of rows returned",
            examples=[2],
        ),
    ]

    execution_time_ms: Annotated[
        int,
        Field(
            ge=0,
            description="Query execution time in milliseconds",
            examples=[15],
        ),
    ]

    truncated: Annotated[
        bool,
        Field(
            default=False,
            description="Whether results were truncated due to limits",
        ),
    ]


class HealthResponse(BaseModel):
    """Response for GET /health and GET /ready endpoints.

    Used for Kubernetes liveness and readiness probes.
    """

    model_config = ConfigDict(frozen=True)

    status: Annotated[
        str,
        Field(
            default="healthy",
            description="Health status",
            examples=["healthy"],
        ),
    ]

    timestamp: Annotated[
        str,
        Field(
            description="Current timestamp (ISO 8601)",
            examples=["2025-01-15T10:32:00Z"],
        ),
    ]


class LockInfo(BaseModel):
    """Lock state information.

    Embedded in LockStatusResponse and StatusResponse.
    """

    model_config = ConfigDict(frozen=True)

    locked: Annotated[
        bool,
        Field(
            description="Whether instance is locked by an algorithm",
        ),
    ]

    holder_id: Annotated[
        str | None,
        Field(
            default=None,
            description="User ID holding the lock",
            examples=["user-uuid"],
        ),
    ]

    holder_username: Annotated[
        str | None,
        Field(
            default=None,
            description="Username holding the lock",
            examples=["alice.smith"],
        ),
    ]

    algorithm_name: Annotated[
        str | None,
        Field(
            default=None,
            description="Algorithm being executed",
            examples=["pagerank"],
        ),
    ]

    execution_id: Annotated[
        str | None,
        Field(
            default=None,
            description="Execution ID of running algorithm",
            examples=["exec-uuid"],
        ),
    ]

    acquired_at: Annotated[
        str | None,
        Field(
            default=None,
            description="When lock was acquired (ISO 8601)",
            examples=["2025-01-15T14:00:00Z"],
        ),
    ]

    algorithm_type: Annotated[
        str | None,
        Field(
            default=None,
            description="Algorithm type (e.g., 'native', 'networkx', 'cypher')",
            examples=["native", "cypher"],
        ),
    ]


class WrapperLockStatusResponse(BaseModel):
    """Response for GET /lock endpoint on wrapper instances.

    Named 'WrapperLockStatusResponse' to distinguish from api_resources.LockStatusResponse.
    """

    model_config = ConfigDict(frozen=True)

    lock: Annotated[
        LockInfo,
        Field(
            description="Current lock state",
        ),
    ]


class NodeTableSchema(BaseModel):
    """Schema for a node table in the graph."""

    model_config = ConfigDict(frozen=True)

    label: Annotated[
        str,
        Field(
            description="Node label",
            examples=["Customer"],
        ),
    ]

    primary_key: Annotated[
        str,
        Field(
            description="Primary key column name",
            examples=["customer_id"],
        ),
    ]

    primary_key_type: Annotated[
        str,
        Field(
            description="Primary key data type",
            examples=["STRING"],
        ),
    ]

    properties: Annotated[
        dict[str, str],
        Field(
            description="Property name -> type mapping",
            examples=[{"name": "STRING", "age": "INT64", "city": "STRING"}],
        ),
    ]

    node_count: Annotated[
        int,
        Field(
            ge=0,
            description="Number of nodes with this label",
            examples=[1000],
        ),
    ]


class EdgeTableSchema(BaseModel):
    """Schema for an edge table in the graph."""

    model_config = ConfigDict(frozen=True)

    type: Annotated[
        str,
        Field(
            description="Edge/relationship type",
            examples=["PURCHASED"],
        ),
    ]

    from_node: Annotated[
        str,
        Field(
            description="Source node label",
            examples=["Customer"],
        ),
    ]

    to_node: Annotated[
        str,
        Field(
            description="Target node label",
            examples=["Product"],
        ),
    ]

    properties: Annotated[
        dict[str, str],
        Field(
            description="Property name -> type mapping",
            examples=[{"amount": "DOUBLE", "purchase_date": "DATE"}],
        ),
    ]

    edge_count: Annotated[
        int,
        Field(
            ge=0,
            description="Number of edges of this type",
            examples=[2500],
        ),
    ]


class WrapperSchemaResponse(BaseModel):
    """Response for GET /schema endpoint.

    Returns graph schema with node and edge table definitions.
    Named 'WrapperSchemaResponse' to distinguish from api_schema.SchemaResponse
    which is for Starburst schema metadata.
    """

    model_config = ConfigDict(frozen=True)

    node_tables: Annotated[
        list[NodeTableSchema],
        Field(
            description="Node table schemas",
        ),
    ]

    edge_tables: Annotated[
        list[EdgeTableSchema],
        Field(
            description="Edge table schemas",
        ),
    ]

    total_nodes: Annotated[
        int,
        Field(
            ge=0,
            description="Total node count across all tables",
            examples=[1500],
        ),
    ]

    total_edges: Annotated[
        int,
        Field(
            ge=0,
            description="Total edge count across all tables",
            examples=[2500],
        ),
    ]


class StatusResponse(BaseModel):
    """Response for GET /status endpoint.

    Detailed instance status including resource usage.
    Flat structure (no 'data' wrapper) matching api.wrapper.spec.md.
    """

    model_config = ConfigDict(frozen=True)

    status: Annotated[
        str,
        Field(
            description="Overall status: starting, loading, running, stopping, failed",
            examples=["running"],
        ),
    ]

    instance_id: Annotated[
        str,
        Field(
            description="Instance identifier",
            examples=["instance-uuid"],
        ),
    ]

    snapshot_id: Annotated[
        str,
        Field(
            description="Source snapshot identifier",
            examples=["snapshot-123"],
        ),
    ]

    mapping_id: Annotated[
        str,
        Field(
            description="Parent mapping identifier",
            examples=["mapping-456"],
        ),
    ]

    owner_id: Annotated[
        str,
        Field(
            description="Owner user identifier",
            examples=["user-789"],
        ),
    ]

    ready: Annotated[
        bool,
        Field(
            description="Whether instance is ready to accept queries",
        ),
    ]

    started_at: Annotated[
        str,
        Field(
            description="When instance started (ISO 8601)",
            examples=["2025-01-15T10:00:00Z"],
        ),
    ]

    uptime_seconds: Annotated[
        int,
        Field(
            ge=0,
            description="Uptime in seconds",
            examples=[3600],
        ),
    ]

    # Graph statistics
    node_count: Annotated[
        int | None,
        Field(
            default=None,
            ge=0,
            description="Total number of nodes",
            examples=[15000],
        ),
    ]

    edge_count: Annotated[
        int | None,
        Field(
            default=None,
            ge=0,
            description="Total number of edges",
            examples=[50000],
        ),
    ]

    node_tables: Annotated[
        list[str],
        Field(
            default_factory=list,
            description="Node table names",
            examples=[["Customer", "Product"]],
        ),
    ]

    edge_tables: Annotated[
        list[str],
        Field(
            default_factory=list,
            description="Edge table names",
            examples=[["PURCHASED"]],
        ),
    ]

    # Resource usage
    memory_usage_bytes: Annotated[
        int | None,
        Field(
            default=None,
            ge=0,
            description="Current memory usage in bytes",
            examples=[536870912],
        ),
    ]

    disk_usage_bytes: Annotated[
        int | None,
        Field(
            default=None,
            ge=0,
            description="Current disk usage in bytes",
        ),
    ]

    # Lock status
    lock: Annotated[
        LockInfo,
        Field(
            description="Current lock state",
        ),
    ]
