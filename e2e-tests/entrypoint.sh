#!/bin/sh
# E2E Test Entrypoint
#
# Runs pre-flight cleanup then pytest with parallelism.
# This ensures orphaned test resources from previous runs are cleaned up.

set -e

echo "============================================================"
echo "E2E Test Configuration"
echo "============================================================"
echo "Mode: ${IN_CLUSTER:+IN-CLUSTER}${IN_CLUSTER:-LOCAL}"
echo "Control Plane: ${CONTROL_PLANE_URL}"
echo "Username: ${E2E_TEST_USERNAME:-e2e-test-user}"
echo "============================================================"
echo

# Run pre-flight cleanup (API-only, no kubectl needed)
echo "Running pre-flight cleanup..."
python scripts/cleanup_before_tests.py

# Run pytest with parallelism
# -n 2: Use 2 workers (limited by cloud memory for wrapper pods)
# --dist=loadgroup: Respect xdist_group markers for test isolation
exec pytest tests/ -v --tb=short -n 2 --dist=loadgroup "$@"
