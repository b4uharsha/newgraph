---
title: "SchemaResource"
---

<div class="nb-header">
  <span class="nb-header__type">Reference</span>
  <h1 class="nb-header__title">SchemaResource</h1>
  <p class="nb-header__subtitle">Data catalog exploration</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">10 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--beginner">
        <span class="nb-difficulty__dot"></span>
      </span>
      Beginner
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">Reference</span><span class="nb-header__tag">API</span></div>
</div>

## SchemaResource

Accessed via `client.schema`, this resource provides read-only access to
Starburst catalog metadata -- catalogs, schemas, tables, and columns.

All operations use cached metadata (refreshed every 24h) so calls are fast
and do not hit Starburst directly.

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
    <h2 class="nb-section__title">Listing Catalogs</h2>
    <p class="nb-section__description">Discover available data sources</p>
  </div>
</div>

### `list_catalogs() -> list[Catalog]`

List all cached Starburst catalogs, sorted by name.

**Returns:** List of `Catalog` objects.

| Field | Type | Description |
|-------|------|-------------|
| `catalog_name` | `str` | Catalog name |
| `schema_count` | `int` | Number of schemas in the catalog |
| `cached_at` | `str \| None` | ISO 8601 timestamp of when metadata was cached |

```python
# Ensure schema cache is populated (admin-only operation)
import time

admin.schema.admin_refresh()
print("Cache refresh triggered, waiting for data...")

# Wait for cache to populate (up to 120s)
for _ in range(24):
    time.sleep(5)
    catalogs = client.schema.list_catalogs()
    if catalogs:
        break
    print("  waiting...")

print(f"\nCatalogs: {len(catalogs)}\n")
for cat in catalogs:
    print(f"  {cat.catalog_name}: {cat.schema_count} schemas")
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Listing Schemas &amp; Tables</h2>
    <p class="nb-section__description">Navigate the catalog hierarchy</p>
  </div>
</div>

### `list_schemas(catalog) -> list[Schema]`

List all schemas in a catalog.

| Parameter | Type | Description |
|-----------|------|-------------|
| `catalog` | `str` | Catalog name (e.g., `"analytics"`) |

**Returns:** List of `Schema` objects.

**Raises:** `NotFoundError` if the catalog is not in cache.

```python
# Use the first catalog discovered above
catalog_name = catalogs[0].catalog_name if catalogs else "default"
schemas = client.schema.list_schemas(catalog_name)

for sch in schemas[:5]:
    print(f"  {sch.schema_name}: {sch.table_count} tables")
```

### `list_tables(catalog, schema) -> list[Table]`

List all tables in a schema.

| Parameter | Type | Description |
|-----------|------|-------------|
| `catalog` | `str` | Catalog name |
| `schema` | `str` | Schema name |

**Returns:** List of `Table` objects.

**Raises:** `NotFoundError` if the schema is not in cache.

```python
# Use the first schema discovered above
schema_name = schemas[0].schema_name if schemas else "public"
tables = client.schema.list_tables(catalog_name, schema_name)

for tbl in tables[:5]:
    print(f"  {tbl.table_name} ({tbl.table_type})")
```

### `list_columns(catalog, schema, table) -> list[Column]`

Get all columns for a table, sorted by ordinal position.

| Parameter | Type | Description |
|-----------|------|-------------|
| `catalog` | `str` | Catalog name |
| `schema` | `str` | Schema name |
| `table` | `str` | Table name |

**Returns:** List of `Column` objects.

**Raises:** `NotFoundError` if the table is not in cache.

```python
# Use the first table discovered above
table_name = tables[0].table_name if tables else "customers"
columns = client.schema.list_columns(catalog_name, schema_name, table_name)

for col in columns[:5]:
    nullable = "NULL" if col.is_nullable else "NOT NULL"
    print(f"  {col.column_name:20s} {col.data_type:15s} {nullable}")
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Searching</h2>
    <p class="nb-section__description">Find tables and columns by name</p>
  </div>
</div>

### `search_tables(pattern, limit=100) -> list[Table]`

Search tables by name pattern (prefix match, case-insensitive).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `pattern` | `str` | *required* | Search pattern |
| `limit` | `int` | `100` | Maximum results (max: 1000) |

**Returns:** List of `Table` objects matching the pattern.

```python
results = client.schema.search_tables("customer", limit=10)

print(f"Found {len(results)} tables\n")
for tbl in results:
    print(f"  {tbl.catalog_name}.{tbl.schema_name}.{tbl.table_name}")
```

### `search_columns(pattern, limit=100) -> list[Column]`

Search columns by name pattern (prefix match, case-insensitive).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `pattern` | `str` | *required* | Search pattern |
| `limit` | `int` | `100` | Maximum results (max: 1000) |

**Returns:** List of `Column` objects matching the pattern.

```python
results = client.schema.search_columns("email", limit=10)

print(f"Found {len(results)} columns\n")
for col in results:
    print(f"  {col.catalog_name}.{col.schema_name}.{col.table_name}.{col.column_name}: {col.data_type}")
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li><code>client.schema</code> provides read-only access to cached Starburst metadata</li>
    <li>Navigate the hierarchy: <code>list_catalogs()</code> &rarr; <code>list_schemas()</code> &rarr; <code>list_tables()</code> &rarr; <code>list_columns()</code></li>
    <li><code>search_tables()</code> and <code>search_columns()</code> find objects by name across all catalogs</li>
    <li>No instances are needed -- schema metadata is always available</li>
  </ul>
</div>
