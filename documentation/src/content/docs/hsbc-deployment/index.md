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
- **API Endpoint:** `https://<HSBC_API_HOST>` (HSBC-provisioned ingress FQDN for control-plane)
- **Docs:** `https://<DOCS_URL>` (HSBC-provisioned ingress FQDN for documentation service)

## Services

| Service | Port | Health |
|---------|------|--------|
| control-plane | 8080 | /health |
| export-worker | — (no HTTP) | — |
| falkordb-wrapper | 8000 | /health |
| ryugraph-wrapper | 8000 | /health |
| wrapper-proxy | 8080 | /healthz |
| documentation | 8000 | / |

## Prerequisites

Before the first deploy, run `./cd/create-secrets.sh` once to provision secrets
from GCP Secret Manager into the `graph-olap-platform` namespace. `deploy.sh`
explicitly skips any `*-secrets.yaml` files during the apply loop, so these
secrets must already exist in-cluster before the deploy runs.

## Quick Commands

```bash
# Check all pods
kubectl get pods -n graph-olap-platform

# Deploy all services (signature: <service|all> <image-tag>)
cd cd/ && ./deploy.sh all hash-abc1234

# Deploy a single service (hot-reload style)
cd cd/ && ./deploy.sh control-plane hash-abc1234

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
