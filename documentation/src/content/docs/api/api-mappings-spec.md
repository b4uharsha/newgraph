---
title: "API Specification: Mappings"
scope: hsbc
---

<!-- Verified against code on 2026-04-20 -->

# API Specification: Mappings

## Overview

REST API specification for Mapping resource management in the Graph OLAP Platform Control Plane.

## Prerequisites

- [api.common.spec.md](--/api.common.spec.md) - **Authentication, base URL, data formats, response patterns, error codes**
- [requirements.md](--/--/foundation/requirements.md) - **Mapping definition structure (node_definitions, edge_definitions JSON schema)**
- [data.model.spec.md](--/data.model.spec.md) - Database schema for mappings and mapping_versions

---

## Endpoints Summary

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/mappings` | List mappings with filters |
| POST | `/api/mappings` | Create a new mapping |
| GET | `/api/mappings/{id}` | Get mapping with current version |
| PUT | `/api/mappings/{id}` | Update mapping (creates new version) |
| DELETE | `/api/mappings/{id}` | Delete mapping |
| POST | `/api/mappings/{id}/copy` | Copy mapping to new owner |
| PUT | `/api/mappings/{id}/lifecycle` | Update TTL and timeout |
| GET | `/api/mappings/{id}/tree` | Get resource tree (versions -> snapshots -> instances) |
| GET | `/api/mappings/{id}/versions` | List all versions |
| GET | `/api/mappings/{id}/versions/{v}` | Get specific version |
| GET | `/api/mappings/{id}/versions/{v1}/diff/{v2}` | Compare two versions |
| GET | `/api/mappings/{id}/snapshots` | List snapshots for mapping |
| GET | `/api/mappings/{id}/instances` | List instances for mapping |

---

## Endpoints

### List Mappings

```
GET /api/mappings
```

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| owner | string | - | Filter by owner_username |
| search | string | - | Text search on name, description |
| created_after | timestamp | - | Filter by created_at >= value |
| created_before | timestamp | - | Filter by created_at <= value |
| sort_by | string | created_at | Sort field: name, created_at, current_version |
| sort_order | string | desc | asc or desc |
| offset | integer | 0 | Records to skip |
| limit | integer | 50 | Max records (max: 100) |

**Response: 200 OK**

```json
{
  "data": [
    {
      "id": 42,
      "owner_username": "alice.smith",
      "name": "Customer Transactions",
      "description": "Graph mapping for customer purchase behavior",
      "current_version": 3,
      "created_at": "2025-01-10T08:00:00Z",
      "updated_at": "2025-01-15T10:30:00Z",
      "ttl": null,
      "inactivity_timeout": "P30D",
      "snapshot_count": 5
    }
  ],
  "meta": {
    "request_id": "req-uuid",
    "total": 42,
    "offset": 0,
    "limit": 50
  }
}
```

---

### Get Mapping

```
GET /api/mappings/:id
```

Returns mapping header with current version details.

**Response: 200 OK** (see [requirements.md](--/--/foundation/requirements.md) for node_definitions/edge_definitions schema)

```json
{
  "data": {
    "id": 42,
    "owner_username": "alice.smith",
    "name": "Customer Transactions",
    "description": "Graph mapping for customer purchase behavior",
    "current_version": 3,
    "created_at": "2025-01-10T08:00:00Z",
    "updated_at": "2025-01-15T10:30:00Z",
    "ttl": null,
    "inactivity_timeout": "P30D",
    "version": {
      "version": 3,
      "change_description": "Added product category property",
      "node_definitions": ["..."],
      "edge_definitions": ["..."],
      "created_at": "2025-01-15T10:30:00Z",
      "created_by": "user-uuid",
      "created_by_name": "Alice Smith"
    }
  }
}
```

**Response: 404 Not Found**

```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "Mapping not found",
    "details": {"id": 42}
  }
}
```

---

### Create Mapping

```
POST /api/mappings
```

**Request Body:** (see [requirements.md](--/--/foundation/requirements.md) for node_definitions/edge_definitions schema)

```json
{
  "name": "Customer Transactions",
  "description": "Graph mapping for customer purchase behavior",
  "node_definitions": ["..."],
  "edge_definitions": ["..."],
  "ttl": null,
  "inactivity_timeout": "P30D"
}
```

**Response: 201 Created**

```json
{
  "data": {
    "id": 42,
    "owner_username": "alice.smith",
    "name": "Customer Transactions",
    "current_version": 1,
    "created_at": "2025-01-15T10:30:00Z"
  }
}
```

**Response: 400 Bad Request**

```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "Invalid request body",
    "details": {
      "errors": [
        {"field": "node_definitions[0].label", "message": "Label is required"},
        {"field": "edge_definitions[0].from_node", "message": "Referenced node 'Customer' not found in node_definitions"}
      ]
    }
  }
}
```

---

### Update Mapping (Create New Version)

```
PUT /api/mappings/:id
```

Creates a new immutable version. Requires change_description.

**Request Body:**

```json
{
  "name": "Customer Transactions v2",
  "description": "Updated description",
  "change_description": "Added product category property",
  "node_definitions": ["..."],
  "edge_definitions": ["..."]
}
```

**Response: 200 OK**

```json
{
  "data": {
    "id": 42,
    "current_version": 4,
    "updated_at": "2025-01-15T11:00:00Z"
  }
}
```

**Response: 400 Bad Request** (missing change_description)

```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "change_description is required when updating mapping definitions",
    "details": {"field": "change_description"}
  }
}
```

**Response: 403 Forbidden**

```json
{
  "error": {
    "code": "PERMISSION_DENIED",
    "message": "Only owner or admin can update this mapping",
    "details": {"owner_username": "other.user", "your_role": "analyst"}
  }
}
```

---

### Delete Mapping

```
DELETE /api/mappings/:id
```

Fails if any snapshots exist for any version.

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
    "message": "Cannot delete mapping with existing snapshots",
    "details": {"snapshot_count": 3}
  }
}
```

---

### Copy Mapping

```
POST /api/mappings/:id/copy
```

Creates a new mapping with the current version's definitions. Caller becomes owner.

**Request Body:**

```json
{
  "name": "My Copy of Customer Transactions"
}
```

**Response: 201 Created**

```json
{
  "data": {
    "id": 43,
    "owner_username": "alice.smith",
    "name": "My Copy of Customer Transactions",
    "current_version": 1,
    "created_at": "2025-01-15T10:30:00Z"
  }
}
```

---

### Set Mapping Lifecycle

```
PUT /api/mappings/:id/lifecycle
```

**Request Body:**

```json
{
  "ttl": "P90D",
  "inactivity_timeout": "P30D"
}
```

**Response: 200 OK**

```json
{
  "data": {
    "id": 42,
    "ttl": "P90D",
    "inactivity_timeout": "P30D",
    "updated_at": "2025-01-15T10:30:00Z"
  }
}
```

**Response: 400 Bad Request** (exceeds hard limit)

```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "TTL exceeds maximum allowed",
    "details": {"requested": "P400D", "max_allowed": "P365D"}
  }
}
```

---

### List Mapping Versions

```
GET /api/mappings/:id/versions
```

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
      "version": 3,
      "change_description": "Added product category property",
      "created_at": "2025-01-15T10:30:00Z",
      "created_by": "user-uuid",
      "created_by_name": "Alice Smith"
    },
    {
      "version": 2,
      "change_description": "Fixed customer SQL query",
      "created_at": "2025-01-12T14:00:00Z",
      "created_by": "user-uuid",
      "created_by_name": "Alice Smith"
    },
    {
      "version": 1,
      "change_description": null,
      "created_at": "2025-01-10T08:00:00Z",
      "created_by": "user-uuid",
      "created_by_name": "Alice Smith"
    }
  ],
  "meta": {"total": 3, "offset": 0, "limit": 50}
}
```

---

### Get Mapping Version

```
GET /api/mappings/:id/versions/:version
```

**Response: 200 OK**

```json
{
  "data": {
    "mapping_id": 42,
    "version": 2,
    "change_description": "Fixed customer SQL query",
    "node_definitions": ["..."],
    "edge_definitions": ["..."],
    "created_at": "2025-01-12T14:00:00Z",
    "created_by": "user-uuid",
    "created_by_name": "Alice Smith"
  }
}
```

**Response: 404 Not Found**

```json
{
  "error": {
    "code": "MAPPING_VERSION_NOT_FOUND",
    "message": "Version 5 not found for mapping",
    "details": {"mapping_id": 42, "version": 5, "latest_version": 3}
  }
}
```

---

### Compare Mapping Versions (Diff)

```
GET /api/mappings/:id/versions/:v1/diff/:v2
```

Returns a diff between two versions of a mapping, showing added, removed, and modified node/edge definitions.

**Response: 200 OK**

```json
{
  "data": {
    "mapping_id": 42,
    "from_version": 2,
    "to_version": 3,
    "summary": {
      "nodes_added": 1,
      "nodes_removed": 0,
      "nodes_modified": 1,
      "edges_added": 0,
      "edges_removed": 0,
      "edges_modified": 1
    },
    "changes": {
      "nodes": [
        {
          "label": "Customer",
          "change_type": "modified",
          "fields_changed": ["sql", "properties"],
          "from": {
            "sql": "SELECT customer_id, name FROM analytics.customers",
            "properties": [{"name": "name", "type": "STRING"}]
          },
          "to": {
            "sql": "SELECT customer_id, name, city FROM analytics.customers",
            "properties": [
              {"name": "name", "type": "STRING"},
              {"name": "city", "type": "STRING"}
            ]
          }
        },
        {
          "label": "Supplier",
          "change_type": "added",
          "from": null,
          "to": {
            "label": "Supplier",
            "sql": "SELECT supplier_id, name FROM analytics.suppliers",
            "primary_key": {"name": "supplier_id", "type": "STRING"},
            "properties": [{"name": "name", "type": "STRING"}]
          }
        }
      ],
      "edges": [
        {
          "type": "PURCHASED",
          "change_type": "modified",
          "fields_changed": ["properties"],
          "from": {
            "properties": [{"name": "amount", "type": "DOUBLE"}]
          },
          "to": {
            "properties": [
              {"name": "amount", "type": "DOUBLE"},
              {"name": "purchase_date", "type": "DATE"}
            ]
          }
        }
      ]
    }
  }
}
```

**Response: 404 Not Found**

```json
{
  "error": {
    "code": "MAPPING_VERSION_NOT_FOUND",
    "message": "Version 5 not found for mapping",
    "details": {"mapping_id": 42, "version": 5, "latest_version": 3}
  }
}
```

---

### Get Mapping Resource Tree

```
GET /api/mappings/:id/tree
```

Returns the full hierarchy of versions, snapshots, and instances for a mapping.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| include_instances | boolean | true | Include instance details in response |
| status | string | - | Filter snapshots by status |

**Response: 200 OK**

```json
{
  "data": {
    "id": 42,
    "name": "Customer Transactions",
    "owner_username": "alice.smith",
    "current_version": 3,
    "versions": [
      {
        "version": 3,
        "change_description": "Added product category property",
        "created_at": "2025-01-15T10:30:00Z",
        "snapshot_count": 1,
        "snapshots": [
          {
            "id": "snapshot-uuid-3",
            "name": "Latest Snapshot",
            "status": "ready",
            "created_at": "2025-01-15T11:00:00Z",
            "instance_count": 2,
            "instances": [
              {"id": "instance-uuid-1", "name": "Analysis 1", "status": "running"},
              {"id": "instance-uuid-2", "name": "Analysis 2", "status": "starting"}
            ]
          }
        ]
      },
      {
        "version": 2,
        "change_description": "Fixed customer SQL query",
        "created_at": "2025-01-12T14:00:00Z",
        "snapshot_count": 2,
        "snapshots": [
          {
            "id": "snapshot-uuid-2",
            "name": "January Snapshot",
            "status": "ready",
            "created_at": "2025-01-12T15:00:00Z",
            "instance_count": 0,
            "instances": []
          },
          {
            "id": "snapshot-uuid-1",
            "name": "Test Snapshot",
            "status": "failed",
            "created_at": "2025-01-12T14:30:00Z",
            "instance_count": 0,
            "instances": []
          }
        ]
      },
      {
        "version": 1,
        "change_description": null,
        "created_at": "2025-01-10T08:00:00Z",
        "snapshot_count": 0,
        "snapshots": []
      }
    ],
    "totals": {
      "version_count": 3,
      "snapshot_count": 3,
      "instance_count": 2
    }
  }
}
```

---

### List Snapshots for Mapping

```
GET /api/mappings/:id/snapshots
```

Returns all snapshots across all versions of this mapping.

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
      "id": "snapshot-uuid",
      "mapping_id": 42,
      "mapping_version": 3,
      "owner_username": "alice.smith",
      "name": "January 2025 Snapshot",
      "description": "Month-end snapshot",
      "gcs_path": "gs://graph-olap-snapshots/42/3/snapshot-uuid/",
      "status": "ready",
      "size_bytes": 1048576,
      "node_counts": {"Customer": 1000, "Product": 500},
      "edge_counts": {"PURCHASED": 5000},
      "progress": null,
      "error_message": null,
      "created_at": "2025-01-15T10:30:00Z",
      "updated_at": "2025-01-15T10:45:00Z",
      "ttl": null,
      "inactivity_timeout": "P30D",
      "last_used_at": "2025-01-16T09:00:00Z"
    }
  ],
  "meta": {"total": 5, "offset": 0, "limit": 50}
}
```

**Response: 404 Not Found**

```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "Mapping not found",
    "details": {"id": 42}
  }
}
```

**Notes:**

- Returns snapshots across all versions of the mapping
- Use this to find all snapshots associated with a mapping regardless of version

---

### List Instances for Mapping

```
GET /api/mappings/:id/instances
```

Returns all instances created from any snapshot of this mapping.

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
      "id": "instance-uuid",
      "snapshot_id": "snapshot-uuid",
      "snapshot_name": "January 2025 Snapshot",
      "owner_username": "alice.smith",
      "wrapper_type": "ryugraph",
      "name": "My Analysis Instance",
      "status": "running",
      "created_at": "2025-01-15T10:30:00Z"
    }
  ],
  "meta": {"total": 3, "offset": 0, "limit": 50}
}
```

**Notes:**

- Returns instances across all versions of the mapping (via snapshot relationships)
- Use this to find all active graph instances associated with a mapping

---

## Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| VALIDATION_FAILED | 400 | Request body validation failed |
| RESOURCE_NOT_FOUND | 404 | Mapping not found |
| MAPPING_VERSION_NOT_FOUND | 404 | Requested version does not exist |
| PERMISSION_DENIED | 403 | User not authorized (not owner, not admin) |
| RESOURCE_HAS_DEPENDENCIES | 409 | Cannot delete (snapshots exist) |
