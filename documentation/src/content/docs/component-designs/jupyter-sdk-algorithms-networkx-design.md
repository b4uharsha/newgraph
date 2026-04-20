---
title: "Jupyter SDK NetworkX Algorithms Design"
scope: hsbc
---

<!-- Verified against SDK code on 2026-04-20 -->

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

### Algorithm Metadata Shape

The SDK does **not** expose dedicated `AlgorithmParam` / `AlgorithmInfo`
dataclasses. The manager returns the wrapper's raw JSON payloads as plain
`dict[str, Any]` — callers inspect them directly. Typed dataclasses were
considered but intentionally dropped because NetworkX's parameter surface is
too heterogeneous to model without forcing extra server-side normalization.

```python
# Typical shape of an algorithm info dict returned by the wrapper
>>> info = conn.networkx.algorithm_info("betweenness_centrality")
>>> info
{
    "name": "betweenness_centrality",
    "category": "centrality",
    "description": "Compute the shortest-path betweenness centrality for nodes.",
    "parameters": [
        {"name": "k", "type": "int", "required": False, "default": None},
        {"name": "normalized", "type": "bool", "required": False, "default": True},
    ],
    "networkx_function": "networkx.algorithms.centrality.betweenness_centrality",
}
```

---

## NetworkXManager Methods

```python
# Generic algorithm execution methods for NetworkXManager

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
        """
        Run any NetworkX algorithm by name.

        The public surface is intentionally small: ``algorithm``, a pair of
        targeting kwargs (``node_label`` / ``property_name``), plus a single
        ``params`` dict for algorithm-specific arguments. Selectors that used
        to live as named kwargs (``edge_types``, ``directed``, ``weight_property``,
        ``source``, ``target``, ``subgraph_query``) now belong inside
        ``params`` — the wrapper forwards them to NetworkX unchanged.

        Args:
            algorithm: NetworkX algorithm name (e.g., 'betweenness_centrality').
            node_label: Node type to filter graph (optional).
            property_name: Property to store results (optional — if omitted
                the wrapper returns results directly in the response).
            params: Algorithm-specific parameters + graph selectors.
                Common keys: ``edge_types``, ``directed``, ``weight_property``,
                ``source``, ``target``, ``subgraph_query``.
            timeout: Max wait time (seconds).
            wait: Wait for completion (default True).

        Returns:
            AlgorithmExecution with status and results.

        Examples:
            >>> # Centrality, results written back to a property
            >>> result = conn.networkx.run(
            ...     "betweenness_centrality",
            ...     node_label="Customer",
            ...     property_name="betweenness",
            ...     params={"k": 100, "normalized": True},
            ... )

            >>> # Shortest path — selectors live in `params`
            >>> result = conn.networkx.run(
            ...     "shortest_path",
            ...     params={
            ...         "source": "C001",
            ...         "target": "C099",
            ...         "weight_property": "distance",
            ...     },
            ... )
            >>> print(result.result["path"])

            >>> # Subgraph via params.subgraph_query
            >>> result = conn.networkx.run(
            ...     "louvain_communities",
            ...     property_name="community",
            ...     params={
            ...         "subgraph_query": "MATCH (c:Customer) WHERE c.region='EMEA' RETURN c",
            ...         "resolution": 1.5,
            ...     },
            ... )
        """
        body: dict[str, Any] = {}
        if node_label:
            body["node_label"] = node_label
        if property_name:
            body["result_property"] = property_name  # wrapper field
        if params:
            body["parameters"] = params               # wrapper field

        response = self._client.post(f"/networkx/{algorithm}", json=body)
        execution = AlgorithmExecution.from_api_response(response.json())

        if wait and execution.status == "running":
            return self._wait_for_completion(execution.execution_id, timeout)
        return execution

    def algorithms(
        self,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        List available NetworkX algorithms as raw dicts.

        The wrapper returns an ``AlgorithmListResponse`` with an
        ``algorithms`` field. The SDK returns those entries directly — there
        is no ``AlgorithmInfo`` dataclass wrapper.

        Args:
            category: Filter by category (centrality, community, clustering, etc.).

        Returns:
            List of dicts with ``name``, ``category``, ``description``,
            ``parameters``, etc. See "Algorithm Metadata Shape" above.
        """
        params: dict[str, Any] = {}
        if category:
            params["category"] = category

        response = self._client.get("/networkx/algorithms", params=params)
        data = response.json()
        return data.get("algorithms", data.get("data", []))

    def algorithm_info(self, algorithm: str) -> dict[str, Any]:
        """
        Get detailed info for a specific algorithm as a raw dict.

        The wrapper returns ``AlgorithmInfoResponse`` directly (no envelope).
        """
        response = self._client.get(f"/networkx/algorithms/{algorithm}")
        return response.json()

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

```

> **Note:** `girvan_newman` is not exposed as an SDK convenience method; it is reachable only via the raw `/networkx/{algorithm}` endpoint call if the wrapper supports it. Prefer Louvain (native, faster) for community detection.

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
[{"name": "louvain_communities", ...}, ...]

# Get detailed info (renders nicely in Jupyter)
>>> info = conn.networkx.algorithm_info("betweenness_centrality")
>>> info.params
[{"name": "k", "type": "int", "required": False, ...},
 {"name": "normalized", "type": "bool", "required": False, "default": True, ...},
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

# Shortest path between two nodes — selectors live in `params`
>>> result = conn.networkx.run(
...     "shortest_path",
...     params={"source": "C001", "target": "C099"},
... )
>>> print(result.result)
{"type": "path", "path": ["C001", "C042", "C099"], "length": 2}

# Weighted shortest path — selectors + weight_property live in `params`
>>> result = conn.networkx.run(
...     "dijkstra_path",
...     params={
...         "source": "LOC001",
...         "target": "LOC999",
...         "weight_property": "distance",
...     },
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

# Adamic-Adar index — edge_types lives in `params`
>>> result = conn.networkx.run(
...     "adamic_adar_index",
...     node_label="User",
...     params={"edge_types": ["FOLLOWS"]},
... )

# ============================================================================
# SUBGRAPH ALGORITHMS (run on subset of graph)
# ============================================================================

# Run algorithm only on nodes matching a Cypher query — subgraph_query in `params`
>>> result = conn.networkx.run(
...     "betweenness_centrality",
...     node_label="Customer",
...     property_name="bc",
...     params={
...         "subgraph_query": "MATCH (c:Customer)-[:PURCHASED]->() WHERE c.region = 'EMEA' RETURN c",
...     },
... )

# Community detection on high-value customers only
>>> result = conn.networkx.run(
...     "louvain_communities",
...     property_name="community",
...     params={
...         "subgraph_query": "MATCH (c:Customer) WHERE c.total_spend > 10000 RETURN c",
...     },
... )

# Shortest path within a filtered subgraph — all selectors in `params`
>>> result = conn.networkx.run(
...     "shortest_path",
...     params={
...         "source": "C001",
...         "target": "C099",
...         "subgraph_query": "MATCH (c:Customer) WHERE c.tier = 'Premium' RETURN c",
...     },
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
