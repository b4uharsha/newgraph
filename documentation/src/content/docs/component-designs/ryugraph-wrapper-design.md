---
title: "Ryugraph Wrapper Design"
scope: hsbc
---

<!-- Verified against wrapper code on 2026-04-20 -->

# Ryugraph Wrapper Design

## Overview

The Ryugraph Wrapper is a Python FastAPI service that runs embedded Ryugraph (KuzuDB fork) within each graph instance pod. It provides REST API endpoints for Cypher queries, graph algorithms (both native Ryugraph and NetworkX), and instance management. Each pod hosts a single graph database loaded from snapshot Parquet files.

## Prerequisites

- [requirements.md](--/foundation/requirements.md) - Instance model, algorithm requirements, lock model
- [architectural.guardrails.md](--/foundation/architectural.guardrails.md) - Embedded Ryugraph pattern, implicit locking
- [system.architecture.design.md](--/system-design/system.architecture.design.md) - Pod architecture, startup flow
- [ryugraph-networkx.reference.md](--/reference/ryugraph-networkx.reference.md) - Ryugraph/NetworkX API reference
- [ryugraph-performance.reference.md](--/reference/ryugraph-performance.reference.md) - Threading, buffer pool, I/O characteristics
- [data-pipeline.reference.md](--/reference/data-pipeline.reference.md) - Schema creation, COPY FROM syntax, type mapping
- [api.wrapper.spec.md](--/system-design/api/api.wrapper.spec.md) - REST API specification
- [api.internal.spec.md](--/system-design/api/api.internal.spec.md) - Internal communication with Control Plane

## Related Components

- [control-plane.design.md](-/control-plane.design.md) - Creates pods, receives status/metrics updates
- [export-worker.design.md](-/export-worker.design.md) - Creates the Parquet files that Wrapper loads
- [jupyter-sdk.design.md](-/jupyter-sdk.design.md) - Client that calls Wrapper Pod APIs

## Core Dependencies

The Ryugraph Wrapper requires these packages as **mandatory dependencies** (not optional):

| Package | Purpose | Why Required |
|---------|---------|--------------|
| `ryugraph` | Embedded graph database (KuzuDB fork) | Core purpose of the wrapper - cannot function without it |
| `networkx` | Graph algorithm library | Provides 100+ algorithms exposed via `/networkx/*` endpoints |
| `numpy` | Numerical computing | Required by NetworkX for algorithm implementations |
| `scipy` | Scientific computing | Required by NetworkX for PageRank, clustering, etc. |

These are not optional because:
- A "Ryugraph Wrapper" without Ryugraph is nonsensical
- The wrapper's API contract includes NetworkX algorithm endpoints
- NetworkX algorithms depend on numpy/scipy for numerical computations
- The Dockerfile and production deployment assume these are installed

## Constraints

From [architectural.guardrails.md](--/foundation/architectural.guardrails.md):

- Ryugraph runs embedded (in-process), not as a separate server
- One Ryugraph database per pod (file locking prevents multiple writers)
- Concurrent read queries allowed; exclusive lock for algorithm writes
- Lock is implicit (automatic acquire/release, no explicit lock API)
- Algorithm results written to node/edge properties, not exportable
- All status updates go through Control Plane API

## This Document Series

This is the core Ryugraph Wrapper design. Additional details are in:

- **[ryugraph-wrapper.services.design.md](-/ryugraph-wrapper.services.design.md)** - Database Service, Lock Service, and Algorithm Service implementations
- **[ryugraph-wrapper.deployment.design.md](-/ryugraph-wrapper.deployment.design.md)** - Deployment model: no Helm chart; pods are spawned imperatively by the control plane's `K8sService.create_wrapper_pod`

---

## Project Structure

```
ryugraph-wrapper/
├── src/
│   └── wrapper/
│       ├── __init__.py
│       ├── main.py              # FastAPI app entrypoint
│       ├── config.py            # Configuration from environment (pydantic-settings)
│       ├── lifespan.py          # Application lifecycle management (startup/shutdown)
│       ├── dependencies.py      # FastAPI dependency injection providers
│       ├── logging.py           # Structured logging configuration (structlog)
│       ├── exceptions.py        # Custom exceptions (ControlPlaneError, DatabaseError, etc.)
│       ├── routers/
│       │   ├── __init__.py
│       │   ├── health.py        # /health, /ready, /status endpoints
│       │   ├── query.py         # /query endpoint
│       │   ├── schema.py        # /schema endpoint
│       │   ├── lock.py          # /lock endpoint
│       │   ├── algo.py          # /algo/{name} endpoints
│       │   └── networkx.py      # /networkx/{name} endpoints
│       ├── services/
│       │   ├── __init__.py
│       │   ├── database.py      # Ryugraph database management
│       │   ├── algorithm.py     # Algorithm execution service
│       │   └── lock.py          # Lock management service
│       ├── algorithms/
│       │   ├── __init__.py
│       │   ├── native.py        # Ryugraph native algorithms (fixed set)
│       │   ├── networkx.py      # NetworkX algorithms (explicit + dynamic discovery)
│       │   ├── registry.py      # Algorithm registry for discovery
│       │   └── writeback.py     # Result write-back to Ryugraph
│       ├── models/
│       │   ├── __init__.py
│       │   ├── requests.py      # Request body models
│       │   ├── responses.py     # Response models
│       │   ├── lock.py          # Lock state model
│       │   ├── execution.py     # Algorithm execution model
│       │   └── mapping.py       # Mapping definition model
│       ├── clients/
│       │   ├── __init__.py
│       │   └── control_plane.py # Control Plane API client
│       └── utils/
│           ├── __init__.py
│           └── ddl.py           # DDL generation utilities
├── tests/
│   ├── unit/
│   └── integration/
├── pyproject.toml
└── README.md
```

### Core Module Descriptions

#### `lifespan.py` - Application Lifecycle Management

Handles the complete startup and shutdown sequences for the wrapper pod:

- **Startup sequence**: Initializes Control Plane client, services (database, lock, algorithm), creates schema from mapping definition, loads data from GCS Parquet files, registers algorithms, starts metrics reporter, and reports ready status.
- **Shutdown sequence**: Cancels metrics reporter, force-releases any held locks, reports stopping status, closes database connection and HTTP clients.
- **Error handling**: Maps exceptions to standardized error codes (`STARTUP_FAILED`, `MAPPING_FETCH_ERROR`, `SCHEMA_CREATE_ERROR`, `DATA_LOAD_ERROR`, `DATABASE_ERROR`) and reports failures to Control Plane with stack traces.
- **Background metrics**: Spawns an async task that periodically reports memory usage to Control Plane for resource monitoring.

#### `dependencies.py` - FastAPI Dependency Injection

Provides dependency injection functions for route handlers:

- **Service dependencies**: `get_database_service()`, `get_lock_service()`, `get_algorithm_service()`, `get_control_plane_client()` - retrieve services from FastAPI app state.
- **User context**: `get_user_id()`, `get_user_name()`, `get_user_role()` - extract user information from request headers.
- **Authorization**: `require_algorithm_permission()` - verifies user has permission to execute algorithms (admin/ops can execute on any instance, analysts only on instances they own).
- **Type aliases**: Provides `Annotated` type aliases (`SettingsDep`, `DatabaseServiceDep`, etc.) for clean route handler signatures.
- **M2M token handling**: Extracts email from JWT custom claims for machine-to-machine authentication (see ADR-095).

#### `logging.py` - Structured Logging Configuration

Configures structured logging using `structlog`:

- **JSON format**: For production (GCP Cloud Logging) - includes timestamps, log levels, exception info.
- **Console format**: For local development - colored output with human-readable formatting.
- **Context binding**: `bind_context()`, `clear_context()`, `unbind_context()` for adding request-scoped context (instance_id, user_id) to all log entries.
- **Noise reduction**: Suppresses verbose logging from third-party libraries (httpx, httpcore, uvicorn.access).

---

## FastAPI App Wiring (main.py)

`main.py` is a `create_app()` factory that registers **CORS middleware** and **centralized exception handlers** before the lifespan and routers are attached (see `wrapper/main.py:64-124`). Route handlers therefore raise typed `WrapperError` subclasses (`ResourceLockedError`, `AlgorithmNotFoundError`, `QueryTimeoutError`, `RequestValidationError`) and the middleware maps each to a structured JSON body via `exc.to_dict()`.

```python
# main.py — excerpt around lines 64-124
def create_app() -> FastAPI:
    app = FastAPI(title="Ryugraph Wrapper API", lifespan=lifespan, ...)

    # CORS middleware — tune origins in production
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Structured exception handlers — all emit {"error": {"code", "message", "details"}}
    @app.exception_handler(WrapperError)
    async def _wrapper_error(request, exc):
        return JSONResponse(status_code=exc.http_status, content=exc.to_dict())

    @app.exception_handler(ResourceLockedError)
    async def _resource_locked(request, exc):
        return JSONResponse(status_code=exc.http_status, content=exc.to_dict())

    @app.exception_handler(AlgorithmNotFoundError)
    async def _algorithm_not_found(request, exc):
        return JSONResponse(status_code=exc.http_status, content=exc.to_dict())

    @app.exception_handler(QueryTimeoutError)
    async def _query_timeout(request, exc):
        return JSONResponse(status_code=exc.http_status, content=exc.to_dict())

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request, exc):
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "VALIDATION_ERROR",
                                "message": "Request validation failed",
                                "details": {"errors": exc.errors()}}},
        )
    # Routers registered after middleware + handlers
    app.include_router(health.router)
    app.include_router(query.router)
    app.include_router(schema.router)
    app.include_router(lock.router)
    app.include_router(algo.router)
    app.include_router(networkx.router)
    return app
```

---

## Application Lifecycle

### Startup Sequence

![instance-startup-sequence](diagrams/ryugraph-wrapper-design/instance-startup-sequence.svg)

<details>
<summary>Mermaid Source</summary>

```mermaid
sequenceDiagram
    accTitle: Instance Startup Sequence
    accDescr: Wrapper pod initializes Ryugraph database, creates schema, loads data from GCS, and reports ready status to Control Plane

    autonumber

    box rgb(227,242,253) Control Plane
        participant CP as Control Plane
    end
    box rgb(225,245,254) Wrapper Pod
        participant W as Wrapper
        participant RG as Ryugraph
    end
    box rgb(232,245,233) Storage
        participant GCS as GCS
    end

    Note over W: Pod scheduled by K8s

    activate W
    W->>CP: Get mapping definition
    CP-->>W: Node/edge definitions, GCS path

    W->>CP: Update progress: "initializing"

    W->>+RG: Initialize database
    RG-->>-W: Database ready

    W->>CP: Update progress: "schema_created"

    loop For each node definition
        W->>CP: Update progress: loading node
        W->>GCS: Read Parquet files
        GCS-->>W: Parquet data
        W->>+RG: COPY FROM (load nodes)
        RG-->>-W: Rows loaded
        W->>CP: Update progress: node complete
    end

    loop For each edge definition
        W->>CP: Update progress: loading edge
        W->>GCS: Read Parquet files
        GCS-->>W: Parquet data
        W->>+RG: COPY FROM (load edges)
        RG-->>-W: Rows loaded
        W->>CP: Update progress: edge complete
    end

    W->>RG: Get graph stats
    RG-->>W: Node/edge counts

    W->>CP: Update status: "running"
    Note over W: Readiness probe passes
    deactivate W
```

</details>

```python
# main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from wrapper.lifespan import startup, shutdown

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await startup(app)
    yield
    # Shutdown
    await shutdown(app)

app = FastAPI(
    title="Ryugraph Wrapper",
    lifespan=lifespan,
)
```

### Lifespan Management

```python
# lifespan.py
import ryugraph
from wrapper.config import Config
from wrapper.services.database import DatabaseService
from wrapper.services.lock import LockService
from wrapper.clients.control_plane import ControlPlaneClient

async def startup(app: FastAPI) -> None:
    """Initialize the wrapper on startup."""
    config = Config.from_env()
    app.state.config = config

    # Initialize Control Plane client (ADR-104: plain HTTP, no auth token)
    cp_client = ControlPlaneClient(
        base_url=config.control_plane_url,
        instance_id=config.instance_id,
        timeout=config.control_plane_timeout,
    )
    app.state.cp_client = cp_client

    # Report starting status
    await cp_client.update_instance_progress(
        instance_id=config.instance_id,
        phase="initializing",
        steps=[{"name": "pod_scheduled", "status": "completed"}],
    )

    # Initialize Ryugraph database
    db_service = DatabaseService(
        database_path=config.database_path,
        buffer_pool_size=config.buffer_pool_size,
        max_threads=config.max_threads,
    )

    try:
        # Get mapping definition from Control Plane
        mapping = await cp_client.get_instance_mapping(config.instance_id)

        # Create schema
        await cp_client.update_instance_progress(
            instance_id=config.instance_id,
            phase="initializing",
            steps=[
                {"name": "pod_scheduled", "status": "completed"},
                {"name": "schema_created", "status": "in_progress"},
            ],
        )

        await db_service.create_schema(mapping.node_definitions, mapping.edge_definitions)

        await cp_client.update_instance_progress(
            instance_id=config.instance_id,
            phase="loading_nodes",
            steps=[
                {"name": "pod_scheduled", "status": "completed"},
                {"name": "schema_created", "status": "completed"},
            ],
        )

        # Load data from GCS Parquet files
        await db_service.load_data(
            gcs_path=mapping.gcs_path,
            node_definitions=mapping.node_definitions,
            edge_definitions=mapping.edge_definitions,
            progress_callback=lambda step, status, count: cp_client.update_instance_progress(
                config.instance_id, step, status, count
            ),
        )

        # Initialize lock service
        lock_service = LockService()
        app.state.lock_service = lock_service

        # Store services in app state
        app.state.db_service = db_service

        # Report running status
        graph_stats = await db_service.get_stats()
        await cp_client.update_instance_status(
            instance_id=config.instance_id,
            status="running",
            pod_ip=get_pod_ip(),
            instance_url=f"https://{config.domain}/{config.instance_id}/",
            graph_stats=graph_stats,
        )

        logger.info("Wrapper startup complete",
                   instance_id=config.instance_id,
                   node_count=graph_stats["node_count"],
                   edge_count=graph_stats["edge_count"])

    except Exception as e:
        logger.exception("Startup failed", error=str(e))
        await cp_client.update_instance_status(
            instance_id=config.instance_id,
            status="failed",
            error_message=str(e),
            failed_phase="startup",
        )
        raise


async def shutdown(app: FastAPI) -> None:
    """Clean shutdown of the wrapper."""
    logger.info("Initiating shutdown")

    # Close database
    if hasattr(app.state, "db_service"):
        await app.state.db_service.close()

    logger.info("Shutdown complete")
```

---

## Algorithm Execution

![algorithm-execution-sequence](diagrams/ryugraph-wrapper-design/algorithm-execution-sequence.svg)

<details>
<summary>Mermaid Source</summary>

```mermaid
sequenceDiagram
    accTitle: Algorithm Execution Sequence
    accDescr: User executes a graph algorithm with automatic lock management and async polling

    autonumber

    box rgb(243,229,245) Client
        participant U as User/SDK
    end
    box rgb(225,245,254) Wrapper Pod
        participant API as API Router
        participant LS as Lock Service
        participant AS as Algorithm Service
        participant RG as Ryugraph
    end

    U->>+API: POST /algo/{name}
    API->>+LS: acquire(user, algorithm)

    alt Lock available
        LS-->>API: success, execution_id
        API->>+AS: execute(algorithm, params)
        AS-->>-API: execution started
        API-->>U: 200 {execution_id, status: "running"}

        Note over AS,RG: Background execution
        AS->>+RG: Run algorithm
        RG-->>-AS: Results
        AS->>RG: Write to properties
        AS->>LS: release(execution_id)
        LS-->>AS: released

        loop Poll for completion
            U->>API: GET /algo/status/{execution_id}
            API-->>U: {status, result}
        end
    else Lock held
        LS-->>-API: failed, current_holder
        API-->>-U: 409 RESOURCE_LOCKED
    end
```

</details>

---

## Lock State Machine

![lock-state-machine](diagrams/ryugraph-wrapper-design/lock-state-machine.svg)

<details>
<summary>Mermaid Source</summary>

```mermaid
stateDiagram-v2
    accTitle: Lock State Machine
    accDescr: Instance lock transitions between unlocked and locked states for algorithm execution

    classDef unlocked fill:#C8E6C9,stroke:#2E7D32,stroke-width:2px,color:#1B5E20
    classDef locked fill:#FFCDD2,stroke:#C62828,stroke-width:2px,color:#B71C1C

    state "Unlocked" as U
    state "Locked" as L

    state L {
        holder_id: string
        holder_name: string
        algorithm: string
        acquired_at: timestamp
        execution_id: uuid
    }

    [*] --> U: Instance startup
    U --> L: acquire(user, algorithm)
    L --> U: release(execution_id)
    L --> L: acquire() → REJECTED<br/>(returns current holder)

    U:::unlocked
    L:::locked
```

</details>

## API Routers

### Query Router

```python
# routers/query.py
from fastapi import APIRouter, Depends, HTTPException
from wrapper.dependencies import get_db_service, get_user, get_audit_client
from wrapper.models.requests import QueryRequest
from wrapper.models.responses import QueryResponse

router = APIRouter()

@router.post("/query", response_model=QueryResponse)
async def execute_query(
    request: QueryRequest,
    db: DatabaseService = Depends(get_db_service),
    user: User = Depends(get_user),
    audit: AuditClient = Depends(get_audit_client),
    cp_client: ControlPlaneClient = Depends(get_cp_client),
    config: Config = Depends(get_config),
):
    """Execute a read-only Cypher query."""
    try:
        result = await db.execute_query(
            cypher=request.cypher,
            parameters=request.parameters,
            timeout_ms=request.timeout_ms or 60000,
        )

        # Record activity for inactivity timeout tracking
        # record_activity() takes no args — instance_id is captured in the
        # ControlPlaneClient constructor.
        asyncio.create_task(cp_client.record_activity())

        # Audit log
        await audit.log_query(
            user_id=user.id,
            cypher=request.cypher,
            row_count=result.row_count,
            execution_time_ms=result.execution_time_ms,
            success=True,
        )

        return QueryResponse(
            data={
                "columns": result.columns,
                "rows": result.rows,
                "row_count": result.row_count,
                "execution_time_ms": result.execution_time_ms,
            }
        )

    except QueryTimeoutError as e:
        raise HTTPException(status_code=408, detail={
            "error": {"code": "QUERY_TIMEOUT", "message": str(e)}
        })

    except RyugraphError as e:
        raise HTTPException(status_code=400, detail={
            "error": {"code": "RYUGRAPH_ERROR", "message": str(e)}
        })
```

### Algorithm Router

```python
# routers/algo.py
from fastapi import APIRouter, Depends, HTTPException
from wrapper.dependencies import get_algorithm_service, get_user, get_config
from wrapper.services.algorithm import AlgorithmService

router = APIRouter()

@router.post("/algo/{name}")
async def run_algorithm(
    name: str,
    request: AlgorithmRequest,
    algo_service: AlgorithmService = Depends(get_algorithm_service),
    user: User = Depends(get_user),
    config: Config = Depends(get_config),
    cp_client: ControlPlaneClient = Depends(get_cp_client),
):
    """Run a Ryugraph native algorithm."""
    # Authorization check - only owner or admin can run algorithms
    if user.username != config.owner_username and user.role not in ("admin", "ops"):
        raise HTTPException(status_code=403, detail={
            "error": {
                "code": "PERMISSION_DENIED",
                "message": "Only instance owner or admin can run algorithms",
                "details": {"owner_username": config.owner_username},
            }
        })

    try:
        execution = await algo_service.execute(
            user_id=user.id,
            user_name=user.name,
            algorithm_name=name,
            params=request.dict(exclude_unset=True),
        )

        # Record activity for inactivity timeout tracking
        # record_activity() takes no args — instance_id is captured in the
        # ControlPlaneClient constructor.
        asyncio.create_task(cp_client.record_activity())

        return {
            "data": {
                "execution_id": execution.execution_id,
                "algorithm": execution.algorithm,
                "status": execution.status,
                "lock_acquired": True,
                "started_at": execution.started_at.isoformat() + "Z",
            }
        }

    except AlgorithmNotFoundError:
        raise HTTPException(status_code=404, detail={
            "error": {"code": "ALGORITHM_NOT_FOUND", "message": f"Unknown algorithm: {name}"}
        })

    except ResourceLockedError as e:
        raise HTTPException(status_code=409, detail={
            "error": {
                "code": "RESOURCE_LOCKED",
                "message": f"Instance locked by user '{e.holder_name}' running algorithm '{e.algorithm}' since {e.acquired_at.isoformat()}Z",
                "details": {
                    "holder_id": e.holder_id,
                    "holder_name": e.holder_name,
                    "algorithm": e.algorithm,
                    "acquired_at": e.acquired_at.isoformat() + "Z",
                },
            }
        })


@router.get("/algo/status/{execution_id}")
async def get_execution_status(
    execution_id: str,
    algo_service: AlgorithmService = Depends(get_algorithm_service),
):
    """Get algorithm execution status."""
    execution = await algo_service.get_execution(execution_id)

    if execution is None:
        raise HTTPException(status_code=404, detail={
            "error": {"code": "EXECUTION_NOT_FOUND", "message": f"Unknown execution: {execution_id}"}
        })

    response = {
        "execution_id": execution.execution_id,
        "algorithm": execution.algorithm,
        "status": execution.status,
        "started_at": execution.started_at.isoformat() + "Z",
    }

    if execution.status == "completed":
        response.update({
            "completed_at": execution.completed_at.isoformat() + "Z",
            "duration_seconds": execution.duration_seconds,
            "result": execution.result,
        })
    elif execution.status == "failed":
        response.update({
            "failed_at": execution.completed_at.isoformat() + "Z",
            "error": execution.error,
        })
    else:
        response["elapsed_seconds"] = int(
            (datetime.utcnow() - execution.started_at).total_seconds()
        )

    return {"data": response}
```

### NetworkX Router

```python
# routers/networkx.py
from fastapi import APIRouter, Depends, HTTPException
from wrapper.dependencies import get_networkx_service, get_user, get_config, get_cp_client
from wrapper.services.networkx import NetworkXAlgorithmService

router = APIRouter()

@router.post("/networkx/{name}")
async def run_networkx_algorithm(
    name: str,
    request: NetworkXRequest,
    nx_service: NetworkXAlgorithmService = Depends(get_networkx_service),
    user: User = Depends(get_user),
    config: Config = Depends(get_config),
    cp_client: ControlPlaneClient = Depends(get_cp_client),
):
    """Run a NetworkX algorithm."""
    # Authorization check - only owner or admin can run algorithms
    if user.username != config.owner_username and user.role not in ("admin", "ops"):
        raise HTTPException(status_code=403, detail={
            "error": {
                "code": "PERMISSION_DENIED",
                "message": "Only instance owner or admin can run algorithms",
            }
        })

    try:
        execution = await nx_service.execute(
            user_id=user.id,
            user_name=user.name,
            algorithm_name=name,
            params=request.dict(exclude_unset=True),
        )

        # Record activity for inactivity timeout tracking
        # record_activity() takes no args — instance_id is captured in the
        # ControlPlaneClient constructor.
        asyncio.create_task(cp_client.record_activity())

        return {"data": execution}

    except AlgorithmNotFoundError:
        raise HTTPException(status_code=404, detail={
            "error": {"code": "ALGORITHM_NOT_FOUND", "message": f"Unknown algorithm: {name}"}
        })

    except ResourceLockedError as e:
        raise HTTPException(status_code=409, detail={
            "error": {
                "code": "RESOURCE_LOCKED",
                "message": str(e),
                "details": e.details,
            }
        })


@router.get("/networkx/algorithms")
async def list_networkx_algorithms(
    category: str | None = None,
    search: str | None = None,
    nx_service: NetworkXAlgorithmService = Depends(get_networkx_service),
):
    """List available NetworkX algorithms (discovered dynamically)."""
    algorithms = nx_service.list_algorithms(category=category, search=search)
    categories = list(set(a["category"] for a in algorithms))
    return {
        "data": {
            "algorithms": algorithms,
            "categories": sorted(categories),
        }
    }


@router.get("/networkx/algorithms/{name}")
async def get_networkx_algorithm_info(
    name: str,
    nx_service: NetworkXAlgorithmService = Depends(get_networkx_service),
):
    """Get detailed info about a NetworkX algorithm."""
    try:
        info = nx_service.get_algorithm_info(name)
        return {"data": info}
    except AlgorithmNotFoundError:
        raise HTTPException(status_code=404, detail={
            "error": {"code": "ALGORITHM_NOT_FOUND", "message": f"Unknown algorithm: {name}"}
        })
```

### Health Router

```python
# routers/health.py
from fastapi import APIRouter, Depends, Response
from wrapper.dependencies import get_db_service, get_config

router = APIRouter()

@router.get("/health")
async def health(db: DatabaseService = Depends(get_db_service)):
    """Liveness probe."""
    try:
        # Basic check - can we get a connection?
        conn = db.get_connection()
        return {
            "status": "healthy",
            "ryugraph": "ready",
            "gcs": "accessible",
        }
    except Exception as e:
        return Response(
            content='{"status": "unhealthy", "error": "' + str(e) + '"}',
            status_code=503,
            media_type="application/json",
        )


@router.get("/ready")
async def ready(db: DatabaseService = Depends(get_db_service)):
    """Readiness probe."""
    if db._loaded_at is None:
        return Response(
            content='{"ready": false, "phase": "loading"}',
            status_code=503,
            media_type="application/json",
        )

    return {
        "ready": True,
        "loaded_at": db._loaded_at.isoformat() + "Z",
    }


@router.get("/status")
async def status(
    db: DatabaseService = Depends(get_db_service),
    lock: LockService = Depends(get_lock_service),
    config: Config = Depends(get_config),
):
    """Detailed instance status."""
    import psutil

    process = psutil.Process()
    memory = process.memory_info()

    stats = await db.get_stats()
    lock_status = await lock.get_status()

    return {
        "data": {
            "instance_id": config.instance_id,
            "status": "running",
            "uptime_seconds": int((datetime.utcnow() - db._loaded_at).total_seconds()),
            "memory_usage_bytes": memory.rss,
            "disk_usage_bytes": get_directory_size(config.database_path),
            "graph_stats": stats,
            "lock": lock_status,
        }
    }
```

---

## Control Plane Client

Per ADR-104 there is **no authentication token** — service-to-service calls within the cluster use plain HTTP. The client uses `httpx.AsyncClient` (NOT `aiohttp`), captures the `instance_id` in the constructor (so individual methods do not take it as a parameter), and relies on the shared Pydantic models from `graph_olap_schemas` for every request body.

```python
# clients/control_plane.py (shape — see wrapper/clients/control_plane.py for complete source)
import httpx
from graph_olap_schemas import (
    InstanceMappingResponse,
    InstanceProgressStep,
    UpdateInstanceMetricsRequest,
    UpdateInstanceProgressRequest,
    UpdateInstanceStatusRequest,
)
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from wrapper.exceptions import ControlPlaneError


class ControlPlaneClient:
    """ADR-104: plain HTTP inside the cluster, no oauth2-proxy, no bearer token."""

    def __init__(
        self,
        base_url: str,
        instance_id: str,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._instance_id = instance_id
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={"Content-Type": "application/json"},
        )

    async def update_status(
        self,
        status: str,
        *,
        error_message: str | None = None,
        error_code: str | None = None,
        stack_trace: str | None = None,
        failed_phase: str | None = None,
        pod_name: str | None = None,
        pod_ip: str | None = None,
        instance_url: str | None = None,
        progress: dict | None = None,
        node_count: int | None = None,
        edge_count: int | None = None,
    ) -> None:
        """PATCH ``/api/internal/instances/{instance_id}/status``.

        Payload validated via ``UpdateInstanceStatusRequest``. ``node_count``
        and ``edge_count`` are collapsed into a ``GraphStats`` object inside
        the request body.
        """

    async def update_progress(
        self,
        phase: str | None = None,
        steps: list[InstanceProgressStep] | None = None,
        *,
        # Legacy aliases retained for backward compatibility during migration
        stage: str | None = None,
        current: int | None = None,
        total: int | None = None,
        message: str | None = None,
    ) -> None:
        """PUT ``/api/internal/instances/{instance_id}/progress``.

        Modern callers pass ``phase`` + a list of ``InstanceProgressStep``.
        Legacy positional ``stage``/``current``/``total``/``message`` form
        is converted into a synthetic step list by the client. The method
        is **not** called ``update_instance_progress`` — it's ``update_progress``.
        """

    async def update_metrics(
        self,
        memory_usage_bytes: int | None = None,
        disk_usage_bytes: int | None = None,
        last_activity_at: str | None = None,
        query_count_since_last: int | None = None,
        avg_query_time_ms: int | None = None,
    ) -> None:
        """PUT ``/api/internal/instances/{instance_id}/metrics``.

        Graph statistics (``node_count``, ``edge_count``) are NOT sent here —
        they go through ``update_status`` via ``GraphStats``.
        """

    async def get_mapping(self) -> InstanceMappingResponse:
        """GET ``/api/internal/instances/{instance_id}/mapping``.

        Returns the shared ``InstanceMappingResponse`` directly — no
        intermediate wrapper type is introduced per the architectural
        guardrail against extending shared schemas.
        """

    async def record_activity(self) -> None:
        """POST ``/api/internal/instances/{instance_id}/activity``.

        Fire-and-forget — failures are logged but never raised so that a
        transient Control Plane blip cannot fail the user's query/algorithm.
        """

    async def close(self) -> None:
        """Close the underlying ``httpx.AsyncClient``."""
        await self._client.aclose()
```

---

## Configuration

Configuration uses **pydantic-settings** with nested models, not a hand-rolled dataclass. The aggregated `Settings` object exposes sub-models at `settings.wrapper`, `settings.ryugraph`, `settings.metrics`, `settings.logging`, and `settings.internal_auth`. Each sub-model has its own `env_prefix` (e.g. `WRAPPER_`, `RYUGRAPH_`, `METRICS_`, `LOG_`) so env vars like `RYUGRAPH_BUFFER_POOL_SIZE` resolve into `settings.ryugraph.buffer_pool_size`. See `packages/ryugraph-wrapper/src/wrapper/config.py` for the full definition.

```python
# config.py (shape — see wrapper/config.py for complete source)
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class WrapperConfig(BaseSettings):
    """Core wrapper config (env_prefix=WRAPPER_)."""

    model_config = SettingsConfigDict(env_prefix="WRAPPER_", extra="ignore")

    instance_id: str = Field(default="")   # empty = standalone/canary mode
    snapshot_id: str = Field(default="")
    mapping_id: str = Field(default="")
    owner_id: str = Field(default="")
    owner_username: str = Field(default="unknown")
    pod_name: str | None = None
    pod_ip: str | None = None
    instance_url: str | None = None
    host: str = "0.0.0.0"
    port: int = 8000
    control_plane_url: str              # required
    control_plane_timeout: float = 30.0
    gcs_base_path: str = ""             # empty = standalone/canary mode

    @field_validator("gcs_base_path")
    @classmethod
    def _validate_gcs_path(cls, v: str) -> str:
        if v and not v.startswith("gs://"):
            raise ValueError("gcs_base_path must start with 'gs://'")
        return v.rstrip("/")


class RyugraphConfig(BaseSettings):
    """Ryugraph tuning (env_prefix=RYUGRAPH_)."""

    model_config = SettingsConfigDict(env_prefix="RYUGRAPH_", extra="ignore")

    # ADR-149: canonical default aligned with spawn-time default and Dockerfile
    database_path: Path = Path("/data/db")
    buffer_pool_size: int = 2_147_483_648          # 2 GiB
    max_threads: int = 16                          # 4× CPU for I/O-bound loading
    query_timeout_ms: int = 60_000
    algorithm_timeout_ms: int = 1_800_000


class MetricsConfig(BaseSettings):
    """Metrics reporting (env_prefix=METRICS_)."""

    model_config = SettingsConfigDict(env_prefix="METRICS_", extra="ignore")

    report_interval_seconds: int = 60
    enabled: bool = True


class LoggingConfig(BaseSettings):
    """Logging (env_prefix=LOG_)."""

    model_config = SettingsConfigDict(env_prefix="LOG_", extra="ignore")

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    format: Literal["json", "console"] = "json"


class Settings(BaseSettings):
    """Aggregated settings — all route handlers receive this via DI."""

    model_config = SettingsConfigDict(extra="ignore")

    wrapper: WrapperConfig = Field(default_factory=WrapperConfig)
    ryugraph: RyugraphConfig = Field(default_factory=RyugraphConfig)
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    environment: Literal["local", "dev", "staging", "prod"] = "local"
```

---

## GCS Authentication

The Wrapper Pod reads Parquet files from GCS using Workload Identity. The pod's Kubernetes service account is bound to a GCP service account with `storage.objectViewer` permission on the snapshot bucket.

```yaml
# Pod annotation for Workload Identity (set by Control Plane)
metadata:
  annotations:
    iam.gke.io/gcp-service-account: graph-wrapper@PROJECT_ID.iam.gserviceaccount.com
```

Ryugraph uses the `gcsfs` library which automatically picks up credentials from the GKE metadata server when Workload Identity is configured.

---

## Metrics Reporting Background Task

There is no `MetricsReporter` class in `services/metrics.py`. Periodic metrics reporting is implemented as a module-level `_metrics_reporter` async function in `wrapper/lifespan.py` (lines 302-335) which is launched via `asyncio.create_task(...)` during startup and cancelled during shutdown. It reads `process.memory_info().rss` via `psutil` and calls `ControlPlaneClient.update_metrics(memory_usage_bytes=...)` on a fixed interval.

```python
# lifespan.py — excerpt around lines 302-335
async def _metrics_reporter(
    control_plane_client: ControlPlaneClient,
    interval_seconds: int,
) -> None:
    """Periodically report resource metrics to Control Plane.

    Graph statistics (node_count/edge_count) are NOT reported here —
    they are pushed via ``update_status`` when the instance transitions
    to ``running`` (per ``UpdateInstanceMetricsRequest`` schema).
    """
    import psutil

    while True:
        try:
            await asyncio.sleep(interval_seconds)
            process = psutil.Process()
            await control_plane_client.update_metrics(
                memory_usage_bytes=process.memory_info().rss,
            )
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning("Metrics reporting failed", error=str(e))
```

---

## Deployment

### Dockerfile

The wrapper image is built with Docker buildkit via `make build SVC=ryugraph-wrapper` — there is **no** Earthly step. The package is managed with **uv** (there is no `poetry.lock` in `packages/ryugraph-wrapper/`). The algo extension binary is baked in per [ADR-138](--/process/adr/infrastructure/adr-138-bake-algo-extension-into-wrapper-image.md); the snippet below is illustrative.

```dockerfile
FROM --platform=linux/amd64 python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv and Python dependencies from pyproject.toml / uv.lock
COPY pyproject.toml uv.lock ./
RUN pip install uv && \
    uv sync --frozen --no-dev

# Copy application
COPY src/ ./src/

# Bake algo extension binary into image (ADR-138).
# Path uses 25.9.0 — Ryugraph native library build version, NOT wheel version.
RUN mkdir -p /root/.ryu/extension/25.9.0/linux_amd64/algo
COPY libalgo.ryu_extension \
    /root/.ryu/extension/25.9.0/linux_amd64/algo/libalgo.ryu_extension

EXPOSE 8000

CMD ["uvicorn", "wrapper.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Pod Spec (from Control Plane)

See [system.architecture.design.md](--/system-design/system.architecture.design.md#kubernetes-resources-per-instance) for the complete Pod specification.

---

## Testing

### Unit Tests

```python
# tests/unit/test_control_plane_client.py
import pytest
from unittest.mock import AsyncMock, patch
from wrapper.clients.control_plane import ControlPlaneClient


class TestRecordActivity:
    """Tests for the record_activity method.

    Note: ADR-104 — service-to-service calls use plain HTTP with no auth token
    and no X-Component header. The client is httpx-based (not aiohttp).
    """

    @pytest.fixture
    def client(self):
        return ControlPlaneClient(
            base_url="http://control-plane.test",
            instance_id="inst-123",
        )

    @pytest.mark.asyncio
    async def test_record_activity_success(self, client):
        """Activity recording should succeed with 204 response."""
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {}

            # record_activity takes no arguments — instance_id is captured
            # in the constructor.
            await client.record_activity()

            mock_request.assert_awaited_once_with(
                "POST", "/api/internal/instances/inst-123/activity"
            )

    @pytest.mark.asyncio
    async def test_record_activity_failure_logs_warning(self, client, caplog):
        """Activity recording failure should log warning, not raise."""
        from wrapper.exceptions import ControlPlaneError

        with patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = ControlPlaneError("boom", status_code=500)

            # Should not raise (fire-and-forget)
            await client.record_activity()

            assert "Failed to record activity" in caplog.text
```

### Integration Tests

```python
# tests/integration/test_activity_recording.py
import pytest
import asyncio
from httpx import AsyncClient
from wrapper.main import app


class TestActivityRecordingIntegration:
    """Integration tests for activity recording on endpoints."""

    @pytest.fixture
    async def client(self):
        async with AsyncClient(app=app, base_url="http://test") as client:
            yield client

    # Per ADR-104/105, identity is carried via X-Username (set by the edge
    # proxy in production, by the SDK in tests). There is no Bearer token
    # and no X-Component header on inbound wrapper requests.

    @pytest.mark.asyncio
    async def test_query_records_activity(self, client, mock_cp_client):
        """POST /query should trigger activity recording."""
        response = await client.post(
            "/query",
            json={"cypher": "MATCH (n) RETURN n LIMIT 1"},
            headers={"X-Username": "test-user@example.com"},
        )

        assert response.status_code == 200
        # Verify activity was recorded (async, so may need small delay).
        # record_activity() takes no arguments — instance_id is captured
        # in the ControlPlaneClient constructor.
        await asyncio.sleep(0.1)
        mock_cp_client.record_activity.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_algorithm_records_activity(self, client, mock_cp_client):
        """POST /algo/{name} should trigger activity recording."""
        response = await client.post(
            "/algo/pagerank",
            json={"node_label": "Customer", "property_name": "pr"},
            headers={"X-Username": "test-user@example.com"},
        )

        assert response.status_code == 200
        await asyncio.sleep(0.1)
        mock_cp_client.record_activity.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_networkx_records_activity(self, client, mock_cp_client):
        """POST /networkx/{name} should trigger activity recording."""
        response = await client.post(
            "/networkx/betweenness_centrality",
            json={"node_label": "Customer", "property_name": "bc"},
            headers={"X-Username": "test-user@example.com"},
        )

        assert response.status_code == 200
        await asyncio.sleep(0.1)
        mock_cp_client.record_activity.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_subgraph_records_activity(self, client, mock_cp_client):
        """POST /subgraph should trigger activity recording."""
        response = await client.post(
            "/subgraph",
            json={"cypher": "MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 10"},
            headers={"X-Username": "test-user@example.com"},
        )

        assert response.status_code == 200
        await asyncio.sleep(0.1)
        mock_cp_client.record_activity.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_activity_failure_does_not_fail_request(self, client, mock_cp_client):
        """Activity recording failure should not fail the main request."""
        mock_cp_client.record_activity.side_effect = Exception("Network error")

        response = await client.post(
            "/query",
            json={"cypher": "MATCH (n) RETURN n LIMIT 1"},
            headers={"X-Username": "test-user@example.com"},
        )

        # Request should still succeed
        assert response.status_code == 200


@pytest.fixture
def mock_cp_client(monkeypatch):
    """Mock the Control Plane client for testing."""
    mock = AsyncMock()
    mock.record_activity = AsyncMock()
    monkeypatch.setattr("wrapper.dependencies.get_cp_client", lambda: mock)
    return mock
```

### Test Coverage Requirements

| Component | Coverage Target | Key Test Scenarios |
|-----------|-----------------|-------------------|
| `ControlPlaneClient.record_activity` | 100% | Success, failure logging (fire-and-forget, no args) |
| Query Router | 90% | Activity recorded, fire-and-forget behavior |
| Algorithm Router | 90% | Activity recorded on start, lock handling |
| NetworkX Router | 90% | Activity recorded, algorithm discovery |
| Subgraph Router | 90% | Activity recorded, graph extraction |

---

## Anti-Patterns

### Architectural

See [architectural.guardrails.md](--/foundation/architectural.guardrails.md#anti-patterns-must-not-do) for the authoritative list. Key sections relevant to Ryugraph Wrapper:

- **Concurrency & Pod Lifecycle** - Single Ryugraph process per pod, no concurrent algorithms, no shared connections
- **Data Handling & GCS** - No structure modification after creation, no algorithm results in GCS
- **Component Communication** - Lock state queried from pod directly, not stored in Control Plane

### Component-Specific

These constraints are specific to the Ryugraph/Python implementation:

- DO NOT use Ryugraph Connection across multiple asyncio tasks (not thread-safe)
- DO NOT hold Ryugraph connections open during algorithm execution (release to pool)
- DO NOT cache NetworkX graph objects between requests (memory management)

---

## Open Questions

See [decision.log.md](--/process/decision.log.md) for:

- OQ-011: WebSocket for algorithm progress (vs polling)
- OQ-012: Algorithm cancellation support
