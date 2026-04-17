---
title: "Appendix C: Cypher Quick Reference"
scope: hsbc
---

# Appendix C: Cypher Quick Reference

This appendix provides a quick reference for common Cypher patterns used with the Graph OLAP SDK. Cypher is the query language used to interact with graph instances.

## Overview

Cypher is a declarative graph query language that allows expressive and efficient pattern matching in property graphs. The SDK uses Cypher for all graph queries executed through the `InstanceConnection.query()` method.

## Basic Query Structure

```cypher
MATCH (pattern)           // Find matching patterns
WHERE condition           // Filter results
WITH variables            // Chain query parts
RETURN expression         // Return results
ORDER BY field            // Sort results
LIMIT n                   // Limit result count
```

## Node Patterns

### Match All Nodes

```cypher
// All nodes
MATCH (n) RETURN n LIMIT 100

// Nodes with specific label
MATCH (c:Customer) RETURN c LIMIT 100

// Multiple labels
MATCH (n:Customer:Premium) RETURN n LIMIT 100
```

### Match by Property

```cypher
// Exact match
MATCH (c:Customer {name: 'Acme Corp'}) RETURN c

// With WHERE clause
MATCH (c:Customer)
WHERE c.status = 'active'
RETURN c

// Multiple conditions
MATCH (c:Customer)
WHERE c.status = 'active' AND c.created_date > date('2024-01-01')
RETURN c
```

### Match by ID

```cypher
// Using internal node ID
MATCH (n) WHERE id(n) = 123 RETURN n

// Using offset (for algorithm results)
MATCH (n:Customer) WHERE offset(id(n)) = 42 RETURN n
```

## Relationship Patterns

### Basic Relationships

```cypher
// Any direction
MATCH (a:Customer)-[r]-(b:Customer) RETURN a, r, b

// Specific direction
MATCH (a:Customer)-[r]->(b:Customer) RETURN a, r, b

// Specific relationship type
MATCH (a:Customer)-[r:KNOWS]->(b:Customer) RETURN a, r, b

// Multiple relationship types
MATCH (a)-[r:KNOWS|WORKS_WITH]->(b) RETURN a, r, b
```

### Variable-Length Paths

```cypher
// Path of length 1 to 3
MATCH (a:Customer)-[*1..3]->(b:Customer) RETURN a, b

// Path of any length
MATCH (a:Customer)-[*]->(b:Customer) RETURN a, b

// Shortest path
MATCH p = shortestPath((a:Customer)-[*]-(b:Customer))
WHERE a.name = 'Acme' AND b.name = 'Beta'
RETURN p
```

### Path Patterns

```cypher
// Capture path as variable
MATCH p = (a:Customer)-[:KNOWS*1..5]->(b:Customer)
RETURN p, length(p) as path_length

// Extract nodes from path
MATCH p = (a)-[*1..3]->(b)
RETURN nodes(p), relationships(p)
```

## Aggregation Functions

### Count

```cypher
// Total count
MATCH (n:Customer) RETURN count(n)

// Count distinct
MATCH (c:Customer)-[:PURCHASED]->(p:Product)
RETURN count(DISTINCT p)

// Count by group
MATCH (c:Customer)-[:PURCHASED]->(p:Product)
RETURN p.category, count(*) as purchase_count
ORDER BY purchase_count DESC
```

### Statistical Aggregations

```cypher
// Sum, average, min, max
MATCH (c:Customer)
RETURN
    sum(c.total_purchases) as total,
    avg(c.total_purchases) as average,
    min(c.total_purchases) as minimum,
    max(c.total_purchases) as maximum

// Standard deviation
MATCH (c:Customer)
RETURN stdev(c.total_purchases) as std_dev
```

### Collect and Lists

```cypher
// Collect into list
MATCH (c:Customer)-[:PURCHASED]->(p:Product)
RETURN c.name, collect(p.name) as products

// Collect with limit
MATCH (c:Customer)-[:PURCHASED]->(p:Product)
RETURN c.name, collect(p.name)[0..5] as top_products
```

## Working with Properties

### Accessing Properties

```cypher
// Single property
MATCH (c:Customer) RETURN c.name

// Multiple properties
MATCH (c:Customer) RETURN c.name, c.email, c.status

// All properties as map
MATCH (c:Customer) RETURN properties(c)
```

### Property Existence

```cypher
// Check property exists
MATCH (c:Customer)
WHERE c.email IS NOT NULL
RETURN c

// Check property doesn't exist
MATCH (c:Customer)
WHERE c.phone IS NULL
RETURN c
```

### Property Operations

```cypher
// String operations
MATCH (c:Customer)
WHERE c.name STARTS WITH 'A'
RETURN c

WHERE c.name ENDS WITH 'Corp'
WHERE c.name CONTAINS 'Tech'
WHERE c.name =~ '.*pattern.*'  // Regex

// Numeric operations
MATCH (c:Customer)
WHERE c.total_purchases > 1000
  AND c.total_purchases <= 10000
RETURN c

// List operations
MATCH (c:Customer)
WHERE c.status IN ['active', 'pending']
RETURN c
```

## Working with Algorithm Results

After running algorithms, results are stored as node properties. Here's how to query them:

### Query Algorithm Results

```cypher
// PageRank scores
MATCH (c:Customer)
WHERE c.pagerank_score IS NOT NULL
RETURN c.name, c.pagerank_score
ORDER BY c.pagerank_score DESC
LIMIT 10

// Community detection results
MATCH (c:Customer)
WHERE c.community_id IS NOT NULL
RETURN c.community_id, count(*) as size
ORDER BY size DESC

// K-Core results
MATCH (c:Customer)
WHERE c.kcore_degree >= 5
RETURN c.name, c.kcore_degree
```

### Combine Algorithm Results

```cypher
// High PageRank in large communities
MATCH (c:Customer)
WHERE c.pagerank_score > 0.01
WITH c.community_id as community, count(*) as size
WHERE size > 100
MATCH (c2:Customer)
WHERE c2.community_id = community AND c2.pagerank_score > 0.01
RETURN c2.name, c2.pagerank_score, community, size
ORDER BY c2.pagerank_score DESC
```

### Find Central Nodes

```cypher
// Top nodes by betweenness centrality
MATCH (c:Customer)
WHERE c.betweenness IS NOT NULL
RETURN c.name, c.betweenness
ORDER BY c.betweenness DESC
LIMIT 20

// Nodes connecting different communities
MATCH (a:Customer)-[r]-(b:Customer)
WHERE a.community_id <> b.community_id
RETURN a.name, a.community_id,
       b.name, b.community_id
LIMIT 50
```

## Path Analysis

### Find Connections

```cypher
// Direct connections
MATCH (a:Customer {name: 'Acme'})-[r]->(b)
RETURN type(r), b.name

// Two-hop connections
MATCH (a:Customer {name: 'Acme'})-[r1]->(intermediate)-[r2]->(b)
RETURN intermediate.name, b.name

// All paths up to length 4
MATCH p = (a:Customer {name: 'Acme'})-[*1..4]-(b:Customer {name: 'Beta'})
RETURN p, length(p)
ORDER BY length(p)
```

### Shortest Path Queries

```cypher
// Single shortest path
MATCH p = shortestPath(
    (a:Customer {name: 'Acme'})-[*]-(b:Customer {name: 'Beta'})
)
RETURN p, length(p)

// All shortest paths
MATCH p = allShortestPaths(
    (a:Customer {name: 'Acme'})-[*]-(b:Customer {name: 'Beta'})
)
RETURN p, length(p)
```

## Subgraph Queries

### Extract Subgraph

```cypher
// Ego network (1-hop neighborhood)
MATCH (center:Customer {name: 'Acme'})-[r]-(neighbor)
RETURN center, r, neighbor

// Extended ego network (2-hops)
MATCH (center:Customer {name: 'Acme'})-[r1]-(n1)-[r2]-(n2)
RETURN center, n1, n2, r1, r2
```

### Community Subgraph

```cypher
// All nodes and edges in a community
MATCH (a:Customer)-[r]-(b:Customer)
WHERE a.community_id = 5 AND b.community_id = 5
RETURN a, r, b
```

## Result Formatting

### Return as Table

```cypher
// Named columns
MATCH (c:Customer)
RETURN
    c.name AS customer_name,
    c.status AS status,
    c.total_purchases AS purchases
ORDER BY purchases DESC
LIMIT 10
```

### Return as Maps

```cypher
// Return as map
MATCH (c:Customer)
RETURN {
    name: c.name,
    status: c.status,
    purchases: c.total_purchases
} AS customer_data
```

### Distinct Results

```cypher
// Remove duplicates
MATCH (c:Customer)-[:PURCHASED]->(p:Product)
RETURN DISTINCT p.category

// Distinct with ordering
MATCH (c:Customer)-[:PURCHASED]->(p:Product)
RETURN DISTINCT p.category
ORDER BY p.category
```

## SDK Query Examples

### Basic Query

```python
# Execute Cypher query
result = conn.query("MATCH (n:Customer) RETURN count(n) as total")
print(result.rows)  # [[1000]]

# With parameters
result = conn.query(
    "MATCH (c:Customer) WHERE c.status = $status RETURN c.name",
    {"status": "active"}
)
```

### Convert to DataFrame

```python
# Query with column names
result = conn.query("""
    MATCH (c:Customer)
    RETURN c.name AS name, c.status AS status, c.total_purchases AS purchases
    ORDER BY purchases DESC
    LIMIT 100
""")

# Convert to Polars DataFrame
df = result.to_polars()
print(df.head())

# Convert to Pandas DataFrame
df_pandas = result.to_pandas()
```

### Handle Large Results

```python
# Use LIMIT for large datasets
result = conn.query("""
    MATCH (c:Customer)
    RETURN c.name, c.pagerank_score
    ORDER BY c.pagerank_score DESC
    LIMIT 1000
""")

# Paginated queries
def fetch_paginated(conn, page_size=1000):
    offset = 0
    while True:
        result = conn.query(f"""
            MATCH (c:Customer)
            RETURN c.name
            ORDER BY c.name
            SKIP {offset}
            LIMIT {page_size}
        """)
        if not result.rows:
            break
        yield result.rows
        offset += page_size
```

## Performance Tips

### Use Indexes

For large graphs, ensure properties used in WHERE clauses are indexed:

```cypher
-- Indexed lookups are faster
MATCH (c:Customer)
WHERE c.customer_id = '12345'  -- If customer_id is indexed
RETURN c
```

### Limit Early

Apply LIMIT as early as possible:

```cypher
-- Better: limit early
MATCH (c:Customer)
WHERE c.status = 'active'
WITH c LIMIT 100
MATCH (c)-[:PURCHASED]->(p:Product)
RETURN c.name, collect(p.name)

-- Worse: limit late
MATCH (c:Customer)-[:PURCHASED]->(p:Product)
WHERE c.status = 'active'
RETURN c.name, collect(p.name)
LIMIT 100
```

### Avoid Cartesian Products

Be explicit about relationships:

```cypher
-- Bad: creates cartesian product
MATCH (a:Customer), (b:Product)
RETURN a, b

-- Good: explicit relationship
MATCH (a:Customer)-[:PURCHASED]->(b:Product)
RETURN a, b
```

### Use WITH for Chaining

Break complex queries into stages:

```cypher
-- Chain with WITH
MATCH (c:Customer)
WHERE c.status = 'active'
WITH c, c.total_purchases as purchases
WHERE purchases > 1000
MATCH (c)-[:PURCHASED]->(p:Product)
WITH c, collect(DISTINCT p.category) as categories
WHERE size(categories) >= 3
RETURN c.name, categories
```

## See Also

- [Algorithm Reference](-/d-algorithm-reference.manual.md) - Available algorithms
- [Error Codes](-/b-error-codes.manual.md) - Error handling
- [SDK Quick Start](--/01-getting-started.manual.html) - Getting started
