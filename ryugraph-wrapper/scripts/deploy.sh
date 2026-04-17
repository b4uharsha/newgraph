#!/usr/bin/env bash
# scripts/deploy.sh - Deploy ryugraph-wrapper to Kubernetes
#
# Usage:
#   ./deploy.sh --target=local      Deploy to local OrbStack
#   ./deploy.sh --target=gke-london Error (use ArgoCD for GKE)
#
# For local deployments, this uses Helm with values-local.yaml.
# For GKE deployments, use ArgoCD GitOps instead.

set -euo pipefail

# =============================================================================
# Configuration
# =============================================================================

IMAGE_NAME="ryugraph-wrapper"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# =============================================================================
# Colors
# =============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1" >&2; }

# =============================================================================
# Parse Arguments
# =============================================================================

TARGET=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --target=*) TARGET="${1#*=}" ;;
        *) log_error "Unknown option: $1"; exit 1 ;;
    esac
    shift
done

if [[ -z "$TARGET" ]]; then
    log_error "--target is required"
    echo "Usage: ./deploy.sh --target=local|gke-london"
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
        local) ;;
        gke-london)
            log_error "Direct deployment to GKE is not supported."
            log_error ""
            log_error "Use ArgoCD for GKE deployments:"
            log_error "  1. Run: make push TARGET=gke-london"
            log_error "  2. Commit the updated Helm values"
            log_error "  3. Push to main branch"
            log_error "  4. ArgoCD auto-deploys on git push"
            exit 1
            ;;
        *)
            log_error "Unknown target: $TARGET"
            log_error "Valid targets: local, gke-london"
            exit 1
            ;;
    esac
}

# =============================================================================
# Preconditions
# =============================================================================

# Services that don't require local-infra (they ARE infrastructure)
INFRA_SERVICES="local-infra pypi-server"

is_infra_service() {
    for svc in $INFRA_SERVICES; do
        if [[ "$IMAGE_NAME" == "$svc" ]]; then
            return 0
        fi
    done
    return 1
}

check_local_infra() {
    if [[ "$TARGET" != "local" ]]; then
        return 0
    fi

    # Skip check for infrastructure services that don't need postgres
    if is_infra_service; then
        log_info "Skipping local-infra check (this is an infrastructure service)"
        return 0
    fi

    log_info "Checking for local-infra..."

    # Check if postgres is running
    local namespace="$(get_namespace "$TARGET")"
    if ! kubectl get deployment postgres -n "$namespace" &>/dev/null; then
        log_error "local-infra not deployed!"
        log_error ""
        log_error "Deploy local-infra first:"
        log_error "  cd ../local-infra && make deploy TARGET=local"
        log_error ""
        log_error "Or deploy from the monorepo:"
        log_error "  make deploy TARGET=local SVC=local-infra"
        exit 1
    fi

    log_success "local-infra is running"
}

ensure_kubectl_context() {
    local context="$(get_kube_context "$TARGET")"

    if [[ -z "$context" ]]; then
        return 0
    fi

    local current_context
    current_context=$(kubectl config current-context 2>/dev/null || echo "none")

    if [[ "$current_context" != "$context" ]]; then
        log_info "Switching kubectl context to $context..."
        kubectl config use-context "$context"
    fi

    log_success "Kubectl context: $context"
}

validate_image() {
    local tag="${TAG:-latest}"
    local image="${IMAGE_NAME}:${tag}"

    log_info "Checking for image: $image"

    if docker image inspect "$image" &>/dev/null; then
        log_success "Image found: $image"
    else
        log_error "Image not found: $image"
        log_error "Run 'make build' first"
        exit 1
    fi
}

# =============================================================================
# Deploy
# =============================================================================

deploy_local() {
    local namespace="$(get_namespace "$TARGET")"
    local tag="${TAG:-latest}"
    local values_file="$REPO_ROOT/infrastructure/helm/values-local.yaml"
    local chart_dir="$REPO_ROOT/infrastructure/helm"

    log_info "Deploying $IMAGE_NAME to $TARGET ($namespace)..."

    # Create namespace if it doesn't exist
    kubectl create namespace "$namespace" --dry-run=client -o yaml | kubectl apply -f - 2>/dev/null

    # Check for Helm chart
    if [[ ! -f "$chart_dir/Chart.yaml" ]]; then
        log_error "Helm chart not found at $chart_dir"
        log_error "Expected Chart.yaml in infrastructure/helm/"
        exit 1
    fi

    # Check for values file
    if [[ ! -f "$values_file" ]]; then
        log_warn "Values file not found: $values_file"
        log_warn "Using default values"
        values_file=""
    fi

    # Deploy via Helm
    log_info "Running Helm upgrade..."
    local helm_args=(
        upgrade --install "$IMAGE_NAME" "$chart_dir"
        --namespace "$namespace"
        --set "image.tag=$tag"
        --set "image.repository=$IMAGE_NAME"
        --wait
        --timeout 5m
    )

    if [[ -n "$values_file" ]]; then
        helm_args+=(--values "$values_file")
    fi

    helm "${helm_args[@]}"

    log_success "$IMAGE_NAME deployed to $namespace"

    # Wait for rollout
    log_info "Waiting for rollout..."
    kubectl rollout status "deployment/$IMAGE_NAME" -n "$namespace" --timeout=2m || true
}

# =============================================================================
# Health Check
# =============================================================================

health_check() {
    local namespace="$(get_namespace "$TARGET")"

    log_info "Checking pod status..."

    local status
    status=$(kubectl get pods -n "$namespace" -l "app=$IMAGE_NAME" -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo "NotFound")

    if [[ "$status" == "Running" ]]; then
        log_success "Pod is running"
    else
        log_warn "Pod status: $status"
        log_warn "Check logs with: make logs"
    fi
}

# =============================================================================
# Main
# =============================================================================

main() {
    echo "=============================================="
    echo "Deploying $IMAGE_NAME to $TARGET"
    echo "=============================================="
    echo ""

    validate_target
    ensure_kubectl_context
    validate_image
    check_local_infra

    echo ""

    deploy_local

    echo ""

    health_check

    echo ""
    echo "=============================================="
    log_success "Deployment complete!"
    echo "=============================================="
    echo ""
    log_info "Run 'make status TARGET=$TARGET' to check status"
    log_info "Run 'make logs' to view logs"
}

main
