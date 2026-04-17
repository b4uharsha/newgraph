---
title: "API Specification: Snapshots"
scope: hsbc
---

# API Specification: Snapshots

> ⚠️ **DEPRECATED - ALL PUBLIC SNAPSHOT ENDPOINTS DISABLED**
>
> The entire public Snapshots API has been disabled. Users cannot list, create, modify,
> or delete snapshots directly via these endpoints.
>
> **Migration path:** Use `POST /api/instances` with `mapping_id` to create an instance
> directly from a mapping. This internally creates a snapshot, runs the export
> pipeline, and starts the instance automatically. See [api.instances.spec.md](api.instances.spec.md).
>
> **Why this was deprecated:**
> - Simplified workflow: users don't need to manage snapshot lifecycle
> - Automatic cleanup: snapshots are tied to instance lifecycle
> - Reduced complexity: one endpoint replaces a multi-step workflow
>
> **What still works:**
> - Internal APIs (export workers, background jobs) remain active - see [api.internal.spec.md](api.internal.spec.md)
> - `GET /snapshots/:id` read-only access remains for debugging
>
> This document is preserved for historical reference.

---

## Overview

REST API specification for Snapshot resource management in the Graph OLAP Platform Control Plane.

> **Note:** The endpoints documented below are **DISABLED**. This documentation
> is preserved for reference only.

## Prerequisites

- [api.common.spec.md](--/api.common.spec.md) - **Authentication, base URL, data formats, response patterns, error codes**
- [requirements.md](--/--/foundation/requirements.md) - Snapshot definition and GCS structure
- [data.model.spec.md](--/data.model.spec.md) - Database schema for snapshots

---

## Endpoints

### List Snapshots

```
GET /snapshots
```

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| mapping_id | uuid | - | Filter by mapping_id |
| mapping_version | integer | - | Filter by mapping_version |
| owner | string | - | Filter by owner_username |
| status | string | - | Filter: pending, creating, ready, failed |
| search | string | - | Text search on name, description |
| created_after | timestamp | - | Filter by created_at >= value |
| created_before | timestamp | - | Filter by created_at <= value |
| sort_by | string | created_at | Sort field: name, created_at, status, size_bytes |
| sort_order | string | desc | asc or desc |
| offset | integer | 0 | Records to skip |
| limit | integer | 50 | Max records (max: 100) |

**Response: 200 OK**

```json
{
  "data": [
    {
      "id": "snapshot-uuid",
      "mapping_id": "mapping-uuid",
      "mapping_name": "Customer Transactions",
      "mapping_version": 3,
      "owner_username": "alice.smith",
      "name": "January 2025 Snapshot",
      "description": "Monthly data export",
      "gcs_path": "gs://bucket/user-uuid/mapping-uuid/snapshot-uuid/",
      "size_bytes": 1073741824,
      "node_counts": {"Customer": 10000, "Product": 5000},
      "edge_counts": {"PURCHASED": 50000},
      "status": "ready",
      "error_message": null,
      "created_at": "2025-01-15T10:30:00Z",
      "updated_at": "2025-01-15T10:35:00Z",
      "ttl": "P7D",
      "inactivity_timeout": "P3D",
      "instance_count": 2
    }
  ],
  "meta": {
    "request_id": "req-uuid",
    "total": 15,
    "offset": 0,
    "limit": 50
  }
}
```

---

### Get Snapshot

```
GET /snapshots/:id
```

**Response: 200 OK**

```json
{
  "data": {
    "id": "snapshot-uuid",
    "mapping_id": "mapping-uuid",
    "mapping_name": "Customer Transactions",
    "mapping_version": 3,
    "owner_username": "alice.smith",
    "name": "January 2025 Snapshot",
    "description": "Monthly data export",
    "gcs_path": "gs://bucket/user-uuid/mapping-uuid/snapshot-uuid/",
    "size_bytes": 1073741824,
    "node_counts": {"Customer": 10000, "Product": 5000},
    "edge_counts": {"PURCHASED": 50000},
    "status": "ready",
    "progress": null,
    "error_message": null,
    "created_at": "2025-01-15T10:30:00Z",
    "updated_at": "2025-01-15T10:35:00Z",
    "ttl": "P7D",
    "inactivity_timeout": "P3D",
    "last_used_at": "2025-01-15T14:00:00Z",
    "instances": [
      {"id": "instance-uuid", "name": "My Analysis", "status": "running"}
    ]
  }
}
```

---

### Create Snapshot

```
POST /snapshots
```

Creates a snapshot and queues Starburst export job.

**Request Body:**

```json
{
  "mapping_id": "mapping-uuid",
  "name": "January 2025 Snapshot",
  "description": "Monthly data export",
  "version": 3,
  "ttl": "P7D",
  "inactivity_timeout": "P3D"
}
```

- `version` is optional; defaults to mapping's current_version

**Response: 201 Created**

```json
{
  "data": {
    "id": "snapshot-uuid",
    "mapping_id": "mapping-uuid",
    "mapping_version": 3,
    "name": "January 2025 Snapshot",
    "status": "pending",
    "created_at": "2025-01-15T10:30:00Z"
  }
}
```

**Response: 404 Not Found** (mapping or version)

```json
{
  "error": {
    "code": "MAPPING_VERSION_NOT_FOUND",
    "message": "Version 5 not found for mapping",
    "details": {"mapping_id": "mapping-uuid", "version": 5}
  }
}
```

---

### Update Snapshot

```
PUT /snapshots/:id
```

Only name and description can be updated.

**Request Body:**

```json
{
  "name": "Updated Snapshot Name",
  "description": "Updated description"
}
```

**Response: 200 OK**

```json
{
  "data": {
    "id": "snapshot-uuid",
    "name": "Updated Snapshot Name",
    "description": "Updated description",
    "updated_at": "2025-01-15T11:00:00Z"
  }
}
```

---

### Delete Snapshot

```
DELETE /snapshots/:id
```

Fails if any active instances exist (status: starting or running). Stopping/failed instances do not block deletion.

**Response: 200 OK**

```json
{
  "data": {"deleted": true}
}
```

**Response: 409 Conflict**

```json
{
  "error": {
    "code": "RESOURCE_HAS_DEPENDENCIES",
    "message": "Cannot delete snapshot with active instances",
    "details": {"active_instance_count": 2, "statuses": ["running", "starting"]}
  }
}
```

---

### Set Snapshot Lifecycle

```
PUT /snapshots/:id/lifecycle
```

**Request Body:**

```json
{
  "ttl": "P14D",
  "inactivity_timeout": "P7D"
}
```

**Response: 200 OK**

```json
{
  "data": {
    "id": "snapshot-uuid",
    "ttl": "P14D",
    "inactivity_timeout": "P7D",
    "updated_at": "2025-01-15T10:30:00Z"
  }
}
```

---

### Retry Failed Snapshot

```
POST /snapshots/:id/retry
```

Re-queues a failed snapshot for export. Only valid when status=failed.

**Response: 200 OK**

```json
{
  "data": {
    "id": "snapshot-uuid",
    "status": "pending",
    "previous_status": "failed",
    "retry_count": 2
  }
}
```

**Response: 409 Conflict** (not failed)

```json
{
  "error": {
    "code": "INVALID_STATE",
    "message": "Can only retry snapshots with status 'failed'",
    "details": {"current_status": "ready"}
  }
}
```

---

### Get Snapshot Progress

```
GET /snapshots/:id/progress
```

Returns detailed progress for snapshots in pending/creating status.

**Response: 200 OK** (creating)

```json
{
  "data": {
    "id": "snapshot-uuid",
    "status": "creating",
    "phase": "exporting_nodes",
    "started_at": "2025-01-15T10:30:00Z",
    "steps": [
      {"name": "Customer", "type": "node", "status": "completed", "row_count": 10000},
      {"name": "Product", "type": "node", "status": "in_progress", "row_count": null},
      {"name": "PURCHASED", "type": "edge", "status": "pending", "row_count": null}
    ],
    "completed_steps": 1,
    "total_steps": 3,
    "elapsed_seconds": 45
  }
}
```

**Response: 200 OK** (ready - no active progress)

```json
{
  "data": {
    "id": "snapshot-uuid",
    "status": "ready",
    "phase": "completed",
    "completed_at": "2025-01-15T10:35:00Z",
    "duration_seconds": 300
  }
}
```

---

## Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| VALIDATION_FAILED | 400 | Request body validation failed |
| RESOURCE_NOT_FOUND | 404 | Snapshot not found |
| MAPPING_VERSION_NOT_FOUND | 404 | Mapping or version not found |
| PERMISSION_DENIED | 403 | User not authorized |
| RESOURCE_HAS_DEPENDENCIES | 409 | Cannot delete (instances exist) |
| INVALID_STATE | 409 | Operation not valid for current state |
