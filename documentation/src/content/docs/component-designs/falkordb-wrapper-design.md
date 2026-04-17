---
title: "FalkorDB Wrapper Design"
scope: hsbc
---

# FalkorDB Wrapper Design

## Overview

FastAPI service providing a REST API wrapper around FalkorDBLite, enabling graph database instances with Cypher query execution and native FalkorDB graph algorithms.

## Prerequisites

Documents to read first:
- [requirements.md](--/foundation/requirements.md) - Functional requirements
- [architectural.guardrails.md](--/foundation/architectural.guardrails.md) - Hard constraints
- [ryugraph-wrapper.design.md](-/ryugraph-wrapper.design.md) - Reference wrapper implementation

## Constraints

### Architectural

See [architectural.guardrails.md](--/foundation/architectural.guardrails.md) for the authoritative list. Key sections:
- **Database & Schema** - No direct database access from other components
- **API Design** - Follow REST conventions, OpenAPI schema validation
- **Security** - Internal API key authentication for Control Plane communication

### Component-Specific

**Python Version:**
- MUST use Python 3.12+ (FalkorDBLite 0.6.0+ requirement)

**FalkorDBLite Version:**
- MUST use FalkorDBLite 0.6.0+ (native async API via `AsyncFalkorDB`)

**Memory Management:**
- FalkorDB is **in-memory only** - all graph data MUST fit in RAM
- No disk-based buffer pool (unlike Ryugraph)
- Hard memory limit (OOM will kill the pod)

**Data Loading:**
- Uses UNWIND batch loading (see ADR-053)
- LOAD CSV does NOT work with FalkorDBLite (subprocess isolation prevents file access)
- Parquet → dictionary batches via Polars, passed as query parameters
- ~200k+ rows/sec, 100-200x faster than row-by-row loading

**Algorithm Execution:**
- NO NetworkX support
- Native FalkorDB algorithms invoked via Cypher procedures: `CALL algo.xxx()`
- Results CAN be written back to graph via `CALL {} SET` pattern (unlike earlier assumption)
- Global analytics (PageRank, Betweenness, WCC, CDLP) run async with status polling
- Pathfinding algorithms (BFS, shortestPath) run sync via `/query` endpoint

## Design

### Package Structure

```
falkordb-wrapper/
├── src/wrapper/
│   ├── __init__.py
│   ├── main.py              # FastAPI app entry point
│   ├── config.py            # Pydantic settings
│   ├── dependencies.py      # FastAPI dependency injection
│   ├── exceptions.py        # Exception hierarchy
│   ├── lifespan.py          # Application lifecycle (startup/shutdown)
│   ├── logging.py           # Structlog configuration
│   ├── routers/
│   │   ├── algo.py          # Async algorithm execution endpoints
│   │   ├── health.py        # Health and readiness probes
│   │   ├── lock.py          # Instance lock management
│   │   ├── query.py         # Cypher query execution
│   │   └── schema.py        # Schema introspection
│   ├── services/
│   │   ├── algorithm.py     # AlgorithmService for async execution orchestration
│   │   ├── database.py      # FalkorDBLite connection & data loading
│   │   └── lock.py          # LockService for algorithm concurrency control
│   ├── clients/
│   │   ├── control_plane.py # Control Plane HTTP client
│   │   └── gcs.py           # GCS client for Parquet download
│   ├── models/
│   │   ├── execution.py     # Algorithm execution tracking models
│   │   ├── lock.py          # Lock state models
│   │   ├── requests.py      # Pydantic request models
│   │   └── responses.py     # Pydantic response models
│   └── utils/
│       ├── csv_converter.py # ParquetReader for batch loading (+ legacy CSV conversion)
│       ├── type_mapping.py  # Type conversion utilities
│       └── memory.py        # Memory monitoring utilities
```

**Note:** Following ADR-049, DatabaseService includes data loading methods (no separate data_loader.py). Global analytics algorithms run async via AlgorithmService with lock-based concurrency control. Pathfinding algorithms run sync via `/query`.

### Configuration (config.py)

```python
from pydantic_settings import BaseSettings

class FalkorDBConfig(BaseSettings):
    database_path: Path = Path("/data/db")
    query_timeout_ms: int = 60_000
    algorithm_timeout_ms: int = 1_800_000
```

**Key Differences from Ryugraph:**
- No `buffer_pool_size` (in-memory only)
- No `max_threads` configuration
- Simpler configuration surface

### Database Service

**Architectural Decision: Following Ryugraph Pattern**

Per ADR-049, FalkorDB wrapper follows the same architectural patterns as Ryugraph wrapper to ensure consistency across all database wrappers:

- **No Settings dependency in constructor** - Caller extracts values from Settings and passes explicitly
- **Data loading as DatabaseService method** - Not a separate service class
- **Explicit parameters over optional parameters** - Clear contract, fewer surprises

**FalkorDBLite Integration (v0.6.0+ Native Async API):**

FalkorDBLite 0.6.0 introduced a native async API, eliminating the need for `asyncio.to_thread` wrappers around sync calls.

```python
# FalkorDBLite 0.6.0+ native async import
from redislite.async_falkordb_client import AsyncFalkorDB

class DatabaseService:
    def __init__(
        self,
        database_path: Path,
        graph_name: str,
        query_timeout_ms: int = 60_000,
    ):
        """Initialize with explicit parameters.

        NOTE: Unlike some dependency injection patterns, we do NOT
        accept a Settings object. Caller must extract values from
        settings and pass explicitly. This matches the Ryugraph pattern
        and ensures testability without mocking entire Settings.
        """
        self._database_path = database_path
        self._graph_name = graph_name
        self._query_timeout_ms = query_timeout_ms
        self._db: AsyncFalkorDB | None = None
        self._graph = None

    async def initialize(self):
        """Initialize FalkorDB connection and select graph."""
        # AsyncFalkorDB spawns Redis subprocess, communicates via Unix socket
        self._db = AsyncFalkorDB(str(self._database_path))
        self._graph = self._db.select_graph(self._graph_name)

    async def load_data(
        self,
        gcs_base_path: str,
        mapping: InstanceMappingResponse,
        gcs_client: GCSClient,
        control_plane_client: ControlPlaneClient,
    ) -> None:
        """Load data from GCS Parquet files.

        FalkorDB-specific: Uses UNWIND batch loading (LOAD CSV doesn't work
        with FalkorDBLite due to subprocess isolation).
        Ryugraph equivalent: Uses COPY FROM for bulk loading.

        This method is responsible for:
        - Downloading Parquet files from GCS
        - Loading nodes via UNWIND batches
        - Creating indexes for edge performance
        - Loading edges via UNWIND batches with MATCH
        - Monitoring memory usage (80% available memory threshold)
        - Reporting progress to Control Plane
        """
        # Implementation merges DataLoaderService functionality
        # See packages/falkordb-wrapper/src/wrapper/services/database.py

    async def execute_query(self, query: str, parameters: dict = None):
        """Execute Cypher query using native async API."""
        # Native async - no asyncio.to_thread wrapper needed
        return await self._graph.query(query, params=parameters)

    async def close(self):
        """Close database connection."""
        if self._db is not None:
            await self._db.close()
```

**Key Characteristics:**
- **Native async API** (FalkorDBLite 0.6.0+) - `await graph.query()`, `await graph.labels()`, `await db.close()`
- FalkorDBLite runs as subprocess communicating via Unix sockets
- Embedded deployment model (single instance per pod)
- All data stored in-memory only (no disk persistence; data lost on pod restart)
- **Explicit constructor parameters** (no Settings dependency)
- **Data loading integrated** (not separate service)

### Data Loading Strategy

**UNWIND Batch Loading (ADR-053):**

FalkorDBLite uses UNWIND batch loading instead of LOAD CSV. This is required because FalkorDBLite's Redis subprocess cannot access files created by the parent Python process (subprocess isolation).

```python
class DatabaseService:
    # Batch size for UNWIND loading
    BATCH_SIZE = 5000  # rows per batch

    # Minimum success rates before failing the instance
    MIN_NODE_SUCCESS_RATE = 10.0  # 10% for nodes
    MIN_EDGE_SUCCESS_RATE = 5.0   # 5% for edges

    async def load_data(
        self,
        gcs_base_path: str,
        mapping: InstanceMappingResponse,
        gcs_client: GCSClient,
        control_plane_client: ControlPlaneClient,
    ) -> None:
        """Load all data using UNWIND batch loading."""
        # 1. Load all nodes
        for node_def in mapping.nodes:
            await self._load_nodes_with_batch(node_def, gcs_base_path, gcs_client)

        # 2. Create indexes on primary keys (critical for edge performance)
        await self._create_indexes_for_edges(mapping)

        # 3. Load all edges
        for edge_def in mapping.edges:
            await self._load_edges_with_batch(edge_def, gcs_base_path, gcs_client, mapping.nodes)

    async def _load_nodes_with_batch(self, node_def: NodeDefinition, ...):
        """Load nodes using UNWIND batch loading."""
        # 1. Build UNWIND query from node definition
        query = self._build_unwind_query_for_nodes(node_def)
        # Example: "UNWIND $nodes AS node CREATE (:Person {id: node.id, name: node.name})"

        # 2. Read Parquet in batches and execute
        async for batch, total_rows in ParquetReader.read_batches(parquet_path, BATCH_SIZE):
            await self.execute_query(query, parameters={"nodes": batch})

        # 3. Validate loaded data
        await self._validate_data_load(node_def.label, expected_count, actual_count)

    def _build_unwind_query_for_nodes(self, node_def: NodeDefinition) -> str:
        """Generate UNWIND CREATE query for nodes."""
        all_properties = [node_def.primary_key.name]
        all_properties.extend(prop.name for prop in node_def.properties)
        prop_assignments = ", ".join(f"{p}: node.{p}" for p in all_properties)
        return f"UNWIND $nodes AS node CREATE (:{node_def.label} {{{prop_assignments}}})"

    def _build_unwind_query_for_edges(self, edge_def: EdgeDefinition, ...) -> str:
        """Generate UNWIND MATCH-CREATE query for edges."""
        return f"""
        UNWIND $edges AS edge
        MATCH (src:{source_label} {{{source_pk}: edge.{source_fk}}})
        MATCH (tgt:{target_label} {{{target_pk}: edge.{target_fk}}})
        CREATE (src)-[:{edge_def.label} {{{prop_assignments}}}]->(tgt)
        """
```

**Why Not LOAD CSV?**

FalkorDBLite spawns a Redis subprocess that communicates via Unix sockets. This subprocess:
- Runs with process isolation from the parent Python process
- Cannot access files created by the parent process
- Results in "Error opening CSV URI" for any local file path

UNWIND batch loading bypasses this by passing data as query parameters.

**Key Design Decisions:**

1. **Parquet → Dictionary Batches**
   - Uses Polars `read_parquet()` + `to_dicts()` for efficient conversion
   - Batch size of 5,000 rows balances memory and network overhead
   - Only one batch in memory at a time

2. **Index Creation for Edge Performance**
   - Indexes created AFTER nodes load, BEFORE edges load
   - Without indexes: Edge MATCH is O(N²) complexity
   - With indexes: Edge MATCH is O(log N) complexity

3. **Native Type Preservation**
   - Dictionary values preserve Parquet types (int, float, bool, string)
   - No string parsing needed (unlike LOAD CSV)
   - Polars handles type conversion automatically

4. **Warning-Based Validation**
   - Minor mismatches → WARNING (instance still READY)
   - Catastrophic loss (<10% nodes, <5% edges) → FAIL instance
   - Warnings exposed via `/status` endpoint `data_load_warnings[]`

**Performance:**
| Operation | Row-by-Row | UNWIND Batch | Improvement |
|-----------|------------|--------------|-------------|
| Node loading | ~1,000 rows/sec | ~100,000-200,000 rows/sec | 100-200x |
| Edge loading | ~500 rows/sec | ~50,000-100,000 rows/sec | 100-200x |
| 1M nodes | 16+ minutes | 5-10 seconds | 100-200x |

**Trade-offs:**
- ✓ Works with FalkorDBLite (bypasses subprocess isolation)
- ✓ 100-200x faster than row-by-row loading
- ✓ No temporary files needed
- ✓ Native type preservation (no string parsing)
- ✓ Memory controlled via batch_size parameter
- ✗ Batch size tuning may be needed for very large rows

### Algorithm Execution

FalkorDB algorithms fall into two categories with different execution patterns:

**Category 1: Pathfinding Algorithms (Sync)**
- `algo.BFS()` - Breadth-first search
- `algo.shortestPath()` - Shortest path

These are fast, targeted queries executed via `/query` endpoint:
```cypher
MATCH path = algo.shortestPath((a:Person {id: 1}), (b:Person {id: 2}))
RETURN path
```

**Category 2: Global Analytics Algorithms (Async)**
- PageRank - Centrality scores based on incoming links
- Betweenness Centrality - Bridge node identification
- WCC - Weakly connected components
- CDLP - Community detection via label propagation

These run O(V*E) or worse, requiring async execution with status polling.

**AlgorithmService Architecture:**

```python
class AlgorithmService:
    """Orchestrates async graph algorithm execution.

    Lifecycle:
    1. Lock acquisition (prevents concurrent algorithm runs)
    2. Cypher query construction with optional writeback
    3. Background execution with timeout
    4. Status tracking and history
    5. Lock release
    """

    async def execute(
        self,
        user_id: str,
        user_name: str,
        algorithm_name: str,
        result_property: str,
        node_labels: list[str] | None = None,
        relationship_types: list[str] | None = None,
        write_back: bool = True,
        timeout_ms: int | None = None,
    ) -> AlgorithmExecution:
        """Start async algorithm execution.

        Acquires lock, starts background task, returns immediately.
        Use get_execution() to poll status.
        """
        # Acquire lock (raises ResourceLockedError if locked)
        execution_id = await self._lock_service.acquire_or_raise(...)

        # Start background task
        asyncio.create_task(self._run_algorithm_background(...))

        return execution  # Returns immediately with execution_id
```

**Property Writeback Support:**

FalkorDB CAN write algorithm results back to node properties using the `CALL {} SET` subquery pattern:

```cypher
CALL {
  CALL pagerank.stream(null, null)
  YIELD node, score
  SET node.pagerank = score
  RETURN count(*) AS updated
}
RETURN updated
```

This enables the same "compute once, query many times" pattern as Ryugraph:
1. Run PageRank → writes `pagerank` property to all nodes
2. Query: `MATCH (n) WHERE n.pagerank > 0.5 RETURN n`

**Execution State Model:**

```python
class ExecutionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class AlgorithmExecution(BaseModel):
    execution_id: str
    algorithm_name: str
    status: ExecutionStatus
    started_at: datetime
    completed_at: datetime | None
    user_id: str
    result_property: str
    write_back: bool
    nodes_updated: int | None
    duration_ms: int | None
    error_message: str | None
```

### API Routers

**Query Router (`/query`):**
```python
@router.post("/query")
async def execute_query(request: QueryRequest):
    """Execute Cypher query (sync).

    Use for pathfinding algorithms and general queries.
    """
    result = await db_service.execute_query(request.query)
    return QueryResponse(result=result)
```

**Algorithm Router (`/algo`):**

Provides async execution for long-running global analytics:

```python
@router.post("/{algorithm_name}")
async def execute_algorithm(
    algorithm_name: str,
    request: AlgorithmExecuteRequest,
) -> AlgorithmExecutionResponse:
    """Start async algorithm execution.

    Returns immediately with execution_id for polling.
    Supported: pagerank, betweenness, wcc, cdlp
    """
    execution = await algorithm_service.execute(
        algorithm_name=algorithm_name,
        result_property=request.result_property,
        write_back=request.write_back,
        ...
    )
    return AlgorithmExecutionResponse(
        execution_id=execution.execution_id,
        status=execution.status.value,
        ...
    )

@router.get("/status/{execution_id}")
async def get_execution_status(execution_id: str):
    """Poll execution status.

    Terminal states: completed, failed, cancelled.
    """
    execution = algorithm_service.get_execution(execution_id)
    return AlgorithmExecutionResponse(...)

@router.get("/executions")
async def list_executions(limit: int = 20, status_filter: str = None):
    """List recent algorithm executions."""

@router.get("/algorithms")
async def list_available_algorithms():
    """List available algorithms with parameters."""

@router.get("/algorithms/{algorithm_name}")
async def get_algorithm_info(algorithm_name: str):
    """Get detailed algorithm information."""

@router.delete("/executions/{execution_id}")
async def cancel_execution(execution_id: str):
    """Cancel a running execution."""
```

**Lock Router (`/lock`):**

The wrapper exposes **read-only** lock introspection only. There is no
client-facing `/lock/acquire` or `/lock/release` endpoint — locking is
implicit and is managed internally by `AlgorithmService` when an algorithm
starts and stops. Callers poll `GET /lock` to see the current holder while an
algorithm is running.

```python
@router.get("/lock")
async def get_lock_status():
    """Get current lock state.

    The instance uses implicit locking: locks are acquired automatically
    when an algorithm starts via POST /algo/{name} and released automatically
    when it completes (success, failure, or cancellation). There is no
    explicit acquire/release API.
    """
```

Internally, `AlgorithmService.execute()` calls
`LockService.acquire_or_raise()` before dispatching the background task, and
the finally-clause in the background task calls `LockService.release()` with
the execution ID that was issued at acquisition time. The same pattern is
used by the Ryugraph wrapper.

### Lifecycle

**Startup Sequence:**
1. Load configuration
2. Initialize FalkorDBLite connection
3. Fetch mapping definition from Control Plane
4. Create graph schema (nodes and edges)
5. Download Parquet files from GCS
6. Load data via UNWIND batches (nodes → indexes → edges)
7. Report status to Control Plane
8. Mark as ready

**Shutdown Sequence:**
1. Stop accepting new requests
2. Wait for in-flight requests to complete (30s timeout)
3. Close FalkorDBLite connection
4. Report shutdown to Control Plane

## API / Interface

### Public API (Consumed by SDK)

**Query & Schema:**
- `POST /query` - Execute Cypher query (sync)
- `GET /schema` - Get graph schema

**Algorithm Execution (Async):**
- `POST /algo/{algorithm_name}` - Start async algorithm execution
- `GET /algo/status/{execution_id}` - Poll execution status
- `GET /algo/executions` - List recent executions
- `GET /algo/algorithms` - List available algorithms
- `GET /algo/algorithms/{name}` - Get algorithm details
- `DELETE /algo/executions/{execution_id}` - Cancel running execution

**Lock Management (read-only):**
- `GET /lock` - Get current lock status (implicit locking; see Lock Router section)

**Health:**
- `GET /health` - Health check (liveness)
- `GET /ready` - Readiness check
- `GET /status` - Detailed status with data load warnings

### Internal API (Consumed by Control Plane)

- Status reporting: Wrapper → Control Plane
- Progress updates during data loading
- Metrics reporting (memory usage)

## Error Handling

**In-Memory Limit Errors:**
- Graph size exceeds available RAM → `OOM_KILLED` error
- Monitor memory usage during data loading
- Fail early if size estimate exceeds limit

**Algorithm Execution Errors:**
- Syntax errors in Cypher procedure calls
- Timeout errors (30-minute limit)
- Lock contention (only one algorithm at a time)

**Data Loading Errors:**
- GCS download failures (retry with exponential backoff)
- Parquet parsing errors (fail entire load)
- Schema validation errors

## Comparison with Ryugraph Wrapper

| Feature | Ryugraph Wrapper | FalkorDB Wrapper |
|---------|-----------------|------------------|
| **Base Technology** | KuzuDB (C++) | FalkorDBLite (subprocess) |
| **Python Version** | 3.11+ | 3.12+ |
| **Deployment** | Embedded | Embedded (subprocess) |
| **Memory Model** | Buffer pool + disk | In-memory only |
| **Data Loading** | Bulk `COPY FROM` | UNWIND batch (bulk) |
| **Load Speed** | Fast (parallel) | Fast (100-200k rows/sec) |
| **NetworkX** | Yes | No |
| **Algorithm Invocation** | REST API `/algo/` | REST API `/algo/` (async) |
| **Algorithm Results** | Property writeback | Property writeback via `CALL {} SET` |
| **Algorithm API Pattern** | Async with status polling | Async with status polling |
| **Memory Requirement** | 4-8Gi | 6-12Gi |
| **Disk Overflow** | Yes | No |

### Cloud-Optimized Resources (ADR-068)

**Canonical shipped values** (from `charts/falkordb-wrapper/values.yaml` — the
chart is what actually gets applied by `make deploy`):

| Resource | Request | Limit |
|----------|---------|-------|
| memory   | `6Gi`   | `12Gi` |
| cpu      | `2`     | `4`   |

**Reference:** ADR-068: Wrapper Resource Optimization

ADR-068 proposed a ~50% reduction (3Gi request / 6Gi limit) based on usage
profiling. That reduction has not yet been applied to the shipped chart; the
chart in `charts/falkordb-wrapper/values.yaml` still carries the pre-ADR-068
request/limit of 6Gi/12Gi, and per the "chart is canonical" rule the chart
values are the ones that take effect in GKE London. Any future reduction
must be applied to the chart, not just to this design document, or it will
silently not ship.

FalkorDB retains higher memory than Ryugraph due to its in-memory-only
architecture (no disk overflow).

## Open Questions

- **Memory Estimation:** How to accurately estimate graph memory usage before loading?

## References

- ADR-049: Multi-Wrapper Pluggable Architecture
- ADR-053: FalkorDB LOAD CSV Optimization
- ADR-068: Wrapper Resource Optimization

---

**Last Updated:** 2026-01-15
**Status:** Complete (UNWIND batch loading + async algorithm execution + FalkorDBLite 0.6.0 native async API)
