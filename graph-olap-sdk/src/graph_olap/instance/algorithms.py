"""Algorithm execution managers."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from graph_olap.exceptions import (
    AlgorithmFailedError,
    AlgorithmTimeoutError,
    exception_from_response,
)
from graph_olap.models.common import AlgorithmExecution

if TYPE_CHECKING:
    import httpx


class AlgorithmManager:
    """Execute native Ryugraph algorithms via dynamic discovery.

    Supports all native Ryugraph algorithms through a generic interface
    with introspection capabilities. Results are written back to node properties.

    Example:
        >>> conn = client.instances.connect(instance_id)

        >>> # List available algorithms
        >>> algos = conn.algo.algorithms()
        >>> for algo in algos:
        ...     print(f"{algo['name']}: {algo['description']}")

        >>> # Get algorithm details
        >>> info = conn.algo.algorithm_info("pagerank")
        >>> print(info['parameters'])

        >>> # Run any algorithm via generic method
        >>> exec = conn.algo.run(
        ...     "pagerank",
        ...     node_label="Customer",
        ...     property_name="pr_score",
        ...     params={"damping_factor": 0.85}
        ... )

        >>> # Or use convenience methods
        >>> conn.algo.pagerank("Customer", "pr_score", damping=0.85)
    """

    def __init__(self, client: httpx.Client):
        """Initialize algorithm manager.

        Args:
            client: HTTP client for instance
        """
        self._client = client

    def algorithms(self, category: str | None = None) -> list[dict[str, Any]]:
        """List available native Ryugraph algorithms.

        Args:
            category: Filter by category (centrality, community, path, etc.)

        Returns:
            List of algorithm info dicts with name, category, description
        """
        params: dict[str, Any] = {}
        if category:
            params["category"] = category

        response = self._client.get("/algo/algorithms", params=params)
        # Wrapper returns AlgorithmListResponse with algorithms field
        data = response.json()
        return data.get("algorithms", data.get("data", []))

    def algorithm_info(self, algorithm: str) -> dict[str, Any]:
        """Get detailed info for an algorithm.

        Args:
            algorithm: Algorithm name

        Returns:
            Dict with name, category, description, parameters
        """
        response = self._client.get(f"/algo/algorithms/{algorithm}")
        # Wrapper returns AlgorithmInfoResponse directly
        return response.json()

    def run(
        self,
        algorithm: str,
        node_label: str | None = None,
        property_name: str | None = None,
        edge_type: str | None = None,
        *,
        params: dict[str, Any] | None = None,
        timeout: int = 300,
        wait: bool = True,
    ) -> AlgorithmExecution:
        """Run any native Ryugraph algorithm.

        Args:
            algorithm: Algorithm name (e.g., "pagerank", "wcc", "louvain")
            node_label: Target node label
            property_name: Property to store result
            edge_type: Relationship type to traverse
            params: Algorithm-specific parameters
            timeout: Max execution time in seconds
            wait: If True, block until completion

        Returns:
            AlgorithmExecution with status and results

        Example:
            >>> exec = conn.algo.run(
            ...     "louvain",
            ...     node_label="Customer",
            ...     property_name="community",
            ...     edge_type="KNOWS",
            ...     params={"max_phases": 20}
            ... )
        """
        # Build request body per wrapper API format
        body: dict[str, Any] = {}
        if node_label:
            body["node_label"] = node_label
        if edge_type:
            body["edge_type"] = edge_type
        if property_name:
            body["result_property"] = property_name
        if params:
            body["parameters"] = params

        # Retry on lock conflict — another algorithm may be running on this
        # instance. Wait briefly and retry up to 30 times (60s total).
        max_retries = 30
        for attempt in range(max_retries + 1):
            response = self._client.post(f"/algo/{algorithm}", json=body)

            if response.status_code in (200, 202):
                break

            # Check if it's a lock/conflict error (409 or lock-related message)
            if response.status_code == 409 and attempt < max_retries:
                time.sleep(2)
                continue

            self._handle_error(response)

        execution = AlgorithmExecution.from_api_response(response.json())

        if wait and execution.status == "running":
            return self._wait_for_completion(execution.execution_id, timeout)

        return execution

    # Convenience methods for common algorithms

    def pagerank(
        self,
        node_label: str,
        property_name: str,
        edge_type: str | None = None,
        *,
        damping: float = 0.85,
        max_iterations: int = 100,
        tolerance: float = 1e-6,
        timeout: int = 300,
        wait: bool = True,
    ) -> AlgorithmExecution:
        """Run PageRank algorithm.

        Args:
            node_label: Target node label
            property_name: Property to store result
            edge_type: Relationship type to traverse
            damping: Damping factor (default: 0.85)
            max_iterations: Maximum iterations
            tolerance: Convergence tolerance
            timeout: Max execution time in seconds
            wait: If True, block until completion

        Returns:
            AlgorithmExecution with status and results
        """
        return self.run(
            "pagerank",
            node_label=node_label,
            property_name=property_name,
            edge_type=edge_type,
            params={
                "damping_factor": damping,
                "max_iterations": max_iterations,
                "tolerance": tolerance,
            },
            timeout=timeout,
            wait=wait,
        )

    def connected_components(
        self,
        node_label: str,
        property_name: str,
        edge_type: str | None = None,
        *,
        timeout: int = 300,
        wait: bool = True,
    ) -> AlgorithmExecution:
        """Find weakly connected components.

        Args:
            node_label: Target node label
            property_name: Property to store component ID
            edge_type: Relationship type to traverse
            timeout: Max execution time in seconds
            wait: If True, block until completion

        Returns:
            AlgorithmExecution with status and results
        """
        return self.run(
            "wcc",
            node_label=node_label,
            property_name=property_name,
            edge_type=edge_type,
            timeout=timeout,
            wait=wait,
        )

    def scc(
        self,
        node_label: str,
        property_name: str,
        *,
        edge_type: str | None = None,
        timeout: int = 300,
        wait: bool = True,
    ) -> AlgorithmExecution:
        """Find strongly connected components.

        Args:
            node_label: Target node label
            property_name: Property to store component ID
            edge_type: Relationship type to traverse
            timeout: Max execution time in seconds
            wait: If True, block until completion

        Returns:
            AlgorithmExecution with status and results
        """
        return self.run(
            "scc",
            node_label=node_label,
            property_name=property_name,
            edge_type=edge_type,
            timeout=timeout,
            wait=wait,
        )

    def scc_kosaraju(
        self,
        node_label: str,
        property_name: str,
        *,
        edge_type: str | None = None,
        timeout: int = 300,
        wait: bool = True,
    ) -> AlgorithmExecution:
        """Find strongly connected components using Kosaraju's algorithm.

        Args:
            node_label: Target node label
            property_name: Property to store component ID
            edge_type: Relationship type to traverse
            timeout: Max execution time in seconds
            wait: If True, block until completion

        Returns:
            AlgorithmExecution with status and results
        """
        return self.run(
            "scc_kosaraju",
            node_label=node_label,
            property_name=property_name,
            edge_type=edge_type,
            timeout=timeout,
            wait=wait,
        )

    def louvain(
        self,
        node_label: str,
        property_name: str,
        *,
        edge_type: str | None = None,
        resolution: float = 1.0,
        timeout: int = 300,
        wait: bool = True,
    ) -> AlgorithmExecution:
        """Run Louvain community detection.

        Args:
            node_label: Target node label
            property_name: Property to store community ID
            edge_type: Relationship type to traverse
            resolution: Resolution parameter (higher = more communities)
            timeout: Max execution time in seconds
            wait: If True, block until completion

        Returns:
            AlgorithmExecution with status and results
        """
        return self.run(
            "louvain",
            node_label=node_label,
            property_name=property_name,
            edge_type=edge_type,
            params={"resolution": resolution} if resolution != 1.0 else None,
            timeout=timeout,
            wait=wait,
        )

    def kcore(
        self,
        node_label: str,
        property_name: str,
        *,
        edge_type: str | None = None,
        timeout: int = 300,
        wait: bool = True,
    ) -> AlgorithmExecution:
        """Run K-Core decomposition.

        Computes the k-core number for each node, which is the largest
        value k such that the node belongs to a k-core subgraph.

        Args:
            node_label: Target node label
            property_name: Property to store k-core number
            edge_type: Relationship type to traverse
            timeout: Max execution time in seconds
            wait: If True, block until completion

        Returns:
            AlgorithmExecution with status and results
        """
        return self.run(
            "kcore",
            node_label=node_label,
            property_name=property_name,
            edge_type=edge_type,
            timeout=timeout,
            wait=wait,
        )

    def shortest_path(
        self,
        source_id: Any,
        target_id: Any,
        *,
        relationship_types: list[str] | None = None,
        max_depth: int | None = None,
        timeout: int = 60,
    ) -> AlgorithmExecution:
        """Find shortest path between two nodes.

        Args:
            source_id: Source node ID
            target_id: Target node ID
            relationship_types: Filter by relationship types
            max_depth: Maximum path length
            timeout: Max execution time in seconds

        Returns:
            AlgorithmExecution with path in result
        """
        # Shortest path uses a different request format than other algorithms
        # since it returns the path in the result rather than writing to properties
        body: dict[str, Any] = {
            "source_id": str(source_id),
            "target_id": str(target_id),
        }
        if relationship_types:
            body["relationship_types"] = relationship_types
        if max_depth:
            body["max_depth"] = max_depth

        response = self._client.post("/algo/shortest_path", json=body)

        if response.status_code not in (200, 202):
            self._handle_error(response)

        return AlgorithmExecution.from_api_response(response.json())

    def label_propagation(
        self,
        node_label: str,
        property_name: str,
        edge_type: str | None = None,
        *,
        max_iterations: int = 100,
        timeout: int = 300,
        wait: bool = True,
    ) -> AlgorithmExecution:
        """Run label propagation for community detection.

        Args:
            node_label: Target node label
            property_name: Property to store label
            edge_type: Relationship type to traverse
            max_iterations: Maximum iterations
            timeout: Max execution time in seconds
            wait: If True, block until completion

        Returns:
            AlgorithmExecution with status and results
        """
        return self.run(
            "label_propagation",
            node_label=node_label,
            property_name=property_name,
            edge_type=edge_type,
            params={"max_iterations": max_iterations},
            timeout=timeout,
            wait=wait,
        )

    def triangle_count(
        self,
        node_label: str,
        property_name: str,
        edge_type: str | None = None,
        *,
        timeout: int = 300,
        wait: bool = True,
    ) -> AlgorithmExecution:
        """Count triangles for each node.

        Args:
            node_label: Target node label
            property_name: Property to store triangle count
            edge_type: Relationship type to traverse
            timeout: Max execution time in seconds
            wait: If True, block until completion

        Returns:
            AlgorithmExecution with status and results
        """
        return self.run(
            "triangle_count",
            node_label=node_label,
            property_name=property_name,
            edge_type=edge_type,
            timeout=timeout,
            wait=wait,
        )

    def _wait_for_completion(
        self,
        execution_id: str,
        timeout: int,
    ) -> AlgorithmExecution:
        """Wait for algorithm to complete.

        Args:
            execution_id: Execution ID to wait for
            timeout: Max wait time in seconds

        Returns:
            Completed AlgorithmExecution

        Raises:
            AlgorithmTimeoutError: If timeout exceeded
            AlgorithmFailedError: If algorithm fails
        """
        start = time.time()

        while time.time() - start < timeout:
            response = self._client.get(f"/algo/status/{execution_id}")

            if response.status_code != 200:
                self._handle_error(response)

            execution = AlgorithmExecution.from_api_response(response.json())

            if execution.status == "completed":
                return execution

            if execution.status == "failed":
                raise AlgorithmFailedError(f"Algorithm failed: {execution.error_message}")

            time.sleep(2)

        raise AlgorithmTimeoutError(f"Algorithm {execution_id} did not complete within {timeout}s")

    def _handle_error(self, response: Any) -> None:
        """Handle error response."""
        request_context = f"{response.request.method} {response.request.url.path}"
        try:
            error_data = response.json()
            error_code = error_data.get("error", {}).get("code")
            message = error_data.get("error", {}).get("message") or f"HTTP {response.status_code}"
            details = error_data.get("error", {}).get("details", {})
        except Exception:
            error_code = None
            message = response.text or f"HTTP {response.status_code}"
            details = {}

        raise exception_from_response(
            status_code=response.status_code,
            error_code=error_code,
            message=f"{request_context}: {message}",
            details=details,
        )


class NetworkXManager:
    """Execute NetworkX algorithms via dynamic discovery.

    Supports any of 500+ NetworkX algorithms through a generic interface.
    Results are written back to node/edge properties.

    Example:
        >>> conn = client.instances.connect(instance_id)

        >>> # Convenience methods for common algorithms
        >>> conn.networkx.degree_centrality("Customer", "degree_cent")
        >>> conn.networkx.betweenness_centrality("Customer", "betweenness")

        >>> # Generic method for any algorithm
        >>> conn.networkx.run(
        ...     "katz_centrality",
        ...     node_label="Customer",
        ...     property_name="katz",
        ...     params={"alpha": 0.1}
        ... )

        >>> # List available algorithms
        >>> algos = conn.networkx.algorithms(category="centrality")
    """

    def __init__(self, client: httpx.Client):
        """Initialize NetworkX manager.

        Args:
            client: HTTP client for instance
        """
        self._client = client

    def algorithms(self, category: str | None = None) -> list[dict[str, Any]]:
        """List available NetworkX algorithms.

        Args:
            category: Filter by category (centrality, community, clustering, etc.)

        Returns:
            List of algorithm info dicts with name, category, description
        """
        params: dict[str, Any] = {}
        if category:
            params["category"] = category

        response = self._client.get("/networkx/algorithms", params=params)
        # Wrapper returns AlgorithmListResponse with algorithms field directly
        data = response.json()
        return data.get("algorithms", data.get("data", []))

    def algorithm_info(self, algorithm: str) -> dict[str, Any]:
        """Get detailed info for an algorithm.

        Args:
            algorithm: Algorithm name

        Returns:
            Dict with name, category, description, parameters
        """
        response = self._client.get(f"/networkx/algorithms/{algorithm}")
        # Wrapper returns AlgorithmInfoResponse directly (no data wrapper)
        return response.json()

    def run(
        self,
        algorithm: str,
        node_label: str | None = None,
        property_name: str | None = None,
        *,
        params: dict[str, Any] | None = None,
        timeout: int = 300,
        wait: bool = True,
    ) -> AlgorithmExecution:
        """Run any NetworkX algorithm.

        Args:
            algorithm: Algorithm name (e.g., "betweenness_centrality")
            node_label: Target node label (for node algorithms)
            property_name: Property to store result
            params: Algorithm-specific parameters
            timeout: Max execution time in seconds
            wait: If True, block until completion

        Returns:
            AlgorithmExecution with status and results

        Example:
            >>> exec = conn.networkx.run(
            ...     "louvain_communities",
            ...     property_name="community",
            ...     params={"resolution": 1.5}
            ... )
        """
        # Build request body per wrapper API format
        body: dict[str, Any] = {}
        if node_label:
            body["node_label"] = node_label
        if property_name:
            body["result_property"] = property_name  # Wrapper uses result_property
        if params:
            body["parameters"] = params  # Wrapper uses parameters, not params

        # Retry on lock conflict — another algorithm may be running on this
        # instance. Wait briefly and retry up to 30 times (60s total).
        max_retries = 30
        for attempt in range(max_retries + 1):
            response = self._client.post(f"/networkx/{algorithm}", json=body)

            if response.status_code in (200, 202):
                break

            if response.status_code == 409 and attempt < max_retries:
                time.sleep(2)
                continue

            self._handle_error(response)

        # Wrapper returns AlgorithmResponse directly (no data wrapper)
        execution = AlgorithmExecution.from_api_response(response.json())

        if wait and execution.status == "running":
            return self._wait_for_completion(execution.execution_id, timeout)

        return execution

    # Convenience methods for common algorithms

    def degree_centrality(
        self,
        node_label: str,
        property_name: str,
        **kwargs: Any,
    ) -> AlgorithmExecution:
        """Calculate degree centrality."""
        return self.run("degree_centrality", node_label, property_name, **kwargs)

    def betweenness_centrality(
        self,
        node_label: str,
        property_name: str,
        *,
        k: int | None = None,
        **kwargs: Any,
    ) -> AlgorithmExecution:
        """Calculate betweenness centrality."""
        params = {"k": k} if k else {}
        return self.run(
            "betweenness_centrality",
            node_label,
            property_name,
            params=params,
            **kwargs,
        )

    def closeness_centrality(
        self,
        node_label: str,
        property_name: str,
        **kwargs: Any,
    ) -> AlgorithmExecution:
        """Calculate closeness centrality."""
        return self.run("closeness_centrality", node_label, property_name, **kwargs)

    def eigenvector_centrality(
        self,
        node_label: str,
        property_name: str,
        *,
        max_iter: int = 100,
        **kwargs: Any,
    ) -> AlgorithmExecution:
        """Calculate eigenvector centrality."""
        return self.run(
            "eigenvector_centrality",
            node_label,
            property_name,
            params={"max_iter": max_iter},
            **kwargs,
        )

    def clustering_coefficient(
        self,
        node_label: str,
        property_name: str,
        **kwargs: Any,
    ) -> AlgorithmExecution:
        """Calculate clustering coefficient."""
        return self.run("clustering", node_label, property_name, **kwargs)

    def _wait_for_completion(
        self,
        execution_id: str,
        timeout: int,
    ) -> AlgorithmExecution:
        """Wait for algorithm to complete."""
        start = time.time()

        while time.time() - start < timeout:
            response = self._client.get(f"/networkx/status/{execution_id}")

            if response.status_code != 200:
                self._handle_error(response)

            # Wrapper returns AlgorithmResponse directly (no data wrapper)
            execution = AlgorithmExecution.from_api_response(response.json())

            if execution.status == "completed":
                return execution

            if execution.status == "failed":
                raise AlgorithmFailedError(f"Algorithm failed: {execution.error_message}")

            time.sleep(2)

        raise AlgorithmTimeoutError(
            f"NetworkX algorithm {execution_id} did not complete within {timeout}s"
        )

    def _handle_error(self, response: Any) -> None:
        """Handle error response."""
        request_context = f"{response.request.method} {response.request.url.path}"
        try:
            error_data = response.json()
            error_code = error_data.get("error", {}).get("code")
            message = error_data.get("error", {}).get("message") or f"HTTP {response.status_code}"
            details = error_data.get("error", {}).get("details", {})
        except Exception:
            error_code = None
            message = response.text or f"HTTP {response.status_code}"
            details = {}

        raise exception_from_response(
            status_code=response.status_code,
            error_code=error_code,
            message=f"{request_context}: {message}",
            details=details,
        )
