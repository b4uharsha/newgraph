"""Schema metadata API router.

Provides REST endpoints for browsing Starburst schema metadata:
- List catalogs, schemas, tables, and columns
- Search tables and columns by name pattern
- Admin operations (manual refresh, cache stats)

All data served from in-memory cache (refreshed every 24h).
Performance: ~1μs for lookups, ~100μs for searches.
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status

from control_plane.dependencies import SchemaCacheDep
from control_plane.jobs.schema_cache import run_schema_cache_job
from control_plane.middleware.identity import CurrentUser, RequireAdmin
from control_plane.models.responses import (
    CacheStatsResponse,
    CatalogResponse,
    ColumnResponse,
    DataResponse,
    SchemaResponse,
    TableResponse,
)

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/schema", tags=["Schema Metadata"])


@router.get("/catalogs", response_model=DataResponse[list[CatalogResponse]])
async def list_catalogs(
    user: CurrentUser,
    cache: SchemaCacheDep,
) -> DataResponse[list[CatalogResponse]]:
    """
    List all cached Starburst catalogs.

    Returns all catalogs visible to the service account.
    Data is cached (refreshed every 24h).

    **Authentication:** Any authenticated user

    **Example:** `/api/schema/catalogs`

    **Performance:** ~1μs (in-memory lookup)
    """
    catalogs = cache.list_catalogs()
    cached_at = cache._last_refresh.isoformat() if cache._last_refresh else None

    response = [
        CatalogResponse(
            catalog_name=cat.name,
            schema_count=cat.schema_count,
            cached_at=cached_at,
        )
        for cat in catalogs
    ]

    return DataResponse(data=response)


@router.get(
    "/catalogs/{catalog_name}/schemas",
    response_model=DataResponse[list[SchemaResponse]],
)
async def list_schemas(
    user: CurrentUser,
    catalog_name: str,
    cache: SchemaCacheDep,
) -> DataResponse[list[SchemaResponse]]:
    """
    List all schemas in a catalog.

    **Authentication:** Any authenticated user

    **Example:** `/api/schema/catalogs/analytics/schemas`

    **Performance:** ~1μs
    """
    catalog = cache.get_catalog(catalog_name)
    if not catalog:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Catalog '{catalog_name}' not found in cache",
        )

    cached_at = cache._last_refresh.isoformat() if cache._last_refresh else None

    response = [
        SchemaResponse(
            catalog_name=catalog_name,
            schema_name=sch.name,
            table_count=sch.table_count,
            cached_at=cached_at,
        )
        for sch in catalog.schemas.values()
    ]

    return DataResponse(data=sorted(response, key=lambda x: x.schema_name))


@router.get(
    "/catalogs/{catalog_name}/schemas/{schema_name}/tables",
    response_model=DataResponse[list[TableResponse]],
)
async def list_tables(
    user: CurrentUser,
    catalog_name: str,
    schema_name: str,
    cache: SchemaCacheDep,
) -> DataResponse[list[TableResponse]]:
    """
    List all tables in a schema.

    **Authentication:** Any authenticated user

    **Example:** `/api/schema/catalogs/analytics/schemas/public/tables`

    **Performance:** ~1μs
    """
    schema = cache.get_schema(catalog_name, schema_name)
    if not schema:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schema '{catalog_name}.{schema_name}' not found in cache",
        )

    cached_at = cache._last_refresh.isoformat() if cache._last_refresh else None

    response = [
        TableResponse(
            catalog_name=catalog_name,
            schema_name=schema_name,
            table_name=tbl.name,
            table_type=tbl.table_type,
            column_count=tbl.column_count,
            cached_at=cached_at,
        )
        for tbl in schema.tables.values()
    ]

    return DataResponse(data=sorted(response, key=lambda x: x.table_name))


@router.get(
    "/catalogs/{catalog_name}/schemas/{schema_name}/tables/{table_name}/columns",
    response_model=DataResponse[list[ColumnResponse]],
)
async def list_columns(
    user: CurrentUser,
    catalog_name: str,
    schema_name: str,
    table_name: str,
    cache: SchemaCacheDep,
) -> DataResponse[list[ColumnResponse]]:
    """
    Get all columns for a table.

    **Authentication:** Any authenticated user

    **Example:** `/api/schema/catalogs/analytics/schemas/public/tables/users/columns`

    **Performance:** ~1μs
    """
    table = cache.get_table(catalog_name, schema_name, table_name)
    if not table:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Table '{catalog_name}.{schema_name}.{table_name}' not found in cache",
        )

    cached_at = cache._last_refresh.isoformat() if cache._last_refresh else None

    response = [
        ColumnResponse(
            catalog_name=catalog_name,
            schema_name=schema_name,
            table_name=table_name,
            column_name=col.name,
            data_type=col.data_type,
            is_nullable=col.is_nullable,
            ordinal_position=col.ordinal_position,
            column_default=col.column_default,
            cached_at=cached_at,
        )
        for col in table.columns
    ]

    return DataResponse(data=response)


@router.get("/search/tables", response_model=DataResponse[list[TableResponse]])
async def search_tables(
    user: CurrentUser,
    cache: SchemaCacheDep,
    q: Annotated[str, Query(min_length=1, description="Search pattern (prefix match)")],
    limit: Annotated[int, Query(ge=1, le=1000, description="Max results")] = 100,
) -> DataResponse[list[TableResponse]]:
    """
    Search tables by name pattern (prefix match, case-insensitive).

    **Authentication:** Any authenticated user

    **Query Parameters:**
    - `q`: Search pattern (e.g., "customer" matches "customers", "customer_orders")
    - `limit`: Maximum results (default: 100, max: 1000)

    **Example:** `/api/schema/search/tables?q=customer&limit=50`

    **Performance:** ~100μs for typical search
    """
    results = cache.search_tables(q, limit=limit)
    cached_at = cache._last_refresh.isoformat() if cache._last_refresh else None

    response = [
        TableResponse(
            catalog_name=cat,
            schema_name=sch,
            table_name=tbl_name,
            table_type=tbl.table_type,
            column_count=tbl.column_count,
            cached_at=cached_at,
        )
        for cat, sch, tbl_name, tbl in results
    ]

    return DataResponse(data=response)


@router.get("/search/columns", response_model=DataResponse[list[ColumnResponse]])
async def search_columns(
    user: CurrentUser,
    cache: SchemaCacheDep,
    q: Annotated[str, Query(min_length=1, description="Search pattern (prefix match)")],
    limit: Annotated[int, Query(ge=1, le=1000, description="Max results")] = 100,
) -> DataResponse[list[ColumnResponse]]:
    """
    Search columns by name pattern (prefix match, case-insensitive).

    **Authentication:** Any authenticated user

    **Query Parameters:**
    - `q`: Search pattern (e.g., "email" matches "email", "email_address")
    - `limit`: Maximum results (default: 100, max: 1000)

    **Example:** `/api/schema/search/columns?q=email&limit=50`

    **Performance:** ~100μs for typical search
    """
    results = cache.search_columns(q, limit=limit)
    cached_at = cache._last_refresh.isoformat() if cache._last_refresh else None

    response = [
        ColumnResponse(
            catalog_name=cat,
            schema_name=sch,
            table_name=tbl,
            column_name=col.name,
            data_type=col.data_type,
            is_nullable=col.is_nullable,
            ordinal_position=col.ordinal_position,
            column_default=col.column_default,
            cached_at=cached_at,
        )
        for cat, sch, tbl, col in results
    ]

    return DataResponse(data=response)


# === Admin Endpoints ===


@router.post("/admin/refresh", response_model=DataResponse[dict])
async def trigger_refresh(
    user: CurrentUser,
    cache: SchemaCacheDep,
    background_tasks: BackgroundTasks,
    _: None = RequireAdmin,
) -> DataResponse[dict]:
    """
    Manually trigger schema cache refresh (admin only).

    Starts background task to fetch latest metadata from Starburst.
    Returns immediately.

    **Authentication:** Admin role required

    **Performance:** Returns immediately; refresh runs in background
    """
    background_tasks.add_task(run_schema_cache_job, cache)
    logger.info("schema_cache_manual_refresh_triggered", user=user.username)
    return DataResponse(data={"status": "refresh triggered"})


@router.get("/stats", response_model=DataResponse[CacheStatsResponse])
async def get_cache_stats(
    user: CurrentUser,
    cache: SchemaCacheDep,
    _: None = RequireAdmin,
) -> DataResponse[CacheStatsResponse]:
    """
    Get schema cache statistics (admin only).

    **Authentication:** Admin role required

    **Response:**
    - `total_catalogs`: Number of cached catalogs
    - `total_schemas`: Number of cached schemas
    - `total_tables`: Number of cached tables
    - `total_columns`: Number of cached columns
    - `last_refresh`: ISO 8601 timestamp of last refresh
    - `index_size_bytes`: Estimated memory usage of search indices
    """
    stats = cache.get_stats()
    return DataResponse(data=CacheStatsResponse(**stats))
