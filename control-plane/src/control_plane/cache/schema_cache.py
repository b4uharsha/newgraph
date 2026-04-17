"""In-memory schema metadata cache with lock-free reads."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

try:
    import pygtrie
except ImportError:
    raise ImportError(
        "pygtrie is required for schema cache. Install with: pip install pygtrie"
    )

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Column:
    """Column metadata (immutable for thread safety)."""

    name: str
    data_type: str
    is_nullable: bool
    ordinal_position: int
    column_default: str | None = None


@dataclass(frozen=True, slots=True)
class Table:
    """Table metadata with columns."""

    name: str
    table_type: str  # 'BASE TABLE', 'VIEW', etc.
    columns: tuple[Column, ...]  # Immutable tuple

    @property
    def column_count(self) -> int:
        """Get column count."""
        return len(self.columns)

    def get_column(self, name: str) -> Column | None:
        """Get column by name (case-insensitive)."""
        name_lower = name.lower()
        return next((c for c in self.columns if c.name.lower() == name_lower), None)


@dataclass(frozen=True, slots=True)
class Schema:
    """Schema metadata with tables."""

    name: str
    tables: dict[str, Table]  # table_name -> Table

    @property
    def table_count(self) -> int:
        """Get table count."""
        return len(self.tables)

    def get_table(self, name: str) -> Table | None:
        """Get table by name (case-insensitive)."""
        name_lower = name.lower()
        # Try exact match first
        if name in self.tables:
            return self.tables[name]
        # Fall back to case-insensitive search
        return next(
            (t for k, t in self.tables.items() if k.lower() == name_lower), None
        )


@dataclass(frozen=True, slots=True)
class Catalog:
    """Catalog metadata with schemas."""

    name: str
    schemas: dict[str, Schema]  # schema_name -> Schema

    @property
    def schema_count(self) -> int:
        """Get schema count."""
        return len(self.schemas)

    def get_schema(self, name: str) -> Schema | None:
        """Get schema by name (case-insensitive)."""
        name_lower = name.lower()
        if name in self.schemas:
            return self.schemas[name]
        return next(
            (s for k, s in self.schemas.items() if k.lower() == name_lower), None
        )


class SchemaMetadataCache:
    """
    Thread-safe in-memory cache for Starburst schema metadata.

    Features:
    - Lock-free reads (immutable data structures)
    - Atomic refresh (exclusive lock)
    - Prefix search via Trie indices
    - Case-insensitive lookups

    Memory usage: ~350 bytes per table, ~150 bytes per column
    Performance: ~1μs for exact lookup, ~100μs for prefix search
    """

    def __init__(self):
        """Initialize empty cache."""
        self._catalogs: dict[str, Catalog] = {}
        self._table_index: pygtrie.StringTrie = pygtrie.StringTrie()
        self._column_index: pygtrie.StringTrie = pygtrie.StringTrie()
        self._lock = asyncio.Lock()
        self._last_refresh: datetime | None = None

    # === READ OPERATIONS (Lock-free) ===

    def list_catalogs(self) -> list[Catalog]:
        """
        List all catalogs.

        Returns:
            List of Catalog objects (sorted by name)

        Thread-safe: Yes (reads immutable data)
        """
        return sorted(self._catalogs.values(), key=lambda c: c.name)

    def get_catalog(self, name: str) -> Catalog | None:
        """
        Get catalog by name.

        Args:
            name: Catalog name (case-sensitive)

        Returns:
            Catalog object or None if not found

        Thread-safe: Yes
        """
        return self._catalogs.get(name)

    def get_schema(self, catalog: str, schema: str) -> Schema | None:
        """
        Get schema by catalog and schema name.

        Args:
            catalog: Catalog name
            schema: Schema name

        Returns:
            Schema object or None if not found

        Thread-safe: Yes
        """
        cat = self._catalogs.get(catalog)
        return cat.get_schema(schema) if cat else None

    def get_table(self, catalog: str, schema: str, table: str) -> Table | None:
        """
        Get table by full path.

        Args:
            catalog: Catalog name
            schema: Schema name
            table: Table name

        Returns:
            Table object or None if not found

        Thread-safe: Yes
        """
        sch = self.get_schema(catalog, schema)
        return sch.get_table(table) if sch else None

    def search_tables(
        self, pattern: str, limit: int = 100
    ) -> list[tuple[str, str, str, Table]]:
        """
        Search tables by name pattern (prefix match, case-insensitive).

        Args:
            pattern: Search pattern (e.g., "customer" matches "customers", "customer_orders")
            limit: Maximum results to return

        Returns:
            List of (catalog, schema, table_name, Table) tuples

        Thread-safe: Yes
        Performance: O(N) where N=total tables (filtered by prefix)
        """
        pattern_lower = pattern.lower()
        results = []

        # Iterate through trie and filter by prefix
        for key, value in self._table_index.items():
            if key.startswith(pattern_lower):
                results.append(value)
                if len(results) >= limit:
                    break

        return results

    def search_columns(
        self, pattern: str, limit: int = 100
    ) -> list[tuple[str, str, str, Column]]:
        """
        Search columns by name pattern (prefix match, case-insensitive).

        Args:
            pattern: Search pattern
            limit: Maximum results to return

        Returns:
            List of (catalog, schema, table_name, Column) tuples

        Thread-safe: Yes
        Performance: O(N) where N=total columns (filtered by prefix)
        """
        pattern_lower = pattern.lower()
        results = []

        # Iterate through trie and filter by prefix
        for key, value_list in self._column_index.items():
            if key.startswith(pattern_lower):
                for item in value_list:
                    results.append(item)
                    if len(results) >= limit:
                        return results

        return results

    def get_stats(self) -> dict:
        """
        Get cache statistics.

        Returns:
            Dict with counts and metadata

        Thread-safe: Yes
        """
        total_schemas = sum(cat.schema_count for cat in self._catalogs.values())
        total_tables = sum(
            schema.table_count
            for cat in self._catalogs.values()
            for schema in cat.schemas.values()
        )
        total_columns = sum(
            table.column_count
            for cat in self._catalogs.values()
            for schema in cat.schemas.values()
            for table in schema.tables.values()
        )

        return {
            "total_catalogs": len(self._catalogs),
            "total_schemas": total_schemas,
            "total_tables": total_tables,
            "total_columns": total_columns,
            "last_refresh": (
                self._last_refresh.isoformat() if self._last_refresh else None
            ),
            "index_size_bytes": self._estimate_index_size(),
        }

    def _estimate_index_size(self) -> int:
        """Estimate memory usage of trie indices in bytes."""
        # Rough estimate: ~10 bytes per character in trie
        table_chars = sum(len(k) for k in self._table_index.keys())
        column_chars = sum(len(k) for k in self._column_index.keys())
        return (table_chars + column_chars) * 10

    # === WRITE OPERATIONS (Exclusive lock) ===

    async def refresh(self, new_catalogs: dict[str, Catalog]) -> None:
        """
        Atomically replace entire cache.

        This is the ONLY write operation. Called by background job.

        Args:
            new_catalogs: Dict of catalog_name -> Catalog

        Thread-safe: Yes (exclusive lock)
        Performance: O(N) where N=total items
        """
        async with self._lock:
            logger.info(f"Refreshing cache with {len(new_catalogs)} catalogs")

            # Build search indices
            table_index = pygtrie.StringTrie()
            column_index = pygtrie.StringTrie()

            for cat_name, catalog in new_catalogs.items():
                for sch_name, schema in catalog.schemas.items():
                    for tbl_name, table in schema.tables.items():
                        # Index table by lowercase name for case-insensitive search
                        table_key = tbl_name.lower()
                        table_index[table_key] = (cat_name, sch_name, tbl_name, table)

                        # Index columns
                        for column in table.columns:
                            col_key = column.name.lower()
                            if col_key not in column_index:
                                column_index[col_key] = []
                            column_index[col_key].append(
                                (cat_name, sch_name, tbl_name, column)
                            )

            # Atomic swap (all or nothing)
            self._catalogs = new_catalogs
            self._table_index = table_index
            self._column_index = column_index
            self._last_refresh = datetime.now(UTC)

            logger.info(f"Cache refresh complete. Stats: {self.get_stats()}")

    async def clear(self) -> None:
        """
        Clear cache (for testing).

        Thread-safe: Uses same lock as refresh
        """
        await self.refresh({})
