"""Starburst metadata client for querying system catalogs."""

from __future__ import annotations

from typing import Any

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from control_plane.config import Settings

logger = structlog.get_logger()


class StarburstMetadataClient:
    """
    Client for fetching Starburst schema metadata via REST API.

    Uses Trino REST API (/v1/statement) for query execution.
    Supports async/await for non-blocking I/O.
    """

    def __init__(
        self,
        url: str,
        user: str,
        password: str,
        timeout: float = 30.0,
        max_retries: int = 3,
        role: str = "",
    ):
        """
        Initialize Starburst metadata client.

        Args:
            url: Starburst coordinator URL (e.g., "https://starburst.example.com")
            user: Username for authentication
            password: Password for authentication
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts for failed requests
            role: Starburst role / use case ID for SET ROLE (ADR-102)
        """
        self.url = url.rstrip("/")
        self.user = user  # Store user separately for X-Trino-User header
        self.role = role
        # Only use Basic Auth if password is meaningful (not empty or placeholder)
        # Vanilla Trino doesn't support password auth over HTTP
        if password and password.lower() not in ("", "unused", "none"):
            self.auth = (user, password)
        else:
            self.auth = None
        self.timeout = timeout
        self.max_retries = max_retries
        self._client: httpx.AsyncClient | None = None
        self._logger = logger.bind(component="starburst")

    @classmethod
    def from_config(cls, settings: Settings) -> StarburstMetadataClient:
        """
        Create client from settings.

        Args:
            settings: Application settings

        Returns: StarburstMetadataClient instance
        """
        return cls(
            url=settings.starburst_url,
            user=settings.starburst_user,
            password=settings.starburst_password.get_secret_value(),
            timeout=float(settings.starburst_timeout_seconds),
            role=settings.starburst_role,
        )

    async def __aenter__(self):
        """Async context manager entry."""
        self._client = httpx.AsyncClient(
            timeout=self.timeout,
            auth=self.auth,
            follow_redirects=True,
        )
        await self._set_role()
        return self

    async def _set_role(self) -> None:
        """Issue SET ROLE if configured (ADR-102). Non-fatal on failure."""
        if not self.role or not self._client:
            return
        try:
            headers = {
                "X-Trino-User": self.user,
                "X-Trino-Source": "graph-olap-schema-cache",
            }
            response = await self._client.post(
                f"{self.url}/v1/statement",
                headers=headers,
                content=f"SET ROLE {self.role}",
            )
            response.raise_for_status()
            self._logger.info("starburst_set_role_ok", role=self.role)
        except Exception as e:
            self._logger.warning(
                "starburst_set_role_failed",
                role=self.role,
                error=str(e),
            )

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def close(self):
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.ConnectError, httpx.ReadTimeout)),
        reraise=True,
    )
    async def execute_query(self, sql: str) -> list[dict[str, Any]]:
        """
        Execute a SELECT query and return all rows.

        Uses Trino REST API with polling until query completes.

        Args:
            sql: SQL query to execute

        Returns: List of rows as dicts (column_name -> value)

        Raises:
            StarburstQueryError: Query execution failed
            StarburstTimeoutError: Query exceeded timeout
            StarburstError: Other errors
        """
        if not self._client:
            raise StarburstError("Client not initialized. Use async with block.")

        self._logger.debug("Executing query", sql=sql[:100])

        # Submit query
        headers = {
            "X-Trino-User": self.user,
            "X-Trino-Source": "graph-olap-schema-cache",
            "X-Trino-Client-Tags": "schema-cache",
        }

        try:
            response = await self._client.post(
                f"{self.url}/v1/statement",
                headers=headers,
                content=sql,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise StarburstError(f"HTTP {e.response.status_code}: {e.response.text}")
        except httpx.TimeoutException:
            raise StarburstTimeoutError(f"Query submission timeout: {sql[:100]}")

        result = response.json()

        # Check for immediate errors
        if error := result.get("error"):
            raise StarburstQueryError(error.get("message", "Unknown error"))

        # Extract data from initial response
        rows = []
        if "data" in result and "columns" in result:
            columns = [col["name"] for col in result["columns"]]
            for row_data in result["data"]:
                rows.append(dict(zip(columns, row_data)))

        next_uri = result.get("nextUri")

        # Poll until complete (if more data to fetch)
        max_polls = 100  # Prevent infinite loops
        polls = 0

        while next_uri and polls < max_polls:
            polls += 1

            try:
                response = await self._client.get(next_uri, headers=headers)
                response.raise_for_status()
            except httpx.TimeoutException:
                raise StarburstTimeoutError(f"Query polling timeout after {polls} polls")

            result = response.json()

            # Extract rows from polling response
            if "data" in result and "columns" in result:
                columns = [col["name"] for col in result["columns"]]
                for row_data in result["data"]:
                    rows.append(dict(zip(columns, row_data)))

            # Check for errors
            if error := result.get("error"):
                raise StarburstQueryError(error.get("message", "Unknown error"))

            next_uri = result.get("nextUri")

        if polls >= max_polls:
            raise StarburstTimeoutError(f"Query exceeded {max_polls} polls")

        self._logger.debug("Query complete", rows=len(rows), polls=polls)
        return rows

    async def fetch_catalogs(self) -> list[dict[str, Any]]:
        """
        Fetch all accessible catalogs.

        Returns: List of dicts with 'catalog_name' key

        Example:
            [{"catalog_name": "analytics"}, {"catalog_name": "sales"}]
        """
        sql = "SELECT catalog_name FROM system.metadata.catalogs ORDER BY catalog_name"
        return await self.execute_query(sql)

    async def fetch_schemas(self, catalog: str) -> list[dict[str, Any]]:
        """
        Fetch all schemas in a catalog.

        Args:
            catalog: Catalog name

        Returns: List of dicts with 'schema_name' key
        """
        # Use information_schema.schemata which works with both Trino and Starburst
        sql = f"""
            SELECT schema_name
            FROM "{catalog}".information_schema.schemata
            ORDER BY schema_name
        """
        return await self.execute_query(sql)

    async def fetch_tables(self, catalog: str, schema: str) -> list[dict[str, Any]]:
        """
        Fetch all tables in a schema.

        Args:
            catalog: Catalog name
            schema: Schema name

        Returns: List of dicts with 'table_name' and 'table_type' keys
        """
        # Use information_schema.tables which works with both Trino and Starburst
        # Escape single quotes in identifiers
        safe_schema = schema.replace("'", "''")
        sql = f"""
            SELECT table_name, table_type
            FROM "{catalog}".information_schema.tables
            WHERE table_schema = '{safe_schema}'
            ORDER BY table_name
        """
        return await self.execute_query(sql)

    async def fetch_columns(
        self, catalog: str, schema: str, table: str
    ) -> list[dict[str, Any]]:
        """
        Fetch all columns for a table.

        Args:
            catalog: Catalog name
            schema: Schema name
            table: Table name

        Returns: List of dicts with column metadata
        """
        # Use catalog-qualified information_schema for Trino compatibility
        # Escape single quotes in identifiers (SQL injection prevention)
        safe_schema = schema.replace("'", "''")
        safe_table = table.replace("'", "''")
        sql = f"""
            SELECT
                column_name,
                data_type,
                is_nullable,
                column_default,
                ordinal_position
            FROM "{catalog}".information_schema.columns
            WHERE table_schema = '{safe_schema}'
              AND table_name = '{safe_table}'
            ORDER BY ordinal_position
        """
        return await self.execute_query(sql)


class StarburstError(Exception):
    """Base exception for Starburst client errors."""

    pass


class StarburstQueryError(StarburstError):
    """Query execution error."""

    pass


class StarburstTimeoutError(StarburstError):
    """Query timeout error."""

    pass
