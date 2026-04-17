"""Unit tests for instance orchestration job.

Tests the job that monitors instances in WAITING_FOR_SNAPSHOT status
and transitions them to STARTING when their snapshots become ready,
or to FAILED when their snapshots fail.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from graph_olap_schemas import WrapperType

from control_plane.models import (
    Instance,
    InstanceStatus,
    Snapshot,
    SnapshotStatus,
)


class TestInstanceOrchestrationJob:
    """Tests for the instance orchestration job.

    The job performs the following:
    1. Query all instances with status=WAITING_FOR_SNAPSHOT
    2. For each instance, check the associated snapshot's status
    3. If snapshot is READY, transition instance to STARTING and spawn pod
    4. If snapshot is FAILED, transition instance to FAILED
    5. If snapshot is still PENDING/CREATING, skip (check again later)
    """

    @pytest.fixture
    def mock_instance_repo(self) -> MagicMock:
        """Create mock instance repository."""
        return MagicMock()

    @pytest.fixture
    def mock_snapshot_repo(self) -> MagicMock:
        """Create mock snapshot repository."""
        return MagicMock()

    @pytest.fixture
    def mock_k8s_service(self) -> MagicMock:
        """Create mock K8s service for pod spawning."""
        return MagicMock()

    def _create_waiting_instance(
        self,
        instance_id: int = 1,
        snapshot_id: int = 1,
        owner: str = "test.user",
    ) -> Instance:
        """Create a waiting instance for testing."""
        now = datetime.now(UTC)
        return Instance(
            id=instance_id,
            snapshot_id=snapshot_id,
            pending_snapshot_id=snapshot_id,  # Required for orchestration job
            owner_username=owner,
            wrapper_type=WrapperType.FALKORDB,
            name=f"Test Instance {instance_id}",
            description="Test instance waiting for snapshot",
            url_slug=f"test-instance-{instance_id}",
            status=InstanceStatus.WAITING_FOR_SNAPSHOT,
            created_at=now,
            updated_at=now,
        )

    def _create_snapshot(
        self,
        snapshot_id: int = 1,
        status: SnapshotStatus = SnapshotStatus.PENDING,
        mapping_id: int = 1,
        mapping_version: int = 1,
        error_message: str | None = None,
    ) -> Snapshot:
        """Create a snapshot for testing."""
        now = datetime.now(UTC)
        return Snapshot(
            id=snapshot_id,
            mapping_id=mapping_id,
            mapping_version=mapping_version,
            owner_username="test.user",
            name=f"Test Snapshot {snapshot_id}",
            description="Test snapshot",
            gcs_path=f"gs://test-bucket/user/{mapping_id}/v{mapping_version}/{snapshot_id}/",
            status=status,
            size_bytes=1024000 if status == SnapshotStatus.READY else None,
            node_counts={"Customer": 100} if status == SnapshotStatus.READY else None,
            edge_counts={"PURCHASED": 500} if status == SnapshotStatus.READY else None,
            error_message=error_message,
            created_at=now,
            updated_at=now,
        )

    @pytest.mark.asyncio
    async def test_no_waiting_instances_noop(
        self,
        mock_instance_repo: MagicMock,
    ):
        """Test job does nothing when no instances are waiting."""
        # No waiting instances
        mock_instance_repo.get_waiting_for_snapshot = AsyncMock(return_value=[])

        # Import and run job
        from control_plane.jobs.instance_orchestration import run_instance_orchestration

        result = await run_instance_orchestration(
            instance_repo=mock_instance_repo,
            snapshot_repo=MagicMock(),
            k8s_service=MagicMock(),
        )

        # Should complete with no changes
        assert result["processed"] == 0
        assert result["transitioned"] == 0
        assert result["failed"] == 0

    @pytest.mark.asyncio
    async def test_transition_to_starting_when_snapshot_ready(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_k8s_service: MagicMock,
    ):
        """Test instance transitions to STARTING when snapshot is READY."""
        waiting_instance = self._create_waiting_instance(instance_id=1, snapshot_id=1)
        ready_snapshot = self._create_snapshot(snapshot_id=1, status=SnapshotStatus.READY)

        mock_instance_repo.get_waiting_for_snapshot = AsyncMock(
            return_value=[waiting_instance]
        )
        mock_snapshot_repo.get_by_id = AsyncMock(return_value=ready_snapshot)
        mock_instance_repo.transition_to_starting = AsyncMock(
            return_value=Instance(
                **{**waiting_instance.__dict__, "status": InstanceStatus.STARTING}
            )
        )
        mock_k8s_service.create_wrapper_pod = AsyncMock(return_value=("wrapper-pod-123", "https://test.example.com/wrapper-pod-123"))

        from control_plane.jobs.instance_orchestration import run_instance_orchestration

        result = await run_instance_orchestration(
            instance_repo=mock_instance_repo,
            snapshot_repo=mock_snapshot_repo,
            k8s_service=mock_k8s_service,
        )

        # Verify transition
        assert result["processed"] == 1
        assert result["transitioned"] == 1
        mock_instance_repo.transition_to_starting.assert_called_once_with(instance_id=1)
        mock_k8s_service.create_wrapper_pod.assert_called_once()

    @pytest.mark.asyncio
    async def test_mark_failed_when_snapshot_fails(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
    ):
        """Test instance is marked FAILED when snapshot fails."""
        waiting_instance = self._create_waiting_instance(instance_id=1, snapshot_id=1)
        failed_snapshot = self._create_snapshot(
            snapshot_id=1,
            status=SnapshotStatus.FAILED,
            error_message="Export failed: Connection timeout",
        )

        mock_instance_repo.get_waiting_for_snapshot = AsyncMock(
            return_value=[waiting_instance]
        )
        mock_snapshot_repo.get_by_id = AsyncMock(return_value=failed_snapshot)
        mock_instance_repo.update_status = AsyncMock(
            return_value=Instance(
                **{
                    **waiting_instance.__dict__,
                    "status": InstanceStatus.FAILED,
                    "error_message": "Snapshot creation failed",
                }
            )
        )

        from control_plane.jobs.instance_orchestration import run_instance_orchestration

        result = await run_instance_orchestration(
            instance_repo=mock_instance_repo,
            snapshot_repo=mock_snapshot_repo,
            k8s_service=MagicMock(),
        )

        # Verify failure handling
        assert result["processed"] == 1
        assert result["failed"] == 1
        mock_instance_repo.update_status.assert_called_once()
        call_args = mock_instance_repo.update_status.call_args
        assert call_args.kwargs.get("status") == InstanceStatus.FAILED or \
               call_args[1].get("status") == InstanceStatus.FAILED

    @pytest.mark.asyncio
    async def test_skip_when_snapshot_still_pending(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
    ):
        """Test instance is skipped when snapshot is still PENDING."""
        waiting_instance = self._create_waiting_instance(instance_id=1, snapshot_id=1)
        pending_snapshot = self._create_snapshot(
            snapshot_id=1, status=SnapshotStatus.PENDING
        )

        mock_instance_repo.get_waiting_for_snapshot = AsyncMock(
            return_value=[waiting_instance]
        )
        mock_snapshot_repo.get_by_id = AsyncMock(return_value=pending_snapshot)

        from control_plane.jobs.instance_orchestration import run_instance_orchestration

        result = await run_instance_orchestration(
            instance_repo=mock_instance_repo,
            snapshot_repo=mock_snapshot_repo,
            k8s_service=MagicMock(),
        )

        # Instance should be skipped
        assert result["processed"] == 1
        assert result["skipped"] == 1
        assert result["transitioned"] == 0

    @pytest.mark.asyncio
    async def test_skip_when_snapshot_still_creating(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
    ):
        """Test instance is skipped when snapshot is still CREATING."""
        waiting_instance = self._create_waiting_instance(instance_id=1, snapshot_id=1)
        creating_snapshot = self._create_snapshot(
            snapshot_id=1, status=SnapshotStatus.CREATING
        )

        mock_instance_repo.get_waiting_for_snapshot = AsyncMock(
            return_value=[waiting_instance]
        )
        mock_snapshot_repo.get_by_id = AsyncMock(return_value=creating_snapshot)

        from control_plane.jobs.instance_orchestration import run_instance_orchestration

        result = await run_instance_orchestration(
            instance_repo=mock_instance_repo,
            snapshot_repo=mock_snapshot_repo,
            k8s_service=MagicMock(),
        )

        # Instance should be skipped
        assert result["processed"] == 1
        assert result["skipped"] == 1

    @pytest.mark.asyncio
    async def test_handles_multiple_waiting_instances(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_k8s_service: MagicMock,
    ):
        """Test job handles multiple waiting instances correctly."""
        # 3 instances: 1 ready, 1 failed, 1 pending
        instances = [
            self._create_waiting_instance(instance_id=1, snapshot_id=1),
            self._create_waiting_instance(instance_id=2, snapshot_id=2),
            self._create_waiting_instance(instance_id=3, snapshot_id=3),
        ]

        snapshots = {
            1: self._create_snapshot(snapshot_id=1, status=SnapshotStatus.READY),
            2: self._create_snapshot(
                snapshot_id=2,
                status=SnapshotStatus.FAILED,
                error_message="Export failed",
            ),
            3: self._create_snapshot(snapshot_id=3, status=SnapshotStatus.PENDING),
        }

        mock_instance_repo.get_waiting_for_snapshot = AsyncMock(return_value=instances)
        mock_snapshot_repo.get_by_id = AsyncMock(side_effect=lambda sid: snapshots[sid])
        mock_instance_repo.transition_to_starting = AsyncMock(
            side_effect=lambda instance_id: Instance(
                **{**instances[0].__dict__, "id": instance_id, "status": InstanceStatus.STARTING}
            )
        )
        mock_instance_repo.update_status = AsyncMock(
            side_effect=lambda instance_id, status, **kwargs: Instance(
                **{
                    **instances[1].__dict__,
                    "id": instance_id,
                    "status": status,
                    "error_message": kwargs.get("error_message"),
                }
            )
        )
        mock_k8s_service.create_wrapper_pod = AsyncMock(return_value=("pod-123", "https://test.example.com/pod-123"))

        from control_plane.jobs.instance_orchestration import run_instance_orchestration

        result = await run_instance_orchestration(
            instance_repo=mock_instance_repo,
            snapshot_repo=mock_snapshot_repo,
            k8s_service=mock_k8s_service,
        )

        assert result["processed"] == 3
        assert result["transitioned"] == 1  # Instance 1
        assert result["failed"] == 1  # Instance 2
        assert result["skipped"] == 1  # Instance 3

    @pytest.mark.asyncio
    async def test_handles_missing_snapshot_gracefully(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
    ):
        """Test job handles missing snapshot gracefully."""
        waiting_instance = self._create_waiting_instance(instance_id=1, snapshot_id=999)

        mock_instance_repo.get_waiting_for_snapshot = AsyncMock(
            return_value=[waiting_instance]
        )
        mock_snapshot_repo.get_by_id = AsyncMock(return_value=None)  # Snapshot deleted
        mock_instance_repo.update_status = AsyncMock(
            return_value=Instance(
                **{
                    **waiting_instance.__dict__,
                    "status": InstanceStatus.FAILED,
                    "error_message": "Snapshot not found",
                }
            )
        )

        from control_plane.jobs.instance_orchestration import run_instance_orchestration

        result = await run_instance_orchestration(
            instance_repo=mock_instance_repo,
            snapshot_repo=mock_snapshot_repo,
            k8s_service=MagicMock(),
        )

        # Should mark instance as failed
        assert result["processed"] == 1
        assert result["failed"] == 1
        mock_instance_repo.update_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_k8s_spawn_failure(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_k8s_service: MagicMock,
    ):
        """Test job handles K8s pod spawn failure gracefully."""
        waiting_instance = self._create_waiting_instance(instance_id=1, snapshot_id=1)
        ready_snapshot = self._create_snapshot(snapshot_id=1, status=SnapshotStatus.READY)

        mock_instance_repo.get_waiting_for_snapshot = AsyncMock(
            return_value=[waiting_instance]
        )
        mock_snapshot_repo.get_by_id = AsyncMock(return_value=ready_snapshot)
        mock_instance_repo.transition_to_starting = AsyncMock(
            return_value=Instance(
                **{**waiting_instance.__dict__, "status": InstanceStatus.STARTING}
            )
        )
        mock_k8s_service.create_wrapper_pod = AsyncMock(
            side_effect=Exception("K8s API error")
        )
        mock_instance_repo.update_status = AsyncMock(
            return_value=Instance(
                **{
                    **waiting_instance.__dict__,
                    "status": InstanceStatus.FAILED,
                    "error_message": "Failed to spawn pod",
                }
            )
        )

        from control_plane.jobs.instance_orchestration import run_instance_orchestration

        result = await run_instance_orchestration(
            instance_repo=mock_instance_repo,
            snapshot_repo=mock_snapshot_repo,
            k8s_service=mock_k8s_service,
        )

        # K8s pod creation failure is handled gracefully - instance is still transitioned
        # The reconciliation job will retry failed pods later
        assert result["processed"] == 1
        assert result["transitioned"] == 1  # Instance was transitioned to starting
        assert result["errors"] == 0  # K8s failure doesn't count as error

    @pytest.mark.asyncio
    async def test_passes_correct_data_to_k8s_service(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_k8s_service: MagicMock,
    ):
        """Test job passes correct data to K8s service for pod spawning."""
        waiting_instance = self._create_waiting_instance(instance_id=42, snapshot_id=7)
        ready_snapshot = self._create_snapshot(
            snapshot_id=7,
            status=SnapshotStatus.READY,
            mapping_id=3,
            mapping_version=2,
        )

        mock_instance_repo.get_waiting_for_snapshot = AsyncMock(
            return_value=[waiting_instance]
        )
        mock_snapshot_repo.get_by_id = AsyncMock(return_value=ready_snapshot)
        mock_instance_repo.transition_to_starting = AsyncMock(
            return_value=Instance(
                **{**waiting_instance.__dict__, "status": InstanceStatus.STARTING}
            )
        )
        mock_k8s_service.create_wrapper_pod = AsyncMock(return_value=("wrapper-pod-42", "https://test.example.com/wrapper-pod-42"))

        from control_plane.jobs.instance_orchestration import run_instance_orchestration

        await run_instance_orchestration(
            instance_repo=mock_instance_repo,
            snapshot_repo=mock_snapshot_repo,
            k8s_service=mock_k8s_service,
        )

        # Verify K8s service was called with correct data
        mock_k8s_service.create_wrapper_pod.assert_called_once()
        call_kwargs = mock_k8s_service.create_wrapper_pod.call_args.kwargs
        assert call_kwargs["instance_id"] == 42
        assert call_kwargs["snapshot_id"] == 7
        assert call_kwargs["gcs_path"] == ready_snapshot.gcs_path
        assert call_kwargs["wrapper_type"] == waiting_instance.wrapper_type
        assert call_kwargs["mapping_version"] == 2

    @pytest.mark.asyncio
    async def test_continues_on_individual_instance_error(
        self,
        mock_instance_repo: MagicMock,
        mock_snapshot_repo: MagicMock,
        mock_k8s_service: MagicMock,
    ):
        """Test job continues processing other instances after an error."""
        instances = [
            self._create_waiting_instance(instance_id=1, snapshot_id=1),
            self._create_waiting_instance(instance_id=2, snapshot_id=2),
        ]

        ready_snapshot_1 = self._create_snapshot(snapshot_id=1, status=SnapshotStatus.READY)
        ready_snapshot_2 = self._create_snapshot(snapshot_id=2, status=SnapshotStatus.READY)

        mock_instance_repo.get_waiting_for_snapshot = AsyncMock(return_value=instances)

        # First snapshot lookup succeeds, second fails
        mock_snapshot_repo.get_by_id = AsyncMock(
            side_effect=[ready_snapshot_1, ready_snapshot_2]
        )

        # First transition fails, second succeeds
        mock_instance_repo.transition_to_starting = AsyncMock(
            side_effect=[
                Exception("Database error"),
                Instance(**{**instances[1].__dict__, "status": InstanceStatus.STARTING}),
            ]
        )
        mock_k8s_service.create_wrapper_pod = AsyncMock(return_value=("pod-123", "https://test.example.com/pod-123"))

        from control_plane.jobs.instance_orchestration import run_instance_orchestration

        result = await run_instance_orchestration(
            instance_repo=mock_instance_repo,
            snapshot_repo=mock_snapshot_repo,
            k8s_service=mock_k8s_service,
        )

        # Both should be processed, one error, one success
        assert result["processed"] == 2
        assert result["errors"] == 1
        assert result["transitioned"] == 1
