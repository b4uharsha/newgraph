---
title: "Background Jobs and Execution Sequence"
scope: hsbc
---

# Background Jobs and Execution Sequence

The control-plane runs six background jobs via APScheduler. All jobs run in-process (no external scheduler) and are configured to `coalesce=True` (combine missed executions) and `max_instances=1` (no concurrent execution of the same job).

---

## Job Inventory

| Job | Default Interval | Configurable | Purpose |
|---|---|---|---|
| **Reconciliation** | 300s (5 min) | `GRAPH_OLAP_RECONCILIATION_JOB_INTERVAL_SECONDS` | Detect and clean up orphaned wrapper pods; reconcile DB state with K8s state |
| **Lifecycle** | 300s (5 min) | `GRAPH_OLAP_LIFECYCLE_JOB_INTERVAL_SECONDS` | Enforce snapshot TTL and instance inactivity timeouts |
| **Instance Orchestration** | 5s | `GRAPH_OLAP_INSTANCE_ORCHESTRATION_JOB_INTERVAL_SECONDS` | Transition instances from `waiting_for_snapshot` to `starting` when their snapshot becomes `ready` |
| **Export Reconciliation** | 5s | *(hardcoded)* | Recover from export worker crashes; re-claim stale export jobs |
| **Schema Cache** | 86400s (24h) | `GRAPH_OLAP_SCHEMA_CACHE_JOB_INTERVAL_SECONDS` | Refresh Starburst schema metadata cache |
| **Resource Monitor** | 60s | *(hardcoded)* | Monitor wrapper pod memory usage; trigger proactive resize if `sizing_enabled=true` |

---

## End-to-End Flow: Mapping to Queryable Graph

The following sequence shows all jobs involved when a user creates a mapping and queries a graph.

![diagram-1](diagrams/job-sequence/diagram-1.svg)

<details>
<summary>Mermaid Source</summary>

```mermaid
sequenceDiagram
    participant User as Analyst (SDK)
    participant CP as Control Plane
    participant DB as PostgreSQL
    participant EW as Export Worker
    participant SB as Starburst
    participant GCS as GCS Bucket
    participant K8s as Kubernetes
    participant WP as Wrapper Pod

    Note over User,WP: Phase 1: Create Mapping
    User->>CP: POST /api/mappings
    CP->>DB: INSERT mapping (status: draft)
    CP-->>User: mapping_id

    Note over User,WP: Phase 2: Create Snapshot (triggers export)
    User->>CP: POST /api/instances (from mapping)
    CP->>DB: INSERT snapshot (status: pending)
    CP->>DB: INSERT instance (status: waiting_for_snapshot)
    CP->>DB: INSERT export_job (status: pending)
    CP-->>User: instance_id

    Note over User,WP: Phase 3: Export Worker Claims Job
    loop Every 5s (poll_interval)
        EW->>CP: POST /api/internal/export-jobs/claim
        CP->>DB: SELECT ... FOR UPDATE SKIP LOCKED
        CP-->>EW: claimed export_job(s)
    end
    EW->>CP: PATCH /api/internal/export-jobs/{id} (status=submitted)
    CP->>DB: UPDATE snapshot SET status=creating (on first job)
    CP->>DB: UPDATE export_job SET status=submitted

    Note over User,WP: Phase 4: Data Export (async submit + poll)
    EW->>SB: Submit UNLOAD query (async)
    loop Poll cycle
        EW->>CP: GET /api/internal/export-jobs/pollable
        CP-->>EW: jobs where next_poll_at <= now
        EW->>SB: Poll query status
    end
    SB-->>EW: Query complete, Parquet written to GCS
    EW->>CP: PATCH /api/internal/export-jobs/{id} (status=completed)
    Note over CP: Export Reconciliation job detects all jobs complete
    CP->>CP: _finalize_snapshots()
    CP->>DB: UPDATE snapshot SET status=ready, node_counts/edge_counts, size_bytes

    Note over User,WP: Phase 5: Instance Orchestration Job
    loop Every 5s (instance_orchestration)
        CP->>DB: SELECT instances WHERE status=waiting_for_snapshot
        CP->>DB: Check snapshot status
        Note over CP: Snapshot is ready → transition instance
        CP->>DB: UPDATE instance SET status=starting
        CP->>K8s: Create wrapper Pod + Service
    end

    Note over User,WP: Phase 6: Wrapper Pod Startup
    K8s->>WP: Pod starts
    WP->>GCS: Download Parquet files
    WP->>WP: Load graph into memory/disk
    WP->>CP: POST /api/internal/wrappers/{id}/ready
    CP->>DB: UPDATE instance SET status=running

    Note over User,WP: Phase 7: Query
    User->>CP: POST /api/instances/{id}/query
    CP->>WP: Proxy query to wrapper pod
    WP-->>CP: Query results
    CP-->>User: Results
```

</details>

---

## Job Dependency Diagram

![diagram-2](diagrams/job-sequence/diagram-2.svg)

<details>
<summary>Mermaid Source</summary>

```mermaid
flowchart TD
    subgraph "Triggered by User Action"
        A[POST /api/instances] --> B[export_job created<br/>status: pending]
    end

    subgraph "Export Worker Loop (5s)"
        B --> C[POST /api/internal/export-jobs/claim]
        C --> CS[Snapshot: pending → creating<br/>on first claimed job]
        CS --> D[Submit UNLOAD to Starburst]
        D --> DP[GET /api/internal/export-jobs/pollable]
        DP --> E[Starburst writes Parquet to GCS]
        E --> F[Mark export job complete]
    end

    subgraph "Export Reconciliation (5 min)"
        F --> FR[_finalize_snapshots: all jobs complete?]
        FR --> G[Snapshot: creating → ready<br/>+ aggregated counts]
    end

    subgraph "Instance Orchestration (5s)"
        G --> H[Detect waiting instances<br/>with ready snapshots]
        H --> I[Create K8s Pod]
        I --> J[Instance → starting]
    end

    subgraph "Wrapper Pod Startup"
        J --> K[Download Parquet from GCS]
        K --> L[Load graph]
        L --> M[Report ready to CP]
        M --> N[Instance → running]
    end

    subgraph "Reconciliation (5 min)"
        O[Reconciliation Job] --> P[Find orphaned pods<br/>not in DB]
        O --> Q[Find DB instances<br/>with no pod]
        P --> R[Delete orphan pods]
        Q --> S[Mark instances failed]
    end

    subgraph "Lifecycle (5 min)"
        T[Lifecycle Job] --> U[Find expired snapshots<br/>created_at + TTL < now]
        T --> V[Find inactive instances<br/>last_accessed + timeout < now]
        U --> W[Delete expired snapshots<br/>+ cascade instances]
        V --> X[Terminate idle instances]
    end

    subgraph "Schema Cache (24h)"
        Y[Schema Cache Job] --> Z[Refresh Starburst<br/>catalog/schema/table metadata]
    end

    subgraph "Resource Monitor (60s)"
        AA[Resource Monitor] --> AB[Check wrapper pod<br/>memory usage]
        AB --> AC[Trigger resize<br/>if near limit]
    end
```

</details>

---

## Recommended Interval Tuning

For a production environment with moderate usage (10-20 analysts, 5-10 concurrent instances):

| Job | Default | Recommended | Rationale |
|---|---|---|---|
| Reconciliation | 300s | 300s | Fine — runs infrequently, catches drift |
| Lifecycle | 300s | 300s | Fine — TTL is in hours, 5-min check is adequate |
| Instance Orchestration | 5s | 30s | Reduces DB polling; instances start 25s slower worst case |
| Export Reconciliation | 5s (hardcoded) | 30s (requires code change) | Same rationale as orchestration |
| Schema Cache | 86400s | 86400s | Metadata changes rarely; manual refresh available via API |
| Resource Monitor | 60s (hardcoded) | 60s | Reasonable for monitoring memory |

To apply:

```bash
# In the control-plane Deployment env vars:
GRAPH_OLAP_INSTANCE_ORCHESTRATION_JOB_INTERVAL_SECONDS=30
GRAPH_OLAP_RECONCILIATION_JOB_INTERVAL_SECONDS=300
GRAPH_OLAP_LIFECYCLE_JOB_INTERVAL_SECONDS=300
GRAPH_OLAP_SCHEMA_CACHE_JOB_INTERVAL_SECONDS=86400
```
