---
title: "Manual Query Testing"
sidebar:
  order: 6
---

Copy-paste commands for testing the API directly.

> The API is not versioned with a `/api/v1/` prefix. Control-plane routes live
> under `/health`, `/api/instances`, `/api/mappings`, etc. Cypher queries go to
> the **per-instance** wrapper pod through the wrapper-proxy, not through the
> control-plane.

## Health Check (control-plane)

```bash
curl https://<HSBC_API_HOST>/health
```

`/health` is an unauthenticated liveness probe and returns `{"status": "healthy", "version": "..."}`.

## List Instances

```bash
curl -H "X-Username: testuser" https://<HSBC_API_HOST>/api/instances
```

## Get an Instance (to read its `url_slug` for querying)

```bash
curl -H "X-Username: testuser" https://<HSBC_API_HOST>/api/instances/<id>
```

The response includes a `url_slug` field used to route queries to the correct
wrapper pod via the wrapper-proxy.

## Run a Cypher Query

Cypher executes on the wrapper pod (RyuGraph or FalkorDB) behind the
wrapper-proxy. Use the `url_slug` from the instance record:

```bash
curl -X POST -H "X-Username: testuser" -H "Content-Type: application/json" \
    -d '{"query": "MATCH (n) RETURN count(n)"}' \
    https://<HSBC_API_HOST>/wrapper/<url_slug>/query
```

The RyuGraph `/query` router rejects Cypher mutation keywords
(`CREATE`, `SET`, `DELETE`, `REMOVE`, `MERGE`, `DROP`) with a 400 before the
query reaches the engine. FalkorDB does not apply the same guard — the engine's
own read-only posture is the guard.
