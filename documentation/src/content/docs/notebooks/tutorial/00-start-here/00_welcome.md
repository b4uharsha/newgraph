---
title: "Welcome"
---

<div class="nb-header">
    <div class="nb-title">Welcome to Graph OLAP</div>
    <div class="nb-subtitle">Your journey into graph analytics starts here</div>
    <div class="nb-metadata">
        <span class="nb-duration">5 min</span>
        <span class="nb-difficulty nb-difficulty--beginner">Beginner</span>
    </div>
</div>

## What is Graph OLAP?

Graph OLAP is a platform for building, analyzing, and querying knowledge graphs from your data warehouse. It combines the power of graph databases with the familiarity of SQL-based analytics.

### Key Capabilities

| Feature | Description |
|---------|-------------|
| **Data Mapping** | Transform warehouse tables into graph structures |
| **Cypher Queries** | Query graphs with the intuitive Cypher language |
| **Graph Algorithms** | Run PageRank, community detection, pathfinding, and more |
| **Schema Evolution** | Version and diff your graph schemas |
| **Export** | Export results to CSV, Parquet, or back to your warehouse |

## Learning Paths

Choose your journey based on your role and goals:

### Data Analyst
Start with **1-sdk-fundamentals** to learn the SDK, then explore **2-cypher-language** for querying.

### Data Scientist
After the fundamentals, dive into **3-graph-algorithms** for centrality, community detection, and more.

### Platform Admin
Check out **4-administration** for user management and **5-operations** for platform config.

### Quick Reference
The **reference/** folder contains API documentation for all SDK components and algorithms.

## Folder Structure

```
00-start-here/          <- You are here
01-fundamentals/    <- Core SDK tutorials (8 notebooks)
02-cypher/     <- Cypher query tutorials (8 notebooks)
03-algorithms/    <- Algorithm tutorials (23 notebooks)
04-admin-ops/      <- Admin operations (2 notebooks)
04-admin-ops/          <- Platform ops (2 notebooks)
05-advanced/     <- Advanced features (5 notebooks)
reference/             <- API documentation
  sdk/                 <- SDK class reference (14 docs)
  algorithms/          <- Algorithm reference (28 docs)
use-cases/        <- E2E validation notebooks (19 tests)
```

## Next Step

Open **01_quick_start.ipynb** in this folder to create your first graph in under 5 minutes!
