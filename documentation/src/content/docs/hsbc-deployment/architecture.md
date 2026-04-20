---
title: "Graph OLAP Platform Architecture"
sidebar:
  order: 2
---

## Overview

The Graph OLAP Platform provides a graph-based analytics layer over Starburst
Galaxy (Trino), exposing OLAP operations through a REST API consumed by Jupyter
notebooks on HSBC Dataproc clusters.

## Component Flow

```
Dataproc Jupyter -> SDK
  |-- Lifecycle   -> Control Plane (/api/instances) -> K8s (spawn wrapper pod)
  |-- Query       -> Wrapper Proxy (nginx) -> Wrapper Pod (/wrapper/<slug>/query)
  |                   (BYPASSES Control Plane)
  \-- Export      -> Control Plane (job row)
                      ^-- Export Worker claims via POST
                          /api/internal/export-jobs/claim -> GCS (Parquet)
```

Wrappers load pre-exported Parquet from GCS at startup; they never query
Starburst directly. Only the Export Worker talks to Starburst.

## Request Paths

There are three distinct paths the SDK uses; they do **not** all flow through
the Control Plane.

### 1. Lifecycle path (spawn / teardown wrapper instances)

1. User opens Jupyter notebook on Dataproc and imports `graph_olap_sdk`.
2. SDK calls Control Plane `/api/instances` with `X-Username` header.
3. Control Plane validates the user via DB role lookup.
4. Control Plane spawns a wrapper pod in Kubernetes and returns the
   instance's `url_slug` + wrapper-proxy URL.

### 2. Query path (Cypher queries — BYPASSES Control Plane)

1. SDK sends the Cypher query to the **Wrapper Proxy** (nginx) at
   `/wrapper/<url_slug>/query` — a separate host/route from the Control Plane
   API.
2. Wrapper Proxy routes to the target wrapper pod by `url_slug`.
3. Wrapper executes Cypher against its in-memory graph (KuzuDB / FalkorDB)
   loaded from pre-exported Parquet in GCS.
4. SDK deserialises the response into a DataFrame.

### 3. Export path (async Starburst -> GCS)

1. SDK asks the Control Plane to create an export; Control Plane inserts a
   job row.
2. **KEDA** scales the Export Worker deployment based on the Control Plane
   endpoint `/api/export-jobs/pending-count` (not a direct queue).
3. Export Worker claims a job via `POST /api/internal/export-jobs/claim`
   (not direct queue polling).
4. Export Worker runs the Starburst query and writes Parquet to GCS.
5. User downloads / reads the Parquet from the notebook.

## Deployment Model

- **CI:** Jenkins `gke_CI()` per repo (build + push image)
- **CD:** `cd/deploy.sh` orchestrates all services (kubectl apply)
- **Secrets:** `cd/create-secrets.sh` from GCP Secret Manager
- **Validation:** `unified-test.sh` 6-phase check
