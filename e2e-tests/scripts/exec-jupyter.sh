#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
E2E_DIR="$(dirname "$SCRIPT_DIR")"
REPO_ROOT="$(git rev-parse --show-toplevel)"

# Parse arguments
CLUSTER=""
PYTEST_ARGS=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --cluster=*) CLUSTER="${1#*=}" ;;
        --pytest-args=*) PYTEST_ARGS="${1#*=}" ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
    shift
done

if [[ -z "$CLUSTER" ]]; then
    echo "ERROR: --cluster is required"
    exit 1
fi

# Load cluster configuration
CLUSTER_FILE="$E2E_DIR/clusters/${CLUSTER}.env"
source "$CLUSTER_FILE"

# Switch kubectl context if specified
if [[ -n "${KUBE_CONTEXT:-}" ]]; then
    echo "Switching to kubectl context: $KUBE_CONTEXT"
    kubectl config use-context "$KUBE_CONTEXT"
fi

NAMESPACE="${GRAPH_OLAP_NAMESPACE:-hsbc-graph}"

# Find Jupyter pod
JUPYTER_POD=$(kubectl get pods -n "$NAMESPACE" -l app=jupyter -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)

if [[ -z "$JUPYTER_POD" ]]; then
    echo "ERROR: No Jupyter pod found in namespace $NAMESPACE"
    echo "Ensure Jupyter is deployed: kubectl get pods -n $NAMESPACE -l app=jupyter"
    exit 1
fi

echo "Found Jupyter pod: $JUPYTER_POD"
echo "Executing tests inside pod..."

# Run pytest inside the Jupyter pod
kubectl exec -it "$JUPYTER_POD" -n "$NAMESPACE" -- bash -c "
    cd /home/jovyan/work/tests/e2e
    export GRAPH_OLAP_API_URL='$GRAPH_OLAP_API_URL'
    pytest tests/ $PYTEST_ARGS
"
