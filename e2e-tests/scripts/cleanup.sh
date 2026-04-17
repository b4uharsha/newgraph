#!/usr/bin/env bash
# =============================================================================
# E2E Test Cleanup Script
# =============================================================================
# Cleans up all E2E test resources via the control-plane API.
#
# Usage:
#   ./cleanup.sh --cluster=orbstack
#   ./cleanup.sh --cluster=gke-london
#
# Or via Makefile:
#   make test-clean CLUSTER=gke-london
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
E2E_DIR="$(dirname "$SCRIPT_DIR")"

# Parse arguments
CLUSTER=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --cluster=*) CLUSTER="${1#*=}" ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
    shift
done

# Validate CLUSTER is provided
if [[ -z "$CLUSTER" ]]; then
    echo "ERROR: CLUSTER is required"
    echo "Usage: $0 --cluster=orbstack|gke-london"
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

# Load persona tokens from Kubernetes Secret (single source of truth)
SECRET_NAME="e2e-persona-tokens"
NAMESPACE="${GRAPH_OLAP_NAMESPACE:-graph-olap-local}"

echo "Loading persona tokens from K8s secret $SECRET_NAME in namespace $NAMESPACE"
if ! kubectl get secret "$SECRET_NAME" -n "$NAMESPACE" &>/dev/null; then
    echo "ERROR: Secret '$SECRET_NAME' not found in namespace '$NAMESPACE'"
    exit 1
fi

# Export all keys from the secret as environment variables
eval "$(kubectl get secret "$SECRET_NAME" -n "$NAMESPACE" -o json | \
    jq -r '.data | to_entries[] | "export \(.key)=\(.value | @base64d)"')"

# Call cleanup API
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "E2E Cleanup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Cluster: $CLUSTER"
echo "  API URL: $GRAPH_OLAP_API_URL"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Use OPS_DAVE persona for cleanup (has ops role)
if [[ -z "${GRAPH_OLAP_API_KEY_OPS_DAVE:-}" ]]; then
    echo "ERROR: GRAPH_OLAP_API_KEY_OPS_DAVE not set"
    exit 1
fi

cleanup_url="${GRAPH_OLAP_API_URL}/api/admin/e2e-cleanup"

# Call cleanup API with 5-minute timeout
response=$(curl -sf -X DELETE --max-time 300 \
    -H "Authorization: Bearer $GRAPH_OLAP_API_KEY_OPS_DAVE" \
    -H "Content-Type: application/json" \
    -w "\n%{http_code}" \
    "$cleanup_url" 2>&1) || true

# Extract HTTP code (last line) and body (everything else)
http_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | sed '$d')

if [[ "$http_code" == "200" ]]; then
    echo "Cleanup successful:"
    echo "$body" | jq '.data' 2>/dev/null || echo "$body"
    exit 0
elif [[ "$http_code" == "401" || "$http_code" == "403" ]]; then
    echo "ERROR: Cleanup API returned $http_code (authentication failed)"
    echo "$body" | head -10
    exit 1
else
    echo "ERROR: Cleanup API returned $http_code"
    echo "$body" | head -10
    exit 1
fi
