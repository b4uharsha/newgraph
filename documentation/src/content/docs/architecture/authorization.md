---
title: "Graph OLAP Platform - Authorization & Access Control"
scope: hsbc
---

# Graph OLAP Platform - Authorization & Access Control

**Document Type:** Authorization Architecture & UX Definition
**Version:** 1.0
**Status:** Ready for Architectural Review
**Author:** Graph OLAP Platform Team
**Target Audience:** HSBC Enterprise Architecture, Information Security, Product
**Last Updated:** 2026-02-09
<style>
table { width: 100%; }
</style>


## Document Structure

This architecture documentation is organized into five focused documents:

| Document | Content |
|----------|---------|
| [Detailed Architecture](detailed-architecture.md) | Executive Summary + C4 Architecture Viewpoints + Resource Management |
| [SDK Architecture](sdk-architecture.md) | Python SDK, Resource Managers, Authentication |
| [Domain & Data Architecture](domain-and-data.md) | Domain Model, State Machines, Data Flows |
| [Platform Operations](platform-operations.md) | Technology, Security, Integration, Operations, NFRs |
| **This document** | RBAC Roles, Permission Matrix, Ownership Model, Enforcement |

---

## 1. Summary

The Graph OLAP Platform has three user roles arranged in a strict hierarchy. Each role builds on the one below it — there are no sideways permissions or special exceptions.

**Analyst** is the default role for data users. Analysts have full access to create and query graphs, but can only modify or delete resources they created themselves. They cannot see other users' export jobs or access any administrative functions.

**Admin** extends Analyst with cross-user data management. Admins can modify or delete any user's resources, perform bulk deletions, and manage the schema cache. This role is intended for team leads and power users who need to manage shared data assets.

**Ops** extends Admin with platform-level control. Only Ops users can change system configuration (concurrency limits, export settings, lifecycle policies), monitor cluster health, trigger background jobs, or enable maintenance mode. This role is reserved for the platform operations team.

```
Analyst  <  Admin  <  Ops
```

A user with a higher role can do everything a lower role can do. An Ops user never needs to switch roles to perform Analyst or Admin tasks.

---

## 2. What Each Role Can Do

### 2.1 Analyst — Data User

Analysts are the primary users of the platform. They work with graph data through mappings, snapshots, and instances.

An Analyst can:

- **Create** mappings, snapshots, and instances. All created resources are owned by the Analyst.
- **Read** any resource on the platform, regardless of who created it. This includes browsing mappings, viewing snapshot details, and listing instances created by other users.
- **Modify and delete** their own resources. An Analyst who created a mapping can update its schema or delete it.
- **Run Cypher queries against any instance**, including instances owned by other users. The wrapper's `/query` endpoint is intentionally unauthenticated — it is a read-only endpoint (mutating Cypher keywords are rejected) and follows the same "read any" rule that applies to instance metadata. Analysts treat other users' instances as a shared read catalogue.
- **Run algorithms on their own instances only.** Algorithm execution is enforced at the wrapper via a slow-path authorization call to the control plane (`/api/internal/instances/{slug}/authorize`); non-owner analysts receive a `403 Forbidden`. Admin and Ops users bypass the check.
- **Copy** any mapping. The copy becomes a new resource owned by the Analyst, not the original author.
- **Browse the data catalog** (Starburst schemas, tables, columns) to build new mappings.
- **Manage personal favorites** (bookmarks for frequently-used resources).
- **View their own export jobs** via the export queue.

An Analyst cannot:

- Modify or delete another user's mapping, snapshot, or instance.
- Run algorithms on another user's instance (queries are allowed — see above).
- See export jobs for snapshots they don't own.
- Access bulk delete, schema admin, or any system configuration.

When an Analyst tries to modify another user's resource, the platform returns a clear error: *"Only the owner or an admin can modify this resource"* with the owner's username and the Analyst's role included in the response.

### 2.2 Admin — Power User

Admins manage shared data assets across the team. They have everything an Analyst has, plus cross-user data access.

In addition to all Analyst capabilities, an Admin can:

- **Modify and delete any user's resources.** Ownership checks are bypassed — an Admin can clean up stale mappings, terminate orphaned instances, or delete snapshots regardless of who created them.
- **Bulk delete resources** with filters (by name prefix, owner, or resource type). Bulk operations require a reason and support dry-run mode for safety.
- **Refresh the schema cache** and view schema statistics.
- **View all export jobs** across the platform.

An Admin cannot:

- Change platform configuration (concurrency limits, export settings, lifecycle policies).
- View cluster health or instance distribution across nodes.
- Trigger or monitor background jobs (reconciliation, lifecycle, export).
- Enable or disable maintenance mode.

This boundary is intentional: Admins manage data, not the platform itself.

### 2.3 Ops — Platform Operator

Ops users run the platform. They have everything an Admin has, plus system-level control.

In addition to all Admin capabilities, an Ops user can:

- **Configure concurrency limits** — set per-analyst and cluster-wide instance caps.
- **Configure export settings** — adjust maximum export duration, concurrency, and Starburst catalog settings.
- **Configure lifecycle policies** — set default TTL and inactivity timeouts for instances and mappings.
- **Monitor cluster health** — view component status, instance distribution, and resource utilisation.
- **Trigger background jobs** — manually run reconciliation, lifecycle cleanup, or schema cache refresh.
- **View background job status** — see scheduler state and job execution history.
- **View platform state** — resource counts, active instances, and system metrics.
- **Enable maintenance mode** — block new instance creation with a user-facing message.
- **Access the ops export job view** — debug-level export queue with full job details.

Ops endpoints are exclusively for Ops users. Admins receive a `403 Forbidden` response if they attempt to access any `/api/config/*`, `/api/cluster/*`, or `/api/ops/*` endpoint.

---

## 3. Permission Matrix

The tables below are the detailed reference for per-endpoint authorization. "Own" means the resource was created by the requesting user.

### 3.1 Data Resources

| **Method** | **Path** | **Analyst** | **Admin** | **Ops** |
|------------|----------|-------------|-----------|---------|
| `GET` | `/api/mappings` | List all | List all | List all |
| `POST` | `/api/mappings` | Create (owns result) | Create (owns result) | Create (owns result) |
| `GET` | `/api/mappings/:id` | Read any | Read any | Read any |
| `PUT` | `/api/mappings/:id` | Own only | Any | Any |
| `DELETE` | `/api/mappings/:id` | Own only | Any | Any |
| `POST` | `/api/mappings/:id/copy` | Create copy (owns result) | Create copy (owns result) | Create copy (owns result) |
| `GET` | `/api/mappings/:id/snapshots` | Read any | Read any | Read any |
| `GET` | `/api/instances` | List all | List all | List all |
| `POST` | `/api/instances` | Create (owns result) | Create (owns result) | Create (owns result) |
| `GET` | `/api/instances/:id` | Read any | Read any | Read any |
| `DELETE` | `/api/instances/:id` | Own only | Any | Any |
| `PUT` | `/api/instances/:id/cpu` | Own only | Any | Any |
| `PUT` | `/api/instances/:id/memory` | Own only | Any | Any |
| `GET` | `/api/instances/:id/events` | Read any (authenticated) | Read any | Read any |
| `GET` | `/api/instances/user/status` | Self (own usage) | Self | Self |
| `POST` | Instance `/query` (Cypher, read-only) | Any instance | Any | Any |
| `POST` | Instance algorithm endpoints | Own only | Any | Any |
| `*` | Favorites | Own only | Own only | Own only |

Snapshots are created implicitly by `POST /api/instances` with a `mapping_id`. There is no public `/api/snapshots/*` HTTP surface — listing, reading, and deleting snapshots as a standalone resource are not exposed to end users, and snapshot lifecycle is managed internally as part of the instance lifecycle.

### 3.2 Export Jobs

| **Method** | **Path** | **Analyst** | **Admin** | **Ops** |
|------------|----------|-------------|-----------|---------|
| `GET` | `/api/export-jobs` | Own snapshots only | All | All |
| `GET` | `/api/export-jobs/pending-count` | **Unauthenticated (KEDA auto-scaling)** | Unauthenticated | Unauthenticated |

Analyst access is scoped via snapshot ownership: only export jobs for snapshots the Analyst created are visible.

The `pending-count` endpoint does **not** require user authentication so KEDA (or an equivalent autoscaler service account) can poll it. It returns only a single integer counter and exposes no user data.

### 3.3 Admin and Ops Endpoints

| **Method** | **Path** | **Analyst** | **Admin** | **Ops** |
|------------|----------|-------------|-----------|---------|
| `POST` | `/api/schema/admin/refresh` | 403 | Allowed | Allowed |
| `GET` | `/api/schema/stats` | 403 | Allowed | Allowed |
| `DELETE` | `/api/admin/resources/bulk` | 403 | Allowed | Allowed |
| `DELETE` | `/api/admin/e2e-cleanup` | 403 | Allowed | Allowed |
| `GET/PUT` | `/api/config/*` | 403 | 403 | Allowed |
| `GET` | `/api/cluster/*` | 403 | 403 | Allowed |
| `POST` | `/api/ops/jobs/trigger` | 403 | 403 | Allowed |
| `GET` | `/api/ops/jobs/status` | 403 | 403 | Allowed |
| `GET` | `/api/ops/state` | 403 | 403 | Allowed |
| `GET` | `/api/ops/export-jobs` | 403 | 403 | Allowed |

All authenticated users can browse the data catalog (`GET /api/schema/catalogs`, `/schemas`, `/tables`, `/columns`, `/search/*`) and health endpoints.

### 3.4 User Management Endpoints

User records are managed via the `/api/users/*` router. The `bootstrap` endpoint is the only un-authenticated path — it is used exactly once per environment to seed the first Ops user, after which it returns a conflict. All other user-management routes require Admin or Ops role, except `GET /api/users/{username}`, which an Analyst may call for their own record only.

| **Method** | **Path** | **Analyst** | **Admin** | **Ops** |
|------------|----------|-------------|-----------|---------|
| `POST` | `/api/users/bootstrap` | **Unauthenticated (seeds first Ops user; 409 after first use)** | Unauthenticated | Unauthenticated |
| `POST` | `/api/users` | 403 | Allowed | Allowed |
| `GET` | `/api/users` | 403 | Allowed | Allowed |
| `GET` | `/api/users/{username}` | Self only (403 otherwise) | Any | Any |
| `PUT` | `/api/users/{username}` | 403 | Allowed | Allowed |
| `PUT` | `/api/users/{username}/role` | 403 | Allowed | Allowed |
| `DELETE` | `/api/users/{username}` | 403 | Allowed (deactivate) | Allowed (deactivate) |

### 3.5 Internal Pod-to-Pod Endpoints

The `/api/internal/*` router family is protected by network policy rather than user-level RBAC (ADR-104/105). Only pods inside the cluster can reach these paths; no `X-Username` header is required or inspected. These endpoints are included here for completeness — they are never reachable from the SDK or the browser.

| **Method** | **Path** | **Analyst** | **Admin** | **Ops** |
|------------|----------|-------------|-----------|---------|
| `GET` | `/api/internal/instances/{slug}/authorize` | **Network-restricted (wrapper-to-control-plane)** | Network-restricted | Network-restricted |

The wrapper calls this endpoint on every algorithm request to resolve whether the requesting user owns the instance or carries an Admin/Ops role. Because all three user-facing role columns are identical (the route is not user-scoped), they are merged into a single "network-restricted" note rather than repeated three times.

---

## 4. Ownership

Every mapping, snapshot, and instance has an owner. Ownership is assigned when the resource is created and cannot be changed.

The owner is the authenticated user who made the creation request. Their username (from the `X-Username` header, resolved via DB-backed user records) is stored in the `owner_username` column on the resource table.

Ownership determines what an Analyst can modify. Analysts can only update or delete resources where `owner_username` matches their own username. Admin and Ops users bypass this check entirely — they can modify any resource regardless of ownership.

Copying a mapping creates a new resource. The copy is owned by the user who requested the copy, not the original mapping's author.

There is no concept of shared ownership, access control lists, or delegation. If an Analyst needs another user's resource modified, they ask an Admin.

### 4.1 Collaboration Patterns

Because there are no ACLs, collaboration on mappings happens through three explicit patterns rather than through sharing:

1. **Read any mapping.** All mappings are visible to all analysts by design. The mapping catalogue is a shared reference — any analyst can list, inspect, and compare versions of any mapping regardless of owner. In the SDK: `client.mappings.list()`, `client.mappings.get(id)`, `client.mappings.list_versions(id)`, `client.mappings.diff(...)`.
2. **Fork by copy.** `POST /api/mappings/:id/copy` (SDK: `client.mappings.copy(mapping_id, new_name)`) creates a new mapping owned by the caller, seeded from the current version of the source mapping. The copy has no upstream link and will not pick up future changes to the original.
3. **Ask an Admin for in-place edits.** If a mapping needs to be modified and the change must apply to everyone already using it, an Admin or Ops user bypasses the ownership check and updates it on behalf of the team. An Analyst calling `client.mappings.update(...)` on a teammate's mapping receives `403 PERMISSION_DENIED`. This is the only path to in-place cross-user edits.

Ownership is **immutable** — there is no mechanism to transfer a mapping from one user to another, or to grant write access to a specific teammate. The SDK-facing documentation for these patterns lives in the [Core Concepts — Working With Other Users' Mappings](/sdk-manual/02-core-concepts-manual/#working-with-other-users-mappings) section.

Snapshots and instances follow the same ownership model. One notable carve-out: read-only Cypher queries against a running instance are **not** ownership-gated — see [§2.1 Analyst — Data User](#21-analyst--data-user) for details. Algorithms remain owner-only.

---

## 5. Authentication

Users authenticate through two paths, both of which produce the same result: an `X-Username` header on every request to the control plane. The user's role is not transmitted in a header — it is resolved from the `role` column in the DB-backed `users` table. (Updated for ADR-104)

**Browser users** authenticate via HSBC SSO. The session cookie is validated by oauth2-proxy, which extracts the user's identity, then forwards the request with the `X-Username` header. The control plane looks up the user record and reads the `role` column.

**SDK and API users** present an API key. The auth middleware resolves the username from the key and loads the user record from the database. There is no JWT parsing in the control plane.

The control plane never sees raw credentials. It receives a pre-validated `X-Username` header, loads the corresponding user record, and constructs a `CurrentUser` context that is available to all route handlers and service methods.

---

## 6. Enforcement

Authorization is enforced at two layers. Both must pass for a request to succeed.

**Layer 1: Role gates** are applied at the router level. Before any business logic runs, the user's role is checked against the endpoint's minimum. Ops-only endpoints require `role == ops`. Admin endpoints require `role in (admin, ops)`. Data endpoints have no role gate — any authenticated user can access them.

In practice, Layer 1 enforcement is a **mix of two patterns**, both considered equivalent guards:

- **FastAPI dependency injection** — `Depends(require_role(...))` declared on the route, executed before the handler body runs. This is the preferred style for new endpoints.
- **Inline helper calls** — a helper such as `require_admin_or_ops_role(user)` invoked as the first statement of the handler (and in some service methods). See, for example, `packages/control-plane/src/control_plane/routers/api/admin.py:339` (`DELETE /api/admin/e2e-cleanup`), which uses the inline call. A small number of service-layer methods also perform inline role checks before mutating state.

Both patterns enforce the same role hierarchy and return the same `403 Forbidden` response on failure; the distinction is purely stylistic and reflects the age of each route.

**Layer 2: Ownership checks** are applied in the service layer for data mutations (update, delete). After loading the resource, the service checks whether the caller is the owner or has Admin/Ops role. Analysts who are not the owner receive a `403 Forbidden` with a message identifying the actual owner.

This two-layer approach provides defense in depth: even if a role gate were misconfigured, the ownership check would still prevent cross-user data modification for Analysts.

### Error Behaviour

When authorization fails, the platform returns a structured JSON error with a clear message:

- **401 Unauthorized** — no valid identity. The user is not authenticated.
- **403 Forbidden (role)** — the user's role is below the endpoint minimum. The response includes which role is required.
- **403 Forbidden (ownership)** — an Analyst is trying to modify another user's resource. The response includes the resource owner's username and the caller's role.

---

## 7. Design Decisions

**Three roles, not more.** A simple hierarchy is easier to reason about, audit, and explain to users. Adding a fourth role (e.g., "Viewer") was considered and rejected — Analysts already have read access to everything.

**Ops is separate from Admin.** Platform configuration changes (concurrency limits, lifecycle policies, maintenance mode) can affect all users. Restricting these to Ops prevents accidental platform-wide disruption from Admin users managing data.

**No ACLs or resource sharing.** Per-resource access control lists add significant complexity to the authorization model, the API surface, and the user experience. The current model covers all identified use cases with three roles and ownership.

**Immutable ownership.** Ownership transfer would require audit logging, approval workflows, and UI for managing transfers. The simpler model — you own what you create, Admins can manage anything — covers the same use cases with less complexity.

**Two-layer enforcement.** Role gates at the router prevent unauthorized endpoint access. Ownership checks in the service layer prevent cross-user data modification. Neither layer alone is sufficient; together they provide comprehensive coverage.

---

## Related Documents

- **[Detailed Architecture](detailed-architecture.md)** - Executive Summary + C4 Architecture Viewpoints + Resource Management
- **[SDK Architecture](sdk-architecture.md)** - Python SDK, Resource Managers, Authentication
- **[Domain & Data Architecture](domain-and-data.md)** - Domain Model, State Machines, Data Flows
- **[Platform Operations](platform-operations.md)** - Technology, Security, Integration, Operations, NFRs

---

*This is part of the Graph OLAP Platform architecture documentation. See also: [Detailed Architecture](detailed-architecture.md), [SDK Architecture](sdk-architecture.md), [Domain & Data Architecture](domain-and-data.md), [Platform Operations](platform-operations.md).*
