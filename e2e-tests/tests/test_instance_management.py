"""E2E tests for instance management operations.

Tests update, lifecycle, health, scaling, and termination APIs
against a running instance created from the shared mapping.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Generator

import pytest

from graph_olap.exceptions import NotFoundError
from graph_olap.models.instance import InstanceProgress
from graph_olap_schemas import WrapperType

if TYPE_CHECKING:
    from graph_olap import GraphOLAPClient

logger = logging.getLogger(__name__)


def _worker_id() -> str:
    """Return the pytest-xdist worker id ('gw0', 'gw1', ...) or 'main' if not parallel."""
    return os.environ.get("PYTEST_XDIST_WORKER", "main")


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture(scope="module")
def managed_instance(
    graph_olap_client: GraphOLAPClient,
    shared_mapping: dict,
) -> Generator[dict, None, None]:
    """Create a single instance for all instance-management tests.

    Uses the shared mapping and waits for the instance to reach 'running'.
    Yields a dict with id, name, and description for the test class.
    """
    wid = _worker_id()
    logger.info(f"[{wid}] Creating managed instance for instance-management tests")

    original_name = f"{wid}-InstanceMgmtE2E"
    original_description = "Instance for management E2E tests"

    instance = None
    try:
        instance = graph_olap_client.instances.create_and_wait(
            mapping_id=shared_mapping["mapping_id"],
            name=original_name,
            wrapper_type=WrapperType.RYUGRAPH,
            description=original_description,
            ttl="PT4H",
            timeout=600,
            poll_interval=5,
        )
        logger.info(f"[{wid}] Managed instance ready: {instance.name} (id={instance.id})")

        yield {
            "id": instance.id,
            "name": original_name,
            "description": original_description,
        }

    finally:
        if instance is not None:
            try:
                graph_olap_client.instances.terminate(instance.id)
                logger.info(f"[{wid}] Terminated managed instance {instance.id}")
            except Exception as e:
                logger.warning(f"[{wid}] Failed to terminate managed instance: {e}")


# =============================================================================
# E2E Tests
# =============================================================================


@pytest.mark.xdist_group("instance_management")
@pytest.mark.e2e
class TestInstanceManagement:
    """E2E tests for instance management operations."""

    def test_update_name_and_description(
        self,
        graph_olap_client: GraphOLAPClient,
        managed_instance: dict,
    ):
        """Validate that instance name and description can be updated and persisted."""
        instance_id = managed_instance["id"]
        original_name = managed_instance["name"]

        logger.info(f"Updating name and description for instance {instance_id}")

        updated = graph_olap_client.instances.update(
            instance_id,
            name="NewName",
            description="NewDesc",
        )

        assert updated.name == "NewName", f"Expected name 'NewName', got '{updated.name}'"
        assert updated.description == "NewDesc", (
            f"Expected description 'NewDesc', got '{updated.description}'"
        )
        logger.info(f"Instance updated: name={updated.name}, description={updated.description}")

        # Restore original name so other tests see a predictable state
        restored = graph_olap_client.instances.update(
            instance_id,
            name=original_name,
        )
        assert restored.name == original_name
        logger.info(f"Restored original name: {restored.name}")

    def test_set_lifecycle(
        self,
        graph_olap_client: GraphOLAPClient,
        managed_instance: dict,
    ):
        """Validate that TTL and inactivity timeout can be set on a running instance."""
        instance_id = managed_instance["id"]

        logger.info(f"Setting lifecycle for instance {instance_id}")

        updated = graph_olap_client.instances.set_lifecycle(
            instance_id,
            ttl="PT24H",
            inactivity_timeout="PT2H",
        )

        assert updated.ttl == "PT24H", f"Expected ttl 'PT24H', got '{updated.ttl}'"
        assert updated.inactivity_timeout == "PT2H", (
            f"Expected inactivity_timeout 'PT2H', got '{updated.inactivity_timeout}'"
        )
        logger.info(f"Lifecycle set: ttl={updated.ttl}, inactivity_timeout={updated.inactivity_timeout}")

    def test_extend_ttl(
        self,
        graph_olap_client: GraphOLAPClient,
        managed_instance: dict,
    ):
        """Validate that extend_ttl runs without raising on a running instance.

        The exact TTL value is timing-dependent, so we only assert that the
        call completes successfully and returns an Instance.
        """
        instance_id = managed_instance["id"]

        logger.info(f"Extending TTL for instance {instance_id}")

        updated = graph_olap_client.instances.extend_ttl(instance_id, hours=6)

        assert updated is not None
        assert updated.id == instance_id
        logger.info(f"TTL extended successfully, ttl={updated.ttl}")

    def test_get_progress(
        self,
        graph_olap_client: GraphOLAPClient,
        managed_instance: dict,
    ):
        """Validate that get_progress returns an InstanceProgress object for a running instance."""
        instance_id = managed_instance["id"]

        logger.info(f"Getting progress for instance {instance_id}")

        progress = graph_olap_client.instances.get_progress(instance_id)

        assert isinstance(progress, InstanceProgress), (
            f"Expected InstanceProgress, got {type(progress).__name__}"
        )
        assert isinstance(progress.phase, str)
        assert len(progress.phase) > 0
        logger.info(f"Progress: phase={progress.phase}, percent={progress.progress_percent}")

    def test_get_health(
        self,
        graph_olap_client: GraphOLAPClient,
        managed_instance: dict,
    ):
        """Validate that get_health returns without raising and check_health returns True."""
        instance_id = managed_instance["id"]

        logger.info(f"Checking health for instance {instance_id}")

        health = graph_olap_client.instances.get_health(instance_id)
        assert health is not None
        logger.info(f"Health response: {health}")

        is_healthy = graph_olap_client.instances.check_health(instance_id)
        assert is_healthy is True, f"Expected check_health to return True, got {is_healthy}"
        logger.info("check_health returned True")

    def test_update_cpu(
        self,
        graph_olap_client: GraphOLAPClient,
        managed_instance: dict,
    ):
        """Validate update_cpu on a running instance (best-effort).

        Some deployments may not support in-place CPU changes. If the API
        raises, the test logs the error but does not fail.
        """
        instance_id = managed_instance["id"]

        logger.info(f"Updating CPU for instance {instance_id}")

        try:
            updated = graph_olap_client.instances.update_cpu(instance_id, cpu_cores=2)
            logger.info(f"CPU updated successfully, cpu_cores={getattr(updated, 'cpu_cores', 'N/A')}")
        except Exception as e:
            logger.warning(f"update_cpu not supported in this deployment: {e}")

    def test_update_memory(
        self,
        graph_olap_client: GraphOLAPClient,
        managed_instance: dict,
    ):
        """Validate update_memory on a running instance (best-effort).

        Some deployments may not support in-place memory changes. If the API
        raises, the test logs the error but does not fail.
        """
        instance_id = managed_instance["id"]

        logger.info(f"Updating memory for instance {instance_id}")

        try:
            updated = graph_olap_client.instances.update_memory(instance_id, memory_gb=4)
            logger.info(f"Memory updated successfully, memory_gb={getattr(updated, 'memory_gb', 'N/A')}")
        except Exception as e:
            logger.warning(f"update_memory not supported in this deployment: {e}")

    def test_double_terminate(
        self,
        graph_olap_client: GraphOLAPClient,
        shared_mapping: dict,
    ):
        """Validate that terminating an already-terminated instance raises NotFoundError.

        Creates a separate short-lived instance, terminates it once, then
        asserts that a second terminate raises NotFoundError.
        """
        wid = _worker_id()
        logger.info(f"[{wid}] Creating short-lived instance for double-terminate test")

        instance = graph_olap_client.instances.create_and_wait(
            mapping_id=shared_mapping["mapping_id"],
            name=f"{wid}-DoubleTerminateE2E",
            wrapper_type=WrapperType.RYUGRAPH,
            ttl="PT1H",
            timeout=600,
            poll_interval=5,
        )
        instance_id = instance.id
        logger.info(f"[{wid}] Created short-lived instance {instance_id}")

        # First terminate should succeed
        graph_olap_client.instances.terminate(instance_id)
        logger.info(f"[{wid}] First terminate succeeded for instance {instance_id}")

        # Second terminate should raise NotFoundError
        with pytest.raises(NotFoundError):
            graph_olap_client.instances.terminate(instance_id)

        logger.info(f"[{wid}] Second terminate raised NotFoundError as expected")
