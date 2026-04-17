---
title: "Graph OLAP Platform - Design Requirements"
scope: hsbc
---

# Graph OLAP Platform - Design Requirements

## Overview

Platform for HSBC customer service analytics enabling analysts to create ad-hoc graph instances from Starburst SQL queries, run graph/network algorithms, and share work.

**User Interface:** The platform is accessed exclusively via the Python SDK in Jupyter notebook environments. There is no web interface.

**Scale:** Tens of analysts, potentially hundreds of concurrent instances, ≤2GB graphs, <24hr typical lifespan

---

## Glossary

### Resources

| Term | Definition |
|------|------------|
| **Mapping** | A user-created configuration that defines how to structure graph data from Starburst SQL queries. Contains node definitions (SQL + schema) and edge definitions (SQL + relationships). This is a resource, not a process. |
| **Snapshot** | A point-in-time export of data based on a Mapping. Created by running the Mapping's SQL queries against Starburst and storing results as Parquet files in GCS. |
| **Instance** | A running Ryugraph database loaded with data from a Snapshot. Provides query and algorithm execution capabilities. |

### Processes

| Term | Definition |
|------|------------|
| **Export** | The process of running Starburst UNLOAD queries and writing Parquet files to GCS. Performed by the Export Worker during Snapshot creation. |
| **Load** | The process of reading Parquet files from GCS and importing them into a graph database. Performed by the graph wrapper (Ryugraph or FalkorDB) during Instance creation. |

### Components (Artefacts)

| Term | Definition |
|------|------------|
| **Control Plane** | The central management component: Python/FastAPI REST API backend. Manages all resource lifecycle, orchestrates operations, and serves as single source of truth. Includes the Mapping Generator subsystem. Accessed exclusively via the Jupyter SDK. |
| **Export Worker** | Background service that handles Snapshot creation. Export Submitter submits UNLOAD queries to Starburst; Export Poller uses APScheduler to poll the `export_jobs` table and call Starburst directly until completion. |
| **Ryugraph Wrapper** | Per-instance FastAPI service wrapping an embedded Ryugraph database. Creates schema, loads data from Snapshots, and provides query/algorithm APIs. |
| **FalkorDB Wrapper** | Per-instance FastAPI service wrapping an embedded FalkorDB database. In-memory graph database with native Cypher algorithms. |
| **Mapping Generator** | Subsystem within Control Plane that validates Mappings against Starburst, infers column types, and generates Ryugraph schema DDL. |

---

## Technology Stack

| Component | Technology |
|-----------|------------|
| **Graph DB** | Ryugraph (KuzuDB fork), FalkorDB | Embedded databases with Python bindings, pluggable architecture (see ADR-049) |
| **Infrastructure** | GKE on Google Cloud |
| **Data Source** | Starburst Galaxy (managed Trino SaaS) + BigQuery |
| **Export Platform** | Starburst Galaxy `system.unload()` with PyArrow fallback |
| **Storage** | GCS at `gs://bucket/{user_id}/{mapping_id}/{snapshot_id}/` (user_id = snapshot owner) |
| **Control Plane** | Python/FastAPI REST API, PostgreSQL (Cloud SQL, DO Managed, or local pod), raw SQL |
| **Ryugraph Wrapper** | Python (FastAPI), per-instance REST API with embedded Ryugraph |
| **FalkorDB Wrapper** | Python (FastAPI), per-instance REST API with embedded FalkorDB |
| **Jupyter SDK** | Python (full control plane + query/algorithm interface) |
| **IaC/GitOps (HSBC)** | Terraform, Jenkins (CI), `./infrastructure/cd/deploy.sh` + `kubectl apply -f infrastructure/cd/resources/` (CD). No Helm (except Zero-to-JupyterHub), no ArgoCD, no GitHub Actions. |

**References:**
- ADR-070: Starburst Galaxy + BigQuery Export Platform
- ADR-071: PyArrow Fallback Export Strategy
- ADR-072: Removal of Local Trino Stack

---

## Core Resources

Three resource types, each with single owner (all resources visible to all analysts):

1. **Mapping:** SQL query defining graph schema. Retention: until deleted/inactivity timeout
2. **Data Snapshot:** Timestamped Parquet files from mapping. Retention: 7 days default (configurable). Re-running mapping creates new versioned snapshot
3. **Graph Instance:** Running Ryugraph pod from snapshot. Retention: <24hr typical (configurable)

---

## Resource Metadata

### Mapping

**Mapping (header):**

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Unique identifier |
| name | string | Display name |
| description | string | General description of the mapping |
| owner_username | string | Owner username (DB-backed user record) |
| current_version | integer | Latest version number |
| created_at | timestamp | Creation time |
| ttl | duration | Time-to-live (null = no expiry) |
| inactivity_timeout | duration | Delete after no snapshots created |

**Mapping Version (immutable):**

| Field | Type | Description |
|-------|------|-------------|
| mapping_id | UUID | Parent mapping reference |
| version | integer | Version number (1, 2, 3, ...) |
| change_description | string | Description of changes (null for initial version) |
| node_definitions | JSON | Array of node definitions (see structure below) |
| edge_definitions | JSON | Array of edge definitions (see structure below) |
| created_at | timestamp | When this version was created |

**Versioning rules:**

- Versions are immutable once created
- Editing a mapping creates a new version (requires change description)
- Cannot delete a mapping if any snapshots exist for any version
- Must delete all snapshots before deleting a mapping

**Node Definition Structure:**

```json
{
  "label": "Customer",
  "sql": "SELECT customer_id, name, city FROM analytics.customers",
  "primary_key": {"name": "customer_id", "type": "STRING"},
  "properties": [
    {"name": "name", "type": "STRING"},
    {"name": "city", "type": "STRING"}
  ]
}
```

- `label`: Ryugraph node table name
- `sql`: Starburst SQL query (primary_key column must be first in SELECT)
- `primary_key`: Column name and Ryugraph type for node primary key
- `properties`: Property columns with Ryugraph types, in SELECT order (after primary key)
- Supported types: STRING, INT64, INT32, INT16, INT8, DOUBLE, FLOAT, DATE, TIMESTAMP, BOOL, BLOB, UUID, LIST, MAP, STRUCT

**Edge Definition Structure:**

```json
{
  "type": "PURCHASED",
  "from_node": "Customer",
  "to_node": "Product",
  "sql": "SELECT customer_id, product_id, amount, purchase_date FROM analytics.transactions",
  "from_key": "customer_id",
  "to_key": "product_id",
  "properties": [
    {"name": "amount", "type": "DOUBLE"},
    {"name": "purchase_date", "type": "DATE"}
  ]
}
```

- `type`: Ryugraph relationship table name
- `from_node`/`to_node`: Source and target node labels
- `sql`: Starburst SQL query (from_key first, to_key second, then properties)
- `from_key`/`to_key`: Column names for source/target node references (types inferred from referenced node primary keys)
- `properties`: Property columns with Ryugraph types, in SELECT order (after from/to keys)

**Copy Mapping Behavior:**

When copying a mapping:

| Field | Behavior |
|-------|----------|
| name | Defaults to "Copy of {source.name}" |
| description | Copied from source |
| node_definitions | Copied from source current_version |
| edge_definitions | Copied from source current_version |
| current_version | Reset to 1 |
| owner | Set to copying user |
| ttl | Reset to global default |
| inactivity_timeout | Reset to global default |
| created_at | Set to now |

What is NOT copied: Version history (only current version copied as v1), snapshots, favorites.

### Data Snapshot

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Unique identifier |
| name | string | Display name |
| description | string | Optional description |
| mapping_id | UUID | Source mapping reference |
| mapping_version | integer | Version of mapping used to create this snapshot |
| owner_username | string | Owner username (DB-backed user record) |
| gcs_path | string | GCS location of Parquet files |
| size_bytes | integer | Total storage size |
| node_count | integer | Number of nodes (per node type) |
| edge_count | integer | Number of edges (per edge type) |
| status | enum | pending, creating, ready, failed, cancelled |
| error_message | string | Failure details (if status=failed) |
| created_at | timestamp | Creation time |
| ttl | duration | Time-to-live |
| inactivity_timeout | duration | Delete after no instances created |

**Deletion rule:** Cannot delete a snapshot if any instances exist for that snapshot. Must terminate all instances before deleting a snapshot.

**GCS File Structure (per snapshot):**

```
gs://bucket/{user_id}/{mapping_id}/{snapshot_id}/   (user_id = snapshot owner)
├── nodes/
│   ├── {node_label_1}/
│   │   └── *.parquet   (multiple files, written in parallel by Starburst)
│   └── {node_label_2}/
│       └── *.parquet
└── edges/
    ├── {edge_type_1}/
    │   └── *.parquet   (multiple files, written in parallel by Starburst)
    └── {edge_type_2}/
        └── *.parquet
```

**Constraints:**

- Node Parquet files: columns in order [primary_key, property1, property2, ...]
- Edge Parquet files: columns in order [from_key, to_key, property1, property2, ...]
- Nodes must be loaded before edges (edges reference node primary keys)
- Starburst UNLOAD writes multiple files in parallel; Ryugraph COPY FROM reads all files via glob pattern (`*.parquet`)

### Graph Instance

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Unique identifier |
| name | string | Display name |
| description | string | Optional description |
| snapshot_id | UUID | Source snapshot reference |
| owner_username | string | Owner username (DB-backed user record) |
| instance_url | string | Unique access URL |
| pod_name | string | Kubernetes pod name |
| pod_ip | string | Internal pod IP |
| status | enum | starting, running, stopping, failed (stopping = terminating, instance deleted when complete) |
| error_message | string | Failure details (if status=failed) |
| created_at | timestamp | Creation time |
| last_activity_at | timestamp | Last query/algorithm execution |
| ttl | duration | Time-to-live |
| inactivity_timeout | duration | Terminate after no activity |
| memory_usage_bytes | integer | Current memory consumption |
| disk_usage_bytes | integer | Current disk consumption |
| lock_holder_id | UUID | User holding algorithm lock (null if unlocked) |
| lock_algorithm | string | Algorithm name being executed |
| lock_acquired_at | timestamp | When lock was acquired |

---

## Naming & Validation Constraints

### Resource Names

| Field | Min | Max | Allowed Characters | Unique Scope |
|-------|-----|-----|-------------------|--------------|
| Mapping name | 1 | 255 | Unicode letters, numbers, spaces, `-_.` | Not unique |
| Snapshot name | 1 | 255 | Unicode letters, numbers, spaces, `-_.` | Not unique |
| Instance name | 1 | 255 | Unicode letters, numbers, spaces, `-_.` | Not unique |
| Description | 0 | 4000 | Any Unicode | N/A |

### Graph Schema Names

| Field | Min | Max | Allowed Characters | Unique Scope |
|-------|-----|-----|-------------------|--------------|
| Node label | 1 | 64 | ASCII letters, numbers, `_` (start with letter) | Per mapping version |
| Edge type | 1 | 64 | ASCII uppercase letters, numbers, `_` | Per mapping version |
| Property name | 1 | 64 | ASCII letters, numbers, `_` (start with letter) | Per node/edge |

### Reserved Names

The following names cannot be used for node labels or edge types:

- Cypher keywords: `NODE`, `RELATIONSHIP`, `MATCH`, `WHERE`, `RETURN`, `CREATE`, `DELETE`, `SET`, `REMOVE`, `WITH`, `ORDER`, `LIMIT`, `SKIP`, `UNION`, `CALL`, `YIELD`
- System prefixes: `_internal_`, `_system_`, `_ryugraph_`

### Validation Behavior

| Check | When | Error Code |
|-------|------|------------|
| Name too long | Create/Update | VALIDATION_FAILED |
| Invalid characters | Create/Update | VALIDATION_FAILED |
| Reserved name | Create/Update | VALIDATION_FAILED |
| Duplicate node label | Create mapping version | VALIDATION_FAILED |
| Duplicate edge type | Create mapping version | VALIDATION_FAILED |

---

## User Roles & Permissions

**Role hierarchy (least to most privileged): Analyst < Admin < Ops.**
Each higher role inherits ALL capabilities of the roles below it.

### Analyst

| Resource | View | Create | Update | Delete | Other |
|----------|------|--------|--------|--------|-------|
| **Mapping** | All | Own | Own only* | Own only** | Copy any; list versions; list snapshots |
| **Snapshot** | All | From any mapping (owns result) | Own only | Own only | - |
| **Instance** | All | From any snapshot (owns result) | Own only | Own only | Query any; algorithms own only |
| **Export Queue** | Own only | - | - | - | - |

*Update creates a new immutable version (requires change description)
**Delete fails if any snapshots exist for any version of the mapping

### Admin

All Analyst capabilities, plus:

- CRUD any user's resources (mappings, snapshots, instances)
- Run algorithms on any instance
- View query logs and algorithm run history
- Read all export queue entries

Ops-only endpoints (config, cluster, jobs) are NOT accessible to Admin.

### Ops

All Admin capabilities (Ops inherits every Admin and Analyst capability), plus:

- View cluster health status and metrics
- Configure global lifecycle defaults and hard limits
- Configure concurrency limits (per-analyst, cluster-wide)
- Manage allowed data sources (catalogs/schemas for Schema Browser)
- Trigger metadata cache refresh
- Enable/disable maintenance mode
- Force terminate stuck instances
- Retry/cancel failed exports
- Manage background jobs (trigger, cancel, view status)

> See `system-design/authorization.spec.md` for the authoritative RBAC matrix.

---

## Instance Access Model

| Operation | Concurrency | Notes |
|-----------|-------------|-------|
| Read (Cypher queries) | Concurrent | Allowed |
| Algorithm writes | Exclusive lock | One algorithm run per instance at a time |
| Structure modification | Not permitted | No add/delete nodes/edges |

### Algorithm Locking

- Lock is implicit: created automatically when algorithm starts, released automatically when it finishes
- Lock includes: holder user ID, algorithm name, start time
- If algorithm hangs, lock remains held - user must terminate the instance
- Clear error message when instance is locked (e.g., "Instance locked by user X running algorithm Y since Z")

---

## Lifecycle Configuration

**Hierarchy:** Global Defaults & Hard Limits (Ops only) → Local Override (resource owner, must be ≤ hard limit)

**Parameters per resource type:**

- **Max age (TTL):** Delete/terminate after duration
- **Inactivity timeout:** Delete/terminate after no activity

**Activity definitions:**

- Mapping: Used to create snapshot
- Snapshot: Used to create instance
- Instance: Query executed or algorithm run

**Concurrency limits (Ops configurable):**

- Instances per analyst
- Total cluster capacity

**Limit enforcement (instance creation only):**

- HTTP 409 Conflict when limit exceeded
- Error message includes: current count, max allowed, which limit hit (per-analyst or cluster)
- Email notification sent to: analyst, all admins, all ops users

### Default Values

| Resource | Field | Default | Source |
|----------|-------|---------|--------|
| Mapping | ttl | null (no expiry) | global_config |
| Mapping | inactivity_timeout | P30D (30 days) | global_config |
| Snapshot | ttl | P7D (7 days) | global_config |
| Snapshot | inactivity_timeout | P3D (3 days) | global_config |
| Instance | ttl | PT24H (24 hours) | global_config |
| Instance | inactivity_timeout | PT4H (4 hours) | global_config |

### Lifecycle Inheritance

| Child Resource | Inherits From | Override Allowed |
|----------------|---------------|------------------|
| Snapshot | Parent mapping's lifecycle settings | Yes (can be shorter only) |
| Instance | Parent snapshot's lifecycle settings | Yes (can be shorter only) |

### API Defaults

| Endpoint | Parameter | Default |
|----------|-----------|---------|
| List endpoints | limit | 50 |
| List endpoints | offset | 0 |
| List endpoints | sort | created_at DESC |
| Snapshot create | mapping_version | mapping.current_version |
| Query execute | timeout_ms | 60000 |

---

## Search & Filter Capabilities

### Text Search

| Resource | Searchable Fields | Match Type |
|----------|-------------------|------------|
| Mapping | name, description | Case-insensitive substring |
| Snapshot | name, description | Case-insensitive substring |
| Instance | name, description | Case-insensitive substring |

### Filter Parameters

| Resource | Filterable Fields | Operators |
|----------|-------------------|-----------|
| Mapping | owner, created_at | equals, date range |
| Snapshot | owner, status, mapping_id, created_at | equals, date range |
| Instance | owner, status, snapshot_id, created_at | equals, date range |

### Sort Options

| Resource | Sortable Fields | Default |
|----------|-----------------|---------|
| Mapping | name, created_at, updated_at | created_at DESC |
| Snapshot | name, created_at, status | created_at DESC |
| Instance | name, created_at, status | created_at DESC |

### Pagination

| Parameter | Default | Maximum |
|-----------|---------|---------|
| limit | 50 | 100 |
| offset | 0 | No limit |

Response includes:

- `total_count`: Total matching resources
- `has_more`: Boolean indicating more pages exist

---

## Graph Algorithms

**All algorithms execute server-side within the Ryugraph pod.**

| Method | Algorithms |
|--------|------------|
| **Ryugraph `algo` extension** | PageRank, Connected Components, Shortest Path, Louvain, Label Propagation, Triangle Count |
| **NetworkX (in-process)** | Centrality (degree, closeness, betweenness, eigenvector), Community (Louvain, Girvan-Newman), Paths, Clustering, Link prediction |

**Key capabilities:**

- Ryugraph is embedded in Python - NetworkX runs in the same process
- Bidirectional integration: Ryugraph query results convert to NetworkX graphs, algorithm results write back to Ryugraph node/edge properties
- Native Ryugraph algorithms (C++) are faster; NetworkX provides broader algorithm coverage

**Result storage:** Algorithm results written to node/edge properties. Changes persist for instance lifetime but are **not exportable** - no facility to persist algorithm results back to snapshots.

---

## Performance Requirements

### Capacity Limits

| Resource | Soft Limit | Hard Limit | Notes |
|----------|------------|------------|-------|
| Graph size (memory) | 1.5 GB | 2 GB | Per instance |
| Node count | 10 million | 50 million | Per instance |
| Edge count | 50 million | 200 million | Per instance |
| Properties per node/edge | 50 | 100 | Schema constraint |
| Concurrent queries | 10 | 20 | Per instance |

### Latency Expectations

| Operation | Expected (p50) | Target (p95) | Timeout |
|-----------|----------------|--------------|---------|
| Simple query (<1000 results) | < 500ms | < 2s | 60s |
| Complex query (aggregation) | < 2s | < 10s | 60s |
| Algorithm (PageRank, 1M nodes) | < 30s | < 2 min | 30 min |
| Algorithm (Betweenness, 100K nodes) | < 2 min | < 10 min | 30 min |
| Instance startup | < 1 min | < 3 min | 5 min |
| Snapshot export (1M rows) | < 5 min | < 15 min | 30 min |

### Throughput Expectations

| Operation | Expected Throughput |
|-----------|---------------------|
| Snapshot exports (concurrent) | 10 parallel |
| Instance startups (concurrent) | 20 parallel |
| API requests (Control Plane) | 100 req/sec |

---

## Component Architecture

### 1. Control Plane (Python/FastAPI REST API)

**Note:** The platform is accessed exclusively via the Python SDK in Jupyter environments. There is no web interface.

**REST API (accessed via Jupyter SDK):**

```
Mappings:     GET/POST/DELETE /api/mappings
              GET /api/mappings/:id
              PUT /api/mappings/:id              - Creates new version (requires change_description)
              POST /api/mappings/:id/copy
              PUT /api/mappings/:id/lifecycle
              GET /api/mappings/:id/versions     - List all versions
              GET /api/mappings/:id/versions/:v  - Get specific version
              GET /api/mappings/:id/snapshots    - List snapshots across all versions
                                                 (NOTE: route is currently commented out in
                                                 packages/control-plane/src/control_plane/routers/api/mappings.py:594;
                                                 ADR-149 Tier-A.8 follow-up to re-enable.)

Snapshots:    GET /api/snapshots           (read-only, CRUD disabled)
              GET /api/snapshots/:id       (read-only, CRUD disabled)
              PUT /api/snapshots/:id/lifecycle

Instances:    GET/POST /api/instances
              POST /api/instances/from-mapping  (creates snapshot automatically)
              GET/PUT/DELETE /api/instances/:id
              PUT /api/instances/:id/lifecycle
              POST /api/instances/:id/terminate

Locks:        GET /api/instances/:id/lock        - Check lock status (no create/delete - lock is implicit)

Config (Ops): GET/PUT /api/config/lifecycle
              GET/PUT /api/config/concurrency

Cluster (Ops): GET /api/cluster/health
               GET /api/cluster/instances
               GET /api/cluster/metrics
```

**Note:** Audit logging is handled by the company's external observability stack (TBD), not the Control Plane API.

### 2. Snapshot Export Processing

Snapshot creation is asynchronous to avoid blocking the user during long-running Starburst exports.

**Export Strategy (Two-Tier):**

| Tier | Method | When Used |
|------|--------|-----------|
| **Primary** | Starburst Galaxy `system.unload()` | Server-side, distributed execution |
| **Fallback** | PyArrow client-side export | When `system.unload()` unavailable |

The export worker automatically falls back to PyArrow if server-side export fails. Both paths produce identical Parquet files.

**User-Observable Behavior:**

1. User triggers snapshot creation via Jupyter SDK
2. Snapshot record created immediately with status `pending`
3. Status progresses to `creating` during export (progress visible via SDK polling)
4. On success: status becomes `ready`, node/edge counts and size recorded
5. On failure: status becomes `failed`, error message recorded
6. On cancellation (Ops): status becomes `cancelled`, partial data cleaned up

**Progress Visibility:**

During the `creating` phase, users can see:

- Current phase (exporting nodes vs edges)
- Which node/edge type is being processed
- Completed tables with row counts

**Retry Behavior:**

- Failed snapshots can be retried via SDK
- Retry creates a new export attempt (overwrites partial data)

**Cancellation:**

- Ops users can cancel in-progress exports
- Cancellation is best-effort (current Starburst query completes)

**Note:** Implementation details (compute platform, message queue) are defined in [export-worker.design.md](--/component-designs/export-worker.design.md) and ADR-018.

### 3. Ryugraph Wrapper (Python/FastAPI, per instance)

Each graph instance runs in its own Kubernetes pod. Ryugraph is an embedded database - it runs in-process within the Python wrapper (not as a separate server).

**Constraints:**

- One Ryugraph database per pod (file locking prevents multiple writers)
- On startup: Create schema (CREATE NODE TABLE, CREATE REL TABLE) from mapping definition, then COPY FROM GCS Parquet files (nodes before edges)
- Supports concurrent read queries, exclusive lock for algorithm writes

**Instance URL structure:** `https://{domain}/{instance-id}/`

- Single domain, path-based routing via Ingress

**REST API:**

*Control Plane endpoints:*

```
GET  /health, GET /status, POST /shutdown
```

*Jupyter SDK endpoints:*

```
POST /query           - Execute Cypher query
POST /algo/{name}     - Run Ryugraph native algorithm
POST /networkx/{name} - Run NetworkX algorithm
POST /subgraph        - Extract subgraph
GET  /lock            - Check lock status (lock is implicit with algorithm execution)
GET  /schema          - Get graph schema
```

**Ryugraph Explorer:** Hosted at `https://{domain}/{instance-id}/explorer/`

### 4. Jupyter SDK (Python) - Primary User Interface

The Jupyter SDK is the **only user interface** for the Graph OLAP Platform. All platform interactions - from mapping creation to query execution - are performed through Python code in Jupyter notebooks.

**Capabilities:**

| Category | Features |
|----------|----------|
| **Control Plane** | Mapping, Snapshot, Instance CRUD with versioning, lifecycle, and favorites |
| **Queries** | Cypher execution with multiple return formats (DataFrame, dict, NetworkX) |
| **Algorithms** | Native Ryugraph + any NetworkX algorithm via dynamic discovery (500+) |
| **Visualization** | Smart auto-visualization, interactive tables, graph rendering |
| **Deployment** | Zero-config Jupyter integration, Docker images, JupyterHub |

**Quick Start (2 lines):**

```python
from graph_olap import notebook
client = notebook.connect()  # Auto-discovers config from environment
```

**Example Workflow:**

```python
# Create and wait for snapshot
snapshot = client.snapshots.create_and_wait(mapping_id=1, name="Analysis")

# Create and connect to instance
instance = client.instances.create_and_wait(snapshot_id=snapshot.id, name="Analysis")
conn = client.instances.connect(instance.id)

# Query and visualize
result = conn.query("MATCH (c:Customer)-[p]->(pr:Product) RETURN c, p, pr LIMIT 1000")
result.show()  # Auto-selects best visualization

# Run algorithms
conn.networkx.run("pagerank", node_label="Customer", property_name="pr")
conn.networkx.run("louvain_communities", property_name="community")

# Export results
df = conn.query_df("MATCH (n) RETURN n.name, n.pr, n.community")
df.to_csv("results.csv")
```

**Implementation Details:** See [jupyter-sdk.design.md](--/component-designs/jupyter-sdk.design.md)

**Deployment:** See [jupyter-sdk.deployment.design.md](--/component-designs/jupyter-sdk.deployment.design.md)

### 5. Instance Resource Model

See [ryugraph-performance.reference.md](--/reference/ryugraph-performance.reference.md) for detailed sizing rationale.

- Memory request: 3Gi (2GB buffer pool + algorithm overhead)
- Memory limit: 8Gi (burst capacity for NetworkX algorithms)
- CPU request: 1 vCPU, limit: 4 vCPU
- Ryugraph threads: 16 (4x CPU for I/O-bound GCS reads)
- Buffer pool: 2GB (optimal for GCS COPY FROM)
- Disk: Persistent volume for buffer pool spilling
- Pod QoS: Burstable (enables memory bursting without eviction risk)

---

## Error Recovery Behavior

### Snapshot Export Failures

| Failure Point | System Behavior | User Action Required |
|---------------|-----------------|---------------------|
| Starburst query fails | Retry 3x with exponential backoff, then fail | User can retry via SDK |
| GCS write fails | Retry 3x with exponential backoff, then fail | User can retry via SDK |
| Worker crashes mid-export | Message redelivered, export restarts | None (automatic) |
| Max retries exhausted | Message to DLQ, status=failed | Contact ops or retry manually |

### Instance Startup Failures

| Failure Point | System Behavior | User Action Required |
|---------------|-----------------|---------------------|
| Pod scheduling fails | Instance marked failed immediately | Create new instance |
| GCS read fails | Instance marked failed | Verify snapshot, create new instance |
| Schema creation fails | Instance marked failed | Check mapping definition |
| Startup timeout (>5 min) | Instance marked failed, pod deleted | Create new instance |

### Partial Failure Semantics

- **Snapshot export:** All-or-nothing. Partial files may exist in GCS but are overwritten on retry.
- **Instance startup:** All-or-nothing. Partial load results in failed instance.
- **Algorithm execution:** All-or-nothing. Partial results are not persisted.

### Maintenance Mode

Ops can enable maintenance mode to gracefully stop accepting new work during upgrades or incidents.

**Behavior when enabled:**

| Request Type | Behavior |
|--------------|----------|
| New resource creation (mappings, snapshots, instances) | Rejected with 503 Service Unavailable |
| Read operations (GET requests) | Allowed |
| In-flight operations (running exports, starting instances) | Continue to completion |
| Terminate/delete operations | Allowed |

**API response during maintenance:**

```json
{
  "error": {
    "code": "SERVICE_UNAVAILABLE",
    "message": "System is in maintenance mode. {maintenance_message}"
  }
}
```

**Configuration:**

- `maintenance_mode`: boolean (default: false)
- `maintenance_message`: string (optional, shown to users)

---

## Observability Requirements

### Metrics (Must Collect)

| Metric | Granularity | Purpose |
|--------|-------------|---------|
| Active instance count | By status, by user | Capacity planning |
| Query latency | p50, p95, p99 | Performance monitoring |
| Algorithm execution time | By algorithm type | Performance monitoring |
| Snapshot export duration | Per snapshot | Pipeline health |
| Memory/disk utilization | Per instance | Resource monitoring |
| Export queue depth | Cluster-wide | Pipeline health |

### Alerting Thresholds

| Condition | Severity | Action |
|-----------|----------|--------|
| Instance failure rate > 10% in 5 min | Critical | Page on-call |
| Export queue depth > 50 | Warning | Notify ops channel |
| Cluster capacity > 80% | Warning | Notify ops channel |
| Control Plane error rate > 5% | Critical | Page on-call |

### SLOs (Targets)

| Metric | Target | Measurement Window |
|--------|--------|-------------------|
| Control Plane availability | 99.5% | Monthly |
| Query latency (p95) | < 10 seconds | Daily |
| Instance startup time (p95) | < 3 minutes | Daily |
| Snapshot export success rate | > 95% | Weekly |

---

## Data Durability Requirements

### Backup Requirements

| Data Store | Backup Frequency | Retention | Recovery Objective |
|------------|------------------|-----------|-------------------|
| Cloud SQL (Control Plane) | Daily automated | 30 days | RPO: 24 hours |
| GCS (Parquet snapshots) | None (source reproducible) | N/A | Re-export from Starburst |

### Recovery Objectives

| Scenario | RTO | RPO | Recovery Method |
|----------|-----|-----|-----------------|
| Control Plane DB corruption | 4 hours | 24 hours | Restore from backup |
| GCS bucket deletion | 8 hours | N/A | Re-export snapshots |
| Single instance failure | Immediate | N/A | Create new instance |
| Cluster failure | 2 hours | 24 hours | Restore DB, re-create instances |

### Data Durability

- GCS: 99.999999999% (11 nines) durability (GCP SLA)
- Cloud SQL: Automated backups with point-in-time recovery
- Instance data: Ephemeral (not backed up, recreatable from snapshot)

---

## Integration Requirements

### Starburst Galaxy Integration

**Reference:** ADR-070: Starburst Galaxy + BigQuery Export Platform

| Aspect | Requirement |
|--------|-------------|
| Service | Starburst Galaxy (managed Trino SaaS) |
| Expected availability | 99% during business hours |
| Query timeout | 30 minutes (configurable) |
| Export method | `system.unload()` with PyArrow fallback |
| Data source | BigQuery tables via Starburst connector |
| Fallback behavior | Automatic PyArrow fallback; fail snapshot with clear error if both paths fail |
| Authentication | Service account with query execution permissions |

**Note:** Local Trino emulation stack has been removed (see ADR-072). E2E tests require network connectivity to Starburst Galaxy.

### GCS Integration

| Aspect | Requirement |
|--------|-------------|
| Required IAM roles | `storage.objectAdmin` on snapshot bucket |
| Authentication | Workload Identity (GKE pods) |
| Bucket location | Same region as GKE cluster |

### Cloud SQL Integration

| Aspect | Requirement |
|--------|-------------|
| Required IAM roles | `cloudsql.client` |
| Authentication | Workload Identity or Cloud SQL Proxy |
| Connection | Private IP within VPC |

---

## Security Baseline Requirements (MVP)

### Encryption

| Data State | Requirement |
|------------|-------------|
| Data in transit | TLS 1.2+ for all external connections |
| Data at rest (Cloud SQL) | Google-managed encryption (default) |
| Data at rest (GCS) | Google-managed encryption (default) |
| Secrets | Stored in Secret Manager, not in code/config |

### Network Isolation

| Boundary | Requirement |
|----------|-------------|
| Control Plane | Internal load balancer, not public |
| Instance pods | Ingress-routed only, no direct public access |
| Cloud SQL | Private IP, no public access |
| GCS | Private Google Access, no public buckets |

### Sensitive Data Classification

| Data Type | Classification | Handling |
|-----------|---------------|----------|
| Graph data | Business Confidential | Access logged, GCS IAM controlled |
| User credentials | N/A | Not stored (external IdP) |
| API keys | Secret | Stored encrypted, rotatable |

---

## User Workflow Example

**Typical analyst workflow (all via Jupyter SDK):**

1. **Create Mapping:** Analyst creates a mapping programmatically using the SDK, defining SQL queries and node/edge definitions in Python
2. **Create Snapshot:** Analyst triggers snapshot creation via SDK; system queues Starburst export job; SDK provides polling methods to wait for completion (status: pending → creating → ready)
3. **Create Instance:** Analyst creates a graph instance from the snapshot via SDK; system provisions pod and loads graph data
4. **Analyze:** Analyst runs Cypher queries and graph algorithms through the SDK, with results returned as DataFrames or visualizations
5. **Collaborate:** Analyst shares notebook with colleague; colleague can see and query all instances via their own SDK connection
6. **Auto-cleanup:** Instance auto-terminates after TTL or inactivity timeout (whichever comes first)

**Versioning workflow:**

1. Analyst creates mapping M1 (v1) with initial node/edge definitions
2. Analyst creates snapshot S1 from M1 (references M1 v1)
3. Analyst edits M1, provides change description → creates M1 v2
4. S1 remains unchanged (still references M1 v1)
5. Analyst creates snapshot S2 from M1 (references M1 v2)
6. Both S1 and S2 coexist; instances can be created from either

**Multi-user scenario:**

- Analyst A creates mapping M1, creates snapshot S1, creates instance I1
- Analyst B sees M1, S1, I1 in their lists (all resources visible)
- Analyst B queries I1 (read access to any instance)
- Analyst B creates their own instance I2 from S1 (B owns I2)
- Analyst B runs algorithms on I2 (can only modify own instances)
- Analyst B cannot delete M1, S1, or I1 (owned by A)

---

## Database Schema (PostgreSQL)

**Tables:** users, mappings, mapping_versions, snapshots, instances, algorithm_locks, global_config, export_queue

**Design:** TEXT for strings/UUIDs/timestamps (ISO 8601), INTEGER for numbers. PostgreSQL required in all environments.

**Audit Event Categories (for external observability stack):**

The following event categories should be captured by the company's external logging/observability stack:

| Category | Event Types |
|----------|-------------|
| **resource** | create, update, delete, copy, set_lifecycle, terminate |
| **query** | execute_cypher, extract_subgraph |
| **algorithm** | algo_start, algo_complete, algo_failed (includes algorithm name, duration) |
| **config** | update_lifecycle_defaults, update_concurrency_limits |
| **auth** | login, logout, token_refresh, permission_denied |
| **system** | snapshot_export_start, snapshot_export_complete, snapshot_export_failed, instance_startup, instance_shutdown, limit_exceeded |

---

## SDK User Experience Requirements

The following UX capabilities are provided through the Jupyter SDK. All user interactions occur via Python code in notebooks.

| # | Requirement | SDK Implementation |
|---|-------------|-------------------|
| 1 | **Progress visibility** | SDK provides `wait_for_*` methods with progress callbacks and status polling for snapshot creation and instance startup. |
| 2 | **Version diffing** | SDK provides `diff_versions()` method to compare mapping versions programmatically. |
| 3 | **Resource relationships view** | SDK provides navigation methods: `mapping.snapshots`, `snapshot.instances`, etc. |
| 4 | **Validation/dry run** | SDK provides `validate()` method to check SQL and mapping definitions before export. |
| 5 | **Favorites/bookmarks** | SDK provides `favorite()` / `unfavorite()` methods for quick access patterns. |

### Progress Visibility (SDK)

**Snapshot Creation Progress:**

The SDK's `create_and_wait()` method provides progress information through callbacks:

| Phase | Status | Available Data |
|-------|--------|----------------|
| pending | `SnapshotStatus.PENDING` | Queue position (if available) |
| creating (nodes) | `SnapshotStatus.CREATING` | Current table, completed tables with row counts |
| creating (edges) | `SnapshotStatus.CREATING` | Current table, completed tables with row counts |
| ready | `SnapshotStatus.READY` | Total size, all row counts |
| failed | `SnapshotStatus.FAILED` | Error message, failed step |

**Instance Startup Progress:**

| Phase | Status | Available Data |
|-------|--------|----------------|
| starting (init) | `InstanceStatus.STARTING` | Pod scheduling status |
| starting (schema) | `InstanceStatus.STARTING` | Schema creation phase |
| starting (nodes) | `InstanceStatus.STARTING` | Current table, completed tables with row counts |
| starting (edges) | `InstanceStatus.STARTING` | Current table, completed tables with row counts |
| running | `InstanceStatus.RUNNING` | Graph stats (node count, edge count) |
| failed | `InstanceStatus.FAILED` | Error message, failed step |

### Error Handling (SDK)

SDK exceptions provide structured error information:

**Exception Types:**

| Exception | When Raised |
|-----------|-------------|
| `PermissionDeniedError` | User lacks permission to modify resource |
| `ConcurrencyLimitError` | Instance limit exceeded (includes current/max counts) |
| `DependencyError` | Resource has dependent resources blocking deletion |
| `ValidationError` | Invalid field values (includes field name and reason) |
| `ResourceLockedError` | Instance locked by running algorithm |
| `ServiceUnavailableError` | External system (Starburst, GCS) unavailable |

**Error Attributes:**

All exceptions include:
- `message`: Human-readable error description
- `code`: Error code for support reference
- `details`: Structured data (e.g., `current_count`, `max_count` for concurrency errors)

### Bulk Operations (SDK)

The SDK supports bulk operations through iteration helpers:

```python
# Terminate multiple instances
for instance in client.instances.list(status="running"):
    instance.terminate()

# Delete snapshots (respects dependencies)
for snapshot in mapping.snapshots:
    try:
        snapshot.delete()
    except DependencyError as e:
        print(f"Skipping {snapshot.name}: {e.message}")
```

### Timestamp Handling

- All timestamps returned as Python `datetime` objects in UTC
- SDK display methods format timestamps in user's local timezone
- Relative formatting available: `snapshot.created_at_relative` returns "2 minutes ago"

---

## Open Questions / TBDs

| # | Area | Question |
|---|------|----------|
| 1 | Networking | How do Jupyter notebooks reach Ryugraph pods? (Ingress path routing? Service mesh?) |
| 2 | Auth | Authentication mechanism for Jupyter SDK? (API keys? OAuth tokens?) |
| 3 | Domain | What domain for Control Plane and Explorer? |
| 4 | Jupyter Location | Where do Jupyter notebooks run? (Same cluster? Same VPC? External?) |
| 5 | Observability | What monitoring/alerting platform is standard in the organization? |
| 6 | Data | What are RTO/RPO requirements for Control Plane database? (Defaults provided, confirm acceptable) |
| 7 | Performance | What are acceptable query latency targets for "typical" queries? (Defaults provided, confirm acceptable) |
| 8 | UX | Should the platform support internationalization/localization? |
| 9 | Compliance | Are there data residency requirements for GCS bucket location? |
| 10 | Operations | What is the expected growth rate (users, instances, data volume)? |

---

## Out of Scope

- Security & compliance (auth, encryption, audit logging, PCI-DSS) - deferred (baseline security requirements captured above)
- Networking configuration (Jupyter runs in separate VPC; connectivity TBD based on target environment)
- Jupyter environment - existing, not building
- Notifications (email, Teams) - deferred
- Persisting algorithm results to snapshots
