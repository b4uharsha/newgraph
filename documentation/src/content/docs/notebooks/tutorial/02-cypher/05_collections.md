---
title: "Collections"
---

<div class="nb-header">
  <span class="nb-header__type">Tutorial</span>
  <h1 class="nb-header__title">Collections</h1>
  <p class="nb-header__subtitle">Lists, UNWIND, and collection functions</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">30 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--intermediate">
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
      </span>
      Intermediate
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">Cypher</span><span class="nb-header__tag">Lists</span><span class="nb-header__tag">UNWIND</span></div>
</div>

<div class="nb-objectives">
  <h3 class="nb-objectives__title">What You'll Learn</h3>
  <ul class="nb-objectives__list">
    <li><strong>List Creation</strong> - Create and manipulate lists</li>
    <li><strong>UNWIND</strong> - Expand lists to rows</li>
    <li><strong>List Functions</strong> - Filter, map, reduce</li>
    <li><strong>List Comprehensions</strong> - Compact list operations</li>
  </ul>
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

print(f"Connected | {conn.query_scalar('MATCH (n) RETURN count(n)')} nodes")
```

<div class="nb-callout nb-callout--info">
  <span class="nb-sr-only">Info:</span>
  <span class="nb-callout__icon" aria-hidden="true"></span>
  <div class="nb-callout__content">
    <div class="nb-callout__title">Prerequisites</div>
    <div class="nb-callout__body">Complete G1_property_graphs before this tutorial.</div>
  </div>
</div>

Cypher has first-class support for **lists** (ordered collections) and **maps** (key-value pairs).
You can build lists from literal values, or aggregate query results into lists with `COLLECT()`.

**List literals** are written with square brackets:

```cypher
RETURN [1, 2, 3] AS numbers
RETURN ['alice', 'bob'] AS names
```

**`COLLECT()`** aggregates values from multiple rows into a single list -- it is the list equivalent of `COUNT()` or `SUM()`:

```cypher
MATCH (p:Person) RETURN COLLECT(p.name) AS all_names
```

**Maps** are key-value structures written with curly braces:

```cypher
RETURN {name: 'Alice', age: 30} AS person_map
```

Every node's properties are internally stored as a map.  You can extract them with `properties(n)`.

```python
# --- List literals ---
result = conn.query("RETURN [1, 2, 3] AS numbers, ['a', 'b', 'c'] AS letters")
result.show()
```

```python
# --- COLLECT() aggregates values into a list ---
df = conn.query_df("MATCH (n) RETURN labels(n)[0] AS label, COLLECT(n.name) AS names LIMIT 5")
df
```

```python
# --- Map literals and node properties ---
result = conn.query("RETURN {name: 'Alice', role: 'Engineer'} AS map_literal")
result.show()
```

```python
# --- Extract property maps from nodes ---
# properties(n) returns all properties as a map; keys(n) returns the property names
df = conn.query_df("MATCH (n) RETURN keys(n) AS property_keys, properties(n) AS props LIMIT 3")
df
```

`UNWIND` is the inverse of `COLLECT()` -- it takes a list and expands each element into its own row.
This is essential when you need to process list elements individually, or when you want to pass a
list of values into a query as parameters.

**Basic pattern:**

```cypher
UNWIND [1, 2, 3] AS num
RETURN num
```

This produces three rows, one for each element.

**Common use case** -- feed a list of lookup values into a `MATCH`:

```cypher
UNWIND ['Alice', 'Bob'] AS name
MATCH (p:Person {name: name})
RETURN p
```

**Round-trip** -- `COLLECT` then `UNWIND` lets you aggregate, filter, and re-expand:

```cypher
MATCH (p:Person)-[:WORKS_AT]->(c:Company)
WITH c, COLLECT(p.name) AS employees
WHERE size(employees) > 2
UNWIND employees AS emp
RETURN c.name, emp
```

```python
# --- UNWIND expands a list into individual rows ---
df = conn.query_df("UNWIND [10, 20, 30] AS value RETURN value, value * 2 AS doubled")
df
```

```python
# --- UNWIND with MATCH: look up nodes from a list ---
df = conn.query_df("""
    UNWIND ['Person', 'Company'] AS lbl
    MATCH (n)
    WHERE lbl IN labels(n)
    RETURN lbl, count(n) AS count
""")
df
```

```python
# --- Round-trip: COLLECT then UNWIND ---
df = conn.query_df("""
    MATCH (n)
    WITH labels(n)[0] AS label, COLLECT(n.name) AS names
    WHERE size(names) >= 2
    UNWIND names AS name
    RETURN label, name
    LIMIT 10
""")
df
```

Cypher provides a rich set of built-in functions for working with lists:

| Function | Description | Example |
|----------|-------------|---------|
| `size(list)` | Number of elements | `size([1,2,3])` => 3 |
| `head(list)` | First element | `head([1,2,3])` => 1 |
| `tail(list)` | All elements except the first | `tail([1,2,3])` => [2,3] |
| `last(list)` | Last element | `last([1,2,3])` => 3 |
| `range(start, end)` | Generate integer sequence | `range(0, 4)` => [0,1,2,3,4] |
| `reverse(list)` | Reverse order | `reverse([1,2,3])` => [3,2,1] |
| `list[idx]` | Index access (0-based) | `[10,20,30][1]` => 20 |
| `list[-1]` | Negative index (from end) | `[10,20,30][-1]` => 30 |
| `list[start..end]` | Slice (exclusive end) | `[10,20,30,40][1..3]` => [20,30] |

You can also check membership with `IN`:

```cypher
RETURN 2 IN [1, 2, 3] AS found
```

```python
# --- Basic list functions ---
df = conn.query_df("""
    WITH [10, 20, 30, 40, 50] AS nums
    RETURN
        size(nums)    AS length,
        head(nums)    AS first,
        last(nums)    AS last_elem,
        tail(nums)    AS all_but_first,
        reverse(nums) AS reversed
""")
df
```

```python
# --- Indexing, slicing, and range() ---
df = conn.query_df("""
    WITH [10, 20, 30, 40, 50] AS nums
    RETURN
        nums[0]    AS first_by_index,
        nums[-1]   AS last_by_index,
        nums[1..3] AS slice_1_to_3,
        range(0, 4) AS generated_range
""")
df
```

```python
# --- Membership test with IN ---
df = conn.query_df("""
    WITH ['Alice', 'Bob', 'Carol'] AS team
    RETURN
        'Alice' IN team AS alice_present,
        'Dave'  IN team AS dave_present
""")
df
```

**List comprehensions** let you filter and transform lists in a single expression, similar to
Python's `[x for x in list if condition]`.

The Cypher syntax is:

```cypher
[variable IN list WHERE predicate | expression]
```

- The `WHERE` clause is optional (omit it to transform all elements).
- The `| expression` part is optional (omit it to just filter).
- You can use both together to filter AND transform.

**Examples:**

```cypher
// Filter: keep only values greater than 2
RETURN [x IN [1,2,3,4,5] WHERE x > 2] AS filtered
// => [3, 4, 5]

// Transform: double every value
RETURN [x IN [1,2,3] | x * 2] AS doubled
// => [2, 4, 6]

// Filter + transform: square values greater than 2
RETURN [x IN [1,2,3,4,5] WHERE x > 2 | x * x] AS filtered_and_squared
// => [9, 16, 25]
```

List comprehensions are especially powerful when combined with `COLLECT()` results from a query.

```python
# --- Filter: keep only even numbers ---
result = conn.query("RETURN [x IN range(1, 10) WHERE x % 2 = 0] AS evens")
result.show()
```

```python
# --- Transform: square each value ---
result = conn.query("RETURN [x IN [1, 2, 3, 4, 5] | x * x] AS squares")
result.show()
```

```python
# --- Filter + transform on real data ---
# Collect node names, then keep only those starting with a specific letter
df = conn.query_df("""
    MATCH (n)
    WITH COLLECT(DISTINCT n.name) AS all_names
    RETURN
        size(all_names) AS total,
        [name IN all_names WHERE name STARTS WITH 'A'] AS a_names
""")
df
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li>Lists created with [1,2,3] or COLLECT()</li>
    <li>UNWIND expands lists to individual rows</li>
    <li>List functions: head(), tail(), size(), range()</li>
    <li>Comprehensions: [x IN list WHERE cond | expr]</li>
  </ul>
</div>
