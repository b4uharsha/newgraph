"""
JSON Schema generation utilities for the Graph OLAP schemas.

Provides functions to export Pydantic models as JSON Schema for:
- OpenAPI documentation
- Client code generation
- External system integration

Usage:
    from graph_olap_schemas.json_schema import (
        export_definition_schemas,
        export_api_schemas,
        export_all_schemas,
    )

    # Export all schemas to a directory
    export_all_schemas("/path/to/schemas")

    # Get specific schema as dict
    schema = get_schema(NodeDefinition)
"""

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from graph_olap_schemas.api_algorithms import (
    AlgorithmExecutionResponse,
    AlgorithmInfoResponse,
    AlgorithmListResponse,
    NativeAlgorithmRequest,
    NetworkXAlgorithmRequest,
)
from graph_olap_schemas.api_common import (
    DataResponse,
    ErrorResponse,
    PaginatedResponse,
)
from graph_olap_schemas.api_internal import (
    CreateExportJobsRequest,
    ExportJobResponse,
    InstanceMappingResponse,
    ShutdownRequest,
    ShutdownResponse,
    UpdateExportJobRequest,
    UpdateInstanceMetricsRequest,
    UpdateInstanceProgressRequest,
    UpdateInstanceStatusRequest,
    UpdateSnapshotStatusRequest,
)
from graph_olap_schemas.api_ops import (
    BulkDeleteRequest,
    BulkDeleteResponse,
    ConcurrencyConfig,
    ConcurrencyConfigResponse,
    ExportConfigRequest,
    ExportConfigResponse,
    ExportJobsListResponse,
    JobsStatusResponse,
    LifecycleConfigRequest,
    LifecycleConfigResponse,
    MaintenanceModeRequest,
    MaintenanceModeResponse,
    SystemStateResponse,
    TriggerJobRequest,
    TriggerJobResponse,
)
from graph_olap_schemas.api_resources import (
    CreateInstanceRequest,
    CreateMappingRequest,
    CreateSnapshotRequest,
    EdgeDiffResponse,
    InstanceResponse,
    MappingDiffResponse,
    MappingResponse,
    MappingVersionResponse,
    NodeDiffResponse,
    SnapshotResponse,
    UpdateLifecycleRequest,
    UpdateMappingRequest,
)
from graph_olap_schemas.api_schema import (
    CacheStatsResponse,
    CatalogResponse,
    ColumnResponse,
    SchemaResponse,
    TableResponse,
)
from graph_olap_schemas.api_wrapper import (
    EdgeTableSchema,
    HealthResponse,
    LockInfo,
    NodeTableSchema,
    QueryRequest,
    QueryResponse,
    StatusResponse,
    WrapperLockStatusResponse,
    WrapperSchemaResponse,
)
from graph_olap_schemas.definitions import (
    EdgeDefinition,
    NodeDefinition,
    PrimaryKeyDefinition,
    PropertyDefinition,
)


def get_schema(model: type[BaseModel]) -> dict[str, Any]:
    """
    Get JSON Schema for a Pydantic model.

    Args:
        model: The Pydantic model class

    Returns:
        JSON Schema as a dictionary
    """
    return model.model_json_schema()


def get_schema_json(model: type[BaseModel], indent: int = 2) -> str:
    """
    Get JSON Schema for a Pydantic model as a formatted JSON string.

    Args:
        model: The Pydantic model class
        indent: JSON indentation level

    Returns:
        JSON Schema as a formatted string
    """
    return json.dumps(get_schema(model), indent=indent)


# Schema groups for export
DEFINITION_SCHEMAS: dict[str, type[BaseModel]] = {
    "PropertyDefinition": PropertyDefinition,
    "PrimaryKeyDefinition": PrimaryKeyDefinition,
    "NodeDefinition": NodeDefinition,
    "EdgeDefinition": EdgeDefinition,
}

API_COMMON_SCHEMAS: dict[str, type[BaseModel]] = {
    "ErrorResponse": ErrorResponse,
    "DataResponse": DataResponse,
    "PaginatedResponse": PaginatedResponse,
}

API_RESOURCE_SCHEMAS: dict[str, type[BaseModel]] = {
    "CreateMappingRequest": CreateMappingRequest,
    "UpdateMappingRequest": UpdateMappingRequest,
    "MappingResponse": MappingResponse,
    "MappingVersionResponse": MappingVersionResponse,
    "NodeDiffResponse": NodeDiffResponse,
    "EdgeDiffResponse": EdgeDiffResponse,
    "MappingDiffResponse": MappingDiffResponse,
    "CreateSnapshotRequest": CreateSnapshotRequest,
    "SnapshotResponse": SnapshotResponse,
    "CreateInstanceRequest": CreateInstanceRequest,
    "InstanceResponse": InstanceResponse,
    "UpdateLifecycleRequest": UpdateLifecycleRequest,
}

API_INTERNAL_SCHEMAS: dict[str, type[BaseModel]] = {
    "UpdateSnapshotStatusRequest": UpdateSnapshotStatusRequest,
    "CreateExportJobsRequest": CreateExportJobsRequest,
    "UpdateExportJobRequest": UpdateExportJobRequest,
    "ExportJobResponse": ExportJobResponse,
    "UpdateInstanceStatusRequest": UpdateInstanceStatusRequest,
    "UpdateInstanceMetricsRequest": UpdateInstanceMetricsRequest,
    "UpdateInstanceProgressRequest": UpdateInstanceProgressRequest,
    "InstanceMappingResponse": InstanceMappingResponse,
    "ShutdownRequest": ShutdownRequest,
    "ShutdownResponse": ShutdownResponse,
}

API_ALGORITHM_SCHEMAS: dict[str, type[BaseModel]] = {
    "NativeAlgorithmRequest": NativeAlgorithmRequest,
    "NetworkXAlgorithmRequest": NetworkXAlgorithmRequest,
    "AlgorithmExecutionResponse": AlgorithmExecutionResponse,
    "AlgorithmInfoResponse": AlgorithmInfoResponse,
    "AlgorithmListResponse": AlgorithmListResponse,
}

API_OPS_SCHEMAS: dict[str, type[BaseModel]] = {
    "JobsStatusResponse": JobsStatusResponse,
    "TriggerJobRequest": TriggerJobRequest,
    "TriggerJobResponse": TriggerJobResponse,
    "SystemStateResponse": SystemStateResponse,
    "ExportJobsListResponse": ExportJobsListResponse,
    "LifecycleConfigRequest": LifecycleConfigRequest,
    "LifecycleConfigResponse": LifecycleConfigResponse,
    "ConcurrencyConfig": ConcurrencyConfig,
    "ConcurrencyConfigResponse": ConcurrencyConfigResponse,
    "MaintenanceModeRequest": MaintenanceModeRequest,
    "MaintenanceModeResponse": MaintenanceModeResponse,
    "ExportConfigRequest": ExportConfigRequest,
    "ExportConfigResponse": ExportConfigResponse,
    "BulkDeleteRequest": BulkDeleteRequest,
    "BulkDeleteResponse": BulkDeleteResponse,
}

API_SCHEMA_SCHEMAS: dict[str, type[BaseModel]] = {
    "CatalogResponse": CatalogResponse,
    "SchemaResponse": SchemaResponse,
    "TableResponse": TableResponse,
    "ColumnResponse": ColumnResponse,
    "CacheStatsResponse": CacheStatsResponse,
}

API_WRAPPER_SCHEMAS: dict[str, type[BaseModel]] = {
    "QueryRequest": QueryRequest,
    "QueryResponse": QueryResponse,
    "HealthResponse": HealthResponse,
    "LockInfo": LockInfo,
    "WrapperLockStatusResponse": WrapperLockStatusResponse,
    "NodeTableSchema": NodeTableSchema,
    "EdgeTableSchema": EdgeTableSchema,
    "WrapperSchemaResponse": WrapperSchemaResponse,
    "StatusResponse": StatusResponse,
}


def export_schemas(
    schemas: dict[str, type[BaseModel]],
    output_dir: Path | str,
) -> list[Path]:
    """
    Export a group of schemas to JSON files.

    Args:
        schemas: Dictionary mapping schema name to model class
        output_dir: Directory to write schema files

    Returns:
        List of paths to created files
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    created_files = []
    for name, model in schemas.items():
        filepath = output_dir / f"{name}.json"
        filepath.write_text(get_schema_json(model))
        created_files.append(filepath)

    return created_files


def export_definition_schemas(output_dir: Path | str) -> list[Path]:
    """Export definition schemas (NodeDefinition, EdgeDefinition, etc.)."""
    return export_schemas(DEFINITION_SCHEMAS, output_dir)


def export_api_common_schemas(output_dir: Path | str) -> list[Path]:
    """Export common API schemas (ErrorResponse, DataResponse, etc.)."""
    return export_schemas(API_COMMON_SCHEMAS, output_dir)


def export_api_resource_schemas(output_dir: Path | str) -> list[Path]:
    """Export resource API schemas (CreateMappingRequest, etc.)."""
    return export_schemas(API_RESOURCE_SCHEMAS, output_dir)


def export_api_internal_schemas(output_dir: Path | str) -> list[Path]:
    """Export internal API schemas (UpdateSnapshotStatusRequest, etc.)."""
    return export_schemas(API_INTERNAL_SCHEMAS, output_dir)


def export_api_algorithm_schemas(output_dir: Path | str) -> list[Path]:
    """Export algorithm API schemas (AlgorithmExecutionResponse, etc.)."""
    return export_schemas(API_ALGORITHM_SCHEMAS, output_dir)


def export_api_ops_schemas(output_dir: Path | str) -> list[Path]:
    """Export ops/admin API schemas (JobsStatusResponse, BulkDeleteRequest, etc.)."""
    return export_schemas(API_OPS_SCHEMAS, output_dir)


def export_api_schema_schemas(output_dir: Path | str) -> list[Path]:
    """Export schema metadata API schemas (CatalogResponse, TableResponse, etc.)."""
    return export_schemas(API_SCHEMA_SCHEMAS, output_dir)


def export_api_wrapper_schemas(output_dir: Path | str) -> list[Path]:
    """Export wrapper API schemas (QueryRequest, QueryResponse, etc.)."""
    return export_schemas(API_WRAPPER_SCHEMAS, output_dir)


def export_all_schemas(output_dir: Path | str) -> dict[str, list[Path]]:
    """
    Export all schemas organized by category.

    Creates the following directory structure:
        output_dir/
        ├── definitions/
        │   ├── NodeDefinition.json
        │   ├── EdgeDefinition.json
        │   └── ...
        ├── api_common/
        │   ├── ErrorResponse.json
        │   └── ...
        ├── api_resources/
        │   ├── CreateMappingRequest.json
        │   └── ...
        ├── api_internal/
        │   ├── UpdateSnapshotStatusRequest.json
        │   └── ...
        ├── api_algorithms/
        │   ├── AlgorithmExecutionResponse.json
        │   ├── NativeAlgorithmRequest.json
        │   └── ...
        └── api_ops/
            ├── JobsStatusResponse.json
            ├── BulkDeleteRequest.json
            └── ...

    Args:
        output_dir: Base directory for schema output

    Returns:
        Dictionary mapping category to list of created file paths
    """
    output_dir = Path(output_dir)

    return {
        "definitions": export_definition_schemas(output_dir / "definitions"),
        "api_common": export_api_common_schemas(output_dir / "api_common"),
        "api_resources": export_api_resource_schemas(output_dir / "api_resources"),
        "api_internal": export_api_internal_schemas(output_dir / "api_internal"),
        "api_algorithms": export_api_algorithm_schemas(output_dir / "api_algorithms"),
        "api_ops": export_api_ops_schemas(output_dir / "api_ops"),
        "api_schema": export_api_schema_schemas(output_dir / "api_schema"),
        "api_wrapper": export_api_wrapper_schemas(output_dir / "api_wrapper"),
    }


def get_combined_schema() -> dict[str, Any]:
    """
    Get a combined JSON Schema with all models as definitions.

    Returns a schema with all models available under $defs,
    useful for generating comprehensive documentation.

    Returns:
        Combined JSON Schema dictionary
    """
    all_schemas = {
        **DEFINITION_SCHEMAS,
        **API_COMMON_SCHEMAS,
        **API_RESOURCE_SCHEMAS,
        **API_INTERNAL_SCHEMAS,
        **API_ALGORITHM_SCHEMAS,
        **API_OPS_SCHEMAS,
    }

    combined = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Graph OLAP Platform API Schemas",
        "description": "Combined JSON Schema for all Graph OLAP Platform API models",
        "$defs": {},
    }

    for name, model in all_schemas.items():
        schema = get_schema(model)
        # Extract the main schema without nested $defs
        main_schema = {k: v for k, v in schema.items() if k != "$defs"}
        combined["$defs"][name] = main_schema

        # Merge nested $defs
        if "$defs" in schema:
            for def_name, def_schema in schema["$defs"].items():
                if def_name not in combined["$defs"]:
                    combined["$defs"][def_name] = def_schema

    return combined
