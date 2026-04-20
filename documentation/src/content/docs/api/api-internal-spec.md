---
title: "API Specification: Internal APIs"
scope: hsbc
---

<!-- Verified against code on 2026-04-20 -->

# API Specification: Internal APIs

## Overview

REST API specification for internal communication between system components. These endpoints live under `/api/internal/*` and are not exposed to external clients — they are reachable only from within the cluster network and are protected by `NetworkPolicy` (not by a shared secret).

## Prerequisites

- [api.common.spec.md](--/api.common.spec.md) - **Error response format** (internal APIs use the same error structure)
- [requirements.md](--/--/foundation/requirements.md) - **Mapping definition structure**
- [system.architecture.design.md](--/system.architecture.design.md) - Component communication patterns
- [architectural.guardrails.md](--/--/foundation/architectural.guardrails.md) - Internal authentication patterns

## Authentication (Internal)

Internal endpoints use the **same `X-Username` identity model** as public endpoints
(ADR-104 / ADR-105). There is **no** `Authorization: Bearer` header, **no**
service-account token validation, and **no** `X-Component` header on these
routes. The callers the control-plane expects on these routes are the
export-worker and wrapper pods, each of which runs with a Kubernetes
`ServiceAccount` that is isolated from public traffic by `NetworkPolicy`
(see `packages/control-plane/src/control_plane/config.py:123-124`).

## Base URL

```
http://control-plane.graph-olap-platform.svc.cluster.local:8080/api/internal
```

Internal callers resolve the control plane via ClusterIP inside the `graph-olap-platform` namespace; no ingress hop is involved.

## Constraints

- Internal endpoints are only accessible within the cluster network (enforced by NetworkPolicy)
- All status updates go through Control Plane (single source of truth)
- IDs on all routes are **integers** (PostgreSQL auto-increment), never UUIDs

---

## Worker → Control Plane

### Claim Export Jobs

```
POST /export-jobs/claim
```

Called by Export Worker to atomically claim pending jobs for processing. Uses `SELECT ... FOR UPDATE SKIP LOCKED` internally to prevent race conditions between workers.

**Request Body:**

```json
{
  "worker_id": "export-worker-abc123-xyz",
  "limit": 10
}
```

**Request Body Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| worker_id | string | Yes | Unique identifier for this worker instance (e.g., pod name) |
| limit | integer | No | Maximum jobs to claim (default: 10) |

**Response: 200 OK**

```json
{
  "data": {
    "claimed": 3,
    "jobs": [
      {
        "id": 1,
        "snapshot_id": 42,
        "job_type": "node",
        "entity_name": "Customer",
        "status": "claimed",
        "sql": "SELECT id, name FROM analytics.public.customers",
        "column_names": ["id", "name"],
        "starburst_catalog": "analytics",
        "gcs_path": "gs://bucket/user/42/v1/123/nodes/Customer/",
        "claimed_by": "export-worker-abc123-xyz",
        "claimed_at": "2025-01-15T10:30:00Z"
      }
    ]
  }
}
```

**Response: 200 OK (no jobs available)**

```json
{
  "data": {
    "claimed": 0,
    "jobs": []
  }
}
```

**Notes:**

- Jobs are claimed atomically - no two workers can claim the same job
- Claimed jobs have a lease timeout (10 minutes) - if worker crashes, reconciliation resets them
- Worker should call this periodically to get new work
- Jobs include denormalized `sql`, `column_names`, `starburst_catalog` so worker doesn't need separate mapping fetch

---

### Get Pollable Jobs

```
GET /export-jobs/pollable
```

Called by Export Worker to get jobs that are ready for Starburst status polling.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| limit | integer | 10 | Maximum jobs to return |

**Response: 200 OK**

```json
{
  "data": {
    "jobs": [
      {
        "id": 1,
        "snapshot_id": 42,
        "job_type": "node",
        "entity_name": "Customer",
        "status": "submitted",
        "starburst_query_id": "query_20250115_abc123",
        "next_uri": "https://starburst.example.com/v1/statement/query_20250115_abc123/5",
        "next_poll_at": "2025-01-15T10:30:00Z",
        "poll_count": 3,
        "gcs_path": "gs://bucket/user/42/v1/123/nodes/Customer/"
      }
    ]
  }
}
```

**Notes:**

- Returns jobs where `status = 'submitted'` AND `next_poll_at <= now`
- Worker should poll Starburst for each job and update status accordingly
- Uses `FOR UPDATE SKIP LOCKED` to prevent multiple workers polling same job

---

### Update Snapshot Status

```
PATCH /api/internal/snapshots/{id}/status
```

Called by Export Worker to update snapshot status during processing.
`{id}` is an integer (the `snapshots.id` primary key).

**Request Body (Creating):**

```json
{
  "status": "creating",
  "phase": "exporting_nodes",
  "progress": {
    "current_step": "Customer",
    "completed_steps": 0,
    "total_steps": 3
  }
}
```

**Request Body (Ready):**

```json
{
  "status": "ready",
  "size_bytes": 1073741824,
  "node_counts": {"Customer": 10000, "Product": 5000},
  "edge_counts": {"PURCHASED": 50000}
}
```

**Request Body (Failed):**

```json
{
  "status": "failed",
  "error_message": "Starburst query timeout after 30 minutes",
  "failed_step": "PURCHASED",
  "partial_results": {
    "node_counts": {"Customer": 10000, "Product": 5000},
    "edge_counts": {}
  }
}
```

**Response: 200 OK**

```json
{
  "data": {"updated": true}
}
```

---

### Create Export Jobs

```
POST /snapshots/:id/export-jobs
```

Called by Export Submitter after submitting UNLOAD queries to Starburst. Creates one export_job record per node/edge definition.

**Request Body:**

```json
{
  "jobs": [
    {
      "job_type": "node",
      "entity_name": "Customer",
      "starburst_query_id": "query_20250115_abc123",
      "next_uri": "https://starburst.example.com/v1/statement/query_20250115_abc123/1",
      "gcs_path": "gs://bucket/user/mapping/snapshot/nodes/Customer/",
      "status": "running",
      "submitted_at": "2025-01-15T10:30:00Z"
    },
    {
      "job_type": "node",
      "entity_name": "Product",
      "starburst_query_id": "query_20250115_def456",
      "next_uri": "https://starburst.example.com/v1/statement/query_20250115_def456/1",
      "gcs_path": "gs://bucket/user/mapping/snapshot/nodes/Product/",
      "status": "running",
      "submitted_at": "2025-01-15T10:30:00Z"
    },
    {
      "job_type": "edge",
      "entity_name": "PURCHASED",
      "starburst_query_id": "query_20250115_ghi789",
      "next_uri": "https://starburst.example.com/v1/statement/query_20250115_ghi789/1",
      "gcs_path": "gs://bucket/user/mapping/snapshot/edges/PURCHASED/",
      "status": "running",
      "submitted_at": "2025-01-15T10:30:00Z"
    }
  ]
}
```

**Request Body Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| job_type | string | Yes | `"node"` or `"edge"` |
| entity_name | string | Yes | Node label or edge type name |
| starburst_query_id | string | Yes | Starburst query ID from submission |
| next_uri | string | Yes | Starburst polling URI |
| gcs_path | string | Yes | GCS destination path |
| status | string | No | Initial status (default: `"running"`) |
| submitted_at | timestamp | No | When query was submitted (default: current time) |

**Response: 201 Created**

```json
{
  "data": {
    "created": 3,
    "jobs": [
      {"id": 1, "entity_name": "Customer", "status": "running"},
      {"id": 2, "entity_name": "Product", "status": "running"},
      {"id": 3, "entity_name": "PURCHASED", "status": "running"}
    ]
  }
}
```

**Response: 404 Not Found** (snapshot doesn't exist)

**Response: 409 Conflict** (jobs already exist for this snapshot)

---

### List Export Jobs

```
GET /snapshots/:id/export-jobs
```

Called by Export Poller to get export jobs for polling. Returns jobs that need attention.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| status | string | - | Filter by status: pending, running, completed, failed |

**Response: 200 OK**

```json
{
  "data": {
    "jobs": [
      {
        "id": 1,
        "snapshot_id": 42,
        "job_type": "node",
        "entity_name": "Customer",
        "status": "running",
        "starburst_query_id": "query_20250115_abc123",
        "next_uri": "https://starburst.example.com/v1/statement/query_20250115_abc123/5",
        "gcs_path": "gs://bucket/user/mapping/snapshot/nodes/Customer/",
        "row_count": null,
        "size_bytes": null,
        "submitted_at": "2025-01-15T10:30:00Z",
        "completed_at": null,
        "error_message": null
      },
      {
        "id": 2,
        "snapshot_id": 42,
        "job_type": "node",
        "entity_name": "Product",
        "status": "completed",
        "starburst_query_id": "query_20250115_def456",
        "next_uri": null,
        "gcs_path": "gs://bucket/user/mapping/snapshot/nodes/Product/",
        "row_count": 5000,
        "size_bytes": 1048576,
        "submitted_at": "2025-01-15T10:30:00Z",
        "completed_at": "2025-01-15T10:32:00Z",
        "error_message": null
      }
    ]
  }
}
```

---

### Update Export Job

```
PATCH /export-jobs/:id
```

Called by Export Worker to update a single export job's status, polling state, and results.

**Request Body (Mark as Submitted - after Starburst accepts query):**

```json
{
  "status": "submitted",
  "starburst_query_id": "query_20250115_abc123",
  "next_uri": "https://starburst.example.com/v1/statement/query_20250115_abc123/1",
  "next_poll_at": "2025-01-15T10:30:05Z",
  "poll_count": 1,
  "submitted_at": "2025-01-15T10:30:00Z"
}
```

**Request Body (Update polling state - query still running):**

```json
{
  "next_uri": "https://starburst.example.com/v1/statement/query_20250115_abc123/10",
  "next_poll_at": "2025-01-15T10:30:35Z",
  "poll_count": 5
}
```

**Request Body (Completed):**

```json
{
  "status": "completed",
  "row_count": 10000,
  "size_bytes": 2097152,
  "completed_at": "2025-01-15T10:35:00Z"
}
```

**Request Body (Failed):**

```json
{
  "status": "failed",
  "error_message": "Starburst query failed: QUERY_EXCEEDED_TIME_LIMIT",
  "completed_at": "2025-01-15T10:35:00Z"
}
```

**Request Body Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| status | string | No | New status: `"submitted"`, `"completed"`, `"failed"` |
| starburst_query_id | string | No | Query ID from Starburst (set when submitted) |
| next_uri | string | No | Updated Starburst polling URI |
| next_poll_at | timestamp | No | When to poll next (for stateless backoff) |
| poll_count | integer | No | Current poll count (for Fibonacci backoff calculation) |
| submitted_at | timestamp | No | When query was submitted to Starburst |
| row_count | integer | No | Final row count (set when completed) |
| size_bytes | integer | No | Final size in bytes (set when completed) |
| completed_at | timestamp | No | When job completed (default: current time if status=completed/failed) |
| error_message | string | No | Error details (set when failed) |

**Row Count Semantics:**

| Value | Meaning |
|-------|---------|
| `null` | Count not yet attempted (job still in progress) |
| `0` | Count successful, table/query returned no rows |
| `n > 0` | Count successful, n rows exported |

Note: On GCS read failure, mark job as `failed` with `error_message` rather than setting `row_count = 0`. A null row count with `completed` status should never occur; the worker must always count rows before completing.

**Response: 200 OK**

```json
{
  "data": {
    "id": 1,
    "snapshot_id": 42,
    "status": "completed",
    "row_count": 10000,
    "size_bytes": 2097152,
    "completed_at": "2025-01-15T10:35:00Z"
  }
}
```

**Response: 404 Not Found** (export job doesn't exist)

**Notes:**

- `next_poll_at` and `poll_count` enable **stateless** Fibonacci backoff - worker doesn't need to track in memory
- When job status changes to `completed` or `failed`, Control Plane checks if all jobs for snapshot are done
- If all jobs `completed`: snapshot status → `ready`
- If any job `failed`: snapshot status → `failed` (after all jobs finish)
- See [data.model.spec.md](--/data.model.spec.md#export_jobs) for the complete export_jobs table schema

---

## Wrapper Pod → Control Plane

### Update Instance Status

```
PATCH /api/internal/instances/{id}/status
```

Called by Wrapper Pod to report status changes. `{id}` is an integer (the
`instances.id` primary key).

**Request Body (Running):**

```json
{
  "status": "running",
  "pod_ip": "10.0.0.42",
  "instance_url": "https://control-plane-graph-olap-platform.hsbc-12636856-udlhk-dev.dev.gcp.cloud.hk.hsbc/inst-42/",
  "graph_stats": {
    "node_count": 15000,
    "edge_count": 50000
  }
}
```

**Request Body (Failed):**

```json
{
  "status": "failed",
  "error_code": "DATA_LOAD_ERROR",
  "error_message": "Failed to load edges: file not found",
  "failed_phase": "loading_edges",
  "stack_trace": "Traceback (most recent call last):\n  File \"/app/wrapper/lifespan.py\", line 142..."
}
```

**Request Body Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| status | string | Yes | `starting`, `running`, `stopping`, `failed` |
| pod_ip | string | No | Pod IP address (set when running) |
| instance_url | string | No | Instance URL (set when running) |
| graph_stats | object | No | Node/edge counts (set when running) |
| error_code | string | No | Machine-readable error code (set when failed) |
| error_message | string | No | Human-readable error message (set when failed) |
| failed_phase | string | No | Phase when failure occurred (set when failed) |
| stack_trace | string | No | Stack trace for debugging (set when failed) |

**Error Codes:**

| Code | Description |
|------|-------------|
| STARTUP_FAILED | General startup failure |
| MAPPING_FETCH_ERROR | Failed to fetch mapping from Control Plane |
| SCHEMA_CREATE_ERROR | Failed to create Ryugraph schema |
| FALKORDB_SCHEMA_CREATE_ERROR | Failed to create FalkorDB schema |
| DATA_LOAD_ERROR | Failed to load Parquet data from GCS |
| DATABASE_ERROR | Ryugraph database error |
| FALKORDB_DATABASE_ERROR | FalkorDB database error |
| OOM_KILLED | Pod killed due to memory limit |

**Response: 200 OK**

```json
{
  "data": {"updated": true}
}
```

---

### Update Instance Metrics

```
PUT /instances/:id/metrics
```

Called periodically by Wrapper Pod to report resource usage.

**Request Body:**

```json
{
  "memory_usage_bytes": 536870912,
  "disk_usage_bytes": 1073741824,
  "last_activity_at": "2025-01-15T14:00:00Z",
  "query_count_since_last": 15,
  "avg_query_time_ms": 25
}
```

**Response: 200 OK**

```json
{
  "data": {"updated": true}
}
```

---

### Report Instance Progress

```
PUT /instances/:id/progress
```

Called during instance startup to report loading progress.

**Request Body:**

```json
{
  "phase": "loading_nodes",
  "steps": [
    {"name": "pod_scheduled", "status": "completed"},
    {"name": "schema_created", "status": "completed"},
    {"name": "Customer", "type": "node", "status": "completed", "row_count": 10000},
    {"name": "Product", "type": "node", "status": "in_progress", "row_count": null},
    {"name": "PURCHASED", "type": "edge", "status": "pending"}
  ]
}
```

**Response: 200 OK**

```json
{
  "data": {"updated": true}
}
```

**Note:** Audit events (queries, algorithms) are sent directly to the company's external observability stack, not through Control Plane.

---

### Get Instance Mapping

```
GET /instances/:id/mapping
```

Called by Wrapper Pod during startup to retrieve the mapping definition for schema creation.

**Response: 200 OK** (see [requirements.md](--/--/foundation/requirements.md) for node_definitions/edge_definitions schema; note: `sql` field omitted as not needed for schema creation)

```json
{
  "data": {
    "snapshot_id": 42,
    "mapping_id": 123,
    "mapping_version": 3,
    "gcs_path": "gs://bucket/mapping-7/snapshot-42/",
    "node_definitions": ["..."],
    "edge_definitions": ["..."]
  }
}
```

**Response: 404 Not Found** (instance doesn't exist)

---

### Record Instance Activity

```
POST /instances/:id/activity
```

Called by Wrapper Pod when queries or algorithms are executed to update `last_activity_at` timestamp.

**Request Body:** None (empty)

**Response: 204 No Content**

---

## Control Plane → Wrapper Pod

There is no Control Plane → Wrapper Pod internal API. Wrapper-pod lifecycle
(spawn / terminate) is driven by the Kubernetes API (the control plane uses
the Python K8s client to create and delete wrapper pods directly). There is
no `POST /shutdown` endpoint on either wrapper — when the control plane
terminates an instance, it deletes the pod via the K8s API.

---

## Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| RESOURCE_NOT_FOUND | 404 | Instance/snapshot/export_job not found |
| INVALID_STATE_TRANSITION | 409 | Status change not allowed |
| JOBS_ALREADY_EXIST | 409 | Export jobs already created for this snapshot |
| STARBURST_ERROR | 500 | Starburst connection/query error |
