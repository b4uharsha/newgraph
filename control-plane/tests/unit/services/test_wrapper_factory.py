"""Unit tests for wrapper factory service."""

import pytest
from graph_olap_schemas import WrapperType

from control_plane.services.wrapper_factory import WrapperFactory

# Parameterized test data for wrapper-specific configurations
WRAPPER_CONFIGS = [
    # (wrapper_type, expected_image, expected_memory_limit, expected_memory_request, expected_env_keys)
    (WrapperType.RYUGRAPH, "ryugraph-wrapper", "8Gi", "4Gi", ["WRAPPER_TYPE", "BUFFER_POOL_SIZE"]),
    (WrapperType.FALKORDB, "falkordb-wrapper", "4Gi", "2Gi", ["WRAPPER_TYPE", "PYTHON_VERSION"]),
]


@pytest.fixture
def factory():
    """Create WrapperFactory with test configuration."""
    return WrapperFactory(
        ryugraph_image="ryugraph-wrapper",
        ryugraph_tag="sha-test123",
        falkordb_image="falkordb-wrapper",
        falkordb_tag="sha-test123",
    )


def test_get_ryugraph_config(factory):
    """Test getting Ryugraph wrapper configuration."""
    config = factory.get_wrapper_config(WrapperType.RYUGRAPH)

    assert config.wrapper_type == WrapperType.RYUGRAPH
    assert config.image_name == "ryugraph-wrapper"
    assert config.container_port == 8000
    assert config.health_check_path == "/health"
    assert "WRAPPER_TYPE" in config.environment_variables
    assert config.environment_variables["WRAPPER_TYPE"] == "ryugraph"


def test_get_falkordb_config(factory):
    """Test getting FalkorDB wrapper configuration."""
    config = factory.get_wrapper_config(WrapperType.FALKORDB)

    assert config.wrapper_type == WrapperType.FALKORDB
    assert config.image_name == "falkordb-wrapper"
    assert config.container_port == 8000
    assert config.health_check_path == "/health"
    assert "WRAPPER_TYPE" in config.environment_variables
    assert config.environment_variables["WRAPPER_TYPE"] == "falkordb"
    assert "PYTHON_VERSION" in config.environment_variables


def test_get_capabilities_ryugraph(factory):
    """Test getting Ryugraph capabilities."""
    caps = factory.get_capabilities(WrapperType.RYUGRAPH)

    assert caps.supports_algorithms is True
    assert caps.supports_networkx is True
    assert caps.supports_bulk_import is True
    assert "pagerank" in caps.native_algorithms


def test_get_capabilities_falkordb(factory):
    """Test getting FalkorDB capabilities."""
    caps = factory.get_capabilities(WrapperType.FALKORDB)

    assert caps.supports_algorithms is True
    assert caps.supports_networkx is False  # FalkorDB doesn't support NetworkX
    assert caps.supports_bulk_import is False  # No Parquet bulk import
    assert "BFS" in caps.native_algorithms


def test_unsupported_wrapper_type(factory):
    """Test that unsupported wrapper type raises error."""
    # Create a fake wrapper type that doesn't exist
    class FakeWrapper(str):
        pass

    fake_type = FakeWrapper("nonexistent")

    with pytest.raises((ValueError, KeyError)):
        factory.get_wrapper_config(fake_type)


def test_resource_limits(factory):
    """Test that wrappers have appropriate resource limits."""
    ryugraph_config = factory.get_wrapper_config(WrapperType.RYUGRAPH)
    falkordb_config = factory.get_wrapper_config(WrapperType.FALKORDB)

    # Parse memory values (e.g., "8Gi" -> 8)
    ryugraph_mem = int(ryugraph_config.resource_limits["memory"].rstrip("Gi"))
    falkordb_mem = int(falkordb_config.resource_limits["memory"].rstrip("Gi"))

    # Both wrappers should have reasonable memory limits
    assert ryugraph_mem == 8  # Ryugraph uses 8Gi
    assert falkordb_mem == 4  # FalkorDB uses 4Gi (reduced for cloud optimization)


@pytest.mark.parametrize("wrapper_type,expected_image,expected_mem_limit,expected_mem_request,expected_env_keys", WRAPPER_CONFIGS)
def test_wrapper_specific_config(factory, wrapper_type, expected_image, expected_mem_limit, expected_mem_request, expected_env_keys):
    """Verify each wrapper gets correct wrapper-specific configuration.

    This parameterized test ensures that the WrapperFactory returns different configurations
    for different wrapper types, including different images, resource limits, and environment variables.
    """
    config = factory.get_wrapper_config(wrapper_type)

    # Verify correct wrapper type
    assert config.wrapper_type == wrapper_type

    # Verify wrapper-specific image
    assert config.image_name == expected_image

    # Verify wrapper-specific resource limits
    assert config.resource_limits["memory"] == expected_mem_limit

    # Verify wrapper-specific resource requests
    assert config.resource_requests["memory"] == expected_mem_request

    # Verify all expected environment variables are present
    for key in expected_env_keys:
        assert key in config.environment_variables, f"Missing environment variable: {key}"

    # Verify wrapper_type env var matches
    assert config.environment_variables["WRAPPER_TYPE"] == wrapper_type.value


@pytest.mark.parametrize("wrapper_type", [WrapperType.RYUGRAPH, WrapperType.FALKORDB])
def test_all_wrappers_have_common_config(factory, wrapper_type):
    """Verify all wrappers have common required configuration fields."""
    config = factory.get_wrapper_config(wrapper_type)

    # All wrappers should have these common fields
    assert config.container_port == 8000
    assert config.health_check_path == "/health"
    assert config.resource_limits is not None
    assert config.resource_requests is not None
    assert "cpu" in config.resource_limits
    assert "cpu" in config.resource_requests
