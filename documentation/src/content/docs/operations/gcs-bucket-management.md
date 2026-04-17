---
title: "GCS Bucket Management"
scope: demo
---

# GCS Bucket Management

This document covers monitoring, troubleshooting, and lifecycle configuration for the GCS export bucket used by the Graph OLAP Platform.

The platform stores Parquet snapshot data in GCS. When graphs are terminated and snapshots deleted, the control-plane cascades the delete to GCS. If this fails (permissions, credential issues), data accumulates. A bucket lifecycle rule acts as a backstop to ensure orphaned data is eventually cleaned up.

---

## How Snapshot Data Gets Into GCS

1. User creates an instance from a mapping
2. Export worker queries Starburst and writes Parquet files to `gs://<BUCKET>/<username>/<mapping_id>/v<version>/<snapshot_id>/`
3. Each node type and edge type gets its own subfolder with one or more `.parquet` files
4. The wrapper pod downloads these files on startup to load the graph

## How Snapshot Data Gets Cleaned Up

There are two cleanup paths:

**Path 1 — Cascade delete (primary):** When an instance is deleted (manually or by lifecycle job), the control-plane checks if any other instances reference the same snapshot. If none remain, it calls `GCSClient.delete_path()` to delete all objects under the snapshot's GCS prefix, then deletes the database row.

**Path 2 — Bucket lifecycle rule (backstop):** A GCS lifecycle rule automatically deletes objects older than a configured age, regardless of whether the application cleaned them up. This catches orphaned data from failed deletes.

---

## Checking Logs for GCS Failures

### Log Events to Search For

| Log Event | Meaning | Severity |
|---|---|---|
| `build_gcs_client_failed` | GCS client could not be constructed (credential/config failure). ALL GCS cleanup is disabled until this is resolved. | Critical |
| `cascade_snapshot_gcs_delete_skipped_no_client` | Cascade delete skipped GCS cleanup because the client is `None`. DB row was still deleted. | High |
| `lifecycle_snapshot_gcs_delete_skipped_no_client` | TTL lifecycle job skipped GCS cleanup because the client is `None`. DB row was still deleted. | High |
| `cascade_snapshot_gcs_delete_failed` | Cascade delete attempted GCS cleanup but it failed (permissions, network). DB row was still deleted. | High |
| `lifecycle_snapshot_gcs_deletion_failed` | TTL lifecycle job attempted GCS cleanup but it failed. DB row was still deleted. | High |
| `Deleted GCS path` | Successful cleanup — files were deleted. | Info |

### Querying Logs

**Cloud Logging (GCP Console):**

```
resource.type="k8s_container"
resource.labels.namespace_name="graph-olap-platform"
resource.labels.container_name="control-plane"
jsonPayload.event="build_gcs_client_failed"
```

Replace `event` with any of the log events above.

**kubectl:**

```bash
# Check for GCS client failures
kubectl logs deploy/control-plane -n graph-olap-platform --since=24h | \
  grep -E "build_gcs_client_failed|gcs_delete_skipped|gcs_delete_failed|gcs_deletion_failed"

# Check for successful cleanups
kubectl logs deploy/control-plane -n graph-olap-platform --since=24h | \
  grep "Deleted GCS path"
```

**Prometheus metrics:**

```promql
# Count of failed GCS cleanups (should be 0)
snapshot_gcs_cleanup_failures_total

# Check if the GCS client is healthy (1 = ok, 0 = broken)
# This is visible via the job health status for the lifecycle job
job_health_status{job_name="lifecycle"}
```

### What Each Failure Means

**`build_gcs_client_failed`** — This is the root cause. If you see this, no GCS cleanup will happen until it's fixed. Common causes:

1. `GRAPH_OLAP_GCS_BUCKET` or `GRAPH_OLAP_GCP_PROJECT` environment variables are empty
2. Workload Identity is not configured — the K8s service account is not bound to a GCP service account
3. The GCP service account does not have `roles/storage.objectAdmin` on the bucket
4. The GKE metadata server is unreachable from the pod

To diagnose:

```bash
# Check if env vars are set
kubectl exec deploy/control-plane -n graph-olap-platform -- \
  env | grep -E "GCS_BUCKET|GCP_PROJECT"

# Test GCS access from the pod
kubectl exec deploy/control-plane -n graph-olap-platform -- \
  python3 -c "
from google.cloud import storage
c = storage.Client()
bucket = c.bucket('<BUCKET_NAME>')
print('Bucket exists:', bucket.exists())
blobs = list(c.list_blobs('<BUCKET_NAME>', max_results=3))
print('Sample objects:', [b.name for b in blobs])
"

# Check Workload Identity binding
kubectl get serviceaccount control-plane -n graph-olap-platform -o yaml | \
  grep "iam.gke.io/gcp-service-account"
```

**`cascade_snapshot_gcs_delete_skipped_no_client` / `lifecycle_snapshot_gcs_delete_skipped_no_client`** — The GCS client is `None` (see `build_gcs_client_failed` above). The database row was deleted but GCS objects remain orphaned.

**`cascade_snapshot_gcs_delete_failed` / `lifecycle_snapshot_gcs_deletion_failed`** — The GCS client exists but the delete operation failed. Usually a 403 Forbidden (missing `storage.objects.delete` permission) or a network error. Check the error message in the log for details.

---

## Checking If Bucket Cleanup Is Working

### Quick Health Check

```bash
# 1. Count objects in the bucket grouped by age
gsutil ls -l gs://<BUCKET_NAME>/** | \
  awk '{print $2}' | \
  cut -d'T' -f1 | \
  sort | uniq -c | sort -rn | head -20

# 2. Check for objects older than the max expected age (e.g., 30 days)
gsutil ls -l gs://<BUCKET_NAME>/** | \
  awk -v cutoff="$(date -u -v-30d +%Y-%m-%d 2>/dev/null || date -u -d '30 days ago' +%Y-%m-%d)" \
  '$2 < cutoff {print $2, $3}'

# 3. Count total objects and size
gsutil du -s gs://<BUCKET_NAME>
```

### Verify a Specific Snapshot Was Cleaned Up

After deleting an instance, verify the GCS data was removed:

```bash
# Find the snapshot's GCS path from the database
kubectl exec deploy/control-plane -n graph-olap-platform -- \
  python3 -c "
# Query for recent deleted snapshots that had GCS paths
import asyncio
from control_plane.config import get_settings
# ... or check the control-plane logs for the gcs_path
"

# Check if the GCS path still has objects
gsutil ls gs://<BUCKET_NAME>/<username>/<mapping_id>/
```

If objects remain after deletion, the cascade delete failed. Check logs for the error.

### Ongoing Monitoring

Set up a Cloud Monitoring alert for bucket size growth:

```yaml
# Alert if bucket size grows by more than 10GB in 24 hours
displayName: "GCS Export Bucket Size Growing"
conditions:
  - conditionThreshold:
      filter: >
        resource.type = "gcs_bucket"
        AND resource.labels.bucket_name = "<BUCKET_NAME>"
        AND metric.type = "storage.googleapis.com/storage/total_bytes"
      comparison: COMPARISON_GT
      thresholdValue: 10737418240  # 10GB
      duration: 86400s  # 24 hours
      aggregations:
        - alignmentPeriod: 3600s
          perSeriesAligner: ALIGN_DELTA
```

---

## Setting Bucket Lifecycle Rules (TTL Backstop)

The bucket lifecycle rule automatically deletes objects older than a specified age. This is the backstop for when application-level cleanup fails.

### Setting the Rule

**Recommended TTL:** Match the maximum snapshot TTL configured in the platform. The default `lifecycle.snapshot.max_ttl` is `P30D` (30 days), so set the bucket lifecycle to 30 days (or slightly longer to avoid racing with the application).

**Using gsutil:**

```bash
# Create a lifecycle configuration file
cat > /tmp/lifecycle.json << 'EOF'
{
  "rule": [
    {
      "action": {"type": "Delete"},
      "condition": {
        "age": 30,
        "matchesPrefix": [""]
      }
    }
  ]
}
EOF

# Apply to the bucket
gsutil lifecycle set /tmp/lifecycle.json gs://<BUCKET_NAME>

# Verify
gsutil lifecycle get gs://<BUCKET_NAME>
```

**Using gcloud:**

```bash
gcloud storage buckets update gs://<BUCKET_NAME> \
  --lifecycle-file=/tmp/lifecycle.json
```

**Using Terraform:**

```hcl
resource "google_storage_bucket" "exports" {
  name     = "<BUCKET_NAME>"
  location = "europe-west2"

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      age = 30  # days
    }
  }
}
```

### Choosing the Right TTL

| Scenario | Bucket TTL | Rationale |
|---|---|---|
| Application cleanup is working | 30 days | Match `lifecycle.snapshot.max_ttl`; backstop only |
| Application cleanup is broken | 7 days | Limit orphaned data growth while fixing the issue |
| Cost-sensitive | 3 days | Aggressive cleanup; ensure no long-running instances need older data |
| Compliance requirement | 90 days | Retain data for audit trail; ensure bucket versioning is enabled |

### Verifying the Rule Is Active

```bash
# Check the current lifecycle configuration
gsutil lifecycle get gs://<BUCKET_NAME>

# Expected output:
# {"rule": [{"action": {"type": "Delete"}, "condition": {"age": 30}}]}
```

GCS evaluates lifecycle rules once per day (not real-time). After setting a rule, objects will start being deleted within 24 hours of exceeding the age threshold.

### Relationship to Application TTLs

The cleanup chain works as follows:

```
Instance deleted (manual or lifecycle job)
  → Control-plane checks: any other instances on this snapshot?
    → No: cascade delete snapshot
      → GCSClient.delete_path() removes Parquet files  ← primary cleanup
      → Database row deleted
    → Yes: keep snapshot (still in use)

Bucket lifecycle rule (daily GCS evaluation)
  → Objects older than TTL age?
    → Yes: delete automatically                        ← backstop cleanup
    → No: keep
```

Both paths are needed:
- **Application cleanup** is immediate but can fail silently (credential issues, permission errors)
- **Bucket lifecycle** is delayed (up to 24h) but never fails — it's enforced by GCS infrastructure

### Adjusting Application TTLs

To change the maximum age of snapshots (which determines how long data stays in GCS before application cleanup):

```bash
# Check current TTL settings
curl -s https://<CONTROL_PLANE_URL>/api/ops/config \
  -H "X-Username: ops-user" | jq '.lifecycle'

# Set snapshot max TTL to 14 days
curl -s -X PUT https://<CONTROL_PLANE_URL>/api/config/lifecycle \
  -H "X-Username: ops-user" \
  -H "Content-Type: application/json" \
  -d '{"lifecycle.snapshot.max_ttl": "P14D", "lifecycle.snapshot.default_ttl": "P7D"}'
```

Then set the bucket lifecycle to match:

```bash
cat > /tmp/lifecycle.json << 'EOF'
{"rule": [{"action": {"type": "Delete"}, "condition": {"age": 14}}]}
EOF
gsutil lifecycle set /tmp/lifecycle.json gs://<BUCKET_NAME>
```
