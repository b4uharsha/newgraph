---
title: "Authorization Specification: Owner-Based RBAC"
scope: hsbc
---

# Authorization Specification: Owner-Based RBAC

## Overview

Owner-based Role-Based Access Control (RBAC) for the Graph OLAP Platform. Three hierarchical roles govern access to all API endpoints. Resource ownership is assigned at creation time and is immutable.

**Tier:** 2 (referenced by all API specs)

## Prerequisites

- [api.common.spec.md](-/api.common.spec.md) - Authentication, middleware-injected headers (`X-Username`, `X-User-Role`)
- [data.model.spec.md](-/data.model.spec.md) - `owner_username` column on resource tables

User identity reaches the control plane via the Azure AD authentication proxy described in [ADR-137](--/process/adr/security/adr-137-azure-ad-auth-proxy.md). The proxy terminates the Azure AD OIDC flow at the ingress edge and forwards the authenticated user's identity to the control plane as the `X-Username` and `X-User-Role` headers. Resource-level owner enforcement is described in [ADR-144](--/process/adr/security/adr-144-graph-node-owner-access-control.md).

---

## Role Definitions

| Role | Purpose | Summary |
|------|---------|---------|
| **Analyst** | Data users | Create, query, and analyze graphs. Modify own resources only. |
| **Admin** | Power users | Full data access across all users. Bulk operations. Schema management. |
| **Ops** | Platform operators | All Admin capabilities plus system configuration, cluster monitoring, and background jobs. |

---

## Role Hierarchy

```
Analyst  <  Admin  <  Ops
```

Each higher role is a **strict superset** of the one below it. An Ops user can do everything an Admin can do, and an Admin can do everything an Analyst can do. There is no concept of disjoint permissions between roles.

---

## RBAC Permission Matrix

Complete per-endpoint authorization. "Own" means `resource.owner_username == user.username`.

### Data Resources

| Endpoint | Analyst | Admin | Ops |
|----------|---------|-------|-----|
| **Mappings** `GET /api/mappings` | List all | List all | List all |
| **Mappings** `POST /api/mappings` | Create (owns result) | Create (owns result) | Create (owns result) |
| **Mappings** `GET /api/mappings/:id` | Read any | Read any | Read any |
| **Mappings** `PUT /api/mappings/:id` | Own only | Any | Any |
| **Mappings** `DELETE /api/mappings/:id` | Own only | Any | Any |
| **Mappings** `POST /api/mappings/:id/copy` | Create copy (owns result) | Create copy (owns result) | Create copy (owns result) |
| **Snapshots** `GET /api/snapshots` | List all | List all | List all |
| **Snapshots** `POST /api/snapshots` | Create (owns result) | Create (owns result) | Create (owns result) |
| **Snapshots** `GET /api/snapshots/:id` | Read any | Read any | Read any |
| **Snapshots** `DELETE /api/snapshots/:id` | Own only | Any | Any |
| **Instances** `GET /api/instances` | List all | List all | List all |
| **Instances** `POST /api/instances` | Create (owns result) | Create (owns result) | Create (owns result) |
| **Instances** `GET /api/instances/:id` | Read any | Read any | Read any |
| **Instances** `DELETE /api/instances/:id` | Own only | Any | Any |
| **Instances** `POST /query` (Cypher, read-only) | Any instance | Any | Any |
| **Instances** algorithm endpoints | Own only | Any | Any |
| **Favorites** `GET /api/favorites` | Own only | Own only | Own only |
| **Favorites** `POST /api/favorites` | Create (owns result) | Create (owns result) | Create (owns result) |
| **Favorites** `DELETE /api/favorites/:id` | Own only | Own only | Own only |
| **Users** `GET /api/users/me` | Self | Self | Self |
| **Users** `GET /api/users` | No access | Full access | Full access |
| **Users** `*` other `/api/users/*` | See `packages/control-plane/src/control_plane/routers/users.py` for full set (scope: self-read for Analyst, admin/ops for cross-user operations) | | |

### Export Jobs (Scoped)

| Endpoint | Analyst | Admin | Ops |
|----------|---------|-------|-----|
| `GET /api/export-jobs` | Own snapshots only | All | All |

Analyst access is scoped via snapshot ownership: only export jobs for snapshots where `snapshot.owner_username == user.username` are returned.

### Admin Endpoints

| Endpoint | Analyst | Admin | Ops |
|----------|---------|-------|-----|
| **Schema Admin** `POST /api/schema/admin/refresh` | No access | Full access | Full access |
| **Schema Stats** `GET /api/schema/stats` | No access | Full access | Full access |
| **Bulk Delete** `DELETE /api/admin/resources/bulk` | No access | Full access | Full access |
| **E2E Cleanup** `DELETE /api/admin/e2e-cleanup` | No access | Full access | Full access |

### Ops-Only Endpoints

| Endpoint | Analyst | Admin | Ops |
|----------|---------|-------|-----|
| **Config** `GET/PUT /api/config/*` | No access | No access | Full access |
| **Cluster** `GET /api/cluster/*` | No access | No access | Full access |
| **Jobs** `POST /api/ops/jobs/trigger` | No access | No access | Full access |
| **Jobs** `GET /api/ops/jobs/status` | No access | No access | Full access |
| **State** `GET /api/ops/state` | No access | No access | Full access |
| **Export Jobs (debug)** `GET /api/ops/export-jobs` | No access | No access | Full access |

### Read-Only Endpoints (Any Authenticated User)

| Endpoint | Analyst | Admin | Ops |
|----------|---------|-------|-----|
| **Schema Browse** `GET /api/schema/catalogs`, `/schemas`, `/tables`, `/columns` | Full access | Full access | Full access |
| **Schema Search** `GET /api/schema/search/*` | Full access | Full access | Full access |

---

## Ownership Model

1. **Assignment.** The user who creates a resource owns it. The `owner_username` is set from the `X-Username` header at creation time.
2. **Immutable.** Ownership cannot be transferred after creation.
3. **No ACLs.** There is no resource-level sharing or access control list. Visibility follows the role hierarchy.
4. **Copy creates new ownership.** Copying a mapping (`POST /api/mappings/:id/copy`) creates a new resource owned by the caller, not the original owner.
5. **Storage.** The `owner_username` column is indexed on every resource table (`mappings`, `snapshots`, `instances`).
6. **Cypher queries are not gated by ownership.** The wrapper's `/query` endpoint is intentionally unauthenticated at the wrapper level. Any authenticated user can execute read-only Cypher against any instance they can reach. Mutating Cypher keywords (`CREATE`, `SET`, `DELETE`, `MERGE`, `REMOVE`, `DROP`) are rejected at the endpoint, so this is a read-catalogue model — consistent with the "Read any" rule for instance metadata. Algorithm execution, by contrast, is owner-gated via `require_algorithm_permission` → `/api/internal/instances/:slug/authorize` on the control plane.

---

## Authorization Enforcement

Authorization is enforced at two layers:

### Layer 1: Router-Level Role Gates

Router functions check the user's role from `X-User-Role` before any business logic executes. Requests from users with insufficient roles are rejected immediately with `403 Forbidden`.

> **Note (2026-04):** `require_ops_role` / `require_admin_role` are currently defined locally in each router module (`admin.py`, `ops.py`, `cluster.py`, `config.py`) rather than shared from a single helpers module. Functionally equivalent but not DRY — a candidate for refactor.

```python
# Ops-only endpoints
def require_ops_role(user: CurrentUser) -> None:
    if user.role != "ops":
        raise HTTPException(status_code=403, detail="Requires ops role")

# Admin-or-above endpoints
def require_admin_role(user: CurrentUser) -> None:
    if user.role not in ("admin", "ops"):
        raise HTTPException(status_code=403, detail="Requires admin role")
```

### Layer 2: Service-Layer Ownership Checks

For data resource mutations (update, delete), the service layer checks ownership after loading the resource. Admin and Ops users bypass the ownership check.

```python
# Analyst can only modify own resources; Admin/Ops can modify any
if user.role == "analyst" and resource.owner_username != user.username:
    raise HTTPException(status_code=403, detail="Only owner or admin can modify this resource")
```

Both layers must pass for a request to succeed.

---

## Error Responses

| Status | Condition | Response |
|--------|-----------|----------|
| **401 Unauthorized** | Missing or invalid authentication token | `{"error": {"code": "UNAUTHORIZED", "message": "Authentication required"}}` |
| **403 Forbidden** | User's role is below the endpoint minimum | `{"error": {"code": "FORBIDDEN", "message": "Requires admin role"}}` |
| **403 Forbidden** | Analyst attempting to modify another user's resource | `{"error": {"code": "PERMISSION_DENIED", "message": "Only owner or admin can update this mapping", "details": {"owner_username": "...", "your_role": "analyst"}}}` |

---

## Related Documents

| Document | Relevance |
|----------|-----------|
| [api.common.spec.md](-/api.common.spec.md) | Authentication middleware, `X-Username` / `X-User-Role` headers |
| [api.admin-ops.spec.md](-/api/api.admin-ops.spec.md) | Admin and Ops endpoint definitions |
| [api.mappings.spec.md](-/api/api.mappings.spec.md) | Mapping ownership and 403 responses |
| [api.instances.spec.md](-/api/api.instances.spec.md) | Instance ownership |
| [api.snapshots.spec.md](-/api/api.snapshots.spec.md) | Snapshot ownership |
| [ADR-137](--/process/adr/security/adr-137-azure-ad-auth-proxy.md) | Azure AD authentication proxy (identity source for `X-Username` / `X-User-Role`) |
| [ADR-144](--/process/adr/security/adr-144-graph-node-owner-access-control.md) | Graph-node owner access control (the ownership model enforced by this spec) |
