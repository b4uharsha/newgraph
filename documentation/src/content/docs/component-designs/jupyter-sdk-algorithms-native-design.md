---
title: "Jupyter SDK Native Algorithms Design"
scope: hsbc
---

# Jupyter SDK Native Algorithms Design

Native Ryugraph algorithm execution for the Jupyter SDK, providing dynamic discovery and execution of built-in graph algorithms.

## Prerequisites

- [jupyter-sdk.algorithms.design.md](-/jupyter-sdk.algorithms.design.md) - Algorithm overview and shared schemas
- [jupyter-sdk.connection.design.md](-/jupyter-sdk.connection.design.md) - Instance connection

## Related Components

- [ryugraph-wrapper.services.design.md](-/ryugraph-wrapper.services.design.md) - Server-side native algorithm implementation
- [api.wrapper.spec.md](--/system-design/api/api.wrapper.spec.md) - Native algorithm API endpoints

---

## Native Algorithm Manager (Dynamic Introspection)

The `AlgorithmManager` provides dynamic discovery and execution of native Ryugraph algorithms. This design mirrors the NetworkX approach - no SDK updates needed when new algorithms are added to the wrapper.

### Core Methods

```python
# instance/algorithms.py

class AlgorithmManager:
    """Execute native Ryugraph algorithms via dynamic discovery.

    Supports all native Ryugraph algorithms through a generic interface
    with introspection capabilities. Results are written back to node properties.
    """

    def __init__(self, client: httpx.Client):
        self._client = client

    def algorithms(self, category: str | None = None) -> list[dict[str, Any]]:
        """List available native Ryugraph algorithms.

        Args:
            category: Filter by category (centrality, community, pathfinding, etc.)

        Returns:
            List of algorithm info dicts with name, category, description

        Example:
            >>> algos = conn.algo.algorithms()
            >>> for algo in algos:
            ...     print(f"{algo['name']}: {algo['description']}")

            >>> # Filter by category
            >>> centrality = conn.algo.algorithms(category="centrality")
        """
        params = {"category": category} if category else {}
        response = self._client.get("/algo/algorithms", params=params)
        data = response.json()
        return data.get("algorithms", [])

    def algorithm_info(self, algorithm: str) -> dict[str, Any]:
        """Get detailed info for an algorithm.

        Args:
            algorithm: Algorithm name (e.g., "pagerank", "wcc", "louvain")

        Returns:
            Dict with name, type, category, description, parameters, returns

        Example:
            >>> info = conn.algo.algorithm_info("pagerank")
            >>> print(info['description'])
            >>> for param in info['parameters']:
            ...     print(f"  {param['name']}: {param['description']}")
        """
        response = self._client.get(f"/algo/algorithms/{algorithm}")
        return response.json()

    def run(
        self,
        algorithm: str,
        node_label: str | None = None,
        property_name: str | None = None,
        *,
        edge_type: str | None = None,
        params: dict[str, Any] | None = None,
        timeout: int = 300,
        wait: bool = True,
    ) -> AlgorithmExecution:
        """Run any native Ryugraph algorithm.

        This generic method provides access to all native algorithms without
        requiring SDK updates. Use algorithms() to discover available algorithms
        and algorithm_info() to get parameter documentation.

        Args:
            algorithm: Algorithm name (e.g., "pagerank", "wcc", "louvain")
            node_label: Target node label for results
            property_name: Property to store results
            edge_type: Filter to specific edge type (optional)
            params: Algorithm-specific parameters
            timeout: Max wait time in seconds
            wait: Wait for completion (default: True)

        Returns:
            AlgorithmExecution with status and results

        Examples:
            >>> # Run PageRank
            >>> exec = conn.algo.run(
            ...     "pagerank",
            ...     node_label="Customer",
            ...     property_name="pr_score",
            ...     params={"damping_factor": 0.85}
            ... )
            >>> print(f"Updated {exec.nodes_updated} nodes")

            >>> # Run Weakly Connected Components
            >>> exec = conn.algo.run(
            ...     "wcc",
            ...     node_label="Account",
            ...     property_name="component_id"
            ... )

            >>> # Run Louvain community detection
            >>> exec = conn.algo.run(
            ...     "louvain",
            ...     node_label="Customer",
            ...     property_name="community_id"
            ... )
        """
        body = {
            "node_label": node_label,
            "result_property": property_name,
            "parameters": params or {},
        }
        if edge_type:
            body["edge_type"] = edge_type

        response = self._client.post(f"/algo/{algorithm}", json=body)
        execution = AlgorithmExecution.from_api_response(response.json())

        if wait:
            return self._wait_for_completion(execution.execution_id, timeout)
        return execution
```

### Convenience Methods

Convenience methods wrap `run()` for common algorithms with better IDE autocomplete:

```python
    # Convenience methods call run() internally

    def pagerank(
        self,
        node_label: str,
        property_name: str,
        *,
        damping: float = 0.85,
        iterations: int = 20,
        wait: bool = True,
        timeout: int = 300,
    ) -> AlgorithmExecution:
        """Run PageRank algorithm."""
        return self.run(
            "pagerank",
            node_label=node_label,
            property_name=property_name,
            params={"damping_factor": damping, "max_iterations": iterations},
            wait=wait,
            timeout=timeout,
        )

    def wcc(
        self,
        node_label: str,
        property_name: str,
        wait: bool = True,
        timeout: int = 300,
    ) -> AlgorithmExecution:
        """Run Weakly Connected Components."""
        return self.run(
            "wcc",
            node_label=node_label,
            property_name=property_name,
            wait=wait,
            timeout=timeout,
        )

    def louvain(
        self,
        node_label: str,
        property_name: str,
        wait: bool = True,
        timeout: int = 300,
    ) -> AlgorithmExecution:
        """Run Louvain community detection."""
        return self.run(
            "louvain",
            node_label=node_label,
            property_name=property_name,
            wait=wait,
            timeout=timeout,
        )
```

### Usage Examples

```python
# ============================================================================
# ALGORITHM DISCOVERY
# ============================================================================

# List all native algorithms
>>> algos = conn.algo.algorithms()
>>> for algo in algos:
...     print(f"{algo['name']} ({algo['category']}): {algo['description']}")
pagerank (centrality): Computes PageRank scores for nodes
wcc (community): Finds weakly connected components
louvain (community): Detects communities using Louvain method
...

# Filter by category
>>> centrality = conn.algo.algorithms(category="centrality")

# Get detailed algorithm info
>>> info = conn.algo.algorithm_info("pagerank")
>>> print(info['parameters'])
[{'name': 'damping_factor', 'type': 'float', 'default': 0.85, ...},
 {'name': 'max_iterations', 'type': 'int', 'default': 20, ...}]

# ============================================================================
# GENERIC EXECUTION
# ============================================================================

# Run any algorithm via generic method
>>> exec = conn.algo.run(
...     "pagerank",
...     node_label="Customer",
...     property_name="pr_score",
...     params={"damping_factor": 0.85}
... )
>>> print(f"Status: {exec.status}, Updated: {exec.nodes_updated} nodes")

# ============================================================================
# CONVENIENCE METHODS
# ============================================================================

# Use typed convenience methods for common algorithms
>>> exec = conn.algo.pagerank("Customer", "pr_score", damping=0.85)
>>> exec = conn.algo.wcc("Account", "component_id")
>>> exec = conn.algo.louvain("Customer", "community_id")
```

---

## Additional Native Algorithms

Additional convenience methods for native algorithms:

```python
# Additional native algorithms in instance/algorithms.py

    def label_propagation(
        self,
        node_label: str,
        property_name: str,
        max_iterations: int = 100,
        wait: bool = True,
        timeout: int = 300,
    ) -> AlgorithmExecution:
        """Run label propagation community detection."""
        return self._execute(
            "label_propagation",
            {
                "node_label": node_label,
                "property_name": property_name,
                "max_iterations": max_iterations,
            },
            wait=wait,
            timeout=timeout,
        )

    def triangle_count(
        self,
        node_label: str,
        property_name: str,
        wait: bool = True,
        timeout: int = 300,
    ) -> AlgorithmExecution:
        """Run triangle count algorithm."""
        return self._execute(
            "triangle_count",
            {"node_label": node_label, "property_name": property_name},
            wait=wait,
            timeout=timeout,
        )
```

---

## Open Questions

See [decision.log.md](--/process/decision.log.md) for consolidated open questions.
