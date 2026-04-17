---
title: "Control Plane Services Design"
scope: hsbc
---

# Control Plane Services Design

Database access layer, service layer, export job service, and Starburst client for the Control Plane.

## Prerequisites

- [control-plane.design.md](-/control-plane.design.md) - Core Control Plane design

## Related Components

- [control-plane.mapping-generator.design.md](-/control-plane.mapping-generator.design.md) - Mapping Generator subsystem
- [export-worker.design.md](-/export-worker.design.md) - Claims and processes export jobs via internal API

---

## Database Access Layer

### Database Setup

```python
# src/control_plane/infrastructure/database.py

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_engine(database_url: str, **kwargs) -> AsyncEngine:
    """Create async SQLAlchemy engine.

    PostgreSQL is required - SQLite is not supported.
    """
    # Convert sync URL to async if needed
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://")

    return create_async_engine(
        database_url,
        pool_size=kwargs.get("pool_size", 25),
        max_overflow=kwargs.get("max_overflow", 5),
        pool_pre_ping=True,
        echo=kwargs.get("echo", False),
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create async session factory."""
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
```

### Repository Pattern

All database access uses raw SQL with explicit column lists. SQLAlchemy Core provides connection management only—no ORM.

```python
# src/control_plane/repositories/mappings.py

from datetime import datetime, timezone
import json
from typing import Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.domain import Mapping, NodeDefinition, EdgeDefinition
from ..models.errors import NotFoundError


class MappingRepository:
    """Raw SQL repository for mappings."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, mapping_id: int) -> Mapping:
        """Fetch mapping with current version."""
        query = text("""
            SELECT m.id, m.owner_username, m.name, m.description, m.current_version,
                   m.created_at, m.updated_at, m.ttl, m.inactivity_timeout,
                   mv.node_definitions, mv.edge_definitions, mv.change_description,
                   mv.created_at as version_created_at, mv.created_by
            FROM mappings m
            JOIN mapping_versions mv ON m.id = mv.mapping_id AND m.current_version = mv.version
            WHERE m.id = :id
        """)

        result = await self._session.execute(query, {"id": mapping_id})
        row = result.mappings().fetchone()

        if row is None:
            raise NotFoundError("mapping", mapping_id)

        return self._row_to_mapping(row)

    async def list(
        self,
        owner: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[Sequence[Mapping], int]:
        """List mappings with pagination."""
        # Build WHERE clause
        where_clause = "WHERE 1=1"
        params: dict = {"limit": limit, "offset": offset}

        if owner:
            where_clause += " AND m.owner_username = :owner"
            params["owner"] = owner

        # Get total count
        count_query = text(f"SELECT COUNT(*) FROM mappings m {where_clause}")
        count_result = await self._session.execute(count_query, params)
        total = count_result.scalar() or 0

        # Get page
        query = text(f"""
            SELECT m.id, m.owner_username, m.name, m.description, m.current_version,
                   m.created_at, m.updated_at, m.ttl, m.inactivity_timeout,
                   mv.node_definitions, mv.edge_definitions, mv.change_description,
                   mv.created_at as version_created_at, mv.created_by
            FROM mappings m
            JOIN mapping_versions mv ON m.id = mv.mapping_id AND m.current_version = mv.version
            {where_clause}
            ORDER BY m.updated_at DESC
            LIMIT :limit OFFSET :offset
        """)

        result = await self._session.execute(query, params)
        rows = result.mappings().fetchall()

        return [self._row_to_mapping(row) for row in rows], total

    async def create(self, mapping: Mapping) -> Mapping:
        """Create mapping with initial version."""
        now = datetime.now(timezone.utc).isoformat()

        # Insert mapping header
        insert_mapping = text("""
            INSERT INTO mappings (owner_username, name, description, current_version,
                                  created_at, updated_at, ttl, inactivity_timeout)
            VALUES (:owner_username, :name, :description, 1, :now, :now, :ttl, :inactivity_timeout)
            RETURNING id
        """)

        result = await self._session.execute(
            insert_mapping,
            {
                "owner_username": mapping.owner_username,
                "name": mapping.name,
                "description": mapping.description,
                "ttl": mapping.ttl,
                "inactivity_timeout": mapping.inactivity_timeout,
                "now": now,
            },
        )
        mapping_id = result.scalar_one()

        # Serialize definitions to JSON
        node_defs_json = json.dumps([nd.model_dump() for nd in mapping.node_definitions])
        edge_defs_json = json.dumps([ed.model_dump() for ed in mapping.edge_definitions])

        # Insert initial version
        insert_version = text("""
            INSERT INTO mapping_versions (mapping_id, version, change_description,
                                         node_definitions, edge_definitions, created_at, created_by)
            VALUES (:mapping_id, 1, NULL, :node_defs, :edge_defs, :now, :created_by)
        """)

        await self._session.execute(
            insert_version,
            {
                "mapping_id": mapping_id,
                "node_defs": node_defs_json,
                "edge_defs": edge_defs_json,
                "now": now,
                "created_by": mapping.owner_username,
            },
        )

        await self._session.commit()

        return await self.get_by_id(mapping_id)

    async def delete(self, mapping_id: int) -> None:
        """Delete mapping (versions cascade via FK)."""
        query = text("DELETE FROM mappings WHERE id = :id")
        result = await self._session.execute(query, {"id": mapping_id})

        if result.rowcount == 0:
            raise NotFoundError("mapping", mapping_id)

        await self._session.commit()

    async def count_snapshots(self, mapping_id: int) -> int:
        """Count snapshots referencing this mapping (any version)."""
        query = text("SELECT COUNT(*) FROM snapshots WHERE mapping_id = :mapping_id")
        result = await self._session.execute(query, {"mapping_id": mapping_id})
        return result.scalar() or 0

    def _row_to_mapping(self, row) -> Mapping:
        """Convert database row to domain model."""
        return Mapping(
            id=row["id"],
            owner_username=row["owner_username"],
            name=row["name"],
            description=row["description"],
            current_version=row["current_version"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            ttl=row["ttl"],
            inactivity_timeout=row["inactivity_timeout"],
            node_definitions=[
                NodeDefinition(**nd) for nd in json.loads(row["node_definitions"])
            ],
            edge_definitions=[
                EdgeDefinition(**ed) for ed in json.loads(row["edge_definitions"])
            ],
            change_description=row["change_description"],
            version_created_at=datetime.fromisoformat(row["version_created_at"]),
            version_created_by=row["created_by"],
        )
```

### Transaction Management

```python
# src/control_plane/repositories/base.py

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession


@asynccontextmanager
async def transaction(session: AsyncSession) -> AsyncIterator[AsyncSession]:
    """Context manager for explicit transaction control."""
    async with session.begin():
        yield session
        # Commits on successful exit, rolls back on exception
```

---

## Service Layer

### Mapping Service

```python
# src/control_plane/services/mappings.py

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.domain import Mapping, User, UserRole
from ..models.requests import CreateMappingRequest, UpdateMappingRequest
from ..models.errors import PermissionDeniedError, DependencyError, ValidationError
from ..repositories.mappings import MappingRepository
from ..repositories.favorites import FavoritesRepository
from ..infrastructure.starburst import StarburstClient
from .audit import AuditService, AuditCategory, AuditEvent

logger = structlog.get_logger()


class MappingService:
    """Business logic for mapping operations."""

    def __init__(
        self,
        session: AsyncSession,
        starburst_client: StarburstClient,
    ):
        self._repo = MappingRepository(session)
        self._favorites_repo = FavoritesRepository(session)
        self._starburst = starburst_client
        self._audit = AuditService(session)

    async def list(
        self,
        owner: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Mapping], int]:
        """List mappings with optional filters."""
        return await self._repo.list(owner=owner, limit=limit, offset=offset)

    async def get_by_id(self, mapping_id: int) -> Mapping:
        """Get mapping by ID."""
        return await self._repo.get_by_id(mapping_id)

    async def create(self, request: CreateMappingRequest, user: User) -> Mapping:
        """Create a new mapping."""
        # Validate SQL against Starburst
        await self._validate_definitions(request.node_definitions, request.edge_definitions)

        mapping = Mapping(
            id=0,  # Will be set by database
            owner_username=user.username,
            name=request.name,
            description=request.description,
            current_version=1,
            node_definitions=request.node_definitions,
            edge_definitions=request.edge_definitions,
            ttl=request.ttl,
            inactivity_timeout=request.inactivity_timeout,
        )

        created = await self._repo.create(mapping)

        await self._audit.log(
            category=AuditCategory.RESOURCE,
            event=AuditEvent.CREATE,
            resource_type="mapping",
            resource_id=created.id,
            user=user,
            details={"name": created.name, "version": 1},
        )

        logger.info("mapping_created", mapping_id=created.id, owner=user.username)

        return created

    async def update(
        self,
        mapping_id: int,
        request: UpdateMappingRequest,
        user: User,
    ) -> Mapping:
        """Update mapping (creates new version if definitions change)."""
        mapping = await self._repo.get_by_id(mapping_id)

        # Authorization check
        if not self._can_modify(user, mapping):
            raise PermissionDeniedError("mapping", mapping_id)

        # change_description required for version > 1
        if not request.change_description:
            raise ValidationError(
                field="change_description",
                message="Change description is required when updating mapping",
            )

        # Validate if definitions changed
        if request.node_definitions or request.edge_definitions:
            node_defs = request.node_definitions or mapping.node_definitions
            edge_defs = request.edge_definitions or mapping.edge_definitions
            await self._validate_definitions(node_defs, edge_defs)

        updated = await self._repo.create_version(mapping_id, request, user.username)

        await self._audit.log(
            category=AuditCategory.RESOURCE,
            event=AuditEvent.UPDATE,
            resource_type="mapping",
            resource_id=mapping_id,
            user=user,
            details={
                "new_version": updated.current_version,
                "change_description": request.change_description,
            },
        )

        return updated

    async def delete(self, mapping_id: int, user: User) -> None:
        """Delete mapping (fails if snapshots exist)."""
        mapping = await self._repo.get_by_id(mapping_id)

        if not self._can_modify(user, mapping):
            raise PermissionDeniedError("mapping", mapping_id)

        # Check for dependent snapshots
        snapshot_count = await self._repo.count_snapshots(mapping_id)
        if snapshot_count > 0:
            raise DependencyError(
                resource_type="mapping",
                resource_id=mapping_id,
                dependent_type="snapshot",
                dependent_count=snapshot_count,
            )

        await self._repo.delete(mapping_id)

        # CASCADE: Delete all favorites referencing this mapping
        deleted_favorites = await self._favorites_repo.remove_for_resource(
            resource_type="mapping",
            resource_id=mapping_id,
        )

        if deleted_favorites > 0:
            logger.info(
                "Cascade deleted favorites for deleted mapping",
                mapping_id=mapping_id,
                favorites_deleted=deleted_favorites,
            )

        await self._audit.log(
            category=AuditCategory.RESOURCE,
            event=AuditEvent.DELETE,
            resource_type="mapping",
            resource_id=mapping_id,
            user=user,
        )

        logger.info("mapping_deleted", mapping_id=mapping_id, deleted_by=user.username)

    async def copy(self, mapping_id: int, user: User) -> Mapping:
        """Copy mapping to the current user."""
        source = await self._repo.get_by_id(mapping_id)

        copy = Mapping(
            id=0,
            owner_username=user.username,
            name=f"Copy of {source.name}",
            description=source.description,
            current_version=1,
            node_definitions=source.node_definitions,
            edge_definitions=source.edge_definitions,
            ttl=source.ttl,
            inactivity_timeout=source.inactivity_timeout,
        )

        created = await self._repo.create(copy)

        await self._audit.log(
            category=AuditCategory.RESOURCE,
            event=AuditEvent.COPY,
            resource_type="mapping",
            resource_id=created.id,
            user=user,
            details={"source_mapping_id": mapping_id},
        )

        return created

    async def get_version_diff(
        self,
        mapping_id: int,
        from_version: int,
        to_version: int,
    ) -> MappingDiffResult:
        """Compare two versions of a mapping.

        Returns a semantic diff showing added, removed, and modified node/edge definitions.

        Algorithm:
        1. Fetch both versions from mapping_versions table
        2. Convert node_definitions/edge_definitions to dicts keyed by label/type
        3. Identify added/removed/modified definitions using set operations
        4. For modified items, use DeepDiff to compute field-level changes
        5. Return structured diff with summary counts

        Performance:
        - In-memory comparison (no database queries after initial fetch)
        - O(n) where n = number of node/edge definitions
        - Typical mapping: 5-20 nodes, 10-50 edges → sub-millisecond computation

        Error Handling:
        - 404 if mapping or version not found
        - 400 if from_version == to_version
        """
        if from_version == to_version:
            raise ValueError("Cannot diff a version with itself")

        v1 = await self._repo.get_version(mapping_id, from_version)
        v2 = await self._repo.get_version(mapping_id, to_version)

        from control_plane.utils.diff import diff_mapping_versions
        return diff_mapping_versions(v1, v2)

    async def _validate_definitions(
        self,
        node_definitions: list,
        edge_definitions: list,
    ) -> None:
        """Validate SQL queries against Starburst."""
        for node_def in node_definitions:
            await self._starburst.validate_query(node_def.sql_query)

        for edge_def in edge_definitions:
            await self._starburst.validate_query(edge_def.sql_query)

    def _can_modify(self, user: User, mapping: Mapping) -> bool:
        """Check if user can modify mapping."""
        if user.role in (UserRole.ADMIN, UserRole.OPS):
            return True
        return user.username == mapping.owner_username
```

### Mapping Version Diff

**Purpose:** Provides semantic comparison of mapping versions for change tracking, debugging, and auditing schema evolution.

**API Endpoint:** `GET /api/mappings/:id/versions/:v1/diff/:v2`

**Spec Reference:** `docs/system-design/api/api.mappings.spec.md:413-498`

#### Algorithm

The diff algorithm compares two mapping versions and produces a semantic diff showing added, removed, and modified definitions:

1. **Fetch Versions:** Retrieve both versions from `mapping_versions` table via repository
2. **Index by Key:** Convert `node_definitions` to dict keyed by `label`, `edge_definitions` to dict keyed by `type`
3. **Set Operations:** Identify changes using set operations on keys:
   - **Added:** Keys in `to_version` but not in `from_version`
   - **Removed:** Keys in `from_version` but not in `to_version`
   - **Modified:** Keys in both versions where content differs
4. **Field-Level Analysis:** For modified items, use DeepDiff library to identify which fields changed
5. **Summary Counts:** Aggregate counts for nodes and edges (added/removed/modified)
6. **Return Structure:** Convert to response models with summary and detailed changes

#### Implementation Details

**Core Diff Logic:** `src/control_plane/utils/diff.py`

```python
from deepdiff import DeepDiff
from dataclasses import dataclass

@dataclass
class MappingDiffResult:
    mapping_id: int
    from_version: int
    to_version: int
    nodes_added: int
    nodes_removed: int
    nodes_modified: int
    edges_added: int
    edges_removed: int
    edges_modified: int
    node_diffs: list[NodeDiff]
    edge_diffs: list[EdgeDiff]

def diff_mapping_versions(
    from_version: MappingVersion,
    to_version: MappingVersion
) -> MappingDiffResult:
    """Compare two mapping versions using semantic analysis."""
    # Index definitions by key
    from_nodes = {n.label: n for n in from_version.node_definitions}
    to_nodes = {n.label: n for n in to_version.node_definitions}

    # Set operations
    added_labels = set(to_nodes.keys()) - set(from_nodes.keys())
    removed_labels = set(from_nodes.keys()) - set(to_nodes.keys())
    common_labels = set(from_nodes.keys()) & set(to_nodes.keys())

    # Identify modified nodes using DeepDiff
    node_diffs = []
    for label in added_labels:
        node_diffs.append(NodeDiff(
            label=label,
            change_type="added",
            fields_changed=None,
            from_def=None,
            to_def=to_dict(to_nodes[label]),
        ))

    for label in common_labels:
        diff = DeepDiff(from_nodes[label], to_nodes[label], ignore_order=False)
        if diff:
            changed_fields = extract_field_names(diff)
            node_diffs.append(NodeDiff(
                label=label,
                change_type="modified",
                fields_changed=changed_fields,
                from_def=to_dict(from_nodes[label]),
                to_def=to_dict(to_nodes[label]),
            ))

    # Similar logic for edges...
    return MappingDiffResult(...)
```

**Service Method:** `src/control_plane/services/mapping_service.py:447-480`

```python
async def get_version_diff(
    self,
    mapping_id: int,
    from_version: int,
    to_version: int,
) -> MappingDiffResult:
    """Compare two versions of a mapping."""
    if from_version == to_version:
        raise ValueError("Cannot diff a version with itself")

    v1 = await self._repo.get_version(mapping_id, from_version)
    v2 = await self._repo.get_version(mapping_id, to_version)

    from control_plane.utils.diff import diff_mapping_versions
    return diff_mapping_versions(v1, v2)
```

#### Performance Characteristics

| Aspect | Specification |
|--------|--------------|
| **Computation** | In-memory comparison (no database queries after initial fetch) |
| **Complexity** | O(n + m) where n = nodes, m = edges |
| **Typical Load** | 5-20 nodes, 10-50 edges |
| **Latency** | Sub-millisecond for diff computation |
| **Database Calls** | 2 queries (one per version fetch) |
| **Memory** | Proportional to definition sizes (~KB per version) |

**Optimization Notes:**
- No caching required (computation is already fast)
- DeepDiff is optimized for structured data comparison
- Field-level granularity avoids large object serialization in response

#### Error Handling

| Error Code | Condition | HTTP Status |
|-----------|-----------|-------------|
| `NotFoundError` | Mapping doesn't exist | 404 |
| `NotFoundError` | Version doesn't exist | 404 |
| `ValueError` | from_version == to_version | 400 |

**Error Response Example:**
```json
{
  "error": {
    "code": "MAPPING_VERSION_NOT_FOUND",
    "message": "Version 5 not found for mapping",
    "details": {
      "mapping_id": 123,
      "version": 5,
      "latest_version": 3
    }
  }
}
```

#### Response Structure

**Summary Counts:**
```json
{
  "summary": {
    "nodes_added": 1,
    "nodes_removed": 0,
    "nodes_modified": 1,
    "edges_added": 0,
    "edges_removed": 0,
    "edges_modified": 1
  }
}
```

**Detailed Changes:**
```json
{
  "changes": {
    "nodes": [
      {
        "label": "Customer",
        "change_type": "modified",
        "fields_changed": ["sql", "properties"],
        "from": { /* old definition */ },
        "to": { /* new definition */ }
      }
    ],
    "edges": [
      {
        "type": "PURCHASED",
        "change_type": "modified",
        "fields_changed": ["properties"],
        "from": { /* old definition */ },
        "to": { /* new definition */ }
      }
    ]
  }
}
```

#### Change Types

- **`added`**: Definition exists in `to_version` but not in `from_version`
  - `from` is `null`, `to` contains full definition
  - `fields_changed` is `null`

- **`removed`**: Definition exists in `from_version` but not in `to_version`
  - `from` contains full definition, `to` is `null`
  - `fields_changed` is `null`

- **`modified`**: Definition exists in both versions but content differs
  - Both `from` and `to` contain partial or full definitions
  - `fields_changed` lists which top-level fields changed (e.g., `["sql", "properties"]`)

#### Field-Level Granularity

The diff identifies changes at the field level:

- `"sql"` - SQL query changed
- `"properties"` - Property array changed (addition, removal, or modification)
- `"primary_key"` - Primary key definition changed
- `"from_node"` / `"to_node"` - Edge node references changed (edges only)
- `"from_key"` / `"to_key"` - Edge key columns changed (edges only)

**Note:** Property array changes are reported as single `"properties"` field change. The `from`/`to` objects contain the full arrays for comparison.

#### Testing

**Unit Tests:** `tests/unit/test_diff.py` (9 tests)
- Empty diff (identical versions)
- Single node/edge added
- Single node/edge removed
- Single node/edge modified (SQL, properties)
- Complex scenario (multiple simultaneous changes)

**Integration Tests:** `tests/integration/test_api_mappings.py:583-874` (8 tests)
- API success cases (node added, removed, modified, edge modified, no changes)
- API error cases (404 for missing mapping/version, 400 for same version)

**Coverage:** >90% for diff logic, 100% for API endpoint

#### SDK Integration

The Python SDK provides a convenient `diff()` method:

```python
from graph_olap import GraphOLAPClient

client = GraphOLAPClient()
mapping = client.mappings.get(123)

# Get diff
diff = mapping.diff(from_version=1, to_version=2)

# Access summary
print(f"Added {diff.summary['nodes_added']} nodes")
print(f"Modified {diff.summary['nodes_modified']} nodes")

# Filter changes
for node in diff.nodes_added():
    print(f"  + {node.label}")

for node in diff.nodes_modified():
    print(f"  ~ {node.label}: {node.fields_changed}")
```

**Jupyter Notebook Rendering:**
```python
from graph_olap.utils.diff import render_diff_summary, render_diff_details

# Summary table
render_diff_summary(diff)

# Detailed side-by-side comparison
render_diff_details(diff, show_from_to=True)
```

#### Use Cases

1. **Schema Evolution Tracking**: Understand how mappings changed between versions
2. **Debugging**: Identify unexpected changes after mapping updates
3. **Audit Trail**: Review historical changes for compliance
4. **Documentation**: Generate change logs for mapping releases
5. **Merge Conflicts**: Identify conflicting changes (future: 3-way diff)

#### Dependencies

**Python Libraries:**
- `deepdiff>=8.6.1` - Structured data comparison

**Internal:**
- `control_plane.utils.diff` - Core diff algorithm
- `graph_olap_schemas.api_resources` - Response models with ChangeType enum
- `MappingRepository.get_version()` - Version retrieval

#### Future Enhancements (Not Implemented)

- **3-Way Diff:** Compare with common ancestor for merge conflict detection
- **Diff Caching:** Cache frequently accessed diffs (likely unnecessary given fast computation)
- **Property-Level Diff:** Show individual property changes instead of full array
- **Visual Diff UI:** Web-based side-by-side comparison view
- **Diff Export:** Export diffs as Markdown, PDF, or structured formats

### Instance Service with Kubernetes Integration

```python
# src/control_plane/services/instances.py

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.domain import Instance, InstanceStatus, User, UserRole
from ..models.requests import CreateInstanceRequest
from ..models.errors import (
    PermissionDeniedError,
    InvalidStateError,
    ConcurrencyLimitError,
)
from ..repositories.instances import InstanceRepository
from ..repositories.favorites import FavoritesRepository
from ..repositories.snapshots import SnapshotRepository
from ..repositories.config import ConfigRepository
from ..infrastructure.kubernetes import KubernetesClient, PodSpec
from .audit import AuditService, AuditCategory, AuditEvent

logger = structlog.get_logger()


class InstanceService:
    """Business logic for instance operations."""

    def __init__(
        self,
        session: AsyncSession,
        k8s_client: KubernetesClient,
    ):
        self._repo = InstanceRepository(session)
        self._snapshot_repo = SnapshotRepository(session)
        self._config_repo = ConfigRepository(session)
        self._favorites_repo = FavoritesRepository(session)
        self._k8s = k8s_client
        self._audit = AuditService(session)

    async def create(self, request: CreateInstanceRequest, user: User) -> Instance:
        """Create a new instance."""
        # Validate snapshot exists and is ready
        snapshot = await self._snapshot_repo.get_by_id(request.snapshot_id)

        if snapshot.status != "ready":
            raise InvalidStateError(
                resource="snapshot",
                resource_id=request.snapshot_id,
                current=snapshot.status,
                required="ready",
            )

        # Check concurrency limits
        await self._check_concurrency_limits(user.username)

        # Create instance record
        instance = Instance(
            id=0,
            snapshot_id=request.snapshot_id,
            owner_username=user.username,
            name=request.name,
            description=request.description,
            status=InstanceStatus.STARTING,
            ttl=request.ttl,
            inactivity_timeout=request.inactivity_timeout,
        )

        created = await self._repo.create(instance)

        # Create Kubernetes pod
        try:
            pod_spec = self._build_pod_spec(created, snapshot)
            await self._k8s.create_pod(pod_spec)
        except Exception as e:
            # Mark instance as failed if pod creation fails
            await self._repo.update_status(
                created.id,
                InstanceStatus.FAILED,
                f"Failed to create pod: {e}",
            )
            raise

        # Update snapshot last_used_at
        await self._snapshot_repo.update_last_used(request.snapshot_id)

        await self._audit.log(
            category=AuditCategory.SYSTEM,
            event=AuditEvent.INSTANCE_STARTUP,
            resource_type="instance",
            resource_id=created.id,
            user=user,
            details={"snapshot_id": request.snapshot_id, "name": request.name},
        )

        logger.info("instance_created", instance_id=created.id, owner=user.username)

        return created

    async def delete_instance(self, instance_id: int, user: User) -> None:
        """Delete instance and all associated Kubernetes resources (permission-checked).

        Permission check: User must be owner OR admin
        No state restrictions: Instances can be deleted in any state

        This is the canonical delete method used by:
        - User DELETE API endpoint
        - Bulk delete operations
        - Lifecycle background job (TTL/inactivity enforcement)

        Deletion order:
        1. Delete K8s resources FIRST (pod, service, ingress) - stops wrapper immediately
        2. Delete from database LAST - prevents 404 errors during shutdown

        This ensures that when DELETE returns 204, the resource is GONE,
        not "eventually gone" via reconciliation job.

        Args:
            instance_id: Instance to delete
            user: User performing deletion

        Raises:
            NotFoundError: If instance doesn't exist
            PermissionDeniedError: If user is not owner or admin

        Example:
            # User DELETE API endpoint
            await instance_service.delete_instance(instance_id=42, user=current_user)

            # Bulk delete (admin only - permission checked inside)
            await instance_service.delete_instance(instance_id=42, user=admin_user)

            # Lifecycle job (system user is admin)
            await instance_service.delete_instance(instance_id=42, user=system_user)

        See Also:
            - [ADR-43](--/--/process/adr/testing/adr-043-google-style-test-runner-cleanup-for-e2e-tests.md)
        """
        # Get existing instance
        instance = await self.get_instance(instance_id)

        # Permission check: owner OR admin
        if not user.is_admin:
            check_ownership(user, instance.owner_username, "Instance", instance_id)

        logger.info(
            "instance_deletion_started",
            instance_id=instance_id,
            pod_name=instance.pod_name,
            url_slug=instance.url_slug,
            status=instance.status.value,
            deleted_by=user.username,
        )

        # Delete K8s resources FIRST (pod, service, ingress)
        await self._cleanup_k8s_resources(instance)

        # Delete from database LAST
        deleted = await self._repo.delete(instance_id)
        if deleted:
            logger.info(
                "instance_deleted",
                instance_id=instance_id,
                owner=instance.owner_username,
                deleted_by=user.username,
            )
        else:
            logger.warning("instance_already_deleted", instance_id=instance_id)

        # CASCADE: Delete all favorites referencing this instance
        deleted_favorites = await self._favorites_repo.remove_for_resource(
            resource_type="instance",
            resource_id=instance_id,
        )

        if deleted_favorites > 0:
            logger.info(
                "Cascade deleted favorites for deleted instance",
                instance_id=instance_id,
                favorites_deleted=deleted_favorites,
            )

    async def _cleanup_k8s_resources(self, instance: Instance) -> None:
        """Delete ALL K8s resources for an instance (pod, service, ingress).

        Internal method - idempotent, safe to call even if resources don't exist.

        Args:
            instance: Instance whose K8s resources should be deleted
        """
        if self._k8s is None or not instance.url_slug:
            return

        try:
            deleted = await self._k8s.delete_wrapper_pod(instance.url_slug)
            if deleted:
                logger.info(
                    "k8s_resources_deleted",
                    instance_id=instance.id,
                    url_slug=instance.url_slug,
                )
            else:
                logger.warning(
                    "k8s_resources_not_found",
                    instance_id=instance.id,
                    url_slug=instance.url_slug,
                )
        except Exception as e:
            # Log error but don't fail - deletion is best-effort
            # If K8s resources are already gone, that's acceptable
            logger.warning(
                "k8s_cleanup_error",
                instance_id=instance.id,
                url_slug=instance.url_slug,
                error=str(e),
            )

    async def _check_concurrency_limits(self, username: str) -> None:
        """Check per-analyst and cluster-wide limits."""
        # Per-analyst limit
        user_count = await self._repo.count_active_by_owner(username)
        per_analyst_limit = await self._config_repo.get_int("concurrency.per_analyst")

        if user_count >= per_analyst_limit:
            raise ConcurrencyLimitError(
                limit_type="per_analyst",
                current_count=user_count,
                max_allowed=per_analyst_limit,
            )

        # Cluster-wide limit
        total_count = await self._repo.count_active()
        cluster_limit = await self._config_repo.get_int("concurrency.cluster_total")

        if total_count >= cluster_limit:
            raise ConcurrencyLimitError(
                limit_type="cluster",
                current_count=total_count,
                max_allowed=cluster_limit,
            )

    def _build_pod_spec(self, instance: Instance, snapshot) -> PodSpec:
        """Build Kubernetes pod specification."""
        return PodSpec(
            name=f"graph-instance-{instance.id}",
            labels={
                "app": "graph-instance",
                "instance-id": str(instance.id),
            },
            env={
                "INSTANCE_ID": str(instance.id),
                "SNAPSHOT_ID": str(snapshot.id),
                "GCS_PATH": snapshot.gcs_path,  # gs://bucket/{owner}/{mapping_id}/v{version}/{snapshot_id}/
                "BUFFER_POOL_SIZE": "2147483648",
            },
            resources={
                "requests": {"memory": "512Mi", "cpu": "250m"},
                "limits": {"memory": "4Gi", "cpu": "2000m"},
            },
            pvc_size="10Gi",
        )

    def _can_modify(self, user: User, instance: Instance) -> bool:
        """Check if user can modify instance."""
        if user.role in (UserRole.ADMIN, UserRole.OPS):
            return True
        return user.username == instance.owner_username
```

### Snapshot Service

The Snapshot Service manages snapshot lifecycle, including GCS cleanup and cascade deletion of favorites.

```python
# src/control_plane/services/snapshots.py

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.domain import Snapshot, User
from ..models.errors import PermissionDeniedError, DependencyError
from ..repositories.snapshots import SnapshotRepository
from ..repositories.favorites import FavoritesRepository
from ..infrastructure.gcs import GCSClient

logger = structlog.get_logger()


class SnapshotService:
    """Business logic for snapshot operations."""

    def __init__(
        self,
        session: AsyncSession,
        gcs_client: GCSClient | None = None,
    ):
        self._repo = SnapshotRepository(session)
        self._favorites_repo = FavoritesRepository(session)
        self._gcs = gcs_client

    async def delete_snapshot(self, snapshot_id: int, user: User) -> None:
        """Delete snapshot with GCS cleanup and cascade delete of favorites.

        Deletion order:
        1. Check permissions
        2. Check for dependent instances
        3. Delete GCS data (best-effort, logged if fails)
        4. Delete snapshot from database
        5. CASCADE delete all favorites referencing this snapshot

        Args:
            snapshot_id: Snapshot to delete
            user: User performing deletion

        Raises:
            NotFoundError: If snapshot doesn't exist
            PermissionDeniedError: If user is not owner or admin
            DependencyError: If active instances exist
        """
        snapshot = await self._repo.get_by_id(snapshot_id)

        # Permission check
        if not self._can_modify(user, snapshot):
            raise PermissionDeniedError("snapshot", snapshot_id)

        # Check for dependent instances
        instance_count = await self._repo.count_instances(snapshot_id)
        if instance_count > 0:
            raise DependencyError(
                resource_type="snapshot",
                resource_id=snapshot_id,
                dependent_type="instance",
                dependent_count=instance_count,
            )

        # Delete GCS data (best-effort)
        if self._gcs and snapshot.gcs_path:
            try:
                await self._gcs.delete_prefix(snapshot.gcs_path)
            except Exception as e:
                logger.warning(
                    "gcs_cleanup_failed",
                    snapshot_id=snapshot_id,
                    gcs_path=snapshot.gcs_path,
                    error=str(e),
                )

        # Delete snapshot (export jobs cascade)
        await self._repo.delete(snapshot_id)

        # CASCADE: Delete all favorites referencing this snapshot
        deleted_favorites = await self._favorites_repo.remove_for_resource(
            resource_type="snapshot",
            resource_id=snapshot_id,
        )

        if deleted_favorites > 0:
            logger.info(
                "Cascade deleted favorites for deleted snapshot",
                snapshot_id=snapshot_id,
                favorites_deleted=deleted_favorites,
            )

    def _can_modify(self, user: User, snapshot: Snapshot) -> bool:
        """Check if user can modify snapshot."""
        if user.is_admin:
            return True
        return user.username == snapshot.owner_username
```

---

## WrapperFactory Service

The WrapperFactory Service centralizes wrapper-specific configuration for dynamic K8s pod creation. See [ADR-049](--/process/adr/system-design/adr-049-multi-wrapper-pluggable-architecture.md) for architecture design.

### Purpose

- Map `WrapperType` enum → `WrapperConfig` dataclass
- Centralize wrapper-specific configuration (images, resources, env vars)
- Query wrapper capabilities from registry
- Provide single source of truth for wrapper deployment configuration

### WrapperConfig Dataclass

```python
# src/control_plane/services/wrapper_factory.py

from dataclasses import dataclass
from graph_olap_schemas import WrapperType


@dataclass
class WrapperConfig:
    """Configuration for a specific wrapper type."""

    wrapper_type: WrapperType
    image_name: str
    image_tag: str
    container_port: int
    health_check_path: str
    resource_limits: dict[str, str]  # {"memory": "8Gi", "cpu": "4"}
    resource_requests: dict[str, str]  # {"memory": "4Gi", "cpu": "2"}
    environment_variables: dict[str, str]  # {"WRAPPER_TYPE": "ryugraph", ...}
```

### WrapperFactory Implementation

```python
class WrapperFactory:
    """Factory for wrapper-specific configuration."""

    def __init__(
        self,
        ryugraph_image: str = "ryugraph-wrapper",
        ryugraph_tag: str = "latest",
        falkordb_image: str = "falkordb-wrapper",
        falkordb_tag: str = "latest",
    ):
        self._ryugraph_image = ryugraph_image
        self._ryugraph_tag = ryugraph_tag
        self._falkordb_image = falkordb_image
        self._falkordb_tag = falkordb_tag

    def get_wrapper_config(self, wrapper_type: WrapperType) -> WrapperConfig:
        """Get configuration for specified wrapper type."""
        if wrapper_type == WrapperType.RYUGRAPH:
            return WrapperConfig(
                wrapper_type=WrapperType.RYUGRAPH,
                image_name=self._ryugraph_image,
                image_tag=self._ryugraph_tag,
                container_port=8000,
                health_check_path="/health",
                resource_limits={"memory": "8Gi", "cpu": "4"},
                resource_requests={"memory": "4Gi", "cpu": "2"},
                environment_variables={
                    "WRAPPER_TYPE": "ryugraph",
                    "BUFFER_POOL_SIZE": "2147483648",  # 2GB
                },
            )
        elif wrapper_type == WrapperType.FALKORDB:
            return WrapperConfig(
                wrapper_type=WrapperType.FALKORDB,
                image_name=self._falkordb_image,
                image_tag=self._falkordb_tag,
                container_port=8000,
                health_check_path="/health",
                resource_limits={"memory": "12Gi", "cpu": "4"},  # In-memory only
                resource_requests={"memory": "6Gi", "cpu": "2"},
                environment_variables={
                    "WRAPPER_TYPE": "falkordb",
                    "PYTHON_VERSION": "3.12",
                },
            )
        else:
            raise ValueError(f"Unsupported wrapper type: {wrapper_type}")

    def get_capabilities(self, wrapper_type: WrapperType) -> WrapperCapabilities:
        """Get capabilities for specified wrapper type."""
        from graph_olap_schemas import get_wrapper_capabilities

        return get_wrapper_capabilities(wrapper_type)
```

### Usage in K8s Service

```python
# src/control_plane/services/k8s_service.py

class K8sService:
    def __init__(self, settings: Settings):
        self._wrapper_factory = WrapperFactory(
            ryugraph_image=settings.ryugraph_image,
            ryugraph_tag=settings.ryugraph_tag,
            falkordb_image=settings.falkordb_image,
            falkordb_tag=settings.falkordb_tag,
        )

    async def create_wrapper_pod(
        self,
        instance_id: int,
        url_slug: str,
        wrapper_type: WrapperType,  # Dynamic wrapper selection
        snapshot_id: int,
        gcs_snapshot_path: str,
    ) -> tuple[str, str]:
        """Create wrapper pod with wrapper-specific configuration."""
        # Get wrapper-specific config from factory
        wrapper_config = self._wrapper_factory.get_wrapper_config(wrapper_type)

        pod_spec = self._build_wrapper_pod_spec(
            instance_id=instance_id,
            url_slug=url_slug,
            wrapper_config=wrapper_config,  # Pass config, not wrapper_type
            snapshot_id=snapshot_id,
            gcs_snapshot_path=gcs_snapshot_path,
        )

        # Create pod with dynamic configuration
        await self._k8s_client.create_namespaced_pod(
            namespace=self._namespace,
            body=pod_spec,
        )

        return pod_name, instance_url

    def _build_wrapper_pod_spec(
        self,
        instance_id: int,
        url_slug: str,
        wrapper_config: WrapperConfig,  # Use config object
        snapshot_id: int,
        gcs_snapshot_path: str,
    ) -> dict[str, Any]:
        """Build pod spec using wrapper configuration."""
        pod_name = f"wrapper-{instance_id}"
        service_name = f"wrapper-svc-{instance_id}"

        return {
            "metadata": {
                "name": pod_name,
                "labels": {
                    "app": f"{wrapper_config.wrapper_type.value}-wrapper",
                    "wrapper-type": wrapper_config.wrapper_type.value,
                    "instance-id": str(instance_id),
                },
            },
            "spec": {
                "containers": [
                    {
                        "name": "wrapper",
                        "image": f"{wrapper_config.image_name}:{wrapper_config.image_tag}",
                        "ports": [{"containerPort": wrapper_config.container_port}],
                        "resources": {
                            "requests": wrapper_config.resource_requests,
                            "limits": wrapper_config.resource_limits,
                        },
                        "env": [
                            {"name": "INSTANCE_ID", "value": str(instance_id)},
                            {"name": "SNAPSHOT_ID", "value": str(snapshot_id)},
                            {"name": "GCS_SNAPSHOT_PATH", "value": gcs_snapshot_path},
                        ]
                        + [
                            {"name": k, "value": v}
                            for k, v in wrapper_config.environment_variables.items()
                        ],
                        "startupProbe": {
                            "httpGet": {
                                "path": wrapper_config.health_check_path,
                                "port": wrapper_config.container_port,
                            },
                            "periodSeconds": 5,
                            "failureThreshold": 30,
                        },
                    }
                ],
            },
        }
```

### Resource Allocation Strategy

See [ADR-051](--/process/adr/infrastructure/adr-051-wrapper-resource-allocation-strategy.md) for resource allocation rationale.

| Wrapper | Memory Request | Memory Limit | Rationale |
|---------|----------------|--------------|-----------|
| **Ryugraph** | 4Gi | 8Gi | Buffer pool + disk-based caching (soft limit) |
| **FalkorDB** | 6Gi | 12Gi | In-memory only (hard limit, no disk overflow) |

**Why FalkorDB needs more memory:**
- No disk-based buffer pool (all data in RAM)
- Hard OOM limit (vs Ryugraph's graceful degradation)
- Subprocess overhead (FalkorDB subprocess + FastAPI process)

### Cloud-Optimized Resources (ADR-068)

For cloud deployments, wrapper resources were reduced by 75% based on actual usage profiling.

**Reference:** [ADR-068: Wrapper Resource Optimization](--/process/adr/infrastructure/adr-068-wrapper-resource-optimization.md)

| Metric | Original | Optimized | Reduction |
|--------|----------|-----------|-----------|
| Memory Request | 1Gi | 512Mi | 50% |
| Memory Limit | 2Gi | 1Gi | 50% |
| CPU Request | 250m | 100m | 60% |
| CPU Limit | 1000m | 500m | 50% |

Observed usage was 10-25% of original allocations. The optimized configuration:
- Increases wrapper density (4x more per node)
- Reduces costs ~75%
- Validated by full E2E test suite (40 tests passing)

### Adding New Wrapper Types

To support a new wrapper type (e.g., Neo4j):

1. **Add enum value:** `WrapperType.NEO4J = "neo4j"` in `graph-olap-schemas`
2. **Add capabilities:** Entry in `WRAPPER_CAPABILITIES` registry
3. **Add factory case:** New `elif` block in `get_wrapper_config()`
4. **Create wrapper package:** `packages/neo4j-wrapper/`
5. **Create Helm chart:** `charts/neo4j-wrapper/`

**No changes required to K8s service** - it uses WrapperFactory abstraction.

---

## Export Job Service

The Export Job Service handles atomic job claiming and status updates for the stateless export workers. See [ADR-25](--/process/adr/system-design/adr-025-export-worker-architecture-simplification.md) for architecture details.

```python
# src/control_plane/services/export_jobs.py

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.domain import ExportJob


class ExportJobService:
    """Service for export job claiming and management."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def claim_jobs(
        self,
        worker_id: str,
        limit: int = 10,
    ) -> list[ExportJob]:
        """
        Atomically claim pending export jobs for a worker.

        Uses SELECT ... FOR UPDATE SKIP LOCKED to prevent race conditions
        between multiple workers claiming the same jobs.

        Returns:
            List of claimed jobs with their SQL and metadata.
        """
        now = datetime.now(timezone.utc).isoformat()

        # Atomic claim using FOR UPDATE SKIP LOCKED
        query = text("""
            WITH claimed AS (
                SELECT id FROM export_jobs
                WHERE status = 'pending'
                ORDER BY created_at
                LIMIT :limit
                FOR UPDATE SKIP LOCKED
            )
            UPDATE export_jobs
            SET status = 'claimed',
                claimed_by = :worker_id,
                claimed_at = :now,
                updated_at = :now
            WHERE id IN (SELECT id FROM claimed)
            RETURNING id, snapshot_id, job_type, entity_name, sql,
                      column_names, starburst_catalog, gcs_path
        """)

        result = await self._session.execute(
            query,
            {"worker_id": worker_id, "limit": limit, "now": now}
        )
        await self._session.commit()

        return [self._row_to_export_job(row) for row in result.mappings()]

    async def get_pollable_jobs(self, limit: int = 10) -> list[ExportJob]:
        """
        Get submitted jobs that are ready to poll.

        Returns jobs where:
        - status = 'submitted'
        - next_poll_at <= now

        Locking Strategy:
        Uses FOR UPDATE SKIP LOCKED to prevent multiple workers from polling
        the same job concurrently. While poll updates are technically idempotent,
        locking avoids redundant Starburst API calls and simplifies debugging.
        Jobs that are already being polled by another worker are skipped.
        """
        now = datetime.now(timezone.utc).isoformat()

        query = text("""
            SELECT id, snapshot_id, job_type, entity_name, status,
                   starburst_query_id, next_uri, next_poll_at, poll_count,
                   gcs_path
            FROM export_jobs
            WHERE status = 'submitted'
              AND next_poll_at <= :now
            ORDER BY next_poll_at
            LIMIT :limit
            FOR UPDATE SKIP LOCKED
        """)

        result = await self._session.execute(query, {"now": now, "limit": limit})
        return [self._row_to_export_job(row) for row in result.mappings()]

    async def update_submitted(
        self,
        job_id: int,
        starburst_query_id: str,
        next_uri: str,
        next_poll_at: datetime,
    ) -> None:
        """Update job to submitted status with Starburst tracking info."""
        query = text("""
            UPDATE export_jobs
            SET status = 'submitted',
                starburst_query_id = :query_id,
                next_uri = :next_uri,
                next_poll_at = :next_poll_at,
                submitted_at = :now,
                updated_at = :now
            WHERE id = :id
        """)
        await self._session.execute(query, {
            "id": job_id,
            "query_id": starburst_query_id,
            "next_uri": next_uri,
            "next_poll_at": next_poll_at.isoformat(),
            "now": datetime.now(timezone.utc).isoformat(),
        })
        await self._session.commit()

    async def complete_job(
        self,
        job_id: int,
        row_count: int,
        size_bytes: int | None = None,
    ) -> None:
        """Mark job as completed with results."""
        now = datetime.now(timezone.utc).isoformat()
        query = text("""
            UPDATE export_jobs
            SET status = 'completed',
                row_count = :row_count,
                size_bytes = :size_bytes,
                completed_at = :now,
                updated_at = :now
            WHERE id = :id
        """)
        await self._session.execute(query, {
            "id": job_id,
            "row_count": row_count,
            "size_bytes": size_bytes,
            "now": now,
        })
        await self._session.commit()
```

---

## Starburst Client

The Control Plane uses a Starburst client for SQL validation during mapping creation/update. This validates queries before they're used for snapshot exports.

### Multi-Distribution Support (ADR-067)

The Starburst client supports both Starburst Galaxy (production) and vanilla Trino (development) through conditional authentication.

**Reference:** [ADR-067: Trino Compatibility Layer](--/process/adr/system-design/adr-067-trino-compatibility-layer.md)

| Environment | Authentication | Detection |
|-------------|----------------|-----------|
| Starburst Galaxy | Enterprise auth enabled | `password != "unused"` |
| Vanilla Trino | Auth disabled | `password == "unused"` |

```python
def _should_authenticate(self) -> bool:
    """Skip authentication for vanilla Trino (local dev)."""
    return self.password != "unused"
```

This enables:
- **Production:** Starburst Galaxy with enterprise authentication
- **Development:** Lightweight Trino without credential management

### Implementation

```python
# src/control_plane/infrastructure/starburst.py

from typing import Any

import httpx
import structlog

from ..models.errors import ValidationError

logger = structlog.get_logger()


class StarburstClient:
    """Client for Starburst SQL validation and schema introspection."""

    def __init__(self, base_url: str, catalog: str, timeout: float = 30.0):
        self._base_url = base_url
        self._catalog = catalog
        self._timeout = timeout
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            headers={"X-Trino-Catalog": catalog},
        )

    async def validate_query(self, sql: str) -> None:
        """
        Validate SQL query syntax and schema references.

        Runs EXPLAIN on the query to check:
        - SQL syntax is valid
        - Referenced tables/columns exist
        - User has permission to query

        Raises ValidationError if query is invalid.
        """
        explain_sql = f"EXPLAIN {sql}"

        try:
            response = await self._client.post(
                "/v1/statement",
                content=explain_sql,
                headers={"X-Trino-Schema": "default"},
            )
            response.raise_for_status()

            # Poll for completion (Trino async model)
            result = response.json()
            while result.get("nextUri"):
                response = await self._client.get(result["nextUri"])
                result = response.json()

            if error := result.get("error"):
                raise ValidationError(
                    field="sql",
                    message=f"SQL validation failed: {error.get('message', 'Unknown error')}",
                )

        except httpx.HTTPStatusError as e:
            logger.error("starburst_validation_failed", sql=sql[:100], error=str(e))
            raise ValidationError(
                field="sql",
                message=f"Failed to validate SQL: {e.response.status_code}",
            )

    async def get_query_columns(self, sql: str) -> list[dict[str, Any]]:
        """
        Execute query with LIMIT 0 to get column metadata.

        Returns list of column definitions: [{"name": str, "type": str}, ...]
        """
        limited_sql = f"SELECT * FROM ({sql}) AS q LIMIT 0"

        response = await self._client.post(
            "/v1/statement",
            content=limited_sql,
        )
        response.raise_for_status()

        result = response.json()
        while result.get("nextUri"):
            response = await self._client.get(result["nextUri"])
            result = response.json()

        columns = result.get("columns", [])
        return [{"name": col["name"], "type": col["type"]} for col in columns]

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()
```

**Usage in lifespan:**

```python
# In app.py lifespan
app.state.starburst_client = StarburstClient(
    base_url=settings.starburst_url,
    catalog=settings.starburst_catalog,
)
```

---

