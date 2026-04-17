# E2E Test Runner - Agent Reference

## Command Pattern

```
make test CLUSTER=<cluster> [EXEC=<exec>] [NOTEBOOK=<notebook>]
```

## Parameter Validation Rules

1. CLUSTER is REQUIRED - always specify
2. EXEC defaults to "local" if omitted
3. NOTEBOOK is optional - omit to run all tests

## Decision Tree: Which Command to Use

```
User wants to run E2E tests
├── Which cluster?
│   ├── Local development → CLUSTER=orbstack
│   └── GKE London staging → CLUSTER=gke-london
│
├── Where to execute?
│   ├── On my laptop (default) → EXEC=local (or omit)
│   ├── As K8s Job in cluster → EXEC=job
│   └── Inside Jupyter pod → EXEC=jupyter
│
└── What to run?
    ├── Everything → (omit NOTEBOOK)
    └── Single specific test → NOTEBOOK=<name>
```

## Valid CLUSTER Values

| Value | Use When |
|-------|----------|
| `orbstack` | Testing locally, OrbStack running, stack deployed |
| `gke-london` | Testing against GKE London demo cluster |

## Valid EXEC Values

| Value | Use When |
|-------|----------|
| `local` | Default. Run pytest process on current machine |
| `job` | Need isolated execution, CI/CD, or no local Python |
| `jupyter` | Interactive debugging, need cluster-internal access |

## Valid NOTEBOOK Values

NOTEBOOK = notebook name without .ipynb extension. Runs ONE specific notebook.

| NOTEBOOK | Description |
|----------|-------------|
| `01_prerequisites` | Setup verification |
| `02_health_checks` | Health endpoints |
| `03_managing_resources` | CRUD operations |
| `04_cypher_basics` | Cypher queries |
| `05_exploring_schemas` | Schema introspection |
| `06_graph_algorithms` | Graph algorithms |
| `07_end_to_end_workflows` | E2E workflows |
| `08_quick_start` | Quick start API |
| `09_handling_errors` | Error handling |
| `10_bookmarks` | Favorites feature |
| `11_instance_lifecycle` | TTL management |
| `12_export_data` | Data export |
| `13_advanced_mappings` | Complex mappings |
| `14_version_diffing` | Schema diffing |
| `15_background_jobs` | Async operations |
| `16_falkordb` | FalkorDB wrapper |
| `17_authorization` | RBAC tests |
| `18_admin_operations` | Admin API |
| `19_ops_configuration` | Ops config (SERIAL) |

## Common Workflows

### Run all tests locally against OrbStack
```bash
make test CLUSTER=orbstack
```

### Test specific notebook you just modified
```bash
make test CLUSTER=orbstack NOTEBOOK=04_cypher_basics
make test CLUSTER=orbstack NOTEBOOK=14_version_diffing
```

### Full regression on GKE
```bash
make test CLUSTER=gke-london
```

### CI/CD pipeline
```bash
make test CLUSTER=gke-london EXEC=job
```

### Debug failing test interactively
```bash
make test CLUSTER=gke-london EXEC=jupyter NOTEBOOK=17_authorization
```

## Error Recovery

### Error: "CLUSTER is required"
**Cause:** Missing CLUSTER parameter
**Fix:** Add CLUSTER=orbstack or CLUSTER=gke-london

### Error: "Unknown cluster 'xyz'"
**Cause:** Invalid cluster name
**Fix:** Use one of: orbstack, gke-london

### Error: "Unknown notebook"
**Cause:** Invalid notebook name
**Fix:** Run `make test-list` to see available notebooks

### Error: "API key not set"
**Cause:** GKE cluster requires authentication
**Fix:** Export GRAPH_OLAP_API_KEY_ANALYST_ALICE and other persona keys

### Error: "validate-test-freshness.sh failed"
**Cause:** Local OrbStack deployment is stale
**Fix:** Run `make rebuild` in tools/local-dev first

### Error: "Jupyter pod not found"
**Cause:** No Jupyter pod in target cluster
**Fix:** Deploy Jupyter first or use EXEC=local

## Prerequisites by Execution Method

### EXEC=local (default)
- Python 3.10+ with pytest, papermill installed
- For CLUSTER=orbstack: OrbStack running, stack deployed
- For CLUSTER=gke-*: API tokens set in environment

### EXEC=job
- kubectl configured for target cluster
- Permission to create Jobs in namespace
- e2e-api-token secret exists in cluster

### EXEC=jupyter
- kubectl configured for target cluster
- Jupyter pod running in cluster
- Permission to exec into pod
