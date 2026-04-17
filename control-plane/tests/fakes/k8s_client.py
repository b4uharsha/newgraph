"""Fake Kubernetes client for testing.

Provides lightweight in-memory implementation of K8s API for fast, isolated unit tests.
Follows Google's testing best practices: prefer fakes over mocks.
"""

from typing import Any

from kubernetes.client import (
    ApiException,
    V1ObjectMeta,
    V1Pod,
    V1PodStatus,
    V1Service,
    V1Status,
)


class FakeK8sClient:
    """In-memory Kubernetes API for testing.

    Simulates pod/service lifecycle without requiring a real cluster.
    Much faster and more maintainable than heavy mocking.

    Example:
        fake_k8s = FakeK8sClient()
        service = K8sService(settings)
        service._core_api = fake_k8s

        pod_name = service.create_pod(...)
        assert pod_name in fake_k8s.pods
    """

    def __init__(self):
        """Initialize empty cluster state."""
        self.pods: dict[str, V1Pod] = {}
        self.services: dict[str, V1Service] = {}

        # Track API calls for verification
        self.call_log: list[tuple[str, dict[str, Any]]] = []

        # Error injection for testing error handling
        self._errors: dict[str, ApiException] = {}

    # -------------------------------------------------------------------------
    # Core V1 API (Pods, Services)
    # -------------------------------------------------------------------------

    def create_namespaced_pod(
        self,
        namespace: str,
        body: V1Pod | dict,
        **kwargs,
    ) -> V1Pod:
        """Create a pod in the specified namespace.

        Args:
            namespace: Kubernetes namespace
            body: Pod specification (V1Pod object or dict)

        Returns:
            Created pod object

        Raises:
            ApiException: 409 if pod already exists
        """
        self._check_injected_error("create_namespaced_pod")

        # Support both V1Pod objects and dicts
        if isinstance(body, dict):
            name = body["metadata"]["name"]
            # Convert dict to V1Pod object
            body = V1Pod(
                metadata=V1ObjectMeta(
                    name=name,
                    labels=body["metadata"].get("labels", {}),
                ),
                spec=body.get("spec", {}),
            )
        else:
            name = body.metadata.name

        self.call_log.append(("create_namespaced_pod", {"name": name, "namespace": namespace}))

        if name in self.pods:
            raise ApiException(status=409, reason="AlreadyExists")

        # Set status to Pending (mimics real K8s behavior)
        body.status = V1PodStatus(phase="Pending")
        self.pods[name] = body

        return body

    def delete_namespaced_pod(
        self,
        name: str,
        namespace: str,
        **kwargs,
    ) -> V1Status:
        """Delete a pod from the specified namespace.

        Args:
            name: Pod name
            namespace: Kubernetes namespace

        Returns:
            Status object

        Raises:
            ApiException: 404 if pod not found
        """
        self._check_injected_error("delete_namespaced_pod")

        self.call_log.append(("delete_namespaced_pod", {"name": name, "namespace": namespace}))

        if name not in self.pods:
            raise ApiException(status=404, reason="NotFound")

        del self.pods[name]
        return V1Status(status="Success")

    def read_namespaced_pod(
        self,
        name: str,
        namespace: str,
        **kwargs,
    ) -> V1Pod:
        """Read a pod from the specified namespace.

        Args:
            name: Pod name
            namespace: Kubernetes namespace

        Returns:
            Pod object

        Raises:
            ApiException: 404 if pod not found
        """
        self._check_injected_error("read_namespaced_pod")

        if name not in self.pods:
            raise ApiException(status=404, reason="NotFound")

        return self.pods[name]

    def read_namespaced_pod_status(
        self,
        name: str,
        namespace: str,
        **kwargs,
    ) -> V1Pod:
        """Read pod status from the specified namespace.

        Args:
            name: Pod name
            namespace: Kubernetes namespace

        Returns:
            Pod object with status

        Raises:
            ApiException: 404 if pod not found
        """
        self._check_injected_error("read_namespaced_pod_status")

        if name not in self.pods:
            raise ApiException(status=404, reason="NotFound")

        return self.pods[name]

    def list_namespaced_pod(
        self,
        namespace: str,
        label_selector: str | None = None,
        **kwargs,
    ) -> Any:
        """List pods in the specified namespace.

        Args:
            namespace: Kubernetes namespace
            label_selector: Label selector (currently ignored in fake)

        Returns:
            Pod list object with items attribute
        """
        self._check_injected_error("list_namespaced_pod")

        self.call_log.append(("list_namespaced_pod", {"namespace": namespace}))

        # Create a simple object with items attribute
        class PodList:
            def __init__(self, items):
                self.items = items

        return PodList(list(self.pods.values()))

    def create_namespaced_service(
        self,
        namespace: str,
        body: V1Service | dict,
        **kwargs,
    ) -> V1Service:
        """Create a service in the specified namespace.

        Args:
            namespace: Kubernetes namespace
            body: Service specification (V1Service object or dict)

        Returns:
            Created service object

        Raises:
            ApiException: 409 if service already exists
        """
        self._check_injected_error("create_namespaced_service")

        # Support both V1Service objects and dicts
        if isinstance(body, dict):
            name = body["metadata"]["name"]
            # Convert dict to V1Service object
            body = V1Service(
                metadata=V1ObjectMeta(
                    name=name,
                    labels=body["metadata"].get("labels", {}),
                ),
                spec=body.get("spec", {}),
            )
        else:
            name = body.metadata.name

        self.call_log.append(("create_namespaced_service", {"name": name, "namespace": namespace}))

        if name in self.services:
            raise ApiException(status=409, reason="AlreadyExists")

        self.services[name] = body
        return body

    def delete_namespaced_service(
        self,
        name: str,
        namespace: str,
        **kwargs,
    ) -> V1Status:
        """Delete a service from the specified namespace.

        Args:
            name: Service name
            namespace: Kubernetes namespace

        Returns:
            Status object

        Raises:
            ApiException: 404 if service not found
        """
        self._check_injected_error("delete_namespaced_service")

        self.call_log.append(("delete_namespaced_service", {"name": name, "namespace": namespace}))

        if name not in self.services:
            raise ApiException(status=404, reason="NotFound")

        del self.services[name]
        return V1Status(status="Success")

    # -------------------------------------------------------------------------
    # Test Utilities
    # -------------------------------------------------------------------------

    def set_error_on_next_call(self, method: str, error: ApiException):
        """Inject an error to be raised on next call to specified method.

        Useful for testing error handling paths.

        Args:
            method: Method name (e.g., "create_namespaced_pod")
            error: ApiException to raise

        Example:
            fake_k8s.set_error_on_next_call(
                "create_namespaced_pod",
                ApiException(status=500, reason="InternalError")
            )
            # Next create_namespaced_pod() call will raise the error
        """
        self._errors[method] = error

    def _check_injected_error(self, method: str):
        """Check if an error should be raised for this method call."""
        if method in self._errors:
            error = self._errors.pop(method)
            raise error

    def reset(self):
        """Reset all state (useful between tests)."""
        self.pods.clear()
        self.services.clear()
        self.call_log.clear()
        self._errors.clear()

    def set_pod_status(self, name: str, phase: str):
        """Update pod phase for testing lifecycle.

        Args:
            name: Pod name
            phase: New phase (Pending, Running, Succeeded, Failed)
        """
        if name in self.pods:
            self.pods[name].status = V1PodStatus(phase=phase)

    def get_call_count(self, method: str) -> int:
        """Get number of times a method was called.

        Args:
            method: Method name

        Returns:
            Call count
        """
        return sum(1 for call_method, _ in self.call_log if call_method == method)
