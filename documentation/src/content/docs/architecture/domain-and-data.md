---
title: "Graph OLAP Platform - Domain & Data Architecture"
scope: hsbc
---

# Graph OLAP Platform - Domain & Data Architecture

**Document Type:** Domain & Data Architecture Specification
**Version:** 1.0
**Status:** Ready for Architectural Review
**Author:** Graph OLAP Platform Team
**Last Updated:** 2026-02-03

---

## Document Structure

This architecture documentation is organized into five focused documents:

| Document | Content |
|----------|---------|
| [Detailed Architecture](detailed-architecture.md) | Executive Summary + C4 Architecture Viewpoints + Resource Management |
| [SDK Architecture](sdk-architecture.md) | Python SDK, Resource Managers, Authentication |
| **This document** | Domain Model, State Machines, Data Flows |
| [Platform Operations](platform-operations.md) | Technology, Security, Integration, Operations, NFRs |
| [Authorization & Access Control](authorization.md) | RBAC Roles, Permission Matrix, Ownership Model, Enforcement |

---

## 2. Domain Model

This section describes the domain model using Domain-Driven Design (DDD) principles, including bounded contexts, aggregates, and state machines.

### 2.1 Bounded Context Overview

The Graph OLAP Platform operates within a single bounded context focused on **Graph Analytics Resource Management**.

<img src="/architecture/diagrams/detailed-architecture/graph-olap-platform-bounded-context.svg" alt="Graph OLAP Platform Bounded Context" width="90%">

<details>
<summary>Mermaid Source</summary>

```mermaid
---
config:
  layout: elk
---
flowchart TB
    accTitle: Graph OLAP Platform Bounded Context
    accDescr: Shows the bounded context with core aggregates and their relationships

    classDef context fill:#E3F2FD,stroke:#1565C0,stroke-width:3px,color:#0D47A1
    classDef aggregate fill:#E8F5E9,stroke:#2E7D32,stroke-width:2px,color:#1B5E20
    classDef entity fill:#FFF8E1,stroke:#F57F17,stroke-width:2px,color:#E65100
    classDef external fill:#ECEFF1,stroke:#455A64,stroke-width:2px,color:#263238

    subgraph BC["Graph Analytics Resource Management Context"]
        subgraph MappingAgg["Mapping Aggregate"]
            Mapping["Mapping<br/>(Aggregate Root)"]:::aggregate
            MappingVersion["MappingVersion<br/>(Entity)"]:::entity
            NodeDef["NodeDefinition<br/>(Value Object)"]:::entity
            EdgeDef["EdgeDefinition<br/>(Value Object)"]:::entity
        end

        subgraph SnapshotAgg["Snapshot Aggregate"]
            Snapshot["Snapshot<br/>(Aggregate Root)"]:::aggregate
            ExportJob["ExportJob<br/>(Entity)"]:::entity
        end

        subgraph InstanceAgg["Instance Aggregate"]
            Instance["Instance<br/>(Aggregate Root)"]:::aggregate
            AlgorithmLock["AlgorithmLock<br/>(Value Object)"]:::entity
        end

        User["User<br/>(Entity)"]:::entity
        Favorite["Favorite<br/>(Entity)"]:::entity
    end

    subgraph External["External Systems"]
        Starburst["Starburst<br/>Data Source"]:::external
        K8s["Kubernetes<br/>Pod Runtime"]:::external
        GCS["GCS<br/>Snapshot Storage"]:::external
    end

    Mapping --> MappingVersion
    MappingVersion --> NodeDef
    MappingVersion --> EdgeDef
    Snapshot --> ExportJob
    Instance --> AlgorithmLock
    User --> Mapping
    User --> Snapshot
    User --> Instance
    User --> Favorite

    MappingVersion -.->|"validates against"| Starburst
    Instance -.->|"runs as"| K8s
    ExportJob -.->|"writes to"| GCS
```

</details>

### 2.2 Core Aggregates

#### 2.2.1 Mapping Aggregate

The **Mapping** aggregate defines the graph structure and is the foundation for all downstream operations.

<img src="/architecture/diagrams/detailed-architecture/mapping-aggregate-structure.svg" alt="Mapping Aggregate Structure" width="70%">

<details>
<summary>Mermaid Source</summary>

```mermaid
---
config:
  layout: elk
---
flowchart TB
    accTitle: Mapping Aggregate Structure
    accDescr: Shows the Mapping aggregate root with MappingVersion entities and value objects

    classDef root fill:#E8F5E9,stroke:#2E7D32,stroke-width:3px,color:#1B5E20
    classDef entity fill:#E1F5FE,stroke:#0277BD,stroke-width:2px,color:#01579B
    classDef vo fill:#FFF8E1,stroke:#F57F17,stroke-width:2px,color:#E65100

    subgraph MappingAggregate["Mapping Aggregate"]
        Mapping["Mapping<br/>───────────<br/>id: int<br/>name: string<br/>owner: User<br/>current_version: int<br/>ttl: duration<br/>inactivity_timeout: duration"]:::root

        subgraph Versions["Versions (immutable)"]
            V1["MappingVersion v1<br/>───────────<br/>change_description<br/>created_at"]:::entity
            V2["MappingVersion v2<br/>───────────<br/>change_description<br/>created_at"]:::entity
            VN["MappingVersion vN<br/>(current)"]:::entity
        end

        subgraph NodeDefs["Node Definitions"]
            Node1["NodeDefinition<br/>───────────<br/>label: Customer<br/>sql: SELECT...<br/>primary_key: id"]:::vo
            Node2["NodeDefinition<br/>───────────<br/>label: Product<br/>sql: SELECT...<br/>primary_key: id"]:::vo
        end

        subgraph EdgeDefs["Edge Definitions"]
            Edge1["EdgeDefinition<br/>───────────<br/>type: PURCHASED<br/>sql: SELECT...<br/>source: Customer<br/>target: Product"]:::vo
        end
    end

    Mapping --> V1
    Mapping --> V2
    Mapping --> VN
    VN --> Node1
    VN --> Node2
    VN --> Edge1
```

</details>

**Invariants:**
- A Mapping must have at least one version
- Versions are immutable once created
- The `current_version` always points to the latest version
- Each NodeDefinition must have a unique label within the mapping
- Each EdgeDefinition's source/target must reference existing NodeDefinitions

#### 2.2.2 Snapshot Aggregate

The **Snapshot** aggregate represents a point-in-time data export from Starburst. Snapshots are created implicitly when users create instances via `create_from_mapping()` and are not directly exposed through public APIs. Users interact with instances directly; the platform manages snapshot lifecycle automatically.

<img src="/architecture/diagrams/detailed-architecture/snapshot-aggregate-structure.svg" alt="Snapshot Aggregate Structure" width="100%">

<details>
<summary>Mermaid Source</summary>

```mermaid
---
config:
  layout: elk
---
flowchart TB
    accTitle: Snapshot Aggregate Structure
    accDescr: Shows the Snapshot aggregate root with ExportJob entities

    classDef root fill:#E8F5E9,stroke:#2E7D32,stroke-width:3px,color:#1B5E20
    classDef entity fill:#E1F5FE,stroke:#0277BD,stroke-width:2px,color:#01579B
    classDef vo fill:#FFF8E1,stroke:#F57F17,stroke-width:2px,color:#E65100

    subgraph SnapshotAggregate["Snapshot Aggregate"]
        Snapshot["Snapshot<br/>───────────<br/>id: int<br/>mapping_id: int<br/>mapping_version: int<br/>owner: User<br/>status: SnapshotStatus<br/>gcs_path: string<br/>size_bytes: int"]:::root

        subgraph Jobs["Export Jobs"]
            NodeJob1["ExportJob (node)<br/>───────────<br/>entity: Customer<br/>status: completed<br/>row_count: 50000"]:::entity
            NodeJob2["ExportJob (node)<br/>───────────<br/>entity: Product<br/>status: completed<br/>row_count: 10000"]:::entity
            EdgeJob1["ExportJob (edge)<br/>───────────<br/>entity: PURCHASED<br/>status: submitted<br/>poll_count: 5"]:::entity
        end

        subgraph Counts["Aggregated Counts"]
            NodeCounts["node_counts<br/>───────────<br/>Customer: 50000<br/>Product: 10000"]:::vo
            EdgeCounts["edge_counts<br/>───────────<br/>PURCHASED: 150000"]:::vo
        end
    end

    Snapshot --> NodeJob1
    Snapshot --> NodeJob2
    Snapshot --> EdgeJob1
    Snapshot --> NodeCounts
    Snapshot --> EdgeCounts
```

</details>

**Invariants:**
- A Snapshot is immutable once status = `ready`
- All ExportJobs must complete (success or failure) before Snapshot can transition
- GCS path follows structure: `{owner}/{mapping_id}/v{version}/{snapshot_id}/`
- If any ExportJob fails, Snapshot status = `failed`
- Snapshot status can also be `cancelled` if the export is explicitly cancelled before completion

#### 2.2.3 Instance Aggregate

The **Instance** aggregate represents a running graph database pod. Instances are created via `POST /api/instances` with a `mapping_id`; the platform creates the required snapshot implicitly and transitions the instance through `waiting_for_snapshot` -> `starting` -> `running` states.

<img src="/architecture/diagrams/detailed-architecture/instance-aggregate-structure.svg" alt="Instance Aggregate Structure" width="100%">

<details>
<summary>Mermaid Source</summary>

```mermaid
---
config:
  layout: elk
---
flowchart TB
    accTitle: Instance Aggregate Structure
    accDescr: Shows the Instance aggregate root with algorithm locking mechanism

    classDef root fill:#E8F5E9,stroke:#2E7D32,stroke-width:3px,color:#1B5E20
    classDef entity fill:#E1F5FE,stroke:#0277BD,stroke-width:2px,color:#01579B
    classDef vo fill:#FFF8E1,stroke:#F57F17,stroke-width:2px,color:#E65100

    subgraph InstanceAggregate["Instance Aggregate"]
        Instance["Instance<br/>───────────<br/>id: int<br/>snapshot_id: int<br/>pending_snapshot_id: int?<br/>owner: User<br/>status: InstanceStatus<br/>pod_name: string<br/>instance_url: string<br/>wrapper_type: string<br/>cpu_cores: int<br/>last_activity_at: timestamp"]:::root

        subgraph Lock["Algorithm Lock"]
            AlgoLock["AlgorithmLock<br/>───────────<br/>algorithm_name: pagerank<br/>locked_at: timestamp<br/>locked_by: user<br/>progress: 45%<br/>result_key: uuid"]:::vo
        end

        subgraph PodInfo["Pod Information"]
            PodStatus["Pod Status<br/>───────────<br/>phase: Running<br/>ready: true<br/>restarts: 0"]:::vo
            Resources["Resources<br/>───────────<br/>memory_used: 3.2Gi<br/>cpu_cores: 2"]:::vo
        end

        subgraph Events["Instance Events"]
            EventLog["InstanceEvent<br/>───────────<br/>event_type: cpu_update<br/>details: {from: 2, to: 4}<br/>created_at: timestamp"]:::vo
        end
    end

    Instance --> AlgoLock
    Instance --> PodStatus
    Instance --> Resources
    Instance --> EventLog
```

</details>

**Invariants:**
- Only one algorithm can hold the lock at a time
- Lock automatically releases after algorithm completion or timeout
- Instance URL is only valid when status = `running`
- `last_activity_at` updates on every query or algorithm execution
- `pending_snapshot_id` is set only when status = `waiting_for_snapshot`
- `cpu_cores` can only be updated when status = `running` (K8s in-place resize)
- Instance events record resource changes (CPU updates, memory upgrades, OOM recoveries)

### 2.3 State Machines

#### 2.3.1 Snapshot State Machine

<img src="/architecture/diagrams/detailed-architecture/snapshot-state-machine.svg" alt="Snapshot State Machine" width="94%">

<details>
<summary>Mermaid Source</summary>

```mermaid
stateDiagram-v2
    accTitle: Snapshot State Machine
    accDescr: Shows snapshot lifecycle from creation through export to ready or failed state

    [*] --> pending: Snapshot created internally

    pending --> creating: Export jobs created

    creating --> ready: All jobs completed successfully
    creating --> failed: Any job failed
    creating --> cancelled: Export cancelled

    ready --> [*]: Snapshot available for use
    failed --> [*]: Snapshot unusable
    cancelled --> [*]: Snapshot discarded

    note right of pending
        Snapshot record created
        No export jobs yet
    end note

    note right of creating
        Export jobs running
        KEDA scales workers
    end note

    note right of ready
        All Parquet files in GCS
        Instance can be created
    end note
```

</details>

**State Transitions:**

| From | To | Trigger | Action |
|------|-----|---------|--------|
| `pending` | `creating` | Export jobs created | Workers claim jobs |
| `creating` | `ready` | All jobs completed | Calculate totals |
| `creating` | `failed` | Any job failed | Record error |
| `creating` | `cancelled` | Export cancelled | Record cancellation |

#### 2.3.2 Instance State Machine

<img src="/architecture/diagrams/detailed-architecture/instance-state-machine.svg" alt="Instance State Machine" width="94%">

<details>
<summary>Mermaid Source</summary>

```mermaid
stateDiagram-v2
    accTitle: Instance State Machine
    accDescr: Shows instance lifecycle from user request through snapshot export to running

    [*] --> waiting_for_snapshot: POST /api/instances (with mapping_id)

    waiting_for_snapshot --> starting: Snapshot ready
    waiting_for_snapshot --> failed: Snapshot export failed

    starting --> running: Pod ready, data loaded
    starting --> failed: Pod failed to start or load data

    running --> stopping: User stops or TTL expired
    running --> failed: Pod crashed

    stopping --> [*]: Pod terminated

    failed --> [*]

    note right of waiting_for_snapshot
        Instance created from mapping
        Snapshot export in progress
    end note

    note right of starting
        Pod created, loading Parquet from GCS
    end note

    note right of running
        Ready for queries
        Algorithm lock available
        CPU can be updated via PUT /cpu
    end note

    note right of stopping
        Graceful shutdown
        Releasing resources
        Row deleted on completion
    end note
```

</details>

**State Transitions:**

| From | To | Trigger | Action |
|------|-----|---------|--------|
| (initial) | `waiting_for_snapshot` | POST /api/instances with mapping_id | Create snapshot, queue instance |
| `waiting_for_snapshot` | `starting` | Snapshot status = `ready` | Orchestration job creates pod |
| `waiting_for_snapshot` | `failed` | Snapshot status = `failed` | Record snapshot error |
| `starting` | `running` | Pod ready + data loaded | Update instance_url |
| `starting` | `failed` | Pod error or timeout | Record error |
| `running` | `stopping` | User request or TTL | Call /shutdown |
| `running` | `failed` | Pod crash | Reconciliation detects |
| `stopping` | (deleted) | Pod terminated | Row deleted from DB |

#### 2.3.3 Export Job State Machine

<img src="/architecture/diagrams/detailed-architecture/export-job-state-machine.svg" alt="Export Job State Machine" width="94%">

<details>
<summary>Mermaid Source</summary>

```mermaid
stateDiagram-v2
    accTitle: Export Job State Machine
    accDescr: Shows export job lifecycle with crash recovery paths

    [*] --> pending: Snapshot created

    pending --> claimed: Worker claims job

    claimed --> pending: Lease expired (>10min)
    claimed --> submitted: Starburst accepts query
    claimed --> failed: Starburst rejects

    submitted --> submitted: Poll returns RUNNING
    submitted --> completed: Poll returns FINISHED
    submitted --> failed: Poll returns FAILED
    submitted --> pending: Orphaned >10min (reconciliation)

    completed --> [*]
    failed --> [*]

    note right of pending
        KEDA scales workers
        based on pending count
    end note

    note right of claimed
        10-minute lease timeout
        claimed_by = worker pod name
    end note

    note right of submitted
        Fibonacci backoff polling
        2s, 3s, 5s, 8s... max 90s
    end note
```

</details>

### 2.4 Invariants & Business Rules

#### Cross-Aggregate Rules

| Rule | Description | Enforcement |
|------|-------------|-------------|
| **Snapshot-Mapping Binding** | Snapshot must reference valid Mapping + Version | Database FK constraint |
| **Instance-Snapshot Binding** | Running instance requires `snapshot_id` with `ready` snapshot; `waiting_for_snapshot` uses `pending_snapshot_id` | Service layer validation |
| **Ownership Consistency** | Analyst: Snapshot/Instance owner must match Mapping owner. Admin/Ops: ownership check bypassed (role-based override) | Service layer authorization |
| **Version Immutability** | MappingVersion cannot be modified after creation | No UPDATE operations |
| **Algorithm Lock Exclusivity** | Only one algorithm per instance at a time | Optimistic locking with version |

#### Lifecycle Rules

| Rule | Description | Default |
|------|-------------|---------|
| **Snapshot TTL** | Snapshots auto-delete after TTL | 7 days |
| **Instance TTL** | Instances auto-stop after TTL | 24 hours |
| **Instance Inactivity** | Instances auto-stop after inactivity | 4 hours |
| **Export Job Timeout** | Jobs fail after max duration | 1 hour |
| **Claim Lease** | Claimed jobs reset after lease expires | 10 minutes |

#### Supporting Domain Concepts

The platform includes additional domain concepts that support the core aggregates:

| Concept | Description | Purpose |
|---------|-------------|---------|
| **Schema Metadata Cache** | In-memory cache of Starburst catalog/schema/table/column metadata | Enables fast SQL validation and autocomplete without Starburst round-trips |
| **Background Job Scheduler** | APScheduler-based periodic job execution | Runs reconciliation, lifecycle, export reconciliation, schema cache refresh, instance orchestration, and resource monitoring |
| **Instance Orchestration** | Background job transitioning `waiting_for_snapshot` instances to `starting` | Decouples instance creation from snapshot completion |
| **Resource Monitor** | Background job for dynamic memory monitoring | Enables proactive OOM prevention via memory tier upgrades |
| **Global Configuration** | Key-value store for platform-wide settings | Configurable export max duration, concurrency limits, default TTLs |

### 2.5 Authorization & Ownership

All resources (Mappings, Snapshots, Instances) carry an `owner: User` property assigned at creation time. Ownership interacts with the platform's hierarchical RBAC model:

| Role | Own Resources | Other Users' Resources | Deletion |
|------|--------------|----------------------|----------|
| **Analyst** | Full CRUD | Read only | Own only |
| **Admin** | Full CRUD | Full CRUD (ownership bypass) | Any resource + bulk delete |
| **Ops** | All Admin capabilities | All Admin capabilities | Any resource + bulk delete |

**Role Hierarchy:** `Analyst < Admin < Ops` (strict superset). See [Authorization & Access Control](authorization.md) for the complete specification.

### 2.6 Deletion Dependency Chain

Resources must be deleted in the correct order to maintain referential integrity. Analyst users may only delete resources they own; Admin and Ops users may delete any resource.

<img src="/architecture/diagrams/detailed-architecture/deletion-dependency-chain.svg" alt="Deletion Dependency Chain" width="45%">

<details>
<summary>Mermaid Source</summary>

```mermaid
---
config:
  layout: elk
---
flowchart TB
    accTitle: Deletion Dependency Chain
    accDescr: Shows the order in which resources must be deleted to maintain referential integrity

    classDef level1 fill:#FFCDD2,stroke:#C62828,stroke-width:2px,color:#B71C1C
    classDef level2 fill:#FFF9C4,stroke:#F9A825,stroke-width:2px,color:#F57F17
    classDef level3 fill:#C8E6C9,stroke:#2E7D32,stroke-width:2px,color:#1B5E20
    classDef storage fill:#E3F2FD,stroke:#1565C0,stroke-width:2px,color:#0D47A1

    subgraph Level1["Level 1: Must Delete First"]
        Instance["Instance<br/>(Delete pod)"]:::level1
        AlgoLock["Algorithm Lock<br/>(Release)"]:::level1
    end

    subgraph Level2["Level 2: After Instances Deleted"]
        Snapshot["Snapshot<br/>(Delete record)"]:::level2
        ExportJobs["Export Jobs<br/>(Delete records)"]:::level2
    end

    subgraph Level3["Level 3: After Snapshots Deleted"]
        Mapping["Mapping<br/>(Delete record)"]:::level3
        Versions["Mapping Versions<br/>(Cascade delete)"]:::level3
    end

    subgraph Storage["Storage Cleanup"]
        GCSFiles["GCS Parquet Files<br/>(Background cleanup)"]:::storage
    end

    Instance -->|"1. Stop pod"| Snapshot
    AlgoLock -->|"Released on delete"| Instance
    Snapshot -->|"2. Delete record"| Mapping
    ExportJobs -->|"Cascade"| Snapshot
    Versions -->|"Cascade"| Mapping
    Snapshot -->|"3. Async cleanup"| GCSFiles
```

</details>

**Deletion Order:**

1. **Instances** - Stop running pods, release algorithm locks
2. **Snapshots** - Delete snapshot records, cascade to export_jobs
3. **Mappings** - Delete mapping records, cascade to versions
4. **GCS Files** - Background job cleans up orphaned Parquet files

---

## 3. Data Architecture

### 3.1 Data Flow Overview

<img src="/architecture/diagrams/detailed-architecture/data-flow-architecture.svg" alt="Data Flow Architecture" width="17%">

<details>
<summary>Mermaid Source</summary>

```mermaid
---
config:
  layout: elk
---
flowchart LR
    accTitle: Data Flow Architecture
    accDescr: Shows the complete data flow from Starburst through export to graph instance

    classDef source fill:#ECEFF1,stroke:#455A64,stroke-width:2px,color:#263238
    classDef process fill:#E8F5E9,stroke:#2E7D32,stroke-width:2px,color:#1B5E20
    classDef storage fill:#FFF8E1,stroke:#F57F17,stroke-width:2px,color:#E65100
    classDef compute fill:#E1F5FE,stroke:#0277BD,stroke-width:2px,color:#01579B

    subgraph Source["Data Source"]
        Starburst["Starburst Galaxy<br/>Data Warehouse"]:::source
    end

    subgraph Export["Export Pipeline"]
        UNLOAD["UNLOAD Query<br/>───────────<br/>SQL → Parquet<br/>client_tags routing"]:::process
    end

    subgraph Storage["Object Storage"]
        GCS["GCS Bucket<br/>───────────<br/>nodes/{label}/*.parquet<br/>edges/{type}/*.parquet"]:::storage
    end

    subgraph Load["Load Pipeline"]
        COPY["COPY FROM<br/>───────────<br/>Parquet → Graph"]:::process
    end

    subgraph Instance["Graph Instance"]
        GraphDB["Graph Database<br/>───────────<br/>Node Tables<br/>Rel Tables"]:::compute
        Algorithms["Algorithm Engine<br/>───────────<br/>NetworkX / Native"]:::compute
    end

    Starburst -->|"1. Export Query"| UNLOAD
    UNLOAD -->|"2. Write Files"| GCS
    GCS -->|"3. Read Files"| COPY
    COPY -->|"4. Load Tables"| GraphDB
    GraphDB <-->|"5. In-Process"| Algorithms
```

</details>

### 3.2 Export Pipeline Sequence

Detailed temporal flow showing how data moves from user request through Starburst export to snapshot completion.

<img src="/architecture/diagrams/detailed-architecture/export-pipeline-sequence.svg" alt="Export Pipeline Sequence" width="100%">

<details>
<summary>Mermaid Source</summary>

```mermaid
sequenceDiagram
    accTitle: Export Pipeline Sequence
    accDescr: Shows the complete temporal flow from SDK instance-from-mapping request through KEDA scaling, job claiming, Starburst export, and finalization

    autonumber
    participant SDK as Jupyter SDK
    participant CP as Control Plane
    participant DB as Cloud SQL
    participant KEDA as KEDA Operator
    participant Worker as Export Worker
    participant SB as Starburst
    participant GCS

    rect rgb(227, 242, 253)
        Note over SDK,DB: Phase 1: Instance from Mapping Request
        SDK->>+CP: POST /api/instances {mapping_id, wrapper_type}
        CP->>DB: INSERT instance (status='waiting_for_snapshot')
        CP->>DB: INSERT snapshot (status='pending')
        CP->>DB: INSERT export_jobs (status='pending') × N
        CP-->>-SDK: 201 Created {instance_id, status: 'waiting_for_snapshot'}
    end

    rect rgb(232, 245, 233)
        Note over KEDA,Worker: Phase 2: KEDA Auto-Scaling
        loop Every 30 seconds
            KEDA->>DB: SELECT COUNT(*) WHERE status IN ('pending','claimed','submitted')
        end
        KEDA->>Worker: Scale Deployment 0 → N replicas
    end

    rect rgb(255, 248, 225)
        Note over Worker,DB: Phase 3: Atomic Job Claiming
        Worker->>+CP: POST /api/internal/export-jobs/claim
        Note right of CP: FOR UPDATE SKIP LOCKED
        CP->>DB: UPDATE status='claimed', claimed_by, claimed_at
        CP-->>-Worker: [{id, sql, columns, gcs_path}, ...]
    end

    rect rgb(225, 245, 254)
        Note over Worker,SB: Phase 4: Starburst Submission
        loop For each claimed job
            Worker->>+SB: POST /v1/statement (UNLOAD)<br/>X-Trino-Client-Tags: graph-olap-export
            Note right of SB: Routes to dedicated<br/>resource group
            SB-->>-Worker: {query_id, nextUri}
            Worker->>CP: PATCH {status='submitted', query_id, next_poll_at}
        end
    end

    rect rgb(236, 239, 241)
        Note over SB,GCS: Phase 5: Starburst Execution
        SB->>GCS: Write Parquet files (parallel)
    end

    rect rgb(243, 229, 245)
        Note over Worker,GCS: Phase 6: Stateless Polling
        Worker->>+CP: GET /api/internal/export-jobs/pollable
        CP-->>-Worker: Jobs where next_poll_at <= now

        loop For each pollable job
            Worker->>+SB: GET {nextUri}
            alt Query FINISHED
                SB-->>Worker: {state: FINISHED}
                Worker->>GCS: Count rows (Parquet metadata)
                Worker->>CP: PATCH {status='completed', row_count}
            else Query RUNNING
                SB-->>-Worker: {state: RUNNING}
                Worker->>CP: PATCH {next_poll_at += fibonacci}
            end
        end
    end

    rect rgb(200, 230, 201)
        Note over CP,DB: Phase 7: Snapshot Finalization + Instance Orchestration
        CP->>DB: All jobs completed?
        CP->>DB: UPDATE snapshot SET status='ready'
        Note over CP: Orchestration job detects snapshot ready
        CP->>DB: UPDATE instance SET status='starting', snapshot_id
    end

    rect rgb(236, 239, 241)
        Note over KEDA,Worker: Phase 8: Scale Down
        KEDA->>DB: SELECT COUNT(*) = 0
        KEDA->>Worker: Scale Deployment N → 0 replicas
    end

    Note over SDK: SDK polls GET /api/instances/{id}<br/>until status='running'
```

</details>

### 3.3 Instance Startup Flow

<img src="/architecture/diagrams/detailed-architecture/instance-startup-flow.svg" alt="Instance Startup Flow" width="100%">

<details>
<summary>Mermaid Source</summary>

```mermaid
sequenceDiagram
    accTitle: Instance Startup Flow (Orchestration)
    accDescr: Shows how orchestration job starts instance pod once snapshot is ready

    autonumber
    participant Orch as Orchestration Job
    participant CP as Control Plane
    participant DB as Cloud SQL
    participant K8s as Kubernetes API
    participant Pod as Wrapper Pod
    participant GCS

    Note over Orch,DB: Orchestration job runs every 5 seconds
    Orch->>DB: SELECT instances WHERE status='waiting_for_snapshot'
    DB-->>Orch: Instance with pending_snapshot_id
    Orch->>DB: Check snapshot status
    alt Snapshot status = 'ready'
        Orch->>DB: UPDATE instance SET status='starting', snapshot_id
        Orch->>K8s: Create Pod spec with GCS path
        K8s-->>Orch: Pod created (Pending)
    else Snapshot status = 'failed'
        Orch->>DB: UPDATE instance SET status='failed'
    end

    Note over K8s,Pod: Kubernetes schedules pod

    K8s->>Pod: Start container
    Pod->>Pod: Initialize graph database

    Pod->>+GCS: List Parquet files
    GCS-->>-Pod: File list

    loop For each node type
        Pod->>+GCS: Download node Parquet
        GCS-->>-Pod: Parquet data
        Pod->>Pod: COPY FROM Parquet
    end

    loop For each edge type
        Pod->>+GCS: Download edge Parquet
        GCS-->>-Pod: Parquet data
        Pod->>Pod: COPY FROM Parquet
    end

    Pod->>+CP: POST /api/internal/instances/{id}/ready
    CP->>CP: Update status='running', instance_url
    CP-->>-Pod: OK

    Note over CP: SDK polls GET /api/instances/{id}<br/>until status='running'
```

</details>

### 3.4 Algorithm Execution Flow (Implicit Locking)

<img src="/architecture/diagrams/detailed-architecture/algorithm-execution-with-implicit-lock.svg" alt="Algorithm Execution with Implicit Lock" width="100%">

<details>
<summary>Mermaid Source</summary>

```mermaid
sequenceDiagram
    accTitle: Algorithm Execution with Implicit Lock
    accDescr: Shows how algorithm execution acquires lock, runs algorithm, and releases lock

    autonumber
    participant SDK as Jupyter SDK
    participant Wrapper as Graph Wrapper
    participant DB as Embedded DB
    participant Algo as Algorithm Engine

    SDK->>+Wrapper: POST /algorithms/pagerank {params}

    Wrapper->>Wrapper: Acquire algorithm lock

    alt Lock acquired
        Wrapper->>+DB: Execute pre-query (if needed)
        DB-->>-Wrapper: Query results

        Wrapper->>+Algo: Run PageRank algorithm
        Note right of Algo: NetworkX or native<br/>depending on wrapper

        loop Progress updates
            Algo-->>Wrapper: Progress: 25%, 50%, 75%
            Wrapper->>Wrapper: Update lock progress
        end

        Algo-->>-Wrapper: Algorithm results

        Wrapper->>Wrapper: Release algorithm lock
        Wrapper-->>-SDK: 200 OK {results, execution_time}

    else Lock held by another
        Wrapper-->>SDK: 409 Conflict {lock_holder, algorithm}
    end
```

</details>

### 3.5 Entity Relationship Diagram

<img src="/architecture/diagrams/detailed-architecture/graph-olap-platform-data-model.svg" alt="Graph OLAP Platform Data Model" width="100%">

<details>
<summary>Mermaid Source</summary>

```mermaid
erDiagram
    accTitle: Graph OLAP Platform Data Model
    accDescr: Shows database schema with users, mappings, snapshots, instances and supporting tables

    USERS ||--o{ MAPPINGS : owns
    USERS ||--o{ SNAPSHOTS : owns
    USERS ||--o{ INSTANCES : owns
    USERS ||--o{ USER_FAVORITES : has
    USERS ||--o{ GLOBAL_CONFIG : updates

    MAPPINGS ||--|{ MAPPING_VERSIONS : has
    MAPPINGS ||--o{ SNAPSHOTS : sources

    MAPPING_VERSIONS ||--o{ SNAPSHOTS : references

    SNAPSHOTS ||--o{ INSTANCES : sources
    SNAPSHOTS ||--|{ EXPORT_JOBS : has

    INSTANCES ||--o{ INSTANCE_EVENTS : has

    USERS {
        string username PK
        string email UK
        string display_name
        string role
        boolean is_active
        timestamp created_at
        timestamp updated_at
    }

    MAPPINGS {
        int id PK
        string owner_username FK
        string name
        text description
        int current_version
        duration ttl
        duration inactivity_timeout
        timestamp created_at
    }

    MAPPING_VERSIONS {
        int mapping_id PK
        int version PK
        text change_description
        json node_definitions
        json edge_definitions
        timestamp created_at
        string created_by FK
    }

    SNAPSHOTS {
        int id PK
        int mapping_id FK
        int mapping_version FK
        string owner_username FK
        string name
        string gcs_path
        string status
        int size_bytes
        json node_counts
        json edge_counts
        timestamp created_at
    }

    INSTANCES {
        int id PK
        int snapshot_id FK
        int pending_snapshot_id FK
        string owner_username FK
        string wrapper_type
        string name
        string status
        string pod_name
        string instance_url
        int cpu_cores
        int memory_gb
        timestamp created_at
        timestamp last_activity_at
    }

    INSTANCE_EVENTS {
        int id PK
        int instance_id FK
        string event_type
        json details
        timestamp created_at
    }

    EXPORT_JOBS {
        int id PK
        int snapshot_id FK
        string job_type
        string entity_name
        string status
        string claimed_by
        timestamp claimed_at
        string starburst_query_id
        string next_uri
        timestamp next_poll_at
        int poll_count
        string gcs_path
        int row_count
        int size_bytes
        string error_message
    }

    USER_FAVORITES {
        string username PK
        string resource_type PK
        int resource_id PK
        timestamp created_at
    }

    GLOBAL_CONFIG {
        string key PK
        string value
        string description
        timestamp updated_at
        string updated_by FK
    }
```

</details>

### 3.6 Data Lifecycle

| Resource | Default TTL | Inactivity Timeout | Cleanup Mechanism |
|----------|-------------|-------------------|-------------------|
| **Mapping** | None | 30 days | Background job (lifecycle cleanup) |
| **Snapshot** | 7 days | 3 days | Background job + GCS cleanup |
| **Instance** | 24 hours | 4 hours | Background job + Pod deletion |
| **Export Job** | N/A | N/A | Cascade delete with snapshot |
| **GCS Files** | N/A | N/A | Orphan cleanup job |

### 3.7 GCS Storage Structure

```
gs://{bucket}/
└── {owner_username}/
    └── {mapping_id}/
        └── v{mapping_version}/
            └── {snapshot_id}/
                ├── nodes/
                │   ├── Customer/
                │   │   └── *.parquet (multiple files from parallel UNLOAD)
                │   └── Product/
                │       └── *.parquet
                └── edges/
                    ├── PURCHASED/
                    │   └── *.parquet
                    └── KNOWS/
                        └── *.parquet
```

---

## Related Documents

- **[Detailed Architecture](detailed-architecture.md)** - Executive Summary + C4 Architecture Viewpoints + Resource Management
- **[SDK Architecture](sdk-architecture.md)** - Python SDK, Resource Managers, Authentication
- **[Platform Operations](platform-operations.md)** - Technology, Security, Integration, Operations, NFRs
- **[Authorization & Access Control](authorization.md)** - RBAC role hierarchy, permission matrix, ownership model, enforcement architecture

---

*This is part of the Graph OLAP Platform architecture documentation. See also: [Detailed Architecture](detailed-architecture.md), [SDK Architecture](sdk-architecture.md), [Platform Operations](platform-operations.md), [Authorization](authorization.md).*
