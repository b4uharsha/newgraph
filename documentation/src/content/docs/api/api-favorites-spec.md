---
title: "API Specification: Favorites"
scope: hsbc
---

<!-- Verified against code on 2026-04-20 -->

# API Specification: Favorites

## Overview

REST API specification for user favorites (bookmarks) in the Graph OLAP Platform Control Plane.

## Prerequisites

- [api.common.spec.md](--/api.common.spec.md) - **Authentication, base URL, data formats, response patterns, error codes**
- [data.model.spec.md](--/data.model.spec.md) - Database schema for user_favorites

## Access

All authenticated users can manage their own favorites.

---

## Endpoints

### List Favorites

```
GET /api/favorites
```

Returns current user's favorites.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| resource_type | string | - | Filter: `mapping` or `instance` |

**Response: 200 OK**

```json
{
  "data": [
    {
      "resource_type": "mapping",
      "resource_id": 42,
      "resource_name": "Customer Transactions",
      "resource_owner": "alice.smith",
      "created_at": "2025-01-15T10:30:00Z",
      "resource_exists": true
    },
    {
      "resource_type": "instance",
      "resource_id": 17,
      "resource_name": "My Analysis",
      "resource_owner": "alice.smith",
      "created_at": "2025-01-14T09:00:00Z",
      "resource_exists": false
    }
  ]
}
```

**Response Fields:**
- `resource_exists`: Indicates if resource still exists (should always be `true` due to cascade delete)
- `resource_name`, `resource_owner`: Metadata enriched from resource tables (null if resource doesn't exist)

---

### Add Favorite

```
POST /api/favorites
```

**Request Body:**

```json
{
  "resource_type": "mapping",
  "resource_id": 42
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| resource_type | string | Yes | `mapping` or `instance` (no snapshot support) |
| resource_id | integer | Yes | Resource ID (positive integer) |

**Response: 201 Created**

```json
{
  "data": {
    "resource_type": "mapping",
    "resource_id": 42,
    "created_at": "2025-01-15T10:30:00Z"
  }
}
```

**Response: 409 Conflict** (already favorited)

```json
{
  "error": {
    "code": "ALREADY_EXISTS",
    "message": "Resource already in favorites"
  }
}
```

**Response: 404 Not Found** (resource doesn't exist)

```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "Resource not found"
  }
}
```

---

### Remove Favorite

```
DELETE /api/favorites/{resource_type}/{resource_id}
```

Idempotent operation - succeeds even if the favorite does not exist.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| resource_type | string | `mapping` or `instance` |
| resource_id | integer | Resource ID |

**Response: 200 OK**

```json
{
  "data": {"deleted": true}
}
```

**Response: 404 Not Found** (favorite doesn't exist)

```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "Favorite not found"
  }
}
```

---

## Cascade Delete Behavior

When a resource (mapping or instance) is deleted, **all favorites referencing that resource are automatically deleted**.

**Rationale**: Maintain referential integrity - favorites should not reference non-existent resources.

**Implementation**:
- Deletion happens in the same service transaction as resource deletion
- No error is raised if resource had zero favorites
- Logged at INFO level for observability:
  ```
  Cascade deleted favorites for deleted mapping
    mapping_id=42
    favorites_deleted=3
  ```

**Alternative Considered**: Keep favorites with `resource_exists=false` flag
- **Rejected**: Violates database integrity, clutters favorites list with deleted resources

**Service Layer**: See [control-plane.services.design.md](--/--/component-designs/control-plane.services.design.md) for implementation details.

---

## Notes

- Favorites are user-specific; users cannot see or modify other users' favorites
- Cannot favorite a resource that doesn't exist (validated on add)
- Deleting a resource automatically cascade-deletes all favorites (see Cascade Delete Behavior above)
