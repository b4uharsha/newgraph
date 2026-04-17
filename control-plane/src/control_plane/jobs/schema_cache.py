"""Schema metadata cache refresh job."""

from __future__ import annotations

import asyncio
import time

import structlog

# Limit concurrent Trino queries to avoid overwhelming the server
# Trino's default queue is 1024, so keep well under that
MAX_CONCURRENT_QUERIES = 10
_query_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    """Get or create the query semaphore (per event loop)."""
    global _query_semaphore
    if _query_semaphore is None:
        _query_semaphore = asyncio.Semaphore(MAX_CONCURRENT_QUERIES)
    return _query_semaphore

from control_plane.cache.schema_cache import (
    Catalog,
    Column,
    Schema,
    SchemaMetadataCache,
    Table,
)
from control_plane.clients.starburst_metadata import StarburstMetadataClient
from control_plane.config import get_settings

logger = structlog.get_logger(__name__)


async def run_schema_cache_job(cache: SchemaMetadataCache) -> None:
    """
    Refresh schema metadata cache from Starburst.

    Fetches all catalogs, schemas, tables, and columns in parallel,
    then atomically swaps the cache.

    Args:
        cache: SchemaMetadataCache instance from app.state

    Raises:
        Exception: Propagates errors for job scheduler to track
    """
    logger.info("schema_cache_refresh_started")
    start_time = time.time()

    settings = get_settings()

    try:
        async with StarburstMetadataClient.from_config(settings) as starburst:
            # 1. Fetch all catalogs
            logger.info("fetching_catalogs")
            catalog_rows = await starburst.fetch_catalogs()
            logger.info("catalogs_fetched", count=len(catalog_rows))

            # 2. Fetch all catalogs in parallel
            tasks = [
                _fetch_catalog_metadata(starburst, row["catalog_name"])
                for row in catalog_rows
            ]
            catalog_objects = await asyncio.gather(*tasks, return_exceptions=True)

            # 3. Filter out errors
            new_catalogs = {}
            for catalog in catalog_objects:
                if isinstance(catalog, Exception):
                    logger.error("catalog_fetch_failed", error=str(catalog))
                    continue
                new_catalogs[catalog.name] = catalog

            # 4. Atomic refresh
            await cache.refresh(new_catalogs)

            # 5. Log stats
            stats = cache.get_stats()
            duration = time.time() - start_time

            logger.info(
                "schema_cache_refresh_completed",
                duration_seconds=round(duration, 2),
                catalogs=stats["total_catalogs"],
                schemas=stats["total_schemas"],
                tables=stats["total_tables"],
                columns=stats["total_columns"],
                index_size_bytes=stats["index_size_bytes"],
            )

    except Exception as e:
        logger.error("schema_cache_refresh_failed", error=str(e), exc_info=True)
        raise


async def _fetch_catalog_metadata(
    starburst: StarburstMetadataClient,
    catalog_name: str,
) -> Catalog:
    """
    Fetch all metadata for a catalog (parallel execution with rate limiting).

    Args:
        starburst: Starburst client
        catalog_name: Catalog name

    Returns: Catalog object with all schemas/tables/columns
    """
    logger.info("fetching_catalog_metadata", catalog=catalog_name)
    sem = _get_semaphore()

    # Fetch schemas (with rate limiting)
    async with sem:
        schema_rows = await starburst.fetch_schemas(catalog_name)

    # Fetch all schemas in parallel
    schema_tasks = [
        _fetch_schema_metadata(starburst, catalog_name, row["schema_name"])
        for row in schema_rows
    ]
    schemas_list = await asyncio.gather(*schema_tasks)

    # Build schema dict
    schemas = {schema.name: schema for schema in schemas_list}

    logger.info(
        "catalog_metadata_fetched", catalog=catalog_name, schemas=len(schemas)
    )
    return Catalog(name=catalog_name, schemas=schemas)


async def _fetch_schema_metadata(
    starburst: StarburstMetadataClient,
    catalog_name: str,
    schema_name: str,
) -> Schema:
    """
    Fetch all tables for a schema (parallel execution with rate limiting).

    Args:
        starburst: Starburst client
        catalog_name: Catalog name
        schema_name: Schema name

    Returns: Schema object with all tables/columns
    """
    logger.debug(
        "fetching_schema_metadata", catalog=catalog_name, schema=schema_name
    )
    sem = _get_semaphore()

    # Fetch tables (with rate limiting)
    async with sem:
        table_rows = await starburst.fetch_tables(catalog_name, schema_name)

    # Fetch all tables in parallel
    table_tasks = [
        _fetch_table_metadata(
            starburst,
            catalog_name,
            schema_name,
            row["table_name"],
            row.get("table_type", "BASE TABLE"),
        )
        for row in table_rows
    ]
    tables_list = await asyncio.gather(*table_tasks)

    # Build table dict
    tables = {table.name: table for table in tables_list}

    return Schema(name=schema_name, tables=tables)


async def _fetch_table_metadata(
    starburst: StarburstMetadataClient,
    catalog_name: str,
    schema_name: str,
    table_name: str,
    table_type: str,
) -> Table:
    """
    Fetch all columns for a table (with rate limiting).

    Args:
        starburst: Starburst client
        catalog_name: Catalog name
        schema_name: Schema name
        table_name: Table name
        table_type: Table type (e.g., "BASE TABLE", "VIEW")

    Returns: Table object with all columns
    """
    logger.debug(
        "fetching_table_metadata",
        catalog=catalog_name,
        schema=schema_name,
        table=table_name,
    )
    sem = _get_semaphore()

    # Fetch columns (with rate limiting)
    async with sem:
        column_rows = await starburst.fetch_columns(catalog_name, schema_name, table_name)

    # Build column tuple (immutable)
    columns = tuple(
        Column(
            name=row["column_name"],
            data_type=row["data_type"],
            is_nullable=row["is_nullable"] == "YES",
            ordinal_position=row["ordinal_position"],
            column_default=row.get("column_default"),
        )
        for row in column_rows
    )

    return Table(name=table_name, table_type=table_type, columns=columns)
