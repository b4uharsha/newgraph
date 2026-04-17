---
title: "MappingResource"
---

<div class="nb-header">
  <span class="nb-header__type">Reference</span>
  <h1 class="nb-header__title">MappingResource</h1>
  <p class="nb-header__subtitle">Graph mapping management</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">15 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--intermediate">
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
      </span>
      Intermediate
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">Reference</span><span class="nb-header__tag">API</span></div>
</div>

## MappingResource

Accessed via `client.mappings`, this resource manages graph mapping definitions --
the SQL-to-graph blueprints that tell the platform how to transform relational
data into nodes and edges.

Each mapping can have multiple immutable **versions** (for auditing and rollback)
and can be used to create snapshots and instances.

<div class="nb-section">
  <span class="nb-section__number">1</span>
  <div>
    <h2 class="nb-section__title">Setup</h2>
    <p class="nb-section__description">Connect to the platform</p>
  </div>
</div>

```python
# Cell 1 — Parameters
USERNAME = "_FILL_ME_IN_"  # Set your email before running
```

```python
# Cell 2 — Connect
from graph_olap import GraphOLAPClient
client = GraphOLAPClient(username=USERNAME)
```

```python
# Cell 3 — Provision
from notebook_setup import provision
personas, _ = provision(USERNAME)
analyst = personas["analyst"]
admin = personas["admin"]
ops = personas["ops"]
client = analyst
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Creating Mappings</h2>
    <p class="nb-section__description">Define SQL-to-graph blueprints</p>
  </div>
</div>

### `create(name, description=None, node_definitions=None, edge_definitions=None) -> Mapping`

Create a new mapping with node and edge definitions that describe how SQL
results map to graph elements.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | *required* | Mapping name |
| `description` | `str \| None` | `None` | Optional description |
| `node_definitions` | `list[NodeDefinition] \| list[dict]` | `None` | Node type definitions |
| `edge_definitions` | `list[EdgeDefinition] \| list[dict]` | `None` | Edge type definitions |

**Returns:** `Mapping` object.

**Raises:** `ValidationError` if definitions are invalid.

Use `NodeDefinition` and `EdgeDefinition` model classes to build type-safe
definitions. Each node needs a `label`, a `sql` query, a `primary_key`, and
optional `properties`. Each edge needs a `type`, `from_node`/`to_node` labels,
a `sql` query, and `from_key`/`to_key` join columns.

```python
from graph_olap.models import NodeDefinition, EdgeDefinition
from graph_olap.models.mapping import PropertyDefinition

# Build node definitions
customer_node = NodeDefinition(
    label="Customer",
    sql="SELECT cust_id, cust_name, segment FROM demo.customers",
    primary_key={"name": "cust_id", "type": "STRING"},
    properties=[
        PropertyDefinition(name="cust_name", type="STRING"),
        PropertyDefinition(name="segment", type="STRING"),
    ],
)

account_node = NodeDefinition(
    label="Account",
    sql="SELECT acct_id, acct_type, balance FROM demo.accounts",
    primary_key={"name": "acct_id", "type": "STRING"},
    properties=[
        PropertyDefinition(name="acct_type", type="STRING"),
        PropertyDefinition(name="balance", type="DOUBLE"),
    ],
)

# Build edge definition
holds_edge = EdgeDefinition(
    type="HOLDS",
    from_node="Customer",
    to_node="Account",
    sql="SELECT cust_id, acct_id, opened_date FROM demo.cust_accounts",
    from_key="cust_id",
    to_key="acct_id",
    properties=[
        PropertyDefinition(name="opened_date", type="DATE"),
    ],
)

# Create the mapping
mapping = client.mappings.create(
    name="ref-mapping",
    description="Reference notebook: customer-account graph",
    node_definitions=[customer_node, account_node],
    edge_definitions=[holds_edge],
)

print(f"ID:      {mapping.id}")
print(f"Name:    {mapping.name}")
print(f"Version: v{mapping.current_version}")
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Listing Mappings</h2>
    <p class="nb-section__description">Search and filter existing mappings</p>
  </div>
</div>

### `list(*, owner, search, created_after, created_before, sort_by, sort_order, offset, limit) -> PaginatedList[Mapping]`

List mappings with optional filters. Returns a `PaginatedList` that supports
iteration and provides `.total` for the full count.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `owner` | `str \| None` | `None` | Filter by owner username |
| `search` | `str \| None` | `None` | Free-text search on name/description |
| `created_after` | `str \| None` | `None` | Filter by created_at >= timestamp (ISO 8601) |
| `created_before` | `str \| None` | `None` | Filter by created_at <= timestamp (ISO 8601) |
| `sort_by` | `str` | `"created_at"` | Sort field (`name`, `created_at`, `current_version`) |
| `sort_order` | `str` | `"desc"` | Sort direction (`asc`, `desc`) |
| `offset` | `int` | `0` | Pagination offset |
| `limit` | `int` | `50` | Max results per page (max 100) |

```python
all_mappings = client.mappings.list(limit=5)

print(f"Total mappings: {all_mappings.total}\n")
for m in all_mappings:
    print(f"  [{m.id}] {m.name} (v{m.current_version})")
```

```python
# Filter by search term and sort
filtered = client.mappings.list(
    search="ref-mapping",
    sort_by="name",
    sort_order="asc",
    limit=10,
)

print(f"Found {filtered.total} mapping(s) matching 'ref-mapping'")
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Getting a Mapping</h2>
    <p class="nb-section__description">Retrieve a single mapping by ID</p>
  </div>
</div>

### `get(mapping_id) -> Mapping`

Retrieve a single mapping by ID. The returned object includes embedded
version details (node/edge definitions) for the current version.

| Parameter | Type | Description |
|-----------|------|-------------|
| `mapping_id` | `int` | Mapping ID |

**Returns:** `Mapping` object with version details.

**Raises:** `NotFoundError` if the mapping does not exist.

```python
detail = client.mappings.get(mapping.id)

print(f"Name:        {detail.name}")
print(f"Owner:       {detail.owner_username}")
print(f"Version:     v{detail.current_version}")
print(f"Description: {detail.description}")
print(f"Created:     {detail.created_at}")
print(f"Nodes:       {len(detail.node_definitions)}")
print(f"Edge types:  {len(detail.edge_definitions)}")
```

<div class="nb-section">
  <span class="nb-section__number">5</span>
  <div>
    <h2 class="nb-section__title">Updating Mappings</h2>
    <p class="nb-section__description">Modify mappings and create new versions</p>
  </div>
</div>

### `update(mapping_id, change_description, *, name=None, description=None, node_definitions=None, edge_definitions=None) -> Mapping`

Update a mapping, creating a new immutable version. The `change_description`
is required and records why the change was made.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `mapping_id` | `int` | *required* | Mapping ID |
| `change_description` | `str` | *required* | Description of what changed |
| `name` | `str \| None` | `None` | New name |
| `description` | `str \| None` | `None` | New description |
| `node_definitions` | `list[NodeDefinition] \| list[dict]` | `None` | Replacement node definitions |
| `edge_definitions` | `list[EdgeDefinition] \| list[dict]` | `None` | Replacement edge definitions |

**Returns:** Updated `Mapping` object with the new version.

**Raises:** `NotFoundError` if the mapping does not exist. `ValidationError` if definitions are invalid.

```python
# Add a property to the Customer node and create a new version
updated_customer = NodeDefinition(
    label="Customer",
    sql="SELECT cust_id, cust_name, segment, region FROM demo.customers",
    primary_key={"name": "cust_id", "type": "STRING"},
    properties=[
        PropertyDefinition(name="cust_name", type="STRING"),
        PropertyDefinition(name="segment", type="STRING"),
        PropertyDefinition(name="region", type="STRING"),
    ],
)

updated = client.mappings.update(
    mapping.id,
    change_description="Added region property to Customer node",
    node_definitions=[updated_customer, account_node],
    edge_definitions=[holds_edge],
)

print(f"Version: v{updated.current_version}")
print(f"Name:    {updated.name}")
```

```python
# Update just the description (no new version of definitions)
renamed = client.mappings.update(
    mapping.id,
    change_description="Clarified description",
    description="Reference notebook: customer-account graph with regions",
)

print(f"Description: {renamed.description}")
```

<div class="nb-section">
  <span class="nb-section__number">6</span>
  <div>
    <h2 class="nb-section__title">Versioning</h2>
    <p class="nb-section__description">Browse and compare immutable versions</p>
  </div>
</div>

### `list_versions(mapping_id) -> list[MappingVersion]`

List all versions of a mapping (newest first).

### `get_version(mapping_id, version) -> MappingVersion`

Retrieve a specific version with full node and edge definitions.

```python
versions = client.mappings.list_versions(mapping.id)

print(f"Total versions: {len(versions)}\n")
for v in versions:
    print(f"  v{v.version}: {v.change_description} (created {v.created_at})")
```

```python
# Get full details of version 1
v1 = client.mappings.get_version(mapping.id, version=1)

print(f"Version {v1.version} node definitions:")
for node in v1.node_definitions:
    props = ", ".join(p.name for p in node.properties)
    print(f"  {node.label}: [{props}]")
```

### `diff(mapping_id, from_version, to_version) -> MappingDiff`

Compare two versions of a mapping. Returns a `MappingDiff` with a summary
and detailed changes for nodes and edges. The object has rich HTML display
in Jupyter.

| Parameter | Type | Description |
|-----------|------|-------------|
| `mapping_id` | `int` | Mapping ID |
| `from_version` | `int` | Starting version number |
| `to_version` | `int` | Ending version number |

**Returns:** `MappingDiff` object with `.summary`, `.nodes_added()`, `.nodes_removed()`, `.nodes_modified()`, `.edges_added()`, `.edges_removed()`, `.edges_modified()` methods.

**Raises:** `NotFoundError` if mapping or version does not exist. `ValidationError` if from_version == to_version.

```python
diff = client.mappings.diff(mapping.id, from_version=1, to_version=2)

print(f"Diff v{diff.from_version} -> v{diff.to_version}:")
print(f"  Nodes added:    {diff.summary['nodes_added']}")
print(f"  Nodes removed:  {diff.summary['nodes_removed']}")
print(f"  Nodes modified: {diff.summary['nodes_modified']}")
print(f"  Edges added:    {diff.summary['edges_added']}")
print(f"  Edges removed:  {diff.summary['edges_removed']}")
print(f"  Edges modified: {diff.summary['edges_modified']}")

for node in diff.nodes_modified():
    print(f"\n  Modified node: {node.label}")
    print(f"    Changed fields: {node.fields_changed}")
```

<div class="nb-section">
  <span class="nb-section__number">7</span>
  <div>
    <h2 class="nb-section__title">Related Resources</h2>
    <p class="nb-section__description">Snapshots, instances, and resource trees</p>
  </div>
</div>

### `list_snapshots(mapping_id, *, offset=0, limit=50) -> PaginatedList[Snapshot]`

List snapshots across all versions of a mapping.

### `list_instances(mapping_id, *, offset=0, limit=50) -> PaginatedList[Instance]`

List instances created from any snapshot of this mapping.

```python
from graph_olap.exceptions import NotFoundError

try:
    snapshots = client.mappings.list_snapshots(mapping.id)
    print(f"Snapshots: {snapshots.total}")
    for s in snapshots:
        print(f"  [{s.id}] {s.status} (v{s.mapping_version})")
except NotFoundError:
    print("No snapshots yet (snapshots are created when an instance is provisioned)")
```

### `get_tree(mapping_id, *, include_instances=True, status=None) -> dict`

Get the full resource hierarchy for a mapping: versions -> snapshots -> instances.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `mapping_id` | `int` | *required* | Mapping ID |
| `include_instances` | `bool` | `True` | Include instance details |
| `status` | `str \| None` | `None` | Filter snapshots by status |

**Returns:** Dict keyed by version number, each containing snapshot and instance details.

```python
try:
    tree = client.mappings.get_tree(mapping.id)
    print(f"Mapping tree: {tree.get('name', 'N/A')}")
    for version in tree.get("versions", []):
        print(f"  v{version.get('version', '?')}: {len(version.get('snapshots', []))} snapshot(s)")
except NotFoundError:
    print("Tree not available for this mapping")
```

<div class="nb-section">
  <span class="nb-section__number">8</span>
  <div>
    <h2 class="nb-section__title">Lifecycle</h2>
    <p class="nb-section__description">Manage mapping TTL and inactivity timeout</p>
  </div>
</div>

### `set_lifecycle(mapping_id, *, ttl=None, inactivity_timeout=None) -> Mapping`

Set lifecycle parameters for a mapping. Values use ISO 8601 duration format
(e.g. `"PT2H"` for 2 hours, `"P7D"` for 7 days).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `mapping_id` | `int` | *required* | Mapping ID |
| `ttl` | `str \| None` | `None` | Time-to-live (ISO 8601 duration) or None to clear |
| `inactivity_timeout` | `str \| None` | `None` | Inactivity timeout (ISO 8601 duration) or None to clear |

**Returns:** Updated `Mapping` object.

```python
lifecycle = client.mappings.set_lifecycle(
    mapping.id,
    ttl="P30D",
    inactivity_timeout="PT6H",
)

print(f"TTL:                {lifecycle.ttl}")
print(f"Inactivity timeout: {lifecycle.inactivity_timeout}")
```

<div class="nb-section">
  <span class="nb-section__number">9</span>
  <div>
    <h2 class="nb-section__title">Copying &amp; Deleting</h2>
    <p class="nb-section__description">Duplicate and remove mappings</p>
  </div>
</div>

### `copy(mapping_id, new_name) -> Mapping`

Copy a mapping to a new mapping with the same definitions. Version history
is not copied (the new mapping starts at v1).

**Primary collaboration primitive.** The platform has no "share" feature, no ACLs,
and no ownership transfer. `copy()` is the intended way to build on a teammate's
mapping: the new mapping is owned by the caller and has no upstream link to the
source. Call `copy()` again if you need to pick up changes from the original.

| Parameter | Type | Description |
|-----------|------|-------------|
| `mapping_id` | `int` | Source mapping ID (any mapping on the platform) |
| `new_name` | `str` | Name for the new mapping |

**Returns:** New `Mapping` object owned by the caller.

**Raises:** `NotFoundError` if the source mapping does not exist.

**See also:** [Sharing Mappings tutorial](../../tutorials/05-advanced/07_sharing_mappings/),
[SDK Manual — Working With Other Users' Mappings](/sdk-manual/02-core-concepts-manual/#working-with-other-users-mappings).

```python
copied = client.mappings.copy(mapping.id, new_name="ref-mapping-copy")

print(f"Original: [{mapping.id}] {mapping.name} (v{mapping.current_version})")
print(f"Copy:     [{copied.id}] {copied.name} (v{copied.current_version})")

# Clean up the copy
client.mappings.delete(copied.id)
print("\nCopy deleted.")
```

### `delete(mapping_id) -> None`

Delete a mapping. This action is irreversible.

| Parameter | Type | Description |
|-----------|------|-------------|
| `mapping_id` | `int` | Mapping ID |

**Raises:** `NotFoundError` if the mapping does not exist. `DependencyError` if the mapping has snapshots.

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li>Use <code>NodeDefinition</code> and <code>EdgeDefinition</code> to build type-safe mapping definitions from SQL queries</li>
    <li>Every <code>update()</code> creates a new immutable version -- use <code>change_description</code> to document why</li>
    <li><code>diff()</code> provides a semantic comparison between any two versions, with rich Jupyter display</li>
    <li><code>get_tree()</code> shows the full resource hierarchy: versions -> snapshots -> instances</li>
    <li><code>copy()</code> duplicates a mapping without its version history -- useful for experimentation</li>
    <li>Use <code>ctx.create_mapping()</code> in notebooks to ensure automatic cleanup on <code>ctx.teardown()</code></li>
  </ul>
</div>
