---
title: "Debugging: Starburst Schema Cache Connection Failure"
scope: demo
---

# Debugging: Starburst Schema Cache Connection Failure

> **Related:** [Known Issues — Schema Cache Not Connecting to Starburst](known-issues.md#schema-cache-not-connecting-to-starburst) · [Known Issues — Schema Cache Starburst URL Empty in GKE London](known-issues.md#schema-cache-starburst-url-empty-in-gke-london-configmap) · [Troubleshooting Runbook — Schema Browser Empty](troubleshooting.runbook.md#schema-browser-returns-empty-catalogs)

**Symptom:** The Starburst schema browser in the SDK returns no catalogs, schemas, or tables. Calls to `/api/schema/catalogs` return an empty list. Analysts cannot discover data sources.

**Component:** Control Plane — `jobs/schema_cache.py`, `clients/starburst_metadata.py`, `cache/schema_cache.py`

---

## How the Cache Works

The control plane maintains an in-memory schema metadata cache (`SchemaMetadataCache`). A background job (`run_schema_cache_job`) refreshes it on startup and then every `GRAPH_OLAP_SCHEMA_CACHE_JOB_INTERVAL_SECONDS` seconds (default: 86400 — once every 24 hours).

The refresh sequence is:

1. Open an HTTP connection to the Starburst coordinator (`GRAPH_OLAP_STARBURST_URL`)
2. Optionally issue `SET ROLE <GRAPH_OLAP_STARBURST_ROLE>` via `/v1/statement`
3. `SELECT catalog_name FROM system.metadata.catalogs`
4. For each catalog: fetch schemas, then tables, then columns — in parallel (capped at 10 concurrent queries)
5. Atomically swap the in-memory cache

If step 1 or 2 fails, the cache is never populated and all `/api/schema/*` endpoints return empty responses. **The failure is logged but does not crash the pod.**

---

## Step 1 — Confirm the Cache is Empty

Check the cache stats endpoint (requires Ops role):

```bash
curl -s https://<INGRESS_HOST>/api/schema/admin/stats \
  -H "X-Username: <OPS_USERNAME>" | jq .
```

A healthy response looks like:

```json
{
  "data": {
    "total_catalogs": 3,
    "total_schemas": 47,
    "total_tables": 1200,
    "total_columns": 18400,
    "last_refresh": "2026-04-16T09:12:34.000000+00:00",
    "index_size_bytes": 284000
  }
}
```

An empty/broken cache looks like:

```json
{
  "data": {
    "total_catalogs": 0,
    "total_schemas": 0,
    "total_tables": 0,
    "total_columns": 0,
    "last_refresh": null,
    "index_size_bytes": 0
  }
}
```

`last_refresh: null` means the job has never completed successfully since the pod started.

---

## Step 2 — Check the Logs

### Find the refresh attempt

```bash
gcloud logging read \
  'resource.type="k8s_container"
   resource.labels.container_name="control-plane"
   jsonPayload.event="schema_cache_refresh_started"' \
  --limit=5 --format=json --freshness=25h
```

If no results: the job has not run at all. Check pod uptime — the job fires on startup.

```bash
kubectl get pods -n graph-olap-platform -l app=control-plane
```

### Find the failure

```bash
gcloud logging read \
  'resource.type="k8s_container"
   resource.labels.container_name="control-plane"
   jsonPayload.event="schema_cache_refresh_failed"' \
  --limit=5 --format=json --freshness=25h
```

The `error` field in the log payload contains the exception message. Common values and their meanings:

| `error` value | Root cause |
|---|---|
| `Client not initialized. Use async with block.` | Code bug — should not occur in production |
| `Name or service not known` / `nodename nor servname provided` | DNS resolution failure — `GRAPH_OLAP_STARBURST_URL` is empty or points to an unreachable hostname |
| `Connection refused` | Starburst endpoint is not listening on that port |
| `SSL: CERTIFICATE_VERIFY_FAILED` | TLS trust issue — certificate chain not trusted by the pod |
| `HTTP 401` | Wrong credentials (`GRAPH_OLAP_STARBURST_USER` / password) |
| `HTTP 403` | User exists but has no permissions (check role) |
| `Query exceeded 100 polls` | Starburst is overloaded — queries are queued and timing out |
| `ConnectError` (after 3 retries) | Network policy blocks egress from control-plane pod to Starburst |

### Find per-catalog failures

If the job started but some catalogs failed:

```bash
gcloud logging read \
  'resource.type="k8s_container"
   resource.labels.container_name="control-plane"
   jsonPayload.event="catalog_fetch_failed"' \
  --limit=20 --format=json --freshness=25h
```

Per-catalog errors do not abort the refresh — the job continues with remaining catalogs. If all catalogs fail, the cache is written as empty (rather than keeping stale data).

### Check the SET ROLE step

```bash
gcloud logging read \
  'resource.type="k8s_container"
   resource.labels.container_name="control-plane"
   (jsonPayload.event="starburst_set_role_ok" OR jsonPayload.event="starburst_set_role_failed")' \
  --limit=5 --format=json --freshness=25h
```

`starburst_set_role_failed` is a warning, not a hard failure — the job continues without a role. However, if the role is required for table visibility, the catalog list may appear empty even if the connection succeeded.

---

## Step 3 — Inspect the Configuration

Check what the control-plane pod actually has for Starburst settings:

```bash
kubectl get configmap -n graph-olap-platform control-plane-config -o yaml \
  | grep -i starburst
```

Check the secret is mounted (password is not readable, only its presence):

```bash
kubectl get secret -n graph-olap-platform starburst-password -o jsonpath='{.data}' \
  | jq 'keys'
```

**Known issue in GKE London:** `GRAPH_OLAP_STARBURST_URL` is set to an empty string in the control-plane ConfigMap. The export-worker ConfigMap has the correct value. See [Fix: Empty URL in GKE London](#fix-empty-starburst-url-in-gke-london-configmap) below.

---

## Step 4 — Test Connectivity from the Pod

```bash
# Get a shell inside the control-plane pod
kubectl exec -it -n graph-olap-platform \
  $(kubectl get pod -n graph-olap-platform -l app=control-plane -o jsonpath='{.items[0].metadata.name}') \
  -- /bin/sh

# From inside the pod, test TCP reachability
nc -zv wsdv-hk-dev.hk.hsbc 8443

# Or using curl
curl -k -u HK-WPB-DSW-DEV:<PASSWORD> \
  https://wsdv-hk-dev.hk.hsbc:8443/v1/info
```

A healthy Starburst coordinator returns a JSON object with `nodeVersion`, `uptime`, and `coordinator: true`.

If `nc` / `curl` times out or refuses connection, the issue is network policy or DNS — not credentials.

---

## Step 5 — Trigger a Manual Refresh

Once the configuration issue is resolved, you can force an immediate cache refresh without waiting for the 24-hour interval:

```bash
curl -X POST https://<INGRESS_HOST>/api/schema/admin/refresh \
  -H "X-Username: <OPS_USERNAME>"
```

The response is immediate (`{"data": {"status": "refresh triggered"}}`). The refresh runs in the background. Poll the stats endpoint to confirm completion:

```bash
watch -n5 'curl -s https://<INGRESS_HOST>/api/schema/admin/stats \
  -H "X-Username: <OPS_USERNAME>" | jq ".data | {total_catalogs, last_refresh}"'
```

---

## Fix: Empty Starburst URL in GKE London ConfigMap

The `GRAPH_OLAP_STARBURST_URL` field is blank in `infrastructure/cd/resources/control-plane-configmap.yaml`. The correct value is visible in the export-worker ConfigMap.

**To fix:**

1. Edit the ConfigMap source file (do not patch live — changes must be in git for ArgoCD):

   ```bash
   # infrastructure/cd/resources/control-plane-configmap.yaml
   GRAPH_OLAP_STARBURST_URL: "https://wsdv-hk-dev.hk.hsbc:8443"
   ```

2. Commit and push; ArgoCD will sync automatically, or force-sync:

   ```bash
   argocd app sync graph-olap-control-plane
   ```

3. The control-plane pods will roll (ConfigMap change triggers a rolling restart). The schema cache job fires automatically on pod startup.

4. Confirm with the stats endpoint (see [Step 1](#step-1--confirm-the-cache-is-empty)).

---

## Root Cause Checklist

| Check | Command / Location | Expected |
|---|---|---|
| URL is set | `kubectl get configmap control-plane-config -o yaml \| grep STARBURST_URL` | `https://wsdv-hk-dev.hk.hsbc:8443` |
| DNS resolves | `kubectl exec ... -- nslookup wsdv-hk-dev.hk.hsbc` | Returns an IP |
| Port is reachable | `kubectl exec ... -- nc -zv wsdv-hk-dev.hk.hsbc 8443` | Connection succeeded |
| Auth succeeds | `curl -k -u <USER>:<PASS> https://.../v1/info` | 200 + JSON body |
| Role is accepted | `jsonPayload.event="starburst_set_role_ok"` in logs | Event present |
| Cache populated | `/api/schema/admin/stats` | `total_catalogs > 0` |

---

## Log Reference Summary

| Log event key | Level | Meaning |
|---|---|---|
| `schema_cache_refresh_started` | INFO | Job began |
| `fetching_catalogs` | INFO | About to query `system.metadata.catalogs` |
| `catalogs_fetched` | INFO | Got catalog list; includes `count` |
| `fetching_catalog_metadata` | INFO | Starting per-catalog fetch; includes `catalog` |
| `catalog_metadata_fetched` | INFO | Per-catalog done; includes `schemas` count |
| `schema_cache_refresh_completed` | INFO | Full refresh done; includes duration and totals |
| `schema_cache_refresh_failed` | ERROR | Refresh aborted; check `error` field |
| `catalog_fetch_failed` | ERROR | One catalog failed; job continues |
| `starburst_set_role_ok` | INFO | SET ROLE accepted |
| `starburst_set_role_failed` | WARNING | SET ROLE rejected; connection still open |

All log events are emitted by the `control-plane` container using structlog. Use `jsonPayload.event` to filter in Cloud Logging.
