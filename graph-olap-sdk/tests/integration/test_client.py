"""Integration tests for GraphOLAPClient with mocked API."""

from __future__ import annotations

import httpx
import pytest
import respx
from graph_olap_schemas import WrapperType

from graph_olap import GraphOLAPClient
from graph_olap.models import Instance, Mapping, Snapshot


class TestClientInitialization:
    """Tests for GraphOLAPClient initialization."""

    def test_init_with_username(self):
        """Test client initialization with username."""
        client = GraphOLAPClient(
            api_url="https://api.example.com",
            username="test-user@example.com",
        )

        assert client._http.base_url == "https://api.example.com"
        assert client._http.username == "test-user@example.com"
        client.close()

    def test_context_manager(self):
        """Test client as context manager."""
        with GraphOLAPClient(
            api_url="https://api.example.com",
            username="test-user@example.com",
        ) as client:
            assert client.mappings is not None
            assert client.snapshots is not None
            assert client.instances is not None

    def test_has_all_resources(self):
        """Test client has all resource managers."""
        with GraphOLAPClient(api_url="https://api.example.com") as client:
            assert hasattr(client, "mappings")
            assert hasattr(client, "snapshots")
            assert hasattr(client, "instances")
            assert hasattr(client, "favorites")


class TestMappingWorkflow:
    """Integration tests for mapping CRUD workflow."""

    @respx.mock
    def test_list_mappings(self):
        """Test listing mappings."""
        respx.get("https://api.example.com/api/mappings").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": 1,
                            "owner_username": "test_user",
            "wrapper_type": "ryugraph",                            "name": "Customer Graph",
                            "description": None,
                            "current_version": 1,
                            "created_at": "2025-01-15T10:30:00Z",
                            "updated_at": "2025-01-15T10:30:00Z",
                            "ttl": None,
                            "inactivity_timeout": None,
                            "snapshot_count": 0,
                            "version": None,
                        }
                    ],
                    "meta": {"total": 1, "offset": 0, "limit": 50},
                },
            )
        )

        with GraphOLAPClient(api_url="https://api.example.com") as client:
            mappings = client.mappings.list()

            assert len(mappings) == 1
            assert mappings[0].name == "Customer Graph"

    @respx.mock
    def test_create_and_get_mapping(self):
        """Test creating and retrieving a mapping."""
        mapping_data = {
            "id": 1,
            "owner_username": "test_user",
            "wrapper_type": "ryugraph",            "name": "New Mapping",
            "description": "Test description",
            "current_version": 1,
            "created_at": "2025-01-15T10:30:00Z",
            "updated_at": "2025-01-15T10:30:00Z",
            "ttl": None,
            "inactivity_timeout": None,
            "snapshot_count": 0,
            "version": {
                "mapping_id": 1,
                "version": 1,
                "change_description": "Initial version",
                "node_definitions": [
                    {
                        "label": "Customer",
                        "sql": "SELECT * FROM customers",
                        "primary_key": {"name": "id", "type": "STRING"},
                        "properties": [],
                    }
                ],
                "edge_definitions": [],
                "created_at": "2025-01-15T10:30:00Z",
                "created_by": "user-1",
                "created_by_name": "Test User",
            },
        }

        respx.post("https://api.example.com/api/mappings").mock(
            return_value=httpx.Response(201, json={"data": mapping_data})
        )
        respx.get("https://api.example.com/api/mappings/1").mock(
            return_value=httpx.Response(200, json={"data": mapping_data})
        )

        with GraphOLAPClient(api_url="https://api.example.com") as client:
            # Create
            created = client.mappings.create(
                name="New Mapping",
                description="Test description",
                node_definitions=[
                    {
                        "label": "Customer",
                        "sql": "SELECT * FROM customers",
                        "primary_key": {"name": "id", "type": "STRING"},
                        "properties": [],
                    }
                ],
            )

            assert isinstance(created, Mapping)
            assert created.name == "New Mapping"

            # Get
            retrieved = client.mappings.get(1)
            assert retrieved.id == 1
            assert retrieved.name == "New Mapping"

    @respx.mock
    def test_update_mapping(self):
        """Test updating a mapping creates new version."""
        respx.put("https://api.example.com/api/mappings/1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "id": 1,
                        "owner_username": "test_user",
            "wrapper_type": "ryugraph",                        "name": "Updated Mapping",
                        "description": None,
                        "current_version": 2,
                        "created_at": "2025-01-15T10:30:00Z",
                        "updated_at": "2025-01-15T11:00:00Z",
                        "ttl": None,
                        "inactivity_timeout": None,
                        "snapshot_count": 0,
                        "version": None,
                    }
                },
            )
        )

        with GraphOLAPClient(api_url="https://api.example.com") as client:
            updated = client.mappings.update(
                mapping_id=1,
                change_description="Updated name",
                name="Updated Mapping",
            )

            assert updated.name == "Updated Mapping"
            assert updated.current_version == 2

    @respx.mock
    def test_delete_mapping(self):
        """Test deleting a mapping."""
        respx.delete("https://api.example.com/api/mappings/1").mock(
            return_value=httpx.Response(204)
        )

        with GraphOLAPClient(api_url="https://api.example.com") as client:
            client.mappings.delete(1)


# =============================================================================
# SNAPSHOT TESTS DISABLED
# These tests are commented out as snapshot functionality has been disabled.
# =============================================================================
# class TestSnapshotWorkflow:
#     """Integration tests for snapshot workflow."""
#
#     @respx.mock
#     def test_create_snapshot(self):
#         """Test creating a snapshot."""
#         snapshot_data = {
#             "id": 1,
#             "mapping_id": 1,
#             "mapping_name": "Customer Graph",
#             "mapping_version": 1,
#             "owner_username": "test_user",
#             "wrapper_type": "ryugraph",            "name": "Analysis Snapshot",
#             "description": None,
#             "gcs_path": None,
#             "size_bytes": None,
#             "node_counts": None,
#             "edge_counts": None,
#             "status": "creating",
#             "error_message": None,
#             "created_at": "2025-01-15T10:30:00Z",
#             "updated_at": "2025-01-15T10:30:00Z",
#             "ttl": "P7D",
#             "inactivity_timeout": "PT24H",
#             "instance_count": 0,
#         }
#
#         respx.post("https://api.example.com/api/snapshots").mock(
#             return_value=httpx.Response(202, json={"data": snapshot_data})
#         )
#
#         with GraphOLAPClient(api_url="https://api.example.com") as client:
#             snapshot = client.snapshots.create(
#                 mapping_id=1,
#                 name="Analysis Snapshot",
#             )
#
#             assert isinstance(snapshot, Snapshot)
#             assert snapshot.status == "creating"
#             assert snapshot.is_ready is False
#
#     @respx.mock
#     def test_get_snapshot_progress(self):
#         """Test getting snapshot creation progress."""
#         respx.get("https://api.example.com/api/snapshots/1/progress").mock(
#             return_value=httpx.Response(
#                 200,
#                 json={
#                     "data": {
#                         "jobs_total": 4,
#                         "jobs_pending": 0,
#                         "jobs_claimed": 0,
#                         "jobs_submitted": 2,
#                         "jobs_completed": 2,
#                         "jobs_failed": 0,
#                         "jobs": [
#                             {"name": "Person", "type": "node", "status": "completed", "row_count": 100},
#                             {"name": "Company", "type": "node", "status": "completed", "row_count": 50},
#                             {"name": "WORKS_AT", "type": "edge", "status": "running", "row_count": None},
#                             {"name": "KNOWS", "type": "edge", "status": "pending", "row_count": None},
#                         ],
#                     }
#                 },
#             )
#         )
#
#         with GraphOLAPClient(api_url="https://api.example.com") as client:
#             progress = client.snapshots.get_progress(1)
#
#             assert progress.progress_percent == 50  # 2 completed out of 4
#             assert progress.jobs_total == 4
#             assert progress.jobs_completed == 2
#
#     @respx.mock
#     def test_list_snapshots_for_mapping(self):
#         """Test listing snapshots for a mapping."""
#         respx.get("https://api.example.com/api/mappings/1/snapshots").mock(
#             return_value=httpx.Response(
#                 200,
#                 json={
#                     "data": [
#                         {
#                             "id": 1,
#                             "mapping_id": 1,
#                             "mapping_name": "Customer Graph",
#                             "mapping_version": 1,
#                             "owner_username": "test_user",
#             "wrapper_type": "ryugraph",                            "name": "Snapshot 1",
#                             "description": None,
#                             "gcs_path": "gs://bucket/1",
#                             "size_bytes": 100 * 1024 * 1024,
#                             "node_counts": {"Customer": 10000},
#                             "edge_counts": {"PURCHASED": 50000},
#                             "status": "ready",
#                             "error_message": None,
#                             "created_at": "2025-01-15T10:30:00Z",
#                             "updated_at": "2025-01-15T10:35:00Z",
#                             "ttl": None,
#                             "inactivity_timeout": None,
#                             "instance_count": 1,
#                         }
#                     ],
#                     "meta": {"total": 1, "offset": 0, "limit": 50},
#                 },
#             )
#         )
#
#         with GraphOLAPClient(api_url="https://api.example.com") as client:
#             snapshots = client.mappings.list_snapshots(1)
#
#             assert len(snapshots) == 1
#             assert snapshots[0].is_ready is True


class TestInstanceWorkflow:
    """Integration tests for instance workflow."""

    @respx.mock
    def test_create_instance(self):
        """Test creating an instance with ryugraph wrapper."""
        instance_data = {
            "id": 1,
            "snapshot_id": 1,
            "snapshot_name": "Analysis Snapshot",
            "owner_username": "test_user",
            "wrapper_type": "ryugraph",            "name": "Analysis Instance",
            "description": None,
            "instance_url": None,
            "explorer_url": None,
            "status": "starting",
            "error_message": None,
            "created_at": "2025-01-15T10:30:00Z",
            "updated_at": "2025-01-15T10:30:00Z",
            "started_at": None,
            "last_activity_at": None,
            "ttl": "PT24H",
            "inactivity_timeout": "PT8H",
            "memory_usage_bytes": None,
            "disk_usage_bytes": None,
            "wrapper_type": "ryugraph",
        }

        respx.post("https://api.example.com/api/instances").mock(
            return_value=httpx.Response(202, json={"data": instance_data})
        )

        with GraphOLAPClient(api_url="https://api.example.com") as client:
            instance = client.instances.create(
                snapshot_id=1,
                name="Analysis Instance",
                wrapper_type=WrapperType.RYUGRAPH,
            )

            assert isinstance(instance, Instance)
            assert instance.wrapper_type == WrapperType.RYUGRAPH
            assert instance.status == "starting"
            assert instance.is_running is False

    @respx.mock
    def test_get_running_instance(self):
        """Test getting a running instance."""
        instance_data = {
            "id": 1,
            "snapshot_id": 1,
            "snapshot_name": "Analysis Snapshot",
            "owner_username": "test_user",
            "wrapper_type": "ryugraph",            "name": "Analysis Instance",
            "description": None,
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

        respx.get("https://api.example.com/api/instances/1").mock(
            return_value=httpx.Response(200, json={"data": instance_data})
        )

        with GraphOLAPClient(api_url="https://api.example.com") as client:
            instance = client.instances.get(1)

            assert instance.is_running is True
            assert instance.instance_url == "https://instance-1.example.com"
            assert instance.memory_mb == pytest.approx(512.0, rel=0.01)

    @respx.mock
    def test_terminate_instance(self):
        """Test terminating an instance (REST: DELETE /api/instances/{id})."""
        respx.delete("https://api.example.com/api/instances/1").mock(
            return_value=httpx.Response(204)
        )

        with GraphOLAPClient(api_url="https://api.example.com") as client:
            client.instances.terminate(1)

    @respx.mock
    def test_create_instance_with_wrapper_type(self):
        """Test creating an instance with explicit wrapper_type."""
        instance_data = {
            "id": 2,
            "snapshot_id": 1,
            "snapshot_name": "Analysis Snapshot",
            "owner_username": "test_user",
            "wrapper_type": "ryugraph",            "name": "FalkorDB Instance",
            "description": None,
            "instance_url": None,
            "explorer_url": None,
            "status": "starting",
            "error_message": None,
            "created_at": "2025-01-15T10:30:00Z",
            "updated_at": "2025-01-15T10:30:00Z",
            "started_at": None,
            "last_activity_at": None,
            "ttl": "PT24H",
            "inactivity_timeout": "PT8H",
            "memory_usage_bytes": None,
            "disk_usage_bytes": None,
            "wrapper_type": "falkordb",
        }

        respx.post("https://api.example.com/api/instances").mock(
            return_value=httpx.Response(202, json={"data": instance_data})
        )

        with GraphOLAPClient(api_url="https://api.example.com") as client:
            instance = client.instances.create(
                snapshot_id=1,
                name="FalkorDB Instance",
                wrapper_type=WrapperType.FALKORDB,
            )

            assert isinstance(instance, Instance)
            assert instance.wrapper_type == WrapperType.FALKORDB
            assert instance.status == "starting"

    @respx.mock
    def test_get_instance_with_wrapper_type(self):
        """Test getting an instance returns wrapper_type field."""
        instance_data = {
            "id": 2,
            "snapshot_id": 1,
            "snapshot_name": "Analysis Snapshot",
            "owner_username": "test_user",
            "wrapper_type": "ryugraph",            "name": "FalkorDB Instance",
            "description": None,
            "instance_url": "https://instance-2.example.com",
            "explorer_url": "https://instance-2.example.com/explorer",
            "status": "running",
            "error_message": None,
            "created_at": "2025-01-15T10:30:00Z",
            "updated_at": "2025-01-15T10:35:00Z",
            "started_at": "2025-01-15T10:35:00Z",
            "last_activity_at": "2025-01-15T11:00:00Z",
            "ttl": "PT24H",
            "inactivity_timeout": "PT8H",
            "memory_usage_bytes": 1024 * 1024 * 1024,
            "disk_usage_bytes": 2048 * 1024 * 1024,
            "wrapper_type": "falkordb",
        }

        respx.get("https://api.example.com/api/instances/2").mock(
            return_value=httpx.Response(200, json={"data": instance_data})
        )

        with GraphOLAPClient(api_url="https://api.example.com") as client:
            instance = client.instances.get(2)

            assert instance.is_running is True
            assert instance.wrapper_type == WrapperType.FALKORDB
            assert instance.memory_mb == pytest.approx(1024.0, rel=0.01)


class TestQueryWorkflow:
    """Integration tests for query execution."""

    @respx.mock
    def test_execute_cypher_query(self):
        """Test executing a Cypher query."""
        # Get instance with URL
        instance_data = {
            "id": 1,
            "snapshot_id": 1,
            "snapshot_name": "Analysis Snapshot",
            "owner_username": "test_user",
            "wrapper_type": "ryugraph",            "name": "Analysis Instance",
            "description": None,
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

        respx.get("https://api.example.com/api/instances/1").mock(
            return_value=httpx.Response(200, json={"data": instance_data})
        )

        # Health check endpoint
        respx.get("https://instance-1.example.com/health").mock(
            return_value=httpx.Response(200, json={"status": "healthy"})
        )

        # Query execution (wrapper API returns direct response, no data wrapper)
        respx.post("https://instance-1.example.com/query").mock(
            return_value=httpx.Response(
                200,
                json={
                    "columns": ["name", "age"],
                    "column_types": ["STRING", "INT64"],
                    "rows": [
                        ["Alice", 30],
                        ["Bob", 25],
                    ],
                    "row_count": 2,
                    "execution_time_ms": 15,
                },
            )
        )

        with GraphOLAPClient(api_url="https://api.example.com") as client:
            conn = client.instances.connect(1)
            result = conn.query("MATCH (n:Customer) RETURN n.name AS name, n.age AS age")

            assert result.columns == ["name", "age"]
            assert result.row_count == 2
            assert list(result)[0]["name"] == "Alice"


class TestQuickStartWorkflow:
    """Integration tests for quick_start convenience method."""

    @respx.mock
    def test_quick_start_from_mapping(self):
        """Test quick_start creates snapshot and instance from mapping."""
        # Get mapping
        mapping_data = {
            "id": 1,
            "owner_username": "test_user",
            "wrapper_type": "ryugraph",            "name": "Customer Graph",
            "description": None,
            "current_version": 1,
            "created_at": "2025-01-15T10:30:00Z",
            "updated_at": "2025-01-15T10:30:00Z",
            "ttl": None,
            "inactivity_timeout": None,
            "snapshot_count": 0,
            "version": None,
        }

        respx.get("https://api.example.com/api/mappings/1").mock(
            return_value=httpx.Response(200, json={"data": mapping_data})
        )

        # Create snapshot
        snapshot_creating = {
            "id": 1,
            "mapping_id": 1,
            "mapping_name": "Customer Graph",
            "mapping_version": 1,
            "owner_username": "test_user",
            "wrapper_type": "ryugraph",            "name": "Quick Start Snapshot",
            "description": None,
            "gcs_path": None,
            "size_bytes": None,
            "node_counts": None,
            "edge_counts": None,
            "status": "creating",
            "error_message": None,
            "created_at": "2025-01-15T10:30:00Z",
            "updated_at": "2025-01-15T10:30:00Z",
            "ttl": None,
            "inactivity_timeout": None,
            "instance_count": 0,
        }

        snapshot_ready = {**snapshot_creating, "status": "ready"}

        respx.post("https://api.example.com/api/snapshots").mock(
            return_value=httpx.Response(202, json={"data": snapshot_creating})
        )

        # Poll for snapshot ready via progress
        respx.get("https://api.example.com/api/snapshots/1/progress").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "id": 1,
                        "status": "ready",
                        "phase": "ready",
                        "progress_percent": 100,
                        "steps": [],
                    }
                },
            )
        )

        # Get snapshot after ready
        respx.get("https://api.example.com/api/snapshots/1").mock(
            return_value=httpx.Response(200, json={"data": snapshot_ready})
        )

        # Create instance
        instance_starting = {
            "id": 1,
            "snapshot_id": 1,
            "snapshot_name": "Quick Start Snapshot",
            "owner_username": "test_user",
            "wrapper_type": "ryugraph",
            "name": "Quick Start Instance",
            "description": None,
            "instance_url": None,
            "explorer_url": None,
            "status": "starting",
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

        instance_running = {
            **instance_starting,
            "status": "running",
            "instance_url": "https://instance-1.example.com",
        }

        respx.post("https://api.example.com/api/instances").mock(
            return_value=httpx.Response(202, json={"data": instance_starting})
        )

        # Poll for instance running via progress
        respx.get("https://api.example.com/api/instances/1/progress").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "id": 1,
                        "status": "running",
                        "phase": "running",
                        "progress_percent": 100,
                        "steps": [],
                    }
                },
            )
        )

        # Get instance after running
        respx.get("https://api.example.com/api/instances/1").mock(
            return_value=httpx.Response(200, json={"data": instance_running})
        )

        # Health check endpoint
        respx.get("https://instance-1.example.com/health").mock(
            return_value=httpx.Response(200, json={"status": "healthy"})
        )

        with GraphOLAPClient(api_url="https://api.example.com") as client:
            conn = client.quick_start(mapping_id=1, wrapper_type=WrapperType.RYUGRAPH)

            assert conn is not None
            assert conn.instance_url == "https://instance-1.example.com"


class TestErrorHandling:
    """Integration tests for error handling."""

    @respx.mock
    def test_not_found_error(self):
        """Test NotFoundError is raised for 404."""
        from graph_olap.exceptions import NotFoundError

        respx.get("https://api.example.com/api/mappings/999").mock(
            return_value=httpx.Response(
                404,
                json={
                    "error": {
                        "code": "NOT_FOUND",
                        "message": "Mapping not found",
                    }
                },
            )
        )

        with GraphOLAPClient(api_url="https://api.example.com") as client:
            with pytest.raises(NotFoundError):
                client.mappings.get(999)

    @respx.mock
    def test_authentication_error(self):
        """Test AuthenticationError is raised for 401."""
        from graph_olap.exceptions import AuthenticationError

        respx.get("https://api.example.com/api/mappings").mock(
            return_value=httpx.Response(
                401,
                json={
                    "error": {
                        "code": "UNAUTHORIZED",
                        "message": "Invalid API key",
                    }
                },
            )
        )

        with GraphOLAPClient(api_url="https://api.example.com") as client:
            with pytest.raises(AuthenticationError):
                client.mappings.list()

    @respx.mock
    def test_concurrency_limit_error(self):
        """Test ConcurrencyLimitError is raised for 429."""
        from graph_olap.exceptions import ConcurrencyLimitError

        respx.post("https://api.example.com/api/instances").mock(
            return_value=httpx.Response(
                429,
                json={
                    "error": {
                        "code": "CONCURRENCY_LIMIT",
                        "message": "Instance limit reached",
                        "details": {"current_count": 5, "max_allowed": 5},
                    }
                },
            )
        )

        with GraphOLAPClient(api_url="https://api.example.com") as client:
            with pytest.raises(ConcurrencyLimitError) as exc_info:
                client.instances.create(snapshot_id=1, name="Test", wrapper_type=WrapperType.RYUGRAPH)

            assert exc_info.value.current_count == 5
            assert exc_info.value.max_allowed == 5
