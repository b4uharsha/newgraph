---
title: "API Specification: Snapshots"
scope: hsbc
---

# API Specification: Snapshots

<!-- Verified against code on 2026-04-20 -->

> **The public snapshots API is disabled.** Snapshots are created, updated, and deleted internally as part of the instance lifecycle and export pipeline. There are no public CRUD endpoints on `/api/snapshots`. See `api.internal.spec.md` for the internal status-update route used by the Export Worker.

## Overview

A snapshot is an immutable, point-in-time export of a mapping's data materialised in GCS (Parquet) and catalogued in the control plane. Snapshots exist only as a side-effect of the instance lifecycle — the Export Worker produces them and the control plane consumes them when starting a graph instance. Users never address snapshots directly over HTTP.

This document describes **what a snapshot is** (data model, lifecycle, field semantics) so other parts of the system have a single reference. For the actual wire protocol:

- User-facing instance creation: [api.instances.spec.md](api.instances.spec.md) — `POST /api/instances` with a `mapping_id` triggers snapshot creation implicitly.
- Internal status updates: [api.internal.spec.md](api.internal.spec.md) — `PATCH /api/internal/snapshots/{id}/status` is called by the Export Worker as the export progresses.

## Prerequisites

- [api.common.spec.md](--/api.common.spec.md) — Authentication, base URL, data formats, response patterns, error codes
- [requirements.md](--/--/foundation/requirements.md) — Snapshot definition and GCS structure
- [data.model.spec.md](--/data.model.spec.md) — Database schema for snapshots

---

## Data Model

A snapshot record has the following fields:

| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Primary key |
| `mapping_id` | integer | Mapping that produced this snapshot |
| `mapping_version` | integer | Version of the mapping at export time |
| `owner_username` | string | Username that triggered the export |
| `name` | string | Human-readable label |
| `description` | string | Free-text description |
| `gcs_path` | string | `gs://<bucket>/<user>/<mapping>/<snapshot>/` location of the Parquet export |
| `size_bytes` | integer | Total export size in bytes |
| `node_counts` | object | Per-node-type row counts (e.g. `{"Customer": 10000}`) |
| `edge_counts` | object | Per-edge-type row counts (e.g. `{"PURCHASED": 50000}`) |
| `status` | enum | `pending`, `creating`, `ready`, `failed` |
| `error_message` | string \| null | Populated when `status = failed` |
| `created_at` | timestamp | When the snapshot row was created |
| `updated_at` | timestamp | Last modification time |
| `ttl` | ISO 8601 duration | Lifetime before automatic cleanup (e.g. `P7D`) |
| `inactivity_timeout` | ISO 8601 duration | Idle period before cleanup (e.g. `P3D`) |
| `last_used_at` | timestamp | When a graph instance last attached to this snapshot |

### Example record

```json
{
  "id": 42,
  "mapping_id": 17,
  "mapping_version": 3,
  "owner_username": "alice.smith",
  "name": "January 2025 Snapshot",
  "description": "Monthly data export",
  "gcs_path": "gs://graph-olap-exports/alice.smith/17/42/",
  "size_bytes": 1073741824,
  "node_counts": {"Customer": 10000, "Product": 5000},
  "edge_counts": {"PURCHASED": 50000},
  "status": "ready",
  "error_message": null,
  "created_at": "2025-01-15T10:30:00Z",
  "updated_at": "2025-01-15T10:35:00Z",
  "ttl": "P7D",
  "inactivity_timeout": "P3D",
  "last_used_at": "2025-01-15T14:00:00Z"
}
```

---

## Lifecycle

Snapshots transition through the following states, all driven by the Export Worker via the internal API (no user action):

1. **`pending`** — Row created when a user calls `POST /api/instances` with a `mapping_id`. An export job is enqueued.
2. **`creating`** — The Export Worker has picked up the job and is materialising Parquet files to GCS (nodes first, then edges).
3. **`ready`** — Export succeeded; `gcs_path`, `size_bytes`, `node_counts`, and `edge_counts` are populated. The control plane can now start a graph instance against this snapshot.
4. **`failed`** — Export failed; `error_message` explains why. The instance that triggered the export is marked failed.

Cleanup is automatic: once `ttl` elapses after `created_at`, or `inactivity_timeout` elapses after `last_used_at`, a background job removes both the GCS objects and the database row.

---

## Why there is no public CRUD

Earlier designs exposed `POST`, `GET`, `PUT`, and `DELETE` under `/api/snapshots`. That surface was removed because:

- Users only ever want a running instance — managing snapshots as a separate object added workflow steps without value.
- Snapshot lifetime is strictly dependent on the owning instance and mapping version, so independent deletion invited dangling-instance bugs.
- Consolidating to a single `POST /api/instances` entry point eliminated a large class of race conditions between snapshot creation and instance startup.

The router file `packages/control-plane/src/control_plane/routers/api/snapshots.py` retains the handler code commented out for historical context; all decorators are disabled so FastAPI registers no public routes.
