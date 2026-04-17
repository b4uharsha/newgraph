---
title: "Exploring Schemas"
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
  <h1 class="nb-header__title">Exploring Schemas</h1>
  <p class="nb-header__subtitle">Data catalog browsing and search</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">10 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--beginner">
        <span class="nb-difficulty__dot"></span>
      </span>
      Beginner
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">E2E Test</span><span class="nb-header__tag">Test</span></div>
</div>

<div class="nb-section">
  <span class="nb-section__number">1</span>
  <div>
    <h2 class="nb-section__title">Setup</h2>
    <p class="nb-section__description">Initialize SDK clients for regular user and admin user.</p>
  </div>
</div>

```python
# Parameters cell - papermill will inject values here
INSTANCE_ID = None  # Injected by papermill from fixtures
```

```python
import os
import time

from graph_olap.notebook_setup import setup
from graph_olap.notebook import wake_starburst
from graph_olap.personas import Persona
from graph_olap.exceptions import ForbiddenError, NotFoundError

print(f"GRAPH_OLAP_API_URL: {os.environ.get('GRAPH_OLAP_API_URL', 'not set')}")

# Wake up Starburst Galaxy cluster (auto-suspends after 5 min idle)
wake_starburst()
```

```python
# Create test context as analyst Alice for regular user tests
ctx = setup(prefix="SchemaTest", persona=Persona.ANALYST_ALICE)
client = ctx.client

# Admin client for admin-only operations
admin_client = ctx.with_persona(Persona.ADMIN_CAROL)

print(f"Connected to {client._config.api_url}")
print(f"  - Regular user: analyst Alice")
print(f"  - Admin user: admin Carol")
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Basic Listing Operations</h2>
    <p class="nb-section__description">Test catalog, schema, table, and column listing with error handling.</p>
  </div>
</div>

```python
# Test 1.1: List all available catalogs
catalogs = client.schema.list_catalogs()

assert isinstance(catalogs, list), "Should return list"
print(f"Found {len(catalogs)} catalogs")

if catalogs:
    print("\nFirst 5 catalogs:")
    for cat in catalogs[:5]:
        print(f"  - {cat.catalog_name} ({cat.schema_count} schemas)")
else:
    print("  (Cache is empty - Starburst not configured)")

print("\nTest 1.1 PASSED: List catalogs")
```

```python
# Test 1.2: List schemas for non-existent catalog returns NotFoundError
try:
    schemas = client.schema.list_schemas("nonexistent_catalog")
    assert False, "Should have raised NotFoundError"
except NotFoundError as e:
    print(f"Correctly raised NotFoundError: {e}")

print("\nTest 1.2 PASSED: Error handling for missing catalog")
```

```python
# Test 1.3: List tables for non-existent schema returns NotFoundError
try:
    tables = client.schema.list_tables("catalog", "nonexistent_schema")
    assert False, "Should have raised NotFoundError"
except NotFoundError as e:
    print(f"Correctly raised NotFoundError: {e}")

print("\nTest 1.3 PASSED: Error handling for missing schema")
```

```python
# Test 1.4: List columns for non-existent table returns NotFoundError
try:
    columns = client.schema.list_columns("catalog", "schema", "nonexistent_table")
    assert False, "Should have raised NotFoundError"
except NotFoundError as e:
    print(f"Correctly raised NotFoundError: {e}")

print("\nTest 1.4 PASSED: Error handling for missing table")
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Search Operations</h2>
    <p class="nb-section__description">Test table and column search with patterns and limits.</p>
  </div>
</div>

```python
# Test 2.1: Search tables by pattern with limit
results = client.schema.search_tables("test", limit=10)

assert isinstance(results, list), "Should return list"
assert len(results) <= 10, "Should respect limit"

print(f"Search found {len(results)} tables matching 'test' (limit=10)")
if results:
    print("\nFirst 3 results:")
    for r in results[:3]:
        print(f"  - {r.catalog_name}.{r.schema_name}.{r.table_name} ({r.table_type})")

print("\nTest 2.1 PASSED: Search tables with limit")
```

```python
# Test 2.2: Search columns by pattern with limit
results = client.schema.search_columns("id", limit=10)

assert isinstance(results, list), "Should return list"
assert len(results) <= 10, "Should respect limit"

print(f"Search found {len(results)} columns matching 'id' (limit=10)")
if results:
    print("\nFirst 3 results:")
    for r in results[:3]:
        print(f"  - {r.catalog_name}.{r.schema_name}.{r.table_name}.{r.column_name} ({r.data_type})")

print("\nTest 2.2 PASSED: Search columns with limit")
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Admin Operations</h2>
    <p class="nb-section__description">Test admin-only operations with permission checks.</p>
  </div>
</div>

```python
# Test 3.1: Regular users cannot access admin endpoints
# Test get_stats forbidden for regular user
try:
    stats = client.schema.get_stats()
    assert False, "Should have raised ForbiddenError"
except ForbiddenError as e:
    print(f"Correctly raised ForbiddenError for stats: {e}")

# Test admin_refresh forbidden for regular user
try:
    result = client.schema.admin_refresh()
    assert False, "Should have raised ForbiddenError"
except ForbiddenError as e:
    print(f"Correctly raised ForbiddenError for refresh: {e}")

print("\nTest 3.1 PASSED: Permission checks")
```

```python
# Test 3.2: Get cache statistics as admin
stats = admin_client.schema.get_stats()

assert stats.total_catalogs >= 0, "Should have non-negative catalog count"
assert stats.total_schemas >= 0, "Should have non-negative schema count"
assert stats.total_tables >= 0, "Should have non-negative table count"
assert stats.total_columns >= 0, "Should have non-negative column count"
assert stats.index_size_bytes >= 0, "Should have non-negative index size"

print("Cache statistics (as admin):")
print(f"  - Catalogs: {stats.total_catalogs}")
print(f"  - Schemas: {stats.total_schemas}")
print(f"  - Tables: {stats.total_tables}")
print(f"  - Columns: {stats.total_columns}")
print(f"  - Index size: {stats.index_size_bytes} bytes")
if stats.last_refresh:
    print(f"  - Last refresh: {stats.last_refresh}")

print("\nTest 3.2 PASSED: Get stats as admin")
```

```python
# Test 3.3: Trigger manual cache refresh as admin
result = admin_client.schema.admin_refresh()

assert isinstance(result, dict), "Should return dict"
assert result["status"] == "refresh triggered", "Should confirm trigger"

print(f"Refresh triggered: {result}")
print("\nTest 3.3 PASSED: Admin refresh trigger")
```

<div class="nb-section">
  <span class="nb-section__number">5</span>
  <div>
    <h2 class="nb-section__title">Complete Workflows</h2>
    <p class="nb-section__description">Test complete end-to-end user workflows for schema browsing.</p>
  </div>
</div>

```python
# Test 4.1: Complete catalog browsing workflow
# This demonstrates the full user journey when exploring data for mapping creation

print("\n" + "="*60)
print("CATALOG BROWSING WORKFLOW")
print("="*60)

# Step 1: List all catalogs
catalogs = client.schema.list_catalogs()
print(f"\nStep 1: Found {len(catalogs)} catalogs")

if not catalogs:
    print("  No catalogs in cache (Starburst not configured)")
    print("  This is expected in environments without Starburst connection")
else:
    # Step 2: Browse first catalog
    first_catalog = catalogs[0]
    print(f"\nStep 2: Exploring catalog '{first_catalog.catalog_name}'")
    print(f"  - Schema count: {first_catalog.schema_count}")
    
    schemas = client.schema.list_schemas(first_catalog.catalog_name)
    print(f"  - Listed {len(schemas)} schemas")
    
    if schemas:
        # Step 3: Browse first schema
        first_schema = schemas[0]
        print(f"\nStep 3: Exploring schema '{first_schema.schema_name}'")
        print(f"  - Table count: {first_schema.table_count}")
        
        tables = client.schema.list_tables(
            first_catalog.catalog_name,
            first_schema.schema_name
        )
        print(f"  - Listed {len(tables)} tables")
        
        if tables:
            # Step 4: Browse first table
            first_table = tables[0]
            print(f"\nStep 4: Exploring table '{first_table.table_name}'")
            print(f"  - Table type: {first_table.table_type}")
            print(f"  - Column count: {first_table.column_count}")
            
            columns = client.schema.list_columns(
                first_catalog.catalog_name,
                first_schema.schema_name,
                first_table.table_name
            )
            print(f"  - Listed {len(columns)} columns:")
            
            # Show first 5 columns with details
            for col in columns[:5]:
                nullable = "NULL" if col.is_nullable else "NOT NULL"
                print(f"    {col.ordinal_position}. {col.column_name} {col.data_type} {nullable}")
            
            if len(columns) > 5:
                print(f"    ... and {len(columns) - 5} more columns")
        else:
            print("  - No tables in this schema")
    else:
        print("  - No schemas in this catalog")

print("\n" + "="*60)
print("Test 4.1 PASSED: Complete browsing workflow")
print("="*60)
```

```python
# Test 4.2: Search-based discovery workflow

print("\n" + "="*60)
print("SEARCH-BASED DISCOVERY WORKFLOW")
print("="*60)

# Search for tables with common pattern
table_results = client.schema.search_tables("a", limit=5)
print(f"\nTable search (pattern='a', limit=5): {len(table_results)} results")
if table_results:
    print("\nFound tables:")
    for r in table_results[:3]:
        print(f"  - {r.catalog_name}.{r.schema_name}.{r.table_name}")
        print(f"    Type: {r.table_type}, Columns: {r.column_count}")
    if len(table_results) > 3:
        print(f"  ... and {len(table_results) - 3} more tables")

# Search for columns with common pattern
column_results = client.schema.search_columns("a", limit=5)
print(f"\nColumn search (pattern='a', limit=5): {len(column_results)} results")
if column_results:
    print("\nFound columns:")
    for r in column_results[:3]:
        print(f"  - {r.catalog_name}.{r.schema_name}.{r.table_name}.{r.column_name}")
        print(f"    Type: {r.data_type}")
    if len(column_results) > 3:
        print(f"  ... and {len(column_results) - 3} more columns")

print("\n" + "="*60)
print("Test 4.2 PASSED: Search-based discovery workflow")
print("="*60)
```

<div class="nb-section">
  <span class="nb-section__number">6</span>
  <div>
    <h2 class="nb-section__title">Performance Validation</h2>
    <p class="nb-section__description">Verify cache operations are fast.</p>
  </div>
</div>

```python
# Test 5.1: Verify cache operations are fast

print("Cache performance validation:")

# Test catalog listing performance
start = time.time()
catalogs = client.schema.list_catalogs()
duration_ms = (time.time() - start) * 1000

print(f"\n  List catalogs: {duration_ms:.2f}ms")
assert duration_ms < 1000, f"Too slow: {duration_ms}ms (expected < 1000ms)"

# Test search performance
start = time.time()
results = client.schema.search_tables("test", limit=10)
duration_ms = (time.time() - start) * 1000

print(f"  Search tables: {duration_ms:.2f}ms")
assert duration_ms < 1000, f"Too slow: {duration_ms}ms (expected < 1000ms)"

print("\nAll cache operations completed within performance threshold")
print("\nTest 5.1 PASSED: Cache performance")
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li>All exploring schemas tests validated</li>
    <li>Resources cleaned up automatically via test context</li>
    <li>Zero residual state on the cluster</li>
  </ul>
</div>

```python
# No resources to cleanup - this test is read-only
ctx.teardown()
client.close()

print("\n" + "="*60)
print("SCHEMA METADATA E2E TESTS COMPLETED!")
print("="*60)

print("\nAll tests passed:")
print("\n  Section 1: Basic Listing Operations")
print("    1.1 List catalogs")
print("    1.2 Error handling for missing catalog (NotFoundError)")
print("    1.3 Error handling for missing schema (NotFoundError)")
print("    1.4 Error handling for missing table (NotFoundError)")

print("\n  Section 2: Search Operations")
print("    2.1 Search tables with pattern and limit")
print("    2.2 Search columns with pattern and limit")

print("\n  Section 3: Admin Operations")
print("    3.1 Permission checks (ForbiddenError for regular users)")
print("    3.2 Get cache statistics (admin)")
print("    3.3 Trigger cache refresh (admin)")

print("\n  Section 4: Complete Workflows")
print("    4.1 Complete catalog browsing workflow")
print("    4.2 Search-based discovery workflow")

print("\n  Section 5: Performance Validation")
print("    5.1 Cache performance (< 1000ms)")

print("\nSchema metadata tests completed.")
```
