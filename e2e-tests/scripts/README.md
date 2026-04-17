# E2E Test Runner

Unified interface for running E2E tests across different clusters and execution methods.

## Quick Start

```bash
# Run all tests against local OrbStack
make test CLUSTER=orbstack

# Run all tests against GKE London
make test CLUSTER=gke-london

# Run single notebook
make test CLUSTER=orbstack NOTEBOOK=04_cypher_basics
```

## Parameters

| Parameter | Required | Values | Description |
|-----------|----------|--------|-------------|
| `CLUSTER` | Yes | `orbstack`, `gke-london` | Target cluster API |
| `EXEC` | No | `local`, `job`, `jupyter` | Where tests run (default: `local`) |
| `NOTEBOOK` | No | See below | Run single notebook (omit for all) |

### Clusters

| Cluster | API URL | Description |
|---------|---------|-------------|
| `orbstack` | http://localhost:30081 | Local OrbStack Kubernetes |
| `gke-london` | https://control-plane-graph-olap-platform.hsbc-12636856-udlhk-dev.dev.gcp.cloud.hk.hsbc | GKE London demo |

### Execution Methods

| Method | Description |
|--------|-------------|
| `local` | Run pytest on your machine (default) |
| `job` | Deploy as K8s Job in target cluster |
| `jupyter` | Run inside Jupyter pod in cluster |

### Notebooks

Use notebook name (without .ipynb):

```bash
NOTEBOOK=01_prerequisites
NOTEBOOK=04_cypher_basics
NOTEBOOK=13_advanced_mappings
NOTEBOOK=17_authorization
```

Run `make test-list` for full list.

## Prerequisites

### For OrbStack (local)
- OrbStack with Kubernetes running
- Stack deployed: `make deploy TARGET=local`

### For GKE
- API tokens set:
  ```bash
  export GRAPH_OLAP_API_KEY_ANALYST_ALICE=<token>
  export GRAPH_OLAP_API_KEY_ANALYST_BOB=<token>
  export GRAPH_OLAP_API_KEY_ADMIN_CAROL=<token>
  export GRAPH_OLAP_API_KEY_OPS_DAVE=<token>
  ```

### For EXEC=job or EXEC=jupyter
- kubectl context set to target cluster
- Appropriate permissions to create Jobs / exec into pods

## Examples

```bash
# Run all tests locally against OrbStack
make test CLUSTER=orbstack

# Run single notebook
make test CLUSTER=orbstack NOTEBOOK=04_cypher_basics

# Full regression on GKE
make test CLUSTER=gke-london

# CI/CD - isolated job execution
make test CLUSTER=gke-london EXEC=job

# Debug in Jupyter
make test CLUSTER=gke-london EXEC=jupyter NOTEBOOK=16_falkordb
```

## Troubleshooting

### "CLUSTER is required"
You must specify which cluster to target:
```bash
make test CLUSTER=orbstack
```

### "Unknown notebook"
Check notebook name with `make test-list`. Use name without .ipynb extension.

### API key errors on GKE
Set the persona tokens:
```bash
export GRAPH_OLAP_API_KEY_ANALYST_ALICE=$(kubectl get secret ...)
```
