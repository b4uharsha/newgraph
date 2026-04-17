"""Utility modules for the wrapper."""

from wrapper.utils.ddl import (
    generate_edge_ddl,
    generate_node_ddl,
    get_edge_gcs_subpath,
    get_node_gcs_subpath,
)

__all__ = [
    "generate_edge_ddl",
    "generate_node_ddl",
    "get_edge_gcs_subpath",
    "get_node_gcs_subpath",
]
