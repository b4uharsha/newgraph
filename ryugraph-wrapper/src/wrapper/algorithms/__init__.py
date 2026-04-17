"""Graph algorithm implementations for native Ryugraph and NetworkX."""

from __future__ import annotations

from wrapper.algorithms.native import (
    NATIVE_ALGORITHMS,
    NativeAlgorithm,
    get_native_algorithm,
    register_native_algorithms,
)
from wrapper.algorithms.networkx import (
    discover_algorithm,
    execute_networkx_algorithm,
    get_algorithm_info,
    list_algorithms,
    register_common_algorithms,
)
from wrapper.algorithms.registry import (
    AlgorithmCategory,
    AlgorithmInfo,
    AlgorithmParameter,
    AlgorithmRegistry,
    AlgorithmType,
    get_registry,
    reset_registry,
)
from wrapper.algorithms.writeback import (
    initialize_node_property,
    remove_node_property,
    write_edge_property,
    write_node_property,
    write_node_property_by_internal_id,
)

__all__ = [
    # Native
    "NATIVE_ALGORITHMS",
    # Registry
    "AlgorithmCategory",
    "AlgorithmInfo",
    "AlgorithmParameter",
    "AlgorithmRegistry",
    "AlgorithmType",
    "NativeAlgorithm",
    # NetworkX
    "discover_algorithm",
    "execute_networkx_algorithm",
    "get_algorithm_info",
    "get_native_algorithm",
    "get_registry",
    # Writeback
    "initialize_node_property",
    "list_algorithms",
    "register_common_algorithms",
    "register_native_algorithms",
    "remove_node_property",
    "reset_registry",
    "write_edge_property",
    "write_node_property",
    "write_node_property_by_internal_id",
]
