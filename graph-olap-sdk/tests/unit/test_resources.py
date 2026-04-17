"""Unit tests for resource classes."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from graph_olap.models.common import PaginatedList
from graph_olap.models.instance import Instance
from graph_olap.models.mapping import Mapping, NodeDefinition
from graph_olap.models.snapshot import Snapshot
from graph_olap.resources.favorites import FavoriteResource
from graph_olap.resources.instances import InstanceResource
from graph_olap.resources.mappings import MappingResource

# SnapshotResource is deprecated - explicit snapshot creation APIs are no longer available
# from graph_olap.resources.snapshots import SnapshotResource

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def mock_http() -> MagicMock:
    """Create mock HTTP client."""
    return MagicMock()


@pytest.fixture
def sample_mapping_response() -> dict[str, Any]:
    """Sample mapping API response."""
    return {
        "data": {
            "id": 1,
            "owner_username": "test_user",
            "name": "Customer Graph",
            "description": "Customer and order relationships",
            "current_version": 1,
            "created_at": "2025-01-15T10:30:00Z",
            "updated_at": "2025-01-15T10:30:00Z",
            "ttl": None,
            "inactivity_timeout": None,
            "snapshot_count": 2,
            "version": {
                "mapping_id": 1,
                "version": 1,
                "change_description": "Initial version",
                "node_definitions": [
                    {
                        "label": "Customer",
                        "sql": "SELECT * FROM customers",
                        "primary_key": {"name": "id", "type": "STRING"},
                        "properties": [{"name": "name", "type": "STRING"}],
                    }
                ],
                "edge_definitions": [],
                "created_at": "2025-01-15T10:30:00Z",
                "created_by": "user-123",
                "created_by_name": "Test User",
            },
        }
    }


@pytest.fixture
def sample_snapshot_response() -> dict[str, Any]:
    """Sample snapshot API response."""
    return {
        "data": {
            "id": 1,
            "mapping_id": 1,
            "mapping_name": "Customer Graph",
            "mapping_version": 1,
            "owner_username": "test_user",
            "name": "Analysis Snapshot",
            "description": "For analysis",
            "gcs_path": "gs://bucket/snapshots/1",
            "size_bytes": 1024 * 1024 * 100,
            "node_counts": {"Customer": 10000},
            "edge_counts": {"PURCHASED": 50000},
            "status": "ready",
            "error_message": None,
            "created_at": "2025-01-15T10:30:00Z",
            "updated_at": "2025-01-15T10:35:00Z",
            "ttl": "P7D",
            "inactivity_timeout": "PT24H",
            "instance_count": 1,
        }
    }


@pytest.fixture
def sample_instance_response() -> dict[str, Any]:
    """Sample instance API response."""
    return {
        "data": {
            "id": 1,
            "snapshot_id": 1,
            "snapshot_name": "Analysis Snapshot",
            "owner_username": "test_user",
            "wrapper_type": "ryugraph",
            "name": "Analysis Instance",
            "description": "For analysis",
            "instance_url": "https://instance-1.example.com",
            "explorer_url": "https://instance-1.example.com/explorer",
            "status": "running",
            "error_message": None,
            "created_at": "2025-01-15T10:30:00Z",
            "updated_at": "2025-01-15T10:35:00Z",
            "started_at": "2025-01-15T10:35:00Z",
            "last_activity_at": "2025-01-15T11:00:00Z",
            "ttl": "PT24H",
            "inactivity_timeout": "PT8H",
            "memory_usage_bytes": 512 * 1024 * 1024,
            "disk_usage_bytes": 1024 * 1024 * 1024,
        }
    }


# =============================================================================
# MappingResource Tests
# =============================================================================


class TestMappingResourceList:
    """Tests for MappingResource.list()."""

    def test_list_returns_paginated_mappings(
        self, mock_http: MagicMock, sample_mapping_response: dict[str, Any]
    ):
        """Test list returns paginated list of mappings."""
        mock_http.get.return_value = {
            "data": [sample_mapping_response["data"]],
            "meta": {"total": 1, "offset": 0, "limit": 50},
        }

        resource = MappingResource(mock_http)
        result = resource.list()

        assert isinstance(result, PaginatedList)
        assert len(result) == 1
        assert result.total == 1
        assert isinstance(result[0], Mapping)
        assert result[0].name == "Customer Graph"

    def test_list_passes_filters(self, mock_http: MagicMock):
        """Test list passes filter parameters."""
        mock_http.get.return_value = {
            "data": [],
            "meta": {"total": 0, "offset": 0, "limit": 50},
        }

        resource = MappingResource(mock_http)
        resource.list(
            owner="user-123",
            search="customer",
            created_after="2025-01-01T00:00:00Z",
            sort_by="name",
            sort_order="asc",
            offset=10,
            limit=25,
        )

        mock_http.get.assert_called_once()
        call_args = mock_http.get.call_args
        params = call_args[1]["params"]
        assert params["owner"] == "user-123"
        assert params["search"] == "customer"
        assert params["created_after"] == "2025-01-01T00:00:00Z"
        assert params["sort_by"] == "name"
        assert params["sort_order"] == "asc"
        assert params["offset"] == 10
        assert params["limit"] == 25

    def test_list_caps_limit_at_100(self, mock_http: MagicMock):
        """Test list caps limit at 100."""
        mock_http.get.return_value = {
            "data": [],
            "meta": {"total": 0, "offset": 0, "limit": 100},
        }

        resource = MappingResource(mock_http)
        resource.list(limit=500)

        call_args = mock_http.get.call_args
        params = call_args[1]["params"]
        assert params["limit"] == 100


class TestMappingResourceGet:
    """Tests for MappingResource.get()."""

    def test_get_returns_mapping(
        self, mock_http: MagicMock, sample_mapping_response: dict[str, Any]
    ):
        """Test get returns mapping by ID."""
        mock_http.get.return_value = sample_mapping_response

        resource = MappingResource(mock_http)
        result = resource.get(1)

        assert isinstance(result, Mapping)
        assert result.id == 1
        assert result.name == "Customer Graph"
        mock_http.get.assert_called_with("/api/mappings/1")


class TestMappingResourceCreate:
    """Tests for MappingResource.create()."""

    def test_create_with_basic_params(
        self, mock_http: MagicMock, sample_mapping_response: dict[str, Any]
    ):
        """Test create with basic parameters."""
        mock_http.post.return_value = sample_mapping_response

        resource = MappingResource(mock_http)
        result = resource.create(
            name="Customer Graph",
            description="Test description",
        )

        assert isinstance(result, Mapping)
        mock_http.post.assert_called_once()
        call_args = mock_http.post.call_args
        body = call_args[1]["json"]
        assert body["name"] == "Customer Graph"
        assert body["description"] == "Test description"

    def test_create_with_node_definition_objects(
        self, mock_http: MagicMock, sample_mapping_response: dict[str, Any]
    ):
        """Test create with NodeDefinition objects."""
        mock_http.post.return_value = sample_mapping_response

        resource = MappingResource(mock_http)
        node = NodeDefinition(
            label="Customer",
            sql="SELECT * FROM customers",
            primary_key={"name": "id", "type": "STRING"},
            properties=[],
        )
        resource.create(name="Test", node_definitions=[node])

        call_args = mock_http.post.call_args
        body = call_args[1]["json"]
        assert len(body["node_definitions"]) == 1
        assert body["node_definitions"][0]["label"] == "Customer"


class TestMappingResourceUpdate:
    """Tests for MappingResource.update()."""

    def test_update_creates_new_version(
        self, mock_http: MagicMock, sample_mapping_response: dict[str, Any]
    ):
        """Test update creates new version."""
        mock_http.put.return_value = sample_mapping_response

        resource = MappingResource(mock_http)
        result = resource.update(
            mapping_id=1,
            change_description="Added new node",
            name="Updated Name",
        )

        assert isinstance(result, Mapping)
        call_args = mock_http.put.call_args
        assert call_args[0][0] == "/api/mappings/1"
        body = call_args[1]["json"]
        assert body["change_description"] == "Added new node"
        assert body["name"] == "Updated Name"


class TestMappingResourceDelete:
    """Tests for MappingResource.delete()."""

    def test_delete_calls_api(self, mock_http: MagicMock):
        """Test delete calls API endpoint."""
        mock_http.delete.return_value = {}

        resource = MappingResource(mock_http)
        resource.delete(1)

        mock_http.delete.assert_called_with("/api/mappings/1")


class TestMappingResourceCopy:
    """Tests for MappingResource.copy()."""

    def test_copy_creates_new_mapping(
        self, mock_http: MagicMock, sample_mapping_response: dict[str, Any]
    ):
        """Test copy creates new mapping."""
        mock_http.post.return_value = sample_mapping_response

        resource = MappingResource(mock_http)
        result = resource.copy(1, "Copy of Mapping")

        assert isinstance(result, Mapping)
        mock_http.post.assert_called_with(
            "/api/mappings/1/copy",
            json={"name": "Copy of Mapping"},
        )


class TestMappingResourceListInstances:
    """Tests for MappingResource.list_instances()."""

    def test_list_instances_returns_paginated_instances(
        self, mock_http: MagicMock, sample_instance_response: dict[str, Any]
    ):
        """Test list_instances returns paginated list of instances."""
        mock_http.get.return_value = {
            "data": [sample_instance_response["data"]],
            "meta": {"total": 1, "offset": 0, "limit": 50},
        }

        resource = MappingResource(mock_http)
        result = resource.list_instances(mapping_id=1)

        assert isinstance(result, PaginatedList)
        assert len(result) == 1
        assert isinstance(result[0], Instance)
        assert result[0].name == "Analysis Instance"
        mock_http.get.assert_called_with(
            "/api/mappings/1/instances",
            params={"offset": 0, "limit": 50},
        )

    def test_list_instances_with_pagination(self, mock_http: MagicMock):
        """Test list_instances passes pagination parameters."""
        mock_http.get.return_value = {
            "data": [],
            "meta": {"total": 0, "offset": 10, "limit": 25},
        }

        resource = MappingResource(mock_http)
        resource.list_instances(mapping_id=1, offset=10, limit=25)

        mock_http.get.assert_called_with(
            "/api/mappings/1/instances",
            params={"offset": 10, "limit": 25},
        )


# =============================================================================
# SnapshotResource Tests
# =============================================================================
# SNAPSHOT TESTS DISABLED
# These tests are commented out as snapshot functionality has been disabled.
# =============================================================================


# class TestSnapshotResourceList:
#     """Tests for SnapshotResource.list()."""
#
#     def test_list_returns_paginated_snapshots(
#         self, mock_http: MagicMock, sample_snapshot_response: dict[str, Any]
#     ):
#         """Test list returns paginated list of snapshots."""
#         mock_http.get.return_value = {
#             "data": [sample_snapshot_response["data"]],
#             "meta": {"total": 1, "offset": 0, "limit": 50},
#         }
#
#         resource = SnapshotResource(mock_http)
#         result = resource.list()
#
#         assert isinstance(result, PaginatedList)
#         assert len(result) == 1
#         assert isinstance(result[0], Snapshot)
#         assert result[0].name == "Analysis Snapshot"
#
#     def test_list_with_filters(self, mock_http: MagicMock):
#         """Test list passes filter parameters."""
#         mock_http.get.return_value = {
#             "data": [],
#             "meta": {"total": 0, "offset": 0, "limit": 50},
#         }
#
#         resource = SnapshotResource(mock_http)
#         resource.list(mapping_id=1, status="ready")
#
#         call_args = mock_http.get.call_args
#         params = call_args[1]["params"]
#         assert params["mapping_id"] == 1
#         assert params["status"] == "ready"


# class TestSnapshotResourceCreate:
#     """Tests for SnapshotResource.create()."""
#
#     def test_create_returns_snapshot(
#         self, mock_http: MagicMock, sample_snapshot_response: dict[str, Any]
#     ):
#         """Test create returns snapshot."""
#         mock_http.post.return_value = sample_snapshot_response
#
#         resource = SnapshotResource(mock_http)
#         result = resource.create(
#             mapping_id=1,
#             name="New Snapshot",
#             description="Test",
#         )
#
#         assert isinstance(result, Snapshot)
#         call_args = mock_http.post.call_args
#         body = call_args[1]["json"]
#         assert body["mapping_id"] == 1
#         assert body["name"] == "New Snapshot"


# class TestSnapshotResourceRetry:
#     """Tests for SnapshotResource.retry()."""
#
#     def test_retry_failed_snapshot(
#         self, mock_http: MagicMock, sample_snapshot_response: dict[str, Any]
#     ):
#         """Test retry on failed snapshot."""
#         mock_http.post.return_value = sample_snapshot_response
#
#         resource = SnapshotResource(mock_http)
#         result = resource.retry(1)
#
#         assert isinstance(result, Snapshot)
#         mock_http.post.assert_called_with("/api/snapshots/1/retry")


# =============================================================================
# InstanceResource Tests
# =============================================================================


@pytest.fixture
def mock_config() -> MagicMock:
    """Create mock config."""
    config = MagicMock()
    config.username = "test-user@example.com"
    return config


class TestInstanceResourceList:
    """Tests for InstanceResource.list()."""

    def test_list_returns_paginated_instances(
        self, mock_http: MagicMock, mock_config: MagicMock, sample_instance_response: dict[str, Any]
    ):
        """Test list returns paginated list of instances."""
        mock_http.get.return_value = {
            "data": [sample_instance_response["data"]],
            "meta": {"total": 1, "offset": 0, "limit": 50},
        }

        resource = InstanceResource(mock_http, mock_config)
        result = resource.list()

        assert isinstance(result, PaginatedList)
        assert len(result) == 1
        assert isinstance(result[0], Instance)
        assert result[0].name == "Analysis Instance"


# =========================================================================
# DEPRECATED: Use create_from_mapping() instead
# Commented out as part of API simplification - 2025-01
# =========================================================================
# class TestInstanceResourceCreate:
#     """Tests for InstanceResource.create()."""
#
#     def test_create_returns_instance(
#         self, mock_http: MagicMock, mock_config: MagicMock, sample_instance_response: dict[str, Any]
#     ):
#         """Test create returns instance."""
#         mock_http.post.return_value = sample_instance_response
#
#         from graph_olap_schemas import WrapperType
#
#         resource = InstanceResource(mock_http, mock_config)
#         result = resource.create(
#             snapshot_id=1,
#             name="New Instance",
#             wrapper_type=WrapperType.RYUGRAPH,
#             description="Test",
#         )
#
#         assert isinstance(result, Instance)
#         call_args = mock_http.post.call_args
#         body = call_args[1]["json"]
#         assert body["snapshot_id"] == 1
#         assert body["name"] == "New Instance"
#         assert body["wrapper_type"] == "ryugraph"


class TestInstanceResourceTerminate:
    """Tests for InstanceResource.terminate()."""

    def test_terminate_calls_api(self, mock_http: MagicMock, mock_config: MagicMock):
        """Test terminate calls DELETE API endpoint (REST-compliant)."""
        mock_http.delete.return_value = {}

        resource = InstanceResource(mock_http, mock_config)
        resource.terminate(1)

        mock_http.delete.assert_called_with("/api/instances/1")


class TestInstanceResourceSetLifecycle:
    """Tests for InstanceResource.set_lifecycle()."""

    def test_set_lifecycle_updates_ttl(
        self, mock_http: MagicMock, mock_config: MagicMock, sample_instance_response: dict[str, Any]
    ):
        """Test set_lifecycle updates TTL."""
        mock_http.put.return_value = sample_instance_response

        resource = InstanceResource(mock_http, mock_config)
        result = resource.set_lifecycle(1, ttl="PT48H")

        assert isinstance(result, Instance)
        call_args = mock_http.put.call_args
        assert call_args[0][0] == "/api/instances/1/lifecycle"
        body = call_args[1]["json"]
        assert body["ttl"] == "PT48H"

    def test_set_lifecycle_updates_inactivity_timeout(
        self, mock_http: MagicMock, mock_config: MagicMock, sample_instance_response: dict[str, Any]
    ):
        """Test set_lifecycle updates inactivity timeout."""
        mock_http.put.return_value = sample_instance_response

        resource = InstanceResource(mock_http, mock_config)
        result = resource.set_lifecycle(1, inactivity_timeout="PT12H")

        assert isinstance(result, Instance)
        call_args = mock_http.put.call_args
        body = call_args[1]["json"]
        assert body["inactivity_timeout"] == "PT12H"

    def test_set_lifecycle_updates_both(
        self, mock_http: MagicMock, mock_config: MagicMock, sample_instance_response: dict[str, Any]
    ):
        """Test set_lifecycle updates both TTL and inactivity timeout."""
        mock_http.put.return_value = sample_instance_response

        resource = InstanceResource(mock_http, mock_config)
        result = resource.set_lifecycle(1, ttl="PT72H", inactivity_timeout="PT24H")

        assert isinstance(result, Instance)
        call_args = mock_http.put.call_args
        body = call_args[1]["json"]
        assert body["ttl"] == "PT72H"
        assert body["inactivity_timeout"] == "PT24H"


class TestInstanceResourceUpdate:
    """Tests for InstanceResource.update()."""

    def test_update_returns_instance(
        self, mock_http: MagicMock, mock_config: MagicMock, sample_instance_response: dict[str, Any]
    ):
        """Test update returns updated instance."""
        mock_http.put.return_value = sample_instance_response

        resource = InstanceResource(mock_http, mock_config)
        result = resource.update(1, name="New Name", description="New description")

        assert isinstance(result, Instance)
        call_args = mock_http.put.call_args
        assert call_args[0][0] == "/api/instances/1"
        body = call_args[1]["json"]
        assert body["name"] == "New Name"
        assert body["description"] == "New description"

    def test_update_with_name_only(
        self, mock_http: MagicMock, mock_config: MagicMock, sample_instance_response: dict[str, Any]
    ):
        """Test update with only name."""
        mock_http.put.return_value = sample_instance_response

        resource = InstanceResource(mock_http, mock_config)
        result = resource.update(1, name="New Name")

        assert isinstance(result, Instance)
        call_args = mock_http.put.call_args
        body = call_args[1]["json"]
        assert body["name"] == "New Name"
        assert "description" not in body

    def test_update_with_description_only(
        self, mock_http: MagicMock, mock_config: MagicMock, sample_instance_response: dict[str, Any]
    ):
        """Test update with only description."""
        mock_http.put.return_value = sample_instance_response

        resource = InstanceResource(mock_http, mock_config)
        result = resource.update(1, description="New description")

        assert isinstance(result, Instance)
        call_args = mock_http.put.call_args
        body = call_args[1]["json"]
        assert "name" not in body
        assert body["description"] == "New description"


# =============================================================================
# FavoriteResource Tests
# =============================================================================


class TestFavoriteResourceList:
    """Tests for FavoriteResource.list()."""

    def test_list_returns_favorites(self, mock_http: MagicMock):
        """Test list returns list of favorites."""
        mock_http.get.return_value = {
            "data": [
                {
                    "id": 1,
                    "resource_type": "mapping",
                    "resource_id": 1,
                    "created_at": "2025-01-15T10:30:00Z",
                }
            ]
        }

        resource = FavoriteResource(mock_http)
        result = resource.list()

        assert len(result) == 1
        assert result[0].resource_type == "mapping"
        assert result[0].resource_id == 1


class TestFavoriteResourceAdd:
    """Tests for FavoriteResource.add()."""

    def test_add_creates_favorite(self, mock_http: MagicMock):
        """Test add creates favorite."""
        mock_http.post.return_value = {
            "data": {
                "id": 1,
                "resource_type": "mapping",
                "resource_id": 1,
                "created_at": "2025-01-15T10:30:00Z",
            }
        }

        resource = FavoriteResource(mock_http)
        result = resource.add(resource_type="mapping", resource_id=1)

        assert result.resource_type == "mapping"
        call_args = mock_http.post.call_args
        body = call_args[1]["json"]
        assert body["resource_type"] == "mapping"
        assert body["resource_id"] == 1


class TestFavoriteResourceRemove:
    """Tests for FavoriteResource.remove()."""

    def test_remove_deletes_favorite(self, mock_http: MagicMock):
        """Test remove deletes favorite."""
        mock_http.delete.return_value = {}

        resource = FavoriteResource(mock_http)
        resource.remove(resource_type="mapping", resource_id=1)

        mock_http.delete.assert_called_with("/api/favorites/mapping/1")


# =============================================================================
# OpsResource Tests
# =============================================================================


from graph_olap.models.ops import (
    ClusterHealth,
    ClusterInstances,
    ConcurrencyConfig,
    ExportConfig,
    LifecycleConfig,
    MaintenanceMode,
)
from graph_olap.resources.ops import OpsResource


@pytest.fixture
def sample_lifecycle_config_response() -> dict[str, Any]:
    """Sample lifecycle config API response."""
    return {
        "data": {
            "mapping": {
                "default_ttl": "P30D",
                "default_inactivity": "P7D",
                "max_ttl": "P90D",
            },
            "snapshot": {
                "default_ttl": "P14D",
                "default_inactivity": "P3D",
                "max_ttl": "P60D",
            },
            "instance": {
                "default_ttl": "PT24H",
                "default_inactivity": "PT8H",
                "max_ttl": "P7D",
            },
        }
    }


@pytest.fixture
def sample_concurrency_config_response() -> dict[str, Any]:
    """Sample concurrency config API response."""
    return {
        "data": {
            "per_analyst": 5,
            "cluster_total": 100,
            "updated_at": "2025-01-15T10:30:00Z",
        }
    }


@pytest.fixture
def sample_maintenance_mode_response() -> dict[str, Any]:
    """Sample maintenance mode API response."""
    return {
        "data": {
            "enabled": False,
            "message": "",
            "updated_at": "2025-01-15T10:30:00Z",
        }
    }


@pytest.fixture
def sample_export_config_response() -> dict[str, Any]:
    """Sample export config API response."""
    return {
        "data": {
            "max_duration_seconds": 3600,
            "updated_at": "2025-01-15T10:30:00Z",
        }
    }


@pytest.fixture
def sample_cluster_health_response() -> dict[str, Any]:
    """Sample cluster health API response."""
    return {
        "data": {
            "status": "healthy",
            "components": {
                "database": {"status": "healthy", "latency_ms": 5},
                "kubernetes": {"status": "healthy", "latency_ms": 10},
            },
            "checked_at": "2025-01-15T10:30:00Z",
        }
    }


@pytest.fixture
def sample_cluster_instances_response() -> dict[str, Any]:
    """Sample cluster instances API response."""
    return {
        "data": {
            "total": 42,
            "by_status": {"running": 35, "starting": 5, "stopping": 2},
            "by_owner": [
                {"owner_username": "analyst-alice", "count": 10},
                {"owner_username": "analyst-bob", "count": 8},
            ],
            "limits": {
                "per_analyst": 5,
                "cluster_total": 100,
                "cluster_used": 42,
                "cluster_available": 58,
            },
        }
    }


class TestOpsResourceGetLifecycleConfig:
    """Tests for OpsResource.get_lifecycle_config()."""

    def test_get_lifecycle_config_returns_config(
        self, mock_http: MagicMock, sample_lifecycle_config_response: dict[str, Any]
    ):
        """Test get_lifecycle_config returns LifecycleConfig."""
        mock_http.get.return_value = sample_lifecycle_config_response

        resource = OpsResource(mock_http)
        result = resource.get_lifecycle_config()

        assert isinstance(result, LifecycleConfig)
        assert result.instance.default_ttl == "PT24H"
        mock_http.get.assert_called_with("/api/config/lifecycle")


class TestOpsResourceUpdateLifecycleConfig:
    """Tests for OpsResource.update_lifecycle_config()."""

    def test_update_lifecycle_config_with_dict(self, mock_http: MagicMock):
        """Test update with dict values."""
        mock_http.put.return_value = {"data": {"updated": True}}

        resource = OpsResource(mock_http)
        result = resource.update_lifecycle_config(
            instance={"default_ttl": "PT48H"}
        )

        assert result is True
        mock_http.put.assert_called_once()
        call_args = mock_http.put.call_args
        assert call_args[0][0] == "/api/config/lifecycle"
        assert call_args[1]["json"]["instance"]["default_ttl"] == "PT48H"

    def test_update_lifecycle_config_with_model(self, mock_http: MagicMock):
        """Test update with ResourceLifecycleConfig model."""
        from graph_olap.models.ops import ResourceLifecycleConfig

        mock_http.put.return_value = {"data": {"updated": True}}

        resource = OpsResource(mock_http)
        config = ResourceLifecycleConfig(
            default_ttl="PT48H",
            default_inactivity="PT12H",
            max_ttl="P7D",
        )
        result = resource.update_lifecycle_config(instance=config)

        assert result is True
        call_args = mock_http.put.call_args
        body = call_args[1]["json"]["instance"]
        assert body["default_ttl"] == "PT48H"
        assert body["default_inactivity"] == "PT12H"
        assert body["max_ttl"] == "P7D"

    def test_update_lifecycle_config_multiple_types(self, mock_http: MagicMock):
        """Test update with multiple resource types."""
        mock_http.put.return_value = {"data": {"updated": True}}

        resource = OpsResource(mock_http)
        resource.update_lifecycle_config(
            mapping={"default_ttl": "P60D"},
            snapshot={"default_ttl": "P30D"},
            instance={"default_ttl": "PT48H"},
        )

        call_args = mock_http.put.call_args
        body = call_args[1]["json"]
        assert "mapping" in body
        assert "snapshot" in body
        assert "instance" in body


class TestOpsResourceGetConcurrencyConfig:
    """Tests for OpsResource.get_concurrency_config()."""

    def test_get_concurrency_config_returns_config(
        self, mock_http: MagicMock, sample_concurrency_config_response: dict[str, Any]
    ):
        """Test get_concurrency_config returns ConcurrencyConfig."""
        mock_http.get.return_value = sample_concurrency_config_response

        resource = OpsResource(mock_http)
        result = resource.get_concurrency_config()

        assert isinstance(result, ConcurrencyConfig)
        assert result.per_analyst == 5
        assert result.cluster_total == 100
        mock_http.get.assert_called_with("/api/config/concurrency")


class TestOpsResourceUpdateConcurrencyConfig:
    """Tests for OpsResource.update_concurrency_config()."""

    def test_update_concurrency_config(
        self, mock_http: MagicMock, sample_concurrency_config_response: dict[str, Any]
    ):
        """Test update_concurrency_config updates and returns config."""
        mock_http.put.return_value = sample_concurrency_config_response

        resource = OpsResource(mock_http)
        result = resource.update_concurrency_config(
            per_analyst=10,
            cluster_total=200,
        )

        assert isinstance(result, ConcurrencyConfig)
        mock_http.put.assert_called_once()
        call_args = mock_http.put.call_args
        assert call_args[0][0] == "/api/config/concurrency"
        body = call_args[1]["json"]
        assert body["per_analyst"] == 10
        assert body["cluster_total"] == 200


class TestOpsResourceGetMaintenanceMode:
    """Tests for OpsResource.get_maintenance_mode()."""

    def test_get_maintenance_mode_returns_status(
        self, mock_http: MagicMock, sample_maintenance_mode_response: dict[str, Any]
    ):
        """Test get_maintenance_mode returns MaintenanceMode."""
        mock_http.get.return_value = sample_maintenance_mode_response

        resource = OpsResource(mock_http)
        result = resource.get_maintenance_mode()

        assert isinstance(result, MaintenanceMode)
        assert result.enabled is False
        mock_http.get.assert_called_with("/api/config/maintenance")


class TestOpsResourceSetMaintenanceMode:
    """Tests for OpsResource.set_maintenance_mode()."""

    def test_set_maintenance_mode_enabled(self, mock_http: MagicMock):
        """Test enabling maintenance mode."""
        mock_http.put.return_value = {
            "data": {
                "enabled": True,
                "message": "Scheduled downtime",
                "updated_at": "2025-01-15T10:30:00Z",
            }
        }

        resource = OpsResource(mock_http)
        result = resource.set_maintenance_mode(
            enabled=True,
            message="Scheduled downtime",
        )

        assert isinstance(result, MaintenanceMode)
        assert result.enabled is True
        assert result.message == "Scheduled downtime"
        call_args = mock_http.put.call_args
        body = call_args[1]["json"]
        assert body["enabled"] is True
        assert body["message"] == "Scheduled downtime"

    def test_set_maintenance_mode_disabled(self, mock_http: MagicMock):
        """Test disabling maintenance mode."""
        mock_http.put.return_value = {
            "data": {
                "enabled": False,
                "message": "",
            }
        }

        resource = OpsResource(mock_http)
        result = resource.set_maintenance_mode(enabled=False)

        assert result.enabled is False


class TestOpsResourceGetExportConfig:
    """Tests for OpsResource.get_export_config()."""

    def test_get_export_config_returns_config(
        self, mock_http: MagicMock, sample_export_config_response: dict[str, Any]
    ):
        """Test get_export_config returns ExportConfig."""
        mock_http.get.return_value = sample_export_config_response

        resource = OpsResource(mock_http)
        result = resource.get_export_config()

        assert isinstance(result, ExportConfig)
        assert result.max_duration_seconds == 3600
        mock_http.get.assert_called_with("/api/config/export")


class TestOpsResourceUpdateExportConfig:
    """Tests for OpsResource.update_export_config()."""

    def test_update_export_config(
        self, mock_http: MagicMock, sample_export_config_response: dict[str, Any]
    ):
        """Test update_export_config updates and returns config."""
        mock_http.put.return_value = sample_export_config_response

        resource = OpsResource(mock_http)
        result = resource.update_export_config(max_duration_seconds=7200)

        assert isinstance(result, ExportConfig)
        call_args = mock_http.put.call_args
        assert call_args[0][0] == "/api/config/export"
        assert call_args[1]["json"]["max_duration_seconds"] == 7200


class TestOpsResourceGetClusterHealth:
    """Tests for OpsResource.get_cluster_health()."""

    def test_get_cluster_health_returns_health(
        self, mock_http: MagicMock, sample_cluster_health_response: dict[str, Any]
    ):
        """Test get_cluster_health returns ClusterHealth."""
        mock_http.get.return_value = sample_cluster_health_response

        resource = OpsResource(mock_http)
        result = resource.get_cluster_health()

        assert isinstance(result, ClusterHealth)
        assert result.status == "healthy"
        assert "database" in result.components
        mock_http.get.assert_called_with("/api/cluster/health")


class TestOpsResourceGetClusterInstances:
    """Tests for OpsResource.get_cluster_instances()."""

    def test_get_cluster_instances_returns_summary(
        self, mock_http: MagicMock, sample_cluster_instances_response: dict[str, Any]
    ):
        """Test get_cluster_instances returns ClusterInstances."""
        mock_http.get.return_value = sample_cluster_instances_response

        resource = OpsResource(mock_http)
        result = resource.get_cluster_instances()

        assert isinstance(result, ClusterInstances)
        assert result.total == 42
        assert result.by_status["running"] == 35
        assert len(result.by_owner) == 2
        assert result.limits.cluster_available == 58
        mock_http.get.assert_called_with("/api/cluster/instances")


class TestOpsResourceGetMetrics:
    """Tests for OpsResource.get_metrics()."""

    def test_get_metrics_returns_text(self, mock_http: MagicMock):
        """Test get_metrics returns Prometheus metrics as text."""
        sample_metrics = """# HELP background_job_execution_total Total number of background job executions
# TYPE background_job_execution_total counter
background_job_execution_total{job_name="reconciliation",status="success"} 42.0
background_job_execution_total{job_name="lifecycle",status="success"} 38.0
# HELP reconciliation_passes_total Total reconciliation passes
# TYPE reconciliation_passes_total counter
reconciliation_passes_total 42.0
"""
        mock_http.get_text.return_value = sample_metrics

        resource = OpsResource(mock_http)
        result = resource.get_metrics()

        assert isinstance(result, str)
        assert "background_job_execution_total" in result
        assert 'job_name="reconciliation"' in result
        assert 'job_name="lifecycle"' in result
        assert "reconciliation_passes_total" in result
        mock_http.get_text.assert_called_once_with("/metrics")

    def test_get_metrics_empty_response(self, mock_http: MagicMock):
        """Test get_metrics with empty metrics response."""
        mock_http.get_text.return_value = ""

        resource = OpsResource(mock_http)
        result = resource.get_metrics()

        assert result == ""
        mock_http.get_text.assert_called_once_with("/metrics")


# =============================================================================
# HealthResource Tests
# =============================================================================


from graph_olap.models.ops import HealthStatus
from graph_olap.resources.health import HealthResource


class TestHealthResourceCheck:
    """Tests for HealthResource.check()."""

    def test_check_returns_health_status(self, mock_http: MagicMock):
        """Test check returns HealthStatus."""
        mock_http.get.return_value = {
            "status": "ok",
            "version": "1.2.3",
        }

        resource = HealthResource(mock_http)
        result = resource.check()

        assert isinstance(result, HealthStatus)
        assert result.status == "ok"
        assert result.version == "1.2.3"
        mock_http.get.assert_called_with("/health")


class TestHealthResourceReady:
    """Tests for HealthResource.ready()."""

    def test_ready_returns_health_status_with_database(self, mock_http: MagicMock):
        """Test ready returns HealthStatus with database status."""
        mock_http.get.return_value = {
            "status": "ok",
            "version": "1.2.3",
            "database": "connected",
        }

        resource = HealthResource(mock_http)
        result = resource.ready()

        assert isinstance(result, HealthStatus)
        assert result.status == "ok"
        assert result.database == "connected"
        mock_http.get.assert_called_with("/ready")


# =============================================================================
# InstanceResource.create_from_mapping Tests
# =============================================================================


@pytest.fixture
def sample_waiting_instance_response() -> dict[str, Any]:
    """Sample instance API response with waiting_for_snapshot status."""
    return {
        "data": {
            "id": 1,
            "snapshot_id": 1,
            "snapshot_name": "Auto-generated Snapshot",
            "owner_username": "test_user",
            "wrapper_type": "falkordb",
            "name": "Instance From Mapping",
            "description": "Created from mapping",
            "instance_url": None,
            "explorer_url": None,
            "status": "waiting_for_snapshot",
            "error_message": None,
            "created_at": "2025-01-15T10:30:00Z",
            "updated_at": "2025-01-15T10:30:00Z",
            "started_at": None,
            "last_activity_at": None,
            "ttl": "PT24H",
            "inactivity_timeout": "PT8H",
            "memory_usage_bytes": None,
            "disk_usage_bytes": None,
        }
    }


class TestInstanceResourceCreate:
    """Tests for InstanceResource.create()."""

    def test_create_basic(
        self, mock_http: MagicMock, mock_config: MagicMock, sample_waiting_instance_response: dict[str, Any]
    ):
        """Test create with basic parameters."""
        mock_http.post.return_value = sample_waiting_instance_response

        from graph_olap_schemas import WrapperType

        resource = InstanceResource(mock_http, mock_config)
        result = resource.create(
            mapping_id=1,
            name="Instance From Mapping",
            wrapper_type=WrapperType.FALKORDB,
        )

        assert isinstance(result, Instance)
        assert result.status == "waiting_for_snapshot"
        mock_http.post.assert_called_once()
        call_args = mock_http.post.call_args
        assert call_args[0][0] == "/api/instances"
        body = call_args[1]["json"]
        assert body["mapping_id"] == 1
        assert body["name"] == "Instance From Mapping"
        assert body["wrapper_type"] == "falkordb"

    def test_create_with_version(
        self, mock_http: MagicMock, mock_config: MagicMock, sample_waiting_instance_response: dict[str, Any]
    ):
        """Test create with specific mapping version."""
        mock_http.post.return_value = sample_waiting_instance_response

        from graph_olap_schemas import WrapperType

        resource = InstanceResource(mock_http, mock_config)
        resource.create(
            mapping_id=1,
            name="Versioned Instance",
            wrapper_type=WrapperType.RYUGRAPH,
            mapping_version=3,
        )

        call_args = mock_http.post.call_args
        body = call_args[1]["json"]
        assert body["mapping_version"] == 3
        assert body["wrapper_type"] == "ryugraph"

    def test_create_with_description(
        self, mock_http: MagicMock, mock_config: MagicMock, sample_waiting_instance_response: dict[str, Any]
    ):
        """Test create with description."""
        mock_http.post.return_value = sample_waiting_instance_response

        from graph_olap_schemas import WrapperType

        resource = InstanceResource(mock_http, mock_config)
        resource.create(
            mapping_id=1,
            name="Described Instance",
            wrapper_type=WrapperType.FALKORDB,
            description="Instance for analysis",
        )

        call_args = mock_http.post.call_args
        body = call_args[1]["json"]
        assert body["description"] == "Instance for analysis"

    def test_create_with_lifecycle(
        self, mock_http: MagicMock, mock_config: MagicMock, sample_waiting_instance_response: dict[str, Any]
    ):
        """Test create with lifecycle settings."""
        mock_http.post.return_value = sample_waiting_instance_response

        from graph_olap_schemas import WrapperType

        resource = InstanceResource(mock_http, mock_config)
        resource.create(
            mapping_id=1,
            name="Lifecycle Instance",
            wrapper_type=WrapperType.FALKORDB,
            ttl="PT48H",
            inactivity_timeout="PT12H",
        )

        call_args = mock_http.post.call_args
        body = call_args[1]["json"]
        assert body["ttl"] == "PT48H"
        assert body["inactivity_timeout"] == "PT12H"

    def test_create_normalizes_integer_ttl(
        self, mock_http: MagicMock, mock_config: MagicMock, sample_waiting_instance_response: dict[str, Any]
    ):
        """Test that integer TTL is normalized to ISO 8601 format."""
        mock_http.post.return_value = sample_waiting_instance_response

        from graph_olap_schemas import WrapperType

        resource = InstanceResource(mock_http, mock_config)
        resource.create(
            mapping_id=1,
            name="Int TTL Instance",
            wrapper_type=WrapperType.FALKORDB,
            ttl=48,  # Integer hours
            inactivity_timeout=12,  # Integer hours
        )

        call_args = mock_http.post.call_args
        body = call_args[1]["json"]
        assert body["ttl"] == "PT48H"
        assert body["inactivity_timeout"] == "PT12H"

    def test_create_without_optional_params(
        self, mock_http: MagicMock, mock_config: MagicMock, sample_waiting_instance_response: dict[str, Any]
    ):
        """Test that optional params are not included when not specified."""
        mock_http.post.return_value = sample_waiting_instance_response

        from graph_olap_schemas import WrapperType

        resource = InstanceResource(mock_http, mock_config)
        resource.create(
            mapping_id=1,
            name="Minimal Instance",
            wrapper_type=WrapperType.FALKORDB,
        )

        call_args = mock_http.post.call_args
        body = call_args[1]["json"]
        assert "mapping_version" not in body
        assert "description" not in body
        assert "ttl" not in body
        assert "inactivity_timeout" not in body


class TestInstanceResourceCreateAndWait:
    """Tests for InstanceResource.create_and_wait()."""

    def test_create_and_wait_success(
        self, mock_http: MagicMock, mock_config: MagicMock
    ):
        """Test create_and_wait transitions through statuses."""
        import os

        # Set environment variable to skip health check
        os.environ["GRAPH_OLAP_SKIP_HEALTH_CHECK"] = "true"

        try:
            from graph_olap_schemas import WrapperType

            # Mock the POST to create instance (returns waiting_for_snapshot)
            waiting_response = {
                "data": {
                    "id": 1,
                    "snapshot_id": 1,
                    "snapshot_name": "Auto-generated",
                    "owner_username": "test_user",
                    "wrapper_type": "falkordb",
                    "name": "Test Instance",
                    "description": None,
                    "instance_url": "https://instance-1.example.com",
                    "explorer_url": "https://instance-1.example.com/explorer",
                    "status": "waiting_for_snapshot",
                    "error_message": None,
                    "created_at": "2025-01-15T10:30:00Z",
                    "updated_at": "2025-01-15T10:30:00Z",
                    "started_at": None,
                    "last_activity_at": None,
                    "ttl": None,
                    "inactivity_timeout": None,
                    "memory_usage_bytes": None,
                    "disk_usage_bytes": None,
                }
            }

            # Mock the GET calls that poll for status
            starting_response = {
                "data": {
                    **waiting_response["data"],
                    "status": "starting",
                }
            }
            running_response = {
                "data": {
                    **waiting_response["data"],
                    "status": "running",
                    "started_at": "2025-01-15T10:35:00Z",
                }
            }

            # Progress response
            progress_response = {
                "data": {
                    "phase": "loading",
                    "completed_steps": 2,
                    "total_steps": 5,
                    "steps": [],
                }
            }

            mock_http.post.return_value = waiting_response
            # Each iteration: GET instance, then GET progress (if on_progress callback)
            # The progress GET happens BEFORE checking if status is "running"
            mock_http.get.side_effect = [
                {"data": waiting_response["data"]},  # GET instance (waiting)
                progress_response,  # GET progress
                {"data": starting_response["data"]},  # GET instance (starting)
                progress_response,  # GET progress
                {"data": running_response["data"]},  # GET instance (running)
                progress_response,  # GET progress (called before break)
            ]

            resource = InstanceResource(mock_http, mock_config)

            # Track progress calls
            progress_calls = []

            def on_progress(phase: str, completed: int, total: int):
                progress_calls.append((phase, completed, total))

            result = resource.create_and_wait(
                mapping_id=1,
                name="Test Instance",
                wrapper_type=WrapperType.FALKORDB,
                poll_interval=0.01,  # Fast polling for test
                on_progress=on_progress,
            )

            assert isinstance(result, Instance)
            assert result.status == "running"
            assert len(progress_calls) >= 1  # Progress was reported
            mock_http.post.assert_called_once()

        finally:
            os.environ.pop("GRAPH_OLAP_SKIP_HEALTH_CHECK", None)

    def test_create_and_wait_timeout(
        self, mock_http: MagicMock, mock_config: MagicMock
    ):
        """Test create_and_wait raises TimeoutError."""
        import os

        os.environ["GRAPH_OLAP_SKIP_HEALTH_CHECK"] = "true"

        try:
            from graph_olap.exceptions import TimeoutError
            from graph_olap_schemas import WrapperType

            waiting_response = {
                "data": {
                    "id": 1,
                    "snapshot_id": 1,
                    "snapshot_name": "Auto-generated",
                    "owner_username": "test_user",
                    "wrapper_type": "falkordb",
                    "name": "Slow Instance",
                    "description": None,
                    "instance_url": None,
                    "explorer_url": None,
                    "status": "waiting_for_snapshot",
                    "error_message": None,
                    "created_at": "2025-01-15T10:30:00Z",
                    "updated_at": "2025-01-15T10:30:00Z",
                    "started_at": None,
                    "last_activity_at": None,
                    "ttl": None,
                    "inactivity_timeout": None,
                    "memory_usage_bytes": None,
                    "disk_usage_bytes": None,
                }
            }

            mock_http.post.return_value = waiting_response
            # Always return waiting status
            mock_http.get.return_value = {"data": waiting_response["data"]}

            resource = InstanceResource(mock_http, mock_config)

            with pytest.raises(TimeoutError) as exc_info:
                resource.create_and_wait(
                    mapping_id=1,
                    name="Slow Instance",
                    wrapper_type=WrapperType.FALKORDB,
                    timeout=0.05,  # Very short timeout
                    poll_interval=0.01,
                )

            assert "did not start within" in str(exc_info.value)

        finally:
            os.environ.pop("GRAPH_OLAP_SKIP_HEALTH_CHECK", None)

    def test_create_and_wait_instance_failed(
        self, mock_http: MagicMock, mock_config: MagicMock
    ):
        """Test create_and_wait raises InstanceFailedError."""
        import os

        os.environ["GRAPH_OLAP_SKIP_HEALTH_CHECK"] = "true"

        try:
            from graph_olap.exceptions import InstanceFailedError
            from graph_olap_schemas import WrapperType

            waiting_response = {
                "data": {
                    "id": 1,
                    "snapshot_id": 1,
                    "snapshot_name": "Auto-generated",
                    "owner_username": "test_user",
                    "wrapper_type": "falkordb",
                    "name": "Failing Instance",
                    "description": None,
                    "instance_url": None,
                    "explorer_url": None,
                    "status": "waiting_for_snapshot",
                    "error_message": None,
                    "created_at": "2025-01-15T10:30:00Z",
                    "updated_at": "2025-01-15T10:30:00Z",
                    "started_at": None,
                    "last_activity_at": None,
                    "ttl": None,
                    "inactivity_timeout": None,
                    "memory_usage_bytes": None,
                    "disk_usage_bytes": None,
                }
            }

            failed_response = {
                "data": {
                    **waiting_response["data"],
                    "status": "failed",
                    "error_message": "Pod failed to start",
                }
            }

            mock_http.post.return_value = waiting_response
            # First returns waiting, then failed
            mock_http.get.side_effect = [
                {"data": waiting_response["data"]},
                {"data": failed_response["data"]},
            ]

            resource = InstanceResource(mock_http, mock_config)

            with pytest.raises(InstanceFailedError) as exc_info:
                resource.create_and_wait(
                    mapping_id=1,
                    name="Failing Instance",
                    wrapper_type=WrapperType.FALKORDB,
                    poll_interval=0.01,
                )

            assert "failed" in str(exc_info.value).lower()

        finally:
            os.environ.pop("GRAPH_OLAP_SKIP_HEALTH_CHECK", None)

    def test_create_and_wait_with_all_params(
        self, mock_http: MagicMock, mock_config: MagicMock
    ):
        """Test create_and_wait passes all parameters."""
        import os

        os.environ["GRAPH_OLAP_SKIP_HEALTH_CHECK"] = "true"

        try:
            from graph_olap_schemas import WrapperType

            running_response = {
                "data": {
                    "id": 1,
                    "snapshot_id": 1,
                    "snapshot_name": "Auto-generated",
                    "owner_username": "test_user",
                    "wrapper_type": "ryugraph",
                    "name": "Full Params Instance",
                    "description": "Test description",
                    "instance_url": "https://instance-1.example.com",
                    "explorer_url": "https://instance-1.example.com/explorer",
                    "status": "running",
                    "error_message": None,
                    "created_at": "2025-01-15T10:30:00Z",
                    "updated_at": "2025-01-15T10:35:00Z",
                    "started_at": "2025-01-15T10:35:00Z",
                    "last_activity_at": None,
                    "ttl": "PT48H",
                    "inactivity_timeout": "PT12H",
                    "memory_usage_bytes": None,
                    "disk_usage_bytes": None,
                }
            }

            mock_http.post.return_value = {"data": {**running_response["data"], "status": "waiting_for_snapshot"}}
            mock_http.get.return_value = running_response

            resource = InstanceResource(mock_http, mock_config)
            result = resource.create_and_wait(
                mapping_id=5,
                name="Full Params Instance",
                wrapper_type=WrapperType.RYUGRAPH,
                mapping_version=2,
                description="Test description",
                ttl=48,
                inactivity_timeout="PT12H",
                poll_interval=0.01,
            )

            assert result.status == "running"

            # Verify POST was called with all params
            call_args = mock_http.post.call_args
            body = call_args[1]["json"]
            assert body["mapping_id"] == 5
            assert body["name"] == "Full Params Instance"
            assert body["wrapper_type"] == "ryugraph"
            assert body["mapping_version"] == 2
            assert body["description"] == "Test description"
            assert body["ttl"] == "PT48H"
            assert body["inactivity_timeout"] == "PT12H"

        finally:
            os.environ.pop("GRAPH_OLAP_SKIP_HEALTH_CHECK", None)
