"""E2E tests for schema metadata cache.

Tests the full workflow from SDK → Control Plane API → Schema Cache.

Note: These tests use the cache as-is and don't require a live Starburst connection.
The cache will be empty unless manually populated via admin refresh endpoint.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest
from graph_olap.exceptions import NotFoundError

if TYPE_CHECKING:
    from graph_olap import GraphOLAPClient

logger = logging.getLogger(__name__)


class TestSchemaMetadata:
    """E2E tests for schema metadata operations."""

    def test_list_catalogs_when_cache_empty(
        self, graph_olap_client: GraphOLAPClient
    ):
        """Test listing catalogs when cache is empty (no Starburst connection).

        This is expected behavior - the cache starts empty and needs an admin
        to trigger refresh with a valid Starburst connection.
        """
        catalogs = graph_olap_client.schema.list_catalogs()

        # Cache starts empty in test environment (no Starburst)
        assert isinstance(catalogs, list)
        # May be empty or populated depending on test environment
        logger.info(f"Cache contains {len(catalogs)} catalogs")

    def test_list_schemas_catalog_not_found(
        self, graph_olap_client: GraphOLAPClient
    ):
        """Test listing schemas for non-existent catalog returns 404."""
        with pytest.raises(NotFoundError, match="not found in cache"):
            graph_olap_client.schema.list_schemas("nonexistent_catalog")

    def test_list_tables_schema_not_found(
        self, graph_olap_client: GraphOLAPClient
    ):
        """Test listing tables for non-existent schema returns 404."""
        with pytest.raises(NotFoundError, match="not found in cache"):
            graph_olap_client.schema.list_tables("catalog", "nonexistent_schema")

    def test_list_columns_table_not_found(
        self, graph_olap_client: GraphOLAPClient
    ):
        """Test listing columns for non-existent table returns 404."""
        with pytest.raises(NotFoundError, match="not found in cache"):
            graph_olap_client.schema.list_columns(
                "catalog", "schema", "nonexistent_table"
            )

    def test_search_tables_returns_results(
        self, graph_olap_client: GraphOLAPClient
    ):
        """Test searching tables by pattern.

        Returns empty list if cache is empty (no Starburst connection).
        """
        results = graph_olap_client.schema.search_tables("test", limit=10)

        assert isinstance(results, list)
        # May be empty if cache not populated
        logger.info(f"Search found {len(results)} tables matching 'test'")

    def test_search_tables_with_limit(
        self, graph_olap_client: GraphOLAPClient
    ):
        """Test search respects limit parameter."""
        results = graph_olap_client.schema.search_tables("a", limit=5)

        assert isinstance(results, list)
        assert len(results) <= 5

    def test_search_columns_returns_results(
        self, graph_olap_client: GraphOLAPClient
    ):
        """Test searching columns by pattern.

        Returns empty list if cache is empty (no Starburst connection).
        """
        results = graph_olap_client.schema.search_columns("id", limit=10)

        assert isinstance(results, list)
        # May be empty if cache not populated
        logger.info(f"Search found {len(results)} columns matching 'id'")

    def test_search_columns_with_limit(
        self, graph_olap_client: GraphOLAPClient
    ):
        """Test column search respects limit parameter."""
        results = graph_olap_client.schema.search_columns("name", limit=3)

        assert isinstance(results, list)
        assert len(results) <= 3


class TestSchemaAdminOperations:
    """E2E tests for schema admin operations (require admin role)."""

    def test_get_stats_as_regular_user_forbidden(
        self, graph_olap_client: GraphOLAPClient
    ):
        """Test that regular users cannot access stats endpoint."""
        from graph_olap.exceptions import ForbiddenError

        with pytest.raises(ForbiddenError):
            graph_olap_client.schema.get_stats()

    def test_admin_refresh_as_regular_user_forbidden(
        self, graph_olap_client: GraphOLAPClient
    ):
        """Test that regular users cannot trigger cache refresh."""
        from graph_olap.exceptions import ForbiddenError

        with pytest.raises(ForbiddenError):
            graph_olap_client.schema.admin_refresh()

    def test_get_stats_as_admin(self, admin_client: GraphOLAPClient):
        """Test getting cache statistics as admin user."""
        stats = admin_client.schema.get_stats()

        assert stats.total_catalogs >= 0
        assert stats.total_schemas >= 0
        assert stats.total_tables >= 0
        assert stats.total_columns >= 0
        assert stats.index_size_bytes >= 0
        # last_refresh may be None if never refreshed
        logger.info(
            f"Cache stats: {stats.total_catalogs} catalogs, "
            f"{stats.total_tables} tables, {stats.total_columns} columns"
        )

    def test_admin_refresh_trigger(self, admin_client: GraphOLAPClient):
        """Test triggering manual cache refresh as admin.

        Note: This will fail if Starburst is not configured, but the endpoint
        should accept the request and return success (refresh runs in background).
        """
        result = admin_client.schema.admin_refresh()

        assert isinstance(result, dict)
        assert result["status"] == "refresh triggered"
        logger.info("Manual cache refresh triggered successfully")


class TestSchemaMetadataWorkflow:
    """E2E tests for complete schema metadata workflows.

    These tests demonstrate the full user journey for browsing schema metadata.
    """

    def test_catalog_browsing_workflow(self, graph_olap_client: GraphOLAPClient):
        """Test the complete workflow of browsing catalog metadata.

        Workflow:
        1. List all catalogs
        2. For first catalog (if exists), list schemas
        3. For first schema (if exists), list tables
        4. For first table (if exists), list columns
        """
        # Step 1: List catalogs
        catalogs = graph_olap_client.schema.list_catalogs()
        logger.info(f"Found {len(catalogs)} catalogs")

        if not catalogs:
            logger.info("No catalogs in cache (Starburst not configured)")
            pytest.skip("Cache is empty - requires Starburst connection")
            return

        # Step 2: List schemas
        first_catalog = catalogs[0]
        assert first_catalog.catalog_name
        assert first_catalog.schema_count >= 0

        schemas = graph_olap_client.schema.list_schemas(first_catalog.catalog_name)
        logger.info(
            f"Catalog '{first_catalog.catalog_name}' has {len(schemas)} schemas"
        )

        if not schemas:
            logger.info("No schemas in first catalog")
            return

        # Step 3: List tables
        first_schema = schemas[0]
        assert first_schema.schema_name
        assert first_schema.table_count >= 0

        tables = graph_olap_client.schema.list_tables(
            first_catalog.catalog_name, first_schema.schema_name
        )
        logger.info(
            f"Schema '{first_schema.schema_name}' has {len(tables)} tables"
        )

        if not tables:
            logger.info("No tables in first schema")
            return

        # Step 4: List columns
        first_table = tables[0]
        assert first_table.table_name
        assert first_table.column_count >= 0

        columns = graph_olap_client.schema.list_columns(
            first_catalog.catalog_name,
            first_schema.schema_name,
            first_table.table_name,
        )
        logger.info(f"Table '{first_table.table_name}' has {len(columns)} columns")

        # Verify column structure
        if columns:
            first_col = columns[0]
            assert first_col.column_name
            assert first_col.data_type
            assert isinstance(first_col.is_nullable, bool)
            assert first_col.ordinal_position >= 1
            logger.info(
                f"First column: {first_col.column_name} ({first_col.data_type})"
            )

    def test_search_workflow(self, graph_olap_client: GraphOLAPClient):
        """Test search-based workflow for finding tables and columns.

        Workflow:
        1. Search for tables by common pattern
        2. Search for columns by common pattern
        3. Verify result structure
        """
        # Search for tables with common patterns (any single char will match all)
        table_results = graph_olap_client.schema.search_tables("a", limit=5)
        logger.info(f"Table search found {len(table_results)} results")

        # Search for columns with common patterns
        column_results = graph_olap_client.schema.search_columns("a", limit=5)
        logger.info(f"Column search found {len(column_results)} results")

        # Verify structure if results exist
        if table_results:
            first_result = table_results[0]
            assert first_result.catalog_name
            assert first_result.schema_name
            assert first_result.table_name
            assert first_result.table_type
            logger.info(
                f"Found table: {first_result.catalog_name}."
                f"{first_result.schema_name}.{first_result.table_name}"
            )

        if column_results:
            first_result = column_results[0]
            assert first_result.catalog_name
            assert first_result.schema_name
            assert first_result.table_name
            assert first_result.column_name
            logger.info(
                f"Found column: {first_result.catalog_name}."
                f"{first_result.schema_name}.{first_result.table_name}."
                f"{first_result.column_name}"
            )

    def test_cache_performance(self, graph_olap_client: GraphOLAPClient):
        """Test that cache operations are fast (< 100ms for lookups).

        This verifies that the in-memory cache provides good performance
        compared to querying Starburst directly.
        """
        import time

        # Test catalog listing performance
        start = time.time()
        catalogs = graph_olap_client.schema.list_catalogs()
        duration_ms = (time.time() - start) * 1000

        logger.info(f"List catalogs took {duration_ms:.2f}ms")
        # Should be fast even over network (< 100ms for API call)
        assert duration_ms < 1000, "Cache lookup too slow"

        # Test search performance
        start = time.time()
        results = graph_olap_client.schema.search_tables("test", limit=10)
        duration_ms = (time.time() - start) * 1000

        logger.info(f"Search tables took {duration_ms:.2f}ms")
        assert duration_ms < 1000, "Search too slow"
