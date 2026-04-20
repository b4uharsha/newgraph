---
title: "Service Catalogue"
scope: hsbc
---

<!-- JupyterHub + extension-server removed, us-central1 corrected, fabricated SLAs neutralised 2026-04-20 -->

# Service Catalogue

**Document Type:** Operations Manual
**Version:** 1.1
**Last Updated:** 2026-04-20
**ADR:** [ADR-134](--/process/adr/operations/adr-134-service-catalogue.md), [ADR-149](--/process/adr/process/adr-149-implementation-vs-documentation-drift-remediation.md) (Tier-B.7 drift remediation)

---

## 1. Service Inventory

### 1.1 Platform Services

| Service | Type | Port | Health Endpoint | Replicas | Criticality | Owner |
|---------|------|------|-----------------|----------|-------------|-------|
| control-plane | Deployment | 8080 | `GET /health` | 2 baseline, HPA 2→3 | Critical | HSBC ops (TBD) |
| export-worker | Deployment | -- | -- | 1 baseline, KEDA 1→5 | High | HSBC ops (TBD) |
| wrapper-proxy | Deployment | 80 | -- | 1 (fixed) | High | HSBC ops (TBD) |
| documentation | Deployment | 8000 | `GET /` | 1 | Low | HSBC ops (TBD) |

> **Autoscaling state.** HPA is wired for control-plane (`infrastructure/cd/resources/control-plane-hpa.yaml`, `minReplicas: 2`, `maxReplicas: 3`, 70% CPU / 80% memory targets). KEDA `ScaledObject` is wired for export-worker (`export-worker-keda-scaledobject.yaml`, `minReplicaCount: 1`, `maxReplicaCount: 5`, metrics-api trigger polling `/api/export-jobs/pending-count`). Wrapper-proxy runs at fixed `replicas: 1`. The export-worker deployment ships with `replicas: 1` so the worker polls permanently; setting `replicas: 0` enables scale-to-zero once KEDA is confirmed installed in the target cluster.

### 1.2 Dynamic Services (Created on Demand)

| Service | Type | Port | Health Endpoint | Lifecycle | Criticality |
|---------|------|------|-----------------|-----------|-------------|
| ryugraph-wrapper | Pod | 8000 | `GET /health` | Per-instance, TTL-managed | High |
| falkordb-wrapper | Pod | 8000 | `GET /health` | Per-instance, TTL-managed | High |

> **Note — wrapper deployment model.** `ryugraph-wrapper` and
> `falkordb-wrapper` have **no Helm charts**. Wrapper pods are created
> imperatively by the control plane at instance creation time, one per
> instance. See
> [`ryugraph-wrapper.deployment.design.md`](--/component-designs/ryugraph-wrapper.deployment.design.md)
> for the spawn flow, image-rollout procedure, and lifecycle.

### 1.3 JupyterHub

JupyterHub is not deployed in the HSBC target environment. Analysts run the SDK from corporate-issued notebooks via the VDI (ADR-108).

---

## 2. Dependency Map

![service-dependency-map](diagrams/service-catalogue-manual/service-dependency-map.svg)

<details>
<summary>Mermaid Source</summary>

```mermaid
---
config:
  layout: elk
  elk:
    mergeEdges: false
    nodePlacementStrategy: BRANDES_KOEPF
---
flowchart TD
    accTitle: Service Dependency Map
    accDescr: Service-to-service and service-to-infrastructure dependencies for the Graph OLAP Platform

    classDef service fill:#E8F5E9,stroke:#2E7D32,stroke-width:2px,color:#1B5E20
    classDef data fill:#FFF8E1,stroke:#F57F17,stroke-width:2px,color:#E65100
    classDef infra fill:#E3F2FD,stroke:#1565C0,stroke-width:2px,color:#0D47A1
    classDef external fill:#ECEFF1,stroke:#455A64,stroke-width:2px,color:#263238
    classDef process fill:#E1F5FE,stroke:#0277BD,stroke-width:2px,color:#01579B

    subgraph ext [External]
        SB[Starburst Galaxy]:::external
    end

    subgraph infra_grp [Infrastructure]
        SQL[(Cloud SQL)]:::data
        GCS[(GCS)]:::data
        K8S[K8s API]:::infra
    end

    subgraph platform [Platform Services]
        CP[control-plane]:::service
        EW[export-worker]:::service
        WP[wrapper pods]:::service
        SDK[SDK on VDI / Dataproc]:::external
    end

    CP -->|metadata CRUD| SQL
    CP -->|snapshot mgmt| GCS
    CP -->|pod lifecycle| K8S
    CP -->|schema metadata| SB

    EW -->|poll + claim jobs| CP
    EW -->|UNLOAD queries| SB
    EW -->|verify Parquet| GCS

    WP -->|load Parquet| GCS

    SDK -->|SDK API calls| CP
    SDK -->|Cypher queries| WP
```

</details>

### 2.1 Dependency Direction Summary

| From | To | Protocol | Purpose |
|------|----|----------|---------|
| control-plane | Cloud SQL | PostgreSQL (TLS) | Metadata CRUD |
| control-plane | GCS | HTTPS | Snapshot management |
| control-plane | K8s API | HTTPS | Wrapper pod lifecycle |
| control-plane | Starburst Galaxy | HTTPS | Schema metadata, query validation |
| export-worker | control-plane | HTTP (in-cluster) | Poll and claim export jobs |
| export-worker | Starburst Galaxy | HTTPS | Submit UNLOAD queries |
| export-worker | GCS | HTTPS | Verify Parquet row counts |
| wrapper pods | GCS | HTTPS | Load Parquet data on startup |
| SDK (VDI / Dataproc) | control-plane | HTTPS (via ingress) | SDK API calls |
| SDK (VDI / Dataproc) | wrapper pods | HTTPS (via wrapper-proxy) | Cypher queries, algorithm execution |

---

## 3. Service Descriptions

### 3.1 control-plane

**Purpose:** Central API server. Manages all platform resources (mappings, snapshots, instances). Runs background reconciliation and lifecycle jobs. Serves as the single entry point for the SDK and all administrative operations.

**Key Endpoints:**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Liveness and readiness probe |
| `/metrics` | GET | Prometheus metrics (port 9090) |
| `/api/mappings/*` | CRUD | Graph mapping definitions |
| `/api/instances/*` | CRUD | Graph instance lifecycle |
| `/api/schema/*` | GET | Starburst Galaxy schema browser |
| `/api/config/*` | GET/PUT | Runtime configuration (Ops role) |
| `/ops/*` | GET/POST | Cluster health, background jobs, metrics |
| `/admin/*` | POST | Bulk operations (Admin role) |
| `/api/internal/*` | POST | Service-to-service (export-worker) |

**Dependencies:**

- **Upstream:** Cloud SQL (required -- will not start without it), GCS, K8s API, Starburst Galaxy
- **Downstream:** export-worker (polls control-plane), SDK/notebooks (API calls), wrapper pods (created by control-plane)

**Data Stores:**

- Cloud SQL PostgreSQL: all metadata (mappings, snapshots, instances, export jobs, config)
- GCS: snapshot Parquet files (read/write)

**Key Environment Variables:**

| Variable | Source | Purpose |
|----------|--------|---------|
| `DATABASE_URL` | Secret `control-plane-secrets` | PostgreSQL connection string |
| `GCS_BUCKET` | ConfigMap | GCS bucket name |
| `GCP_PROJECT` | ConfigMap | GCP project ID |
| `K8S_NAMESPACE` | ConfigMap | Namespace for wrapper pods |
| `WRAPPER_IMAGE` | ConfigMap | Ryugraph wrapper Docker image |
| `FALKORDB_WRAPPER_IMAGE` | ConfigMap | FalkorDB wrapper Docker image |
| `STARBURST_URL` | ConfigMap | Starburst Galaxy endpoint |
| `STARBURST_USER` | ConfigMap | Starburst Galaxy service account |
| `STARBURST_PASSWORD` | Secret `starburst-credentials` | Starburst Galaxy password |

> **Note — internal endpoint authentication.** Internal endpoints (`/api/internal/*`) are isolated by NetworkPolicy, not a shared secret. See `packages/control-plane/src/control_plane/config.py:123-124`.

**Health Check:** Liveness and readiness probes both target `/health` on the control plane (see `infrastructure/cd/resources/control-plane-deployment.yaml`). There is no separate `/ready` endpoint on the control plane — wrapper pods do have one (see `api.wrapper.spec.md`).

**Restart Safety:** Safe to restart. Stateless -- all state is in Cloud SQL. In-flight API requests will fail; clients (SDK) retry automatically. Background jobs resume on startup.

**Scaling:** Deployment ships with `replicas: 2` (`infrastructure/cd/resources/control-plane-deployment.yaml`); HPA (`control-plane-hpa.yaml`) scales between 2 and 3 replicas on 70% CPU / 80% memory utilisation. Database connection pool: 25 per replica + 5 overflow.

---

### 3.2 export-worker

**Purpose:** Polls control-plane for pending export jobs, submits UNLOAD queries to Starburst Galaxy, monitors query progress, and verifies Parquet row counts in GCS. Fully stateless -- all state is persisted in Cloud SQL via the control-plane API.

**Key Interfaces:**

| Interface | Direction | Purpose |
|-----------|-----------|---------|
| `POST /api/internal/exports/claim` | Outbound to control-plane | Claim pending jobs |
| `POST /api/internal/exports/{id}/status` | Outbound to control-plane | Report job status |
| Starburst Galaxy REST API | Outbound | Submit UNLOAD, poll query status |
| GCS | Outbound | Count Parquet rows |

**Dependencies:**

- **Upstream:** control-plane (required -- will not start without it via init container check)
- **Upstream:** Starburst Galaxy (required for export execution)
- **Upstream:** GCS (required for row count verification)
- **Downstream:** None

**Data Stores:** None directly. All state is managed through the control-plane API.

**Key Environment Variables:**

| Variable | Source | Purpose |
|----------|--------|---------|
| `CONTROL_PLANE_URL` | ConfigMap | Control-plane internal URL |
| `STARBURST_URL` | ConfigMap | Starburst Galaxy endpoint |
| `STARBURST_USER` | ConfigMap | Starburst Galaxy service account |
| `STARBURST_PASSWORD` | Secret `export-worker-secrets` | Starburst Galaxy password |
| `POLL_INTERVAL_SECONDS` | ConfigMap | Main loop interval (default 5) |
| `CLAIM_LIMIT` | ConfigMap | Max jobs to claim per cycle (default 10) |

> **Note — internal endpoint authentication.** The worker authenticates to the control-plane via NetworkPolicy-scoped in-cluster access, not a shared secret.

**Health Check:** No HTTP health endpoint. Liveness is determined by pod status. The worker runs a continuous polling loop and exits on fatal errors.

**Restart Safety:** Safe to restart at any time. No in-memory state. Export jobs use a claim-based model: uncompleted claims are reset by the control-plane export reconciliation job (runs every 5 seconds; deliberate exception to ADR-040 for near-real-time propagation) and re-claimed by another worker.

**Scaling:** KEDA `ScaledObject` (`infrastructure/cd/resources/export-worker-keda-scaledobject.yaml`) is wired for export-worker (`minReplicaCount: 1`, `maxReplicaCount: 5`, scales on the control-plane `/api/export-jobs/pending-count` metrics-api trigger). Today the deployment ships `replicas: 1` so the worker polls permanently; setting `replicas: 0` enables scale-to-zero once KEDA is confirmed installed in the cluster.

---

### 3.3 wrapper-proxy

**Purpose:** Nginx-based request routing proxy that sits in front of ryugraph-wrapper and falkordb-wrapper pods. Routes graph API requests (`/wrapper/{slug}/*`) to the appropriate backend wrapper pod via dynamic DNS resolution through CoreDNS. Supports both static wrappers (always-running `falkordb-wrapper` and `ryugraph-wrapper` services) and dynamic per-analyst wrappers created by the control-plane.

**Key Endpoints:**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/healthz` | GET | Liveness and readiness probe |
| `/wrapper/falkordb/*` | ANY | Proxy to static falkordb-wrapper pod |
| `/wrapper/ryugraph/*` | ANY | Proxy to static ryugraph-wrapper pod |
| `/wrapper/{slug}/*` | ANY | Proxy to dynamic wrapper pod by instance slug |

**Dependencies:**

- **Upstream:** CoreDNS (resolves `wrapper-{slug}` ClusterIP services)
- **Downstream:** ryugraph-wrapper pods, falkordb-wrapper pods (all dynamic and static instances)

**Data Stores:** None. Fully stateless reverse proxy.

**Key Environment Variables:**

| Variable | Source | Purpose |
|----------|--------|---------|
| `POD_NAMESPACE` | Downward API (`metadata.namespace`) | Injected into nginx config for service DNS resolution |

**Resource Requirements:**

| Resource | Request | Limit |
|----------|---------|-------|
| CPU | 100m | 500m |
| Memory | 128Mi | 256Mi |

**Ports:** Container port 8080, Service port 80. Exposed externally via Ingress for instance API routing.

**Health Check:** `GET /healthz` on port 8080 returns HTTP 200. Liveness probe: initial delay 10s, period 10s. Readiness probe: initial delay 5s, period 5s.

**Restart Safety:** Fully stateless. Safe to restart at any time. In-flight proxied requests will fail; clients (SDK) retry automatically. Rolling updates use `maxUnavailable: 0` / `maxSurge: 1` so a new replica is brought up before the old one is retired; there is no wrapper-proxy PodDisruptionBudget (the only PDB in `infrastructure/cd/resources/` is `control-plane-pdb.yaml`).

**Scaling:** Fixed at 1 replica (no autoscaling). Resource footprint is minimal. Can be scaled horizontally if proxy throughput becomes a bottleneck.

---

### 3.4 ryugraph-wrapper

**Purpose:** Serves a single Ryugraph (KuzuDB fork) graph instance. Loads Parquet data from GCS on startup, provides Cypher query execution and NetworkX graph algorithm APIs.

**Key Endpoints:**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Liveness probe |
| `/ready` | GET | Readiness probe (data loaded) |
| `/api/query` | POST | Execute Cypher query |
| `/api/algorithms/*` | POST | Run graph algorithms (PageRank, etc.) |

**Dependencies:**

- **Upstream:** GCS (load Parquet on startup)
- **Downstream:** None (serves SDK/notebook queries directly)

**Data Stores:** Embedded KuzuDB (disk-backed buffer pool). Data loaded from GCS Parquet at startup.

**Key Environment Variables:**

| Variable | Source | Purpose |
|----------|--------|---------|
| `WRAPPER_TYPE` | Pod spec | `ryugraph` |
| `WRAPPER_SNAPSHOT_ID` | Pod spec | Snapshot to load |
| `WRAPPER_GCS_BASE_PATH` | Pod spec | GCS path for Parquet data |
| `BUFFER_POOL_SIZE` | Pod spec | KuzuDB buffer pool in bytes |

**Health Check:** `GET /health` returns HTTP 200 when process is alive. `GET /ready` returns HTTP 200 only after Parquet data is fully loaded.

**Restart Safety:** Pods are ephemeral. Data is loaded from GCS on every startup. Restarting a wrapper pod causes temporary unavailability for that graph instance. Users can re-query after the pod restarts and reloads data (typically 1--3 minutes).

**Scaling:** Not horizontally scalable -- one pod per graph instance by design. Vertical scaling via in-place resize (CPU: both directions; memory: increase only).

---

### 3.5 falkordb-wrapper

**Purpose:** Serves a single FalkorDB graph instance. In-memory only graph database. Provides Cypher query execution and native C-based graph algorithm APIs.

**Key Endpoints:** Same as ryugraph-wrapper (`/health`, `/ready`, `/api/query`, `/api/algorithms/*`).

**Dependencies:** Same as ryugraph-wrapper (GCS for data loading).

**Data Stores:** FalkorDB (in-memory, Redis-based). All data must fit in RAM. No disk caching.

**Key Environment Variables:**

| Variable | Source | Purpose |
|----------|--------|---------|
| `WRAPPER_TYPE` | Pod spec | `falkordb` |
| `WRAPPER_SNAPSHOT_ID` | Pod spec | Snapshot to load |
| `WRAPPER_GCS_BASE_PATH` | Pod spec | GCS path for Parquet data |

**Health Check:** Same as ryugraph-wrapper.

**Restart Safety:** Same as ryugraph-wrapper. Data is re-loaded from GCS on restart. In-memory state is lost on restart.

**Scaling:** Same as ryugraph-wrapper. FalkorDB typically requires 1.5x more memory than Ryugraph for the same dataset due to its in-memory-only architecture.

---

### 3.7 notebook-sync (not deployed to HSBC)

`notebook-sync` is not deployed to the HSBC target. It is an internal init-container used alongside JupyterHub in the Sparkling Ideas demo environment only. HSBC analysts run the SDK from corporate-issued notebooks via the VDI (ADR-108).

**Dependencies:** GitHub (clones notebooks via a PAT stored in the `git-sync-token` Kubernetes secret).

**Restart Safety:** Runs once per pod start. No persistent state. Re-runs automatically on pod restart.

---

### 3.8 documentation

**Purpose:** Starlight/AstroJS static documentation site. Serves the platform's user and operator documentation.

**Key Endpoints:**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET | Documentation site root |

**Dependencies:** None at runtime. Static files served by built-in HTTP server.

**Data Stores:** None. Static content baked into Docker image.

**Key Environment Variables:**

| Variable | Source | Purpose |
|----------|--------|---------|
| `PORT` | ConfigMap | HTTP listen port (default 8000) |

**Health Check:** `GET /` returns HTTP 200.

**Restart Safety:** Fully stateless. Safe to restart at any time with zero data loss.

**Scaling:** Single replica sufficient. Can scale horizontally if needed but load is minimal.

---

---

## 4. Infrastructure Dependencies

| Dependency | Type | Purpose | Failure Impact |
|------------|------|---------|----------------|
| Cloud SQL PostgreSQL | Managed database | All platform metadata | control-plane returns 503; no new instances/exports |
| GCS (bucket) | Object storage | Parquet snapshots, notebooks | Instance creation fails; exports fail; notebook sync fails |
| GKE API | Kubernetes API server | Wrapper pod lifecycle | Cannot create/delete graph instances |
| Workload Identity | IAM binding | Pod-to-GCP authentication | GCS and Cloud SQL access denied |
| Cloud NAT | Networking | Egress for Starburst Galaxy, container pulls | Exports fail; image pulls fail |
| cert-manager + HSBC-provided `ClusterIssuer` | TLS | HTTPS termination at ingress (HSBC internal PKI) | External API access fails |

---

## 5. External Dependencies

| Dependency | Type | Protocol | Purpose | Failure Impact |
|------------|------|----------|---------|----------------|
| Starburst Galaxy (managed Trino) | SaaS | HTTPS | Data source for exports and schema browsing | Exports fail; schema cache stale (serves cached data) |

> **Access control:** External access is fronted by the Azure AD auth proxy (ADR-137). The proxy terminates the user's Azure AD session and forwards the resolved identity to the control plane via the `X-Username` header.

---

## 6. Network Topology

### 6.1 Internal Communication

All service-to-service communication is via ClusterIP services within the `graph-olap-platform` namespace.

![network-topology](diagrams/service-catalogue-manual/network-topology.svg)

<details>
<summary>Mermaid Source</summary>

```mermaid
flowchart TD
    accTitle: Network Topology
    accDescr: External traffic routing through ingress to backend services

    classDef infra fill:#E3F2FD,stroke:#1565C0,stroke-width:2px,color:#0D47A1
    classDef service fill:#E8F5E9,stroke:#2E7D32,stroke-width:2px,color:#1B5E20
    classDef external fill:#ECEFF1,stroke:#455A64,stroke-width:2px,color:#263238

    INET([Internet]):::external --> ING[Ingress Controller<br/>nginx · TLS termination]:::infra

    ING --> CP[control-plane :8080]:::service
    ING --> DOCS[documentation :8000]:::service
    ING --> WPX[wrapper-proxy :80]:::service

    WPX -->|by instance ID| WPODS[Wrapper Pods :8000<br/>ClusterIP per pod]:::service
```

</details>

### 6.2 Ingress Routes

The HSBC handoff target is the GKE cluster `hsbc-12636856-udlhk-dev-vp2-cluster` in `asia-east2-b` (project `hsbc-12636856-udlhk-dev`). Hostnames are defined in `infrastructure/cd/resources/certificate.yaml` and `infrastructure/cd/resources/control-plane-ingress.yaml`.

| Host / Path | Backend | Notes |
|-------------|---------|-------|
| `control-plane-graph-olap-platform.hsbc-12636856-udlhk-dev.dev.gcp.cloud.hk.hsbc/*` | control-plane:8080 | API and admin (`gce-internal` ingress, self-signed TLS via cert-manager) |
| `control-plane-graph-olap-platform.hsbc-12636856-udlhk-dev.dev.gcp.cloud.hk.hsbc/wrapper/*` | nginx-wrapper-proxy:80 | Routed to wrapper pods (same ingress, path-based) |
| `graphdocs-graph-olap-platform.hsbc-12636856-udlhk-dev.dev.gcp.cloud.hk.hsbc/*` | documentation:8000 | IP-whitelisted |
| `wrappers-graph-olap-platform.hsbc-12636856-udlhk-dev.dev.gcp.cloud.hk.hsbc/*` | wrapper-proxy (direct) | Wildcard wrapper hostname (per-instance via DNS) |

> JupyterHub is not deployed to the HSBC target; analysts run the SDK from corporate-issued notebooks via the VDI (ADR-108). The wildcard cert in `infrastructure/cd/resources/certificate.yaml` covers `*.graph-olap-platform.hsbc-12636856-udlhk-dev.dev.gcp.cloud.hk.hsbc` for per-instance wrapper DNS.

### 6.3 Pod-to-Pod Encryption

Internal traffic is encrypted with WireGuard (ChaCha20-Poly1305) via Cilium Transparent Encryption on GKE Dataplane V2. No application-level TLS is needed for in-cluster communication.

---

## 7. Port Map

| Service | Container Port | Service Port | Protocol | Exposed Via |
|---------|---------------|--------------|----------|-------------|
| control-plane | 8080 | 8080 | HTTP | Ingress |
| control-plane (metrics) | 9090 | 9090 | HTTP | PodMonitoring |
| export-worker | -- | -- | -- | None (outbound only) |
| ryugraph-wrapper | 8000 | 8000 | HTTP | ClusterIP + wrapper-proxy |
| falkordb-wrapper | 8000 | 8000 | HTTP | ClusterIP + wrapper-proxy |
| wrapper-proxy | 8080 | 80 | HTTP | Ingress |
| documentation | 8000 | 8000 | HTTP | Ingress |
| Cloud SQL | 5432 | -- | PostgreSQL | Private IP |

---

## 8. Configuration Reference

### 8.1 Shared Configuration (All Services)

| Variable | Purpose | Default |
|----------|---------|---------|
| `LOG_LEVEL` | Logging verbosity | `INFO` |
| `LOG_FORMAT` | Log output format | `json` |
| `ENVIRONMENT` | Environment name | `production` |
| `GCP_PROJECT` | GCP project ID | -- (required) |

### 8.2 Control-Plane Configuration

| Variable | Purpose | Default |
|----------|---------|---------|
| `DATABASE_URL` | PostgreSQL connection string | -- (required, from Secret) |
| `DB_POOL_SIZE` | SQLAlchemy pool size | `25` |
| `DB_MAX_OVERFLOW` | Pool overflow connections | `5` |
| `GCS_BUCKET` | GCS bucket for snapshots | -- (required) |
| `K8S_NAMESPACE` | Namespace for wrapper pods | Release namespace |
| `K8S_IN_CLUSTER` | Use in-cluster K8s config | `true` |
| `WRAPPER_IMAGE` | Ryugraph Docker image:tag | -- (required) |
| `FALKORDB_WRAPPER_IMAGE` | FalkorDB Docker image:tag | -- (required) |
| `WRAPPER_SERVICE_ACCOUNT` | K8s SA for wrapper pods | `graph-wrapper` |
| `EXTERNAL_BASE_URL` | Public API URL for SDK | -- (required) |
| `STARBURST_URL` | Starburst Galaxy endpoint | -- (required) |
| `STARBURST_USER` | Starburst Galaxy service account | -- (required) |
| `RECONCILIATION_JOB_INTERVAL_SECONDS` | Instance reconciliation job interval | `30` |
| `LIFECYCLE_JOB_INTERVAL_SECONDS` | TTL/cleanup job interval | `30` |
| `SCHEMA_CACHE_JOB_INTERVAL_SECONDS` | Starburst Galaxy schema cache refresh | `300` |
| `CONCURRENCY_PER_ANALYST` | Max instances per user | `10` |
| `CONCURRENCY_CLUSTER_TOTAL` | Max instances cluster-wide | `50` |

### 8.3 Export-Worker Configuration

| Variable | Purpose | Default |
|----------|---------|---------|
| `CONTROL_PLANE_URL` | Internal API endpoint | `http://control-plane:8080` |
| `STARBURST_URL` | Starburst Galaxy endpoint | -- (required) |
| `STARBURST_USER` | Starburst Galaxy service account | -- (required) |
| `STARBURST_PASSWORD` | Starburst Galaxy password | -- (from Secret) |
| `POLL_INTERVAL_SECONDS` | Main loop polling interval | `5` |
| `EMPTY_POLL_BACKOFF_SECONDS` | Backoff when no jobs found | `10` |
| `CLAIM_LIMIT` | Max jobs claimed per cycle | `10` |
| `POLL_LIMIT` | Max queries polled per cycle | `10` |
| `STARBURST_REQUEST_TIMEOUT_SECONDS` | Starburst Galaxy API timeout | `30` |
| `STARBURST_CLIENT_TAGS` | Client identification tags | `graph-olap-export` |

### 8.4 Wrapper Pod Configuration

| Variable | Purpose | Default |
|----------|---------|---------|
| `WRAPPER_TYPE` | `ryugraph` or `falkordb` | Set by control-plane |
| `WRAPPER_SNAPSHOT_ID` | Snapshot to load from GCS | Set by control-plane |
| `WRAPPER_GCS_BASE_PATH` | Full GCS path for Parquet data | Set by control-plane |
| `WRAPPER_INSTANCE_ID` | Instance identifier | Set by control-plane |
| `WRAPPER_URL_SLUG` | URL path segment for proxy routing | Set by control-plane |
| `WRAPPER_MAPPING_ID` | Source mapping identifier | Set by control-plane |
| `WRAPPER_CONTROL_PLANE_URL` | Control-plane URL for status callbacks | Set by control-plane |
| `WRAPPER_INSTANCE_URL` | External URL of this instance | Set by control-plane |
| `BUFFER_POOL_SIZE` | KuzuDB buffer pool (ryugraph only) | `1073741824` (1 GB) |
| `RYUGRAPH_DATABASE_PATH` | KuzuDB data directory (ryugraph only) | Set by control-plane |
| `FALKORDB_DATABASE_PATH` | FalkorDB data directory (falkordb only) | Set by control-plane |

### 8.5 Secrets

| Secret Name | Keys | Used By |
|-------------|------|---------|
| `control-plane-secrets` | `database-url` | control-plane |
| `export-worker-secrets` | `STARBURST_PASSWORD` | export-worker |
| `starburst-credentials` | `password` | control-plane (schema cache) |

> Internal traffic between export-worker and control-plane is isolated by NetworkPolicy rather than a shared secret.

All secrets are managed via Google Secret Manager with External Secrets Operator syncing to Kubernetes Secrets.

---

## 9. Background Jobs

The control-plane runs these six background jobs via APScheduler (in-process, not separate pods):

| Job | Interval | Purpose | Manually Triggerable |
|-----|----------|---------|---------------------|
| Instance Orchestration | 5 seconds | Process pending instance operations | No |
| Instance Reconciliation | 30 seconds | Sync pod state with database records | Yes (`trigger_job("reconciliation")`) |
| Export Reconciliation | 5 seconds | Reset stale export claims, finalize jobs (deliberate exception to ADR-040; near-real-time propagation required) | Yes (`trigger_job("export_reconciliation")`) |
| Lifecycle Cleanup | 30 seconds | Enforce TTL, clean up orphaned resources | Yes (`trigger_job("lifecycle")`) |
| Schema Cache Refresh | 5 minutes | Update Starburst Galaxy metadata cache | Yes (`trigger_job("schema_cache")`) |
| Resource Monitor | 60 seconds | Monitor wrapper pod memory usage; trigger proactive resize if `sizing_enabled=true` | No |

---

## 10. Service Startup Order

Services must start in this order (init containers enforce this automatically):

![service-startup-order](diagrams/service-catalogue-manual/service-startup-order.svg)

<details>
<summary>Mermaid Source</summary>

```mermaid
flowchart TD
    accTitle: Service Startup Order
    accDescr: Strict boot dependencies and independently startable services

    classDef data fill:#FFF8E1,stroke:#F57F17,stroke-width:2px,color:#E65100
    classDef service fill:#E8F5E9,stroke:#2E7D32,stroke-width:2px,color:#1B5E20
    classDef independent fill:#E3F2FD,stroke:#1565C0,stroke-width:2px,color:#0D47A1

    subgraph ordered ["Strict Order (init containers enforce)"]
        SQL[(Cloud SQL)]:::data -->|waitForPostgres| CP[control-plane]:::service
        CP -->|waitForDeps| EW[export-worker]:::service
    end

    subgraph parallel ["Independent (can start in any order)"]
        WPX[wrapper-proxy]:::independent
        DOCS[documentation]:::independent
    end
```

</details>

1. **Cloud SQL** -- must be available (init container: `waitForPostgres`)
2. **control-plane** -- starts and runs database migrations
3. **export-worker** -- waits for control-plane (init container: `waitForDeps`)
4. **wrapper-proxy** -- stateless, can start in any order
5. **documentation** -- independent, no dependencies

Wrapper pods are created dynamically by the control-plane and are not part of the startup sequence.

---

## Related Documents

- [Detailed Architecture](--/architecture/detailed-architecture.md) -- C4 diagrams, container decomposition
- [Platform Operations Architecture](--/architecture/platform-operations.md) -- technology stack, SLOs, background jobs, observability
- [Capacity Planning Guide](capacity-planning.manual.md) -- resource allocation and sizing formulas
- [ADR-134: Service Catalogue](--/process/adr/operations/adr-134-service-catalogue.md)
