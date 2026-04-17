---
title: "Jupyter SDK Algorithms Design"
scope: hsbc
---

# Jupyter SDK Algorithms Design

Algorithm execution for the Jupyter SDK, including native Ryugraph algorithms and NetworkX integration.

## Prerequisites

- [jupyter-sdk.design.md](-/jupyter-sdk.design.md) - Core SDK design
- [jupyter-sdk.connection.design.md](-/jupyter-sdk.connection.design.md) - Instance connection

## Related Documents

- [jupyter-sdk.algorithms.native.design.md](-/jupyter-sdk.algorithms.native.design.md) - Native Ryugraph algorithms
- [jupyter-sdk.algorithms.networkx.design.md](-/jupyter-sdk.algorithms.networkx.design.md) - NetworkX algorithms
- [ryugraph-wrapper.design.md](-/ryugraph-wrapper.design.md) - Server-side algorithm execution
- [reference/ryugraph-networkx.reference.md](--/reference/ryugraph-networkx.reference.md) - NetworkX integration reference

---

> **Wrapper Capabilities:** Algorithm availability differs by wrapper type.
>
> - **Ryugraph**: Native algorithms + NetworkX (100+ algorithms)
> - **FalkorDB**: Native Cypher procedures only (NO NetworkX)
>
> See [falkordb-wrapper.design.md](-/falkordb-wrapper.design.md) for FalkorDB algorithm details.

---

## Shared Algorithm Schemas

Algorithm types are defined in the shared `graph-olap-schemas` package to ensure consistency between SDK and wrapper:

```python
from graph_olap_schemas import (
    AlgorithmType,        # native, networkx
    ExecutionStatus,      # pending, running, completed, failed, cancelled
    AlgorithmCategory,    # centrality, community, pathfinding, etc.
    AlgorithmExecutionResponse,
    AlgorithmInfoResponse,
    AlgorithmListResponse,
)
```

See [graph-olap-schemas](--/--/graph-olap-schemas/) for the authoritative schema definitions. See [ADR-24](--/process/adr/system-design/adr-024-shared-algorithm-schemas-in-graph-olap-schemas.md) for the decision rationale.

---

## Algorithm Managers Overview

The SDK provides two algorithm managers accessible via `InstanceConnection`:

| Manager | Access | Purpose |
|---------|--------|---------|
| `conn.algo` | `AlgorithmManager` | Native Ryugraph algorithms (PageRank, WCC, Louvain, etc.) |
| `conn.networkx` | `NetworkXManager` | NetworkX algorithms (100+ via dynamic introspection) |

Both managers support:
- **Dynamic discovery** - `algorithms()` lists available algorithms
- **Introspection** - `algorithm_info()` returns parameter documentation
- **Generic execution** - `run()` executes any algorithm by name
- **Convenience methods** - Typed methods for common algorithms

### Native Algorithms (conn.algo)

Native algorithms run directly in Ryugraph's C++ engine for maximum performance.

```python
# Discovery
>>> conn.algo.algorithms()
>>> conn.algo.algorithm_info("pagerank")

# Generic execution
>>> conn.algo.run("pagerank", node_label="Customer", property_name="pr_score")

# Convenience methods
>>> conn.algo.pagerank("Customer", "pr_score", damping=0.85)
>>> conn.algo.wcc("Account", "component_id")
>>> conn.algo.louvain("Customer", "community_id")
```

See [jupyter-sdk.algorithms.native.design.md](-/jupyter-sdk.algorithms.native.design.md) for full details.

### NetworkX Algorithms (conn.networkx)

NetworkX algorithms are discovered dynamically - no SDK updates needed when new algorithms are added.

```python
# Discovery
>>> conn.networkx.algorithms(category="centrality")
>>> conn.networkx.algorithm_info("betweenness_centrality")

# Generic execution
>>> conn.networkx.run("betweenness_centrality", node_label="Customer", property_name="bc")

# Convenience methods
>>> conn.networkx.closeness_centrality("Customer", "cc")
>>> conn.networkx.eigenvector_centrality("Customer", "ec")
```

See [jupyter-sdk.algorithms.networkx.design.md](-/jupyter-sdk.algorithms.networkx.design.md) for full details.

---

## Additional Exception Types

Add these to `exceptions.py`:

```python
# Additional exceptions

class SnapshotNotReadyError(ConflictError):
    """Cannot use a snapshot that is not ready."""
    pass


class StarburstError(GraphOLAPError):
    """Error from Starburst during export."""
    def __init__(self, message: str, details: dict = None):
        super().__init__(message)
        self.details = details or {}


class GCSError(GraphOLAPError):
    """Error accessing Google Cloud Storage."""
    def __init__(self, message: str, details: dict = None):
        super().__init__(message)
        self.details = details or {}


class ExecutionNotFoundError(NotFoundError):
    """Algorithm execution not found."""
    pass
```

---

## Quick Start Helper

Add to `client.py`:

```python
# Quick start convenience method in client.py

    def quick_start(
        self,
        mapping_id: int,
        snapshot_name: str | None = None,
        instance_name: str | None = None,
        snapshot_timeout: int = 600,
        instance_timeout: int = 300,
    ) -> "InstanceConnection":
        """
        Convenience method to go from mapping to running instance in one call.

        Creates a snapshot from the mapping, waits for it to be ready,
        creates an instance, waits for it to start, and returns a connection.

        Args:
            mapping_id: Source mapping ID
            snapshot_name: Name for snapshot (default: auto-generated)
            instance_name: Name for instance (default: auto-generated)
            snapshot_timeout: Max seconds to wait for snapshot
            instance_timeout: Max seconds to wait for instance

        Returns:
            InstanceConnection ready for queries

        Example:
            >>> conn = client.quick_start(mapping_id=1)
            >>> df = conn.query_df("MATCH (n) RETURN n LIMIT 10")
        """
        from datetime import datetime

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

        # Create and wait for snapshot
        snapshot = self.snapshots.create_and_wait(
            mapping_id=mapping_id,
            name=snapshot_name or f"QuickStart_{timestamp}",
            timeout=snapshot_timeout,
        )

        # Create and wait for instance
        instance = self.instances.create_and_wait(
            snapshot_id=snapshot.id,
            name=instance_name or f"QuickStart_{timestamp}",
            timeout=instance_timeout,
        )

        # Return connection
        return self.instances.connect(instance.id)
```

---

## Pagination Iterator

Add to `pagination.py`:

```python
# pagination.py
from dataclasses import dataclass
from typing import Generic, TypeVar, Iterator, Callable

T = TypeVar("T")

@dataclass
class PaginatedList(Generic[T]):
    """Paginated list of items with metadata."""
    items: list[T]
    total: int
    offset: int
    limit: int

    def __iter__(self) -> Iterator[T]:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.items) < self.total


class PaginatedIterator(Generic[T]):
    """Iterator that automatically fetches all pages."""

    def __init__(
        self,
        fetch_page: Callable[[int, int], PaginatedList[T]],
        limit: int = 100,
    ):
        self._fetch_page = fetch_page
        self._limit = limit
        self._offset = 0
        self._exhausted = False
        self._current_page: list[T] = []
        self._page_index = 0

    def __iter__(self) -> Iterator[T]:
        return self

    def __next__(self) -> T:
        # Fetch next page if needed
        if self._page_index >= len(self._current_page):
            if self._exhausted:
                raise StopIteration

            page = self._fetch_page(self._offset, self._limit)
            self._current_page = page.items
            self._page_index = 0
            self._offset += len(page.items)

            if not page.has_more:
                self._exhausted = True

            if not self._current_page:
                raise StopIteration

        item = self._current_page[self._page_index]
        self._page_index += 1
        return item


# Add to each resource class:
def iter_all(self, **filters) -> PaginatedIterator[T]:
    """
    Iterate through all matching resources, automatically handling pagination.

    Example:
        >>> for mapping in client.mappings.iter_all(owner="alice"):
        ...     process(mapping)
    """
    def fetch_page(offset: int, limit: int) -> PaginatedList[T]:
        return self.list(**filters, offset=offset, limit=limit)

    return PaginatedIterator(fetch_page)
```

---

## Packaging and Deployment

For packaging configuration, Docker images, JupyterHub deployment, and IPython magic commands, see:

**[jupyter-sdk.deployment.design.md](-/jupyter-sdk.deployment.design.md)**

---

## Open Questions

See [decision.log.md](--/process/decision.log.md) for:

- OQ-001: Authentication mechanism (OAuth, API keys, JWT)
- OQ-002: Jupyter connectivity (Ingress, service mesh)
