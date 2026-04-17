---
title: "Ryugraph Wrapper Services Design"
scope: hsbc
---

# Ryugraph Wrapper Services Design

Service layer implementation for the Ryugraph Wrapper including database management, lock handling, and algorithm execution.

## Prerequisites

- [ryugraph-wrapper.design.md](-/ryugraph-wrapper.design.md) - Core wrapper architecture, project structure, lifecycle
- [ryugraph-networkx.reference.md](--/reference/ryugraph-networkx.reference.md) - Ryugraph/NetworkX API reference
- [ryugraph-performance.reference.md](--/reference/ryugraph-performance.reference.md) - Threading, buffer pool, I/O characteristics

## Related Components

- [control-plane.design.md](-/control-plane.design.md) - Receives status updates from wrapper
- [jupyter-sdk.algorithms.design.md](-/jupyter-sdk.algorithms.design.md) - Client-side algorithm execution

---

## Database Service

### Ryugraph Management

```python
# services/database.py
import ryugraph
from concurrent.futures import ThreadPoolExecutor
import asyncio

class DatabaseService:
    def __init__(
        self,
        database_path: str,
        buffer_pool_size: int = 2_147_483_648,  # 2GB - see ryugraph-performance.reference.md
        max_threads: int = 16,  # 4x CPU for I/O-bound GCS reads - see ryugraph-performance.reference.md
    ):
        self.database_path = database_path
        self.buffer_pool_size = buffer_pool_size
        self.max_threads = max_threads

        self._db: ryugraph.Database | None = None
        self._executor = ThreadPoolExecutor(max_workers=max_threads)
        self._loaded_at: datetime | None = None

    async def initialize(self) -> None:
        """Initialize the Ryugraph database."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self._executor, self._init_db)

    def _init_db(self) -> None:
        """Blocking database initialization."""
        self._db = ryugraph.Database(
            database_path=self.database_path,
            buffer_pool_size=self.buffer_pool_size,
            max_num_threads=self.max_threads,
            compression=True,
            lazy_init=False,
            read_only=False,
        )
        self._connection = ryugraph.Connection(self._db)

        # Load algo extension. The binary is baked into the wrapper image at build
        # time at /root/.ryu/extension/25.9.0/linux_amd64/algo/, so LOAD finds it
        # locally with no network call. Required for native algorithms
        # (page_rank, wcc, scc, louvain, kcore). The 25.9.0 path segment is the
        # Ryugraph *native library* build version, NOT the Python wheel version
        # (which resolves to 25.9.2 from PyPI). See ADR-138 for the full gotcha.
        self._connection.execute("LOAD algo")

    def get_connection(self) -> ryugraph.Connection:
        """Get a new connection for query execution."""
        if self._db is None:
            raise RuntimeError("Database not initialized")
        return ryugraph.Connection(self._db, num_threads=self.max_threads)

    async def create_schema(
        self,
        node_definitions: list[NodeDefinition],
        edge_definitions: list[EdgeDefinition],
    ) -> None:
        """Create graph schema from mapping definitions."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            self._executor,
            self._create_schema_sync,
            node_definitions,
            edge_definitions,
        )

    def _create_schema_sync(
        self,
        node_definitions: list[NodeDefinition],
        edge_definitions: list[EdgeDefinition],
    ) -> None:
        """Blocking schema creation."""
        conn = self.get_connection()

        # Create node tables
        for node_def in node_definitions:
            props = [f"{node_def.primary_key.name} {node_def.primary_key.type} PRIMARY KEY"]
            props.extend(f"{p.name} {p.type}" for p in node_def.properties)
            cypher = f"CREATE NODE TABLE {node_def.label}({', '.join(props)});"
            conn.execute(cypher)
            logger.info("Created node table", label=node_def.label)

        # Create relationship tables
        for edge_def in edge_definitions:
            props = [f"FROM {edge_def.from_node} TO {edge_def.to_node}"]
            props.extend(f"{p.name} {p.type}" for p in edge_def.properties)
            cypher = f"CREATE REL TABLE {edge_def.type}({', '.join(props)});"
            conn.execute(cypher)
            logger.info("Created rel table", type=edge_def.type)

    async def load_data(
        self,
        gcs_path: str,
        node_definitions: list[NodeDefinition],
        edge_definitions: list[EdgeDefinition],
        progress_callback: Callable | None = None,
    ) -> None:
        """Load data from GCS Parquet files.

        Always downloads files via the Python ``google-cloud-storage`` client and
        then ``COPY``s them into Ryugraph from local paths. The client handles GKE
        Workload Identity, service account keys, and ``STORAGE_EMULATOR_HOST``
        (for fake-gcs-server in E2E) transparently, so there is a single load
        path for production, local dev, and E2E.

        Ryugraph's ``httpfs`` extension also supports direct ``gs://`` reading,
        but only via S3-interoperability mode with static HMAC credentials.
        GKE Workload Identity cannot supply those credentials, so the
        httpfs-direct path was never actually deployed. See ADR-031 (the
        original dual-mode proposal, now partially superseded) and ADR-138
        for the full history.
        """
        loop = asyncio.get_event_loop()
        conn = self.get_connection()

        await self._load_data_via_download(
            gcs_path, node_definitions, edge_definitions, progress_callback
        )

        self._loaded_at = datetime.utcnow()

    async def _load_data_via_download(
        self,
        gcs_path: str,
        node_definitions: list[NodeDefinition],
        edge_definitions: list[EdgeDefinition],
        progress_callback: Callable | None = None,
    ) -> None:
        """Local/E2E mode: Download from GCS emulator, then load locally.

        The Google Cloud Storage Python library supports STORAGE_EMULATOR_HOST,
        so we can download files from fake-gcs-server, then load them locally.
        Ryugraph still parallelizes reading within the local Parquet files.
        """
        import tempfile
        from pathlib import Path
        from google.cloud import storage

        loop = asyncio.get_event_loop()
        conn = self.get_connection()

        # Parse GCS path: gs://bucket/prefix/...
        path_parts = gcs_path.replace("gs://", "").split("/", 1)
        bucket_name = path_parts[0]
        base_prefix = path_parts[1].rstrip("/") if len(path_parts) > 1 else ""

        # GCS client uses STORAGE_EMULATOR_HOST automatically
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Load nodes
            for node_def in node_definitions:
                if progress_callback:
                    await progress_callback(node_def.label, "in_progress", None)

                gcs_prefix = f"{base_prefix}/nodes/{node_def.label}"
                local_dir = temp_path / "nodes" / node_def.label
                local_dir.mkdir(parents=True, exist_ok=True)

                # Download all files (filter out directories and empty files)
                blobs = list(bucket.list_blobs(prefix=f"{gcs_prefix}/"))
                parquet_blobs = [b for b in blobs if not b.name.endswith("/") and b.size > 0]

                for blob in parquet_blobs:
                    local_file = local_dir / Path(blob.name).name
                    blob.download_to_filename(str(local_file))

                # Load from local files
                await loop.run_in_executor(
                    self._executor,
                    lambda: conn.execute(f"COPY {node_def.label} FROM '{local_dir}/*';"),
                )

                result = conn.execute(f"MATCH (n:{node_def.label}) RETURN count(n);")
                row_count = result.get_next()[0]

                if progress_callback:
                    await progress_callback(node_def.label, "completed", row_count)

                logger.info("Loaded node table (via download)",
                           label=node_def.label,
                           rows=row_count)

            # Load edges
            for edge_def in edge_definitions:
                if progress_callback:
                    await progress_callback(edge_def.type, "in_progress", None)

                gcs_prefix = f"{base_prefix}/edges/{edge_def.type}"
                local_dir = temp_path / "edges" / edge_def.type
                local_dir.mkdir(parents=True, exist_ok=True)

                blobs = list(bucket.list_blobs(prefix=f"{gcs_prefix}/"))
                parquet_blobs = [b for b in blobs if not b.name.endswith("/") and b.size > 0]

                for blob in parquet_blobs:
                    local_file = local_dir / Path(blob.name).name
                    blob.download_to_filename(str(local_file))

                await loop.run_in_executor(
                    self._executor,
                    lambda: conn.execute(f"COPY {edge_def.type} FROM '{local_dir}/*';"),
                )

                result = conn.execute(
                    f"MATCH (:{edge_def.from_node})-[r:{edge_def.type}]->(:{edge_def.to_node}) RETURN count(r);"
                )
                row_count = result.get_next()[0]

                if progress_callback:
                    await progress_callback(edge_def.type, "completed", row_count)

                logger.info("Loaded rel table (via download)",
                           type=edge_def.type,
                           rows=row_count)

    async def execute_query(
        self,
        cypher: str,
        parameters: dict | None = None,
        timeout_ms: int = 60000,
    ) -> QueryResult:
        """Execute a Cypher query with timeout."""
        loop = asyncio.get_event_loop()

        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(
                    self._executor,
                    self._execute_query_sync,
                    cypher,
                    parameters,
                ),
                timeout=timeout_ms / 1000,
            )
            return result
        except asyncio.TimeoutError:
            raise QueryTimeoutError(f"Query exceeded timeout of {timeout_ms}ms")

    def _execute_query_sync(
        self,
        cypher: str,
        parameters: dict | None = None,
    ) -> QueryResult:
        """Blocking query execution."""
        conn = self.get_connection()
        start = time.time()

        result = conn.execute(cypher, parameters or {})

        # Fetch all results
        columns = result.get_column_names()
        rows = []
        while result.has_next():
            rows.append(result.get_next())

        execution_time_ms = int((time.time() - start) * 1000)

        return QueryResult(
            columns=columns,
            rows=rows,
            row_count=len(rows),
            execution_time_ms=execution_time_ms,
        )

    async def get_stats(self) -> dict:
        """Get graph statistics."""
        conn = self.get_connection()

        # Get node count
        node_result = conn.execute("MATCH (n) RETURN count(n);")
        node_count = node_result.get_next()[0]

        # Get edge count
        edge_result = conn.execute("MATCH ()-[r]->() RETURN count(r);")
        edge_count = edge_result.get_next()[0]

        # Get table names
        schema = await self.get_schema()

        return {
            "node_count": node_count,
            "edge_count": edge_count,
            "node_tables": list(schema["nodes"].keys()),
            "rel_tables": list(schema["relationships"].keys()),
        }

    async def get_schema(self) -> dict:
        """Get graph schema (tables and properties)."""
        conn = self.get_connection()

        # Use Ryugraph introspection
        result = conn.execute("CALL show_tables();")
        tables = []
        while result.has_next():
            tables.append(result.get_next())

        nodes = {}
        relationships = {}

        for table in tables:
            table_name, table_type = table[0], table[1]
            props_result = conn.execute(f"CALL table_info('{table_name}');")
            properties = {}
            primary_key = None

            while props_result.has_next():
                prop = props_result.get_next()
                prop_name, prop_type, is_pk = prop[0], prop[1], prop[2]
                properties[prop_name] = prop_type
                if is_pk:
                    primary_key = prop_name

            if table_type == "NODE":
                nodes[table_name] = {
                    "primary_key": primary_key,
                    "properties": properties,
                }
            else:
                # Get FROM/TO for relationships
                relationships[table_name] = {
                    "properties": properties,
                }

        return {"nodes": nodes, "relationships": relationships}

    async def close(self) -> None:
        """Close the database."""
        if self._db:
            self._db.close()
            self._db = None
        self._executor.shutdown(wait=True)
```

---

## Lock Service

### Implicit Lock Management

From [architectural.guardrails.md](--/foundation/architectural.guardrails.md): Lock is managed entirely within the Wrapper Pod (in-memory). Lock acquisition must be atomic using mutex to prevent race conditions.

```python
# services/lock.py
import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class LockState:
    holder_id: str
    holder_name: str
    algorithm: str
    acquired_at: datetime
    execution_id: str


class LockService:
    """Thread-safe lock management for algorithm execution."""

    def __init__(self):
        self._lock_state: Optional[LockState] = None
        self._mutex = asyncio.Lock()

    async def acquire(
        self,
        user_id: str,
        user_name: str,
        algorithm: str,
    ) -> tuple[bool, str, Optional[LockState]]:
        """
        Attempt to acquire the lock atomically.

        Returns:
            (success, execution_id, current_lock_state)
            - If success=True: execution_id is the new execution ID
            - If success=False: current_lock_state is who holds the lock
        """
        async with self._mutex:
            if self._lock_state is not None:
                return (False, "", self._lock_state)

            execution_id = str(uuid.uuid4())
            self._lock_state = LockState(
                holder_id=user_id,
                holder_name=user_name,
                algorithm=algorithm,
                acquired_at=datetime.utcnow(),
                execution_id=execution_id,
            )
            return (True, execution_id, None)

    async def release(self, execution_id: str) -> bool:
        """
        Release the lock for a specific execution.

        Returns True if released, False if execution_id doesn't match.
        """
        async with self._mutex:
            if self._lock_state is None:
                return False
            if self._lock_state.execution_id != execution_id:
                return False

            self._lock_state = None
            return True

    async def get_status(self) -> dict:
        """Get current lock status (non-blocking read)."""
        async with self._mutex:
            if self._lock_state is None:
                return {"locked": False}

            return {
                "locked": True,
                "holder_id": self._lock_state.holder_id,
                "holder_name": self._lock_state.holder_name,
                "algorithm": self._lock_state.algorithm,
                "acquired_at": self._lock_state.acquired_at.isoformat() + "Z",
                "duration_seconds": int(
                    (datetime.utcnow() - self._lock_state.acquired_at).total_seconds()
                ),
            }

    async def is_locked(self) -> bool:
        """Check if lock is held."""
        async with self._mutex:
            return self._lock_state is not None
```

---

## Algorithm Service

### Algo Extension Loading

The Ryugraph native algorithms (PageRank, WCC, SCC, Louvain, K-Core) require the **algo extension** to be loaded. The binary is **baked into the wrapper Docker image at build time**, so loading is a single in-process call with no network dependency. See ADR-138 for rationale.

#### Extension Loading Mechanism

The `libalgo.ryu_extension` shared library is copied into the wrapper image during the Earthfile build, at the exact path Ryugraph looks for cached extensions:

```
/root/.ryu/extension/25.9.0/linux_amd64/algo/libalgo.ryu_extension
```

**The `25.9.0` segment is the Ryugraph *native library* build version**, hardcoded in the Ryugraph C++ extension loader. It is **not** the Python wheel version, which is currently `25.9.2` on PyPI. The two can diverge and they do: `import ryugraph; print(ryugraph.__version__)` returns `25.9.2`, but Ryugraph's runtime resolver only finds the binary at `/root/.ryu/extension/25.9.0/linux_amd64/algo/...`. See [ADR-138](--/process/adr/infrastructure/adr-138-bake-algo-extension-into-wrapper-image.md) for the full gotcha and the empirical matrix that established which path works.

At runtime the wrapper just loads it:

```cypher
-- LOAD finds the binary in the local extension cache. No INSTALL, no network call.
LOAD algo;
```

The wrapper performs this automatically during database initialization in `services/database.py`:

```python
# In _init_database() - the binary is already on disk inside the image,
# so LOAD finds it immediately. No retry loop needed.
try:
    logger.info("Loading algo extension from local cache")
    self._connection.execute("LOAD algo")
    logger.info("Algo extension loaded successfully")
except Exception as e:
    logger.error(
        "Failed to load algo extension - native algorithms will not work",
        error=str(e),
        error_type=type(e).__name__,
    )
```

The previous flow — `INSTALL algo FROM '<extension-server-url>'` followed by a 1s/2s/3s linear retry loop against an external `extension-server` pod — has been removed entirely. The `RYUGRAPH_EXTENSION_SERVER_URL` environment variable is no longer read by the wrapper at all: the algo branch is gone, and the httpfs loading block that previously also consulted it has been deleted as well (httpfs was dead code — see [ADR-031](--/process/adr/system-design/adr-031-dual-mode-gcs-data-loading.md), partially superseded).

#### Build-Time Provisioning

Earthly does not support `COPY --from=<external-image>` the way Docker does, so the upstream extension-repo image is wrapped in a named artifact target (`+algo-extension-binary`) that uses `FROM + SAVE ARTIFACT`. The wrapper target then consumes the artifact via `COPY +algo-extension-binary/libalgo.ryu_extension`.

```earthly
algo-extension-binary:
    FROM --platform=linux/amd64 ghcr.io/predictable-labs/extension-repo:latest
    SAVE ARTIFACT /usr/share/nginx/html/v25.9.0/linux_amd64/algo/libalgo.ryu_extension libalgo.ryu_extension

ryugraph-wrapper:
    FROM --platform=linux/amd64 python:3.12-slim
    # ... install ryugraph-wrapper and deps ...

    # Bake algo extension binary into image (ADR-138).
    # Path uses 25.9.0 — Ryugraph native library build version, NOT wheel version.
    RUN mkdir -p /root/.ryu/extension/25.9.0/linux_amd64/algo
    COPY +algo-extension-binary/libalgo.ryu_extension \
        /root/.ryu/extension/25.9.0/linux_amd64/algo/libalgo.ryu_extension
```

The bundled binary is approximately 454 KB, and `v25.9.0` is currently the only version published by the upstream extension-repo image. When Ryugraph bumps its native library version, **both** the source path inside `+algo-extension-binary` (`/usr/share/nginx/html/v{X}/...`) and the target cache path (`/root/.ryu/extension/{X}/linux_amd64/algo/...`) must be updated in the Earthfile. Confirm the correct value by checking which `v{X}/` directory the updated extension-repo image publishes.

#### Platform Constraint (ADR-026, still in effect)

The bundled binary is **AMD64-only**: the upstream `linux_arm64` directory contains misnamed x86-64 ELF binaries (see [ADR-026](--/process/adr/infrastructure/adr-026-arm64-algo-extension-workaround.md) and [predictable-labs/ryugraph#44](https://github.com/predictable-labs/ryugraph/issues/44)). Wrapper images must therefore still be built `--platform=linux/amd64`. On Apple Silicon Macs with OrbStack, AMD64 containers run via **Rosetta 2** at approximately 80-90% native performance.

| Environment | How algo extension is delivered |
|---|---|
| Wrapper container (GKE London, HSBC, Orbstack, E2E) | Baked into image at `/root/.ryu/extension/25.9.0/linux_amd64/algo/` |

The wrapper is only executed inside Linux AMD64 containers — there is no "wrapper as a bare macOS Python process" supported path, so there is no separate macOS-host row in this table. All real test surfaces (unit tests mock Ryugraph; integration tests mock Ryugraph; E2E tests and tutorial/reference/UAT notebook suites hit wrapper pods over HTTP via the SDK) exercise the containerised baked-binary path. The previous "extension server required?" matrix is gone — no environment requires an extension server at runtime.

#### E2E Test Configuration

The E2E tests in `e2e-tests/conftest.py` build all images with `--platform linux/amd64`. The previous step that pulled `extension-server` separately has been removed, along with the wrapper's startup retry loop against it.

```python
# conftest.py - _build_image()
def _build_image(tag, dockerfile, context, platform="linux/amd64"):
    subprocess.run([
        "docker", "buildx", "build",
        "--platform", platform,
        "-t", tag,
        "--load",
        str(context),
    ], check=True)
```

#### Reference Documentation

- [ADR-138: Bake Algo Extension Into Wrapper Image](--/process/adr/infrastructure/adr-138-bake-algo-extension-into-wrapper-image.md) - Rationale for the build-time baking approach
- [ADR-026: ARM64 Algo Extension Workaround](--/process/adr/infrastructure/adr-026-arm64-algo-extension-workaround.md) - Why the bundled binary is still AMD64-only
- [Ryugraph Algo Extension](--/--/reference/ryugraph-v25-9/extensions/algo/index-mdx) - Algorithm syntax and examples
- [ARM64 Workaround](--/--/platform/extensions/arm64-workaround-mdx) - Historical context for the platform constraint
- [KuzuDB Extension Docs](https://docs.kuzudb.com/extensions/) - Upstream documentation

### Shared Algorithm Schemas

Algorithm types, enums, and response models are defined in the shared `graph-olap-schemas` package to ensure consistency between wrapper and SDK:

```python
# Wrapper imports shared types from graph-olap-schemas
from graph_olap_schemas import (
    AlgorithmType,              # native, networkx
    AlgorithmCategory,          # centrality, community, pathfinding, etc.
    ExecutionStatus,            # pending, running, completed, failed, cancelled
    AlgorithmInfoResponse,      # Algorithm details response
    AlgorithmListResponse,      # List algorithms response
    AlgorithmExecutionResponse, # Execution result response
    NativeAlgorithmRequest,     # Native algorithm request body
    NetworkXAlgorithmRequest,   # NetworkX algorithm request body
)
```

The wrapper's `registry.py` imports `AlgorithmType` and `AlgorithmCategory` from shared schemas instead of defining them locally. This ensures the SDK and wrapper use identical enum values.

See [graph-olap-schemas](--/--/graph-olap-schemas/) for the authoritative schema definitions.

### Algorithm Execution

```python
# services/algorithm.py
from graph_olap_schemas import ExecutionStatus
from wrapper.algorithms.registry import AlgorithmRegistry
from wrapper.services.lock import LockService
from wrapper.services.database import DatabaseService

@dataclass
class ExecutionResult:
    execution_id: str
    algorithm: str
    status: str  # "running", "completed", "failed"
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    result: Optional[dict] = None
    error: Optional[str] = None


class AlgorithmService:
    def __init__(
        self,
        db_service: DatabaseService,
        lock_service: LockService,
        registry: AlgorithmRegistry,
    ):
        self.db = db_service
        self.lock = lock_service
        self.registry = registry
        self._executions: dict[str, ExecutionResult] = {}
        self._executor = ThreadPoolExecutor(max_workers=1)  # Single algorithm at a time

    async def execute(
        self,
        user_id: str,
        user_name: str,
        algorithm_name: str,
        params: dict,
    ) -> ExecutionResult:
        """
        Start algorithm execution.

        Returns immediately with execution_id (async pattern).
        """
        # Validate algorithm exists
        algorithm = self.registry.get(algorithm_name)
        if algorithm is None:
            raise AlgorithmNotFoundError(algorithm_name)

        # Validate parameters
        algorithm.validate_params(params)

        # Acquire lock (atomic)
        success, execution_id, current_lock = await self.lock.acquire(
            user_id, user_name, algorithm_name
        )

        if not success:
            raise ResourceLockedError(
                holder_id=current_lock.holder_id,
                holder_name=current_lock.holder_name,
                algorithm=current_lock.algorithm,
                acquired_at=current_lock.acquired_at,
            )

        # Create execution record
        execution = ExecutionResult(
            execution_id=execution_id,
            algorithm=algorithm_name,
            status="running",
            started_at=datetime.utcnow(),
        )
        self._executions[execution_id] = execution

        # Start async execution
        asyncio.create_task(self._run_algorithm(execution_id, algorithm, params))

        return execution

    async def _run_algorithm(
        self,
        execution_id: str,
        algorithm: Algorithm,
        params: dict,
    ) -> None:
        """Run algorithm in background and update execution status."""
        execution = self._executions[execution_id]

        try:
            loop = asyncio.get_event_loop()

            # Run algorithm (blocking) in executor
            result = await loop.run_in_executor(
                self._executor,
                algorithm.execute,
                self.db,
                params,
            )

            # Update execution
            execution.status = "completed"
            execution.completed_at = datetime.utcnow()
            execution.duration_seconds = int(
                (execution.completed_at - execution.started_at).total_seconds()
            )
            execution.result = result

            logger.info("Algorithm completed",
                       execution_id=execution_id,
                       algorithm=execution.algorithm,
                       duration_seconds=execution.duration_seconds)

        except Exception as e:
            logger.exception("Algorithm failed",
                           execution_id=execution_id,
                           algorithm=execution.algorithm)

            execution.status = "failed"
            execution.completed_at = datetime.utcnow()
            execution.error = str(e)

        finally:
            # Release lock
            await self.lock.release(execution_id)

    async def get_execution(self, execution_id: str) -> Optional[ExecutionResult]:
        """Get execution status by ID."""
        return self._executions.get(execution_id)
```

### Algorithm Architecture

The wrapper supports two categories of algorithms with different execution models:

| Category | Endpoint | Discovery | Execution |
|----------|----------|-----------|-----------|
| **Ryugraph Native** | `POST /algo/{name}` | Fixed set | Runs directly in Ryugraph (fastest) |
| **NetworkX** | `POST /networkx/{name}` | Dynamic introspection | Extracts to NetworkX, runs in Python |

**Why both?** Some algorithms exist in both (e.g., PageRank, shortest path). Users can choose:
- **Native**: Faster, runs in-database, no data extraction
- **NetworkX**: More parameters, familiar API, 100+ algorithms available

See [api.wrapper.spec.md](--/system-design/api/api.wrapper.spec.md) for the complete API specification.

### Ryugraph Native Algorithms

Native algorithms use the **KuzuDB/Ryugraph algo extension** which provides parallelized C++ implementations based on [Ligra](https://jshun.github.io/ligra/docs/examples.html). All algorithms require a **projected graph** to be created first.

**Key pattern:**

1. Create projected graph: `CALL project_graph('<name>', ['<NodeTable>'], ['<RelTable>'])`
2. Run algorithm: `CALL page_rank('<name>', ...) RETURN node, rank`
3. Clean up: `CALL drop_projected_graph('<name>')`

**Available algorithms (6 total):**

| Algorithm | Function | Alias | Parameters | Returns |
|-----------|----------|-------|------------|---------|
| PageRank | `page_rank(graph)` | `pr` | `dampingFactor:=0.85, maxIterations:=20, tolerance:=0.0000001, normalizeInitial:=true` | `node, rank` |
| WCC | `weakly_connected_components(graph)` | `wcc` | `maxIterations:=100` | `node, group_id` |
| SCC | `strongly_connected_components(graph)` | `scc` | `maxIterations:=100` | `node, group_id` |
| SCC Kosaraju | `strongly_connected_components_kosaraju(graph)` | `scc_ko` | (none) | `node, group_id` |
| Louvain | `louvain(graph)` | - | `maxPhases:=20, maxIterations:=20` | `node, louvain_id` |
| K-Core | `k_core_decomposition(graph)` | `kcore` | (none) | `node, k_degree` |

**Notes:**
- All algorithms operate on **projected graphs**, not directly on database tables
- Projected graphs are evaluated lazily (on-demand, not materialized in memory)
- WCC and Louvain treat edges as undirected
- SCC has two implementations: parallel BFS-based (default) and DFS-based Kosaraju's algorithm
- `group_id`/`louvain_id`/`k_degree` are assigned based on internal node offsets

**Reference:** [KuzuDB Algo Extension Documentation](https://docs.kuzudb.com/extensions/algo/)

```python
# algorithms/native.py
class PageRankAlgorithm(NativeAlgorithm):
    """PageRank using Ryugraph algo extension."""

    async def execute(
        self,
        db_service: DatabaseService,
        node_label: str,
        edge_type: str,
        result_property: str,
        parameters: dict,
    ) -> dict:
        damping = parameters.get("damping_factor", 0.85)
        max_iter = parameters.get("max_iterations", 20)
        tolerance = parameters.get("tolerance", 1e-7)

        # Ensure result property exists
        await db_service.ensure_property_exists(node_label, result_property, "DOUBLE", "0.0")

        # Unique graph name to avoid collisions
        graph_name = f"_pr_{int(time.time() * 1000)}"

        try:
            # Step 1: Create projected graph (REQUIRED)
            await db_service.execute_query(
                f"CALL project_graph('{graph_name}', ['{node_label}'], ['{edge_type}'])"
            )

            # Step 2: Run PageRank
            result = await db_service.execute_query(f"""
                CALL page_rank('{graph_name}',
                    dampingFactor := {damping},
                    maxIterations := {max_iter},
                    tolerance := {tolerance}
                )
                RETURN offset(id(node)) AS node_offset, rank
            """)

            # Step 3: Write results back to nodes
            nodes_updated = await self._write_algo_results(
                db_service, result["rows"], node_label, result_property
            )

            return {"nodes_updated": nodes_updated, "converged": True}

        finally:
            # Step 4: Always clean up projected graph
            try:
                await db_service.execute_query(f"CALL drop_projected_graph('{graph_name}')")
            except Exception:
                pass  # Graph may not exist if creation failed


class WeaklyConnectedComponentsAlgorithm(NativeAlgorithm):
    """WCC using Ryugraph algo extension."""

    async def execute(
        self,
        db_service: DatabaseService,
        node_label: str,
        edge_type: str,
        result_property: str,
        parameters: dict,
    ) -> dict:
        max_iter = parameters.get("max_iterations", 100)

        await db_service.ensure_property_exists(node_label, result_property, "INT64", "0")

        graph_name = f"_wcc_{int(time.time() * 1000)}"

        try:
            # Create projected graph
            await db_service.execute_query(
                f"CALL project_graph('{graph_name}', ['{node_label}'], ['{edge_type}'])"
            )

            # Run WCC
            result = await db_service.execute_query(f"""
                CALL weakly_connected_components('{graph_name}', maxIterations := {max_iter})
                RETURN offset(id(node)) AS node_offset, group_id
            """)

            nodes_updated = await self._write_algo_results(
                db_service, result["rows"], node_label, result_property
            )

            return {"nodes_updated": nodes_updated, "components": len(set(r[1] for r in result["rows"]))}

        finally:
            try:
                await db_service.execute_query(f"CALL drop_projected_graph('{graph_name}')")
            except Exception:
                pass
```

**Utility functions:**

```sql
CALL show_projected_graphs();           -- List all projected graphs
CALL drop_projected_graph('<NAME>');    -- Remove a projected graph
```

### NetworkX Algorithms (Dynamic Discovery)

NetworkX algorithms are discovered **dynamically at runtime** via Python introspection. Any algorithm in `networkx.algorithms` is automatically available—no code changes needed when NetworkX is upgraded.

```python
# algorithms/networkx.py
import networkx as nx
import inspect
import typing
from docstring_parser import parse as parse_docstring

class NetworkXAlgorithmService:
    """
    Dynamic NetworkX algorithm discovery and execution.

    - Explicit convenience methods for common algorithms (better IDE support)
    - Generic run() for any algorithm (dynamic introspection)
    """

    def __init__(self, db_service: DatabaseService):
        self.db = db_service
        self._cache: dict = {}

    # -------------------------------------------------------------------------
    # Dynamic Discovery (for generic run())
    # -------------------------------------------------------------------------

    def discover_algorithm(self, name: str) -> callable:
        """Find algorithm function in networkx.algorithms namespace."""
        if name in self._cache:
            return self._cache[name]

        for submodule_name in dir(nx.algorithms):
            submodule = getattr(nx.algorithms, submodule_name)
            if inspect.ismodule(submodule) and hasattr(submodule, name):
                func = getattr(submodule, name)
                if callable(func):
                    self._cache[name] = func
                    return func

        # Check top-level nx namespace (some algorithms aliased there)
        if hasattr(nx, name) and callable(getattr(nx, name)):
            self._cache[name] = getattr(nx, name)
            return self._cache[name]

        raise AlgorithmNotFoundError(f"Unknown NetworkX algorithm: {name}")

    def get_algorithm_info(self, name: str) -> dict:
        """Extract parameter info via introspection."""
        func = self.discover_algorithm(name)
        sig = inspect.signature(func)
        type_hints = typing.get_type_hints(func) if hasattr(func, '__annotations__') else {}
        docstring = parse_docstring(func.__doc__ or "")
        param_docs = {p.arg_name: p.description for p in docstring.params}

        params = []
        for pname, param in sig.parameters.items():
            if pname == "G":
                continue
            params.append({
                "name": pname,
                "type": str(type_hints.get(pname, "any")),
                "required": param.default == inspect.Parameter.empty,
                "default": None if param.default == inspect.Parameter.empty else param.default,
                "description": param_docs.get(pname, ""),
            })

        return {
            "name": name,
            "description": docstring.short_description or "",
            "params": params,
        }

    def list_algorithms(self, category: str = None, search: str = None) -> list[dict]:
        """List all available NetworkX algorithms."""
        algorithms = []
        for submodule_name in dir(nx.algorithms):
            submodule = getattr(nx.algorithms, submodule_name)
            if not inspect.ismodule(submodule):
                continue
            for func_name in dir(submodule):
                if func_name.startswith("_"):
                    continue
                func = getattr(submodule, func_name)
                if not callable(func):
                    continue
                if search and search.lower() not in func_name.lower():
                    continue
                if category and submodule_name != category:
                    continue
                algorithms.append({
                    "name": func_name,
                    "category": submodule_name,
                    "description": (func.__doc__ or "").split("\n")[0][:100],
                })
        return algorithms

    # -------------------------------------------------------------------------
    # Generic Execution (any algorithm)
    # -------------------------------------------------------------------------

    def execute(self, algorithm_name: str, params: dict) -> dict:
        """Execute any NetworkX algorithm dynamically."""
        func = self.discover_algorithm(algorithm_name)
        conn = self.db.get_connection()

        # Extract graph
        G = self._extract_graph(conn, params)

        # Build algorithm arguments (exclude our wrapper params)
        algo_params = params.get("params", {})

        # Execute
        result = func(G, **algo_params)

        # Process result and optionally write back
        return self._process_result(conn, result, params)

    def _extract_graph(self, conn, params: dict):
        """Extract subgraph based on node_label and edge_types."""
        node_label = params.get("node_label")
        edge_types = params.get("edge_types")
        directed = params.get("directed", False)

        if node_label and edge_types:
            pattern = "|".join(edge_types)
            cypher = f"MATCH (n:{node_label})-[r:{pattern}]->(m:{node_label}) RETURN *"
        elif node_label:
            cypher = f"MATCH (n:{node_label})-[r]->(m:{node_label}) RETURN *"
        else:
            cypher = "MATCH (n)-[r]->(m) RETURN *"

        result = conn.execute(cypher)
        return result.get_as_networkx(directed=directed)

    def _process_result(self, conn, result, params: dict) -> dict:
        """Process algorithm result and optionally write to graph."""
        property_name = params.get("property_name")
        node_label = params.get("node_label")

        if isinstance(result, dict) and property_name and node_label:
            # Node values - write back to graph
            self._write_node_values(conn, node_label, property_name, result)
            return {"type": "node_values", "property_name": property_name, "nodes_updated": len(result)}
        elif isinstance(result, dict):
            return {"type": "node_values", "values": {str(k): v for k, v in result.items()}}
        elif isinstance(result, (int, float)):
            return {"type": "scalar", "value": result}
        elif isinstance(result, (list, tuple)):
            return {"type": "path", "path": list(result), "length": len(result) - 1}
        else:
            return {"type": "unknown", "value": str(result)}

    def _write_node_values(self, conn, node_label: str, property_name: str, values: dict):
        """Write algorithm results back to node properties."""
        import polars as pl
        data = []
        for node_id, score in values.items():
            parts = str(node_id).split("_", 1)
            if len(parts) == 2:
                data.append({"node_id": parts[1], "score": float(score)})

        if data:
            df = pl.DataFrame(data)
            try:
                conn.execute(f"ALTER TABLE {node_label} ADD {property_name} DOUBLE DEFAULT 0.0;")
            except Exception:
                pass
            conn.execute(f"""
                LOAD FROM df
                MERGE (n:{node_label} {{id: node_id}})
                SET n.{property_name} = score;
            """)
```
