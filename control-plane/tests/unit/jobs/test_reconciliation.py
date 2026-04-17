"""Unit tests for reconciliation job.

Tests orphan pod detection, missing pod detection, and status drift detection.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from control_plane.models import InstanceStatus


class MockInstance:
    """Mock instance for testing."""

    def __init__(self, id: int, pod_name: str | None, status: InstanceStatus):
        self.id = id
        self.pod_name = pod_name
        self.status = status


class MockPod:
    """Mock Kubernetes pod for testing."""

    def __init__(self, name: str, phase: str = "Running"):
        self.metadata = MagicMock()
        self.metadata.name = name
        self.status = MagicMock()
        self.status.phase = phase


class TestOrphanPodDetection:
    """Test orphan pod detection logic."""

    def test_detect_orphan_pod_when_no_database_instance(self):
        """Test orphan detected when pod exists but no database instance."""
        # Setup: DB has pod-1, K8s has pod-1 and pod-2
        db_instances = [MockInstance(id=1, pod_name="pod-1", status=InstanceStatus.RUNNING)]
        k8s_pods = [MockPod("pod-1"), MockPod("pod-2")]

        # Build lookup maps (same logic as reconciliation job)
        db_by_pod_name = {inst.pod_name: inst for inst in db_instances if inst.pod_name}
        k8s_by_name = {pod.metadata.name: pod for pod in k8s_pods}

        # Detect orphans
        orphaned_pods = []
        for pod_name in k8s_by_name:
            if pod_name not in db_by_pod_name:
                orphaned_pods.append(pod_name)

        # Verify
        assert orphaned_pods == ["pod-2"]

    def test_no_orphans_when_all_pods_have_instances(self):
        """Test no orphans when all pods have corresponding instances."""
        # Setup: DB has pod-1 and pod-2, K8s has pod-1 and pod-2
        db_instances = [
            MockInstance(id=1, pod_name="pod-1", status=InstanceStatus.RUNNING),
            MockInstance(id=2, pod_name="pod-2", status=InstanceStatus.RUNNING),
        ]
        k8s_pods = [MockPod("pod-1"), MockPod("pod-2")]

        # Build lookup maps
        db_by_pod_name = {inst.pod_name: inst for inst in db_instances if inst.pod_name}
        k8s_by_name = {pod.metadata.name: pod for pod in k8s_pods}

        # Detect orphans
        orphaned_pods = [name for name in k8s_by_name if name not in db_by_pod_name]

        # Verify
        assert orphaned_pods == []

    def test_multiple_orphans_detected(self):
        """Test multiple orphan pods detected."""
        # Setup: DB has pod-1, K8s has pod-1, pod-2, pod-3
        db_instances = [MockInstance(id=1, pod_name="pod-1", status=InstanceStatus.RUNNING)]
        k8s_pods = [MockPod("pod-1"), MockPod("pod-2"), MockPod("pod-3")]

        # Build lookup maps
        db_by_pod_name = {inst.pod_name: inst for inst in db_instances if inst.pod_name}
        k8s_by_name = {pod.metadata.name: pod for pod in k8s_pods}

        # Detect orphans
        orphaned_pods = [name for name in k8s_by_name if name not in db_by_pod_name]

        # Verify
        assert set(orphaned_pods) == {"pod-2", "pod-3"}

    def test_empty_database_all_pods_orphans(self):
        """Test when database is empty, all pods are orphans."""
        # Setup: DB is empty, K8s has pod-1 and pod-2
        db_instances = []
        k8s_pods = [MockPod("pod-1"), MockPod("pod-2")]

        # Build lookup maps
        db_by_pod_name = {inst.pod_name: inst for inst in db_instances if inst.pod_name}
        k8s_by_name = {pod.metadata.name: pod for pod in k8s_pods}

        # Detect orphans
        orphaned_pods = [name for name in k8s_by_name if name not in db_by_pod_name]

        # Verify
        assert set(orphaned_pods) == {"pod-1", "pod-2"}

    def test_empty_kubernetes_no_orphans(self):
        """Test when Kubernetes is empty, no orphans to detect."""
        # Setup: DB has pod-1, K8s is empty
        db_instances = [MockInstance(id=1, pod_name="pod-1", status=InstanceStatus.RUNNING)]
        k8s_pods = []

        # Build lookup maps
        db_by_pod_name = {inst.pod_name: inst for inst in db_instances if inst.pod_name}
        k8s_by_name = {pod.metadata.name: pod for pod in k8s_pods}

        # Detect orphans
        orphaned_pods = [name for name in k8s_by_name if name not in db_by_pod_name]

        # Verify
        assert orphaned_pods == []


class TestMissingPodDetection:
    """Test missing pod detection logic."""

    def test_detect_missing_pod_for_starting_instance(self):
        """Test missing pod detected for instance in STARTING status."""
        # Setup: DB has instance with pod_name, but pod missing from K8s
        db_instances = [MockInstance(id=1, pod_name="pod-1", status=InstanceStatus.STARTING)]
        k8s_pods = []

        # Build lookup maps
        db_by_pod_name = {inst.pod_name: inst for inst in db_instances if inst.pod_name}
        k8s_by_name = {pod.metadata.name: pod for pod in k8s_pods}

        # Detect missing pods
        missing_pods = []
        for instance in db_instances:
            if instance.pod_name and instance.pod_name not in k8s_by_name:
                if instance.status in [InstanceStatus.STARTING, InstanceStatus.RUNNING]:
                    missing_pods.append(instance)

        # Verify
        assert len(missing_pods) == 1
        assert missing_pods[0].id == 1

    def test_detect_missing_pod_for_running_instance(self):
        """Test missing pod detected for instance in RUNNING status."""
        # Setup: DB has running instance with pod_name, but pod missing
        db_instances = [MockInstance(id=1, pod_name="pod-1", status=InstanceStatus.RUNNING)]
        k8s_pods = []

        # Build lookup maps
        k8s_by_name = {pod.metadata.name: pod for pod in k8s_pods}

        # Detect missing pods
        missing_pods = []
        for instance in db_instances:
            if instance.pod_name and instance.pod_name not in k8s_by_name:
                if instance.status in [InstanceStatus.STARTING, InstanceStatus.RUNNING]:
                    missing_pods.append(instance)

        # Verify
        assert len(missing_pods) == 1
        assert missing_pods[0].status == InstanceStatus.RUNNING

    def test_ignore_missing_pod_for_failed_instance(self):
        """Test missing pod ignored for instance in FAILED status."""
        # Setup: DB has failed instance with pod_name, pod missing
        db_instances = [MockInstance(id=1, pod_name="pod-1", status=InstanceStatus.FAILED)]
        k8s_pods = []

        # Build lookup maps
        k8s_by_name = {pod.metadata.name: pod for pod in k8s_pods}

        # Detect missing pods
        missing_pods = []
        for instance in db_instances:
            if instance.pod_name and instance.pod_name not in k8s_by_name:
                if instance.status in [InstanceStatus.STARTING, InstanceStatus.RUNNING]:
                    missing_pods.append(instance)

        # Verify - should be empty because instance is already FAILED
        assert missing_pods == []

    def test_ignore_instance_without_pod_name(self):
        """Test instances without pod_name are ignored."""
        # Setup: DB has instance without pod_name
        db_instances = [MockInstance(id=1, pod_name=None, status=InstanceStatus.RUNNING)]
        k8s_pods = []

        # Build lookup maps
        k8s_by_name = {pod.metadata.name: pod for pod in k8s_pods}

        # Detect missing pods
        missing_pods = []
        for instance in db_instances:
            if instance.pod_name and instance.pod_name not in k8s_by_name:
                if instance.status in [InstanceStatus.STARTING, InstanceStatus.RUNNING]:
                    missing_pods.append(instance)

        # Verify
        assert missing_pods == []

    def test_multiple_missing_pods_detected(self):
        """Test multiple missing pods detected."""
        # Setup: DB has 3 instances with pod_names, K8s has none
        db_instances = [
            MockInstance(id=1, pod_name="pod-1", status=InstanceStatus.RUNNING),
            MockInstance(id=2, pod_name="pod-2", status=InstanceStatus.STARTING),
            MockInstance(id=3, pod_name="pod-3", status=InstanceStatus.RUNNING),
        ]
        k8s_pods = []

        # Build lookup maps
        k8s_by_name = {pod.metadata.name: pod for pod in k8s_pods}

        # Detect missing pods
        missing_pods = []
        for instance in db_instances:
            if instance.pod_name and instance.pod_name not in k8s_by_name:
                if instance.status in [InstanceStatus.STARTING, InstanceStatus.RUNNING]:
                    missing_pods.append(instance)

        # Verify
        assert len(missing_pods) == 3


class TestStatusDriftDetection:
    """Test status drift detection logic."""

    def test_detect_drift_when_db_running_pod_failed(self):
        """Test drift detected when DB says RUNNING but pod is Failed."""
        # Setup: DB has running instance, K8s pod is Failed
        db_instances = [MockInstance(id=1, pod_name="pod-1", status=InstanceStatus.RUNNING)]
        k8s_pods = [MockPod("pod-1", phase="Failed")]

        # Build lookup maps
        k8s_by_name = {pod.metadata.name: pod for pod in k8s_pods}

        # Detect status drift
        status_drift = []
        for instance in db_instances:
            if not instance.pod_name:
                continue
            pod = k8s_by_name.get(instance.pod_name)
            if pod:
                pod_phase = pod.status.phase
                # Database says running but pod is failed
                if instance.status == InstanceStatus.RUNNING and pod_phase == "Failed":
                    status_drift.append((instance, pod))

        # Verify
        assert len(status_drift) == 1
        assert status_drift[0][0].id == 1
        assert status_drift[0][1].status.phase == "Failed"

    def test_no_drift_when_db_running_pod_running(self):
        """Test no drift when DB says RUNNING and pod is Running."""
        # Setup: DB has running instance, K8s pod is Running
        db_instances = [MockInstance(id=1, pod_name="pod-1", status=InstanceStatus.RUNNING)]
        k8s_pods = [MockPod("pod-1", phase="Running")]

        # Build lookup maps
        k8s_by_name = {pod.metadata.name: pod for pod in k8s_pods}

        # Detect status drift
        status_drift = []
        for instance in db_instances:
            if not instance.pod_name:
                continue
            pod = k8s_by_name.get(instance.pod_name)
            if pod:
                pod_phase = pod.status.phase
                if instance.status == InstanceStatus.RUNNING and pod_phase == "Failed":
                    status_drift.append((instance, pod))

        # Verify
        assert status_drift == []

    def test_no_drift_when_db_starting_pod_failed(self):
        """Test no drift when DB says STARTING and pod is Failed (not checked)."""
        # Setup: DB has starting instance, K8s pod is Failed
        db_instances = [MockInstance(id=1, pod_name="pod-1", status=InstanceStatus.STARTING)]
        k8s_pods = [MockPod("pod-1", phase="Failed")]

        # Build lookup maps
        k8s_by_name = {pod.metadata.name: pod for pod in k8s_pods}

        # Detect status drift (only checks RUNNING instances)
        status_drift = []
        for instance in db_instances:
            if not instance.pod_name:
                continue
            pod = k8s_by_name.get(instance.pod_name)
            if pod:
                pod_phase = pod.status.phase
                # Only check drift for RUNNING instances
                if instance.status == InstanceStatus.RUNNING and pod_phase == "Failed":
                    status_drift.append((instance, pod))

        # Verify - no drift because instance is STARTING, not RUNNING
        assert status_drift == []

    def test_ignore_instance_without_pod_name(self):
        """Test instances without pod_name are ignored in drift detection."""
        # Setup: DB has instance without pod_name
        db_instances = [MockInstance(id=1, pod_name=None, status=InstanceStatus.RUNNING)]
        k8s_pods = []

        # Build lookup maps
        k8s_by_name = {pod.metadata.name: pod for pod in k8s_pods}

        # Detect status drift
        status_drift = []
        for instance in db_instances:
            if not instance.pod_name:
                continue  # Skip
            pod = k8s_by_name.get(instance.pod_name)
            if pod:
                pod_phase = pod.status.phase
                if instance.status == InstanceStatus.RUNNING and pod_phase == "Failed":
                    status_drift.append((instance, pod))

        # Verify
        assert status_drift == []

    def test_multiple_status_drifts_detected(self):
        """Test multiple status drifts detected."""
        # Setup: DB has 3 running instances, K8s has 2 Failed pods
        db_instances = [
            MockInstance(id=1, pod_name="pod-1", status=InstanceStatus.RUNNING),
            MockInstance(id=2, pod_name="pod-2", status=InstanceStatus.RUNNING),
            MockInstance(id=3, pod_name="pod-3", status=InstanceStatus.STARTING),  # Not checked
        ]
        k8s_pods = [
            MockPod("pod-1", phase="Failed"),
            MockPod("pod-2", phase="Failed"),
            MockPod("pod-3", phase="Failed"),
        ]

        # Build lookup maps
        k8s_by_name = {pod.metadata.name: pod for pod in k8s_pods}

        # Detect status drift
        status_drift = []
        for instance in db_instances:
            if not instance.pod_name:
                continue
            pod = k8s_by_name.get(instance.pod_name)
            if pod:
                pod_phase = pod.status.phase
                if instance.status == InstanceStatus.RUNNING and pod_phase == "Failed":
                    status_drift.append((instance, pod))

        # Verify - only 2 drifts (pod-3 instance is STARTING)
        assert len(status_drift) == 2


class TestLookupMapBuilding:
    """Test lookup map building logic."""

    def test_db_lookup_excludes_instances_without_pod_name(self):
        """Test DB lookup map excludes instances without pod_name."""
        # Setup: Mix of instances with and without pod_name
        db_instances = [
            MockInstance(id=1, pod_name="pod-1", status=InstanceStatus.RUNNING),
            MockInstance(id=2, pod_name=None, status=InstanceStatus.RUNNING),
            MockInstance(id=3, pod_name="pod-3", status=InstanceStatus.RUNNING),
        ]

        # Build lookup map (same logic as job)
        db_by_pod_name = {inst.pod_name: inst for inst in db_instances if inst.pod_name}

        # Verify
        assert len(db_by_pod_name) == 2
        assert "pod-1" in db_by_pod_name
        assert "pod-3" in db_by_pod_name
        assert None not in db_by_pod_name

    def test_k8s_lookup_by_pod_name(self):
        """Test K8s lookup map uses pod metadata.name."""
        # Setup: K8s pods
        k8s_pods = [
            MockPod("pod-1"),
            MockPod("pod-2"),
            MockPod("pod-3"),
        ]

        # Build lookup map
        k8s_by_name = {pod.metadata.name: pod for pod in k8s_pods}

        # Verify
        assert len(k8s_by_name) == 3
        assert "pod-1" in k8s_by_name
        assert "pod-2" in k8s_by_name
        assert "pod-3" in k8s_by_name

    def test_empty_lookups_when_no_data(self):
        """Test empty lookup maps when no data."""
        db_instances = []
        k8s_pods = []

        # Build lookup maps
        db_by_pod_name = {inst.pod_name: inst for inst in db_instances if inst.pod_name}
        k8s_by_name = {pod.metadata.name: pod for pod in k8s_pods}

        # Verify
        assert db_by_pod_name == {}
        assert k8s_by_name == {}


@pytest.mark.asyncio
class TestReconciliationJobIntegration:
    """Test reconciliation job with mocked dependencies."""

    async def test_reconciliation_job_processes_orphans(self):
        """Test reconciliation job detects and cleans orphan pods."""
        from control_plane.jobs.reconciliation import run_reconciliation_job

        # Mock database session and repositories
        with patch("control_plane.jobs.reconciliation.get_session") as mock_session:
            with patch("control_plane.jobs.reconciliation.InstanceRepository") as MockRepo:
                with patch("control_plane.jobs.reconciliation.get_k8s_service") as mock_k8s_service:
                    with patch("control_plane.jobs.reconciliation.metrics") as mock_metrics:
                        # Setup mocks
                        mock_repo = AsyncMock()
                        MockRepo.return_value = mock_repo

                        # DB has pod-1, K8s has pod-1 and pod-2 (orphan)
                        mock_repo.list_all.return_value = [
                            MockInstance(id=1, pod_name="pod-1", status=InstanceStatus.RUNNING)
                        ]

                        mock_k8s = AsyncMock()
                        mock_k8s_service.return_value = mock_k8s
                        mock_k8s.list_wrapper_pods.return_value = [
                            MockPod("pod-1"),
                            MockPod("pod-2"),  # Orphan
                        ]
                        mock_k8s.delete_wrapper_pod_by_name.return_value = True

                        # Mock session context manager
                        mock_session.return_value.__aenter__.return_value = AsyncMock()
                        mock_session.return_value.__aexit__.return_value = AsyncMock()

                        # Run job
                        await run_reconciliation_job()

                        # Verify orphan pod was deleted
                        mock_k8s.delete_wrapper_pod_by_name.assert_called_once_with(
                            "pod-2", grace_period_seconds=30
                        )

                        # Verify metrics
                        mock_metrics.orphaned_pods_detected_total.inc.assert_called()
                        mock_metrics.orphaned_pods_cleaned_total.inc.assert_called()


# Mark all tests for asyncio compatibility
pytest_plugins = ("pytest_asyncio",)
