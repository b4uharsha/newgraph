"""Unit tests for InstanceService - create_from_mapping functionality.

Tests the new create_from_mapping() method that allows creating instances
directly from a mapping, which internally:
1. Validates the mapping exists
2. Checks concurrency limits
3. Creates a snapshot
4. Creates an instance with status='waiting_for_snapshot'
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from graph_olap_schemas import WrapperType

from control_plane.models import (
    ConcurrencyLimitError,
    Instance,
    InstanceStatus,
    Mapping,
    MappingVersion,
    NotFoundError,
    RequestUser,
    Snapshot,
    SnapshotStatus,
    UserRole,
)
from control_plane.models.requests import CreateInstanceFromMappingRequest
from control_plane.repositories.instances import InstanceRepository
from control_plane.services.instance_service import InstanceService
from tests.fixtures.data import (
    create_test_mapping,
    create_test_node_definitions,
    create_test_snapshot,
)


class TestInstanceServiceCreateFromMapping:
    """Tests for InstanceService.create_from_mapping()."""

    @pytest.fixture
    def mock_instance_repo(self) -> MagicMock:
        """Create mock instance repository."""
        return MagicMock(spec=InstanceRepository)

    @pytest.fixture
    def mock_snapshot_repo(self) -> MagicMock:
        """Create mock snapshot repository."""
        return MagicMock()

    @pytest.fixture
    def mock_mapping_repo(self) -> MagicMock:
        """Create mock mapping repository."""
        return MagicMock()

    @pytest.fixture
    def mock_config_repo(self) -> MagicMock:
        """Create mock config repository."""
        return MagicMock()

    @pytest.fixture
    def mock_favorites_repo(self) -> MagicMock:
        """Create mock favorites repository."""
        mock = MagicMock()
        mock.remove_for_resource = AsyncMock(return_value=0)
        return mock

    @pytest.fixture
    def mock_snapshot_service(self) -> MagicMock:
        """Create mock snapshot service."""
        return MagicMock()

    @pytest.fixture
    def sample_user(self) -> RequestUser:
        """Create a sample analyst user."""
        return RequestUser(
            username="alice.smith",
            role=UserRole.ANALYST,
            email="alice.smith@example.com",
            display_name="Alice Smith",
            is_active=True,
        )

    @pytest.fixture
    def sample_mapping(self) -> Mapping:
        """Create a sample mapping."""
        return create_test_mapping(
            mapping_id=1,
            owner_username="alice.smith",
            name="Test Mapping",
            current_version=1,
        )

    @pytest.fixture
    def sample_mapping_version(self, sample_mapping: Mapping) -> MappingVersion:
        """Create a sample mapping version."""
        return MappingVersion(
            mapping_id=sample_mapping.id,
            version=1,
            node_definitions=create_test_node_definitions(2),
            edge_definitions=[],
            change_description=None,
            created_at=sample_mapping.created_at,
            created_by=sample_mapping.owner_username,
        )

    @pytest.fixture
    def sample_pending_snapshot(self, sample_mapping: Mapping) -> Snapshot:
        """Create a sample pending snapshot."""
        return create_test_snapshot(
            snapshot_id=1,
            mapping_id=sample_mapping.id,
            mapping_version=1,
            owner_username="alice.smith",
            status=SnapshotStatus.PENDING,
        )

    @pytest.fixture
    def service(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_config_repo: MagicMock,
        mock_favorites_repo: MagicMock,
        mock_mapping_repo: MagicMock,
        mock_snapshot_service: MagicMock,
    ) -> InstanceService:
        """Create instance service with mocks."""
        service = InstanceService(
            instance_repo=mock_instance_repo,
            snapshot_repo=mock_snapshot_repo,
            config_repo=mock_config_repo,
            favorites_repo=mock_favorites_repo,
        )
        # Inject additional dependencies needed for create_from_mapping
        service._mapping_repo = mock_mapping_repo
        service._snapshot_service = mock_snapshot_service
        return service

    @pytest.mark.asyncio
    async def test_create_from_mapping_success(
        self,
        service: InstanceService,
        mock_instance_repo: MagicMock,
        mock_mapping_repo: MagicMock,
        mock_snapshot_service: MagicMock,
        mock_config_repo: MagicMock,
        sample_user: RequestUser,
        sample_mapping: Mapping,
        sample_mapping_version: MappingVersion,
        sample_pending_snapshot: Snapshot,
    ):
        """Test successful instance creation from mapping."""
        # Setup mocks
        mock_mapping_repo.get_by_id = AsyncMock(return_value=sample_mapping)
        mock_mapping_repo.get_version = AsyncMock(return_value=sample_mapping_version)
        mock_config_repo.get_concurrency_limits = AsyncMock(
            return_value={"per_analyst": 5, "cluster_total": 100}
        )
        mock_instance_repo.count_by_owner = AsyncMock(return_value=2)
        mock_instance_repo.count_total_active = AsyncMock(return_value=10)
        mock_config_repo.get_lifecycle_config = AsyncMock(
            return_value={"default_ttl": "PT24H", "default_inactivity": "PT8H"}
        )

        # Mock snapshot creation
        mock_snapshot_service.create_snapshot = AsyncMock(return_value=sample_pending_snapshot)

        # Mock instance creation
        now = datetime.now(UTC)
        expected_instance = Instance(
            id=1,
            snapshot_id=sample_pending_snapshot.id,
            owner_username=sample_user.username,
            wrapper_type=WrapperType.FALKORDB,
            name="Test Instance",
            description="Created from mapping",
            url_slug="uuid-slug",
            status=InstanceStatus.WAITING_FOR_SNAPSHOT,
            created_at=now,
            updated_at=now,
        )
        mock_instance_repo.create_waiting_for_snapshot = AsyncMock(return_value=expected_instance)

        # Create request
        request = CreateInstanceFromMappingRequest(
            mapping_id=sample_mapping.id,
            name="Test Instance",
            wrapper_type=WrapperType.FALKORDB,
            description="Created from mapping",
        )

        # Execute
        result = await service.create_from_mapping(sample_user, request)

        # Verify
        assert result.status == InstanceStatus.WAITING_FOR_SNAPSHOT
        assert result.name == "Test Instance"
        assert result.wrapper_type == WrapperType.FALKORDB
        mock_mapping_repo.get_by_id.assert_called_once_with(sample_mapping.id)
        mock_snapshot_service.create_snapshot.assert_called_once()
        mock_instance_repo.create_waiting_for_snapshot.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_from_mapping_with_specific_version(
        self,
        service: InstanceService,
        mock_instance_repo: MagicMock,
        mock_mapping_repo: MagicMock,
        mock_snapshot_service: MagicMock,
        mock_config_repo: MagicMock,
        sample_user: RequestUser,
        sample_mapping: Mapping,
        sample_mapping_version: MappingVersion,
        sample_pending_snapshot: Snapshot,
    ):
        """Test instance creation with specific mapping version."""
        # Setup mocks
        sample_mapping_v2 = MappingVersion(
            mapping_id=sample_mapping.id,
            version=2,
            node_definitions=create_test_node_definitions(3),
            edge_definitions=[],
            change_description="Added new node",
            created_at=sample_mapping.created_at,
            created_by=sample_mapping.owner_username,
        )
        mock_mapping_repo.get_by_id = AsyncMock(return_value=sample_mapping)
        mock_mapping_repo.get_version = AsyncMock(return_value=sample_mapping_v2)
        mock_config_repo.get_concurrency_limits = AsyncMock(
            return_value={"per_analyst": 5, "cluster_total": 100}
        )
        mock_instance_repo.count_by_owner = AsyncMock(return_value=0)
        mock_instance_repo.count_total_active = AsyncMock(return_value=0)
        mock_config_repo.get_lifecycle_config = AsyncMock(
            return_value={"default_ttl": "PT24H", "default_inactivity": "PT8H"}
        )
        mock_snapshot_service.create_snapshot = AsyncMock(return_value=sample_pending_snapshot)

        now = datetime.now(UTC)
        expected_instance = Instance(
            id=1,
            snapshot_id=sample_pending_snapshot.id,
            owner_username=sample_user.username,
            wrapper_type=WrapperType.FALKORDB,
            name="Test Instance",
            description=None,
            url_slug="uuid-slug",
            status=InstanceStatus.WAITING_FOR_SNAPSHOT,
            created_at=now,
            updated_at=now,
        )
        mock_instance_repo.create_waiting_for_snapshot = AsyncMock(return_value=expected_instance)

        # Create request with specific version
        request = CreateInstanceFromMappingRequest(
            mapping_id=sample_mapping.id,
            name="Test Instance",
            wrapper_type=WrapperType.FALKORDB,
            mapping_version=2,
        )

        # Execute
        result = await service.create_from_mapping(sample_user, request)

        # Verify mapping version was fetched with correct version
        mock_mapping_repo.get_version.assert_called_once_with(sample_mapping.id, 2)

    @pytest.mark.asyncio
    async def test_create_from_mapping_mapping_not_found(
        self,
        service: InstanceService,
        mock_mapping_repo: MagicMock,
        sample_user: RequestUser,
    ):
        """Test error when mapping doesn't exist."""
        mock_mapping_repo.get_by_id = AsyncMock(return_value=None)

        request = CreateInstanceFromMappingRequest(
            mapping_id=999,
            name="Test Instance",
            wrapper_type=WrapperType.FALKORDB,
        )

        with pytest.raises(NotFoundError) as exc_info:
            await service.create_from_mapping(sample_user, request)

        assert exc_info.value.status == 404
        assert "Mapping" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_from_mapping_version_not_found(
        self,
        service: InstanceService,
        mock_mapping_repo: MagicMock,
        sample_user: RequestUser,
        sample_mapping: Mapping,
    ):
        """Test error when mapping version doesn't exist."""
        mock_mapping_repo.get_by_id = AsyncMock(return_value=sample_mapping)
        mock_mapping_repo.get_version = AsyncMock(return_value=None)

        request = CreateInstanceFromMappingRequest(
            mapping_id=sample_mapping.id,
            name="Test Instance",
            wrapper_type=WrapperType.FALKORDB,
            mapping_version=99,
        )

        with pytest.raises(NotFoundError) as exc_info:
            await service.create_from_mapping(sample_user, request)

        assert exc_info.value.status == 404
        assert "MappingVersion" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_from_mapping_per_analyst_limit_exceeded(
        self,
        service: InstanceService,
        mock_instance_repo: MagicMock,
        mock_mapping_repo: MagicMock,
        mock_config_repo: MagicMock,
        sample_user: RequestUser,
        sample_mapping: Mapping,
        sample_mapping_version: MappingVersion,
    ):
        """Test error when per-analyst instance limit exceeded."""
        mock_mapping_repo.get_by_id = AsyncMock(return_value=sample_mapping)
        mock_mapping_repo.get_version = AsyncMock(return_value=sample_mapping_version)
        mock_config_repo.get_concurrency_limits = AsyncMock(
            return_value={"per_analyst": 5, "cluster_total": 100}
        )
        # User already at limit
        mock_instance_repo.count_by_owner = AsyncMock(return_value=5)
        mock_instance_repo.count_total_active = AsyncMock(return_value=10)

        request = CreateInstanceFromMappingRequest(
            mapping_id=sample_mapping.id,
            name="Test Instance",
            wrapper_type=WrapperType.FALKORDB,
        )

        with pytest.raises(ConcurrencyLimitError) as exc_info:
            await service.create_from_mapping(sample_user, request)

        assert exc_info.value.status == 409
        assert exc_info.value.details["limit_type"] == "per_analyst"

    @pytest.mark.asyncio
    async def test_create_from_mapping_cluster_limit_exceeded(
        self,
        service: InstanceService,
        mock_instance_repo: MagicMock,
        mock_mapping_repo: MagicMock,
        mock_config_repo: MagicMock,
        sample_user: RequestUser,
        sample_mapping: Mapping,
        sample_mapping_version: MappingVersion,
    ):
        """Test error when cluster-wide instance limit exceeded."""
        mock_mapping_repo.get_by_id = AsyncMock(return_value=sample_mapping)
        mock_mapping_repo.get_version = AsyncMock(return_value=sample_mapping_version)
        mock_config_repo.get_concurrency_limits = AsyncMock(
            return_value={"per_analyst": 5, "cluster_total": 100}
        )
        mock_instance_repo.count_by_owner = AsyncMock(return_value=2)
        # Cluster at limit
        mock_instance_repo.count_total_active = AsyncMock(return_value=100)

        request = CreateInstanceFromMappingRequest(
            mapping_id=sample_mapping.id,
            name="Test Instance",
            wrapper_type=WrapperType.FALKORDB,
        )

        with pytest.raises(ConcurrencyLimitError) as exc_info:
            await service.create_from_mapping(sample_user, request)

        assert exc_info.value.status == 409
        assert exc_info.value.details["limit_type"] == "cluster_total"

    @pytest.mark.asyncio
    async def test_create_from_mapping_with_lifecycle_settings(
        self,
        service: InstanceService,
        mock_instance_repo: MagicMock,
        mock_mapping_repo: MagicMock,
        mock_snapshot_service: MagicMock,
        mock_config_repo: MagicMock,
        sample_user: RequestUser,
        sample_mapping: Mapping,
        sample_mapping_version: MappingVersion,
        sample_pending_snapshot: Snapshot,
    ):
        """Test instance creation with custom lifecycle settings."""
        mock_mapping_repo.get_by_id = AsyncMock(return_value=sample_mapping)
        mock_mapping_repo.get_version = AsyncMock(return_value=sample_mapping_version)
        mock_config_repo.get_concurrency_limits = AsyncMock(
            return_value={"per_analyst": 5, "cluster_total": 100}
        )
        mock_instance_repo.count_by_owner = AsyncMock(return_value=0)
        mock_instance_repo.count_total_active = AsyncMock(return_value=0)
        mock_config_repo.get_lifecycle_config = AsyncMock(
            return_value={"default_ttl": "PT24H", "default_inactivity": "PT8H"}
        )
        mock_snapshot_service.create_snapshot = AsyncMock(return_value=sample_pending_snapshot)

        now = datetime.now(UTC)
        expected_instance = Instance(
            id=1,
            snapshot_id=sample_pending_snapshot.id,
            owner_username=sample_user.username,
            wrapper_type=WrapperType.FALKORDB,
            name="Test Instance",
            description=None,
            url_slug="uuid-slug",
            status=InstanceStatus.WAITING_FOR_SNAPSHOT,
            ttl="PT48H",
            inactivity_timeout="PT12H",
            created_at=now,
            updated_at=now,
        )
        mock_instance_repo.create_waiting_for_snapshot = AsyncMock(return_value=expected_instance)

        request = CreateInstanceFromMappingRequest(
            mapping_id=sample_mapping.id,
            name="Test Instance",
            wrapper_type=WrapperType.FALKORDB,
            ttl="PT48H",
            inactivity_timeout="PT12H",
        )

        result = await service.create_from_mapping(sample_user, request)

        # Verify lifecycle settings were passed
        create_call = mock_instance_repo.create_waiting_for_snapshot.call_args
        assert create_call.kwargs.get("ttl") == "PT48H" or create_call[1].get("ttl") == "PT48H"

    @pytest.mark.asyncio
    async def test_create_from_mapping_uses_current_version_by_default(
        self,
        service: InstanceService,
        mock_instance_repo: MagicMock,
        mock_mapping_repo: MagicMock,
        mock_snapshot_service: MagicMock,
        mock_config_repo: MagicMock,
        sample_user: RequestUser,
        sample_pending_snapshot: Snapshot,
    ):
        """Test that current mapping version is used when none specified."""
        # Mapping with current_version=3
        mapping = create_test_mapping(mapping_id=1, current_version=3)
        version = MappingVersion(
            mapping_id=1,
            version=3,
            node_definitions=create_test_node_definitions(2),
            edge_definitions=[],
            change_description=None,
            created_at=mapping.created_at,
            created_by=mapping.owner_username,
        )

        mock_mapping_repo.get_by_id = AsyncMock(return_value=mapping)
        mock_mapping_repo.get_version = AsyncMock(return_value=version)
        mock_config_repo.get_concurrency_limits = AsyncMock(
            return_value={"per_analyst": 5, "cluster_total": 100}
        )
        mock_instance_repo.count_by_owner = AsyncMock(return_value=0)
        mock_instance_repo.count_total_active = AsyncMock(return_value=0)
        mock_config_repo.get_lifecycle_config = AsyncMock(
            return_value={"default_ttl": "PT24H", "default_inactivity": "PT8H"}
        )
        mock_snapshot_service.create_snapshot = AsyncMock(return_value=sample_pending_snapshot)

        now = datetime.now(UTC)
        expected_instance = Instance(
            id=1,
            snapshot_id=sample_pending_snapshot.id,
            owner_username=sample_user.username,
            wrapper_type=WrapperType.FALKORDB,
            name="Test Instance",
            description=None,
            url_slug="uuid-slug",
            status=InstanceStatus.WAITING_FOR_SNAPSHOT,
            created_at=now,
            updated_at=now,
        )
        mock_instance_repo.create_waiting_for_snapshot = AsyncMock(return_value=expected_instance)

        # No mapping_version specified
        request = CreateInstanceFromMappingRequest(
            mapping_id=1,
            name="Test Instance",
            wrapper_type=WrapperType.FALKORDB,
        )

        await service.create_from_mapping(sample_user, request)

        # Should use current_version=3
        mock_mapping_repo.get_version.assert_called_once_with(1, 3)
