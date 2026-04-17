"""Integration tests for lifecycle job.

Tests lifecycle job with real database and mocked services.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from graph_olap_schemas import WrapperType

from control_plane.jobs.lifecycle import run_lifecycle_job
from control_plane.models import InstanceStatus


@pytest.mark.asyncio
@pytest.mark.integration
class TestLifecycleIntegration:
    """Integration tests for lifecycle job."""

    async def test_lifecycle_terminates_ttl_expired_instance(
        self, db_session, instance_repo, snapshot_repo, mapping_repo
    ):
        """Test lifecycle job terminates instance with expired TTL."""
        # Create mapping and snapshot first (required FKs)
        mapping = await mapping_repo.create(name="test-mapping", created_by="test-user", raw_schema={})
        snapshot = await snapshot_repo.create(name="test-snapshot", mapping_id=mapping.id, created_by="test-user")

        # Create instance with TTL="PT1H" created 2 hours ago
        two_hours_ago = datetime.now(UTC) - timedelta(hours=2)
        instance = await instance_repo.create(
            mapping_id=mapping.id,
            snapshot_id=snapshot.id,
            created_by="test-user",
            wrapper_type=WrapperType.RYUGRAPH,
            ttl="PT1H",  # 1 hour TTL
        )

        # Update created_at to 2 hours ago (simulate expired)
        await instance_repo.update(instance.id, {"created_at": two_hours_ago.isoformat()})

        # Mock instance service to avoid actually deleting pods
        with patch("control_plane.jobs.lifecycle.InstanceService") as MockInstanceService:
            mock_service = AsyncMock()
            MockInstanceService.return_value = mock_service
            mock_service.delete_instance = AsyncMock()

            # Run lifecycle job
            await run_lifecycle_job(session=db_session)

            # Verify delete was called
            mock_service.delete_instance.assert_called_once()
            call_args = mock_service.delete_instance.call_args
            assert call_args.kwargs["instance_id"] == instance.id

    async def test_lifecycle_does_not_terminate_unexpired_instance(
        self, db_session, instance_repo, snapshot_repo, mapping_repo
    ):
        """Test lifecycle job does not terminate instance with valid TTL."""
        # Create mapping and snapshot first (required FKs)
        mapping = await mapping_repo.create(name="test-mapping", created_by="test-user", raw_schema={})
        snapshot = await snapshot_repo.create(name="test-snapshot", mapping_id=mapping.id, created_by="test-user")

        # Create instance with TTL="PT24H" created 1 hour ago (not expired)
        one_hour_ago = datetime.now(UTC) - timedelta(hours=1)
        instance = await instance_repo.create(
            mapping_id=mapping.id,
            snapshot_id=snapshot.id,
            created_by="test-user",
            wrapper_type=WrapperType.RYUGRAPH,
            ttl="PT24H",  # 24 hour TTL
        )

        # Update created_at to 1 hour ago
        await instance_repo.update(instance.id, {"created_at": one_hour_ago.isoformat()})

        # Mock instance service
        with patch("control_plane.jobs.lifecycle.InstanceService") as MockInstanceService:
            mock_service = AsyncMock()
            MockInstanceService.return_value = mock_service
            mock_service.delete_instance = AsyncMock()

            # Run lifecycle job
            await run_lifecycle_job(session=db_session)

            # Verify delete was NOT called
            mock_service.delete_instance.assert_not_called()

    async def test_lifecycle_terminates_inactive_instance(
        self, db_session, instance_repo, snapshot_repo, mapping_repo
    ):
        """Test lifecycle job terminates instance with expired inactivity timeout."""
        # Create mapping and snapshot first (required FKs)
        mapping = await mapping_repo.create(name="test-mapping", created_by="test-user", raw_schema={})
        snapshot = await snapshot_repo.create(name="test-snapshot", mapping_id=mapping.id, created_by="test-user")

        # Create running instance with inactivity timeout
        instance = await instance_repo.create(
            mapping_id=mapping.id,
            snapshot_id=snapshot.id,
            created_by="test-user",
            wrapper_type=WrapperType.RYUGRAPH,
            ttl=None,
            inactivity_timeout="PT4H",  # 4 hour timeout
        )

        # Update to RUNNING with last_activity_at 5 hours ago (expired)
        five_hours_ago = datetime.now(UTC) - timedelta(hours=5)
        await instance_repo.update(
            instance.id,
            {
                "status": InstanceStatus.RUNNING.value,
                "last_activity_at": five_hours_ago.isoformat(),
            },
        )

        # Mock instance service
        with patch("control_plane.jobs.lifecycle.InstanceService") as MockInstanceService:
            mock_service = AsyncMock()
            MockInstanceService.return_value = mock_service
            mock_service.delete_instance = AsyncMock()

            # Run lifecycle job
            await run_lifecycle_job(session=db_session)

            # Verify delete was called
            mock_service.delete_instance.assert_called_once()
            call_args = mock_service.delete_instance.call_args
            assert call_args.kwargs["instance_id"] == instance.id

    # =========================================================================
    # SNAPSHOT TEST DISABLED
    # This test is commented out as snapshot functionality has been disabled.
    # =========================================================================
    # async def test_lifecycle_deletes_ttl_expired_snapshot(
    #     self, db_session, snapshot_repo, mapping_repo
    # ):
    #     """Test lifecycle job deletes snapshot with expired TTL."""
    #     # Create mapping first (required FK)
    #     mapping = await mapping_repo.create(
    #         name="test-mapping",
    #         created_by="test-user",
    #         raw_schema={},
    #     )
    #
    #     # Create snapshot with TTL="P7D" created 8 days ago
    #     eight_days_ago = datetime.now(UTC) - timedelta(days=8)
    #     snapshot = await snapshot_repo.create(
    #         name="test-snapshot",
    #         mapping_id=mapping.id,
    #         created_by="test-user",
    #         ttl="P7D",  # 7 day TTL
    #     )
    #
    #     # Update created_at to 8 days ago
    #     await snapshot_repo.update(snapshot.id, {"created_at": eight_days_ago.isoformat()})
    #
    #     # Run lifecycle job with test session
    #     await run_lifecycle_job(session=db_session)
    #
    #     # Verify snapshot was deleted
    #     deleted_snapshot = await snapshot_repo.get(snapshot.id)
    #     assert deleted_snapshot is None

    async def test_lifecycle_deletes_ttl_expired_mapping(
        self, db_session, mapping_repo
    ):
        """Test lifecycle job deletes mapping with expired TTL."""
        # Create mapping with TTL="P30D" created 31 days ago
        thirty_one_days_ago = datetime.now(UTC) - timedelta(days=31)
        mapping = await mapping_repo.create(
            name="test-mapping",
            created_by="test-user",
            raw_schema={},
            ttl="P30D",  # 30 day TTL
        )

        # Update created_at to 31 days ago
        await mapping_repo.update(mapping.id, {"created_at": thirty_one_days_ago.isoformat()})

        # Run lifecycle job with test session
        await run_lifecycle_job(session=db_session)

        # Verify mapping was deleted
        deleted_mapping = await mapping_repo.get(mapping.id)
        assert deleted_mapping is None

    async def test_lifecycle_handles_multiple_expired_resources(
        self, db_session, instance_repo, snapshot_repo, mapping_repo
    ):
        """Test lifecycle job handles multiple expired resources in one pass."""
        # Create mapping
        mapping = await mapping_repo.create(
            name="test-mapping", created_by="test-user", raw_schema={}
        )

        # Create a snapshot for the instance (required FK)
        instance_snapshot = await snapshot_repo.create(
            name="instance-snapshot", mapping_id=mapping.id, created_by="test-user"
        )

        # Create expired instance (TTL="PT1H", created 2 hours ago)
        two_hours_ago = datetime.now(UTC) - timedelta(hours=2)
        instance = await instance_repo.create(
            mapping_id=mapping.id,
            snapshot_id=instance_snapshot.id,
            created_by="test-user",
            wrapper_type=WrapperType.RYUGRAPH,
            ttl="PT1H",
        )
        await instance_repo.update(instance.id, {"created_at": two_hours_ago.isoformat()})

        # Snapshot TTL deletion disabled in lifecycle.py - see lines 97-105
        # eight_days_ago = datetime.now(UTC) - timedelta(days=8)
        # snapshot = await snapshot_repo.create(
        #     name="test-snapshot",
        #     mapping_id=mapping.id,
        #     created_by="test-user",
        #     ttl="P7D",
        # )
        # await snapshot_repo.update(snapshot.id, {"created_at": eight_days_ago.isoformat()})

        # Create expired mapping (TTL="P30D", created 31 days ago)
        thirty_one_days_ago = datetime.now(UTC) - timedelta(days=31)
        expired_mapping = await mapping_repo.create(
            name="expired-mapping",
            created_by="test-user",
            raw_schema={},
            ttl="P30D",
        )
        await mapping_repo.update(expired_mapping.id, {"created_at": thirty_one_days_ago.isoformat()})

        # Mock instance service
        with patch("control_plane.jobs.lifecycle.InstanceService") as MockInstanceService:
            mock_service = AsyncMock()
            MockInstanceService.return_value = mock_service
            mock_service.delete_instance = AsyncMock()

            # Run lifecycle job
            await run_lifecycle_job(session=db_session)

            # Verify instance termination was called
            mock_service.delete_instance.assert_called_once()

            # Snapshot TTL deletion disabled in lifecycle.py - see lines 97-105
            # deleted_snapshot = await snapshot_repo.get(snapshot.id)
            # assert deleted_snapshot is None

            # Verify mapping was deleted
            deleted_mapping = await mapping_repo.get(expired_mapping.id)
            assert deleted_mapping is None

    async def test_lifecycle_ignores_failed_instance(
        self, db_session, instance_repo, snapshot_repo, mapping_repo
    ):
        """Test lifecycle job does not re-terminate failed instances."""
        # Create mapping and snapshot first (required FKs)
        mapping = await mapping_repo.create(name="test-mapping", created_by="test-user", raw_schema={})
        snapshot = await snapshot_repo.create(name="test-snapshot", mapping_id=mapping.id, created_by="test-user")

        # Create instance with expired TTL but already FAILED
        two_hours_ago = datetime.now(UTC) - timedelta(hours=2)
        instance = await instance_repo.create(
            mapping_id=mapping.id,
            snapshot_id=snapshot.id,
            created_by="test-user",
            wrapper_type=WrapperType.RYUGRAPH,
            ttl="PT1H",
        )
        await instance_repo.update(
            instance.id,
            {
                "created_at": two_hours_ago.isoformat(),
                "status": InstanceStatus.FAILED.value,
            },
        )

        # Mock instance service
        with patch("control_plane.jobs.lifecycle.InstanceService") as MockInstanceService:
            mock_service = AsyncMock()
            MockInstanceService.return_value = mock_service
            mock_service.delete_instance = AsyncMock()

            # Run lifecycle job
            await run_lifecycle_job(session=db_session)

            # Verify delete was NOT called (instance already FAILED)
            mock_service.delete_instance.assert_not_called()


# Use pytest-asyncio for async tests
pytest_plugins = ("pytest_asyncio",)
