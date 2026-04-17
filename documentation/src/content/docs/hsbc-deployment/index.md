---
title: "Graph OLAP Platform -- HSBC Operations"
sidebar:
  order: 1
---

Quick reference for the HSBC Graph OLAP Platform deployment.

## Cluster

- **GKE Project:** hsbc-12636856-udlhk-dev
- **Region:** asia-east2 (Hong Kong)
- **Namespace:** graph-olap-platform
- **API Endpoint:** https://control-plane-graph-olap-platform.hsbc-12636856-udlhk-dev.dev.gcp.cloud.hk.hsbc
- **Docs:** https://<DOCS_URL>

## Services

| Service | Port | Health |
|---------|------|--------|
| control-plane | 8080 | /health |
| export-worker | 8080 | /health |
| falkordb-wrapper | 8080 | /health |
| ryugraph-wrapper | 8080 | /health |
| wrapper-proxy | 8080 | /health |
| documentation | 8080 | / |

## Quick Commands

```bash
# Check all pods
kubectl get pods -n graph-olap-platform

# Deploy new version
cd cd/ && ./deploy.sh v1.2.3

# Run E2E tests
kubectl apply -f cd/jobs/e2e-test-job.yaml

# View logs
kubectl logs -n graph-olap-platform -l app=control-plane -f
```

## Documentation Index

- [Architecture](architecture.md) -- Platform architecture and data flow
- [Debug Guide](debug.md) -- Troubleshooting headers, proxy, pods
- [Jupyter Setup](jupyter.md) -- Dataproc Jupyter configuration
- [SAML/SSO](saml.md) -- Authentication integration status
- [Query Guide](query.md) -- Manual Cypher test commands
- [E2E Guide](run-all-e2e.md) -- Running the full E2E suite
- [SDK Changes](sdk-notebook-changes.md) -- SDK modifications for HSBC
