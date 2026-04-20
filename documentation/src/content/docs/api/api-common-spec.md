---
title: "API Specification: Common Patterns"
scope: hsbc
---

<!-- Verified against code on 2026-04-20 -->

# API Specification: Common Patterns

## Overview

Shared conventions, response formats, and error handling for all Graph OLAP Platform APIs.

## Prerequisites

- [architectural.guardrails.md](--/foundation/architectural.guardrails.md) - Error codes and HTTP status conventions

---

## Related API Documents

| Document | Content |
|----------|---------|
| [api.mappings.spec.md](-/api/api.mappings.spec.md) | Mapping CRUD, versions, lifecycle |
| [api.snapshots.spec.md](-/api/api.snapshots.spec.md) | Snapshot read-only APIs (CRUD disabled), progress, retry |
| [api.instances.spec.md](-/api/api.instances.spec.md) | Instance CRUD, lock status |
| [api.admin-ops.spec.md](-/api/api.admin-ops.spec.md) | Config, cluster, audit, favorites |
| [api.starburst.spec.md](-/api/api.starburst.spec.md) | Starburst schema browser, SQL validation |
| [api.wrapper.spec.md](-/api/api.wrapper.spec.md) | Graph queries, algorithms |
| [api.internal.spec.md](-/api/api.internal.spec.md) | Internal component communication |

---

## API Classification

The Control Plane exposes two categories of APIs based on consumer type and authentication model:

### API (`/api/*`)

The product API for user-initiated operations. Used by external SDK clients.

| Aspect | Description |
|--------|-------------|
| **Authentication** | `X-Username` identity header set upstream of the control plane; role is resolved from PostgreSQL |
| **Authorization** | Role-based (analyst, admin, ops) + ownership checks |
| **Network Access** | Ingress (SDK) |
| **Consumers** | Python SDK |
| **Audit Logging** | Request logs include the resolved username |

**Endpoints:** Mappings, Snapshots, Instances, Favorites, Admin/Ops, Starburst introspection

### Internal API (`/api/internal/*`)

Component-to-component communication. Not for external consumption.

| Aspect | Description |
|--------|-------------|
| **Authentication** | ClusterIP reachability + Kubernetes NetworkPolicy (no application-level token) |
| **Authorization** | Network-level: only `wrapper` / `worker` pod selectors can reach these routes |
| **Network Access** | ClusterIP only (cluster-internal) |
| **Consumers** | Ryugraph Wrapper, FalkorDB Wrapper, Export Worker |
| **Audit Logging** | System-level logging only |

**Endpoints:** Status updates, metrics reporting, mapping retrieval, activity recording, Starburst introspection

### Why This Distinction Matters

1. **Consumer Type**: API is for user-facing clients; Internal API is for platform components
2. **Auth Model**: API uses user credentials; Internal API uses service accounts
3. **Contract Stability**: API requires backward compatibility; Internal API can evolve freely
4. **Trust Model**: API validates user permissions; Internal API trusts component identity

### Network Access Patterns

```
┌─────────────────────────────────────────────────────────────┐
│  External                                                   │
│                                                             │
│  Python SDK ───► Ingress ───► Control Plane (/api/*)       │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  Cluster-Internal                                           │
│                                                             │
│  Wrapper ───► ClusterIP ───► Control Plane (/api/internal/*) │
│  Worker  ───► ClusterIP ───► Control Plane (/api/internal/*) │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Network Enforcement

```yaml
# NetworkPolicy ensures internal APIs are cluster-only
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: control-plane-internal
spec:
  podSelector:
    matchLabels:
      app: control-plane
  ingress:
    # Internal APIs from platform components
    - from:
        - podSelector:
            matchLabels:
              component: wrapper
        - podSelector:
            matchLabels:
              component: worker
      ports:
        - port: 8000
          # Path: /api/internal/* (enforced at application level)
```

---

## API Consumption Matrix

This matrix shows which platform components consume each API endpoint group.

### Consumer Legend

| Consumer | Authentication | Access Pattern |
|----------|----------------|----------------|
| **WebApp** | `X-Username` header (forwarded) | All user-facing + Ops endpoints |
| **SDK** | `X-Username` header | User-facing endpoints only |
| **Wrapper** | K8s Service Account | Internal status reporting |
| **Exporter** | K8s Service Account | Internal job management |

### User-Facing APIs (`/api/*`)

| Endpoint Group | Endpoints | WebApp | SDK | Wrapper | Exporter |
|----------------|-----------|:------:|:---:|:-------:|:--------:|
| Mappings | 12 | ✅ | ✅ | - | - |
| Snapshots | 8 | (disabled) | (disabled) | - | - |
| Instances | 11 | ✅ | ✅ | - | - |
| Favorites | 3 | ✅ | ✅ | - | - |
| Starburst Schema | 6 | ✅ | ✅ | - | - |
| Admin/Ops Config | 10 | ✅ | - | - | - |
| Cluster Ops | 3 | ✅ | - | - | - |
| Export Queue | 4 | ✅ | - | - | - |
| **Subtotal** | **57** | **49** | **32** | **0** | **0** |

> **Note:** Public snapshot CRUD endpoints are disabled. Instances are created directly from
> mappings via `POST /instances/from-mapping`. The snapshot layer operates internally.

### Internal APIs (`/api/internal/*`)

| Endpoint Group | Endpoints | WebApp | SDK | Wrapper | Exporter |
|----------------|-----------|:------:|:---:|:-------:|:--------:|
| Snapshot Status | 4 | - | - | - | ✅ |
| Instance Status | 4 | - | - | ✅ | - |
| Instance Config | 2 | - | - | ✅ | - |
| **Subtotal** | **10** | **0** | **0** | **6** | **4** |

### Wrapper Pod APIs (per instance)

| Endpoint Group | Endpoints | WebApp | SDK | Internal |
|----------------|-----------|:------:|:---:|:--------:|
| Health/Status | 3 | ✅ | ✅ | ✅ |
| Graph Operations | 3 | - | ✅ | - |
| Lock Status | 1 | ✅ | ✅ | - |
| Algorithms | 5 | - | ✅ | - |
| **Subtotal** | **12** | **2** | **12** | **3** |

### Summary

| Category | Total | WebApp | SDK | Wrapper | Exporter |
|----------|-------|--------|-----|---------|----------|
| User-Facing | 49 | 49 | 32 | 0 | 0 |
| Internal | 10 | 0 | 0 | 6 | 4 |
| Wrapper Pod | 12 | 2 | 12 | 0 | 0 |
| **Total** | **71** | **51** | **44** | **6** | **4** |

> **Note:** User-facing count excludes 8 disabled snapshot endpoints.

### Communication Flow

```
┌─────────────────────────────────────────────────────────────────┐
│  External                                                       │
│                                                                 │
│  SDK ──────► Ingress ──────► Control Plane (/api/*)            │
│    │                                                            │
│    └──────► Ingress ──────► Wrapper Pods (queries, algorithms) │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  Cluster-Internal                                               │
│                                                                 │
│  WebApp ───► ClusterIP ───► Control Plane (/api/*)             │
│  Wrapper ──► ClusterIP ───► Control Plane (/api/internal/*)    │
│  Exporter ─► ClusterIP ───► Control Plane (/api/internal/*)    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Request Conventions

### Content Type

All requests and responses use JSON:

```
Content-Type: application/json
Accept: application/json
```

### Authentication

**Current:** `X-Username` header (ADR-104/105). **Proposed (ADR-137):** oauth2-proxy fronted by HSBC Azure AD (Entra ID) — will verify identity upstream and pass `X-Username` through to the control plane unchanged.

**References:**
- ADR-104: Database-Backed User Role Management
- ADR-105: `X-Username` Header Identity with Static Default
- ADR-112: IP Whitelisting at Ingress (current interim network control)
- ADR-137: Azure AD Authentication Proxy Migration (Proposed)

#### Identity Headers

The Control Plane trusts one identity header populated upstream of the application:

```
X-Username: {username}            # e.g. 'alice.smith'
```

The Control Plane reads `X-Username`, looks the user up in PostgreSQL, and resolves the role server-side (ADR-104). Handlers trust the header value and the DB-backed role; they do not validate tokens themselves.

Under the current model (ADR-105), the SDK sets `X-Username` directly and network access is gated at the nginx ingress by IP whitelisting (ADR-112). Once ADR-137 ships, oauth2-proxy will authenticate the user against Azure AD and overwrite `X-Username` with the verified Entra ID principal — application code does not change. Service-to-service calls inside the cluster use ClusterIP and bypass the auth proxy.

Roles are hierarchical: `Analyst < Admin < Ops`. Each higher role inherits all permissions of lower roles. See [`authorization.spec.md`](-/authorization.spec.md) for the complete matrix.

### Data Formats

| Type | Format | Example |
|------|--------|---------|
| Resource ID | Integer | `1`, `42`, `1337` |
| Username | String | `alice.smith`, `bob.jones` |
| Timestamp | ISO 8601 | `2025-01-15T10:30:00Z` |
| Duration | ISO 8601 | `PT24H`, `P7D`, `PT30M` |
| Boolean | JSON boolean | `true`, `false` |

**ID Strategy:**

- **User IDs:** Username from the `X-Username` identity header (e.g., `alice.smith`)
- **Resource IDs:** Database-generated auto-incrementing integers

---

## Response Headers

All API responses include:

| Header | Description |
|--------|-------------|
| `Content-Type` | `application/json` |
| `X-Request-ID` | Unique request identifier for tracing |

**X-Request-ID Behavior:**

- Server generates a UUID for each incoming request
- If client provides `X-Request-ID` header, server uses that value instead
- Same ID appears in response header and `meta.request_id` body field
- All log entries for the request include this ID for correlation

```
Response Header:
X-Request-ID: 550e8400-e29b-41d4-a716-446655440000

Response Body:
{
  "data": {...},
  "meta": {
    "request_id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

---

## Response Formats

### Success Response (Single Resource)

```json
{
  "data": {
    "id": 42,
    "name": "Resource Name",
    ...
  },
  "meta": {
    "request_id": "req-uuid"
  }
}
```

### Success Response (List/Paginated)

```json
{
  "data": [
    {"id": 1, ...},
    {"id": 2, ...}
  ],
  "meta": {
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "total": 150,
    "offset": 0,
    "limit": 50
  }
}
```

### Error Response

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable description",
    "details": {
      "field": "specific_field",
      "reason": "additional context"
    }
  },
  "meta": {
    "request_id": "req-uuid"
  }
}
```

---

## Pagination

All list endpoints support pagination:

| Parameter | Type | Default | Max | Description |
|-----------|------|---------|-----|-------------|
| offset | integer | 0 | - | Records to skip |
| limit | integer | 50 | 100 | Records to return |

Response includes:

- `meta.total`: Total matching records
- `meta.offset`: Current offset
- `meta.limit`: Current limit

### Example

```
GET /api/mappings?offset=50&limit=25

Response:
{
  "data": [...25 items...],
  "meta": {
    "total": 150,
    "offset": 50,
    "limit": 25
  }
}
```

---

## Filtering and Sorting

### Common Filter Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| owner | string | Filter by owner_username |
| search | string | Text search on name, description |
| created_after | timestamp | Filter by created_at >= value |
| created_before | timestamp | Filter by created_at <= value |
| status | string | Filter by resource status |

### Sorting Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| sort_by | string | created_at | Field to sort by |
| sort_order | string | desc | `asc` or `desc` |

---

## HTTP Status Codes

| Code | Usage |
|------|-------|
| 200 OK | Successful GET, PUT, DELETE |
| 201 Created | Successful POST (resource created) |
| 202 Accepted | Async operation started |
| 400 Bad Request | Invalid request body, validation failure |
| 401 Unauthorized | Missing identity header, user not provisioned, or user disabled |
| 403 Forbidden | Permission denied or insufficient role |
| 404 Not Found | Resource not found |
| 409 Conflict | State conflict (limit exceeded, dependencies, already exists) |
| 429 Too Many Requests | Rate limit exceeded |
| 500 Internal Server Error | Unexpected server error |
| 503 Service Unavailable | Maintenance mode or dependency unreachable |

---

## Error Codes Reference

The following table is the authoritative list of application-level error codes, verified against
`packages/control-plane/src/control_plane/models/errors.py` and
`packages/control-plane/src/control_plane/middleware/` (identity + error handler).

### Validation Errors (400)

| Code | Description |
|------|-------------|
| VALIDATION_FAILED | Request body or query parameter validation failed |

### Authentication Errors (401)

| Code | Description |
|------|-------------|
| UNAUTHORIZED | Missing or invalid identity (no `X-Username` header) |
| USER_NOT_PROVISIONED | `X-Username` present but user not found in PostgreSQL |
| USER_DISABLED | User account is disabled |

### Authorization Errors (403)

| Code | Description |
|------|-------------|
| PERMISSION_DENIED | User not authorized for the target resource |
| INSUFFICIENT_ROLE | User's role is lower than the endpoint requires |

### Not Found Errors (404)

| Code | Description |
|------|-------------|
| RESOURCE_NOT_FOUND | Generic resource not found (mapping, version, snapshot, instance, background job, etc.) |

### Conflict Errors (409)

| Code | Description |
|------|-------------|
| CONCURRENCY_LIMIT_EXCEEDED | Per-user or cluster-wide instance limit reached |
| RESOURCE_HAS_DEPENDENCIES | Cannot delete — dependent resources exist |
| INVALID_STATE | Resource is not in the state required for the operation (e.g. snapshot not ready) |
| ALREADY_EXISTS | Resource already exists |

### Rate Limit Errors (429)

| Code | Description |
|------|-------------|
| RATE_LIMIT_EXCEEDED | Endpoint-local rate limit exceeded; response includes `retry_after_seconds` in `details` |

### Server Errors (500/503)

| Code | Description |
|------|-------------|
| INTERNAL_ERROR | Unhandled server-side error |
| SERVICE_UNAVAILABLE | Maintenance mode enabled, or a required dependency (scheduler, DB, Starburst) is unavailable |

**503 SERVICE_UNAVAILABLE details:**

Returns 503 when:
- Maintenance mode is enabled (for resource creation requests)
- A required component (background job scheduler, Starburst, database) is unreachable

Note: During maintenance mode, read operations (GET) continue to work. Only creation requests (POST for new resources) return 503.

Each error response follows the standard envelope (`error.code`, `error.message`, `error.details`, `meta.request_id`). Specific endpoints may add structured `details` fields — see the per-endpoint specs.

---

## Rate Limiting

Rate limiting is not currently implemented at the API layer. Individual endpoints may enforce local throttles where noted (e.g. `POST /api/ops/jobs/trigger` — see [api.admin-ops.spec.md](-/api/api.admin-ops.spec.md)).

---

## Versioning

API versioning is not currently implemented. Future consideration:

```
Accept: application/vnd.graph-olap.v1+json
```

Or path-based:

```
/api/v1/mappings
/api/v2/mappings
```

---

## Anti-Patterns

See [architectural.guardrails.md](-/architectural.guardrails.md#anti-patterns-must-not-do) for the authoritative list.

Key sections relevant to API design:

- **API Design** - JSON only, pagination, immutable fields, validation rules
- **Authentication & Authorization** - Owner-based permissions, no credential exposure
- **Resource Lifecycle** - Lifecycle limits, concurrency limits, cleanup order
- **Data Handling & GCS** - GCS deletion order, favorites cleanup

---

## Open Questions

See [decision.log.md](--/process/decision.log.md) for consolidated open questions and architecture decision records.
