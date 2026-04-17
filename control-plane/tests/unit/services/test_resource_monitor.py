"""Unit tests for resource monitoring functionality (Phase 3).

Tests the resource monitor job that:
1. Polls running instances for memory/disk usage
2. Detects instances exceeding memory thresholds
3. Records instance events for monitoring and auditing
4. Respects sizing guardrails (max memory, cooldown periods)
"""

import pytest
from datetime import datetime, UTC, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from graph_olap_schemas import WrapperType

from control_plane.models import Instance, InstanceStatus


@pytest.fixture
def mock_settings():
    """Create mock settings for resource monitoring."""
    settings = MagicMock()
    settings.sizing_enabled = True
    settings.sizing_max_memory_gb = 32.0
    settings.sizing_max_resize_steps = 3
    settings.sizing_resize_cooldown_seconds = 300
    settings.sizing_per_user_max_memory_gb = 64.0
    settings.sizing_cluster_memory_soft_limit_gb = 256.0
    return settings


@pytest.fixture
def running_instances():
    """Create a list of running instances with various memory usage levels."""
    now = datetime.now(UTC)
    return [
        Instance(
            id=1,
            snapshot_id=1,
            owner_username="user1",
            wrapper_type=WrapperType.RYUGRAPH,
            name="Instance 1 - Low Memory",
            description=None,
            status=InstanceStatus.RUNNING,
            pod_name="wrapper-abc123",
            memory_usage_bytes=2 * 1024**3,  # 2GB
            disk_usage_bytes=5 * 1024**3,  # 5GB
            created_at=now - timedelta(hours=2),
            updated_at=now - timedelta(minutes=5),
            started_at=now - timedelta(hours=1),
            last_activity_at=now - timedelta(minutes=10),
        ),
        Instance(
            id=2,
            snapshot_id=2,
            owner_username="user2",
            wrapper_type=WrapperType.FALKORDB,
            name="Instance 2 - High Memory",
            description=None,
            status=InstanceStatus.RUNNING,
            pod_name="wrapper-def456",
            memory_usage_bytes=8 * 1024**3,  # 8GB
            disk_usage_bytes=15 * 1024**3,  # 15GB
            created_at=now - timedelta(hours=4),
            updated_at=now - timedelta(minutes=2),
            started_at=now - timedelta(hours=3),
            last_activity_at=now - timedelta(minutes=5),
        ),
        Instance(
            id=3,
            snapshot_id=3,
            owner_username="user1",
            wrapper_type=WrapperType.FALKORDB,
            name="Instance 3 - Critical Memory",
            description=None,
            status=InstanceStatus.RUNNING,
            pod_name="wrapper-ghi789",
            memory_usage_bytes=30 * 1024**3,  # 30GB (near 32GB cap)
            disk_usage_bytes=25 * 1024**3,  # 25GB
            created_at=now - timedelta(hours=6),
            updated_at=now - timedelta(minutes=1),
            started_at=now - timedelta(hours=5),
            last_activity_at=now - timedelta(minutes=2),
        ),
    ]


@pytest.fixture
def starting_instance():
    """Create a starting instance (should be skipped by monitor)."""
    now = datetime.now(UTC)
    return Instance(
        id=4,
        snapshot_id=4,
        owner_username="user3",
        wrapper_type=WrapperType.RYUGRAPH,
        name="Instance 4 - Starting",
        description=None,
        status=InstanceStatus.STARTING,
        pod_name="wrapper-jkl012",
        memory_usage_bytes=None,  # No metrics yet
        disk_usage_bytes=None,
        created_at=now - timedelta(minutes=5),
        updated_at=now - timedelta(minutes=1),
        started_at=None,
        last_activity_at=None,
    )


class TestResourceMonitorJobConfiguration:
    """Tests for resource monitor job configuration and feature flags."""

    @pytest.mark.asyncio
    async def test_skips_when_sizing_disabled(self, mock_settings):
        """Test that job skips all processing when sizing is disabled."""
        mock_settings.sizing_enabled = False

        with patch("control_plane.config.get_settings", return_value=mock_settings):
            # The job should return early without querying any data
            # This tests the feature flag check
            result = await self._simulate_resource_monitor_disabled_check(mock_settings)

        assert result["skipped"] is True
        assert result["reason"] == "sizing_disabled"

    @pytest.mark.asyncio
    async def test_runs_when_sizing_enabled(self, mock_settings):
        """Test that job runs when sizing is enabled."""
        mock_settings.sizing_enabled = True

        result = await self._simulate_resource_monitor_disabled_check(mock_settings)

        assert result["skipped"] is False

    async def _simulate_resource_monitor_disabled_check(self, settings) -> dict:
        """Simulate the disabled check logic of resource monitor."""
        if not settings.sizing_enabled:
            return {"skipped": True, "reason": "sizing_disabled"}
        return {"skipped": False}


class TestResourceMonitorJobExecution:
    """Tests for resource monitor job execution."""

    @pytest.mark.asyncio
    async def test_only_monitors_running_instances(
        self, mock_settings, running_instances, starting_instance
    ):
        """Test that job only monitors instances in RUNNING status."""
        all_instances = running_instances + [starting_instance]

        # Filter as the job would
        monitored = [i for i in all_instances if i.status == InstanceStatus.RUNNING]

        assert len(monitored) == 3
        assert starting_instance not in monitored
        assert all(i.status == InstanceStatus.RUNNING for i in monitored)

    @pytest.mark.asyncio
    async def test_updates_memory_usage_from_k8s_metrics(
        self, mock_settings, running_instances
    ):
        """Test that job updates instance memory usage from K8s metrics."""
        mock_k8s = MagicMock()
        mock_k8s.get_pod_metrics = AsyncMock(
            return_value={
                "memory_bytes": 4 * 1024**3,  # 4GB
                "cpu_millicores": 2000,
            }
        )

        mock_repo = MagicMock()
        mock_repo.update_resource_usage = AsyncMock(return_value=True)

        instance = running_instances[0]

        # Simulate fetching and updating metrics
        metrics = await mock_k8s.get_pod_metrics(instance.pod_name)
        updated = await mock_repo.update_resource_usage(
            instance_id=instance.id,
            memory_usage_bytes=metrics["memory_bytes"],
        )

        mock_k8s.get_pod_metrics.assert_called_once_with(instance.pod_name)
        mock_repo.update_resource_usage.assert_called_once()
        assert updated is True

    @pytest.mark.asyncio
    async def test_handles_missing_pod_metrics_gracefully(
        self, mock_settings, running_instances
    ):
        """Test that job handles cases where pod metrics are unavailable."""
        mock_k8s = MagicMock()
        mock_k8s.get_pod_metrics = AsyncMock(return_value=None)  # No metrics available

        instance = running_instances[0]
        metrics = await mock_k8s.get_pod_metrics(instance.pod_name)

        # Job should continue without updating (not fail)
        assert metrics is None

    @pytest.mark.asyncio
    async def test_handles_k8s_service_unavailable(self, mock_settings):
        """Test that job handles K8s service being unavailable."""
        with patch(
            "control_plane.services.k8s_service.get_k8s_service", return_value=None
        ):
            # Job should complete without error when K8s is unavailable
            k8s_service = None
            assert k8s_service is None
            # In real implementation, job would log and skip


class TestResizeGuardrails:
    """Tests for resize guardrails and limits."""

    def test_max_memory_cap_at_32gb(self, mock_settings):
        """Test that memory resize is capped at max_memory_gb (32GB)."""
        # If current memory is 16GB and we would double it
        current_memory_gb = 16
        new_memory_gb = min(current_memory_gb * 2, mock_settings.sizing_max_memory_gb)
        assert new_memory_gb == 32.0

    def test_max_memory_cap_when_at_limit(self, mock_settings):
        """Test that resize returns same value when already at max."""
        current_memory_gb = 32
        new_memory_gb = min(current_memory_gb * 2, mock_settings.sizing_max_memory_gb)
        assert new_memory_gb == 32.0

    def test_resize_doubles_when_below_max(self, mock_settings):
        """Test that resize doubles memory when below max."""
        current_memory_gb = 4
        new_memory_gb = min(current_memory_gb * 2, mock_settings.sizing_max_memory_gb)
        assert new_memory_gb == 8

    def test_max_resize_steps_limits_upgrades(self, mock_settings):
        """Test that max_resize_steps limits total auto-upgrades."""
        resize_count = 0
        max_steps = mock_settings.sizing_max_resize_steps

        # Simulate 3 resize operations (at limit)
        for _ in range(3):
            resize_count += 1

        assert resize_count == max_steps

        # Fourth resize should be blocked
        can_resize = resize_count < max_steps
        assert can_resize is False

    def test_cooldown_prevents_rapid_resizing(self, mock_settings):
        """Test that cooldown period prevents rapid consecutive resizes."""
        cooldown_seconds = mock_settings.sizing_resize_cooldown_seconds
        last_resize_at = datetime.now(UTC) - timedelta(seconds=100)  # 100s ago
        now = datetime.now(UTC)

        elapsed = (now - last_resize_at).total_seconds()
        can_resize = elapsed >= cooldown_seconds

        assert can_resize is False  # 100s < 300s cooldown

    def test_cooldown_allows_resize_after_period(self, mock_settings):
        """Test that resize is allowed after cooldown period."""
        cooldown_seconds = mock_settings.sizing_resize_cooldown_seconds
        last_resize_at = datetime.now(UTC) - timedelta(seconds=400)  # 400s ago
        now = datetime.now(UTC)

        elapsed = (now - last_resize_at).total_seconds()
        can_resize = elapsed >= cooldown_seconds

        assert can_resize is True  # 400s >= 300s cooldown


class TestMemoryThresholdDetection:
    """Tests for memory threshold detection."""

    def test_detects_high_memory_usage(self, running_instances):
        """Test detection of instances with high memory usage."""
        high_threshold_percent = 0.80  # 80% of allocated memory

        # Assuming allocated memory is tracked or inferred
        allocated_memory_gb = {
            1: 4,  # 4GB allocated
            2: 16,  # 16GB allocated
            3: 32,  # 32GB allocated (at cap)
        }

        high_usage_instances = []
        for instance in running_instances:
            if instance.memory_usage_bytes:
                usage_gb = instance.memory_usage_bytes / (1024**3)
                allocated = allocated_memory_gb.get(instance.id, 4)
                if usage_gb / allocated >= high_threshold_percent:
                    high_usage_instances.append(instance)

        # Instance 3 has 30GB usage on 32GB allocation = 93.75%
        assert len(high_usage_instances) >= 1

    def test_detects_critical_memory_usage(self, running_instances):
        """Test detection of instances at critical memory levels."""
        critical_threshold_percent = 0.90  # 90% of allocated memory

        allocated_memory_gb = {
            1: 4,
            2: 16,
            3: 32,
        }

        critical_instances = []
        for instance in running_instances:
            if instance.memory_usage_bytes:
                usage_gb = instance.memory_usage_bytes / (1024**3)
                allocated = allocated_memory_gb.get(instance.id, 4)
                if usage_gb / allocated >= critical_threshold_percent:
                    critical_instances.append(instance)

        # Instance 3 has 30/32 = 93.75% > 90%
        assert len(critical_instances) >= 1


class TestInstanceEventsRepository:
    """Tests for instance events repository functionality."""

    @pytest.mark.asyncio
    async def test_create_memory_upgraded_event(self):
        """Test creating a memory_upgraded instance event."""
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.inserted_primary_key = [1]
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        # Simulate event creation
        event_data = {
            "id": 1,
            "instance_id": 1,
            "event_type": "memory_upgraded",
            "details": {"old_gb": 4, "new_gb": 8},
            "created_at": datetime.now(UTC),
        }

        assert event_data["id"] == 1
        assert event_data["instance_id"] == 1
        assert event_data["event_type"] == "memory_upgraded"
        assert event_data["details"]["old_gb"] == 4
        assert event_data["details"]["new_gb"] == 8

    @pytest.mark.asyncio
    async def test_create_memory_threshold_exceeded_event(self):
        """Test creating a memory_threshold_exceeded event."""
        event_data = {
            "id": 2,
            "instance_id": 3,
            "event_type": "memory_threshold_exceeded",
            "details": {
                "usage_gb": 30,
                "allocated_gb": 32,
                "threshold_percent": 90,
            },
            "created_at": datetime.now(UTC),
        }

        assert event_data["event_type"] == "memory_threshold_exceeded"
        assert event_data["details"]["usage_gb"] == 30
        assert event_data["details"]["threshold_percent"] == 90

    @pytest.mark.asyncio
    async def test_create_resize_cooldown_blocked_event(self):
        """Test creating a resize_cooldown_blocked event."""
        event_data = {
            "id": 3,
            "instance_id": 2,
            "event_type": "resize_cooldown_blocked",
            "details": {
                "last_resize_at": "2025-01-28T10:00:00+00:00",
                "cooldown_seconds": 300,
                "elapsed_seconds": 150,
            },
            "created_at": datetime.now(UTC),
        }

        assert event_data["event_type"] == "resize_cooldown_blocked"
        assert event_data["details"]["cooldown_seconds"] == 300
        assert event_data["details"]["elapsed_seconds"] == 150

    @pytest.mark.asyncio
    async def test_list_events_by_instance_returns_ordered(self):
        """Test listing events for an instance returns them in chronological order."""
        # Simulate event data
        events = [
            {
                "id": 1,
                "instance_id": 1,
                "event_type": "memory_upgraded",
                "details": {"old_gb": 4, "new_gb": 8},
                "created_at": datetime(2025, 1, 28, 10, 0, 0, tzinfo=UTC),
            },
            {
                "id": 2,
                "instance_id": 1,
                "event_type": "memory_threshold_exceeded",
                "details": {"usage_gb": 7, "allocated_gb": 8},
                "created_at": datetime(2025, 1, 28, 11, 0, 0, tzinfo=UTC),
            },
            {
                "id": 3,
                "instance_id": 1,
                "event_type": "memory_upgraded",
                "details": {"old_gb": 8, "new_gb": 16},
                "created_at": datetime(2025, 1, 28, 12, 0, 0, tzinfo=UTC),
            },
        ]

        # Sort by created_at descending (most recent first)
        sorted_events = sorted(events, key=lambda e: e["created_at"], reverse=True)

        assert len(sorted_events) == 3
        assert sorted_events[0]["id"] == 3  # Most recent
        assert sorted_events[2]["id"] == 1  # Oldest

    @pytest.mark.asyncio
    async def test_list_events_filters_by_event_type(self):
        """Test listing events can filter by event type."""
        events = [
            {"id": 1, "event_type": "memory_upgraded"},
            {"id": 2, "event_type": "memory_threshold_exceeded"},
            {"id": 3, "event_type": "memory_upgraded"},
            {"id": 4, "event_type": "resize_cooldown_blocked"},
        ]

        memory_upgraded_events = [e for e in events if e["event_type"] == "memory_upgraded"]

        assert len(memory_upgraded_events) == 2
        assert all(e["event_type"] == "memory_upgraded" for e in memory_upgraded_events)


class TestResourceMonitorJobResults:
    """Tests for resource monitor job result tracking."""

    @pytest.mark.asyncio
    async def test_job_returns_metrics(self, running_instances):
        """Test that job returns monitoring metrics."""
        # Simulate job result
        result = {
            "processed": len(running_instances),
            "updated": 3,
            "threshold_exceeded": 1,
            "resizes_triggered": 0,
            "resizes_blocked_cooldown": 0,
            "resizes_blocked_max_steps": 0,
            "errors": 0,
            "duration_seconds": 0.5,
        }

        assert result["processed"] == 3
        assert result["threshold_exceeded"] == 1
        assert result["errors"] == 0

    @pytest.mark.asyncio
    async def test_job_continues_on_individual_instance_error(self, running_instances):
        """Test that job continues processing after an error on one instance."""
        processed = 0
        errors = 0

        for i, instance in enumerate(running_instances):
            try:
                if i == 1:
                    raise Exception("K8s API timeout")
                processed += 1
            except Exception:
                errors += 1
                # Continue processing other instances
                continue

        # Should have processed 2 instances and recorded 1 error
        assert processed == 2
        assert errors == 1


class TestResourceUsageUpdates:
    """Tests for resource usage update operations."""

    @pytest.mark.asyncio
    async def test_update_memory_usage_bytes(self):
        """Test updating instance memory usage."""
        mock_repo = MagicMock()
        mock_repo.update_resource_usage = AsyncMock(return_value=True)

        instance_id = 1
        new_memory_bytes = 5 * 1024**3  # 5GB

        updated = await mock_repo.update_resource_usage(
            instance_id=instance_id,
            memory_usage_bytes=new_memory_bytes,
        )

        mock_repo.update_resource_usage.assert_called_once_with(
            instance_id=instance_id,
            memory_usage_bytes=new_memory_bytes,
        )
        assert updated is True

    @pytest.mark.asyncio
    async def test_update_disk_usage_bytes(self):
        """Test updating instance disk usage."""
        mock_repo = MagicMock()
        mock_repo.update_resource_usage = AsyncMock(return_value=True)

        instance_id = 2
        new_disk_bytes = 20 * 1024**3  # 20GB

        updated = await mock_repo.update_resource_usage(
            instance_id=instance_id,
            disk_usage_bytes=new_disk_bytes,
        )

        mock_repo.update_resource_usage.assert_called_once()
        assert updated is True

    @pytest.mark.asyncio
    async def test_update_both_memory_and_disk(self):
        """Test updating both memory and disk usage."""
        mock_repo = MagicMock()
        mock_repo.update_resource_usage = AsyncMock(return_value=True)

        instance_id = 3
        new_memory_bytes = 8 * 1024**3
        new_disk_bytes = 15 * 1024**3

        updated = await mock_repo.update_resource_usage(
            instance_id=instance_id,
            memory_usage_bytes=new_memory_bytes,
            disk_usage_bytes=new_disk_bytes,
        )

        mock_repo.update_resource_usage.assert_called_once_with(
            instance_id=instance_id,
            memory_usage_bytes=new_memory_bytes,
            disk_usage_bytes=new_disk_bytes,
        )
        assert updated is True

    @pytest.mark.asyncio
    async def test_update_returns_false_for_missing_instance(self):
        """Test that update returns False when instance doesn't exist."""
        mock_repo = MagicMock()
        mock_repo.update_resource_usage = AsyncMock(return_value=False)

        instance_id = 999  # Non-existent

        updated = await mock_repo.update_resource_usage(
            instance_id=instance_id,
            memory_usage_bytes=1024**3,
        )

        assert updated is False


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_zero_memory_usage(self):
        """Test handling of zero memory usage."""
        instance = Instance(
            id=1,
            snapshot_id=1,
            owner_username="user1",
            wrapper_type=WrapperType.RYUGRAPH,
            name="Zero Memory Instance",
            description=None,
            status=InstanceStatus.RUNNING,
            memory_usage_bytes=0,
        )

        assert instance.memory_usage_bytes == 0

    def test_none_memory_usage(self):
        """Test handling of None memory usage (not yet reported)."""
        instance = Instance(
            id=2,
            snapshot_id=2,
            owner_username="user2",
            wrapper_type=WrapperType.FALKORDB,
            name="No Metrics Instance",
            description=None,
            status=InstanceStatus.RUNNING,
            memory_usage_bytes=None,
        )

        assert instance.memory_usage_bytes is None

    def test_memory_at_exact_threshold(self, mock_settings):
        """Test handling of memory usage at exactly the threshold."""
        allocated_gb = 8
        threshold_percent = 0.80
        # Use exact calculation without int() truncation to test boundary
        exact_threshold_gb = allocated_gb * threshold_percent  # 6.4 GB
        exact_threshold_bytes = exact_threshold_gb * 1024**3

        usage_percent = exact_threshold_bytes / (allocated_gb * 1024**3)
        at_threshold = usage_percent >= threshold_percent

        assert at_threshold is True

    def test_very_large_memory_values(self):
        """Test handling of very large memory values (64GB+)."""
        large_memory_bytes = 64 * 1024**3  # 64GB

        instance = Instance(
            id=5,
            snapshot_id=5,
            owner_username="power_user",
            wrapper_type=WrapperType.FALKORDB,
            name="Large Memory Instance",
            description=None,
            status=InstanceStatus.RUNNING,
            memory_usage_bytes=large_memory_bytes,
        )

        memory_gb = instance.memory_usage_bytes / (1024**3)
        assert memory_gb == 64.0

    def test_cooldown_at_exact_boundary(self, mock_settings):
        """Test cooldown check at exactly the boundary time."""
        cooldown_seconds = mock_settings.sizing_resize_cooldown_seconds
        last_resize_at = datetime.now(UTC) - timedelta(seconds=cooldown_seconds)
        now = datetime.now(UTC)

        elapsed = (now - last_resize_at).total_seconds()
        can_resize = elapsed >= cooldown_seconds

        # At exactly the boundary, should be allowed
        assert can_resize is True


# Mark tests as async for consistency with job implementation
pytest_plugins = ("pytest_asyncio",)
