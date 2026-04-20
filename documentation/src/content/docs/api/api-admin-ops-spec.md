---
title: "API Specification: Admin and Ops Endpoints"
scope: hsbc
---

<!-- Verified against code on 2026-04-20 -->

# API Specification: Admin and Ops Endpoints

## Overview

REST API specification for administrative and operational endpoints in the Graph OLAP Platform Control Plane. Includes configuration management, cluster operations, and export queue management.

**Note:** Audit logging is handled by the external observability stack, not this API.

## Prerequisites

- [api.common.spec.md](--/api.common.spec.md) - **Authentication, base URL, data formats, response patterns, error codes**
- [requirements.md](--/--/foundation/requirements.md) - User roles (Admin, Ops)
- [data.model.spec.md](--/data.model.spec.md) - Database schema for global_config, user_favorites

## Role Requirements

| Endpoint Category | Required Role |
|-------------------|---------------|
| Config (`/api/config/*`) | Ops |
| Cluster (`/api/cluster/*`) | Ops |
| Background Jobs (`/api/ops/jobs/*`) | Ops |
| System State (`/api/ops/state`, `/api/ops/export-jobs`) | Ops |
| Schema Metadata (`/api/schema/*`) | Any authenticated user |
| Schema Admin (`/api/schema/admin/*`, `/api/schema/stats`) | Admin |
| Bulk Operations (`/api/admin/resources/*`) | Admin or Ops |
| Export Jobs (scoped) (`/api/export-jobs`) | All authenticated (scoped) |
| E2E Cleanup (`/api/admin/e2e-cleanup`) | Admin or Ops |

Note: For Export Jobs (scoped), Analyst sees own jobs only; Admin/Ops see all jobs.

Note: Favorites moved to [api.favorites.spec.md](-/api.favorites.spec.md) (all authenticated users).

> See [`../authorization.spec.md`](--/authorization.spec.md) for the complete RBAC matrix.

---

## Configuration Endpoints (Ops Only)

### Get Lifecycle Configuration

```
GET /api/config/lifecycle
```

**Response: 200 OK**

```json
{
  "data": {
    "mapping": {
      "default_ttl": null,
      "default_inactivity": "P30D",
      "max_ttl": "P365D"
    },
    "snapshot": {
      "default_ttl": "P7D",
      "default_inactivity": "P3D",
      "max_ttl": "P30D"
    },
    "instance": {
      "default_ttl": "PT24H",
      "default_inactivity": "PT4H",
      "max_ttl": "P7D"
    }
  }
}
```

---

### Update Lifecycle Configuration

```
PUT /api/config/lifecycle
```

**Request Body:**

```json
{
  "mapping": {
    "default_ttl": null,
    "default_inactivity": "P30D",
    "max_ttl": "P365D"
  },
  "snapshot": {
    "default_ttl": "P7D",
    "default_inactivity": "P3D",
    "max_ttl": "P30D"
  },
  "instance": {
    "default_ttl": "PT24H",
    "default_inactivity": "PT4H",
    "max_ttl": "P7D"
  }
}
```

**Response: 200 OK**

```json
{
  "data": {
    "updated": true,
    "updated_at": "2025-01-15T10:30:00Z"
  }
}
```

---

### Get Concurrency Configuration

```
GET /api/config/concurrency
```

**Response: 200 OK**

```json
{
  "data": {
    "per_analyst": 5,
    "cluster_total": 50
  }
}
```

---

### Update Concurrency Configuration

```
PUT /api/config/concurrency
```

**Request Body:**

```json
{
  "per_analyst": 10,
  "cluster_total": 100
}
```

**Response: 200 OK**

```json
{
  "data": {
    "per_analyst": 10,
    "cluster_total": 100,
    "updated_at": "2025-01-15T10:30:00Z"
  }
}
```

---

### Get Maintenance Mode

```
GET /api/config/maintenance
```

**Response: 200 OK**

```json
{
  "data": {
    "enabled": false,
    "message": "",
    "updated_at": "2025-01-15T10:30:00Z",
    "updated_by": "ops_user"
  }
}
```

---

### Set Maintenance Mode

```
PUT /api/config/maintenance
```

**Request:**

```json
{
  "enabled": true,
  "message": "Scheduled maintenance until 14:00 UTC"
}
```

**Response: 200 OK** - Returns updated status.

---

### Get Export Configuration

```
GET /api/config/export
```

**Response: 200 OK**

```json
{
  "data": {
    "max_duration_seconds": 3600,
    "updated_at": "2025-01-15T10:30:00Z",
    "updated_by": "ops_user"
  }
}
```

---

### Update Export Configuration

```
PUT /api/config/export
```

**Request:**

```json
{
  "max_duration_seconds": 7200
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| max_duration_seconds | integer | No | Maximum time for a single export job before timeout (default: 3600). Jobs exceeding this are marked failed by reconciliation. |

**Response: 200 OK**

```json
{
  "data": {
    "max_duration_seconds": 7200,
    "updated_at": "2025-01-15T10:35:00Z",
    "updated_by": "ops_user"
  }
}
```

---

## Cluster Endpoints (Ops Only)

### Get Cluster Health

```
GET /api/cluster/health
```

**Response: 200 OK**

```json
{
  "data": {
    "status": "healthy",
    "components": {
      "database": {"status": "connected", "latency_ms": 5},
      "kubernetes": {"status": "connected"},
      "starburst": {"status": "connected", "latency_ms": 120}
    },
    "checked_at": "2025-01-15T10:30:00Z"
  }
}
```

**Response: 503 Service Unavailable**

```json
{
  "data": {
    "status": "degraded",
    "components": {
      "database": {"status": "connected", "latency_ms": 5},
      "kubernetes": {"status": "connected"},
      "starburst": {"status": "unreachable", "error": "connection timeout"}
    },
    "checked_at": "2025-01-15T10:30:00Z"
  }
}
```

---

### Get Cluster Instances Summary

```
GET /api/cluster/instances
```

**Response: 200 OK**

```json
{
  "data": {
    "total": 25,
    "by_status": {
      "starting": 2,
      "running": 20,
      "stopping": 1,
      "failed": 2
    },
    "by_owner": [
      {"owner_username": "alice", "count": 5},
      {"owner_username": "bob", "count": 3}
    ],
    "limits": {
      "per_analyst": 5,
      "cluster_total": 50,
      "cluster_used": 25,
      "cluster_available": 25
    }
  }
}
```

---

## Background Jobs Endpoints (Ops Only)

### Trigger Background Job

```
POST /api/ops/jobs/trigger
```

Manually triggers a background job for immediate execution. Useful for debugging, smoke tests after deployment, and incident response.

**Rate Limiting:** 1 request per minute per job (prevents accidental job spam).

**Request Body:**

```json
{
  "job_name": "reconciliation",
  "reason": "post-deployment smoke test"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| job_name | string | Yes | Job to trigger: `reconciliation`, `lifecycle`, `export_reconciliation`, `schema_cache`, `resource_monitor` |
| reason | string | Yes | Reason for manual trigger (audit log, 1-500 chars) |

**Response: 200 OK**

```json
{
  "data": {
    "job_name": "reconciliation",
    "status": "queued",
    "triggered_at": "2025-01-15T10:30:00Z",
    "triggered_by": "ops.user",
    "reason": "post-deployment smoke test"
  }
}
```

**Error: 400 Bad Request** - Invalid job name or missing reason

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid job_name. Must be one of: reconciliation, lifecycle, export_reconciliation, schema_cache, resource_monitor"
  }
}
```

**Error: 429 Too Many Requests** - Rate limit exceeded (1 per minute per job)

```json
{
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Job 'reconciliation' was triggered 30 seconds ago. Please wait 30 seconds before triggering again.",
    "details": {
      "retry_after_seconds": 30
    }
  }
}
```

**Error: 403 Forbidden** - Requires ops role

---

### Get Background Job Status

```
GET /api/ops/jobs/status
```

Returns the list of registered background jobs and their next scheduled run time.

**Response: 200 OK**

```json
{
  "data": {
    "jobs": [
      {
        "name": "reconciliation",
        "next_run": "2026-04-20T10:35:00Z"
      },
      {
        "name": "lifecycle",
        "next_run": "2026-04-20T10:35:00Z"
      },
      {
        "name": "export_reconciliation",
        "next_run": "2026-04-20T10:30:05Z"
      },
      {
        "name": "schema_cache",
        "next_run": "2026-04-21T02:00:00Z"
      },
      {
        "name": "resource_monitor",
        "next_run": "2026-04-20T10:31:00Z"
      }
    ]
  }
}
```

**Response Fields (per job):**
- `name` - Job identifier
- `next_run` - ISO 8601 timestamp of next scheduled execution (null if not scheduled)

**Error: 403 Forbidden** - Requires ops role

---

### Get System State

```
GET /api/ops/state
```

Returns current system state snapshot including resource counts by status. Useful for operational dashboards and debugging.

**Response: 200 OK**

```json
{
  "data": {
    "instances": {
      "total": 25,
      "by_status": {
        "starting": 2,
        "running": 20,
        "stopping": 1,
        "stopped": 0,
        "failed": 2,
        "terminated": 0
      },
      "without_pod_name": 0
    },
    "snapshots": {
      "total": 150,
      "by_status": {
        "pending": 2,
        "creating": 1,
        "ready": 140,
        "failed": 7
      }
    },
    "export_jobs": {
      "by_status": {
        "pending": 5,
        "claimed": 2,
        "completed": 140,
        "failed": 3
      }
    },
    "retrieved_at": "2025-01-15T10:30:00Z"
  }
}
```

**Use Cases:**
- Verify lifecycle job enforcement (instances should transition to terminated)
- Verify reconciliation job cleanup (instances_without_pod_name should be 0)
- Monitor export job queue depth
- E2E test assertions

**Error: 403 Forbidden** - Requires ops role

---

### Get Export Jobs for Debugging

```
GET /api/ops/export-jobs
```

Returns export jobs for debugging export worker issues. Similar to `/exports` but optimized for ops troubleshooting.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| status | string | - | Filter: pending, claimed, completed, failed |
| limit | integer | 100 | Max records (max: 100) |

**Response: 200 OK**

```json
{
  "data": {
    "jobs": [
      {
        "id": 123,
        "snapshot_id": 456,
        "entity_type": "node",
        "entity_name": "Customer",
        "status": "pending",
        "claimed_at": null,
        "claimed_by": null,
        "attempts": 0,
        "error_message": null
      },
      {
        "id": 122,
        "snapshot_id": 456,
        "entity_type": "edge",
        "entity_name": "PURCHASED",
        "status": "failed",
        "claimed_at": "2025-01-15T10:25:10Z",
        "claimed_by": "export-worker-1",
        "attempts": 3,
        "error_message": "Table not found: analytics.purchases"
      }
    ]
  }
}
```

**Error: 403 Forbidden** - Requires ops role

---

## Favorites

See [api.favorites.spec.md](-/api.favorites.spec.md) for favorites endpoints (available to all authenticated users).

---

## Admin Bulk Operations (Admin Only)

### Bulk Delete Resources

```
DELETE /api/admin/resources/bulk
```

Safely deletes multiple resources matching filters. Designed for test cleanup and operational maintenance with comprehensive safety mechanisms.

**Safety Features:**
1. Admin role required
2. At least one filter required (prevents accidental "delete all")
3. Max 100 deletions per request
4. Expected count validation (confirm you know what you're deleting)
5. Dry run mode (preview before deleting)
6. Full audit logging (who, what, when, why)
7. Per-resource error tracking (partial failures don't block others)
8. Filter validation (prevent overly broad matches)
9. Authorization checks (admin can delete any, owner-only for non-admins)

**Implementation Behavior (ADR-043):**

For **instances**, bulk delete performs complete, synchronous resource cleanup:
- Deletes Kubernetes resources (pod, service, ingress) FIRST
- Deletes database record LAST
- Returns 200 OK when resources are **GONE**, not "eventually gone"
- Parallel execution (10 concurrent deletions) for performance (~3 seconds for 10 instances)
- No orphaned K8s resources left behind (unlike previous lazy cleanup pattern)

For **snapshots** and **mappings**, bulk delete performs simple database deletion (no Kubernetes resources to clean up).

**See Also:**
- [InstanceService.delete()](--/--/component-designs/control-plane.services.design.md#instance-service-with-kubernetes-integration) - Deletion implementation
- ADR-043 - Architecture decision
- [Background Jobs](--/--/component-designs/control-plane.background-jobs.design.md#1-reconciliation-job) - Reconciliation job role change

**Request Body:**

```json
{
  "resource_type": "instance",
  "filters": {
    "name_prefix": "E2ETest-",
    "older_than_hours": 24,
    "status": "terminated",
    "created_by": "e2e-test-user"
  },
  "reason": "cleanup old e2e test instances",
  "expected_count": 15,
  "dry_run": false
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| resource_type | string | Yes | Resource type: `instance`, `snapshot`, `mapping` |
| filters | object | Yes | Filters (at least one required) |
| filters.name_prefix | string | No | Match resources starting with prefix |
| filters.created_by | string | No | Match resources created by username |
| filters.older_than_hours | integer | No | Match resources older than N hours |
| filters.status | string | No | Match resources with specific status |
| reason | string | Yes | Reason for deletion (audit log, 1-500 chars) |
| expected_count | integer | No | Expected number of matches (safety check) |
| dry_run | boolean | No | If true, return matches without deleting (default: false) |

**Recommended Workflow:**

1. **Step 1: Dry run** - Preview what would be deleted
2. **Step 2: Verify** - Check matched_ids and matched_count
3. **Step 3: Delete** - Use expected_count from dry run for safety

**Response: 200 OK (Dry Run)**

```json
{
  "data": {
    "dry_run": true,
    "matched_count": 15,
    "matched_ids": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
    "deleted_count": 0,
    "deleted_ids": [],
    "failed_ids": [],
    "errors": []
  }
}
```

**Response: 200 OK (Actual Delete)**

```json
{
  "data": {
    "dry_run": false,
    "matched_count": 15,
    "matched_ids": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
    "deleted_count": 14,
    "deleted_ids": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14],
    "failed_ids": [15],
    "errors": [
      {
        "resource_id": 15,
        "error": "Cannot delete instance with active pod"
      }
    ]
  }
}
```

**Error: 400 Bad Request** - No filters provided

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "At least one filter is required to prevent accidental bulk deletion",
    "details": {
      "available_filters": ["name_prefix", "created_by", "older_than_hours", "status"]
    }
  }
}
```

**Error: 400 Bad Request** - Too many matches (> 100)

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Matched 250 resources. Bulk delete is limited to 100 resources per request. Use more specific filters.",
    "details": {
      "matched_count": 250,
      "max_allowed": 100
    }
  }
}
```

**Error: 400 Bad Request** - Expected count mismatch

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Expected count mismatch. Found 15 resources, but expected 10. Data may have changed since dry run.",
    "details": {
      "expected_count": 10,
      "actual_count": 15
    }
  }
}
```

**Error: 403 Forbidden** - Requires admin role

```json
{
  "error": {
    "code": "FORBIDDEN",
    "message": "Bulk delete requires admin role"
  }
}
```

**Error: 422 Unprocessable Entity** - Invalid resource type

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid resource_type. Must be one of: instance, snapshot, mapping"
  }
}
```

---

### E2E Test Cleanup

```
DELETE /api/admin/e2e-cleanup
```

Deletes ALL resources owned by E2E test users. Called before and after E2E test runs to ensure clean state.

**Requires:** Admin or Ops role

**Cleanup Order:**

1. Instances (including K8s wrapper pods)
2. Snapshots (including GCS files)
3. Mappings
4. Force-terminate any orphaned K8s pods by owner-email label

**Response: 200 OK**

```json
{
  "data": {
    "users_processed": ["e2e-test-user@example.com"],
    "instances_deleted": 5,
    "snapshots_deleted": 3,
    "mappings_deleted": 2,
    "pods_terminated": 1,
    "gcs_files_deleted": 15,
    "gcs_bytes_deleted": 1073741824,
    "errors": [],
    "success": true
  }
}
```

**Response: 200 OK** (with partial failures)

```json
{
  "data": {
    "users_processed": ["e2e-test-user@example.com"],
    "instances_deleted": 4,
    "snapshots_deleted": 3,
    "mappings_deleted": 2,
    "pods_terminated": 0,
    "gcs_files_deleted": 10,
    "gcs_bytes_deleted": 536870912,
    "errors": [
      "Failed to delete instance 123: timeout waiting for pod termination"
    ],
    "success": false
  }
}
```

**Error: 403 Forbidden** - Requires admin or ops role

```json
{
  "error": {
    "code": "FORBIDDEN",
    "message": "E2E cleanup requires admin or ops role"
  }
}
```

**Notes:**

- E2E test users are configured via `E2E_TEST_USER_EMAILS` environment variable
- This endpoint is idempotent - safe to call multiple times
- Errors are collected but don't stop the cleanup process
- GCS cleanup requires configured `GCS_BUCKET` and `GCP_PROJECT`

---

## Schema Metadata API

The Schema Metadata API provides read-only access to cached Starburst schema metadata for the mapping builder UI. All data is served from an in-memory cache refreshed every 24 hours.

**Performance:** ~1μs for lookups, ~100μs for searches (in-memory)

### List Catalogs

```
GET /api/schema/catalogs
```

Returns all cached Starburst catalogs.

**Response: 200 OK**

```json
{
  "data": [
    {
      "catalog_name": "hive",
      "schema_count": 15,
      "cached_at": "2025-01-15T02:00:00Z"
    },
    {
      "catalog_name": "iceberg",
      "schema_count": 8,
      "cached_at": "2025-01-15T02:00:00Z"
    }
  ]
}
```

---

### List Schemas

```
GET /api/schema/catalogs/:catalog/schemas
```

Returns all schemas in a catalog.

**Response: 200 OK**

```json
{
  "data": [
    {
      "catalog_name": "hive",
      "schema_name": "analytics",
      "table_count": 45,
      "cached_at": "2025-01-15T02:00:00Z"
    },
    {
      "catalog_name": "hive",
      "schema_name": "raw_data",
      "table_count": 120,
      "cached_at": "2025-01-15T02:00:00Z"
    }
  ]
}
```

**Error: 404 Not Found** - Catalog not found in cache

---

### List Tables

```
GET /api/schema/catalogs/:catalog/schemas/:schema/tables
```

Returns all tables in a schema.

**Response: 200 OK**

```json
{
  "data": [
    {
      "catalog_name": "hive",
      "schema_name": "analytics",
      "table_name": "customers",
      "table_type": "TABLE",
      "column_count": 12,
      "cached_at": "2025-01-15T02:00:00Z"
    },
    {
      "catalog_name": "hive",
      "schema_name": "analytics",
      "table_name": "orders",
      "table_type": "TABLE",
      "column_count": 8,
      "cached_at": "2025-01-15T02:00:00Z"
    }
  ]
}
```

**Error: 404 Not Found** - Schema not found in cache

---

### List Columns

```
GET /api/schema/catalogs/:catalog/schemas/:schema/tables/:table/columns
```

Returns all columns for a table.

**Response: 200 OK**

```json
{
  "data": [
    {
      "catalog_name": "hive",
      "schema_name": "analytics",
      "table_name": "customers",
      "column_name": "customer_id",
      "data_type": "varchar",
      "is_nullable": false,
      "ordinal_position": 1,
      "column_default": null,
      "cached_at": "2025-01-15T02:00:00Z"
    },
    {
      "catalog_name": "hive",
      "schema_name": "analytics",
      "table_name": "customers",
      "column_name": "name",
      "data_type": "varchar",
      "is_nullable": true,
      "ordinal_position": 2,
      "column_default": null,
      "cached_at": "2025-01-15T02:00:00Z"
    }
  ]
}
```

**Error: 404 Not Found** - Table not found in cache

---

### Search Tables

```
GET /api/schema/search/tables
```

Search tables by name pattern (prefix match, case-insensitive).

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| q | string | - | **Required.** Search pattern (prefix match) |
| limit | integer | 100 | Max results (max: 1000) |

**Response: 200 OK**

```json
{
  "data": [
    {
      "catalog_name": "hive",
      "schema_name": "analytics",
      "table_name": "customers",
      "table_type": "TABLE",
      "column_count": 12,
      "cached_at": "2025-01-15T02:00:00Z"
    },
    {
      "catalog_name": "hive",
      "schema_name": "analytics",
      "table_name": "customer_orders",
      "table_type": "TABLE",
      "column_count": 8,
      "cached_at": "2025-01-15T02:00:00Z"
    }
  ]
}
```

---

### Search Columns

```
GET /api/schema/search/columns
```

Search columns by name pattern (prefix match, case-insensitive).

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| q | string | - | **Required.** Search pattern (prefix match) |
| limit | integer | 100 | Max results (max: 1000) |

**Response: 200 OK**

```json
{
  "data": [
    {
      "catalog_name": "hive",
      "schema_name": "analytics",
      "table_name": "customers",
      "column_name": "email",
      "data_type": "varchar",
      "is_nullable": true,
      "ordinal_position": 3,
      "column_default": null,
      "cached_at": "2025-01-15T02:00:00Z"
    },
    {
      "catalog_name": "hive",
      "schema_name": "analytics",
      "table_name": "users",
      "column_name": "email_address",
      "data_type": "varchar",
      "is_nullable": false,
      "ordinal_position": 2,
      "column_default": null,
      "cached_at": "2025-01-15T02:00:00Z"
    }
  ]
}
```

---

### Trigger Cache Refresh (Admin Only)

```
POST /api/schema/admin/refresh
```

Manually triggers schema cache refresh. Starts background task and returns immediately.

**Requires:** Admin role

**Response: 200 OK**

```json
{
  "data": {
    "status": "refresh triggered"
  }
}
```

**Error: 403 Forbidden** - Requires admin role

---

### Get Cache Statistics (Admin Only)

```
GET /api/schema/stats
```

Returns schema cache statistics.

**Requires:** Admin role

**Response: 200 OK**

```json
{
  "data": {
    "total_catalogs": 3,
    "total_schemas": 25,
    "total_tables": 450,
    "total_columns": 3200,
    "last_refresh": "2025-01-15T02:00:00Z",
    "index_size_bytes": 1048576
  }
}
```

**Error: 403 Forbidden** - Requires admin role

---

## Error Codes

See [api.common.spec.md](--/api.common.spec.md#error-codes-reference) for the complete error codes reference.
