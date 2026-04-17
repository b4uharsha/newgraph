"""E2E tests for mapping management operations.

Tests mapping lifecycle, copy, diff, tree, snapshots, and deletion guards.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Generator

import pytest

from graph_olap.test_data import CUSTOMER_NODE, SHARES_ACCOUNT_EDGE

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
def test_mapping(graph_olap_client: GraphOLAPClient) -> Generator[dict, None, None]:
    """Create a mapping for mapping management tests.

    Creates a Customer/SHARES_ACCOUNT graph mapping.
    Yields mapping metadata dict, then deletes the mapping on teardown.
    """
    wid = _worker_id()
    logger.info(f"[{wid}] Creating test mapping for mapping management E2E tests")

    mapping = graph_olap_client.mappings.create(
        name=f"{wid}-MappingMgmtE2E",
        description=f"Mapping for mapping management E2E tests (worker={wid})",
        node_definitions=[CUSTOMER_NODE],
        edge_definitions=[SHARES_ACCOUNT_EDGE],
    )

    logger.info(f"[{wid}] Created test mapping: {mapping.name} (id={mapping.id})")

    try:
        yield {
            "id": mapping.id,
            "name": mapping.name,
            "version": mapping.current_version,
        }
    finally:
        logger.info("Cleaning up test mapping")
        try:
            graph_olap_client.mappings.delete(mapping.id)
            logger.info(f"Deleted mapping {mapping.id}")
        except Exception as e:
            logger.error(f"Failed to cleanup test mapping: {e}")


# =============================================================================
# E2E Tests
# =============================================================================


@pytest.mark.xdist_group("mapping_management")
@pytest.mark.e2e
class TestMappingManagement:
    """E2E tests for mapping management operations."""

    def test_copy_mapping(
        self,
        graph_olap_client: GraphOLAPClient,
        test_mapping: dict,
    ):
        """Test copying a mapping creates a new mapping with version 1."""
        wid = _worker_id()
        copy_name = f"CopyTest-{wid}-MappingMgmtE2E"
        logger.info(f"Copying mapping {test_mapping['id']} to '{copy_name}'")

        copied = None
        try:
            copied = graph_olap_client.mappings.copy(
                test_mapping["id"],
                new_name=copy_name,
            )

            logger.info(f"Copied mapping: id={copied.id}, name={copied.name}")

            assert copied.id != test_mapping["id"], "Copy must have a different ID"
            assert copied.name == copy_name, (
                f"Expected name '{copy_name}', got '{copied.name}'"
            )
            assert copied.current_version == 1, (
                f"Copy should start at version 1, got {copied.current_version}"
            )
        finally:
            if copied is not None:
                try:
                    graph_olap_client.mappings.delete(copied.id)
                    logger.info(f"Cleaned up copied mapping {copied.id}")
                except Exception as e:
                    logger.warning(f"Failed to delete copied mapping: {e}")

    def test_set_lifecycle(
        self,
        graph_olap_client: GraphOLAPClient,
        test_mapping: dict,
    ):
        """Test setting lifecycle parameters on a mapping."""
        logger.info(f"Setting lifecycle on mapping {test_mapping['id']}")

        updated = graph_olap_client.mappings.set_lifecycle(
            test_mapping["id"],
            ttl="PT720H",
            inactivity_timeout="PT168H",
        )

        logger.info(
            f"Lifecycle set: ttl={updated.ttl}, "
            f"inactivity_timeout={updated.inactivity_timeout}"
        )

        assert updated.ttl == "PT720H", f"Expected ttl 'PT720H', got '{updated.ttl}'"
        assert updated.inactivity_timeout == "PT168H", (
            f"Expected inactivity_timeout 'PT168H', got '{updated.inactivity_timeout}'"
        )

    @pytest.mark.xfail(reason="list_snapshots endpoint returns 404 — not yet implemented", strict=False)
    def test_list_snapshots(
        self,
        graph_olap_client: GraphOLAPClient,
        test_mapping: dict,
    ):
        """Test listing snapshots for a mapping returns a PaginatedList."""
        from graph_olap.models.common import PaginatedList

        logger.info(f"Listing snapshots for mapping {test_mapping['id']}")

        snapshots = graph_olap_client.mappings.list_snapshots(test_mapping["id"])

        logger.info(f"Got {snapshots.total} snapshot(s)")

        assert isinstance(snapshots, PaginatedList), (
            f"Expected PaginatedList, got {type(snapshots).__name__}"
        )
        assert isinstance(snapshots.items, list)
        assert snapshots.total >= 0

    def test_list_instances(
        self,
        graph_olap_client: GraphOLAPClient,
        test_mapping: dict,
    ):
        """Test listing instances for a mapping returns a PaginatedList."""
        from graph_olap.models.common import PaginatedList

        logger.info(f"Listing instances for mapping {test_mapping['id']}")

        instances = graph_olap_client.mappings.list_instances(test_mapping["id"])

        logger.info(f"Got {instances.total} instance(s)")

        assert isinstance(instances, PaginatedList), (
            f"Expected PaginatedList, got {type(instances).__name__}"
        )
        assert isinstance(instances.items, list)
        assert instances.total >= 0

    def test_diff_versions(
        self,
        graph_olap_client: GraphOLAPClient,
        test_mapping: dict,
    ):
        """Test diffing two mapping versions after creating version 2.

        Updates the mapping to create version 2, then verifies both
        diff_versions (returns dict) and diff (returns MappingDiff).
        """
        from graph_olap.models.mapping import MappingDiff, NodeDefinition, PropertyDefinition

        mapping_id = test_mapping["id"]
        logger.info(f"Updating mapping {mapping_id} to create version 2")

        # Add a second node definition to create version 2
        account_node = NodeDefinition(
            label="Account",
            sql=(
                """SELECT DISTINCT CAST(psdo_acno AS VARCHAR) AS id, acct_type FROM "hsbc-244552-hkibishk-dev"."hk_ibis_wsdv_app_view_dev".bis_acct_dh WHERE image_dt >= DATE '2020-01-01'"""
            ),
            primary_key={"name": "id", "type": "STRING"},
            properties=[
                PropertyDefinition(name="acct_type", type="STRING"),
            ],
        )

        graph_olap_client.mappings.update(
            mapping_id,
            change_description="Add Account node for diff test",
            node_definitions=[CUSTOMER_NODE, account_node],
            edge_definitions=[SHARES_ACCOUNT_EDGE],
        )

        logger.info("Created version 2, now diffing v1 vs v2")

        # Test diff_versions (returns raw dict)
        diff_dict = graph_olap_client.mappings.diff_versions(
            mapping_id, from_version=1, to_version=2,
        )

        assert isinstance(diff_dict, dict), (
            f"Expected dict from diff_versions, got {type(diff_dict).__name__}"
        )
        assert "summary" in diff_dict, "Diff dict should contain 'summary' key"
        logger.info(f"diff_versions summary: {diff_dict['summary']}")

        # Test diff (returns MappingDiff model)
        diff_obj = graph_olap_client.mappings.diff(mapping_id, 1, 2)

        assert isinstance(diff_obj, MappingDiff), (
            f"Expected MappingDiff from diff(), got {type(diff_obj).__name__}"
        )
        logger.info(f"diff() mapping_id={diff_obj.mapping_id}")

    def test_get_tree(
        self,
        graph_olap_client: GraphOLAPClient,
        test_mapping: dict,
    ):
        """Test getting the version/snapshot/instance hierarchy tree."""
        mapping_id = test_mapping["id"]
        logger.info(f"Getting tree for mapping {mapping_id}")

        tree = graph_olap_client.mappings.get_tree(mapping_id)

        assert isinstance(tree, dict), (
            f"Expected dict from get_tree, got {type(tree).__name__}"
        )
        assert len(tree) > 0, "Tree should have at least one version entry"

        # Each key should be an integer version number
        for version_num, version_data in tree.items():
            assert isinstance(version_num, int), (
                f"Version key should be int, got {type(version_num).__name__}"
            )
            assert "snapshots" in version_data, (
                f"Version {version_num} should have 'snapshots' key"
            )
            logger.info(
                f"Version {version_num}: "
                f"{version_data.get('snapshot_count', 0)} snapshot(s)"
            )

    def test_delete_with_active_instance_fails(
        self,
        graph_olap_client: GraphOLAPClient,
        test_mapping: dict,
    ):
        """Test that deleting a mapping with an active instance fails.

        Creates an instance from the mapping, then asserts that deletion
        raises an error because the mapping has dependencies.
        """
        from graph_olap.exceptions import ConflictError, DependencyError
        from graph_olap_schemas import WrapperType

        mapping_id = test_mapping["id"]
        wid = _worker_id()
        logger.info(f"Creating instance from mapping {mapping_id} to block deletion")

        instance = graph_olap_client.instances.create_and_wait(
            mapping_id=mapping_id,
            mapping_version=1,  # Use v1 (v2 has Account node with invalid SQL)
            name=f"{wid}-MappingMgmtE2E-BlockDelete",
            wrapper_type=WrapperType.FALKORDB,
            ttl="PT1H",
            timeout=600,
            poll_interval=10,
        )

        logger.info(f"Instance {instance.id} is running, attempting mapping delete")

        try:
            with pytest.raises((DependencyError, ConflictError)) as exc_info:
                graph_olap_client.mappings.delete(mapping_id)

            logger.info(f"Got expected error: {exc_info.value}")
        finally:
            try:
                graph_olap_client.instances.terminate(instance.id)
                logger.info(f"Terminated blocking instance {instance.id}")
            except Exception as e:
                logger.warning(f"Failed to terminate instance: {e}")
