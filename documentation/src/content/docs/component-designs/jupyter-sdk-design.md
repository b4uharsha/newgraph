---
title: "Jupyter SDK Design"
scope: hsbc
---

# Jupyter SDK Design

## Overview

The Jupyter SDK is a Python client library providing the **sole user interface** for the Graph OLAP Platform. All platform operations - from creating graph mappings to querying instances - are performed through this SDK. There is no separate web interface or GUI; the SDK is the complete and authoritative interface for analysts interacting with the platform.

The SDK provides:

- **Control Plane Operations**: Full CRUD for mappings (create, read, update, delete, copy, list), instance lifecycle management (create, terminate, update CPU), and administrative operations
- **Data Plane Operations**: Cypher query execution and graph algorithms on running instances
- **Schema Discovery**: Browse Starburst catalog metadata to design mappings
- **Operational Management**: Cluster health monitoring, configuration, and bulk operations (admin role)

Designed for use in Jupyter notebooks, it emphasizes ergonomic API design, clear error messages, and seamless integration with pandas/polars DataFrames.

> **Note:** Explicit snapshot APIs have been disabled. Instances are created directly from mappings
> using `client.instances.create_from_mapping()`. The snapshot layer operates internally.

---

## SDK as the Sole User Interface

The Graph OLAP Platform is **notebook-first** by design. Unlike traditional enterprise platforms with web consoles, all user interactions happen through Python code in Jupyter notebooks:

| Operation Category | SDK Resource | Key Methods |
|--------------------|--------------|-------------|
| **Mapping Management** | `client.mappings` | `create()`, `list()`, `get()`, `update()`, `delete()`, `copy()` |
| **Instance Lifecycle** | `client.instances` | `create_from_mapping_and_wait()`, `terminate()`, `update_cpu()`, `list()` |
| **Graph Queries** | `conn.query()` | `query()`, `query_df()`, `query_scalar()`, `query_one()` |
| **Graph Algorithms** | `conn.algo` / `conn.networkx` | `pagerank()`, `louvain()`, `wcc()`, 500+ NetworkX algorithms |
| **Schema Discovery** | `client.schema` | `list_catalogs()`, `list_tables()`, `search_tables()` |
| **Favorites** | `client.favorites` | `add()`, `remove()`, `list()` |
| **Operations (Ops role)** | `client.ops` | `get_cluster_health()`, `get_lifecycle_config()`, `trigger_job()` |
| **Administration (Admin role)** | `client.admin` | `bulk_delete()` |
| **Health Checks** | `client.health` | `check()`, `ready()` |

### Why Notebook-First?

1. **Reproducibility**: All operations are code, making workflows reproducible and version-controllable
2. **Automation**: Scripts can automate common tasks without GUI interaction
3. **Integration**: Seamless integration with data science workflows (pandas, polars, visualization)
4. **Auditability**: Every operation is logged with the user who executed it
5. **Flexibility**: Power users can extend and customize workflows programmatically

## Prerequisites

- [requirements.md](--/foundation/requirements.md) - SDK interface requirements, user workflows
- [api.common.spec.md](--/system-design/api.common.spec.md) - API conventions, error codes, authentication
- [api.mappings.spec.md](--/system-design/api/api.mappings.spec.md), [api.snapshots.spec.md](--/system-design/api/api.snapshots.spec.md), [api.instances.spec.md](--/system-design/api/api.instances.spec.md) - Control Plane API specs
- [api.wrapper.spec.md](--/system-design/api/api.wrapper.spec.md) - Wrapper Pod API specs (query, algorithm endpoints)

## Related Components

- [control-plane.design.md](-/control-plane.design.md) - Server-side implementation of Control Plane APIs
- [ryugraph-wrapper.design.md](-/ryugraph-wrapper.design.md) - Server-side implementation of instance APIs
- [falkordb-wrapper.design.md](-/falkordb-wrapper.design.md) - FalkorDB wrapper implementation (alternative to Ryugraph)
- [jupyter-sdk.deployment.design.md](-/jupyter-sdk.deployment.design.md) - SDK packaging and Jupyter cluster deployment

## This Document Series

This is the core SDK design. Additional details are in:

- **[jupyter-sdk.connection.design.md](-/jupyter-sdk.connection.design.md)** - Instance connection, queries, visualization, exceptions
- **[jupyter-sdk.models.spec.md](-/jupyter-sdk.models.spec.md)** - Model definitions (Mapping, Snapshot, Instance, QueryResult, etc.)
- **[jupyter-sdk.algorithms.design.md](-/jupyter-sdk.algorithms.design.md)** - Algorithm extensions, pagination, quick start helper

## Constraints

- Python 3.9+ compatibility (Jupyter environment)
- Synchronous API by default (notebook-friendly), with async support
- Clear, actionable error messages for common failure modes
- Minimal dependencies (httpx, pydantic, polars optional)

---

## Package Structure

```
graph-olap-sdk/
├── src/
│   └── graph_olap/
│       ├── __init__.py          # Public API exports
│       ├── client.py            # Main GraphOLAPClient class
│       ├── config.py            # Configuration and authentication
│       ├── notebook.py          # Jupyter integration (connect(), init())
│       ├── testing.py           # E2E test fixtures and utilities
│       ├── styles/
│       │   └── notebook.css     # Embedded CSS design system (1506 lines)
│       ├── resources/
│       │   ├── __init__.py
│       │   ├── mappings.py      # MappingResource
│       │   ├── snapshots.py     # SnapshotResource
│       │   ├── instances.py     # InstanceResource
│       │   ├── favorites.py     # FavoriteResource
│       │   ├── ops.py           # OpsResource (config, cluster)
│       │   ├── health.py        # HealthResource (health, ready)
│       │   ├── schema.py        # SchemaResource (Starburst metadata)
│       │   └── admin.py         # AdminResource (bulk delete, privileged ops)
│       ├── instance/
│       │   ├── __init__.py
│       │   ├── connection.py    # InstanceConnection class
│       │   └── algorithms.py    # Algorithm execution
│       ├── models/
│       │   ├── __init__.py
│       │   ├── mapping.py       # Mapping, MappingVersion models
│       │   ├── snapshot.py      # Snapshot model
│       │   ├── instance.py      # Instance model
│       │   ├── execution.py     # AlgorithmExecution model
│       │   ├── ops.py           # Config, cluster, health models
│       │   └── common.py        # Shared types
│       ├── exceptions.py        # Exception hierarchy
│       ├── http.py              # HTTP client wrapper
│       └── utils/
│           ├── __init__.py
│           └── diff.py          # Diff utilities
├── tests/
├── examples/
│   ├── basic_workflow.ipynb
│   ├── algorithms.ipynb
│   └── visualization.ipynb
├── pyproject.toml
└── README.md
```

---

## Client Architecture

![client-architecture](diagrams/jupyter-sdk-design/client-architecture.svg)

<details>
<summary>Mermaid Source</summary>

```mermaid
flowchart TB
    accTitle: Jupyter SDK Client Architecture
    accDescr: Layered architecture from GraphOLAPClient through resources and HTTP to Control Plane API

    classDef client fill:#F3E5F5,stroke:#7B1FA2,stroke-width:2px,color:#4A148C
    classDef resource fill:#E1F5FE,stroke:#0277BD,stroke-width:2px,color:#01579B
    classDef http fill:#E8F5E9,stroke:#2E7D32,stroke-width:2px,color:#1B5E20
    classDef api fill:#E3F2FD,stroke:#1565C0,stroke-width:2px,color:#0D47A1
    classDef instance fill:#FFF3E0,stroke:#E65100,stroke-width:2px,color:#E65100

    subgraph SDK["Jupyter SDK"]
        CLIENT[GraphOLAPClient]:::client

        subgraph Resources
            MAP[MappingResource]:::resource
            SNAP[SnapshotResource]:::resource
            INST[InstanceResource]:::resource
            FAV[FavoriteResource]:::resource
            OPS[OpsResource]:::resource
            HEALTH[HealthResource]:::resource
        end

        HTTP[HTTPClient<br/>retry, auth, errors]:::http

        subgraph Instance["InstanceConnection"]
            CONN[Connection]:::instance
            ALGO[AlgorithmManager]:::instance
            NX[NetworkXManager]:::instance
        end
    end

    CP[Control Plane API]:::api
    WRAP[Wrapper Pod API]:::api

    CLIENT --> MAP & SNAP & INST & FAV & OPS & HEALTH
    MAP & SNAP & INST & FAV & OPS & HEALTH --> HTTP
    HTTP --> CP

    INST -.->|connect()| CONN
    CONN --> ALGO & NX
    CONN --> WRAP
```

</details>

### Main Client

```python
# client.py
from graph_olap.resources import (
    MappingResource,
    SnapshotResource,
    InstanceResource,
    FavoriteResource,
    OpsResource,
    HealthResource,
)
from graph_olap.http import HTTPClient
from graph_olap.config import Config

class GraphOLAPClient:
    """
    Main client for the Graph OLAP Platform.

    Example:
        >>> client = GraphOLAPClient(
        ...     api_url="https://graph.example.com",
        ...     api_key="your-api-key"
        ... )
        >>> mappings = client.mappings.list()
        >>> instance = client.instances.create(snapshot_id=123, name="My Graph")
    """

    def __init__(
        self,
        api_url: str,
        api_key: str | None = None,
        internal_api_key: str | None = None,
        username: str | None = None,
        *,
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        """
        Initialize the Graph OLAP client.

        Authentication modes (in priority order):
        - internal_api_key: Uses 'X-Internal-Api-Key' header (internal services)
        - api_key: Uses 'Authorization: Bearer {key}' header (production)
        - username: Uses 'X-Username' header (development/testing)

        Args:
            api_url: Base URL of the Control Plane API
            api_key: API key for authentication (Bearer token)
            internal_api_key: Internal API key (X-Internal-Api-Key header)
            username: Username for user-scoped routes (X-Username header)
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts for transient failures
        """
        self._config = Config(
            api_url=api_url.rstrip("/"),
            api_key=api_key,
            timeout=timeout,
            max_retries=max_retries,
        )
        self._http = HTTPClient(self._config)

        # Resource managers
        self.mappings = MappingResource(self._http)
        self.snapshots = SnapshotResource(self._http)
        self.instances = InstanceResource(self._http, self._config)
        self.favorites = FavoriteResource(self._http)
        self.ops = OpsResource(self._http)
        self.health = HealthResource(self._http)

    def close(self) -> None:
        """Close the HTTP client and release resources."""
        self._http.close()

    def __enter__(self) -> "GraphOLAPClient":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    @classmethod
    def from_env(
        cls,
        api_url: str | None = None,
        api_key: str | None = None,
        internal_api_key: str | None = None,
        username: str | None = None,
        **kwargs,
    ) -> "GraphOLAPClient":
        """
        Create client from environment variables.

        Environment Variables:
            GRAPH_OLAP_API_URL: Base URL for the control plane API
            GRAPH_OLAP_API_KEY: API key for authentication (Bearer token)
            GRAPH_OLAP_INTERNAL_API_KEY: Internal API key (X-Internal-Api-Key header)
            GRAPH_OLAP_USERNAME: Username for development/testing (X-Username header)
            GRAPH_OLAP_IN_CLUSTER_MODE: Set to "true" for in-cluster execution (default: "false")
            GRAPH_OLAP_NAMESPACE: Kubernetes namespace for service DNS (default: "graph-olap-local")

        Args:
            api_url: Override GRAPH_OLAP_API_URL
            api_key: Override GRAPH_OLAP_API_KEY
            internal_api_key: Override GRAPH_OLAP_INTERNAL_API_KEY
            username: Override GRAPH_OLAP_USERNAME
            **kwargs: Additional config options (timeout, max_retries)

        Returns:
            Configured GraphOLAPClient

        Raises:
            ValueError: If GRAPH_OLAP_API_URL is not set
        """
        config = Config.from_env(...)
        return cls(...)

    def quick_start(
        self,
        mapping_id: int,
        *,
        snapshot_name: str | None = None,
        instance_name: str | None = None,
        wait_timeout: int = 600,
    ) -> "InstanceConnection":
        """
        Quick start: create snapshot, instance, and connect in one call.

        Convenience method for the common workflow of going from a mapping
        to a connected instance ready for queries.

        Args:
            mapping_id: Mapping ID to use
            snapshot_name: Name for snapshot (defaults to "Quick Snapshot")
            instance_name: Name for instance (defaults to "Quick Instance")
            wait_timeout: Max time to wait for snapshot + instance creation

        Returns:
            InstanceConnection ready for queries

        Example:
            >>> conn = client.quick_start(mapping_id=1)
            >>> result = conn.query("MATCH (n) RETURN count(n)")
            >>> # Remember to terminate the instance when done!
        """
        ...
```

---

## Notebook Integration

The `graph_olap.notebook` module provides zero-config Jupyter integration:

```python
# notebook.py
from graph_olap.client import GraphOLAPClient

# Global client for notebook convenience
_current_client: GraphOLAPClient | None = None


def connect(
    api_url: str | None = None,
    api_key: str | None = None,
    **kwargs,
) -> GraphOLAPClient:
    """
    Connect to Graph OLAP Platform with auto-discovery.

    This is the recommended entry point for Jupyter notebooks.
    Configuration is auto-discovered from environment variables,
    or can be provided explicitly.

    Args:
        api_url: Override GRAPH_OLAP_API_URL environment variable
        api_key: Override GRAPH_OLAP_API_KEY environment variable
        **kwargs: Additional config options (timeout, max_retries)

    Returns:
        Configured GraphOLAPClient ready for use

    Raises:
        ValueError: If GRAPH_OLAP_API_URL is not set

    Example:
        >>> from graph_olap import notebook
        >>> client = notebook.connect()

        >>> # Or with explicit configuration
        >>> client = notebook.connect(
        ...     api_url="https://graph-olap.example.com",
        ...     api_key="sk-xxx",
        ... )

        >>> # Start working immediately
        >>> mappings = client.mappings.list()
    """
    global _current_client

    # Initialize itables for interactive DataFrames if available
    _setup_itables()

    # Create and store client
    _current_client = GraphOLAPClient.from_env(
        api_url=api_url,
        api_key=api_key,
        **kwargs,
    )

    return _current_client


def init(
    api_url: str | None = None,
    api_key: str | None = None,
    **kwargs,
) -> GraphOLAPClient:
    """Alias for connect() - initialize Graph OLAP SDK for notebooks."""
    return connect(api_url=api_url, api_key=api_key, **kwargs)


def get_client() -> GraphOLAPClient | None:
    """
    Get the current notebook client.

    Returns:
        Current GraphOLAPClient or None if not connected
    """
    return _current_client
```

**Quick Start (2 lines):**
```python
>>> from graph_olap import notebook
>>> client = notebook.connect()
```

---

## Configuration

**Reference:** ADR-073: Notebook Environment Variables Standardization

### Environment Variables

| Variable | Purpose | Example |
|----------|---------|---------|
| `GRAPH_OLAP_API_URL` | Control Plane API endpoint | `http://control-plane:8000` |
| `GRAPH_OLAP_IN_CLUSTER_MODE` | Enable in-cluster service DNS | `true` or `false` |
| `GRAPH_OLAP_API_KEY` | Bearer token for authentication | `sk-xxx` |
| `GRAPH_OLAP_USERNAME` | Username for development/testing | `e2e-test-user` |
| `GRAPH_OLAP_NAMESPACE` | Kubernetes namespace for service DNS | `graph-olap-local` |

### Environment Detection

The `notebook.connect()` function automatically detects the runtime environment:

```python
def connect() -> GraphOLAPClient:
    """Connect to API with automatic environment detection."""
    url = os.environ.get("GRAPH_OLAP_API_URL")

    if url:
        return GraphOLAPClient(url)

    # Auto-detect in-cluster mode
    if os.environ.get("GRAPH_OLAP_IN_CLUSTER_MODE") == "true":
        return GraphOLAPClient("http://control-plane.graph-olap.svc:8000")

    # Default for local development
    return GraphOLAPClient("http://localhost:8000")
```

---

## Testing Module

**Reference:** ADR-074: SDK Testing Module with Fixture Utilities

The `graph_olap.testing` module provides reusable fixtures and utilities for E2E tests.

### Module Components

```python
# graph_olap/testing.py

# Connection utilities
def connect() -> GraphOLAPClient: ...

# Fixture factory
class TestFixtures:
    def create_instance(self, **kwargs) -> Instance: ...
    def create_snapshot(self, **kwargs) -> Snapshot: ...
    def create_mapping(self, **kwargs) -> Mapping: ...
    def cleanup(self) -> None: ...  # Automatic resource cleanup

# Context managers
@contextmanager
def test_context(): ...

@contextmanager
def instance_context(name: str): ...

# Data factories
def random_name(prefix: str = "test") -> str: ...
```

### Usage in Tests

```python
# Before (50+ lines of boilerplate)
client = GraphOLAPClient(os.environ.get("API_URL"))
# ... complex setup and cleanup ...

# After (3 lines)
from graph_olap.testing import test_context

with test_context() as (client, fixtures):
    instance = fixtures.create_instance(name="test-instance")
    # test code - cleanup automatic
```

---

## Notebook Styling

**Reference:** ADR-091: SDK Embedded CSS Distribution

The SDK embeds the notebook CSS design system for zero-config styling in JupyterHub deployments.

### CSS Location

```python
# styles/__init__.py

from importlib import resources

def get_notebook_css() -> str:
    """Load the notebook CSS from package resources."""
    return resources.files(__package__).joinpath("notebook.css").read_text()
```

### Distribution Flow

The CSS is distributed via the SDK package and installed by init containers:

```
SDK Package                    JupyterHub Pod
┌─────────────┐               ┌─────────────────┐
│ graph_olap/ │               │ Init Container  │
│ styles/     │   pip install │                 │
│ notebook.css│──────────────►│ cp CSS to       │
│ (1506 lines)│               │ ~/.jupyter/     │
└─────────────┘               │ custom/         │
                              └─────────────────┘
```

See [notebook-design-system.md](--/standards/notebook-design-system.md) for CSS component documentation.

---

### HTTP Client

```python
# http.py
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from graph_olap.exceptions import (
    GraphOLAPError,
    AuthenticationError,
    NotFoundError,
    ValidationError,
    ConflictError,
    ServerError,
)

class HTTPClient:
    """HTTP client with retry logic and error handling."""

    def __init__(self, config: Config):
        self._config = config
        self._client = httpx.Client(
            base_url=config.api_url,
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=config.timeout,
        )

    def close(self) -> None:
        self._client.close()

    @retry(
        retry=retry_if_exception_type((httpx.ConnectError, httpx.ReadTimeout)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    def request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        json: dict | None = None,
    ) -> dict:
        """Make an HTTP request with error handling."""
        response = self._client.request(
            method=method,
            url=path,
            params=params,
            json=json,
        )

        return self._handle_response(response)

    def _handle_response(self, response: httpx.Response) -> dict:
        """Parse response and raise appropriate exceptions."""
        if response.status_code == 204:
            return {}

        try:
            data = response.json()
        except ValueError:
            raise ServerError(f"Invalid JSON response: {response.text}")

        if response.is_success:
            return data

        # Handle error responses
        error = data.get("error", {})
        code = error.get("code", "UNKNOWN_ERROR")
        message = error.get("message", "Unknown error")
        details = error.get("details", {})

        if response.status_code == 401:
            raise AuthenticationError(message)
        elif response.status_code == 403:
            raise PermissionDeniedError(message, details)
        elif response.status_code == 404:
            raise NotFoundError(message, details)
        elif response.status_code == 400:
            raise ValidationError(message, details)
        elif response.status_code == 409:
            if code == "RESOURCE_LOCKED":
                raise ResourceLockedError(message, details)
            elif code == "CONCURRENCY_LIMIT_EXCEEDED":
                raise ConcurrencyLimitError(message, details)
            elif code == "RESOURCE_HAS_DEPENDENCIES":
                raise DependencyError(message, details)
            else:
                raise ConflictError(message, details)
        elif response.status_code == 408:
            raise TimeoutError(message)
        elif response.status_code >= 500:
            raise ServerError(message)
        else:
            raise GraphOLAPError(f"{code}: {message}")

    def get(self, path: str, params: dict | None = None) -> dict:
        return self.request("GET", path, params=params)

    def post(self, path: str, json: dict | None = None) -> dict:
        return self.request("POST", path, json=json)

    def put(self, path: str, json: dict | None = None) -> dict:
        return self.request("PUT", path, json=json)

    def delete(self, path: str) -> dict:
        return self.request("DELETE", path)
```

---

## Resource Classes

### Mapping Resource

```python
# resources/mappings.py
from graph_olap.models import Mapping, MappingVersion, NodeDefinition, EdgeDefinition
from graph_olap.pagination import PaginatedList

class MappingResource:
    """Manage mapping definitions."""

    def __init__(self, http: HTTPClient):
        self._http = http

    def list(
        self,
        owner: str | None = None,
        search: str | None = None,
        created_after: str | None = None,
        created_before: str | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        offset: int = 0,
        limit: int = 50,
    ) -> PaginatedList[Mapping]:
        """
        List mappings with optional filters.

        Args:
            owner: Filter by owner username
            search: Text search on name and description
            created_after: Filter by created_at >= timestamp (ISO 8601)
            created_before: Filter by created_at <= timestamp (ISO 8601)
            sort_by: Field to sort by (name, created_at, current_version)
            sort_order: Sort direction (asc, desc)
            offset: Number of records to skip
            limit: Maximum records to return (max 100)

        Returns:
            PaginatedList of Mapping objects
        """
        params = {
            "offset": offset,
            "limit": min(limit, 100),
            "sort_by": sort_by,
            "sort_order": sort_order,
        }
        if owner:
            params["owner"] = owner
        if search:
            params["search"] = search
        if created_after:
            params["created_after"] = created_after
        if created_before:
            params["created_before"] = created_before

        response = self._http.get("/api/mappings", params=params)

        return PaginatedList(
            items=[Mapping.from_dict(m) for m in response["data"]],
            total=response["meta"]["total"],
            offset=response["meta"]["offset"],
            limit=response["meta"]["limit"],
        )

    def get(self, mapping_id: int) -> Mapping:
        """
        Get a mapping by ID (returns current version).

        Args:
            mapping_id: Mapping ID

        Returns:
            Mapping object with current version data

        Raises:
            NotFoundError: If mapping doesn't exist
        """
        response = self._http.get(f"/api/mappings/{mapping_id}")
        return Mapping.from_dict(response["data"])

    def get_version(self, mapping_id: int, version: int) -> MappingVersion:
        """
        Get a specific mapping version.

        Args:
            mapping_id: Mapping ID
            version: Version number

        Returns:
            MappingVersion object

        Raises:
            NotFoundError: If mapping or version doesn't exist
        """
        response = self._http.get(f"/api/mappings/{mapping_id}/versions/{version}")
        return MappingVersion.from_dict(response["data"])

    def list_versions(self, mapping_id: int) -> list[MappingVersion]:
        """List all versions of a mapping."""
        response = self._http.get(f"/api/mappings/{mapping_id}/versions")
        return [MappingVersion.from_dict(v) for v in response["data"]]

    def list_snapshots(self, mapping_id: int) -> PaginatedList["Snapshot"]:
        """List all snapshots for a mapping (across all versions)."""
        from graph_olap.models import Snapshot

        response = self._http.get(f"/api/mappings/{mapping_id}/snapshots")
        return PaginatedList(
            items=[Snapshot.from_dict(s) for s in response["data"]],
            total=response["meta"]["total"],
            offset=response["meta"]["offset"],
            limit=response["meta"]["limit"],
        )

    def create(
        self,
        name: str,
        description: str,
        node_definitions: list[NodeDefinition] | list[dict],
        edge_definitions: list[EdgeDefinition] | list[dict],
        ttl: str | None = None,
        inactivity_timeout: str | None = None,
    ) -> Mapping:
        """
        Create a new mapping.

        Args:
            name: Display name
            description: Description of the mapping
            node_definitions: List of node definitions (see NodeDefinition)
            edge_definitions: List of edge definitions (see EdgeDefinition)
            ttl: Time-to-live (ISO 8601 duration, e.g., "P7D")
            inactivity_timeout: Inactivity timeout (ISO 8601 duration)

        Returns:
            Created Mapping object

        Raises:
            ValidationError: If definitions are invalid or SQL fails validation
        """
        # Convert to dicts if needed
        nodes = [n.to_dict() if hasattr(n, "to_dict") else n for n in node_definitions]
        edges = [e.to_dict() if hasattr(e, "to_dict") else e for e in edge_definitions]

        body = {
            "name": name,
            "description": description,
            "node_definitions": nodes,
            "edge_definitions": edges,
        }
        if ttl:
            body["ttl"] = ttl
        if inactivity_timeout:
            body["inactivity_timeout"] = inactivity_timeout

        response = self._http.post("/api/mappings", json=body)
        return Mapping.from_dict(response["data"])

    def update(
        self,
        mapping_id: int,
        change_description: str,
        node_definitions: list[NodeDefinition] | list[dict] | None = None,
        edge_definitions: list[EdgeDefinition] | list[dict] | None = None,
    ) -> Mapping:
        """
        Update a mapping (creates a new version).

        Args:
            mapping_id: Mapping ID to update
            change_description: Description of what changed (required)
            node_definitions: New node definitions (optional, keeps current if None)
            edge_definitions: New edge definitions (optional, keeps current if None)

        Returns:
            Updated Mapping object with new version

        Raises:
            ValidationError: If change_description is empty or definitions invalid
            PermissionDeniedError: If not owner or admin
        """
        body = {"change_description": change_description}

        if node_definitions is not None:
            body["node_definitions"] = [
                n.to_dict() if hasattr(n, "to_dict") else n for n in node_definitions
            ]
        if edge_definitions is not None:
            body["edge_definitions"] = [
                e.to_dict() if hasattr(e, "to_dict") else e for e in edge_definitions
            ]

        response = self._http.put(f"/api/mappings/{mapping_id}", json=body)
        return Mapping.from_dict(response["data"])

    def delete(self, mapping_id: int) -> None:
        """
        Delete a mapping.

        Args:
            mapping_id: Mapping ID to delete

        Raises:
            DependencyError: If snapshots exist for this mapping
            PermissionDeniedError: If not owner or admin
        """
        self._http.delete(f"/api/mappings/{mapping_id}")

    def copy(self, mapping_id: int, new_name: str) -> Mapping:
        """
        Copy a mapping to create a new one.

        Args:
            mapping_id: Source mapping ID
            new_name: Name for the new mapping

        Returns:
            New Mapping object (you own it)
        """
        response = self._http.post(
            f"/api/mappings/{mapping_id}/copy",
            json={"name": new_name},
        )
        return Mapping.from_dict(response["data"])

    def set_lifecycle(
        self,
        mapping_id: int,
        ttl: str | None = None,
        inactivity_timeout: str | None = None,
    ) -> Mapping:
        """
        Set lifecycle parameters for a mapping.

        Args:
            mapping_id: Mapping ID
            ttl: Time-to-live (ISO 8601 duration) or None to clear
            inactivity_timeout: Inactivity timeout (ISO 8601 duration) or None to clear

        Returns:
            Updated Mapping object
        """
        body = {}
        if ttl is not None:
            body["ttl"] = ttl
        if inactivity_timeout is not None:
            body["inactivity_timeout"] = inactivity_timeout

        response = self._http.put(f"/api/mappings/{mapping_id}/lifecycle", json=body)
        return Mapping.from_dict(response["data"])

    def get_tree(
        self,
        mapping_id: int,
        *,
        include_instances: bool = True,
        status: str | None = None,
    ) -> dict:
        """
        Get full resource hierarchy for a mapping.

        Returns versions -> snapshots -> instances tree structure.

        Args:
            mapping_id: Mapping ID
            include_instances: Include instance details
            status: Filter snapshots by status

        Returns:
            Tree structure with versions, snapshots, and instances
        """
        params = {"include_instances": include_instances}
        if status:
            params["status"] = status

        response = self._http.get(f"/api/mappings/{mapping_id}/tree", params=params)
        return response["data"]

    def diff_versions(
        self,
        mapping_id: int,
        from_version: int,
        to_version: int,
    ) -> dict:
        """
        Compare two mapping versions.

        Args:
            mapping_id: Mapping ID
            from_version: Base version number
            to_version: Target version number

        Returns:
            Diff with summary and detailed changes for nodes/edges

        Example:
            >>> diff = client.mappings.diff_versions(1, from_version=2, to_version=3)
            >>> print(f"Added {diff['summary']['nodes_added']} nodes")
        """
        response = self._http.get(
            f"/api/mappings/{mapping_id}/versions/{from_version}/diff/{to_version}"
        )
        return response["data"]
```

### Snapshot Resource

```python
# resources/snapshots.py
import time
from graph_olap.models import Snapshot
from graph_olap.exceptions import TimeoutError as SDKTimeoutError

class SnapshotResource:
    """Manage data snapshots."""

    def __init__(self, http: HTTPClient):
        self._http = http

    def list(
        self,
        mapping_id: int | None = None,
        mapping_version: int | None = None,
        owner: str | None = None,
        status: str | None = None,
        search: str | None = None,
        created_after: str | None = None,
        created_before: str | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        offset: int = 0,
        limit: int = 50,
    ) -> PaginatedList[Snapshot]:
        """List snapshots with optional filters."""
        params = {
            "offset": offset,
            "limit": min(limit, 100),
            "sort_by": sort_by,
            "sort_order": sort_order,
        }
        if mapping_id is not None:
            params["mapping_id"] = mapping_id
        if mapping_version is not None:
            params["mapping_version"] = mapping_version
        if owner:
            params["owner"] = owner
        if status:
            params["status"] = status
        if search:
            params["search"] = search
        if created_after:
            params["created_after"] = created_after
        if created_before:
            params["created_before"] = created_before

        response = self._http.get("/api/snapshots", params=params)
        return PaginatedList(
            items=[Snapshot.from_dict(s) for s in response["data"]],
            total=response["meta"]["total"],
            offset=response["meta"]["offset"],
            limit=response["meta"]["limit"],
        )

    def get(self, snapshot_id: int) -> Snapshot:
        """Get a snapshot by ID."""
        response = self._http.get(f"/api/snapshots/{snapshot_id}")
        return Snapshot.from_dict(response["data"])

    def create(
        self,
        mapping_id: int,
        name: str,
        description: str | None = None,
        version: int | None = None,
        ttl: str | None = None,
        inactivity_timeout: str | None = None,
    ) -> Snapshot:
        """
        Create a new snapshot from a mapping.

        This triggers an async export job. The snapshot will be in 'pending'
        status initially, then 'creating' while exporting, then 'ready' when
        complete or 'failed' if there's an error.

        Args:
            mapping_id: Source mapping ID
            name: Display name
            description: Optional description
            version: Mapping version to use (defaults to current)
            ttl: Time-to-live (ISO 8601 duration)
            inactivity_timeout: Inactivity timeout (ISO 8601 duration)

        Returns:
            Snapshot object (status will be 'pending')
        """
        body = {
            "mapping_id": mapping_id,
            "name": name,
        }
        if description:
            body["description"] = description
        if version is not None:
            body["version"] = version
        if ttl:
            body["ttl"] = ttl
        if inactivity_timeout:
            body["inactivity_timeout"] = inactivity_timeout

        response = self._http.post("/api/snapshots", json=body)
        return Snapshot.from_dict(response["data"])

    def wait_until_ready(
        self,
        snapshot_id: int,
        timeout: int = 600,
        poll_interval: int = 5,
    ) -> Snapshot:
        """
        Wait for a snapshot to become ready.

        Args:
            snapshot_id: Snapshot ID to wait for
            timeout: Maximum time to wait in seconds
            poll_interval: Time between status checks in seconds

        Returns:
            Snapshot object with status='ready'

        Raises:
            TimeoutError: If snapshot doesn't become ready within timeout
            SnapshotFailedError: If snapshot status becomes 'failed'
        """
        start = time.time()

        while time.time() - start < timeout:
            snapshot = self.get(snapshot_id)

            if snapshot.status == "ready":
                return snapshot

            if snapshot.status == "failed":
                raise SnapshotFailedError(
                    f"Snapshot {snapshot_id} failed: {snapshot.error_message}"
                )

            time.sleep(poll_interval)

        raise SDKTimeoutError(
            f"Snapshot {snapshot_id} did not become ready within {timeout}s"
        )

    def delete(self, snapshot_id: int) -> None:
        """
        Delete a snapshot.

        Raises:
            DependencyError: If active instances exist
            PermissionDeniedError: If not owner or admin
        """
        self._http.delete(f"/api/snapshots/{snapshot_id}")

    def update(
        self,
        snapshot_id: int,
        name: str | None = None,
        description: str | None = None,
    ) -> Snapshot:
        """Update snapshot metadata."""
        body = {}
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description

        response = self._http.put(f"/api/snapshots/{snapshot_id}", json=body)
        return Snapshot.from_dict(response["data"])

    def set_lifecycle(
        self,
        snapshot_id: int,
        ttl: str | None = None,
        inactivity_timeout: str | None = None,
    ) -> Snapshot:
        """Set lifecycle parameters for a snapshot."""
        body = {}
        if ttl is not None:
            body["ttl"] = ttl
        if inactivity_timeout is not None:
            body["inactivity_timeout"] = inactivity_timeout

        response = self._http.put(f"/api/snapshots/{snapshot_id}/lifecycle", json=body)
        return Snapshot.from_dict(response["data"])

    def get_progress(self, snapshot_id: int) -> SnapshotProgress:
        """
        Get detailed creation progress for a snapshot.

        Args:
            snapshot_id: Snapshot ID

        Returns:
            SnapshotProgress with phase, steps, and completion info
        """
        response = self._http.get(f"/api/snapshots/{snapshot_id}/progress")
        return SnapshotProgress.from_api_response(response["data"])

    def retry(self, snapshot_id: int) -> Snapshot:
        """
        Retry a failed snapshot export.

        Args:
            snapshot_id: Snapshot ID (must be in 'failed' status)

        Returns:
            Snapshot object (status will be 'pending')

        Raises:
            InvalidStateError: If snapshot is not in 'failed' status
        """
        response = self._http.post(f"/api/snapshots/{snapshot_id}/retry")
        return Snapshot.from_dict(response["data"])

    def create_and_wait(
        self,
        mapping_id: int,
        name: str,
        *,
        description: str | None = None,
        version: int | None = None,
        ttl: str | None = None,
        inactivity_timeout: str | None = None,
        timeout: int = 600,
        poll_interval: int = 5,
        on_progress: Callable[[str, int, int], None] | None = None,
    ) -> Snapshot:
        """
        Create a snapshot and wait for it to become ready.

        Convenience method that combines create() and wait_until_ready().

        Args:
            mapping_id: Source mapping ID
            name: Snapshot name
            description: Optional description
            version: Mapping version to use (defaults to current)
            ttl: Time-to-live (ISO 8601 duration)
            inactivity_timeout: Inactivity timeout (ISO 8601 duration)
            timeout: Maximum wait time in seconds
            poll_interval: Time between status checks
            on_progress: Optional callback(phase, completed_steps, total_steps)

        Returns:
            Snapshot object with status='ready'

        Example:
            >>> def show_progress(phase, completed, total):
            ...     print(f"{phase}: {completed}/{total}")
            >>> snapshot = client.snapshots.create_and_wait(
            ...     mapping_id=1,
            ...     name="Analysis",
            ...     on_progress=show_progress,
            ... )
        """
        snapshot = self.create(
            mapping_id=mapping_id,
            name=name,
            description=description,
            version=version,
            ttl=ttl,
            inactivity_timeout=inactivity_timeout,
        )

        start = time.time()

        while time.time() - start < timeout:
            progress = self.get_progress(snapshot.id)

            if on_progress:
                on_progress(progress.phase, progress.completed_steps, progress.total_steps)

            if progress.status == "ready":
                return self.get(snapshot.id)

            if progress.status == "failed":
                raise SnapshotFailedError(
                    f"Snapshot {snapshot.id} failed: {progress.error_message}"
                )

            time.sleep(poll_interval)

        raise SDKTimeoutError(f"Snapshot {snapshot.id} did not complete within {timeout}s")
```

### Instance Resource

```python
# resources/instances.py
from graph_olap.models import Instance
from graph_olap.instance.connection import InstanceConnection

class InstanceResource:
    """Manage graph instances."""

    def __init__(self, http: HTTPClient, config: Config):
        self._http = http
        self._config = config

    def list(
        self,
        snapshot_id: int | None = None,
        owner: str | None = None,
        status: str | None = None,
        search: str | None = None,
        created_after: str | None = None,
        created_before: str | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        offset: int = 0,
        limit: int = 50,
    ) -> PaginatedList[Instance]:
        """List instances with optional filters."""
        params = {
            "offset": offset,
            "limit": min(limit, 100),
            "sort_by": sort_by,
            "sort_order": sort_order,
        }
        if snapshot_id is not None:
            params["snapshot_id"] = snapshot_id
        if owner:
            params["owner"] = owner
        if status:
            params["status"] = status
        if search:
            params["search"] = search
        if created_after:
            params["created_after"] = created_after
        if created_before:
            params["created_before"] = created_before

        response = self._http.get("/api/instances", params=params)
        return PaginatedList(
            items=[Instance.from_dict(i) for i in response["data"]],
            total=response["meta"]["total"],
            offset=response["meta"]["offset"],
            limit=response["meta"]["limit"],
        )

    def get(self, instance_id: int) -> Instance:
        """Get an instance by ID."""
        response = self._http.get(f"/api/instances/{instance_id}")
        return Instance.from_dict(response["data"])

    def create(
        self,
        snapshot_id: int,
        name: str,
        description: str | None = None,
        ttl: str | None = None,
        inactivity_timeout: str | None = None,
    ) -> Instance:
        """
        Create a new graph instance from a snapshot.

        Args:
            snapshot_id: Source snapshot ID (must be 'ready')
            name: Display name
            description: Optional description
            ttl: Time-to-live (ISO 8601 duration)
            inactivity_timeout: Inactivity timeout (ISO 8601 duration)

        Returns:
            Instance object (status will be 'starting')

        Raises:
            InvalidStateError: If snapshot is not 'ready'
            ConcurrencyLimitError: If instance limits exceeded
        """
        body = {
            "snapshot_id": snapshot_id,
            "name": name,
        }
        if description:
            body["description"] = description
        if ttl:
            body["ttl"] = ttl
        if inactivity_timeout:
            body["inactivity_timeout"] = inactivity_timeout

        response = self._http.post("/api/instances", json=body)
        return Instance.from_dict(response["data"])

    def wait_until_running(
        self,
        instance_id: int,
        timeout: int = 300,
        poll_interval: int = 5,
    ) -> Instance:
        """
        Wait for an instance to become running.

        Args:
            instance_id: Instance ID to wait for
            timeout: Maximum time to wait in seconds
            poll_interval: Time between status checks in seconds

        Returns:
            Instance object with status='running'

        Raises:
            TimeoutError: If instance doesn't start within timeout
            InstanceFailedError: If instance status becomes 'failed'
        """
        start = time.time()

        while time.time() - start < timeout:
            instance = self.get(instance_id)

            if instance.status == "running":
                return instance

            if instance.status == "failed":
                raise InstanceFailedError(
                    f"Instance {instance_id} failed: {instance.error_message}"
                )

            time.sleep(poll_interval)

        raise TimeoutError(
            f"Instance {instance_id} did not start within {timeout}s"
        )

    def terminate(self, instance_id: int) -> None:
        """
        Terminate an instance.

        Args:
            instance_id: Instance ID to terminate

        Raises:
            PermissionDeniedError: If not owner or admin
        """
        self._http.post(f"/api/instances/{instance_id}/terminate")

    def update(
        self,
        instance_id: int,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> Instance:
        """
        Update instance metadata.

        Args:
            instance_id: Instance ID
            name: New name (optional)
            description: New description (optional)

        Returns:
            Updated Instance object
        """
        body = {}
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description

        response = self._http.put(f"/api/instances/{instance_id}", json=body)
        return Instance.from_dict(response["data"])

    def get_progress(self, instance_id: int) -> InstanceProgress:
        """
        Get detailed startup progress for an instance.

        Args:
            instance_id: Instance ID

        Returns:
            InstanceProgress with phase, steps, and completion info
        """
        response = self._http.get(f"/api/instances/{instance_id}/progress")
        return InstanceProgress.from_api_response(response["data"])

    def extend_ttl(self, instance_id: int, hours: int = 24) -> Instance:
        """
        Extend instance TTL by specified hours from current expiry.

        Convenience method matching UX "Extend TTL" button behavior.
        Calculates new expiry as current_expiry + hours.

        Args:
            instance_id: Instance ID
            hours: Hours to add to current TTL (default: 24)

        Returns:
            Updated Instance object

        Raises:
            ValidationError: If extension would exceed maximum TTL (7 days from creation)

        Example:
            >>> instance = client.instances.extend_ttl(123)  # +24 hours
            >>> instance = client.instances.extend_ttl(123, hours=48)  # +48 hours
        """
        ...

    def create_and_wait(
        self,
        snapshot_id: int,
        name: str,
        *,
        description: str | None = None,
        ttl: str | None = None,
        inactivity_timeout: str | None = None,
        timeout: int = 300,
        poll_interval: int = 5,
        on_progress: Callable[[str, int, int], None] | None = None,
    ) -> Instance:
        """
        Create an instance and wait for it to become running.

        This method performs environment-aware health checks:
        - In-cluster mode (GRAPH_OLAP_IN_CLUSTER_MODE="true"): Uses Kubernetes service DNS
        - External mode: Uses ingress URL from instance.instance_url

        Both modes wait for the wrapper HTTP service to be ready (not just pod status).

        Args:
            snapshot_id: Source snapshot ID
            name: Display name
            description: Optional description
            ttl: Time-to-live (ISO 8601 duration)
            inactivity_timeout: Inactivity timeout (ISO 8601 duration)
            timeout: Maximum wait time in seconds
            poll_interval: Time between status checks
            on_progress: Optional callback(phase, completed_steps, total_steps)

        Returns:
            Instance object with status='running'

        Example:
            >>> instance = client.instances.create_and_wait(
            ...     snapshot_id=1,
            ...     name="Quick Analysis"
            ... )
            >>> conn = client.instances.connect(instance.id)
        """
        ...

    def connect(self, instance_id: int) -> "InstanceConnection":
        """
        Connect to a running instance for queries and algorithms.

        This method performs environment-aware URL construction:
        - In-cluster mode (GRAPH_OLAP_IN_CLUSTER_MODE="true"): Uses Kubernetes service DNS
        - External mode: Uses ingress URL from instance.instance_url

        Args:
            instance_id: Instance ID to connect to

        Returns:
            InstanceConnection object for graph operations

        Raises:
            InvalidStateError: If instance is not 'running'

        Example:
            >>> conn = client.instances.connect(123)
            >>> result = conn.query("MATCH (n:Customer) RETURN n LIMIT 10")
            >>> df = conn.query_df("MATCH (n)-[r]->(m) RETURN n.id, m.id")
        """
        instance = self.get(instance_id)

        if instance.status != "running":
            raise InvalidStateError(
                f"Instance {instance_id} is not running (status: {instance.status})"
            )

        return InstanceConnection(
            instance_url=instance.instance_url,
            api_key=self._config.api_key,
            instance_id=instance_id,
        )

    def create_from_mapping(
        self,
        mapping_id: int,
        name: str,
        *,
        description: str | None = None,
        mapping_version: int | None = None,
        snapshot_name: str | None = None,
        ttl: str | None = None,
        inactivity_timeout: str | None = None,
    ) -> Instance:
        """
        Create an instance directly from a mapping.

        This is a convenience method that creates both a snapshot and instance
        in a single API call. The instance is returned immediately with
        status='waiting_for_snapshot'. A background job monitors for snapshot
        completion and transitions the instance to 'starting' automatically.

        This method is ideal for workflows where you want to start an instance
        from a mapping without manually managing the snapshot lifecycle.

        Args:
            mapping_id: Source mapping ID
            name: Display name for the instance
            description: Optional description
            mapping_version: Mapping version to use (defaults to current)
            snapshot_name: Name for auto-created snapshot (defaults to instance name)
            ttl: Time-to-live (ISO 8601 duration, e.g., "PT24H")
            inactivity_timeout: Inactivity timeout (ISO 8601 duration)

        Returns:
            Instance object with status='waiting_for_snapshot'

        Raises:
            NotFoundError: If mapping doesn't exist
            ValidationError: If mapping version is invalid
            ConcurrencyLimitError: If instance limits exceeded

        Example:
            >>> instance = client.instances.create_from_mapping(
            ...     mapping_id=1,
            ...     name="Quick Analysis",
            ... )
            >>> print(f"Instance {instance.id} status: {instance.status}")
            # Instance 123 status: waiting_for_snapshot
        """
        body = {
            "mapping_id": mapping_id,
            "name": name,
        }
        if description:
            body["description"] = description
        if mapping_version is not None:
            body["mapping_version"] = mapping_version
        if snapshot_name:
            body["snapshot_name"] = snapshot_name
        if ttl:
            body["ttl"] = ttl
        if inactivity_timeout:
            body["inactivity_timeout"] = inactivity_timeout

        response = self._http.post("/api/instances/from-mapping", json=body)
        return Instance.from_dict(response["data"])

    def create_from_mapping_and_wait(
        self,
        mapping_id: int,
        name: str,
        *,
        description: str | None = None,
        mapping_version: int | None = None,
        snapshot_name: str | None = None,
        ttl: str | None = None,
        inactivity_timeout: str | None = None,
        timeout: int = 900,
        poll_interval: int = 5,
        on_progress: Callable[[str, int, int], None] | None = None,
    ) -> Instance:
        """
        Create an instance from a mapping and wait until it becomes running.

        This is a convenience method that combines create_from_mapping() with
        polling until the instance reaches 'running' status. It handles the
        full lifecycle: snapshot creation, instance creation, and startup.

        The default timeout is 900 seconds (15 minutes) to account for both
        snapshot export time and instance startup time.

        Args:
            mapping_id: Source mapping ID
            name: Display name for the instance
            description: Optional description
            mapping_version: Mapping version to use (defaults to current)
            snapshot_name: Name for auto-created snapshot (defaults to instance name)
            ttl: Time-to-live (ISO 8601 duration, e.g., "PT24H")
            inactivity_timeout: Inactivity timeout (ISO 8601 duration)
            timeout: Maximum wait time in seconds (default: 900)
            poll_interval: Time between status checks in seconds
            on_progress: Optional callback(phase, completed_steps, total_steps)

        Returns:
            Instance object with status='running'

        Raises:
            NotFoundError: If mapping doesn't exist
            ValidationError: If mapping version is invalid
            ConcurrencyLimitError: If instance limits exceeded
            TimeoutError: If instance doesn't become running within timeout
            InstanceFailedError: If instance or snapshot fails

        Example:
            >>> def show_progress(phase, completed, total):
            ...     print(f"{phase}: {completed}/{total}")
            >>> instance = client.instances.create_from_mapping_and_wait(
            ...     mapping_id=1,
            ...     name="Quick Analysis",
            ...     on_progress=show_progress,
            ... )
            >>> conn = client.instances.connect(instance.id)
            >>> result = conn.query("MATCH (n) RETURN count(n)")
        """
        instance = self.create_from_mapping(
            mapping_id=mapping_id,
            name=name,
            description=description,
            mapping_version=mapping_version,
            snapshot_name=snapshot_name,
            ttl=ttl,
            inactivity_timeout=inactivity_timeout,
        )

        start = time.time()

        while time.time() - start < timeout:
            instance = self.get(instance.id)

            if on_progress:
                # Map status to progress info
                if instance.status == "waiting_for_snapshot":
                    on_progress("waiting_for_snapshot", 0, 3)
                elif instance.status == "starting":
                    on_progress("starting", 1, 3)
                elif instance.status == "running":
                    on_progress("running", 3, 3)

            if instance.status == "running":
                return instance

            if instance.status == "failed":
                raise InstanceFailedError(
                    f"Instance {instance.id} failed: {instance.error_message}"
                )

            time.sleep(poll_interval)

        raise SDKTimeoutError(
            f"Instance {instance.id} did not become running within {timeout}s"
        )

    def update_cpu(
        self,
        instance_id: int,
        cpu_cores: int,
    ) -> Instance:
        """
        Update CPU cores for a running instance.

        Scale the instance's CPU allocation up or down. The change takes
        effect without restarting the instance.

        Args:
            instance_id: Instance ID
            cpu_cores: New CPU core count (1-8)

        Returns:
            Updated Instance object

        Raises:
            ValidationError: If cpu_cores is out of valid range
            InvalidStateError: If instance is not running
            PermissionDeniedError: If not owner or admin

        Example:
            >>> # Scale up to 4 cores for intensive analysis
            >>> instance = client.instances.update_cpu(123, cpu_cores=4)
            >>> print(f"Instance now has {instance.cpu_cores} CPU cores")
        """
        response = self._http.put(
            f"/api/instances/{instance_id}/cpu",
            json={"cpu_cores": cpu_cores},
        )
        return Instance.from_dict(response["data"])
```

### Ops Resource

```python
# resources/ops.py
from graph_olap.models.ops import (
    LifecycleConfig,
    ResourceLifecycleConfig,
    ConcurrencyConfig,
    MaintenanceMode,
    ExportConfig,
    ClusterHealth,
    ClusterInstances,
)

class OpsResource:
    """
    Operations endpoints for platform configuration and cluster status.

    Requires ops role for access. Use for:
    - Lifecycle configuration (TTL, inactivity timeouts)
    - Concurrency limits (per-analyst, cluster-wide)
    - Maintenance mode
    - Export configuration
    - Cluster health and instance monitoring

    Example:
        >>> # Check cluster health
        >>> health = client.ops.get_cluster_health()
        >>> print(f"Status: {health.status}")

        >>> # View instance distribution
        >>> instances = client.ops.get_cluster_instances()
        >>> print(f"Total: {instances.total}, Available: {instances.limits.cluster_available}")
    """

    def __init__(self, http: HTTPClient):
        self._http = http

    # Config Methods

    def get_lifecycle_config(self) -> LifecycleConfig:
        """
        Get lifecycle configuration for all resource types.

        Returns:
            LifecycleConfig with mapping, snapshot, and instance settings
        """
        response = self._http.get("/api/config/lifecycle")
        return LifecycleConfig.from_api_response(response["data"])

    def update_lifecycle_config(
        self,
        mapping: ResourceLifecycleConfig | dict | None = None,
        snapshot: ResourceLifecycleConfig | dict | None = None,
        instance: ResourceLifecycleConfig | dict | None = None,
    ) -> bool:
        """
        Update lifecycle configuration.

        Args:
            mapping: Mapping lifecycle config (default_ttl, default_inactivity, max_ttl)
            snapshot: Snapshot lifecycle config
            instance: Instance lifecycle config

        Returns:
            True if update succeeded
        """
        body = {}
        for key, val in [("mapping", mapping), ("snapshot", snapshot), ("instance", instance)]:
            if val is not None:
                if hasattr(val, "__dataclass_fields__"):
                    body[key] = {
                        "default_ttl": val.default_ttl,
                        "default_inactivity": val.default_inactivity,
                        "max_ttl": val.max_ttl,
                    }
                else:
                    body[key] = val

        self._http.put("/api/config/lifecycle", json=body)
        return True

    def get_concurrency_config(self) -> ConcurrencyConfig:
        """Get concurrency limits configuration."""
        response = self._http.get("/api/config/concurrency")
        return ConcurrencyConfig.from_api_response(response["data"])

    def update_concurrency_config(
        self,
        per_analyst: int | None = None,
        cluster_total: int | None = None,
    ) -> ConcurrencyConfig:
        """
        Update concurrency limits.

        Args:
            per_analyst: Max instances per analyst
            cluster_total: Max instances cluster-wide
        """
        body = {}
        if per_analyst is not None:
            body["per_analyst"] = per_analyst
        if cluster_total is not None:
            body["cluster_total"] = cluster_total

        response = self._http.put("/api/config/concurrency", json=body)
        return ConcurrencyConfig.from_api_response(response["data"])

    def get_maintenance_mode(self) -> MaintenanceMode:
        """Get maintenance mode status."""
        response = self._http.get("/api/config/maintenance")
        return MaintenanceMode.from_api_response(response["data"])

    def set_maintenance_mode(
        self,
        enabled: bool,
        message: str = "",
    ) -> MaintenanceMode:
        """
        Enable or disable maintenance mode.

        Args:
            enabled: True to enable, False to disable
            message: Message shown to users during maintenance
        """
        response = self._http.put(
            "/api/config/maintenance",
            json={"enabled": enabled, "message": message},
        )
        return MaintenanceMode.from_api_response(response["data"])

    def get_export_config(self) -> ExportConfig:
        """Get export configuration."""
        response = self._http.get("/api/config/export")
        return ExportConfig.from_api_response(response["data"])

    def update_export_config(self, max_duration_seconds: int) -> ExportConfig:
        """Update export configuration."""
        response = self._http.put(
            "/api/config/export",
            json={"max_duration_seconds": max_duration_seconds},
        )
        return ExportConfig.from_api_response(response["data"])

    # Cluster Methods

    def get_cluster_health(self) -> ClusterHealth:
        """
        Get cluster health status.

        Returns:
            ClusterHealth with status and component health
        """
        response = self._http.get("/api/cluster/health")
        return ClusterHealth.from_api_response(response["data"])

    def get_cluster_instances(self) -> ClusterInstances:
        """
        Get cluster-wide instance summary.

        Returns:
            ClusterInstances with counts by status, owner, and limits
        """
        response = self._http.get("/api/cluster/instances")
        return ClusterInstances.from_api_response(response["data"])

    # Background Jobs Methods (NEW in 2025-12)

    def trigger_job(
        self,
        job_name: str,
        reason: str = "manual-trigger",
    ) -> dict[str, Any]:
        """
        Manually trigger a background job for immediate execution.

        Useful for debugging, smoke tests, and incident response.

        **Rate Limiting:** 1 request per minute per job.

        Args:
            job_name: Job to trigger: "reconciliation", "lifecycle",
                     "export_reconciliation", "schema_cache"
            reason: Reason for manual trigger (audit log, 1-500 chars)

        Returns:
            Dict with job_name, status, triggered_at, triggered_by, reason

        Raises:
            RateLimitError: If job was triggered < 1 minute ago
            ValidationError: If invalid job_name
            ForbiddenError: If user doesn't have ops role

        Example:
            >>> # Trigger reconciliation for smoke test
            >>> result = client.ops.trigger_job(
            ...     job_name="reconciliation",
            ...     reason="post-deployment smoke test"
            ... )
            >>> print(f"Job {result['job_name']} status: {result['status']}")
        """
        response = self._http.post(
            "/api/ops/jobs/trigger",
            json={"job_name": job_name, "reason": reason},
        )
        return response["data"]

    def get_job_status(self) -> dict[str, Any]:
        """
        Get status of all background jobs.

        Returns health status and last execution times for all jobs.

        Returns:
            Dict with "jobs" list containing name, schedule, last_success_at,
            last_failure_at, consecutive_failures, health_status

        Raises:
            ForbiddenError: If user doesn't have ops role

        Example:
            >>> status = client.ops.get_job_status()
            >>> for job in status["jobs"]:
            ...     if job["health_status"] == "unhealthy":
            ...         print(f"WARNING: Job {job['name']} is unhealthy!")
        """
        response = self._http.get("/api/ops/jobs/status")
        return response["data"]

    def get_state(self) -> dict[str, Any]:
        """
        Get system state snapshot.

        Returns current counts of instances, snapshots, export jobs by status.
        Useful for operational dashboards and debugging.

        Returns:
            Dict with "instances", "snapshots", "export_jobs" containing
            counts by status

        Raises:
            ForbiddenError: If user doesn't have ops role

        Example:
            >>> state = client.ops.get_state()
            >>> print(f"Running instances: {state['instances']['by_status']['running']}")
            >>> print(f"Instances without pod: {state['instances']['without_pod_name']}")
        """
        response = self._http.get("/api/ops/state")
        return response["data"]

    def get_export_jobs(
        self,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Get export jobs for debugging.

        Returns export jobs with detailed status for troubleshooting worker issues.

        Args:
            status: Filter by status: "pending", "claimed", "completed", "failed"
            limit: Max records to return (max: 100)

        Returns:
            List of export job dicts with id, snapshot_id, entity_type,
            entity_name, status, attempts, timestamps, error_message

        Raises:
            ForbiddenError: If user doesn't have ops role

        Example:
            >>> # Get all failed export jobs
            >>> failed_jobs = client.ops.get_export_jobs(status="failed")
            >>> for job in failed_jobs:
            ...     print(f"Job {job['id']}: {job['error_message']}")
        """
        params = {"limit": limit}
        if status:
            params["status"] = status

        response = self._http.get("/api/ops/export-jobs", params=params)
        return response["data"]

    def get_metrics(self) -> str:
        """
        Get Prometheus metrics in text format.

        Returns raw Prometheus metrics for parsing job health and system state.
        Used by E2E tests to poll for job execution.

        Returns:
            Prometheus metrics text

        Raises:
            ForbiddenError: If user doesn't have ops role

        Example:
            >>> metrics_text = client.ops.get_metrics()
            >>> # Parse metric value
            >>> for line in metrics_text.split("\\n"):
            ...     if line.startswith("instances_by_status_total"):
            ...         print(line)
        """
        response = self._http.get("/metrics")
        return response
```

### Admin Resource

**File:** `packages/graph-olap-sdk/src/graph_olap/resources/admin.py`

```python
# resources/admin.py
from graph_olap.http import HTTPClient
from typing import Any

class AdminResource:
    """
    Admin-only privileged operations.

    Requires admin role. Use for:
    - Bulk resource deletion (test cleanup, ops maintenance)
    - Other privileged operations

    Example:
        >>> # Dry run to see what would be deleted
        >>> result = client.admin.bulk_delete(
        ...     resource_type="instance",
        ...     filters={"created_by": "e2e-test-user"},
        ...     reason="test-cleanup",
        ...     dry_run=True
        ... )
        >>> print(f"Would delete {result['matched_count']} instances")
        >>> print(f"IDs: {result['matched_ids']}")
        >>>
        >>> # Actually delete with expected_count safety check
        >>> result = client.admin.bulk_delete(
        ...     resource_type="instance",
        ...     filters={"created_by": "e2e-test-user"},
        ...     reason="test-cleanup",
        ...     expected_count=result['matched_count'],
        ...     dry_run=False
        ... )
        >>> print(f"Deleted {result['deleted_count']} instances")
    """

    def __init__(self, http: HTTPClient):
        self._http = http

    def bulk_delete(
        self,
        resource_type: str,
        filters: dict[str, Any],
        reason: str,
        expected_count: int | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """
        Bulk delete resources with safety filters.

        **Requires:** Admin role

        **Safety features:**
        - At least one filter required
        - Max 100 deletions per request
        - Expected count validation
        - Dry run mode available
        - Full audit logging

        Args:
            resource_type: Resource type: "instance", "snapshot", "mapping"
            filters: Filters to match resources (at least one required):
                - name_prefix: Match resources starting with prefix
                - created_by: Match resources created by username
                - older_than_hours: Match resources older than N hours
                - status: Match resources with specific status
            reason: Reason for deletion (audit log, 1-500 chars)
            expected_count: Expected number to delete (safety check).
                Must match actual count or operation fails.
            dry_run: If True, return what would be deleted without deleting

        Returns:
            Dict with dry_run, matched_count, matched_ids, deleted_count,
            deleted_ids, failed_ids, errors

        Raises:
            ForbiddenError: If user doesn't have Admin role
            ValidationError: If no filters, matched > 100, or count mismatch

        Example:
            >>> # Step 1: Dry run to get count
            >>> result = client.admin.bulk_delete(
            ...     resource_type="instance",
            ...     filters={
            ...         "name_prefix": "E2ETest-",
            ...         "older_than_hours": 24
            ...     },
            ...     reason="cleanup-old-test-instances",
            ...     dry_run=True
            ... )
            >>> print(f"Would delete {result['matched_count']} instances")
            >>>
            >>> # Step 2: Actually delete with expected_count
            >>> result = client.admin.bulk_delete(
            ...     resource_type="instance",
            ...     filters={
            ...         "name_prefix": "E2ETest-",
            ...         "older_than_hours": 24
            ...     },
            ...     reason="cleanup-old-test-instances",
            ...     expected_count=result['matched_count'],  # Safety check!
            ...     dry_run=False
            ... )
            >>> print(f"Deleted: {result['deleted_count']}")
            >>> print(f"Failed: {len(result['failed_ids'])}")
        """
        response = self._http.delete(
            "/api/admin/resources/bulk",
            json={
                "resource_type": resource_type,
                "filters": filters,
                "reason": reason,
                "expected_count": expected_count,
                "dry_run": dry_run,
            },
        )
        return response["data"]
```

### Health Resource

```python
# resources/health.py
from graph_olap.models.ops import HealthStatus

class HealthResource:
    """
    Health check endpoints.

    Use for monitoring and readiness checks:
    - /health - Basic liveness check
    - /ready - Full readiness check including database

    Example:
        >>> health = client.health.check()
        >>> print(f"Status: {health.status}, Version: {health.version}")

        >>> ready = client.health.ready()
        >>> print(f"Database: {ready.database}")
    """

    def __init__(self, http: HTTPClient):
        self._http = http

    def check(self) -> HealthStatus:
        """
        Basic health check (liveness probe).

        Returns:
            HealthStatus with status and version
        """
        response = self._http.get("/health")
        return HealthStatus.from_api_response(response)

    def ready(self) -> HealthStatus:
        """
        Readiness check including database connectivity.

        Returns:
            HealthStatus with status, version, and database status
        """
        response = self._http.get("/ready")
        return HealthStatus.from_api_response(response)
```

### Favorite Resource

```python
# resources/favorites.py
from graph_olap.models.common import Favorite

class FavoriteResource:
    """
    Manage user favorites/bookmarks.

    Favorites allow users to quickly access frequently used resources.

    Example:
        >>> # List all favorites
        >>> favorites = client.favorites.list()
        >>> for f in favorites:
        ...     print(f"{f.resource_type}: {f.resource_name}")

        >>> # Add a mapping to favorites
        >>> client.favorites.add("mapping", 1)

        >>> # Remove from favorites
        >>> client.favorites.remove("mapping", 1)
    """

    def __init__(self, http: HTTPClient):
        self._http = http

    def list(self, resource_type: str | None = None) -> list[Favorite]:
        """
        List current user's favorites.

        Args:
            resource_type: Filter by type (mapping, snapshot, instance)

        Returns:
            List of Favorite objects
        """
        params = {}
        if resource_type:
            params["resource_type"] = resource_type

        response = self._http.get("/api/favorites", params=params)
        return [Favorite.from_api_response(f) for f in response["data"]]

    def add(self, resource_type: str, resource_id: int) -> Favorite:
        """
        Add a resource to favorites.

        Args:
            resource_type: Resource type (mapping, snapshot, instance)
            resource_id: Resource ID

        Returns:
            Created Favorite object

        Raises:
            NotFoundError: If resource doesn't exist
            ConflictError: If already favorited
        """
        response = self._http.post(
            "/api/favorites",
            json={"resource_type": resource_type, "resource_id": resource_id},
        )
        return Favorite.from_api_response(response["data"])

    def remove(self, resource_type: str, resource_id: int) -> None:
        """
        Remove a resource from favorites.

        Args:
            resource_type: Resource type (mapping, snapshot, instance)
            resource_id: Resource ID

        Raises:
            NotFoundError: If favorite doesn't exist
        """
        self._http.delete(f"/api/favorites/{resource_type}/{resource_id}")
```

### Schema Resource

```python
# resources/schema.py
from graph_olap.models.schema import CacheStats, Catalog, Column, Schema, Table

class SchemaResource:
    """
    Browse Starburst schema metadata.

    All operations use cached metadata (refreshed every 24h).
    Performance: ~5ms per API call (HTTP overhead), ~1us for cache lookup.

    Example:
        >>> # List all catalogs
        >>> catalogs = client.schema.list_catalogs()
        >>> for cat in catalogs:
        ...     print(f"{cat.catalog_name}: {cat.schema_count} schemas")

        >>> # List schemas in a catalog
        >>> schemas = client.schema.list_schemas("analytics")
        >>> for sch in schemas:
        ...     print(f"{sch.schema_name}: {sch.table_count} tables")

        >>> # List tables in a schema
        >>> tables = client.schema.list_tables("analytics", "public")
        >>> for tbl in tables:
        ...     print(f"{tbl.table_name} ({tbl.table_type})")

        >>> # Get columns for a table
        >>> columns = client.schema.list_columns("analytics", "public", "users")
        >>> for col in columns:
        ...     print(f"{col.column_name}: {col.data_type}")

        >>> # Search for tables
        >>> results = client.schema.search_tables("customer", limit=50)
        >>> for tbl in results:
        ...     print(f"{tbl.catalog_name}.{tbl.schema_name}.{tbl.table_name}")

        >>> # Search for columns
        >>> results = client.schema.search_columns("email", limit=50)
        >>> for col in results:
        ...     print(f"{col.catalog_name}.{col.schema_name}.{col.table_name}.{col.column_name}")
    """

    def __init__(self, http: HTTPClient):
        self._http = http

    def list_catalogs(self) -> list[Catalog]:
        """
        List all cached Starburst catalogs.

        Returns:
            List of Catalog objects (sorted by name)
        """
        response = self._http.get("/api/schema/catalogs")
        return [Catalog.from_api_response(item) for item in response["data"]]

    def list_schemas(self, catalog: str) -> list[Schema]:
        """
        List all schemas in a catalog.

        Args:
            catalog: Catalog name (e.g., "analytics")

        Returns:
            List of Schema objects

        Raises:
            NotFoundError: Catalog not found in cache
        """
        response = self._http.get(f"/api/schema/catalogs/{catalog}/schemas")
        return [Schema.from_api_response(item) for item in response["data"]]

    def list_tables(self, catalog: str, schema: str) -> list[Table]:
        """
        List all tables in a schema.

        Args:
            catalog: Catalog name
            schema: Schema name

        Returns:
            List of Table objects

        Raises:
            NotFoundError: Schema not found in cache
        """
        response = self._http.get(
            f"/api/schema/catalogs/{catalog}/schemas/{schema}/tables"
        )
        return [Table.from_api_response(item) for item in response["data"]]

    def list_columns(self, catalog: str, schema: str, table: str) -> list[Column]:
        """
        Get all columns for a table.

        Args:
            catalog: Catalog name
            schema: Schema name
            table: Table name

        Returns:
            List of Column objects (sorted by ordinal_position)

        Raises:
            NotFoundError: Table not found in cache
        """
        response = self._http.get(
            f"/api/schema/catalogs/{catalog}/schemas/{schema}/tables/{table}/columns"
        )
        return [Column.from_api_response(item) for item in response["data"]]

    def search_tables(self, pattern: str, limit: int = 100) -> list[Table]:
        """
        Search tables by name pattern (prefix match, case-insensitive).

        Args:
            pattern: Search pattern (e.g., "customer" matches "customers", "customer_orders")
            limit: Maximum results (default: 100, max: 1000)

        Returns:
            List of Table objects matching pattern
        """
        response = self._http.get(
            "/api/schema/search/tables", params={"q": pattern, "limit": limit}
        )
        return [Table.from_api_response(item) for item in response["data"]]

    def search_columns(self, pattern: str, limit: int = 100) -> list[Column]:
        """
        Search columns by name pattern (prefix match, case-insensitive).

        Args:
            pattern: Search pattern (e.g., "email" matches "email", "email_address")
            limit: Maximum results (default: 100, max: 1000)

        Returns:
            List of Column objects matching pattern
        """
        response = self._http.get(
            "/api/schema/search/columns", params={"q": pattern, "limit": limit}
        )
        return [Column.from_api_response(item) for item in response["data"]]

    # Admin operations

    def admin_refresh(self) -> dict:
        """
        Trigger cache refresh (admin only).

        Starts background task to fetch latest metadata from Starburst.

        Returns:
            Dict with status message

        Raises:
            ForbiddenError: If user doesn't have admin role
        """
        response = self._http.post("/api/schema/admin/refresh")
        return response["data"]

    def get_stats(self) -> CacheStats:
        """
        Get cache statistics (admin only).

        Returns:
            CacheStats object with counts and metadata

        Raises:
            ForbiddenError: If user doesn't have admin role
        """
        response = self._http.get("/api/schema/stats")
        return CacheStats.from_api_response(response["data"])
```

---

## Progress Models

Models for tracking async operations (snapshot creation, instance startup):

```python
# models/snapshot.py
class SnapshotProgress(BaseModel):
    """Detailed progress for snapshot creation."""

    id: int
    status: str
    phase: str  # queued, exporting, uploading, importing, ready, failed
    started_at: datetime | None = None
    steps: list[dict[str, Any]] = []
    current_step: str | None = None
    progress_percent: int = 0
    estimated_remaining_seconds: int | None = None
    error_message: str | None = None

    @property
    def completed_steps(self) -> int:
        """Number of completed steps."""
        return sum(1 for s in self.steps if s.get("status") == "completed")

    @property
    def total_steps(self) -> int:
        """Total number of steps."""
        return len(self.steps)


# models/instance.py
class InstanceProgress(BaseModel):
    """Detailed progress for instance startup."""

    id: int
    status: str
    phase: str  # pod_scheduled, downloading, loading_schema, loading_data, ready, failed
    started_at: datetime | None = None
    steps: list[dict[str, Any]] = []
    current_step: str | None = None
    progress_percent: int = 0
    estimated_remaining_seconds: int | None = None
    error_message: str | None = None

    @property
    def completed_steps(self) -> int:
        """Number of completed steps."""
        return sum(1 for s in self.steps if s.get("status") == "completed")

    @property
    def total_steps(self) -> int:
        """Total number of steps."""
        return len(self.steps)


class LockStatus(BaseModel):
    """Instance lock status for algorithm execution."""

    locked: bool
    holder_id: str | None = None
    holder_name: str | None = None
    algorithm: str | None = None
    locked_at: datetime | None = None
```

---

