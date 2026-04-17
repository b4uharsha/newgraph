"""Unit tests for Pydantic models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from export_worker.models import (
    EdgeDefinition,
    ExportPhase,
    NodeDefinition,
    PrimaryKeyDefinition,
    ProgressStep,
    PropertyDefinition,
    SnapshotProgress,
    SnapshotRequest,
    StepStatus,
)


class TestPropertyDefinition:
    """Tests for PropertyDefinition model."""

    def test_valid_property(self) -> None:
        """Test creating a valid property definition."""
        prop = PropertyDefinition(name="customer_id", type="STRING")
        assert prop.name == "customer_id"
        assert prop.type == "STRING"

    def test_empty_name_invalid(self) -> None:
        """Test that empty name is rejected."""
        with pytest.raises(ValidationError):
            PropertyDefinition(name="", type="STRING")

    def test_empty_type_invalid(self) -> None:
        """Test that empty type is rejected."""
        with pytest.raises(ValidationError):
            PropertyDefinition(name="id", type="")


class TestNodeDefinition:
    """Tests for NodeDefinition model."""

    def test_valid_node(self, sample_node_definition: NodeDefinition) -> None:
        """Test creating a valid node definition."""
        assert sample_node_definition.label == "Customer"
        assert sample_node_definition.primary_key.name == "customer_id"
        assert len(sample_node_definition.properties) == 3

    def test_column_names_order(self, sample_node_definition: NodeDefinition) -> None:
        """Test that column_names returns correct order (PK first)."""
        columns = sample_node_definition.column_names
        assert columns[0] == "customer_id"  # Primary key first
        assert columns[1:] == ["name", "email", "city"]

    def test_empty_label_invalid(self) -> None:
        """Test that empty label is rejected."""
        with pytest.raises(ValidationError):
            NodeDefinition(
                label="",
                sql="SELECT * FROM t",
                primary_key=PrimaryKeyDefinition(name="id", type="STRING"),
            )

    def test_empty_sql_invalid(self) -> None:
        """Test that empty SQL is rejected."""
        with pytest.raises(ValidationError):
            NodeDefinition(
                label="Test",
                sql="",
                primary_key=PrimaryKeyDefinition(name="id", type="STRING"),
            )


class TestEdgeDefinition:
    """Tests for EdgeDefinition model."""

    def test_valid_edge(self, sample_edge_definition: EdgeDefinition) -> None:
        """Test creating a valid edge definition."""
        assert sample_edge_definition.type == "PURCHASED"
        assert sample_edge_definition.from_node == "Customer"
        assert sample_edge_definition.to_node == "Product"

    def test_column_names_order(self, sample_edge_definition: EdgeDefinition) -> None:
        """Test that column_names returns correct order (from_key, to_key first)."""
        columns = sample_edge_definition.column_names
        assert columns[0] == "customer_id"  # from_key first
        assert columns[1] == "product_id"  # to_key second
        assert columns[2:] == ["amount", "purchase_date"]


# =============================================================================
# SNAPSHOT TESTS DISABLED
# These tests are commented out as snapshot functionality has been disabled.
# =============================================================================
# class TestSnapshotRequest:
#     """Tests for SnapshotRequest model."""
#
#     def test_valid_request(self, sample_snapshot_request: SnapshotRequest) -> None:
#         """Test creating a valid snapshot request."""
#         assert sample_snapshot_request.snapshot_id == 123
#         assert sample_snapshot_request.mapping_id == 45
#         assert len(sample_snapshot_request.node_definitions) == 1
#         assert len(sample_snapshot_request.edge_definitions) == 1
#
#     def test_gcs_path_validation_requires_gs_prefix(self) -> None:
#         """Test that GCS path must start with gs://."""
#         with pytest.raises(ValidationError) as exc_info:
#             SnapshotRequest(
#                 snapshot_id=1,
#                 mapping_id=1,
#                 mapping_version=1,
#                 gcs_base_path="/bucket/path/",  # Missing gs://
#                 node_definitions=[
#                     NodeDefinition(
#                         label="Test",
#                         sql="SELECT * FROM t",
#                         primary_key=PrimaryKeyDefinition(name="id", type="STRING"),
#                     )
#                 ],
#                 edge_definitions=[],
#                 starburst_catalog="analytics",
#                 created_at="2025-01-15T10:00:00Z",
#             )
#         assert "must start with gs://" in str(exc_info.value)
#
#     def test_gcs_path_adds_trailing_slash(self) -> None:
#         """Test that GCS path gets trailing slash added if missing."""
#         request = SnapshotRequest(
#             snapshot_id=1,
#             mapping_id=1,
#             mapping_version=1,
#             gcs_base_path="gs://bucket/path",  # No trailing slash
#             node_definitions=[
#                 NodeDefinition(
#                     label="Test",
#                     sql="SELECT * FROM t",
#                     primary_key=PrimaryKeyDefinition(name="id", type="STRING"),
#                 )
#             ],
#             edge_definitions=[],
#             starburst_catalog="analytics",
#             created_at="2025-01-15T10:00:00Z",
#         )
#         assert request.gcs_base_path.endswith("/")
#
#     def test_get_node_gcs_path(self, sample_snapshot_request: SnapshotRequest) -> None:
#         """Test getting node GCS path."""
#         path = sample_snapshot_request.get_node_gcs_path("Customer")
#         assert path == "gs://test-bucket/user-123/mapping-45/snapshot-123/nodes/Customer/"
#
#     def test_get_edge_gcs_path(self, sample_snapshot_request: SnapshotRequest) -> None:
#         """Test getting edge GCS path."""
#         path = sample_snapshot_request.get_edge_gcs_path("PURCHASED")
#         assert path == "gs://test-bucket/user-123/mapping-45/snapshot-123/edges/PURCHASED/"
#
#     def test_requires_at_least_one_node(self) -> None:
#         """Test that at least one node definition is required."""
#         with pytest.raises(ValidationError):
#             SnapshotRequest(
#                 snapshot_id=1,
#                 mapping_id=1,
#                 mapping_version=1,
#                 gcs_base_path="gs://bucket/path/",
#                 node_definitions=[],  # Empty!
#                 edge_definitions=[],
#                 starburst_catalog="analytics",
#                 created_at="2025-01-15T10:00:00Z",
#             )
#
#     def test_snapshot_id_must_be_positive(self) -> None:
#         """Test that snapshot_id must be positive."""
#         with pytest.raises(ValidationError):
#             SnapshotRequest(
#                 snapshot_id=0,  # Must be > 0
#                 mapping_id=1,
#                 mapping_version=1,
#                 gcs_base_path="gs://bucket/path/",
#                 node_definitions=[
#                     NodeDefinition(
#                         label="Test",
#                         sql="SELECT * FROM t",
#                         primary_key=PrimaryKeyDefinition(name="id", type="STRING"),
#                     )
#                 ],
#                 edge_definitions=[],
#                 starburst_catalog="analytics",
#                 created_at="2025-01-15T10:00:00Z",
#             )


# class TestSnapshotProgress:
#     """Tests for SnapshotProgress model."""
#
#     def test_initial_state(self) -> None:
#         """Test initial progress state."""
#         progress = SnapshotProgress()
#         assert progress.phase == ExportPhase.INITIALIZING
#         assert progress.current_step is None
#         assert progress.steps == []
#         assert progress.completed_at is None
#
#     def test_mark_step_started(self) -> None:
#         """Test marking a step as started."""
#         progress = SnapshotProgress()
#         progress.steps.append(ProgressStep(name="Customer", step_type="node"))
#
#         progress.mark_step_started("Customer")
#
#         assert progress.current_step == "Customer"
#         assert progress.steps[0].status == StepStatus.IN_PROGRESS
#         assert progress.steps[0].started_at is not None
#
#     def test_mark_step_completed(self) -> None:
#         """Test marking a step as completed."""
#         progress = SnapshotProgress()
#         progress.steps.append(ProgressStep(name="Customer", step_type="node"))
#
#         progress.mark_step_started("Customer")
#         progress.mark_step_completed("Customer", row_count=5000)
#
#         assert progress.current_step is None
#         assert progress.steps[0].status == StepStatus.COMPLETED
#         assert progress.steps[0].row_count == 5000
#         assert progress.steps[0].completed_at is not None
#
#     def test_mark_step_failed(self) -> None:
#         """Test marking a step as failed."""
#         progress = SnapshotProgress()
#         progress.steps.append(ProgressStep(name="Customer", step_type="node"))
#
#         progress.mark_step_started("Customer")
#         progress.mark_step_failed("Customer", error="Connection timeout")
#
#         assert progress.current_step is None
#         assert progress.steps[0].status == StepStatus.FAILED
#         assert progress.steps[0].error == "Connection timeout"
#
#     def test_get_node_counts(self) -> None:
#         """Test getting node counts."""
#         progress = SnapshotProgress()
#         progress.steps.append(ProgressStep(name="Customer", step_type="node"))
#         progress.steps.append(ProgressStep(name="Product", step_type="node"))
#         progress.steps.append(ProgressStep(name="PURCHASED", step_type="edge"))
#
#         progress.mark_step_completed("Customer", 1000)
#         progress.mark_step_completed("Product", 500)
#         progress.mark_step_completed("PURCHASED", 5000)
#
#         node_counts = progress.get_node_counts()
#         assert node_counts == {"Customer": 1000, "Product": 500}
#
#     def test_get_edge_counts(self) -> None:
#         """Test getting edge counts."""
#         progress = SnapshotProgress()
#         progress.steps.append(ProgressStep(name="Customer", step_type="node"))
#         progress.steps.append(ProgressStep(name="PURCHASED", step_type="edge"))
#
#         progress.mark_step_completed("Customer", 1000)
#         progress.mark_step_completed("PURCHASED", 5000)
#
#         edge_counts = progress.get_edge_counts()
#         assert edge_counts == {"PURCHASED": 5000}
#
#     def test_to_api_dict(self) -> None:
#         """Test conversion to API dict format."""
#         progress = SnapshotProgress()
#         progress.phase = ExportPhase.EXPORTING_NODES
#         progress.steps.append(ProgressStep(name="Customer", step_type="node"))
#         progress.mark_step_completed("Customer", 1000)
#
#         api_dict = progress.to_api_dict()
#
#         assert api_dict["phase"] == "exporting_nodes"
#         assert "started_at" in api_dict
#         assert len(api_dict["steps"]) == 1
#         assert api_dict["steps"][0]["name"] == "Customer"
#         assert api_dict["steps"][0]["status"] == "completed"
#         assert api_dict["steps"][0]["row_count"] == 1000
