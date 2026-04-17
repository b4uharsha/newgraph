#!/usr/bin/env bash
# prebuild.sh — Regenerate the Starlight content tree before Astro build (ADR-142).
#
# Pipeline (top to bottom):
#   1. build-handover.sh       docs/ + infrastructure/ → handover/
#   2. build-starlight.sh      handover/ → src/content/docs/
#   3. build-notebooks.mjs     docs/notebooks/ + tests/e2e/notebooks/ → src/content/docs/notebooks/
#
# Run context:
#   - Local dev: host filesystem, handover/ regenerated every time
#   - Earthfile LOCALLY stage: host filesystem, same as local dev
#   - Dockerfile build: container filesystem, needs docs/ + tools/ COPY'd in
#
# Environment variables:
#   SKIP_HANDOVER_REBUILD=1  Skip step 1 if handover/ already exists (CI cache)
#   SKIP_PREBUILD=1          Skip everything (used by external callers that
#                            already regenerated the tree themselves)
#
# Exit non-zero if any step fails.

set -euo pipefail

if [ -n "${SKIP_PREBUILD:-}" ]; then
    echo "prebuild: SKIP_PREBUILD=$SKIP_PREBUILD set, skipping all steps"
    exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$PKG_ROOT/../.." && pwd)"

echo "prebuild: package=$PKG_ROOT repo=$REPO_ROOT"

# ── Step 1: Regenerate handover/ from docs/ (unless already present or skipped) ──
HANDOVER_SCRIPT="$REPO_ROOT/tools/repo-split/build-handover.sh"
HANDOVER_DIR="$REPO_ROOT/handover"

if [ -n "${SKIP_HANDOVER_REBUILD:-}" ] && [ -d "$HANDOVER_DIR" ]; then
    echo "prebuild: step 1 — SKIP_HANDOVER_REBUILD=$SKIP_HANDOVER_REBUILD + handover/ exists, skipping"
elif [ -x "$HANDOVER_SCRIPT" ]; then
    echo "prebuild: step 1 — running build-handover.sh"
    "$HANDOVER_SCRIPT"
elif [ -d "$HANDOVER_DIR" ]; then
    echo "prebuild: step 1 — build-handover.sh not found, but handover/ exists; using as-is"
else
    echo "ERROR: prebuild: step 1 — neither build-handover.sh nor handover/ exists" >&2
    echo "  expected script: $HANDOVER_SCRIPT" >&2
    echo "  expected dir:    $HANDOVER_DIR" >&2
    echo "  If running inside a container, ensure the Dockerfile COPYs both" >&2
    echo "  docs/ and tools/repo-split/ into the build context." >&2
    exit 1
fi

# ── Step 2: Regenerate src/content/docs/ from handover/ ──
echo "prebuild: step 2 — running build-starlight.sh --copy-only"
bash "$PKG_ROOT/tools/build-starlight.sh" --copy-only

# ── Step 3: Regenerate notebooks tree from .ipynb sources ──
echo "prebuild: step 3 — running build-notebooks.mjs"
node "$PKG_ROOT/tools/build-notebooks.mjs"

echo "prebuild: complete"
