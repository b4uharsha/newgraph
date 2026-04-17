#!/usr/bin/env bash
# scripts/status.sh - Check deployment status for control-plane
#
# Usage:
#   ./status.sh --target=local       Check local OrbStack deployment
#   ./status.sh --target=gke-london  Check GKE London deployment
#
# Shows pod status, image tag, and recent logs on failure.

set -euo pipefail

# =============================================================================
# Configuration
# =============================================================================

IMAGE_NAME="control-plane"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# =============================================================================
# Colors
# =============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# =============================================================================
# Parse Arguments
# =============================================================================

TARGET=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --target=*) TARGET="${1#*=}" ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
    shift
done

if [[ -z "$TARGET" ]]; then
    echo "ERROR: --target is required"
    echo "Usage: ./status.sh --target=local|gke-london"
    exit 1
fi

# =============================================================================
# Target Configuration
# =============================================================================

get_namespace() {
    case "$1" in
        local) echo "graph-olap-local" ;;
        gke-london) echo "hsbc-graph" ;;
        *) echo "" ;;
    esac
}

get_kube_context() {
    case "$1" in
        local) echo "orbstack" ;;
        gke-london) echo "gke_hsbc-graph_europe-west2-a_hsbc-graph-london" ;;
        *) echo "" ;;
    esac
}

# =============================================================================
# Validation
# =============================================================================

validate_target() {
    case "$TARGET" in
        local|gke-london) ;;
        *)
            echo -e "${RED}[ERROR]${NC} Unknown target: $TARGET"
            echo "Valid targets: local, gke-london"
            exit 1
            ;;
    esac
}

# =============================================================================
# Context Setup
# =============================================================================

setup_context() {
    local context="$(get_kube_context "$TARGET")"

    if [[ -n "$context" ]]; then
        kubectl config use-context "$context" 2>/dev/null || true
    fi
}

# =============================================================================
# Status Functions
# =============================================================================

get_pod_status() {
    local namespace="$1"

    local status
    status=$(kubectl get pods -n "$namespace" -l "app=$IMAGE_NAME" -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo "")

    if [[ -z "$status" ]]; then
        echo "NotFound"
        return
    fi

    # Check for CrashLoopBackOff
    local container_status
    container_status=$(kubectl get pods -n "$namespace" -l "app=$IMAGE_NAME" -o jsonpath='{.items[0].status.containerStatuses[0].state.waiting.reason}' 2>/dev/null || echo "")

    if [[ "$container_status" == "CrashLoopBackOff" ]]; then
        echo "CrashLoop"
    else
        echo "$status"
    fi
}

get_deployed_image() {
    local namespace="$1"

    local image
    image=$(kubectl get deploy/"$IMAGE_NAME" -n "$namespace" -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null || echo "")

    if [[ -z "$image" ]]; then
        echo "none"
    else
        echo "$image"
    fi
}

get_restart_count() {
    local namespace="$1"

    kubectl get pods -n "$namespace" -l "app=$IMAGE_NAME" -o jsonpath='{.items[0].status.containerStatuses[0].restartCount}' 2>/dev/null || echo "0"
}

format_status() {
    local status="$1"

    case "$status" in
        Running)
            echo -e "${GREEN}Running${NC}"
            ;;
        Pending)
            echo -e "${YELLOW}Pending${NC}"
            ;;
        CrashLoop)
            echo -e "${RED}CrashLoopBackOff${NC}"
            ;;
        NotFound)
            echo -e "${CYAN}Not Deployed${NC}"
            ;;
        *)
            echo -e "${YELLOW}$status${NC}"
            ;;
    esac
}

show_recent_logs() {
    local namespace="$1"
    local lines="${2:-20}"

    echo ""
    echo -e "${YELLOW}Recent logs (last $lines lines):${NC}"
    echo "----------------------------------------"
    kubectl logs -n "$namespace" -l "app=$IMAGE_NAME" --tail="$lines" 2>/dev/null || echo "No logs available"
    echo "----------------------------------------"
}

# =============================================================================
# Main
# =============================================================================

main() {
    validate_target
    setup_context

    local namespace="$(get_namespace "$TARGET")"

    echo ""
    echo -e "${BLUE}Service:${NC}   $IMAGE_NAME"
    echo -e "${BLUE}Target:${NC}    $TARGET"
    echo -e "${BLUE}Namespace:${NC} $namespace"
    echo ""

    # Get status info
    local pod_status deployed_image restart_count

    pod_status=$(get_pod_status "$namespace")
    deployed_image=$(get_deployed_image "$namespace")
    restart_count=$(get_restart_count "$namespace")

    # Format output
    local status_text
    status_text=$(format_status "$pod_status")

    echo -e "Status:   $status_text"
    echo -e "Image:    $deployed_image"
    echo -e "Restarts: $restart_count"

    # Show logs on failure
    if [[ "$pod_status" == "CrashLoop" ]] || [[ "$pod_status" == "Error" ]]; then
        show_recent_logs "$namespace" 30
        echo ""
        echo -e "${YELLOW}Troubleshooting:${NC}"
        echo "  - Check logs: make logs"
        echo "  - Describe pod: kubectl describe pod -n $namespace -l app=$IMAGE_NAME"
        echo "  - Exec into pod: make shell"
    elif [[ "$pod_status" == "NotFound" ]]; then
        echo ""
        echo -e "${YELLOW}Service not deployed.${NC}"
        echo "  - Deploy with: make deploy TARGET=$TARGET"
    elif [[ "$pod_status" == "Running" ]]; then
        echo ""
        echo -e "${GREEN}Service is healthy.${NC}"
    fi

    echo ""
}

main
