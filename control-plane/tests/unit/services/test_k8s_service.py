"""Unit tests for K8sService.

Tests all K8s operations using FakeK8sClient for fast, isolated tests
without requiring a real K8s cluster.
"""

import pytest
from graph_olap_schemas import WrapperType
from kubernetes.client import (
    ApiException,
    V1ObjectMeta,
    V1Pod,
    V1PodCondition,
    V1PodStatus,
)

from control_plane.config import Settings
from control_plane.services.k8s_service import K8sService
from tests.fakes import FakeK8sClient


@pytest.fixture
def settings():
    """Test settings with K8s configuration.

    Note: Uses a dummy PostgreSQL URL since this is a unit test that doesn't
    actually connect to the database (tests K8s operations with FakeK8sClient).
    """
    return Settings(
        database_url="postgresql+asyncpg://test:test@localhost:5432/test",
        k8s_namespace="test-namespace",
        wrapper_image="ryugraph-wrapper:sha-test123",
        wrapper_external_base_url="https://api.example.com",
        internal_api_key="test-internal-key",
    )


@pytest.fixture
def settings_no_external_url(settings):
    """Test settings without external URL."""
    settings.wrapper_external_base_url = None
    return settings


@pytest.fixture
def fake_k8s():
    """Fresh fake K8s client."""
    return FakeK8sClient()


@pytest.fixture
def k8s_service(settings, fake_k8s):
    """K8sService with injected fake K8s client."""
    service = K8sService(settings)
    # Inject fake client and mark as initialized
    service._core_api = fake_k8s
    service._initialized = True
    return service


class TestK8sServiceInitialization:
    """Tests for K8sService initialization."""

    def test_init_stores_settings(self, settings):
        """Test initialization stores settings."""
        service = K8sService(settings)

        assert service._settings == settings
        assert service._namespace == "test-namespace"
        assert service._wrapper_image == "ryugraph-wrapper:sha-test123"
        assert service._external_base_url == "https://api.example.com"
        assert service._initialized is False

    def test_ensure_initialized_marks_initialized(self, settings):
        """Test _ensure_initialized sets flag even on failure."""
        service = K8sService(settings)

        # Should not raise even if K8s config fails
        service._ensure_initialized()

        assert service._initialized is True


class TestBuildPodSpec:
    """Tests for _build_wrapper_pod_spec."""

    def test_build_pod_spec_basic(self, k8s_service):
        """Test pod spec generation with all fields."""
        spec = k8s_service._build_wrapper_pod_spec(
            instance_id=123,
            url_slug="abc-def-123",
            wrapper_type=WrapperType.RYUGRAPH,
            snapshot_id=456,
            mapping_id=789,
            mapping_version=2,
            owner_username="alice",
            owner_email="alice@example.com",
            gcs_path="gs://bucket/path",
            instance_name="Customer Graph Q4",
            mapping_name="customer_accounts",
        )

        # Check metadata
        assert spec["metadata"]["name"] == "wrapper-abc-def-123"
        labels = spec["metadata"]["labels"]
        assert labels["app"] == "ryugraph-wrapper"
        assert labels["graph-id"] == "123"
        assert labels["instance-id"] == "123"
        assert labels["url-slug"] == "abc-def-123"
        assert labels["snapshot-id"] == "456"
        assert labels["mapping-id"] == "789"
        assert labels["owner-email"] == "alice-at-example-com"
        assert labels["owner"] == "alice"
        assert labels["graph-name"] == "Customer-Graph-Q4"
        assert labels["mapping-name"] == "customer_accounts"

        # Check container config
        container = spec["spec"]["containers"][0]
        assert container["name"] == "wrapper"
        # Image is now wrapper-specific (from WrapperFactory with parsed tag)
        assert container["image"] == "ryugraph-wrapper:sha-test123"
        assert container["ports"][0]["containerPort"] == 8000

        # Check environment variables
        env_dict = {e["name"]: e["value"] for e in container["env"]}
        assert env_dict["WRAPPER_INSTANCE_ID"] == "123"
        assert env_dict["WRAPPER_URL_SLUG"] == "abc-def-123"
        assert env_dict["WRAPPER_SNAPSHOT_ID"] == "456"
        assert env_dict["WRAPPER_MAPPING_ID"] == "789"
        assert env_dict["WRAPPER_MAPPING_VERSION"] == "2"
        assert env_dict["WRAPPER_OWNER_ID"] == "alice"
        assert env_dict["WRAPPER_GCS_BASE_PATH"] == "gs://bucket/path"

        # Check resources (from WrapperFactory for ryugraph, using config defaults)
        assert container["resources"]["requests"]["memory"] == "2Gi"
        assert container["resources"]["requests"]["cpu"] == "1"
        assert container["resources"]["limits"]["memory"] == "4Gi"
        assert container["resources"]["limits"]["cpu"] == "2"

    def test_build_pod_spec_with_storage_emulator(self, settings, fake_k8s):
        """Test pod spec includes storage emulator host when configured."""
        settings.storage_emulator_host = "http://fake-gcs:4443"
        service = K8sService(settings)
        service._core_api = fake_k8s
        service._initialized = True

        spec = service._build_wrapper_pod_spec(
            instance_id=1,
            url_slug="test",
            wrapper_type=WrapperType.RYUGRAPH,
            snapshot_id=1,
            mapping_id=1,
            mapping_version=1,
            owner_username="test",
            owner_email="test@example.com",
            gcs_path="gs://test",
        )

        container = spec["spec"]["containers"][0]
        env_dict = {e["name"]: e["value"] for e in container["env"]}
        assert env_dict["STORAGE_EMULATOR_HOST"] == "http://fake-gcs:4443"

    def test_build_pod_spec_without_storage_emulator(self, k8s_service):
        """Test pod spec excludes storage emulator when not configured."""
        spec = k8s_service._build_wrapper_pod_spec(
            instance_id=1,
            url_slug="test",
            wrapper_type=WrapperType.RYUGRAPH,
            snapshot_id=1,
            mapping_id=1,
            mapping_version=1,
            owner_username="test",
            owner_email="test@example.com",
            gcs_path="gs://test",
        )

        container = spec["spec"]["containers"][0]
        env_names = {e["name"] for e in container["env"]}
        assert "STORAGE_EMULATOR_HOST" not in env_names


class TestBuildServiceSpec:
    """Tests for _build_wrapper_service_spec."""

    def test_build_service_spec(self, k8s_service):
        """Test service spec generation."""
        spec = k8s_service._build_wrapper_service_spec(
            instance_id=123,
            url_slug="abc-def-123",
            wrapper_type=WrapperType.RYUGRAPH,
        )

        assert spec["metadata"]["name"] == "wrapper-abc-def-123"
        assert spec["metadata"]["labels"]["app"] == "ryugraph-wrapper"
        assert spec["metadata"]["labels"]["instance-id"] == "123"
        assert spec["spec"]["selector"]["url-slug"] == "abc-def-123"
        assert spec["spec"]["ports"][0]["port"] == 8000
        assert spec["spec"]["type"] == "ClusterIP"


class TestGetExternalInstanceUrl:
    """Tests for get_external_instance_url."""

    def test_get_external_url_with_configured_base(self, k8s_service):
        """Test external URL generation when base URL is configured."""
        url = k8s_service.get_external_instance_url("abc-def-123")
        assert url == "https://api.example.com/wrapper/abc-def-123"

    def test_get_external_url_strips_trailing_slash(self, settings, fake_k8s):
        """Test external URL strips trailing slash from base URL."""
        settings.wrapper_external_base_url = "https://api.example.com/"
        service = K8sService(settings)
        service._core_api = fake_k8s
        service._initialized = True

        url = service.get_external_instance_url("abc-def-123")
        assert url == "https://api.example.com/wrapper/abc-def-123"

    def test_get_external_url_falls_back_to_cluster_dns(self, settings_no_external_url, fake_k8s):
        """Test falls back to in-cluster DNS when external URL not configured."""
        service = K8sService(settings_no_external_url)
        service._core_api = fake_k8s
        service._initialized = True

        url = service.get_external_instance_url("abc-def-123")
        assert "svc.cluster.local:8000" in url
        assert "wrapper-abc-def-123" in url


class TestCreateWrapperPod:
    """Tests for create_wrapper_pod."""

    @pytest.mark.asyncio
    async def test_create_wrapper_pod_success(self, k8s_service, fake_k8s):
        """Test successful pod creation with service (no Ingress per ADR-101)."""
        pod_name, external_url = await k8s_service.create_wrapper_pod(
            instance_id=123,
            url_slug="abc-def-123",
            wrapper_type=WrapperType.RYUGRAPH,
            snapshot_id=456,
            mapping_id=789,
            mapping_version=2,
            owner_username="alice",
            owner_email="alice@example.com",
            gcs_path="gs://bucket/path",
        )

        assert pod_name == "wrapper-abc-def-123"
        assert external_url == "https://api.example.com/wrapper/abc-def-123"
        assert external_url is not None

        # Verify only Pod + Service are created (no Ingress per ADR-101)
        assert "wrapper-abc-def-123" in fake_k8s.pods
        assert "wrapper-abc-def-123" in fake_k8s.services

        # Verify call order (service first, then pod)
        assert fake_k8s.call_log[0][0] == "create_namespaced_service"
        assert fake_k8s.call_log[1][0] == "create_namespaced_pod"

    @pytest.mark.asyncio
    async def test_create_wrapper_pod_without_external_url(self, settings_no_external_url, fake_k8s):
        """Test pod creation falls back to in-cluster DNS when no external URL configured."""
        service = K8sService(settings_no_external_url)
        service._core_api = fake_k8s
        service._initialized = True

        pod_name, external_url = await service.create_wrapper_pod(
            instance_id=123,
            url_slug="abc-def-123",
            wrapper_type=WrapperType.RYUGRAPH,
            snapshot_id=456,
            mapping_id=789,
            mapping_version=2,
            owner_username="alice",
            owner_email="alice@example.com",
            gcs_path="gs://bucket/path",
        )

        assert pod_name == "wrapper-abc-def-123"
        # Falls back to in-cluster DNS (ADR-101 C13)
        assert "svc.cluster.local:8000" in external_url
        assert "wrapper-abc-def-123" in external_url

    @pytest.mark.asyncio
    async def test_create_wrapper_pod_service_already_exists(self, k8s_service, fake_k8s):
        """Test pod creation continues when service already exists (409)."""
        # Pre-create service
        service_spec = k8s_service._build_wrapper_service_spec(123, "abc-def-123", WrapperType.RYUGRAPH)
        fake_k8s.create_namespaced_service("test-namespace", service_spec)

        pod_name, external_url = await k8s_service.create_wrapper_pod(
            instance_id=123,
            url_slug="abc-def-123",
            wrapper_type=WrapperType.RYUGRAPH,
            snapshot_id=456,
            mapping_id=789,
            mapping_version=2,
            owner_username="alice",
            owner_email="alice@example.com",
            gcs_path="gs://bucket/path",
        )

        # Should still succeed
        assert pod_name == "wrapper-abc-def-123"
        assert "wrapper-abc-def-123" in fake_k8s.pods

    @pytest.mark.asyncio
    async def test_create_wrapper_pod_already_exists(self, k8s_service, fake_k8s):
        """Test pod creation returns existing pod name when pod exists (409)."""
        # Pre-create pod
        pod_spec = k8s_service._build_wrapper_pod_spec(
            instance_id=123,
            url_slug="abc-def-123",
            wrapper_type=WrapperType.RYUGRAPH,
            snapshot_id=456,
            mapping_id=789,
            mapping_version=2,
            owner_username="alice",
            owner_email="alice@example.com",
            gcs_path="gs://bucket/path",
        )
        fake_k8s.create_namespaced_pod("test-namespace", pod_spec)

        pod_name, external_url = await k8s_service.create_wrapper_pod(
            instance_id=123,
            url_slug="abc-def-123",
            wrapper_type=WrapperType.RYUGRAPH,
            snapshot_id=456,
            mapping_id=789,
            mapping_version=2,
            owner_username="alice",
            owner_email="alice@example.com",
            gcs_path="gs://bucket/path",
        )

        # Should return existing pod name
        assert pod_name == "wrapper-abc-def-123"

    @pytest.mark.asyncio
    async def test_create_wrapper_pod_service_creation_error(self, k8s_service, fake_k8s):
        """Test pod creation continues when service creation fails (best-effort)."""
        # Inject error for service creation
        fake_k8s.set_error_on_next_call(
            "create_namespaced_service",
            ApiException(status=500, reason="InternalError"),
        )

        pod_name, external_url = await k8s_service.create_wrapper_pod(
            instance_id=123,
            url_slug="abc-def-123",
            wrapper_type=WrapperType.RYUGRAPH,
            snapshot_id=456,
            mapping_id=789,
            mapping_version=2,
            owner_username="alice",
            owner_email="alice@example.com",
            gcs_path="gs://bucket/path",
        )

        # Should still create pod despite service failure
        assert pod_name == "wrapper-abc-def-123"
        assert "wrapper-abc-def-123" in fake_k8s.pods

    @pytest.mark.asyncio
    async def test_create_wrapper_pod_failure(self, k8s_service, fake_k8s):
        """Test pod creation raises on pod creation failure (non-409)."""
        # Inject error for pod creation
        fake_k8s.set_error_on_next_call(
            "create_namespaced_pod",
            ApiException(status=500, reason="InternalError"),
        )

        with pytest.raises(ApiException) as exc_info:
            await k8s_service.create_wrapper_pod(
                instance_id=123,
                url_slug="abc-def-123",
                wrapper_type=WrapperType.RYUGRAPH,
                snapshot_id=456,
                mapping_id=789,
                mapping_version=2,
                owner_username="alice",
                owner_email="alice@example.com",
                gcs_path="gs://bucket/path",
            )

        assert exc_info.value.status == 500

    @pytest.mark.asyncio
    async def test_create_wrapper_pod_without_k8s(self, settings):
        """Test pod creation returns None when K8s not available."""
        service = K8sService(settings)
        # Don't initialize, leave _core_api as None
        service._initialized = True
        service._core_api = None

        pod_name, external_url = await service.create_wrapper_pod(
            instance_id=123,
            url_slug="abc-def-123",
            wrapper_type=WrapperType.RYUGRAPH,
            snapshot_id=456,
            mapping_id=789,
            mapping_version=2,
            owner_username="alice",
            owner_email="alice@example.com",
            gcs_path="gs://bucket/path",
        )

        assert pod_name is None
        assert external_url is None


class TestDeleteWrapperPod:
    """Tests for delete_wrapper_pod."""

    @pytest.mark.asyncio
    async def test_delete_wrapper_pod_success(self, k8s_service, fake_k8s):
        """Test successful deletion of pod and service."""
        # Pre-create resources
        pod_spec = k8s_service._build_wrapper_pod_spec(
            instance_id=123,
            url_slug="abc-def-123",
            wrapper_type=WrapperType.RYUGRAPH,
            snapshot_id=456,
            mapping_id=789,
            mapping_version=2,
            owner_username="alice",
            owner_email="alice@example.com",
            gcs_path="gs://bucket/path",
        )
        service_spec = k8s_service._build_wrapper_service_spec(123, "abc-def-123", WrapperType.RYUGRAPH)

        fake_k8s.create_namespaced_pod("test-namespace", pod_spec)
        fake_k8s.create_namespaced_service("test-namespace", service_spec)

        deleted = await k8s_service.delete_wrapper_pod("abc-def-123")

        assert deleted is True
        assert "wrapper-abc-def-123" not in fake_k8s.pods
        assert "wrapper-abc-def-123" not in fake_k8s.services

    @pytest.mark.asyncio
    async def test_delete_wrapper_pod_not_found(self, k8s_service, fake_k8s):
        """Test deletion returns False when resources don't exist."""
        deleted = await k8s_service.delete_wrapper_pod("nonexistent")

        assert deleted is False

    @pytest.mark.asyncio
    async def test_delete_wrapper_pod_partial_resources(self, k8s_service, fake_k8s):
        """Test deletion succeeds when only some resources exist."""
        # Only create service
        service_spec = k8s_service._build_wrapper_service_spec(123, "abc-def-123", WrapperType.RYUGRAPH)
        fake_k8s.create_namespaced_service("test-namespace", service_spec)

        deleted = await k8s_service.delete_wrapper_pod("abc-def-123")

        assert deleted is True
        assert "wrapper-abc-def-123" not in fake_k8s.services

    @pytest.mark.asyncio
    async def test_delete_wrapper_pod_error(self, k8s_service, fake_k8s):
        """Test deletion continues on error (best-effort)."""
        # Pre-create pod
        pod_spec = k8s_service._build_wrapper_pod_spec(
            instance_id=123,
            url_slug="abc-def-123",
            wrapper_type=WrapperType.RYUGRAPH,
            snapshot_id=456,
            mapping_id=789,
            mapping_version=2,
            owner_username="alice",
            owner_email="alice@example.com",
            gcs_path="gs://bucket/path",
        )
        fake_k8s.create_namespaced_pod("test-namespace", pod_spec)

        # Inject error for pod deletion
        fake_k8s.set_error_on_next_call(
            "delete_namespaced_pod",
            ApiException(status=500, reason="InternalError"),
        )

        # Should not raise, continues with best-effort
        deleted = await k8s_service.delete_wrapper_pod("abc-def-123")

        # Returns False since pod deletion failed
        assert deleted is False

    @pytest.mark.asyncio
    async def test_delete_wrapper_pod_without_k8s(self, settings):
        """Test deletion returns False when K8s not available."""
        service = K8sService(settings)
        service._initialized = True
        service._core_api = None

        deleted = await service.delete_wrapper_pod("abc-def-123")

        assert deleted is False


class TestGetPodStatus:
    """Tests for get_pod_status."""

    @pytest.mark.asyncio
    async def test_get_pod_status_success(self, k8s_service, fake_k8s):
        """Test getting pod status successfully."""
        # Create pod
        pod_spec = k8s_service._build_wrapper_pod_spec(
            instance_id=123,
            url_slug="abc-def-123",
            wrapper_type=WrapperType.RYUGRAPH,
            snapshot_id=456,
            mapping_id=789,
            mapping_version=2,
            owner_username="alice",
            owner_email="alice@example.com",
            gcs_path="gs://bucket/path",
        )
        fake_k8s.create_namespaced_pod("test-namespace", pod_spec)

        # Update pod status
        fake_k8s.set_pod_status("wrapper-abc-def-123", "Running")
        pod = fake_k8s.pods["wrapper-abc-def-123"]
        pod.status.pod_ip = "10.0.0.5"
        pod.status.conditions = [
            V1PodCondition(type="Ready", status="True"),
        ]

        status = await k8s_service.get_pod_status("abc-def-123")

        assert status["name"] == "wrapper-abc-def-123"
        assert status["phase"] == "Running"
        assert status["pod_ip"] == "10.0.0.5"
        assert len(status["conditions"]) == 1
        assert status["conditions"][0]["type"] == "Ready"

    @pytest.mark.asyncio
    async def test_get_pod_status_not_found(self, k8s_service, fake_k8s):
        """Test get_pod_status returns None when pod not found."""
        status = await k8s_service.get_pod_status("nonexistent")
        assert status is None

    @pytest.mark.asyncio
    async def test_get_pod_status_api_error(self, k8s_service, fake_k8s):
        """Test get_pod_status raises on non-404 API errors."""
        fake_k8s.set_error_on_next_call(
            "read_namespaced_pod",
            ApiException(status=500, reason="InternalError"),
        )

        with pytest.raises(ApiException) as exc_info:
            await k8s_service.get_pod_status("abc-def-123")

        assert exc_info.value.status == 500

    @pytest.mark.asyncio
    async def test_get_pod_status_without_k8s(self, settings):
        """Test get_pod_status returns None when K8s not available."""
        service = K8sService(settings)
        service._initialized = True
        service._core_api = None

        status = await service.get_pod_status("abc-def-123")
        assert status is None


class TestListWrapperPods:
    """Tests for list_wrapper_pods."""

    @pytest.mark.asyncio
    async def test_list_wrapper_pods_empty(self, k8s_service, fake_k8s):
        """Test listing pods when none exist."""
        pods = await k8s_service.list_wrapper_pods()
        assert pods == []

    @pytest.mark.asyncio
    async def test_list_wrapper_pods_with_pods(self, k8s_service, fake_k8s):
        """Test listing pods returns wrapper pods."""
        # Create multiple pods
        for i in range(3):
            pod_spec = k8s_service._build_wrapper_pod_spec(
                instance_id=i,
                url_slug=f"slug-{i}",
                wrapper_type=WrapperType.RYUGRAPH,
                snapshot_id=i,
                mapping_id=i,
                mapping_version=1,
                owner_username="alice",
                owner_email="alice@example.com",
                gcs_path="gs://test",
            )
            fake_k8s.create_namespaced_pod("test-namespace", pod_spec)

        pods = await k8s_service.list_wrapper_pods()

        # FakeK8sClient returns all pods (doesn't filter by label selector)
        # In real implementation, would filter by app=ryugraph-wrapper
        assert len(pods) >= 3

    @pytest.mark.asyncio
    async def test_list_wrapper_pods_api_error(self, k8s_service, fake_k8s):
        """Test list_wrapper_pods returns empty list on API error."""
        fake_k8s.set_error_on_next_call(
            "list_namespaced_pod",
            ApiException(status=500, reason="InternalError"),
        )

        # Should not raise, returns empty list
        pods = await k8s_service.list_wrapper_pods()
        assert pods == []

    @pytest.mark.asyncio
    async def test_list_wrapper_pods_without_k8s(self, settings):
        """Test list_wrapper_pods returns empty list when K8s not available."""
        service = K8sService(settings)
        service._initialized = True
        service._core_api = None

        pods = await service.list_wrapper_pods()
        assert pods == []


class TestDeleteWrapperPodByName:
    """Tests for delete_wrapper_pod_by_name."""

    @pytest.mark.asyncio
    async def test_delete_wrapper_pod_by_name_success(self, k8s_service, fake_k8s):
        """Test deletion by pod name."""
        # Create pod
        pod_spec = k8s_service._build_wrapper_pod_spec(
            instance_id=123,
            url_slug="abc-def-123",
            wrapper_type=WrapperType.RYUGRAPH,
            snapshot_id=456,
            mapping_id=789,
            mapping_version=2,
            owner_username="alice",
            owner_email="alice@example.com",
            gcs_path="gs://bucket/path",
        )
        fake_k8s.create_namespaced_pod("test-namespace", pod_spec)

        deleted = await k8s_service.delete_wrapper_pod_by_name("wrapper-abc-def-123")

        assert deleted is True
        assert "wrapper-abc-def-123" not in fake_k8s.pods

    @pytest.mark.asyncio
    async def test_delete_wrapper_pod_by_name_not_found(self, k8s_service, fake_k8s):
        """Test deletion by name returns False when not found."""
        deleted = await k8s_service.delete_wrapper_pod_by_name("nonexistent")
        assert deleted is False

    @pytest.mark.asyncio
    async def test_delete_wrapper_pod_by_name_custom_grace_period(self, k8s_service, fake_k8s):
        """Test deletion uses custom grace period."""
        pod_spec = k8s_service._build_wrapper_pod_spec(
            instance_id=123,
            url_slug="abc-def-123",
            wrapper_type=WrapperType.RYUGRAPH,
            snapshot_id=456,
            mapping_id=789,
            mapping_version=2,
            owner_username="alice",
            owner_email="alice@example.com",
            gcs_path="gs://bucket/path",
        )
        fake_k8s.create_namespaced_pod("test-namespace", pod_spec)

        deleted = await k8s_service.delete_wrapper_pod_by_name(
            "wrapper-abc-def-123",
            grace_period_seconds=0,
        )

        assert deleted is True

    @pytest.mark.asyncio
    async def test_delete_wrapper_pod_by_name_error(self, k8s_service, fake_k8s):
        """Test deletion by name raises on non-404 errors."""
        fake_k8s.set_error_on_next_call(
            "delete_namespaced_pod",
            ApiException(status=500, reason="InternalError"),
        )

        with pytest.raises(ApiException) as exc_info:
            await k8s_service.delete_wrapper_pod_by_name("wrapper-abc-def-123")

        assert exc_info.value.status == 500

    @pytest.mark.asyncio
    async def test_delete_wrapper_pod_by_name_without_k8s(self, settings):
        """Test deletion by name returns False when K8s not available."""
        service = K8sService(settings)
        service._initialized = True
        service._core_api = None

        deleted = await service.delete_wrapper_pod_by_name("wrapper-abc-def-123")
        assert deleted is False


class TestGetPodStatusByName:
    """Tests for get_pod_status_by_name."""

    @pytest.mark.asyncio
    async def test_get_pod_status_by_name_success(self, k8s_service, fake_k8s):
        """Test getting detailed pod status by name."""
        # Create pod with real V1Pod object
        from datetime import UTC, datetime

        pod = V1Pod(
            metadata=V1ObjectMeta(
                name="wrapper-abc-def-123",
                creation_timestamp=datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
            ),
            status=V1PodStatus(phase="Running"),
        )
        fake_k8s.pods["wrapper-abc-def-123"] = pod

        # Add fake read_namespaced_pod_status method
        def read_pod_status(name, namespace):
            if name not in fake_k8s.pods:
                raise ApiException(status=404, reason="NotFound")
            return fake_k8s.pods[name]

        fake_k8s.read_namespaced_pod_status = read_pod_status

        status = await k8s_service.get_pod_status_by_name("wrapper-abc-def-123")

        assert status["phase"] == "Running"
        assert "ready" in status
        assert "containers" in status
        assert status["created_at"] == "2024-01-01T12:00:00+00:00"

    @pytest.mark.asyncio
    async def test_get_pod_status_by_name_not_found(self, k8s_service, fake_k8s):
        """Test get_pod_status_by_name returns NotFound phase when not found."""
        # Add fake read_namespaced_pod_status method
        def read_pod_status(name, namespace):
            raise ApiException(status=404, reason="NotFound")

        fake_k8s.read_namespaced_pod_status = read_pod_status

        status = await k8s_service.get_pod_status_by_name("nonexistent")

        assert status == {"phase": "NotFound"}

    @pytest.mark.asyncio
    async def test_get_pod_status_by_name_api_error(self, k8s_service, fake_k8s):
        """Test get_pod_status_by_name raises on non-404 errors."""
        # Add fake read_namespaced_pod_status method
        def read_pod_status(name, namespace):
            raise ApiException(status=500, reason="InternalError")

        fake_k8s.read_namespaced_pod_status = read_pod_status

        with pytest.raises(ApiException) as exc_info:
            await k8s_service.get_pod_status_by_name("wrapper-abc-def-123")

        assert exc_info.value.status == 500

    @pytest.mark.asyncio
    async def test_get_pod_status_by_name_without_k8s(self, settings):
        """Test get_pod_status_by_name returns None when K8s not available."""
        service = K8sService(settings)
        service._initialized = True
        service._core_api = None

        status = await service.get_pod_status_by_name("wrapper-abc-def-123")
        assert status is None
