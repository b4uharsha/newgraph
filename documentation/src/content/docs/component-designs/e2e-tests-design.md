---
title: "E2E Tests Design"
scope: hsbc
---

<!-- Verified against code on 2026-04-20 -->

# E2E Tests Design

## Overview

The E2E test suite validates the full Graph OLAP stack running on the HSBC development cluster (`hsbc-12636856-udlhk-dev`). Tests run as a Kubernetes Job inside the target cluster and exercise real wrapper pods, real Control Plane, and real Starburst exports end-to-end via the SDK.

**Execution model:** E2E runs are launched via `kubectl apply -f cd/jobs/e2e-test-job.yaml` against the target HSBC cluster. The Job authenticates to the in-cluster Control Plane service, drives the full mapping → snapshot → instance → query lifecycle via the SDK, and tears down its own resources on completion.

**Isolation:** Each conformance run uses a dedicated, short-lived namespace suffix so resource names cannot collide with other tenants of `graph-olap-platform`. Cleanup runs before and after the suite.

## Prerequisites

Documents to read first:

- [requirements.md](--/foundation/requirements.md) - Functional requirements being tested
- [architectural.guardrails.md](--/foundation/architectural.guardrails.md) - Constraints the tests verify
- [system.architecture.design.md](--/system-design/system.architecture.design.md) - Component interactions
- [control-plane.design.md](-/control-plane.design.md) - Control Plane API under test
- [ryugraph-wrapper.design.md](-/ryugraph-wrapper.design.md) - Wrapper API under test

## Scope

Conformance tests must cover:

1. **Control Plane API contract** — CRUD over mappings, snapshots, instances; favourites; `/api/schema/*` browse/search; internal status/metrics callbacks.
2. **Wrapper API contract** — `/query`, `/algo/{name}`, `/networkx/{name}`, `/subgraph`, `/lock`, `/schema`, `/health`, `/status`, `/shutdown`.
3. **Pod lifecycle** — instance provisioning, termination, orphan reconciliation.
4. **Export workflow** — Starburst UNLOAD submission, poll, Parquet landing in the target GCS bucket.

Tests MUST run exclusively against in-cluster services; they MUST NOT depend on any developer-workstation tooling or dev-cluster artefacts.

## Constraints

1. **In-cluster execution** — Conformance runs MUST execute as a Kubernetes Job inside the target HSBC cluster. K8s service DNS is the only supported way to reach Control Plane and wrapper pods.
2. **SDK-only interaction** — All resource manipulation MUST go through the SDK. No direct database seeding, no direct kubectl mutation of Control Plane state, no direct Starburst query submission outside the Export Worker.
3. **Dynamic test data** — Mappings, snapshots, and instances MUST be created by the test at runtime and cleaned up at the end. No hardcoded IDs.
4. **Short-lived namespace suffix** — Resource names MUST use a unique prefix per run (`{TestPrefix}-{ResourceType}-{uuid}`) so parallel runs and retries cannot clash.
5. **Real dependencies** — The Job hits the real Control Plane, real Ryugraph/FalkorDB wrappers, real Starburst (via Export Worker), and real GCS bucket configured on the cluster. There is no emulator in the supported execution path.

## Notebook Organisation

The E2E suite is implemented as a set of Jupyter notebooks executed via papermill. Notebooks serve as both executable tests and documentation.

```
┌─────────────────────────────────────────────────────────┐
│  Kubernetes Cluster                                     │
│  ┌─────────────────────────────────────────────────┐   │
│  │  e2e-test namespace                              │   │
│  │                                                  │   │
│  │  ┌─────────────┐   K8s DNS   ┌───────────────┐  │   │
│  │  │ e2e-tests   │────────────▶│ control-plane │  │   │
│  │  │ Job         │             │ :8080         │  │   │
│  │  │             │             └───────────────┘  │   │
│  │  │ pytest      │                                │   │
│  │  │ IN_CLUSTER  │   K8s DNS   ┌───────────────┐  │   │
│  │  │ =true       │────────────▶│ ryugraph-     │  │   │
│  │  │             │             │ wrapper:8000  │  │   │
│  │  └─────────────┘             └───────────────┘  │   │
│  │                                                  │   │
│  │                  K8s DNS     ┌───────────────┐  │   │
│  │                 ───────────▶│ fake-gcs      │  │   │
│  │                              │ :4443         │  │   │
│  │                              └───────────────┘  │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### Notebook Organization (Three-Tier Hierarchy)

**Reference:** ADR-092: Three-Tier Notebook Documentation Hierarchy

Notebook source of truth today is a single flat tier — 20 numbered
platform-test notebooks used as both E2E tests and documentation. The
three-tier ``docs/notebooks/{tutorials,reference,examples}`` hierarchy below
is **planned** (ADR-092) but not yet populated on ``main``.

```
tests/e2e/notebooks/
└── platform-tests/      # Pure E2E tests (20 notebooks; see table below)

docs/notebooks/          # (PLANNED — not yet populated)
├── tutorials/           # Learning-focused, step-by-step
├── reference/           # Task-focused, API documentation
└── examples/            # Real-world use cases
```

**Tier Definitions:**

| Tier | Purpose | Style | Length |
|------|---------|-------|--------|
| **Platform Tests** | E2E validation | Assertions, coverage | Variable |
| **Tutorials** (planned) | Teach concepts | Narrative, step-by-step | 15-30 min |
| **Reference** (planned) | Document APIs | Structured, comprehensive | Variable |
| **Examples** (planned) | Show applications | Real-world, complete | 20-45 min |

---

### Module Structure

The actual on-disk layout uses numbered notebooks under
`tests/e2e/notebooks/platform-tests/`. Execution order is encoded in the
filename prefix (01–20), not in a manifest mapping abstract names.

```
tests/e2e/                          # E2E test module
├── pyproject.toml                  # Dependencies (pytest-xdist, pytest-order, papermill)
├── notebooks.yaml                  # Test manifest (execution order, groups)
├── cleanup_before_tests.py         # Pre-flight cleanup for cloud
├── entrypoint.sh                   # Container entry point
├── notebooks/
│   └── platform-tests/             # 20 numbered E2E notebooks
│       ├── 01_prerequisites.ipynb
│       ├── 02_health_checks.ipynb
│       ├── 03_managing_resources.ipynb
│       ├── 04_cypher_basics.ipynb
│       ├── 05_exploring_schemas.ipynb
│       ├── 06_graph_algorithms.ipynb
│       ├── 07_end_to_end_workflows.ipynb
│       ├── 08_quick_start.ipynb
│       ├── 09_handling_errors.ipynb
│       ├── 10_bookmarks.ipynb
│       ├── 11_instance_lifecycle.ipynb
│       ├── 13_advanced_mappings.ipynb
│       ├── 14_version_diffing.ipynb
│       ├── 15_background_jobs.ipynb
│       ├── 16_falkordb.ipynb
│       ├── 17_authorization.ipynb
│       ├── 18_admin_operations.ipynb
│       ├── 19_ops_configuration.ipynb
│       └── 20_schema_cache.ipynb
└── tests/
    ├── conftest.py                # Pre-flight cleanup fixture
    └── test_notebook_execution.py # Notebook driver with try/finally cleanup
```

### Test Notebook Manifest (`notebooks.yaml`)

Execution order, grouping, and conditional execution are defined declaratively:

```yaml
version: 1
notebooks:
  - path: platform-tests/01_prerequisites.ipynb
    group: prerequisites
    order: 1

  - path: platform-tests/02_health_checks.ipynb
    group: core
    parallel: true

  - path: platform-tests/17_authorization.ipynb
    group: auth
    skip_if: SINGLE_USER_MODE

config:
  timeout: 300
  workers: 2
  retry: 1
```

| Field | Description |
|---|---|
| `order` | Explicit execution order |
| `group` | Logical grouping used by pytest-xdist `--dist=loadgroup` |
| `parallel` | Enable parallel execution within group |
| `skip_if` | Conditional skip based on env var |
| `depends_on` | Wait for another group to complete before starting |

### Notebook Responsibilities and Isolation

See `tests/e2e/notebooks/platform-tests/` for the 20 numbered platform-tests notebooks (`01_prerequisites.ipynb` through `20_schema_cache.ipynb` per ADR-139). Each notebook's purpose is described in its own header cell; the test harness executes them sequentially in filename order.

xdist grouping (`instance_lock`, `global_state`, `smoke`, `crud`, `query`, `validation`) is applied via `notebooks.yaml`, not via the filename. `instance_lock` and `global_state` groups run sequentially because the wrapper holds a per-instance lock during algorithm execution and ops tests mutate global config.

## Test Data Strategy

Test data is created dynamically via the SDK at runtime. There is no database seeding.

- **Users**: Auto-created in Control Plane when requests arrive with the `X-Username` header. Roles are stored in the database (ADR-104); no per-request role header is used.
- **Resources**: Mapping, snapshot, and instance are created via SDK fixtures before tests run. IDs are returned at runtime and never hardcoded.
- **Graph shape**: Small deterministic social-network fixture (5 Person nodes, 6 KNOWS edges) against a known Starburst table. Exports are driven by the Export Worker and land in the real GCS bucket wired into the cluster.

### Naming Convention

Resources follow the pattern `{TestPrefix}-{ResourceType}-{uuid}`. Each numbered platform-tests notebook picks a prefix appropriate to its scope; the canonical allow-list of prefixes recognised by the lifecycle-job cleanup safety net is:

`Test-`, `SmokeTest`, `CrudTest`, `AlgoTest`, `AuthTest`, `OpsTest`, `ValTest`, `WorkflowTest`, `ExportTest`, `AdminTest`

See `packages/control-plane/src/control_plane/jobs/lifecycle.py` for the authoritative list and `tests/e2e/tests/test_notebook_execution.py::_extract_test_prefix()` for the per-notebook mapping. Production resources never use these prefixes.

## Cleanup Strategy

Cleanup follows the test-framework-owns-cleanup pattern with three independent layers.

### Layer 1: Test Runner Cleanup (primary)

Implemented in `tests/test_notebook_execution.py::_execute_notebook()` using `try/finally`:

```python
def _execute_notebook(notebook_name: str, parameters: dict, ...) -> None:
    test_prefix = _extract_test_prefix(notebook_name)
    username = parameters.get("USERNAME", "e2e-test-user")

    try:
        pm.execute_notebook(
            input_path=notebook_path,
            output_path=output_path,
            parameters=parameters,
            execution_timeout=execution_timeout,
        )
    except pm.PapermillExecutionError as e:
        pytest.fail(f"Notebook execution failed: {e}")
    finally:
        _cleanup_test_resources(
            username=username,
            test_prefix=test_prefix,
            max_age_minutes=30,
        )
```

Cleanup runs whether the notebook passed or failed. It lists instances, snapshots, and mappings, filters by prefix + username + age, and deletes in reverse-dependency order (instances → snapshots → mappings).

Context managers cannot be used here because papermill's cell-by-cell execution model stops immediately on the first failing cell, so any `__exit__` in a `with`-block would never run.

### Layer 2: Lifecycle Job Cleanup (safety net)

The Control Plane lifecycle job (`packages/control-plane/src/control_plane/jobs/lifecycle.py`) runs every 5 minutes and has a Phase 5 that deletes test resources older than 1 hour whose names match the known test prefixes (`Test-`, `SmokeTest`, `CrudTest`, `AlgoTest`, `AuthTest`, `OpsTest`, `ValTest`, `WorkflowTest`, `ExportTest`, `AdminTest`). This catches resources missed when the Job pod itself is killed mid-run.

### Layer 3: Pre-Test Cleanup

`tests/conftest.py::cleanup_orphaned_resources` (session fixture) and `cleanup_before_tests.py` (invoked from `entrypoint.sh`) delete any lingering test resources before the suite starts, so every run begins from a known baseline.

```bash
#!/bin/bash
set -e

echo "=== Pre-flight cleanup ==="
python cleanup_before_tests.py

echo "=== Running E2E tests ==="
pytest tests/ --tb=short -n ${WORKERS:-2} --dist=loadfile "$@"
```

### Deletion Order

```
1. Instances  (no dependents)
   ↓
2. Snapshots  (depend on mappings; instances depend on snapshots)
   ↓
3. Mappings   (snapshots depend on them)
```

All cleanup operations are idempotent — deleting a resource that no longer exists is treated as success.

### Adding a New Notebook

1. Add the notebook's test prefix to `_extract_test_prefix()` in `test_notebook_execution.py`.
2. If the prefix is new, add it to `test_patterns` in `lifecycle.py`.
3. Use the `{Prefix}-{ResourceType}-{uuid}` naming convention inside the notebook.
4. Pin a unique xdist group in `notebooks.yaml` so parallel runs behave predictably.

## Fixtures

Key fixtures exposed to notebooks via papermill parameters:

| Parameter | Value |
|-----------|-------|
| `CONTROL_PLANE_URL` | `http://control-plane.graph-olap-platform.svc.cluster.local:8080` |
| `WRAPPER_URL` | Resolved per-instance via SDK |
| `USERNAME` | `e2e-test-user` (default); other roles for auth/ops notebooks |
| `X_USERNAME` / `X_USER_ROLE` | HSBC in-cluster auth is header-based per ADR-104/105. The test scaffolding writes `X-Username` and `X-User-Role` headers on each request directly; there are no bearer tokens to fetch. |

Pytest-level fixtures used by `test_notebook_execution.py`:

| Fixture | Scope | Returns |
|---------|-------|---------|
| `sdk_client` | session | `GraphOLAPClient` connected to Control Plane via in-cluster DNS |
| `test_data` | session | `{"mapping_id", "snapshot_id", "instance_id", "gcs_path", ...}` created via SDK |
| `running_instance` | session | `Instance` object from `test_data` |
| `instance_connection` | session | `InstanceConnection` for queries against the wrapper |

No Kubernetes-client fixtures are required in the Job execution path; tests rely entirely on in-cluster DNS + the SDK.

## Execution

### Launching a Run

```bash
# Apply the Job to the target namespace
kubectl apply -f cd/jobs/e2e-test-job.yaml -n graph-olap-platform

# Stream logs until completion
kubectl logs -f job/e2e-tests -n graph-olap-platform

# Wait for terminal state
kubectl wait --for=condition=complete job/e2e-tests -n graph-olap-platform --timeout=1800s

# Clean up the Job (auto-deleted via ttlSecondsAfterFinished, but can be forced)
kubectl delete job e2e-tests -n graph-olap-platform
```

The Job spec sets:

- `backoffLimit: 0` — no silent retries; a failed run is a failed run.
- `ttlSecondsAfterFinished: 3600` — finished Jobs are auto-deleted after an hour.
- `restartPolicy: Never` — on failure, inspect the logs before resubmitting.

### Init Containers

The Job currently uses **no init containers**. Authentication in the E2E test harness uses the `X-Username` header set by the test scaffolding directly (ADR-104/105). There is no JWT token generation step; the harness writes the header value at call time. See `infrastructure/cd/jobs/e2e-test-job.yaml` for the authoritative spec — the Control-Plane readiness check is performed inline in the main container (via `curl $GRAPH_OLAP_API_URL/health` and an authenticated `curl -H "X-Username: ..." -H "X-User-Role: ..."` probe) rather than in a separate init container, to avoid busybox image-pull issues on the HSBC cluster which blocks Docker Hub.

### Parallel Execution

Tests use `pytest-xdist` with `--dist=loadgroup` to respect xdist group boundaries. Default is `WORKERS=2` (overridable via env var). Workers >2 overwhelm Starburst with concurrent export jobs, so do not raise this without coordinating with the Starburst operators.

| Group | Tests | Parallelism | Reason |
|-------|-------|-------------|--------|
| `smoke` | smoke_test | Sequential | Validates stack health first |
| `crud` | crud_test | Parallel | Self-contained resources |
| `query` | query_test | Parallel | Read-only |
| `validation` | validation_test | Parallel | Self-contained resources |
| `instance_lock` | algorithm_test, workflow_test | Sequential | Share wrapper's per-instance lock |
| `global_state` | authorization_test, ops_test | Sequential | Mutate global config |

### Environment Variables

| Variable | Required | Description |
|---|---|---|
| `CONTROL_PLANE_URL` | Yes | In-cluster Control Plane URL |
| `GRAPH_OLAP_API_URL` | Yes | Same as `CONTROL_PLANE_URL`; set by `e2e-test-job.yaml` for SDK/readiness-probe compatibility |
| `GRAPH_OLAP_IN_CLUSTER_MODE` | Yes | Set to `"true"` by the Job; SDK uses this to skip ingress/oauth2-proxy |
| `USERNAME` | No | Test user (default `e2e-test-user`); injected as the `X-Username` header by the test scaffolding (ADR-104/105) |
| `WORKERS` | No | pytest-xdist worker count (default `2`) |
| `SINGLE_USER_MODE` | No | If set, authorization notebooks are skipped |

## SDK-Only Testing Principle

All tests interact with the system exclusively through the SDK:

| Operation | SDK Method |
|---|---|
| Create mapping | `sdk_client.mappings.create()` |
| Create snapshot | `sdk_client.snapshots.create()` |
| Wait for snapshot | `sdk_client.snapshots.wait_until_ready()` |
| Create instance | `sdk_client.instances.create_and_wait()` |
| Execute query | `InstanceConnection.query()`, `.query_df()`, `.query_scalar()` |
| Get schema | `InstanceConnection.get_schema()` |
| Run algorithm | `InstanceConnection.algorithms.run_native()` / `run_networkx()` |

Direct HTTP calls, kubectl mutations, or Starburst SQL bypass mean the test is no longer exercising the contract that real clients use.

## Anti-Patterns

### Architectural

See [architectural.guardrails.md](--/foundation/architectural.guardrails.md) for the authoritative list. Highlights:

- Tests use PostgreSQL (matches production); data is created via SDK.
- Tests validate API contracts defined in the Control Plane and Wrapper specs.

### Component-Specific

- DO NOT share fixtures with component unit tests (isolation requirement).
- DO NOT seed the database directly.
- DO NOT hardcode resource IDs.
- DO NOT modify component source code from tests.
- DO NOT rely on wall-clock timing for synchronisation — use SDK `wait_until_*` helpers.
- DO NOT rely on fake GCS, trino-proxy, or any translation layer. E2E runs against real Starburst + real GCS as configured on the target cluster.
- DO NOT raise `WORKERS` above 2 without explicit coordination with the Starburst operators.

## Appendix: Dependencies

```toml
[project.dependencies]
pytest = ">=9.0.2"
pytest-asyncio = ">=1.3.0"
pytest-timeout = ">=2.4.0"
pytest-xdist = ">=3.8.0"
pytest-order = ">=1.3.0"

papermill = ">=2.6.0"
jupyter = ">=1.1.1"
ipykernel = ">=7.1.0"

graph-olap-sdk
graph-olap-schemas

httpx = ">=0.28.1"
pyarrow = ">=22.0.0"
polars = ">=1.36.1"
google-cloud-storage = ">=3.7.0"
```

## Appendix: Timeouts

| Operation | Timeout |
|-----------|---------|
| Individual notebook execution | 300s (override per notebook in `notebooks.yaml`) |
| Full Job run | 1800s |
| Snapshot wait | 600s |
| Instance wait | 300s |
| Pre-flight cleanup | 120s |

## Appendix: Container Artifacts

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .
RUN pip install --no-cache-dir pytest-json-report junit-xml

COPY conftest.py ./
COPY tests/ ./tests/

ENV IN_CLUSTER=true
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["pytest"]
CMD ["tests/", "-v", "--tb=short", "--junitxml=/results/junit.xml"]
```

### Kubernetes Job

The authoritative spec lives in `infrastructure/cd/jobs/e2e-test-job.yaml`. A condensed view:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: e2e-test
  namespace: graph-olap-platform
spec:
  backoffLimit: 0
  ttlSecondsAfterFinished: 3600
  template:
    spec:
      restartPolicy: Never
      # No initContainers — readiness check for control-plane is done inline
      # in the main container (see command below). This avoids busybox image
      # pull issues on the HSBC cluster which blocks Docker Hub.
      containers:
        - name: e2e-tests
          image: <registry>/e2e-tests:<tag>
          env:
            - name: GRAPH_OLAP_API_URL
              value: "http://control-plane-svc:8080"
            - name: GRAPH_OLAP_IN_CLUSTER_MODE
              value: "true"
          command:
            - /bin/bash
            - -c
            - |
              set -e
              # Inline readiness probes (no token generation — auth is X-Username header)
              curl -sf "$GRAPH_OLAP_API_URL/health"
              curl -sf -H "X-Username: alice@hsbc.com" -H "X-User-Role: analyst" \
                "$GRAPH_OLAP_API_URL/api/config"
              pytest tests/ -v --tb=short -n auto --dist=loadgroup
```

No JWT/bearer tokens are fetched or mounted. Per ADR-104/105, auth is carried on every request as `X-Username` + `X-User-Role` headers, which the test scaffolding sets directly.

## Open Questions

None currently.
