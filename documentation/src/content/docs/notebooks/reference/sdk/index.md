---
title: "SDK Reference"
---

<div class="nb-header">
  <span class="nb-header__type">Reference</span>
  <h1 class="nb-header__title">SDK Reference</h1>
  <p class="nb-header__subtitle">Complete API reference for the Graph OLAP Python SDK</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">2 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--beginner">
        <span class="nb-difficulty__dot"></span>
      </span>
      Beginner
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">Reference</span><span class="nb-header__tag">Index</span></div>
</div>

## SDK Reference Notebooks

This directory contains executable reference notebooks for every public class in the Graph OLAP SDK.
Each notebook demonstrates all methods with parameter tables, return types, and runnable examples.

### Client

| Notebook | Class | Role | Description |
|----------|-------|------|-------------|
| [grapholap_client.ipynb](grapholap_client/) | `GraphOLAPClient` | analyst | Client construction, `from_env()`, `quick_start()`, context manager |
| [instance_resource.ipynb](instance_resource/) | `InstanceResource` | analyst | Instance CRUD, lifecycle, health checks |
| [instance_connection.ipynb](instance_connection/) | `InstanceConnection` | analyst | Query execution, result conversion, schema, locks |
| [mapping_resource.ipynb](mapping_resource/) | `MappingResource` | analyst | Mapping CRUD, versioning, snapshots |

### Algorithms

| Notebook | Class | Role | Description |
|----------|-------|------|-------------|
| [algorithms.ipynb](algorithms/) | `AlgorithmManager` + `NetworkXManager` | analyst | Native algorithms, NetworkX bridge, generic `run()` |

### Data & Discovery

| Notebook | Class | Role | Description |
|----------|-------|------|-------------|
| [schema_resource.ipynb](schema_resource/) | `SchemaResource` | analyst | Catalog, schema, table, and column exploration |
| [favorite_resource.ipynb](favorite_resource/) | `FavoriteResource` | analyst | Bookmark frequently used resources |
| [health_resource.ipynb](health_resource/) | `HealthResource` | analyst | Platform health and readiness checks |

### Administration

| Notebook | Class | Role | Description |
|----------|-------|------|-------------|
| [user_resource.ipynb](user_resource/) | `UserResource` | admin | User CRUD, roles, deactivation |
| [admin_resource.ipynb](admin_resource/) | `AdminResource` | admin | Bulk delete with dry-run safety |
| [ops_resource.ipynb](ops_resource/) | `OpsResource` | ops | Lifecycle, concurrency, maintenance, jobs |

### Types & Errors

| Notebook | Class | Role | Description |
|----------|-------|------|-------------|
| [models.ipynb](models/) | All model classes | analyst | Data classes, enums, `PaginatedList` |
| [exceptions.ipynb](exceptions/) | Exception hierarchy | analyst | Error handling patterns, `exception_from_response()` |
