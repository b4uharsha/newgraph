"""Unit tests for memory upgrade functionality (Phase 3).

Tests the runtime memory scaling feature that allows users to increase memory allocation
for running instances using Kubernetes in-place pod resize (K8s 1.27+).

Key features tested:
- Memory validation (2-32 GB allowed)
- Permission checks (owner, admin, or ops required)
- State validation (instance must be running with pod)
- Memory increase-only enforcement (decreases rejected)
- Memory Guaranteed QoS (request == limit)
- K8s integration (resize_pod_memory called correctly)
"""

from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

import pytest
from graph_olap_schemas import WrapperType
from pydantic import BaseModel, Field, ValidationError

from control_plane.models import (
    Instance,
    InstanceStatus,
    InvalidStateError,
    NotFoundError,
    PermissionDeniedError,
    RequestUser,
    UserRole,
)
from control_plane.services.instance_service import InstanceService


# Define UpdateMemoryRequest inline for testing until it's added to graph_olap_schemas
class UpdateMemoryRequest(BaseModel):
    """Request to update memory allocation for a running instance."""

    memory_gb: int = Field(
        ...,
        ge=2,
        le=32,
        description="Memory in GB (2-32). Sets request=limit for Guaranteed QoS.",
    )


@pytest.fixture
def mock_instance_repo() -> MagicMock:
    """Create a mock instance repository."""
    repo = MagicMock()
    repo.get_by_id = AsyncMock()
    repo.update_memory_gb = AsyncMock()
    return repo


@pytest.fixture
def mock_snapshot_repo() -> MagicMock:
    """Create a mock snapshot repository."""
    return MagicMock()


@pytest.fixture
def mock_config_repo() -> MagicMock:
    """Create a mock config repository."""
    return MagicMock()


@pytest.fixture
def mock_favorites_repo() -> MagicMock:
    """Create a mock favorites repository."""
    mock = MagicMock()
    mock.remove_for_resource = AsyncMock(return_value=0)
    return mock


@pytest.fixture
def mock_k8s_service() -> MagicMock:
    """Create a mock K8s service."""
    service = MagicMock()
    service.resize_pod_memory = AsyncMock()
    service.is_pod_ready = AsyncMock(return_value=True)
    return service


@pytest.fixture
def admin_user() -> RequestUser:
    """Create an admin user."""
    return RequestUser(
        username="admin",
        email="admin@test.com",
        display_name="Admin User",
        role=UserRole.ADMIN,
    )


@pytest.fixture
def ops_user() -> RequestUser:
    """Create an ops user."""
    return RequestUser(
        username="ops_user",
        email="ops@test.com",
        display_name="Ops User",
        role=UserRole.OPS,
    )


@pytest.fixture
def regular_user() -> RequestUser:
    """Create a regular user (analyst)."""
    return RequestUser(
        username="user1",
        email="user1@test.com",
        display_name="User One",
        role=UserRole.ANALYST,
    )


@pytest.fixture
def other_user() -> RequestUser:
    """Create another regular user (not the owner)."""
    return RequestUser(
        username="other",
        email="other@test.com",
        display_name="Other User",
        role=UserRole.ANALYST,
    )


@pytest.fixture
def running_instance() -> Instance:
    """Create a running instance with pod_name and memory_gb."""
    return Instance(
        id=1,
        snapshot_id=1,
        owner_username="user1",
        wrapper_type=WrapperType.RYUGRAPH,
        name="Test Instance",
        description=None,
        status=InstanceStatus.RUNNING,
        pod_name="wrapper-abc123",
        url_slug="abc123",
        cpu_cores=2,
        memory_gb=4,  # Current memory is 4GB
    )


@pytest.fixture
def starting_instance() -> Instance:
    """Create a starting instance."""
    return Instance(
        id=2,
        snapshot_id=1,
        owner_username="user1",
        wrapper_type=WrapperType.RYUGRAPH,
        name="Starting Instance",
        description=None,
        status=InstanceStatus.STARTING,
        pod_name="wrapper-def456",
        url_slug="def456",
        cpu_cores=2,
        memory_gb=4,
    )


@pytest.fixture
def stopped_instance() -> Instance:
    """Create a stopped (failed) instance without pod."""
    return Instance(
        id=3,
        snapshot_id=1,
        owner_username="user1",
        wrapper_type=WrapperType.RYUGRAPH,
        name="Stopped Instance",
        description=None,
        status=InstanceStatus.FAILED,
        pod_name=None,
        url_slug="ghi789",
        cpu_cores=2,
        memory_gb=4,
    )


@pytest.fixture
def waiting_instance() -> Instance:
    """Create an instance waiting for snapshot."""
    return Instance(
        id=4,
        snapshot_id=1,
        owner_username="user1",
        wrapper_type=WrapperType.RYUGRAPH,
        name="Waiting Instance",
        description=None,
        status=InstanceStatus.WAITING_FOR_SNAPSHOT,
        pod_name=None,
        url_slug="jkl012",
        cpu_cores=2,
        memory_gb=4,
    )


def _make_service(
    instance_repo: MagicMock,
    snapshot_repo: MagicMock,
    config_repo: MagicMock,
    favorites_repo: MagicMock,
    k8s_service: MagicMock | None = None,
) -> InstanceService:
    """Create InstanceService with provided mocks."""
    return InstanceService(
        instance_repo=instance_repo,
        snapshot_repo=snapshot_repo,
        config_repo=config_repo,
        favorites_repo=favorites_repo,
        k8s_service=k8s_service,
    )


class TestUpdateMemoryRequest:
    """Tests for UpdateMemoryRequest validation."""

    def test_memory_gb_valid_minimum(self):
        """memory_gb=2 is valid (minimum)."""
        request = UpdateMemoryRequest(memory_gb=2)
        assert request.memory_gb == 2

    def test_memory_gb_valid_maximum(self):
        """memory_gb=32 is valid (maximum)."""
        request = UpdateMemoryRequest(memory_gb=32)
        assert request.memory_gb == 32

    def test_memory_gb_valid_mid_range(self):
        """memory_gb=16 is valid (middle of range)."""
        request = UpdateMemoryRequest(memory_gb=16)
        assert request.memory_gb == 16

    def test_memory_gb_below_minimum_rejected(self):
        """memory_gb=1 is rejected (below minimum)."""
        with pytest.raises(ValidationError) as exc_info:
            UpdateMemoryRequest(memory_gb=1)
        assert "memory_gb" in str(exc_info.value)

    def test_memory_gb_zero_rejected(self):
        """memory_gb=0 is rejected (zero)."""
        with pytest.raises(ValidationError) as exc_info:
            UpdateMemoryRequest(memory_gb=0)
        assert "memory_gb" in str(exc_info.value)

    def test_memory_gb_negative_rejected(self):
        """memory_gb=-1 is rejected (negative)."""
        with pytest.raises(ValidationError) as exc_info:
            UpdateMemoryRequest(memory_gb=-1)
        assert "memory_gb" in str(exc_info.value)

    def test_memory_gb_above_maximum_rejected(self):
        """memory_gb=33 is rejected (above maximum)."""
        with pytest.raises(ValidationError) as exc_info:
            UpdateMemoryRequest(memory_gb=33)
        assert "memory_gb" in str(exc_info.value)

    def test_memory_gb_way_above_maximum_rejected(self):
        """memory_gb=64 is rejected (way above maximum)."""
        with pytest.raises(ValidationError) as exc_info:
            UpdateMemoryRequest(memory_gb=64)
        assert "memory_gb" in str(exc_info.value)

    def test_memory_gb_required(self):
        """memory_gb is required."""
        with pytest.raises(ValidationError) as exc_info:
            UpdateMemoryRequest()  # type: ignore[call-arg]
        assert "memory_gb" in str(exc_info.value)


class TestUpdateMemoryPermissions:
    """Tests for memory upgrade permissions."""

    @pytest.mark.asyncio
    async def test_owner_can_upgrade_memory(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_config_repo: MagicMock,
        mock_favorites_repo: MagicMock,
        mock_k8s_service: MagicMock,
        regular_user: RequestUser,
        running_instance: Instance,
    ):
        """Test that owner can upgrade memory."""
        mock_instance_repo.get_by_id.return_value = running_instance
        updated_instance = replace(running_instance, memory_gb=8)
        mock_instance_repo.update_memory_gb.return_value = updated_instance

        service = _make_service(
            mock_instance_repo,
            mock_snapshot_repo,
            mock_config_repo,
            mock_favorites_repo,
            mock_k8s_service,
        )

        result = await service.update_memory(regular_user, 1, 8)

        assert result.memory_gb == 8
        mock_k8s_service.resize_pod_memory.assert_called_once()

    @pytest.mark.asyncio
    async def test_admin_can_upgrade_memory(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_config_repo: MagicMock,
        mock_favorites_repo: MagicMock,
        mock_k8s_service: MagicMock,
        admin_user: RequestUser,
        running_instance: Instance,
    ):
        """Test that admin can upgrade memory for other users' instances."""
        mock_instance_repo.get_by_id.return_value = running_instance
        updated_instance = replace(running_instance, memory_gb=8)
        mock_instance_repo.update_memory_gb.return_value = updated_instance

        service = _make_service(
            mock_instance_repo,
            mock_snapshot_repo,
            mock_config_repo,
            mock_favorites_repo,
            mock_k8s_service,
        )

        result = await service.update_memory(admin_user, 1, 8)

        assert result.memory_gb == 8
        mock_k8s_service.resize_pod_memory.assert_called_once()

    @pytest.mark.asyncio
    async def test_ops_can_upgrade_memory(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_config_repo: MagicMock,
        mock_favorites_repo: MagicMock,
        mock_k8s_service: MagicMock,
        ops_user: RequestUser,
        running_instance: Instance,
    ):
        """Test that ops user can upgrade memory for other users' instances."""
        mock_instance_repo.get_by_id.return_value = running_instance
        updated_instance = replace(running_instance, memory_gb=16)
        mock_instance_repo.update_memory_gb.return_value = updated_instance

        service = _make_service(
            mock_instance_repo,
            mock_snapshot_repo,
            mock_config_repo,
            mock_favorites_repo,
            mock_k8s_service,
        )

        result = await service.update_memory(ops_user, 1, 16)

        assert result.memory_gb == 16
        mock_k8s_service.resize_pod_memory.assert_called_once()

    @pytest.mark.asyncio
    async def test_non_owner_cannot_upgrade_memory(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_config_repo: MagicMock,
        mock_favorites_repo: MagicMock,
        mock_k8s_service: MagicMock,
        other_user: RequestUser,
        running_instance: Instance,
    ):
        """Test that non-owner analyst cannot upgrade memory."""
        mock_instance_repo.get_by_id.return_value = running_instance

        service = _make_service(
            mock_instance_repo,
            mock_snapshot_repo,
            mock_config_repo,
            mock_favorites_repo,
            mock_k8s_service,
        )

        with pytest.raises(PermissionDeniedError) as exc_info:
            await service.update_memory(other_user, 1, 8)

        assert exc_info.value.status == 403
        assert "Instance" in exc_info.value.message
        mock_k8s_service.resize_pod_memory.assert_not_called()

    @pytest.mark.asyncio
    async def test_instance_not_found(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_config_repo: MagicMock,
        mock_favorites_repo: MagicMock,
        mock_k8s_service: MagicMock,
        regular_user: RequestUser,
    ):
        """Test error when instance doesn't exist."""
        mock_instance_repo.get_by_id.return_value = None

        service = _make_service(
            mock_instance_repo,
            mock_snapshot_repo,
            mock_config_repo,
            mock_favorites_repo,
            mock_k8s_service,
        )

        with pytest.raises(NotFoundError) as exc_info:
            await service.update_memory(regular_user, 999, 8)

        assert exc_info.value.status == 404
        assert "Instance" in exc_info.value.message


class TestUpdateMemoryStateValidation:
    """Tests for instance state validation."""

    @pytest.mark.asyncio
    async def test_running_instance_allowed(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_config_repo: MagicMock,
        mock_favorites_repo: MagicMock,
        mock_k8s_service: MagicMock,
        regular_user: RequestUser,
        running_instance: Instance,
    ):
        """Test that memory upgrade is allowed for running instances."""
        mock_instance_repo.get_by_id.return_value = running_instance
        updated_instance = replace(running_instance, memory_gb=8)
        mock_instance_repo.update_memory_gb.return_value = updated_instance

        service = _make_service(
            mock_instance_repo,
            mock_snapshot_repo,
            mock_config_repo,
            mock_favorites_repo,
            mock_k8s_service,
        )

        result = await service.update_memory(regular_user, 1, 8)

        assert result.memory_gb == 8
        mock_k8s_service.resize_pod_memory.assert_called_once()

    @pytest.mark.asyncio
    async def test_starting_instance_rejected(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_config_repo: MagicMock,
        mock_favorites_repo: MagicMock,
        mock_k8s_service: MagicMock,
        regular_user: RequestUser,
        starting_instance: Instance,
    ):
        """Test that memory upgrade is rejected for starting instances (409)."""
        mock_instance_repo.get_by_id.return_value = starting_instance

        service = _make_service(
            mock_instance_repo,
            mock_snapshot_repo,
            mock_config_repo,
            mock_favorites_repo,
            mock_k8s_service,
        )

        with pytest.raises(InvalidStateError) as exc_info:
            await service.update_memory(regular_user, 2, 8)

        assert exc_info.value.status == 409
        mock_k8s_service.resize_pod_memory.assert_not_called()

    @pytest.mark.asyncio
    async def test_failed_instance_rejected(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_config_repo: MagicMock,
        mock_favorites_repo: MagicMock,
        mock_k8s_service: MagicMock,
        regular_user: RequestUser,
        stopped_instance: Instance,
    ):
        """Test that memory upgrade is rejected for failed instances (409)."""
        # Adjust owner to match regular_user
        stopped_instance = replace(stopped_instance, owner_username="user1")
        mock_instance_repo.get_by_id.return_value = stopped_instance

        service = _make_service(
            mock_instance_repo,
            mock_snapshot_repo,
            mock_config_repo,
            mock_favorites_repo,
            mock_k8s_service,
        )

        with pytest.raises(InvalidStateError) as exc_info:
            await service.update_memory(regular_user, 3, 8)

        assert exc_info.value.status == 409
        assert "failed" in exc_info.value.message.lower()
        assert "running" in exc_info.value.message.lower()
        mock_k8s_service.resize_pod_memory.assert_not_called()

    @pytest.mark.asyncio
    async def test_waiting_instance_rejected(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_config_repo: MagicMock,
        mock_favorites_repo: MagicMock,
        mock_k8s_service: MagicMock,
        regular_user: RequestUser,
        waiting_instance: Instance,
    ):
        """Test that memory upgrade is rejected for waiting instances (409)."""
        mock_instance_repo.get_by_id.return_value = waiting_instance

        service = _make_service(
            mock_instance_repo,
            mock_snapshot_repo,
            mock_config_repo,
            mock_favorites_repo,
            mock_k8s_service,
        )

        with pytest.raises(InvalidStateError) as exc_info:
            await service.update_memory(regular_user, 4, 8)

        assert exc_info.value.status == 409
        mock_k8s_service.resize_pod_memory.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_pod_name_rejected(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_config_repo: MagicMock,
        mock_favorites_repo: MagicMock,
        mock_k8s_service: MagicMock,
        regular_user: RequestUser,
        running_instance: Instance,
    ):
        """Test that memory upgrade is rejected if instance has no pod_name (409)."""
        instance_no_pod = replace(running_instance, pod_name=None)
        mock_instance_repo.get_by_id.return_value = instance_no_pod

        service = _make_service(
            mock_instance_repo,
            mock_snapshot_repo,
            mock_config_repo,
            mock_favorites_repo,
            mock_k8s_service,
        )

        with pytest.raises(InvalidStateError) as exc_info:
            await service.update_memory(regular_user, 1, 8)

        assert exc_info.value.status == 409
        mock_k8s_service.resize_pod_memory.assert_not_called()


class TestMemoryIncreaseOnly:
    """Tests for memory increase-only enforcement (CRITICAL).

    Memory can only be increased, not decreased. This is a Kubernetes limitation:
    - Memory increases work with in-place resize
    - Memory decreases require RestartContainer policy (not supported)
    """

    @pytest.mark.asyncio
    async def test_memory_increase_allowed(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_config_repo: MagicMock,
        mock_favorites_repo: MagicMock,
        mock_k8s_service: MagicMock,
        regular_user: RequestUser,
        running_instance: Instance,
    ):
        """Memory increase (4GB -> 8GB) should succeed."""
        # running_instance has memory_gb=4
        mock_instance_repo.get_by_id.return_value = running_instance
        updated_instance = replace(running_instance, memory_gb=8)
        mock_instance_repo.update_memory_gb.return_value = updated_instance

        service = _make_service(
            mock_instance_repo,
            mock_snapshot_repo,
            mock_config_repo,
            mock_favorites_repo,
            mock_k8s_service,
        )

        result = await service.update_memory(regular_user, 1, 8)

        assert result.memory_gb == 8
        mock_k8s_service.resize_pod_memory.assert_called_once()
        mock_instance_repo.update_memory_gb.assert_called_once_with(1, 8)

    @pytest.mark.asyncio
    async def test_memory_decrease_rejected(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_config_repo: MagicMock,
        mock_favorites_repo: MagicMock,
        mock_k8s_service: MagicMock,
        regular_user: RequestUser,
    ):
        """Memory decrease (8GB -> 4GB) should raise InvalidStateError."""
        # Instance with 8GB memory
        instance_8gb = Instance(
            id=1,
            snapshot_id=1,
            owner_username="user1",
            wrapper_type=WrapperType.RYUGRAPH,
            name="Test Instance",
            description=None,
            status=InstanceStatus.RUNNING,
            pod_name="wrapper-abc123",
            url_slug="abc123",
            cpu_cores=2,
            memory_gb=8,
        )
        mock_instance_repo.get_by_id.return_value = instance_8gb

        service = _make_service(
            mock_instance_repo,
            mock_snapshot_repo,
            mock_config_repo,
            mock_favorites_repo,
            mock_k8s_service,
        )

        with pytest.raises(InvalidStateError) as exc_info:
            await service.update_memory(regular_user, 1, 4)  # Decrease 8 -> 4

        assert exc_info.value.status == 409
        assert "decrease" in exc_info.value.message.lower() or "increase" in exc_info.value.message.lower()
        mock_k8s_service.resize_pod_memory.assert_not_called()
        mock_instance_repo.update_memory_gb.assert_not_called()

    @pytest.mark.asyncio
    async def test_same_value_allowed(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_config_repo: MagicMock,
        mock_favorites_repo: MagicMock,
        mock_k8s_service: MagicMock,
        regular_user: RequestUser,
        running_instance: Instance,
    ):
        """Memory update to same value (4GB -> 4GB) should succeed (idempotent)."""
        # running_instance has memory_gb=4
        mock_instance_repo.get_by_id.return_value = running_instance
        mock_instance_repo.update_memory_gb.return_value = running_instance

        service = _make_service(
            mock_instance_repo,
            mock_snapshot_repo,
            mock_config_repo,
            mock_favorites_repo,
            mock_k8s_service,
        )

        result = await service.update_memory(regular_user, 1, 4)  # Same value

        assert result.memory_gb == 4
        # Should still call K8s and repo (idempotent operation)
        mock_k8s_service.resize_pod_memory.assert_called_once()
        mock_instance_repo.update_memory_gb.assert_called_once()

    @pytest.mark.asyncio
    async def test_increase_to_max_allowed(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_config_repo: MagicMock,
        mock_favorites_repo: MagicMock,
        mock_k8s_service: MagicMock,
        regular_user: RequestUser,
        running_instance: Instance,
    ):
        """Memory increase to maximum (4GB -> 32GB) should succeed."""
        # running_instance has memory_gb=4
        mock_instance_repo.get_by_id.return_value = running_instance
        updated_instance = replace(running_instance, memory_gb=32)
        mock_instance_repo.update_memory_gb.return_value = updated_instance

        service = _make_service(
            mock_instance_repo,
            mock_snapshot_repo,
            mock_config_repo,
            mock_favorites_repo,
            mock_k8s_service,
        )

        result = await service.update_memory(regular_user, 1, 32)

        assert result.memory_gb == 32
        mock_k8s_service.resize_pod_memory.assert_called_once()

    @pytest.mark.asyncio
    async def test_instance_without_memory_gb_set(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_config_repo: MagicMock,
        mock_favorites_repo: MagicMock,
        mock_k8s_service: MagicMock,
        regular_user: RequestUser,
    ):
        """Memory upgrade for instance with memory_gb=None should succeed."""
        # Instance without memory_gb set (legacy instance)
        legacy_instance = Instance(
            id=1,
            snapshot_id=1,
            owner_username="user1",
            wrapper_type=WrapperType.RYUGRAPH,
            name="Legacy Instance",
            description=None,
            status=InstanceStatus.RUNNING,
            pod_name="wrapper-abc123",
            url_slug="abc123",
            cpu_cores=2,
            memory_gb=None,  # Not set
        )
        mock_instance_repo.get_by_id.return_value = legacy_instance
        updated_instance = replace(legacy_instance, memory_gb=8)
        mock_instance_repo.update_memory_gb.return_value = updated_instance

        service = _make_service(
            mock_instance_repo,
            mock_snapshot_repo,
            mock_config_repo,
            mock_favorites_repo,
            mock_k8s_service,
        )

        # Should succeed - any value is valid when current is None
        result = await service.update_memory(regular_user, 1, 8)

        assert result.memory_gb == 8
        mock_k8s_service.resize_pod_memory.assert_called_once()


class TestUpdateMemoryK8sIntegration:
    """Tests for K8s service integration in update_memory()."""

    @pytest.mark.asyncio
    async def test_resize_pod_memory_called_correctly(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_config_repo: MagicMock,
        mock_favorites_repo: MagicMock,
        mock_k8s_service: MagicMock,
        regular_user: RequestUser,
        running_instance: Instance,
    ):
        """Test that resize_pod_memory is called with correct params."""
        mock_instance_repo.get_by_id.return_value = running_instance
        updated_instance = replace(running_instance, memory_gb=8)
        mock_instance_repo.update_memory_gb.return_value = updated_instance

        service = _make_service(
            mock_instance_repo,
            mock_snapshot_repo,
            mock_config_repo,
            mock_favorites_repo,
            mock_k8s_service,
        )

        await service.update_memory(regular_user, 1, 8)

        mock_k8s_service.resize_pod_memory.assert_called_once_with(
            pod_name="wrapper-abc123",
            memory_request="8Gi",
            memory_limit="8Gi",  # Guaranteed QoS: request == limit
        )

    @pytest.mark.asyncio
    async def test_memory_request_equals_limit_guaranteed_qos(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_config_repo: MagicMock,
        mock_favorites_repo: MagicMock,
        mock_k8s_service: MagicMock,
        regular_user: RequestUser,
        running_instance: Instance,
    ):
        """Test that memory request equals limit for Guaranteed QoS."""
        mock_instance_repo.get_by_id.return_value = running_instance
        updated_instance = replace(running_instance, memory_gb=16)
        mock_instance_repo.update_memory_gb.return_value = updated_instance

        service = _make_service(
            mock_instance_repo,
            mock_snapshot_repo,
            mock_config_repo,
            mock_favorites_repo,
            mock_k8s_service,
        )

        await service.update_memory(regular_user, 1, 16)

        # Verify request == limit (Guaranteed QoS)
        call_kwargs = mock_k8s_service.resize_pod_memory.call_args[1]
        assert call_kwargs["memory_request"] == "16Gi"
        assert call_kwargs["memory_limit"] == "16Gi"

    @pytest.mark.asyncio
    async def test_update_memory_without_k8s_service(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_config_repo: MagicMock,
        mock_favorites_repo: MagicMock,
        regular_user: RequestUser,
        running_instance: Instance,
    ):
        """Test memory update when K8s service is not available."""
        mock_instance_repo.get_by_id.return_value = running_instance
        mock_instance_repo.update_memory_gb.return_value = replace(
            running_instance, memory_gb=8
        )

        # No K8s service
        service = _make_service(
            mock_instance_repo,
            mock_snapshot_repo,
            mock_config_repo,
            mock_favorites_repo,
            k8s_service=None,
        )

        # Should still update the database even without K8s
        result = await service.update_memory(regular_user, 1, 8)

        assert result.memory_gb == 8
        mock_instance_repo.update_memory_gb.assert_called_once_with(1, 8)

    @pytest.mark.asyncio
    async def test_k8s_error_propagates(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_config_repo: MagicMock,
        mock_favorites_repo: MagicMock,
        mock_k8s_service: MagicMock,
        regular_user: RequestUser,
        running_instance: Instance,
    ):
        """Test behavior when K8s resize fails."""
        from control_plane.services.k8s_service import K8sError

        mock_instance_repo.get_by_id.return_value = running_instance
        mock_k8s_service.resize_pod_memory.side_effect = K8sError("Resize failed")

        service = _make_service(
            mock_instance_repo,
            mock_snapshot_repo,
            mock_config_repo,
            mock_favorites_repo,
            mock_k8s_service,
        )

        # Should propagate the K8sError
        with pytest.raises(K8sError):
            await service.update_memory(regular_user, 1, 8)

        # Database should NOT be updated if K8s fails
        mock_instance_repo.update_memory_gb.assert_not_called()


class TestUpdateMemoryRepositoryIntegration:
    """Tests for repository integration in update_memory()."""

    @pytest.mark.asyncio
    async def test_update_memory_calls_update_memory_gb(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_config_repo: MagicMock,
        mock_favorites_repo: MagicMock,
        mock_k8s_service: MagicMock,
        regular_user: RequestUser,
        running_instance: Instance,
    ):
        """Test that update_memory calls repository.update_memory_gb correctly."""
        mock_instance_repo.get_by_id.return_value = running_instance
        updated = replace(running_instance, memory_gb=16)
        mock_instance_repo.update_memory_gb.return_value = updated

        service = _make_service(
            mock_instance_repo,
            mock_snapshot_repo,
            mock_config_repo,
            mock_favorites_repo,
            mock_k8s_service,
        )

        result = await service.update_memory(regular_user, 1, 16)

        mock_instance_repo.update_memory_gb.assert_called_once_with(1, 16)
        assert result.memory_gb == 16

    @pytest.mark.asyncio
    async def test_update_memory_returns_updated_instance(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_config_repo: MagicMock,
        mock_favorites_repo: MagicMock,
        mock_k8s_service: MagicMock,
        regular_user: RequestUser,
        running_instance: Instance,
    ):
        """Test that update_memory returns the updated instance from repository."""
        mock_instance_repo.get_by_id.return_value = running_instance
        # Simulate repository returning updated instance with new memory_gb
        updated = replace(running_instance, memory_gb=24, name="Modified Instance")
        mock_instance_repo.update_memory_gb.return_value = updated

        service = _make_service(
            mock_instance_repo,
            mock_snapshot_repo,
            mock_config_repo,
            mock_favorites_repo,
            mock_k8s_service,
        )

        result = await service.update_memory(regular_user, 1, 24)

        # Should return the instance from the repository, not a modified copy
        assert result.memory_gb == 24
        assert result.name == "Modified Instance"


class TestUpdateMemoryEdgeCases:
    """Edge case tests for update_memory()."""

    @pytest.mark.asyncio
    async def test_memory_upgrade_falkordb_wrapper(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_config_repo: MagicMock,
        mock_favorites_repo: MagicMock,
        mock_k8s_service: MagicMock,
        regular_user: RequestUser,
    ):
        """Test memory upgrade works for FalkorDB wrapper type."""
        falkordb_instance = Instance(
            id=10,
            snapshot_id=1,
            owner_username="user1",
            wrapper_type=WrapperType.FALKORDB,
            name="FalkorDB Instance",
            description=None,
            status=InstanceStatus.RUNNING,
            pod_name="wrapper-falkor123",
            url_slug="falkor123",
            cpu_cores=2,
            memory_gb=8,
        )
        mock_instance_repo.get_by_id.return_value = falkordb_instance
        mock_instance_repo.update_memory_gb.return_value = replace(
            falkordb_instance, memory_gb=16
        )

        service = _make_service(
            mock_instance_repo,
            mock_snapshot_repo,
            mock_config_repo,
            mock_favorites_repo,
            mock_k8s_service,
        )

        result = await service.update_memory(regular_user, 10, 16)

        assert result.memory_gb == 16
        assert result.wrapper_type == WrapperType.FALKORDB
        mock_k8s_service.resize_pod_memory.assert_called_once_with(
            pod_name="wrapper-falkor123",
            memory_request="16Gi",
            memory_limit="16Gi",
        )

    @pytest.mark.asyncio
    async def test_memory_2gb_minimum(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_config_repo: MagicMock,
        mock_favorites_repo: MagicMock,
        mock_k8s_service: MagicMock,
        regular_user: RequestUser,
    ):
        """Test memory upgrade to 2GB (minimum allowed)."""
        instance_2gb = Instance(
            id=1,
            snapshot_id=1,
            owner_username="user1",
            wrapper_type=WrapperType.RYUGRAPH,
            name="Test Instance",
            description=None,
            status=InstanceStatus.RUNNING,
            pod_name="wrapper-abc123",
            url_slug="abc123",
            cpu_cores=2,
            memory_gb=None,  # No current value
        )
        mock_instance_repo.get_by_id.return_value = instance_2gb
        mock_instance_repo.update_memory_gb.return_value = replace(
            instance_2gb, memory_gb=2
        )

        service = _make_service(
            mock_instance_repo,
            mock_snapshot_repo,
            mock_config_repo,
            mock_favorites_repo,
            mock_k8s_service,
        )

        result = await service.update_memory(regular_user, 1, 2)

        assert result.memory_gb == 2
        mock_k8s_service.resize_pod_memory.assert_called_once_with(
            pod_name="wrapper-abc123",
            memory_request="2Gi",
            memory_limit="2Gi",
        )

    @pytest.mark.asyncio
    async def test_memory_32gb_maximum(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_config_repo: MagicMock,
        mock_favorites_repo: MagicMock,
        mock_k8s_service: MagicMock,
        regular_user: RequestUser,
        running_instance: Instance,
    ):
        """Test memory upgrade to 32GB (maximum allowed)."""
        mock_instance_repo.get_by_id.return_value = running_instance
        mock_instance_repo.update_memory_gb.return_value = replace(
            running_instance, memory_gb=32
        )

        service = _make_service(
            mock_instance_repo,
            mock_snapshot_repo,
            mock_config_repo,
            mock_favorites_repo,
            mock_k8s_service,
        )

        result = await service.update_memory(regular_user, 1, 32)

        assert result.memory_gb == 32
        mock_k8s_service.resize_pod_memory.assert_called_once_with(
            pod_name="wrapper-abc123",
            memory_request="32Gi",
            memory_limit="32Gi",
        )
