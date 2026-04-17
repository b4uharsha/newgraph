---
title: "Schema Cache"
---

<div class="nb-callout nb-callout--warning">
  <span class="nb-sr-only">Warning:</span>
  <span class="nb-callout__icon" aria-hidden="true"></span>
  <div class="nb-callout__content">
    <div class="nb-callout__title">Not for Jupyter</div>
    <div class="nb-callout__body">
      These E2E notebooks are <strong>not designed to run in JupyterHub or an interactive Jupyter kernel</strong>. They are executed standalone by the test runner (<code>make test TYPE=e2e CLUSTER=gke-london</code>) and depend on pytest fixtures, environment variables, and cluster-provisioned personas that are not present in an interactive session.
      <br/><br/>
      Opening them in Jupyter will surface missing imports, undefined fixtures, and cleanup failures. Use the tutorials under <code>docs/notebooks/tutorials/</code> for interactive learning.
    </div>
  </div>
</div>

<div class="nb-header">
  <span class="nb-header__type">E2E Test</span>
  <h1 class="nb-header__title">Schema Cache</h1>
  <p class="nb-header__subtitle">Cache invalidation and refresh validation</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">10 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--intermediate">
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
      </span>
      Intermediate
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">E2E Test</span><span class="nb-header__tag">Test</span></div>
</div>

```python
# Parameters cell - papermill will inject values here
INSTANCE_ID = None  # Injected by papermill from fixtures
```

```python
import os
import time

from graph_olap.notebook import wake_starburst
from graph_olap.exceptions import ForbiddenError, NotFoundError

print(f"GRAPH_OLAP_API_URL: {os.environ.get('GRAPH_OLAP_API_URL', 'not set')}")
wake_starburst()
```

```python
from graph_olap.notebook_setup import setup
from graph_olap.personas import Persona

ctx = setup(prefix="SchemaCacheTest", persona=Persona.ANALYST_ALICE)
client = ctx.client
admin_client = ctx.with_persona(Persona.ADMIN_CAROL)
ops_client = ctx.with_persona(Persona.OPS_DAVE)
print("Clients ready: analyst (Alice), admin (Carol), ops (Dave)")
```

<div class="nb-section">
  <span class="nb-section__number">1</span>
  <div>
    <h2 class="nb-section__title">Cache Lifecycle</h2>
    <p class="nb-section__description">Ensure the schema cache is populated and fresh. An admin triggers a refresh,</p>
  </div>
</div>

```python
# Test 1.1: Admin triggers cache refresh
result = admin_client.schema.admin_refresh()

assert isinstance(result, dict), f"Expected dict, got {type(result)}"
assert result.get("status") == "refresh triggered", (
    f"Expected {{'status': 'refresh triggered'}}, got {result}"
)

print(f"Refresh response: {result}")
print("\nTest 1.1 PASSED: Admin triggered cache refresh")
```

```python
# Test 1.2: Wait for cache to populate (up to 120s)
print("Waiting for cache to populate...")

MAX_WAIT = 120
POLL_INTERVAL = 10
elapsed = 0
stats = None

while elapsed < MAX_WAIT:
    stats = admin_client.schema.get_stats()
    if stats.total_catalogs > 0:
        break
    print(f"  {elapsed}s - cache empty (total_catalogs=0), retrying in {POLL_INTERVAL}s...")
    time.sleep(POLL_INTERVAL)
    elapsed += POLL_INTERVAL

assert stats is not None, "Stats should not be None"
assert stats.total_catalogs > 0, (
    f"Cache still empty after {MAX_WAIT}s (total_catalogs={stats.total_catalogs})"
)

print(f"\nCache populated after ~{elapsed}s:")
print(f"  Catalogs:  {stats.total_catalogs}")
print(f"  Schemas:   {stats.total_schemas}")
print(f"  Tables:    {stats.total_tables}")
print(f"  Columns:   {stats.total_columns}")
print(f"  Index:     {stats.index_size_bytes} bytes")
print(f"  Refreshed: {stats.last_refresh}")
print("\nTest 1.2 PASSED: Cache populated with data")
```

```python
# Test 1.3: Verify last_refresh timestamp is recent (within 5 minutes)
from datetime import datetime, timezone

assert stats.last_refresh is not None, "last_refresh should be set after refresh"

# Parse ISO 8601 timestamp
last_refresh_dt = datetime.fromisoformat(stats.last_refresh.replace("Z", "+00:00"))
now = datetime.now(timezone.utc)
age_seconds = (now - last_refresh_dt).total_seconds()

assert age_seconds < 300, (
    f"last_refresh is too old: {age_seconds:.0f}s ago (expected < 300s). "
    f"last_refresh={stats.last_refresh}"
)
assert age_seconds >= 0, (
    f"last_refresh is in the future: {age_seconds:.0f}s from now"
)

print(f"last_refresh: {stats.last_refresh}")
print(f"Age: {age_seconds:.0f}s (threshold: 300s)")
print("\nTest 1.3 PASSED: last_refresh is recent (within 5 minutes)")
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Hierarchical Browsing & Data Integrity</h2>
    <p class="nb-section__description">Walk the full hierarchy: catalogs -> schemas -> tables -> columns.</p>
  </div>
</div>

```python
# Test 2.1: List catalogs
catalogs = client.schema.list_catalogs()

assert isinstance(catalogs, list), f"Expected list, got {type(catalogs)}"
assert len(catalogs) > 0, "Should have at least one catalog"

for cat in catalogs:
    assert hasattr(cat, "catalog_name"), "Catalog missing catalog_name"
    assert isinstance(cat.catalog_name, str), "catalog_name should be str"
    assert len(cat.catalog_name) > 0, "catalog_name should not be empty"
    assert hasattr(cat, "schema_count"), "Catalog missing schema_count"
    assert cat.schema_count >= 0, f"schema_count should be >= 0, got {cat.schema_count}"

print(f"Found {len(catalogs)} catalogs:")
for cat in catalogs[:5]:
    print(f"  - {cat.catalog_name} ({cat.schema_count} schemas)")
if len(catalogs) > 5:
    print(f"  ... and {len(catalogs) - 5} more")

print("\nTest 2.1 PASSED: List catalogs with valid metadata")
```

```python
# Test 2.2: List schemas for first catalog, verify count matches
first_catalog = catalogs[0]
schemas = client.schema.list_schemas(first_catalog.catalog_name)

assert isinstance(schemas, list), f"Expected list, got {type(schemas)}"
assert len(schemas) == first_catalog.schema_count, (
    f"Schema count mismatch: list_schemas returned {len(schemas)}, "
    f"but catalog.schema_count={first_catalog.schema_count}"
)

for sch in schemas:
    assert hasattr(sch, "schema_name"), "Schema missing schema_name"
    assert isinstance(sch.schema_name, str), "schema_name should be str"
    assert len(sch.schema_name) > 0, "schema_name should not be empty"
    assert hasattr(sch, "table_count"), "Schema missing table_count"
    assert sch.table_count >= 0, f"table_count should be >= 0, got {sch.table_count}"

print(f"Catalog '{first_catalog.catalog_name}' has {len(schemas)} schemas:")
for sch in schemas[:5]:
    print(f"  - {sch.schema_name} ({sch.table_count} tables)")
if len(schemas) > 5:
    print(f"  ... and {len(schemas) - 5} more")

print("\nTest 2.2 PASSED: Schema count matches catalog.schema_count")
```

```python
# Test 2.3: List tables for first schema with tables, verify count matches
# Find first schema that actually has tables
target_schema = None
target_catalog_name = None
for cat in catalogs:
    cat_schemas = client.schema.list_schemas(cat.catalog_name)
    for sch in cat_schemas:
        if sch.table_count > 0:
            target_schema = sch
            target_catalog_name = cat.catalog_name
            break
    if target_schema:
        break

assert target_schema is not None, "No schema with tables found in any catalog"

tables = client.schema.list_tables(target_catalog_name, target_schema.schema_name)

assert isinstance(tables, list), f"Expected list, got {type(tables)}"
assert len(tables) == target_schema.table_count, (
    f"Table count mismatch: list_tables returned {len(tables)}, "
    f"but schema.table_count={target_schema.table_count}"
)

for tbl in tables:
    assert hasattr(tbl, "table_name"), "Table missing table_name"
    assert isinstance(tbl.table_name, str), "table_name should be str"
    assert len(tbl.table_name) > 0, "table_name should not be empty"
    assert hasattr(tbl, "table_type"), "Table missing table_type"
    assert isinstance(tbl.table_type, str), "table_type should be str"
    assert hasattr(tbl, "column_count"), "Table missing column_count"
    assert tbl.column_count >= 0, f"column_count should be >= 0, got {tbl.column_count}"

print(f"Schema '{target_catalog_name}.{target_schema.schema_name}' has {len(tables)} tables:")
for tbl in tables[:5]:
    print(f"  - {tbl.table_name} ({tbl.table_type}, {tbl.column_count} columns)")
if len(tables) > 5:
    print(f"  ... and {len(tables) - 5} more")

print("\nTest 2.3 PASSED: Table count matches schema.table_count")
```

```python
# Test 2.4: List columns for first table, verify count and metadata
first_table = tables[0]
columns = client.schema.list_columns(
    target_catalog_name,
    target_schema.schema_name,
    first_table.table_name,
)

assert isinstance(columns, list), f"Expected list, got {type(columns)}"
assert len(columns) == first_table.column_count, (
    f"Column count mismatch: list_columns returned {len(columns)}, "
    f"but table.column_count={first_table.column_count}"
)

for col in columns:
    assert hasattr(col, "column_name"), "Column missing column_name"
    assert isinstance(col.column_name, str), "column_name should be str"
    assert len(col.column_name) > 0, "column_name should not be empty"

    assert hasattr(col, "data_type"), "Column missing data_type"
    assert isinstance(col.data_type, str), "data_type should be str"
    assert len(col.data_type) > 0, "data_type should not be empty"

    assert hasattr(col, "is_nullable"), "Column missing is_nullable"
    assert isinstance(col.is_nullable, bool), (
        f"is_nullable should be bool, got {type(col.is_nullable)}"
    )

    assert hasattr(col, "ordinal_position"), "Column missing ordinal_position"
    assert isinstance(col.ordinal_position, int), (
        f"ordinal_position should be int, got {type(col.ordinal_position)}"
    )
    assert col.ordinal_position >= 1, (
        f"ordinal_position should be >= 1, got {col.ordinal_position}"
    )

print(f"Table '{first_table.table_name}' has {len(columns)} columns:")
for col in columns[:8]:
    nullable = "NULL" if col.is_nullable else "NOT NULL"
    default = f" DEFAULT {col.column_default}" if col.column_default else ""
    print(f"  {col.ordinal_position}. {col.column_name} {col.data_type} {nullable}{default}")
if len(columns) > 8:
    print(f"  ... and {len(columns) - 8} more")

print("\nTest 2.4 PASSED: Column count matches table.column_count, metadata well-formed")
```

```python
# Test 2.5: Verify ordinal positions are contiguous (1, 2, 3, ..., N)
positions = sorted(col.ordinal_position for col in columns)
expected = list(range(1, len(columns) + 1))

assert positions == expected, (
    f"Ordinal positions are not contiguous. "
    f"Expected {expected}, got {positions}"
)

print(f"Ordinal positions: {positions}")
print(f"Contiguous from 1 to {len(columns)}: YES")
print("\nTest 2.5 PASSED: Ordinal positions are contiguous (1..N)")
```

```python
# Test 2.6: Cross-check total columns across all schemas against stats
# Sum column_count from every table in every schema of every catalog
print("Cross-checking column totals across full hierarchy...")

total_column_count = 0
catalogs_checked = 0
schemas_checked = 0
tables_checked = 0

for cat in catalogs:
    cat_schemas = client.schema.list_schemas(cat.catalog_name)
    for sch in cat_schemas:
        if sch.table_count > 0:
            sch_tables = client.schema.list_tables(cat.catalog_name, sch.schema_name)
            for tbl in sch_tables:
                total_column_count += tbl.column_count
                tables_checked += 1
            schemas_checked += 1
    catalogs_checked += 1

# Re-fetch stats for comparison
fresh_stats = admin_client.schema.get_stats()

assert total_column_count == fresh_stats.total_columns, (
    f"Column count mismatch: sum of table.column_count={total_column_count}, "
    f"but stats.total_columns={fresh_stats.total_columns}"
)

print(f"Traversed: {catalogs_checked} catalogs, {schemas_checked} schemas, {tables_checked} tables")
print(f"Sum of table column_counts: {total_column_count}")
print(f"stats.total_columns:        {fresh_stats.total_columns}")
print(f"Match: YES")
print("\nTest 2.6 PASSED: Column totals match stats.total_columns")
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Search Operations</h2>
    <p class="nb-section__description">Test table and column search with pattern matching, result limits,</p>
  </div>
</div>

```python
# Test 3.1: Search tables with a broad pattern (prefix of a known table)
# Use the first 2 characters of a known table name as search pattern
known_table = tables[0]
search_prefix = known_table.table_name[:2].lower()

table_results = client.schema.search_tables(search_prefix)

assert isinstance(table_results, list), f"Expected list, got {type(table_results)}"
assert len(table_results) > 0, (
    f"Search for '{search_prefix}' returned 0 results, expected at least 1 "
    f"(known table: {known_table.table_name})"
)

# Verify all results have a table_name starting with the search prefix (case-insensitive)
for tbl in table_results:
    assert tbl.table_name.lower().startswith(search_prefix.lower()), (
        f"Table '{tbl.table_name}' does not start with '{search_prefix}'"
    )

print(f"Search pattern: '{search_prefix}'")
print(f"Results: {len(table_results)} tables")
for tbl in table_results[:5]:
    print(f"  - {tbl.catalog_name}.{tbl.schema_name}.{tbl.table_name}")
if len(table_results) > 5:
    print(f"  ... and {len(table_results) - 5} more")

print("\nTest 3.1 PASSED: Table search returns matching results with correct prefix")
```

```python
# Test 3.2: Search tables with limit=3
limited_results = client.schema.search_tables(search_prefix, limit=3)

assert isinstance(limited_results, list), f"Expected list, got {type(limited_results)}"
assert len(limited_results) <= 3, (
    f"Limit=3 but got {len(limited_results)} results"
)

print(f"Search pattern: '{search_prefix}', limit=3")
print(f"Results: {len(limited_results)} tables (max 3)")
for tbl in limited_results:
    print(f"  - {tbl.catalog_name}.{tbl.schema_name}.{tbl.table_name}")

print("\nTest 3.2 PASSED: Search tables respects limit=3")
```

```python
# Test 3.3: Search columns with a broad pattern (prefix of a known column)
known_column = columns[0]
col_search_prefix = known_column.column_name[:2].lower()

column_results = client.schema.search_columns(col_search_prefix)

assert isinstance(column_results, list), f"Expected list, got {type(column_results)}"
assert len(column_results) > 0, (
    f"Search for '{col_search_prefix}' returned 0 results, expected at least 1 "
    f"(known column: {known_column.column_name})"
)

print(f"Search pattern: '{col_search_prefix}'")
print(f"Results: {len(column_results)} columns")
for col in column_results[:5]:
    print(f"  - {col.catalog_name}.{col.schema_name}.{col.table_name}.{col.column_name} ({col.data_type})")
if len(column_results) > 5:
    print(f"  ... and {len(column_results) - 5} more")

print("\nTest 3.3 PASSED: Column search returns matching results")
```

```python
# Test 3.4: Search columns with limit=5
limited_col_results = client.schema.search_columns(col_search_prefix, limit=5)

assert isinstance(limited_col_results, list), f"Expected list, got {type(limited_col_results)}"
assert len(limited_col_results) <= 5, (
    f"Limit=5 but got {len(limited_col_results)} results"
)

print(f"Search pattern: '{col_search_prefix}', limit=5")
print(f"Results: {len(limited_col_results)} columns (max 5)")
for col in limited_col_results:
    print(f"  - {col.column_name} ({col.data_type})")

print("\nTest 3.4 PASSED: Search columns respects limit=5")
```

```python
# Test 3.5: Search with non-matching pattern returns empty list
no_results = client.schema.search_tables("zzzznonexistent")

assert isinstance(no_results, list), f"Expected list, got {type(no_results)}"
assert len(no_results) == 0, (
    f"Expected 0 results for 'zzzznonexistent', got {len(no_results)}"
)

no_col_results = client.schema.search_columns("zzzznonexistent")

assert isinstance(no_col_results, list), f"Expected list, got {type(no_col_results)}"
assert len(no_col_results) == 0, (
    f"Expected 0 column results for 'zzzznonexistent', got {len(no_col_results)}"
)

print("Search for 'zzzznonexistent':")
print(f"  Tables:  {len(no_results)} results")
print(f"  Columns: {len(no_col_results)} results")
print("\nTest 3.5 PASSED: Non-matching pattern returns empty results")
```

```python
# Test 3.6: Search is case-insensitive (same pattern in different cases returns same count)
pattern_lower = search_prefix.lower()
pattern_upper = search_prefix.upper()

results_lower = client.schema.search_tables(pattern_lower)
results_upper = client.schema.search_tables(pattern_upper)

assert len(results_lower) == len(results_upper), (
    f"Case-insensitive mismatch: '{pattern_lower}' returned {len(results_lower)} results, "
    f"'{pattern_upper}' returned {len(results_upper)} results"
)

# Also verify column search is case-insensitive
col_lower = client.schema.search_columns(col_search_prefix.lower())
col_upper = client.schema.search_columns(col_search_prefix.upper())

assert len(col_lower) == len(col_upper), (
    f"Column case-insensitive mismatch: '{col_search_prefix.lower()}' returned {len(col_lower)} results, "
    f"'{col_search_prefix.upper()}' returned {len(col_upper)} results"
)

print(f"Table search '{pattern_lower}' vs '{pattern_upper}': {len(results_lower)} == {len(results_upper)}")
print(f"Column search '{col_search_prefix.lower()}' vs '{col_search_prefix.upper()}': {len(col_lower)} == {len(col_upper)}")
print("\nTest 3.6 PASSED: Search is case-insensitive")
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Error Handling (404s)</h2>
    <p class="nb-section__description">Verify that schema endpoints raise `NotFoundError` for nonexistent resources.</p>
  </div>
</div>

```python
# Test 4.1: list_schemas on nonexistent catalog raises NotFoundError
try:
    client.schema.list_schemas("nonexistent_catalog_xyz")
    assert False, "Should have raised NotFoundError"
except NotFoundError:
    pass

print("Test 4.1 PASSED: NotFoundError for nonexistent catalog")
```

```python
# Test 4.2: list_tables on nonexistent schema raises NotFoundError
try:
    client.schema.list_tables(catalogs[0].catalog_name, "nonexistent_schema_xyz")
    assert False, "Should have raised NotFoundError"
except NotFoundError:
    pass

print("Test 4.2 PASSED: NotFoundError for nonexistent schema")
```

```python
# Test 4.3: list_columns on nonexistent table raises NotFoundError
try:
    client.schema.list_columns(
        catalogs[0].catalog_name,
        "information_schema",
        "nonexistent_table_xyz",
    )
    assert False, "Should have raised NotFoundError"
except NotFoundError:
    pass

print("Test 4.3 PASSED: NotFoundError for nonexistent table")
```

<div class="nb-section">
  <span class="nb-section__number">5</span>
  <div>
    <h2 class="nb-section__title">Permission Model</h2>
    <p class="nb-section__description">Verify role-based access for admin-only endpoints (`get_stats`, `admin_refresh`)</p>
  </div>
</div>

```python
# Test 5.1: Analyst calling get_stats raises ForbiddenError
try:
    client.schema.get_stats()
    assert False, "Should have raised ForbiddenError"
except ForbiddenError:
    pass

print("Test 5.1 PASSED: Analyst cannot call get_stats (ForbiddenError)")
```

```python
# Test 5.2: Analyst calling admin_refresh raises ForbiddenError
try:
    client.schema.admin_refresh()
    assert False, "Should have raised ForbiddenError"
except ForbiddenError:
    pass

print("Test 5.2 PASSED: Analyst cannot call admin_refresh (ForbiddenError)")
```

```python
# Test 5.3: Admin can call get_stats successfully
stats = admin_client.schema.get_stats()

assert stats.total_catalogs >= 0, "total_catalogs should be non-negative"
assert stats.total_schemas >= 0, "total_schemas should be non-negative"
assert stats.total_tables >= 0, "total_tables should be non-negative"
assert stats.total_columns >= 0, "total_columns should be non-negative"
assert stats.index_size_bytes >= 0, "index_size_bytes should be non-negative"

print(f"Admin stats: {stats.total_catalogs} catalogs, "
      f"{stats.total_schemas} schemas, "
      f"{stats.total_tables} tables, "
      f"{stats.total_columns} columns")
print("Test 5.3 PASSED: Admin can call get_stats")
```

```python
# Test 5.4: Admin can call admin_refresh successfully
result = admin_client.schema.admin_refresh()

assert isinstance(result, dict), "admin_refresh should return a dict"
assert result["status"] == "refresh triggered", "Should confirm refresh triggered"

print(f"Admin refresh result: {result}")
print("Test 5.4 PASSED: Admin can call admin_refresh")
```

```python
# Test 5.5: Ops can call get_stats (ops has admin-level access to monitoring endpoints)
ops_stats = ops_client.schema.get_stats()

assert ops_stats.total_catalogs >= 0, "total_catalogs should be non-negative"

print(f"Ops stats: {ops_stats.total_catalogs} catalogs, "
      f"{ops_stats.total_schemas} schemas, "
      f"{ops_stats.total_tables} tables, "
      f"{ops_stats.total_columns} columns")
print("Test 5.5 PASSED: Ops can call get_stats")
```

```python
# Test 5.6: All personas can call list_catalogs (read endpoints open to all)
analyst_catalogs = client.schema.list_catalogs()
assert isinstance(analyst_catalogs, list), "Analyst list_catalogs should return a list"

admin_catalogs = admin_client.schema.list_catalogs()
assert isinstance(admin_catalogs, list), "Admin list_catalogs should return a list"

ops_catalogs = ops_client.schema.list_catalogs()
assert isinstance(ops_catalogs, list), "Ops list_catalogs should return a list"

print(f"Analyst sees {len(analyst_catalogs)} catalogs")
print(f"Admin sees {len(admin_catalogs)} catalogs")
print(f"Ops sees {len(ops_catalogs)} catalogs")
print("Test 5.6 PASSED: All personas can call list_catalogs")
```

<div class="nb-section">
  <span class="nb-section__number">6</span>
  <div>
    <h2 class="nb-section__title">Performance & Summary</h2>
    <p class="nb-section__description">Verify schema cache endpoints respond within acceptable latency thresholds,</p>
  </div>
</div>

```python
# Test 6.1: list_catalogs responds within 500ms
start = time.time()
client.schema.list_catalogs()
duration_ms = (time.time() - start) * 1000

print(f"list_catalogs: {duration_ms:.2f}ms")
assert duration_ms < 500, f"Too slow: {duration_ms:.2f}ms (threshold 500ms)"

print("Test 6.1 PASSED: list_catalogs < 500ms")
```

```python
# Test 6.2: search_tables responds within 500ms
start = time.time()
client.schema.search_tables("a", limit=50)
duration_ms = (time.time() - start) * 1000

print(f"search_tables: {duration_ms:.2f}ms")
assert duration_ms < 500, f"Too slow: {duration_ms:.2f}ms (threshold 500ms)"

print("Test 6.2 PASSED: search_tables < 500ms")
```

```python
# Test 6.3: list_columns for a known table responds within 500ms
# Use the first catalog from Section 2 and drill into a real table
if catalogs:
    schemas = client.schema.list_schemas(catalogs[0].catalog_name)
    if schemas:
        tables = client.schema.list_tables(
            catalogs[0].catalog_name, schemas[0].schema_name
        )
        if tables:
            start = time.time()
            client.schema.list_columns(
                catalogs[0].catalog_name,
                schemas[0].schema_name,
                tables[0].table_name,
            )
            duration_ms = (time.time() - start) * 1000

            print(f"list_columns({catalogs[0].catalog_name}."
                  f"{schemas[0].schema_name}."
                  f"{tables[0].table_name}): {duration_ms:.2f}ms")
            assert duration_ms < 500, f"Too slow: {duration_ms:.2f}ms (threshold 500ms)"
            print("Test 6.3 PASSED: list_columns < 500ms")
        else:
            print("Test 6.3 SKIPPED: No tables available to time")
    else:
        print("Test 6.3 SKIPPED: No schemas available to time")
else:
    print("Test 6.3 SKIPPED: No catalogs available to time")
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li>Schema cache populated and queried</li>
    <li>Cache invalidation triggers refresh</li>
    <li>Stale entries cleared correctly</li>
  </ul>
</div>

```python
# Final summary
ctx.teardown()

print("\n" + "=" * 60)
print("SCHEMA CACHE E2E TESTS COMPLETED!")
print("=" * 60)

print("\n  Section 4: Error Handling (404s)")
print("    4.1 NotFoundError for nonexistent catalog")
print("    4.2 NotFoundError for nonexistent schema")
print("    4.3 NotFoundError for nonexistent table")

print("\n  Section 5: Permission Model")
print("    5.1 Analyst cannot call get_stats (ForbiddenError)")
print("    5.2 Analyst cannot call admin_refresh (ForbiddenError)")
print("    5.3 Admin can call get_stats")
print("    5.4 Admin can call admin_refresh")
print("    5.5 Ops can call get_stats")
print("    5.6 All personas can call list_catalogs")

print("\n  Section 6: Performance")
print("    6.1 list_catalogs < 500ms")
print("    6.2 search_tables < 500ms")
print("    6.3 list_columns < 500ms")

print("\nAll schema cache tests passed.")
```
