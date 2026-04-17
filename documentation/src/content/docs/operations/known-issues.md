---
title: "Known Issues"
scope: hsbc
---

# Known Issues

Issues and limitations known at handover. Listed by severity.

---

## High

### GCS Bucket Permission Failure Silently Disables Cleanup

**Component:** Control Plane — `clients/gcs.py:137-182`

If the control-plane's GKE Workload Identity service account lacks `storage.objectAdmin` on the GCS bucket, the `build_gcs_client_from_settings` function returns `None` and logs a warning (`build_gcs_client_failed`). All subsequent snapshot deletions skip GCS cleanup — database records are removed but Parquet files remain in GCS.

**Impact:** GCS storage costs grow indefinitely. No alert fires for this condition by default.

**Workaround:** Set a GCS bucket lifecycle rule to auto-delete objects older than 90 days. Monitor for `build_gcs_client_failed` log entries and fix the service account IAM binding.

**Fix required:** Grant `roles/storage.objectAdmin` on the export bucket to the control-plane's Workload Identity GSA. See [Configuration Reference](configuration-reference.md#gcs-bucket-permissions) for details.

### Schema Cache Not Connecting to Starburst

**Component:** Control Plane — `cache/schema_cache.py`

The schema metadata cache job runs every 24 hours (configurable via `GRAPH_OLAP_SCHEMA_CACHE_JOB_INTERVAL_SECONDS`) and requires a working Starburst connection. If `GRAPH_OLAP_STARBURST_URL` is not set or Starburst is unreachable, the cache refresh raises, is logged at ERROR (`schema_cache_refresh_failed` with `exc_info=True` at `jobs/schema_cache.py:93-95`), and re-raises to the scheduler — no alert fires and the schema browser endpoints (`/api/schema/*`) return empty or stale data until the next successful refresh.

**Impact:** The Starburst schema browser in the SDK returns no catalogs/schemas/tables, which means analysts cannot discover available data sources.

**Workaround:** Verify Starburst connectivity from the control-plane pod. The cache can be manually refreshed via `POST /api/schema/admin/refresh` (requires Ops role).

**Fix required:** Ensure `GRAPH_OLAP_STARBURST_URL` is set correctly and the control-plane pod has network access to the Starburst endpoint.

---

## Medium

### No Authentication in Current Deployment

**Component:** Platform-wide — ADR-112

The platform currently operates with IP whitelisting as the sole access control boundary. The `X-Username` header is client-set and unverified — any client behind the IP whitelist can impersonate any user.

**Impact:** No authentication or identity verification. Acceptable for a demo environment, not for production.

**Planned fix:** ADR-137 describes the Azure AD authentication proxy migration. HSBC must deploy an Azure AD auth proxy (oauth2-proxy or similar) in front of the control-plane ingress to enforce real identity. No application code changes required — purely infrastructure configuration.

**Resources for enabling authentication and authorisation integration:**

- [Platform Operations Manual](platform-operations.manual.md) — current auth model and Azure AD migration plan (7 phases)
- [Security Operations Runbook](security-operations.runbook.md) — access control procedures and known `X-Username` trust limitation
- [Authorization](--/architecture/authorization.md) — RBAC roles (Analyst/Admin/Ops), permission matrix, ownership model
- [Authorization Spec](--/system-design/authorization.spec.md) — enforcement code and endpoint-level permissions
- [ADR-112](--/process/adr/security/adr-112-remove-auth0-replace-with-ip-whitelisting.md) — rationale for the current IP-whitelist posture
- [ADR-137](--/process/adr/operations/adr-137-azure-ad-auth-proxy-migration.md) — target Azure AD / oauth2-proxy architecture

### Instance Events Not Written to Database

**Component:** Control Plane — `jobs/resource_monitor.py:270`

The resource monitor job logs memory upgrade, OOM recovery, and resize events to structured logs but does not write them to the `instance_events` database table. The repository (`InstanceEventsRepository` at `repositories/instance_events.py:27`) is fully implemented with a `create` method, and the read endpoint (`GET /instances/{id}/events` at `routers/api/instances.py:427-452`) is wired. The write path is a one-line gap — `_create_instance_event` only logs, with a stale TODO comment claiming the repository doesn't exist yet. The `_instance_repo` parameter is already passed in but unused.

**Impact:** The instance events API endpoint always returns an empty list.

### Maintenance Mode Enforcement Not Wired

**Component:** Control Plane — `models/errors.py:130`, `repositories/config.py:308`, `routers/api/*.py`

The maintenance-mode toggle is only half-implemented. The `GET` and `PUT /api/config/maintenance` endpoints work and persist `maintenance.enabled` and `maintenance.message` to the database. The `MaintenanceError` exception class (HTTP 503, code `SERVICE_UNAVAILABLE`) and the `ConfigRepository.is_maintenance_mode()` helper are both defined. However, no router, middleware, or FastAPI dependency ever calls `is_maintenance_mode()` or raises `MaintenanceError`. As a result, setting the flag records state in the database but does **not** block any write operations.

The component design document (`component-designs/control-plane.design.md:860`) imports a `require_maintenance_off` FastAPI dependency that is supposed to guard write routers (mappings, instances, snapshots, favourites); its body is defined at lines 1463-1471 and applied via `Depends(require_maintenance_off)` at lines 1125 and 1174. This dependency does not exist in the source code — the design describes an intended wiring that was never implemented.

**Impact:** Operators cannot put the platform into a read-only state via the API. During scheduled maintenance windows, write requests continue to succeed silently. Analysts receive no `SERVICE_UNAVAILABLE` response and the SDK has no `MaintenanceError` handling. Maintenance windows must be coordinated out-of-band (email, JupyterHub MOTD, or an ingress-level maintenance page).

**Workaround:** Block traffic at the ingress (for example, by serving a static maintenance page from the GKE ingress controller) or scale the control-plane deployment to zero replicas for the duration of the window. Communicate the window to analysts via email in advance.

**Fix required:**
1. Implement a `require_maintenance_off` FastAPI dependency in `dependencies.py` that calls `ConfigRepository.is_maintenance_mode()` and raises `MaintenanceError(message=...)` with the configured message when the flag is set.
2. Add `Depends(require_maintenance_off)` to every write route in `routers/api/mappings.py`, `instances.py`, `favorites.py`, and any future write endpoints. Read routes must remain unguarded.
3. Update the SDK `HTTPClient` to map `503 SERVICE_UNAVAILABLE` responses to a typed `MaintenanceError` exception that carries the operator-supplied message.
4. Add integration tests that flip the flag and assert a 503 on writes and a 200 on reads.

**Resources for enabling maintenance-mode enforcement:**

- [Control Plane Design — maintenance-mode wiring](--/component-designs/control-plane.design.md) — `require_maintenance_off` body and the write-router `Depends(...)` placements the implementation must match (search for `require_maintenance_off`; key lines are the import at `:860`, dependency placements at `:1125` and `:1174`, and the dependency body at `:1463-1471`)
- [Admin/Ops API Spec — Maintenance Mode](--/system-design/api/api.admin-ops.spec.md#set-maintenance-mode) — `GET`/`PUT /config/maintenance` contract (already implemented)
- `models/errors.py:130` — `MaintenanceError` (HTTP 503, code `SERVICE_UNAVAILABLE`)
- `repositories/config.py:308` — `ConfigRepository.is_maintenance_mode()` helper

---

## Low

### Background Job Interval Conflict in Documentation

The service catalogue (`docs/operations/service-catalogue.manual.md:522-524,578-580`) lists `RECONCILIATION_JOB_INTERVAL_SECONDS=30`, `LIFECYCLE_JOB_INTERVAL_SECONDS=30`, and `SCHEMA_CACHE_JOB_INTERVAL_SECONDS=300`. The code is authoritative and the actual defaults in `config.py:117-121` are:

- `lifecycle_job_interval_seconds = 300`
- `reconciliation_job_interval_seconds = 300`
- `instance_orchestration_job_interval_seconds = 5`
- `schema_cache_job_interval_seconds = 86400`

The service catalogue undershoots reconciliation/lifecycle by 10x and schema cache by ~288x. Update the catalogue to match the code.

