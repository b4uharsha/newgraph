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
JOB_NAME="e2e-test-$(date +%Y%m%d-%H%M%S)"

# E2E Cleanup API function - cleans up all test resources via control-plane API
call_cleanup_api() {
    local phase="$1"  # "PRE-TEST" or "POST-TEST"

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "E2E Cleanup: $phase (Job Mode)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # Use OPS_DAVE persona for cleanup (has ops role)
    if [[ -z "${GRAPH_OLAP_API_KEY_OPS_DAVE:-}" ]]; then
        echo "WARNING: GRAPH_OLAP_API_KEY_OPS_DAVE not set, skipping API cleanup"
        return 0
    fi

    local cleanup_url="${GRAPH_OLAP_API_URL}/api/admin/e2e-cleanup"
    local response
    local http_code

    # Call cleanup API with 5-minute timeout
    response=$(curl -sf -X DELETE --max-time 300 \
        -H "Authorization: Bearer $GRAPH_OLAP_API_KEY_OPS_DAVE" \
        -H "Content-Type: application/json" \
        -w "\n%{http_code}" \
        "$cleanup_url" 2>&1) || true

    # Extract HTTP code (last line) and body (everything else)
    http_code=$(echo "$response" | tail -n1)
    local body=$(echo "$response" | sed '$d')

    if [[ "$http_code" == "200" ]]; then
        echo "Cleanup successful:"
        echo "$body" | jq '.data' 2>/dev/null || echo "$body"
    elif [[ "$http_code" == "401" || "$http_code" == "403" ]]; then
        echo "WARNING: Cleanup API returned $http_code (auth failed), continuing..."
    else
        echo "WARNING: Cleanup API returned $http_code, continuing..."
        echo "$body" | head -5
    fi
    echo ""
}

# PRE-TEST cleanup via API
call_cleanup_api "PRE-TEST"

echo "Creating K8s Job: $JOB_NAME in namespace $NAMESPACE"

# Create job manifest
cat <<EOF | kubectl apply -f -
apiVersion: batch/v1
kind: Job
metadata:
  name: $JOB_NAME
  namespace: $NAMESPACE
spec:
  ttlSecondsAfterFinished: 3600
  backoffLimit: 0
  template:
    spec:
      restartPolicy: Never
      containers:
      - name: e2e-tests
        image: ghcr.io/hsbc-graph/e2e-tests:latest
        env:
        - name: GRAPH_OLAP_API_URL
          value: "$GRAPH_OLAP_API_URL"
        - name: PYTEST_ARGS
          value: "$PYTEST_ARGS"
        envFrom:
        - secretRef:
            name: e2e-api-tokens
            optional: true
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "2000m"
EOF

echo "Waiting for job to complete..."
kubectl wait --for=condition=complete --timeout=1800s "job/$JOB_NAME" -n "$NAMESPACE" || {
    echo "Job failed or timed out. Fetching logs..."
    kubectl logs "job/$JOB_NAME" -n "$NAMESPACE" --tail=200
    echo ""
    echo "Tests failed - skipping POST-TEST cleanup to preserve state"
    echo "Run cleanup manually: curl -X DELETE -H 'Authorization: Bearer \$GRAPH_OLAP_API_KEY_OPS_DAVE' ${GRAPH_OLAP_API_URL}/api/admin/e2e-cleanup"
    exit 1
}

echo "Job completed successfully. Fetching logs..."
kubectl logs "job/$JOB_NAME" -n "$NAMESPACE"

# POST-TEST cleanup via API (only runs on success)
call_cleanup_api "POST-TEST"
