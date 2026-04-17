---
title: "ADR-144: Graph Node Owner-Only Access Control for Algorithm Endpoints"
---

| | |
|---|---|
| **Date** | 2026-04-16 |
| **Status** | Proposed |
| **Category** | security |


## Context

Each graph instance is owned by the analyst who created it. Wrapper pods (ryugraph, falkordb) run as
ephemeral Kubernetes pods scoped to a single instance — one pod per graph. When a pod starts, it
receives `WRAPPER_OWNER_ID` as an env var set to the creating analyst's username.

### What was removed and why

`AlgorithmPermissionDep` was a FastAPI dependency applied to all algorithm and NetworkX endpoints in
both wrappers. It implemented a two-path authorisation check:

**Fast path** (no network call):
```python
owner_id = get_settings().wrapper.owner_id   # WRAPPER_OWNER_ID env var
if username == owner_id:
    return username  # allow immediately
```

**Slow path** (CP round-trip):
```python
resp = await httpx.AsyncClient().get(
    f"{cp_url}/api/internal/instances/{url_slug}/authorize",
    params={"username": username},
)
# allowed if resp.json()["allowed"] == True
```

The slow path hit `{cp_url}` — the external-facing control-plane URL. In the HSBC environment,
the external CP URL is protected by a reverse proxy requiring authentication (oauth2-proxy or
IP-whitelisting). Wrapper pods are inside the cluster and do not carry bearer tokens, so the
authorise call returned HTTP 401 and the wrapper raised `AuthenticationError`.

Commit `a11e9ed8` removed `AlgorithmPermissionDep` from all three routers and justified the
removal with "network policy already protects wrapper pods". That is partially true, but it leaves
a gap (see below).

---

## Current Security Posture

| Layer | Protection provided | Limitation |
|---|---|---|
| **Network policy** | Wrapper pods are only reachable via the nginx wrapper-proxy | Proxy enforces routing, not identity |
| **Unguessable URL slug** | UUID url_slug is required to reach a pod | Not cryptographically enforced; leaks via logs/error messages |
| **No algorithm auth** | Any user who reaches the pod can call `/algo/*` and `/networkx/*` | **Gap** |

### Threat scenario

If analyst B learns analyst A's `url_slug` (e.g. from shared notebook output, an error message, or
access logs), analyst B can:

1. Call `POST /algo/pagerank` on analyst A's graph pod
2. Read graph topology containing sensitive entity relationships (Customer nodes, account links)
3. Cancel or pollute in-flight algorithm executions

This is a horizontal privilege escalation within the analyst tier.

---

## Root Cause of the HSBC Failure

The slow path (`/api/internal/instances/{url_slug}/authorize`) itself is unauthenticated — the
control-plane router for `/api/internal/` does not require an API key. The 401 came from the
**external reverse proxy in front of the CP**, not from the CP endpoint itself.

The fix is therefore not to remove the check but to route the authorise call correctly:

- **Wrong:** call the external CP URL (goes through proxy requiring auth)
- **Right:** call the in-cluster CP service directly (bypasses the external proxy)

The in-cluster service address follows the pattern:
`http://control-plane.{namespace}.svc.cluster.local:8080`

This is already how export-worker communicates with the CP.

---

## Decision Options

### Option A — Fix the CP URL used for authorisation calls (preferred)

Re-add `AlgorithmPermissionDep` to all algorithm routes. Change `require_algorithm_permission` to
use an internal-only `control_plane_internal_url` setting (defaults to the same host but on the
cluster-internal service address, bypassing the proxy).

**Implementation:**
- Add `WRAPPER_CONTROL_PLANE_INTERNAL_URL` env var to wrapper config
  (`packages/ryugraph-wrapper/src/wrapper/config.py`,
  `packages/falkordb-wrapper/src/wrapper/config.py`)
- Set it in `k8s_service.py` alongside `WRAPPER_OWNER_ID`, pointing at the in-cluster service
- In `require_algorithm_permission` (both `dependencies.py`), prefer the internal URL for the
  authorise call, falling back to fast-path-only if the env var is absent
- Re-add `_authorized: AlgorithmPermissionDep` to:
  - `ryugraph-wrapper/src/wrapper/routers/algo.py`: `find_shortest_path`, `execute_algorithm`
  - `ryugraph-wrapper/src/wrapper/routers/networkx.py`: `execute_algorithm`
  - `falkordb-wrapper/src/wrapper/routers/algo.py`: `execute_algorithm`, `cancel_execution`

**Advantages:**
- Restores full design intent: Analysts restricted to own graph, Admin/Ops can access any graph
- Defense-in-depth: slug secrecy + network policy + identity check
- The CP authorize endpoint (`/api/internal/instances/{url_slug}/authorize`) already implements the
  correct rules (owner allowed, admin/ops allowed, everyone else denied)

**Disadvantages:**
- CP unavailability degrades algorithm endpoints (mitigated by fast-path for owner)
- Requires correct in-cluster DNS at deploy time

---

### Option B — Fast-path-only (owner == requester, else 403)

Remove the slow path entirely. If the requesting username does not match `WRAPPER_OWNER_ID`, deny
immediately. No CP round-trip.

**Implementation:**
- Modify `require_algorithm_permission` to raise `HTTP 403` if `username != owner_id`
- Re-add the dependency to all algorithm routes (same four files as Option A)
- No new env vars needed

**Advantages:**
- No network dependency; cannot fail due to CP unavailability
- Simple, auditable logic

**Disadvantages:**
- Admin and Ops users cannot run algorithms on an analyst's graph (reduces operational capability)
- To inspect a graph for support purposes, Ops would need to find another access path

---

### Option C — Proxy-layer enforcement (future consideration)

Extend the nginx wrapper-proxy to validate `X-Username` against the instance owner stored in the
CP database before forwarding algorithm requests. The proxy is already the single ingress point;
adding stateful enforcement here would remove the need for any auth logic in the wrappers.

This is architecturally clean but requires the proxy to carry instance-owner state, which
significantly increases its complexity. Deferred to a future ADR.

---

## Recommendation

**Implement Option A** as the primary fix. It restores the original design intent without
sacrificing Admin/Ops cross-instance access. Option B is a safe interim fallback if Option A
cannot be deployed immediately (e.g. during staged HSBC environment testing).

### Implementation checklist

```
packages/control-plane/src/control_plane/services/k8s_service.py
  └── add {"name": "WRAPPER_CONTROL_PLANE_INTERNAL_URL",
           "value": f"http://control-plane.{namespace}.svc.cluster.local:8080"}
      to wrapper pod env vars (alongside WRAPPER_OWNER_ID)

packages/ryugraph-wrapper/src/wrapper/config.py
packages/falkordb-wrapper/src/wrapper/config.py
  └── add: control_plane_internal_url: str | None = Field(
              default=None,
              validation_alias="WRAPPER_CONTROL_PLANE_INTERNAL_URL")

packages/ryugraph-wrapper/src/wrapper/dependencies.py
packages/falkordb-wrapper/src/wrapper/dependencies.py
  └── in require_algorithm_permission:
        use settings.wrapper.control_plane_internal_url (or control_plane_url if absent)
        for the /authorize httpx call

packages/ryugraph-wrapper/src/wrapper/routers/algo.py
  └── re-add: _authorized_user: AlgorithmPermissionDep  (find_shortest_path, execute_algorithm)

packages/ryugraph-wrapper/src/wrapper/routers/networkx.py
  └── re-add: _authorized_user: AlgorithmPermissionDep  (execute_algorithm)

packages/falkordb-wrapper/src/wrapper/routers/algo.py
  └── re-add: _authorized: AlgorithmPermissionDep  (execute_algorithm, cancel_execution)
```

### Testing

- Unit: `test_require_algorithm_permission` — owner passes, non-owner denied (fast path)
- Unit: slow path returns 200 `{"allowed": true}` → passes; 200 `{"allowed": false}` → 403
- Integration: analyst calling their own graph algo → 200; calling another graph's algo → 403
- E2E: UAT GP-03/04 (role variants) must exercise Admin/Ops accessing analyst graph algos

---

## Consequences

**Positive:**
- Closes horizontal privilege escalation gap between analyst graph instances
- Re-establishes defense-in-depth (network policy + identity + slug secrecy)
- Admin/Ops retain cross-instance algorithm access via CP authorise endpoint

**Negative:**
- Adds one CP round-trip per algorithm call for non-owners
- Requires new env var deployed to all wrapper pods (rolling restart of active instances)

---

## References

- Commit [`a11e9ed8`](https://github.com/sparkling-ideas/hsbc-graph/commit/a11e9ed8) — removal of `AlgorithmPermissionDep` (root cause commit)
- [ADR-097](-/adr-097-hierarchical-role-model.md) — role model: Analyst < Admin < Ops
- [ADR-105](-/adr-105-x-username-header-identity-with-static-default.md) — `X-Username` header identity
- [ADR-101](--/infrastructure/adr-101-nginx-reverse-proxy-for-wrapper-routing.md) — wrapper-proxy routing
- Control-plane authorize endpoint: `packages/control-plane/src/control_plane/routers/internal/instances.py:301`
- Dependency definition: `packages/ryugraph-wrapper/src/wrapper/dependencies.py:170`
