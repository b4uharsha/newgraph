# Graph OLAP SDK Tutorials & Reference Guide

Welcome to the Graph OLAP Platform tutorials! These interactive Jupyter notebooks teach you how to create graph instances from your data warehouse tables, run graph algorithms, and discover insights in your data.

## Platform Architecture

The Graph OLAP Platform enables analysts to create ad-hoc graph instances from SQL queries, run graph algorithms (PageRank, Louvain, Centrality, etc.), and collaborate on graph analysis.

![Platform Architecture](assets/diagrams/platform-architecture/graph-olap-platform-architecture.png)

<details>
<summary>Architecture Overview</summary>

**Key Components:**

| Component | Purpose |
|-----------|---------|
| **Jupyter SDK** | Python client for programmatic access to all platform features |
| **Control Plane** | REST API managing resources, orchestrating workers and pods |
| **Export Workers** | KEDA-scaled workers that export data from Starburst to GCS |
| **Ryugraph Wrapper** | FastAPI pods with embedded Ryugraph database for queries and algorithms |
| **PostgreSQL** | Metadata storage for mappings, snapshots, instances |
| **GCS** | Parquet file storage for snapshot data |
| **Starburst** | Enterprise data warehouse (source data) |

</details>

---

## Quick Start (5 Minutes)

Get from zero to your first graph query in 5 minutes:

| Step | Notebook | What You'll Do |
|------|----------|----------------|
| 1 | [01_prerequisites](./platform-tests/01_prerequisites.ipynb) | Verify your environment is set up |
| 2 | [08_quick_start](./platform-tests/08_quick_start.ipynb) | Create a graph instance with one line of code |
| 3 | [04_cypher_basics](./platform-tests/04_cypher_basics.ipynb) | Run your first Cypher query |

---

## Learning Paths

### Path A: New Analyst Onboarding (Recommended)

Complete this path to become proficient with the Graph OLAP Platform:

| Step | Notebook | What You'll Learn | Duration |
|------|----------|-------------------|----------|
| 1 | [01_prerequisites](./platform-tests/01_prerequisites.ipynb) | Environment setup and connectivity | 5 min |
| 2 | [02_health_checks](./platform-tests/02_health_checks.ipynb) | Platform health monitoring | 5 min |
| 3 | [08_quick_start](./platform-tests/08_quick_start.ipynb) | One-liner graph creation | 10 min |
| 4 | [03_managing_resources](./platform-tests/03_managing_resources.ipynb) | Full resource lifecycle (CRUD) | 15 min |
| 5 | [04_cypher_basics](./platform-tests/04_cypher_basics.ipynb) | Cypher query fundamentals | 15 min |
| 6 | [06_graph_algorithms](./platform-tests/06_graph_algorithms.ipynb) | PageRank, communities, centrality | 20 min |
| 7 | [07_end_to_end_workflows](./platform-tests/07_end_to_end_workflows.ipynb) | Complete analyst workflows | 15 min |

**Total: ~85 minutes**

### Path B: Advanced Topics

After completing Path A, explore these advanced features:

| Notebook | Topic | Prerequisites |
|----------|-------|---------------|
| [05_exploring_schemas](./platform-tests/05_exploring_schemas.ipynb) | Browse data warehouse schemas | Path A |
| [09_handling_errors](./platform-tests/09_handling_errors.ipynb) | Error handling best practices | 04_cypher_basics |
| [10_bookmarks](./platform-tests/10_bookmarks.ipynb) | Organize favorites | 03_managing_resources |
| [11_instance_lifecycle](./platform-tests/11_instance_lifecycle.ipynb) | TTL, health, progress tracking | 03_managing_resources |
| [12_export_data](./platform-tests/12_export_data.ipynb) | Export to CSV/Parquet | 04_cypher_basics |
| [13_advanced_mappings](./platform-tests/13_advanced_mappings.ipynb) | Complex graph schemas | 03_managing_resources |
| [14_version_diffing](./platform-tests/14_version_diffing.ipynb) | Schema version comparison | 03_managing_resources |
| [15_background_jobs](./platform-tests/15_background_jobs.ipynb) | Async operation tracking | 03_managing_resources |

### Path C: Platform Administration

For admins and operators:

| Notebook | Topic | Required Role |
|----------|-------|---------------|
| [16_falkordb](./platform-tests/16_falkordb.ipynb) | Alternative graph engine | Analyst |
| [17_authorization](./platform-tests/17_authorization.ipynb) | RBAC and permissions | Analyst |
| [18_admin_operations](./platform-tests/18_admin_operations.ipynb) | Admin API operations | Admin |
| [19_ops_configuration](./platform-tests/19_ops_configuration.ipynb) | Platform configuration | Ops |

---

## Core Concepts

### The Three Resources

The Graph OLAP Platform has three core resource types that form a hierarchy:

```
Mapping (SQL Definition)
    └── Snapshot (Exported Data)
            └── Instance (Running Graph Database)
```

<details>
<summary><strong>Mapping</strong> - Define your graph structure</summary>

A **Mapping** is a reusable SQL definition that describes how to create a graph from your data warehouse tables.

- **Node Definitions**: SQL queries that define graph nodes (vertices)
- **Edge Definitions**: SQL queries that define graph edges (relationships)
- **Versioned**: Editing creates a new immutable version
- **Retention**: Kept until deleted or inactivity timeout (default: 30 days)

```python
mapping = client.mappings.create(
    name="Customer Network",
    node_definitions=[...],
    edge_definitions=[...]
)
```

</details>

<details>
<summary><strong>Snapshot</strong> - Export point-in-time data</summary>

A **Snapshot** is an export of data from your warehouse at a specific point in time.

- **Timestamped**: Captures data as it exists at creation time
- **Parquet Format**: Stored as optimized Parquet files in GCS
- **Status Flow**: pending → creating → ready (or failed)
- **Retention**: 7 days default (configurable)

```python
snapshot = client.snapshots.create_and_wait(
    mapping_id=mapping.id,
    name="Q4 2024 Data"
)
```

</details>

<details>
<summary><strong>Instance</strong> - Query and analyze your graph</summary>

An **Instance** is a running Ryugraph database loaded with snapshot data.

- **Ephemeral**: Auto-terminates after TTL (default: 24h) or inactivity
- **Queryable**: Execute Cypher queries and graph algorithms
- **One Pod per Instance**: Dedicated resources for your analysis

```python
instance = client.instances.create_and_wait(
    snapshot_id=snapshot.id,
    name="Analysis Instance"
)
conn = client.instances.connect(instance.id)
result = conn.query("MATCH (n) RETURN n LIMIT 10")
```

</details>

---

## API Quick Reference

### Resource Management

| Operation | SDK Method | Notebook |
|-----------|------------|----------|
| List mappings | `client.mappings.list()` | [03](./platform-tests/03_managing_resources.ipynb) |
| Create mapping | `client.mappings.create(...)` | [03](./platform-tests/03_managing_resources.ipynb) |
| Create snapshot | `client.snapshots.create_and_wait(...)` | [03](./platform-tests/03_managing_resources.ipynb) |
| Create instance | `client.instances.create_and_wait(...)` | [03](./platform-tests/03_managing_resources.ipynb) |
| Quick start | `client.quick_start(mapping_id)` | [08](./platform-tests/08_quick_start.ipynb) |

### Querying

| Operation | SDK Method | Notebook |
|-----------|------------|----------|
| Execute query | `conn.query(cypher)` | [04](./platform-tests/04_cypher_basics.ipynb) |
| Query to DataFrame | `conn.query_df(cypher)` | [04](./platform-tests/04_cypher_basics.ipynb) |
| Single value | `conn.query_scalar(cypher)` | [04](./platform-tests/04_cypher_basics.ipynb) |
| Single row | `conn.query_one(cypher)` | [04](./platform-tests/04_cypher_basics.ipynb) |
| Get schema | `conn.get_schema()` | [04](./platform-tests/04_cypher_basics.ipynb) |

### Algorithms

| Operation | SDK Method | Notebook |
|-----------|------------|----------|
| PageRank | `conn.algo.pagerank(...)` | [06](./platform-tests/06_graph_algorithms.ipynb) |
| Connected Components | `conn.algo.connected_components(...)` | [06](./platform-tests/06_graph_algorithms.ipynb) |
| Louvain Communities | `conn.algo.louvain(...)` | [06](./platform-tests/06_graph_algorithms.ipynb) |
| Shortest Path | `conn.algo.shortest_path(...)` | [06](./platform-tests/06_graph_algorithms.ipynb) |
| NetworkX algorithms | `conn.networkx.<algorithm>(...)` | [06](./platform-tests/06_graph_algorithms.ipynb) |

### Result Conversion

| Format | Method | Use Case |
|--------|--------|----------|
| Polars DataFrame | `result.to_polars()` | Fast analytics |
| Pandas DataFrame | `result.to_pandas()` | Compatibility |
| List of dicts | `result.to_list_of_dicts()` | JSON processing |
| NetworkX graph | `result.to_networkx()` | Graph visualization |
| CSV file | `result.to_csv(path)` | Export |
| Parquet file | `result.to_parquet(path)` | Big data export |

---

## Running the Notebooks

### Interactive (JupyterLab)

```bash
cd tools/local-dev
make jupyter
```

Then open notebooks in order and run cells sequentially.

### As E2E Tests

```bash
# Run all notebooks
cd tools/local-dev && make test CLUSTER=orbstack

# Run single notebook
make test CLUSTER=orbstack NOTEBOOK=04_cypher_basics
```

See [scripts/README.md](../scripts/README.md) for full test documentation.

---

## Prerequisites

- Python 3.10+
- Graph OLAP SDK installed (`pip install graph-olap`)
- Environment variables configured:
  - `GRAPH_OLAP_API_URL` - Control Plane API URL
  - `GRAPH_OLAP_API_KEY` - API authentication key

---

## Troubleshooting

<details>
<summary><strong>Connection refused to Control Plane</strong></summary>

1. Check if control-plane pod is running:
   ```bash
   kubectl get pods -n e2e-test -l app=control-plane
   ```
2. Check control-plane logs:
   ```bash
   kubectl logs -n e2e-test -l app=control-plane
   ```
3. Verify `GRAPH_OLAP_API_URL` is correct

</details>

<details>
<summary><strong>Snapshot stuck in "creating" status</strong></summary>

1. Check export worker logs:
   ```bash
   kubectl logs -n e2e-test -l app=export-worker
   ```
2. Verify Starburst connectivity
3. Check for SQL errors in the mapping definition

</details>

<details>
<summary><strong>Instance fails to start</strong></summary>

1. Check wrapper pod events:
   ```bash
   kubectl describe pod -n e2e-test -l app=ryugraph-wrapper
   ```
2. Verify snapshot data exists in GCS
3. Check for resource limits (memory, CPU)

</details>

<details>
<summary><strong>Query timeout errors</strong></summary>

1. Use `LIMIT` clause for large result sets
2. Check instance health: `conn.get_health()`
3. Consider query optimization (use indexes, projections)

</details>

---

## Additional Resources

- [System Architecture Design](../../../system-design/system.architecture.design.md)
- [SDK Design](../../../component-designs/jupyter-sdk.design.md)
- [API Specifications](../../../system-design/api/)
- [Requirements](../../../foundation/requirements.md)

---

## Notebook Index

| # | Notebook | Description | Duration |
|---|----------|-------------|----------|
| 01 | [01_prerequisites](./platform-tests/01_prerequisites.ipynb) | Setup verification | 5 min |
| 02 | [02_health_checks](./platform-tests/02_health_checks.ipynb) | Health endpoints | 5 min |
| 03 | [03_managing_resources](./platform-tests/03_managing_resources.ipynb) | CRUD operations | 15 min |
| 04 | [04_cypher_basics](./platform-tests/04_cypher_basics.ipynb) | Cypher queries | 15 min |
| 05 | [05_exploring_schemas](./platform-tests/05_exploring_schemas.ipynb) | Schema introspection | 10 min |
| 06 | [06_graph_algorithms](./platform-tests/06_graph_algorithms.ipynb) | Graph algorithms | 20 min |
| 07 | [07_end_to_end_workflows](./platform-tests/07_end_to_end_workflows.ipynb) | E2E workflows | 15 min |
| 08 | [08_quick_start](./platform-tests/08_quick_start.ipynb) | Quick start API | 10 min |
| 09 | [09_handling_errors](./platform-tests/09_handling_errors.ipynb) | Error handling | 10 min |
| 10 | [10_bookmarks](./platform-tests/10_bookmarks.ipynb) | Favorites feature | 10 min |
| 11 | [11_instance_lifecycle](./platform-tests/11_instance_lifecycle.ipynb) | TTL management | 15 min |
| 12 | [12_export_data](./platform-tests/12_export_data.ipynb) | Data export | 15 min |
| 13 | [13_advanced_mappings](./platform-tests/13_advanced_mappings.ipynb) | Complex mappings | 20 min |
| 14 | [14_version_diffing](./platform-tests/14_version_diffing.ipynb) | Schema diffing | 15 min |
| 15 | [15_background_jobs](./platform-tests/15_background_jobs.ipynb) | Async operations | 10 min |
| 16 | [16_falkordb](./platform-tests/16_falkordb.ipynb) | FalkorDB wrapper | 15 min |
| 17 | [17_authorization](./platform-tests/17_authorization.ipynb) | RBAC tests | 15 min |
| 18 | [18_admin_operations](./platform-tests/18_admin_operations.ipynb) | Admin API | 10 min |
| 19 | [19_ops_configuration](./platform-tests/19_ops_configuration.ipynb) | Ops configuration | 10 min |
