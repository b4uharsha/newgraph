"""Unit tests for service layer with mocks."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from control_plane.models import (
    DependencyError,
    NotFoundError,
    PermissionDeniedError,
    RequestUser,
    SnapshotStatus,
    User,
    UserRole,
)
from control_plane.models.requests import CreateMappingRequest, CreateSnapshotRequest
from control_plane.services.mapping_service import MappingService
from control_plane.services.snapshot_service import SnapshotService
from tests.fixtures.data import (
    create_test_mapping,
    create_test_node_definitions,
    create_test_snapshot,
)


class TestMappingService:
    """Tests for MappingService."""

    @pytest.fixture
    def mock_mapping_repo(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def mock_snapshot_repo(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def mock_favorites_repo(self) -> MagicMock:
        """Mock FavoritesRepository with default return values."""
        mock = MagicMock()
        mock.remove_for_resource = AsyncMock(return_value=0)
        return mock

    @pytest.fixture
    def service(
        self, mock_mapping_repo: MagicMock, mock_snapshot_repo: MagicMock, mock_favorites_repo: MagicMock
    ) -> MappingService:
        return MappingService(
            mapping_repo=mock_mapping_repo,
            snapshot_repo=mock_snapshot_repo,
            favorites_repo=mock_favorites_repo,
        )

    @pytest.fixture
    def sample_user(self) -> RequestUser:
        """Create a sample analyst user for service tests."""
        return RequestUser(
            username="alice.smith",
            role=UserRole.ANALYST,
            email="alice.smith@example.com",
            display_name="Alice Smith",
            is_active=True,
        )

    @pytest.fixture
    def admin_user(self) -> RequestUser:
        """Create an admin user for service tests."""
        return RequestUser(
            username="bob.admin",
            role=UserRole.ADMIN,
            email="bob.admin@example.com",
            display_name="Bob Admin",
            is_active=True,
        )

    @pytest.mark.asyncio
    async def test_get_mapping_success(
        self,
        service: MappingService,
        mock_mapping_repo: MagicMock,
    ):
        """Test getting a mapping by ID."""
        expected = create_test_mapping(mapping_id=1)
        mock_mapping_repo.get_by_id = AsyncMock(return_value=expected)

        result = await service.get_mapping(1)

        assert result.id == 1
        mock_mapping_repo.get_by_id.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_get_mapping_not_found(
        self,
        service: MappingService,
        mock_mapping_repo: MagicMock,
    ):
        """Test getting a non-existent mapping raises NotFoundError."""
        mock_mapping_repo.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(NotFoundError) as exc_info:
            await service.get_mapping(999)

        assert exc_info.value.status == 404

    @pytest.mark.asyncio
    async def test_create_mapping_success(
        self,
        service: MappingService,
        mock_mapping_repo: MagicMock,
        sample_user: User,
    ):
        """Test creating a mapping."""
        expected = create_test_mapping(mapping_id=1, owner_username=sample_user.username)
        mock_mapping_repo.create = AsyncMock(return_value=expected)

        request = CreateMappingRequest(
            name="Test Mapping",
            description="A test",
            node_definitions=[
                {
                    "label": "Customer",
                    "sql": "SELECT * FROM customers",
                    "primary_key": {"name": "id", "type": "STRING"},
                    "properties": [],
                }
            ],
            edge_definitions=[],
        )

        result = await service.create_mapping(sample_user, request)

        assert result.owner_username == sample_user.username
        mock_mapping_repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_mapping_owner_success(
        self,
        service: MappingService,
        mock_mapping_repo: MagicMock,
        sample_user: User,
    ):
        """Test owner can delete their mapping."""
        mapping = create_test_mapping(mapping_id=1, owner_username=sample_user.username)
        mock_mapping_repo.get_by_id = AsyncMock(return_value=mapping)
        mock_mapping_repo.get_snapshot_count = AsyncMock(return_value=0)
        mock_mapping_repo.delete = AsyncMock(return_value=True)

        await service.delete_mapping(sample_user, 1)

        mock_mapping_repo.delete.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_delete_mapping_other_user_denied(
        self,
        service: MappingService,
        mock_mapping_repo: MagicMock,
        sample_user: User,
    ):
        """Test non-owner cannot delete mapping."""
        mapping = create_test_mapping(mapping_id=1, owner_username="other.user")
        mock_mapping_repo.get_by_id = AsyncMock(return_value=mapping)

        with pytest.raises(PermissionDeniedError) as exc_info:
            await service.delete_mapping(sample_user, 1)

        assert exc_info.value.status == 403

    @pytest.mark.asyncio
    async def test_delete_mapping_admin_allowed(
        self,
        service: MappingService,
        mock_mapping_repo: MagicMock,
        admin_user: User,
    ):
        """Test admin can delete any mapping."""
        mapping = create_test_mapping(mapping_id=1, owner_username="other.user")
        mock_mapping_repo.get_by_id = AsyncMock(return_value=mapping)
        mock_mapping_repo.get_snapshot_count = AsyncMock(return_value=0)
        mock_mapping_repo.delete = AsyncMock(return_value=True)

        await service.delete_mapping(admin_user, 1)

        mock_mapping_repo.delete.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_delete_mapping_with_snapshots_denied(
        self,
        service: MappingService,
        mock_mapping_repo: MagicMock,
        sample_user: User,
    ):
        """Test cannot delete mapping with snapshots."""
        mapping = create_test_mapping(mapping_id=1, owner_username=sample_user.username)
        mock_mapping_repo.get_by_id = AsyncMock(return_value=mapping)
        mock_mapping_repo.get_snapshot_count = AsyncMock(return_value=3)

        with pytest.raises(DependencyError) as exc_info:
            await service.delete_mapping(sample_user, 1)

        assert exc_info.value.status == 409
        assert exc_info.value.details["dependent_count"] == 3


# =============================================================================
# SNAPSHOT TESTS DISABLED
# These tests are commented out as snapshot functionality has been disabled.
# =============================================================================
# class TestSnapshotService:
#     """Tests for SnapshotService."""
#
#     @pytest.fixture
#     def mock_snapshot_repo(self) -> MagicMock:
#         return MagicMock()
#
#     @pytest.fixture
#     def mock_mapping_repo(self) -> MagicMock:
#         return MagicMock()
#
#     @pytest.fixture
#     def mock_export_job_repo(self) -> MagicMock:
#         return MagicMock()
#
#     @pytest.fixture
#     def mock_config_repo(self) -> MagicMock:
#         return MagicMock()
#
#     @pytest.fixture
#     def mock_favorites_repo(self) -> MagicMock:
#         """Mock FavoritesRepository with default return values."""
#         mock = MagicMock()
#         mock.remove_for_resource = AsyncMock(return_value=0)
#         return mock
#
#     @pytest.fixture
#     def service(
#         self,
#         mock_snapshot_repo: MagicMock,
#         mock_mapping_repo: MagicMock,
#         mock_export_job_repo: MagicMock,
#         mock_config_repo: MagicMock,
#         mock_favorites_repo: MagicMock,
#     ) -> SnapshotService:
#         return SnapshotService(
#             snapshot_repo=mock_snapshot_repo,
#             mapping_repo=mock_mapping_repo,
#             export_job_repo=mock_export_job_repo,
#             config_repo=mock_config_repo,
#             favorites_repo=mock_favorites_repo,
#         )
#
#     @pytest.fixture
#     def sample_user(self) -> RequestUser:
#         """Create a sample analyst user for snapshot service tests."""
#         return RequestUser(
#             username="alice.smith",
#             role=UserRole.ANALYST,
#             email="alice.smith@example.com",
#             display_name="Alice Smith",
#             is_active=True,
#         )
#
#     @pytest.mark.asyncio
#     async def test_create_snapshot_success(
#         self,
#         service: SnapshotService,
#         mock_snapshot_repo: MagicMock,
#         mock_mapping_repo: MagicMock,
#         mock_export_job_repo: MagicMock,
#         mock_config_repo: MagicMock,
#         sample_user: RequestUser,
#     ):
#         """Test creating a snapshot."""
#         # Setup mocks
#         mapping = create_test_mapping(mapping_id=1)
#         mock_mapping_repo.get_by_id = AsyncMock(return_value=mapping)
#
#         from control_plane.models import MappingVersion
#
#         version = MappingVersion(
#             mapping_id=1,
#             version=1,
#             node_definitions=create_test_node_definitions(2),
#             edge_definitions=[],
#             change_description=None,
#             created_at=mapping.created_at,
#             created_by=mapping.owner_username,
#         )
#         mock_mapping_repo.get_version = AsyncMock(return_value=version)
#
#         expected_snapshot = create_test_snapshot(
#             snapshot_id=1,
#             mapping_version=1,
#             status=SnapshotStatus.PENDING,
#         )
#         mock_snapshot_repo.create = AsyncMock(return_value=expected_snapshot)
#         # After create, update_gcs_path is called to set the final path with snapshot_id
#         mock_snapshot_repo.update_gcs_path = AsyncMock(return_value=expected_snapshot)
#         mock_export_job_repo.create_batch = AsyncMock(return_value=[])
#         mock_config_repo.get_lifecycle_config = AsyncMock(
#             return_value={"default_ttl": "P7D", "default_inactivity": "P3D"}
#         )
#
#         request = CreateSnapshotRequest(
#             mapping_id=1,
#             name="Test Snapshot",
#             description="A test snapshot",
#         )
#
#         result = await service.create_snapshot(sample_user, request)
#
#         assert result.status == SnapshotStatus.PENDING
#         mock_snapshot_repo.create.assert_called_once()
#         mock_snapshot_repo.update_gcs_path.assert_called_once()
#         mock_export_job_repo.create_batch.assert_called_once()
#
#     @pytest.mark.asyncio
#     async def test_create_snapshot_mapping_not_found(
#         self,
#         service: SnapshotService,
#         mock_mapping_repo: MagicMock,
#         sample_user: User,
#     ):
#         """Test creating snapshot with invalid mapping raises error."""
#         mock_mapping_repo.get_by_id = AsyncMock(return_value=None)
#
#         request = CreateSnapshotRequest(
#             mapping_id=999,
#             name="Test Snapshot",
#         )
#
#         with pytest.raises(NotFoundError):
#             await service.create_snapshot(sample_user, request)
#
#     @pytest.mark.asyncio
#     async def test_delete_snapshot_with_instances_denied(
#         self,
#         service: SnapshotService,
#         mock_snapshot_repo: MagicMock,
#         sample_user: User,
#     ):
#         """Test cannot delete snapshot with active instances."""
#         snapshot = create_test_snapshot(
#             snapshot_id=1,
#             owner_username=sample_user.username,
#         )
#         mock_snapshot_repo.get_by_id = AsyncMock(return_value=snapshot)
#         mock_snapshot_repo.get_instance_count = AsyncMock(return_value=2)
#
#         with pytest.raises(DependencyError) as exc_info:
#             await service.delete_snapshot(sample_user, 1)
#
#         assert exc_info.value.status == 409
#         assert exc_info.value.details["dependent_count"] == 2
