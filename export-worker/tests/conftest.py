"""Shared test fixtures and configuration.

This module provides:
- Sample data fixtures (requests, definitions, export jobs)
- Mock client fixtures (ADR-025 database polling architecture)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from export_worker.clients import ControlPlaneClient, GCSClient, StarburstClient
from export_worker.clients.starburst import QueryPollResult, QuerySubmissionResult
from export_worker.models import (
    EdgeDefinition,
    ExportJob,
    ExportJobStatus,
    NodeDefinition,
    PrimaryKeyDefinition,
    PropertyDefinition,
    SnapshotJobsResult,
    SnapshotRequest,
    SnapshotStatus,
)

# =============================================================================
# Sample Data Fixtures
# =============================================================================


@pytest.fixture
def sample_node_definition() -> NodeDefinition:
    """Sample node definition for testing."""
    return NodeDefinition(
        label="Customer",
        sql="SELECT customer_id, name, email, city FROM analytics.customers",
        primary_key=PrimaryKeyDefinition(name="customer_id", type="STRING"),
        properties=[
            PropertyDefinition(name="name", type="STRING"),
            PropertyDefinition(name="email", type="STRING"),
            PropertyDefinition(name="city", type="STRING"),
        ],
    )


@pytest.fixture
def sample_edge_definition() -> EdgeDefinition:
    """Sample edge definition for testing."""
    return EdgeDefinition(
        type="PURCHASED",
        from_node="Customer",
        to_node="Product",
        sql="SELECT customer_id, product_id, amount, purchase_date FROM analytics.transactions",
        from_key="customer_id",
        to_key="product_id",
        properties=[
            PropertyDefinition(name="amount", type="DOUBLE"),
            PropertyDefinition(name="purchase_date", type="DATE"),
        ],
    )


@pytest.fixture
def sample_snapshot_request(
    sample_node_definition: NodeDefinition,
    sample_edge_definition: EdgeDefinition,
) -> SnapshotRequest:
    """Sample snapshot request for testing."""
    return SnapshotRequest(
        snapshot_id=123,
        mapping_id=45,
        mapping_version=3,
        gcs_base_path="gs://test-bucket/user-123/mapping-45/snapshot-123/",
        node_definitions=[sample_node_definition],
        edge_definitions=[sample_edge_definition],
        starburst_catalog="analytics",
        created_at="2025-01-15T10:00:00Z",
    )


@pytest.fixture
def sample_snapshot_request_nodes_only(
    sample_node_definition: NodeDefinition,
) -> SnapshotRequest:
    """Snapshot request with nodes only (no edges)."""
    return SnapshotRequest(
        snapshot_id=124,
        mapping_id=46,
        mapping_version=1,
        gcs_base_path="gs://test-bucket/user-123/mapping-46/snapshot-124/",
        node_definitions=[sample_node_definition],
        edge_definitions=[],
        starburst_catalog="analytics",
        created_at="2025-01-15T11:00:00Z",
    )


@pytest.fixture
def sample_pending_export_job() -> ExportJob:
    """Sample pending export job (after claim) with denormalized data."""
    return ExportJob(
        id=1,
        snapshot_id=123,
        job_type="node",
        entity_name="Customer",
        status=ExportJobStatus.PENDING,
        sql="SELECT customer_id, name, email FROM analytics.customers",
        column_names=["customer_id", "name", "email"],
        starburst_catalog="analytics",
        starburst_role="test-use-case",
        gcs_path="gs://test-bucket/exports/nodes/Customer/",
        claimed_by="worker-123",
        claimed_at="2025-01-15T10:00:00Z",
    )


@pytest.fixture
def sample_submitted_export_job() -> ExportJob:
    """Sample submitted export job ready for polling."""
    return ExportJob(
        id=1,
        snapshot_id=123,
        job_type="node",
        entity_name="Customer",
        status=ExportJobStatus.SUBMITTED,
        sql="SELECT customer_id, name, email FROM analytics.customers",
        column_names=["customer_id", "name", "email"],
        starburst_catalog="analytics",
        gcs_path="gs://test-bucket/exports/nodes/Customer/",
        starburst_query_id="query-123",
        next_uri="http://starburst/v1/query/123/1",
        next_poll_at="2025-01-15T10:00:05Z",
        poll_count=1,
        submitted_at="2025-01-15T10:00:00Z",
    )


@pytest.fixture
def sample_export_jobs() -> list[ExportJob]:
    """Create sample export jobs for testing."""
    return [
        ExportJob(
            id=1,
            snapshot_id=123,
            job_type="node",
            entity_name="Customer",
            status=ExportJobStatus.PENDING,
            sql="SELECT id, name FROM customers",
            column_names=["id", "name"],
            starburst_catalog="analytics",
            starburst_role="test-use-case",
            gcs_path="gs://test-bucket/exports/nodes/Customer/",
            claimed_by="worker-123",
            claimed_at="2025-01-15T10:00:00Z",
        ),
        ExportJob(
            id=2,
            snapshot_id=123,
            job_type="edge",
            entity_name="PURCHASED",
            status=ExportJobStatus.PENDING,
            sql="SELECT customer_id, product_id FROM purchases",
            column_names=["customer_id", "product_id"],
            starburst_catalog="analytics",
            starburst_role="test-use-case",
            gcs_path="gs://test-bucket/exports/edges/PURCHASED/",
            claimed_by="worker-123",
            claimed_at="2025-01-15T10:00:00Z",
        ),
    ]


# =============================================================================
# Mock Client Fixtures
# =============================================================================


@pytest.fixture
def mock_starburst_client() -> MagicMock:
    """Mock Starburst client."""
    client = MagicMock(spec=StarburstClient)
    client.client_tags = ["graph-olap-export"]
    client.source = "graph-olap-export-worker"

    # Async API
    client.submit_unload_async = MagicMock(
        return_value=QuerySubmissionResult(
            query_id="test-query-id",
            next_uri="http://starburst/v1/query/test-query-id/1",
        )
    )
    client.poll_query_async = MagicMock(
        return_value=QueryPollResult(
            state="FINISHED",
            next_uri=None,
            error_message=None,
        )
    )
    return client


@pytest.fixture
def mock_gcs_client() -> MagicMock:
    """Mock GCS client."""
    client = MagicMock(spec=GCSClient)
    client.count_parquet_rows = MagicMock(return_value=(1000, 1024 * 1024))  # (rows, bytes)
    client.calculate_total_size = MagicMock(return_value=1024 * 1024)  # 1MB
    client.list_files = MagicMock(return_value=[])
    return client


@pytest.fixture
def mock_control_plane_client() -> MagicMock:
    """Mock Control Plane client (ADR-025)."""
    client = MagicMock(spec=ControlPlaneClient)
    client.update_snapshot_status = MagicMock(return_value=None)
    client.get_snapshot_status = MagicMock(return_value=SnapshotStatus.EXPORTING)
    client.is_cancelled = MagicMock(return_value=False)

    # ADR-025: Database polling endpoints
    client.claim_export_jobs = MagicMock(return_value=[])
    client.get_pollable_export_jobs = MagicMock(return_value=[])

    # Export job methods
    client.update_export_job = MagicMock(
        return_value=ExportJob(
            id=1,
            snapshot_id=123,
            job_type="node",
            entity_name="Customer",
            status=ExportJobStatus.COMPLETED,
            gcs_path="gs://test-bucket/path/",
            row_count=1000,
            size_bytes=1024 * 1024,
        )
    )
    client.get_export_job = MagicMock(
        return_value=ExportJob(
            id=1,
            snapshot_id=123,
            job_type="node",
            entity_name="Customer",
            status=ExportJobStatus.SUBMITTED,
            gcs_path="gs://test-bucket/path/",
            starburst_query_id="test-query-id",
            next_uri="http://starburst/v1/query/test-query-id/1",
        )
    )
    client.list_export_jobs = MagicMock(return_value=[])
    client.get_snapshot_jobs_result = MagicMock(
        return_value=SnapshotJobsResult(
            all_complete=True,
            any_failed=False,
            node_counts={"Customer": 1000},
            edge_counts={},
            total_size=1024 * 1024,
        )
    )
    client.finalize_snapshot = MagicMock(return_value=None)
    return client


# =============================================================================
# Environment Fixtures
# =============================================================================


@pytest.fixture
def mock_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set up mock environment variables (ADR-025)."""
    monkeypatch.setenv("STARBURST_URL", "http://starburst.test:8080")
    monkeypatch.setenv("STARBURST_USER", "test_user")
    monkeypatch.setenv("STARBURST_PASSWORD", "test_password")
    monkeypatch.setenv("STARBURST_CATALOG", "analytics")
    monkeypatch.setenv("STARBURST_CLIENT_TAGS", "graph-olap-export")
    monkeypatch.setenv("STARBURST_SOURCE", "graph-olap-export-worker")
    monkeypatch.setenv("GCP_PROJECT", "test-project")
    monkeypatch.setenv("CONTROL_PLANE_URL", "http://control-plane.test:8080")
    monkeypatch.setenv("POLL_INTERVAL_SECONDS", "5")
    monkeypatch.setenv("EMPTY_POLL_BACKOFF_SECONDS", "10")
    monkeypatch.setenv("CLAIM_LIMIT", "10")
    monkeypatch.setenv("POLL_LIMIT", "10")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")


# =============================================================================
# HTTP Mocking Fixtures
# =============================================================================


@pytest.fixture
def respx_mock():
    """RESPX mock for httpx requests.

    Usage:
        def test_something(respx_mock):
            respx_mock.post("http://example.com/api").respond(200, json={"ok": True})
    """
    import respx

    with respx.mock(assert_all_called=False) as respx_mock:
        yield respx_mock
