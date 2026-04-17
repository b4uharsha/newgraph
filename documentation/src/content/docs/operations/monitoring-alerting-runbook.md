---
title: "Monitoring and Alerting Runbook"
scope: hsbc
---

# Monitoring and Alerting Runbook

**Version:** 1.0
**Last Updated:** 2026-04-08

This runbook provides on-call engineers with alert response procedures, investigation queries, and dashboard references for the Graph OLAP Platform.

**References:** [ADR-131: Monitoring and Alerting Runbook](--/process/adr/operations/adr-131-monitoring-alerting-runbook.md)

- [ADR-131: Monitoring and Alerting Runbook](--/process/adr/operations/adr-131-monitoring-alerting-runbook.md)
- [Observability Design](-/observability.design.md) -- metric definitions, alerting rules, architecture
- [Incident Response Runbook](-/incident-response.runbook.md) -- incident playbooks and escalation procedures

> **Namespace Note:** All `kubectl` commands in this runbook use the namespace `graph-olap-platform`. All platform services and dynamically created wrapper pods run in this namespace. Verify the correct namespace for the target cluster before running commands. Use `kubectl get namespaces | grep graph` to discover available namespaces.

## Table of Contents

- [Dashboard Inventory](#dashboard-inventory)
- [Alert Catalogue](#alert-catalogue)
- [Alert Response Procedures](#alert-response-procedures)
- [Key Metrics Reference](#key-metrics-reference)
- [Log Query Cookbook](#log-query-cookbook)
- [Prometheus Query Cookbook](#prometheus-query-cookbook)
- [Silence and Acknowledge Procedures](#silence-and-acknowledge-procedures)
- [Dashboard Creation Guide](#dashboard-creation-guide)

---

## Dashboard Inventory

All dashboards are in Google Cloud Monitoring under the project that hosts the GKE cluster.

**Navigation:** Google Cloud Console > Monitoring > Dashboards

| Dashboard | Purpose | Key Panels |
|-----------|---------|------------|
| **Graph OLAP Overview** | Platform-wide health at a glance | Request rate, error rate, active instances, CPU/memory |
| **Instance Lifecycle** | Graph instance creation, status, and termination | Startup duration, status distribution, per-instance resource usage |
| **Export Pipeline** | Export job queue and Starburst Galaxy integration | Queue depth, export duration, success/failure rate, KEDA scaling |
| **Background Jobs** | Reconciliation, lifecycle, export reconciliation, schema cache | Job execution frequency, duration, failure counts |
| **Infrastructure** | GKE node and pod resources | Node CPU/memory, pod restarts, PVC usage, network I/O |
| **JupyterHub** | Notebook server sessions | Active users, server spawn duration, idle culling |
| **SLO Burn Rate** | Error budget consumption for availability and latency SLOs | Burn rate over 1h/6h/24h windows |

---

## Alert Catalogue

### Severity Definitions

| Severity | Response Time | Notification Channel | Escalation |
|----------|---------------|----------------------|------------|
| **Critical** | Immediate (< 15 min) | On-call rotation (via HSBC's on-call management tool) + designated incident communication channel | Page secondary on-call after 30 min |
| **Warning** | Within 1 hour | Designated incident communication channel + email | Escalate to critical if unresolved in 2 hours |
| **Info** | Next business day | Designated incident communication channel | No escalation |

### Alert Summary Table

| Alert | Severity | Condition | For Duration |
|-------|----------|-----------|--------------|
| ControlPlaneDown | Critical | `up{job="control-plane"} == 0` | 2 min |
| HighErrorRate | Critical | 5xx rate > 1% of total requests | 5 min |
| HighLatency | Warning | p99 request latency > 2s | 5 min |
| PodRestartLoop | Warning | Pod restarts > 5 in 1 hour | 5 min |
| DatabaseConnectionPoolExhausted | Critical | Available connections < 10% of pool | 5 min |
| ExportQueueBacklog | Warning | `graph_olap_export_queue_depth > 100` | 10 min |
| ExportWorkersScaledToZero | Critical | KEDA replicas == 0 with pending jobs | 5 min |
| StarburstExportFailureRateHigh | Warning | Export failure rate > 10% | 10 min |
| ExportDurationHigh | Warning | p95 export duration > 30 min | 30 min |
| PodMemoryHigh | Warning | Pod memory > 90% of limit | 5 min |
| InstanceStuckInTransition | Warning | Instance in CREATING/DELETING > 5 min | 5 min |
| GCSOperationFailure | Warning | Any GCS error in 5 min window | 5 min |
| JupyterHubUnhealthy | Warning | Hub pod not ready | 5 min |
| CertificateExpiringSoon | Warning | TLS certificate expires in < 14 days | 1 hour |
| InstanceFailureRateHigh | Critical | > 10% of instances failing | 5 min |
| PersistentVolumeAlmostFull | Warning | PVC < 10% free space | 5 min |
| ExportJobsStaleClaimedHigh | Warning | > 5 jobs claimed but not completed for > 10 min | 10 min |
| ExportReconciliationFailing | Warning | > 50 stale claims reset in 1 hour | 5 min |
| GraphInstanceQueryTimeouts | Warning | Query timeout rate > 5% | 5 min |

> **Deployed Alert Name Mapping:** The raw Kubernetes alerting-rules manifest (`infrastructure/cd/resources/monitoring/alerting-rules.yaml`, applied by `infrastructure/cd/deploy.sh` via `kubectl apply -f`) uses different alert names. Operators receiving alerts from the deployed rules should use this mapping to find the correct response procedure:
>
> | Deployed Alert Name | Runbook Alert Name |
> |---|---|
> | ControlPlaneHighErrorRate | [HighErrorRate](#higherrorrate-critical) |
> | ControlPlaneHighLatency | [HighLatency](#highlatency-warning) |
> | ControlPlanePodRestarts | [PodRestartLoop](#podrestartloop-warning) |
> | GraphInstanceStartupTimeout | [InstanceStuckInTransition](#instancestuckintransition-warning) |
> | GraphInstanceHighMemory | [PodMemoryHigh](#podmemoryhigh-warning) |
> | GraphInstanceQueryTimeouts | [GraphInstanceQueryTimeouts](#graphinstancequerytimeouts-warning) |
> | ExportWorkerHighFailureRate | [StarburstExportFailureRateHigh](#starburstexportfailureratehigh-warning) |
> | ExportQueueBacklog | [ExportQueueBacklog](#exportqueuebacklog-warning) |
> | ExportDurationExceeded | [ExportDurationHigh](#exportdurationhigh-warning) |
> | CloudSQLConnectionPoolExhausted | [DatabaseConnectionPoolExhausted](#databaseconnectionpoolexhausted-critical) |
> | GCSHighErrorRate | [GCSOperationFailure](#gcsoperationfailure-warning) |
>
> **Threshold note:** The deployed `infrastructure/cd/resources/monitoring/alerting-rules.yaml` manifest defines the authoritative thresholds in effect in the cluster; the values in this runbook are taken from `observability.design.md` and may differ if an environment-specific override has been committed. If there is a discrepancy, the thresholds in the manifest applied by Jenkins take precedence.
>
> **Export Alert Cascade:** These five export alerts form a causal chain. Investigate upstream (left) first.
>
>     ExportQueueBacklog ──> WorkersScaledToZero ──> StaleClaimedHigh ──> ReconciliationFailing
>           (Warning)            (CRITICAL)             (Warning)              (Warning)
>                │                                          ^
>                └──────────────────────────────────────────┘
>
> StarburstExportFailureRateHigh (WARNING) can independently trigger any of the above.

---

## Alert Response Procedures

> **Change Control:** Any remediation action that modifies production state requires a Deliverance change request. For P1/P2 incidents, use the Deliverance emergency change process and obtain retrospective approval within 24 hours.

### ControlPlaneDown (Critical)

**Meaning:** The control-plane pod is not responding to Prometheus scrapes.

**Impact:** All API operations are unavailable. Graph instance creation, snapshot, and export operations are blocked.

**Steps:**

1. Check pod status:
   ```bash
   kubectl -n graph-olap-platform get pods -l app=control-plane
   ```
2. Check pod events and logs:
   ```bash
   kubectl -n graph-olap-platform describe pod -l app=control-plane
   kubectl -n graph-olap-platform logs -l app=control-plane --tail=100
   ```
3. Check if the pod is in CrashLoopBackOff -- if so, look at previous container logs:
   ```bash
   kubectl -n graph-olap-platform logs -l app=control-plane --previous --tail=100
   ```
4. Verify Cloud SQL connectivity from the pod:
   ```bash
   kubectl -n graph-olap-platform exec deploy/control-plane -- python -c "import asyncpg; print('OK')"
   ```
5. If the pod is stuck in Pending, check node resources:
   ```bash
   kubectl describe nodes | grep -A5 "Allocated resources"
   ```
6. If unresolvable, trigger a rollback:
   ```bash
   # Roll back to the previous deployment:
   kubectl rollout undo deployment/control-plane -n graph-olap-platform
   ```

### HighErrorRate (Critical)

**Meaning:** More than 1% of HTTP responses are 5xx over a 5-minute window.

**Impact:** Users are experiencing failures. API reliability SLO is burning error budget.

**Steps:**

1. Identify which endpoints are failing -- see [PromQL: Error rate by endpoint](#error-rate-by-endpoint).
2. Check recent deployments:
   ```bash
   kubectl -n graph-olap-platform rollout history deploy/control-plane
   ```
3. Search logs for error details -- see [Log Query: Recent errors](#recent-errors-by-service).
4. If caused by a recent deployment, roll back:
   ```bash
   # Roll back to the previous deployment:
   kubectl rollout undo deployment/control-plane -n graph-olap-platform
   ```
5. If caused by Cloud SQL issues, check database health -- see [DatabaseConnectionPoolExhausted](#databaseconnectionpoolexhausted-critical).
6. If caused by an external dependency (Starburst Galaxy, GCS), check that service's status.

### HighLatency (Warning)

**Meaning:** The 99th percentile request latency exceeds 2 seconds.

**Steps:**

1. Identify slow endpoints -- see [PromQL: Latency by endpoint](#latency-by-endpoint).
2. Check database query performance -- see [Log Query: Slow queries](#slow-database-queries).
3. Check if pod CPU is throttled:
   ```bash
   kubectl -n graph-olap-platform top pods -l app=control-plane
   ```
4. Check Cloud SQL CPU and connection metrics in Cloud Console.
5. If caused by a specific endpoint, investigate the operation (e.g., large snapshot, complex mapping).

### PodRestartLoop (Warning)

**Meaning:** A pod has restarted more than 5 times in the past hour.

**Steps:**

1. Identify the crashing pod:
   ```bash
   kubectl -n graph-olap-platform get pods --sort-by='.status.containerStatuses[0].restartCount'
   ```
2. Check the previous container's exit reason and logs:
   ```bash
   kubectl -n graph-olap-platform describe pod <POD_NAME>
   kubectl -n graph-olap-platform logs <POD_NAME> --previous --tail=200
   ```
3. Common causes:
   - **OOMKilled**: Pod exceeded memory limit. Check memory usage patterns and consider increasing limits.
   - **Liveness probe failure**: Application is hanging. Check for deadlocks or blocked I/O.
   - **Startup failure**: Missing config, bad secret, database unreachable.

### DatabaseConnectionPoolExhausted (Critical)

**Meaning:** The Cloud SQL connection pool has fewer than 10% of connections available.

**Steps:**

1. Check current pool state -- see [PromQL: Database connection pool](#database-connection-pool).
2. Look for connection leaks -- long-running queries or transactions:
   ```sql
   SELECT pid, now() - pg_stat_activity.query_start AS duration, query
   FROM pg_stat_activity
   WHERE state != 'idle'
   ORDER BY duration DESC;
   ```
3. Check if pod count has increased (more pods = more connections drawn from pool).
4. If connections are genuinely exhausted, consider restarting the control-plane pod as a short-term fix:
   ```bash
   kubectl -n graph-olap-platform rollout restart deploy/control-plane
   ```
5. Long-term: review connection pool size in application configuration.

### ExportQueueBacklog (Warning)

**Meaning:** More than 100 export jobs have been pending for over 10 minutes.

**Steps:**

1. Check KEDA scaling status:
   ```bash
   kubectl -n graph-olap-platform get scaledobjects
   kubectl -n graph-olap-platform get hpa
   ```
2. Verify export worker pods are running:
   ```bash
   kubectl -n graph-olap-platform get pods -l app=export-worker
   ```
3. Check if Starburst Galaxy is reachable and healthy (export workers submit UNLOAD queries to Starburst Galaxy).
4. Check for stale claimed jobs -- see [PromQL: Stale export claims](#stale-export-claims).
5. If workers are scaled to zero despite pending jobs, see [ExportWorkersScaledToZero](#exportworkersscaledtozero-critical).

### ExportWorkersScaledToZero (Critical)

**Meaning:** KEDA has scaled export workers to zero replicas while there are pending export jobs.

**Steps:**

1. Check KEDA scaler logs:
   ```bash
   kubectl -n keda logs -l app=keda-operator --tail=100
   ```
2. Verify the KEDA ScaledObject configuration:
   ```bash
   kubectl -n graph-olap-platform describe scaledobject export-worker
   ```
3. Check if the Prometheus query used by KEDA is returning data:
   ```promql
   graph_olap_export_queue_depth
   ```
4. Restart KEDA if the scaler is stuck:
   ```bash
   kubectl -n keda rollout restart deploy/keda-operator
   ```

### PodMemoryHigh (Warning)

**Meaning:** A pod is using more than 90% of its memory limit and is at risk of OOMKill.

**Steps:**

1. Identify the pod:
   ```bash
   kubectl -n graph-olap-platform top pods --sort-by=memory
   ```
2. If it is a graph instance pod, this may be expected for large graphs. Check the graph size.
3. If it is the control-plane, check for memory leaks -- review recent changes.
4. Consider updating the resource limits in the deployment manifest (`infrastructure/cd/resources/<service>-deployment.yaml`) and re-applying via Jenkins / `infrastructure/cd/deploy.sh <VERSION>` (or `kubectl apply -f infrastructure/cd/resources/<service>-deployment.yaml` for break-glass) if the workload genuinely needs more memory.

### InstanceStuckInTransition (Warning)

**Meaning:** A graph instance has been in CREATING or DELETING state for more than 5 minutes.

**Steps:**

1. Check the instance status via the API or database.
2. Check the wrapper pod status:
   ```bash
   kubectl -n graph-olap-platform get pods -l graph-olap.io/instance-id=<INSTANCE_ID>
   ```
3. If the pod is stuck in Pending, check node capacity and resource quotas.
4. If the pod is running but the control plane has not updated the status, trigger reconciliation manually by restarting the control-plane.
5. The reconciliation background job should eventually detect and fix stuck instances.

### GCSOperationFailure (Warning)

**Meaning:** Google Cloud Storage operations are failing.

**Steps:**

1. Check GCS service status at https://status.cloud.google.com.
2. Verify Workload Identity is correctly configured:
   ```bash
   kubectl -n graph-olap-platform describe serviceaccount <SA_NAME>
   ```
3. Check pod logs for specific GCS error messages -- see [Log Query: GCS errors](#gcs-operation-errors).
4. Verify the GCS bucket exists and the service account has correct IAM roles.

### JupyterHubUnhealthy (Warning)

**Meaning:** The JupyterHub pod is not passing readiness probes.

**Steps:**

1. Check hub pod status:
   ```bash
   kubectl -n graph-olap-platform get pods -l app=jupyterhub,component=hub
   ```
2. Check hub logs:
   ```bash
   kubectl -n graph-olap-platform logs -l app=jupyterhub,component=hub --tail=100
   ```
3. Verify the hub database (SQLite or PostgreSQL) is accessible.
4. Restart if needed:
   ```bash
   kubectl -n graph-olap-platform rollout restart deploy/hub
   ```

### CertificateExpiringSoon (Warning)

**Meaning:** A TLS certificate will expire in fewer than 14 days.

**Steps:**

1. Identify which certificate is expiring:
   ```bash
   kubectl -n graph-olap-platform get certificates
   kubectl -n graph-olap-platform describe certificate <CERT_NAME>
   ```
2. If using cert-manager, check the certificate request status:
   ```bash
   kubectl -n graph-olap-platform get certificaterequests
   ```
3. Check cert-manager logs for renewal failures:
   ```bash
   kubectl -n cert-manager logs -l app=cert-manager --tail=100
   ```
4. If auto-renewal is stuck, delete the CertificateRequest to trigger a new one.

### StarburstExportFailureRateHigh (Warning)

**Meaning:** More than 10% of export jobs submitted to Starburst Galaxy are failing over a 1-hour window.

**Impact:** Data exports are unreliable. Analysts cannot access exported data in the expected timeframe. Error budget is burning.

**Steps:**

1. Check export worker logs for Starburst-specific errors:
   ```bash
   kubectl -n graph-olap-platform logs -l app=export-worker --tail=200 | grep -i "starburst\|UNLOAD\|failed"
   ```
2. Verify Starburst Galaxy connectivity from an export worker pod:
   ```bash
   kubectl -n graph-olap-platform exec deploy/export-worker -- python -c "import requests; print(requests.get('https://<STARBURST_HOST>/v1/info').status_code)"
   ```
3. Check if failures are concentrated on specific catalogs or schemas -- see [Log Query: Export job failures](#export-job-failures).
4. Check Starburst Galaxy cluster status and query quotas in the Starburst Galaxy console.
5. If Starburst Galaxy is healthy but queries are failing, check for recent schema changes in the source data that may have broken UNLOAD queries.
6. If Starburst Galaxy is unreachable, check network policies and firewall rules between the GKE cluster and Starburst Galaxy endpoints.
7. If caused by a recent deployment, roll back:
   ```bash
   kubectl rollout undo deployment/export-worker -n graph-olap-platform
   ```

### InstanceFailureRateHigh (Critical)

**Meaning:** More than 10% of graph instance creation or lifecycle operations are failing.

**Impact:** Users cannot create graph instances. Platform reliability SLO is at risk.

**Steps:**

1. Check which instances are failing:
   ```bash
   kubectl -n graph-olap-platform get pods -l app.kubernetes.io/component=graph-instance --field-selector status.phase!=Running
   ```
2. Check control-plane logs for instance creation errors -- see [Log Query: Instance lifecycle events](#instance-lifecycle-events).
3. Check if a specific wrapper type (ryugraph-wrapper or falkordb-wrapper) is failing:
   ```bash
   kubectl -n graph-olap-platform logs -l app=control-plane --tail=200 | grep -i "instance.*fail\|wrapper.*error"
   ```
4. Check node capacity -- insufficient resources cause pods to stay in Pending:
   ```bash
   kubectl describe nodes | grep -A5 "Allocated resources"
   ```
5. Verify Cloud SQL connectivity -- instance metadata operations require the database:
   ```bash
   kubectl -n graph-olap-platform exec deploy/control-plane -- python -c "import asyncpg; print('OK')"
   ```
6. If a specific wrapper image is broken, roll back the control-plane to revert instance creation logic:
   ```bash
   kubectl rollout undo deployment/control-plane -n graph-olap-platform
   ```

### ExportDurationHigh (Warning)

**Meaning:** The 95th percentile export duration exceeds 30 minutes.

**Steps:**

1. Identify which export jobs are running long -- see [PromQL: Export queue depth over time](#export-queue-depth-over-time).
2. Check Starburst Galaxy query performance -- long UNLOAD queries may indicate large datasets or resource contention in Starburst.
3. Check GCS write throughput -- slow writes to the export bucket increase total export duration:
   ```bash
   kubectl -n graph-olap-platform logs -l app=export-worker --tail=200 | grep -i "gcs\|duration\|slow"
   ```
4. Check if the data volume has increased (larger graphs produce larger exports).
5. Verify KEDA is scaling export workers to handle the load:
   ```bash
   kubectl -n graph-olap-platform get scaledobjects
   kubectl -n graph-olap-platform get hpa
   ```
6. If Starburst Galaxy is slow, check if concurrent queries from other teams are contending for resources.

### PersistentVolumeAlmostFull (Warning)

**Meaning:** A PersistentVolumeClaim has less than 10% free space remaining.

**Steps:**

1. Identify the affected volume:
   ```bash
   kubectl -n graph-olap-platform get pvc
   kubectl -n graph-olap-platform describe pvc <PVC_NAME>
   ```
2. Check what is consuming space on the pod using the volume:
   ```bash
   kubectl -n graph-olap-platform exec <POD_NAME> -- df -h
   kubectl -n graph-olap-platform exec <POD_NAME> -- du -sh /*
   ```
3. If the volume belongs to JupyterHub, check for large user notebooks or data files that can be cleaned up.
4. If the volume belongs to a graph instance, the graph data may have grown beyond the provisioned size.
5. To expand the PVC (if the StorageClass supports volume expansion):
   ```bash
   kubectl -n graph-olap-platform patch pvc <PVC_NAME> -p '{"spec":{"resources":{"requests":{"storage":"<NEW_SIZE>"}}}}'
   ```
6. Monitor the volume after expansion to confirm the resize completes.

### ExportJobsStaleClaimedHigh (Warning)

**Meaning:** More than 5 export jobs have been claimed by workers but not completed for over 10 minutes, indicating workers may have crashed mid-export.

**Steps:**

1. Check export worker pod status for recent crashes or OOMKills:
   ```bash
   kubectl -n graph-olap-platform get pods -l app=export-worker --sort-by='.status.containerStatuses[0].restartCount'
   ```
2. Check previous container logs for crash reasons:
   ```bash
   kubectl -n graph-olap-platform logs -l app=export-worker --previous --tail=200
   ```
3. Verify Starburst Galaxy connectivity -- workers may hang if Starburst becomes unreachable during an UNLOAD query.
4. The export reconciliation background job should automatically detect and reset stale claims. Verify it is running:
   ```bash
   kubectl -n graph-olap-platform logs -l app=control-plane --tail=100 | grep "export_reconciliation"
   ```
5. If reconciliation is not resetting claims, restart the control-plane:
   ```bash
   kubectl -n graph-olap-platform rollout restart deploy/control-plane
   ```

### ExportReconciliationFailing (Warning)

**Meaning:** The export reconciliation job is resetting more than 50 stale claims per hour, indicating workers are repeatedly crashing or hanging.

**Steps:**

1. This alert signals a systemic issue with export workers, not a one-off crash. Check worker logs for a recurring crash pattern:
   ```bash
   kubectl -n graph-olap-platform logs -l app=export-worker --tail=300 | grep -i "error\|exception\|killed\|timeout"
   ```
2. Check if workers are being OOMKilled -- see [PodRestartLoop](#podrestartloop-warning) for memory investigation steps.
3. Check worker resource limits -- repeated OOMKills during large exports may require increasing the memory limit.
4. Check Starburst Galaxy health -- if Starburst is intermittently failing, workers will claim jobs, fail, and the reconciliation job will reset them in a loop.
5. Consider reducing the claim batch size to limit the blast radius of individual worker failures. Review the `EXPORT_CLAIM_BATCH_SIZE` environment variable on the export-worker deployment.

### GraphInstanceQueryTimeouts (Warning)

**Meaning:** More than 5% of queries against graph instances are timing out.

**Steps:**

1. Identify which graph instances have high timeout rates:
   ```bash
   kubectl -n graph-olap-platform logs -l app.kubernetes.io/component=graph-instance --tail=200 | grep -i "timeout"
   ```
2. Check if the affected instances are running large graphs that exceed memory or CPU capacity:
   ```bash
   kubectl -n graph-olap-platform top pods -l app.kubernetes.io/component=graph-instance --sort-by=memory
   ```
3. Check whether specific query types (e.g., path-finding algorithms on large graphs) are causing timeouts.
4. Verify the query timeout configuration on the wrapper pods. Timeouts may need adjustment for legitimately complex queries.
5. If a single instance is causing all timeouts, check its graph size and consider provisioning a larger instance.

---

## Key Metrics Reference

| Metric | Normal Range | Warning Threshold | Description |
|--------|-------------|-------------------|-------------|
| `http_requests_total` (rate) | 10-200 req/s | N/A (traffic dependent) | Total request throughput |
| 5xx / total ratio | < 0.5% | > 1% | Error rate |
| `http_request_duration_seconds` p50 | 20-100 ms | > 500 ms | Median latency |
| `http_request_duration_seconds` p99 | 200-800 ms | > 2s | Tail latency |
| `graph_olap_instances_active{status="running"}` | 5-50 | > 100 (check capacity) | Running graph instances |
| `graph_olap_export_queue_depth` | 0-10 | > 100 | Pending export jobs |
| `graph_olap_database_connections{state="available"}` | > 50% of pool | < 10% of pool | Connection pool headroom |
| Pod memory usage / limit | 40-70% | > 90% | Per-pod memory pressure |
| Pod CPU usage / request | 20-60% | > 90% sustained | Per-pod CPU pressure |
| `background_job_health_status` | 1 (healthy) | 0 (unhealthy) | Background job circuit breaker |
| `orphaned_pods_detected_current` | 0 | > 0 sustained | Leaked pods not tracked in DB |

---

## Log Query Cookbook

> **PII Note:** Cloud Logging queries may return records containing user identifiers. Apply HSBC data protection controls when exporting or sharing log data.

All queries are for the Cloud Logging Logs Explorer. Filter by resource type `k8s_container` and namespace `graph-olap-platform`.

### Recent Errors by Service

```
resource.type="k8s_container"
resource.labels.namespace_name="graph-olap-platform"
resource.labels.container_name="control-plane"
severity>=ERROR
timestamp>="<YYYY-MM-DD>T00:00:00Z"  # Replace with the start of your investigation window
```

### Errors for a Specific Request

```
resource.type="k8s_container"
resource.labels.namespace_name="graph-olap-platform"
jsonPayload.trace_id="<REQUEST_ID>"
```

### Slow Database Queries

```
resource.type="k8s_container"
resource.labels.namespace_name="graph-olap-platform"
jsonPayload.message=~"duration_ms"
jsonPayload.duration_ms>1000
```

### Export Job Failures

```
resource.type="k8s_container"
resource.labels.namespace_name="graph-olap-platform"
resource.labels.container_name="export-worker"
severity>=ERROR
```

### GCS Operation Errors

```
resource.type="k8s_container"
resource.labels.namespace_name="graph-olap-platform"
jsonPayload.message=~"gcs"
severity>=ERROR
```

### Instance Lifecycle Events

```
resource.type="k8s_container"
resource.labels.namespace_name="graph-olap-platform"
resource.labels.container_name="control-plane"
jsonPayload.resource_type="instance"
jsonPayload.message=~"created|terminated|failed"
```

### Background Job Execution

```
resource.type="k8s_container"
resource.labels.namespace_name="graph-olap-platform"
resource.labels.container_name="control-plane"
jsonPayload.message=~"reconciliation|lifecycle|export_reconciliation|schema_cache"
```

---

## Prometheus Query Cookbook

These queries use PromQL and can be run in Cloud Monitoring's PromQL editor.

### Error Rate (Overall)

```promql
sum(rate(http_requests_total{status=~"5.."}[5m]))
/ sum(rate(http_requests_total[5m]))
```

### Error Rate by Endpoint

```promql
sum by (endpoint) (rate(http_requests_total{status=~"5.."}[5m]))
/ sum by (endpoint) (rate(http_requests_total[5m]))
```

### Latency by Endpoint

```promql
histogram_quantile(0.99,
  sum by (le, endpoint) (rate(http_request_duration_seconds_bucket[5m]))
)
```

### Request Rate by Endpoint

```promql
sum by (endpoint) (rate(http_requests_total[5m]))
```

### Database Connection Pool

```promql
graph_olap_database_connections{state="available"}
/ graph_olap_database_connections{state="total"}
```

### Export Queue Depth Over Time

```promql
graph_olap_export_queue_depth
```

### Export Success Rate

```promql
sum(rate(graph_olap_export_jobs_completed_total{status="success"}[1h]))
/ sum(rate(graph_olap_export_jobs_completed_total[1h]))
```

### Stale Export Claims

```promql
increase(stale_export_claims_detected_total[1h])
```

### Pod Memory Usage as Percentage of Limit

```promql
container_memory_usage_bytes{namespace="graph-olap-platform"}
/ container_spec_memory_limit_bytes{namespace="graph-olap-platform"}
```

### Pod Restart Rate

```promql
increase(kube_pod_container_status_restarts_total{namespace="graph-olap-platform"}[1h])
```

### Background Job Health

```promql
background_job_health_status
```

### Reconciliation Duration Trend

```promql
histogram_quantile(0.95,
  sum by (le) (rate(reconciliation_pass_duration_seconds_bucket[1h]))
)
```

### KEDA Replica Count

```promql
keda_scaled_object_status{scaledObject="export-worker"}
```

---

## Silence and Acknowledge Procedures

### Silencing Alerts During Planned Maintenance

Use Cloud Monitoring snooze policies to suppress alerts during maintenance windows.

**Via Console:**

1. Go to Google Cloud Console > Monitoring > Alerting.
2. Click **Snooze** in the top bar.
3. Click **Create Snooze**.
4. Set the start time and duration.
5. Choose which alert policies to snooze (all, or specific policies).
6. Add a description (e.g., "Planned maintenance: Cloud SQL upgrade").
7. Click **Save**.

**Via gcloud CLI:**

```bash
gcloud monitoring snoozes create \
  --display-name="Planned maintenance" \
  --criteria-policies="projects/<PROJECT>/alertPolicies/<POLICY_ID>" \
  --start-time="2026-04-08T22:00:00Z" \
  --end-time="2026-04-09T02:00:00Z"
```

### Acknowledging an Incident

1. Open the incident in Cloud Monitoring > Alerting > Incidents.
2. Click **Acknowledge** to signal that someone is investigating.
3. Add comments with investigation progress.
4. When resolved, the incident auto-closes when the condition clears, or close it manually.

### Post-Maintenance Checklist

After maintenance completes and the snooze expires:

1. Verify all pods are running: `kubectl -n graph-olap-platform get pods`.
2. Check the Overview dashboard for error rate and latency spikes.
3. Confirm background jobs are executing: check `background_job_health_status` metric.
4. Verify export pipeline is processing: check `graph_olap_export_queue_depth`.

---

## Dashboard Creation Guide

### Adding a New Dashboard

1. Define the dashboard in JSON format following the Cloud Monitoring mosaic layout schema. See `observability.design.md` for an example.
2. Add the dashboard JSON to the `infrastructure/cd/resources/` directory or apply it via `gcloud monitoring dashboards create`.
3. Apply via the standard deploy workflow:
   ```bash
   # From the infrastructure/cd/ directory:
   ./deploy.sh <VERSION>
   ```

### Adding a New Alert Policy

1. Define the alert rule in `infrastructure/cd/resources/monitoring/alerting-rules.yaml` (raw Kubernetes manifest, applied by `infrastructure/cd/deploy.sh`) or as a Terraform `google_monitoring_alert_policy` resource.
2. Every alert MUST have:
   - A `severity` label (critical, warning, or info).
   - An `annotations.summary` with a human-readable description.
   - A response procedure documented in this runbook.
3. Apply the rule and update this runbook with the new alert's response procedure.

### Adding a New Metric

1. Define the metric in application code using `prometheus_client` (Python).
2. Ensure the metric name follows the `graph_olap_` prefix convention.
3. Add the metric to the relevant table in `observability.design.md`.
4. Create a dashboard panel and/or alert rule if the metric warrants monitoring.
5. Verify the metric appears in Managed Prometheus after deploying:
   ```promql
   {__name__=~"graph_olap_new_metric.*"}
   ```

---

## Related Documents

- [Incident Response Runbook (ADR-130)](incident-response.runbook.md) — Escalation and incident management procedures
- [Platform Operations Manual (ADR-129)](platform-operations.manual.md) — Routine operations and health checks
- [Disaster Recovery Plan (ADR-132)](disaster-recovery.runbook.md) — Recovery procedures for major failures
- [Troubleshooting Guide (ADR-135)](troubleshooting.runbook.md) — Symptom-based diagnostic trees
- [Service Catalogue (ADR-134)](service-catalogue.manual.md) — Service inventory and dependency map
- [Observability Design](observability.design.md) — Alert rules, metrics catalogue, SLO definitions
