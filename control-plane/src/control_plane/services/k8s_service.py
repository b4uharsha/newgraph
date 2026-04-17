"""Kubernetes service for managing wrapper pods.

Manages the lifecycle of Ryugraph wrapper pods in Kubernetes, including:
- Pod creation with proper resource limits and environment configuration
- Service creation for network access
- Graceful pod deletion with cleanup of associated resources

External access is handled by wrapper-proxy (ADR-101), not per-instance Ingress.

This module follows the stateless pattern where all state is stored in
the database and K8s resources are created/deleted based on instance state.
"""

import asyncio
from typing import Any

import structlog
from graph_olap_schemas import WrapperType
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException

from control_plane.config import Settings
from control_plane.services.wrapper_factory import WrapperFactory

logger = structlog.get_logger(__name__)


class K8sError(Exception):
    """Exception raised for Kubernetes operation failures."""

    pass


class K8sService:
    """Service for managing Kubernetes resources for instances."""

    def __init__(self, settings: Settings):
        """Initialize K8s client.

        Args:
            settings: Application settings
        """
        self._settings = settings
        self._namespace = settings.k8s_namespace
        self._wrapper_image = settings.wrapper_image
        self._external_base_url = settings.wrapper_external_base_url

        # Parse wrapper_image into name and tag (e.g., "ryugraph-wrapper:sha-53f3800")
        # Support both ryugraph and falkordb images via environment variables
        ryugraph_image, ryugraph_tag = self._parse_image_spec(settings.wrapper_image)
        # FalkorDB wrapper uses its own image setting for independent versioning
        falkordb_image, falkordb_tag = self._parse_image_spec(settings.falkordb_wrapper_image)

        self._wrapper_factory = WrapperFactory(
            ryugraph_image=ryugraph_image,
            ryugraph_tag=ryugraph_tag,
            falkordb_image=falkordb_image,
            falkordb_tag=falkordb_tag,
            settings=settings,
        )
        self._initialized = False
        self._core_api: client.CoreV1Api | None = None
        self._apps_api: client.AppsV1Api | None = None

    @property
    def namespace(self) -> str:
        """Get the Kubernetes namespace."""
        return self._namespace

    @staticmethod
    def _parse_image_spec(image_spec: str) -> tuple[str, str]:
        """Parse image specification into name and tag.

        Args:
            image_spec: Image spec like "ryugraph-wrapper:sha-53f3800" or "gcr.io/project/image:v1"

        Returns:
            Tuple of (image_name, image_tag)

        Raises:
            ValueError: If image spec doesn't contain a tag (no "latest" allowed)
        """
        if ":" not in image_spec:
            raise ValueError(
                f"Image spec '{image_spec}' must include explicit tag (no implicit 'latest' allowed)"
            )
        # Split on last colon to handle registry URLs like gcr.io/project/image:tag
        last_colon = image_spec.rfind(":")
        image_name = image_spec[:last_colon]
        image_tag = image_spec[last_colon + 1:]

        if image_tag == "latest":
            raise ValueError(
                f"Image tag 'latest' is not allowed. Use explicit version tags for reproducibility."
            )

        return image_name, image_tag

    @staticmethod
    def _sanitize_label_value(value: str) -> str:
        """Sanitize string for K8s label (max 63 chars, alphanumeric + -_.).

        K8s label values must:
        - Be max 63 characters
        - Start and end with alphanumeric
        - Contain only alphanumeric, -, _, .

        Args:
            value: The value to sanitize (e.g., email address)

        Returns:
            Sanitized value suitable for K8s label
        """
        import re

        # Replace common email characters
        sanitized = value.replace("@", "-at-").replace(".", "-")
        # Remove any remaining invalid characters
        sanitized = re.sub(r"[^a-zA-Z0-9\-_.]", "-", sanitized)
        # Collapse multiple dashes
        sanitized = re.sub(r"-+", "-", sanitized)
        # Truncate to 63 chars
        sanitized = sanitized[:63]
        # Strip leading/trailing non-alphanumeric
        sanitized = sanitized.strip("-_.")

        return sanitized

    def _ensure_initialized(self) -> None:
        """Initialize K8s client if not already done."""
        if self._initialized:
            return

        try:
            if self._settings.k8s_in_cluster:
                config.load_incluster_config()
                logger.info("k8s_config_loaded", config_type="in-cluster")
            else:
                config.load_kube_config()
                logger.info("k8s_config_loaded", config_type="kubeconfig")

            self._core_api = client.CoreV1Api()
            self._apps_api = client.AppsV1Api()
            self._initialized = True
        except Exception as e:
            logger.warning("k8s_client_init_failed", error=str(e))
            # Don't fail - allow running without K8s (for local dev/testing)
            self._initialized = True

    def _build_wrapper_pod_spec(
        self,
        instance_id: int,
        url_slug: str,
        wrapper_type: WrapperType,
        snapshot_id: int,
        mapping_id: int,
        mapping_version: int,
        owner_username: str,
        owner_email: str,
        gcs_path: str,
        resource_overrides: dict[str, str] | None = None,
        instance_name: str = "",
        mapping_name: str = "",
    ) -> dict[str, Any]:
        """Build pod spec for a wrapper instance.

        Args:
            instance_id: Instance ID (for labels/env vars)
            url_slug: UUID slug for K8s resource naming
            wrapper_type: Wrapper type (ryugraph, falkordb)
            snapshot_id: Snapshot ID
            mapping_id: Mapping ID
            mapping_version: Mapping version
            owner_username: Owner username
            owner_email: Owner email (for owner-email label, enables cleanup by email)
            gcs_path: GCS path for snapshot data
            resource_overrides: Optional resource overrides from dynamic sizing
                               (keys: memory_request, memory_limit, cpu_request, cpu_limit, disk_size)
            instance_name: Human-readable instance name (for GKE console visibility)
            mapping_name: Human-readable mapping name (for GKE console visibility)

        Returns:
            Pod spec dictionary
        """
        pod_name = f"wrapper-{url_slug}"

        # Get wrapper-specific configuration from factory
        wrapper_config = self._wrapper_factory.get_wrapper_config(wrapper_type)

        # Determine instance URL: prefer external ingress URL (for LOCAL mode),
        # fall back to cluster DNS (for IN_CLUSTER mode)
        instance_url = (
            self.get_external_instance_url(url_slug)
            if self._external_base_url
            else f"http://wrapper-{url_slug}:{wrapper_config.container_port}"
        )

        return {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": pod_name,
                "labels": {
                    "app": f"{wrapper_type.value}-wrapper",
                    "wrapper-type": wrapper_type.value,
                    "graph-id": str(instance_id),
                    "instance-id": str(instance_id),
                    "url-slug": url_slug,
                    "snapshot-id": str(snapshot_id),
                    "mapping-id": str(mapping_id),
                    "owner-email": self._sanitize_label_value(owner_email),
                    "owner": self._sanitize_label_value(owner_username),
                    **({"graph-name": self._sanitize_label_value(instance_name)} if instance_name else {}),
                    **({"mapping-name": self._sanitize_label_value(mapping_name)} if mapping_name else {}),
                },
            },
            "spec": {
                "restartPolicy": "Never",
                # Use dedicated service account for GCS access via Workload Identity
                **({"serviceAccountName": self._settings.wrapper_service_account}
                   if self._settings.wrapper_service_account else {}),
                "containers": [
                    {
                        "name": "wrapper",
                        "image": f"{wrapper_config.image_name}:{wrapper_config.image_tag}",
                        "imagePullPolicy": self._settings.wrapper_image_pull_policy,
                        "ports": [{"containerPort": wrapper_config.container_port, "name": "http"}],
                        "env": [
                            {"name": "WRAPPER_INSTANCE_ID", "value": str(instance_id)},
                            {"name": "WRAPPER_URL_SLUG", "value": url_slug},
                            {"name": "WRAPPER_SNAPSHOT_ID", "value": str(snapshot_id)},
                            {"name": "WRAPPER_MAPPING_ID", "value": str(mapping_id)},
                            {"name": "WRAPPER_MAPPING_VERSION", "value": str(mapping_version)},
                            {"name": "WRAPPER_OWNER_ID", "value": owner_username},
                            {"name": "WRAPPER_GCS_BASE_PATH", "value": gcs_path},
                            {"name": "WRAPPER_CONTROL_PLANE_URL", "value": "http://control-plane-svc.graph-olap-platform.svc.cluster.local:8080"},
                            {"name": "WRAPPER_INSTANCE_URL", "value": instance_url},
                            {"name": "FALKORDB_DATABASE_PATH" if wrapper_type == WrapperType.FALKORDB else "RYUGRAPH_DATABASE_PATH", "value": "/data/db"},
                            {"name": "LOG_LEVEL", "value": "INFO"},
                            {"name": "LOG_FORMAT", "value": "json"},
                            {"name": "ENVIRONMENT", "value": "dev"},
                            # Internal API key removed (ADR-104/105) -- network policy protects internal endpoints
                        ]
                        # Add wrapper-specific environment variables
                        + [{"name": k, "value": v} for k, v in wrapper_config.environment_variables.items()]
                        # Add storage emulator host if configured (for E2E tests)
                        + (
                            [{"name": "STORAGE_EMULATOR_HOST", "value": self._settings.storage_emulator_host}]
                            if self._settings.storage_emulator_host
                            else []
                        )
                        # Add GCP credentials if secret is configured (for local dev)
                        + (
                            [{"name": "GOOGLE_APPLICATION_CREDENTIALS", "value": "/var/secrets/google/key.json"}]
                            if self._settings.wrapper_gcp_secret
                            else []
                        ),
                        "volumeMounts": [
                            {"name": "data", "mountPath": "/data"},
                        ]
                        # Mount GCP credentials secret if configured (for local dev)
                        + (
                            [{"name": "gcp-credentials", "mountPath": "/var/secrets/google", "readOnly": True}]
                            if self._settings.wrapper_gcp_secret
                            else []
                        ),
                        "resources": {
                            "requests": (
                                {
                                    "memory": resource_overrides["memory_request"],
                                    "cpu": resource_overrides["cpu_request"],
                                }
                                if resource_overrides
                                else wrapper_config.resource_requests
                            ),
                            "limits": (
                                {
                                    "memory": resource_overrides["memory_limit"],
                                    "cpu": resource_overrides["cpu_limit"],
                                }
                                if resource_overrides
                                else wrapper_config.resource_limits
                            ),
                        },
                        # Startup probe: handles long initial startup (data loading takes 60-150s)
                        # Checks /health endpoint which returns 200 once FastAPI is running
                        # Allows up to 150 seconds for wrapper to complete data loading
                        "startupProbe": {
                            "httpGet": {"path": wrapper_config.health_check_path, "port": wrapper_config.container_port},
                            "initialDelaySeconds": 5,  # Start checking quickly
                            "periodSeconds": 5,  # Check every 5 seconds
                            "timeoutSeconds": 3,
                            "failureThreshold": 30,  # 30 × 5s = 150s max startup time
                        },
                        # Readiness probe: aggressive checks after startup completes
                        # Checks /ready endpoint which only returns 200 when data is loaded
                        "readinessProbe": {
                            "httpGet": {"path": "/ready", "port": wrapper_config.container_port},
                            "periodSeconds": 2,  # Check every 2s (not 5s) for faster detection
                            "timeoutSeconds": 1,
                            "failureThreshold": 3,  # Fail fast - mark unready after 6s
                        },
                        # Liveness probe: detect crashed wrappers
                        "livenessProbe": {
                            "httpGet": {"path": wrapper_config.health_check_path, "port": wrapper_config.container_port},
                            "initialDelaySeconds": 10,  # Allow time for initial startup
                            "periodSeconds": 10,
                            "timeoutSeconds": 5,
                            "failureThreshold": 3,  # Kill pod after 30s of failed health checks
                        },
                    }
                ],
                "volumes": [
                    {"name": "data", "emptyDir": {}},
                ]
                # Add GCP credentials secret volume if configured (for local dev)
                + (
                    [{"name": "gcp-credentials", "secret": {"secretName": self._settings.wrapper_gcp_secret}}]
                    if self._settings.wrapper_gcp_secret
                    else []
                ),
            },
        }

    def get_external_instance_url(self, url_slug: str) -> str:
        """Get URL for accessing a wrapper instance.

        Prefers external URL (via wrapper-proxy). Falls back to
        in-cluster DNS when no external URL is configured (ADR-101 C13).

        Args:
            url_slug: UUID slug for URL routing

        Returns:
            URL for accessing the wrapper instance
        """
        if not self._external_base_url:
            return f"http://wrapper-{url_slug}.{self._namespace}.svc.cluster.local:8000"
        return f"{self._external_base_url.rstrip('/')}/wrapper/{url_slug}"

    def _build_wrapper_service_spec(
        self,
        instance_id: int,
        url_slug: str,
        wrapper_type: WrapperType,
        owner_username: str = "",
        instance_name: str = "",
        mapping_name: str = "",
    ) -> dict[str, Any]:
        """Build service spec for a wrapper instance.

        Args:
            instance_id: Instance ID (for labels)
            url_slug: UUID slug for K8s resource naming
            wrapper_type: Type of wrapper (RYUGRAPH or FALKORDB)
            owner_username: Owner username (for GKE console visibility)
            instance_name: Human-readable instance name (for GKE console visibility)
            mapping_name: Human-readable mapping name (for GKE console visibility)

        Returns:
            Service spec dictionary
        """
        service_name = f"wrapper-{url_slug}"
        app_label = f"{wrapper_type.value}-wrapper"

        return {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "name": service_name,
                "labels": {
                    "app": app_label,
                    "instance-id": str(instance_id),
                    "url-slug": url_slug,
                    "wrapper-type": wrapper_type.value,
                    **({"owner": self._sanitize_label_value(owner_username)} if owner_username else {}),
                    **({"graph-name": self._sanitize_label_value(instance_name)} if instance_name else {}),
                    **({"mapping-name": self._sanitize_label_value(mapping_name)} if mapping_name else {}),
                },
            },
            "spec": {
                "selector": {
                    "app": app_label,
                    "url-slug": url_slug,
                },
                "ports": [{"port": 8000, "targetPort": 8000, "name": "http"}],
                "type": "ClusterIP",
            },
        }

    async def create_wrapper_pod(
        self,
        instance_id: int,
        url_slug: str,
        wrapper_type: WrapperType,
        snapshot_id: int,
        mapping_id: int,
        mapping_version: int,
        owner_username: str,
        owner_email: str,
        gcs_path: str,
        resource_overrides: dict[str, str] | None = None,
        instance_name: str = "",
        mapping_name: str = "",
    ) -> tuple[str | None, str | None]:
        """Create a wrapper pod and service for an instance.

        Args:
            instance_id: Instance ID (for labels/env vars)
            url_slug: UUID slug for K8s resource naming and external URLs
            wrapper_type: Wrapper type (ryugraph, falkordb)
            snapshot_id: Snapshot ID
            mapping_id: Mapping ID
            mapping_version: Mapping version
            owner_username: Owner username
            owner_email: Owner email (for owner-email label, enables cleanup by email)
            gcs_path: GCS path for snapshot data
            resource_overrides: Optional resource overrides from dynamic sizing
                               (keys: memory_request, memory_limit, cpu_request, cpu_limit, disk_size)
            instance_name: Human-readable instance name (for GKE console visibility)
            mapping_name: Human-readable mapping name (for GKE console visibility)

        Returns:
            Tuple of (pod_name, external_url) if created, (None, None) if K8s not available
        """
        self._ensure_initialized()

        if self._core_api is None:
            logger.warning("k8s_pod_creation_skipped", reason="k8s_not_available")
            return None, None

        pod_spec = self._build_wrapper_pod_spec(
            instance_id=instance_id,
            url_slug=url_slug,
            wrapper_type=wrapper_type,
            snapshot_id=snapshot_id,
            mapping_id=mapping_id,
            mapping_version=mapping_version,
            owner_username=owner_username,
            owner_email=owner_email,
            gcs_path=gcs_path,
            resource_overrides=resource_overrides,
            instance_name=instance_name,
            mapping_name=mapping_name,
        )

        pod_name = pod_spec["metadata"]["name"]
        service_name = f"wrapper-{url_slug}"

        # Create Service first (so DNS is ready when pod starts)
        try:
            service_spec = self._build_wrapper_service_spec(
                instance_id, url_slug, wrapper_type,
                owner_username=owner_username,
                instance_name=instance_name,
                mapping_name=mapping_name,
            )
            self._core_api.create_namespaced_service(
                namespace=self._namespace,
                body=service_spec,
            )
            logger.info("k8s_service_created", service_name=service_name)
        except ApiException as e:
            if e.status == 409:
                logger.warning("k8s_service_exists", service_name=service_name)
            else:
                logger.error("k8s_service_creation_failed", service_name=service_name, error=str(e))
                # Continue anyway - pod might still work via IP

        # External URL via wrapper-proxy (ADR-101) — no per-instance Ingress needed
        external_url = self.get_external_instance_url(url_slug)

        # Create Pod
        try:
            self._core_api.create_namespaced_pod(
                namespace=self._namespace,
                body=pod_spec,
            )
            logger.info("k8s_pod_created", pod_name=pod_name, namespace=self._namespace)
            return pod_name, external_url
        except ApiException as e:
            if e.status == 409:
                # Pod already exists
                logger.warning("k8s_pod_exists", pod_name=pod_name)
                return pod_name, external_url
            logger.error("k8s_pod_creation_failed", pod_name=pod_name, error=str(e))
            raise

    async def delete_wrapper_pod(self, url_slug: str) -> bool:
        """Delete a wrapper pod and service for an instance.

        Args:
            url_slug: UUID slug used for K8s resource naming

        Returns:
            True if deleted, False if not found or K8s not available
        """
        self._ensure_initialized()

        if self._core_api is None:
            logger.warning("k8s_pod_deletion_skipped", reason="k8s_not_available")
            return False

        pod_name = f"wrapper-{url_slug}"
        service_name = f"wrapper-{url_slug}"
        deleted = False

        # Delete Pod
        try:
            self._core_api.delete_namespaced_pod(
                name=pod_name,
                namespace=self._namespace,
                body=client.V1DeleteOptions(grace_period_seconds=30),
            )
            logger.info("k8s_pod_deleted", pod_name=pod_name)
            deleted = True
        except ApiException as e:
            if e.status == 404:
                logger.warning("k8s_pod_not_found", pod_name=pod_name)
            else:
                logger.error("k8s_pod_deletion_failed", pod_name=pod_name, error=str(e))

        # Delete Service
        try:
            self._core_api.delete_namespaced_service(
                name=service_name,
                namespace=self._namespace,
            )
            logger.info("k8s_service_deleted", service_name=service_name)
            deleted = True
        except ApiException as e:
            if e.status == 404:
                logger.warning("k8s_service_not_found", service_name=service_name)
            else:
                logger.error("k8s_service_deletion_failed", service_name=service_name, error=str(e))

        return deleted

    async def get_pod_status(self, url_slug: str) -> dict[str, Any] | None:
        """Get status of a wrapper pod.

        Args:
            url_slug: UUID slug used for K8s resource naming

        Returns:
            Pod status dict or None if not found
        """
        self._ensure_initialized()

        if self._core_api is None:
            return None

        pod_name = f"wrapper-{url_slug}"

        try:
            pod = self._core_api.read_namespaced_pod(
                name=pod_name,
                namespace=self._namespace,
            )
            return {
                "name": pod.metadata.name,
                "phase": pod.status.phase,
                "pod_ip": pod.status.pod_ip,
                "conditions": [
                    {"type": c.type, "status": c.status}
                    for c in (pod.status.conditions or [])
                ],
            }
        except ApiException as e:
            if e.status == 404:
                return None
            raise

    async def list_wrapper_pods(self) -> list[Any]:
        """List all wrapper pods in the namespace.

        Returns pods with label: wrapper-type (any value).
        This matches all wrapper types (ryugraph, falkordb, etc).

        Returns:
            List of V1Pod objects
        """
        self._ensure_initialized()

        if self._core_api is None:
            logger.warning("k8s_list_pods_skipped", reason="k8s_not_available")
            return []

        try:
            pod_list = self._core_api.list_namespaced_pod(
                namespace=self._namespace,
                label_selector="wrapper-type",  # All wrapper pods have this label
            )
            return pod_list.items
        except ApiException as e:
            logger.error("k8s_list_pods_failed", namespace=self._namespace, error=str(e))
            return []

    async def list_pods_by_owner_email(self, owner_email: str) -> list[Any]:
        """List all wrapper pods owned by a specific email address.

        Uses the owner-email label to filter pods. The email is sanitized
        to match the label format.

        Args:
            owner_email: Owner email to filter by

        Returns:
            List of V1Pod objects owned by the email
        """
        self._ensure_initialized()

        if self._core_api is None:
            logger.warning("k8s_list_pods_by_email_skipped", reason="k8s_not_available")
            return []

        sanitized_email = self._sanitize_label_value(owner_email)

        try:
            pod_list = self._core_api.list_namespaced_pod(
                namespace=self._namespace,
                label_selector=f"owner-email={sanitized_email}",
            )
            logger.debug(
                "k8s_list_pods_by_email",
                owner_email=owner_email,
                sanitized=sanitized_email,
                count=len(pod_list.items),
            )
            return pod_list.items
        except ApiException as e:
            logger.error(
                "k8s_list_pods_by_email_failed",
                owner_email=owner_email,
                error=str(e),
            )
            return []

    async def delete_wrapper_pod_by_name(
        self,
        pod_name: str,
        grace_period_seconds: int = 30,
    ) -> bool:
        """Delete a wrapper pod by explicit pod name.

        This method is used by reconciliation when we have the exact pod name
        (not url_slug). It does NOT delete service/ingress since we might not
        know the url_slug.

        Args:
            pod_name: Exact pod name to delete
            grace_period_seconds: Grace period for termination

        Returns:
            True if deleted, False if not found
        """
        self._ensure_initialized()

        if self._core_api is None:
            logger.warning("k8s_pod_deletion_skipped", reason="k8s_not_available")
            return False

        try:
            self._core_api.delete_namespaced_pod(
                name=pod_name,
                namespace=self._namespace,
                body=client.V1DeleteOptions(grace_period_seconds=grace_period_seconds),
            )
            logger.info("k8s_pod_deleted_by_name", pod_name=pod_name)
            return True
        except ApiException as e:
            if e.status == 404:
                logger.warning("k8s_pod_not_found", pod_name=pod_name)
                return False
            logger.error("k8s_pod_deletion_failed", pod_name=pod_name, error=str(e))
            raise

    async def is_pod_ready(self, pod_name: str) -> bool:
        """Check if a pod is Ready according to Kubernetes.

        This is used to validate that a pod is actually reachable via Service/Ingress
        before reporting "running" status to clients. A pod must have Ready=True
        condition for Kubernetes to add it to Service endpoints.

        Args:
            pod_name: Name of the pod to check

        Returns:
            True if pod exists and has Ready=True condition.
            False if pod doesn't exist, not Ready, or K8s unavailable.
        """
        self._ensure_initialized()

        if self._core_api is None:
            # K8s not available - return True to avoid blocking
            # (graceful degradation: trust wrapper-reported status)
            logger.debug("is_pod_ready_skipped", pod_name=pod_name, reason="k8s_not_available")
            return True

        try:
            pod = self._core_api.read_namespaced_pod_status(
                name=pod_name,
                namespace=self._namespace,
            )

            # Check pod conditions for Ready=True
            ready = False
            if pod.status and pod.status.conditions:
                for condition in pod.status.conditions:
                    if condition.type == "Ready":
                        ready = condition.status == "True"
                        break

            logger.info(
                "is_pod_ready_checked",
                pod_name=pod_name,
                ready=ready,
                phase=pod.status.phase if pod.status else None,
            )
            return ready
        except ApiException as e:
            if e.status == 404:
                # Pod doesn't exist - not ready
                logger.info("is_pod_ready_not_found", pod_name=pod_name)
                return False
            logger.warning("k8s_pod_ready_check_failed", pod_name=pod_name, error=str(e))
            # On error, return True to avoid blocking (graceful degradation)
            return True

    async def get_pod_status_by_name(self, pod_name: str) -> dict[str, Any] | None:
        """Get detailed pod status by explicit pod name.

        Returns:
            {
                "phase": "Running" | "Pending" | "Failed" | "Succeeded" | "Unknown",
                "ready": bool,
                "containers": [{"name": str, "ready": bool, "restart_count": int}],
                "created_at": str (ISO 8601),
            }
            or None if not found
        """
        self._ensure_initialized()

        if self._core_api is None:
            return None

        try:
            pod = self._core_api.read_namespaced_pod_status(
                name=pod_name,
                namespace=self._namespace,
            )
            return {
                "phase": pod.status.phase,
                "ready": all(
                    cond.status == "True"
                    for cond in pod.status.conditions or []
                    if cond.type == "Ready"
                ),
                "containers": [
                    {
                        "name": c.name,
                        "ready": c.ready,
                        "restart_count": c.restart_count,
                    }
                    for c in pod.status.container_statuses or []
                ],
                "created_at": pod.metadata.creation_timestamp.isoformat() if pod.metadata.creation_timestamp else None,
            }
        except ApiException as e:
            if e.status == 404:
                return {"phase": "NotFound"}
            raise

    async def get_pod_logs(self, pod_name: str, tail_lines: int = 50) -> str:
        """Get the last N lines of logs from a pod.

        Returns log text, or an error description if logs cannot be fetched.
        Safe to call on terminated/failed pods — K8s retains logs until
        the pod object is deleted.
        """
        self._ensure_initialized()
        if self._core_api is None:
            return "(k8s not initialized)"
        try:
            return self._core_api.read_namespaced_pod_log(
                name=pod_name,
                namespace=self._namespace,
                tail_lines=tail_lines,
                previous=False,
            )
        except ApiException as e:
            if e.status == 404:
                return "(pod not found — already deleted)"
            return f"(failed to fetch logs: {e.reason})"
        except Exception as e:
            return f"(failed to fetch logs: {e})"

    async def get_pod_failure_info(self, pod_name: str) -> str:
        """Get a diagnostic summary for a failed or missing pod.

        Extracts container exit codes, termination reasons, and last log
        lines. Returns a human-readable string suitable for storing in
        the instance error_message field.
        """
        self._ensure_initialized()
        if self._core_api is None:
            return "Pod failure (k8s not initialized)"

        parts = []
        try:
            pod = self._core_api.read_namespaced_pod(
                name=pod_name, namespace=self._namespace,
            )
            parts.append(f"phase={pod.status.phase}")
            for cs in pod.status.container_statuses or []:
                terminated = cs.state.terminated if cs.state else None
                if terminated:
                    parts.append(
                        f"container={cs.name} exit_code={terminated.exit_code} "
                        f"reason={terminated.reason} message={terminated.message}"
                    )
                waiting = cs.state.waiting if cs.state else None
                if waiting:
                    parts.append(
                        f"container={cs.name} waiting reason={waiting.reason} "
                        f"message={waiting.message}"
                    )
        except ApiException as e:
            if e.status == 404:
                parts.append("pod not found (already deleted)")
            else:
                parts.append(f"failed to read pod: {e.reason}")
        except Exception as e:
            parts.append(f"failed to read pod: {e}")

        # Capture last log lines
        logs = await self.get_pod_logs(pod_name, tail_lines=20)
        if logs and logs.strip():
            parts.append(f"last_logs:\n{logs.strip()}")

        return "; ".join(parts) if parts else "Unknown pod failure"

    async def resize_pod_cpu(
        self,
        pod_name: str,
        cpu_request: str,
        cpu_limit: str,
    ) -> None:
        """Resize CPU allocation for a running pod using K8s in-place resize.

        Uses kubectl patch with --subresource=resize for K8s 1.27+ in-place resize.
        Falls back to pod recreation if in-place resize is not supported.

        Args:
            pod_name: Name of the pod to resize
            cpu_request: CPU request (e.g., "2")
            cpu_limit: CPU limit (e.g., "4")

        Raises:
            K8sError: If resize fails
        """
        import json
        import subprocess

        logger.info(
            "resizing_pod_cpu",
            pod_name=pod_name,
            cpu_request=cpu_request,
            cpu_limit=cpu_limit,
        )

        # Build the patch payload
        patch = {
            "spec": {
                "containers": [{
                    "name": "wrapper",
                    "resources": {
                        "requests": {"cpu": cpu_request},
                        "limits": {"cpu": cpu_limit},
                    }
                }]
            }
        }

        # Try in-place resize first (K8s 1.27+)
        try:
            cmd = [
                "kubectl", "patch", "pod", pod_name,
                "-n", self.namespace,
                "--subresource=resize",
                "--type=merge",
                "-p", json.dumps(patch),
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                logger.info("pod_cpu_resized", pod_name=pod_name)
                return

            # If --subresource=resize fails, log warning
            logger.warning(
                "in_place_resize_not_supported",
                pod_name=pod_name,
                stderr=result.stderr,
            )

        except subprocess.TimeoutExpired:
            logger.error("pod_resize_timeout", pod_name=pod_name)
            raise K8sError(f"Timeout resizing pod {pod_name}")
        except Exception as e:
            logger.error("pod_resize_failed", pod_name=pod_name, error=str(e))
            raise K8sError(f"Failed to resize pod {pod_name}: {e}")

    async def resize_pod_memory(
        self,
        pod_name: str,
        memory_request: str,
        memory_limit: str,
    ) -> None:
        """Resize memory allocation for a running pod using K8s in-place resize.

        Uses kubectl patch with --subresource=resize for K8s 1.27+ in-place resize.
        Memory increase works without restart; memory decrease requires RestartContainer
        policy (not supported - only increases allowed).

        Args:
            pod_name: Name of the pod to resize
            memory_request: Memory request (e.g., "4Gi")
            memory_limit: Memory limit (e.g., "4Gi") - should equal request for Guaranteed QoS

        Raises:
            K8sError: If resize fails
        """
        import json
        import subprocess

        logger.info(
            "resizing_pod_memory",
            pod_name=pod_name,
            memory_request=memory_request,
            memory_limit=memory_limit,
        )

        # Build the patch payload
        patch = {
            "spec": {
                "containers": [{
                    "name": "wrapper",
                    "resources": {
                        "requests": {"memory": memory_request},
                        "limits": {"memory": memory_limit},
                    }
                }]
            }
        }

        # Try in-place resize (K8s 1.27+)
        try:
            cmd = [
                "kubectl", "patch", "pod", pod_name,
                "-n", self.namespace,
                "--subresource=resize",
                "--type=merge",
                "-p", json.dumps(patch),
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                logger.info("pod_memory_resized", pod_name=pod_name)
                return

            # If --subresource=resize fails, log warning
            logger.warning(
                "in_place_memory_resize_not_supported",
                pod_name=pod_name,
                stderr=result.stderr,
            )

        except subprocess.TimeoutExpired:
            logger.error("pod_memory_resize_timeout", pod_name=pod_name)
            raise K8sError(f"Timeout resizing pod memory {pod_name}")
        except Exception as e:
            logger.error("pod_memory_resize_failed", pod_name=pod_name, error=str(e))
            raise K8sError(f"Failed to resize pod memory {pod_name}: {e}")

    async def get_pod_memory_usage(self, pod_name: str) -> dict:
        """Get current memory usage for a pod.

        Queries Kubernetes metrics API for container memory usage, falling back
        to pod resource status if metrics are unavailable.

        Args:
            pod_name: Name of the pod to query

        Returns:
            Dict with usage_bytes, limit_bytes, usage_percent, or empty dict if unavailable
        """
        import subprocess

        logger.debug("getting_pod_memory_usage", pod_name=pod_name)

        # Try metrics API first via kubectl top
        try:
            cmd = [
                "kubectl", "top", "pod", pod_name,
                "-n", self.namespace,
                "--containers",
                "--no-headers",
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0 and result.stdout.strip():
                # Parse output: POD_NAME CONTAINER CPU MEMORY
                # e.g., "my-pod wrapper 10m 512Mi"
                lines = result.stdout.strip().split("\n")
                for line in lines:
                    parts = line.split()
                    if len(parts) >= 4 and parts[1] == "wrapper":
                        memory_str = parts[3]  # e.g., "512Mi"
                        usage_bytes = self._parse_memory_string(memory_str)

                        # Get limit from pod spec
                        limit_bytes = await self._get_pod_memory_limit(pod_name)

                        usage_percent = 0.0
                        if limit_bytes and limit_bytes > 0:
                            usage_percent = (usage_bytes / limit_bytes) * 100

                        return {
                            "usage_bytes": usage_bytes,
                            "limit_bytes": limit_bytes,
                            "usage_percent": round(usage_percent, 2),
                        }

            logger.debug(
                "metrics_api_unavailable",
                pod_name=pod_name,
                stderr=result.stderr if result.returncode != 0 else None,
            )

        except subprocess.TimeoutExpired:
            logger.warning("pod_memory_metrics_timeout", pod_name=pod_name)
        except Exception as e:
            logger.warning("pod_memory_metrics_failed", pod_name=pod_name, error=str(e))

        # Fallback: return empty dict if metrics unavailable
        return {}

    def _parse_memory_string(self, memory_str: str) -> int:
        """Parse Kubernetes memory string to bytes.

        Args:
            memory_str: Memory string (e.g., "512Mi", "2Gi", "1024Ki")

        Returns:
            Memory in bytes
        """
        memory_str = memory_str.strip()
        if memory_str.endswith("Ki"):
            return int(memory_str[:-2]) * 1024
        elif memory_str.endswith("Mi"):
            return int(memory_str[:-2]) * 1024 * 1024
        elif memory_str.endswith("Gi"):
            return int(memory_str[:-2]) * 1024 * 1024 * 1024
        elif memory_str.endswith("Ti"):
            return int(memory_str[:-2]) * 1024 * 1024 * 1024 * 1024
        elif memory_str.endswith("k") or memory_str.endswith("K"):
            return int(memory_str[:-1]) * 1000
        elif memory_str.endswith("M"):
            return int(memory_str[:-1]) * 1000 * 1000
        elif memory_str.endswith("G"):
            return int(memory_str[:-1]) * 1000 * 1000 * 1000
        elif memory_str.endswith("T"):
            return int(memory_str[:-1]) * 1000 * 1000 * 1000 * 1000
        else:
            # Assume bytes
            return int(memory_str)

    async def _get_pod_memory_limit(self, pod_name: str) -> int | None:
        """Get memory limit from pod spec.

        Args:
            pod_name: Name of the pod

        Returns:
            Memory limit in bytes, or None if unavailable
        """
        try:
            pod = await asyncio.to_thread(
                self._core_api.read_namespaced_pod,
                name=pod_name,
                namespace=self.namespace,
            )

            for container in pod.spec.containers:
                if container.name == "wrapper":
                    if container.resources and container.resources.limits:
                        memory_limit = container.resources.limits.get("memory")
                        if memory_limit:
                            return self._parse_memory_string(memory_limit)

        except ApiException as e:
            logger.warning(
                "failed_to_get_pod_memory_limit",
                pod_name=pod_name,
                error=str(e),
            )

        return None


# Singleton instance
_k8s_service: K8sService | None = None


def get_k8s_service(settings: Settings | None = None) -> K8sService:
    """Get or create K8s service singleton.

    Args:
        settings: Optional settings (uses default if not provided)

    Returns:
        K8sService instance
    """
    global _k8s_service
    if _k8s_service is None:
        if settings is None:
            from control_plane.config import get_settings
            settings = get_settings()
        _k8s_service = K8sService(settings)
    return _k8s_service
