"""Unit tests for CPU override functionality (Phase 2).

Tests the runtime CPU scaling feature that allows users to adjust CPU allocation
for running instances using Kubernetes in-place pod resize (K8s 1.27+).

Key features tested:
- CPU validation (1-8 cores allowed)
- Permission checks (owner or admin required)
- State validation (instance must be running)
- CPU burst calculation (limit = 2x request)
- K8s integration (resize_pod_cpu called correctly)
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


# Define UpdateCpuRequest inline for testing until it's added to graph_olap_schemas
class UpdateCpuRequest(BaseModel):
    """Request to update CPU allocation for a running instance."""

    cpu_cores: int = Field(
        ...,
        ge=1,
        le=8,
        description="CPU cores (1-8). Sets request=N, limit=2N for burst capacity.",
    )


@pytest.fixture
def mock_instance_repo() -> MagicMock:
    """Create a mock instance repository."""
    repo = MagicMock()
    repo.get_by_id = AsyncMock()
    repo.update_cpu_cores = AsyncMock()
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
    service.resize_pod_cpu = AsyncMock()
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
    """Create a running instance with pod_name."""
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


class TestUpdateCpuRequest:
    """Tests for UpdateCpuRequest validation."""

    def test_cpu_cores_valid_minimum(self):
        """cpu_cores=1 is valid (minimum)."""
        request = UpdateCpuRequest(cpu_cores=1)
        assert request.cpu_cores == 1

    def test_cpu_cores_valid_maximum(self):
        """cpu_cores=8 is valid (maximum)."""
        request = UpdateCpuRequest(cpu_cores=8)
        assert request.cpu_cores == 8

    def test_cpu_cores_valid_mid_range(self):
        """cpu_cores=4 is valid (middle of range)."""
        request = UpdateCpuRequest(cpu_cores=4)
        assert request.cpu_cores == 4

    def test_cpu_cores_below_minimum_rejected(self):
        """cpu_cores=0 is rejected (below minimum)."""
        with pytest.raises(ValidationError) as exc_info:
            UpdateCpuRequest(cpu_cores=0)
        assert "cpu_cores" in str(exc_info.value)

    def test_cpu_cores_negative_rejected(self):
        """cpu_cores=-1 is rejected (negative)."""
        with pytest.raises(ValidationError) as exc_info:
            UpdateCpuRequest(cpu_cores=-1)
        assert "cpu_cores" in str(exc_info.value)

    def test_cpu_cores_above_maximum_rejected(self):
        """cpu_cores=9 is rejected (above maximum)."""
        with pytest.raises(ValidationError) as exc_info:
            UpdateCpuRequest(cpu_cores=9)
        assert "cpu_cores" in str(exc_info.value)

    def test_cpu_cores_way_above_maximum_rejected(self):
        """cpu_cores=16 is rejected (way above maximum)."""
        with pytest.raises(ValidationError) as exc_info:
            UpdateCpuRequest(cpu_cores=16)
        assert "cpu_cores" in str(exc_info.value)

    def test_cpu_cores_required(self):
        """cpu_cores is required."""
        with pytest.raises(ValidationError) as exc_info:
            UpdateCpuRequest()  # type: ignore[call-arg]
        assert "cpu_cores" in str(exc_info.value)


class TestUpdateCpu:
    """Tests for InstanceService.update_cpu() method."""

    @pytest.mark.asyncio
    async def test_update_cpu_success(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_config_repo: MagicMock,
        mock_favorites_repo: MagicMock,
        mock_k8s_service: MagicMock,
        regular_user: RequestUser,
        running_instance: Instance,
    ):
        """Test successful CPU update for owner."""
        mock_instance_repo.get_by_id.return_value = running_instance
        updated_instance = replace(running_instance, cpu_cores=4)
        mock_instance_repo.update_cpu_cores.return_value = updated_instance

        service = _make_service(
            mock_instance_repo,
            mock_snapshot_repo,
            mock_config_repo,
            mock_favorites_repo,
            mock_k8s_service,
        )

        result = await service.update_cpu(regular_user, 1, 4)

        assert result.cpu_cores == 4
        mock_k8s_service.resize_pod_cpu.assert_called_once_with(
            pod_name="wrapper-abc123",
            cpu_request="4",
            cpu_limit="8",
        )
        mock_instance_repo.update_cpu_cores.assert_called_once_with(1, 4)

    @pytest.mark.asyncio
    async def test_update_cpu_admin_can_modify_others(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_config_repo: MagicMock,
        mock_favorites_repo: MagicMock,
        mock_k8s_service: MagicMock,
        admin_user: RequestUser,
        running_instance: Instance,
    ):
        """Test that admin can update CPU for other users' instances."""
        mock_instance_repo.get_by_id.return_value = running_instance
        updated_instance = replace(running_instance, cpu_cores=4)
        mock_instance_repo.update_cpu_cores.return_value = updated_instance

        service = _make_service(
            mock_instance_repo,
            mock_snapshot_repo,
            mock_config_repo,
            mock_favorites_repo,
            mock_k8s_service,
        )

        result = await service.update_cpu(admin_user, 1, 4)

        assert result.cpu_cores == 4
        mock_k8s_service.resize_pod_cpu.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_cpu_ops_can_modify_others(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_config_repo: MagicMock,
        mock_favorites_repo: MagicMock,
        mock_k8s_service: MagicMock,
        ops_user: RequestUser,
        running_instance: Instance,
    ):
        """Test that ops user can update CPU for other users' instances."""
        mock_instance_repo.get_by_id.return_value = running_instance
        updated_instance = replace(running_instance, cpu_cores=6)
        mock_instance_repo.update_cpu_cores.return_value = updated_instance

        service = _make_service(
            mock_instance_repo,
            mock_snapshot_repo,
            mock_config_repo,
            mock_favorites_repo,
            mock_k8s_service,
        )

        result = await service.update_cpu(ops_user, 1, 6)

        assert result.cpu_cores == 6
        mock_k8s_service.resize_pod_cpu.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_cpu_non_owner_rejected(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_config_repo: MagicMock,
        mock_favorites_repo: MagicMock,
        mock_k8s_service: MagicMock,
        other_user: RequestUser,
        running_instance: Instance,
    ):
        """Test that non-owner analyst cannot update CPU."""
        mock_instance_repo.get_by_id.return_value = running_instance

        service = _make_service(
            mock_instance_repo,
            mock_snapshot_repo,
            mock_config_repo,
            mock_favorites_repo,
            mock_k8s_service,
        )

        with pytest.raises(PermissionDeniedError) as exc_info:
            await service.update_cpu(other_user, 1, 4)

        assert exc_info.value.status == 403
        assert "Instance" in exc_info.value.message
        mock_k8s_service.resize_pod_cpu.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_cpu_instance_not_found(
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
            await service.update_cpu(regular_user, 999, 4)

        assert exc_info.value.status == 404
        assert "Instance" in exc_info.value.message


class TestUpdateCpuStateValidation:
    """Tests for state validation in update_cpu()."""

    @pytest.mark.asyncio
    async def test_update_cpu_failed_instance_rejected(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_config_repo: MagicMock,
        mock_favorites_repo: MagicMock,
        mock_k8s_service: MagicMock,
        regular_user: RequestUser,
        stopped_instance: Instance,
    ):
        """Test that CPU update is rejected for failed instances."""
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
            await service.update_cpu(regular_user, 3, 4)

        assert exc_info.value.status == 409
        assert "failed" in exc_info.value.message.lower()
        assert "running" in exc_info.value.message.lower()
        mock_k8s_service.resize_pod_cpu.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_cpu_starting_instance_rejected(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_config_repo: MagicMock,
        mock_favorites_repo: MagicMock,
        mock_k8s_service: MagicMock,
        regular_user: RequestUser,
        starting_instance: Instance,
    ):
        """Test that CPU update is rejected for starting instances."""
        mock_instance_repo.get_by_id.return_value = starting_instance

        service = _make_service(
            mock_instance_repo,
            mock_snapshot_repo,
            mock_config_repo,
            mock_favorites_repo,
            mock_k8s_service,
        )

        with pytest.raises(InvalidStateError) as exc_info:
            await service.update_cpu(regular_user, 2, 4)

        assert exc_info.value.status == 409
        mock_k8s_service.resize_pod_cpu.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_cpu_waiting_instance_rejected(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_config_repo: MagicMock,
        mock_favorites_repo: MagicMock,
        mock_k8s_service: MagicMock,
        regular_user: RequestUser,
        waiting_instance: Instance,
    ):
        """Test that CPU update is rejected for waiting instances."""
        mock_instance_repo.get_by_id.return_value = waiting_instance

        service = _make_service(
            mock_instance_repo,
            mock_snapshot_repo,
            mock_config_repo,
            mock_favorites_repo,
            mock_k8s_service,
        )

        with pytest.raises(InvalidStateError) as exc_info:
            await service.update_cpu(regular_user, 4, 4)

        assert exc_info.value.status == 409
        mock_k8s_service.resize_pod_cpu.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_cpu_no_pod_name_rejected(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_config_repo: MagicMock,
        mock_favorites_repo: MagicMock,
        mock_k8s_service: MagicMock,
        regular_user: RequestUser,
        running_instance: Instance,
    ):
        """Test that CPU update is rejected if instance has no pod_name."""
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
            await service.update_cpu(regular_user, 1, 4)

        assert exc_info.value.status == 409
        mock_k8s_service.resize_pod_cpu.assert_not_called()


class TestCpuBurstCalculation:
    """Tests for CPU burst limit calculation (limit = 2x request)."""

    @pytest.mark.asyncio
    async def test_cpu_1_core_burst_2(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_config_repo: MagicMock,
        mock_favorites_repo: MagicMock,
        mock_k8s_service: MagicMock,
        regular_user: RequestUser,
        running_instance: Instance,
    ):
        """cpu_cores=1 -> request=1, limit=2."""
        mock_instance_repo.get_by_id.return_value = running_instance
        mock_instance_repo.update_cpu_cores.return_value = replace(
            running_instance, cpu_cores=1
        )

        service = _make_service(
            mock_instance_repo,
            mock_snapshot_repo,
            mock_config_repo,
            mock_favorites_repo,
            mock_k8s_service,
        )

        await service.update_cpu(regular_user, 1, 1)

        mock_k8s_service.resize_pod_cpu.assert_called_once_with(
            pod_name="wrapper-abc123",
            cpu_request="1",
            cpu_limit="2",
        )

    @pytest.mark.asyncio
    async def test_cpu_2_cores_burst_4(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_config_repo: MagicMock,
        mock_favorites_repo: MagicMock,
        mock_k8s_service: MagicMock,
        regular_user: RequestUser,
        running_instance: Instance,
    ):
        """cpu_cores=2 -> request=2, limit=4."""
        mock_instance_repo.get_by_id.return_value = running_instance
        mock_instance_repo.update_cpu_cores.return_value = replace(
            running_instance, cpu_cores=2
        )

        service = _make_service(
            mock_instance_repo,
            mock_snapshot_repo,
            mock_config_repo,
            mock_favorites_repo,
            mock_k8s_service,
        )

        await service.update_cpu(regular_user, 1, 2)

        mock_k8s_service.resize_pod_cpu.assert_called_once_with(
            pod_name="wrapper-abc123",
            cpu_request="2",
            cpu_limit="4",
        )

    @pytest.mark.asyncio
    async def test_cpu_4_cores_burst_8(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_config_repo: MagicMock,
        mock_favorites_repo: MagicMock,
        mock_k8s_service: MagicMock,
        regular_user: RequestUser,
        running_instance: Instance,
    ):
        """cpu_cores=4 -> request=4, limit=8."""
        mock_instance_repo.get_by_id.return_value = running_instance
        mock_instance_repo.update_cpu_cores.return_value = replace(
            running_instance, cpu_cores=4
        )

        service = _make_service(
            mock_instance_repo,
            mock_snapshot_repo,
            mock_config_repo,
            mock_favorites_repo,
            mock_k8s_service,
        )

        await service.update_cpu(regular_user, 1, 4)

        mock_k8s_service.resize_pod_cpu.assert_called_once_with(
            pod_name="wrapper-abc123",
            cpu_request="4",
            cpu_limit="8",
        )

    @pytest.mark.asyncio
    async def test_cpu_8_cores_burst_16(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_config_repo: MagicMock,
        mock_favorites_repo: MagicMock,
        mock_k8s_service: MagicMock,
        regular_user: RequestUser,
        running_instance: Instance,
    ):
        """cpu_cores=8 -> request=8, limit=16."""
        mock_instance_repo.get_by_id.return_value = running_instance
        mock_instance_repo.update_cpu_cores.return_value = replace(
            running_instance, cpu_cores=8
        )

        service = _make_service(
            mock_instance_repo,
            mock_snapshot_repo,
            mock_config_repo,
            mock_favorites_repo,
            mock_k8s_service,
        )

        await service.update_cpu(regular_user, 1, 8)

        mock_k8s_service.resize_pod_cpu.assert_called_once_with(
            pod_name="wrapper-abc123",
            cpu_request="8",
            cpu_limit="16",
        )


class TestUpdateCpuK8sIntegration:
    """Tests for K8s service integration in update_cpu()."""

    @pytest.mark.asyncio
    async def test_update_cpu_without_k8s_service(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_config_repo: MagicMock,
        mock_favorites_repo: MagicMock,
        regular_user: RequestUser,
        running_instance: Instance,
    ):
        """Test CPU update when K8s service is not available."""
        mock_instance_repo.get_by_id.return_value = running_instance
        mock_instance_repo.update_cpu_cores.return_value = replace(
            running_instance, cpu_cores=4
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
        result = await service.update_cpu(regular_user, 1, 4)

        assert result.cpu_cores == 4
        mock_instance_repo.update_cpu_cores.assert_called_once_with(1, 4)

    @pytest.mark.asyncio
    async def test_update_cpu_k8s_resize_failure(
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
        mock_k8s_service.resize_pod_cpu.side_effect = K8sError("Resize failed")

        service = _make_service(
            mock_instance_repo,
            mock_snapshot_repo,
            mock_config_repo,
            mock_favorites_repo,
            mock_k8s_service,
        )

        # Should propagate the K8sError
        with pytest.raises(K8sError):
            await service.update_cpu(regular_user, 1, 4)

        # Database should NOT be updated if K8s fails
        mock_instance_repo.update_cpu_cores.assert_not_called()


class TestUpdateCpuRepositoryIntegration:
    """Tests for repository integration in update_cpu()."""

    @pytest.mark.asyncio
    async def test_update_cpu_calls_update_cpu_cores(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_config_repo: MagicMock,
        mock_favorites_repo: MagicMock,
        mock_k8s_service: MagicMock,
        regular_user: RequestUser,
        running_instance: Instance,
    ):
        """Test that update_cpu calls repository.update_cpu_cores correctly."""
        mock_instance_repo.get_by_id.return_value = running_instance
        updated = replace(running_instance, cpu_cores=6)
        mock_instance_repo.update_cpu_cores.return_value = updated

        service = _make_service(
            mock_instance_repo,
            mock_snapshot_repo,
            mock_config_repo,
            mock_favorites_repo,
            mock_k8s_service,
        )

        result = await service.update_cpu(regular_user, 1, 6)

        mock_instance_repo.update_cpu_cores.assert_called_once_with(1, 6)
        assert result.cpu_cores == 6

    @pytest.mark.asyncio
    async def test_update_cpu_returns_updated_instance(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_config_repo: MagicMock,
        mock_favorites_repo: MagicMock,
        mock_k8s_service: MagicMock,
        regular_user: RequestUser,
        running_instance: Instance,
    ):
        """Test that update_cpu returns the updated instance from repository."""
        mock_instance_repo.get_by_id.return_value = running_instance
        # Simulate repository returning updated instance with new cpu_cores
        updated = replace(running_instance, cpu_cores=3, name="Modified Instance")
        mock_instance_repo.update_cpu_cores.return_value = updated

        service = _make_service(
            mock_instance_repo,
            mock_snapshot_repo,
            mock_config_repo,
            mock_favorites_repo,
            mock_k8s_service,
        )

        result = await service.update_cpu(regular_user, 1, 3)

        # Should return the instance from the repository, not a modified copy
        assert result.cpu_cores == 3
        assert result.name == "Modified Instance"


class TestUpdateCpuEdgeCases:
    """Edge case tests for update_cpu()."""

    @pytest.mark.asyncio
    async def test_update_cpu_same_value(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_config_repo: MagicMock,
        mock_favorites_repo: MagicMock,
        mock_k8s_service: MagicMock,
        regular_user: RequestUser,
        running_instance: Instance,
    ):
        """Test updating CPU to the same value (should still work)."""
        mock_instance_repo.get_by_id.return_value = running_instance
        mock_instance_repo.update_cpu_cores.return_value = running_instance

        service = _make_service(
            mock_instance_repo,
            mock_snapshot_repo,
            mock_config_repo,
            mock_favorites_repo,
            mock_k8s_service,
        )

        # Update to same value (2 cores)
        result = await service.update_cpu(regular_user, 1, 2)

        assert result.cpu_cores == 2
        # Should still call K8s and repo (idempotent operation)
        mock_k8s_service.resize_pod_cpu.assert_called_once()
        mock_instance_repo.update_cpu_cores.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_cpu_falkordb_wrapper(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_config_repo: MagicMock,
        mock_favorites_repo: MagicMock,
        mock_k8s_service: MagicMock,
        regular_user: RequestUser,
    ):
        """Test CPU update works for FalkorDB wrapper type."""
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
        )
        mock_instance_repo.get_by_id.return_value = falkordb_instance
        mock_instance_repo.update_cpu_cores.return_value = replace(
            falkordb_instance, cpu_cores=4
        )

        service = _make_service(
            mock_instance_repo,
            mock_snapshot_repo,
            mock_config_repo,
            mock_favorites_repo,
            mock_k8s_service,
        )

        result = await service.update_cpu(regular_user, 10, 4)

        assert result.cpu_cores == 4
        assert result.wrapper_type == WrapperType.FALKORDB
        mock_k8s_service.resize_pod_cpu.assert_called_once_with(
            pod_name="wrapper-falkor123",
            cpu_request="4",
            cpu_limit="8",
        )
