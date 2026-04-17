---
title: "Configuration Reference"
scope: hsbc
---

# Configuration Reference

All configurable parameters for the Graph OLAP Platform, their default values, and where to change them.

---

## Control Plane (`GRAPH_OLAP_` prefix)

All control-plane environment variables use the `GRAPH_OLAP_` prefix. Set them in the Kubernetes ConfigMap or Deployment manifest.

### Server

| Parameter | Env Var | Default | Description |
|---|---|---|---|
| `host` | `GRAPH_OLAP_HOST` | `0.0.0.0` | Listen address |
| `port` | `GRAPH_OLAP_PORT` | `8080` | Listen port |
| `debug` | `GRAPH_OLAP_DEBUG` | `false` | Enable debug mode |
| `shutdown_timeout_seconds` | `GRAPH_OLAP_SHUTDOWN_TIMEOUT_SECONDS` | `30` | Graceful shutdown timeout |

### Database (PostgreSQL)

| Parameter | Env Var | Default | Description |
|---|---|---|---|
| `database_url` | `GRAPH_OLAP_DATABASE_URL` | *(required)* | PostgreSQL connection string (`postgresql+asyncpg://user:pass@host:port/dbname`) |
| `db_pool_size` | `GRAPH_OLAP_DB_POOL_SIZE` | `25` | Connection pool size |
| `db_max_overflow` | `GRAPH_OLAP_DB_MAX_OVERFLOW` | `5` | Max overflow connections |
| `db_echo` | `GRAPH_OLAP_DB_ECHO` | `false` | Log SQL queries |

### Kubernetes

| Parameter | Env Var | Default | Description |
|---|---|---|---|
| `k8s_namespace` | `GRAPH_OLAP_K8S_NAMESPACE` | `graph-instances` | Namespace for wrapper pods |
| `k8s_in_cluster` | `GRAPH_OLAP_K8S_IN_CLUSTER` | `true` | Use in-cluster K8s config |
| `wrapper_image` | `GRAPH_OLAP_WRAPPER_IMAGE` | `ryugraph-wrapper:dev` | RyuGraph wrapper image (must include tag) |
| `falkordb_wrapper_image` | `GRAPH_OLAP_FALKORDB_WRAPPER_IMAGE` | `falkordb-wrapper:dev` | FalkorDB wrapper image (must include tag) |
| `wrapper_image_pull_policy` | `GRAPH_OLAP_WRAPPER_IMAGE_PULL_POLICY` | `IfNotPresent` | `IfNotPresent`, `Always`, or `Never` |
| `storage_class` | `GRAPH_OLAP_STORAGE_CLASS` | `standard` | K8s StorageClass for PVCs |
| `wrapper_service_account` | `GRAPH_OLAP_WRAPPER_SERVICE_ACCOUNT` | *(empty)* | K8s service account for wrapper pods (for Workload Identity) |
| `wrapper_gcp_secret` | `GRAPH_OLAP_WRAPPER_GCP_SECRET` | *(empty)* | K8s secret containing GCP credentials (alternative to Workload Identity) |
| `wrapper_external_base_url` | `GRAPH_OLAP_WRAPPER_EXTERNAL_BASE_URL` | *(empty)* | Base URL for external wrapper access via Ingress |

### Wrapper Resource Sizing

| Parameter | Env Var | Default | Description |
|---|---|---|---|
| `ryugraph_memory_request` | `GRAPH_OLAP_RYUGRAPH_MEMORY_REQUEST` | `2Gi` | Memory request for RyuGraph wrappers |
| `ryugraph_memory_limit` | `GRAPH_OLAP_RYUGRAPH_MEMORY_LIMIT` | `4Gi` | Memory limit for RyuGraph wrappers |
| `ryugraph_cpu_request` | `GRAPH_OLAP_RYUGRAPH_CPU_REQUEST` | `1` | CPU request for RyuGraph wrappers |
| `ryugraph_cpu_limit` | `GRAPH_OLAP_RYUGRAPH_CPU_LIMIT` | `2` | CPU limit for RyuGraph wrappers |
| `ryugraph_buffer_pool_size` | `GRAPH_OLAP_RYUGRAPH_BUFFER_POOL_SIZE` | `1073741824` (1 GB) | RyuGraph buffer pool size in bytes |
| `falkordb_memory_request` | `GRAPH_OLAP_FALKORDB_MEMORY_REQUEST` | `2Gi` | Memory request for FalkorDB wrappers |
| `falkordb_memory_limit` | `GRAPH_OLAP_FALKORDB_MEMORY_LIMIT` | `4Gi` | Memory limit for FalkorDB wrappers |
| `falkordb_cpu_request` | `GRAPH_OLAP_FALKORDB_CPU_REQUEST` | `1` | CPU request for FalkorDB wrappers |
| `falkordb_cpu_limit` | `GRAPH_OLAP_FALKORDB_CPU_LIMIT` | `2` | CPU limit for FalkorDB wrappers |

### Dynamic Resource Sizing

| Parameter | Env Var | Default | Description |
|---|---|---|---|
| `sizing_enabled` | `GRAPH_OLAP_SIZING_ENABLED` | `true` | Auto-calculate memory/disk from snapshot size |
| `sizing_falkordb_memory_multiplier` | `GRAPH_OLAP_SIZING_FALKORDB_MEMORY_MULTIPLIER` | `2.0` | `parquet_size * multiplier` for in-memory graph |
| `sizing_ryugraph_memory_multiplier` | `GRAPH_OLAP_SIZING_RYUGRAPH_MEMORY_MULTIPLIER` | `1.2` | `parquet_size * multiplier` for disk-based graph |
| `sizing_memory_headroom` | `GRAPH_OLAP_SIZING_MEMORY_HEADROOM` | `1.5` | Additional headroom multiplier |
| `sizing_min_memory_gb` | `GRAPH_OLAP_SIZING_MIN_MEMORY_GB` | `2.0` | Minimum memory per wrapper (GB) |
| `sizing_max_memory_gb` | `GRAPH_OLAP_SIZING_MAX_MEMORY_GB` | `32.0` | Maximum memory per wrapper (GB) |
| `sizing_disk_multiplier` | `GRAPH_OLAP_SIZING_DISK_MULTIPLIER` | `1.2` | PVC size = `parquet_size * multiplier` |
| `sizing_min_disk_gb` | `GRAPH_OLAP_SIZING_MIN_DISK_GB` | `10` | Minimum PVC size (GB) |
| `sizing_per_user_max_memory_gb` | `GRAPH_OLAP_SIZING_PER_USER_MAX_MEMORY_GB` | `64.0` | Max total memory across all instances per user |
| `sizing_cluster_memory_soft_limit_gb` | `GRAPH_OLAP_SIZING_CLUSTER_MEMORY_SOFT_LIMIT_GB` | `256.0` | Warn/block when cluster total exceeds this |
| `sizing_max_resize_steps` | `GRAPH_OLAP_SIZING_MAX_RESIZE_STEPS` | `3` | Max auto-upgrades per instance |
| `sizing_resize_cooldown_seconds` | `GRAPH_OLAP_SIZING_RESIZE_COOLDOWN_SECONDS` | `300` | Minimum time between resizes |
| `sizing_default_cpu_cores` | `GRAPH_OLAP_SIZING_DEFAULT_CPU_CORES` | `1` | Default CPU cores (request=N, limit=N*2) |

### Concurrency Limits

| Parameter | Env Var | Default | Description |
|---|---|---|---|
| `concurrency_per_analyst` | `GRAPH_OLAP_CONCURRENCY_PER_ANALYST` | `10` | Max instances per analyst |
| `concurrency_cluster_total` | `GRAPH_OLAP_CONCURRENCY_CLUSTER_TOTAL` | `50` | Max instances cluster-wide |

These values are seeded to the `global_config` database table on startup. Once seeded, they can be changed at runtime via the `/api/ops/config` endpoint without restarting the control-plane.

### Starburst Connection

| Parameter | Env Var | Default | Description |
|---|---|---|---|
| `starburst_url` | `GRAPH_OLAP_STARBURST_URL` | *(empty)* | Starburst REST API URL |
| `starburst_catalog` | `GRAPH_OLAP_STARBURST_CATALOG` | `bigquery` | Default catalog |
| `starburst_user` | `GRAPH_OLAP_STARBURST_USER` | `admin` | Starburst username |
| `starburst_password` | `GRAPH_OLAP_STARBURST_PASSWORD` | *(required)* | Starburst password |
| `starburst_timeout_seconds` | `GRAPH_OLAP_STARBURST_TIMEOUT_SECONDS` | `60` | HTTP request timeout |
| `starburst_role` | `GRAPH_OLAP_STARBURST_ROLE` | *(empty)* | Use case ID for `SET ROLE` |

### GCS (Google Cloud Storage)

| Parameter | Env Var | Default | Description |
|---|---|---|---|
| `gcp_project` | `GRAPH_OLAP_GCP_PROJECT` | *(empty)* | GCP project ID |
| `gcs_bucket` | `GRAPH_OLAP_GCS_BUCKET` | *(empty)* | GCS bucket name for snapshot exports |

### Background Job Intervals

| Parameter | Env Var | Default | Description |
|---|---|---|---|
| `reconciliation_job_interval_seconds` | `GRAPH_OLAP_RECONCILIATION_JOB_INTERVAL_SECONDS` | `300` (5 min) | Orphan pod cleanup and state drift detection |
| `lifecycle_job_interval_seconds` | `GRAPH_OLAP_LIFECYCLE_JOB_INTERVAL_SECONDS` | `300` (5 min) | TTL and inactivity timeout enforcement |
| `instance_orchestration_job_interval_seconds` | `GRAPH_OLAP_INSTANCE_ORCHESTRATION_JOB_INTERVAL_SECONDS` | `5` | `waiting_for_snapshot` to `starting` transitions |
| `schema_cache_job_interval_seconds` | `GRAPH_OLAP_SCHEMA_CACHE_JOB_INTERVAL_SECONDS` | `86400` (24h) | Starburst metadata cache refresh |

The export reconciliation job runs every 5 seconds (hardcoded) and the resource monitor runs every 60 seconds (hardcoded). These are not configurable via environment variables.

**Cost note:** The `instance_orchestration_job_interval_seconds` default of 5 seconds is aggressive. If you are not creating instances frequently, increase it to 30 seconds or more to reduce database polling load:

```bash
GRAPH_OLAP_INSTANCE_ORCHESTRATION_JOB_INTERVAL_SECONDS=30
```

Similarly, reconciliation and lifecycle can safely run at 300s (5 min) intervals for most workloads.

---

## Export Worker

The export worker uses three separate config prefixes.

### Starburst (`STARBURST_` prefix)

| Parameter | Env Var | Default | Description |
|---|---|---|---|
| `url` | `STARBURST_URL` | *(required)* | Starburst REST API URL |
| `user` | `STARBURST_USER` | *(required)* | Starburst username |
| `password` | `STARBURST_PASSWORD` | *(optional)* | Starburst password (omit for header-only auth) |
| `catalog` | `STARBURST_CATALOG` | `bigquery` | Default catalog |
| `schema_name` | `STARBURST_SCHEMA` | `public` | Default schema |
| `request_timeout_seconds` | `STARBURST_REQUEST_TIMEOUT_SECONDS` | `60` | HTTP request timeout |
| `client_tags` | `STARBURST_CLIENT_TAGS` | `graph-olap-export` | Resource group routing tags |
| `source` | `STARBURST_SOURCE` | `graph-olap-export-worker` | Source identifier |
| `ssl_verify` | `STARBURST_SSL_VERIFY` | `true` | Verify SSL certificates |

### GCS (`GCS_` prefix)

| Parameter | Env Var | Default | Description |
|---|---|---|---|
| `project` | `GCP_PROJECT` | *(required)* | GCP project ID |
| `emulator_host` | `STORAGE_EMULATOR_HOST` | *(empty)* | GCS emulator endpoint (testing only) |

### Control Plane (`CONTROL_PLANE_` prefix)

| Parameter | Env Var | Default | Description |
|---|---|---|---|
| `url` | `CONTROL_PLANE_URL` | *(required)* | Control Plane internal API URL |
| `timeout_seconds` | `CONTROL_PLANE_TIMEOUT_SECONDS` | `30` | Request timeout |
| `max_retries` | `CONTROL_PLANE_MAX_RETRIES` | `5` | Max retry attempts |

### Worker Loop

| Parameter | Env Var | Default | Description |
|---|---|---|---|
| `poll_interval_seconds` | `POLL_INTERVAL_SECONDS` | `5` | Main loop interval when work is found |
| `empty_poll_backoff_seconds` | `EMPTY_POLL_BACKOFF_SECONDS` | `10` | Backoff when no work found |
| `claim_limit` | `CLAIM_LIMIT` | `10` | Max jobs to claim per cycle |
| `poll_limit` | `POLL_LIMIT` | `10` | Max jobs to poll per cycle |
| `direct_export` | `DIRECT_EXPORT` | `true` | Use PyArrow export instead of `system.unload` |

---

## Runtime Configuration (Database)

Some parameters are stored in the `global_config` database table and can be changed at runtime via the `/api/ops/config` endpoint without restarting the control-plane.

### Reading Current Config

```bash
curl -s https://<CONTROL_PLANE_URL>/api/ops/config \
  -H "X-Username: ops-user" | jq
```

### Updating Config

```bash
curl -s -X PUT https://<CONTROL_PLANE_URL>/api/ops/config \
  -H "X-Username: ops-user" \
  -H "Content-Type: application/json" \
  -d '{"key": "snapshot_ttl_hours", "value": "168"}'
```

### Available Runtime Config Keys

| Key | Default | Description |
|---|---|---|
| `snapshot_ttl_hours` | `720` (30 days) | Time before expired snapshots are cleaned up |
| `instance_inactivity_timeout_minutes` | `60` | Auto-terminate instances after this idle time |
| `max_instances_per_user` | `10` | Max concurrent instances per analyst |
| `max_instances_cluster` | `50` | Max concurrent instances cluster-wide |
| `max_export_retries` | `3` | Max retry attempts for failed exports |
| `export_timeout_minutes` | `120` | Max time for a single export job |

---

## GCS Bucket Permissions

The control-plane service account requires the following IAM permissions on the GCS bucket used for snapshot exports:

| Permission | Used By | Purpose |
|---|---|---|
| `storage.objects.list` | Control Plane | List objects under a snapshot prefix |
| `storage.objects.delete` | Control Plane | Delete snapshot data when TTL expires or snapshot is deleted |
| `storage.objects.get` | Export Worker | Verify export completion |
| `storage.objects.create` | Export Worker | Write Parquet files during export |
| `storage.buckets.get` | Both | Verify bucket exists |

The simplest approach is to grant `roles/storage.objectAdmin` on the specific bucket to the GKE Workload Identity service account.

### Diagnosing GCS Permission Failures

If the control-plane cannot delete GCS objects, it logs `build_gcs_client_failed` or `cascade_snapshot_gcs_delete_skipped_no_client` and proceeds with the database deletion only. GCS objects become orphaned.

To check:

```bash
# Verify Workload Identity binding
gcloud iam service-accounts get-iam-policy <GSA>@<PROJECT>.iam.gserviceaccount.com

# Verify bucket IAM
gsutil iam get gs://<BUCKET_NAME>

# Test GCS access from the pod
kubectl exec -it deploy/control-plane -n graph-olap-platform -- \
  python3 -c "from google.cloud import storage; c=storage.Client(); print(list(c.list_blobs('<BUCKET>', max_results=1)))"
```

If GCS cleanup is broken, set a bucket lifecycle rule as a backstop:

```bash
gsutil lifecycle set lifecycle.json gs://<BUCKET_NAME>
```

Where `lifecycle.json` deletes objects older than 90 days.

---

## RyuGraph Wrapper (`WRAPPER_` / `RYUGRAPH_` prefix)

These are set by the control-plane when spawning wrapper pods. Operators may need to override resource-related values.

| Env Var | Default | Description |
|---|---|---|
| `WRAPPER_HOST` | `0.0.0.0` | Server bind address |
| `WRAPPER_PORT` | `8000` | Server bind port |
| `WRAPPER_CONTROL_PLANE_URL` | *(set at spawn)* | Control plane internal URL |
| `WRAPPER_CONTROL_PLANE_TIMEOUT` | `30.0` | HTTP timeout to control plane |
| `WRAPPER_GCS_BASE_PATH` | *(set at spawn)* | GCS path to snapshot Parquet files |
| `RYUGRAPH_DATABASE_PATH` | `/data/ryugraph` | Database directory path |
| `RYUGRAPH_BUFFER_POOL_SIZE` | `2147483648` (2 GB) | Buffer pool in bytes (minimum 128 MB) |
| `RYUGRAPH_MAX_THREADS` | `16` | Max threads for parallel I/O (1-64) |
| `RYUGRAPH_QUERY_TIMEOUT_MS` | `60000` (60s) | Per-query timeout |
| `RYUGRAPH_ALGORITHM_TIMEOUT_MS` | `1800000` (30 min) | Algorithm execution timeout |
| `METRICS_REPORT_INTERVAL_SECONDS` | `60` | How often metrics are reported to control plane |
| `METRICS_ENABLED` | `true` | Enable metrics reporting |

## FalkorDB Wrapper

Same `WRAPPER_*` and `METRICS_*` variables as RyuGraph. FalkorDB-specific:

| Env Var | Default | Description |
|---|---|---|
| `FALKORDB_DATABASE_PATH` | `/data/db` | Database directory path |
| `FALKORDB_QUERY_TIMEOUT_MS` | `60000` (60s) | Per-query timeout |
| `FALKORDB_ALGORITHM_TIMEOUT_MS` | `1800000` (30 min) | Algorithm execution timeout |

## SDK (`GRAPH_OLAP_` prefix)

Environment variables used by the Python SDK in Jupyter notebooks.

| Env Var | Default | Description |
|---|---|---|
| `GRAPH_OLAP_API_URL` | *(required)* | Control plane API base URL |
| `GRAPH_OLAP_USERNAME` | *(required)* | Username sent as `X-Username` header |
| `GRAPH_OLAP_USE_CASE_ID` | `e2e_test_role` | Use-case ID sent as `X-Use-Case-Id` |
| `GRAPH_OLAP_PROXY` | *(empty)* | HTTP proxy URL |
| `GRAPH_OLAP_SSL_VERIFY` | `true` | Verify SSL certificates |

---

## Runtime Configuration (Database `global_config`)

These values are stored in PostgreSQL and can be changed at runtime via the `/api/ops/config` or `/api/config/*` endpoints without restarting the control-plane. They take effect on the next background job run.

### Lifecycle TTL Defaults

| Key | Default | Description |
|---|---|---|
| `lifecycle.mapping.default_ttl` | *(null — no expiry)* | Default TTL for new mappings (ISO 8601 duration) |
| `lifecycle.mapping.default_inactivity` | `P30D` | Default inactivity timeout for mappings |
| `lifecycle.mapping.max_ttl` | `P365D` | Maximum allowed TTL for mappings |
| `lifecycle.snapshot.default_ttl` | `P7D` | Default TTL for new snapshots |
| `lifecycle.snapshot.default_inactivity` | `P3D` | Default inactivity timeout for snapshots |
| `lifecycle.snapshot.max_ttl` | `P30D` | Maximum allowed TTL for snapshots |
| `lifecycle.instance.default_ttl` | `PT24H` | Default TTL for new instances |
| `lifecycle.instance.default_inactivity` | `PT4H` | Default inactivity timeout for instances |
| `lifecycle.instance.max_ttl` | `P7D` | Maximum allowed TTL for instances |

### Concurrency

| Key | Default | Description |
|---|---|---|
| `concurrency.per_analyst` | `5` (seeded from env; env default is `10`) | Max simultaneous running instances per analyst |
| `concurrency.cluster_total` | `50` | Max simultaneous running instances cluster-wide |

### Maintenance Mode

| Key | Default | Description |
|---|---|---|
| `maintenance.enabled` | `0` | Maintenance mode toggle (`0`/`1`) |
| `maintenance.message` | `System is under maintenance` | Message displayed during maintenance |

### Export

| Key | Default | Description |
|---|---|---|
| `export.max_duration_seconds` | `3600` (1 hour) | Maximum export job duration before timeout |

### Reading and Updating Config

```bash
# Read all lifecycle config
curl -s https://<CP_URL>/api/ops/config -H "X-Username: ops-user" | jq

# Update snapshot TTL to 30 days
curl -s -X PUT https://<CP_URL>/api/config/lifecycle \
  -H "X-Username: ops-user" \
  -H "Content-Type: application/json" \
  -d '{"lifecycle.snapshot.default_ttl": "P30D"}'

# Update concurrency limits
curl -s -X PUT https://<CP_URL>/api/config/concurrency \
  -H "X-Username: ops-user" \
  -H "Content-Type: application/json" \
  -d '{"concurrency.per_analyst": 5, "concurrency.cluster_total": 50}'
```
