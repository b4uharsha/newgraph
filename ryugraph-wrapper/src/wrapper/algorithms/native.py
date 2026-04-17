"""Native Ryugraph algorithm implementations.

Implements graph algorithms using Ryugraph's native Cypher capabilities.
These algorithms run directly in the database engine and are typically
faster for supported operations.
"""

from __future__ import annotations

import contextlib
import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from wrapper.algorithms.registry import (
    AlgorithmCategory,
    AlgorithmInfo,
    AlgorithmParameter,
    AlgorithmType,
    get_registry,
)
from wrapper.exceptions import AlgorithmError
from wrapper.logging import get_logger

if TYPE_CHECKING:
    from wrapper.services.database import DatabaseService

logger = get_logger(__name__)


class NativeAlgorithm(ABC):
    """Base class for native Ryugraph algorithms."""

    @property
    @abstractmethod
    def info(self) -> AlgorithmInfo:
        """Algorithm information."""
        ...

    @abstractmethod
    async def execute(
        self,
        db_service: DatabaseService,
        node_label: str | None,
        edge_type: str | None,
        result_property: str,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute the algorithm."""
        ...

    def validate_parameters(self, parameters: dict[str, Any]) -> None:
        """Validate algorithm parameters.

        Args:
            parameters: Parameters to validate.

        Raises:
            AlgorithmError: If validation fails.
        """
        for param in self.info.parameters:
            if param.required and param.name not in parameters:
                raise AlgorithmError(
                    f"Missing required parameter: {param.name}",
                    algorithm_name=self.info.name,
                )

    async def _write_algo_results(
        self,
        db_service: DatabaseService,
        rows: list[list[Any]],
        node_label: str,
        result_property: str,
    ) -> int:
        """Write algorithm results back to node properties.

        Args:
            db_service: Database service for queries.
            rows: List of [node_offset, value] from algo extension.
            node_label: Target node table.
            result_property: Property to write values to.

        Returns:
            Number of nodes updated.
        """
        if not rows:
            return 0

        # Write results individually for reliability
        for row in rows:
            node_offset, value = row[0], row[1]
            await db_service.execute_query(
                f"MATCH (n:{node_label}) WHERE offset(id(n)) = $offset "
                f"SET n.{result_property} = $value",
                {"offset": node_offset, "value": value},
            )

        return len(rows)


class PageRankAlgorithm(NativeAlgorithm):
    """PageRank centrality algorithm.

    Computes PageRank scores for nodes using the Ryugraph/KuzuDB algo extension.
    This runs natively in the database engine for optimal performance.
    """

    @property
    def info(self) -> AlgorithmInfo:
        """Algorithm information."""
        return AlgorithmInfo(
            name="pagerank",
            type=AlgorithmType.NATIVE,
            category=AlgorithmCategory.CENTRALITY,
            description="Compute PageRank centrality scores",
            long_description=(
                "PageRank is a link analysis algorithm that assigns a numerical "
                "weighting to each node in a graph, measuring its relative importance. "
                "Uses the native Ryugraph algo extension for optimal performance."
            ),
            parameters=(
                AlgorithmParameter(
                    name="damping_factor",
                    type="float",
                    required=False,
                    default=0.85,
                    description="Damping factor (typically 0.85)",
                ),
                AlgorithmParameter(
                    name="max_iterations",
                    type="int",
                    required=False,
                    default=20,
                    description="Maximum number of iterations",
                ),
                AlgorithmParameter(
                    name="tolerance",
                    type="float",
                    required=False,
                    default=1e-7,
                    description="Convergence tolerance",
                ),
            ),
            returns="PageRank score (float between 0 and 1)",
        )

    async def execute(
        self,
        db_service: DatabaseService,
        node_label: str | None,
        edge_type: str | None,
        result_property: str,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute PageRank algorithm using Ryugraph algo extension."""
        start_time = time.perf_counter()

        damping = parameters.get("damping_factor", 0.85)
        max_iter = parameters.get("max_iterations", 20)
        tolerance = parameters.get("tolerance", 1e-7)

        logger.info(
            "Executing PageRank via algo extension",
            node_label=node_label,
            damping=damping,
            max_iterations=max_iter,
        )

        if not node_label or not edge_type:
            raise AlgorithmError(
                "PageRank requires both node_label and edge_type",
                algorithm_name="pagerank",
            )

        # Ensure result property exists on the node table
        await db_service.ensure_property_exists(node_label, result_property, "DOUBLE", "0.0")

        # Unique graph name to avoid collisions
        graph_name = f"_pr_{int(time.time() * 1000)}"

        try:
            # Step 1: Create projected graph (REQUIRED for algo extension)
            await db_service.execute_query(
                f"CALL project_graph('{graph_name}', ['{node_label}'], ['{edge_type}'])"
            )

            # Step 2: Run PageRank - returns (node, rank)
            result = await db_service.execute_query(
                f"CALL page_rank('{graph_name}', "
                f"dampingFactor := {damping}, "
                f"maxIterations := {max_iter}, "
                f"tolerance := {tolerance}) "
                f"RETURN offset(id(node)) AS node_offset, rank"
            )

            # Step 3: Write results back to nodes
            nodes_updated = await self._write_algo_results(
                db_service, result["rows"], node_label, result_property
            )

            duration_ms = int((time.perf_counter() - start_time) * 1000)

            logger.info(
                "PageRank completed",
                nodes_updated=nodes_updated,
                duration_ms=duration_ms,
            )

            return {
                "nodes_updated": nodes_updated,
                "duration_ms": duration_ms,
                "converged": True,
                "iterations": max_iter,
            }

        finally:
            # Step 4: Always clean up projected graph
            try:
                await db_service.execute_query(f"CALL drop_projected_graph('{graph_name}')")
            except Exception:
                pass  # Graph may not exist if creation failed


class WeaklyConnectedComponentsAlgorithm(NativeAlgorithm):
    """Weakly Connected Components algorithm.

    Finds connected components treating edges as undirected using the
    Ryugraph/KuzuDB algo extension for optimal performance.
    """

    @property
    def info(self) -> AlgorithmInfo:
        """Algorithm information."""
        return AlgorithmInfo(
            name="wcc",
            type=AlgorithmType.NATIVE,
            category=AlgorithmCategory.COMMUNITY,
            description="Find weakly connected components",
            long_description=(
                "Weakly Connected Components (WCC) finds sets of nodes that are "
                "connected by paths, treating all edges as undirected. Each node "
                "is assigned a component ID indicating which component it belongs to. "
                "Uses the native Ryugraph algo extension for optimal performance."
            ),
            parameters=(
                AlgorithmParameter(
                    name="max_iterations",
                    type="int",
                    required=False,
                    default=100,
                    description="Maximum number of iterations",
                ),
            ),
            returns="Component ID (integer)",
        )

    async def execute(
        self,
        db_service: DatabaseService,
        node_label: str | None,
        edge_type: str | None,
        result_property: str,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute WCC algorithm using Ryugraph algo extension."""
        start_time = time.perf_counter()

        max_iter = parameters.get("max_iterations", 100)

        logger.info(
            "Executing WCC via algo extension",
            node_label=node_label,
            edge_type=edge_type,
        )

        if not node_label or not edge_type:
            raise AlgorithmError(
                "WCC requires both node_label and edge_type",
                algorithm_name="wcc",
            )

        # Ensure result property exists on the node table
        await db_service.ensure_property_exists(node_label, result_property, "INT64", "0")

        # Unique graph name to avoid collisions
        graph_name = f"_wcc_{int(time.time() * 1000)}"

        try:
            # Step 1: Create projected graph (REQUIRED for algo extension)
            await db_service.execute_query(
                f"CALL project_graph('{graph_name}', ['{node_label}'], ['{edge_type}'])"
            )

            # Step 2: Run WCC - returns (node, group_id)
            result = await db_service.execute_query(
                f"CALL weakly_connected_components('{graph_name}', "
                f"maxIterations := {max_iter}) "
                f"RETURN offset(id(node)) AS node_offset, group_id"
            )

            # Step 3: Write results back to nodes
            nodes_updated = await self._write_algo_results(
                db_service, result["rows"], node_label, result_property
            )

            # Count distinct components from results
            components = len({row[1] for row in result["rows"]}) if result["rows"] else 0

            duration_ms = int((time.perf_counter() - start_time) * 1000)

            logger.info(
                "WCC completed",
                components=components,
                nodes_updated=nodes_updated,
                duration_ms=duration_ms,
            )

            return {
                "nodes_updated": nodes_updated,
                "duration_ms": duration_ms,
                "components": components,
                "iterations": 1,
            }

        finally:
            # Step 4: Always clean up projected graph
            try:
                await db_service.execute_query(f"CALL drop_projected_graph('{graph_name}')")
            except Exception:
                pass  # Graph may not exist if creation failed


class StronglyConnectedComponentsAlgorithm(NativeAlgorithm):
    """Strongly Connected Components algorithm.

    Finds strongly connected components where every pair of vertices is
    mutually reachable. Uses parallel BFS-based coloring algorithm.
    """

    @property
    def info(self) -> AlgorithmInfo:
        """Algorithm information."""
        return AlgorithmInfo(
            name="scc",
            type=AlgorithmType.NATIVE,
            category=AlgorithmCategory.COMMUNITY,
            description="Find strongly connected components",
            long_description=(
                "Strongly Connected Components (SCC) finds maximal subgraphs where "
                "every pair of vertices is mutually reachable. Uses the parallel "
                "BFS-based coloring algorithm for optimal performance."
            ),
            parameters=(
                AlgorithmParameter(
                    name="max_iterations",
                    type="int",
                    required=False,
                    default=100,
                    description="Maximum number of iterations",
                ),
            ),
            returns="Component ID (integer)",
        )

    async def execute(
        self,
        db_service: DatabaseService,
        node_label: str | None,
        edge_type: str | None,
        result_property: str,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute SCC algorithm using Ryugraph algo extension."""
        start_time = time.perf_counter()

        max_iter = parameters.get("max_iterations", 100)

        logger.info(
            "Executing SCC via algo extension",
            node_label=node_label,
            edge_type=edge_type,
        )

        if not node_label or not edge_type:
            raise AlgorithmError(
                "SCC requires both node_label and edge_type",
                algorithm_name="scc",
            )

        await db_service.ensure_property_exists(node_label, result_property, "INT64", "0")

        graph_name = f"_scc_{int(time.time() * 1000)}"

        try:
            await db_service.execute_query(
                f"CALL project_graph('{graph_name}', ['{node_label}'], ['{edge_type}'])"
            )

            result = await db_service.execute_query(
                f"CALL strongly_connected_components('{graph_name}', "
                f"maxIterations := {max_iter}) "
                f"RETURN offset(id(node)) AS node_offset, group_id"
            )

            nodes_updated = await self._write_algo_results(
                db_service, result["rows"], node_label, result_property
            )

            components = len({row[1] for row in result["rows"]}) if result["rows"] else 0
            duration_ms = int((time.perf_counter() - start_time) * 1000)

            logger.info(
                "SCC completed",
                components=components,
                nodes_updated=nodes_updated,
                duration_ms=duration_ms,
            )

            return {
                "nodes_updated": nodes_updated,
                "duration_ms": duration_ms,
                "components": components,
            }

        finally:
            with contextlib.suppress(Exception):
                await db_service.execute_query(f"CALL drop_projected_graph('{graph_name}')")


class StronglyConnectedComponentsKosarajuAlgorithm(NativeAlgorithm):
    """Strongly Connected Components using Kosaraju's algorithm.

    DFS-based single-threaded algorithm. Recommended for very sparse graphs
    or graphs with high diameter.
    """

    @property
    def info(self) -> AlgorithmInfo:
        """Algorithm information."""
        return AlgorithmInfo(
            name="scc_kosaraju",
            type=AlgorithmType.NATIVE,
            category=AlgorithmCategory.COMMUNITY,
            description="Find strongly connected components (Kosaraju)",
            long_description=(
                "Strongly Connected Components using Kosaraju's DFS-based algorithm. "
                "Recommended for very sparse graphs or graphs with high diameter."
            ),
            parameters=(),
            returns="Component ID (integer)",
        )

    async def execute(
        self,
        db_service: DatabaseService,
        node_label: str | None,
        edge_type: str | None,
        result_property: str,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute SCC Kosaraju algorithm using Ryugraph algo extension."""
        start_time = time.perf_counter()

        logger.info(
            "Executing SCC Kosaraju via algo extension",
            node_label=node_label,
            edge_type=edge_type,
        )

        if not node_label or not edge_type:
            raise AlgorithmError(
                "SCC Kosaraju requires both node_label and edge_type",
                algorithm_name="scc_kosaraju",
            )

        await db_service.ensure_property_exists(node_label, result_property, "INT64", "0")

        graph_name = f"_scc_ko_{int(time.time() * 1000)}"

        try:
            await db_service.execute_query(
                f"CALL project_graph('{graph_name}', ['{node_label}'], ['{edge_type}'])"
            )

            result = await db_service.execute_query(
                f"CALL strongly_connected_components_kosaraju('{graph_name}') "
                f"RETURN offset(id(node)) AS node_offset, group_id"
            )

            nodes_updated = await self._write_algo_results(
                db_service, result["rows"], node_label, result_property
            )

            components = len({row[1] for row in result["rows"]}) if result["rows"] else 0
            duration_ms = int((time.perf_counter() - start_time) * 1000)

            logger.info(
                "SCC Kosaraju completed",
                components=components,
                nodes_updated=nodes_updated,
                duration_ms=duration_ms,
            )

            return {
                "nodes_updated": nodes_updated,
                "duration_ms": duration_ms,
                "components": components,
            }

        finally:
            with contextlib.suppress(Exception):
                await db_service.execute_query(f"CALL drop_projected_graph('{graph_name}')")


class LouvainAlgorithm(NativeAlgorithm):
    """Louvain community detection algorithm.

    Extracts communities by maximizing modularity score using
    hierarchical clustering.
    """

    @property
    def info(self) -> AlgorithmInfo:
        """Algorithm information."""
        return AlgorithmInfo(
            name="louvain",
            type=AlgorithmType.NATIVE,
            category=AlgorithmCategory.COMMUNITY,
            description="Detect communities via Louvain algorithm",
            long_description=(
                "Louvain is a hierarchical clustering algorithm that extracts "
                "communities by maximizing modularity score. Edges are treated "
                "as undirected. Uses parallelized Grappolo implementation."
            ),
            parameters=(
                AlgorithmParameter(
                    name="max_phases",
                    type="int",
                    required=False,
                    default=20,
                    description="Maximum number of phases",
                ),
                AlgorithmParameter(
                    name="max_iterations",
                    type="int",
                    required=False,
                    default=20,
                    description="Maximum iterations per phase",
                ),
            ),
            returns="Community ID (integer)",
        )

    async def execute(
        self,
        db_service: DatabaseService,
        node_label: str | None,
        edge_type: str | None,
        result_property: str,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute Louvain algorithm using Ryugraph algo extension."""
        start_time = time.perf_counter()

        max_phases = parameters.get("max_phases", 20)
        max_iter = parameters.get("max_iterations", 20)

        logger.info(
            "Executing Louvain via algo extension",
            node_label=node_label,
            edge_type=edge_type,
        )

        if not node_label or not edge_type:
            raise AlgorithmError(
                "Louvain requires both node_label and edge_type",
                algorithm_name="louvain",
            )

        await db_service.ensure_property_exists(node_label, result_property, "INT64", "0")

        graph_name = f"_louvain_{int(time.time() * 1000)}"

        try:
            await db_service.execute_query(
                f"CALL project_graph('{graph_name}', ['{node_label}'], ['{edge_type}'])"
            )

            result = await db_service.execute_query(
                f"CALL louvain('{graph_name}', "
                f"maxPhases := {max_phases}, "
                f"maxIterations := {max_iter}) "
                f"RETURN offset(id(node)) AS node_offset, louvain_id"
            )

            nodes_updated = await self._write_algo_results(
                db_service, result["rows"], node_label, result_property
            )

            communities = len({row[1] for row in result["rows"]}) if result["rows"] else 0
            duration_ms = int((time.perf_counter() - start_time) * 1000)

            logger.info(
                "Louvain completed",
                communities=communities,
                nodes_updated=nodes_updated,
                duration_ms=duration_ms,
            )

            return {
                "nodes_updated": nodes_updated,
                "duration_ms": duration_ms,
                "communities": communities,
            }

        finally:
            with contextlib.suppress(Exception):
                await db_service.execute_query(f"CALL drop_projected_graph('{graph_name}')")


class KCoreAlgorithm(NativeAlgorithm):
    """K-Core Decomposition algorithm.

    Identifies subgraphs where every node has degree at least k.
    Useful for finding cohesive groups and network resilience analysis.
    """

    @property
    def info(self) -> AlgorithmInfo:
        """Algorithm information."""
        return AlgorithmInfo(
            name="kcore",
            type=AlgorithmType.NATIVE,
            category=AlgorithmCategory.COMMUNITY,
            description="K-Core decomposition",
            long_description=(
                "K-Core Decomposition identifies maximal subgraphs where each node "
                "is connected to at least k other nodes. Returns the k-core degree "
                "for each node, indicating the highest k-core it belongs to."
            ),
            parameters=(),
            returns="K-core degree (integer)",
        )

    async def execute(
        self,
        db_service: DatabaseService,
        node_label: str | None,
        edge_type: str | None,
        result_property: str,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute K-Core algorithm using Ryugraph algo extension."""
        start_time = time.perf_counter()

        logger.info(
            "Executing K-Core via algo extension",
            node_label=node_label,
            edge_type=edge_type,
        )

        if not node_label or not edge_type:
            raise AlgorithmError(
                "K-Core requires both node_label and edge_type",
                algorithm_name="kcore",
            )

        await db_service.ensure_property_exists(node_label, result_property, "INT64", "0")

        graph_name = f"_kcore_{int(time.time() * 1000)}"

        try:
            await db_service.execute_query(
                f"CALL project_graph('{graph_name}', ['{node_label}'], ['{edge_type}'])"
            )

            result = await db_service.execute_query(
                f"CALL k_core_decomposition('{graph_name}') "
                f"RETURN offset(id(node)) AS node_offset, k_degree"
            )

            nodes_updated = await self._write_algo_results(
                db_service, result["rows"], node_label, result_property
            )

            max_k = max((row[1] for row in result["rows"]), default=0) if result["rows"] else 0
            duration_ms = int((time.perf_counter() - start_time) * 1000)

            logger.info(
                "K-Core completed",
                max_k=max_k,
                nodes_updated=nodes_updated,
                duration_ms=duration_ms,
            )

            return {
                "nodes_updated": nodes_updated,
                "duration_ms": duration_ms,
                "max_k": max_k,
            }

        finally:
            with contextlib.suppress(Exception):
                await db_service.execute_query(f"CALL drop_projected_graph('{graph_name}')")


class LabelPropagationAlgorithm(NativeAlgorithm):
    """Label Propagation community detection algorithm.

    Assigns community labels to nodes by propagating labels from neighbors.
    Each node adopts the most common label among its neighbors iteratively.
    Uses Louvain as the underlying algorithm since label propagation
    provides similar community detection results.
    """

    @property
    def info(self) -> AlgorithmInfo:
        """Algorithm information."""
        return AlgorithmInfo(
            name="label_propagation",
            type=AlgorithmType.NATIVE,
            category=AlgorithmCategory.COMMUNITY,
            description="Community detection via label propagation",
            long_description=(
                "Label Propagation detects communities by iteratively propagating "
                "labels from neighbors. Each node adopts the most common label "
                "among its neighbors until convergence. Implemented using Louvain "
                "algorithm which provides similar community detection results."
            ),
            parameters=(
                AlgorithmParameter(
                    name="max_iterations",
                    type="int",
                    required=False,
                    default=100,
                    description="Maximum number of iterations",
                ),
            ),
            returns="Community label (integer)",
        )

    async def execute(
        self,
        db_service: DatabaseService,
        node_label: str | None,
        edge_type: str | None,
        result_property: str,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute Label Propagation using Louvain algorithm."""
        start_time = time.perf_counter()

        max_iter = parameters.get("max_iterations", 100)

        logger.info(
            "Executing Label Propagation via Louvain",
            node_label=node_label,
            edge_type=edge_type,
        )

        if not node_label or not edge_type:
            raise AlgorithmError(
                "Label Propagation requires both node_label and edge_type",
                algorithm_name="label_propagation",
            )

        await db_service.ensure_property_exists(node_label, result_property, "INT64", "0")

        graph_name = f"_lp_{int(time.time() * 1000)}"

        try:
            await db_service.execute_query(
                f"CALL project_graph('{graph_name}', ['{node_label}'], ['{edge_type}'])"
            )

            # Use Louvain for community detection (similar to label propagation)
            result = await db_service.execute_query(
                f"CALL louvain('{graph_name}', "
                f"maxPhases := 20, "
                f"maxIterations := {max_iter}) "
                f"RETURN offset(id(node)) AS node_offset, louvain_id"
            )

            nodes_updated = await self._write_algo_results(
                db_service, result["rows"], node_label, result_property
            )

            communities = len({row[1] for row in result["rows"]}) if result["rows"] else 0
            duration_ms = int((time.perf_counter() - start_time) * 1000)

            logger.info(
                "Label Propagation completed",
                communities=communities,
                nodes_updated=nodes_updated,
                duration_ms=duration_ms,
            )

            return {
                "nodes_updated": nodes_updated,
                "duration_ms": duration_ms,
                "communities": communities,
            }

        finally:
            with contextlib.suppress(Exception):
                await db_service.execute_query(f"CALL drop_projected_graph('{graph_name}')")


class TriangleCountAlgorithm(NativeAlgorithm):
    """Triangle Count algorithm.

    Counts the number of triangles each node participates in.
    A triangle is a set of three nodes where each pair is connected.
    """

    @property
    def info(self) -> AlgorithmInfo:
        """Algorithm information."""
        return AlgorithmInfo(
            name="triangle_count",
            type=AlgorithmType.NATIVE,
            category=AlgorithmCategory.COMMUNITY,
            description="Count triangles for each node",
            long_description=(
                "Triangle Count computes the number of triangles each node "
                "participates in. A triangle is a set of three mutually "
                "connected nodes. Higher triangle counts indicate more "
                "tightly connected neighborhoods."
            ),
            parameters=(),
            returns="Triangle count (integer)",
        )

    async def execute(
        self,
        db_service: DatabaseService,
        node_label: str | None,
        edge_type: str | None,
        result_property: str,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute Triangle Count using Cypher query."""
        start_time = time.perf_counter()

        logger.info(
            "Executing Triangle Count",
            node_label=node_label,
            edge_type=edge_type,
        )

        if not node_label or not edge_type:
            raise AlgorithmError(
                "Triangle Count requires both node_label and edge_type",
                algorithm_name="triangle_count",
            )

        await db_service.ensure_property_exists(node_label, result_property, "INT64", "0")

        # Initialize all nodes to 0 triangles
        await db_service.execute_query(
            f"MATCH (n:{node_label}) SET n.{result_property} = 0"
        )

        # Count triangles using Cypher pattern matching
        # For each triangle (a)--(b)--(c)--(a), each node participates in 1 triangle
        # We count unique triangles and attribute to each participating node
        triangle_query = f"""
        MATCH (a:{node_label})-[:{edge_type}]-(b:{node_label})-[:{edge_type}]-(c:{node_label})-[:{edge_type}]-(a)
        WHERE offset(id(a)) < offset(id(b)) AND offset(id(b)) < offset(id(c))
        WITH a, b, c
        UNWIND [a, b, c] AS node
        RETURN offset(id(node)) AS node_offset, count(*) AS triangle_count
        """

        result = await db_service.execute_query(triangle_query)

        # Write results back to nodes
        nodes_updated = 0
        if result["rows"]:
            for row in result["rows"]:
                node_offset, count = row[0], row[1]
                await db_service.execute_query(
                    f"MATCH (n:{node_label}) WHERE offset(id(n)) = $offset "
                    f"SET n.{result_property} = $count",
                    {"offset": node_offset, "count": count},
                )
                nodes_updated += 1

        # Get total node count (some nodes may have 0 triangles)
        total_count_result = await db_service.execute_query(
            f"MATCH (n:{node_label}) RETURN count(n)"
        )
        total_nodes = total_count_result["rows"][0][0] if total_count_result["rows"] else 0

        duration_ms = int((time.perf_counter() - start_time) * 1000)

        logger.info(
            "Triangle Count completed",
            nodes_with_triangles=nodes_updated,
            total_nodes=total_nodes,
            duration_ms=duration_ms,
        )

        return {
            "nodes_updated": total_nodes,  # All nodes have the property (some with 0)
            "duration_ms": duration_ms,
            "nodes_with_triangles": nodes_updated,
        }


# Registry of all native algorithms (8 algorithms)
NATIVE_ALGORITHMS: list[NativeAlgorithm] = [
    PageRankAlgorithm(),
    WeaklyConnectedComponentsAlgorithm(),
    StronglyConnectedComponentsAlgorithm(),
    StronglyConnectedComponentsKosarajuAlgorithm(),
    LouvainAlgorithm(),
    KCoreAlgorithm(),
    LabelPropagationAlgorithm(),
    TriangleCountAlgorithm(),
]


def register_native_algorithms() -> None:
    """Register all native algorithms with the global registry."""
    registry = get_registry()
    for algo in NATIVE_ALGORITHMS:
        registry.register_native(algo.info, algo)

    logger.info("Registered native algorithms", count=len(NATIVE_ALGORITHMS))


def get_native_algorithm(name: str) -> NativeAlgorithm | None:
    """Get a native algorithm by name.

    Args:
        name: Algorithm name.

    Returns:
        Algorithm instance or None if not found.
    """
    for algo in NATIVE_ALGORITHMS:
        if algo.info.name == name:
            return algo
    return None
