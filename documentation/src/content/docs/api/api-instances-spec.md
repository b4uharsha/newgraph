---
title: "API Specification: Instances"
scope: hsbc
---

# API Specification: Instances

## Overview

REST API specification for Graph Instance resource management in the Graph OLAP Platform Control Plane.

## Prerequisites

- [api.common.spec.md](--/api.common.spec.md) - **Authentication, base URL, data formats, response patterns, error codes**
- [requirements.md](--/--/foundation/requirements.md) - Instance definition, lock model
- [data.model.spec.md](--/data.model.spec.md) - Database schema for instances

---

## Endpoints Summary

| Method | Path | Description |
|--------|------|-------------|
| GET | `/instances` | List instances with filters |
| POST | `/instances` | Create instance from mapping |
| GET | `/instances/{id}` | Get instance details |
| PUT | `/instances/{id}` | Update instance metadata |
| DELETE | `/instances/{id}` | Delete instance |
| PUT | `/instances/{id}/lifecycle` | Update TTL and timeout |
| PUT | `/instances/{id}/cpu` | Update CPU cores |
| GET | `/instances/{id}/progress` | Get startup progress |
| GET | `/instances/{id}/events` | Get instance events |
| GET | `/instances/user/status` | Get user's instance status |

---

## Endpoints

### List Instances

```
GET /instances
```

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| snapshot_id | uuid | - | Filter by snapshot_id |
| owner | string | - | Filter by owner_username |
| status | string | - | Filter: waiting_for_snapshot, starting, running, stopping, failed |
| search | string | - | Text search on name, description |
| created_after | timestamp | - | Filter by created_at >= value |
| created_before | timestamp | - | Filter by created_at <= value |
| sort_by | string | created_at | Sort field: name, created_at, status, last_activity_at, memory_usage_bytes |
| sort_order | string | desc | asc or desc |
| offset | integer | 0 | Records to skip |
| limit | integer | 50 | Max records (max: 100) |

**Response: 200 OK**

```json
{
  "data": [
    {
      "id": "instance-uuid",
      "snapshot_id": "snapshot-uuid",
      "snapshot_name": "January 2025 Snapshot",
      "owner_username": "alice.smith",
      "wrapper_type": "ryugraph",
      "name": "My Analysis Instance",
      "description": "PageRank analysis",
      "instance_url": "https://graph.example.com/instance-uuid/",
      "status": "running",
      "error_code": null,
      "error_message": null,
      "created_at": "2025-01-15T10:30:00Z",
      "started_at": "2025-01-15T10:32:00Z",
      "last_activity_at": "2025-01-15T14:00:00Z",
      "ttl": "PT24H",
      "inactivity_timeout": "PT4H",
      "memory_usage_bytes": 536870912,
      "disk_usage_bytes": 1073741824
    }
  ],
  "meta": {
    "request_id": "req-uuid",
    "total": 8,
    "offset": 0,
    "limit": 50
  }
}
```

---

### Get Instance

```
GET /instances/:id
```

**Response: 200 OK**

```json
{
  "data": {
    "id": "instance-uuid",
    "snapshot_id": "snapshot-uuid",
    "snapshot_name": "January 2025 Snapshot",
    "mapping_id": "mapping-uuid",
    "mapping_name": "Customer Transactions",
    "mapping_version": 3,
    "owner_username": "alice.smith",
    "wrapper_type": "ryugraph",
    "name": "My Analysis Instance",
    "description": "PageRank analysis",
    "instance_url": "https://graph.example.com/instance-uuid/",
    "pod_name": "graph-instance-abc123",
    "status": "running",
    "progress": null,
    "error_code": null,
    "error_message": null,
    "stack_trace": null,
    "created_at": "2025-01-15T10:30:00Z",
    "updated_at": "2025-01-15T14:00:00Z",
    "started_at": "2025-01-15T10:32:00Z",
    "last_activity_at": "2025-01-15T14:00:00Z",
    "ttl": "PT24H",
    "inactivity_timeout": "PT4H",
    "memory_usage_bytes": 536870912,
    "disk_usage_bytes": 1073741824
  }
}
```

**Response (Failed Instance):**

```json
{
  "data": {
    "id": "instance-uuid",
    "snapshot_id": "snapshot-uuid",
    "snapshot_name": "January 2025 Snapshot",
    "mapping_id": "mapping-uuid",
    "mapping_name": "Customer Transactions",
    "mapping_version": 3,
    "owner_username": "alice.smith",
    "wrapper_type": "falkordb",
    "name": "My Analysis Instance",
    "description": "PageRank analysis",
    "instance_url": null,
    "pod_name": "graph-instance-abc123",
    "status": "failed",
    "progress": null,
    "error_code": "DATA_LOAD_ERROR",
    "error_message": "Failed to load Customer nodes: gs://bucket/path not found",
    "stack_trace": "Traceback (most recent call last):\n  File \"/app/wrapper/lifespan.py\"...",
    "created_at": "2025-01-15T10:30:00Z",
    "updated_at": "2025-01-15T10:31:30Z",
    "started_at": null,
    "last_activity_at": null,
    "ttl": "PT24H",
    "inactivity_timeout": "PT4H",
    "memory_usage_bytes": null,
    "disk_usage_bytes": null
  }
}
```

**Notes:**

- Lock status is not tracked by Control Plane. Query `GET /{instance-id}/lock` on the Wrapper Pod directly.
- `stack_trace` is only included in the detail view (GET /instances/:id), not in list view, to reduce payload size.
- `stack_trace` may be null even for failed instances if the error was captured without a traceback.

---

### Create Instance

```
POST /instances
```

Create a new instance from a mapping. This endpoint automatically creates a snapshot from the mapping and queues instance creation. The instance will transition through `waiting_for_snapshot` -> `starting` -> `running`.

**Request Body:**

```json
{
  "mapping_id": 1,
  "name": "My Analysis Instance",
  "wrapper_type": "ryugraph",
  "mapping_version": 2,
  "description": "PageRank analysis on latest data",
  "ttl": "PT48H",
  "inactivity_timeout": "PT24H",
  "cpu_cores": 4
}
```

**Request Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `mapping_id` | integer | ✓ Yes | ID of the mapping to create snapshot from (must be > 0) |
| `name` | string | ✓ Yes | Instance display name (1-255 chars) |
| `wrapper_type` | string | ✓ Yes | Graph database wrapper: `ryugraph` or `falkordb` |
| `mapping_version` | integer | No | Specific mapping version to use (defaults to current version) |
| `description` | string | No | Optional description (max 4000 chars) |
| `ttl` | duration | No | Time-to-live (ISO 8601 duration, e.g. `PT48H`) |
| `inactivity_timeout` | duration | No | Auto-terminate after inactivity (must be ≤ TTL) |
| `cpu_cores` | integer | No | CPU cores for the instance (1-8, default: 2). Sets request=N, limit=2N for burst capacity. |

**Wrapper Types:**

| Value | Description | Memory | Features |
|-------|-------------|--------|----------|
| `ryugraph` | Ryugraph (KuzuDB) | 4-8Gi | NetworkX ✓, Bulk import ✓, Buffer pool + disk |
| `falkordb` | FalkorDB Lite | 6-12Gi | Cypher procedures, In-memory only |

See ADR-049 for wrapper comparison.

**Response: 201 Created**

```json
{
  "data": {
    "id": "instance-uuid",
    "snapshot_id": null,
    "wrapper_type": "ryugraph",
    "name": "My Analysis Instance",
    "status": "waiting_for_snapshot",
    "created_at": "2025-01-15T10:30:00Z"
  }
}
```

**Notes:**

- The `snapshot_id` will be `null` initially and populated once the snapshot is created.
- Instance status will be `waiting_for_snapshot` until the snapshot creation completes.
- Once the snapshot is ready, the instance automatically transitions to `starting`.

**Response: 404 Not Found**

```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "Mapping not found",
    "details": {
      "mapping_id": 1
    }
  }
}
```

**Response: 409 Conflict (Concurrency Limit)**

```json
{
  "error": {
    "code": "CONCURRENCY_LIMIT_EXCEEDED",
    "message": "Cannot create instance: analyst limit exceeded",
    "details": {
      "current_count": 5,
      "max_allowed": 5,
      "limit_type": "per_analyst"
    }
  }
}
```

**Response: 422 Unprocessable Entity**

```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "Invalid request body",
    "details": {
      "mapping_id": "must be greater than 0",
      "name": "must be between 1 and 255 characters"
    }
  }
}
```

---

### Update Instance

> **Internal Use Only:** This endpoint is primarily for internal metadata updates.
> Set name and description at instance creation time via `POST /instances/from-mapping`.

```
PUT /instances/:id
```

Only name and description can be updated.

**Request Body:**

```json
{
  "name": "Updated Instance Name",
  "description": "Updated description"
}
```

**Response: 200 OK**

```json
{
  "data": {
    "id": "instance-uuid",
    "name": "Updated Instance Name",
    "description": "Updated description",
    "updated_at": "2025-01-15T11:00:00Z"
  }
}
```

---

### Delete Instance

> **Prefer TTL-based cleanup:** Set `ttl` at creation time via `POST /instances`
> to enable automatic cleanup. Use this endpoint only for immediate cleanup when needed.

```
DELETE /instances/:id
```

Terminates and deletes the instance. Immediately deletes K8s resources (pod, service, ingress) and removes the instance from the database.

**Response: 204 No Content**

(No response body)

---

### Set Instance Lifecycle

> **Prefer setting lifecycle at creation:** Set `ttl` and `inactivity_timeout`
> parameters when calling `POST /instances`. Use this endpoint
> only when you need to modify an already-running instance.

```
PUT /instances/:id/lifecycle
```

**Request Body:**

```json
{
  "ttl": "PT48H",
  "inactivity_timeout": "PT8H"
}
```

**Response: 200 OK**

```json
{
  "data": {
    "id": "instance-uuid",
    "ttl": "PT48H",
    "inactivity_timeout": "PT8H",
    "updated_at": "2025-01-15T10:30:00Z"
  }
}
```

---

### Get Instance Progress

```
GET /instances/:id/progress
```

Returns detailed progress for instances in starting status.

**Response: 200 OK** (starting)

```json
{
  "data": {
    "id": "instance-uuid",
    "status": "starting",
    "phase": "loading_data",
    "started_at": "2025-01-15T10:30:00Z",
    "steps": [
      {"name": "pod_scheduled", "status": "completed", "completed_at": "2025-01-15T10:30:05Z"},
      {"name": "schema_created", "status": "completed", "completed_at": "2025-01-15T10:30:10Z"},
      {"name": "nodes_loaded", "status": "in_progress", "tables": ["Customer", "Product"]},
      {"name": "edges_loaded", "status": "pending", "tables": ["PURCHASED"]}
    ],
    "completed_steps": 2,
    "total_steps": 4,
    "elapsed_seconds": 15
  }
}
```

**Response: 200 OK** (running - no active progress)

```json
{
  "data": {
    "id": "instance-uuid",
    "status": "running",
    "phase": "ready",
    "started_at": "2025-01-15T10:30:00Z",
    "ready_at": "2025-01-15T10:32:00Z",
    "startup_duration_seconds": 120
  }
}
```

---

### Update Instance CPU

```
PUT /instances/:id/cpu
```

Update CPU cores for a running instance using K8s in-place resize.

**Request Body:**

```json
{
  "cpu_cores": 4
}
```

**Request Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `cpu_cores` | integer | ✓ Yes | CPU cores (1-8). Sets request=N cores, limit=2N cores for burst capacity. |

**Response: 200 OK**

```json
{
  "data": {
    "id": "instance-uuid",
    "cpu_cores": 4,
    "updated_at": "2025-01-15T10:30:00Z"
  }
}
```

**Response: 409 Conflict** (Instance not running)

```json
{
  "error": {
    "code": "INVALID_STATE",
    "message": "Can only update CPU for running instances",
    "details": {
      "current_status": "starting"
    }
  }
}
```

---

### Get Instance Events

```
GET /instances/:id/events
```

Returns resource events for an instance, such as memory upgrades, CPU updates, and OOM recoveries.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| offset | integer | 0 | Records to skip |
| limit | integer | 50 | Max records (max: 100) |

**Response: 200 OK**

```json
{
  "data": [
    {
      "id": 1,
      "event_type": "cpu_updated",
      "details": {
        "old_cpu_cores": 2,
        "new_cpu_cores": 4
      },
      "created_at": "2025-01-15T10:30:00Z"
    },
    {
      "id": 2,
      "event_type": "memory_upgraded",
      "details": {
        "old_memory_bytes": 4294967296,
        "new_memory_bytes": 8589934592,
        "reason": "oom_recovery"
      },
      "created_at": "2025-01-15T10:25:00Z"
    }
  ],
  "meta": {
    "total": 2,
    "offset": 0,
    "limit": 50
  }
}
```

---

### Get User Status

```
GET /instances/user/status
```

Returns instance status for the current authenticated user, including active instance count and limits.

**Response: 200 OK**

```json
{
  "data": {
    "username": "alice.smith",
    "active_instances": 3,
    "instance_limit": 5,
    "instances_available": 2,
    "instances": [
      {
        "id": 1,
        "name": "Analysis Instance",
        "status": "running",
        "created_at": "2025-01-15T10:00:00Z"
      },
      {
        "id": 2,
        "name": "Test Instance",
        "status": "starting",
        "created_at": "2025-01-15T10:30:00Z"
      }
    ]
  }
}
```

---

## Instance Status Values

| Status | Description |
|--------|-------------|
| `waiting_for_snapshot` | Instance created, waiting for snapshot creation to complete |
| `starting` | Pod scheduled and loading data from snapshot |
| `running` | Instance ready and accepting queries |
| `stopping` | Graceful shutdown in progress |
| `failed` | Instance failed to start or encountered fatal error |

**Status Transitions:**

```
waiting_for_snapshot -> starting -> running -> stopping -> (deleted)
                    \            \
                     \            -> failed
                      -> failed
```

---

## Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| VALIDATION_FAILED | 400 | Request body validation failed |
| RESOURCE_NOT_FOUND | 404 | Instance not found |
| PERMISSION_DENIED | 403 | User not authorized |
| CONCURRENCY_LIMIT_EXCEEDED | 409 | Instance limit reached |
| SNAPSHOT_NOT_READY | 409 | Cannot create from non-ready snapshot |
| RESOURCE_LOCKED | 409 | Instance locked by algorithm |
| SERVICE_UNAVAILABLE | 503 | Maintenance mode (create rejected) |
