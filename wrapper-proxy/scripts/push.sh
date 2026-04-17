#!/usr/bin/env bash
# scripts/push.sh - Push wrapper-proxy to container registry
#
# Usage:
#   ./push.sh --target=local                    Tag for local (no push needed)
#   ./push.sh --target=gke-london [--tag=x]     Push to GCR
#
# For local deployments, OrbStack shares the Docker daemon so no push is needed.
# For GKE deployments, this pushes to gcr.io/hsbc-graph/wrapper-proxy.

set -euo pipefail

# =============================================================================
# Configuration
# =============================================================================

IMAGE_NAME="wrapper-proxy"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Registry configuration
GKE_REGISTRY="europe-west2-docker.pkg.dev/hsbc-graph/hsbc-graph"

# =============================================================================
# Colors
# =============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_push() { echo -e "${GREEN}[PUSH]${NC} $1"; }
log_skip() { echo -e "${YELLOW}[SKIP]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1" >&2; }

# =============================================================================
# Parse Arguments
# =============================================================================

TARGET=""
TAG="${TAG:-latest}"

while [[ $# -gt 0 ]]; do
    case $1 in
        --target=*) TARGET="${1#*=}" ;;
        --tag=*) TAG="${1#*=}" ;;
        *) log_error "Unknown option: $1"; exit 1 ;;
    esac
    shift
done

if [[ -z "$TARGET" ]]; then
    log_error "--target is required"
    echo "Usage: ./push.sh --target=local|gke-london [--tag=<tag>]"
    exit 1
fi

# =============================================================================
# Validation
# =============================================================================

validate_target() {
    case "$TARGET" in
        local|gke-london) ;;
        *)
            log_error "Unknown target: $TARGET"
            log_error "Valid targets: local, gke-london"
            exit 1
            ;;
    esac
}

validate_image() {
    local image="${IMAGE_NAME}:${TAG}"

    log_info "Checking for local image: $image"

    if docker image inspect "$image" &>/dev/null; then
        log_info "Image found: $image"
    else
        log_error "Local image not found: $image"
        log_error "Run 'make build' first"
        exit 1
    fi
}

# =============================================================================
# Push Functions
# =============================================================================

push_local() {
    log_info "Target 'local' uses OrbStack's shared Docker daemon"
    log_info "No push needed - images are already available to k8s"
    log_info ""
    log_info "Run 'make deploy TARGET=local' to deploy"
}

push_gke() {
    local local_image="${IMAGE_NAME}:${TAG}"
    local remote_image="${GKE_REGISTRY}/${IMAGE_NAME}:${TAG}"

    # Check if already in registry
    if docker manifest inspect "$remote_image" &>/dev/null 2>&1; then
        log_skip "$IMAGE_NAME:$TAG already in registry"
        log_info "Remote image: $remote_image"
        return 0
    fi

    # Tag and push
    log_push "$IMAGE_NAME:$TAG -> $remote_image"
    docker tag "$local_image" "$remote_image"
    docker push "$remote_image"

    log_info ""
    log_info "Image pushed successfully!"
    log_info "Remote image: $remote_image"
    log_info ""
    log_info "Next steps for GitOps deployment:"
    log_info "  1. Update Helm values with new image tag: $TAG"
    log_info "  2. Commit the changes"
    log_info "  3. Push to main branch"
    log_info "  4. ArgoCD will auto-deploy"
}

# =============================================================================
# Main
# =============================================================================

main() {
    echo "=============================================="
    echo "Pushing $IMAGE_NAME"
    echo "=============================================="
    echo ""

    validate_target
    validate_image

    log_info "Target: $TARGET"
    log_info "Tag: $TAG"
    echo ""

    case "$TARGET" in
        local)
            push_local
            ;;
        gke-london)
            push_gke
            ;;
    esac

    echo ""
    echo "=============================================="
    echo -e "${GREEN}[OK]${NC} Push complete!"
    echo "=============================================="
}

main
