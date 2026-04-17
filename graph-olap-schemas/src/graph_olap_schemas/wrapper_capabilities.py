"""Wrapper capabilities registry and validation."""

from dataclasses import dataclass

from graph_olap_schemas.wrapper_interface import WrapperType


@dataclass(frozen=True)
class WrapperCapabilities:
    """Capabilities and features of a graph database wrapper.

    This defines what features each wrapper supports, including:
    - Supported data types
    - Algorithm execution modes
    - Query language
    - Bulk import capabilities
    """

    wrapper_type: WrapperType
    supports_algorithms: bool
    supports_networkx: bool
    supports_bulk_import: bool
    supported_data_types: list[str]
    query_language: str
    algorithm_invocation: str  # "rest_api" | "cypher_procedure" | "none"
    native_algorithms: list[str] | None
    algorithm_result_mode: str  # "property_writeback" | "query_result" | "none"


# Registry of wrapper capabilities
WRAPPER_CAPABILITIES: dict[WrapperType, WrapperCapabilities] = {
    WrapperType.RYUGRAPH: WrapperCapabilities(
        wrapper_type=WrapperType.RYUGRAPH,
        supports_algorithms=True,
        supports_networkx=True,
        supports_bulk_import=True,
        supported_data_types=[
            "STRING",
            "INT64",
            "INT32",
            "INT16",
            "INT8",
            "DOUBLE",
            "FLOAT",
            "BOOL",
            "DATE",
            "TIMESTAMP",
            "BLOB",
            "UUID",
        ],
        query_language="cypher",
        algorithm_invocation="rest_api",
        native_algorithms=["pagerank", "wcc", "scc", "scc_kosaraju", "louvain", "kcore"],
        algorithm_result_mode="property_writeback",
    ),
    WrapperType.FALKORDB: WrapperCapabilities(
        wrapper_type=WrapperType.FALKORDB,
        supports_algorithms=True,
        supports_networkx=False,
        supports_bulk_import=False,  # FalkorDB doesn't support Parquet bulk import
        supported_data_types=[
            "STRING",
            "INTEGER",  # Note: FalkorDB uses INTEGER not INT64/INT32/etc
            "DOUBLE",
            "BOOLEAN",
            "DATE",
            "TIME",
            "DATETIME",
            "POINT",
        ],
        query_language="cypher",
        algorithm_invocation="cypher_procedure",  # Algorithms via CALL algo.xxx()
        native_algorithms=["BFS", "betweennessCentrality", "WCC", "CDLP", "shortestPath"],
        algorithm_result_mode="query_result",  # Results returned as query results
    ),
}


def get_wrapper_capabilities(wrapper_type: WrapperType) -> WrapperCapabilities:
    """Get capabilities for a wrapper type.

    Args:
        wrapper_type: The wrapper type

    Returns:
        Wrapper capabilities

    Raises:
        KeyError: If wrapper type is not supported
    """
    return WRAPPER_CAPABILITIES[wrapper_type]
