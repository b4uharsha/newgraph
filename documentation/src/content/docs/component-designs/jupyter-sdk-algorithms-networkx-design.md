---
title: "Jupyter SDK NetworkX Algorithms Design"
scope: hsbc
---

# Jupyter SDK NetworkX Algorithms Design

NetworkX algorithm execution for the Jupyter SDK, providing access to 100+ algorithms via dynamic introspection.

> **Important:** NetworkX algorithms are only available for Ryugraph instances.
> FalkorDB instances do NOT support NetworkX. For FalkorDB algorithms, see [falkordb-wrapper.design.md](-/falkordb-wrapper.design.md).

## Prerequisites

- [jupyter-sdk.algorithms.design.md](-/jupyter-sdk.algorithms.design.md) - Algorithm overview and shared schemas
- [jupyter-sdk.connection.design.md](-/jupyter-sdk.connection.design.md) - Instance connection

## Related Components

- [ryugraph-wrapper.services.design.md](-/ryugraph-wrapper.services.design.md) - Server-side NetworkX implementation
- [api.wrapper.spec.md](--/system-design/api/api.wrapper.spec.md) - NetworkX algorithm API endpoints

---

## Generic NetworkX Algorithm Execution

The `NetworkXManager` provides a generic `run()` method that can execute **any** NetworkX algorithm by name. The wrapper uses **dynamic reflection** to discover algorithms at runtime from the installed NetworkX version, so:

- **No SDK updates needed** when new algorithms are added to NetworkX
- **No wrapper updates needed** - just `pip upgrade networkx`
- **Parameter info is always accurate** for the installed version
- **100+ algorithms available** out of the box

### Data Classes

```python
# instance/algorithms.py - Generic NetworkX support

from dataclasses import dataclass

@dataclass
class AlgorithmParam:
    """Algorithm parameter specification."""
    name: str
    type: str
    required: bool
    default: any = None
    description: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "AlgorithmParam":
        return cls(**data)


@dataclass
class AlgorithmInfo:
    """Detailed algorithm information."""
    name: str
    category: str
    description: str
    returns: str  # node_values, edge_values, scalar, graph
    params: list[AlgorithmParam]
    networkx_function: str | None = None
    documentation_url: str | None = None
    complexity: str | None = None
    notes: list[str] | None = None
    example: dict | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "AlgorithmInfo":
        return cls(
            name=data["name"],
            category=data["category"],
            description=data["description"],
            returns=data["returns"],
            params=[AlgorithmParam.from_dict(p) for p in data.get("params", [])],
            networkx_function=data.get("networkx_function"),
            documentation_url=data.get("documentation_url"),
            complexity=data.get("complexity"),
            notes=data.get("notes"),
            example=data.get("example"),
        )

    def _repr_html_(self) -> str:
        """Rich HTML display for Jupyter notebooks."""
        params_html = ""
        for p in self.params:
            req = "required" if p.required else f"default: {p.default}"
            params_html += f"<li><code>{p.name}</code> ({p.type}, {req}): {p.description}</li>"

        return f"""
        <div style="border: 1px solid #ddd; padding: 15px; border-radius: 5px;">
            <h4>{self.name}</h4>
            <span style="background: #6c757d; color: white; padding: 2px 8px; border-radius: 3px; font-size: 0.8em;">{self.category}</span>
            <p style="margin-top: 10px;">{self.description}</p>
            <h5>Parameters</h5>
            <ul>{params_html or "<li>No parameters</li>"}</ul>
            {f'<p><strong>Complexity:</strong> {self.complexity}</p>' if self.complexity else ''}
            {f'<p><a href="{self.documentation_url}" target="_blank">NetworkX Documentation</a></p>' if self.documentation_url else ''}
        </div>
        """
```

---

## NetworkXManager Methods

```python
# Generic algorithm execution methods for NetworkXManager

    def run(
        self,
        algorithm: str,
        *,  # Force keyword arguments for clarity
        node_label: str | None = None,
        property_name: str | None = None,
        params: dict | None = None,
        edge_types: list[str] | None = None,
        directed: bool = False,
        weight_property: str | None = None,
        source: str | None = None,
        target: str | None = None,
        subgraph_query: str | None = None,
        wait: bool = True,
        timeout: int = 300,
    ) -> AlgorithmExecution:
        """
        Run any NetworkX algorithm by name.

        This generic method provides access to the full NetworkX algorithm library
        without requiring SDK updates. Use algorithms() to discover available
        algorithms and algorithm_info() to get parameter documentation.

        Parameters vary by algorithm type - all are optional except where noted:

        **Graph Selection (all optional):**
        - node_label: Filter to specific node type
        - edge_types: Filter to specific edge types
        - directed: Treat graph as directed
        - weight_property: Edge property to use as weight
        - subgraph_query: Cypher query to select subset of nodes for algorithm

        **Result Handling:**
        - property_name: If provided, write results to this node/edge property
        - If omitted, results are returned directly in the response

        **Path Algorithms (required for shortest_path, etc.):**
        - source: Source node ID
        - target: Target node ID

        Args:
            algorithm: NetworkX algorithm name (e.g., 'betweenness_centrality')
            node_label: Node type to filter graph (optional)
            property_name: Property to store results (optional - if omitted, return directly)
            params: Algorithm-specific parameters (passed to NetworkX function)
            edge_types: Edge types to include (default: all edges)
            directed: Treat graph as directed (default: False)
            weight_property: Edge property to use as weight
            source: Source node ID (required for path algorithms)
            target: Target node ID (required for path algorithms)
            subgraph_query: Cypher query selecting nodes for subgraph (optional)
            wait: Wait for completion (default: True)
            timeout: Max wait time in seconds

        Returns:
            AlgorithmExecution with status and results

        Raises:
            AlgorithmNotFoundError: If algorithm name is invalid
            ValidationError: If required parameters are missing
            ResourceLockedError: If instance is locked

        Examples:
            >>> # Run centrality and write to property
            >>> result = conn.networkx.run(
            ...     algorithm="betweenness_centrality",
            ...     node_label="Customer",
            ...     property_name="betweenness",
            ...     params={"k": 100, "normalized": True}
            ... )

            >>> # Run centrality and get results directly (no property_name)
            >>> result = conn.networkx.run(
            ...     algorithm="pagerank",
            ...     node_label="Customer"
            ... )
            >>> print(result.result["values"])  # {"C001": 0.15, "C002": 0.08, ...}

            >>> # Find shortest path between nodes
            >>> result = conn.networkx.run(
            ...     algorithm="shortest_path",
            ...     source="C001",
            ...     target="C099",
            ...     weight_property="distance"
            ... )
            >>> print(result.result["path"])  # ["C001", "C042", "C099"]

            >>> # Calculate graph density (graph-level metric)
            >>> result = conn.networkx.run(algorithm="density")
            >>> print(result.result["value"])  # 0.0342

            >>> # Run community detection on full graph
            >>> result = conn.networkx.run(
            ...     algorithm="louvain_communities",
            ...     property_name="community",
            ...     params={"resolution": 1.5}
            ... )

            >>> # Link prediction
            >>> result = conn.networkx.run(
            ...     algorithm="jaccard_coefficient",
            ...     node_label="User"
            ... )
            >>> for pred in result.result["predictions"]:
            ...     print(f"{pred['source']} -> {pred['target']}: {pred['score']}")
        """
        body = {}

        # Graph selection (all optional)
        if node_label:
            body["node_label"] = node_label
        if edge_types:
            body["edge_types"] = edge_types
        if directed:
            body["directed"] = directed
        if weight_property:
            body["weight_property"] = weight_property

        # Result handling (optional)
        if property_name:
            body["property_name"] = property_name

        # Path algorithm parameters
        if source:
            body["source"] = source
        if target:
            body["target"] = target

        # Algorithm-specific parameters
        if params:
            body["params"] = params

        response = self._http.post(
            f"{self._base_url}/networkx/{algorithm}",
            json=body,
        )

        execution = AlgorithmExecution.from_dict(response["data"])

        if wait:
            return self._wait_for_completion(execution.execution_id, timeout)

        return execution

    def algorithms(
        self,
        category: str | None = None,
        search: str | None = None,
    ) -> list[AlgorithmInfo]:
        """
        List available NetworkX algorithms.

        Algorithms are discovered dynamically from the wrapper's installed
        NetworkX version. This list updates automatically when NetworkX
        is upgraded on the server.

        Args:
            category: Filter by category (centrality, community, clustering, etc.)
            search: Search algorithm names

        Returns:
            List of AlgorithmInfo objects with params extracted via introspection

        Example:
            >>> # List all centrality algorithms
            >>> algos = conn.networkx.algorithms(category="centrality")
            >>> for algo in algos:
            ...     print(f"{algo.name}: {algo.description}")

            >>> # Search for community detection algorithms
            >>> algos = conn.networkx.algorithms(search="community")

            >>> # Check what's available after NetworkX upgrade
            >>> new_algos = conn.networkx.algorithms(search="new_feature")
        """
        params = {}
        if category:
            params["category"] = category
        if search:
            params["search"] = search

        response = self._http.get(
            f"{self._base_url}/networkx/algorithms",
            params=params,
        )

        return [AlgorithmInfo.from_dict(a) for a in response["data"]["algorithms"]]

    def algorithm_info(self, name: str) -> AlgorithmInfo:
        """
        Get detailed information about a specific algorithm.

        Returns full parameter documentation, complexity analysis, and examples.
        In Jupyter notebooks, displays as rich HTML with parameter docs.

        Args:
            name: Algorithm name

        Returns:
            AlgorithmInfo with full details

        Example:
            >>> info = conn.networkx.algorithm_info("betweenness_centrality")
            >>> print(info.complexity)
            >>> for param in info.params:
            ...     print(f"{param.name}: {param.description}")

            >>> # In Jupyter, just display the object
            >>> conn.networkx.algorithm_info("louvain_communities")
        """
        response = self._http.get(f"{self._base_url}/networkx/algorithms/{name}")
        return AlgorithmInfo.from_dict(response["data"])

    def categories(self) -> list[str]:
        """
        Get available algorithm categories.

        Returns:
            List of category names

        Example:
            >>> categories = conn.networkx.categories()
            >>> # ['centrality', 'community', 'clustering', 'components', ...]
        """
        response = self._http.get(f"{self._base_url}/networkx/algorithms")
        return response["data"]["categories"]
```

---

## Convenience Methods

Convenience methods wrap `run()` for better IDE autocomplete and documentation:

```python
    # -------------------------------------------------------------------------
    # Convenience Methods (for common algorithms without needing params dict)
    # -------------------------------------------------------------------------

    def closeness_centrality(
        self,
        node_label: str,
        property_name: str,
        wait: bool = True,
        timeout: int = 300,
    ) -> AlgorithmExecution:
        """Run closeness centrality."""
        return self.run(
            "closeness_centrality",
            node_label=node_label,
            property_name=property_name,
            wait=wait,
            timeout=timeout,
        )

    def eigenvector_centrality(
        self,
        node_label: str,
        property_name: str,
        max_iterations: int = 100,
        tolerance: float = 1e-6,
        wait: bool = True,
        timeout: int = 300,
    ) -> AlgorithmExecution:
        """Run eigenvector centrality."""
        return self.run(
            "eigenvector_centrality",
            node_label=node_label,
            property_name=property_name,
            params={"max_iterations": max_iterations, "tolerance": tolerance},
            wait=wait,
            timeout=timeout,
        )

    def girvan_newman(
        self,
        node_label: str,
        property_name: str,
        levels: int = 2,
        wait: bool = True,
        timeout: int = 300,
    ) -> AlgorithmExecution:
        """Run Girvan-Newman community detection."""
        return self.run(
            "girvan_newman",
            node_label=node_label,
            property_name=property_name,
            params={"levels": levels},
            wait=wait,
            timeout=timeout,
        )
```

---

## Usage Examples

```python
# ============================================================================
# ALGORITHM DISCOVERY
# ============================================================================

# List all available algorithms
>>> algos = conn.networkx.algorithms()
>>> print(f"Total algorithms: {len(algos)}")
Total algorithms: 47

# Filter by category
>>> centrality_algos = conn.networkx.algorithms(category="centrality")
>>> for algo in centrality_algos:
...     print(f"  {algo.name}")
  degree_centrality
  betweenness_centrality
  closeness_centrality
  eigenvector_centrality
  katz_centrality
  pagerank
  ...

# Search algorithms
>>> conn.networkx.algorithms(search="community")
[AlgorithmInfo(name='louvain_communities', ...), ...]

# Get detailed info (renders nicely in Jupyter)
>>> info = conn.networkx.algorithm_info("betweenness_centrality")
>>> info.params
[AlgorithmParam(name='k', type='int', required=False, ...),
 AlgorithmParam(name='normalized', type='bool', required=False, default=True, ...),
 ...]

# ============================================================================
# NODE-LEVEL ALGORITHMS (centrality, clustering)
# ============================================================================

# Write results to node property (common pattern)
>>> result = conn.networkx.run(
...     algorithm="betweenness_centrality",
...     node_label="Customer",
...     property_name="betweenness",
...     params={"k": 100, "normalized": True}
... )
>>> # Results now queryable: MATCH (c:Customer) RETURN c.betweenness

# Return results directly (don't write to graph)
>>> result = conn.networkx.run(
...     algorithm="pagerank",
...     node_label="Customer"
... )
>>> print(result.result["values"])
{"C001": 0.15, "C002": 0.08, "C003": 0.12, ...}

# ============================================================================
# COMMUNITY DETECTION
# ============================================================================

# Louvain communities
>>> result = conn.networkx.run(
...     algorithm="louvain_communities",
...     property_name="community",
...     params={"resolution": 1.5}
... )

# Label propagation
>>> result = conn.networkx.run(
...     algorithm="label_propagation_communities",
...     property_name="community"
... )

# ============================================================================
# PATH ALGORITHMS
# ============================================================================

# Shortest path between two nodes
>>> result = conn.networkx.run(
...     algorithm="shortest_path",
...     source="C001",
...     target="C099"
... )
>>> print(result.result)
{"type": "path", "path": ["C001", "C042", "C099"], "length": 2}

# Weighted shortest path
>>> result = conn.networkx.run(
...     algorithm="dijkstra_path",
...     source="LOC001",
...     target="LOC999",
...     weight_property="distance"
... )
>>> print(result.result)
{"type": "path", "path": ["LOC001", "LOC042", "LOC999"], "length": 2, "total_weight": 156.7}

# ============================================================================
# GRAPH METRICS (return scalar values)
# ============================================================================

# Graph density
>>> result = conn.networkx.run(algorithm="density")
>>> print(result.result["value"])
0.0342

# Average clustering coefficient
>>> result = conn.networkx.run(
...     algorithm="average_clustering",
...     node_label="Customer"
... )
>>> print(result.result["value"])
0.287

# Number of connected components
>>> result = conn.networkx.run(algorithm="number_connected_components")
>>> print(result.result["value"])
3

# ============================================================================
# LINK PREDICTION
# ============================================================================

# Jaccard coefficient for potential edges
>>> result = conn.networkx.run(
...     algorithm="jaccard_coefficient",
...     node_label="User"
... )
>>> for pred in result.result["predictions"][:5]:
...     print(f"{pred['source']} -> {pred['target']}: {pred['score']:.3f}")
U001 -> U005: 0.850
U002 -> U007: 0.720
...

# Adamic-Adar index
>>> result = conn.networkx.run(
...     algorithm="adamic_adar_index",
...     node_label="User",
...     edge_types=["FOLLOWS"]
... )

# ============================================================================
# SUBGRAPH ALGORITHMS (run on subset of graph)
# ============================================================================

# Run algorithm only on nodes matching a Cypher query
>>> result = conn.networkx.run(
...     algorithm="betweenness_centrality",
...     node_label="Customer",
...     property_name="bc",
...     subgraph_query="MATCH (c:Customer)-[:PURCHASED]->() WHERE c.region = 'EMEA' RETURN c"
... )

# Community detection on high-value customers only
>>> result = conn.networkx.run(
...     algorithm="louvain_communities",
...     property_name="community",
...     subgraph_query="MATCH (c:Customer) WHERE c.total_spend > 10000 RETURN c"
... )

# Shortest path within a filtered subgraph
>>> result = conn.networkx.run(
...     algorithm="shortest_path",
...     source="C001",
...     target="C099",
...     subgraph_query="MATCH (c:Customer) WHERE c.tier = 'Premium' RETURN c"
... )

# ============================================================================
# COMBINING RESULTS
# ============================================================================

# Run multiple algorithms, then query combined results
>>> conn.networkx.run(algorithm="pagerank", node_label="Customer", property_name="pr")
>>> conn.networkx.run(algorithm="betweenness_centrality", node_label="Customer", property_name="bc")
>>> conn.networkx.run(algorithm="louvain_communities", property_name="community")

>>> df = conn.query_df('''
...     MATCH (c:Customer)
...     RETURN c.name, c.pr, c.bc, c.community
...     ORDER BY c.pr DESC
...     LIMIT 10
... ''')
```

---

## Open Questions

See [decision.log.md](--/process/decision.log.md) for consolidated open questions.
