---
title: "Mapping Authoring"
---

<div class="nb-header">
  <span class="nb-header__type">Tutorial</span>
  <h1 class="nb-header__title">Mapping Authoring</h1>
  <p class="nb-header__subtitle">Design graph schemas from SQL tables and manage mapping versions</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">35 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--advanced">
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
      </span>
      Advanced
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">Mappings</span><span class="nb-header__tag">SQL</span><span class="nb-header__tag">Schema</span><span class="nb-header__tag">Versioning</span><span class="nb-header__tag">NodeDefinition</span></div>
</div>

<div class="nb-objectives">
  <h3 class="nb-objectives__title">What You'll Learn</h3>
  <ul class="nb-objectives__list">
    <li><strong>Catalog Browsing</strong> - Discover tables and columns in Starburst catalogs</li>
    <li><strong>Node Definitions</strong> - Design nodes with primary keys and typed properties</li>
    <li><strong>Edge Definitions</strong> - Define relationships between node types</li>
    <li><strong>Mapping Lifecycle</strong> - Create, update, version, diff, copy, and delete mappings</li>
  </ul>
</div>

<div class="nb-section">
  <span class="nb-section__number">1</span>
  <div>
    <h2 class="nb-section__title">Setup</h2>
    <p class="nb-section__description">Connect to the platform and provision tutorial resources</p>
  </div>
</div>

```python
# Cell 1 — Parameters
USERNAME = "_FILL_ME_IN_"  # Set your email before running
```

```python
# Cell 2 — Connect and provision
from graph_olap import GraphOLAPClient
client = GraphOLAPClient(username=USERNAME)

from notebook_setup import provision, make_namespace
personas, conn = provision(USERNAME)
analyst = personas["analyst"]

namespace = make_namespace(USERNAME)
print(f"Connected | namespace: {namespace}")
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Browsing the Catalog</h2>
    <p class="nb-section__description">Discover catalogs, schemas, tables, and columns in Starburst</p>
  </div>
</div>

```python
# Ensure schema cache is populated before browsing
# The cache is refreshed every 24h; admin_refresh() forces an immediate update
import time

admin = personas["admin"]
admin.schema.admin_refresh()
print("Schema cache refresh triggered, waiting for data...")

for _ in range(24):
    time.sleep(5)
    catalogs = analyst.schema.list_catalogs()
    if catalogs:
        break
    print("  waiting...")

print(f"\nCatalogs ({len(catalogs)}):")
for cat in catalogs:
    print(f"  {cat.catalog_name}")
```

```python
# List schemas in the first catalog
catalog_name = catalogs[0].catalog_name if catalogs else "bigquery"
schemas = analyst.schema.list_schemas(catalog_name)
print(f"Schemas in '{catalog_name}' ({len(schemas)}):")
for s in schemas:
    print(f"  {s.schema_name}")
```

```python
# List tables — find the graph_olap_e2e schema
schema_name = next(
    (s.schema_name for s in schemas if "graph_olap" in s.schema_name),
    schemas[0].schema_name if schemas else "graph_olap_e2e",
)
tables = analyst.schema.list_tables(catalog_name, schema_name)
print(f"Tables in '{catalog_name}.{schema_name}' ({len(tables)}):")
for t in tables:
    print(f"  {t.table_name}")
```

```python
# List columns in the account table
cust_table = next(
    (t.table_name for t in tables if "acct" in t.table_name.lower()),
    tables[0].table_name if tables else "bis_acct_dh",
)
columns = analyst.schema.list_columns(catalog_name, schema_name, cust_table)
print(f"Columns in '{cust_table}' ({len(columns)}):")
for col in columns:
    print(f"  {col.column_name:20s}  {col.data_type}")
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Designing Node Definitions</h2>
    <p class="nb-section__description">Create a Customer node with typed properties</p>
  </div>
</div>

```python
from graph_olap.models.mapping import NodeDefinition, EdgeDefinition, PropertyDefinition
from graph_olap_schemas import RyugraphType

# RyugraphType defines the supported property types
print("Supported property types:")
for rt in RyugraphType:
    print(f"  {rt.value}")

# Define a Customer node from the bis_acct_dh table
customer_node = NodeDefinition(
    label="Customer",
    sql=(
        "SELECT DISTINCT CAST(psdo_cust_id AS VARCHAR) AS id, "
        "MIN(bk_sectr) AS bk_sectr, COUNT(DISTINCT psdo_acno) AS account_count, "
        "MIN(acct_stus) AS acct_stus FROM bigquery.graph_olap_e2e.bis_acct_dh WHERE 1=1 GROUP BY psdo_cust_id"
    ),
    primary_key={"name": "id", "type": "STRING"},
    properties=[
        PropertyDefinition(name="bk_sectr", type="STRING"),
        PropertyDefinition(name="account_count", type="INT64"),
        PropertyDefinition(name="acct_stus", type="STRING"),
    ],
)

print(f"\nNode label:   {customer_node.label}")
print(f"Primary key:  {customer_node.primary_key}")
print(f"Properties:   {[p.name for p in customer_node.properties]}")
print(f"SQL preview:  {customer_node.sql[:60]}...")
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Designing Edge Definitions</h2>
    <p class="nb-section__description">Define a SHARES_ACCOUNT relationship between customers</p>
  </div>
</div>

```python
from graph_olap.models.mapping import EdgeDefinition

# Define a SHARES_ACCOUNT edge via the account table
shares_account_edge = EdgeDefinition(
    type="SHARES_ACCOUNT",
    from_node="Customer",
    to_node="Customer",
    sql=(
        "SELECT DISTINCT "
        "CAST(a.psdo_cust_id AS VARCHAR) AS from_id, "
        "CAST(b.psdo_cust_id AS VARCHAR) AS to_id "
        "FROM bigquery.graph_olap_e2e.bis_acct_dh a "
        "JOIN bigquery.graph_olap_e2e.bis_acct_dh b "
        "ON a.psdo_acno = b.psdo_acno "
        "AND a.psdo_cust_id < b.psdo_cust_id"
    ),
    from_key="from_id",
    to_key="to_id",
)

print(f"Edge type:  {shares_account_edge.type}")
print(f"From node:  {shares_account_edge.from_node}")
print(f"To node:    {shares_account_edge.to_node}")
print(f"From key:   {shares_account_edge.from_key}")
print(f"To key:     {shares_account_edge.to_key}")
print(f"SQL preview: {shares_account_edge.sql[:60]}...")
```

<div class="nb-section">
  <span class="nb-section__number">5</span>
  <div>
    <h2 class="nb-section__title">Creating a Mapping</h2>
    <p class="nb-section__description">Combine node and edge definitions into a mapping</p>
  </div>
</div>

```python
# Create a mapping with a unique namespaced name
mapping_name = f"tutorial-authoring-{namespace}"

mapping = analyst.mappings.create(
    name=mapping_name,
    node_definitions=[customer_node],
    edge_definitions=[shares_account_edge],
    description="Tutorial mapping: Customer graph with shared accounts",
)

print(f"Created mapping: {mapping.name}")
print(f"  ID:          {mapping.id}")
print(f"  Version:     {mapping.current_version}")
print(f"  Nodes:       {[n.label for n in mapping.node_definitions]}")
print(f"  Edges:       {[e.type for e in mapping.edge_definitions]}")
```

<div class="nb-section">
  <span class="nb-section__number">6</span>
  <div>
    <h2 class="nb-section__title">Evolving with Versions</h2>
    <p class="nb-section__description">Update the mapping and track version history</p>
  </div>
</div>

```python
# Add a new Account node to the mapping (version 2)
account_node = NodeDefinition(
    label="Account",
    sql=(
        "SELECT DISTINCT CAST(psdo_acno AS VARCHAR) AS id"
        " FROM bigquery.graph_olap_e2e.bis_acct_dh WHERE 1=1"
    ),
    primary_key={"name": "id", "type": "STRING"},
    properties=[],
)

owns_account_edge = EdgeDefinition(
    type="OWNS_ACCOUNT",
    from_node="Customer",
    to_node="Account",
    sql=(
        "SELECT DISTINCT "
        "CAST(psdo_cust_id AS VARCHAR) AS from_id, "
        "CAST(psdo_acno AS VARCHAR) AS to_id"
        " FROM bigquery.graph_olap_e2e.bis_acct_dh WHERE 1=1"
    ),
    from_key="from_id",
    to_key="to_id",
)

updated = analyst.mappings.update(
    mapping.id,
    node_definitions=[customer_node, account_node],
    edge_definitions=[shares_account_edge, owns_account_edge],
    change_description="Add Account node and OWNS_ACCOUNT edge",
)

print(f"Updated to version {updated.current_version}")
print(f"  Nodes: {[n.label for n in updated.node_definitions]}")
print(f"  Edges: {[e.type for e in updated.edge_definitions]}")
```

```python
# List all versions of the mapping
versions = analyst.mappings.list_versions(mapping.id)
print(f"Versions for mapping {mapping.id} ({len(versions)} total):")
for v in versions:
    desc = v.change_description or "(initial)"
    nodes = [n.label for n in v.node_definitions]
    edges = [e.type for e in v.edge_definitions]
    print(f"  v{v.version}: {desc}")
    print(f"         nodes={nodes}  edges={edges}")
```

<div class="nb-section">
  <span class="nb-section__number">7</span>
  <div>
    <h2 class="nb-section__title">Comparing Versions</h2>
    <p class="nb-section__description">Diff two versions to see what changed</p>
  </div>
</div>

```python
# Diff version 1 vs version 2
diff = analyst.mappings.diff(mapping.id, from_version=1, to_version=2)

print(f"Diff v1 -> v2:")
print(f"  Nodes added:    {diff.summary.get('nodes_added', 0)}")
print(f"  Nodes removed:  {diff.summary.get('nodes_removed', 0)}")
print(f"  Edges added:    {diff.summary.get('edges_added', 0)}")
print(f"  Edges removed:  {diff.summary.get('edges_removed', 0)}")

# Use helper methods to inspect individual changes
print(f"\nAdded nodes:")
for node in diff.nodes_added():
    print(f"  + {node}")
print(f"Added edges:")
for edge in diff.edges_added():
    print(f"  + {edge}")
```

```python
# Retrieve a specific version
v1 = analyst.mappings.get_version(mapping.id, version=1)
print(f"Version 1 snapshot:")
print(f"  Nodes: {[n.label for n in v1.node_definitions]}")
print(f"  Edges: {[e.type for e in v1.edge_definitions]}")
```

<div class="nb-section">
  <span class="nb-section__number">8</span>
  <div>
    <h2 class="nb-section__title">Copy and Cleanup</h2>
    <p class="nb-section__description">Copy a mapping for experimentation, then clean up</p>
  </div>
</div>

```python
# Copy the mapping for experimentation
copy_name = f"tutorial-authoring-copy-{namespace}"
copy = analyst.mappings.copy(mapping.id, copy_name)
print(f"Copied mapping:")
print(f"  Original: {mapping.name} (id={mapping.id})")
print(f"  Copy:     {copy.name} (id={copy.id})")
print(f"  Nodes:    {[n.label for n in copy.node_definitions]}")
print(f"  Edges:    {[e.type for e in copy.edge_definitions]}")

# View the mapping tree structure
tree = analyst.mappings.get_tree(mapping.id)
print(f"\nMapping tree:")
for key, value in tree.items():
    print(f"  {key}: {value}")
```

```python
# Clean up: delete the copy and the tutorial mapping
analyst.mappings.delete(copy.id)
print(f"Deleted copy: {copy.name} (id={copy.id})")

analyst.mappings.delete(mapping.id)
print(f"Deleted mapping: {mapping.name} (id={mapping.id})")

print("\nCleanup complete.")
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li>Use <code>schema.list_catalogs/schemas/tables/columns</code> to discover SQL data sources before designing mappings</li>
    <li><code>NodeDefinition</code> maps a SQL query to a graph node label with a primary key and typed properties</li>
    <li><code>EdgeDefinition</code> maps a SQL join to a graph relationship between two node labels</li>
    <li><code>mappings.create()</code> builds a mapping from node and edge definitions in a single call</li>
    <li><code>mappings.update()</code> creates a new version -- use <code>change_description</code> to document the reason</li>
    <li><code>mappings.diff()</code> shows exactly what changed between two versions (added, removed, modified)</li>
    <li><code>mappings.copy()</code> creates an independent copy for safe experimentation</li>
    <li>Always clean up tutorial mappings with <code>mappings.delete()</code> to avoid resource clutter</li>
  </ul>
</div>
