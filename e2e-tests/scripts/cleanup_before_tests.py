#!/usr/bin/env python3
"""Pre-flight cleanup of test resources for cloud E2E tests.

This script runs ONCE before E2E tests start.
It deletes ALL resources with test prefixes via the SDK API.

Unlike the local cleanup script, this does NOT use kubectl.
The API will handle pod cleanup through reconciliation.

Usage:
    python cleanup_before_tests.py

Environment:
    GRAPH_OLAP_API_URL: Control plane API URL (required)
    GRAPH_OLAP_API_KEY_ANALYST_ALICE: API key for analyst Alice
    GRAPH_OLAP_API_KEY_ANALYST_BOB: API key for analyst Bob
    GRAPH_OLAP_API_KEY_ADMIN_CAROL: API key for admin Carol
    GRAPH_OLAP_API_KEY_OPS_DAVE: API key for ops Dave
"""

import os
import sys
import time

# Import test constants
from utils.constants import TEST_PREFIXES_WITH_DASH


def is_test_resource(name: str) -> bool:
    """Check if resource name has a test prefix."""
    return any(name.startswith(prefix) for prefix in TEST_PREFIXES_WITH_DASH)


def cleanup_test_resources():
    """Delete all test-prefixed resources via API."""
    # Import here to avoid import errors if SDK not installed
    from graph_olap import GraphOLAPClient
    from graph_olap.personas import Persona as TestPersona

    control_plane_url = os.environ.get("GRAPH_OLAP_API_URL")
    if not control_plane_url:
        print("ERROR: GRAPH_OLAP_API_URL not set")
        sys.exit(1)

    # All test personas to clean up resources for
    test_personas = [
        TestPersona.ANALYST_ALICE,
        TestPersona.ANALYST_BOB,
        TestPersona.ADMIN_CAROL,
        TestPersona.OPS_DAVE,
    ]

    print("=" * 60)
    print("Pre-flight cleanup: Removing orphaned test resources")
    print("=" * 60)
    print(f"Control Plane: {control_plane_url}")
    print(f"Test prefixes: {', '.join(TEST_PREFIXES_WITH_DASH)}")
    print()

    total_cleaned = 0

    for persona in test_personas:
        config = persona.value
        username = os.environ.get(config.env_var) or f"{config.name}@e2e.local"

        try:
            client = GraphOLAPClient(username=username, api_url=control_plane_url)
            cleaned = _cleanup_user_resources(client, config.name)
            total_cleaned += cleaned
            client.close()
        except Exception as e:
            print(f"  Warning: Failed to cleanup for {config.name}: {e}")

    # Wait for reconciliation to clean up pods
    if total_cleaned > 0:
        print()
        print("Waiting for pod cleanup...")
        time.sleep(15)

    print()
    print("=" * 60)
    if total_cleaned > 0:
        print(f"Cleaned up {total_cleaned} orphaned test resource(s)")
    else:
        print("No orphaned test resources found")
    print("=" * 60)
    print()


def _cleanup_user_resources(client, persona_name: str) -> int:
    """Clean up test resources for a specific persona.

    Args:
        client: GraphOLAPClient authenticated as the persona
        persona_name: Name of the persona (for logging only)

    Returns:
        Number of resources cleaned up
    """
    cleaned = 0

    # Clean instances first (they depend on snapshots and mappings)
    # Note: list() returns resources owned by the authenticated user (from JWT)
    try:
        instances = client.instances.list()
        for instance in instances:
            if is_test_resource(instance.name):
                print(f"  [{persona_name}] Deleting instance: {instance.name} (id={instance.id})")
                try:
                    client.instances.terminate(instance.id)
                    cleaned += 1
                except Exception as e:
                    print(f"    Warning: {e}")
    except Exception as e:
        print(f"  Warning: Failed to list instances for {persona_name}: {e}")

    # Clean snapshots (they depend on mappings)
    try:
        snapshots = client.snapshots.list()
        for snapshot in snapshots:
            if is_test_resource(snapshot.name):
                print(f"  [{persona_name}] Deleting snapshot: {snapshot.name} (id={snapshot.id})")
                try:
                    client.snapshots.delete(snapshot.id)
                    cleaned += 1
                except Exception as e:
                    print(f"    Warning: {e}")
    except Exception as e:
        print(f"  Warning: Failed to list snapshots for {persona_name}: {e}")

    # Clean mappings last
    try:
        mappings = client.mappings.list()
        for mapping in mappings:
            if is_test_resource(mapping.name):
                print(f"  [{persona_name}] Deleting mapping: {mapping.name} (id={mapping.id})")
                try:
                    client.mappings.delete(mapping.id)
                    cleaned += 1
                except Exception as e:
                    print(f"    Warning: {e}")
    except Exception as e:
        print(f"  Warning: Failed to list mappings for {persona_name}: {e}")

    return cleaned


if __name__ == "__main__":
    cleanup_test_resources()
