"""E2E test configuration and fixtures.

This is the SINGLE conftest.py for all E2E tests. Infrastructure management
is handled by the local-dev/ module.

FAIL-FAST BEHAVIOR:
- By default, tests halt on first failure (--exitfirst / -x)
- This ensures failures are noticed immediately, not buried in output
- To run all tests despite failures: PYTEST_ARGS="--no-exitfirst" make test

Prerequisites:
    Infrastructure must be running before tests:
        cd ../local-dev && make up

Usage:
    pytest tests/ -v              # Run all tests
    pytest tests/ -v -k "smoke"   # Run smoke tests only

Authentication (ADR-104):
    Tests use username-based authentication via X-Username header.
    Each persona maps to a username and role; no API keys needed.

For notebooks, use notebook.test() with TestPersona enum instead of these fixtures.
"""
from __future__ import annotations

import logging
import os
import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from utils.cleanup import ResourceTracker

if TYPE_CHECKING:
    from graph_olap import GraphOLAPClient

from graph_olap.personas import Persona as TestPersona
from graph_olap_schemas import WrapperType

logger = logging.getLogger(__name__)


# =============================================================================
# Mode Detection
# =============================================================================

IN_CLUSTER = os.environ.get("IN_CLUSTER", "").lower() in ("true", "1", "yes")


def _worker_id() -> str:
    """Return the pytest-xdist worker id ('gw0', 'gw1', ...) or 'main' if not parallel."""
    return os.environ.get("PYTEST_XDIST_WORKER", "main")


# Module-level sets to track resource IDs created by THIS worker's session fixtures.
# Each xdist worker process has its own copy (separate processes).
# Used by cleanup_all_resources_on_exit to avoid cross-worker interference.
_worker_instance_ids: set[int] = set()
_worker_mapping_ids: set[int] = set()


# =============================================================================
# pytest Configuration
# =============================================================================

def pytest_addoption(parser: pytest.Parser) -> None:
    """Add command-line options for E2E tests."""
    parser.addoption(
        "--no-exitfirst",
        action="store_true",
        default=False,
        help="Continue running tests after first failure (overrides default fail-fast)",
    )
    parser.addoption(
        "--keep-cluster",
        action="store_true",
        default=True,
        help="Deprecated: cluster is always kept (managed by local-dev)",
    )
    parser.addoption(
        "--reuse-cluster",
        action="store_true",
        default=True,
        help="Deprecated: cluster is always reused (managed by local-dev)",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Configure pytest for E2E tests.

    Google TAP Best Practice: Fail fast, fail loud.
    - Default behavior: Stop on first failure (--exitfirst)
    - Override with: --no-exitfirst or -p no:exitfirst
    """
    # Only enable exitfirst if not explicitly disabled
    if not config.getoption("--no-exitfirst", default=False):
        # Set exitfirst unless already set via command line
        if not config.getoption("exitfirst", default=False):
            config.option.exitfirst = True

    # Print configuration at test start
    url = os.environ.get("GRAPH_OLAP_API_URL", "NOT SET")
    print(f"\n{'='*60}")
    print("E2E Test Configuration")
    print(f"{'='*60}")
    print(f"Mode: {'IN-CLUSTER' if IN_CLUSTER else 'LOCAL'}")
    print(f"Control Plane: {url}")
    print(f"Auth: X-Username header (ADR-104)")
    print(f"{'='*60}\n")


def pytest_collection_modifyitems(session, config, items):
    """Dynamically apply xdist_group and timeout markers from YAML configs.

    This allows notebooks.yaml and tutorials.yaml to be the single source of
    truth for test configuration.  Markers are applied at collection time, so
    pytest-xdist respects them.
    """
    from pathlib import Path

    import yaml

    # --- E2E notebook tests (notebooks.yaml) ---
    config_path = Path(__file__).parent / "notebooks.yaml"
    if config_path.exists():
        with open(config_path) as f:
            nb_config = yaml.safe_load(f)

        defaults = nb_config.get("defaults", {})
        notebooks = nb_config.get("notebooks", {})

        for item in items:
            if "test_notebook" not in item.name:
                continue
            if "[" not in item.name:
                continue

            param_id = item.name.split("[")[1].rstrip("]")
            if not param_id.startswith("test_"):
                continue

            notebook_name = param_id[5:]  # Remove "test_" prefix

            if notebook_name not in notebooks:
                continue

            cfg = notebooks[notebook_name] or {}

            xdist_group = cfg.get("xdist_group", defaults.get("xdist_group", "default"))
            item.add_marker(pytest.mark.xdist_group(xdist_group))

            timeout = cfg.get("timeout", defaults.get("timeout", 120))
            item.add_marker(pytest.mark.timeout(timeout))

            item.add_marker(pytest.mark.e2e)

    # --- Tutorial notebook tests (tutorials.yaml) ---
    tutorials_path = Path(__file__).parent / "tutorials.yaml"
    if tutorials_path.exists():
        with open(tutorials_path) as f:
            tut_config = yaml.safe_load(f)

        tut_defaults = tut_config.get("defaults", {})
        tut_notebooks = tut_config.get("notebooks", {})

        for item in items:
            if "test_tutorial" not in item.name:
                continue
            if "[" not in item.name:
                continue

            param_id = item.name.split("[")[1].rstrip("]")
            if not param_id.startswith("tutorial_"):
                continue

            tutorial_name = param_id[9:]  # Remove "tutorial_" prefix

            if tutorial_name not in tut_notebooks:
                continue

            cfg = tut_notebooks[tutorial_name] or {}

            xdist_group = cfg.get("xdist_group", tut_defaults.get("xdist_group", "tutorials"))
            item.add_marker(pytest.mark.xdist_group(xdist_group))

            timeout = cfg.get("timeout", tut_defaults.get("timeout", 120))
            item.add_marker(pytest.mark.timeout(timeout))

            item.add_marker(pytest.mark.tutorials)


# =============================================================================
# Helper Functions
# =============================================================================

def get_persona_username(persona: TestPersona) -> str:
    """Get username for a specific test persona.

    Args:
        persona: TestPersona enum value

    Returns:
        Username string for the persona (e.g. "analyst_alice@e2e.local")
    """
    config = persona.value
    return f"{config.name}@e2e.local"


def get_control_plane_url() -> str:
    """Get Control Plane URL from environment.

    Uses SDK-standard environment variable names for consistency.
    Configuration is managed externally (Makefile, CI/CD, etc.)
    This function just retrieves the configured value and fails fast if missing.

    Returns:
        Control plane URL

    Raises:
        RuntimeError: If GRAPH_OLAP_API_URL environment variable is not set

    Environment Variables:
        GRAPH_OLAP_API_URL: Full URL to control plane API (SDK standard)
            Local:      http://localhost:30081 (via OrbStack + nginx ingress)
            In-cluster: http://control-plane.graph-olap-local.svc.cluster.local:8080
    """
    url = os.environ.get("GRAPH_OLAP_API_URL")
    if not url:
        raise RuntimeError(
            "GRAPH_OLAP_API_URL environment variable not set. "
            "Configure your test environment:\n"
            "  Local: Run tests via 'make test' from tools/local-dev/\n"
            "  CI/CD: Ensure test environment configuration is loaded"
        )
    return url


# =============================================================================
# Auth Fixtures (ADR-104: username-based, no API keys)
# =============================================================================

@pytest.fixture(scope="session")
def control_plane_url() -> str:
    """Get Control Plane URL for tests.

    Session-scoped because URL is constant across all tests.
    """
    return get_control_plane_url()


# =============================================================================
# Client Fixtures (ADR-104: username-based auth)
# =============================================================================

@pytest.fixture(scope="module")
def graph_olap_client(control_plane_url: str) -> Generator[GraphOLAPClient, None, None]:
    """Create GraphOLAP client for tests (as analyst Alice).

    Automatically closes client after tests complete.
    Uses username-based authentication (ADR-104).
    """
    from graph_olap import GraphOLAPClient

    client = GraphOLAPClient(
        api_url=control_plane_url,
        username=get_persona_username(TestPersona.ANALYST_ALICE),
        use_case_id=os.environ.get("GRAPH_OLAP_USE_CASE_ID"),
    )

    logger.info(f"Created GraphOLAP client (analyst Alice) at {control_plane_url}")

    try:
        yield client
    finally:
        client.close()
        logger.info("Closed GraphOLAP client")


@pytest.fixture(scope="module")
def sdk_client(graph_olap_client: GraphOLAPClient) -> GraphOLAPClient:
    """Alias for graph_olap_client for backward compatibility."""
    return graph_olap_client


@pytest.fixture(scope="module")
def admin_client(control_plane_url: str) -> Generator[GraphOLAPClient, None, None]:
    """Create GraphOLAP client for admin Carol."""
    from graph_olap import GraphOLAPClient

    client = GraphOLAPClient(
        api_url=control_plane_url,
        username=get_persona_username(TestPersona.ADMIN_CAROL),
        use_case_id=os.environ.get("GRAPH_OLAP_USE_CASE_ID"),
    )
    logger.info(f"Created admin client (Carol) at {control_plane_url}")

    try:
        yield client
    finally:
        client.close()


@pytest.fixture(scope="module")
def ops_client(control_plane_url: str) -> Generator[GraphOLAPClient, None, None]:
    """Create GraphOLAP client for ops Dave."""
    from graph_olap import GraphOLAPClient

    client = GraphOLAPClient(
        api_url=control_plane_url,
        username=get_persona_username(TestPersona.OPS_DAVE),
        use_case_id=os.environ.get("GRAPH_OLAP_USE_CASE_ID"),
    )
    logger.info(f"Created ops client (Dave) at {control_plane_url}")

    try:
        yield client
    finally:
        client.close()


@pytest.fixture(scope="module")
def analyst_client(control_plane_url: str) -> Generator[GraphOLAPClient, None, None]:
    """Create GraphOLAP client for analyst Alice."""
    from graph_olap import GraphOLAPClient

    client = GraphOLAPClient(
        api_url=control_plane_url,
        username=get_persona_username(TestPersona.ANALYST_ALICE),
        use_case_id=os.environ.get("GRAPH_OLAP_USE_CASE_ID"),
    )
    logger.info(f"Created analyst client (Alice) at {control_plane_url}")

    try:
        yield client
    finally:
        client.close()


# =============================================================================
# Resource Management Fixtures
# =============================================================================

@pytest.fixture
def resource_tracker(graph_olap_client: GraphOLAPClient) -> Generator[ResourceTracker, None, None]:
    """Provide resource tracker with automatic cleanup.

    This fixture ensures all resources created during a test are cleaned up,
    even if the test fails.

    Usage:
        def test_something(resource_tracker):
            mapping = resource_tracker.create_mapping(name="Test")
            # ... test code ...
            # Cleanup happens automatically
    """
    tracker = ResourceTracker(
        client=graph_olap_client,
        username="analyst_alice",  # For logging only
        fail_on_cleanup_error=True,
    )

    logger.info("Starting resource tracker for test")

    try:
        yield tracker
    finally:
        # Always cleanup, even if test fails
        logger.info("Cleaning up test resources")
        tracker.cleanup_all()

        # Check for cleanup failures
        failed = [r for r in tracker.cleanup_results if not r.success and not r.skipped]
        if failed:
            error_details = "\n".join(
                f"  - {r.resource.resource_type.value} {r.resource.resource_id}: {r.error}"
                for r in failed
            )
            pytest.fail(f"Resource cleanup failed:\n{error_details}")


@pytest.fixture(scope="session")
def seeded_ids(shared_mapping: dict, shared_readonly_instance: str) -> dict[str, int]:
    """Get IDs from shared test resources (mapping + running instance).

    Use this for notebooks that need both a mapping ID AND a running instance ID.
    For notebooks that only need a mapping ID, use seeded_mapping_id instead
    (avoids forcing instance pool creation).

    Returns:
        dict with mapping_id, instance_id from shared fixtures
    """
    return {
        "mapping_id": shared_mapping["mapping_id"],
        "instance_id": int(shared_readonly_instance),
    }


@pytest.fixture(scope="session")
def seeded_mapping_id(shared_mapping: dict) -> dict[str, int]:
    """Get mapping ID only — no instance pool needed.

    Use this for notebooks that only need a mapping (e.g., copy, diff, update)
    and don't need a running graph instance.

    Returns:
        dict with mapping_id only
    """
    return {
        "mapping_id": shared_mapping["mapping_id"],
    }


# =============================================================================
# Session-Scoped Shared Resources
# =============================================================================

# NOTE: Cleanup of orphaned test resources is handled by the Makefile.
# The pre-flight cleanup script (tools/local-dev/scripts/cleanup-test-resources.py)
# runs ONCE before pytest starts, avoiding race conditions with pytest-xdist.
#
# Why not a pytest fixture?
# - pytest-xdist runs session fixtures once PER WORKER, not once globally
# - This caused race conditions where Worker 2 would delete resources from Worker 1
# - Makefile cleanup runs ONCE, BEFORE any tests start - no race conditions
#
# Manual cleanup:
#   cd tools/local-dev && python3 ./scripts/cleanup-test-resources.py


@pytest.fixture(scope="session", autouse=True)
def configure_parallel_test_limits(control_plane_url: str) -> Generator[None, None, None]:
    """Configure instance limits for parallel test execution.

    Parallel tests require higher instance limits:
    - Session fixtures: 4 instances (3 generic + 1 readonly, all in instance_pool)
    - Concurrent tests: 6 instances (crud, algorithm, workflow, authorization, validation, etc.)
    - Total needed: 10 instances (vs default limit of 5)

    This fixture:
    1. Gets current concurrency limits
    2. Increases per_analyst limit to 50 (cluster_total to 50)
    3. Yields to tests
    4. Restores original limits on teardown (ONLY the last worker does this)

    PARALLEL-SAFE: Uses a filelock-based worker counter so only the LAST
    finishing worker restores original limits. Without this, Worker A finishes
    first and restores limits to 5 while Workers B/C/D still have 10+ instances.

    AUTOUSE: This fixture runs automatically for all test sessions.
    """
    from filelock import FileLock
    from graph_olap import GraphOLAPClient

    wid = _worker_id()
    run_uid = os.environ.get("PYTEST_XDIST_TESTRUNUID", "main")
    counter_path = Path(tempfile.gettempdir()) / f"e2e_worker_counter_{run_uid}"
    lock_path = Path(tempfile.gettempdir()) / f"e2e_worker_counter_{run_uid}.lock"

    logger.info(f"[{wid}] Configuring instance limits for parallel test execution")

    # Create ops client (Dave) to access config API
    ops_client = GraphOLAPClient(
        api_url=control_plane_url,
        username=get_persona_username(TestPersona.OPS_DAVE),
        use_case_id=os.environ.get("GRAPH_OLAP_USE_CASE_ID"),
    )

    original_per_analyst = None
    original_cluster_total = None

    try:
        # Get current limits
        original_limits = ops_client.ops.get_concurrency_config()
        original_per_analyst = original_limits.per_analyst
        original_cluster_total = original_limits.cluster_total
        logger.info(
            f"[{wid}] Original limits: per_analyst={original_per_analyst}, "
            f"cluster_total={original_cluster_total}"
        )

        # Increase limits for parallel tests
        # - Session fixtures need 4 instances (pool + shared_readonly)
        # - Concurrent tests need up to 6 instances per worker
        # - With 8 workers, instances accumulate if cleanup is slow
        # - 50 gives enough headroom to avoid hitting the limit mid-run
        new_limits = ops_client.ops.update_concurrency_config(
            per_analyst=50,
            cluster_total=50
        )
        logger.info(
            f"[{wid}] Increased limits for parallel tests: "
            f"per_analyst={new_limits.per_analyst}, cluster_total={new_limits.cluster_total}"
        )

        # Register this worker in the counter file
        with FileLock(str(lock_path)):
            count = int(counter_path.read_text()) if counter_path.exists() else 0
            counter_path.write_text(str(count + 1))
            logger.info(f"[{wid}] Registered worker (active_count={count + 1})")

        yield

    finally:
        # Deregister this worker and only restore limits if we are the last one
        is_last_worker = False
        try:
            with FileLock(str(lock_path)):
                count = int(counter_path.read_text()) if counter_path.exists() else 1
                new_count = max(0, count - 1)
                counter_path.write_text(str(new_count))
                logger.info(f"[{wid}] Deregistered worker (remaining={new_count})")
                is_last_worker = new_count == 0
        except Exception as e:
            logger.warning(f"[{wid}] Error updating worker counter: {e}")
            # If we can't read the counter, assume we should restore (safe default)
            is_last_worker = True

        if is_last_worker:
            # Restore concurrency limits (only last worker)
            if original_per_analyst is not None:
                try:
                    restored = ops_client.ops.update_concurrency_config(
                        per_analyst=original_per_analyst,
                        cluster_total=original_cluster_total,
                    )
                    logger.info(
                        f"[{wid}] Last worker -- restored original limits: "
                        f"per_analyst={restored.per_analyst}, cluster_total={restored.cluster_total}"
                    )
                except Exception as e:
                    logger.warning(f"[{wid}] Failed to restore original limits: {e}")

            # Clean up counter files
            try:
                counter_path.unlink(missing_ok=True)
            except Exception:
                pass
            try:
                lock_path.unlink(missing_ok=True)
            except Exception:
                pass
        else:
            logger.info(f"[{wid}] Skipping limit restore (other workers still active)")

        # NOTE: Broad resource cleanup is handled by run-tests.sh AFTER pytest exits.
        # Do NOT clean all resources here — other xdist workers may still be running.
        # Each worker's fixtures (instance_pool, shared_mapping) clean their own resources.

        ops_client.close()


@pytest.fixture(scope="session", autouse=True)
def cleanup_all_resources_on_exit(control_plane_url: str) -> Generator[None, None, None]:
    """Clean up instances and mappings created by THIS worker.

    PARALLEL-SAFE: Each worker only cleans up resources it created (tracked by
    ID in _worker_instance_ids / _worker_mapping_ids). This prevents Worker B
    from nuking Worker A's resources.

    Runs BEFORE tests (clean orphans from previous failed runs) and AFTER
    tests (clean resources created in this session).
    """
    from graph_olap import GraphOLAPClient

    wid = _worker_id()
    client = GraphOLAPClient(
        api_url=control_plane_url,
        username=get_persona_username(TestPersona.ANALYST_ALICE),
    )

    # --- PRE-TEST: Clean orphaned resources from previous failed runs ---
    try:
        # Terminate failed instances (they consume per_analyst slots)
        instances = client.instances.list(limit=200)
        orphans = [i for i in instances.items if i.status in ("failed", "terminated")]
        if orphans:
            logger.info(f"[{wid}] Pre-test cleanup: {len(orphans)} orphaned instance(s)")
            for inst in orphans:
                try:
                    client.instances.terminate(inst.id)
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"[{wid}] Pre-test instance cleanup failed: {e}")

    yield

    # --- POST-TEST: Clean resources created by this session ---
    instance_ids = list(_worker_instance_ids)
    mapping_ids = list(_worker_mapping_ids)
    logger.info(
        f"[{wid}] Post-test cleanup: {len(instance_ids)} instance(s), "
        f"{len(mapping_ids)} mapping(s)"
    )

    # Terminate instances first (they reference mappings via snapshots)
    for iid in instance_ids:
        try:
            client.instances.terminate(iid)
            logger.info(f"[{wid}] Terminated instance {iid}")
        except Exception:
            pass

    # Delete tracked mappings
    for mid in mapping_ids:
        try:
            client.mappings.delete(mid)
            logger.info(f"[{wid}] Deleted mapping {mid}")
        except Exception:
            pass

    # Broad cleanup is handled by configure_parallel_test_limits (last-worker only).
    # This fixture only cleans resources tracked by _worker_instance_ids/_worker_mapping_ids.

    client.close()


# Per-test instance cleanup removed — it was too aggressive and terminated
# shared session-scoped instances (pool, shared_readonly) that other tests need.
# Cleanup is handled at session level by cleanup_all_instances_on_exit and
# the raised per_analyst limit (50) provides enough headroom.


@pytest.fixture(scope="session")
def shared_mapping(control_plane_url: str) -> Generator[dict, None, None]:
    """Create a shared mapping for ALL E2E tests.

    Instances are created directly from mappings using create_and_wait().
    This fixture creates ONE shared mapping that all other fixtures and
    tests reuse.

    This fixture:
    1. Creates ONE mapping with Customer + SHARES_ACCOUNT schema
    2. Wakes the Starburst Galaxy cluster
    3. Yields the mapping ID for dependent fixtures (instance_pool, seeded_ids)

    Yields:
        dict: {
            "mapping_id": int,
        }
    """
    from graph_olap import GraphOLAPClient
    from graph_olap.test_data import CUSTOMER_NODE, SHARES_ACCOUNT_EDGE

    wid = _worker_id()
    logger.info("=" * 60)
    logger.info(f"[{wid}] Creating shared mapping for all E2E tests")
    logger.info("=" * 60)

    client = GraphOLAPClient(
        api_url=control_plane_url,
        username=get_persona_username(TestPersona.ANALYST_ALICE),
        use_case_id=os.environ.get("GRAPH_OLAP_USE_CASE_ID"),
    )

    customer_node = CUSTOMER_NODE
    shares_account_edge = SHARES_ACCOUNT_EDGE

    # Wake Starburst Galaxy cluster (auto-suspends after 5 min idle)
    from graph_olap.notebook import wake_starburst
    wake_starburst(timeout=90, quiet=False)

    mapping = None

    try:
        # Create ONE mapping (worker-prefixed to avoid collisions with other xdist workers)
        mapping = client.mappings.create(
            name=f"{wid}-SharedE2EMapping",
            description=f"Shared mapping for E2E tests (worker={wid})",
            node_definitions=[customer_node],
            edge_definitions=[shares_account_edge],
        )
        logger.info(f"[{wid}] Created shared mapping: {mapping.name} (id={mapping.id})")
        _worker_mapping_ids.add(mapping.id)

        yield {
            "mapping_id": mapping.id,
        }

    finally:
        logger.info(f"[{wid}] Cleaning up shared mapping")

        if mapping:
            try:
                client.mappings.delete(mapping.id)
                logger.info(f"[{wid}] Deleted shared mapping {mapping.id}")
            except Exception as e:
                logger.error(f"[{wid}] Failed to delete shared mapping: {e}")

        client.close()


@pytest.fixture(scope="session")
def shared_mapping_id(shared_mapping: dict) -> int:
    """Get the shared mapping ID for tests that need it.

    Convenience fixture that extracts just the mapping ID.
    """
    return shared_mapping["mapping_id"]


@pytest.fixture(scope="session")
def shared_readonly_instance(instance_pool: dict[str, str]) -> str:
    """Get the shared read-only instance from the instance pool.

    OPTIMIZED (ADR-119): Instance is now created in parallel with the other
    pool instances inside instance_pool, instead of sequentially after it.
    Saves ~60s by overlapping creation with the 3 generic instances.

    Tests using this fixture:
    - sdk_query_test: Read-only Cypher queries
    - sdk_validation_test: Error handling, read-only validation
    - sdk_schema_test: Read-only schema metadata browsing

    Returns:
        str: Instance ID that can be passed to notebooks via INSTANCE_ID parameter
    """
    return instance_pool["readonly"]


@pytest.fixture(scope="session")
def instance_pool(
    shared_mapping: dict,
    control_plane_url: str,
) -> Generator[dict[str, str], None, None]:
    """Create a shared instance using the shared mapping.

    Reduced from 4 instances to 1 — the 3 generic instances were never used
    by any notebook. This single instance serves all tests that need a running
    graph (02_health_checks, 04_cypher_basics, 05_schemas, 09_errors, etc.).

    Resource impact: 1 pod per worker (was 4). On an 8-CPU node with 2 workers,
    this uses 2 CPUs instead of 8, leaving headroom for tutorial instances.

    Returns:
        dict with keys: "generic_1", "readonly" (both point to the same instance)
    """
    from graph_olap import GraphOLAPClient

    wid = _worker_id()
    logger.info(f"[{wid}] Creating shared instance (using shared_mapping)")

    client = GraphOLAPClient(
        api_url=control_plane_url,
        username=get_persona_username(TestPersona.ANALYST_ALICE),
        use_case_id=os.environ.get("GRAPH_OLAP_USE_CASE_ID"),
    )

    mapping_id = shared_mapping["mapping_id"]
    instances = {}

    try:
        instance = client.instances.create_and_wait(
            mapping_id=mapping_id,
            name=f"{wid}-SharedInstance",
            wrapper_type=WrapperType.RYUGRAPH,
            ttl="PT1H",
            timeout=600,
            poll_interval=5,
        )
        _worker_instance_ids.add(instance.id)
        instance_id = str(instance.id)
        # Both keys point to the same instance for backwards compatibility
        instances = {
            "generic_1": instance_id,
            "readonly": instance_id,
        }
        logger.info(f"[{wid}] Shared instance ready: {instance.name} (id={instance.id})")

        yield instances

    finally:
        # Cleanup pool instances at end of session
        logger.info(f"[{wid}] Cleaning up instance pool")
        for key, instance_id in instances.items():
            try:
                client.instances.terminate(int(instance_id))
                _worker_instance_ids.discard(int(instance_id))
                logger.info(f"[{wid}] Terminated pool instance {key} (id={instance_id})")
            except Exception as e:
                logger.error(f"[{wid}] Failed to terminate pool instance {key}: {e}")

        client.close()
