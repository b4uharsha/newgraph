---
title: "API Specification: Starburst Schema Browser"
scope: hsbc
---

# API Specification: Starburst Schema Browser

## Overview

Endpoints for browsing Starburst schema metadata and validating SQL queries. Used by the SDK to provide schema discovery and SQL validation for mapping creation.

## Prerequisites

- [api.common.spec.md](--/api.common.spec.md) - API conventions, authentication, error handling
- [architectural.guardrails.md](--/--/foundation/architectural.guardrails.md) - Constraints

## Base URL

```
https://{domain}/api
```

---

## Cache vs Real-Time

These endpoints use a **hybrid approach**:

| Endpoint | Data Source | Use Case |
|----------|-------------|----------|
| `GET /starburst/catalogs` | **Cache** | Schema browser dropdown |
| `GET /starburst/schemas` | **Cache** | Schema browser tree |
| `GET /starburst/tables` | **Cache** | Schema browser tree |
| `GET /starburst/columns` | **Cache** | Table column display |
| `POST /starburst/parse-sql` | **Real-time** | Infer mapping from SQL on submit |
| `POST /starburst/validate` | **Real-time** | Validate SQL on save/submit |

**Cache Architecture:**

- Schema metadata (catalogs, schemas, tables, columns) is stored in the Control Plane database
- Cache is scoped to admin-configured "allowed schemas" (see ADR-012)
- Refresh triggers: scheduled job (24h), manual Ops trigger, config change
- SQL validation requires real-time Starburst call

**Why Cache?**

1. **Performance**: Schema browser loads instantly from cache vs 300-800ms per Starburst query
2. **Security**: Only allowed schemas are cached and exposed to users
3. **Reliability**: UI works even if Starburst is temporarily unavailable
4. **Cost**: Reduces load on Starburst cluster

---

## Schema Browser Endpoints (Cached)

### List Catalogs

```
GET /starburst/catalogs
```

Returns cached catalog list (filtered to allowed catalogs). Used by UI for dropdown population.

**Response: 200 OK**

```json
{
  "data": {
    "catalogs": ["analytics", "raw_data", "reporting"],
    "cached_at": "2025-01-15T06:00:00Z"
  },
  "meta": {
    "request_id": "req-uuid"
  }
}
```

---

### List Schemas

```
GET /starburst/schemas
```

Returns cached schemas for a catalog (filtered to allowed schemas).

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| catalog | string | Yes | Catalog name |

**Response: 200 OK**

```json
{
  "data": {
    "catalog": "analytics",
    "schemas": ["customer", "product", "transactions"],
    "cached_at": "2025-01-15T06:00:00Z"
  },
  "meta": {
    "request_id": "req-uuid"
  }
}
```

---

### List Tables

```
GET /starburst/tables
```

Returns cached tables for a schema.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| catalog | string | Yes | Catalog name |
| schema | string | Yes | Schema name |

**Response: 200 OK**

```json
{
  "data": {
    "catalog": "analytics",
    "schema": "customer",
    "tables": ["customers", "addresses", "preferences"],
    "cached_at": "2025-01-15T06:00:00Z"
  },
  "meta": {
    "request_id": "req-uuid"
  }
}
```

---

### Get Table Columns

```
GET /starburst/columns
```

Returns cached column metadata for a table.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| catalog | string | Yes | Catalog name |
| schema | string | Yes | Schema name |
| table | string | Yes | Table name |

**Response: 200 OK**

```json
{
  "data": {
    "catalog": "analytics",
    "schema": "customer",
    "table": "customers",
    "columns": [
      {"name": "customer_id", "type": "VARCHAR", "nullable": false},
      {"name": "name", "type": "VARCHAR", "nullable": true},
      {"name": "city", "type": "VARCHAR", "nullable": true},
      {"name": "created_at", "type": "TIMESTAMP", "nullable": false}
    ],
    "cached_at": "2025-01-15T06:00:00Z"
  },
  "meta": {
    "request_id": "req-uuid"
  }
}
```

---

## SQL Validation Endpoints (Real-Time)

### Parse SQL to Mapping

```
POST /starburst/parse-sql
```

**⚠️ Real-time Starburst call** - This endpoint queries Starburst in real-time to analyze SQL and infer column types.

Analyzes SQL queries and generates node/edge definition suggestions.

**Request Body:**

```json
{
  "node_queries": [
    "SELECT customer_id, name, city FROM analytics.customers",
    "SELECT product_id, name, category FROM analytics.products"
  ],
  "edge_queries": [
    "SELECT customer_id, product_id, amount, purchase_date FROM analytics.transactions"
  ]
}
```

**Response: 200 OK**

```json
{
  "data": {
    "node_definitions": [
      {
        "label": "customers",
        "sql": "SELECT customer_id, name, city FROM analytics.customers",
        "primary_key": {"name": "customer_id", "type": "STRING"},
        "properties": [
          {"name": "name", "type": "STRING"},
          {"name": "city", "type": "STRING"}
        ],
        "inferred": true
      }
    ],
    "edge_definitions": [
      {
        "type": "transactions",
        "sql": "SELECT customer_id, product_id, amount, purchase_date FROM analytics.transactions",
        "from_key": "customer_id",
        "to_key": "product_id",
        "from_node": null,
        "to_node": null,
        "properties": [
          {"name": "amount", "type": "DOUBLE"},
          {"name": "purchase_date", "type": "DATE"}
        ],
        "inferred": true,
        "warnings": ["from_node and to_node must be set manually"]
      }
    ],
    "warnings": [
      "Edge 'transactions' requires from_node and to_node to be specified"
    ]
  },
  "meta": {
    "request_id": "req-uuid"
  }
}
```

---

### Validate SQL Query

```
POST /starburst/validate
```

**⚠️ Real-time Starburst call** - This endpoint queries Starburst in real-time to validate SQL syntax and check table/column existence. Used when saving/submitting mappings, not for real-time typing validation.

Validates SQL syntax and checks table/column existence.

**Request Body:**

```json
{
  "sql": "SELECT customer_id, name, city FROM analytics.customers WHERE created_at > '2025-01-01'"
}
```

**Response: 200 OK (Valid)**

```json
{
  "data": {
    "valid": true,
    "columns": [
      {"name": "customer_id", "type": "VARCHAR"},
      {"name": "name", "type": "VARCHAR"},
      {"name": "city", "type": "VARCHAR"}
    ]
  },
  "meta": {
    "request_id": "req-uuid"
  }
}
```

**Response: 200 OK (Invalid)**

```json
{
  "data": {
    "valid": false,
    "error": "Column 'invalid_column' not found in table 'analytics.customers'",
    "position": 25
  },
  "meta": {
    "request_id": "req-uuid"
  }
}
```

---

## Error Handling

| Code | HTTP Status | Description |
|------|-------------|-------------|
| VALIDATION_FAILED | 400 | Invalid request body |
| UNAUTHORIZED | 401 | Missing or invalid authentication |
| PERMISSION_DENIED | 403 | User not authorized for catalog/schema |
| RESOURCE_NOT_FOUND | 404 | Catalog, schema, or table not found in cache |
| STARBURST_ERROR | 500 | Starburst connection/query error (real-time endpoints only) |
| SERVICE_UNAVAILABLE | 503 | Starburst unreachable (real-time endpoints only) |

---

## Open Questions

See [decision.log.md](--/--/process/decision.log.md) for consolidated open questions and architecture decision records.
