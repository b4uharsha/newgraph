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
Dataproc Jupyter -> SDK -> Control Plane -> Wrappers -> Databases
                                |
                                +-- FalkorDB Wrapper -> FalkorDB (graph cache)
                                +-- RyuGraph Wrapper -> Starburst (OLAP queries)
                                +-- Export Worker -> GCS (async exports)
```

## 12-Step Request Flow

1. User opens Jupyter notebook on Dataproc
2. Notebook imports `graph_olap_sdk`
3. SDK sends request to Control Plane (X-Username header)
4. Control Plane validates user via DB role lookup
5. Control Plane routes to appropriate wrapper
6. Wrapper executes query against backend database
7. Response returned through Control Plane
8. SDK deserialises response into DataFrame
9. For exports: Control Plane queues job
10. Export Worker picks up job via KEDA scaling
11. Export Worker writes to GCS
12. User downloads export from notebook

## Deployment Model

- **CI:** Jenkins `gke_CI()` per repo (build + push image)
- **CD:** `cd/deploy.sh` orchestrates all services (kubectl apply)
- **Secrets:** `cd/create-secrets.sh` from GCP Secret Manager
- **Validation:** `unified-test.sh` 6-phase check
