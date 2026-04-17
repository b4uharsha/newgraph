"""Schema metadata resource management."""

from __future__ import annotations

from typing import TYPE_CHECKING

from graph_olap.models.schema import CacheStats, Catalog, Column, Schema, Table

if TYPE_CHECKING:
    from graph_olap.http import HTTPClient


class SchemaResource:
    """Browse Starburst schema metadata.

    All operations use cached metadata (refreshed every 24h).
    Performance: ~5ms per API call (HTTP overhead), ~1μs for cache lookup.

    Example:
        >>> client = GraphOLAPClient(api_url=api_url, username="user@example.com")

        >>> # List all catalogs
        >>> catalogs = client.schema.list_catalogs()
        >>> for cat in catalogs:
        ...     print(f"{cat.catalog_name}: {cat.schema_count} schemas")

        >>> # List schemas in a catalog
        >>> schemas = client.schema.list_schemas("analytics")
        >>> for sch in schemas:
        ...     print(f"{sch.schema_name}: {sch.table_count} tables")

        >>> # List tables in a schema
        >>> tables = client.schema.list_tables("analytics", "public")
        >>> for tbl in tables:
        ...     print(f"{tbl.table_name} ({tbl.table_type})")

        >>> # Get columns for a table
        >>> columns = client.schema.list_columns("analytics", "public", "users")
        >>> for col in columns:
        ...     print(f"{col.column_name}: {col.data_type}")

        >>> # Search for tables
        >>> results = client.schema.search_tables("customer", limit=50)
        >>> for tbl in results:
        ...     print(f"{tbl.catalog_name}.{tbl.schema_name}.{tbl.table_name}")

        >>> # Search for columns
        >>> results = client.schema.search_columns("email", limit=50)
        >>> for col in results:
        ...     print(f"{col.catalog_name}.{col.schema_name}.{col.table_name}.{col.column_name}")
    """

    def __init__(self, http: HTTPClient):
        """Initialize schema resource.

        Args:
            http: HTTP client for API requests
        """
        self._http = http

    def list_catalogs(self) -> list[Catalog]:
        """List all cached Starburst catalogs.

        Returns:
            List of Catalog objects (sorted by name)

        Example:
            >>> catalogs = client.schema.list_catalogs()
            >>> for cat in catalogs:
            ...     print(f"{cat.catalog_name}: {cat.schema_count} schemas")
            analytics: 12 schemas
            sales: 5 schemas
        """
        response = self._http.get("/api/schema/catalogs")
        return [Catalog.from_api_response(item) for item in response["data"]]

    def list_schemas(self, catalog: str) -> list[Schema]:
        """List all schemas in a catalog.

        Args:
            catalog: Catalog name (e.g., "analytics")

        Returns:
            List of Schema objects

        Raises:
            NotFoundError: Catalog not found in cache

        Example:
            >>> schemas = client.schema.list_schemas("analytics")
            >>> for sch in schemas:
            ...     print(f"{sch.schema_name}: {sch.table_count} tables")
            public: 25 tables
            staging: 10 tables
        """
        response = self._http.get(f"/api/schema/catalogs/{catalog}/schemas")
        return [Schema.from_api_response(item) for item in response["data"]]

    def list_tables(self, catalog: str, schema: str) -> list[Table]:
        """List all tables in a schema.

        Args:
            catalog: Catalog name
            schema: Schema name

        Returns:
            List of Table objects

        Raises:
            NotFoundError: Schema not found in cache

        Example:
            >>> tables = client.schema.list_tables("analytics", "public")
            >>> for tbl in tables:
            ...     print(f"{tbl.table_name} ({tbl.table_type})")
            customers (BASE TABLE)
            orders (BASE TABLE)
            customer_orders_view (VIEW)
        """
        response = self._http.get(
            f"/api/schema/catalogs/{catalog}/schemas/{schema}/tables"
        )
        return [Table.from_api_response(item) for item in response["data"]]

    def list_columns(self, catalog: str, schema: str, table: str) -> list[Column]:
        """Get all columns for a table.

        Args:
            catalog: Catalog name
            schema: Schema name
            table: Table name

        Returns:
            List of Column objects (sorted by ordinal_position)

        Raises:
            NotFoundError: Table not found in cache

        Example:
            >>> columns = client.schema.list_columns("analytics", "public", "users")
            >>> for col in columns:
            ...     print(f"{col.column_name}: {col.data_type}")
            id: bigint
            email: varchar
            created_at: timestamp
        """
        response = self._http.get(
            f"/api/schema/catalogs/{catalog}/schemas/{schema}/tables/{table}/columns"
        )
        return [Column.from_api_response(item) for item in response["data"]]

    def search_tables(self, pattern: str, limit: int = 100) -> list[Table]:
        """Search tables by name pattern (prefix match, case-insensitive).

        Args:
            pattern: Search pattern (e.g., "customer" matches "customers", "customer_orders")
            limit: Maximum results (default: 100, max: 1000)

        Returns:
            List of Table objects matching pattern

        Example:
            >>> results = client.schema.search_tables("customer", limit=50)
            >>> for tbl in results:
            ...     print(f"{tbl.catalog_name}.{tbl.schema_name}.{tbl.table_name}")
            analytics.public.customers
            analytics.public.customer_orders
            sales.main.customer_segments
        """
        response = self._http.get(
            "/api/schema/search/tables", params={"q": pattern, "limit": limit}
        )
        return [Table.from_api_response(item) for item in response["data"]]

    def search_columns(self, pattern: str, limit: int = 100) -> list[Column]:
        """Search columns by name pattern (prefix match, case-insensitive).

        Args:
            pattern: Search pattern (e.g., "email" matches "email", "email_address")
            limit: Maximum results (default: 100, max: 1000)

        Returns:
            List of Column objects matching pattern

        Example:
            >>> results = client.schema.search_columns("email", limit=50)
            >>> for col in results:
            ...     print(f"{col.catalog_name}.{col.schema_name}.{col.table_name}.{col.column_name}")
            analytics.public.users.email
            analytics.public.customers.email_address
            sales.contacts.email_primary
        """
        response = self._http.get(
            "/api/schema/search/columns", params={"q": pattern, "limit": limit}
        )
        return [Column.from_api_response(item) for item in response["data"]]

    # Admin operations

    def admin_refresh(self) -> dict:
        """Trigger cache refresh (admin only).

        Starts background task to fetch latest metadata from Starburst.
        Returns immediately.

        Returns:
            Dict with status message

        Raises:
            ForbiddenError: If user doesn't have admin role

        Example:
            >>> result = client.schema.admin_refresh()
            >>> print(result["status"])
            refresh triggered
        """
        response = self._http.post("/api/schema/admin/refresh")
        return response["data"]

    def get_stats(self) -> CacheStats:
        """Get cache statistics (admin only).

        Returns:
            CacheStats object with counts and metadata

        Raises:
            ForbiddenError: If user doesn't have admin role

        Example:
            >>> stats = client.schema.get_stats()
            >>> print(f"Tables: {stats.total_tables}")
            >>> print(f"Last refresh: {stats.last_refresh}")
            Tables: 1523
            Last refresh: 2025-12-25T10:30:00Z
        """
        response = self._http.get("/api/schema/stats")
        return CacheStats.from_api_response(response["data"])
