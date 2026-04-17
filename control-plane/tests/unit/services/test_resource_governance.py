"""Unit tests for resource governance."""

import pytest
from unittest.mock import AsyncMock

from control_plane.models import ConcurrencyLimitError
from control_plane.services.instance_service import InstanceService


def _make_service(
    user_memory_gb: float = 0.0,
    cluster_memory_gb: float = 0.0,
) -> InstanceService:
    """Create InstanceService with mock dependencies returning specified memory usage."""
    instance_repo = AsyncMock()
    instance_repo.get_total_memory_by_owner = AsyncMock(return_value=user_memory_gb)
    instance_repo.get_total_cluster_memory = AsyncMock(return_value=cluster_memory_gb)

    return InstanceService(
        instance_repo=instance_repo,
        snapshot_repo=AsyncMock(),
        config_repo=AsyncMock(),
        favorites_repo=AsyncMock(),
    )


class TestResourceGovernance:
    """Tests for _check_resource_governance()."""

    @pytest.mark.asyncio
    async def test_passes_within_limits(self):
        """Normal case: all limits satisfied."""
        service = _make_service(user_memory_gb=10.0, cluster_memory_gb=50.0)
        # Should not raise
        await service._check_resource_governance(memory_gi=4, owner_username="alice")

    @pytest.mark.asyncio
    async def test_instance_memory_cap(self):
        """Reject if calculated memory > 32Gi."""
        service = _make_service()
        with pytest.raises(ConcurrencyLimitError) as exc_info:
            await service._check_resource_governance(memory_gi=64, owner_username="alice")
        assert "instance_memory" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_user_memory_cap(self):
        """Reject if user total + new > 64Gi."""
        service = _make_service(user_memory_gb=60.0)
        with pytest.raises(ConcurrencyLimitError) as exc_info:
            await service._check_resource_governance(memory_gi=8, owner_username="alice")
        assert "user_memory" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_cluster_soft_limit(self):
        """Reject if cluster total + new > 256Gi."""
        service = _make_service(cluster_memory_gb=250.0)
        with pytest.raises(ConcurrencyLimitError) as exc_info:
            await service._check_resource_governance(memory_gi=8, owner_username="alice")
        assert "cluster_memory" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_at_exact_limit_passes(self):
        """Exactly at limit should pass (not exceed)."""
        service = _make_service(user_memory_gb=56.0)
        # 56 + 8 = 64 == limit, should pass
        await service._check_resource_governance(memory_gi=8, owner_username="alice")

    @pytest.mark.asyncio
    async def test_just_over_limit_fails(self):
        """Just over limit should fail."""
        service = _make_service(user_memory_gb=57.0)
        # 57 + 8 = 65 > 64 limit
        with pytest.raises(ConcurrencyLimitError):
            await service._check_resource_governance(memory_gi=8, owner_username="alice")
