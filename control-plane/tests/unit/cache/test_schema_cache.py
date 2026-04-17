"""Unit tests for schema metadata cache."""

from datetime import UTC, datetime

import pytest

from control_plane.cache.schema_cache import (
    Catalog,
    Column,
    Schema,
    SchemaMetadataCache,
    Table,
)


@pytest.fixture
def sample_columns():
    """Create sample columns for testing."""
    return (
        Column("id", "bigint", False, 1, None),
        Column("name", "varchar", True, 2, None),
        Column("email", "varchar", True, 3, None),
        Column("created_at", "timestamp", False, 4, "now()"),
    )


@pytest.fixture
def sample_table(sample_columns):
    """Create sample table for testing."""
    return Table("users", "BASE TABLE", sample_columns)


@pytest.fixture
def sample_schema(sample_table):
    """Create sample schema for testing."""
    return Schema("public", {"users": sample_table})


@pytest.fixture
def sample_catalog(sample_schema):
    """Create sample catalog for testing."""
    return Catalog("analytics", {"public": sample_schema})


@pytest.fixture
def cache():
    """Create empty cache for testing."""
    return SchemaMetadataCache()


@pytest.fixture
async def populated_cache(cache, sample_catalog):
    """Create cache with test data."""
    await cache.refresh({"analytics": sample_catalog})
    return cache


class TestColumn:
    """Tests for Column dataclass."""

    def test_column_immutable(self, sample_columns):
        """Test that Column is immutable."""
        col = sample_columns[0]
        with pytest.raises(AttributeError):
            col.name = "new_name"  # type: ignore

    def test_column_attributes(self, sample_columns):
        """Test Column attributes."""
        col = sample_columns[0]
        assert col.name == "id"
        assert col.data_type == "bigint"
        assert col.is_nullable is False
        assert col.ordinal_position == 1
        assert col.column_default is None


class TestTable:
    """Tests for Table dataclass."""

    def test_table_immutable(self, sample_table):
        """Test that Table is immutable."""
        with pytest.raises(AttributeError):
            sample_table.name = "new_name"  # type: ignore

    def test_table_column_count(self, sample_table):
        """Test column_count property."""
        assert sample_table.column_count == 4

    def test_table_get_column_case_insensitive(self, sample_table):
        """Test get_column with case-insensitive lookup."""
        # Exact match
        col = sample_table.get_column("email")
        assert col is not None
        assert col.name == "email"

        # Case-insensitive match
        col = sample_table.get_column("EMAIL")
        assert col is not None
        assert col.name == "email"

        # Not found
        col = sample_table.get_column("nonexistent")
        assert col is None


class TestSchema:
    """Tests for Schema dataclass."""

    def test_schema_immutable(self, sample_schema):
        """Test that Schema is immutable."""
        with pytest.raises(AttributeError):
            sample_schema.name = "new_name"  # type: ignore

    def test_schema_table_count(self, sample_schema):
        """Test table_count property."""
        assert sample_schema.table_count == 1

    def test_schema_get_table_case_insensitive(self, sample_schema):
        """Test get_table with case-insensitive lookup."""
        # Exact match
        table = sample_schema.get_table("users")
        assert table is not None
        assert table.name == "users"

        # Case-insensitive match
        table = sample_schema.get_table("USERS")
        assert table is not None
        assert table.name == "users"

        # Not found
        table = sample_schema.get_table("nonexistent")
        assert table is None


class TestCatalog:
    """Tests for Catalog dataclass."""

    def test_catalog_immutable(self, sample_catalog):
        """Test that Catalog is immutable."""
        with pytest.raises(AttributeError):
            sample_catalog.name = "new_name"  # type: ignore

    def test_catalog_schema_count(self, sample_catalog):
        """Test schema_count property."""
        assert sample_catalog.schema_count == 1

    def test_catalog_get_schema_case_insensitive(self, sample_catalog):
        """Test get_schema with case-insensitive lookup."""
        # Exact match
        schema = sample_catalog.get_schema("public")
        assert schema is not None
        assert schema.name == "public"

        # Case-insensitive match
        schema = sample_catalog.get_schema("PUBLIC")
        assert schema is not None
        assert schema.name == "public"

        # Not found
        schema = sample_catalog.get_schema("nonexistent")
        assert schema is None


class TestSchemaMetadataCache:
    """Tests for SchemaMetadataCache."""

    def test_cache_starts_empty(self, cache):
        """Test cache starts with no data."""
        assert cache.list_catalogs() == []
        assert cache.get_catalog("analytics") is None

    @pytest.mark.asyncio
    async def test_refresh_populates_cache(self, cache, sample_catalog):
        """Test refresh() populates cache."""
        assert len(cache.list_catalogs()) == 0

        await cache.refresh({"analytics": sample_catalog})

        assert len(cache.list_catalogs()) == 1
        assert cache.get_catalog("analytics") is not None

    @pytest.mark.asyncio
    async def test_refresh_is_atomic(self, cache, sample_catalog):
        """Test refresh() atomically replaces cache."""
        # Initial state
        await cache.refresh({"analytics": sample_catalog})
        assert len(cache.list_catalogs()) == 1

        # Create new catalog
        col = Column("id", "bigint", False, 1, None)
        tbl = Table("products", "BASE TABLE", (col,))
        sch = Schema("main", {"products": tbl})
        new_catalog = Catalog("sales", {"main": sch})

        # Refresh with new data
        await cache.refresh({"sales": new_catalog})

        # Old data should be gone
        assert len(cache.list_catalogs()) == 1
        assert cache.get_catalog("analytics") is None
        assert cache.get_catalog("sales") is not None

    @pytest.mark.asyncio
    async def test_list_catalogs_sorted(self, cache):
        """Test list_catalogs() returns sorted list."""
        col = Column("id", "bigint", False, 1, None)
        tbl = Table("t1", "BASE TABLE", (col,))
        sch = Schema("s1", {"t1": tbl})

        cat_a = Catalog("analytics", {"s1": sch})
        cat_z = Catalog("zebra", {"s1": sch})
        cat_m = Catalog("marketing", {"s1": sch})

        await cache.refresh({"zebra": cat_z, "analytics": cat_a, "marketing": cat_m})

        catalogs = cache.list_catalogs()
        assert len(catalogs) == 3
        assert catalogs[0].name == "analytics"
        assert catalogs[1].name == "marketing"
        assert catalogs[2].name == "zebra"

    @pytest.mark.asyncio
    async def test_get_catalog(self, populated_cache):
        """Test get_catalog() retrieval."""
        catalog = populated_cache.get_catalog("analytics")
        assert catalog is not None
        assert catalog.name == "analytics"

        # Not found
        catalog = populated_cache.get_catalog("nonexistent")
        assert catalog is None

    @pytest.mark.asyncio
    async def test_get_schema(self, populated_cache):
        """Test get_schema() retrieval."""
        schema = populated_cache.get_schema("analytics", "public")
        assert schema is not None
        assert schema.name == "public"

        # Catalog not found
        schema = populated_cache.get_schema("nonexistent", "public")
        assert schema is None

        # Schema not found
        schema = populated_cache.get_schema("analytics", "nonexistent")
        assert schema is None

    @pytest.mark.asyncio
    async def test_get_table(self, populated_cache):
        """Test get_table() retrieval."""
        table = populated_cache.get_table("analytics", "public", "users")
        assert table is not None
        assert table.name == "users"

        # Not found
        table = populated_cache.get_table("analytics", "public", "nonexistent")
        assert table is None

    @pytest.mark.asyncio
    async def test_search_tables_prefix_match(self, cache):
        """Test search_tables() with prefix matching."""
        col = Column("id", "bigint", False, 1, None)

        # Create tables with different names
        users_tbl = Table("users", "BASE TABLE", (col,))
        user_orders_tbl = Table("user_orders", "BASE TABLE", (col,))
        customers_tbl = Table("customers", "BASE TABLE", (col,))

        sch = Schema("public", {
            "users": users_tbl,
            "user_orders": user_orders_tbl,
            "customers": customers_tbl,
        })
        cat = Catalog("analytics", {"public": sch})

        await cache.refresh({"analytics": cat})

        # Search for "user" prefix
        results = cache.search_tables("user", limit=10)
        assert len(results) == 2
        table_names = [r[2] for r in results]  # Extract table names
        assert "users" in table_names
        assert "user_orders" in table_names
        assert "customers" not in table_names

    @pytest.mark.asyncio
    async def test_search_tables_case_insensitive(self, cache):
        """Test search_tables() is case-insensitive."""
        col = Column("id", "bigint", False, 1, None)
        users_tbl = Table("Users", "BASE TABLE", (col,))  # Mixed case
        sch = Schema("public", {"Users": users_tbl})
        cat = Catalog("analytics", {"public": sch})

        await cache.refresh({"analytics": cat})

        # Search with lowercase
        results = cache.search_tables("users", limit=10)
        assert len(results) == 1
        assert results[0][2] == "Users"  # Original casing preserved

    @pytest.mark.asyncio
    async def test_search_tables_limit(self, cache):
        """Test search_tables() respects limit."""
        col = Column("id", "bigint", False, 1, None)

        # Create many tables with "user" prefix
        tables = {}
        for i in range(10):
            tables[f"user_table_{i}"] = Table(f"user_table_{i}", "BASE TABLE", (col,))

        sch = Schema("public", tables)
        cat = Catalog("analytics", {"public": sch})

        await cache.refresh({"analytics": cat})

        # Search with limit
        results = cache.search_tables("user", limit=5)
        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_search_columns_prefix_match(self, cache):
        """Test search_columns() with prefix matching."""
        email_col = Column("email", "varchar", True, 1, None)
        email_verified_col = Column("email_verified", "boolean", False, 2, None)
        name_col = Column("name", "varchar", True, 3, None)

        tbl = Table("users", "BASE TABLE", (email_col, email_verified_col, name_col))
        sch = Schema("public", {"users": tbl})
        cat = Catalog("analytics", {"public": sch})

        await cache.refresh({"analytics": cat})

        # Search for "email" prefix
        results = cache.search_columns("email", limit=10)
        assert len(results) == 2
        column_names = [r[3].name for r in results]  # Extract column objects
        assert "email" in column_names
        assert "email_verified" in column_names
        assert "name" not in column_names

    @pytest.mark.asyncio
    async def test_get_stats(self, populated_cache):
        """Test get_stats() returns correct counts."""
        stats = populated_cache.get_stats()

        assert stats["total_catalogs"] == 1
        assert stats["total_schemas"] == 1
        assert stats["total_tables"] == 1
        assert stats["total_columns"] == 4
        assert stats["last_refresh"] is not None
        assert "index_size_bytes" in stats
        assert stats["index_size_bytes"] > 0

    @pytest.mark.asyncio
    async def test_clear(self, populated_cache):
        """Test clear() empties cache."""
        assert len(populated_cache.list_catalogs()) == 1

        await populated_cache.clear()

        assert len(populated_cache.list_catalogs()) == 0
        stats = populated_cache.get_stats()
        assert stats["total_catalogs"] == 0
        assert stats["total_tables"] == 0

    @pytest.mark.asyncio
    async def test_last_refresh_timestamp(self, cache):
        """Test _last_refresh timestamp is set."""
        assert cache._last_refresh is None

        col = Column("id", "bigint", False, 1, None)
        tbl = Table("t1", "BASE TABLE", (col,))
        sch = Schema("s1", {"t1": tbl})
        cat = Catalog("c1", {"s1": sch})

        await cache.refresh({"c1": cat})

        assert cache._last_refresh is not None
        assert isinstance(cache._last_refresh, datetime)
        assert cache._last_refresh.tzinfo == UTC

    @pytest.mark.asyncio
    async def test_search_no_results(self, populated_cache):
        """Test search returns empty list when no matches."""
        results = populated_cache.search_tables("nonexistent", limit=10)
        assert results == []

        results = populated_cache.search_columns("nonexistent", limit=10)
        assert results == []
