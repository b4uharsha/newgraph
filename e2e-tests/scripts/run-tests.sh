#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
E2E_DIR="$(dirname "$SCRIPT_DIR")"
REPO_ROOT="$(git rev-parse --show-toplevel)"

# Parse arguments
CLUSTER=""
EXEC="local"
NOTEBOOK=""
WORKERS="auto"

while [[ $# -gt 0 ]]; do
    case $1 in
        --cluster=*) CLUSTER="${1#*=}" ;;
        --exec=*) EXEC="${1#*=}" ;;
        --notebook=*) NOTEBOOK="${1#*=}" ;;
        --workers=*) WORKERS="${1#*=}" ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
    shift
done

# Validate CLUSTER is provided
if [[ -z "$CLUSTER" ]]; then
    echo "ERROR: CLUSTER is required"
    echo "Usage: $0 --cluster=orbstack|gke-london [--exec=local|job|jupyter] [--notebook=<name>]"
    exit 1
fi

# Load cluster configuration
CLUSTER_FILE="$E2E_DIR/clusters/${CLUSTER}.env"
if [[ ! -f "$CLUSTER_FILE" ]]; then
    echo "ERROR: Unknown cluster '$CLUSTER'"
    echo "Available: $(ls -1 "$E2E_DIR/clusters/" 2>/dev/null | sed 's/.env$//' | tr '\n' ' ')"
    exit 1
fi

# Export cluster config
set -a
source "$CLUSTER_FILE"
set +a

# Switch to correct kubectl context if specified
if [[ -n "${KUBE_CONTEXT:-}" ]]; then
    CURRENT_CONTEXT=$(kubectl config current-context 2>/dev/null || echo "")
    if [[ "$CURRENT_CONTEXT" != "$KUBE_CONTEXT" ]]; then
        echo "Switching kubectl context: $CURRENT_CONTEXT → $KUBE_CONTEXT"
        if ! kubectl config use-context "$KUBE_CONTEXT" &>/dev/null; then
            echo "ERROR: Failed to switch to context '$KUBE_CONTEXT'"
            echo "Available contexts: $(kubectl config get-contexts -o name | tr '\n' ' ')"
            exit 1
        fi
    fi
fi

# Load persona tokens from Kubernetes Secret (only when secret exists)
# ADR-104/105: X-Username header identity replaces JWT tokens.
SECRET_NAME="e2e-persona-tokens"
NAMESPACE="${GRAPH_OLAP_NAMESPACE:-graph-olap-local}"

if kubectl get secret "$SECRET_NAME" -n "$NAMESPACE" &>/dev/null; then
    echo "Loading persona tokens from K8s secret $SECRET_NAME in namespace $NAMESPACE"
    eval "$(kubectl get secret "$SECRET_NAME" -n "$NAMESPACE" -o json | \
        jq -r '.data | to_entries[] | "export \(.key)=\(.value | @base64d)"')"
else
    echo "No persona token secret found — using X-Username header identity (ADR-104)"
fi

# Load Starburst Galaxy credentials from K8s secret (ADR-119)
if kubectl get secret starburst-credentials -n "$NAMESPACE" &>/dev/null; then
    export STARBURST_USER="graph-olap-e2e@hsbcgraph.galaxy.starburst.io"
    export STARBURST_PASSWORD=$(kubectl get secret starburst-credentials -n "$NAMESPACE" -o jsonpath='{.data.password}' | base64 -d)
    echo "Loaded Starburst credentials from K8s secret"

    # Pre-warm Starburst Galaxy cluster (auto-suspends after 5 min idle)
    echo "Pre-warming Starburst cluster..."
    python3 -c "from graph_olap.notebook import wake_starburst; wake_starburst(timeout=90)" || true
fi

# E2E Cleanup via SDK — uses admin_carol bulk_delete for reliable cleanup.
# This runs OUTSIDE pytest (after all workers are done), so no cross-worker
# interference. Deletes: instances -> snapshots -> mappings (dependency order).
sdk_cleanup() {
    local phase="$1"  # "PRE-TEST" or "POST-TEST"

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "E2E Cleanup: $phase (SDK bulk_delete via admin_carol)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    python3 -c "
import sys, os
from graph_olap import GraphOLAPClient

api_url = '${GRAPH_OLAP_API_URL}'
client = GraphOLAPClient(
    api_url=api_url,
    username='analyst_alice@e2e.local',
    use_case_id=os.environ.get('GRAPH_OLAP_USE_CASE_ID'),
)

# Check current state
instances = client.instances.list(limit=200)
mappings = client.mappings.list(limit=200)
print(f'Found {len(instances.items)} instance(s), {len(mappings)} mapping(s)')

if len(instances.items) == 0 and len(mappings) == 0:
    print('Nothing to clean up')
    client.close()
    sys.exit(0)

# Phase 1: Terminate all instances (cascade-deletes snapshots)
terminated = 0
for inst in instances.items:
    try:
        client.instances.terminate(inst.id)
        terminated += 1
    except Exception:
        pass
print(f'Phase 1: terminated {terminated} instance(s)')

# Phase 2: Delete all mappings (snapshots were cascade-deleted)
deleted = 0
for m in mappings:
    try:
        client.mappings.delete(m.id)
        deleted += 1
    except Exception:
        pass
print(f'Phase 2: deleted {deleted} mapping(s)')

# Verify
remaining_m = len(client.mappings.list(limit=10))
remaining_i = len(client.instances.list(limit=10).items)
print(f'Remaining: {remaining_m} mapping(s), {remaining_i} instance(s)')
if remaining_m > 0 or remaining_i > 0:
    print('WARNING: Some resources could not be cleaned up')

client.close()
" || echo "WARNING: SDK cleanup failed, continuing..."
    echo ""
}

# Build pytest args
# ADR-117 + ADR-100 tuning: Real-time visibility, fail fast, full diagnostics
#   -s              : no stdout capture — real-time papermill output
#   -x              : stop on first failure (ALL modes — fail fast always)
#   --tb=long       : full tracebacks for diagnosis (not truncated)
#   --showlocals    : print local variables at point of failure
#   --log-cli-level : DEBUG shows HTTP requests, SQL queries, GCS operations in real time
#                     INFO was hiding SDK internals; WARNING was squelching everything
#   --durations=0   : timing summary at end — spot slow tests
# NOTE: -v is already in pyproject.toml addopts — not duplicated here
PYTEST_ARGS="-s -x --tb=long --showlocals --log-cli-level=DEBUG --durations=0"
if [[ -n "$NOTEBOOK" ]]; then
    # Run specific test — NO xdist (single-test = no buffering)
    # Accepts notebook names (04_cypher_basics) or Python test names (lifecycle_settings)
    TEST_NUM=$(echo "$NOTEBOOK" | grep -oE '^[0-9]+' || true)
    if [[ -n "$TEST_NUM" ]]; then
        # Notebook name (starts with number): match test_04, test_05, etc.
        PYTEST_ARGS="$PYTEST_ARGS -k test_${TEST_NUM}"
    else
        # Python test name or keyword: pass directly to -k
        PYTEST_ARGS="$PYTEST_ARGS -k ${NOTEBOOK}"
    fi
elif [[ "$WORKERS" == "1" ]]; then
    # WORKERS=1 — run without xdist (zero overhead, unbuffered output)
    true  # -x already in PYTEST_ARGS
else
    # Multiple workers — use xdist for parallel execution
    # -x still applies: any error = immediate exit for all workers
    PYTEST_ARGS="$PYTEST_ARGS -n $WORKERS --dist=loadgroup"
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "E2E Test Runner"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Cluster:  $CLUSTER ($GRAPH_OLAP_API_URL)"
echo "  Exec:     $EXEC"
echo "  Notebook: ${NOTEBOOK:-all}"
echo "  Workers:  $WORKERS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Execute based on method
case "$EXEC" in
    local)
        # Run pre-flight checks for local OrbStack
        if [[ "$CLUSTER" == "orbstack" && "${VALIDATE_DEPLOYMENT:-false}" == "true" ]]; then
            if [[ -f "$REPO_ROOT/tools/local-dev/scripts/validate-test-freshness.sh" ]]; then
                "$REPO_ROOT/tools/local-dev/scripts/validate-test-freshness.sh"
            fi
        fi

        # Clean stale xdist worker counter files from previous interrupted runs
        rm -f /tmp/e2e_worker_counter /tmp/e2e_worker_counter.lock 2>/dev/null || true

        # Cleanup: only for full-suite runs (not single-notebook dev iterations)
        if [[ -z "$NOTEBOOK" ]]; then
            sdk_cleanup "PRE-TEST"
        fi

        # Kill orphaned wrapper pods from previous runs (prevents resource exhaustion)
        echo "Cleaning orphaned wrapper pods..."
        kubectl delete pods -n "$NAMESPACE" -l app=ryugraph-wrapper --ignore-not-found 2>/dev/null || true
        kubectl delete pods -n "$NAMESPACE" -l app=falkordb-wrapper --ignore-not-found 2>/dev/null || true
        kubectl delete svc -n "$NAMESPACE" -l app=ryugraph-wrapper --ignore-not-found 2>/dev/null || true
        kubectl delete svc -n "$NAMESPACE" -l app=falkordb-wrapper --ignore-not-found 2>/dev/null || true
        echo "Wrapper cleanup done"

        # Wake Starburst immediately before pytest (not earlier — cluster auto-suspends after 5 min)
        if [[ -n "$STARBURST_USER" && -n "$STARBURST_PASSWORD" ]]; then
            echo "Waking Starburst cluster (right before tests)..."
            python3 -c "from graph_olap.notebook import wake_starburst; wake_starburst(timeout=90)" || true
        fi

        # Run tests and capture exit code
        TEST_EXIT=0
        cd "$E2E_DIR" && pytest tests/ $PYTEST_ARGS || TEST_EXIT=$?

        # Always clean up after full-suite runs (all pytest workers are done here)
        if [[ -z "$NOTEBOOK" ]]; then
            sdk_cleanup "POST-TEST"
        fi

        exit $TEST_EXIT
        ;;
    job)
        "$SCRIPT_DIR/exec-job.sh" --cluster="$CLUSTER" --pytest-args="$PYTEST_ARGS"
        ;;
    jupyter)
        "$SCRIPT_DIR/exec-jupyter.sh" --cluster="$CLUSTER" --pytest-args="$PYTEST_ARGS"
        ;;
    *)
        echo "ERROR: Unknown exec method '$EXEC'"
        echo "Available: local, job, jupyter"
        exit 1
        ;;
esac
