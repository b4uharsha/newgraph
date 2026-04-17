---
title: "Exploring Warehouse Schemas"
---

<div class="nb-header">
  <span class="nb-header__type">Tutorial</span>
  <h1 class="nb-header__title">Exploring Warehouse Schemas</h1>
  <p class="nb-header__subtitle">Discover tables, columns, and relationships in your data warehouse</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">20 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--intermediate">
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
      </span>
      Intermediate
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">Schema</span><span class="nb-header__tag">Catalog</span><span class="nb-header__tag">Discovery</span><span class="nb-header__tag">Tables</span></div>
</div>

<div class="nb-objectives">
  <h3 class="nb-objectives__title">What You'll Learn</h3>
  <ul class="nb-objectives__list">
    <li><strong>Catalog Browsing</strong> - List catalogs, schemas, and tables</li>
    <li><strong>Column Discovery</strong> - Inspect table columns and data types</li>
    <li><strong>Search</strong> - Find tables and columns by pattern</li>
    <li><strong>Schema Navigation</strong> - Drill down through the catalog hierarchy</li>
  </ul>
</div>

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

# Cell 3 — Provision
from notebook_setup import provision
personas, conn = provision(USERNAME)
analyst = personas["analyst"]
admin = personas["admin"]
ops = personas["ops"]
client = analyst

print(f"Connected to: {client._config.api_url}")
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Browsing the Catalog</h2>
    <p class="nb-section__description">Navigate catalogs, schemas, and tables</p>
  </div>
</div>

```python
# List available catalogs
catalogs = client.schema.list_catalogs()
print("Catalogs:")
if not catalogs:
    print("  (no catalogs in cache — Starburst cache may be cold)")
else:
    for cat in catalogs:
        print(f"  {cat.catalog_name}")

    # List schemas within a catalog
    cat_name = catalogs[0].catalog_name
    schemas = client.schema.list_schemas(cat_name)
    print(f"\nSchemas in '{cat_name}':")
    for s in schemas:
        print(f"  {s.schema_name}")

    # List tables within a schema
    if schemas:
        schema_name = schemas[0].schema_name
        tables = client.schema.list_tables(cat_name, schema_name)
        print(f"\nTables in '{cat_name}.{schema_name}':")
        for t in tables:
            print(f"  {t.table_name}")
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Inspecting Columns</h2>
    <p class="nb-section__description">View column names and data types</p>
  </div>
</div>

```python
# List columns for the customer demographics table
if catalogs and schemas and tables:
    columns = client.schema.list_columns(cat_name, schema_name, tables[0].table_name)
    print(f"Columns in '{tables[0].table_name}':")
    for col in columns:
        print(f"  {col.column_name}: {col.data_type}")

    # List columns for the account data table
    if len(tables) > 1:
        acct_columns = client.schema.list_columns(cat_name, schema_name, tables[1].table_name)
        print(f"\nColumns in '{tables[1].table_name}':")
        for col in acct_columns:
            print(f"  {col.column_name}: {col.data_type}")
else:
    print("Skipped — no catalogs, schemas, or tables available.")
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Searching Tables and Columns</h2>
    <p class="nb-section__description">Find tables and columns by pattern</p>
  </div>
</div>

```python
# Search for tables matching a pattern
table_results = client.schema.search_tables("bis", limit=10)
print("Tables matching 'bis':")
for t in table_results:
    print(f"  {t}")

# Search for columns matching a pattern
column_results = client.schema.search_columns("psdo", limit=10)
print("\nColumns matching 'psdo':")
for c in column_results:
    print(f"  {c}")
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li>Use <code>client.schema</code> (singular) to access the schema browser</li>
    <li>Navigate the hierarchy: <code>list_catalogs()</code> → <code>list_schemas()</code> → <code>list_tables()</code> → <code>list_columns()</code></li>
    <li>Use <code>search_tables()</code> and <code>search_columns()</code> to find objects by pattern</li>
    <li>Column metadata helps you understand your data before building mappings</li>
  </ul>
</div>
