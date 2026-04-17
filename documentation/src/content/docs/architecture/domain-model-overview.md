---
title: "Domain Model Overview"
scope: hsbc
---

# Domain Model Overview

## Overview

This document provides a comprehensive view of the Graph OLAP Platform domain model, following Domain-Driven Design (DDD) principles. It consolidates the business domain concepts, aggregates, entity relationships, state machines, and invariants that govern the platform.

## Prerequisites

- [requirements.md](--/foundation/requirements.md) - Functional requirements and resource definitions
- [data.model.spec.md](-/data.model.spec.md) - Database schema specification
- [system.architecture.design.md](-/system.architecture.design.md) - System architecture

---

## Business Domain

The Graph OLAP Platform enables **HSBC customer service analysts** to:

1. **Define graph schemas** from Starburst SQL queries (Mappings)
2. **Export point-in-time data** to GCS as Parquet files (Snapshots)
3. **Create graph instances** for interactive analysis (Instances)
4. **Run graph algorithms** (PageRank, Louvain, centrality, etc.)
5. **Share work** across teams (all resources visible to all analysts)

**Scale Characteristics:**

| Dimension | Expected Range |
|-----------|---------------|
| Analysts | Tens |
| Concurrent Instances | Hundreds |
| Graph Size | ≤2GB per instance |
| Instance Lifespan | <24 hours typical |

---

## Bounded Context

The platform operates within a **single bounded context**: the Graph Analytics Context.

![graph-olap-platform-bounded-context](diagrams/domain-model-overview/graph-olap-platform-bounded-context.svg)

<details>
<summary>Mermaid Source</summary>

```mermaid
---
config:
  layout: elk
---
flowchart TB
    accTitle: Graph OLAP Platform Bounded Context
    accDescr: Shows the single bounded context with core domain and supporting subdomains

    classDef context fill:#E3F2FD,stroke:#1565C0,stroke-width:3px,color:#0D47A1
    classDef core fill:#FFF8E1,stroke:#F57F17,stroke-width:2px,color:#E65100
    classDef supporting fill:#E8F5E9,stroke:#2E7D32,stroke-width:2px,color:#1B5E20
    classDef external fill:#ECEFF1,stroke:#455A64,stroke-width:2px,color:#263238

    subgraph BC["Graph Analytics Context (Bounded Context)"]
        direction TB

        subgraph Core["Core Domain"]
            M[Mapping<br/>Aggregate]:::core
            S[Snapshot<br/>Aggregate]:::core
            I[Instance<br/>Aggregate]:::core
        end

        subgraph Supporting["Supporting Subdomains"]
            LC[Lifecycle<br/>Management]:::supporting
            EX[Export<br/>Processing]:::supporting
            ALG[Algorithm<br/>Execution]:::supporting
            FAV[Favorites]:::supporting
        end
    end

    subgraph External["External Systems"]
        SB[Starburst]:::external
        GCS[Google Cloud<br/>Storage]:::external
        K8S[Kubernetes]:::external
        IDP[Identity<br/>Provider]:::external
    end

    Core --> Supporting
    EX --> SB
    EX --> GCS
    I --> GCS
    I --> K8S
    BC --> IDP

    class BC context
```

</details>

**Context Relationships:**

| External System | Relationship Type | Description |
|-----------------|------------------|-------------|
| Starburst | **Conformist** | We conform to Starburst's SQL dialect and UNLOAD semantics |
| GCS | **Published Language** | Standard Parquet format as interchange |
| Kubernetes | **Open Host Service** | We consume K8s API for pod management |
| Identity Provider | **Anti-Corruption Layer** | Auth headers translated to internal User model |

---

## Core Aggregates

The domain has three core aggregates forming a hierarchy: **Mapping → Snapshot → Instance**.

![core-aggregates-and-ownership](diagrams/domain-model-overview/core-aggregates-and-ownership.svg)

<details>
<summary>Mermaid Source</summary>

```mermaid
---
config:
  layout: elk
---
flowchart TB
    accTitle: Core Aggregates and Ownership
    accDescr: Shows the three core aggregates with User as identity and ownership relationships

    classDef user fill:#F3E5F5,stroke:#7B1FA2,stroke-width:2px,color:#4A148C
    classDef aggregate fill:#FFF8E1,stroke:#F57F17,stroke-width:3px,color:#E65100
    classDef entity fill:#E8F5E9,stroke:#2E7D32,stroke-width:2px,color:#1B5E20
    classDef valueobject fill:#E1BEE7,stroke:#6A1B9A,stroke-width:2px,color:#4A148C
    classDef external fill:#ECEFF1,stroke:#455A64,stroke-width:2px,color:#263238

    USER["User<br/>(Identity)"]:::user

    subgraph MappingAgg["Mapping Aggregate"]
        direction TB
        MAPPING["Mapping<br/>«Aggregate Root»"]:::aggregate
        MV["MappingVersion<br/>«Entity»"]:::entity
        ND["NodeDefinition<br/>«Value Object»"]:::valueobject
        ED["EdgeDefinition<br/>«Value Object»"]:::valueobject

        MAPPING -->|"1:N"| MV
        MV -->|"contains"| ND
        MV -->|"contains"| ED
    end

    subgraph SnapshotAgg["Snapshot Aggregate"]
        direction TB
        SNAPSHOT["Snapshot<br/>«Aggregate Root»"]:::aggregate
        EJ["ExportJob<br/>«Entity»"]:::entity
        GCSPATH["GCSPath<br/>«Value Object»"]:::valueobject

        SNAPSHOT -->|"1:N"| EJ
        SNAPSHOT -->|"has"| GCSPATH
    end

    subgraph InstanceAgg["Instance Aggregate"]
        direction TB
        INSTANCE["Instance<br/>«Aggregate Root»"]:::aggregate
        LOCK["AlgorithmLock<br/>«Value Object»<br/>(in-memory)"]:::valueobject
        PODSPEC["PodSpec<br/>«Value Object»"]:::valueobject

        INSTANCE -.->|"optional"| LOCK
        INSTANCE -->|"has"| PODSPEC
    end

    USER -->|"owns"| MAPPING
    USER -->|"owns"| SNAPSHOT
    USER -->|"owns"| INSTANCE

    MAPPING -.->|"referenced by"| SNAPSHOT
    MV -.->|"specific version"| SNAPSHOT
    SNAPSHOT -.->|"source for"| INSTANCE

    GCS["GCS Parquet Files"]:::external
    SNAPSHOT -->|"exports to"| GCS
    INSTANCE -->|"loads from"| GCS
```

</details>

### Aggregate Boundaries

| Aggregate | Root Entity | Contained Entities | Value Objects | Invariants |
|-----------|-------------|-------------------|---------------|------------|
| **Mapping** | Mapping | MappingVersion | NodeDefinition, EdgeDefinition | Versions immutable; delete blocked if snapshots exist |
| **Snapshot** | Snapshot | ExportJob | GCSPath, Progress | Delete blocked if active instances exist |
| **Instance** | Instance | — | AlgorithmLock (in-memory), PodSpec, Progress | One algorithm at a time (exclusive lock) |

---

## Aggregate Detail: Mapping

![mapping-aggregate-structure](diagrams/domain-model-overview/mapping-aggregate-structure.svg)

<details>
<summary>Mermaid Source</summary>

```mermaid
classDiagram
    class Mapping {
        +int id
        +string owner_username
        +string name
        +string description
        +int current_version
        +Duration ttl
        +Duration inactivity_timeout
        +createVersion()
        +updateLifecycle()
        +copy() Mapping
    }

    class MappingVersion {
        +int mapping_id
        +int version
        +string change_description
        +JSON node_definitions
        +JSON edge_definitions
        +Timestamp created_at
        +string created_by
    }

    class NodeDefinition {
        +string label
        +string sql
        +PropertyDef primary_key
        +List properties
    }

    class EdgeDefinition {
        +string type
        +string from_node
        +string to_node
        +string sql
        +string from_key
        +string to_key
        +List properties
    }

    class PropertyDef {
        +string name
        +string type
    }

    Mapping "1" *-- "1..*" MappingVersion : contains
    MappingVersion "1" *-- "0..*" NodeDefinition : contains
    MappingVersion "1" *-- "0..*" EdgeDefinition : contains
    NodeDefinition "1" *-- "1..*" PropertyDef : has
    EdgeDefinition "1" *-- "0..*" PropertyDef : has
```

</details>

---

## Aggregate Detail: Snapshot

![snapshot-aggregate-structure](diagrams/domain-model-overview/snapshot-aggregate-structure.svg)

<details>
<summary>Mermaid Source</summary>

```mermaid
classDiagram
    class Snapshot {
        +int id
        +int mapping_id
        +int mapping_version
        +string owner_username
        +string name
        +string gcs_path
        +string status
        +JSON progress
        +int size_bytes
        +JSON node_counts
        +JSON edge_counts
        +retry()
        +cancel()
        +updateLifecycle()
    }

    class ExportJob {
        +int id
        +int snapshot_id
        +string job_type
        +string entity_name
        +string status
        +string sql
        +string gcs_path
        +string starburst_query_id
        +int row_count
        +claim()
        +submit()
        +complete()
        +fail()
    }

    class GCSPath {
        +string bucket
        +string owner
        +int mapping_id
        +int mapping_version
        +int snapshot_id
        +toUri() string
    }

    class SnapshotStatus {
        PENDING
        CREATING
        READY
        FAILED
    }

    class ExportJobStatus {
        PENDING
        CLAIMED
        SUBMITTED
        COMPLETED
        FAILED
    }

    Snapshot "1" *-- "0..*" ExportJob : contains
    Snapshot "1" *-- "1" GCSPath : has
    Snapshot "1" --> "1" SnapshotStatus : status
    ExportJob "1" --> "1" ExportJobStatus : status
    ExportJob "1" *-- "1" GCSPath : has
```

</details>

---

## Aggregate Detail: Instance

![instance-aggregate-structure](diagrams/domain-model-overview/instance-aggregate-structure.svg)

<details>
<summary>Mermaid Source</summary>

```mermaid
classDiagram
    class Instance {
        +int id
        +int snapshot_id
        +int pending_snapshot_id
        +string owner_username
        +string name
        +string instance_url
        +string pod_name
        +string pod_ip
        +string status
        +JSON progress
        +int memory_usage_bytes
        +int disk_usage_bytes
        +terminate()
        +updateLifecycle()
        +recordActivity()
    }

    class AlgorithmLock {
        +string holder_username
        +string algorithm_name
        +Timestamp acquired_at
    }

    class PodSpec {
        +string memory_request
        +string memory_limit
        +string cpu_request
        +string cpu_limit
        +int buffer_pool_size
        +int max_threads
    }

    class InstanceStatus {
        WAITING_FOR_SNAPSHOT
        STARTING
        RUNNING
        STOPPING
        FAILED
    }

    Instance "1" --> "1" InstanceStatus : status
    Instance "1" o-- "0..1" AlgorithmLock : lock
    Instance "1" *-- "1" PodSpec : spec
```

</details>

**Note:** The `AlgorithmLock` is managed in-memory by the Wrapper Pod, not persisted to the database. This ensures low-latency lock operations during algorithm execution.

---

## Entity Relationship Diagram

Complete database schema showing all entities and relationships:

![graph-olap-platform-entity-relationship-diagram](diagrams/domain-model-overview/graph-olap-platform-entity-relationship-diagram.svg)

<details>
<summary>Mermaid Source</summary>

```mermaid
erDiagram
    accTitle: Graph OLAP Platform Entity Relationship Diagram
    accDescr: Complete database schema showing all tables and relationships

    users ||--o{ mappings : owns
    users ||--o{ snapshots : owns
    users ||--o{ instances : owns
    users ||--o{ user_favorites : has
    users ||--o{ global_config : updates

    mappings ||--|{ mapping_versions : has
    mappings ||--o{ snapshots : has

    mapping_versions ||--o{ snapshots : references

    snapshots ||--o{ instances : has
    snapshots ||--|{ export_jobs : has

    instances ||--o{ instance_events : has

    allowed_catalogs ||--o{ allowed_schemas : contains
    allowed_schemas ||--o{ schema_metadata_cache : caches

    users {
        string username PK
        string email UK
        string display_name
        string role
        bool is_active
        timestamp created_at
        timestamp updated_at
        timestamp last_login_at
    }

    mappings {
        int id PK
        string owner_username FK
        string name
        string description
        int current_version
        string ttl
        string inactivity_timeout
        timestamp created_at
        timestamp updated_at
    }

    mapping_versions {
        int mapping_id PK
        int version PK
        string change_description
        json node_definitions
        json edge_definitions
        timestamp created_at
        string created_by FK
    }

    snapshots {
        int id PK
        int mapping_id FK
        int mapping_version FK
        string owner_username FK
        string name
        string gcs_path
        string status
        json progress
        json node_counts
        json edge_counts
        bigint size_bytes
        string error_message
        timestamp last_used_at
    }

    instances {
        int id PK
        int snapshot_id FK
        int pending_snapshot_id FK
        string owner_username FK
        string wrapper_type
        string name
        string instance_url
        string pod_name
        string pod_ip
        string status
        json progress
        string error_message
        int cpu_cores
        int memory_gb
        bigint memory_usage_bytes
        bigint disk_usage_bytes
        timestamp last_activity_at
    }

    instance_events {
        int id PK
        int instance_id FK
        string event_type
        json details
        timestamp created_at
    }

    export_jobs {
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
        string sql
        string gcs_path
        int row_count
        bigint size_bytes
    }

    global_config {
        string key PK
        string value
        string description
        timestamp updated_at
        string updated_by FK
    }

    user_favorites {
        string username PK
        string resource_type PK
        int resource_id PK
        timestamp created_at
    }

    allowed_catalogs {
        int id PK
        string catalog_name UK
        bool enabled
    }

    allowed_schemas {
        int id PK
        int catalog_id FK
        string schema_name
        bool enabled
    }

    schema_metadata_cache {
        int id PK
        int schema_id FK
        string table_name
        json columns
        timestamp cached_at
    }
```

</details>

---

## State Machines

### Snapshot Lifecycle

![snapshot-state-machine](diagrams/domain-model-overview/snapshot-state-machine.svg)

<details>
<summary>Mermaid Source</summary>

```mermaid
%%{init: {
  "theme": "base",
  "themeVariables": {
    "primaryColor": "#E1F5FE",
    "primaryTextColor": "#01579B",
    "primaryBorderColor": "#0277BD"
  }
}}%%
stateDiagram-v2
    accTitle: Snapshot State Machine
    accDescr: Shows snapshot lifecycle from creation through export to ready or failed state

    classDef pending fill:#FFF9C4,stroke:#F9A825,color:#F57F17
    classDef processing fill:#BBDEFB,stroke:#1565C0,color:#0D47A1
    classDef success fill:#C8E6C9,stroke:#2E7D32,color:#1B5E20
    classDef failed fill:#FFCDD2,stroke:#C62828,color:#B71C1C

    [*] --> pending: Created via from-mapping

    pending --> creating: Worker claims jobs
    creating --> ready: All export_jobs completed
    creating --> failed: Any export_job failed
    creating --> cancelled: Export cancelled

    failed --> creating: Retry triggered

    ready --> [*]: Delete or TTL expiry
    failed --> [*]: Delete
    cancelled --> [*]: Delete

    class pending pending
    class creating processing
    class ready success
    class failed failed

    note right of pending
        Export jobs created
        Waiting for worker
    end note

    note right of creating
        UNLOAD queries executing
        Progress tracked per job
    end note

    note right of ready
        Parquet files in GCS
        Counts and size recorded
    end note

    note right of failed
        Error message captured
        Partial files may exist
    end note
```

</details>

### Instance Lifecycle

![instance-state-machine](diagrams/domain-model-overview/instance-state-machine.svg)

<details>
<summary>Mermaid Source</summary>

```mermaid
%%{init: {
  "theme": "base",
  "themeVariables": {
    "primaryColor": "#E1F5FE",
    "primaryTextColor": "#01579B",
    "primaryBorderColor": "#0277BD"
  }
}}%%
stateDiagram-v2
    accTitle: Instance State Machine
    accDescr: Shows instance lifecycle from pod creation through running to termination

    classDef waiting fill:#E1BEE7,stroke:#6A1B9A,color:#4A148C
    classDef pending fill:#FFF9C4,stroke:#F9A825,color:#F57F17
    classDef processing fill:#BBDEFB,stroke:#1565C0,color:#0D47A1
    classDef success fill:#C8E6C9,stroke:#2E7D32,color:#1B5E20
    classDef failed fill:#FFCDD2,stroke:#C62828,color:#B71C1C
    classDef stopping fill:#E1BEE7,stroke:#6A1B9A,color:#4A148C

    [*] --> waiting_for_snapshot: POST /api/instances/from-mapping
    [*] --> starting: POST /api/instances

    waiting_for_snapshot --> starting: Snapshot ready
    waiting_for_snapshot --> failed: Snapshot failed

    starting --> running: Pod ready, data loaded
    starting --> failed: Startup error

    running --> stopping: Terminate request
    running --> stopping: TTL expired
    running --> stopping: Inactivity timeout

    stopping --> [*]: Pod deleted

    failed --> [*]: Cleanup

    class waiting_for_snapshot waiting
    class starting pending
    class running success
    class stopping stopping
    class failed failed

    note right of waiting_for_snapshot
        Instance created with
        pending_snapshot_id
        Waiting for snapshot export
    end note

    note right of starting
        1. Pod scheduling
        2. Schema creation
        3. COPY FROM nodes
        4. COPY FROM edges
    end note

    note right of running
        Queries: concurrent
        Algorithms: exclusive lock
        Structure: read-only
    end note

    note right of stopping
        Graceful shutdown
        /shutdown called
        Pod terminating
    end note
```

</details>

### Export Job Lifecycle

![export-job-state-machine](diagrams/domain-model-overview/export-job-state-machine.svg)

<details>
<summary>Mermaid Source</summary>

```mermaid
%%{init: {
  "theme": "base",
  "themeVariables": {
    "primaryColor": "#E1F5FE",
    "primaryTextColor": "#01579B",
    "primaryBorderColor": "#0277BD"
  }
}}%%
stateDiagram-v2
    accTitle: Export Job State Machine
    accDescr: Shows individual export job lifecycle through claim, submit, poll, complete

    classDef pending fill:#FFF9C4,stroke:#F9A825,color:#F57F17
    classDef claimed fill:#E1BEE7,stroke:#6A1B9A,color:#4A148C
    classDef submitted fill:#BBDEFB,stroke:#1565C0,color:#0D47A1
    classDef success fill:#C8E6C9,stroke:#2E7D32,color:#1B5E20
    classDef failed fill:#FFCDD2,stroke:#C62828,color:#B71C1C

    [*] --> pending: Snapshot created

    pending --> claimed: Worker claims (atomic)
    claimed --> submitted: UNLOAD query sent
    claimed --> pending: Lease expired (>10 min)

    submitted --> submitted: Poll (Fibonacci backoff)
    submitted --> completed: Query FINISHED
    submitted --> failed: Query FAILED
    submitted --> pending: Stale poll (>10 min)

    completed --> [*]
    failed --> [*]

    class pending pending
    class claimed claimed
    class submitted submitted
    class completed success
    class failed failed
```

</details>

---

## Resource Lifecycle Flow

End-to-end flow from user action to graph instance:

![resource-lifecycle-flow](diagrams/domain-model-overview/resource-lifecycle-flow.svg)

<details>
<summary>Mermaid Source</summary>

```mermaid
---
config:
  layout: elk
---
flowchart TB
    accTitle: Resource Lifecycle Flow
    accDescr: Shows complete flow from Mapping creation through Snapshot export to Instance creation

    classDef user fill:#F3E5F5,stroke:#7B1FA2,stroke-width:2px,color:#4A148C
    classDef resource fill:#FFF8E1,stroke:#F57F17,stroke-width:2px,color:#E65100
    classDef process fill:#E1F5FE,stroke:#0277BD,stroke-width:2px,color:#01579B
    classDef storage fill:#E8F5E9,stroke:#2E7D32,stroke-width:2px,color:#1B5E20
    classDef external fill:#ECEFF1,stroke:#455A64,stroke-width:2px,color:#263238
    classDef infra fill:#E3F2FD,stroke:#1565C0,stroke-width:2px,color:#0D47A1

    USER["Analyst"]:::user

    subgraph Phase1["Phase 1: Define Schema"]
        M1["Create Mapping<br/>(SQL queries)"]:::process
        M2["Mapping<br/>v1"]:::resource
        M3["Edit Mapping<br/>(new version)"]:::process
        M4["Mapping<br/>v2, v3..."]:::resource
    end

    subgraph Phase2["Phase 2: Create Instance from Mapping"]
        S1["POST /instances/from-mapping"]:::process
        S2["Instance (waiting_for_snapshot)<br/>Snapshot (pending)"]:::resource
        S3["Export Worker<br/>claims jobs"]:::process
        S4["UNLOAD to<br/>Starburst"]:::external
        S5["Parquet files<br/>written"]:::storage
        S6["Snapshot<br/>(ready)"]:::resource
    end

    subgraph Phase3["Phase 3: Instance Startup"]
        I1["Instance transitions<br/>to starting"]:::process
        I2["Instance<br/>(starting)"]:::resource
        I3["K8s Pod<br/>scheduled"]:::infra
        I4["COPY FROM<br/>GCS Parquet"]:::process
        I5["Instance<br/>(running)"]:::resource
    end

    subgraph Phase4["Phase 4: Analyze"]
        A1["Execute Cypher<br/>queries"]:::process
        A2["Run graph<br/>algorithms"]:::process
        A3["Export results<br/>to CSV/DataFrame"]:::process
    end

    USER --> M1
    M1 --> M2
    M2 --> M3
    M3 --> M4

    M2 --> S1
    M4 --> S1
    S1 --> S2
    S2 --> S3
    S3 --> S4
    S4 --> S5
    S5 --> S6

    S6 --> I1
    I1 --> I2
    I2 --> I3
    I3 --> I4
    I4 --> I5

    I5 --> A1
    I5 --> A2
    A1 --> A3
    A2 --> A3
```

</details>

---

## Domain Rules and Invariants

### Deletion Dependencies

Resources form a strict dependency chain that must be respected during deletion:

![deletion-dependency-chain](diagrams/domain-model-overview/deletion-dependency-chain.svg)

<details>
<summary>Mermaid Source</summary>

```mermaid
---
config:
  layout: elk
---
flowchart TB
    accTitle: Deletion Dependency Chain
    accDescr: Shows resource dependencies and deletion rules preventing orphaned resources

    classDef resource fill:#E3F2FD,stroke:#1565C0,stroke-width:2px,color:#0D47A1
    classDef check fill:#FFF8E1,stroke:#F57F17,stroke-width:2px,color:#E65100
    classDef allowed fill:#C8E6C9,stroke:#2E7D32,stroke-width:2px,color:#1B5E20
    classDef blocked fill:#FFCDD2,stroke:#C62828,stroke-width:2px,color:#B71C1C

    subgraph Chain["DELETION DEPENDENCY CHAIN"]
        direction LR
        Mapping["Mapping"]:::resource
        Snapshot["Snapshot"]:::resource
        Instance["Instance"]:::resource
        Snapshot -->|"depends on"| Mapping
        Instance -->|"depends on"| Snapshot
    end

    subgraph InstDel["DELETE Instance"]
        instAction["Always Allowed<br/>Pod deleted, DB row removed"]:::allowed
    end

    subgraph SnapDel["DELETE Snapshot"]
        snapCheck{"Active instances?<br/>(starting | running)"}:::check
        snapYes["409 RESOURCE_HAS_DEPENDENCIES<br/>Must terminate instances first"]:::blocked
        snapNo["DELETE allowed<br/>+ GCS cleanup<br/>+ favorites cleanup"]:::allowed
        snapCheck -->|yes| snapYes
        snapCheck -->|no| snapNo
    end

    subgraph MapDel["DELETE Mapping"]
        mapCheck{"Any snapshots exist?<br/>(any status, any version)"}:::check
        mapYes["409 RESOURCE_HAS_DEPENDENCIES<br/>Must delete snapshots first"]:::blocked
        mapNo["DELETE allowed<br/>+ versions cascade<br/>+ favorites cleanup"]:::allowed
        mapCheck -->|yes| mapYes
        mapCheck -->|no| mapNo
    end

    Instance --> InstDel
    Snapshot --> SnapDel
    Mapping --> MapDel
```

</details>

### Versioning Rules

| Rule | Description |
|------|-------------|
| **Immutability** | Mapping versions are immutable once created |
| **Change Description** | Required for versions > 1 |
| **Snapshot Binding** | Snapshot records specific `mapping_version` used |
| **Version Survival** | Deleting a mapping deletes all versions (CASCADE) |
| **No Version Deletion** | Cannot delete individual versions |

### Concurrency Rules

| Rule | Scope | Enforcement |
|------|-------|-------------|
| **Per-Analyst Instance Limit** | Configurable (default: 5) | Control Plane validates on create |
| **Cluster Instance Limit** | Configurable (default: 50) | Control Plane validates on create |
| **Concurrent Queries** | Allowed | Ryugraph supports concurrent reads |
| **Exclusive Algorithm Lock** | Per-instance | In-memory lock in Wrapper Pod |
| **No Structure Modification** | Per-instance | Cannot add/delete nodes/edges |

### Lifecycle Rules

| Resource | TTL Source | Inactivity Definition |
|----------|------------|----------------------|
| **Mapping** | Global default or override | Snapshot created from mapping |
| **Snapshot** | Inherited from mapping (max) | Instance created from snapshot |
| **Instance** | Inherited from snapshot (max) | Query executed or algorithm run |

**Inheritance Constraint:** Child resources can only have shorter timeouts than parent.

### Algorithm Locking

![algorithm-lock-acquisition-flow](diagrams/domain-model-overview/algorithm-lock-acquisition-flow.svg)

<details>
<summary>Mermaid Source</summary>

```mermaid
%%{init: {
  "theme": "base",
  "themeVariables": {
    "actorBkg": "#E3F2FD",
    "actorBorder": "#1565C0",
    "noteBkgColor": "#FFF8E1",
    "activationBkgColor": "#E8F5E9"
  }
}}%%
sequenceDiagram
    accTitle: Algorithm Lock Acquisition Flow
    accDescr: Shows implicit lock behavior during algorithm execution

    participant SDK as Jupyter SDK
    participant Pod as Wrapper Pod
    participant Lock as In-Memory Lock

    SDK->>+Pod: POST /algo/pagerank

    alt Lock Available
        Pod->>Lock: Acquire lock (user, algo, time)
        Lock-->>Pod: Lock acquired
        Pod-->>SDK: 202 Accepted (started)

        Note over Pod: Algorithm executes...

        Pod->>Lock: Release lock
        Lock-->>Pod: Lock released
    else Lock Held
        Pod-->>SDK: 409 Conflict
        Note over SDK: "Instance locked by {user}<br/>running {algo} since {time}"
    end

    deactivate Pod
```

</details>

**Lock Characteristics:**

- **Implicit:** Acquired automatically on algorithm start, released on completion
- **Non-persistent:** Stored in Wrapper Pod memory, lost on pod restart
- **Non-transferable:** Only completion or pod termination releases lock
- **Timeout-free:** Hung algorithms require instance termination

---

## Domain Events

Key events that drive state transitions:

| Event | Publisher | Subscribers | Effect |
|-------|-----------|-------------|--------|
| `SnapshotCreated` | Control Plane | Export Worker (via polling) | Jobs become claimable |
| `ExportJobCompleted` | Export Worker | Control Plane | Updates snapshot progress |
| `SnapshotReady` | Control Plane | — | Snapshot can create instances |
| `InstanceStarted` | Wrapper Pod | Control Plane | Status → running, URL set |
| `InstanceFailed` | Wrapper Pod / Reconciler | Control Plane | Status → failed, cleanup |
| `AlgorithmStarted` | Wrapper Pod | — | Lock acquired |
| `AlgorithmCompleted` | Wrapper Pod | — | Lock released, activity recorded |
| `LifecycleExpired` | Background Job | Control Plane | Terminate/delete resource |

---

## Ubiquitous Language

| Term | Definition |
|------|------------|
| **Mapping** | Configuration defining graph schema from SQL queries |
| **Mapping Version** | Immutable snapshot of mapping configuration |
| **Node Definition** | SQL query + schema for a node type |
| **Edge Definition** | SQL query + schema for a relationship type |
| **Snapshot** | Point-in-time data export from a mapping version |
| **Export Job** | Single UNLOAD query within a snapshot export |
| **Instance** | Running Ryugraph database pod |
| **Algorithm Lock** | Exclusive execution rights for graph algorithms |
| **TTL** | Time-to-live duration before automatic deletion |
| **Inactivity Timeout** | Duration without use before automatic cleanup |
| **Export** | Process of running SQL → writing Parquet to GCS |
| **Load** | Process of reading Parquet from GCS → Ryugraph COPY FROM |
| **Waiting for Snapshot** | Instance state when created from mapping, pending snapshot completion |

---

## References

- [requirements.md](--/foundation/requirements.md) - Full resource definitions
- [data.model.spec.md](-/data.model.spec.md) - Database schema details
- [system.architecture.design.md](-/system.architecture.design.md) - Component architecture
- [architectural.guardrails.md](--/foundation/architectural.guardrails.md) - Design constraints
- Evans, Eric. *Domain-Driven Design: Tackling Complexity in the Heart of Software*
- [Microsoft: Using tactical DDD to design microservices](https://learn.microsoft.com/en-us/azure/architecture/microservices/model/tactical-ddd)
- [Martin Fowler: Bounded Context](https://www.martinfowler.com/bliki/BoundedContext.html)
