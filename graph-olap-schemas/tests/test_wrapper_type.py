"""Tests for wrapper_type integration in API schemas."""

from graph_olap_schemas import (
    CreateInstanceRequest,
    InstanceResponse,
    WrapperType,
    get_wrapper_capabilities,
)


def test_wrapper_type_enum():
    """Test WrapperType enum values."""
    assert WrapperType.RYUGRAPH == "ryugraph"
    assert WrapperType.FALKORDB == "falkordb"
    assert str(WrapperType.RYUGRAPH) == "ryugraph"


def test_create_instance_request_with_wrapper_type():
    """Test CreateInstanceRequest includes wrapper_type field."""
    request = CreateInstanceRequest(
        snapshot_id=1,
        wrapper_type=WrapperType.FALKORDB,
        name="Test Instance",
        description="Test",
    )

    assert request.wrapper_type == WrapperType.FALKORDB
    assert request.snapshot_id == 1
    assert request.name == "Test Instance"


def test_instance_response_with_wrapper_type():
    """Test InstanceResponse includes wrapper_type field."""
    from datetime import datetime

    response = InstanceResponse(
        id=1,
        snapshot_id=1,
        owner_username="testuser",
        wrapper_type=WrapperType.RYUGRAPH,
        name="Test",
        description=None,
        status="running",
        instance_url="http://test:8000",
        pod_name="wrapper-123",
        progress=None,
        error_message=None,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        started_at=None,
        last_activity_at=None,
        expires_at=None,
        ttl=None,
        inactivity_timeout=None,
        memory_usage_bytes=None,
        disk_usage_bytes=None,
    )

    assert response.wrapper_type == WrapperType.RYUGRAPH
    assert response.id == 1


def test_wrapper_capabilities_registry():
    """Test wrapper capabilities can be retrieved."""
    ryugraph_caps = get_wrapper_capabilities(WrapperType.RYUGRAPH)
    falkordb_caps = get_wrapper_capabilities(WrapperType.FALKORDB)

    # Verify key differences
    assert ryugraph_caps.supports_networkx is True
    assert falkordb_caps.supports_networkx is False

    assert ryugraph_caps.supports_bulk_import is True
    assert falkordb_caps.supports_bulk_import is False

    assert ryugraph_caps.algorithm_invocation == "rest_api"
    assert falkordb_caps.algorithm_invocation == "cypher_procedure"
