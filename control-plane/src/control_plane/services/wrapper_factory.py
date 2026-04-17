"""Wrapper factory service for creating wrapper-specific configurations.

This service acts as a factory for wrapper-specific configurations and
capabilities, enabling the control plane to support multiple graph database
backends (Ryugraph, FalkorDB, etc.) without coupling to specific implementations.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from graph_olap_schemas import WrapperCapabilities, WrapperType, get_wrapper_capabilities

if TYPE_CHECKING:
    from control_plane.config import Settings


@dataclass
class WrapperConfig:
    """Configuration for deploying a wrapper instance.

    Contains all the information needed by K8s service to create a pod
    for a specific wrapper type.
    """

    wrapper_type: WrapperType
    image_name: str
    image_tag: str
    container_port: int
    health_check_path: str
    resource_limits: dict[str, str]
    resource_requests: dict[str, str]
    environment_variables: dict[str, str]


class WrapperFactory:
    """Factory for creating wrapper-specific configurations and capabilities."""

    def __init__(
        self,
        ryugraph_image: str,
        ryugraph_tag: str,
        falkordb_image: str,
        falkordb_tag: str,
        settings: "Settings | None" = None,
    ):
        """Initialize factory with wrapper image configurations.

        Args:
            ryugraph_image: Ryugraph wrapper container image name
            ryugraph_tag: Ryugraph wrapper image tag
            falkordb_image: FalkorDB wrapper container image name
            falkordb_tag: FalkorDB wrapper image tag
            settings: Application settings for resource configuration
        """
        self._ryugraph_image = ryugraph_image
        self._ryugraph_tag = ryugraph_tag
        self._falkordb_image = falkordb_image
        self._falkordb_tag = falkordb_tag
        self._settings = settings

    def get_wrapper_config(self, wrapper_type: WrapperType) -> WrapperConfig:
        """Get deployment configuration for a wrapper type.

        Args:
            wrapper_type: The wrapper type (RYUGRAPH, FALKORDB)

        Returns:
            WrapperConfig with deployment settings

        Raises:
            ValueError: If wrapper_type is not supported
        """
        if wrapper_type == WrapperType.RYUGRAPH:
            # Resource configuration from settings (environment variables)
            # Allows customization per environment: local dev, demo, production
            return WrapperConfig(
                wrapper_type=WrapperType.RYUGRAPH,
                image_name=self._ryugraph_image,
                image_tag=self._ryugraph_tag,
                container_port=8000,
                health_check_path="/health",
                resource_limits={
                    "memory": self._settings.ryugraph_memory_limit if self._settings else "8Gi",
                    "cpu": self._settings.ryugraph_cpu_limit if self._settings else "4",
                },
                resource_requests={
                    "memory": self._settings.ryugraph_memory_request if self._settings else "4Gi",
                    "cpu": self._settings.ryugraph_cpu_request if self._settings else "2",
                },
                environment_variables={
                    "WRAPPER_TYPE": "ryugraph",
                    "BUFFER_POOL_SIZE": self._settings.ryugraph_buffer_pool_size if self._settings else "2147483648",
                },
            )
        elif wrapper_type == WrapperType.FALKORDB:
            # FalkorDB resource configuration from settings
            return WrapperConfig(
                wrapper_type=WrapperType.FALKORDB,
                image_name=self._falkordb_image,
                image_tag=self._falkordb_tag,
                container_port=8000,
                health_check_path="/health",
                resource_limits={
                    "memory": self._settings.falkordb_memory_limit if self._settings else "4Gi",
                    "cpu": self._settings.falkordb_cpu_limit if self._settings else "2",
                },
                resource_requests={
                    "memory": self._settings.falkordb_memory_request if self._settings else "2Gi",
                    "cpu": self._settings.falkordb_cpu_request if self._settings else "1",
                },
                environment_variables={
                    "WRAPPER_TYPE": "falkordb",
                    "PYTHON_VERSION": "3.12",  # FalkorDBLite requires Python 3.12+
                    # Skip CPU check to prevent Polars crash on Apple Silicon with x86 emulation
                    "POLARS_SKIP_CPU_CHECK": "1",
                },
            )
        else:
            raise ValueError(f"Unsupported wrapper type: {wrapper_type}")

    def get_capabilities(self, wrapper_type: WrapperType) -> WrapperCapabilities:
        """Get capabilities for a wrapper type.

        Args:
            wrapper_type: The wrapper type

        Returns:
            WrapperCapabilities object

        Raises:
            KeyError: If wrapper type is not registered
        """
        return get_wrapper_capabilities(wrapper_type)

    def supports_bulk_import(self, wrapper_type: WrapperType) -> bool:
        """Check if wrapper supports bulk Parquet import.

        Args:
            wrapper_type: The wrapper type

        Returns:
            True if wrapper supports bulk import
        """
        capabilities = self.get_capabilities(wrapper_type)
        return capabilities.supports_bulk_import

    def supports_algorithms(self, wrapper_type: WrapperType) -> bool:
        """Check if wrapper supports native graph algorithms.

        Args:
            wrapper_type: The wrapper type

        Returns:
            True if wrapper supports algorithms
        """
        capabilities = self.get_capabilities(wrapper_type)
        return capabilities.supports_algorithms

    def supports_networkx(self, wrapper_type: WrapperType) -> bool:
        """Check if wrapper supports NetworkX algorithm execution.

        Args:
            wrapper_type: The wrapper type

        Returns:
            True if wrapper supports NetworkX
        """
        capabilities = self.get_capabilities(wrapper_type)
        return capabilities.supports_networkx
