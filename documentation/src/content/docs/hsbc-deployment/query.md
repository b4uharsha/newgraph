---
title: "Manual Query Testing"
sidebar:
  order: 6
---

Copy-paste commands for testing the API directly.

## Health Check

```bash
curl -H "X-Username: testuser" https://control-plane-graph-olap-platform.hsbc-12636856-udlhk-dev.dev.gcp.cloud.hk.hsbc/api/v1/health
```

## List Graphs

```bash
curl -H "X-Username: testuser" https://control-plane-graph-olap-platform.hsbc-12636856-udlhk-dev.dev.gcp.cloud.hk.hsbc/api/v1/graphs
```

## Run Cypher Query

```bash
curl -X POST -H "X-Username: testuser" -H "Content-Type: application/json" \
    -d '{"query": "MATCH (n) RETURN count(n)"}' \
    https://control-plane-graph-olap-platform.hsbc-12636856-udlhk-dev.dev.gcp.cloud.hk.hsbc/api/v1/graphs/default/query
```
