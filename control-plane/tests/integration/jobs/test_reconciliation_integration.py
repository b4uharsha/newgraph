"""Integration tests for reconciliation job.

Tests reconciliation job with real database and mocked Kubernetes.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from graph_olap_schemas import WrapperType

from control_plane.jobs.reconciliation import run_reconciliation_job
from control_plane.models import InstanceErrorCode, InstanceStatus


class MockPod:
    """Mock Kubernetes pod."""

    def __init__(self, name: str, phase: str = "Running"):
        self.metadata = MagicMock()
        self.metadata.name = name
        self.status = MagicMock()
        self.status.phase = phase


@pytest.mark.asyncio
@pytest.mark.integration
class TestReconciliationIntegration:
    """Integration tests for reconciliation job."""

    async def test_reconciliation_deletes_orphan_pod(self, db_session, instance_repo, mapping_repo, snapshot_repo):
        """Test reconciliation job deletes orphaned pods."""
        # Create mapping and snapshot first (required FKs)
        mapping = await mapping_repo.create(name="test-mapping", created_by="test-user", raw_schema={})
        snapshot = await snapshot_repo.create(name="test-snapshot", mapping_id=mapping.id, created_by="test-user")

        # Create instance in database
        instance = await instance_repo.create(
            mapping_id=mapping.id,
            snapshot_id=snapshot.id,
            created_by="test-user",
            wrapper_type=WrapperType.RYUGRAPH,
            ttl=None,
            inactivity_timeout=None,
        )

        # Update with pod_name (simulate instance started)
        await instance_repo.update(instance.id, {"pod_name": "test-pod-1"})

        # Delete instance from database (simulate orphan scenario)
        await instance_repo.delete(instance.id)

        # Mock K8s service and engine (engine is used for metrics)
        with patch("control_plane.jobs.reconciliation.get_k8s_service") as mock_k8s_service, \
             patch("control_plane.infrastructure.database.get_engine") as mock_engine:
            mock_k8s = AsyncMock()
            mock_k8s_service.return_value = mock_k8s
            mock_engine.return_value.pool.size.return_value = 5
            mock_engine.return_value.pool.checkedout.return_value = 1

            # K8s has the orphaned pod
            mock_k8s.list_wrapper_pods.return_value = [MockPod("test-pod-1")]
            mock_k8s.delete_wrapper_pod_by_name.return_value = True

            # Run reconciliation job with test session
            await run_reconciliation_job(session=db_session)

            # Verify orphan pod was deleted
            mock_k8s.delete_wrapper_pod_by_name.assert_called_once_with(
                "test-pod-1", grace_period_seconds=30
            )

    async def test_reconciliation_marks_instance_failed_when_pod_missing(
        self, db_session, instance_repo, mapping_repo, snapshot_repo
    ):
        """Test reconciliation job marks instance as failed when pod is missing."""
        # Create mapping and snapshot first (required FKs)
        mapping = await mapping_repo.create(name="test-mapping", created_by="test-user", raw_schema={})
        snapshot = await snapshot_repo.create(name="test-snapshot", mapping_id=mapping.id, created_by="test-user")

        # Create instance with pod_name and RUNNING status
        instance = await instance_repo.create(
            mapping_id=mapping.id,
            snapshot_id=snapshot.id,
            created_by="test-user",
            wrapper_type=WrapperType.RYUGRAPH,
            ttl=None,
            inactivity_timeout=None,
        )

        # Update to RUNNING with pod_name
        await instance_repo.update(
            instance.id,
            {
                "pod_name": "test-pod-2",
                "status": InstanceStatus.RUNNING.value,
            },
        )

        # Mock K8s service and engine (engine is used for metrics)
        with patch("control_plane.jobs.reconciliation.get_k8s_service") as mock_k8s_service, \
             patch("control_plane.infrastructure.database.get_engine") as mock_engine:
            mock_k8s = AsyncMock()
            mock_k8s_service.return_value = mock_k8s
            mock_engine.return_value.pool.size.return_value = 5
            mock_engine.return_value.pool.checkedout.return_value = 1

            # K8s has no pods (pod disappeared)
            mock_k8s.list_wrapper_pods.return_value = []

            # Run reconciliation job with test session
            await run_reconciliation_job(session=db_session)

            # Verify instance was marked as FAILED
            updated_instance = await instance_repo.get(instance.id)
            assert updated_instance.status == InstanceStatus.FAILED
            assert updated_instance.error_code == InstanceErrorCode.UNEXPECTED_TERMINATION
            assert "disappeared from Kubernetes" in updated_instance.error_message

    async def test_reconciliation_fixes_status_drift(self, db_session, instance_repo, mapping_repo, snapshot_repo):
        """Test reconciliation job fixes status drift (DB says running but pod failed)."""
        # Create mapping and snapshot first (required FKs)
        mapping = await mapping_repo.create(name="test-mapping", created_by="test-user", raw_schema={})
        snapshot = await snapshot_repo.create(name="test-snapshot", mapping_id=mapping.id, created_by="test-user")

        # Create instance with pod_name and RUNNING status
        instance = await instance_repo.create(
            mapping_id=mapping.id,
            snapshot_id=snapshot.id,
            created_by="test-user",
            wrapper_type=WrapperType.RYUGRAPH,
            ttl=None,
            inactivity_timeout=None,
        )

        # Update to RUNNING with pod_name
        await instance_repo.update(
            instance.id,
            {
                "pod_name": "test-pod-3",
                "status": InstanceStatus.RUNNING.value,
            },
        )

        # Mock K8s service and engine (engine is used for metrics)
        with patch("control_plane.jobs.reconciliation.get_k8s_service") as mock_k8s_service, \
             patch("control_plane.infrastructure.database.get_engine") as mock_engine:
            mock_k8s = AsyncMock()
            mock_k8s_service.return_value = mock_k8s
            mock_engine.return_value.pool.size.return_value = 5
            mock_engine.return_value.pool.checkedout.return_value = 1

            # K8s has pod in Failed phase
            mock_k8s.list_wrapper_pods.return_value = [MockPod("test-pod-3", phase="Failed")]

            # Run reconciliation job with test session
            await run_reconciliation_job(session=db_session)

            # Verify instance was marked as FAILED
            updated_instance = await instance_repo.get(instance.id)
            assert updated_instance.status == InstanceStatus.FAILED
            assert updated_instance.error_code == InstanceErrorCode.UNEXPECTED_TERMINATION
            assert "Failed phase" in updated_instance.error_message

    async def test_reconciliation_handles_multiple_issues(self, db_session, instance_repo, mapping_repo, snapshot_repo):
        """Test reconciliation job handles multiple issues in one pass."""
        # Create mapping and snapshot first (required FKs)
        mapping = await mapping_repo.create(name="test-mapping", created_by="test-user", raw_schema={})
        snapshot = await snapshot_repo.create(name="test-snapshot", mapping_id=mapping.id, created_by="test-user")

        # Create multiple instances
        instance1 = await instance_repo.create(
            mapping_id=mapping.id, snapshot_id=snapshot.id, created_by="test-user", wrapper_type=WrapperType.RYUGRAPH, ttl=None
        )
        instance2 = await instance_repo.create(
            mapping_id=mapping.id, snapshot_id=snapshot.id, created_by="test-user", wrapper_type=WrapperType.RYUGRAPH, ttl=None
        )
        instance3 = await instance_repo.create(
            mapping_id=mapping.id, snapshot_id=snapshot.id, created_by="test-user", wrapper_type=WrapperType.RYUGRAPH, ttl=None
        )

        # Instance 1: RUNNING with pod_name, pod missing
        await instance_repo.update(
            instance1.id,
            {"pod_name": "pod-1", "status": InstanceStatus.RUNNING.value},
        )

        # Instance 2: RUNNING with pod_name, pod is Failed
        await instance_repo.update(
            instance2.id,
            {"pod_name": "pod-2", "status": InstanceStatus.RUNNING.value},
        )

        # Instance 3: Has pod_name but we'll delete it (orphan scenario)
        await instance_repo.update(instance3.id, {"pod_name": "pod-3"})
        await instance_repo.delete(instance3.id)

        # Mock K8s service and engine (engine is used for metrics)
        with patch("control_plane.jobs.reconciliation.get_k8s_service") as mock_k8s_service, \
             patch("control_plane.infrastructure.database.get_engine") as mock_engine:
            mock_k8s = AsyncMock()
            mock_k8s_service.return_value = mock_k8s
            mock_engine.return_value.pool.size.return_value = 5
            mock_engine.return_value.pool.checkedout.return_value = 1

            # K8s state:
            # - pod-1: missing (missing pod scenario)
            # - pod-2: Failed (status drift scenario)
            # - pod-3: exists (orphan scenario)
            mock_k8s.list_wrapper_pods.return_value = [
                MockPod("pod-2", phase="Failed"),
                MockPod("pod-3"),  # Orphan
            ]
            mock_k8s.delete_wrapper_pod_by_name.return_value = True

            # Run reconciliation job with test session
            await run_reconciliation_job(session=db_session)

            # Verify instance1 marked as FAILED (missing pod)
            updated1 = await instance_repo.get(instance1.id)
            assert updated1.status == InstanceStatus.FAILED

            # Verify instance2 marked as FAILED (status drift)
            updated2 = await instance_repo.get(instance2.id)
            assert updated2.status == InstanceStatus.FAILED

            # Verify orphan pod-3 was deleted
            mock_k8s.delete_wrapper_pod_by_name.assert_called_with(
                "pod-3", grace_period_seconds=30
            )

    async def test_reconciliation_ignores_instances_without_pod_name(
        self, db_session, instance_repo, mapping_repo, snapshot_repo
    ):
        """Test reconciliation job ignores instances without pod_name."""
        # Create mapping and snapshot first (required FKs)
        mapping = await mapping_repo.create(name="test-mapping", created_by="test-user", raw_schema={})
        snapshot = await snapshot_repo.create(name="test-snapshot", mapping_id=mapping.id, created_by="test-user")

        # Create instance without pod_name
        instance = await instance_repo.create(
            mapping_id=mapping.id,
            snapshot_id=snapshot.id,
            created_by="test-user",
            wrapper_type=WrapperType.RYUGRAPH,
            ttl=None,
        )

        # Update to RUNNING but no pod_name
        await instance_repo.update(instance.id, {"status": InstanceStatus.RUNNING.value})

        # Mock K8s service and engine (engine is used for metrics)
        with patch("control_plane.jobs.reconciliation.get_k8s_service") as mock_k8s_service, \
             patch("control_plane.infrastructure.database.get_engine") as mock_engine:
            mock_k8s = AsyncMock()
            mock_k8s_service.return_value = mock_k8s
            mock_engine.return_value.pool.size.return_value = 5
            mock_engine.return_value.pool.checkedout.return_value = 1

            # K8s has no pods
            mock_k8s.list_wrapper_pods.return_value = []

            # Run reconciliation job with test session
            await run_reconciliation_job(session=db_session)

            # Verify instance status unchanged (not marked as FAILED)
            updated = await instance_repo.get(instance.id)
            assert updated.status == InstanceStatus.RUNNING  # Unchanged


# Use pytest-asyncio for async tests
pytest_plugins = ("pytest_asyncio",)
