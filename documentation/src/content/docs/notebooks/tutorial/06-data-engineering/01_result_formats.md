---
title: "Result Formats"
---

<div class="nb-header">
  <span class="nb-header__type">Tutorial</span>
  <h1 class="nb-header__title">Result Formats</h1>
  <p class="nb-header__subtitle">Convert query results to DataFrames, CSV, Parquet, and more</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">25 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--intermediate">
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
      </span>
      Intermediate
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">QueryResult</span><span class="nb-header__tag">Polars</span><span class="nb-header__tag">Pandas</span><span class="nb-header__tag">Export</span><span class="nb-header__tag">DataFrame</span></div>
</div>

<div class="nb-objectives">
  <h3 class="nb-objectives__title">What You'll Learn</h3>
  <ul class="nb-objectives__list">
    <li><strong>Query Methods</strong> - Choose between query, query_df, query_scalar, and query_one</li>
    <li><strong>Result Metadata</strong> - Inspect columns, types, row counts, and execution time</li>
    <li><strong>DataFrame Conversion</strong> - Convert results to Polars and Pandas DataFrames</li>
    <li><strong>File Export</strong> - Save results as CSV and Parquet files</li>
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

from notebook_setup import provision
personas, conn = provision(USERNAME)
analyst = personas["analyst"]

print(f"Connected | {conn.query_scalar('MATCH (n) RETURN count(n)')} nodes")
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Choosing the Right Query Method</h2>
    <p class="nb-section__description">Compare query, query_df, query_scalar, and query_one</p>
  </div>
</div>

```python
# query() returns a full QueryResult with metadata and conversion methods
result = conn.query("MATCH (c:Customer) RETURN c.id AS id, c.id AS name LIMIT 5")
print(f"query()       -> {type(result).__name__}  ({result.row_count} rows)")

# query_df() returns a DataFrame directly (polars by default)
df = conn.query_df("MATCH (c:Customer) RETURN c.id AS id, c.id AS name LIMIT 5")
print(f"query_df()    -> {type(df).__name__}  ({len(df)} rows)")

# query_scalar() returns a single value
count = conn.query_scalar("MATCH (n) RETURN count(n)")
print(f"query_scalar() -> {type(count).__name__}  (value={count})")

# query_one() returns a single row as a dict, or None
row = conn.query_one("MATCH (c:Customer) RETURN c.id AS id, c.id AS name LIMIT 1")
print(f"query_one()   -> {type(row).__name__}  (keys={list(row.keys())})")
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">QueryResult Metadata</h2>
    <p class="nb-section__description">Inspect columns, types, row counts, and execution time</p>
  </div>
</div>

```python
# Run a query and inspect the result metadata
result = conn.query(
    "MATCH (c:Customer) RETURN c.id AS id, c.id AS name, c.bk_sectr AS sector LIMIT 10"
)

print(f"Columns:        {result.columns}")
print(f"Column types:   {result.column_types}")
print(f"Row count:      {result.row_count}")
print(f"Execution time: {result.execution_time_ms} ms")
print(f"Length (len()): {len(result)}")
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">DataFrame Conversion</h2>
    <p class="nb-section__description">Convert results to Polars and Pandas DataFrames</p>
  </div>
</div>

```python
# Convert QueryResult to a Polars DataFrame
polars_df = result.to_polars()
print("=== to_polars() ===")
print(f"Type: {type(polars_df).__module__}.{type(polars_df).__name__}")
print(polars_df)

# Convert QueryResult to a Pandas DataFrame
pandas_df = result.to_pandas()
print("\n=== to_pandas() ===")
print(f"Type: {type(pandas_df).__module__}.{type(pandas_df).__name__}")
print(pandas_df.head())
```

```python
# query_df() with explicit backend selection
cypher = "MATCH (c:Customer) RETURN c.id AS id, c.id AS name LIMIT 5"

# Polars backend (default)
df_polars = conn.query_df(cypher, backend="polars")
print(f"backend='polars' -> {type(df_polars).__module__}.{type(df_polars).__name__}")

# Pandas backend
df_pandas = conn.query_df(cypher, backend="pandas")
print(f"backend='pandas' -> {type(df_pandas).__module__}.{type(df_pandas).__name__}")
```

<div class="nb-section">
  <span class="nb-section__number">5</span>
  <div>
    <h2 class="nb-section__title">Dictionary Access</h2>
    <p class="nb-section__description">Iterate rows, convert to dicts, and extract scalars</p>
  </div>
</div>

```python
result = conn.query(
    "MATCH (c:Customer) RETURN c.id AS id, c.id AS name LIMIT 3"
)

# Iterate rows as dicts
print("=== Iteration (for row in result) ===")
for row in result:
    print(f"  {row}")

# to_dicts() returns a list of dicts
print(f"\n=== to_dicts() ===")
dicts = result.to_dicts()
print(f"  Type: {type(dicts).__name__}, length: {len(dicts)}")
print(f"  First: {dicts[0]}")
print(f"  Third: {dicts[2]}")

# scalar() extracts a single value from a single-column, single-row result
count_result = conn.query("MATCH (n) RETURN count(n) AS total")
print(f"\n=== scalar() ===")
print(f"  count_result.scalar() = {count_result.scalar()}")
```

<div class="nb-section">
  <span class="nb-section__number">6</span>
  <div>
    <h2 class="nb-section__title">File Export</h2>
    <p class="nb-section__description">Save query results as CSV and Parquet files</p>
  </div>
</div>

```python
import os

# Query customer data for export
result = conn.query(
    "MATCH (c:Customer) RETURN c.id AS id, c.id AS name, c.bk_sectr AS sector LIMIT 100"
)

# Export to CSV
csv_path = "/tmp/customers_export.csv"
result.to_csv(csv_path)
csv_size = os.path.getsize(csv_path)
print(f"Exported CSV:     {csv_path} ({csv_size:,} bytes)")

# Export to Parquet
parquet_path = "/tmp/customers_export.parquet"
result.to_parquet(parquet_path)
parquet_size = os.path.getsize(parquet_path)
print(f"Exported Parquet: {parquet_path} ({parquet_size:,} bytes)")

print(f"\nCompression ratio: {csv_size / parquet_size:.1f}x (CSV/Parquet)")
```

<div class="nb-section">
  <span class="nb-section__number">7</span>
  <div>
    <h2 class="nb-section__title">Display</h2>
    <p class="nb-section__description">Auto-formatted Jupyter output with result.show()</p>
  </div>
</div>

```python
# show() renders an auto-formatted table in Jupyter
result = conn.query(
    "MATCH (c:Customer) RETURN c.id AS id, c.id AS name, c.bk_sectr AS sector LIMIT 5"
)
result.show()
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li>Use <code>query()</code> for full control over results, <code>query_df()</code> to go straight to a DataFrame</li>
    <li><code>query_scalar()</code> and <code>query_one()</code> are shortcuts for single-value and single-row results</li>
    <li>QueryResult exposes <code>columns</code>, <code>column_types</code>, <code>row_count</code>, and <code>execution_time_ms</code> for metadata inspection</li>
    <li><code>to_polars()</code> and <code>to_pandas()</code> convert results into DataFrames for analysis</li>
    <li><code>to_csv()</code> and <code>to_parquet()</code> export results directly to files -- Parquet is significantly smaller</li>
    <li><code>show()</code> provides auto-formatted display in Jupyter notebooks</li>
  </ul>
</div>
