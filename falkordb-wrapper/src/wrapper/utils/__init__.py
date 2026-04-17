"""Utility modules for FalkorDB wrapper.

Provides:
- ParquetReader: Batch reading of Parquet files for UNWIND loading
- CSVConverter: Streaming Parquet to CSV conversion (legacy)
- Type mapping utilities for FalkorDB type validation
"""

from wrapper.utils.csv_converter import (
    CSVConversionError,
    CSVConverter,
    ParquetReadError,
    ParquetReader,
)
from wrapper.utils.type_mapping import (
    SUPPORTED_TYPES,
    UNSUPPORTED_TYPES,
    validate_edge_types,
    validate_mapping_types,
    validate_node_types,
)

__all__ = [
    "SUPPORTED_TYPES",
    "UNSUPPORTED_TYPES",
    "CSVConversionError",
    "CSVConverter",
    "ParquetReadError",
    "ParquetReader",
    "validate_edge_types",
    "validate_mapping_types",
    "validate_node_types",
]
