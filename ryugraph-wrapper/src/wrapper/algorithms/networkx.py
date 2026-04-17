"""NetworkX algorithm discovery and execution.

Provides dynamic discovery and execution of NetworkX graph algorithms.
Extracts algorithm metadata via introspection and provides a unified
interface for running algorithms on Ryugraph data.
"""

from __future__ import annotations

import inspect
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, get_type_hints

import networkx as nx
from docstring_parser import parse as parse_docstring

from wrapper.algorithms.registry import (
    AlgorithmCategory,
    AlgorithmInfo,
    AlgorithmParameter,
    AlgorithmType,
    get_registry,
)
from wrapper.exceptions import AlgorithmError, AlgorithmNotFoundError
from wrapper.logging import get_logger

if TYPE_CHECKING:
    from wrapper.services.database import DatabaseService

logger = get_logger(__name__)

# Mapping of NetworkX module paths to categories
CATEGORY_MAPPING: dict[str, AlgorithmCategory] = {
    "centrality": AlgorithmCategory.CENTRALITY,
    "link_analysis": AlgorithmCategory.CENTRALITY,  # PageRank, HITS, etc.
    "community": AlgorithmCategory.COMMUNITY,
    "shortest_paths": AlgorithmCategory.PATHFINDING,
    "shortest_path": AlgorithmCategory.PATHFINDING,
    "traversal": AlgorithmCategory.TRAVERSAL,
    "cluster": AlgorithmCategory.CLUSTERING,
    "clustering": AlgorithmCategory.CLUSTERING,
    "link_prediction": AlgorithmCategory.LINK_PREDICTION,
    "similarity": AlgorithmCategory.SIMILARITY,
}

# Algorithms known to return node-centric results
NODE_OUTPUT_ALGORITHMS = {
    "pagerank",
    "betweenness_centrality",
    "closeness_centrality",
    "degree_centrality",
    "eigenvector_centrality",
    "katz_centrality",
    "harmonic_centrality",
    "load_centrality",
    "clustering",
    "triangles",
    "square_clustering",
    "local_efficiency",
}

# Algorithms to exclude (not suitable for this interface)
EXCLUDED_ALGORITHMS = {
    "read_adjlist",
    "write_adjlist",
    "read_edgelist",
    "write_edgelist",
    "read_gml",
    "write_gml",
    "to_numpy_array",
    "from_numpy_array",
    "draw",
    "draw_networkx",
}

# Type mapping from Python types to string representations
TYPE_MAPPING: dict[type, str] = {
    int: "int",
    float: "float",
    str: "string",
    bool: "boolean",
    list: "array",
    dict: "object",
    type(None): "null",
}


def _get_type_string(annotation: Any) -> str:
    """Convert type annotation to string representation."""
    if annotation is inspect.Parameter.empty:
        return "any"
    if annotation in TYPE_MAPPING:
        return TYPE_MAPPING[annotation]
    if hasattr(annotation, "__origin__"):  # Generic types
        origin = annotation.__origin__
        if origin is list:
            return "array"
        if origin is dict:
            return "object"
    return str(annotation).replace("typing.", "")


def _infer_category(func: Callable[..., Any], module_path: str) -> AlgorithmCategory:
    """Infer algorithm category from module path or function."""
    # Check the function's actual module first (most accurate)
    actual_module = getattr(func, "__module__", "")
    for key, category in CATEGORY_MAPPING.items():
        if key in actual_module.lower():
            return category

    # Fallback to provided module path
    for key, category in CATEGORY_MAPPING.items():
        if key in module_path.lower():
            return category

    # Default to other
    return AlgorithmCategory.OTHER


def discover_algorithm(name: str) -> tuple[Callable[..., Any], str] | None:
    """Discover a NetworkX algorithm by name.

    Searches through NetworkX's algorithm modules to find the function.

    Args:
        name: Algorithm name (e.g., 'pagerank', 'betweenness_centrality').

    Returns:
        Tuple of (function, module_path) or None if not found.
    """
    # Direct attribute lookup on nx
    if hasattr(nx, name):
        func = getattr(nx, name)
        if callable(func) and not name.startswith("_"):
            return func, f"networkx.{name}"

    # Search in nx.algorithms submodules
    algorithms_module = nx.algorithms
    for submodule_name in dir(algorithms_module):
        if submodule_name.startswith("_"):
            continue

        submodule = getattr(algorithms_module, submodule_name, None)
        if submodule is None or not inspect.ismodule(submodule):
            continue

        if hasattr(submodule, name):
            func = getattr(submodule, name)
            if callable(func):
                return func, f"networkx.algorithms.{submodule_name}.{name}"

    return None


def get_algorithm_info(name: str) -> AlgorithmInfo | None:
    """Get detailed information about a NetworkX algorithm.

    Extracts parameter information, docstrings, and metadata via introspection.

    Args:
        name: Algorithm name.

    Returns:
        AlgorithmInfo or None if not found.
    """
    result = discover_algorithm(name)
    if result is None:
        return None

    func, module_path = result

    # Parse docstring
    docstring = inspect.getdoc(func) or ""
    parsed_doc = parse_docstring(docstring)

    # Get function signature
    try:
        sig = inspect.signature(func)
    except (ValueError, TypeError):
        sig = None

    # Extract type hints
    try:
        hints = get_type_hints(func)
    except Exception:
        hints = {}

    # Build parameter list
    parameters: list[AlgorithmParameter] = []
    param_docs = {p.arg_name: p.description for p in parsed_doc.params}

    if sig:
        for param_name, param in sig.parameters.items():
            # Skip 'G' (graph) parameter - we provide that
            if param_name.lower() in ("g", "graph"):
                continue

            # Skip *args and **kwargs
            if param.kind in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            ):
                continue

            # Determine type
            param_type = _get_type_string(hints.get(param_name, param.annotation))

            # Determine if required
            required = param.default is inspect.Parameter.empty

            # Get default value
            default = None if required else param.default

            # Get description from docstring
            description = param_docs.get(param_name, "")

            parameters.append(
                AlgorithmParameter(
                    name=param_name,
                    type=param_type,
                    required=required,
                    default=default,
                    description=description,
                )
            )

    # Build description
    description = parsed_doc.short_description or ""
    long_description = parsed_doc.long_description or ""

    # Determine category
    category = _infer_category(func, module_path)

    # Determine return type
    returns = ""
    if parsed_doc.returns:
        returns = parsed_doc.returns.description or str(parsed_doc.returns.type_name or "")

    return AlgorithmInfo(
        name=name,
        type=AlgorithmType.NETWORKX,
        category=category,
        description=description,
        long_description=long_description,
        parameters=tuple(parameters),
        returns=returns,
        node_output=name in NODE_OUTPUT_ALGORITHMS,
    )


def list_algorithms(
    category: AlgorithmCategory | None = None,
    search: str | None = None,
) -> list[AlgorithmInfo]:
    """List available NetworkX algorithms.

    Args:
        category: Filter by category.
        search: Search string for name/description.

    Returns:
        List of algorithm infos.
    """
    results: list[AlgorithmInfo] = []

    # Scan nx.algorithms for functions
    for name in dir(nx):
        if name.startswith("_") or name in EXCLUDED_ALGORITHMS:
            continue

        func = getattr(nx, name, None)
        if func is None or not callable(func):
            continue

        # Check if it looks like an algorithm (takes graph as first arg)
        try:
            sig = inspect.signature(func)
            params = list(sig.parameters.keys())
            if not params or params[0].lower() not in ("g", "graph"):
                continue
        except (ValueError, TypeError):
            continue

        info = get_algorithm_info(name)
        if info is None:
            continue

        # Apply category filter
        if category is not None and info.category != category:
            continue

        # Apply search filter
        if search:
            search_lower = search.lower()
            if (
                search_lower not in info.name.lower()
                and search_lower not in info.description.lower()
            ):
                continue

        results.append(info)

    # Sort by name
    results.sort(key=lambda a: a.name)

    return results


def register_common_algorithms() -> None:
    """Register commonly used NetworkX algorithms with the registry."""
    registry = get_registry()

    common_algorithms = [
        "pagerank",
        "betweenness_centrality",
        "closeness_centrality",
        "degree_centrality",
        "eigenvector_centrality",
        "clustering",
        "triangles",
        "connected_components",
        "strongly_connected_components",
        "shortest_path",
        "shortest_path_length",
        "all_pairs_shortest_path_length",
        "diameter",
        "average_clustering",
        "transitivity",
        "density",
    ]

    registered = 0
    for name in common_algorithms:
        info = get_algorithm_info(name)
        if info is not None:
            registry.register_networkx(info)
            registered += 1

    logger.info("Registered NetworkX algorithms", count=registered)


async def execute_networkx_algorithm(
    db_service: DatabaseService,
    algorithm_name: str,
    node_label: str | None,
    edge_type: str | None,
    result_property: str,
    parameters: dict[str, Any],
    subgraph_query: str | None = None,
) -> dict[str, Any]:
    """Execute a NetworkX algorithm on graph data.

    Extracts graph data from Ryugraph, converts to NetworkX graph,
    executes the algorithm, and writes results back.

    Args:
        db_service: Database service for data access.
        algorithm_name: Name of the NetworkX algorithm.
        node_label: Node label filter (None = all).
        edge_type: Edge type filter (None = all).
        result_property: Property to store results.
        parameters: Algorithm parameters.
        subgraph_query: Optional Cypher query to select subgraph.

    Returns:
        Execution result dict.

    Raises:
        AlgorithmNotFoundError: If algorithm not found.
        AlgorithmError: If execution fails.
    """
    start_time = time.perf_counter()

    # Discover algorithm
    result = discover_algorithm(algorithm_name)
    if result is None:
        raise AlgorithmNotFoundError(algorithm_name)

    func, _module_path = result

    logger.info(
        "Executing NetworkX algorithm",
        algorithm=algorithm_name,
        node_label=node_label,
        edge_type=edge_type,
    )

    try:
        # Extract graph from database
        graph = await _extract_graph(
            db_service,
            node_label,
            edge_type,
            subgraph_query,
        )

        extraction_time = time.perf_counter()
        logger.debug(
            "Graph extracted",
            nodes=graph.number_of_nodes(),
            edges=graph.number_of_edges(),
            extraction_ms=int((extraction_time - start_time) * 1000),
        )

        # Execute algorithm
        algo_result = func(graph, **parameters)

        execution_time = time.perf_counter()
        logger.debug(
            "Algorithm executed",
            execution_ms=int((execution_time - extraction_time) * 1000),
        )

        # Process result and write back
        nodes_updated = await _write_results(
            db_service,
            algo_result,
            result_property,
            node_label,
        )

        duration_ms = int((time.perf_counter() - start_time) * 1000)

        logger.info(
            "NetworkX algorithm completed",
            algorithm=algorithm_name,
            nodes_updated=nodes_updated,
            duration_ms=duration_ms,
        )

        return {
            "nodes_updated": nodes_updated,
            "duration_ms": duration_ms,
            "graph_nodes": graph.number_of_nodes(),
            "graph_edges": graph.number_of_edges(),
        }

    except AlgorithmNotFoundError:
        raise
    except Exception as e:
        logger.error(
            "NetworkX algorithm failed",
            algorithm=algorithm_name,
            error=str(e),
        )
        raise AlgorithmError(
            f"Algorithm execution failed: {e}",
            algorithm_name=algorithm_name,
        ) from e


async def _extract_graph(
    db_service: DatabaseService,
    node_label: str | None,
    edge_type: str | None,
    subgraph_query: str | None,
) -> nx.DiGraph:
    """Extract graph data from Ryugraph into NetworkX.

    Args:
        db_service: Database service.
        node_label: Node label filter.
        edge_type: Edge type filter.
        subgraph_query: Optional subgraph selection query.

    Returns:
        NetworkX DiGraph.
    """
    graph = nx.DiGraph()

    if subgraph_query:
        # Use custom query for subgraph selection
        result = await db_service.execute_query(subgraph_query)
        # Expect query to return edges as (source, target) or (source, target, props)
        for row in result["rows"]:
            if len(row) >= 2:
                source, target = row[0], row[1]
                props = row[2] if len(row) > 2 else {}
                graph.add_edge(source, target, **props if isinstance(props, dict) else {})
    else:
        # Extract all edges matching filters
        # Use offset(id(n)) to get integer node IDs instead of internal structs
        # which are unhashable in Python
        node_match = f"(n:{node_label})" if node_label else "(n)"
        edge_match = f"-[r:{edge_type}]->" if edge_type else "-[r]->"
        target_match = f"(m:{node_label})" if node_label else "(m)"

        query = f"""
        MATCH {node_match}{edge_match}{target_match}
        RETURN offset(id(n)), offset(id(m))
        """

        result = await db_service.execute_query(query)
        for row in result["rows"]:
            graph.add_edge(row[0], row[1])

        # Also extract isolated nodes if node_label specified
        if node_label:
            node_query = f"""
            MATCH (n:{node_label})
            WHERE NOT EXISTS {{ MATCH (n)-[]->() }} AND NOT EXISTS {{ MATCH ()-[]->(n) }}
            RETURN offset(id(n))
            """
            node_result = await db_service.execute_query(node_query)
            for row in node_result["rows"]:
                graph.add_node(row[0])

    return graph


async def _write_results(
    db_service: DatabaseService,
    algo_result: Any,
    result_property: str,
    node_label: str | None,
) -> int:
    """Write algorithm results back to the database.

    Args:
        db_service: Database service.
        algo_result: Algorithm result (dict mapping node_id -> value).
        result_property: Property name to write.
        node_label: Node label filter.

    Returns:
        Number of nodes updated.
    """
    # Handle different result types
    if isinstance(algo_result, dict):
        # Most centrality algorithms return dict
        return await _write_dict_results(db_service, algo_result, result_property, node_label)
    elif isinstance(algo_result, (int, float)):
        # Global metrics - no per-node results
        logger.debug("Algorithm returned scalar result", result=algo_result)
        return 0
    elif hasattr(algo_result, "__iter__"):
        # Iterator/generator results (e.g., connected_components)
        logger.debug("Algorithm returned iterator result")
        return 0
    else:
        logger.warning("Unknown algorithm result type", type=type(algo_result).__name__)
        return 0


async def _write_dict_results(
    db_service: DatabaseService,
    results: dict[Any, Any],
    result_property: str,
    node_label: str | None,
) -> int:
    """Write dictionary results to node properties.

    Args:
        db_service: Database service.
        results: Dict mapping node_id (offset) -> value.
        result_property: Property name.
        node_label: Node label filter.

    Returns:
        Number of nodes updated.
    """
    if not results:
        return 0

    # Ensure result property exists on the node table
    # Kuzu requires properties to be defined in schema before SET operations
    if node_label:
        # Determine type from first value
        first_value = next(iter(results.values()))
        if isinstance(first_value, float):
            await db_service.ensure_property_exists(node_label, result_property, "DOUBLE", "0.0")
        elif isinstance(first_value, int):
            await db_service.ensure_property_exists(node_label, result_property, "INT64", "0")
        else:
            # Default to DOUBLE for numeric algorithms
            await db_service.ensure_property_exists(node_label, result_property, "DOUBLE", "0.0")

    # Write results individually for reliability
    # Batch UNWIND with Kuzu has indexing issues
    total_updated = 0
    node_match = f"(n:{node_label})" if node_label else "(n)"

    for node_offset, value in results.items():
        # Convert value to appropriate type
        typed_value = float(value) if isinstance(value, (int, float)) else value

        result = await db_service.execute_query(
            f"MATCH {node_match} WHERE offset(id(n)) = $offset "
            f"SET n.{result_property} = $value "
            f"RETURN count(n) AS updated",
            {"offset": int(node_offset), "value": typed_value},
        )

        if result["rows"] and result["rows"][0][0] > 0:
            total_updated += 1

    return total_updated
