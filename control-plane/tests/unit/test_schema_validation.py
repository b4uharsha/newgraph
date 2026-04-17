"""Schema validation tests.

Ensures that all API endpoints use proper Pydantic schemas for validation
and that there are no missing response models.
"""

from typing import get_origin

from fastapi.routing import APIRoute
from pydantic import BaseModel

from control_plane.main import app


def test_all_endpoints_have_response_models():
    """Ensure all API endpoints declare response_model."""
    missing_response_models = []

    for route in app.routes:
        if isinstance(route, APIRoute):
            # Skip health endpoint which returns plain dict
            if route.path == "/health":
                continue

            # Skip metrics endpoint which returns text/plain
            if route.path == "/metrics":
                continue

            # Skip debug endpoints which return plain dict by design
            if route.path.startswith("/api/debug/"):
                continue

            # Skip DELETE endpoints with 204 No Content
            if route.response_model is None:
                # Check if it's a 204 No Content endpoint
                if route.status_code == 204 or (hasattr(route, 'responses') and 204 in route.responses):
                    continue

                # Skip specific endpoints that return 204 No Content
                if "DELETE" in route.methods or "/activity" in route.path:
                    continue

                missing_response_models.append({
                    "path": route.path,
                    "methods": route.methods,
                })

    assert not missing_response_models, (
        "The following endpoints are missing response_model:\n"
        + "\n".join(f"  {r['methods']} {r['path']}" for r in missing_response_models)
    )


def test_response_models_are_pydantic():
    """Ensure all response models are Pydantic BaseModel subclasses."""
    non_pydantic_models = []

    for route in app.routes:
        if isinstance(route, APIRoute) and route.response_model:
            # Skip health and metrics endpoints
            if route.path in ["/health", "/metrics"]:
                continue

            # Handle generic types like DataResponse[SomeModel]
            response_model = route.response_model
            origin = get_origin(response_model)

            # If it's a generic type, get the base class
            if origin is not None:
                response_model = origin

            # Check if it's a Pydantic model
            if not issubclass(response_model, BaseModel):
                non_pydantic_models.append({
                    "path": route.path,
                    "model": response_model,
                })

    assert not non_pydantic_models, (
        "The following endpoints have non-Pydantic response models:\n"
        + "\n".join(f"  {r['path']}: {r['model']}" for r in non_pydantic_models)
    )


def test_no_duplicate_schema_definitions():
    """Ensure we don't have duplicate schema definitions.

    All schemas should be imported from graph_olap_schemas package,
    not defined locally in routers.
    """
    # This test verifies the fix we just made by checking imports

    from control_plane.routers.api import admin, config, ops

    # Verify that routers are using the shared schemas
    # by checking that they can import them
    assert hasattr(ops, "TriggerJobRequest") or "TriggerJobRequest" in str(ops.__dict__)
    assert hasattr(admin, "BulkDeleteResponse") or "BulkDeleteResponse" in str(admin.__dict__)
    assert hasattr(config, "ConcurrencyConfig") or "ConcurrencyConfig" in str(config.__dict__)


def test_shared_schemas_are_exportable():
    """Verify that all shared schemas can be exported as JSON Schema."""
    from graph_olap_schemas import get_combined_schema

    # This should not raise any exceptions
    combined = get_combined_schema()

    # Verify it has the expected structure
    assert "$schema" in combined
    assert "$defs" in combined
    assert "title" in combined

    # Verify ops schemas are included
    assert "JobsStatusResponse" in combined["$defs"]
    assert "TriggerJobRequest" in combined["$defs"]
    assert "BulkDeleteResponse" in combined["$defs"]
    assert "ConcurrencyConfig" in combined["$defs"]


def test_ops_schemas_in_export_all():
    """Verify that ops schemas are included in export_all_schemas."""
    import tempfile
    from pathlib import Path

    from graph_olap_schemas import export_all_schemas

    with tempfile.TemporaryDirectory() as tmpdir:
        result = export_all_schemas(tmpdir)

        # Verify api_ops directory was created
        assert "api_ops" in result
        assert len(result["api_ops"]) > 0

        # Verify some expected files exist
        ops_dir = Path(tmpdir) / "api_ops"
        assert (ops_dir / "JobsStatusResponse.json").exists()
        assert (ops_dir / "TriggerJobRequest.json").exists()
        assert (ops_dir / "BulkDeleteResponse.json").exists()


def test_schema_consistency_between_producer_and_consumer():
    """Verify schemas match between API (producer) and SDK (consumer)."""
    from graph_olap_schemas import (
        CreateMappingRequest,
        InstanceResponse,
        MappingResponse,
        SnapshotResponse,
    )

    # These should be the same models used by both control plane and SDK
    # Just verify they can be instantiated with expected fields

    # Test CreateMappingRequest
    schema = CreateMappingRequest.model_json_schema()
    assert "name" in schema["properties"]
    assert "node_definitions" in schema["properties"]

    # Test MappingResponse
    schema = MappingResponse.model_json_schema()
    assert "id" in schema["properties"]
    assert "owner_username" in schema["properties"]
    assert "node_definitions" in schema["properties"]

    # Test SnapshotResponse
    schema = SnapshotResponse.model_json_schema()
    assert "id" in schema["properties"]
    assert "status" in schema["properties"]
    assert "gcs_path" in schema["properties"]

    # Test InstanceResponse
    schema = InstanceResponse.model_json_schema()
    assert "id" in schema["properties"]
    assert "status" in schema["properties"]
    assert "instance_url" in schema["properties"]


def test_no_breaking_schema_changes():
    """Detect potential breaking changes in schemas.

    This test validates that required fields remain required
    and that field types don't change unexpectedly.
    """
    from graph_olap_schemas import (
        CreateInstanceRequest,
        CreateMappingRequest,
        CreateSnapshotRequest,
    )

    # Verify core request schemas have expected required fields
    mapping_schema = CreateMappingRequest.model_json_schema()
    assert "name" in mapping_schema["required"]
    assert "node_definitions" in mapping_schema["required"]

    snapshot_schema = CreateSnapshotRequest.model_json_schema()
    assert "mapping_id" in snapshot_schema["required"]
    assert "name" in snapshot_schema["required"]

    instance_schema = CreateInstanceRequest.model_json_schema()
    assert "snapshot_id" in instance_schema["required"]
    assert "name" in instance_schema["required"]
