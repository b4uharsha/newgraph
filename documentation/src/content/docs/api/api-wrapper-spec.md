---
title: "API Specification: Wrapper Pod"
scope: hsbc
---

# API Specification: Wrapper Pod

## Overview

REST API specification for the Graph OLAP Wrapper Pods that run graph instances. Each instance runs in its own pod with an embedded graph database. The platform supports multiple wrapper types:

- **Ryugraph Wrapper** - Uses KuzuDB with NetworkX integration for algorithms
- **FalkorDB Wrapper** - Uses FalkorDBLite with native Cypher graph algorithms

Both wrappers share the same base API contract for health, query, schema, and lock endpoints. Algorithm endpoints differ based on the underlying database capabilities.

## Prerequisites

- [api.common.spec.md](--/api.common.spec.md) - **Authentication, error response format**
- [requirements.md](--/--/foundation/requirements.md) - Graph algorithms, lock model
- [ryugraph-networkx.reference.md](--/--/reference/ryugraph-networkx.reference.md) - Ryugraph technical details
- [architectural.guardrails.md](--/--/foundation/architectural.guardrails.md) - Implicit locking pattern

## Base URL

```
https://{domain}/{instance-id}
```

Note: Wrapper Pod endpoints are accessed via the instance-specific URL, not the Control Plane API base URL.

## Constraints

- One Ryugraph database per pod (file locking)
- Concurrent read queries allowed
- Exclusive lock for algorithm execution (implicit, automatic)
- Algorithm results written to node/edge properties, not exportable
- All operations are synchronous except algorithm execution

---

## Complete Endpoint Inventory

All wrapper endpoints are **SDK-facing** (accessible to external Jupyter notebooks via ingress):

### Common Endpoints (Both Wrappers)

| Endpoint | Method | Purpose | SDK Access |
|----------|--------|---------|------------|
| `/` | GET | API info and documentation | ✅ Public |
| `/health` | GET | Health check (liveness probe) | ✅ SDK |
| `/ready` | GET | Readiness check (readiness probe) | ✅ SDK |
| `/status` | GET | Detailed status (graph stats, lock info) | ✅ SDK |
| `/query` | POST | Execute Cypher query | ✅ SDK |
| `/schema` | GET | Get graph schema | ✅ SDK |
| `/lock` | GET | Get algorithm lock status | ✅ SDK |

### Ryugraph-Specific Algorithm Endpoints

| Endpoint | Method | Purpose | SDK Access |
|----------|--------|---------|------------|
| `/algo/{name}` | POST | Execute native Ryugraph algorithm | ✅ SDK |
| `/algo/algorithms` | GET | List native Ryugraph algorithms | ✅ SDK |
| `/algo/status/{execution_id}` | GET | Algorithm execution status | ✅ SDK |
| `/networkx/{name}` | POST | Execute NetworkX algorithm | ✅ SDK |
| `/networkx/algorithms` | GET | List NetworkX algorithms | ✅ SDK |
| `/networkx/algorithms/{name}` | GET | Get NetworkX algorithm details | ✅ SDK |

### FalkorDB-Specific Algorithm Endpoints

| Endpoint | Method | Purpose | SDK Access |
|----------|--------|---------|------------|
| `/algo/{algorithm_name}` | POST | Execute FalkorDB native algorithm | ✅ SDK |
| `/algo/status/{execution_id}` | GET | Poll algorithm execution status | ✅ SDK |
| `/algo/executions` | GET | List recent algorithm executions | ✅ SDK |
| `/algo/algorithms` | GET | List FalkorDB native algorithms | ✅ SDK |
| `/algo/algorithms/{algorithm_name}` | GET | Get algorithm details | ✅ SDK |
| `/algo/executions/{execution_id}` | DELETE | Cancel running execution | ✅ SDK |

**Future Internal Endpoints:**

When internal endpoints are added (e.g., `/internal/*`), they should be blocked from external access via ingress annotations. Currently, no internal endpoints exist.

**Instance Termination:**

Instance termination is handled by the Control Plane deleting the pod via Kubernetes API (see "Instance Termination" section below). There is no HTTP `/shutdown` endpoint.

---

## Health and Status

### Health Check (Liveness Probe)

```
GET /health
```

Kubernetes liveness probe. Always returns 200 if the process is alive. Does NOT check database state - that's the readiness probe's job.

**Response: 200 OK**

```json
{
  "status": "healthy",
  "timestamp": "2025-01-15T10:32:00Z"
}
```

Note: This endpoint always returns 200 unless the process itself is dead. Use `/ready` to check if the database is initialized and ready.

---

### Readiness Check

```
GET /ready
```

Kubernetes readiness probe. Returns 200 only when database is initialized and graph data is fully loaded.

**Response: 200 OK**

```json
{
  "status": "healthy",
  "timestamp": "2025-01-15T10:32:00Z"
}
```

**Response: 503 Service Unavailable**

```json
{
  "detail": "Service not ready - data not loaded"
}
```

---

### Get Status

```
GET /status
```

Detailed instance status including resource usage. Returns flat response (no `data` wrapper).

**Response: 200 OK**

```json
{
  "status": "running",
  "instance_id": "instance-uuid",
  "snapshot_id": "snapshot-123",
  "mapping_id": "mapping-456",
  "owner_username": "alice.smith",
  "ready": true,
  "started_at": "2025-01-15T10:00:00Z",
  "uptime_seconds": 3600,
  "node_count": 15000,
  "edge_count": 50000,
  "node_tables": ["Customer", "Product"],
  "edge_tables": ["PURCHASED"],
  "memory_usage_bytes": 536870912,
  "disk_usage_bytes": null,
  "lock": {
    "locked": false
  }
}
```

**Response: 200 OK (Starting/Loading)**

When instance is still initializing:

```json
{
  "status": "loading",
  "instance_id": "instance-uuid",
  "snapshot_id": "snapshot-123",
  "mapping_id": "mapping-456",
  "owner_username": "alice.smith",
  "ready": false,
  "started_at": "2025-01-15T10:00:00Z",
  "uptime_seconds": 30,
  "node_count": null,
  "edge_count": null,
  "node_tables": [],
  "edge_tables": [],
  "memory_usage_bytes": 104857600,
  "disk_usage_bytes": null,
  "lock": {
    "locked": false
  }
}
```

---

## Instance Termination

**Note:** Instance termination is handled by the Control Plane deleting the pod via Kubernetes API, not via an HTTP endpoint. There is no `/shutdown` endpoint implemented in the wrapper.

When the Control Plane deletes an instance:
1. Kubernetes sends SIGTERM to the wrapper pod
2. Wrapper lifespan shutdown handler closes Ryugraph gracefully
3. Pod terminates after cleanup or timeout (30s)

---

## Graph Operations

### Execute Cypher Query

```
POST /query
```

Execute a read-only Cypher query. Returns flat response (no `data` wrapper).

**Request Body:**

```json
{
  "query": "MATCH (c:Customer) WHERE c.city = 'London' RETURN c.name, c.customer_id LIMIT 10",
  "parameters": {},
  "timeout_ms": 60000
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| query | string | Yes | Cypher query to execute (1-100,000 chars) |
| parameters | object | No | Query parameters for parameterized queries |
| timeout_ms | integer | No | Query timeout in milliseconds (1000-1,800,000) |

**Response: 200 OK (Scalar/Property Values)**

```json
{
  "columns": ["c.name", "c.customer_id", "c.age", "c.created_at"],
  "column_types": ["STRING", "STRING", "INT64", "TIMESTAMP"],
  "rows": [
    ["Alice Smith", "C001", 32, "2024-01-15T10:30:00Z"],
    ["Bob Jones", "C002", 28, "2024-03-20T14:15:00Z"]
  ],
  "row_count": 2,
  "execution_time_ms": 15,
  "truncated": false
}
```

**Column Types**: The `column_types` array provides type metadata for each column, enabling the SDK to properly deserialize values:

| Wire Type | Ryugraph Type | SDK Conversion |
|-----------|---------------|----------------|
| `string` | `STRING` | `str` (as-is) |
| `number` | `INT64`, `INT32`, etc. | `int` |
| `number` | `DOUBLE`, `FLOAT` | `float` |
| `boolean` | `BOOL` | `bool` |
| `string` | `DATE` | Parse to `datetime.date` |
| `string` | `TIMESTAMP` | Parse to `datetime.datetime` |
| `string` | `INTERVAL` | Parse to `datetime.timedelta` |
| `string` | `UUID` | `str` or `uuid.UUID` |
| `string` | `BLOB` | Base64 decode to `bytes` |
| `array` | `LIST` | `list` (recursive) |
| `object` | `MAP`, `STRUCT` | `dict` |
| `object` | `NODE` | `dict` with `_id`, `_label` |
| `object` | `REL` | `dict` with `_type`, `_start`, `_end` |
| `array` | `PATH` | `list` of alternating NODE/REL |

**Response: 200 OK (Returning Nodes)**

When query returns nodes (e.g., `RETURN n`), each node is a structured object:

```json
{
  "columns": ["n"],
  "rows": [
    [{"_id": "Customer_C001", "_label": "Customer", "name": "Alice Smith", "city": "London", "age": 32}],
    [{"_id": "Customer_C002", "_label": "Customer", "name": "Bob Jones", "city": "Paris", "age": 28}]
  ],
  "row_count": 2,
  "execution_time_ms": 18,
  "truncated": false
}
```

**Response: 200 OK (Returning Nodes and Relationships)**

When query returns relationships, they include source/target references:

```json
{
  "columns": ["a", "r", "b"],
  "rows": [
    [
      {"_id": "Customer_C001", "_label": "Customer", "name": "Alice"},
      {"_id": "PURCHASED_0", "_type": "PURCHASED", "_start": "Customer_C001", "_end": "Product_P001", "amount": 99.99},
      {"_id": "Product_P001", "_label": "Product", "name": "Widget"}
    ]
  ],
  "row_count": 1,
  "execution_time_ms": 25,
  "truncated": false
}
```

| Field | Description |
|-------|-------------|
| `_id` | Unique node/relationship identifier |
| `_label` | Node label (for nodes) |
| `_type` | Relationship type (for relationships) |
| `_start` | Source node ID (for relationships) |
| `_end` | Target node ID (for relationships) |
| Other fields | Node/relationship properties |

**Response: 200 OK (Aggregation/Scalar)**

```json
{
  "columns": ["count(n)"],
  "rows": [[42]],
  "row_count": 1,
  "execution_time_ms": 5,
  "truncated": false
}
```

**Response: 400 Bad Request (Cypher Error)**

```json
{
  "error": {
    "code": "RYUGRAPH_ERROR",
    "message": "Cypher syntax error",
    "details": {
      "position": 45,
      "message": "Unknown function 'INVALID'"
    }
  }
}
```

**Response: 408 Request Timeout**

```json
{
  "error": {
    "code": "QUERY_TIMEOUT",
    "message": "Query exceeded timeout of 60000ms"
  }
}
```

---

### Get Schema

```
GET /schema
```

Returns the graph schema (node tables, relationship tables, properties). Returns flat response with structured table definitions.

**Response: 200 OK**

```json
{
  "node_tables": [
    {
      "label": "Customer",
      "primary_key": "customer_id",
      "primary_key_type": "STRING",
      "properties": {
        "customer_id": "STRING",
        "name": "STRING",
        "city": "STRING"
      },
      "node_count": 1000
    },
    {
      "label": "Product",
      "primary_key": "product_id",
      "primary_key_type": "STRING",
      "properties": {
        "product_id": "STRING",
        "name": "STRING",
        "category": "STRING"
      },
      "node_count": 500
    }
  ],
  "edge_tables": [
    {
      "type": "PURCHASED",
      "from_node": "Customer",
      "to_node": "Product",
      "properties": {
        "amount": "DOUBLE",
        "purchase_date": "DATE"
      },
      "edge_count": 2500
    }
  ],
  "total_nodes": 1500,
  "total_edges": 2500
}
```

---

### Extract Subgraph

```
POST /subgraph
```

Extract a subgraph as nodes and edges.

**Request Body:**

```json
{
  "cypher": "MATCH (c:Customer)-[p:PURCHASED]->(pr:Product) WHERE c.city = 'London' RETURN c, p, pr LIMIT 100"
}
```

**Response: 200 OK**

```json
{
  "data": {
    "nodes": [
      {"_id": "Customer_C001", "_label": "Customer", "name": "Alice Smith", "city": "London"},
      {"_id": "Product_P001", "_label": "Product", "name": "Widget", "category": "Electronics"}
    ],
    "edges": [
      {"_id": "PURCHASED_0", "_type": "PURCHASED", "_from": "Customer_C001", "_to": "Product_P001", "amount": 99.99}
    ],
    "node_count": 2,
    "edge_count": 1,
    "execution_time_ms": 45
  }
}
```

---

## Lock Status

### Get Lock Status

```
GET /lock
```

Check if instance is locked by an algorithm execution. Returns flat response.

**Response: 200 OK (Locked)**

```json
{
  "lock": {
    "locked": true,
    "holder_id": "user-uuid",
    "holder_username": "alice.smith",
    "algorithm_name": "pagerank",
    "execution_id": "exec-uuid",
    "acquired_at": "2025-01-15T14:00:00Z"
  }
}
```

**Response: 200 OK (Unlocked)**

```json
{
  "lock": {
    "locked": false
  }
}
```

---

## Algorithms

Algorithms execute asynchronously. The endpoint returns immediately with 202 Accepted, and the client should poll `/lock` or `/algo/status/:execution_id` for completion.

Algorithm availability depends on wrapper type:
- **Ryugraph**: Native algorithms + NetworkX integration (100+ algorithms)
- **FalkorDB**: Native graph algorithms via Cypher procedures (pagerank, betweenness, wcc, cdlp)

---

## Ryugraph Algorithms

The following sections document Ryugraph-specific algorithm endpoints. For FalkorDB algorithms, see [FalkorDB Algorithms](#falkordb-algorithms).

### Run Ryugraph Native Algorithm

```
POST /algo/{name}
```

**Supported algorithms:** pagerank, connected_components, shortest_path, louvain, label_propagation, triangle_count

**Request Body (PageRank):**

```json
{
  "node_label": "Customer",
  "property_name": "pr_score",
  "damping": 0.85,
  "max_iterations": 100,
  "tolerance": 1e-6
}
```

**Response: 202 Accepted**

```json
{
  "data": {
    "execution_id": "exec-uuid",
    "algorithm": "pagerank",
    "status": "running",
    "lock_acquired": true,
    "started_at": "2025-01-15T14:00:00Z"
  }
}
```

**Response: 409 Conflict (Locked)**

```json
{
  "error": {
    "code": "RESOURCE_LOCKED",
    "message": "Instance locked by user 'Alice Smith' running algorithm 'betweenness_centrality' since 2025-01-15T14:00:00Z",
    "details": {
      "holder_id": "user-uuid",
      "holder_name": "Alice Smith",
      "algorithm": "betweenness_centrality",
      "acquired_at": "2025-01-15T14:00:00Z"
    }
  }
}
```

**Response: 403 Forbidden** (not owner, not admin)

```json
{
  "error": {
    "code": "PERMISSION_DENIED",
    "message": "Only instance owner or admin can run algorithms",
    "details": {"owner_username": "other.user"}
  }
}
```

---

### List Available Native Algorithms

```
GET /algo/algorithms
```

Returns all available native Ryugraph algorithms. The SDK uses this for dynamic discovery.

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| category | string | Filter by category (centrality, community, pathfinding, etc.) |

**Response: 200 OK**

```json
{
  "algorithms": [
    {
      "name": "pagerank",
      "type": "native",
      "category": "centrality",
      "description": "Computes PageRank scores for nodes",
      "parameters": [
        {"name": "damping_factor", "type": "float", "required": false, "default": 0.85},
        {"name": "max_iterations", "type": "int", "required": false, "default": 100}
      ],
      "returns": "node_values"
    },
    {
      "name": "wcc",
      "type": "native",
      "category": "community",
      "description": "Finds weakly connected components",
      "parameters": [],
      "returns": "node_values"
    },
    {
      "name": "louvain",
      "type": "native",
      "category": "community",
      "description": "Detects communities using Louvain method",
      "parameters": [],
      "returns": "node_values"
    }
  ]
}
```

**Note:** Response uses `AlgorithmListResponse` from shared `graph-olap-schemas` package.

---

### Get Native Algorithm Details

```
GET /algo/algorithms/{name}
```

Returns detailed information about a specific native algorithm.

**Response: 200 OK**

```json
{
  "name": "pagerank",
  "type": "native",
  "category": "centrality",
  "description": "Computes PageRank scores for nodes",
  "long_description": "PageRank is an algorithm used to rank nodes in a graph based on their connectivity.",
  "parameters": [
    {
      "name": "damping_factor",
      "type": "float",
      "required": false,
      "default": 0.85,
      "description": "Damping factor for random walk probability"
    },
    {
      "name": "max_iterations",
      "type": "int",
      "required": false,
      "default": 100,
      "description": "Maximum iterations for convergence"
    }
  ],
  "returns": "node_values"
}
```

**Note:** Response uses `AlgorithmInfoResponse` from shared `graph-olap-schemas` package.

**Response: 404 Not Found**

```json
{
  "error": {
    "code": "ALGORITHM_NOT_FOUND",
    "message": "Unknown algorithm: 'invalid_algo'"
  }
}
```

---

### Run NetworkX Algorithm

```
POST /networkx/{name}
```

Runs any NetworkX algorithm by name using **dynamic reflection**. The wrapper discovers algorithms at runtime by introspecting the `networkx.algorithms` module, so new algorithms are automatically available when NetworkX is upgraded—no wrapper code changes required.

**How It Works:**

1. Wrapper uses `inspect.signature()` to discover function parameters at runtime
2. Any public function in `networkx.algorithms.*` is automatically available
3. Parameter validation happens at runtime based on function signatures
4. Algorithm metadata (params, defaults, docstrings) extracted via introspection

For implementation details, see [ryugraph-wrapper.design.md](--/--/component-designs/ryugraph-wrapper.design.md#networkx-algorithms-dynamic-discovery).

**Parameter Information Sources:**

| Info | Source | Availability |
|------|--------|--------------|
| Parameter names | `inspect.signature()` | Always |
| Required vs optional | `inspect.signature()` | Always |
| Default values | `inspect.signature()` | Always |
| Parameter types | `typing.get_type_hints()` | If type hints present |
| Parameter descriptions | Docstring parsing | If docstring present |

Most NetworkX functions have comprehensive NumPy-style docstrings and type hints (especially in NetworkX 3.0+), so parameter info is typically complete.

**Automatic Algorithm Discovery Benefits:**

- **Zero maintenance**: New NetworkX algorithms work immediately after `pip upgrade networkx`
- **Full coverage**: Access to 100+ algorithms without explicit mapping
- **Accurate params**: Parameter info always matches installed NetworkX version
- **Self-documenting**: Docstrings extracted from NetworkX source

**Algorithm Categories (examples, not exhaustive):**

| Category | Examples |
|----------|----------|
| Centrality | `degree_centrality`, `betweenness_centrality`, `closeness_centrality`, `eigenvector_centrality`, `katz_centrality`, `pagerank` |
| Community | `louvain_communities`, `girvan_newman`, `label_propagation_communities`, `greedy_modularity_communities` |
| Clustering | `clustering`, `triangles`, `transitivity`, `average_clustering` |
| Components | `connected_components`, `strongly_connected_components`, `weakly_connected_components` |
| Shortest Paths | `shortest_path`, `dijkstra_path`, `bellman_ford_path`, `all_pairs_shortest_path` |
| Link Analysis | `hits`, `pagerank`, `voterank` |
| Similarity | `jaccard_coefficient`, `adamic_adar_index`, `resource_allocation_index` |

**Request Body:**

Parameters vary by algorithm type. All fields except algorithm-specific requirements are optional.

```json
{
  "node_label": "Customer",
  "property_name": "result_property",
  "params": {
    "normalized": true,
    "k": 100
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| node_label | string | No | Node type to filter graph (default: all nodes) |
| edge_types | array | No | Edge types to include (default: all edges) |
| property_name | string | No | Property to store results. If omitted, results returned directly |
| params | object | No | Algorithm-specific parameters (passed to NetworkX function) |
| directed | boolean | No | Treat graph as directed (default: false) |
| weight_property | string | No | Edge property to use as weight |
| source | string | No | Source node ID (required for path algorithms) |
| target | string | No | Target node ID (required for path algorithms) |

**Algorithm-Specific Requirements:**

| Algorithm Type | Required Fields | Optional Fields |
|----------------|-----------------|-----------------|
| Node centrality | - | `node_label`, `property_name`, `params` |
| Edge centrality | - | `edge_types`, `property_name`, `params` |
| Community detection | - | `node_label`, `property_name`, `params` |
| Path algorithms | `source`, `target` | `weight_property`, `params` |
| Graph metrics | - | `node_label`, `params` |
| Link prediction | - | `node_label`, `params` |

**Response: 202 Accepted**

```json
{
  "data": {
    "execution_id": "exec-uuid",
    "algorithm": "betweenness_centrality",
    "status": "running",
    "lock_acquired": true,
    "started_at": "2025-01-15T14:00:00Z"
  }
}
```

**Response Variations by Algorithm Type:**

When `property_name` is provided, results are written to the graph:

```json
{
  "data": {
    "execution_id": "exec-uuid",
    "algorithm": "pagerank",
    "status": "completed",
    "result": {
      "property_name": "pr_score",
      "nodes_updated": 10000
    }
  }
}
```

When `property_name` is omitted, results are returned directly:

```json
{
  "data": {
    "execution_id": "exec-uuid",
    "algorithm": "pagerank",
    "status": "completed",
    "result": {
      "type": "node_values",
      "values": {"C001": 0.15, "C002": 0.08, "C003": 0.12}
    }
  }
}
```

Path algorithm response:

```json
{
  "data": {
    "execution_id": "exec-uuid",
    "algorithm": "shortest_path",
    "status": "completed",
    "result": {
      "type": "path",
      "path": ["C001", "C002", "C003"],
      "length": 2,
      "total_weight": 15.5
    }
  }
}
```

Graph metric response:

```json
{
  "data": {
    "execution_id": "exec-uuid",
    "algorithm": "density",
    "status": "completed",
    "result": {
      "type": "scalar",
      "value": 0.0342
    }
  }
}
```

Link prediction response:

```json
{
  "data": {
    "execution_id": "exec-uuid",
    "algorithm": "jaccard_coefficient",
    "status": "completed",
    "result": {
      "type": "edge_predictions",
      "predictions": [
        {"source": "C001", "target": "C005", "score": 0.85},
        {"source": "C002", "target": "C007", "score": 0.72}
      ]
    }
  }
}
```

**Response: 400 Bad Request (Unknown Algorithm)**

```json
{
  "error": {
    "code": "ALGORITHM_NOT_FOUND",
    "message": "Unknown NetworkX algorithm: 'invalid_algo'",
    "details": {
      "algorithm": "invalid_algo",
      "suggestion": "Use GET /networkx/algorithms to list available algorithms"
    }
  }
}
```

**Response: 400 Bad Request (Invalid Parameters)**

```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "Invalid parameter for betweenness_centrality: 'invalid_param'",
    "details": {
      "algorithm": "betweenness_centrality",
      "invalid_params": ["invalid_param"],
      "valid_params": ["k", "normalized", "weight", "endpoints", "seed"]
    }
  }
}
```

---

### List Available NetworkX Algorithms

```
GET /networkx/algorithms
```

Returns all available NetworkX algorithms, **dynamically discovered** from the installed NetworkX version. The list updates automatically when NetworkX is upgraded.

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| category | string | Filter by category (centrality, community, clustering, etc.) |
| search | string | Search algorithm names |

**Response: 200 OK**

```json
{
  "data": {
    "algorithms": [
      {
        "name": "betweenness_centrality",
        "category": "centrality",
        "description": "Compute betweenness centrality for nodes",
        "returns": "node_values",
        "params": [
          {"name": "k", "type": "int", "required": false, "description": "Sample size for approximation"},
          {"name": "normalized", "type": "bool", "required": false, "default": true},
          {"name": "weight", "type": "string", "required": false, "description": "Edge weight property"},
          {"name": "endpoints", "type": "bool", "required": false, "default": false},
          {"name": "seed", "type": "int", "required": false, "description": "Random seed for sampling"}
        ]
      },
      {
        "name": "louvain_communities",
        "category": "community",
        "description": "Find communities using Louvain algorithm",
        "returns": "node_values",
        "params": [
          {"name": "weight", "type": "string", "required": false},
          {"name": "resolution", "type": "float", "required": false, "default": 1.0},
          {"name": "threshold", "type": "float", "required": false, "default": 0.0000001},
          {"name": "seed", "type": "int", "required": false}
        ]
      }
    ],
    "categories": ["centrality", "community", "clustering", "components", "shortest_paths", "link_analysis", "similarity"],
    "total": 47
  }
}
```

---

### Get Algorithm Details

```
GET /networkx/algorithms/{name}
```

Returns detailed information about a specific algorithm including full parameter documentation.

**Response: 200 OK**

All parameter information is extracted dynamically via Python introspection:

```json
{
  "data": {
    "name": "betweenness_centrality",
    "category": "centrality",
    "description": "Compute betweenness centrality for nodes.",
    "long_description": "Betweenness centrality of a node v is the sum of the fraction of all-pairs shortest paths that pass through v.",
    "returns": "dict[node, float]",
    "networkx_function": "networkx.algorithms.centrality.betweenness_centrality",
    "documentation_url": "https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.centrality.betweenness_centrality.html",
    "params": [
      {
        "name": "k",
        "type": "int | None",
        "required": false,
        "default": null,
        "description": "If k is not None, use k node samples to estimate betweenness. The value of k <= n where n is the number of nodes in the graph. Higher values give better approximation."
      },
      {
        "name": "normalized",
        "type": "bool",
        "required": false,
        "default": true,
        "description": "If True the betweenness values are normalized by 2/((n-1)(n-2)) for graphs, and 1/((n-1)(n-2)) for directed graphs where n is the number of nodes in G."
      },
      {
        "name": "weight",
        "type": "str | None",
        "required": false,
        "default": null,
        "description": "If None, all edge weights are considered equal. Otherwise holds the name of the edge attribute used as weight."
      },
      {
        "name": "endpoints",
        "type": "bool",
        "required": false,
        "default": false,
        "description": "If True include the endpoints in the shortest path counts."
      },
      {
        "name": "seed",
        "type": "int | RandomState | None",
        "required": false,
        "default": null,
        "description": "Indicator of random number generation state. See Randomness for additional details."
      }
    ],
    "extracted_from": {
      "source": "introspection",
      "networkx_version": "3.6.1",
      "signature": "betweenness_centrality(G, k=None, normalized=True, weight=None, endpoints=False, seed=None)"
    },
    "example": {
      "request": {
        "node_label": "Customer",
        "property_name": "betweenness",
        "params": {"k": 100, "normalized": true}
      }
    }
  }
}
```

**Note:** The `params` array contains ALL parameters for the algorithm except `G` (the graph), which is provided internally by the wrapper. Parameter descriptions are parsed from the function's docstring.

**Response: 404 Not Found**

```json
{
  "error": {
    "code": "ALGORITHM_NOT_FOUND",
    "message": "Unknown algorithm: 'invalid_algo'"
  }
}
```

---

### Get Algorithm Execution Status

```
GET /algo/status/:execution_id
```

Poll this endpoint to check algorithm completion.

**Response: 200 OK (Running)**

```json
{
  "data": {
    "execution_id": "exec-uuid",
    "algorithm": "pagerank",
    "status": "running",
    "started_at": "2025-01-15T14:00:00Z",
    "elapsed_seconds": 30
  }
}
```

**Response: 200 OK (Completed)**

```json
{
  "data": {
    "execution_id": "exec-uuid",
    "algorithm": "pagerank",
    "status": "completed",
    "started_at": "2025-01-15T14:00:00Z",
    "completed_at": "2025-01-15T14:00:45Z",
    "duration_seconds": 45,
    "result": {
      "property_name": "pr_score",
      "nodes_updated": 10000
    }
  }
}
```

**Response: 200 OK (Failed)**

```json
{
  "data": {
    "execution_id": "exec-uuid",
    "algorithm": "pagerank",
    "status": "failed",
    "started_at": "2025-01-15T14:00:00Z",
    "failed_at": "2025-01-15T14:00:10Z",
    "error": "Convergence not reached within max_iterations"
  }
}
```

---

## FalkorDB Algorithms

FalkorDB wrapper provides native graph algorithms via Cypher procedures. Unlike Ryugraph, FalkorDB does NOT support NetworkX. All algorithms execute asynchronously with status polling.

**Supported Algorithms:**

| Algorithm | Cypher Procedure | Category | Description |
|-----------|-----------------|----------|-------------|
| `pagerank` | `pagerank.stream` | Centrality | Node importance based on incoming links |
| `betweenness` | `algo.betweenness` | Centrality | Bridge node identification |
| `wcc` | `algo.WCC` | Community | Weakly connected component IDs |
| `cdlp` | `algo.labelPropagation` | Community | Community detection via label propagation |

### Run FalkorDB Algorithm

```
POST /algo/{algorithm_name}
```

Start async execution of a graph algorithm. Returns immediately with execution_id for polling.

**Request Body:**

```json
{
  "result_property": "pagerank_score",
  "node_labels": ["Customer"],
  "relationship_types": ["PURCHASED"],
  "parameters": {},
  "write_back": true,
  "timeout_ms": 1800000
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| result_property | string | Yes | Property name to store results on nodes (1-64 chars) |
| node_labels | array | No | Node labels to include (null = all nodes) |
| relationship_types | array | No | Relationship types to traverse (null = all) |
| parameters | object | No | Algorithm-specific parameters |
| write_back | boolean | No | Write results to node properties (default: true) |
| timeout_ms | integer | No | Execution timeout 60000-7200000 ms (default: algorithm-specific) |

**Response: 202 Accepted**

Async execution started. Poll `/algo/status/{execution_id}` for completion.

```json
{
  "execution_id": "exec-uuid",
  "algorithm_name": "pagerank",
  "algorithm_type": "native",
  "status": "running",
  "started_at": "2025-01-15T14:00:00Z",
  "user_id": "user-uuid",
  "user_name": "alice.smith",
  "result_property": "pagerank_score",
  "write_back": true,
  "elapsed_ms": 1500
}
```

| Field | Type | Description |
|-------|------|-------------|
| execution_id | string | Unique execution ID for polling |
| elapsed_ms | integer | Elapsed time in milliseconds (available while running) |
| duration_ms | integer | Total execution time (set when completed) |

**Response: 400 Bad Request (Unknown Algorithm)**

```json
{
  "error": {
    "code": "QUERY_ERROR",
    "message": "Unknown algorithm: invalid_algo. Available: ['pagerank', 'betweenness', 'wcc', 'cdlp']",
    "details": {}
  }
}
```

**Response: 409 Conflict (Locked)**

```json
{
  "error": {
    "code": "RESOURCE_LOCKED",
    "message": "Instance locked by alice.smith running betweenness",
    "details": {
      "holder_id": "user-uuid",
      "holder_username": "alice.smith",
      "algorithm_name": "betweenness",
      "acquired_at": "2025-01-15T14:00:00Z"
    }
  }
}
```

---

### Get FalkorDB Execution Status

```
GET /algo/status/{execution_id}
```

Poll execution status. Terminal states: `completed`, `failed`, `cancelled`.

**Response: 200 OK (Running)**

```json
{
  "execution_id": "exec-uuid",
  "algorithm_name": "pagerank",
  "algorithm_type": "native",
  "status": "running",
  "started_at": "2025-01-15T14:00:00Z",
  "user_id": "user-uuid",
  "user_name": "alice.smith",
  "result_property": "pagerank_score",
  "write_back": true
}
```

**Response: 200 OK (Completed)**

```json
{
  "execution_id": "exec-uuid",
  "algorithm_name": "pagerank",
  "algorithm_type": "native",
  "status": "completed",
  "started_at": "2025-01-15T14:00:00Z",
  "completed_at": "2025-01-15T14:00:45Z",
  "user_id": "user-uuid",
  "user_name": "alice.smith",
  "result_property": "pagerank_score",
  "write_back": true,
  "nodes_updated": 10000,
  "duration_ms": 45000
}
```

**Response: 200 OK (Failed)**

```json
{
  "execution_id": "exec-uuid",
  "algorithm_name": "pagerank",
  "algorithm_type": "native",
  "status": "failed",
  "started_at": "2025-01-15T14:00:00Z",
  "completed_at": "2025-01-15T14:00:10Z",
  "user_id": "user-uuid",
  "user_name": "alice.smith",
  "result_property": "pagerank_score",
  "error_message": "Query timeout exceeded"
}
```

**Response: 404 Not Found**

```json
{
  "detail": "Execution not found: invalid-uuid"
}
```

---

### List FalkorDB Executions

```
GET /algo/executions
```

List recent algorithm executions.

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| limit | integer | Max results (default: 20) |
| status_filter | string | Filter by status (pending, running, completed, failed, cancelled) |

**Response: 200 OK**

```json
{
  "executions": [
    {
      "execution_id": "exec-uuid-1",
      "algorithm_name": "pagerank",
      "algorithm_type": "native",
      "status": "completed",
      "started_at": "2025-01-15T14:00:00Z",
      "completed_at": "2025-01-15T14:00:45Z",
      "user_id": "user-uuid",
      "user_name": "alice.smith",
      "result_property": "pagerank_score",
      "nodes_updated": 10000,
      "duration_ms": 45000
    }
  ],
  "total_count": 1
}
```

---

### List FalkorDB Algorithms

```
GET /algo/algorithms
```

List all available FalkorDB graph algorithms.

**Response: 200 OK**

```json
{
  "algorithms": [
    {
      "name": "pagerank",
      "display_name": "PageRank",
      "category": "centrality",
      "description": "Measures node importance based on incoming links",
      "cypher_procedure": "pagerank.stream",
      "supports_write_back": true,
      "default_timeout_ms": 300000,
      "parameters": [
        {"name": "node_label", "type": "string", "required": false, "default": null, "description": "Node label to filter (null = all nodes)"},
        {"name": "relationship_type", "type": "string", "required": false, "default": null, "description": "Relationship type to traverse (null = all)"}
      ]
    },
    {
      "name": "betweenness",
      "display_name": "Betweenness Centrality",
      "category": "centrality",
      "description": "Measures how often a node lies on shortest paths between other nodes",
      "cypher_procedure": "algo.betweenness",
      "supports_write_back": true,
      "default_timeout_ms": 3600000,
      "parameters": [
        {"name": "node_labels", "type": "list[string]", "required": false, "default": null, "description": "Node labels to include"},
        {"name": "relationship_types", "type": "list[string]", "required": false, "default": null, "description": "Relationship types to traverse"}
      ]
    },
    {
      "name": "wcc",
      "display_name": "Weakly Connected Components",
      "category": "community",
      "description": "Finds groups of nodes connected by any path (ignoring direction)",
      "cypher_procedure": "algo.WCC",
      "supports_write_back": true,
      "default_timeout_ms": 300000,
      "parameters": [
        {"name": "node_labels", "type": "list[string]", "required": false, "default": null, "description": "Node labels to include"},
        {"name": "relationship_types", "type": "list[string]", "required": false, "default": null, "description": "Relationship types to traverse"}
      ]
    },
    {
      "name": "cdlp",
      "display_name": "Community Detection (Label Propagation)",
      "category": "community",
      "description": "Detects communities by propagating labels through the graph",
      "cypher_procedure": "algo.labelPropagation",
      "supports_write_back": true,
      "default_timeout_ms": 300000,
      "parameters": [
        {"name": "max_iterations", "type": "int", "required": false, "default": 10, "description": "Maximum iterations for convergence"}
      ]
    }
  ],
  "total_count": 4
}
```

---

### Get FalkorDB Algorithm Details

```
GET /algo/algorithms/{algorithm_name}
```

Get detailed information about a specific algorithm.

**Response: 200 OK**

```json
{
  "name": "pagerank",
  "display_name": "PageRank",
  "category": "centrality",
  "description": "Measures node importance based on incoming links",
  "cypher_procedure": "pagerank.stream",
  "supports_write_back": true,
  "default_timeout_ms": 300000,
  "parameters": [
    {"name": "node_label", "type": "string", "required": false, "default": null, "description": "Node label to filter (null = all nodes)"},
    {"name": "relationship_type", "type": "string", "required": false, "default": null, "description": "Relationship type to traverse (null = all)"}
  ]
}
```

**Response: 404 Not Found**

```json
{
  "detail": "Algorithm not found: invalid_algo"
}
```

---

### Cancel FalkorDB Execution

```
DELETE /algo/executions/{execution_id}
```

Cancel a running algorithm execution.

**Response: 200 OK**

```json
{
  "status": "cancelled",
  "execution_id": "exec-uuid"
}
```

**Response: 404 Not Found**

```json
{
  "detail": "Execution not found or not running: exec-uuid"
}
```

---

### FalkorDB Pathfinding Algorithms

Pathfinding algorithms in FalkorDB are executed synchronously via the `/query` endpoint using Cypher procedures:

**Breadth-First Search:**

```cypher
MATCH path = algo.BFS((a:Person {id: 'A'}), (b:Person {id: 'B'}))
RETURN path
```

**Shortest Path:**

```cypher
MATCH path = algo.shortestPath((a:Person {id: 'A'}), (b:Person {id: 'B'}))
RETURN path
```

These run in milliseconds and don't require async execution or locks.

---

## Algorithm Parameters Reference

### Ryugraph Native Algorithms

**PageRank:**

```json
{
  "node_label": "string (required)",
  "property_name": "string (required)",
  "damping": "float (default: 0.85)",
  "max_iterations": "int (default: 100)",
  "tolerance": "float (default: 1e-6)"
}
```

**Connected Components:**

```json
{
  "node_label": "string (required)",
  "property_name": "string (required)"
}
```

**Shortest Path:**

```json
{
  "source_id": "string (required)",
  "target_id": "string (required)",
  "weight_property": "string (optional)"
}
```

Returns path rather than writing to property:

```json
{
  "data": {
    "path": ["node1", "node2", "node3"],
    "total_weight": 5.2,
    "hop_count": 2
  }
}
```

**Louvain:**

```json
{
  "node_label": "string (required)",
  "property_name": "string (required)",
  "resolution": "float (default: 1.0)"
}
```

**Label Propagation:**

```json
{
  "node_label": "string (required)",
  "property_name": "string (required)",
  "max_iterations": "int (default: 100)"
}
```

**Triangle Count:**

```json
{
  "node_label": "string (required)",
  "property_name": "string (required)"
}
```

### NetworkX Algorithms

**Degree Centrality:**

```json
{
  "node_label": "string (required)",
  "property_name": "string (required)"
}
```

**Betweenness Centrality:**

```json
{
  "node_label": "string (required)",
  "property_name": "string (required)",
  "normalized": "bool (default: true)",
  "k": "int (optional, sample size for approximation)"
}
```

**Closeness Centrality:**

```json
{
  "node_label": "string (required)",
  "property_name": "string (required)"
}
```

**Eigenvector Centrality:**

```json
{
  "node_label": "string (required)",
  "property_name": "string (required)",
  "max_iterations": "int (default: 100)",
  "tolerance": "float (default: 1e-6)"
}
```

**Girvan-Newman:**

```json
{
  "node_label": "string (required)",
  "property_name": "string (required)",
  "levels": "int (default: 2)"
}
```

**Clustering Coefficient:**

```json
{
  "node_label": "string (required)",
  "property_name": "string (required)"
}
```

### FalkorDB Native Algorithms

All FalkorDB algorithm requests share these common fields:

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| result_property | string | Yes | - | Property name to store results (1-64 chars) |
| node_labels | array | No | null | Node labels to include (null = all nodes) |
| relationship_types | array | No | null | Relationship types to traverse (null = all) |
| write_back | bool | No | true | Write results to node properties |
| timeout_ms | int | No | algorithm-specific | Timeout (60000-7200000 ms) |
| parameters | object | No | {} | Algorithm-specific parameters |

**PageRank:**

```json
{
  "result_property": "pagerank_score",
  "node_labels": ["Customer"],
  "relationship_types": ["PURCHASED"],
  "write_back": true,
  "timeout_ms": 300000
}
```

Default timeout: 5 minutes (300,000 ms). Uses `pagerank.stream()` procedure.

**Betweenness Centrality:**

```json
{
  "result_property": "betweenness_score",
  "node_labels": ["Customer"],
  "relationship_types": ["PURCHASED"],
  "write_back": true,
  "timeout_ms": 3600000
}
```

Default timeout: 1 hour (3,600,000 ms) due to O(V*E) complexity. Uses `algo.betweenness()` procedure.

**Weakly Connected Components (WCC):**

```json
{
  "result_property": "component_id",
  "node_labels": ["Customer"],
  "relationship_types": ["PURCHASED"],
  "write_back": true,
  "timeout_ms": 300000
}
```

Default timeout: 5 minutes (300,000 ms). Uses `algo.WCC()` procedure. Result is component ID (integer).

**Community Detection Label Propagation (CDLP):**

```json
{
  "result_property": "community_id",
  "node_labels": ["Customer"],
  "relationship_types": ["PURCHASED"],
  "write_back": true,
  "timeout_ms": 300000,
  "parameters": {
    "max_iterations": 10
  }
}
```

Default timeout: 5 minutes (300,000 ms). Uses `algo.labelPropagation()` procedure.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| max_iterations | int | 10 | Maximum iterations for label propagation |

---

## Error Codes

### Common Error Codes (Both Wrappers)

| Code | HTTP Status | Description |
|------|-------------|-------------|
| QUERY_TIMEOUT | 408 | Query exceeded timeout |
| QUERY_SYNTAX_ERROR | 400 | Cypher syntax error |
| RESOURCE_LOCKED | 409 | Instance locked by algorithm |
| PERMISSION_DENIED | 403 | User cannot run algorithms on this instance |
| ALGORITHM_NOT_FOUND | 404 | Unknown algorithm name |
| EXECUTION_NOT_FOUND | 404 | Unknown execution ID |
| DATABASE_NOT_INITIALIZED | 503 | Database not ready for queries |

### Ryugraph-Specific Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| RYUGRAPH_ERROR | 400/500 | Cypher or graph operation error |

### FalkorDB-Specific Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| FALKORDB_ERROR | 400/500 | FalkorDB Cypher or graph operation error |

---

## Open Questions

See [decision.log.md](--/--/process/decision.log.md) for consolidated open questions and architecture decision records.
