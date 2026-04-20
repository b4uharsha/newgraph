---
title: "API Specification: Starburst Schema Browser"
scope: hsbc
---

<!-- Rewritten against actual /api/schema/* routes on 2026-04-20 (earlier
     version documented a /api/starburst/* namespace that does not exist). -->

# API Specification: Starburst Schema Browser

## Overview

Endpoints for browsing Starburst schema metadata (catalogs, schemas, tables,
columns). The Control Plane maintains an in-memory schema cache that is
refreshed from Starburst every 24 hours (and on demand by an Admin user).
SDK and UI clients read the cache; they never hit Starburst directly.

> **Source of truth:** `packages/control-plane/src/control_plane/routers/api/schema.py`
> (router prefix `/api/schema`). The cache implementation lives in
> `packages/control-plane/src/control_plane/cache/schema_cache.py` and the
> refresh job in `packages/control-plane/src/control_plane/jobs/schema_cache.py`.

There is no `/api/starburst/*` route namespace on the Control Plane. SQL
validation, SQL→mapping inference, and "real-time Starburst" endpoints are
**not implemented** — earlier drafts of this document described a design that
did not ship.

## Prerequisites

- [api.common.spec.md](--/api.common.spec.md) - API conventions, authentication (`X-Username`), error format
- [architectural.guardrails.md](--/--/foundation/architectural.guardrails.md) - Constraints

## Base URL

All endpoints are served by the Control Plane. At HSBC the ingress host is:

```
https://control-plane-graph-olap-platform.hsbc-12636856-udlhk-dev.dev.gcp.cloud.hk.hsbc/api/schema
```

In-cluster callers should use the ClusterIP service (see
[api.common.spec.md](--/api.common.spec.md)).

## Authentication

`X-Username` header (ADR-104 / ADR-105). The browser endpoints require any
authenticated user; the admin endpoints additionally require the **Admin**
role (enforced via `RequireAdmin` dependency in `schema.py`).

---

## Endpoint Inventory

| Method | Path | Role | Purpose |
|--------|------|------|---------|
| GET | `/api/schema/catalogs` | Any | List all cached Starburst catalogs |
| GET | `/api/schema/catalogs/{catalog_name}/schemas` | Any | List schemas in a catalog |
| GET | `/api/schema/catalogs/{catalog_name}/schemas/{schema_name}/tables` | Any | List tables in a schema |
| GET | `/api/schema/catalogs/{catalog_name}/schemas/{schema_name}/tables/{table_name}/columns` | Any | List columns on a table |
| GET | `/api/schema/search/tables?q={pattern}&limit={N}` | Any | Prefix search for tables |
| GET | `/api/schema/search/columns?q={pattern}&limit={N}` | Any | Prefix search for columns |
| POST | `/api/schema/admin/refresh` | Admin | Trigger a cache refresh (background task) |
| GET | `/api/schema/stats` | Admin | Get cache statistics |

All cached lookups return in ~1μs (in-memory); the two search endpoints run
in ~100μs. The cache itself is refreshed on startup and every 24 hours by
the `schema_cache` background job.

---

## List Catalogs

```
GET /api/schema/catalogs
```

Returns all cached catalogs visible to the control plane's Starburst service
account.

**Response: 200 OK**

```json
{
  "data": [
    {"catalog_name": "analytics", "schema_count": 12, "cached_at": "2026-04-20T06:00:00Z"},
    {"catalog_name": "raw_data",  "schema_count": 5,  "cached_at": "2026-04-20T06:00:00Z"}
  ]
}
```

---

## List Schemas in a Catalog

```
GET /api/schema/catalogs/{catalog_name}/schemas
```

**Response: 200 OK**

```json
{
  "data": [
    {"schema_name": "customer",     "table_count": 8},
    {"schema_name": "product",      "table_count": 3},
    {"schema_name": "transactions", "table_count": 2}
  ]
}
```

---

## List Tables in a Schema

```
GET /api/schema/catalogs/{catalog_name}/schemas/{schema_name}/tables
```

**Response: 200 OK**

```json
{
  "data": [
    {"table_name": "customers",    "column_count": 12},
    {"table_name": "addresses",    "column_count": 7}
  ]
}
```

---

## List Columns on a Table

```
GET /api/schema/catalogs/{catalog_name}/schemas/{schema_name}/tables/{table_name}/columns
```

**Response: 200 OK**

```json
{
  "data": [
    {"column_name": "customer_id", "column_type": "VARCHAR", "nullable": false},
    {"column_name": "name",        "column_type": "VARCHAR", "nullable": true},
    {"column_name": "created_at",  "column_type": "TIMESTAMP", "nullable": false}
  ]
}
```

---

## Search Tables

```
GET /api/schema/search/tables?q={pattern}&limit={N}
```

Case-insensitive prefix match against cached table names.

**Query parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| q | string | Yes | Search pattern (minimum length 1) |
| limit | integer | No | Max results (1-1000, default 100) |

**Response: 200 OK** — same shape as the per-schema list, but each row also
includes `catalog_name` and `schema_name` because search crosses schemas.

---

## Search Columns

```
GET /api/schema/search/columns?q={pattern}&limit={N}
```

Same semantics as `/search/tables` but for column names.

---

## Admin: Trigger Cache Refresh

```
POST /api/schema/admin/refresh
```

**Role required:** Admin

Starts an asynchronous refresh (background task) against Starburst. Returns
immediately — poll `GET /api/schema/stats` or the background-jobs admin
endpoints in [api.admin-ops.spec.md](-/api.admin-ops.spec.md) to observe
progress.

**Response: 200 OK**

```json
{"data": {"triggered": true, "started_at": "2026-04-20T10:30:00Z"}}
```

---

## Admin: Cache Stats

```
GET /api/schema/stats
```

**Role required:** Admin

**Response: 200 OK**

```json
{
  "data": {
    "total_catalogs": 3,
    "total_schemas": 42,
    "total_tables": 317,
    "total_columns": 2890,
    "last_refresh": "2026-04-20T06:00:00Z",
    "refresh_running": false
  }
}
```

`last_refresh: null` means the background refresh job has never completed
successfully since the pod last started (common symptom: `GRAPH_OLAP_STARBURST_URL`
empty in the control-plane ConfigMap — see the operations handover Q&A).

---

## Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| RESOURCE_NOT_FOUND | 404 | Catalog, schema, or table not present in cache |
| PERMISSION_DENIED | 403 | Non-Admin user called an `admin/*` route |
| STARBURST_ERROR | 500 | Cache refresh failed against Starburst (visible only during manual refresh) |
| SERVICE_UNAVAILABLE | 503 | Cache not yet populated (startup race; refresh job has not completed) |

---

## Not Implemented

The following endpoints appeared in earlier drafts of this spec but are NOT
implemented and will return 404:

- `POST /api/starburst/parse-sql` — SQL→mapping inference
- `POST /api/starburst/validate` — real-time SQL validation
- `GET /api/starburst/*` — entire `/api/starburst/` namespace

Mapping SQL is validated implicitly when a mapping is saved (the
control-plane runs the node/edge queries as part of the Export Worker's
UNLOAD submission). There is no separate real-time validation endpoint.

---

## References

- Router: `packages/control-plane/src/control_plane/routers/api/schema.py`
- Cache implementation: `packages/control-plane/src/control_plane/cache/schema_cache.py`
- Refresh job: `packages/control-plane/src/control_plane/jobs/schema_cache.py`
- Configuration: `GRAPH_OLAP_STARBURST_URL`, `GRAPH_OLAP_STARBURST_USER`, `GRAPH_OLAP_STARBURST_PASSWORD` (see [configuration-reference.md](--/--/operations/configuration-reference.md))
