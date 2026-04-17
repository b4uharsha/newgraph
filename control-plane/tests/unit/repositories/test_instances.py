# =============================================================================
# SNAPSHOT TESTS DISABLED
# These tests are commented out as snapshot functionality has been disabled.
# =============================================================================
# """Unit tests for InstanceRepository - waiting_for_snapshot functionality.
#
# Tests the new repository methods that support the create_from_mapping workflow:
# - create_waiting_for_snapshot(): Create instance in WAITING_FOR_SNAPSHOT status
# - get_waiting_for_snapshot(): Get all instances waiting for their snapshots
# - transition_to_starting(): Move instance from waiting to starting status
# """
#
# import pytest
# import pytest_asyncio
# from sqlalchemy.ext.asyncio import AsyncSession
#
# from control_plane.models import InstanceStatus, SnapshotStatus
# from control_plane.repositories.instances import InstanceFilters, InstanceRepository
# from control_plane.repositories.mappings import MappingRepository
# from control_plane.repositories.snapshots import SnapshotRepository
# from control_plane.repositories.users import UserRepository
# from graph_olap_schemas import WrapperType
# from tests.fixtures.data import (
#     create_test_edge_definitions,
#     create_test_node_definitions,
#     create_test_user,
# )
#
#
# class TestInstanceRepositoryWaitingForSnapshot:
#     """Tests for InstanceRepository waiting_for_snapshot functionality."""
#
#     @pytest_asyncio.fixture
#     async def instance_repo(self, db_session: AsyncSession) -> InstanceRepository:
#         """Create instance repository."""
#         return InstanceRepository(db_session)
#
#     @pytest_asyncio.fixture
#     async def snapshot_repo(self, db_session: AsyncSession) -> SnapshotRepository:
#         """Create snapshot repository."""
#         return SnapshotRepository(db_session)
#
#     @pytest_asyncio.fixture
#     async def mapping_repo(self, db_session: AsyncSession) -> MappingRepository:
#         """Create mapping repository."""
#         return MappingRepository(db_session)
#
#     @pytest_asyncio.fixture
#     async def user_repo(self, db_session: AsyncSession) -> UserRepository:
#         """Create user repository."""
#         return UserRepository(db_session)
#
#     @pytest_asyncio.fixture
#     async def test_user(self, user_repo: UserRepository):
#         """Create a test user."""
#         user = create_test_user("test.user")
#         return await user_repo.create(user)
#
#     @pytest_asyncio.fixture
#     async def test_mapping(self, mapping_repo: MappingRepository, test_user):
#         """Create a test mapping."""
#         return await mapping_repo.create(
#             owner_username=test_user.username,
#             name="Test Mapping",
#             description="Test mapping for instances",
#             node_definitions=create_test_node_definitions(2),
#             edge_definitions=create_test_edge_definitions(1),
#         )
#
#     @pytest_asyncio.fixture
#     async def pending_snapshot(self, snapshot_repo: SnapshotRepository, test_mapping, test_user):
#         """Create a pending snapshot."""
#         return await snapshot_repo.create(
#             mapping_id=test_mapping.id,
#             mapping_version=1,
#             owner_username=test_user.username,
#             name="Pending Snapshot",
#             description="Test snapshot in pending status",
#             gcs_path=f"gs://test-bucket/{test_user.username}/{test_mapping.id}/v1/1/",
#         )
#
#     @pytest_asyncio.fixture
#     async def ready_snapshot(self, snapshot_repo: SnapshotRepository, test_mapping, test_user):
#         """Create a ready snapshot."""
#         snapshot = await snapshot_repo.create(
#             mapping_id=test_mapping.id,
#             mapping_version=1,
#             owner_username=test_user.username,
#             name="Ready Snapshot",
#             description="Test snapshot in ready status",
#             gcs_path=f"gs://test-bucket/{test_user.username}/{test_mapping.id}/v1/2/",
#         )
#         await snapshot_repo.update_status(
#             snapshot.id,
#             SnapshotStatus.READY,
#             size_bytes=1024000,
#             node_counts={"Customer": 100, "Product": 50},
#             edge_counts={"PURCHASED": 500},
#         )
#         return await snapshot_repo.get_by_id(snapshot.id)
#
#     @pytest.mark.asyncio
#     async def test_create_waiting_for_snapshot(
#         self,
#         instance_repo: InstanceRepository,
#         pending_snapshot,
#         test_user,
#     ):
#         """Test creating instance with WAITING_FOR_SNAPSHOT status."""
#         instance = await instance_repo.create_waiting_for_snapshot(
#             snapshot_id=pending_snapshot.id,
#             owner_username=test_user.username,
#             wrapper_type=WrapperType.FALKORDB,
#             name="Test Instance",
#             description="Instance waiting for snapshot",
#             url_slug="test-instance-abc123",
#         )
#
#         assert instance.id is not None
#         assert instance.snapshot_id == pending_snapshot.id
#         assert instance.status == InstanceStatus.WAITING_FOR_SNAPSHOT
#         assert instance.name == "Test Instance"
#         assert instance.wrapper_type == WrapperType.FALKORDB
#         assert instance.pod_name is None  # No pod until snapshot ready
#
#     @pytest.mark.asyncio
#     async def test_create_waiting_for_snapshot_with_lifecycle(
#         self,
#         instance_repo: InstanceRepository,
#         pending_snapshot,
#         test_user,
#     ):
#         """Test creating waiting instance with lifecycle settings."""
#         instance = await instance_repo.create_waiting_for_snapshot(
#             snapshot_id=pending_snapshot.id,
#             owner_username=test_user.username,
#             wrapper_type=WrapperType.RYUGRAPH,
#             name="Lifecycle Test",
#             url_slug="lifecycle-test-xyz",
#             ttl="PT48H",
#             inactivity_timeout="PT12H",
#         )
#
#         assert instance.status == InstanceStatus.WAITING_FOR_SNAPSHOT
#         assert instance.ttl == "PT48H"
#         assert instance.inactivity_timeout == "PT12H"
#
#     @pytest.mark.asyncio
#     async def test_get_waiting_for_snapshot_empty(
#         self,
#         instance_repo: InstanceRepository,
#     ):
#         """Test get_waiting_for_snapshot when no instances are waiting."""
#         instances = await instance_repo.get_waiting_for_snapshot()
#         assert instances == []
#
#     @pytest.mark.asyncio
#     async def test_get_waiting_for_snapshot_finds_waiting(
#         self,
#         instance_repo: InstanceRepository,
#         pending_snapshot,
#         test_user,
#     ):
#         """Test get_waiting_for_snapshot returns waiting instances."""
#         # Create waiting instance
#         await instance_repo.create_waiting_for_snapshot(
#             snapshot_id=pending_snapshot.id,
#             owner_username=test_user.username,
#             wrapper_type=WrapperType.FALKORDB,
#             name="Waiting Instance",
#             url_slug="waiting-abc",
#         )
#
#         instances = await instance_repo.get_waiting_for_snapshot()
#         assert len(instances) == 1
#         assert instances[0].status == InstanceStatus.WAITING_FOR_SNAPSHOT
#         assert instances[0].name == "Waiting Instance"
#
#     @pytest.mark.asyncio
#     async def test_get_waiting_for_snapshot_excludes_other_statuses(
#         self,
#         instance_repo: InstanceRepository,
#         pending_snapshot,
#         ready_snapshot,
#         test_user,
#     ):
#         """Test that get_waiting_for_snapshot excludes non-waiting instances."""
#         # Create waiting instance
#         await instance_repo.create_waiting_for_snapshot(
#             snapshot_id=pending_snapshot.id,
#             owner_username=test_user.username,
#             wrapper_type=WrapperType.FALKORDB,
#             name="Waiting Instance",
#             url_slug="waiting-123",
#         )
#
#         # Create starting instance (normal path) - url_slug is auto-generated
#         starting = await instance_repo.create(
#             snapshot_id=ready_snapshot.id,
#             owner_username=test_user.username,
#             wrapper_type=WrapperType.RYUGRAPH,
#             name="Starting Instance",
#             description=None,
#         )
#         # Normal create() should create in STARTING status
#
#         instances = await instance_repo.get_waiting_for_snapshot()
#         assert len(instances) == 1
#         assert instances[0].name == "Waiting Instance"
#
#     @pytest.mark.asyncio
#     async def test_get_waiting_for_snapshot_includes_snapshot_info(
#         self,
#         instance_repo: InstanceRepository,
#         pending_snapshot,
#         test_user,
#     ):
#         """Test that get_waiting_for_snapshot includes snapshot status info."""
#         await instance_repo.create_waiting_for_snapshot(
#             snapshot_id=pending_snapshot.id,
#             owner_username=test_user.username,
#             wrapper_type=WrapperType.FALKORDB,
#             name="Instance With Snapshot Info",
#             url_slug="info-test-789",
#         )
#
#         instances = await instance_repo.get_waiting_for_snapshot()
#         assert len(instances) == 1
#
#         # The returned instance should have snapshot info attached
#         instance = instances[0]
#         assert instance.snapshot_id == pending_snapshot.id
#         # Depending on implementation, snapshot status might be attached
#
#     @pytest.mark.asyncio
#     async def test_transition_to_starting_success(
#         self,
#         instance_repo: InstanceRepository,
#         snapshot_repo: SnapshotRepository,
#         pending_snapshot,
#         test_user,
#     ):
#         """Test successful transition from WAITING_FOR_SNAPSHOT to STARTING."""
#         # Create waiting instance
#         instance = await instance_repo.create_waiting_for_snapshot(
#             snapshot_id=pending_snapshot.id,
#             owner_username=test_user.username,
#             wrapper_type=WrapperType.FALKORDB,
#             name="Transition Test",
#             url_slug="transition-abc",
#         )
#         assert instance.status == InstanceStatus.WAITING_FOR_SNAPSHOT
#
#         # Mark snapshot as ready
#         await snapshot_repo.update_status(
#             pending_snapshot.id,
#             SnapshotStatus.READY,
#             size_bytes=1024000,
#             node_counts={"Customer": 100},
#             edge_counts={},
#         )
#
#         # Transition to starting
#         updated = await instance_repo.transition_to_starting(instance.id)
#
#         assert updated is not None
#         assert updated.status == InstanceStatus.STARTING
#         assert updated.id == instance.id
#
#     @pytest.mark.asyncio
#     async def test_transition_to_starting_not_waiting(
#         self,
#         instance_repo: InstanceRepository,
#         ready_snapshot,
#         test_user,
#     ):
#         """Test transition_to_starting fails for non-waiting instance."""
#         # Create normal starting instance - url_slug is auto-generated
#         instance = await instance_repo.create(
#             snapshot_id=ready_snapshot.id,
#             owner_username=test_user.username,
#             wrapper_type=WrapperType.FALKORDB,
#             name="Already Starting",
#             description=None,
#         )
#
#         # Attempt to transition (should fail or return None)
#         result = await instance_repo.transition_to_starting(instance.id)
#
#         # Either returns None or raises an error
#         if result is not None:
#             # If it doesn't return None, it should still be STARTING
#             assert result.status == InstanceStatus.STARTING
#
#     @pytest.mark.asyncio
#     async def test_transition_to_failed(
#         self,
#         instance_repo: InstanceRepository,
#         snapshot_repo: SnapshotRepository,
#         pending_snapshot,
#         test_user,
#     ):
#         """Test transitioning waiting instance to FAILED when snapshot fails."""
#         # Create waiting instance
#         instance = await instance_repo.create_waiting_for_snapshot(
#             snapshot_id=pending_snapshot.id,
#             owner_username=test_user.username,
#             wrapper_type=WrapperType.FALKORDB,
#             name="Will Fail",
#             url_slug="will-fail-xyz",
#         )
#
#         # Mark snapshot as failed
#         await snapshot_repo.update_status(
#             pending_snapshot.id,
#             SnapshotStatus.FAILED,
#             error_message="Export failed: Connection timeout",
#         )
#
#         # Mark instance as failed
#         updated = await instance_repo.update_status(
#             instance.id,
#             InstanceStatus.FAILED,
#             error_message="Snapshot creation failed",
#         )
#
#         assert updated.status == InstanceStatus.FAILED
#         assert "Snapshot" in updated.error_message
#
#     @pytest.mark.asyncio
#     async def test_count_by_owner_includes_waiting(
#         self,
#         instance_repo: InstanceRepository,
#         pending_snapshot,
#         ready_snapshot,
#         test_user,
#     ):
#         """Test that count_by_owner includes WAITING_FOR_SNAPSHOT instances."""
#         # Create waiting instance
#         await instance_repo.create_waiting_for_snapshot(
#             snapshot_id=pending_snapshot.id,
#             owner_username=test_user.username,
#             wrapper_type=WrapperType.FALKORDB,
#             name="Waiting",
#             url_slug="waiting-count-1",
#         )
#
#         # Create starting instance - url_slug is auto-generated
#         await instance_repo.create(
#             snapshot_id=ready_snapshot.id,
#             owner_username=test_user.username,
#             wrapper_type=WrapperType.RYUGRAPH,
#             name="Starting",
#             description=None,
#         )
#
#         # Count should include both
#         count = await instance_repo.count_by_owner(test_user.username)
#         assert count == 2
#
#     @pytest.mark.asyncio
#     async def test_count_total_active_includes_waiting(
#         self,
#         instance_repo: InstanceRepository,
#         pending_snapshot,
#         test_user,
#     ):
#         """Test that count_total_active includes WAITING_FOR_SNAPSHOT instances."""
#         # Create waiting instance
#         await instance_repo.create_waiting_for_snapshot(
#             snapshot_id=pending_snapshot.id,
#             owner_username=test_user.username,
#             wrapper_type=WrapperType.FALKORDB,
#             name="Active Waiting",
#             url_slug="active-waiting-1",
#         )
#
#         # WAITING_FOR_SNAPSHOT should count as active
#         count = await instance_repo.count_total_active()
#         assert count >= 1
#
#     @pytest.mark.asyncio
#     async def test_list_includes_waiting_for_snapshot_status(
#         self,
#         instance_repo: InstanceRepository,
#         pending_snapshot,
#         test_user,
#     ):
#         """Test that list() can filter by WAITING_FOR_SNAPSHOT status."""
#         # Create waiting instance
#         await instance_repo.create_waiting_for_snapshot(
#             snapshot_id=pending_snapshot.id,
#             owner_username=test_user.username,
#             wrapper_type=WrapperType.FALKORDB,
#             name="Listed Waiting",
#             url_slug="listed-waiting-1",
#         )
#
#         # List with status filter
#         filters = InstanceFilters(status=InstanceStatus.WAITING_FOR_SNAPSHOT)
#         instances, total = await instance_repo.list_instances(filters)
#
#         assert len(instances) >= 1
#         assert all(i.status == InstanceStatus.WAITING_FOR_SNAPSHOT for i in instances)
